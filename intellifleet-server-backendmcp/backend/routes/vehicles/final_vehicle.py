from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from pydantic import BaseModel
from pulp import PULP_CBC_CMD, LpMinimize, LpProblem, LpVariable, lpSum

from backend.config.logger import logger
from backend.database.database import (
    get_nodes_by_user,
    get_vehicles_by_user,
    update_vehicle,
    get_nearest_airport_by_city
)
from backend.utilities.vehicleConstants import VEHICLE_TYPES



# ─────────────────────────────────────────────────────────────────────────────
# REQUEST MODEL
# ─────────────────────────────────────────────────────────────────────────────

class MultiSegmentAssignRequest(BaseModel):
    source: str
    destination: str
    capacity: int
    objective: Optional[str] = "cost"       # "cost" | "duration" | "distance"
    vehicle_type: Optional[str] = None       # optional preferred type hint


# ─────────────────────────────────────────────────────────────────────────────
# 1. SEGMENT NORMALISATION
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_segment(seg: Dict) -> Dict:
    """
    Accept any column-name variant coming out of the DB and return a
    guaranteed-consistent dict with these keys:
        from_location, to_location, route_type, distance, duration, cost
    """
    def _pick(d, *keys, default=None):
        for k in keys:
            v = d.get(k)
            if v is not None:
                return v
        return default

    frm = str(_pick(seg, "from_location") or "").strip().title()
    to  = str(_pick(seg, "to_location") or "").strip().title()
    route_type = str(_pick(seg, "route_type", "type", "mode") or "road").strip().lower()
    distance   = float(_pick(seg, "distance", "dist", "distance_km") or 0)
    duration   = float(_pick(seg, "duration", "duration_h", "duration_hours") or 0)
    cost       = float(_pick(seg, "cost") or 0)
    route_id = _pick(seg, "route_id", "id")

    return {
        "route_id": route_id,
        "from_location": frm,
        "to_location":   to,
        "route_type":    route_type,   # always lowercase "road" or "air"
        "distance":      distance,
        "duration":      duration,
        "cost":          cost,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. BFS PATH FINDER
#    IMPORTANT: The graph is built from ALL segments regardless of route_type.
#    Road and air segments sit in the same graph so a path like
#    Delhi(air)→Berlin(road)→Hamburg is fully traversable.
#    route_type is only used later, per-segment, during vehicle selection.
# ─────────────────────────────────────────────────────────────────────────────

# import heapq


# def _find_path(segments: List[Dict], source: str, destination: str, objective: str = "cost") -> Optional[List[Dict]]:
#     """
#     Dijkstra shortest path based on objective:
#         cost | duration | distance
#     """

#     source_l = source.strip().lower()
#     dest_l = destination.strip().lower()

#     # Build graph
#     graph = {}
#     for seg in segments:
#         frm = seg["from_location"].strip().lower()
#         to = seg["to_location"].strip().lower()

#         weight = seg.get(objective) or 0

#         graph.setdefault(frm, []).append((to, weight, seg))

#     if source_l not in graph:
#         return None

#     # Min heap
#     pq = [(0, source_l, [])]  # (total_weight, current_node, path)
#     visited = {}

#     while pq:
#         total_weight, node, path = heapq.heappop(pq)

#         if node in visited and visited[node] <= total_weight:
#             continue

#         visited[node] = total_weight

#         if node == dest_l:
#             return path

#         for neighbour, weight, seg in graph.get(node, []):
#             heapq.heappush(
#                 pq,
#                 (
#                     total_weight + weight,
#                     neighbour,
#                     path + [seg]
#                 )
#             )

#     return None


import heapq
import itertools
from typing import List, Dict, Optional


def _find_path(
    segments: List[Dict],
    source: str,
    destination: str,
    objective: str = "cost"
) -> Optional[List[Dict]]:
    """
    Dijkstra shortest path based on objective:
        - cost
        - duration
        - distance
    """

    source_l = source.strip().lower()
    dest_l = destination.strip().lower()

    # ---------------------------
    # Build adjacency graph
    # ---------------------------
    graph = {}
    for seg in segments:
        frm = seg["from_location"].strip().lower()
        to = seg["to_location"].strip().lower()

        weight = seg.get(objective) or 0
        graph.setdefault(frm, []).append((to, weight, seg))

    if source_l not in graph:
        return None

    # ---------------------------
    # Priority queue with tie-breaker
    # ---------------------------
    counter = itertools.count()  # ensures tuples never compare dicts/strings
    # (total_weight, tie_breaker, current_node, path)
    pq = [(0, next(counter), source_l, [])]

    visited = {}

    while pq:
        total_weight, _, node, path = heapq.heappop(pq)

        # skip if we already found a cheaper route
        if node in visited and visited[node] <= total_weight:
            continue

        visited[node] = total_weight

        if node == dest_l:
            return path

        # relax neighbors
        for neighbour, weight, seg in graph.get(node, []):
            new_cost = total_weight + weight
            heapq.heappush(
                pq,
                (
                    new_cost,
                    next(counter),   # tie-breaker avoids TypeError
                    neighbour,
                    path + [seg]
                )
            )

    return None

# ─────────────────────────────────────────────────────────────────────────────
# 3. VEHICLE SELECTOR  (for one segment)
# ─────────────────────────────────────────────────────────────────────────────

def _safe_series(df: pd.DataFrame, col: str, default) -> pd.Series:
    """Return df[col] if it exists, otherwise a Series filled with *default*."""
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(default)
    return pd.Series([default] * len(df), index=df.index, dtype=float)


def _select_vehicles(
    df: pd.DataFrame,
    required_capacity: int,
    distance: float,
    objective: str,
) -> Optional[List[Dict]]:
    """
    Pick the smallest set of vehicles from *df* that together satisfy
    *required_capacity*.

    Returns a list of row-dicts or None on failure.
    """
    df = df.copy()
    df["_cap"]   = _safe_series(df, "capacity",   0)
    df["_cpm"]   = _safe_series(df, "cost_per_km", 10)
    df["_speed"] = _safe_series(df, "speed_kmph",  60)

    # ── Fast path: single vehicle covers the full capacity ───────────────────
    single = df[df["_cap"] >= required_capacity]
    if not single.empty:
        if objective == "duration":
            best = single.sort_values("_speed", ascending=False).iloc[0]
        else:                                # cost / distance / default
            best = single.sort_values("_cpm").iloc[0]
        return [best.to_dict()]

    # ── Multi-vehicle LP ─────────────────────────────────────────────────────
    if df.empty:
        return None

    model = LpProblem("veh_select", LpMinimize)
    x = LpVariable.dicts("v", df.index, cat="Binary")

    if objective == "duration":
        model += lpSum(
            x[i] * (distance / max(float(df.at[i, "_speed"]), 1))
            for i in df.index
        )
    else:
        model += lpSum(
            x[i] * float(df.at[i, "_cpm"]) * distance
            for i in df.index
        )

    # Capacity must be met
    model += lpSum(x[i] * float(df.at[i, "_cap"]) for i in df.index) >= required_capacity

    if model.solve(PULP_CBC_CMD(msg=0)) != 1:
        return None

    selected = [df.loc[i].to_dict() for i in df.index if (x[i].varValue or 0) >= 0.5]
    return selected or None


# ─────────────────────────────────────────────────────────────────────────────
# 4. SINGLE-SEGMENT ASSIGNER
# ─────────────────────────────────────────────────────────────────────────────

def _assign_segment(
    *,
    segment:          Dict,
    required_capacity: int,
    user_id:          int,
    vehicles_df:      pd.DataFrame,
    departure_dt:     datetime,
    objective:        str,
    vehicle_type_hint: Optional[str],
) -> Dict:
    """
    Assign vehicles to one segment and update the DB.

    Returns a result dict with success=True|False plus all details.
    """
    route_type = segment["route_type"]   # "road" or "air"
    from_loc   = segment["from_location"]
    to_loc     = segment["to_location"]
    distance   = segment["distance"]
    duration_h = segment["duration"]

    logger.info(
        f"[ASSIGN SEGMENT] {from_loc} → {to_loc} | "
        f"mode={route_type} | dist={distance} | dur={duration_h}h | "
        f"depart={departure_dt.strftime('%Y-%m-%d %H:%M')}"
    )

    # ── 1. Filter by origin city ──────────────────────────────────────────────
    seg_df = vehicles_df[
        vehicles_df["warehouse_name"].str.strip().str.lower() == from_loc.strip().lower()
    ].copy()

    if seg_df.empty:
        return {
            "success": False,
            "message": (
                f"No available vehicles stationed at '{from_loc}'. "
                f"Ensure vehicles are assigned to this warehouse."
            )
        }

    # ── 2. Filter by transport mode ───────────────────────────────────────────
    if route_type == "air":
        seg_df = seg_df[seg_df["type"].str.strip().str.lower() == "plane"]
        mode_label = "plane (air segment)"
    else:
        seg_df = seg_df[seg_df["type"].str.strip().str.lower() != "plane"]
        mode_label = "road vehicle"

    if seg_df.empty:
        return {
            "success": False,
            "message": (
                f"No {mode_label} available at '{from_loc}' "
                f"for {'air' if route_type=='air' else 'road'} segment."
            )
        }

    # ── 3. Optional vehicle-type hint (e.g. "truck") ──────────────────────────
    if vehicle_type_hint:
        hinted = seg_df[seg_df["type"].str.strip().str.lower() == vehicle_type_hint.lower()]
        if not hinted.empty:
            seg_df = hinted
        # if hint yields nothing → silently ignore so we still assign something

    # ── 4. Select vehicle(s) via LP ────────────────────────────────────────────
    selected = _select_vehicles(seg_df, required_capacity, distance, objective)

    if not selected:
        return {
            "success": False,
            "message": (
                f"Cannot satisfy {required_capacity} kg capacity on "
                f"{route_type} segment '{from_loc}' → '{to_loc}'. "
                f"Add more vehicles or reduce capacity requirement."
            )
        }

    # ── 5. Build timing + cost, update DB ────────────────────────────────────
    arrival_dt = departure_dt + timedelta(hours=duration_h)
    assigned_vehicles = []
    total_assigned_cap = 0

    for v in selected:
        v_type = str(v.get("type", "")).strip().lower()
        specs  = VEHICLE_TYPES.get(v_type, {})

        fuel_consumption = float(specs.get("fuel_consumption") or 1)
        fuel_price       = float(specs.get("fuel_price") or 0)
        segment_cost     = round((distance / fuel_consumption) * fuel_price, 2)

        vehicle_id = v.get("id") or v.get("vehicle_id")
        capacity   = int(v.get("_cap") or v.get("capacity") or 0)

        record = {
            "vehicle_id":      vehicle_id,
            "vehicle_type":    v_type,
            "label":           v.get("label") or f"{v_type}_{vehicle_id}",
            "capacity_kg":     capacity,
            "vehicle_details": specs,
            "segment_cost":    segment_cost,
            "departure_time":  departure_dt.strftime("%Y-%m-%d %H:%M"),
            "arrival_time":    arrival_dt.strftime("%Y-%m-%d %H:%M"),
        }
        assigned_vehicles.append(record)
        total_assigned_cap += capacity

        # Persist assignment to DB
        update_vehicle(
            vehicle_id,
            user_id,
            {
                "is_available":   False,
                "status":         "assigned",
                "assigned_route": {
                    "source":      from_loc,
                    "destination": to_loc,
                    "assigned_at": departure_dt.isoformat(),
                    "route_type":  route_type,
                },
                "vehicle_details":  specs,
                "departure_time":   departure_dt.strftime("%Y-%m-%d %H:%M"),
                "arrival_time":     arrival_dt.strftime("%Y-%m-%d %H:%M"),
            }
        )

    # ── Step 5b: Resolve airport info for air segments ────────────────────────
    # For road segments this will always be None (no airport lookup needed).
    # For air segments we query the nearest_airports table via the warehouse
    # name so the frontend can display departure / arrival airport details
    # including name, address, and coordinates for map rendering.
    airport_info = None
    if route_type == "air":
        src_airport  = get_nearest_airport_by_city(from_loc, user_id)
        dest_airport = get_nearest_airport_by_city(to_loc,   user_id)

        airport_info = {
            "source_airport": {
                "name":                     src_airport.get("airport_name")    if src_airport  else None,
                "address":                  src_airport.get("airport_address") if src_airport  else None,
                "latitude":                 src_airport.get("latitude")        if src_airport  else None,
                "longitude":                src_airport.get("longitude")       if src_airport  else None,
                # Distance from the origin warehouse to its nearest airport (km)
                "distance_from_warehouse_km": src_airport.get("distance_km")  if src_airport  else None,
            },
            "destination_airport": {
                "name":                     dest_airport.get("airport_name")    if dest_airport else None,
                "address":                  dest_airport.get("airport_address") if dest_airport else None,
                "latitude":                 dest_airport.get("latitude")        if dest_airport else None,
                "longitude":                dest_airport.get("longitude")       if dest_airport else None,
                # Distance from the destination warehouse to its nearest airport (km)
                "distance_from_warehouse_km": dest_airport.get("distance_km") if dest_airport else None,
            },
        }

        logger.info(
            f"[ASSIGN SEGMENT] Air segment airport info resolved: "
            f"src={airport_info['source_airport']['name']} | "
            f"dst={airport_info['destination_airport']['name']}"
        )

    return {
        "success": True,
        "from": from_loc,
        "to": to_loc,
        "route_id": segment["route_id"],
        "route_type": route_type,
        "distance_km": round(distance, 2),
        "duration_hours": round(duration_h, 2),
        "required_capacity_kg": required_capacity,
        "total_assigned_capacity_kg": total_assigned_cap,
        "departure_time": departure_dt.strftime("%Y-%m-%d %H:%M"),
        "arrival_time": arrival_dt.strftime("%Y-%m-%d %H:%M"),
        "segment_cost": round(sum(v["segment_cost"] for v in assigned_vehicles), 2),
        "assigned_vehicles": assigned_vehicles,
        "airport_info": airport_info,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

async def assign_vehicles_multi_segment(
    user_id:           int,
    source:            str,
    destination:       str,
    required_capacity: int,
    objective:         str = "cost",
    vehicle_type:      Optional[str] = None,
) -> Dict[str, Any]:
    """
    End-to-end multi-segment vehicle assignment.

    Returns
    -------
    {
        success        : bool
        response_text  : human-readable summary with per-segment times
        data           : full structured result
        actions        : frontend action payload
    }
    """
    try:
        logger.info(
            f"[MULTI-SEG] user={user_id} | {source} → {destination} | "
            f"cap={required_capacity}kg | obj={objective}"
        )

        # ── Load and normalise ALL segments (road + air) ──────────────────────
        raw = get_nodes_by_user(user_id)
        if not raw:
            return _err("No route network found. Upload a CSV or add routes manually.")

        segments = [_normalize_segment(s) for s in raw]
        logger.info(f"[MULTI-SEG] Loaded {len(segments)} segments from nodes table.")

        # ── Find path through the unified graph ───────────────────────────────
        path = _find_path(segments, source, destination, objective)

        if not path:
            logger.warning(
                f"[MULTI-SEG] No path found between {source} and {destination}"
            )

            return _err(
                f"No direct or indirect route possible from '{source}' to '{destination}' "
                f"in your network. Please ensure route segments exist connecting these locations."
            )

        route_chain = " → ".join(
            [path[0]["from_location"]] + [s["to_location"] for s in path]
        )
        logger.info(f"[MULTI-SEG] Route chain: {route_chain}")

        # ── Load available vehicles ───────────────────────────────────────────
        all_vehicles = get_vehicles_by_user(user_id)
        if not all_vehicles:
            return _err("No vehicles found for this account.")

        vehicles_df = pd.DataFrame(all_vehicles)

        # Seed optional columns before filtering
        for col, default in [("cost_per_km", 10), ("speed_kmph", 60), ("warehouse_name", "")]:
            if col not in vehicles_df.columns:
                vehicles_df[col] = default

        vehicles_df = vehicles_df[vehicles_df["is_available"] == 1].copy()

        if vehicles_df.empty:
            return _err("All vehicles are currently assigned. No available vehicles.")

        # ── Assign segment by segment, chaining times ─────────────────────────
        current_departure = datetime.now()
        segment_results: List[Dict] = []

        for idx, seg in enumerate(path, start=1):
            result = _assign_segment(
                segment=seg,
                required_capacity=required_capacity,
                user_id=user_id,
                vehicles_df=vehicles_df,
                departure_dt=current_departure,
                objective=objective,
                vehicle_type_hint=vehicle_type,
            )

            if not result["success"]:
                return {
                    "success": False,
                    "response_text": (
                        f"Assignment failed at segment {idx} "
                        f"({seg['from_location']} → {seg['to_location']}): "
                        f"{result['message']}"
                    ),
                    "data": {"completed_segments": segment_results, "failed_at": idx},
                    "actions": [],
                }

            segment_results.append(result)

            # Remove assigned vehicles from pool so they can't be double-booked
            assigned_ids = {v["vehicle_id"] for v in result["assigned_vehicles"]}
            vehicles_df  = vehicles_df[~vehicles_df["id"].isin(assigned_ids)]

            # Next segment departs when this one arrives
            current_departure = datetime.strptime(result["arrival_time"], "%Y-%m-%d %H:%M")

        # ── Aggregate ─────────────────────────────────────────────────────────
        overall_departure = segment_results[0]["departure_time"]
        final_arrival     = segment_results[-1]["arrival_time"]
        total_distance    = round(sum(s["distance_km"]    for s in segment_results), 2)
        total_duration    = round(sum(s["duration_hours"] for s in segment_results), 2)
        total_cost        = round(sum(s["segment_cost"]   for s in segment_results), 2)

        # ── Human-readable summary ────────────────────────────────────────────
        lines = [
            f"✅ {required_capacity} kg assigned from '{source}' to '{destination}'.",
            f"   Route    : {route_chain}",
            f"   Departure: {overall_departure}   →   Final arrival: {final_arrival}",
            f"   Totals   : {total_distance} km | {total_duration} hrs | cost {total_cost:,.2f}",
            "",
        ]
        for i, seg in enumerate(segment_results, start=1):
            icon = "✈️ " if seg["route_type"] == "air" else "🚛"
            v_labels = ", ".join(
                f"{v['label']} ({v['vehicle_type']}, {v['capacity_kg']}kg)"
                for v in seg["assigned_vehicles"]
            )
            lines.append(
                f"  Segment {i} {icon} "
                f"{seg['from']} → {seg['to']}  [{seg['route_type'].upper()}]  |  "
                f"Depart {seg['departure_time']} → Arrive {seg['arrival_time']}  |  "
                f"{seg['distance_km']} km / {seg['duration_hours']} hrs  |  "
                f"Cost: {seg['segment_cost']:,.2f}  |  "
                f"Vehicles: {v_labels}"
            )

        return {
            "success":       True,
            "response_text": "\n".join(lines),
            "data": {
                "source":               source,
                "destination":          destination,
                "route_chain":          route_chain,
                "required_capacity_kg": required_capacity,
                "total_distance_km":    total_distance,
                "total_duration_hours": total_duration,
                "total_cost":           total_cost,
                "overall_departure":    overall_departure,
                "final_arrival":        final_arrival,
                "segments":             segment_results,
            },
            "actions": [
                {
                    "type": "assign_vehicles",
                    "data": {
                        "source":            source,
                        "destination":       destination,
                        "route_chain":       route_chain,
                        "overall_departure": overall_departure,
                        "final_arrival":     final_arrival,
                        "total_cost":        total_cost,
                        "segments":          segment_results,
                    }
                }
            ],
        }

    except Exception as exc:
        logger.error(f"[MULTI-SEG] Unhandled error: {exc}", exc_info=True)
        return _err("Internal error during vehicle assignment.")


def _err(msg: str) -> Dict[str, Any]:
    return {"success": False, "response_text": msg, "actions": []}

