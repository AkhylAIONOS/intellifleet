"""Session-scoped logical identities, separate from immutable plan revisions."""
from copy import deepcopy
import re
from uuid import uuid4


def route_alternative(message):
    patterns = (
        r'\b(?:route|path)\b.{0,30}\b(?:unavailable|blocked)\b',
        r'\b(?:use|find|take|choose)\b.{0,35}\balternative\b',
        r'\bavoid\b.{0,20}\b(?:route|path)\b',
        r'\b(?:alternative|another|different)\s+(?:(?:ground|road)\s+)?(?:route|path)\b',
        r'\bre-route\b',
        r'\b(?:road|route|service|flight|air leg)\b.{0,25}\b(?:closed|unavailable|cancelled|canceled|cannot be used)\b',
        r'\bcannot use (?:this|the|current) route\b',
    )
    return any(re.search(pattern, message, re.I) for pattern in patterns)


def explicit_live_recovery(message):
    return bool(re.search(
        r'\b(?:in[ -]transit|already[ -]moving|live\s+(?:vehicle|truck|shipment)|'
        r'current\s+position|(?:truck|vehicle)\s+is\s+currently\s+at)\b', message, re.I))


def is_action(message):
    if route_alternative(message):
        return True
    if explicit_live_recovery(message) and re.search(r'\brecovery\b', message, re.I):
        return True
    return bool(re.search(r'\b(replan|recover|recovery|another way|optimi[sz]e|fastest|quickest|cheapest|lowest[ -]cost|lowest[ -]risk|least risk|safest|balanced|cost[ -]efficient|best overall|blocked|disrupted|breakdown|broke down|broken down|delayed by|add .*delay|change .*(?:truck|vehicle))\b', message, re.I)
                or re.search(r'^\s*(?:(?:please|now|can you|could you)\s+)*delay\b', message, re.I))


def is_new(message):
    # An explicit Plan/Create command with a complete OD pair always starts
    # a new planning request. This must win over stale selected-journey context.
    if re.search(
        r'^\s*(?:please\s+)?(?:plan|create)\b.*\bfrom\s+.+?\s+to\s+.+',
        message,
        re.I,
    ):
        return True

    if re.search(r'\b(current|same|this|replan|assigned|it)\b', message, re.I):
        return False

    return bool(re.search(
        r'\b(?:another|new|additional)\b.*\bshipment\b|'
        r'^\s*(?:plan|create)\b|'
        r'\bshipment\b.*\bfrom\b',
        message,
        re.I,
    ))


def resolve(context, message, selected_id=None):
    """Return a selected context or clarification; explicit references never fall back."""
    context = context or {}
    journeys = context.get('journeys') or {}
    from backend.operations.journey_selection import current_journeys
    candidates = current_journeys(context)
    text = message.casefold()

    # Explicit multimodal follow-ups must resolve only an actually multimodal
    # journey. Never fall back to a previously selected pure-Air/Ground plan.
    wants_multimodal = bool(
        re.search(r'\b(?:multimodal|multi-modal|multi modal)\b', text)
        or re.search(
            r'\b(?:ground|road)\b.{0,40}\b(?:air|airway|flight)\b.{0,40}\b(?:ground|road)\b',
            text,
            re.I,
        )
    )

    if wants_multimodal:
        multimodal = []
        for candidate in candidates:
            legs = candidate.get('route_legs') or []
            modes = {
                str(leg.get('route_type') or '').casefold()
                for leg in legs
            }
            if 'air' in modes and modes.intersection({'road', 'ground', 'surface'}):
                multimodal.append(candidate)

        if multimodal:
            candidates = multimodal
        elif re.search(r'\b(?:same|this|current)\b', text):
            return {}, 'No multimodal shipment exists in this chat yet.'
    def mentioned(value):
        return value and re.search(r'(?<!\w)' + re.escape(str(value).casefold()) + r'(?!\w)', text)
    explicit = [c for c in candidates if any(mentioned(c.get(k)) for k in ('journey_id','selected_plan_id','movement_id','shipment_id')) or any(mentioned(p.get('plan_id')) for p in c.get('revisions', []))]
    if explicit:
        candidates = explicit
    elif re.search(r'\b(?:PLAN-)?[a-f0-9]{8}-[a-f0-9-]{27,}\b', text):
        return {}, 'No matching shipment ID in this chat.'
    else:
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
                    re.escape(src) + r'\s*(?:to|→|->)\s*' + re.escape(dst),
                    text,
                )
                for src in sources
                for dst in destinations
            )

        pairs = [c for c in candidates if lane_matches(c)]
        if pairs:
            candidates = pairs
        elif re.search(r'\bfrom\s+.+?\s+to\s+|\b(?:current|active)\s+[^.!?]+?\s+to\s+[^.!?]+?\s+(?:shipment|journey|route)\b', text):
            return {}, 'No matching shipment in this chat. Specify its journey or movement ID.'
        else:
            vehicles = [c for c in candidates if any(mentioned(v.get('label')) for v in c.get('assigned_vehicles', []))]
            if vehicles:
                candidates = vehicles
    selected = [c for c in candidates if selected_id and c.get('movement_id') == selected_id]
    active = [c for c in candidates if c.get('journey_id') == context.get('journey_id')]
    if len(candidates) > 1:
        grouped=[c for c in candidates if c.get('movement_id') in context.get('map_comparison_ids',[])]
        candidates = selected or (grouped if len(grouped)==1 else []) or active or candidates
    if len(candidates) != 1:
        ids = ', '.join(str(c.get('journey_id') or c.get('selected_plan_id')) for c in candidates)
        return {}, 'Specify one shipment ID' + (': ' + ids if ids else ' or plan a shipment in this chat first.')
    chosen = candidates[0]
    return {**deepcopy(chosen), 'journeys': deepcopy(journeys),
            **({'map_comparison_ids':deepcopy(context['map_comparison_ids'])} if 'map_comparison_ids' in context else {})}, None


def record(owner, result, previous, updated, *, revise, planner_reroute=False):
    """Commit only a feasible, applied result; keep other journeys and revision history."""
    plan = result.get('approved_plan') or result.get('recommended_plan') or result.get('recovery_plan')
    if not isinstance(plan, dict) or result.get('status') == 'draft':
        return updated
    from backend.operations.plan_journeys import canonical_identity
    if revise:
        previous = {**previous, **canonical_identity(owner, previous.get('selected_plan_id'), previous.get('movement_id'))}
    journeys = deepcopy(previous.get('journeys') or {})
    journey_id = (previous.get('journey_id') or previous.get('selected_plan_id')) if revise else None
    journey_id = journey_id or str(uuid4())
    revisions = deepcopy((journeys.get(journey_id) or {}).get('revisions') or [])
    revisions.append(deepcopy(plan))
    revisions = revisions[-50:]
    plan.update(journey_id=journey_id, revision=int((previous.get('selected_plan') or {}).get('revision', 1))+1 if revise else 1)
    updated.update(journey_id=journey_id, selected_plan=plan, revisions=revisions)
    if revise:
        updated['previous_plan']=deepcopy(previous.get('selected_plan') or {})
        for field in ('source','destination'):
            if updated.get(field)==previous.get(field) and previous.get('requested_'+field):
                updated['requested_'+field]=previous['requested_'+field]
    from backend.operations.plan_journeys import remember, start
    remember(owner, [plan])
    try:
        snapshot = start(owner, plan['plan_id'], planner_reroute=planner_reroute)
        if not revise and snapshot['paused'] and snapshot['progress'] == 0:
            from backend.fedex.telemetry import runtime
            snapshot = runtime.get(owner, snapshot['simulation_id']).control('resume', runtime.clock())
        updated['movement_id'] = snapshot['simulation_id']
        updated['shipment_id'] = snapshot['shipment_id']
        result['movement'] = snapshot
    except (ValueError, KeyError, RuntimeError) as exc:
        result.setdefault('warnings', []).append('Journey playback unavailable: ' + str(exc))
        if revise and previous.get('movement_id'):
            result['proposed_plan'] = deepcopy(plan)
            for key in ('recommended_plan', 'recovery_plan', 'approved_plan'):
                if key in result: result[key] = None
            result['reason'] = 'Revision was not applied: ' + str(exc)
            return deepcopy(previous)
    journeys[journey_id] = {k: deepcopy(v) for k,v in updated.items() if k != 'journeys'}
    updated['journeys'] = journeys
    return updated
