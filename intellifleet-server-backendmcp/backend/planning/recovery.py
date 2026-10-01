"""Network-only Air recovery, with explicit constraints ahead of preferences."""
import itertools
import re
from .models import PlanningRequest

STRUCTURES = [('air',), ('air', 'road'), ('road', 'air'), ('road', 'air', 'road'), ('road',)]


def strict_air_only(message):
    return bool(re.search(r'\b(?:air[ -]only|aircraft only|keep (?:it|this shipment) air|do not use (?:ground|road)|no (?:ground|road)(?: fallback)?)\b', message, re.I))


def recover_air(service, owner, request, changes, message='', *, strict=False, network=None):
    from backend.agents.supervisor import _deadline_from_message, _objective_from_message
    values = dict(request)
    values['objective'] = _objective_from_message(message) or values.get('objective', 'balanced')
    values['deadline'] = _deadline_from_message(message) or values.get('deadline')
    # A missed mandatory SLA is reported, rather than hiding the best recovery.
    values['sla_mandatory'] = False
    ground_only = bool(re.search(r'\b(?:ground[ -]only|road[ -]only|do not use air|no air(?: fallback)?)\b', message, re.I))
    values['allowed_modes'] = ['air'] if strict else ['road'] if ground_only else ['air', 'multimodal', 'road']
    values['required_mode_sequence'] = ['air'] if strict else ['road'] if ground_only else values.get('required_mode_sequence', [])
    req = PlanningRequest(**values)
    network = network or service.load_network(owner)
    structures = [s for s in STRUCTURES if
        (not req.required_mode_sequence or list(s) == req.required_mode_sequence) and
        (not strict or s == ('air',)) and (not ground_only or s == ('road',))]
    candidates, searches = [], []
    for sequence in structures:
        mode = sequence[0] if len(sequence) == 1 else 'multimodal'
        search = service.plan(owner, req.model_copy(update={'allowed_modes':[mode], 'required_mode_sequence':list(sequence)}),
                              changes=changes, network=network)
        searches.append(search)
        candidates.extend(search['candidate_plans'])
    result = searches[0] if searches else service.plan(owner, req, changes=changes, network=network)
    result['planning_request'] = req.model_dump(mode='json')
    def structure(p):
        return tuple(k for k, _ in itertools.groupby(l['route_type'] for l in p['route_legs']))
    candidates = [p for p in candidates if structure(p) in STRUCTURES]
    candidates.sort(key=lambda p: STRUCTURES.index(structure(p)))

    # The user's objective is authoritative across all permitted recovery
    # structures. Do not remove Ground candidates merely because a multimodal
    # candidate is faster: that would make a "cheapest" or "lowest-risk"
    # request behave like "fastest".
    #
    # STRUCTURES still defines which recovery forms are permitted/searched;
    # service._rank() below decides which verified candidate best satisfies
    # fastest / cheapest / lowest-risk / balanced / SLA-aware planning.
    budget = re.search(r'(?:under|below|budget(?: of)?)\s*₹?\s*([\d,]+(?:\.\d+)?)', message, re.I)
    warnings = list(dict.fromkeys(w for search in searches for w in search.get('warnings', []) if w != 'No feasible route found'))
    if budget:
        limit = float(budget.group(1).replace(',', ''))
        affordable = [p for p in candidates if p['operational_cost'] <= limit]
        if affordable:
            candidates = affordable
        elif re.search(r'if possible', message, re.I):
            warnings.append(f'No verified recovery meets the preferred budget ₹{limit:,.2f}.')
        else:
            candidates = []
    ranked = service._rank(candidates, req)
    plan = ranked[0] if ranked else None
    alternate_air = any(p['mode'] == 'air' for p in candidates)
    if plan:
        label = ' → '.join('Air' if m == 'air' else 'Ground' for m in structure(plan))
        lane = ' → '.join([plan['route_legs'][0]['from_location'], *[l['to_location'] for l in plan['route_legs']]])
        explanation = f"Air route(s) {', '.join(map(str, changes.get('blocked_route_ids', [])))} excluded. "
        explanation += ('Alternate Air-only paths were evaluated. ' if alternate_air else 'No alternate Air-only path was feasible. ')
        explanation += f"The {req.objective} verified recovery is {label} via {lane}."
        if plan['mode'] != 'air':
            explanation += ' Transport mode changed because recovery permits Ground and this option best satisfies the recovery constraints and objective.'
        if plan['sla_met'] is False:
            explanation += ' No allowed recovery meets the deadline; this recovery misses SLA.'
    else:
        explanation = 'No feasible Air-only recovery.' if strict else 'No feasible recovery in the allowed transport structures and constraints.'
    result.update(candidate_plans=ranked, recommended_plan=plan,
                  recommended_plan_id=plan['plan_id'] if plan else None,
                  comparison=[], explanation_inputs={'recommended':plan, 'comparisons':[]} if plan else None,
                  reason=explanation, recovery_explanation=explanation, warnings=warnings,
                  recovery_search_order=[list(s) for s in structures])
    return result
