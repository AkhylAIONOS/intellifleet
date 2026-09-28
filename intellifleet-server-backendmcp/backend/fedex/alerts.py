from .eligibility import evaluate
from .models import EligibilityInput


def recovery(simulation):
    request = EligibilityInput(origin_station=simulation.request.origin_station, gateway=simulation.request.gateway,
                               shipment_ready_datetime=simulation.now, simulation_date=simulation.request.simulation_date)
    result = evaluate(simulation.schedules, request)
    alternatives = [c for c in result['candidates'] if c['eligible'] and c['schedule_id'] != simulation.selected['schedule_id']]
    in_transit = simulation.progress > 0
    return {
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
            'synthetic_data': True, **recovery(simulation)}
