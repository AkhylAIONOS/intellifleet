from backend.operations.road_routing_engine import RoadRoutingError
import asyncio
import json
import zipfile
from xml.etree.ElementTree import ParseError
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from backend.routes.auth import get_current_user
from .disruptions import inject
from .eligibility import evaluate, TEMPLATE_NOTICE
from .importer import load_schedules
from .models import ControlInput, DisruptionInput, EligibilityInput, SimulationInput
from .simulator import DEMO_LOCATIONS
from .telemetry import runtime

router = APIRouter(prefix='/fedex', tags=['FedEx Simulation'])


@lru_cache(maxsize=1)
def schedules():
    try:
        from backend.client_network import CITY_CENTRES
        return [s.model_copy(update={'origin_coordinates':CITY_CENTRES.get(s.origin_station[:3]),
                                    'destination_coordinates':CITY_CENTRES.get(s.gateway[:3])}) for s in load_schedules()]
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ParseError, IndexError) as exc:
        raise HTTPException(503, 'FedEx workbook unavailable or invalid; configure FEDEX_WORKBOOK_PATH and restart') from exc


def owned(user, simulation_id):
    try:
        return runtime.get(user['user_id'], simulation_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get('/schedules')
async def summary(user=Depends(get_current_user)):
    ss = schedules()
    lanes = sorted({(s.origin_station, s.gateway) for s in ss})
    from .models import DEFAULT_PLAYBACK_SPEED
    return {'playback_speed':DEFAULT_PLAYBACK_SPEED,'schedules': ss, 'schedule_notice': TEMPLATE_NOTICE,
            'lanes': [{'origin_station':a, 'gateway':b, 'simulation_supported':any(s.origin_station==a and s.gateway==b and s.origin_coordinates and s.destination_coordinates for s in ss)} for a,b in lanes],
            'runtime': 'Single-process ephemeral demo; reset on restart; six-hour retention',
            'synthetic_location_mapping': {}}


@router.get('/eligible-services')
async def eligible(request: EligibilityInput = Depends(), user=Depends(get_current_user)):
    return evaluate(schedules(), request)


@router.post('/simulations', status_code=201)
def create(request: SimulationInput, user=Depends(get_current_user)):
    try:
        return runtime.create(user['user_id'], request, schedules()).snapshot()
    except RoadRoutingError as exc:
        raise HTTPException(503 if exc.code=='ROAD_ROUTE_UNAVAILABLE' else 422, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/simulations/{simulation_id}')
async def state(simulation_id: str, user=Depends(get_current_user)):
    return owned(user, simulation_id).snapshot()


@router.post('/simulations/{simulation_id}/events')
async def event(simulation_id: str, request: DisruptionInput, user=Depends(get_current_user)):
    s = owned(user, simulation_id)
    try:
        inject(s, request)
        return s.snapshot()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/simulations/{simulation_id}/control')
async def control(simulation_id: str, request: ControlInput, user=Depends(get_current_user)):
    s = owned(user, simulation_id)
    if request.action == 'reset':
        runtime.remove(user['user_id'], simulation_id)
        return {'reset': True, 'simulation_id': simulation_id}
    try:
        return s.control(request.action, runtime.clock(), request.speed)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/simulations/{simulation_id}/stream')
async def stream(simulation_id: str, request: Request, user=Depends(get_current_user)):
    owned(user, simulation_id)

    async def events():
        # Full snapshots make reconnect idempotent; event history is bounded and included.
        # Connections rotate at five minutes so the client reauthenticates.
        started = runtime.clock()
        while runtime.clock()-started < 300:
            if await request.is_disconnected():
                break
            try:
                snapshot = owned(user, simulation_id).snapshot()
            except HTTPException:
                yield 'event: expired\ndata: {}\n\n'
                break
            data = json.dumps(jsonable_encoder(snapshot), separators=(',', ':'))
            yield f'id: {snapshot["sequence"]}\nevent: telemetry\ndata: {data}\n\n'
            if snapshot['stopped'] or snapshot['status'] == 'ARRIVED_AT_GTW':
                break
            await asyncio.sleep(.5)
    return StreamingResponse(events(), media_type='text/event-stream', headers={
        'Cache-Control':'no-cache', 'X-Accel-Buffering':'no', 'Connection':'keep-alive'})
