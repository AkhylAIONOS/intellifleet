from backend.operations.road_routing_engine import RoadRoutingError
import csv
import io
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
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


def _balanced_builtin_synthetic_schedules():
    """
    Balanced built-in Synthetic Udaipur -> Delhi schedule.

    AIR closes at 16:30.
    SURFACE remains available until 21:30.

    Selection itself is still performed by the normal
    earliest-arrival-among-eligible-services engine.
    """

    schedules = list(synthetic_schedules())

    origin = 'SYN-UDR-STN'
    gateway = 'SYN-DEL-GTW'

    air_number = 0
    surface_number = 0
    balanced = []

    for schedule in schedules:

        is_demo_lane = (
            schedule.origin_station == origin
            and schedule.gateway == gateway
        )

        if not is_demo_lane:
            balanced.append(schedule)
            continue

        mode = str(schedule.mode).upper()


        # ====================================================
        # AIR
        # All AIR services close at 16:30.
        #
        # This prevents AIR Run 2 from remaining eligible at
        # 18:00 and incorrectly defeating Surface.
        # ====================================================

        if mode == 'AIR':
            air_number += 1

            updates = {
                'cutoff_minutes': 16 * 60 + 30,
            }

            # Canonical first AIR service
            if air_number == 1:
                updates.update({
                    'etd_minutes': 20 * 60,
                    'eta_minutes': 21 * 60 + 20,
                    'eta_day_offset': 0,
                    'transit_minutes': 80,
                })

            schedule = schedule.model_copy(update=updates)


        # ====================================================
        # SURFACE
        # Surface remains eligible after AIR closes.
        # ====================================================

        elif mode in {'SURFACE', 'ROAD', 'GROUND'}:
            surface_number += 1

            updates = {
                'cutoff_minutes': 21 * 60 + 30,
            }

            # Canonical first Surface service
            if surface_number == 1:
                updates.update({
                    'etd_minutes': 22 * 60,
                    'eta_minutes': 12 * 60,
                    'eta_day_offset': 1,
                    'transit_minutes': 14 * 60,
                })

            schedule = schedule.model_copy(update=updates)

        balanced.append(schedule)

    return balanced


def schedules_for(owner,source='SYNTHETIC'):

    # --------------------------------------------------------
    # FEDEX SOURCE
    #
    # Keep the actual FedEx workbook authoritative.
    # Do not fabricate or overwrite FedEx cutoff/ETD/ETA.
    # --------------------------------------------------------

    if source == 'FEDEX':
        from backend.fedex.routes import schedules
        return schedules()


    # --------------------------------------------------------
    # USER-UPLOADED SYNTHETIC SCHEDULE
    #
    # User data remains authoritative too.
    # --------------------------------------------------------

    custom = custom_schedules.get(owner)

    if custom:
        return custom


    # --------------------------------------------------------
    # BUILT-IN SYNTHETIC DEMO
    # --------------------------------------------------------

    return _balanced_builtin_synthetic_schedules()


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
    except RoadRoutingError as exc: raise HTTPException(503 if exc.code=='ROAD_ROUTE_UNAVAILABLE' else 422,str(exc)) from exc
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc


@router.get('/movements')
def all_movements(user=Depends(get_current_user), include_geometry: bool=True):
    ss=list(schedules_for(user['user_id']))
    try: ss+=schedules_for(user['user_id'],'FEDEX')
    except HTTPException: pass
    # Only known city mappings are positioned; other templates remain in the table.
    ss=[s.model_copy(update={'origin_coordinates':s.origin_coordinates or DEMO_LOCATIONS.get(s.origin_station),
                             'destination_coordinates':s.destination_coordinates or DEMO_LOCATIONS.get(s.gateway)}) for s in ss]
    return movements(user['user_id'],ss,include_geometry=include_geometry)


class DemoInput(BaseModel):
    count: Literal[10,50,100]=10
    seed: int=42
    reuse_existing: bool=False


@router.post('/movements/initialize')
def initialize_movements(user=Depends(get_current_user)):
    from .fleet import initialize
    try: return initialize(user['user_id'])
    except (ValueError, KeyError) as exc: raise HTTPException(422,str(exc)) from exc


@router.post('/demo')
def demo(request: DemoInput,user=Depends(get_current_user)):
    try: return start_demo(user['user_id'],request.count,request.seed,request.reuse_existing)
    except RoadRoutingError as exc: raise HTTPException(503 if exc.code=='ROAD_ROUTE_UNAVAILABLE' else 422,str(exc)) from exc
    except (ValueError,KeyError) as exc: raise HTTPException(422,str(exc)) from exc


class RouteInput(BaseModel):
    origin: str
    destination: str
    weight: float = Field(gt=0, allow_inf_nan=False)


@router.post('/plan-journeys/reset-all')
def reset_plan_journeys(user=Depends(get_current_user)):
    from .service import reset_plan_movements
    return reset_plan_movements(user['user_id'])


@router.post('/plan-journeys/{plan_id}',status_code=201)
def plan_journey(plan_id: str,user=Depends(get_current_user)):
    from .plan_journeys import start
    try: return start(user['user_id'],plan_id)
    except KeyError as exc: raise HTTPException(404,str(exc)) from exc
    except RoadRoutingError as exc: raise HTTPException(503,str(exc)) from exc
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc


@router.post('/route-simulation',status_code=201)
def route_simulation(request: RouteInput,user=Depends(get_current_user)):
    from .service import start_route
    try: return start_route(user['user_id'],request.origin,request.destination,request.weight)
    except RoadRoutingError as exc: raise HTTPException(503 if exc.code=='ROAD_ROUTE_UNAVAILABLE' else 422,str(exc)) from exc
    except (ValueError,KeyError) as exc: raise HTTPException(422,str(exc)) from exc
