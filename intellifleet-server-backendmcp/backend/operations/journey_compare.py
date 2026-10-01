from backend.operations.journey_selection import latest_per_lane
"""Read-only comparison of already planned conversational journeys."""

import re


def _names(ctx, key):
    values = {
        str(ctx.get(key) or "").strip(),
        str(ctx.get("requested_" + key) or "").strip(),
    }
    return {value for value in values if value}


def _lane_mentioned(ctx, text):
    sources = _names(ctx, "source")
    destinations = _names(ctx, "destination")

    return any(
        re.search(
            re.escape(source.casefold())
            + r"\s*(?:to|→|->)\s*"
            + re.escape(destination.casefold()),
            text,
        )
        for source in sources
        for destination in destinations
    )


def answer(owner, message, context, selected_id=None):
    text = message.casefold()

    if not re.search(r"\bcompare\b", text):
        return None

    # Spatial comparison belongs to journey_display.
    if re.search(
        r"\b(?:on the map|map|show both|display both|together|overlay|visible)\b",
        text,
    ):
        return None

    contexts = list((context.get("journeys") or {}).values())

    if not contexts and context.get("selected_plan_id"):
        contexts = [context]

    matched = [ctx for ctx in contexts if _lane_mentioned(ctx, text)]

    # Only intercept clear comparison of existing named journeys.
    if len(matched) < 2:
        return None

    # Avoid comparing duplicate revisions of one logical journey.
    unique = {}
    for ctx in matched:
        key = ctx.get("journey_id") or ctx.get("movement_id") or ctx.get("selected_plan_id")
        if key:
            unique[key] = ctx

    matched = latest_per_lane(list(unique.values()))

    if len(matched) < 2:
        return None

    lines = ["Existing shipment comparison:"]

    for ctx in matched:
        source = ctx.get("requested_source") or ctx.get("source") or "Unknown"
        canonical_source = ctx.get("source")
        destination = ctx.get("requested_destination") or ctx.get("destination") or "Unknown"
        canonical_destination = ctx.get("destination")

        source_label = (
            f"{source} ({canonical_source})"
            if canonical_source and source.casefold() != str(canonical_source).casefold()
            else source
        )

        destination_label = (
            f"{destination} ({canonical_destination})"
            if canonical_destination
            and destination.casefold() != str(canonical_destination).casefold()
            else destination
        )

        cost = ctx.get("cost")
        eta = ctx.get("duration_hours")
        risk = ctx.get("risk")
        reliability = ctx.get("reliability")

        vehicle_labels = [
            str(vehicle.get("label") or vehicle.get("id"))
            for vehicle in ctx.get("assigned_vehicles") or []
            if vehicle.get("label") or vehicle.get("id")
        ]

        line = f"- {source_label} → {destination_label}"

        if cost is not None:
            line += f"; cost ₹{float(cost):,.2f}"
        if eta is not None:
            line += f"; ETA {float(eta):.2f} h"
        if risk is not None:
            line += f"; risk {float(risk):.2%}"
        if reliability is not None:
            line += f"; reliability {float(reliability):.2%}"
        if vehicle_labels:
            line += f"; vehicle {', '.join(vehicle_labels)}"

        lines.append(line)

    lines.append("No shipment was replanned or modified by this comparison.")

    return {
        "success": True,
        "response": "\n".join(lines),
        "actions": [],
    }
