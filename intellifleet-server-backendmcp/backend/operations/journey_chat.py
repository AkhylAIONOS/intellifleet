"""Deterministic operational actions before the read-only status adapter."""
from copy import deepcopy
from datetime import datetime, timedelta
import re
from backend.planning.lifecycle import resolve, is_action, is_new, record, route_alternative, explicit_live_recovery
from backend.planning.models import PlanningRequest
from backend.planning.service import PlanningService


async def answer(owner, message, context, selected_id=None):
    # A complete explicit Plan/Create FROM→TO request is always a new shipment.
    # Never resolve it against an existing selected journey.
    if re.search(
        r'^\s*(?:please\s+)?(?:plan|create)\b.*\bfrom\s+.+?\s+to\s+.+',
        message,
        re.I,
    ):
        return None

    if not is_action(message) or is_new(message) or re.search(r'\b(?:what if|what happens|hypothetical)\b', message, re.I):
        return None
    if not context and re.search(r'\b(current|same|this|assigned)\b', message, re.I):
        return {'success': True, 'response': 'No selected shipment in this chat. Plan a shipment or provide its ID.', 'actions': []}
    # Independent cheapest/fastest shipment requests still use normal extraction.
    if not context or (re.search(r'\bfor a\b|\bfrom\b', message, re.I) and not re.search(r'\b(current|same|this|replan|blocked|disrupted)\b', message, re.I)):
        return None
    selected, error = resolve(context, message, selected_id)
    def reply(text, actions=None):
        return {'success': True, 'response': text, 'actions': actions or []}
    if error:
        return reply(error)
    from backend.config.redis import set_active_planning_context
    from backend.fedex.telemetry import runtime
    from backend.operations.plan_journeys import start, canonical_identity
    from backend.agents.supervisor import _context_from_result, _format_planning_result, _attach_replan_baseline
    selected.update(canonical_identity(owner, selected['selected_plan_id'], selected.get('movement_id')))
    selected.setdefault('journeys', {})
    try:
        # Mutations address the selected runtime entity directly. Replaying a
        # result revision is not a prerequisite for applying a delay.
        if selected.get('movement_id'):
            sim = runtime.get(owner, selected['movement_id'])
        else:
            snapshot = start(owner, selected['selected_plan_id'])
            sim = runtime.get(owner, snapshot['simulation_id'])
    except (KeyError, ValueError, RuntimeError) as exc:
        return reply('Cannot apply an operational change: ' + str(exc))
    if sim.stopped or sim.progress >= 1:
        return reply('This movement is stopped or completed; no change was applied.')
    delay = re.search(r'(\d+(?:\.\d+)?)\s*(?:minute|min)s?\b', message, re.I)
    if delay and re.search(r'\bdelay(?:ed)?\b', message, re.I):
        minutes = float(delay.group(1))
        original = sim.current_eta
        sim.current_eta += timedelta(minutes=minutes)
        sim.hold_until = max(sim.now, sim.hold_until or sim.now) + timedelta(minutes=minutes)
        sim.status = 'DELAYED'
        sim.sequence += 1
        sim.events.append({'event_type':'DELAY', 'expected_delay_minutes':minutes,
                           'original_eta':original.isoformat(), 'revised_eta':sim.current_eta.isoformat()})
        selected.update(eta=sim.current_eta.isoformat(), delay_minutes=sim.snapshot()['delay_minutes'])
        selected['journeys'][selected['journey_id']] = {k:deepcopy(v) for k,v in selected.items() if k != 'journeys'}
        await set_active_planning_context(owner, selected)
        deadline = selected.get('deadline')
        impact = f"SLA delay: {max(0, (sim.current_eta-datetime.fromisoformat(deadline)).total_seconds()/60):g} minutes." if deadline else 'SLA impact cannot be calculated without a deadline.'
        return reply(f"Shipment {sim.request.shipment_id}: added {minutes:g} minutes; revised ETA {sim.current_eta.isoformat()}. {impact} Mitigation: retain the verified route and monitor the delay; no verified faster recovery has been calculated.",
                     [{'type':'movement_updated','data':sim.snapshot()}])
    breakdown = bool(re.search(r'\b(breakdown|broke down|broken down|change (?:the |assigned )?(?:truck|vehicle))\b', message, re.I))
    live_recovery = explicit_live_recovery(message)
    unavailable = bool(re.search(r'\b(blocked|disrupted|unavailable|closed|cancelled|canceled)\b', message, re.I))
    outage = route_alternative(message) or unavailable
    objective_alternative = bool(re.search(
        r'\b(?:cheapest|fastest|lowest[ -]risk)\s+(?:feasible\s+)?alternative\b',
        message,
        re.I,
    ))
    changes = deepcopy(selected.get('planning_changes') or {})
    request = deepcopy(selected['planning_request'])
    service = PlanningService()
    from backend.agents.supervisor import _objective_from_message
    objective = _objective_from_message(message)
    if objective:request['objective']=objective
    async def retain_constraints():
        selected['planning_changes'] = deepcopy(changes)
        selected['journeys'][selected['journey_id']] = {k:deepcopy(v) for k,v in selected.items() if k != 'journeys'}
        await set_active_planning_context(owner, selected)
    if breakdown:
        vehicles = selected.get('assigned_vehicles') or []
        if len(vehicles) != 1:
            return reply('Recovery requires the failed vehicle ID; this journey has multiple assigned vehicles.')
        failed = vehicles[0]['label']
        changes['unavailable_vehicles'] = list(set(changes.get('unavailable_vehicles', []) + [failed]))
        sim.paused = True
        await retain_constraints()
        if sim.progress > 0:
            return reply(f"Breakdown recovery for {sim.request.shipment_id}: {failed} is unavailable for this scenario; movement paused at progress {sim.progress:.1%}. Recovery is infeasible with currently verified data: mid-route transfer locations and access routes are not supplied. Provide a verified network recovery location to calculate replacement vehicle, ETA, cost and risk.", [{'type':'movement_updated','data':sim.snapshot()}])
        # At the verified origin, existing recovery planner checks approach and continuation.
        result = service.breakdown_recovery(owner, failed, request['source'], request['destination'], request['shipment']['weight_kg'], request.get('deadline'), changes=changes)
        result['planning_request'] = request
        result['planning_operation'] = 'breakdown_recovery'
        result['applied_changes'] = changes
    else:
        # Optimizing alternatives again retains the original exclusions; it does
        # not declare the newly selected alternative blocked without that request.
        exclude_current = unavailable or (outage and not (objective_alternative and changes.get('blocked_route_ids')))
        if exclude_current:
            legs = selected.get('route_legs') or []
            if re.search(
                r'\b(?:air|airway|flight|air service|selected air service)\b',
                message,
                re.I,
            ):
                legs = [
                    leg for leg in legs
                    if str(leg.get('route_type') or '').casefold() in {'air', 'flight'}
                ]

            elif re.search(r'\b(ground|road)\b', message, re.I):
                legs = [
                    leg for leg in legs
                    if str(leg.get('route_type') or '').casefold() == 'road'
                ]
            if not legs:
                requested_mode = (
                    'Ground/Road'
                    if re.search(r'\b(?:ground|road)\b', message, re.I)
                    else 'Air'
                    if re.search(r'\bair\b', message, re.I)
                    else 'requested'
                )
                return reply(
                    f'The selected shipment has no matching {requested_mode} leg. '
                    'Name the shipment lane you want to replan or select that movement.'
                )
            # Route IDs distinguish Air and Ground sharing the same endpoints.
            changes['blocked_route_ids'] = list(set(
                changes.get('blocked_route_ids', [])
                + [
                    leg['route_id']
                    for leg in legs
                    if leg.get('route_id') is not None
                ]
            ))

        if re.search(r'\bcompare\b', message, re.I) and re.search(r'\bair\b', message, re.I):
            request['allowed_modes'] = ['road','air','multimodal']
        for objective in ('fastest','cheapest','lowest-risk'):
            if objective in message.casefold().replace('lowest risk','lowest-risk'): request['objective'] = objective
        from backend.planning.recovery import recover_air, strict_air_only
        air_recovery = (outage or bool(changes.get('blocked_route_ids'))) and any(l.get('route_type') == 'air' for l in selected.get('route_legs', []))
        if air_recovery:
            # Explicit instructions in the current message override historical
            # Air-only preference. This allows:
            #   "keep it Air-only" -> strict Air recovery
            # followed later by:
            #   "you may use Ground and Air" -> flexible recovery.
            explicit_flexible = bool(re.search(
                r'\b(?:may|can|allow|use)\s+(?:ground|road).*\bair\b'
                r'|\b(?:ground|road)\s*(?:and|\+|/|→|->)\s*air\b'
                r'|\bair\s*(?:and|\+|/|→|->)\s*(?:ground|road)\b'
                r'|\bmultimodal\b',
                message,
                re.I,
            ))
            if explicit_flexible:
                strict = False
            elif strict_air_only(message):
                strict = True
            else:
                strict = bool(selected.get('strict_air_only', False))

            selected['strict_air_only'] = bool(strict)
            result = recover_air(service, owner, request, changes, message, strict=strict)
        else:
            result = service.plan(owner, PlanningRequest(**request), changes=changes)
        result['planning_operation'] = 'route_alternatives'
        result['applied_changes'] = changes
    revised = result.get('recommended_plan') or result.get('recovery_plan')
    if outage:
        await retain_constraints()
    if not revised:
        if outage or breakdown: sim.paused = True
        return reply('No feasible alternative/recovery plan. ' + result.get('reason','') + ' The existing journey was retained' + (' and paused.' if outage or breakdown else '.'), [{'type':'movement_updated','data':sim.snapshot()}])
    if live_recovery:
        if outage: sim.paused = True
        return reply('A network alternative exists, but applying it from the current mid-route position requires a verified transfer/rejoin location. No route replacement was applied.' , [{'type':'movement_updated','data':sim.snapshot()}])
    _attach_replan_baseline(result, selected, changes)
    result['_active_plan_before'] = {'route_legs':selected['route_legs'], 'vehicles':selected['assigned_vehicles'], 'cost':selected['cost'], 'duration_hours':selected['duration_hours'], 'risk':selected['risk'], 'deadline':selected.get('deadline'), 'sla_met':selected.get('sla_met')}
    updated = record(owner, result, selected, _context_from_result(result, selected), revise=True, planner_reroute=not live_recovery and not breakdown)
    await set_active_planning_context(owner, updated)
    for key in ('requested_source','requested_destination'):
        if updated.get(key):result[key]=updated[key]
    text = _format_planning_result(result, message)
    if result.get('recovery_explanation'):
        text = result['recovery_explanation'] + '\n\n' + text
    if revised.get('deadline'):
        text += (f"\nOld ETA: {selected.get('eta')}; New ETA: {revised['eta']}; Deadline: {revised['deadline']}. "
                 f"SLA before disruption: {selected.get('sla_met')}; SLA after disruption: {revised['sla_met']}. "
                 f"Delay: {revised.get('sla_delay_hours')} hours; slack: {revised.get('sla_slack_hours')} hours.")
    if revised['route_legs']==selected['route_legs'] and objective:
        text += f'\nThe current route is already the {objective} feasible route under the active constraints.'
    result.pop('_active_plan_before', None)
    return reply(text, [{'type':'supply_chain_planning_operation','data':result}])
