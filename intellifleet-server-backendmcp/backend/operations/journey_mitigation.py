"""Read-only operational impact and mitigation responses."""

from __future__ import annotations

import re
from typing import Any


def _is_request(message: str) -> bool:
    """Return True only for read-only impact / mitigation questions."""
    text = str(message or "").casefold()

    # Never steal a request that actually changes operational state.
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
        r"cancelled|canceled|"
        r"breakdown|broke down|broken down|"
        r"replace|"
        r"change\s+(?:the\s+|assigned\s+)?(?:truck|vehicle|aircraft)|"
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
            r"impact of (?:this|the) reroute|"
            r"mitigation|"
            r"mitigation plan|"
            r"recommended mitigation|"
            r"recommended response|"
            r"recovery recommendation|"
            r"what should (?:we|operations) do next"
            r")\b",
            text,
            re.I,
        )
    )


def _plan(context: dict[str, Any]) -> dict[str, Any]:
    return (
        context.get("selected_plan")
        or context.get("recommended_plan")
        or context.get("current_plan")
        or {}
    )


def _previous(context: dict[str, Any]) -> dict[str, Any]:
    return (
        context.get("previous_plan")
        or context.get("baseline_plan")
        or {}
    )


def _num(obj: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _vehicles(plan: dict[str, Any]) -> list[str]:
    rows = plan.get("vehicles") or plan.get("assigned_vehicles") or []
    labels: list[str] = []
    for vehicle in rows:
        if not isinstance(vehicle, dict):
            continue
        label = (
            vehicle.get("label")
            or vehicle.get("vehicle_label")
            or vehicle.get("vehicle_id")
            or vehicle.get("id")
        )
        if label is not None:
            labels.append(str(label))
    return labels


def _route(plan: dict[str, Any]) -> str:
    legs = plan.get("route_legs") or []
    if not legs:
        return "Not available"

    parts: list[str] = []
    for leg in legs:
        if not isinstance(leg, dict):
            continue
        source = leg.get("from_location") or leg.get("source") or "?"
        destination = leg.get("to_location") or leg.get("destination") or "?"
        mode = str(leg.get("route_type") or leg.get("mode") or "").title()
        route_id = leg.get("route_id")

        text = f"{source} → {destination}"
        if mode:
            text += f" ({mode}"
            if route_id is not None:
                text += f", Route ID {route_id}"
            text += ")"
        elif route_id is not None:
            text += f" (Route ID {route_id})"

        parts.append(text)

    return " | ".join(parts) if parts else "Not available"


def _risk_percent(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 100 if abs(value) <= 1 else value


def answer(message: str, context: dict):
    if not _is_request(message):
        return None

    current = _plan(context)
    previous = _previous(context)

    # Some contexts keep the current plan fields directly on the journey.
    if not current and context.get("route_legs"):
        current = {
            "route_legs": context.get("route_legs") or [],
            "vehicles": context.get("assigned_vehicles") or [],
            "cost": context.get("cost"),
            "duration_hours": context.get("duration_hours"),
            "risk": context.get("risk"),
            "deadline": context.get("deadline"),
            "sla_met": context.get("sla_met"),
            "eta": context.get("eta"),
        }

    if not current:
        return {
            "success": True,
            "response": (
                "There is not enough verified shipment context to calculate the "
                "operational impact. Select the affected shipment and retry."
            ),
            "actions": [],
        }

    changes = context.get("planning_changes") or {}
    blocked = (
        changes.get("blocked_route_ids")
        or context.get("blocked_route_ids")
        or []
    )

    lines: list[str] = ["Operational impact and mitigation"]

    if previous:
        lines.append(f"- Previous route: {_route(previous)}")
    else:
        lines.append("- Previous route: baseline data is not available for this revision.")

    lines.append(f"- Current route: {_route(current)}")

    old_cost = _num(previous, "cost", "operational_cost", "total_cost")
    new_cost = _num(current, "cost", "operational_cost", "total_cost")

    if old_cost is not None and new_cost is not None:
        delta = new_cost - old_cost
        lines.append(
            f"- Cost before ₹{old_cost:,.2f}; after ₹{new_cost:,.2f}; "
            f"delta ₹{delta:+,.2f}"
        )

    old_eta = _num(previous, "duration_hours", "eta_hours", "total_hours")
    new_eta = _num(current, "duration_hours", "eta_hours", "total_hours")

    if old_eta is not None and new_eta is not None:
        delta = new_eta - old_eta
        lines.append(
            f"- ETA before {old_eta:.2f} hours; after {new_eta:.2f} hours; "
            f"delta {delta:+.2f} hours"
        )

    old_risk = _risk_percent(_num(previous, "risk", "risk_score"))
    new_risk = _risk_percent(_num(current, "risk", "risk_score"))

    if old_risk is not None and new_risk is not None:
        delta = new_risk - old_risk
        lines.append(
            f"- Risk before {old_risk:.2f}%; after {new_risk:.2f}%; "
            f"delta {delta:+.2f} percentage points"
        )

    old_vehicles = _vehicles(previous)
    new_vehicles = _vehicles(current)

    if old_vehicles or new_vehicles:
        lines.append(
            "- Vehicles: "
            f"{', '.join(old_vehicles) if old_vehicles else 'not available'} "
            "→ "
            f"{', '.join(new_vehicles) if new_vehicles else 'not available'}"
        )

    old_sla = previous.get("sla_met") if previous else None
    new_sla = current.get("sla_met")

    deadline = current.get("deadline") or context.get("deadline")
    if deadline:
        lines.append(
            f"- SLA: {old_sla} → {new_sla}; deadline: {deadline}"
        )

        delay = _num(current, "sla_delay_hours")
        slack = _num(current, "sla_slack_hours")

        if delay is not None and delay > 0:
            lines.append(f"- SLA delay after recovery: {delay:.2f} hours")
        elif slack is not None:
            lines.append(f"- SLA slack after recovery: {slack:.2f} hours")
    else:
        lines.append("- SLA impact: no delivery deadline was provided.")

    if blocked:
        lines.append(
            "- Active disruption exclusions: "
            + ", ".join(f"Route ID {route_id}" for route_id in blocked)
        )

    current_route_ids = {
        str(leg.get("route_id"))
        for leg in current.get("route_legs", [])
        if isinstance(leg, dict) and leg.get("route_id") is not None
    }
    blocked_ids = {str(route_id) for route_id in blocked}

    blocked_still_used = current_route_ids.intersection(blocked_ids)

    if blocked_still_used:
        lines.append(
            "- Mitigation: the current plan still contains a disrupted route. "
            "Keep the shipment paused and do not resume until a verified route "
            "excluding the blocked leg is available."
        )
    elif previous and current:
        if new_sla is False:
            lines.append(
                "- Mitigation: continue with the verified recovery only if the "
                "service impact is acceptable; the current recovery misses the "
                "SLA. Evaluate another feasible objective or escalate the delivery "
                "exception while keeping all disrupted routes excluded."
            )
        elif old_eta is not None and new_eta is not None and new_eta > old_eta:
            lines.append(
                "- Mitigation: retain the verified recovery route, keep the "
                "disrupted route excluded, and monitor the revised ETA. The "
                "recovery is operationally feasible but increases transit time."
            )
        elif old_cost is not None and new_cost is not None and new_cost > old_cost:
            lines.append(
                "- Mitigation: retain the verified recovery route and monitor "
                "the additional operational cost. Do not restore the disrupted "
                "route until its availability is verified."
            )
        else:
            lines.append(
                "- Mitigation: retain the currently verified feasible recovery "
                "and continue monitoring ETA, capacity, risk and SLA. Keep the "
                "disrupted route excluded until availability is confirmed."
            )
    else:
        lines.append(
            "- Mitigation: no verified before/after baseline is available. "
            "Keep the current verified plan and monitor ETA, capacity, risk and "
            "SLA while preserving all recorded disruption exclusions."
        )

    return {
        "success": True,
        "response": "\n".join(lines),
        "actions": [],
    }
