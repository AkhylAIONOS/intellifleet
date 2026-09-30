from .eligibility import evaluate
from .models import EligibilityInput


def recovery(simulation):
    request = EligibilityInput(origin_station=simulation.request.origin_station, gateway=simulation.request.gateway,
                               shipment_ready_datetime=simulation.now, simulation_date=simulation.request.simulation_date)
    result = evaluate(simulation.schedules, request)
    alternatives = [c for c in result['candidates'] if c['eligible'] and c['schedule_id'] != simulation.selected['schedule_id']]
    in_transit = simulation.progress > 0
    response = {
        'problem': 'Synthetic disruption affects the selected movement',
        'impact': f"Arrival shifts by {(simulation.current_eta-simulation.selected['eta']).total_seconds()/60:g} minutes from schedule",
        'revised_eta': simulation.current_eta.isoformat(),
        'eligible_alternatives': alternatives,
        'alternatives_condition': 'Origin-ready services only; return/transfer feasibility is unverified' if in_transit else 'Origin-ready schedule candidates',
        'recommended_action': 'Notify gateway of revised ETA and confirm onward handover; continue monitoring. No automatic reroute.' if in_transit or not alternatives else 'Review the next eligible provided service with an operator before reassignment.',
        'reason': 'No verified recovery vehicle, capacity, transfer geometry or onward schedule is supplied. Generic planning would invent feasibility. No future operating calendar is assumed.',
        'planning_status': 'Not invoked: FedEx schedule alone lacks compatible capacity/cost/network inputs',
        'automatically_executed': False,
    }

    context=getattr(simulation,'planning_context',None)
    if context:
        from backend.planning.service import PlanningService
        request=context['request'].model_copy(update={'objective':'fastest'})
        result=PlanningService(':memory:').plan(context['owner'],request,context['network'])
        plan=result.get('recommended_plan')
        response['planning_status']='Hypothetical origin recovery evaluated against loaded network; no fleet reserved'
        response['hypothetical_network_recovery']={'data_source':simulation.data_source,'origin_transfer_unverified':in_transit,
            'plan_id':plan['plan_id'] if plan else None,'duration_hours':plan['duration_hours'] if plan else None,
            'operational_cost':plan['operational_cost'] if plan else None,'vehicles':plan['vehicles'] if plan else []}
        response['reason']='Loaded network capacity, cost, risk and travel time were calculated by the existing planner. In-transit transfer and return-to-origin remain unverified.'
    return response


def evaluate_compatible_plan(planning_request, verified_network, user_id):
    """Explicit adapter for callers with a verified UniFleet network and shipment.

    Schedule-only simulations intentionally cannot invoke this. Returned plans
    still require separate FedEx schedule validation before being actionable.
    """
    from backend.planning.service import PlanningService
    if not all(verified_network.get(k) for k in ('routes', 'warehouses', 'vehicles')):
        raise ValueError('Verified routes, warehouses and vehicles are required')
    return {'planning_result': PlanningService(':memory:').plan(user_id, planning_request, verified_network),
            'schedule_validation_required': True, 'automatically_executed': False}


def create_alert(simulation, event):
    return {'alert_id': event['event_id'], 'severity': event['severity'],
            'title': f"{event['event_type']} DETECTED", 'shipment_id': simulation.request.shipment_id,
            'origin': simulation.request.origin_station, 'destination': simulation.request.gateway,
            'previous_eta': event['original_eta'], 'delay_minutes': event['expected_delay_minutes'],
            'synthetic_data': True, **recovery(simulation)}
