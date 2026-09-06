from fastapi import APIRouter, Depends, HTTPException

from backend.routes.auth import get_current_user
from .models import (BreakdownRequest, ConsolidationRequest, ExpansionRequest, FulfilmentRequest,
                     FutureReplanRequest, MultiStopRequest, PlanningRequest, ScenarioCreateRequest,
                     ShipmentScheduleRequest, TransportScopeRequest)
from .service import PlanningService

router = APIRouter(prefix="/planning", tags=["Unified Planning"])
service = PlanningService()


@router.post("/plans")
def create_plan(request: PlanningRequest, current_user=Depends(get_current_user)):
    return service.plan(current_user["user_id"], request)

@router.post("/compare-modes")
def compare_modes(request: PlanningRequest,current_user=Depends(get_current_user)):
    return service.compare_modes(current_user["user_id"],request)

@router.post("/disruption-mitigation")
def disruption_mitigation(request:ScenarioCreateRequest,current_user=Depends(get_current_user)):
    return service.disruption_mitigation(current_user["user_id"],request.planning_request,request.changes)


@router.post("/scenarios")
def create_scenario(request: ScenarioCreateRequest, current_user=Depends(get_current_user)):
    return service.create_scenario(current_user["user_id"], request.planning_request, request.changes)


@router.post("/scenarios/{scenario_id}/{action}")
def scenario_action(scenario_id: str, action: str, current_user=Depends(get_current_user)):
    if action not in {"apply", "discard"}:
        raise HTTPException(400, "action must be apply or discard")
    try:
        return service.scenario_action(current_user["user_id"], scenario_id, action)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/expansion")
def expansion(request: ExpansionRequest, current_user=Depends(get_current_user)):
    return service.expansion(request)


@router.post("/consolidation")
def consolidation(request: ConsolidationRequest, current_user=Depends(get_current_user)):
    return service.consolidate(current_user["user_id"], [x.model_dump(mode="json") for x in request.shipments])

@router.get("/warehouse-capacity")
def warehouse_capacity(current_user=Depends(get_current_user)):
    return service.warehouse_capacity(current_user["user_id"])

@router.post("/fulfilment")
def fulfilment(request: FulfilmentRequest,current_user=Depends(get_current_user)):
    return service.fulfilment(current_user["user_id"],request.destination,request.quantity,request.weight_kg,request.objective,request.deadline)

@router.post("/breakdown-recovery")
def breakdown(request: BreakdownRequest,current_user=Depends(get_current_user)):
    return service.breakdown_recovery(current_user["user_id"],request.vehicle_label,request.current_location,request.destination,request.remaining_weight_kg,request.deadline,request.plan_id,request.shipment_id)

@router.post("/future-replan")
def future_replan(request: FutureReplanRequest,current_user=Depends(get_current_user)):
    return service.future_replan(current_user["user_id"],request.delayed_vehicle_label,request.delay_hours)

@router.post("/multi-stop")
def multi_stop(request: MultiStopRequest,current_user=Depends(get_current_user)):
    return service.optimize_stops(current_user["user_id"],request.source,request.destination,request.stops,request.shipment.model_dump(),request.objective)

@router.post("/transport-scope")
def transport_scope(request:TransportScopeRequest,current_user=Depends(get_current_user)):
    return service.transport_scope(request.source_country,request.destination_country)

@router.post("/global-plan")
def global_plan(request:PlanningRequest,current_user=Depends(get_current_user)):
    try: return service.global_plan(current_user["user_id"],request)
    except ValueError as exc: raise HTTPException(422,str(exc)) from exc

@router.post("/shipments")
def schedule_shipment(request:ShipmentScheduleRequest,current_user=Depends(get_current_user)):
    return service.schedule_shipment(current_user["user_id"],request.model_dump(mode="json"))
