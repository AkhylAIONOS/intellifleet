import csv
import io
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from backend.routes.auth import get_current_user
from backend.fedex.models import EligibilityInput, SimulationInput
from backend.fedex.eligibility import evaluate, TEMPLATE_NOTICE
from backend.fedex.telemetry import runtime
from backend.fedex.simulator import DEMO_LOCATIONS
from .data import synthetic_schedules
from .service import movements, start_demo

router=APIRouter(prefix='/operations',tags=['UniFleet Operations'])
# Same ephemeral, owner-scoped lifecycle as simulation runtime.
custom_schedules={}


def schedules_for(owner,source='SYNTHETIC'):
    if source=='FEDEX':
        from backend.fedex.routes import schedules
        return schedules()
    return custom_schedules.get(owner) or synthetic_schedules()


@router.get('/schedules')
def summary(source: Literal['SYNTHETIC','FEDEX']='SYNTHETIC', user=Depends(get_current_user)):
    ss=schedules_for(user['user_id'],source)
    return {'schedules':ss,'schedule_notice':TEMPLATE_NOTICE,'lanes':[
        {'origin_station':a,'gateway':b,'simulation_supported':any(s.origin_coordinates or (a in DEMO_LOCATIONS and b in DEMO_LOCATIONS) for s in ss if s.origin_station==a and s.gateway==b)}
        for a,b in sorted({(s.origin_station,s.gateway) for s in ss})]}


@router.post('/schedules/import')
async def upload(file: UploadFile=File(...), user=Depends(get_current_user)):
    try:
        records=list(csv.DictReader(io.StringIO((await file.read()).decode('utf-8-sig'))))
        if not records or len(records)>5000: raise ValueError('Provide 1–5000 synthetic schedule rows')
        parsed=synthetic_schedules(records)
    except (ValueError,KeyError,TypeError) as exc: raise HTTPException(422,str(exc)) from exc
    custom_schedules[user['user_id']]=parsed
    return {'success':True,'rows':len(parsed),'data_source':'SYNTHETIC_SCHEDULE'}


@router.get('/eligible-services')
def eligible(request: EligibilityInput=Depends(),source: Literal['SYNTHETIC','FEDEX']='SYNTHETIC',user=Depends(get_current_user)):
    return evaluate(schedules_for(user['user_id'],source),request)


@router.post('/simulations',status_code=201)
def create(request: SimulationInput,source: Literal['SYNTHETIC','FEDEX']='SYNTHETIC',user=Depends(get_current_user)):
    try: return runtime.create(user['user_id'],request,schedules_for(user['user_id'],source)).snapshot()
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc


@router.get('/movements')
def all_movements(user=Depends(get_current_user)):
    ss=list(schedules_for(user['user_id']))
    try: ss+=schedules_for(user['user_id'],'FEDEX')
    except HTTPException: pass
    # Only known city mappings are positioned; other templates remain in the table.
    ss=[s.model_copy(update={'origin_coordinates':s.origin_coordinates or DEMO_LOCATIONS.get(s.origin_station),
                             'destination_coordinates':s.destination_coordinates or DEMO_LOCATIONS.get(s.gateway)}) for s in ss]
    return movements(user['user_id'],ss)


class DemoInput(BaseModel):
    count: Literal[10,50,100]=10
    seed: int=42


@router.post('/demo')
def demo(request: DemoInput,user=Depends(get_current_user)):
    try: return start_demo(user['user_id'],request.count,request.seed)
    except (ValueError,KeyError) as exc: raise HTTPException(422,str(exc)) from exc


class RouteInput(BaseModel):
    origin: str
    destination: str
    weight: float = 6000


@router.post('/route-simulation',status_code=201)
def route_simulation(request: RouteInput,user=Depends(get_current_user)):
    from .service import start_route
    try: return start_route(user['user_id'],request.origin,request.destination,request.weight)
    except (ValueError,KeyError) as exc: raise HTTPException(422,str(exc)) from exc
