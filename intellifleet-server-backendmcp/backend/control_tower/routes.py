from datetime import date, datetime
from typing import Literal
import asyncio
import secrets
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field, EmailStr, field_validator
from backend.routes.auth import get_current_user
from backend.fedex.models import SimulationInput
from backend.operations.road_routing_engine import RoadRoutingError
from .service import ControlTower
from .status import timestamp
from backend.config.config import settings

router=APIRouter(prefix='/operations',tags=['FedEx Control Tower'])
service=ControlTower()


class ImportInput(BaseModel):
    service_date: date


class PlaybackInput(SimulationInput):
    demo_playback: bool = False
    autoplay: bool = False


class SyntheticActionInput(BaseModel):
    action: Literal['delay10','delay30','arrive']


class CriticalInput(BaseModel):
    critical: bool


class RecipientInput(BaseModel):
    emails: list[EmailStr] = Field(max_length=1)


def alert_identity(user=Depends(get_current_user), x_unifleet_demo_session_id: str | None=Header(default=None)):
    # Account remains authenticated; the unguessable browser capability scopes demo alerts.
    # Replace this dependency with authenticated_user_id when personal login is introduced.
    if not x_unifleet_demo_session_id:
        raise HTTPException(422, 'Browser session identity required')
    try:
        session=UUID(x_unifleet_demo_session_id)
        if session.version != 4:
            raise ValueError('Random session required')
        identity=str(session)
    except ValueError:
        raise HTTPException(422, 'Invalid browser session identity')
    return user['user_id'], identity


class ScanInput(BaseModel):
    event_id: str = Field(min_length=1,max_length=160)
    event_type: Literal['DEPARTURE','ARRIVAL','ETA_UPDATE','LOCATION']
    source: Literal['FEDEX_SCAN','SYNTHETIC_TELEMETRY']
    event_at: datetime
    current_eta: datetime | None = None
    reason: str = Field(default='Operational event',max_length=500)
    latitude: float | None = Field(default=None,ge=-90,le=90,allow_inf_nan=False)
    longitude: float | None = Field(default=None,ge=-180,le=180,allow_inf_nan=False)
    carrier: str | None = Field(default=None,max_length=100)

    @field_validator('event_at','current_eta')
    @classmethod
    def aware(cls,value):
        if value is not None:
            timestamp(value)
        return value


class ConInput(BaseModel):
    con_number: str = Field(min_length=1,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    run_id: str = Field(min_length=1,max_length=100)
    event_id: str = Field(min_length=1,max_length=160)
    source: Literal['FEDEX_SCAN','SYNTHETIC_TELEMETRY']
    event_at: datetime

    @field_validator('event_at')
    @classmethod
    def aware(cls,value):
        timestamp(value)
        return value


def current_source_run(row):
    from backend.client_network import network
    source=next((s for s in network()['schedules'] if s['schedule_id']==row.get('schedule_id')),None)
    given=row.get('schedule',{})
    return source is not None and all(given.get(k)==source.get(k) for k in ('origin_station','gateway','lane','run','mode','service','source'))


def enforce_source(value):
    if isinstance(value,dict):
        if 'schedule' in value and 'schedule_id' in value and not current_source_run(value):
            raise HTTPException(410,'This archived run is not part of the current client workbook')
        if 'run' in value and isinstance(value['run'],dict):enforce_source(value['run'])
    return value


def invoke(fn,*args,**kwargs):
    try:
        return enforce_source(fn(*args,**kwargs))
    except KeyError as exc:
        raise HTTPException(404,str(exc)) from exc
    except (ValueError,TypeError) as exc:
        raise HTTPException(422,str(exc)) from exc
    except RoadRoutingError as exc:
        raise HTTPException(503,'Road geometry unavailable; existing run retained') from exc


def verify_ingestion(source,token):
    if source!='FEDEX_SCAN':
        return
    configured=settings.FEDEX_SCAN_INGEST_TOKEN
    if not configured:
        raise HTTPException(503,'Real FedEx scan ingestion is not configured')
    if not token or not secrets.compare_digest(token,configured):
        raise HTTPException(403,'Invalid scan ingestion credential')


@router.post('/control-tower/import')
def import_plan(request: ImportInput,user=Depends(get_current_user)):
    from backend.fedex.routes import schedules
    return {'runs':invoke(service.import_network,user['user_id'],schedules(),request.service_date)}


class BatchPlaybackInput(BaseModel):
    service_date: date


@router.post('/control-tower/playback')
def playback(request:BatchPlaybackInput,user=Depends(get_current_user)):
    from backend.fedex.models import DEFAULT_PLAYBACK_SPEED
    rows=[r for r in service.runs(user['user_id'],request.service_date) if current_source_run(r)]
    started=[];skipped=[]
    for row in rows:
        if not row['schedule']['valid']:
            skipped.append({'run_id':row['run_id'],'reason':'Source schedule requires validation'});continue
        try:
            result=service.link_simulation(user['user_id'],row['run_id'],PlaybackInput(
                origin_station=row['schedule']['origin_station'],gateway=row['schedule']['gateway'],
                simulation_date=request.service_date,shipment_ready_datetime=datetime.combine(request.service_date,datetime.min.time()),
                demo_playback=True,autoplay=True,schedule_based_geometry=True))
            started.append(result['run_id'])
        except (ValueError,KeyError) as exc:skipped.append({'run_id':row['run_id'],'reason':str(exc)})
    return {'started':started,'skipped':skipped,'playback_speed':DEFAULT_PLAYBACK_SPEED,
            'notice':'Simulated movement along approximate city-centre lanes; source ETD/ETA unchanged.'}


@router.get('/control-tower/runs')
def runs(service_date:date|None=None,mode:Literal['AIR','SURFACE','RAIL']|None=None,status:str|None=None,
         critical:bool|None=None,search:str='',sort:Literal['lane','status','eta']='lane',offset:int=0,limit:int=100,user=Depends(get_current_user)):
    if offset<0 or not 1<=limit<=200:
        raise HTTPException(422,'Invalid pagination')
    rows=[r for r in service.runs(user['user_id'],service_date,mode,status,critical,search) if current_source_run(r)]
    rows.sort(key=lambda r:r['status'] if sort=='status' else (r['current_eta'] or '') if sort=='eta' else r['schedule']['lane'])
    return {'runs':rows[offset:offset+limit],'total':len(rows),'source':'FEDEX_SOURCE'}


@router.get('/control-tower/summary')
def summary(service_date:date|None=None,user=Depends(get_current_user)):
    return service.summary([r for r in service.runs(user['user_id'],service_date) if current_source_run(r)])


@router.get('/control-tower/runs/{run_id}')
def detail(run_id:str,user=Depends(get_current_user)):
    return invoke(service.detail,user['user_id'],run_id)


@router.put('/critical-lanes/{run_id}')
def critical(run_id:str,request:CriticalInput,user=Depends(get_current_user)):
    return invoke(service.mark_critical,user['user_id'],run_id,request.critical)


@router.post('/control-tower/runs/{run_id}/events')
def event(run_id:str,request:ScanInput,user=Depends(get_current_user),x_fedex_ingest_token:str|None=Header(default=None)):
    verify_ingestion(request.source,x_fedex_ingest_token)
    return invoke(service.event,user['user_id'],run_id,request.model_dump(mode='json'))


@router.post('/control-tower/runs/{run_id}/simulation')
def simulation(run_id:str,request:PlaybackInput,user=Depends(get_current_user)):
    return invoke(service.link_simulation,user['user_id'],run_id,request)


@router.post('/control-tower/runs/{run_id}/synthetic-action')
def synthetic_action(run_id:str,request:SyntheticActionInput,user=Depends(get_current_user)):
    return invoke(service.synthetic_action,user['user_id'],run_id,request.action)


@router.get('/alerts/recipients')
def recipients(scope=Depends(alert_identity)):
    email=service.personal_email(*scope)
    return {'emails':[email] if email else []}


@router.put('/alerts/recipients')
def set_recipients(request:RecipientInput,scope=Depends(alert_identity)):
    email=service.personal_email(*scope,str(request.emails[0]) if request.emails else None)
    return {'emails':[email] if email else []}


@router.get('/alerts')
def alerts(scope=Depends(alert_identity)):
    return {'alerts':service.personal_alerts(*scope),
        'delivery_enabled':settings.FEDEX_ALERT_DELIVERY_ENABLED}


@router.post('/cons/events')
def con_event(request:ConInput,user=Depends(get_current_user),x_fedex_ingest_token:str|None=Header(default=None)):
    verify_ingestion(request.source,x_fedex_ingest_token)
    return invoke(service.con_event,user['user_id'],request.model_dump(mode='json'))


@router.get('/cons/{con_number}')
def con(con_number:str,user=Depends(get_current_user)):
    return invoke(service.con,user['user_id'],con_number)


async def monitor():
    """Separate low-frequency business monitor; never runs per telemetry tick."""
    while True:
        try:
            with service.db() as conn:
                owners=[r[0] for r in conn.execute('SELECT DISTINCT owner FROM ct_runs')]
            for owner in owners:
                await asyncio.to_thread(service.observe,owner)
            await service.deliver(enabled=settings.FEDEX_ALERT_DELIVERY_ENABLED)
        except Exception:
            from backend.config.logger import logger
            logger.warning('Control Tower monitor unavailable; operational records retained')
        await asyncio.sleep(10)
