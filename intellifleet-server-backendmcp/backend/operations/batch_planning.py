"""Independent batch shipments, parsed before single-journey intent handling."""
import re
from backend.planning.models import PlanningRequest
from backend.planning.service import PlanningService


def parse(message, network):
    if not re.search(r'^\s*(?:please\s+)?(?:create|plan)\b', message, re.I):
        return []
    names = {str(w[k]).casefold(): w['name'] for w in network['warehouses'] for k in ('name', 'city') if w.get(k)}
    pattern = '|'.join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    if not pattern:
        return []
    pair = re.compile(r'(?<!\w)('+pattern+r')\s*(?:→|->|\bto\b)\s*('+pattern+r')(?!\w)', re.I)
    rows = []
    for line in message.splitlines():
        matches = list(pair.finditer(line))
        for match in matches:
            rows.append((names[match[1].casefold()], names[match[2].casefold()], line))
        # Unknown endpoints remain explicit failed rows; never silently drop them.
        if not matches and not re.search(r'^\s*(?:create|plan)\b', line, re.I):
            raw = re.match(r'^\s*(?:[-*]|\d+[.)])?\s*(.+?)\s*(?:→|->|\bto\b)\s*(.+?)\s*$', line, re.I)
            if raw:
                source, destination = raw.groups()
                destination = re.split(r'\s+(?:[\d,]+(?:\.\d+)?\s*kg|ground|road|air|fastest|cheapest|lowest|before|by)\b', destination, maxsplit=1, flags=re.I)[0].rstrip(' .;')
                rows.append((names.get(source.casefold(), source), names.get(destination.casefold(), destination), line))
    if len(rows) < 2:
        common = re.search(r'\bfrom\s+(.+?)\s+to\s+('+pattern+r')(?!\w)', message, re.I)
        if common:
            origins = re.findall(r'(?<!\w)('+pattern+r')(?!\w)', common[1], re.I)
            if len(origins) > 1:
                rows = [(names[a.casefold()], names[common[2].casefold()], '') for a in origins]
    return rows if len(rows) > 1 else []


async def answer(owner, message, context):
    if not re.search(r'^\s*(?:please\s+)?(?:create|plan)\b', message, re.I):
        return None
    service = PlanningService()
    network = service.load_network(owner)
    rows = parse(message, network)
    if not rows:
        return None
    from backend.agents.supervisor import _weight_kg_from_message, _objective_from_message, _deadline_from_message, _context_from_result, _format_planning_result
    from backend.planning.lifecycle import record
    from backend.planning.recovery import strict_air_only
    from backend.config.redis import set_active_planning_context
    def modes(text):
        if strict_air_only(text):return ['air']
        ground = bool(re.search(r'\b(?:ground|road)\b', text, re.I))
        air = bool(re.search(r'\b(?:air|aircraft)\b', text, re.I))
        if ground and air:return ['multimodal']
        if ground:return ['road']
        if air:return ['air']
        return None
    # Only the header contributes shared attributes; a row never leaks into others.
    header = message.splitlines()[0] if '\n' in message else message
    common_weight = _weight_kg_from_message(header)
    if any(_weight_kg_from_message(line) is None and common_weight is None for _, _, line in rows):
        return {'success':True, 'response':f'Found {len(rows)} independent shipments. Provide a weight in kg for each shipment or one common weight for the batch.', 'actions':[]}
    actions, summaries, ids = [], [], []
    updated = context
    for i, (source, destination, line) in enumerate(rows, 1):
        if source == destination:
            summaries.append(f'{i}. {source} → {destination}: Infeasible. Source and destination must differ.')
            continue
        request = PlanningRequest(source=source, destination=destination,
            shipment={'weight_kg':_weight_kg_from_message(line) or common_weight},
            allowed_modes=modes(line) or modes(header) or ['road','air','multimodal'],
            objective=_objective_from_message(line) or _objective_from_message(header) or 'balanced',
            deadline=_deadline_from_message(line) or _deadline_from_message(header))
        result = service.plan(owner, request, network=network)
        result['planning_operation'] = 'plan'
        if result.get('recommended_plan'):
            previous = {'journeys':updated.get('journeys', {})}
            if strict_air_only(line) or strict_air_only(header):previous['strict_air_only'] = True
            updated = record(owner, result, previous, _context_from_result(result, previous), revise=False)
            ids.append(updated['movement_id'])
            actions.append({'type':'supply_chain_planning_operation','data':result})
            summaries.append(f'{i}. '+_format_planning_result(result, message))
        else:
            summaries.append(f'{i}. {source} → {destination}: Infeasible. {result["reason"]}')
    updated['map_comparison_ids'] = ids
    await set_active_planning_context(owner, updated)
    if ids:
        actions.append({'type':'set_journey_display', 'data':{'mode':'MULTI_ROUTE' if len(ids)>1 else 'SINGLE_ROUTE',
            'simulation_ids':ids, 'movements':[a['data']['movement'] for a in actions]}})
    return {'success':True, 'response':f'Created: {len(ids)} shipments. Infeasible: {len(rows)-len(ids)}.\n\n'+'\n\n'.join(summaries), 'actions':actions}
