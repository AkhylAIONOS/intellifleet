"""Read-only operational impact and mitigation responses."""

import re


def _is_request(message: str) -> bool:
    text = message.casefold()

    # Read-only mitigation must never steal a real operational mutation.
    # Requests that change shipment state belong to journey_chat/planner.
    mutation = re.search(
        r"\b(?:"
        r"delay(?:ed)?|"
        r"replan|"
        r"optimi[sz]e|"
        r"fastest|"
        r"cheapest|"
        r"lowest[ -]risk|"
        r"blocked|"
        r"unavailable|"
        r"closed|"
        r"cancelled|"
        r"breakdown|"
        r"broke down|"
        r"broken down|"
        r"replace|"
        r"change\s+(?:truck|vehicle)|"
        r"use\s+another|"
        r"find\s+another"
        r")\b",
        text,
        re.I,
    )

    if mutation:
        return False

    return bool(
        re.search(
            r"\b(?:"
            r"operational impact|"
            r"impact of (?:this|the) disruption|"
            r"impact of (?:this|the) airport closure|"
            r"mitigation|"
            r"mitigation plan|"
            r"recommended mitigation|"
            r"recommended response|"
            r"recovery recommendation"
            r")\b",
            text,
        )
    )


def _plan(context):
    return (
        context.get("selected_plan")
        or context.get("recommended_plan")
        or context.get("current_plan")
        or {}
    )


def _previous(context):
    return (
        context.get("previous_plan")
        or context.get("baseline_plan")
        or {}
    )


def answer(message: str, context: dict):
    if not _is_request(message):
        return None

    current = _plan(context)
    previous = _previous(context)

    from backend.operations.journey_queries import route_text
    lines = ['Operational impact and mitigation:', 'Previous route:', route_text(previous), 'Current route:', route_text(current)]

    if not current:
        # Still keep this informational instead of falling into mutation logic.
        route_legs = context.get("route_legs") or []
        if not route_legs:
            return {
                "success": True,
                "response": (
                    "There is not enough verified "
                    "shipment context to calculate cost, ETA and risk deltas. "
                    "Select the affected shipment and retry."
                ),
                "actions": [],
            }

    def num(obj, *keys):
        for key in keys:
            value = obj.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return None

    old_cost = num(previous, "cost", "operational_cost", "total_cost")
    new_cost = num(current, "cost", "operational_cost", "total_cost")

    old_eta = num(previous, "duration_hours", "eta_hours", "total_hours")
    new_eta = num(current, "duration_hours", "eta_hours", "total_hours")

    old_risk = num(previous, "risk", "risk_score")
    new_risk = num(current, "risk", "risk_score")

    if old_cost is not None and new_cost is not None:
        lines.append(
            f"- Cost before {old_cost:,.2f}; after {new_cost:,.2f}; change: ₹{new_cost - old_cost:+,.2f}."
        )

    if old_eta is not None and new_eta is not None:
        lines.append(
            f"- ETA before {old_eta:.2f}; after {new_eta:.2f}; change: {new_eta - old_eta:+.2f} hours."
        )

    if old_risk is not None and new_risk is not None:
        # Support either 0..1 or percentage values.
        factor = 100 if abs(old_risk) <= 1 and abs(new_risk) <= 1 else 1
        lines.append(
            f"- Risk before {old_risk}; after {new_risk}; change: {(new_risk - old_risk) * factor:+.2f} percentage points."
        )

    blocked = (context.get("planning_changes") or {}).get("blocked_route_ids") or context.get("blocked_route_ids") or []
    if blocked:
        lines.append(
            f"- Disrupted route constraints retained: {len(blocked)} blocked route(s)."
        )

    lines.append(f"Vehicles: {[v.get('label') or v.get('id') for v in previous.get('vehicles',[])]} → {[v.get('label') or v.get('id') for v in current.get('vehicles',[])]}; SLA: {previous.get('sla_met')} → {current.get('sla_met')}; blocked route IDs: {blocked}.")
    invalid_current = set(blocked).intersection(l.get('route_id') for l in current.get('route_legs',[]))
    if invalid_current:
        lines.append('- Mitigation: the retained route is affected by a recorded exclusion. No feasible applied alternative is available; keep the affected movement paused and obtain verified alternatives before resuming.')
    else:
        lines.append('- Mitigation: retain the currently verified feasible alternative and monitor ETA, capacity and risk. Do not restore excluded legs without confirming availability.')


    return {
        "success": True,
        "response": "\n".join(lines),
        "actions": [],
    }
