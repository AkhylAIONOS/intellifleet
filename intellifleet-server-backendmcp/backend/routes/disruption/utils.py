# import json
# import math
# from datetime import datetime, timedelta
# from typing import Dict, List, Optional, Tuple
# from unittest import result
# from backend.database.database import prepare_disruption_data

# import pandas as pd
# import numpy as np


# # from disruption_db import (
# #     get_warehouses_df,
# #     get_road_routes_df,
# #     get_vehicles_df,
# #     prepare_disruption_data,
# # )


# # ─────────────────────────────────────────────────────────────────────────────
# # Haversine
# # ─────────────────────────────────────────────────────────────────────────────

# def haversine(lat1, lon1, lat2, lon2) -> float:
#     R = 6371
#     lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
#     dlat, dlon = lat2 - lat1, lon2 - lon1
#     a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
#     return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)



# # ─────────────────────────────────────────────────────────────────────────────
# # DisruptionManager
# # ─────────────────────────────────────────────────────────────────────────────

# class DisruptionManager:

#     # ── Init ──────────────────────────────────────────────────────────────────

#     def __init__(self, user_id: int):
#         self.user_id = user_id
#         # Perform the initial data load so the object is immediately usable.
#         # Every public method calls _load_data() again to guarantee fresh,
#         # user-scoped data on each invocation.                       [FIX 10]
#         self._load_data()

#     # ── Data loader ───────────────────────────────────────────────────────────

#     def _load_data(self) -> None:
#         """
#         (Re-)fetch all user-scoped tables from the database using self.user_id.

#         Called at __init__ AND at the top of every public method so that each
#         call always operates on current data for the correct user.   [FIX 10]
#         """
#         self.warehouses_df, self.road_routes_df, self.vehicles_df = (
#             prepare_disruption_data(self.user_id)
#         )

#         # Pre-build (src, dst) set for O(1) road-route existence checks.
#         self._routed_pairs: set = set()
#         for _, r in self.road_routes_df.iterrows():
#             src = str(r.get("source_city",      "")).lower().strip()
#             dst = str(r.get("destination_city", "")).lower().strip()
#             if src and dst:
#                 self._routed_pairs.add((src, dst))

#     # ── Internal helpers ──────────────────────────────────────────────────────

#     def _build_city_coords(self) -> Dict[str, Tuple[float, float]]:
#         """
#         Build a {city_lower: (lat, lon)} map from the current user's road
#         routes dataframe (already user-scoped via _load_data).
#         """
#         coords: Dict[str, Tuple[float, float]] = {}
#         for _, r in self.road_routes_df.iterrows():
#             src = str(r.get("source_city",      "")).lower().strip()
#             dst = str(r.get("destination_city", "")).lower().strip()
#             if src and src not in coords:
#                 coords[src] = (float(r.get("lat_src", 0)), float(r.get("lon_src", 0)))
#             if dst and dst not in coords:
#                 coords[dst] = (float(r.get("lat_dst", 0)), float(r.get("lon_dst", 0)))
#         return coords

#     def _has_road_route(self, source: str, destination: str) -> bool:
#         """Check existence of a direct road edge for the current user."""
#         return (source.lower().strip(), destination.lower().strip()) in self._routed_pairs

#     @staticmethod
#     def _parse_hhmm(t: str) -> datetime:
#         h, m = map(int, t.split(":"))
#         return datetime(2000, 1, 1, h, m)

#     @staticmethod
#     def _format_arrival_label(base_dt: datetime, arrival_dt: datetime) -> str:
#         """
#         Return a human-readable arrival label.                        [FIX 1]

#         same day   →  "20:45"
#         next day   →  "Next day 04:39"
#         2+ days    →  "+3 days 03:12"
#         """
#         day_offset = (arrival_dt.date() - base_dt.date()).days
#         t = arrival_dt.strftime("%H:%M")
#         if day_offset == 0:
#             return t
#         elif day_offset == 1:
#             return f"Next day {t}"
#         else:
#             return f"+{day_offset} days {t}"

#     def _get_distance_km(self, src_l: str, dst_l: str) -> Optional[float]:
#         """
#         Haversine distance between two known cities for the current user,
#         or None if coordinates are unavailable.
#         Uses self.road_routes_df which is always user-scoped via _load_data.
#         """
#         match = self.road_routes_df[
#             (self.road_routes_df["source_city"].str.lower()      == src_l) &
#             (self.road_routes_df["destination_city"].str.lower() == dst_l)
#         ]
#         if not match.empty:
#             r = match.iloc[0]
#             return haversine(r["lat_src"], r["lon_src"], r["lat_dst"], r["lon_dst"])
#         coords = self._build_city_coords()
#         if src_l in coords and dst_l in coords:
#             return haversine(*coords[src_l], *coords[dst_l])
#         return None

#     # ── Transport assignment ──────────────────────────────────────────────────
#     async def _assign_transport(
#         self,
#         source_city: str,
#         dest_city: str,
#         load_kg: float,
#         objective: str = "cost",
#         vehicle_type: Optional[str] = None,
#     ) -> Optional[Dict]:
#         try:
#             from backend.routes.vehicles.partial_vehicle import start_partial_assignment
#         except ImportError:
#             return None

#         result = await start_partial_assignment(
#             user_id=self.user_id,
#             source=source_city,
#             destination=dest_city,
#             required_capacity=int(load_kg),
#             objective=objective,
#             vehicle_type=vehicle_type,
#         )

#         print(f"==>> kjsbcksbckjsbckasbckasjbkasbckasb result:  {result}")

#         if not result.get("success"):
#             return None

#         # Extract only the animate_segment action
#         animate_segment = None
#         for action in result.get("actions", []):
#             if action.get("type") == "animate_segment":
#                 animate_segment = action
#                 break
#         print(f"\n🚚 Transport result for {source_city} → {dest_city}")
#         print(json.dumps(result, indent=2))

#         return animate_segment  # None if not found
    

#     # async def _assign_transport(
#     #     self,
#     #     source_city: str,
#     #     dest_city: str,
#     #     load_kg: float,
#     #     objective: str = "cost",
#     #     vehicle_type: Optional[str] = None,
#     # ) -> Optional[Dict]:
#     #     """
#     #     Assign vehicles for a single warehouse → destination leg.
#     #     Uses self.user_id so the partial-assignment service only considers
#     #     vehicles belonging to this user.
#     #     """
#     #     try:
#     #         from backend.routes.vehicles.partial_vehicle import start_partial_assignment
#     #     except ImportError:
#     #         return None

#     #     result = await start_partial_assignment(
#     #         user_id=self.user_id,          # user_id explicitly forwarded
#     #         source=source_city,
#     #         destination=dest_city,
#     #         required_capacity=int(load_kg),
#     #         objective=objective,
#     #         vehicle_type=vehicle_type,
#     #     )
#     #     if not result.get("success"):
#     #         return None

#     #     vehicles: List[Dict] = []
#     #     for action in result.get("actions", []):
#     #         if action.get("type") == "animate_segment":
#     #             for v in action["data"].get("segment", {}).get("assigned_vehicles", []):
#     #                 dep = v.get("departure_time", "N/A")
#     #                 arr = v.get("arrival_time",   "N/A")
#     #                 if dep not in ("N/A", None) and len(str(dep)) > 5:
#     #                     dep = str(dep)[-5:]
#     #                 if arr not in ("N/A", None) and len(str(arr)) > 5:
#     #                     arr = str(arr)[-5:]
#     #                 vehicles.append({
#     #                     "vehicle_id":   v.get("vehicle_id",   "N/A"),
#     #                     "departure":    dep,
#     #                     "arrival":      arr,
#     #                     "vehicle_type": v.get("vehicle_type"),
#     #                     "capacity_kg":  v.get("capacity_kg"),
#     #                     "segment_cost": v.get("segment_cost"),
#     #                 })
#     #             break

#     #     if not vehicles:
#     #         return None
#     #     return {
#     #         "user_id":       self.user_id,   # [FIX 11]
#     #         "vehicles":      vehicles,
#     #         "session_id":    result.get("session_id"),
#     #         "response_text": result.get("response_text", ""),
#     #         "raw_actions":   result.get("actions", []),
#     #     }

#     # ── Step 1: original route feasibility ───────────────────────────────────

#     def estimate_delivery_time(
#         self,
#         source_city: str,
#         destination_city: str,
#         repair_duration_hours: int,
#         disruption_time: str,
#         required_delivery_time: str,
#         require_road_route: bool = False,
#     ) -> Dict:
#         """
#         Check whether the DAMAGED vehicle can still deliver after repair.

#         Exposed as a standalone API endpoint — calls _load_data() first so it
#         always uses fresh data for self.user_id.                     [FIX 10]

#         source_city here is disruption_location (or source_warehouse as
#         fallback).  repair_duration_hours IS added because the original
#         vehicle must wait for repair before moving.
#         """
#         # Always refresh data for the correct user before any calculation.
#         self._load_data()                                            # [FIX 10]

#         src_l = source_city.lower().strip()
#         dst_l = destination_city.lower().strip()

#         base_response = {"user_id": self.user_id}                   # [FIX 11]

#         if require_road_route and not self._has_road_route(src_l, dst_l):
#             return {
#                 **base_response,
#                 "feasible":                False,
#                 "error":                   f"No road route: {source_city} → {destination_city}",
#                 "estimated_delivery_time": None,
#                 "meets_requirement":       False,
#                 "total_hours_to_arrival":  float("inf"),
#             }

#         distance_km = self._get_distance_km(src_l, dst_l)
#         if distance_km is None:
#             return {
#                 **base_response,
#                 "feasible":                False,
#                 "error":                   f"No route or coordinates found from {src_l} to {dst_l}",
#                 "estimated_delivery_time": None,
#                 "meets_requirement":       False,
#                 "total_hours_to_arrival":  float("inf"),
#             }

#         try:
#             disruption_dt     = self._parse_hhmm(disruption_time)
#             repair_completion = disruption_dt + timedelta(hours=repair_duration_hours)
#             travel_hours      = distance_km / 60.0
#             estimated_arrival = repair_completion + timedelta(hours=travel_hours)

#             arrival_label = self._format_arrival_label(disruption_dt, estimated_arrival)
#             day_offset    = (estimated_arrival.date() - disruption_dt.date()).days
#             req_dt        = self._parse_hhmm(required_delivery_time)

#             # [FIX 9] correct: arrival must be same day AND before deadline
#             meets = (day_offset == 0) and (estimated_arrival <= req_dt)
#             time_delta_h = (estimated_arrival - req_dt).total_seconds() / 3600

#             return {
#                 **base_response,
#                 "feasible":                True,
#                 "distance_km":             round(float(distance_km), 2),
#                 "travel_hours":            round(float(travel_hours), 2),
#                 "repair_hours":            int(repair_duration_hours),
#                 "disruption_time":         disruption_time,
#                 "repair_completion_time":  repair_completion.strftime("%H:%M"),
#                 "estimated_delivery_time": arrival_label,
#                 "required_delivery_time":  required_delivery_time,
#                 "meets_requirement":       bool(meets),
#                 "time_delta_hours":        round(float(time_delta_h), 2),
#                 "total_hours_to_arrival":  round(float(repair_duration_hours + travel_hours), 2),
#             }
#         except Exception as exc:
#             return {
#                 **base_response,
#                 "feasible":                False,
#                 "error":                   f"Calculation error: {exc}",
#                 "estimated_delivery_time": None,
#                 "meets_requirement":       False,
#                 "total_hours_to_arrival":  float("inf"),
#             }

#     # ── Step 2 helper: alternative warehouse delivery time ────────────────────

#     def _estimate_alt_delivery(
#         self,
#         warehouse_city: str,
#         destination_city: str,
#         disruption_time: str,
#         required_delivery_time: str,
#     ) -> Dict:
#         """
#         Estimate when an ALTERNATIVE warehouse can deliver to destination.

#         Private helper — data is always current because the calling public
#         method has already called _load_data() for self.user_id.

#         Key differences from estimate_delivery_time():
#           • NO repair time — alternative warehouses dispatch IMMEDIATELY at
#             disruption_time.                                         [FIX 7]
#           • Requires a road edge to destination.                     [FIX 3]
#         """
#         src_l = warehouse_city.lower().strip()
#         dst_l = destination_city.lower().strip()

#         base_response = {"user_id": self.user_id}                   # [FIX 11]

#         if not self._has_road_route(src_l, dst_l):                   # [FIX 3]
#             return {
#                 **base_response,
#                 "feasible":          False,
#                 "error":             f"No road route: {warehouse_city} → {destination_city}",
#                 "estimated_arrival": None,
#                 "travel_hours":      float("inf"),
#                 "meets_deadline":    False,
#             }

#         distance_km = self._get_distance_km(src_l, dst_l)
#         if distance_km is None:
#             return {
#                 **base_response,
#                 "feasible":          False,
#                 "error":             f"No coordinates: {warehouse_city} → {destination_city}",
#                 "estimated_arrival": None,
#                 "travel_hours":      float("inf"),
#                 "meets_deadline":    False,
#             }

#         try:
#             travel_hours      = distance_km / 60.0
#             disruption_dt     = self._parse_hhmm(disruption_time)
#             estimated_arrival = disruption_dt + timedelta(hours=travel_hours)  # no repair [FIX 7]

#             arrival_label = self._format_arrival_label(disruption_dt, estimated_arrival)
#             day_offset    = (estimated_arrival.date() - disruption_dt.date()).days
#             req_dt        = self._parse_hhmm(required_delivery_time)

#             meets      = (day_offset == 0) and (estimated_arrival <= req_dt)  # [FIX 9]
#             time_delta = (estimated_arrival - req_dt).total_seconds() / 3600
#             hours_late = round(abs(float(time_delta)), 2) if time_delta > 0 else 0.0  # [FIX 5]

#             return {
#                 **base_response,
#                 "feasible":          True,
#                 "distance_km":       round(float(distance_km), 2),
#                 "travel_hours":      round(float(travel_hours), 2),
#                 "estimated_arrival": arrival_label,
#                 "meets_deadline":    bool(meets),
#                 "time_delta_hours":  round(float(time_delta), 2),
#                 "hours_late":        hours_late,
#             }
#         except Exception as exc:
#             return {
#                 **base_response,
#                 "feasible":          False,
#                 "error":             f"Calculation error: {exc}",
#                 "estimated_arrival": None,
#                 "travel_hours":      float("inf"),
#                 "meets_deadline":    False,
#             }

#     # ── Public warehouse finder ───────────────────────────────────────────────

#     def find_nearest_warehouses(
#         self,
#         origin_lat: float,
#         origin_lon: float,
#         demand_weight: int,
#         exclude_cities: List[str] = None,
#         max_results: int = None,
#         max_distance_km: Optional[float] = None,         # [FIX 4] no default
#         require_road_route_to: Optional[str] = None,     # [FIX 3] road guard
#     ) -> List[Dict]:
#         """
#         Return warehouses sorted by distance from (origin_lat, origin_lon).

#         Exposed as a standalone API endpoint — calls _load_data() first so it
#         always fetches current stock and routes for self.user_id.   [FIX 10]

#         require_road_route_to:
#             Only keep warehouses that have a real road edge TO this city.
#             This is the correct reachability guard — not a distance cap.[FIX 3]

#         max_distance_km:
#             Optional hard fence. No default — do NOT set a global default
#             as it breaks large-country networks.                      [FIX 4]
#         """
#         # Always refresh data for the correct user before scanning warehouses.
#         self._load_data()                                            # [FIX 10]

#         if exclude_cities is None:
#             exclude_cities = []
#         coords        = self._build_city_coords()
#         exclude_lower = {c.lower() for c in exclude_cities}
#         available: List[Dict] = []

#         for _, wh in self.warehouses_df.iterrows():
#             city = str(wh.get("City", "")).strip().lower()
#             if city in exclude_lower:
#                 continue
#             if require_road_route_to and not self._has_road_route(city, require_road_route_to):
#                 continue                                               # [FIX 3]

#             inventory     = int(wh.get("Inventory",    0))
#             reorder_level = int(wh.get("ReorderLevel", 0))
#             available_qty = inventory - reorder_level
#             if available_qty <= 0:
#                 continue

#             lat, lon = coords.get(city, (0.0, 0.0))
#             dist_km  = float(haversine(origin_lat, origin_lon, lat, lon))

#             if max_distance_km is not None and dist_km > max_distance_km:
#                 continue                                               # [FIX 4]

#             available.append({
#                 "user_id":            self.user_id,                  # [FIX 11]
#                 "city":               city,
#                 "Name":               str(wh.get("Name", city)),
#                 "inventory":          inventory,
#                 "reorder_level":      reorder_level,
#                 "available_quantity": available_qty,
#                 "lat":                float(lat),
#                 "lon":                float(lon),
#                 "distance_km":        dist_km,
#             })

#         available.sort(key=lambda x: x["distance_km"])
#         return available if max_results is None else available[:max_results]

#     # ── Main entry point ──────────────────────────────────────────────────────

#     async def handle_disruption(
#         self,
#         source_warehouse: str,
#         destination_city: str,
#         demand_weight: int,
#         disruption_time: str,
#         required_delivery_time: str,
#         repair_duration_hours: int,
#         disruption_location: Optional[str] = None,
#         max_distance_km: Optional[float] = None,
#     ) -> Dict:
#         """
#         Full disruption handling.
 
#         disruption_location is ONLY used in Step 1 to check whether the
#         damaged vehicle can self-recover after repair.  It has NO effect on
#         alternative warehouse selection or scoring.                   [FIX 6]
#         """
#         import logging
#         logger = logging.getLogger(__name__)
 
#         # Normalise types up-front so floats from the request don't bite later
#         demand_weight = int(demand_weight)
 
#         try:
#             # ─────────────────────────────────────────────────────────────────
#             # Step 1 – can the damaged vehicle make it after repair?
#             # ─────────────────────────────────────────────────────────────────
 
#             repair_origin = (disruption_location or source_warehouse).strip()
 
#             original_analysis = self.estimate_delivery_time(
#                 source_city=source_warehouse,
#                 destination_city=destination_city,
#                 repair_duration_hours=repair_duration_hours,
#                 disruption_time=disruption_time,
#                 required_delivery_time=required_delivery_time,
#                 require_road_route=False,
#             )
 
#             result: Dict = {
#                 "disruption_time":        disruption_time,
#                 "required_delivery_time": required_delivery_time,
#                 "repair_duration_hours":  repair_duration_hours,
#                 "demand_weight_kg":       demand_weight,
#                 "user_id":                self.user_id,
#                 "original_route": {
#                     "source":      source_warehouse,
#                     "destination": destination_city,
#                     "analysis":    original_analysis,
#                 },
#                 "original_feasible": bool(original_analysis.get("meets_requirement", False)),
#             }
 
#             if original_analysis.get("meets_requirement"):
#                 result["recommendation"] = "PROCEED_WITH_REPAIR"
#                 result["message"] = "\n".join([
#                     "✅ **Original route still viable after repair**",
#                     f"- Vehicle stuck at: {repair_origin}, repair ~{repair_duration_hours}h",
#                     f"- Repair complete by: {original_analysis.get('repair_completion_time')}",
#                     f"- Estimated arrival at {destination_city}: "
#                     f"{original_analysis.get('estimated_delivery_time')} "
#                     f"(deadline {required_delivery_time} ✅)",
#                     "Proceed with repair and resume delivery.",
#                 ])
#                 return json.loads(json.dumps(result, default=str))
 
#             # ─────────────────────────────────────────────────────────────────
#             # Step 2 – greedy incremental warehouse selection
#             # ─────────────────────────────────────────────────────────────────
 
#             coords = self._build_city_coords()
#             dest_l = destination_city.lower().strip()
#             dest_lat, dest_lon = coords.get(dest_l, (0.0, 0.0))
 
#             if dest_lat == 0.0 and dest_lon == 0.0:
#                 logger.warning(
#                     "[DISRUPTION] No coordinates found for destination '%s'", destination_city
#                 )
 
#             exclude = [destination_city, source_warehouse]
#             if disruption_location:
#                 exclude.append(disruption_location)
 
#             candidates = self.find_nearest_warehouses(
#                 origin_lat=dest_lat,
#                 origin_lon=dest_lon,
#                 demand_weight=demand_weight,
#                 exclude_cities=exclude,
#                 max_distance_km=max_distance_km,
#                 require_road_route_to=destination_city,
#             )
 
#             enriched: List[Dict] = []
#             for wh in candidates:
#                 da = self._estimate_alt_delivery(
#                     wh["city"], destination_city, disruption_time, required_delivery_time
#                 )
#                 if da["feasible"]:
#                     enriched.append({**wh, "alt_delivery": da})
 
#             # result["alternative_warehouses"] = [
#             #     {
#             #         "warehouse_city":               wh["city"],
#             #         "warehouse_name":               wh["Name"],
#             #         "distance_from_destination_km": round(wh["distance_km"], 2),
#             #         "available_inventory":          wh["available_quantity"],
#             #         "inventory":                    wh["inventory"],
#             #         "reorder_level":                wh["reorder_level"],
#             #         "delivery_analysis": {
#             #             "distance_km":             wh["alt_delivery"]["distance_km"],
#             #             "travel_hours":            wh["alt_delivery"]["travel_hours"],
#             #             "estimated_delivery_time": wh["alt_delivery"]["estimated_arrival"],
#             #             "meets_deadline":          wh["alt_delivery"]["meets_deadline"],
#             #             "hours_late":              wh["alt_delivery"].get("hours_late", 0),
#             #         },
#             #         "can_fulfill_demand": wh["available_quantity"] >= demand_weight,
#             #     }
#             #     for wh in enriched
#             # ]
 
#             if not enriched:
#                 result["recommendation"] = "ESCALATE"
#                 # result["warehouse_combinations"] = []
#                 result["message"] = (
#                     f"⚠️ **Disruption detected**\n"
#                     f"- Route: {source_warehouse} → {destination_city}\n"
#                     f"- Disruption at {disruption_time}, repair duration {repair_duration_hours}h\n"
#                     f"- Demand: {demand_weight} kg\n\n"
#                     f"⛔ No road-connected warehouses found near {destination_city}.\n"
#                     f"Consider air freight or emergency procurement."
#                 )
#                 return json.loads(json.dumps(result, default=str))
 
#             # ─────────────────────────────────────────────────────────────────
#             # Greedy loop: [wh0], [wh0,wh1], [wh0,wh1,wh2], …
#             # ─────────────────────────────────────────────────────────────────
 
#             selected: List[Dict] = []
#             combination_attempts: List[Dict] = []
#             final_attempt: Optional[Dict] = None
 
#             for wh in enriched:
#                 selected.append(wh)
 
#                 remaining   = demand_weight
#                 allocations = []
#                 for s in selected:
#                     qty = min(s["available_quantity"], remaining)
#                     allocations.append(qty)
#                     remaining = max(0, remaining - qty)
 
#                 qty_fulfilled = sum(allocations)
#                 demand_met    = (qty_fulfilled >= demand_weight)
 
#                 delivering = [
#                     (selected[i], allocations[i])
#                     for i in range(len(selected))
#                     if allocations[i] > 0
#                 ]
 
#                 bottleneck_wh, _ = max(
#                     delivering,
#                     key=lambda x: x[0]["alt_delivery"]["travel_hours"],
#                 )
#                 bottleneck_label  = bottleneck_wh["alt_delivery"]["estimated_arrival"]
#                 bottleneck_hours  = bottleneck_wh["alt_delivery"]["travel_hours"]
#                 deadline_met      = demand_met and bottleneck_wh["alt_delivery"]["meets_deadline"]
#                 hours_late        = (
#                     bottleneck_wh["alt_delivery"].get("hours_late", 0.0)
#                     if not deadline_met else 0.0
#                 )
 
#                 attempt: Dict = {
#                     "num_warehouses":    len(delivering),
#                     "qty_fulfilled_kg":  qty_fulfilled,
#                     "demand_weight_kg":  demand_weight,
#                     "demand_fully_met":  demand_met,
#                     "bottleneck_arrival": bottleneck_label,
#                     "bottleneck_hours":  round(float(bottleneck_hours), 2),
#                     "meets_deadline":    deadline_met,
#                     "hours_late":        round(float(hours_late), 2),
#                     "warehouses": [
#                         {
#                             "city":                       wh_i["city"],
#                             "name":                       wh_i["Name"],
#                             "delivery_kg":                alloc,
#                             "available_kg":               wh_i["available_quantity"],
#                             "distance_to_destination_km": round(wh_i["distance_km"], 2),
#                             "estimated_arrival":          wh_i["alt_delivery"]["estimated_arrival"],
#                             "travel_hours":               wh_i["alt_delivery"]["travel_hours"],
#                             "meets_deadline":             wh_i["alt_delivery"]["meets_deadline"],
#                         }
#                         for wh_i, alloc in delivering
#                     ],
#                 }
#                 combination_attempts.append(attempt)
 
#                 if demand_met:
#                     final_attempt = attempt
#                     break
 
#             if final_attempt is None:
#                 final_attempt = combination_attempts[-1]
 
#             # result["warehouse_combinations"] = combination_attempts
#             result["final_plan"]             = final_attempt
 
#             # ─────────────────────────────────────────────────────────────────
#             # Assign vehicles for the final delivering warehouses
#             # ─────────────────────────────────────────────────────────────────
 
#             # transport_plans: Dict[str, Optional[Dict]] = {}
#             # for wh_info in final_attempt["warehouses"]:
#             #     transport_plans[wh_info["city"]] = await self._assign_transport(
#             #         wh_info["city"], destination_city, wh_info["delivery_kg"]
#             #     )
#             # result["transport_plans"] = transport_plans

#             transport_plans: List[Dict] = []
#             route_ids: List[int] = []
#             for wh_info in final_attempt["warehouses"]:
#                 plan = await self._assign_transport(
#                     wh_info["city"], destination_city, wh_info["delivery_kg"]
#                 )
#                 if plan:
#                     transport_plans.append(plan)

#                     # ✅ SAFE extraction (no silent failure)
#                     segment = plan.get("data", {}).get("segment", {})
#                     route_id = segment.get("route_id")

#                     if route_id is not None:
#                         route_ids.append(route_id)
                    
#             result["transport_plans"] = transport_plans
#             result["route_ids"] = route_ids
 
#             # ─────────────────────────────────────────────────────────────────
#             # Recommendation tag
#             # ─────────────────────────────────────────────────────────────────
 
#             if not final_attempt["demand_fully_met"]:
#                 result["recommendation"] = "ESCALATE"
#             elif final_attempt["num_warehouses"] == 1:
#                 result["recommendation"] = "DIVERT_TO_WAREHOUSE"
#             else:
#                 result["recommendation"] = "DIVERT_TO_MULTIPLE_WAREHOUSES"
 
#             # ─────────────────────────────────────────────────────────────────
#             # Human-readable message
#             # ─────────────────────────────────────────────────────────────────
 
#             rec_label = {
#                 "PROCEED_WITH_REPAIR":           "PROCEED WITH REPAIR",
#                 "DIVERT_TO_WAREHOUSE":           "USE SINGLE WAREHOUSE",
#                 "DIVERT_TO_MULTIPLE_WAREHOUSES": "USE MULTIPLE WAREHOUSES",
#                 "ESCALATE":                      "ESCALATE – PARTIAL FULFILLMENT",
#             }.get(result["recommendation"], result["recommendation"])
 
#             msg_lines = [
#                 "🚨 Disruption Analysis",
#                 f"Source: {source_warehouse}",
#                 f"Destination: {destination_city}",
#                 f"Disruption Time: {disruption_time}",
#                 f"Repair Duration: {repair_duration_hours} hours",
#                 f"Demand: {demand_weight} kg",
#                 "",
#                 f"🚚 RECOMMENDATION: {rec_label}",
#                 "",
#                 "⚠️ **Disruption detected**",
#                 f"- Route: {source_warehouse} → {destination_city}",
#                 f"- Disruption at {disruption_time}, repair duration {repair_duration_hours}h",
#                 f"- Demand: {demand_weight} kg",
#             ]
 
#             if final_attempt["demand_fully_met"]:
#                 n = final_attempt["num_warehouses"]
#                 divert_label = "divert to warehouse" if n == 1 else "divert to dual warehouses"
#                 msg_lines += ["", f"🚚 **Recommendation:** {divert_label}"]
 
#                 # for wh_info in final_attempt["warehouses"]:
#                 #     tp = transport_plans.get(wh_info["city"])
#                 #     msg_lines.append(
#                 #         f"  * {wh_info['name']} ({wh_info['city']}) – {wh_info['delivery_kg']}kg"
#                 #     )
#                 #     if tp and tp.get("vehicles"):
#                 #         v = tp["vehicles"][0]
#                 #         msg_lines.append(
#                 #             f"    - Vehicle {v['vehicle_id']} departs from "
#                 #             f"{wh_info['name']} at {v['departure']} towards "
#                 #             f"{destination_city.title()}, arrives at {v['arrival']}"
#                 #         )

#                 for idx, wh_info in enumerate(final_attempt["warehouses"]):
#                     tp = transport_plans[idx] if idx < len(transport_plans) else None
#                     msg_lines.append(
#                         f"  * {wh_info['name']} ({wh_info['city']}) – {wh_info['delivery_kg']}kg"
#                     )
#                     if tp:
#                         # New format: {"type": "animate_segment", "data": {"segment": {...}}}
#                         segment = tp["data"]["segment"]
#                         vehicles = segment.get("assigned_vehicles", [])
#                         if vehicles:
#                             v   = vehicles[0]
#                             dep = str(v.get("departure_time", ""))[-5:]
#                             arr = str(v.get("arrival_time",   ""))[-5:]
#                             msg_lines.append(
#                                 f"    - Vehicle {v['vehicle_id']} departs from "
#                                 f"{wh_info['name']} at {dep} towards "
#                                 f"{destination_city.title()}, arrives at {arr}"
#                             )
 
#                 # Per-warehouse detail cards
#                 msg_lines.append("")
#                 for idx, wh_info in enumerate(final_attempt["warehouses"], start=1):
#                     msg_lines += [
#                         f"Warehouse {idx} Details:",
#                         f"- Name: {wh_info['name']}",
#                         f"- City: {wh_info['city']}",
#                         f"- Delivery Quantity: {wh_info['delivery_kg']}kg "
#                         f"(Available: {wh_info['available_kg']}kg)",
#                         "",
#                     ]
#                 msg_lines.append(
#                     f"- Combined Delivery Time: {final_attempt['bottleneck_arrival']}"
#                 )
 
#             else:
#                 shortfall = demand_weight - final_attempt["qty_fulfilled_kg"]
#                 msg_lines += [
#                     "",
#                     "⛔ **Cannot fully meet demand with available warehouses.**",
#                     f"- Best partial: {final_attempt['qty_fulfilled_kg']} kg from "
#                     f"{final_attempt['num_warehouses']} warehouse(s), "
#                     f"arriving by {final_attempt['bottleneck_arrival']}",
#                     f"- Shortfall: {shortfall} kg",
#                     "- Consider air freight or emergency procurement for the remaining quantity.",
#                 ]
 
#             result["message"] = "\n".join(msg_lines)
#             return json.loads(json.dumps(result, default=str))
 
#         except Exception as exc:
#             # Surface the real error instead of silently returning falsy
#             logger.exception(
#                 "[DISRUPTION] handle_disruption FAILED | user=%s | %s → %s | %s",
#                 self.user_id, source_warehouse, destination_city, exc
#             )
#             return {
#                 "success":         False,
#                 "error":           str(exc),
#                 "error_type":      type(exc).__name__,
#                 "source_warehouse": source_warehouse,
#                 "destination_city": destination_city,
#                 "demand_weight_kg": demand_weight,
#                 "message": (
#                     f"⛔ Disruption handler failed for {source_warehouse} → {destination_city}.\n"
#                     f"Error ({type(exc).__name__}): {exc}"
#                 ),
#             }


# # ─────────────────────────────────────────────────────────────────────────────
# # Convenience wrapper
# # ─────────────────────────────────────────────────────────────────────────────

# async def analyze_disruption_scenario(
#     user_id: int,
#     source_warehouse: str,
#     destination_city: str,
#     demand_weight: int,
#     disruption_time: str,
#     required_delivery_time: str,
#     repair_duration_hours: int,
#     disruption_location: Optional[str] = None,
#     max_distance_km: Optional[float] = None,
# ) -> Dict:
    
#     manager = DisruptionManager(user_id=user_id)
#     return await manager.handle_disruption(
#         source_warehouse=source_warehouse,
#         destination_city=destination_city,
#         demand_weight=demand_weight,
#         disruption_time=disruption_time,
#         required_delivery_time=required_delivery_time,
#         repair_duration_hours=repair_duration_hours,
#         disruption_location=disruption_location,
#         max_distance_km=max_distance_km,
#     )


import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Any
import logging
import re
import math
import requests
from itertools import combinations
from backend.database.database import (
    get_warehouses_df,
    get_road_routes_df,
    get_vehicles_df,
    get_air_routes_df,
    get_nodes_by_user,
    prepare_disruption_data
)


logger = logging.getLogger(__name__)

# Constants
AVERAGE_AIR_SPEED = 800   # km/h
AVERAGE_ROAD_SPEED = 60   # km/h
PLANE_SPEED = 800          # km/h
TRUCK_SPEED = 60           # km/h


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points (km)."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return round(2 * math.asin(math.sqrt(a)) * 6371, 2)

def convert_numpy_types(obj):
    """Recursively convert numpy / non-JSON-serialisable types."""
    
    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [convert_numpy_types(v) for v in obj]

    # ✅ Handle numpy types
    if isinstance(obj, (np.integer,)):
        return int(obj)

    if isinstance(obj, (np.floating,)):
        val = float(obj)
        if math.isinf(val) or math.isnan(val):
            return None
        return val

    if isinstance(obj, (np.bool_,)):
        return bool(obj)

    # ✅ Handle Python float edge cases (THIS IS YOUR BUG FIX)
    if isinstance(obj, float):
        if math.isinf(obj) or math.isnan(obj):
            return None

    return obj

# ─────────────────────────────────────────────────────────────────────────────
# Time Parser
# ─────────────────────────────────────────────────────────────────────────────

class TimeParser:
    """Parse natural language time expressions like 'today 10pm', 'tomorrow 6am'."""

    @staticmethod
    def parse_time(time_str: str, reference_date: datetime = None) -> datetime:
        if reference_date is None:
            reference_date = datetime.now()

        time_str = time_str.lower().strip()

        day_offset = 0
        if 'yesterday' in time_str:
            day_offset = -1
            time_str = time_str.replace('yesterday', '').strip()
        elif 'tomorrow' in time_str:
            day_offset = 1
            time_str = time_str.replace('tomorrow', '').strip()
        elif 'today' in time_str:
            time_str = time_str.replace('today', '').strip()

        if ':' in time_str:
            m = re.search(r'(\d{1,2}):(\d{2})', time_str)
            if m:
                hour, minute = int(m.group(1)), int(m.group(2))
            else:
                logger.warning(f"Could not parse time with colon: {time_str}, defaulting to 00:00")
                hour, minute = 0, 0
        elif 'am' in time_str or 'pm' in time_str:
            m = re.search(r'(\d{1,2})\s*(am|pm)', time_str)
            if m:
                hour = int(m.group(1))
                minute = 0
                if m.group(2) == 'pm' and hour != 12:
                    hour += 12
                elif m.group(2) == 'am' and hour == 12:
                    hour = 0
            else:
                logger.warning(f"Could not parse time with am/pm: {time_str}, defaulting to 00:00")
                hour, minute = 0, 0
        else:
            logger.warning(f"Could not parse time: {time_str}, defaulting to 00:00")
            hour, minute = 0, 0

        target_date = reference_date.date() + timedelta(days=day_offset)
        return datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))


# ─────────────────────────────────────────────────────────────────────────────
# Google Maps Service
# ─────────────────────────────────────────────────────────────────────────────

class GoogleMapsService:
    """Thin wrapper around Google Maps Geocoding + Distance Matrix APIs."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key

    def geocode_city(self, city_name: str) -> Optional[Tuple[float, float]]:
        if not self.api_key:
            logger.debug("⚠️ Google Maps API key not configured for geocoding")
            return None
        try:
            logger.info(f"🌍 GEOCODING: '{city_name}'")
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": f"{city_name}, India", "key": self.api_key},
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "OK" and data.get("results"):
                loc = data["results"][0]["geometry"]["location"]
                logger.info(f"✅ GEOCODED: '{city_name}' → ({loc['lat']:.4f}, {loc['lng']:.4f})")
                return (loc["lat"], loc["lng"])
            logger.debug(f"❌ GEOCODING FAILED: '{city_name}' – {data.get('status')}")
            return None
        except Exception as e:
            logger.error(f"❌ GEOCODING ERROR for '{city_name}': {e}")
            return None

    def get_road_distance(self, origin_lat: float, origin_lon: float,
                          dest_lat: float, dest_lon: float) -> Tuple[float, float]:
        """Return (distance_km, duration_hours). Falls back to haversine * 1.2."""
        if not self.api_key:
            dist = haversine(origin_lat, origin_lon, dest_lat, dest_lon) * 1.2
            return (dist, dist / AVERAGE_ROAD_SPEED)
        try:
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/distancematrix/json",
                params={
                    "origins": f"{origin_lat},{origin_lon}",
                    "destinations": f"{dest_lat},{dest_lon}",
                    "key": self.api_key,
                    "mode": "driving",
                },
                timeout=10,
            )
            data = resp.json()
            elem = (data.get("rows") or [{}])[0].get("elements", [{}])[0]
            if data.get("status") == "OK" and elem.get("status") == "OK":
                dist_km = elem["distance"]["value"] / 1000
                dur_h = elem["duration"]["value"] / 3600
                logger.info(f"✅ GOOGLE MAPS DISTANCE: {dist_km:.2f} km, {dur_h:.2f} h")
                return (dist_km, dur_h)
        except Exception as e:
            logger.warning(f"⚠️ Google Maps API error, using fallback: {e}")

        dist = haversine(origin_lat, origin_lon, dest_lat, dest_lon) * 1.2
        return (dist, dist / AVERAGE_ROAD_SPEED)


# ─────────────────────────────────────────────────────────────────────────────
# Disruption Manager
# ─────────────────────────────────────────────────────────────────────────────

class DisruptionManager:

    def __init__(self,
                 user_id: int = None,
                #  warehouses_df: pd.DataFrame = None,
                #  road_routes_df: pd.DataFrame = None,
                #  vehicles_df: pd.DataFrame = None,
                #  air_routes_df: pd.DataFrame = None,
                #  nodes_df: pd.DataFrame = None,
                 google_api_key: str = None):
        
        warehouses_df, road_routes_df, vehicles_df, air_routes_df = (
            prepare_disruption_data(user_id)
        )

        rows = get_nodes_by_user(user_id)

        nodes_df = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["route_id", "from_location", "to_location",
                    "distance", "duration", "cost", "route_type"]
        )
        self.warehouses_df  = warehouses_df  if warehouses_df  is not None else pd.DataFrame()
        self.road_routes_df = road_routes_df if road_routes_df is not None else pd.DataFrame()
        self.vehicles_df    = vehicles_df    if vehicles_df    is not None else pd.DataFrame()
        self.air_routes_df  = air_routes_df  if air_routes_df  is not None else pd.DataFrame()
        self.nodes_df       = nodes_df       if nodes_df       is not None else pd.DataFrame(
            columns=["route_id", "from_location", "to_location",
                        "distance", "duration", "cost", "route_type"]
        )

        self.google_service   = GoogleMapsService(google_api_key)
        self.time_parser      = TimeParser()
        self.coordinate_cache: Dict[str, Tuple[float, float]] = {}

        self._build_coordinate_cache()
        self._normalize_data()
        self._normalize_nodes()

    # ──────────────────────────────────────────────────────────────────────
    # Data loading
    # ──────────────────────────────────────────────────────────────────────

    # def _load_data_from_db(self, user_id: int):
    #     """Load and transform all required DataFrames from the database."""
    #     logger.info(f"Loading disruption data for user_id={user_id}")

    #     self.warehouses_df  = get_warehouses_df(user_id)
    #     self.road_routes_df = get_road_routes_df(user_id)
    #     self.air_routes_df  = get_air_routes_df(user_id)
    #     logger.info(f"Loaded {len(self.warehouses_df)} warehouses, "
    #                 f"{len(self.road_routes_df)} road routes, "
    #                 f"{len(self.air_routes_df)} air routes")

    #     # Vehicles – rename columns to internal names
    #     veh_df = get_vehicles_df(user_id)
    #     if not veh_df.empty:
    #         if 'departure_time' in veh_df.columns:
    #             veh_df['departure_time'] = (
    #                 pd.to_datetime(veh_df['departure_time'], format='%H:%M:%S', errors='coerce')
    #                   .dt.strftime('%H:%M')
    #                   .fillna('00:00')
    #             )
    #         else:
    #             veh_df['departure_time'] = '00:00'
    #         if 'vehicle_id' not in veh_df.columns:
    #             veh_df['vehicle_id'] = None
    #     self.vehicles_df = veh_df
    #     logger.info(f"Loaded {len(self.vehicles_df)} vehicles")

    #     # nodes_combined
    #     rows = get_nodes_by_user(user_id)
    #     self.nodes_df = pd.DataFrame(rows) if rows else pd.DataFrame(
    #         columns=["route_id", "from_location", "to_location",
    #                  "distance", "duration", "cost", "route_type"]
    #     )
    #     logger.info(f"Loaded {len(self.nodes_df)} nodes_combined rows")

    # ──────────────────────────────────────────────────────────────────────
    # Normalisation helpers
    # ──────────────────────────────────────────────────────────────────────

    def _normalize_data(self):
        """Lowercase city name columns for consistent matching."""
        try:
            if 'City' in self.warehouses_df.columns:
                self.warehouses_df['city_lower'] = (
                    self.warehouses_df['City'].str.lower().str.strip()
                )
            if 'base_city' in self.vehicles_df.columns:
                self.vehicles_df['warehouse_lower'] = (
                    self.vehicles_df['base_city'].str.lower().str.strip()
                )
            else:
                logger.warning("⚠️ base_city column not found in vehicles_df. "
                               f"Available: {list(self.vehicles_df.columns)}")
        except Exception as e:
            logger.error(f"❌ Error normalizing data: {e}")
            

    def _normalize_nodes(self):
        """Lowercase from/to columns in nodes_df for case-insensitive matching."""
        if self.nodes_df.empty:
            logger.warning("⚠️ nodes_df is empty – direct-route filtering disabled")
            return
        self.nodes_df['from_lower'] = self.nodes_df['from_location'].str.lower().str.strip()
        self.nodes_df['to_lower']   = self.nodes_df['to_location'].str.lower().str.strip()
        logger.info(f"✅ Normalized nodes_combined ({len(self.nodes_df)} rows)")

    def _build_coordinate_cache(self):
        """Populate coordinate cache from road and air route tables."""
        logger.info("🔨 Building coordinate cache from routes...")
        try:
            if self.road_routes_df is not None and not self.road_routes_df.empty:
                for _, row in self.road_routes_df.iterrows():
                    src = str(row['source_city']).lower().strip()
                    dst = str(row['destination_city']).lower().strip()
                    self.coordinate_cache.setdefault(src, (float(row['lat_src']), float(row['lon_src'])))
                    self.coordinate_cache.setdefault(dst, (float(row['lat_dst']), float(row['lon_dst'])))

            if self.air_routes_df is not None and not self.air_routes_df.empty:
                for _, row in self.air_routes_df.iterrows():
                    src = str(row['source_airport']).lower().strip()
                    dst = str(row['destination_airport']).lower().strip()
                    self.coordinate_cache.setdefault(src, (float(row['lat_src']), float(row['lon_src'])))
                    self.coordinate_cache.setdefault(dst, (float(row['lat_dst']), float(row['lon_dst'])))

            logger.info(f"✅ Coordinate cache: {len(self.coordinate_cache)} cities – "
                        f"{sorted(self.coordinate_cache.keys())}")
        except Exception as e:
            logger.error(f"❌ Error building coordinate cache: {e}")

    # ──────────────────────────────────────────────────────────────────────
    # Direct-route lookup (nodes_combined)
    # ──────────────────────────────────────────────────────────────────────

    def _get_direct_route(self,
                      from_city: str,
                      to_city: str,
                      route_type: str = None) -> Optional[Dict]:

        if self.nodes_df.empty:
            # Warning already emitted once at startup in _normalize_nodes — use DEBUG here
            logger.debug("nodes_df is empty – direct-route lookup skipped")
            return None                       # ← returns None → warehouse is skipped

        from_lower = from_city.lower().strip()
        to_lower   = to_city.lower().strip()

        mask = (
            (self.nodes_df['from_lower'] == from_lower) &
            (self.nodes_df['to_lower']   == to_lower)
        )
        if route_type:
            mask &= (self.nodes_df['route_type'] == route_type)

        matches = self.nodes_df[mask]
        if matches.empty:
            logger.debug(f"🚫 No direct {route_type or 'any'} route: {from_city} → {to_city}")
            return None

        row = matches.iloc[0]
        return {
            'route_id':   int(row['route_id']),
            'distance':   float(row['distance']) if pd.notna(row['distance']) else 0.0,
            'duration':   float(row['duration']) if pd.notna(row['duration']) else 0.0,
            'cost':       float(row['cost'])     if pd.notna(row['cost'])     else 0.0,
            'route_type': row['route_type'],
        }
    
    # ──────────────────────────────────────────────────────────────────────
    # Coordinate & distance helpers
    # ──────────────────────────────────────────────────────────────────────

    def _get_coordinates(self, city_name: str,
                         route_type: str = 'road') -> Optional[Tuple[float, float]]:
        city_lower = city_name.lower().strip()

        if city_lower in self.coordinate_cache:
            return self.coordinate_cache[city_lower]

        # Search road routes
        if route_type == 'road' and self.road_routes_df is not None:
            for _, row in self.road_routes_df.iterrows():
                if str(row['source_city']).lower() == city_lower:
                    return (float(row['lat_src']), float(row['lon_src']))
                if str(row['destination_city']).lower() == city_lower:
                    return (float(row['lat_dst']), float(row['lon_dst']))

        # Search air routes
        if route_type == 'air' and self.air_routes_df is not None:
            for _, row in self.air_routes_df.iterrows():
                if str(row['source_airport']).lower() == city_lower:
                    return (float(row['lat_src']), float(row['lon_src']))
                if str(row['destination_airport']).lower() == city_lower:
                    return (float(row['lat_dst']), float(row['lon_dst']))

        # Fallback: Google Maps geocoding
        coords = self.google_service.geocode_city(city_name)
        if coords:
            self.coordinate_cache[city_lower] = coords
            return coords

        logger.warning(f"⚠️ Could not find coordinates for {city_name}")
        return None

    def get_distance_between_cities(self, source_city: str, destination_city: str) -> float:
        src_lower  = source_city.lower().strip()
        dest_lower = destination_city.lower().strip()

        if src_lower not in self.coordinate_cache or dest_lower not in self.coordinate_cache:
            logger.warning(f"⚠️ Missing coordinates: {source_city} or {destination_city}")
            return 0

        src_lat,  src_lon  = self.coordinate_cache[src_lower]
        dest_lat, dest_lon = self.coordinate_cache[dest_lower]

        if self.google_service.api_key:
            try:
                dist, _ = self.google_service.get_road_distance(src_lat, src_lon, dest_lat, dest_lon)
                if dist > 0:
                    return dist
            except Exception:
                pass

        return haversine(src_lat, src_lon, dest_lat, dest_lon)

    # ──────────────────────────────────────────────────────────────────────
    # Vehicle helpers
    # ──────────────────────────────────────────────────────────────────────

    # def _get_available_vehicles(self, warehouse: str, current_time: datetime,
    #                             demand_kg: int, mode: str = 'road') -> List[Dict]:
    #     """
    #     Return vehicles from *warehouse* that:
    #       • depart at or after current_time
    #       • have capacity >= demand_kg
    #     Sorted by earliest departure.
    #     """
    #     warehouse_lower = warehouse.lower().strip()

    #     if 'warehouse_lower' not in self.vehicles_df.columns:
    #         self.vehicles_df['warehouse_lower'] = (
    #             self.vehicles_df['base_city'].str.lower().str.strip()
    #         )

    #     wh_vehicles = self.vehicles_df[
    #         self.vehicles_df['warehouse_lower'] == warehouse_lower
    #     ].copy()

    #     if wh_vehicles.empty:
    #         return []

    #     available = []
    #     counter = 0
    #     for _, v in wh_vehicles.iterrows():
    #         try:
    #             h, m = map(int, str(v['departure_time']).split(':'))
    #             dept = current_time.replace(hour=h, minute=m, second=0, microsecond=0)
    #             if dept < current_time:
    #                 dept += timedelta(days=1)

    #             capacity = int(v['capacity_kg'])
    #             if capacity < demand_kg:
    #                 continue

    #             counter += 1
    #             v_type = 'Plane' if mode == 'air' else str(v['vehicle_type']).strip()
    #             v_id   = v.get('vehicle_id', None)

    #             if not v_id or (isinstance(v_id, float) and pd.isna(v_id)):
    #                 prefix    = warehouse[:3].upper()
    #                 type_code = 'PLA' if mode == 'air' else str(v_type).upper()[:3]
    #                 v_id      = f"{prefix}-{type_code}-{counter:02d}"
    #                 existing  = [x['vehicle_id'] for x in available]
    #                 while v_id in existing:
    #                     counter += 1
    #                     v_id = f"{prefix}-{type_code}-{counter:02d}"

    #             available.append({
    #                 'vehicle_id': v_id,
    #                 'type':       v_type,
    #                 'capacity':   capacity,
    #                 'departure':  dept,
    #                 'warehouse':  warehouse,
    #             })
    #         except Exception:
    #             continue

    #     available.sort(key=lambda x: x['departure'])
    #     return available
    def _get_available_vehicles(self, warehouse: str, current_time: datetime,
                            demand_kg: int, mode: str = 'road') -> List[Dict]:
        warehouse_lower = warehouse.lower().strip()

        if 'warehouse_lower' not in self.vehicles_df.columns:
            self.vehicles_df['warehouse_lower'] = (
                self.vehicles_df['base_city'].str.lower().str.strip()
            )

        wh_vehicles = self.vehicles_df[
            self.vehicles_df['warehouse_lower'] == warehouse_lower
        ].copy()

        if wh_vehicles.empty:
            return []

        available = []
        counter = 0
        for _, v in wh_vehicles.iterrows():
            try:
                capacity = int(v['capacity_kg'])
                if capacity < demand_kg:
                    continue

                actual_type = str(v['vehicle_type']).strip().lower()

                # ── MODE GATE: enforce vehicle ↔ route type compatibility ──
                if mode == 'road' and actual_type == 'plane':
                    continue   # planes cannot serve road routes
                if mode == 'air' and actual_type != 'plane':
                    continue   # only planes can serve air routes

                counter += 1
                v_type = 'Plane' if mode == 'air' else str(v['vehicle_type']).strip()
                v_id   = v.get('vehicle_id', None)

                if not v_id or (isinstance(v_id, float) and pd.isna(v_id)):
                    prefix    = warehouse[:3].upper()
                    type_code = 'PLA' if mode == 'air' else str(v_type).upper()[:3]
                    v_id      = f"{prefix}-{type_code}-{counter:02d}"
                    existing  = [x['vehicle_id'] for x in available]
                    while v_id in existing:
                        counter += 1
                        v_id = f"{prefix}-{type_code}-{counter:02d}"

                available.append({
                    'vehicle_id': v_id,
                    'type':       v_type,
                    'capacity':   capacity,
                    'departure':  current_time,
                    'warehouse':  warehouse,
                })
            except Exception:
                continue

        available.sort(key=lambda x: x['departure'])
        return available

        
    # def _get_available_vehicles(self, warehouse: str, current_time: datetime,
    #                         demand_kg: int, mode: str = 'road') -> List[Dict]:
    #     """
    #     Return vehicles from *warehouse* that:
    #     • have capacity >= demand_kg
    #     • depart immediately (at current_time)
    #     (Original departure_time column is ignored.)
    #     """
    #     warehouse_lower = warehouse.lower().strip()

    #     if 'warehouse_lower' not in self.vehicles_df.columns:
    #         self.vehicles_df['warehouse_lower'] = (
    #             self.vehicles_df['base_city'].str.lower().str.strip()
    #         )

    #     wh_vehicles = self.vehicles_df[
    #         self.vehicles_df['warehouse_lower'] == warehouse_lower
    #     ].copy()

    #     if wh_vehicles.empty:
    #         return []

    #     available = []
    #     counter = 0
    #     for _, v in wh_vehicles.iterrows():
    #         try:
    #             capacity = int(v['capacity_kg'])
    #             if capacity < demand_kg:
    #                 continue

    #             counter += 1
    #             v_type = 'Plane' if mode == 'air' else str(v['vehicle_type']).strip()
    #             v_id   = v.get('vehicle_id', None)

    #             if not v_id or (isinstance(v_id, float) and pd.isna(v_id)):
    #                 prefix    = warehouse[:3].upper()
    #                 type_code = 'PLA' if mode == 'air' else str(v_type).upper()[:3]
    #                 v_id      = f"{prefix}-{type_code}-{counter:02d}"
    #                 existing  = [x['vehicle_id'] for x in available]
    #                 while v_id in existing:
    #                     counter += 1
    #                     v_id = f"{prefix}-{type_code}-{counter:02d}"

    #             available.append({
    #                 'vehicle_id': v_id,
    #                 'type':       v_type,
    #                 'capacity':   capacity,
    #                 'departure':  current_time,      # <-- changed: use current timestamp
    #                 'warehouse':  warehouse,
    #             })
    #         except Exception:
    #             continue

    #     # Sorting by departure is no longer meaningful, but kept for consistency
    #     available.sort(key=lambda x: x['departure'])
    #     return available


    def _calculate_arrival_time(self, departure_time: datetime,
                                distance_km: float, mode: str = 'road') -> datetime:
        speed = TRUCK_SPEED if mode == 'road' else PLANE_SPEED
        return departure_time + timedelta(hours=distance_km / speed)

    # ──────────────────────────────────────────────────────────────────────
    # Core: find warehouse combinations (with direct-route gate)
    # ──────────────────────────────────────────────────────────────────────

    def _find_warehouse_combinations(self, destination: str, demand_kg: int,
                                     required_delivery: datetime, current_time: datetime,
                                     mode: str = 'road',
                                     exclude_city: str = None) -> List[Dict]:
        """
        Find single or multi-warehouse combinations that can fulfil demand_kg.

        Only warehouses that have a DIRECT route entry in nodes_combined
        (from_location=warehouse, to_location=destination, route_type=mode)
        are considered.

        Each solution dict contains:
            warehouses      – list of warehouse info dicts (each with 'route_id')
            total_inventory – total kg available
            latest_arrival  – datetime of the last arriving shipment
            meets_deadline  – bool
            min_distance    – shortest individual leg (km)
            route_ids       – list of route_id values for each selected warehouse

        Sorting: deadline-meeting first → earliest arrival → shortest distance.
        """
        dest_coords = self._get_coordinates(destination, mode)
        if not dest_coords:
            logger.warning(f"⚠️ No coordinates for destination: {destination}")
            return []

        dest_lat, dest_lon = dest_coords
        candidates = []

        for _, wh in self.warehouses_df.iterrows():
            city      = wh['Name']
            inventory = int(wh.get('Inventory', 0))

            if inventory <= 0:
                continue
            if exclude_city and city.lower().strip() == exclude_city.lower().strip():
                continue

            # ── DIRECT-ROUTE GATE ────────────────────────────────────────
            direct = self._get_direct_route(city, destination, route_type=mode)
            if direct is None:
                logger.debug(f"⏭️ Skipping {city}: no direct {mode} route to {destination}")
                continue

            # Use stored distance when valid
            if direct['distance'] > 0:
                distance = direct['distance']
                duration = direct['duration'] if direct['duration'] > 0 else (
                    distance / (TRUCK_SPEED if mode == 'road' else PLANE_SPEED)
                )
            else:
                if mode == 'road':
                    distance = self.get_distance_between_cities(city, destination)
                    duration = distance / TRUCK_SPEED
                else:
                    wh_coords = self._get_coordinates(city, 'air')
                    if not wh_coords:
                        continue
                    distance = haversine(wh_coords[0], wh_coords[1], dest_lat, dest_lon)
                    duration = distance / PLANE_SPEED

            if distance <= 0:
                continue

            vehicles = self._get_available_vehicles(city, current_time, inventory, mode=mode)
            if not vehicles:
                continue

            vehicle = vehicles[0]
            arrival = self._calculate_arrival_time(vehicle['departure'], distance, mode)

            candidates.append({
                'city':           city,
                'inventory':      inventory,
                'distance':       distance,
                'duration':       duration,
                'vehicle':        vehicle,
                'arrival':        arrival,
                'meets_deadline': arrival <= required_delivery,
                'route_id':       direct['route_id'],
                'route_type':     direct['route_type'],
            })

        if not candidates:
            return []

        candidates.sort(key=lambda x: x['distance'])

        solutions = []

        # Single warehouse
        for wh in candidates:
            if wh['inventory'] >= demand_kg:
                solutions.append({
                    'warehouses':      [wh],
                    'total_inventory': wh['inventory'],
                    'latest_arrival':  wh['arrival'],
                    'meets_deadline':  wh['meets_deadline'],
                    'min_distance':    wh['distance'],
                    'route_ids':       [wh['route_id']],
                })

        # Two-warehouse combinations
        for wh1, wh2 in combinations(candidates, 2):
            total = wh1['inventory'] + wh2['inventory']
            if total >= demand_kg:
                latest = max(wh1['arrival'], wh2['arrival'])
                solutions.append({
                    'warehouses':      [wh1, wh2],
                    'total_inventory': total,
                    'latest_arrival':  latest,
                    'meets_deadline':  latest <= required_delivery,
                    'min_distance':    min(wh1['distance'], wh2['distance']),
                    'route_ids':       [wh1['route_id'], wh2['route_id']],
                })

        # Three-warehouse combinations
        for wh1, wh2, wh3 in combinations(candidates, 3):
            total = wh1['inventory'] + wh2['inventory'] + wh3['inventory']
            if total >= demand_kg:
                latest = max(wh1['arrival'], wh2['arrival'], wh3['arrival'])
                solutions.append({
                    'warehouses':      [wh1, wh2, wh3],
                    'total_inventory': total,
                    'latest_arrival':  latest,
                    'meets_deadline':  latest <= required_delivery,
                    'min_distance':    min(wh1['distance'], wh2['distance'], wh3['distance']),
                    'route_ids':       [wh1['route_id'], wh2['route_id'], wh3['route_id']],
                })

        solutions.sort(key=lambda x: (not x['meets_deadline'],
                                      x['latest_arrival'],
                                      x['min_distance']))

        logger.info(f"✅ Found {len(solutions)} combinations for {destination} ({mode})")
        if solutions:
            best = solutions[0]
            logger.info(f"   Best: {len(best['warehouses'])} wh(s), "
                        f"total={best['total_inventory']}kg, "
                        f"arrival={best['latest_arrival'].strftime('%H:%M %d-%m-%Y')}, "
                        f"route_ids={best['route_ids']}")
        return solutions

    # ──────────────────────────────────────────────────────────────────────
    # Road disruption handler
    # ──────────────────────────────────────────────────────────────────────

    def handle_road_disruption(self, source_warehouse: str, destination_city: str,
                               demand_weight: int, disruption_time: str, repair_hours: int,
                               required_delivery_time: str,
                               disruption_location: str = None) -> Dict:
        """
        Handle a road-route disruption.

        Priority:
          Tier 1 – Original route (after repair) meets deadline  → WAIT_FOR_REPAIR
          Tier 2 – Road alternatives from other warehouses meet deadline
          Tier 3 – Air alternatives meet deadline
          Tier 4 – Nothing meets deadline; return best options from all tiers
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"🚨 ROAD DISRUPTION: {source_warehouse} → {destination_city}")
        logger.info(f"{'='*80}")

        current_time        = datetime.now()
        disruption_dt       = self.time_parser.parse_time(disruption_time, current_time)
        required_delivery_dt = self.time_parser.parse_time(required_delivery_time, current_time)

        if disruption_dt > current_time:
            return {
                'message': 'Disruption time cannot be in the future'
            }

        logger.info(f"⏰ Disruption:         {disruption_dt.strftime('%H:%M on %d-%m-%Y')}")
        logger.info(f"⏰ Required Delivery:  {required_delivery_dt.strftime('%H:%M on %d-%m-%Y')}")
        logger.info(f"📦 Demand:            {demand_weight} kg")
        logger.info(f"🔧 Repair Time:       {repair_hours} hours")

        src_coords  = self._get_coordinates(source_warehouse, 'road')
        dest_coords = self._get_coordinates(destination_city,  'road')

        if not src_coords:
            return {'message': 'Could not determine coordinates for source warehouse'}
        
        if not dest_coords:
            return {'message': 'Could not determine coordinates for destination warehouse'}

        # ── TIER 1: original route after repair ──────────────────────────
        repair_complete  = disruption_dt + timedelta(hours=repair_hours)
        road_distance    = self.get_distance_between_cities(source_warehouse, destination_city)
        src_vehicles     = self._get_available_vehicles(
            source_warehouse, repair_complete, demand_weight, mode='road'
        )

        original_solution = None
        if src_vehicles and road_distance > 0:
            v       = src_vehicles[0]
            arrival = self._calculate_arrival_time(v['departure'], road_distance, 'road')
            original_solution = {
                'type':           'ORIGINAL_ROUTE',
                'distance':       road_distance,
                'departure':      v['departure'],
                'arrival':        arrival,
                'meets_deadline': arrival <= required_delivery_dt,
                'vehicle':        v,
            }
            logger.info(f"\n📍 ORIGINAL ROUTE (After Repair):")
            logger.info(f"   Repair Complete: {repair_complete.strftime('%H:%M on %d-%m-%Y')}")
            logger.info(f"   Distance:        {road_distance:.2f} km")
            logger.info(f"   Departure:       {v['departure'].strftime('%H:%M on %d-%m-%Y')}")
            logger.info(f"   Arrival:         {arrival.strftime('%H:%M on %d-%m-%Y')}")
            logger.info(f"   Meets Deadline:  {'✅' if original_solution['meets_deadline'] else '❌'}")

        if original_solution and original_solution['meets_deadline']:
            return self._format_response(
                disruption_type='road',
                source=source_warehouse,
                destination=destination_city,
                demand_kg=demand_weight,
                disruption_time=disruption_dt,
                required_delivery=required_delivery_dt,
                repair_hours=repair_hours,
                recommendation='WAIT_FOR_REPAIR',
                reason='Original route (after repair) meets deadline',
                original_route=original_solution,
            )

        # ── TIER 2: road alternatives ─────────────────────────────────────
        logger.info(f"\n🚚 SEARCHING ROAD ALTERNATIVES...")

        road_candidates = []
        for _, wh in self.warehouses_df.iterrows():
            city      = wh['Name']
            inventory = int(wh.get('Inventory', 0))

            if city.lower().strip() == source_warehouse.lower().strip():
                continue
            if inventory <= 0:
                continue

            # Direct-route gate
            direct = self._get_direct_route(city, destination_city, route_type='road')
            if direct is None:
                logger.debug(f"⏭️ Skipping {city}: no direct road route to {destination_city}")
                continue

            wh_coords = self._get_coordinates(city, 'road')
            if not wh_coords:
                continue

            distance = direct['distance'] if direct['distance'] > 0 else (
                self.get_distance_between_cities(city, destination_city)
            )
            if distance <= 0:
                continue

            vehicles = self._get_available_vehicles(city, current_time, inventory, mode='road')
            if not vehicles:
                continue

            v       = vehicles[0]
            arrival = self._calculate_arrival_time(v['departure'], distance, 'road')

            road_candidates.append({
                'city':           city,
                'inventory':      inventory,
                'distance':       distance,
                'duration':       distance / TRUCK_SPEED,
                'vehicle':        v,
                'arrival':        arrival,
                'meets_deadline': arrival <= required_delivery_dt,
                'route_id':       direct['route_id'],
                'route_type':     'road',
            })

        road_candidates.sort(key=lambda x: x['arrival'])
        road_solutions = self._build_solutions(road_candidates, demand_weight, required_delivery_dt)

        if road_solutions and road_solutions[0]['meets_deadline']:
            best = road_solutions[0]
            return self._format_response(
                disruption_type='road',
                source=source_warehouse,
                destination=destination_city,
                demand_kg=demand_weight,
                disruption_time=disruption_dt,
                required_delivery=required_delivery_dt,
                repair_hours=repair_hours,
                recommendation='USE_ROAD_ALTERNATIVES',
                reason=(f"Road alternatives ({len(best['warehouses'])} warehouse(s)) meet deadline "
                        f"(arrival: {best['latest_arrival'].strftime('%H:%M on %d-%m-%Y')})"),
                original_route=original_solution,
                road_alternatives=best,
            )

        # ── TIER 3: air alternatives ──────────────────────────────────────
        logger.info(f"\n✈️ SEARCHING AIR ALTERNATIVES...")

        air_candidates = []
        dest_coords_air = self._get_coordinates(destination_city, 'air')
        if dest_coords_air:
            for _, wh in self.warehouses_df.iterrows():
                city      = wh['Name']
                inventory = int(wh.get('Inventory', 0))
                if inventory <= 0:
                    continue

                direct = self._get_direct_route(city, destination_city, route_type='air')
                if direct is None:
                    logger.debug(f"⏭️ Skipping {city}: no direct air route to {destination_city}")
                    continue

                wh_coords = self._get_coordinates(city, 'air')
                if not wh_coords:
                    continue

                if direct['distance'] > 0:
                    distance = direct['distance']
                else:
                    distance = haversine(wh_coords[0], wh_coords[1],
                                         dest_coords_air[0], dest_coords_air[1])
                if distance <= 0:
                    continue

                vehicles = self._get_available_vehicles(city, current_time, inventory, mode='air')
                if not vehicles:
                    continue

                v       = vehicles[0]
                arrival = self._calculate_arrival_time(v['departure'], distance, 'air')

                air_candidates.append({
                    'city':           city,
                    'inventory':      inventory,
                    'distance':       distance,
                    'duration':       distance / PLANE_SPEED,
                    'vehicle':        v,
                    'arrival':        arrival,
                    'meets_deadline': arrival <= required_delivery_dt,
                    'route_id':       direct['route_id'],
                    'route_type':     'air',
                })

        air_candidates.sort(key=lambda x: x['arrival'])
        air_solutions = self._build_solutions(air_candidates, demand_weight, required_delivery_dt)

        if air_solutions and air_solutions[0]['meets_deadline']:
            best = air_solutions[0]
            return self._format_response(
                disruption_type='road',
                source=source_warehouse,
                destination=destination_city,
                demand_kg=demand_weight,
                disruption_time=disruption_dt,
                required_delivery=required_delivery_dt,
                repair_hours=repair_hours,
                recommendation='USE_AIR_ALTERNATIVES',
                reason=(f"Air alternatives meet deadline "
                        f"(arrival: {best['latest_arrival'].strftime('%H:%M on %d-%m-%Y')})"),
                original_route=original_solution,
                air_alternatives=best,
            )

        # ── TIER 4: nothing meets deadline ────────────────────────────────
        if not original_solution and not road_solutions and not air_solutions:
            return {'message': 'No viable solutions found'}

        if road_solutions and air_solutions:
            rec    = 'USE_BOTH_ROAD_AND_AIR_ALTERNATIVES'
            reason = 'Neither road nor air alternatives meet deadline; presenting both.'
        elif road_solutions:
            rec    = 'USE_ROAD_ALTERNATIVES'
            reason = 'Road alternatives available but deadline missed.'
        elif air_solutions:
            rec    = 'USE_AIR_ALTERNATIVES'
            reason = 'Air alternatives available but deadline missed.'
        else:
            rec    = 'WAIT_FOR_REPAIR'
            reason = 'No alternatives found; wait for repair.'

        return self._format_response(
            disruption_type='road',
            source=source_warehouse,
            destination=destination_city,
            demand_kg=demand_weight,
            disruption_time=disruption_dt,
            required_delivery=required_delivery_dt,
            repair_hours=repair_hours,
            recommendation=rec,
            reason=reason,
            original_route=original_solution,
            road_alternatives=road_solutions[0] if road_solutions else None,
            air_alternatives=air_solutions[0]  if air_solutions  else None,
            all_road_alternatives=road_solutions,
            all_air_alternatives=air_solutions,
        )

    def handle_air_route_disruption(self, source_warehouse: str, destination_city: str,
                                demand_weight: int, disruption_time: str,
                                flight_delay_minutes: int,
                                required_delivery_time: str) -> Dict:
        """
        Handle an air-route disruption.
        Uses the same source_warehouse / destination_city naming as road disruptions,
        because air routes are keyed by warehouse name in nearest_airports.
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"✈️ AIR DISRUPTION: {source_warehouse} → {destination_city}")
        logger.info(f"{'='*80}")

        current_time         = datetime.now()
        disruption_dt        = self.time_parser.parse_time(disruption_time, current_time)
        required_delivery_dt = self.time_parser.parse_time(required_delivery_time, current_time)

        if disruption_dt > current_time:
            return {
                'message': 'Disruption time cannot be in the future'
            }

        delay_hours = flight_delay_minutes / 60
        logger.info(f"⏰ Disruption:        {disruption_dt.strftime('%H:%M on %d-%m-%Y')}")
        logger.info(f"⏰ Required Delivery: {required_delivery_dt.strftime('%H:%M on %d-%m-%Y')}")
        logger.info(f"📦 Demand:           {demand_weight} kg")
        logger.info(f"⏱️ Delay:            {flight_delay_minutes} min ({delay_hours:.1f} h)")

        # Air coordinates are stored under warehouse names in the cache
        src_coords  = self._get_coordinates(source_warehouse, 'air')
        dest_coords = self._get_coordinates(destination_city, 'air')

        if not src_coords:
            return {'message': 'Could not determine coordinates for source warehouse'}
        
        if not dest_coords:
            return {'message': 'Could not determine coordinates for destination warehouse'}

        # ── TIER 1: delayed flight ────────────────────────────────────────
        flight_ready    = disruption_dt + timedelta(minutes=flight_delay_minutes)
        air_distance    = haversine(src_coords[0], src_coords[1], dest_coords[0], dest_coords[1])
        delayed_arrival = self._calculate_arrival_time(flight_ready, air_distance, 'air')

        original_solution = {
            'type':           'DELAYED_FLIGHT',
            'distance':       air_distance,
            'departure':      flight_ready,
            'arrival':        delayed_arrival,
            'meets_deadline': delayed_arrival <= required_delivery_dt,
            'delay_minutes':  flight_delay_minutes,
        }

        logger.info(f"\n✈️ DELAYED FLIGHT:")
        logger.info(f"   Ready:          {flight_ready.strftime('%H:%M on %d-%m-%Y')}")
        logger.info(f"   Distance:       {air_distance:.2f} km")
        logger.info(f"   Arrival:        {delayed_arrival.strftime('%H:%M on %d-%m-%Y')}")
        logger.info(f"   Meets Deadline: {'✅' if original_solution['meets_deadline'] else '❌'}")

        if original_solution['meets_deadline']:
            return self._format_response(
                disruption_type='air',
                source=source_warehouse,
                destination=destination_city,
                demand_kg=demand_weight,
                disruption_time=disruption_dt,
                required_delivery=required_delivery_dt,
                delay_minutes=flight_delay_minutes,
                recommendation='WAIT_FOR_DELAYED_FLIGHT',
                reason='Delayed flight still meets deadline',
                original_route=original_solution,
            )

        # ── TIER 2: road alternatives ─────────────────────────────────────
        logger.info(f"\n🚚 SEARCHING ROAD ALTERNATIVES...")
        road_solutions = self._find_warehouse_combinations(
            destination_city, demand_weight, required_delivery_dt,
            current_time, 'road', exclude_city=source_warehouse
        )

        if road_solutions and road_solutions[0]['meets_deadline']:
            best = road_solutions[0]
            return self._format_response(
                disruption_type='air',
                source=source_warehouse,
                destination=destination_city,
                demand_kg=demand_weight,
                disruption_time=disruption_dt,
                required_delivery=required_delivery_dt,
                delay_minutes=flight_delay_minutes,
                recommendation='USE_ROAD_ALTERNATIVES',
                reason=(f"Road alternatives meet deadline "
                        f"(arrival: {best['latest_arrival'].strftime('%H:%M on %d-%m-%Y')})"),
                original_route=original_solution,
                road_alternatives=best,
            )

        # ── TIER 3: air alternatives ──────────────────────────────────────
        logger.info(f"\n✈️ SEARCHING AIR ALTERNATIVES...")
        air_solutions = self._find_warehouse_combinations(
            destination_city, demand_weight, required_delivery_dt,
            current_time, 'air', exclude_city=source_warehouse
        )

        if air_solutions and air_solutions[0]['meets_deadline']:
            best = air_solutions[0]
            return self._format_response(
                disruption_type='air',
                source=source_warehouse,
                destination=destination_city,
                demand_kg=demand_weight,
                disruption_time=disruption_dt,
                required_delivery=required_delivery_dt,
                delay_minutes=flight_delay_minutes,
                recommendation='USE_AIR_ALTERNATIVES',
                reason=(f"Alternative flights meet deadline "
                        f"(arrival: {best['latest_arrival'].strftime('%H:%M on %d-%m-%Y')})"),
                original_route=original_solution,
                air_alternatives=best,
            )

        # ── TIER 4: nothing meets deadline ────────────────────────────────
        if not original_solution and not road_solutions and not air_solutions:
            return {'message': 'No viable solutions found'}

        if road_solutions and air_solutions:
            rec    = 'USE_BOTH_ROAD_AND_AIR_ALTERNATIVES'
            reason = 'Neither road nor air alternatives meet deadline; presenting both.'
        elif road_solutions:
            rec    = 'USE_ROAD_ALTERNATIVES'
            reason = 'Road alternatives available but deadline missed.'
        elif air_solutions:
            rec    = 'USE_AIR_ALTERNATIVES'
            reason = 'Air alternatives available but deadline missed.'
        else:
            rec    = 'WAIT_FOR_DELAYED_FLIGHT'
            reason = 'No alternatives found; take the delayed flight.'

        return self._format_response(
            disruption_type='air',
            source=source_warehouse,
            destination=destination_city,
            demand_kg=demand_weight,
            disruption_time=disruption_dt,
            required_delivery=required_delivery_dt,
            delay_minutes=flight_delay_minutes,
            recommendation=rec,
            reason=reason,
            original_route=original_solution,
            road_alternatives=road_solutions[0] if road_solutions else None,
            air_alternatives=air_solutions[0]  if air_solutions  else None,
            all_road_alternatives=road_solutions,
            all_air_alternatives=air_solutions,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Internal: build solution list from pre-filtered candidates
    # ──────────────────────────────────────────────────────────────────────

    def _build_solutions(self, candidates: List[Dict],
                         demand_kg: int,
                         required_delivery: datetime) -> List[Dict]:
        """
        Given a list of already-filtered candidate warehouse dicts, produce
        all viable single / 2-wh / 3-wh combinations sorted by:
            deadline compliance → latest_arrival → min_distance
        Each solution carries a 'route_ids' list.
        """
        solutions = []

        for wh in candidates:
            if wh['inventory'] >= demand_kg:
                solutions.append({
                    'warehouses':      [wh],
                    'total_inventory': wh['inventory'],
                    'latest_arrival':  wh['arrival'],
                    'meets_deadline':  wh['meets_deadline'],
                    'min_distance':    wh['distance'],
                    'route_ids':       [wh['route_id']],
                })

        for wh1, wh2 in combinations(candidates, 2):
            total = wh1['inventory'] + wh2['inventory']
            if total >= demand_kg:
                latest = max(wh1['arrival'], wh2['arrival'])
                solutions.append({
                    'warehouses':      [wh1, wh2],
                    'total_inventory': total,
                    'latest_arrival':  latest,
                    'meets_deadline':  latest <= required_delivery,
                    'min_distance':    min(wh1['distance'], wh2['distance']),
                    'route_ids':       [wh1['route_id'], wh2['route_id']],
                })

        for wh1, wh2, wh3 in combinations(candidates, 3):
            total = wh1['inventory'] + wh2['inventory'] + wh3['inventory']
            if total >= demand_kg:
                latest = max(wh1['arrival'], wh2['arrival'], wh3['arrival'])
                solutions.append({
                    'warehouses':      [wh1, wh2, wh3],
                    'total_inventory': total,
                    'latest_arrival':  latest,
                    'meets_deadline':  latest <= required_delivery,
                    'min_distance':    min(wh1['distance'], wh2['distance'], wh3['distance']),
                    'route_ids':       [wh1['route_id'], wh2['route_id'], wh3['route_id']],
                })

        solutions.sort(key=lambda x: (not x['meets_deadline'],
                                      x['latest_arrival'],
                                      x['min_distance']))
        return solutions

    # ──────────────────────────────────────────────────────────────────────
    # Delivery analysis helpers
    # ──────────────────────────────────────────────────────────────────────

    def _format_time_readable(self, dt: datetime, reference_date: datetime = None) -> str:
        if reference_date is None:
            reference_date = datetime.now()
        if dt.date() == reference_date.date():
            return f"Today {dt.strftime('%H:%M')}"
        elif dt.date() == (reference_date + timedelta(days=1)).date():
            return f"Next day {dt.strftime('%H:%M')}"
        days_diff = (dt.date() - reference_date.date()).days
        return f"+{days_diff} days {dt.strftime('%H:%M')}"

    def _calculate_delivery_analysis(self, source_lat: float, source_lon: float,
                                     dest_lat: float, dest_lon: float,
                                     disruption_dt: datetime, required_delivery_dt: datetime,
                                     repair_or_delay_hours: float,
                                     mode: str = 'road') -> Dict:
        try:
            if mode == 'road':
                distance_km, travel_hours = self.google_service.get_road_distance(
                    source_lat, source_lon, dest_lat, dest_lon
                )
            else:
                distance_km  = haversine(source_lat, source_lon, dest_lat, dest_lon)
                travel_hours = distance_km / PLANE_SPEED

            repair_complete   = disruption_dt + timedelta(hours=repair_or_delay_hours)
            est_delivery      = repair_complete + timedelta(hours=travel_hours)
            time_delta_hours  = (est_delivery - required_delivery_dt).total_seconds() / 3600
            meets             = est_delivery <= required_delivery_dt

            return {
                'feasible':                True,
                'distance_km':             round(distance_km, 2),
                'travel_hours':            round(travel_hours, 2),
                'repair_hours':            round(repair_or_delay_hours, 2),
                'disruption_time':         disruption_dt.strftime('%H:%M'),
                'repair_completion_time':  repair_complete.strftime('%H:%M'),
                'estimated_delivery_time': self._format_time_readable(est_delivery, disruption_dt),
                'required_delivery_time':  required_delivery_dt.strftime('%H:%M'),
                'meets_requirement':       meets,
                'time_delta_hours':        round(time_delta_hours, 2),
            }
        except Exception as e:
            logger.warning(f"Could not calculate delivery analysis: {e}")
            return {'feasible': False, 'error': str(e), 'meets_requirement': False}

    def _extract_warehouse_details(self, warehouse_info: Dict) -> Dict:
        return {
            'warehouse_city':                warehouse_info.get('city', '').lower(),
            'warehouse_name':                warehouse_info.get('name', ''),
            'distance_from_destination_km':  round(warehouse_info.get('distance', 0), 2),
            'available_inventory':           warehouse_info.get('available_inventory',
                                                warehouse_info.get('inventory', 0)),
            'inventory':                     warehouse_info.get('inventory', 0),
            'reorder_level':                 warehouse_info.get('reorder_level', 0),
        }

    # ──────────────────────────────────────────────────────────────────────
    # Response formatter
    # ──────────────────────────────────────────────────────────────────────
    def _format_response(self,
                        disruption_type: str,
                        source: str,
                        destination: str,
                        demand_kg: int,
                        disruption_time: datetime,
                        required_delivery: datetime,
                        recommendation: str,
                        reason: str,
                        original_route: Dict,
                        repair_hours: int = None,
                        delay_minutes: int = None,
                        road_alternatives: Dict = None,
                        air_alternatives: Dict = None,
                        all_road_alternatives: List = None,
                        all_air_alternatives: List = None,
                        alternatives: List = None) -> Dict:

        src_coords  = self._get_coordinates(source,      'road' if disruption_type == 'road' else 'air')
        dest_coords = self._get_coordinates(destination, 'road' if disruption_type == 'road' else 'air')

        response: Dict[str, Any] = {
            'disruption_time':        disruption_time.strftime('%H:%M on %d-%m-%Y'),
            'required_delivery_time': required_delivery.strftime('%H:%M on %d-%m-%Y'),
            'demand_weight_kg':       demand_kg,
        }

        if disruption_type == 'road':
            response['repair_duration_hours'] = repair_hours
        else:
            response['delay_duration_minutes'] = delay_minutes
            response['delay_duration_hours']   = round((delay_minutes or 0) / 60, 2)

        # ── Original route analysis ───────────────────────────────────────
        if original_route and src_coords and dest_coords:
            duration = repair_hours if disruption_type == 'road' else ((delay_minutes or 0) / 60)
            analysis = self._calculate_delivery_analysis(
                src_coords[0], src_coords[1],
                dest_coords[0], dest_coords[1],
                disruption_time, required_delivery,
                duration, disruption_type
            )
            response['original_route'] = {
                'source':      source.lower(),
                'destination': destination.lower(),
                'analysis':    analysis,
            }
            response['original_feasible'] = (
                analysis.get('feasible', False) and analysis.get('meets_requirement', False)
            )
        else:
            response['original_feasible'] = False

        # ── Collect selected_route_ids ────────────────────────────────────
        raw_route_ids: List[int] = []

        if road_alternatives and 'route_ids' in road_alternatives:
            raw_route_ids.extend(road_alternatives['route_ids'])
        if air_alternatives and 'route_ids' in air_alternatives:
            raw_route_ids.extend(air_alternatives['route_ids'])

        seen: set = set()
        unique_route_ids: List[int] = []
        for rid in raw_route_ids:
            if rid not in seen:
                seen.add(rid)
                unique_route_ids.append(rid)

        response['route_ids'] = unique_route_ids

        # ── Recommendation ────────────────────────────────────────────────
        response['recommendation'] = recommendation
        response['reason']         = reason

        # ── Helper: format datetime values ───────────────────────────────
        def _fmt(dt_val) -> str:
            if isinstance(dt_val, datetime):
                return dt_val.strftime('%H:%M on %d-%m-%Y')
            s = str(dt_val).strip()
            if re.match(r'^\d{1,2}:\d{2}$', s):
                return f"{s} on {disruption_time.strftime('%d-%m-%Y')}"
            return s

        # ── Separate road vs air warehouses (by solution dict, NOT vehicle type) ──
        road_wh_list: List[Dict] = (
            road_alternatives['warehouses']
            if road_alternatives and 'warehouses' in road_alternatives
            else []
        )
        air_wh_list: List[Dict] = (
            air_alternatives['warehouses']
            if air_alternatives and 'warehouses' in air_alternatives
            else []
        )

        # ── Build human-readable message ──────────────────────────────────
        lines = [
            "⚠️ **Disruption detected**",
            f"- Route: {source} → {destination}",
        ]
        if disruption_type == 'road':
            lines.append(f"- Disruption at {_fmt(disruption_time)}, repair duration {repair_hours}h")
        else:
            lines.append(f"- Disruption at {_fmt(disruption_time)}, flight delay {delay_minutes} minutes")

        lines.append(f"- Demand: {demand_kg} kg")
        lines.append("")

        if road_wh_list or air_wh_list:
            if road_wh_list and air_wh_list:
                lines.append("🚚✈️ **Recommendation:** consider both road and air alternatives")
            elif road_wh_list:
                label = (
                    f"divert to multiple warehouses (combination of {len(road_wh_list)})"
                    if len(road_wh_list) > 1
                    else "divert to road alternative warehouse"
                )
                lines.append(f"🚚 **Recommendation:** {label}")
            else:
                label = (
                    f"divert to multiple warehouses (combination of {len(air_wh_list)})"
                    if len(air_wh_list) > 1
                    else "divert to air alternative warehouse"
                )
                lines.append(f"✈️ **Recommendation:** {label}")

            def _append_wh_section(wh_list: List[Dict], label: str):
                if not wh_list:
                    return
                lines.append(f"\n{label}:")
                remaining = demand_kg
                for wh in wh_list[:3]:
                    avail     = wh.get('available_inventory', wh.get('inventory', 0))
                    alloc     = min(remaining, avail)
                    remaining -= alloc
                    v         = wh.get('vehicle', {})
                    v_id      = v.get('vehicle_id') or v.get('id') or 'N/A'
                    dep       = _fmt(v.get('departure', datetime.now()))
                    arr       = _fmt(wh.get('arrival',  datetime.now()))
                    route_id  = wh.get('route_id', 'N/A')
                    lines.append(
                        f"  * {wh.get('name', wh.get('city', '')).capitalize()} "
                        f"({wh.get('city', '').lower()}) – {alloc}kg  [route_id={route_id}]"
                    )
                    lines.append(
                        f"    - Vehicle departs at {dep}, arrives at {arr}"
                    )

            _append_wh_section(
                road_wh_list,
                f"Road alternatives ({len(road_wh_list)} warehouse(s))"
                if len(road_wh_list) > 1 else "Road alternative"
            )
            _append_wh_section(
                air_wh_list,
                f"Air alternatives ({len(air_wh_list)} warehouse(s))"
                if len(air_wh_list) > 1 else "Air alternative"
            )

            if road_wh_list:
                latest = max(wh.get('arrival', datetime.now()) for wh in road_wh_list)
                lines.append(f"- Road estimated final delivery by {_fmt(latest)}")
            if air_wh_list:
                latest = max(wh.get('arrival', datetime.now()) for wh in air_wh_list)
                lines.append(f"- Air estimated final delivery by {_fmt(latest)}")

        else:
            lines.append(f"✅ **Recommendation:** {recommendation}")
            if response.get('original_feasible'):
                lines.append("- Original route meets deadline after repair/delay")

        lines.append("")
        if unique_route_ids:
            lines.append(f"📋 **Selected route IDs (warehouse → destination):** {unique_route_ids}")
        else:
            lines.append("📋 **Selected route IDs:** none (original route used or no alternatives found)")

        response['message'] = '\n'.join(lines)

        return response
    # def _format_response(self,
    #                      disruption_type: str,
    #                      source: str,
    #                      destination: str,
    #                      demand_kg: int,
    #                      disruption_time: datetime,
    #                      required_delivery: datetime,
    #                      recommendation: str,
    #                      reason: str,
    #                      original_route: Dict,
    #                      repair_hours: int = None,
    #                      delay_minutes: int = None,
    #                      road_alternatives: Dict = None,
    #                      air_alternatives: Dict = None,
    #                      all_road_alternatives: List = None,
    #                      all_air_alternatives: List = None,
    #                      alternatives: List = None) -> Dict:
    #     """
    #     Build the final response dict.

    #     Key additions over the original:
    #       • 'selected_route_ids'  – deduplicated list of route_id values from
    #                                 nodes_combined for every warehouse → destination
    #                                 leg that was chosen.
    #       • Each warehouse entry inside road_alternatives / air_alternatives
    #         already carries its individual 'route_id'.
    #     """

    #     src_coords  = self._get_coordinates(source,      'road' if disruption_type == 'road' else 'air')
    #     dest_coords = self._get_coordinates(destination, 'road' if disruption_type == 'road' else 'air')

    #     response: Dict[str, Any] = {
    #         'disruption_time':       disruption_time.strftime('%H:%M on %d-%m-%Y'),
    #         'required_delivery_time': required_delivery.strftime('%H:%M on %d-%m-%Y'),
    #         'demand_weight_kg':      demand_kg,
    #     }

    #     if disruption_type == 'road':
    #         response['repair_duration_hours'] = repair_hours
    #     else:
    #         response['delay_duration_minutes'] = delay_minutes
    #         response['delay_duration_hours']   = round((delay_minutes or 0) / 60, 2)

    #     # ── Original route analysis ───────────────────────────────────────
    #     if original_route and src_coords and dest_coords:
    #         duration = repair_hours if disruption_type == 'road' else ((delay_minutes or 0) / 60)
    #         analysis = self._calculate_delivery_analysis(
    #             src_coords[0], src_coords[1],
    #             dest_coords[0], dest_coords[1],
    #             disruption_time, required_delivery,
    #             duration, disruption_type
    #         )
    #         response['original_route'] = {
    #             'source':      source.lower(),
    #             'destination': destination.lower(),
    #             'analysis':    analysis,
    #         }
    #         response['original_feasible'] = (
    #             analysis.get('feasible', False) and analysis.get('meets_requirement', False)
    #         )
    #     else:
    #         response['original_feasible'] = False

    #     # ── Collect selected_route_ids ────────────────────────────────────
    #     raw_route_ids: List[int] = []

    #     if road_alternatives and 'route_ids' in road_alternatives:
    #         raw_route_ids.extend(road_alternatives['route_ids'])
    #     if air_alternatives and 'route_ids' in air_alternatives:
    #         raw_route_ids.extend(air_alternatives['route_ids'])

    #     # Deduplicate preserving order
    #     seen: set = set()
    #     unique_route_ids: List[int] = []
    #     for rid in raw_route_ids:
    #         if rid not in seen:
    #             seen.add(rid)
    #             unique_route_ids.append(rid)

    #     response['route_ids'] = unique_route_ids   # ← KEY OUTPUT

    #     # ── Recommendation ────────────────────────────────────────────────
    #     response['recommendation'] = recommendation
    #     response['reason']         = reason

    #     # ── Helper: format datetime values ────────────────────────────────
    #     def _fmt(dt_val) -> str:
    #         if isinstance(dt_val, datetime):
    #             return dt_val.strftime('%H:%M on %d-%m-%Y')
    #         s = str(dt_val).strip()
    #         if re.match(r'^\d{1,2}:\d{2}$', s):
    #             return f"{s} on {disruption_time.strftime('%d-%m-%Y')}"
    #         return s

    #     # ── Separate road vs air warehouses ──────────────────────────────
    #     road_wh_list: List[Dict] = []
    #     air_wh_list:  List[Dict] = []

    #     for solution, target_list_road, target_list_air in [
    #         (road_alternatives, road_wh_list, []),
    #         (air_alternatives,  [],           air_wh_list),
    #     ]:
    #         if not solution or 'warehouses' not in solution:
    #             continue
    #         for wh in solution['warehouses']:
    #             vtype = str(wh.get('vehicle', {}).get('type', '')).strip().lower()
    #             if vtype == 'plane':
    #                 air_wh_list.append(wh)
    #             else:
    #                 road_wh_list.append(wh)

    #     # ── Build human-readable message ──────────────────────────────────
    #     lines = [
    #         "⚠️ **Disruption detected**",
    #         f"- Route: {source} → {destination}",
    #     ]
    #     if disruption_type == 'road':
    #         lines.append(f"- Disruption at {_fmt(disruption_time)}, repair duration {repair_hours}h")
    #     else:
    #         lines.append(f"- Disruption at {_fmt(disruption_time)}, flight delay {delay_minutes} minutes")

    #     lines.append(f"- Demand: {demand_kg} kg")
    #     lines.append("")

    #     if road_wh_list or air_wh_list:
    #         if road_wh_list and air_wh_list:
    #             lines.append("🚚✈️ **Recommendation:** consider both road and air alternatives")
    #         elif road_wh_list:
    #             label = (f"divert to multiple warehouses (combination of {len(road_wh_list)})"
    #                      if len(road_wh_list) > 1 else "divert to road alternative warehouse")
    #             lines.append(f"🚚 **Recommendation:** {label}")
    #         else:
    #             lines.append("✈️ **Recommendation:** divert to air alternative warehouses")

    #         def _append_wh_section(wh_list: List[Dict], label: str):
    #             if not wh_list:
    #                 return
    #             lines.append(f"\n{label}:")
    #             remaining = demand_kg
    #             for wh in wh_list[:3]:
    #                 avail    = wh.get('available_inventory', wh.get('inventory', 0))
    #                 alloc    = min(remaining, avail)
    #                 remaining -= alloc
    #                 v        = wh.get('vehicle', {})
    #                 v_id     = v.get('vehicle_id') or v.get('id') or 'N/A'
    #                 dep      = _fmt(v.get('departure', datetime.now()))
    #                 arr      = _fmt(wh.get('arrival',  datetime.now()))
    #                 route_id = wh.get('route_id', 'N/A')
    #                 lines.append(
    #                     f"  * {wh.get('name', wh.get('city', '')).capitalize()} "
    #                     f"({wh.get('city', '').lower()}) – {alloc}kg  [route_id={route_id}]"
    #                 )
    #                 lines.append(
    #                     f"    - Vehicle {v_id} departs at {dep}, arrives at {arr}"
    #                 )

    #         _append_wh_section(
    #             road_wh_list,
    #             f"Road alternatives ({len(road_wh_list)} warehouse(s))"
    #             if len(road_wh_list) > 1 else "Road alternative"
    #         )
    #         _append_wh_section(
    #             air_wh_list,
    #             f"Air alternatives ({len(air_wh_list)} warehouse(s))"
    #             if len(air_wh_list) > 1 else "Air alternative"
    #         )

    #         if road_wh_list:
    #             latest = max(wh.get('arrival', datetime.now()) for wh in road_wh_list)
    #             lines.append(f"- Road estimated final delivery by {_fmt(latest)}")
    #         if air_wh_list:
    #             latest = max(wh.get('arrival', datetime.now()) for wh in air_wh_list)
    #             lines.append(f"- Air estimated final delivery by {_fmt(latest)}")
    #     else:
    #         lines.append(f"✅ **Recommendation:** {recommendation}")
    #         if response.get('original_feasible'):
    #             lines.append("- Original route meets deadline after repair/delay")

    #     # Append selected_route_ids summary
    #     lines.append("")
    #     if unique_route_ids:
    #         lines.append(f"📋 **Selected route IDs (warehouse → destination):** {unique_route_ids}")
    #     else:
    #         lines.append("📋 **Selected route IDs:** none (original route used or no alternatives found)")

    #     response['message'] = '\n'.join(lines)

    #     return response