"""Read-only map display intents, independent of planning and movement creation."""
import re


def display_intent(message):
    text = message.casefold()
    if re.search(r'\b(?:route|vehicle)\s+ids?\b',text) and not re.search(r'\bmap|together|visible\b',text):
        return None

    # Information queries must be handled by operations/comparison handlers,
    # not consumed as map-display commands merely because they contain
    # words such as "show", "shipment" or "only".
    information_query = re.search(
        r'\b(?:operational\s+status|current\s+status|shipment\s+status|'
        r'progress|current\s+location|revised\s+eta|current\s+eta|'
        r'delay|risk|cost|eta|reliability|utilization)\b',
        text,
    )
    explicit_map_cue = re.search(
        r'\b(?:map|on\s+the\s+map|visible|together|overlay|'
        r'multiple\s+routes|both\s+routes|display\s+routes|show\s+routes)\b',
        text,
    )

    if information_query and not explicit_map_cue:
        return None

    display = re.search(r'\b(show|display|view|visuali[sz]e|keep|put|see|compare|overlay)\b', text)
    if not display:
        return None
    route = re.search(r'\b(routes?|paths?|journeys?|shipments?)\b', text)
    # Pronouns need a spatial/display cue, so comparing transport modes stays planning.
    if not route and re.search(r'\b(?:show|display)\s+(?:all\s+)?(?:three|3|two|2)\s+again\b',text):
        return 'MULTI_ROUTE'
    if not route and re.search(r'\b(them|both|these)\b', text):
        route = re.search(r'\b(together|visible|map|simultaneously|side.by.side|at once)\b', text)
    single = re.search(r'\b(only|just|single|one at a time)\b', text)
    if single and route:
        return 'SINGLE_ROUTE'
    multiple = re.search(r'\b(multiple|two|three|several|both|together|simultaneously|concurrently|alongside|side.by.side|at once|at the same time)\b', text)
    all_routes = re.search(r'\ball (?:these |the |my )?(?:routes|paths|journeys|shipments)\b', text)
    named_pairs = len(re.findall(r'\s(?:to|→|->)\s', text)) >= 2
    on_map = re.search(r'\bmap\b', text)
    if (route and (multiple or all_routes)) or (named_pairs and on_map):
        if re.search(r"\b(don't|do not|stop)\s+(?:show|display|overlay|keep)", text):
            return 'SINGLE_ROUTE'
        return 'MULTI_ROUTE'
    return None


def answer(owner, message, context, selected_id=None):
    mode = display_intent(message)
    if not mode:
        return None
    from backend.planning.lifecycle import resolve
    from backend.fedex.telemetry import runtime
    def clarification(text):
        return {'success': True, 'response': text, 'actions': []}
    from backend.operations.journey_selection import current_journeys
    contexts = current_journeys(context, owner, active_only=True)
    if not contexts and context.get('selected_plan_id'):
        contexts = [context]
    if mode == 'SINGLE_ROUTE':
        scope={**next((c for c in contexts if c.get('journey_id')==context.get('journey_id')),{}), 'map_comparison_ids':context.get('map_comparison_ids',[]), 'journeys':{c.get('journey_id') or c['selected_plan_id']:c for c in contexts}}
        selected, error = resolve(scope, message, selected_id)
        if error:
            return clarification(error)
        contexts = [selected]
    else:
        text = message.casefold()
        def mentioned(value):
            return value and re.search(r'(?<![\w-])'+re.escape(str(value).casefold())+r'(?![\w-])',text)
        explicit = [c for c in contexts if any(mentioned(c.get(k)) for k in ('journey_id','movement_id','shipment_id','selected_plan_id'))]
        def lane_matches(c):
            sources = {
                str(c.get('source') or '').casefold(),
                str(c.get('requested_source') or '').casefold(),
            }
            destinations = {
                str(c.get('destination') or '').casefold(),
                str(c.get('requested_destination') or '').casefold(),
            }
            sources.discard('')
            destinations.discard('')
            return any(
                re.search(
                    re.escape(src)+r'\s*(?:to|→|->)\s*'+re.escape(dst),
                    text,
                )
                for src in sources
                for dst in destinations
            )

        pairs = [c for c in contexts if lane_matches(c)]
        requested_pairs = len(re.findall(r'\s(?:to|→|->)\s', text))
        if requested_pairs:
            unique_pairs = {(c.get('source'),c.get('destination')) for c in pairs}
            if len(unique_pairs) != requested_pairs:
                return clarification('Some requested routes are not available in this chat. Plan those shipments first, then ask to show them together.')
            if len(pairs) != len(unique_pairs) and not explicit:
                return clarification('Multiple shipments match a requested lane. Specify the journey IDs to display together.')
        remembered=context.get('map_comparison_ids') or []
        if not explicit and not pairs and remembered and re.search(r'\b(?:again|those|these|all three)\b',text):
            contexts=[c for c in contexts if c.get('movement_id') in remembered]
        if not explicit and not pairs and not remembered and re.search(r'\b(?:those|these)\s+(?:three|3)\b',text):
            contexts=contexts[-3:]
        contexts = explicit or pairs or contexts
        if len(contexts) < 2:
            return clarification('There is only one planned journey in this chat. Plan another shipment before displaying multiple routes together.')
        if not explicit and not pairs and len(contexts) > 2 and re.search(r'\bboth\b',text):
            return clarification('Which two journeys should I show? Specify their lanes or journey IDs.')
    snapshots = []
    for ctx in contexts:
        try:
            sim = runtime.get(owner, ctx.get('movement_id'))
        except KeyError:
            return clarification('A requested movement is unavailable or expired. Refresh its plan before displaying it.')
        if sim.stopped:
            return clarification('A requested movement is stopped. Select an active journey to display.')
        snapshots.append(sim.snapshot())
    ids = [m['simulation_id'] for m in snapshots]
    return {'success': True, 'response': f"Showing {len(ids)} {'route' if len(ids)==1 else 'routes'} on the map.",
            'actions': [{'type': 'set_journey_display', 'data': {'mode': mode, 'simulation_ids': ids, 'movements': snapshots}}]}
