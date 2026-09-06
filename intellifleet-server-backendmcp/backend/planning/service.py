from __future__ import annotations

import copy
import heapq
import itertools
import math
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import ExpansionRequest, PlanningRequest
from .database import load_scenario, migrate_planning_schema, save_scenario


MODE_RISK = {"road": 0.18, "air": 0.10, "multimodal": 0.14}
MODE_RELIABILITY = {"road": 0.88, "air": 0.94, "multimodal": 0.91}


def _norm(value: str) -> str:
    return value.strip().casefold()


class PlanningService:
    """Pure calculations plus thin SQLite data access; the LLM is never used here."""

    _scenarios: dict[str, dict[str, Any]] = {}

    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        if db_path != ":memory:":
            migrate_planning_schema(db_path)

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def load_network(self, user_id: int) -> dict[str, list[dict[str, Any]]]:
        with self._connect() as conn:
            routes = [dict(r) for r in conn.execute(
                """SELECT n.route_id, n.from_location, n.to_location, n.distance, n.duration, n.cost,
                          COALESCE(n.route_type, 'road') route_type,
                          COALESCE(rc.reliability,.9) reliability, COALESCE(rc.weather_risk,0) weather_risk,
                          COALESCE(rc.operational_risk,0) operational_risk, COALESCE(rc.toll_cost,0) toll_cost,
                          COALESCE(rc.handling_cost,0) handling_cost, COALESCE(rc.fuel_cost,0) fuel_cost,
                          COALESCE(rc.air_cost,0) air_cost, COALESCE(rc.base_transport_cost,n.cost) base_transport_cost,
                          rc.capacity_per_day_kg, rc.current_utilization_pct, rc.service_class, rc.express_eligible,
                          rc.sla_hours, rc.carbon_kg, COALESCE(rc.status,'active') status
                   FROM nodes n LEFT JOIN route_conditions rc ON rc.user_id=n.user_id AND rc.route_id=n.route_id
                   WHERE n.user_id=?
                   UNION ALL
                   SELECT n.route_id, n.from_location, n.to_location, n.distance, n.duration, n.cost,
                          COALESCE(n.route_type, 'air') route_type,
                          COALESCE(rc.reliability,.94), COALESCE(rc.weather_risk,0), COALESCE(rc.operational_risk,0),
                          COALESCE(rc.toll_cost,0), COALESCE(rc.handling_cost,0), COALESCE(rc.fuel_cost,0), COALESCE(rc.air_cost,0),
                          COALESCE(rc.base_transport_cost,n.cost), rc.capacity_per_day_kg, rc.current_utilization_pct,
                          rc.service_class, rc.express_eligible, rc.sla_hours, rc.carbon_kg, COALESCE(rc.status,'active')
                   FROM nodes_air n LEFT JOIN route_conditions rc ON rc.user_id=n.user_id AND rc.route_id=n.route_id
                   WHERE n.user_id=?""", (user_id, user_id)
            )]
            warehouses = [dict(r) for r in conn.execute(
                """SELECT w.warehouse_id, w.name, w.city, w.latitude, w.longitude, w.is_active,
                          COALESCE(i.inventory,0) inventory, COALESCE(i.reserved_inventory,0) reserved_inventory,
                          COALESCE(i.storage_capacity,0) storage_capacity, COALESCE(i.handling_cost,0) handling_cost,
                          COALESCE(i.fixed_operating_cost,0) fixed_operating_cost, COALESCE(i.reliability,.9) reliability,
                          COALESCE(i.disruption_risk,0) disruption_risk, i.nearest_airport_iata, i.airport_distance_km,
                          i.region, i.annual_demand_units, i.primary_sku, w.country, w.node_type
                   FROM warehouses w LEFT JOIN warehouse_inventory i
                     ON i.user_id=w.user_id AND i.warehouse_id=w.warehouse_id
                   WHERE w.user_id=?""", (user_id,)
            )]
            vehicles = [dict(r) for r in conn.execute(
                """SELECT id, warehouse_id, type, label, capacity, current_location,
                          is_available, status, is_active, vehicle_details, cost_per_km, reliability, compatible_modes,
                          cost_per_hour, fixed_dispatch_cost, avg_speed_kmph, breakdown_risk, available_from, available_until,
                          max_range_km, loading_time_min, unloading_time_min, co2_kg_per_km, express_eligible, refrigerated
                   FROM vehicles WHERE user_id=?""", (user_id,)
            )]
        coordinates={_norm(w["name"]):{"lat":w.get("latitude"),"lng":w.get("longitude")} for w in warehouses}
        for route in routes:
            route["source_coords"]=coordinates.get(_norm(route["from_location"]))
            route["destination_coords"]=coordinates.get(_norm(route["to_location"]))
        return {"routes": routes, "warehouses": warehouses, "vehicles": vehicles}

    @staticmethod
    def risk_breakdown(legs: list[dict], vehicle_utilization: float, vehicles: list[dict] | None = None,
                       warehouses: list[dict] | None = None, changes: dict | None = None) -> dict:
        if not legs:
            return {"route":1.0,"vehicle":1.0,"weather":0.0,"warehouse":0.0,"mode":1.0,"overall":1.0}
        distance = sum(float(x.get("distance") or 0) for x in legs)
        modes = {x.get("route_type", "road") for x in legs}
        mode = sum(MODE_RISK.get(m, .2) for m in modes)/len(modes)
        route = sum((1-float(x.get("reliability",.9)))+float(x.get("operational_risk",0)) for x in legs)/len(legs)
        route=min(1,route+min(distance/10000,.15)+float((changes or {}).get("risk_delta",0)))
        weather=min(1,sum(float(x.get("weather_risk",0)) for x in legs)/len(legs))
        vehicle_list=vehicles or []
        vehicle=min(1,(sum((1-float(v.get("reliability") or .9))+float(v.get("breakdown_risk") or 0) for v in vehicle_list)/len(vehicle_list) if vehicle_list else .25)+max(0,vehicle_utilization-.9)*.25)
        warehouse_list=warehouses or []
        warehouse=min(1,sum((1-float(w.get("reliability") or .9))+float(w.get("disruption_risk") or 0) for w in warehouse_list)/len(warehouse_list)) if warehouse_list else .1
        # Weighted, normalized deterministic formula: route 35%, vehicle 25%, weather 15%, warehouse 10%, mode 15%.
        overall=min(1,.35*route+.25*vehicle+.15*weather+.10*warehouse+.15*mode)
        return {k:round(v,4) for k,v in {"route":route,"vehicle":vehicle,"weather":weather,"warehouse":warehouse,"mode":mode,"overall":overall}.items()}

    @staticmethod
    def risk_score(legs: list[dict], vehicle_utilization: float, changes: dict | None = None) -> float:
        return PlanningService.risk_breakdown(legs,vehicle_utilization,changes=changes)["overall"]

    @staticmethod
    def select_vehicles(vehicles: list[dict], source: str, weight: float, mode: str,
                        required_range_km: float = 0, objective: str = "balanced", travel_hours: float = 0) -> tuple[list[dict], float]:
        import json
        accepted = {"air": {"plane", "aircraft"}, "road": {"truck", "car", "auto", "bike"}}
        now = datetime.now(timezone.utc).timestamp()
        valid = []
        for vehicle in vehicles:
            if (not vehicle.get("is_available") or not vehicle.get("is_active", 1)
                    or _norm(str(vehicle.get("current_location", ""))) != _norm(source)
                    or str(vehicle.get("type", "")).casefold() not in accepted.get(mode, accepted["road"])
                    or float(vehicle.get("capacity") or 0) <= 0):
                continue
            if vehicle.get("max_range_km") and float(vehicle["max_range_km"]) < required_range_km:
                continue
            compatible = vehicle.get("compatible_modes")
            if isinstance(compatible, str):
                try:
                    compatible = json.loads(compatible)
                except ValueError:
                    compatible = [x.strip() for x in compatible.split(",")]
            if compatible and mode not in compatible:
                continue
            speed = float(vehicle.get("avg_speed_kmph") or 0)
            hours = max(travel_hours, required_range_km/speed if speed else 0)
            hours += (float(vehicle.get("loading_time_min") or 0)+float(vehicle.get("unloading_time_min") or 0))/60
            availability = vehicle.get("available_from")
            until = vehicle.get("available_until")
            wait_hours = 0.0
            if availability and "T" not in availability and len(availability) <= 8:
                # Loaded HH:MM values describe recurring dispatch windows.
                local_now = datetime.now().astimezone()
                start_time = datetime.strptime(availability[:5], "%H:%M").time()
                start = local_now.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
                if until and len(until) <= 8:
                    end_time = datetime.strptime(until[:5], "%H:%M").time()
                    end = local_now.replace(hour=end_time.hour, minute=end_time.minute, second=0, microsecond=0)
                    if end < start:
                        if local_now > end and local_now < start:
                            wait_hours = (start-local_now).total_seconds()/3600
                    elif local_now < start:
                        wait_hours = (start-local_now).total_seconds()/3600
                    elif local_now > end:
                        wait_hours = (start+timedelta(days=1)-local_now).total_seconds()/3600
                elif local_now < start:
                    wait_hours = (start-local_now).total_seconds()/3600
            else:
                if availability:
                    wait_hours = max(0, (datetime.fromisoformat(availability).timestamp()-now)/3600)
                if until and datetime.fromisoformat(until).timestamp() < now+(hours+wait_hours)*3600:
                    continue
            valid.append({**vehicle, "_departure_wait_hours": wait_hours})
        if sum(float(v["capacity"]) for v in valid) < weight:
            return [], 0.0
        options = []
        # Typical source fleets are small; enumerate exact feasible subsets.
        if len(valid) <= 18:
            combinations = (combo for count in range(1,len(valid)+1) for combo in itertools.combinations(valid,count))
        else:
            combinations = (valid[:count] for count in range(1,len(valid)+1))
        for combo in combinations:
            capacity = sum(float(v["capacity"]) for v in combo)
            if capacity < weight:
                continue
            hours = max([travel_hours]+[required_range_km/float(v["avg_speed_kmph"]) for v in combo if v.get("avg_speed_kmph")])
            hours += max(float(v.get("_departure_wait_hours") or 0) for v in combo)
            hours += sum(float(v.get("loading_time_min") or 0)+float(v.get("unloading_time_min") or 0) for v in combo)/60
            cost = sum(float(v.get("fixed_dispatch_cost") or 0)+float(v.get("cost_per_km") or 0)*required_range_km+float(v.get("cost_per_hour") or 0)*hours for v in combo)
            risk = sum(1-float(v.get("reliability") or .9)+float(v.get("breakdown_risk") or 0) for v in combo)/len(combo)
            excess = (capacity-weight)/capacity
            key = {"cheapest":(cost,excess,risk),"fastest":(hours,cost,excess),"lowest-risk":(risk,cost,excess)}.get(objective,(excess+cost/1_000_000+risk,cost,len(combo)))
            options.append((key,combo,capacity))
        _,chosen,capacity=min(options,key=lambda row:row[0])
        return list(chosen), round(weight/capacity,4)

    @staticmethod
    def allocate_inventory(warehouses: list[dict], source: str, quantity: int) -> list[dict]:
        candidates = [w for w in warehouses if w.get("is_active", 1)]
        candidates.sort(key=lambda w: (0 if _norm(w["name"]) == _norm(source) else 1,
                                       -max(0, float(w.get("inventory", 0)) - float(w.get("reserved_inventory", 0)))))
        remaining, result = quantity, []
        for wh in candidates:
            available = max(0, int(wh.get("inventory", 0)) - int(wh.get("reserved_inventory", 0)))
            allocated = min(remaining, available)
            if allocated:
                result.append({"warehouse_id": wh["warehouse_id"], "warehouse": wh["name"],
                               "quantity": allocated, "available_before": available})
                remaining -= allocated
            if remaining == 0:
                break
        if remaining:
            return []
        return result

    @staticmethod
    def _shortest(routes: list[dict], source: str, destination: str, metric: str,
                  allowed: set[str], blocked: set[tuple[str, str]]) -> list[dict]:
        graph: dict[str, list[dict]] = {}
        names: dict[str, str] = {}
        for edge in routes:
            mode = str(edge.get("route_type") or "road").casefold()
            a, b = _norm(edge["from_location"]), _norm(edge["to_location"])
            if mode not in allowed or str(edge.get("status","active")).casefold() not in {"active","available","open"} or (a, b) in blocked or (b, a) in blocked:
                continue
            names[a], names[b] = edge["from_location"], edge["to_location"]
            graph.setdefault(a, []).append(edge)
        start, end = _norm(source), _norm(destination)
        queue, best = [(0.0, start, [])], {start: 0.0}
        while queue:
            score, node, path = heapq.heappop(queue)
            if node == end:
                return path
            if score > best.get(node, math.inf):
                continue
            for edge in graph.get(node, []):
                nxt = _norm(edge["to_location"])
                value = float(edge.get(metric) or 0)
                new_score = score + value
                if new_score < best.get(nxt, math.inf):
                    best[nxt] = new_score
                    heapq.heappush(queue, (new_score, nxt, path + [edge]))
        return []

    @staticmethod
    def _paths(routes, source, destination, allowed, blocked):
        graph = {}
        for edge in routes:
            a, b = _norm(edge["from_location"]), _norm(edge["to_location"])
            if (str(edge.get("route_type") or "road").casefold() in allowed
                    and str(edge.get("status", "active")).casefold() in {"active", "available", "open"}
                    and (a, b) not in blocked and (b, a) not in blocked):
                graph.setdefault(a, []).append(edge)
        found = []
        stack = [(_norm(source), [], {_norm(source)})]
        while stack and len(found) < 10000:
            node, path, visited = stack.pop()
            if node == _norm(destination):
                if path:
                    found.append(path)
                continue
            for edge in reversed(graph.get(node, [])):
                target = _norm(edge["to_location"])
                if target not in visited:
                    stack.append((target, path + [edge], visited | {target}))
        return found

    def _candidate(self, legs: list[dict], request: PlanningRequest, vehicles: list[dict],
                   changes: dict | None = None, warehouses: list[dict] | None = None) -> dict | None:
        if not legs:
            return None
        modes = {str(x.get("route_type") or "road").casefold() for x in legs}
        mode = next(iter(modes)) if len(modes) == 1 else "multimodal"
        if mode == "multimodal":
            segments = []
            for _, group in itertools.groupby(legs, key=lambda leg: str(leg.get("route_type") or "road").casefold()):
                segment = list(group)
                segment_request = request.model_copy(update={"source": segment[0]["from_location"], "destination": segment[-1]["to_location"]})
                calculated = self._candidate(segment, segment_request, vehicles, changes, warehouses)
                if calculated is None:
                    return None
                segments.append(calculated)
            plan = copy.deepcopy(segments[0])
            plan.update(plan_id=str(uuid.uuid4()), mode="multimodal", product="Express", route_legs=legs)
            plan["leg_assignments"] = [{"route_legs": segment["route_legs"], "vehicles": segment["vehicles"]} for segment in segments]
            plan["distance_km"] = round(sum(x["distance_km"] for x in segments), 2)
            plan["duration_hours"] = round(sum(x["duration_hours"] for x in segments) + .5*(len(segments)-1), 2)
            plan["eta"] = (datetime.now(timezone.utc)+timedelta(hours=plan["duration_hours"])).isoformat()
            plan["cost_breakdown"] = {key: round(sum(x["cost_breakdown"][key] for x in segments), 2) for key in plan["cost_breakdown"]}
            plan["cost_breakdown"]["handling_cost"] += request.handling_cost_per_stop*(len(segments)-1)
            plan["operational_cost"] = round(sum(plan["cost_breakdown"].values()), 2)
            plan["selling_price"] = plan["expected_revenue"] = round(plan["operational_cost"]/(1-request.target_margin), 2)
            plan["profit"] = round(plan["selling_price"]-plan["operational_cost"], 2)
            plan["risk_breakdown"] = {key: round(sum(x["risk_breakdown"][key] for x in segments)/len(segments), 4) for key in plan["risk_breakdown"]}
            plan["risk_score"] = plan["risk_breakdown"]["overall"]
            plan["reliability"] = round(math.prod(x["reliability"] for x in segments), 4)
            if request.deadline:
                slack = (request.deadline.timestamp()-datetime.fromisoformat(plan["eta"]).timestamp())/3600
                plan.update(sla_met=slack>=0, sla_slack_hours=round(max(0,slack),2), sla_delay_hours=round(max(0,-slack),2))
            return plan
        vehicle_mode = "air" if mode == "air" else "road"
        route_distance = sum(float(x.get("distance") or 0) for x in legs)
        selected, utilization = self.select_vehicles(vehicles, request.source,
                                                     request.shipment.weight_kg, vehicle_mode,
                                                     route_distance, request.objective, sum(float(x.get("duration") or 0) for x in legs))
        if not selected:
            return None
        # Existing routes already contain transport cost; deterministic modifiers cover shipment and scenario.
        base_cost = sum(float(x.get("base_transport_cost") if x.get("base_transport_cost") is not None else x.get("cost") or 0) for x in legs)
        weight_factor = max(1.0, request.shipment.weight_kg / 1000)
        fuel_multiplier = float((changes or {}).get("fuel_cost_multiplier", request.fuel_cost_multiplier))
        handling = max(0, len(legs) - 1) * request.handling_cost_per_stop
        fuel = sum(float(x.get("fuel_cost") or 0) for x in legs) * fuel_multiplier
        tolls = sum(float(x.get("toll_cost") or 0) for x in legs)
        air_cost = sum(float(x.get("air_cost") or 0) for x in legs)
        route_handling = sum(float(x.get("handling_cost") or 0) for x in legs)
        total_distance=sum(float(x.get("distance") or 0) for x in legs)
        travel_hours=sum(float(x.get("duration") or 0) for x in legs)
        travel_hours=max([travel_hours]+[total_distance/float(v["avg_speed_kmph"]) for v in selected if v.get("avg_speed_kmph")])
        distance_cost = sum(float(v.get("cost_per_km") or 0) for v in selected)*total_distance
        driver_time_cost=sum(float(v.get("cost_per_hour") or 0) for v in selected)*travel_hours
        fixed_dispatch=sum(float(v.get("fixed_dispatch_cost") or 0) for v in selected)
        transportation = base_cost * weight_factor
        if fuel_multiplier != 1 and fuel == 0:
            # Legacy route rows store fuel inside aggregate transport cost. Treat 30% as fuel.
            transportation *= 0.70 + 0.30 * fuel_multiplier
        cost_breakdown = {"base_transport":round(transportation,2),"distance_cost":round(distance_cost,2),
                          "fuel_cost":round(fuel,2),"toll_cost":round(tolls,2),"fixed_dispatch_cost":round(fixed_dispatch,2),
                          "driver_time_cost":round(driver_time_cost,2),"vehicle_cost":0.0,
                          "handling_cost":round(handling+route_handling,2),"air_cost":round(air_cost,2),"other_cost":0.0}
        operational_cost = round(sum(cost_breakdown.values()), 2)
        handling_hours=(sum(float(v.get("loading_time_min") or 0)+float(v.get("unloading_time_min") or 0) for v in selected)/60)
        transfer_hours=max(0,len(legs)-1)*.5+sum(.75 for x in legs if x.get("route_type")=="air")
        departure_wait_hours = max(float(v.get("_departure_wait_hours") or 0) for v in selected)
        duration_h = round(travel_hours+handling_hours+transfer_hours+departure_wait_hours, 2)
        risk_breakdown=self.risk_breakdown(legs,utilization,selected,warehouses=[w for w in warehouses or [] if any(_norm(w["name"]) in {_norm(leg["from_location"]), _norm(leg["to_location"])} for leg in legs)],changes=changes)
        risk = risk_breakdown["overall"]
        now = datetime.now(timezone.utc)
        eta = now.timestamp() + duration_h * 3600
        deadline = request.deadline
        slack = None if deadline is None else round((deadline.timestamp() - eta) / 3600, 2)
        sla_met = None if slack is None else slack >= 0
        selling = round(operational_cost / (1 - request.target_margin), 2)
        total_capacity=sum(float(x.get("capacity") or 0) for x in selected)
        assigned=[]; allocated=0.0
        for index,vehicle in enumerate(selected):
            load=(request.shipment.weight_kg-allocated if index==len(selected)-1
                  else request.shipment.weight_kg*float(vehicle.get("capacity") or 0)/total_capacity)
            load=round(load,6); allocated+=load
            capacity=float(vehicle.get("capacity") or 0)
            assigned.append({**{k:vehicle.get(k) for k in ("id","label","type","capacity")},
                             "assigned_load_kg":load,
                             "utilization_percentage":round(load/capacity*100,2) if capacity else 0})
        return {
            "plan_id": str(uuid.uuid4()), "mode": mode, "route_legs": legs,
            "distance_km": round(sum(float(x.get("distance") or 0) for x in legs), 2),
            "departure_wait_hours": round(departure_wait_hours,2), "duration_hours": duration_h, "eta": datetime.fromtimestamp(eta, timezone.utc).isoformat(),
            "operational_cost": operational_cost, "cost_breakdown": cost_breakdown, "selling_price": selling,
            "expected_revenue": selling, "profit": round(selling - operational_cost, 2),
            "margin_percentage": round(request.target_margin * 100, 2),
            "risk_score": risk,"risk_breakdown":risk_breakdown, "reliability": round(sum(float(x.get("reliability") or .9) for x in legs)/len(legs),4),
            "sla_met": sla_met, "deadline":deadline.isoformat() if deadline else None,"sla_slack_hours":max(0,slack) if slack is not None else None,"sla_delay_hours":max(0,-slack) if slack is not None else None,
            "vehicles": assigned,
            "vehicle_utilization": utilization, "product": "Express" if mode in {"air","multimodal"} else "Ground",
            "warnings": [] if selected else ["No currently available source vehicle covers the shipment load"],
        }

    @staticmethod
    def _rank(candidates: list[dict], request: PlanningRequest) -> list[dict]:
        if not candidates:
            return []
        max_cost = max(x["operational_cost"] for x in candidates) or 1
        max_time = max(x["duration_hours"] for x in candidates) or 1
        weights=request.scoring_weights; total=sum(weights.model_dump().values())
        for plan in candidates:
            cost, time, risk = plan["operational_cost"] / max_cost, plan["duration_hours"] / max_time, plan["risk_score"]
            components = {
                "normalized_cost": round(cost, 6),
                "normalized_time": round(time, 6),
                "normalized_risk": round(risk, 6),
                "reliability_penalty": round(1-plan["reliability"], 6),
                "sla_penalty": 1 if plan["sla_met"] is False else 0,
                "utilization_penalty": round(1-plan["vehicle_utilization"], 6),
            }
            weighted = {
                "cost": weights.cost*cost, "eta": weights.eta*time,
                "risk": weights.risk*risk,
                "reliability": weights.reliability*(1-plan["reliability"]),
                "sla": weights.sla*components["sla_penalty"],
                "utilization": weights.utilization*(1-plan["vehicle_utilization"]),
            }
            balanced=sum(weighted.values())/total
            plan["score_components"] = {**components,
                "weighted_contributions": {k: round(v/total, 6) for k, v in weighted.items()},
                "balanced_score": round(balanced, 4)}
            plan["score"] = round({"cheapest": cost, "fastest": time, "lowest-risk": risk}.get(request.objective,balanced)+(10 if request.sla_mandatory and plan["sla_met"] is False else 0),4)
        return sorted(candidates, key=lambda x: (x["sla_met"] is False, x["score"], x["operational_cost"]))

    def plan(self, user_id: int, request: PlanningRequest, network: dict | None = None,
             changes: dict | None = None) -> dict:
        network = copy.deepcopy(network or self.load_network(user_id))
        def resolve_location(value: str) -> str:
            wanted = _norm(value)
            exact = [w for w in network["warehouses"]
                     if wanted in {_norm(str(w.get("name", ""))), _norm(str(w.get("city", "")))}]
            if exact:
                return exact[0]["name"]
            contained = [w for w in network["warehouses"]
                         if wanted and (wanted in _norm(str(w.get("name", "")))
                                        or wanted in _norm(str(w.get("city", "")))
                                        or _norm(str(w.get("city", ""))) in wanted)]
            return contained[0]["name"] if len(contained) == 1 else value

        request = request.model_copy(update={
            "source": resolve_location(request.source),
            "destination": resolve_location(request.destination),
            "intermediate_stops": [resolve_location(x) for x in request.intermediate_stops],
        })
        changes = changes or {}
        blocked = {tuple(map(_norm, pair)) for pair in changes.get("blocked_routes", [])}
        unavailable_vehicles = {str(x) for x in changes.get("unavailable_vehicles", [])}
        unavailable_warehouses = {_norm(x) for x in changes.get("unavailable_warehouses", [])}
        network["vehicles"] = [v for v in network["vehicles"] if str(v.get("label")) not in unavailable_vehicles]
        network["warehouses"] = [w for w in network["warehouses"] if _norm(w["name"]) not in unavailable_warehouses]
        network["routes"] = [r for r in network["routes"]
                             if _norm(r["from_location"]) not in unavailable_warehouses
                             and _norm(r["to_location"]) not in unavailable_warehouses]
        candidates = []
        route_without_feasible_vehicle = None
        mode_sets = []
        if "road" in request.allowed_modes: mode_sets.append({"road"})
        if "air" in request.allowed_modes: mode_sets.append({"air"})
        if "multimodal" in request.allowed_modes: mode_sets.append({"road", "air"})
        # Enumerate actual simple network paths so an infeasible shortest path
        # cannot hide a feasible alternative. Bound work and disclose truncation.
        search_truncated = False
        for allowed in mode_sets:
            points = [request.source, *request.intermediate_stops, request.destination]
            segments = [self._paths(network["routes"], start, end, allowed, blocked)
                        for start, end in zip(points, points[1:])]
            search_truncated = search_truncated or any(len(paths) >= 10000 for paths in segments)
            if any(not paths for paths in segments):
                continue
            for index, parts in enumerate(itertools.product(*segments)):
                if index >= 10000:
                    search_truncated = True
                    break
                legs = [leg for part in parts for leg in part]
                candidate = self._candidate(legs, request, network["vehicles"], changes, network["warehouses"])
                if legs and candidate is None and route_without_feasible_vehicle is None:
                    route_without_feasible_vehicle = legs
                if candidate and not any(x["route_legs"] == candidate["route_legs"] for x in candidates):
                    candidates.append(candidate)
        allocation = self.allocate_inventory(network["warehouses"], request.source, request.shipment.quantity)
        for candidate in candidates:
            candidate["inventory_allocation"] = allocation
            if not allocation:
                candidate["warnings"].append("Insufficient active warehouse inventory")
        ranked = self._rank(candidates, request)
        if request.sla_mandatory:
            compliant=[x for x in ranked if x["sla_met"] is not False]
            ranked=compliant
        if request.max_risk is not None:
            feasible = [x for x in ranked if x["risk_score"] <= request.max_risk]
            ranked = feasible
        recommended = ranked[0] if ranked else None
        comparison = []
        if recommended:
            for other in ranked[1:]:
                cost_delta=round(other["operational_cost"]-recommended["operational_cost"],2); time_delta=round(other["duration_hours"]-recommended["duration_hours"],2); risk_delta=round(other["risk_score"]-recommended["risk_score"],4)
                comparison.append({"plan_id": other["plan_id"],"cost_difference":cost_delta,
                                   "cost_percentage_difference":round(cost_delta / recommended["operational_cost"] * 100, 2) if recommended["operational_cost"] else None,
                                   "money_saved":max(0,cost_delta),"money_lost":max(0,-cost_delta),
                                   "time_difference_hours":time_delta,"time_saved_hours":max(0,time_delta),"time_lost_hours":max(0,-time_delta),
                                   "risk_difference":risk_delta,"sla_difference":{"recommended":recommended["sla_met"],"alternative":other["sla_met"]},
                                   "utilization_difference":round(other["vehicle_utilization"]-recommended["vehicle_utilization"],4)})
            sla_reason = ("SLA was not evaluated because no delivery deadline was provided"
                          if recommended["sla_met"] is None else
                          f"SLA {'met' if recommended['sla_met'] else 'missed'}")
            reason = (f"Choose plan {recommended['plan_id']} ({recommended['mode']}): calculated cost ₹{recommended['operational_cost']:,.2f}, "
                      f"ETA {recommended['duration_hours']} hours, risk {recommended['risk_score']:.1%}; {sla_reason}.")
        else:
            reason = ("An alternative path exists, but no available compatible source-vehicle combination satisfies "
                      "the shipment capacity and full-route range requirements."
                      if route_without_feasible_vehicle else
                      "No feasible path exists in the current network and constraints.")
        if not recommended and candidates:
            reason = ("No SLA-feasible candidate exists for the requested deadline."
                      if request.sla_mandatory and not any(x["sla_met"] is not False for x in candidates)
                      else "No candidate satisfies the maximum permitted disruption risk.")
        feasibility = None
        if not recommended and route_without_feasible_vehicle:
            feasibility = {
                "constraint": "vehicle_capacity_or_full_route_range",
                "shipment_weight_kg": request.shipment.weight_kg,
                "alternative_route": [route_without_feasible_vehicle[0]["from_location"],
                                      *[leg["to_location"] for leg in route_without_feasible_vehicle]],
                "distance_km": round(sum(float(leg.get("distance") or 0) for leg in route_without_feasible_vehicle),2),
            }
        return {"planning_request": request.model_dump(mode="json"), "candidate_plans": ranked,
                "recommended_plan": recommended, "reason": reason, "comparison": comparison,
                "recommended_plan_id":recommended["plan_id"] if recommended else None,
                "explanation_inputs":{"recommended":recommended,"comparisons":comparison} if recommended else None,
                "warnings": (["Candidate search limit reached; global optimality is not established"] if search_truncated else []) + ([] if ranked else ["No feasible route found"]), "feasibility": feasibility}

    def consolidate(self, user_id: int, shipments: list[dict]) -> dict:
        network = self.load_network(user_id)
        groups = {}
        for shipment in shipments:
            groups.setdefault(_norm(shipment["source"]), []).append(shipment)
        results = []
        for group in groups.values():
            if len(group) < 2:
                continue
            departures=[datetime.fromisoformat(x["planned_departure"]) for x in group if x.get("planned_departure")]
            if departures and (max(departures)-min(departures)).total_seconds()>7200:
                continue
            individual=[]
            for shipment in group:
                request=PlanningRequest(source=shipment["source"],destination=shipment["destination"],
                    shipment={"weight_kg":shipment["weight_kg"]},objective="cheapest",allowed_modes=["road"],
                    deadline=shipment.get("deadline"),sla_mandatory=bool(shipment.get("deadline")))
                plan=self.plan(user_id,request,network)["recommended_plan"]
                if plan:individual.append(plan)
            if len(individual)!=len(group):
                continue
            destinations=list(dict.fromkeys(x["destination"] for x in group))
            if len(destinations)>7:
                continue
            deadlines=[datetime.fromisoformat(x["deadline"]) for x in group if x.get("deadline")]
            shared=[]
            for order in itertools.permutations(destinations):
                request=PlanningRequest(source=group[0]["source"],destination=order[-1],
                    shipment={"weight_kg":sum(float(x["weight_kg"]) for x in group)},objective="cheapest",allowed_modes=["road"],
                    intermediate_stops=list(order[:-1]),deadline=min(deadlines) if deadlines else None,sla_mandatory=bool(deadlines))
                plan=self.plan(user_id,request,network)["recommended_plan"]
                if plan:shared.append(plan)
            if not shared:
                continue
            consolidated=min(shared,key=lambda x:x["operational_cost"])
            before=sum(p["operational_cost"] for p in individual)
            savings=round(before-consolidated["operational_cost"],2)
            original_count=sum(len(p["vehicles"]) for p in individual)
            results.append({"shipment_ids":[x["shipment_id"] for x in group],"original_cost":round(before,2),
                "consolidated_cost":consolidated["operational_cost"],"savings":savings,
                "utilization_before":round(sum(p["vehicle_utilization"] for p in individual)/len(individual),4),
                "utilization_after":consolidated["vehicle_utilization"],"vehicle_utilization":consolidated["vehicle_utilization"],
                "vehicles_before":original_count,"vehicles_after":len(consolidated["vehicles"]),
                "vehicle_reduction":original_count-len(consolidated["vehicles"]),
                "eta_impact_hours":round(consolidated["duration_hours"]-max(p["duration_hours"] for p in individual),2),
                "sla_met":consolidated["sla_met"],"plan":consolidated,
                "recommended_action":"consolidate" if savings>0 else "retain separate shipments",
                "cost_basis":"Conservative full combined load carried on every leg; unloading-specific pricing is not modeled."})
        return {"consolidation_opportunities":results,
                "reason":"Evaluate compatible shared routes and retain separate trips when no saving is calculated."}

    def compare_modes(self,user_id:int,request:PlanningRequest,changes:dict | None=None)->dict:
        network=self.load_network(user_id); options={}
        for name,modes in {"ground":["road"],"express":["air"],"road":["road"],"air":["air"],"multimodal":["multimodal"]}.items():
            option_request=request.model_copy(update={"allowed_modes":modes})
            options[name]=self.plan(user_id,option_request,network,changes).get("recommended_plan")
        feasible=[x for x in options.values() if x]
        ranked=self._rank(feasible,request) if feasible else []
        ground,express=options["ground"],options["express"]
        delta=None
        if ground and express:
            delta={"additional_cost":round(express["operational_cost"]-ground["operational_cost"],2),
                   "time_saved_hours":round(ground["duration_hours"]-express["duration_hours"],2),
                   "risk_difference":round(express["risk_score"]-ground["risk_score"],4),
                   "sla_comparison":{"ground":ground["sla_met"],"express":express["sla_met"]}}
        return {"planning_request":request.model_dump(mode="json"),"options":options,
                "express_vs_ground":delta,"recommended_plan":ranked[0] if ranked else None,
                "recommended_plan_id":ranked[0]["plan_id"] if ranked else None,
                "reason":"Recommend the feasible mode with the lowest deterministic score for the requested objective."}

    def disruption_mitigation(self,user_id:int,request:PlanningRequest,changes:dict)->dict:
        scenario=self.create_scenario(user_id,request,changes)
        scenario["affected_resources"]={k:v for k,v in changes.items() if k in {
            "blocked_routes","unavailable_vehicles","unavailable_warehouses","risk_delta","allowed_modes"
        }}
        scenario["recovery_plan"]=scenario["scenario"].get("recommended_plan")
        scenario["alternatives"]=scenario["scenario"].get("candidate_plans",[])
        return scenario

    def warehouse_capacity(self, user_id: int, warehouse_names=None) -> dict:
        warehouses = self.load_network(user_id)["warehouses"]
        if warehouse_names:
            selected = []
            for name in warehouse_names:
                wanted = _norm(name)
                exact = [w for w in warehouses if wanted in {_norm(w["name"]), _norm(str(w.get("city") or ""))}]
                matches = exact or [w for w in warehouses if wanted in _norm(w["name"])]
                if len(matches) != 1:
                    return {"warehouses": [], "reason": "Warehouse name is unknown or ambiguous: " + name}
                if matches[0] not in selected:
                    selected.append(matches[0])
            warehouses = selected
        result = []
        for w in warehouses:
            capacity, inventory, reserved = float(w.get("storage_capacity") or 0), float(w.get("inventory") or 0), float(w.get("reserved_inventory") or 0)
            available = max(0, capacity - inventory) if capacity else 0
            result.append({"warehouse_id": w["warehouse_id"], "warehouse": w["name"], "storage_capacity": capacity,
                           "current_inventory": inventory, "reserved_inventory": reserved,"available_inventory":max(0,inventory-reserved), "available_storage": available,
                           "utilization_percentage": round(inventory / capacity * 100, 2) if capacity else None,
                           "additional_inventory": available})
        return {"warehouses": result}

    def fulfilment(self, user_id: int, destination: str, quantity: int, weight: float, objective: str,
                   deadline=None, excluded_warehouses=None, sku=None) -> dict:
        if quantity <= 0 or weight <= 0:
            raise ValueError("Demand quantity and weight must be positive")
        network = copy.deepcopy(self.load_network(user_id))
        wanted = _norm(destination)
        matches = [w["name"] for w in network["warehouses"] if wanted in {_norm(w["name"]), _norm(str(w.get("city") or ""))} or wanted in _norm(w["name"])]
        if len(matches) == 1:
            destination = matches[0]
        excluded = {_norm(x) for x in excluded_warehouses or []}
        warehouses = [w for w in network["warehouses"] if w.get("is_active", 1)
                      and _norm(w["name"]) not in excluded and _norm(str(w.get("city") or "")) not in excluded
                      and (sku is None or w.get("primary_sku") == sku)]
        # Exact integer allocation DP. Every option is independently planned at
        # its actual load; there is no proportional rescaling of dispatch cost.
        if quantity > 2000:
            return {"fulfilled": False, "allocation": [], "ranked_alternatives": [],
                    "unfulfilled_quantity": quantity, "total_cost": 0, "eta_hours": None,
                    "recommendation": "Exact allocation supports up to 2000 inventory units per request; provide coarser compatible units for larger demand."}
        states = {0: (0.0, [])}
        alternatives = []
        for wh in warehouses:
            available = min(quantity, max(0, int(wh.get("inventory") or 0)-int(wh.get("reserved_inventory") or 0)))
            options = []
            for amount in range(1, available + 1):
                if _norm(wh["name"]) == _norm(destination):
                    now = datetime.now(timezone.utc)
                    due = datetime.fromisoformat(deadline) if isinstance(deadline, str) else deadline
                    if due and due.timestamp() < now.timestamp():
                        continue
                    cost = round(float(wh.get("handling_cost") or 0)*amount, 2)
                    plan = {"plan_id": str(uuid.uuid4()), "mode": "local", "route_legs": [], "vehicles": [],
                            "distance_km": 0, "duration_hours": 0, "eta": now.isoformat(), "operational_cost": cost,
                            "risk_score": float(wh.get("disruption_risk") or 0), "reliability": float(wh.get("reliability") or 1),
                            "vehicle_utilization": 0, "sla_met": True if deadline else None, "deadline": str(deadline) if deadline else None,
                            "score": 0, "inventory_allocation": [], "cost_breakdown": {"handling": cost}, "warnings": []}
                else:
                    request = PlanningRequest(source=wh["name"], destination=destination,
                        shipment={"weight_kg": weight*amount/quantity, "quantity": amount}, objective=objective,
                        deadline=deadline, sla_mandatory=deadline is not None)
                    plan = self.plan(user_id, request, network)["recommended_plan"]
                if plan:
                    item = {"warehouse": wh["name"], "available": available, "allocation": amount,
                            "weight_kg": weight*amount/quantity, "plan": plan}
                    options.append(item)
            if options:
                alternatives.append(options[-1])
            next_states = dict(states)
            for allocated, (_, rows) in states.items():
                for item in options:
                    total = allocated + item["allocation"]
                    if total > quantity:
                        break
                    chosen = rows + [item]
                    cost = sum(x["plan"]["operational_cost"] for x in chosen)
                    eta = max(x["plan"]["duration_hours"] for x in chosen)
                    risk = sum(x["plan"]["risk_score"]*x["allocation"] for x in chosen)/total
                    score = {"cheapest": cost, "fastest": eta, "lowest-risk": risk}.get(objective, cost + eta*100 + risk*1000)
                    if total not in next_states or score < next_states[total][0]:
                        next_states[total] = (score, chosen)
            states = next_states
        fulfilled = quantity in states
        allocated = quantity if fulfilled else max(states)
        allocation = states[allocated][1]
        return {"fulfilled": fulfilled, "unfulfilled_quantity": quantity-allocated, "allocation": allocation,
                "ranked_alternatives": alternatives, "total_cost": round(sum(x["plan"]["operational_cost"] for x in allocation), 2),
                "eta_hours": max((x["plan"]["duration_hours"] for x in allocation), default=None),
                "source_count": len(allocation),
                "risk_score": sum(x["plan"]["risk_score"]*x["allocation"] for x in allocation)/allocated if allocated else None,
                "recommendation": "Use the calculated inventory allocation." if fulfilled else "Insufficient active, SKU-compatible inventory with feasible routes, vehicles, and deadline."}

    def auto_fulfilment(self,user_id:int,destination:str|None=None)->dict:
        network=self.load_network(user_id); groups={}
        for warehouse in network["warehouses"]:
            sku=warehouse.get("primary_sku")
            if not sku:continue
            available=max(0,int(warehouse.get("inventory",0))-int(warehouse.get("reserved_inventory",0)))
            if available:groups.setdefault(str(sku),[]).append((warehouse,available))
        cases=[]
        for sku,rows in groups.items():
            maximum=max(amount for _,amount in rows); total=sum(amount for _,amount in rows)
            if len(rows)>1 and total>maximum:cases.append((sku,maximum+1,total,rows))
        if not cases:return {"inventory_case":None,"fulfilled":False,"allocation":[],"ranked_alternatives":[]}
        sku,quantity,total,rows=sorted(cases,key=lambda item:(item[0],item[1]))[0]
        target=destination or rows[0][0]["name"]
        result=self.fulfilment(user_id,target,quantity,float(quantity),"balanced")
        result["inventory_case"]={"sku":sku,"required_quantity":quantity,"network_available":total}
        return result

    def breakdown_recovery(self,user_id:int,vehicle_label:str,current_location:str,destination:str,weight:float,deadline=None,plan_id=None,shipment_id=None)->dict:
        if not current_location:
            return {"recovery_plan":None,"reason":"Additional breakdown location is required.","missing_fields":["current_location"]}
        if isinstance(deadline,str):
            deadline=datetime.fromisoformat(deadline.replace("Z","+00:00"))
        network=copy.deepcopy(self.load_network(user_id))
        broken=next((v for v in network["vehicles"] if str(v.get("label"))==vehicle_label),None)
        if broken is None:
            return {"recovery_plan":None,"reason":"Failed vehicle is not present in the loaded network.","replacement_vehicles":[]}
        for value, field in ((current_location,"current_location"),(destination,"destination")):
            matches=[w["name"] for w in network["warehouses"] if _norm(value) in {_norm(w["name"]),_norm(str(w.get("city") or ""))}]
            if len(matches)==1:
                if field=="current_location":current_location=matches[0]
                else:destination=matches[0]
        request=PlanningRequest(source=current_location,destination=destination,shipment={"weight_kg":weight,"quantity":1},deadline=deadline)
        candidates=[]
        available=[v for v in network["vehicles"] if v.get("label")!=vehicle_label and v.get("is_available") and v.get("is_active",1)]
        groups={}
        for v in available:
            mode="air" if str(v.get("type")).casefold() in {"plane","aircraft"} else "road"
            groups.setdefault((v.get("current_location"),mode),[]).append(v)
        for (location,mode),vehicles in groups.items():
            approaches=[[]] if _norm(str(location))==_norm(current_location) else self._paths(network["routes"],str(location),current_location,{mode},set())
            for approach in approaches:
                approach_distance=sum(float(x.get("distance") or 0) for x in approach)
                moved=[]
                for v in vehicles:
                    if v.get("max_range_km") and float(v["max_range_km"])<=approach_distance:
                        continue
                    moved.append({**v,"current_location":current_location,
                                  "max_range_km":float(v["max_range_km"])-approach_distance if v.get("max_range_km") else None})
                recovery=self.plan(user_id,request.model_copy(update={"allowed_modes":[mode]}),{**network,"vehicles":moved})
                plan=recovery.get("recommended_plan")
                if not plan:
                    continue
                labels={v["label"] for v in plan["vehicles"]}
                selected=[v for v in vehicles if v["label"] in labels]
                approach_plan=self._candidate(approach,request.model_copy(update={"source":str(location),"destination":current_location,"shipment":request.shipment.model_copy(update={"weight_kg":1})}),selected) if approach else None
                if approach and approach_plan is None:
                    continue
                cost=approach_plan["operational_cost"] if approach_plan else 0
                hours=approach_plan["duration_hours"] if approach_plan else 0
                plan["replacement_approach_legs"]=approach
                plan["replacement_arrival_hours"]=hours
                plan["repositioning_cost"]=cost
                plan["transfer_time_hours"]=max((float(v.get("loading_time_min") or 0)/60 for v in selected),default=0)
                plan["duration_hours"]=round(plan["duration_hours"]+hours+plan["transfer_time_hours"],2)
                plan["cost_breakdown"]["other_cost"]+=cost
                plan["operational_cost"]=round(sum(plan["cost_breakdown"].values()),2)
                plan["selling_price"]=plan["expected_revenue"]=round(plan["operational_cost"]/(1-request.target_margin),2)
                plan["profit"]=round(plan["selling_price"]-plan["operational_cost"],2)
                plan["eta"]=(datetime.now(timezone.utc)+timedelta(hours=plan["duration_hours"])).isoformat()
                if deadline:
                    slack=(deadline.timestamp()-datetime.fromisoformat(plan["eta"]).timestamp())/3600
                    plan.update(sla_met=slack>=0,sla_slack_hours=round(max(0,slack),2),sla_delay_hours=round(max(0,-slack),2))
                candidates.append(plan)
        ranked=self._rank(candidates,request)
        plan=ranked[0] if ranked else None
        return {"plan_id":plan_id,"shipment_id":shipment_id,"broken_vehicle":broken,
                "remaining_journey":{"source":current_location,"destination":destination},"replacement_vehicles":plan["vehicles"] if plan else [],
                "transfer_load_kg":weight,"recovery_plan":plan,"candidate_plans":ranked,
                "additional_cost":plan["operational_cost"] if plan else None,
                "additional_cost_basis":"Gross replacement transport and repositioning spend; original sunk charges and refunds are not supplied.",
                "new_eta":plan["eta"] if plan else None,"sla_met":plan["sla_met"] if plan else None,
                "reason":"Use the ranked feasible replacement plan." if plan else "No remaining compatible vehicle combination can reach the recovery location and complete the route within its capacity and range."}

    def future_replan(self,user_id:int,vehicle_label:str,delay_hours:float)->dict:
        import json
        if delay_hours <= 0:
            raise ValueError("Delay must be positive")
        with self._connect() as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM shipments WHERE user_id=? ORDER BY scheduled_start", (user_id,))]
        def labels(row):
            try:
                value = json.loads(row.get("assigned_vehicle_ids") or "[]")
                return value if isinstance(value, list) else []
            except (ValueError, TypeError):
                return []
        def stamp(value):
            return datetime.fromisoformat(value).timestamp() if value else None
        reservations = {}
        affected_rows = [row for row in rows if vehicle_label in labels(row)]
        for row in rows:
            if row in affected_rows:
                continue
            start, end = stamp(row.get("scheduled_start")), stamp(row.get("scheduled_end"))
            if start is not None and end is not None:
                for label in labels(row):
                    reservations.setdefault(label, []).append((start, end))
        network = self.load_network(user_id)
        affected = []
        delayed_available = None
        for row in affected_rows:
            start, end = stamp(row.get("scheduled_start")), stamp(row.get("scheduled_end"))
            if start is None or end is None:
                affected.append({"shipment_id": row["shipment_id"], "before_assignment": vehicle_label,
                    "after_assignment": vehicle_label, "action": "needs_schedule", "cascading_delay_hours": None, "sla_met": None})
                continue
            duration = end-start
            new_start = max(start+delay_hours*3600, delayed_available or 0)
            replacement = None
            alternatives = []
            for vehicle in network["vehicles"]:
                label = vehicle.get("label")
                if label == vehicle_label or not vehicle.get("is_available") or not vehicle.get("is_active", 1):
                    continue
                if any(start < booked_end and end > booked_start for booked_start, booked_end in reservations.get(label, [])):
                    continue
                if not row.get("source") or not row.get("destination") or not row.get("weight_kg"):
                    continue
                trial_network = {**network, "vehicles": [vehicle]}
                request = PlanningRequest(source=row["source"], destination=row["destination"], shipment={"weight_kg":row["weight_kg"]}, objective="cheapest")
                plan = self.plan(user_id, request, trial_network)["recommended_plan"]
                if plan and plan["duration_hours"]*3600 <= duration:
                    alternatives.append((plan["operational_cost"], vehicle))
            if alternatives:
                _, replacement = min(alternatives, key=lambda x:x[0])
                new_start = start
            new_end = new_start+duration
            label = replacement["label"] if replacement else vehicle_label
            reservations.setdefault(label, []).append((new_start, new_end))
            if not replacement:
                delayed_available = new_end
            delay = round((new_start-start)/3600, 2)
            deadline = stamp(row.get("deadline"))
            affected.append({"shipment_id":row["shipment_id"], "before_assignment":vehicle_label, "after_assignment":label,
                "action":"reassigned" if replacement else "rescheduled", "original_start":row.get("scheduled_start"), "original_end":row.get("scheduled_end"),
                "new_start":datetime.fromtimestamp(new_start,timezone.utc).isoformat(), "new_end":datetime.fromtimestamp(new_end,timezone.utc).isoformat(),
                "cascading_delay_hours":delay, "delay_reduction_hours":round(delay_hours-delay,2),
                "cost_impact":None, "cost_impact_reason":"Original booked shipment cost is not stored in the schedule.",
                "sla_met":None if deadline is None else new_end<=deadline})
        return {"delayed_vehicle":vehicle_label,"affected_shipments":affected,"cascading_delays":len(affected),
                "live_data_changed":False,"limitations":["Warehouse and route time-slot capacities are not present in the shipment schedule."]}

    def schedule_shipment(self,user_id:int,data:dict)->dict:
        import json
        with self._connect() as conn:
            conn.execute("""INSERT OR REPLACE INTO shipments(shipment_id,user_id,source,destination,weight_kg,quantity,sku,deadline,status,
                assigned_vehicle_ids,route_id,scheduled_start,scheduled_end,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (data["shipment_id"],user_id,data["source"],data["destination"],data["weight_kg"],data["quantity"],data.get("sku"),
                 str(data.get("deadline")) if data.get("deadline") else None,"planned",json.dumps(data.get("assigned_vehicle_labels",[])),
                 data.get("route_id"),str(data["scheduled_start"]),str(data["scheduled_end"]),datetime.now(timezone.utc).isoformat()))
        return {"shipment_id":data["shipment_id"],"status":"planned"}

    def optimize_stops(self,user_id:int,source:str,destination:str,stops:list[str],shipment:dict,objective:str)->dict:
        network=self.load_network(user_id)
        def resolve(value):
            wanted=_norm(value); matches=[w["name"] for w in network["warehouses"] if wanted==_norm(w["name"]) or wanted==_norm(str(w.get("city") or "")) or wanted in _norm(w["name"])]
            return matches[0] if len(matches)==1 else value
        source,destination=resolve(source),resolve(destination); stops=[resolve(x) for x in stops]
        if len(stops) > 7:
            return {"recommended_plan": None, "candidate_plans": [], "reason": "Exact stop ordering supports at most seven stops per request.", "optimized_stop_sequence": []}
        original_request=PlanningRequest(source=source,destination=destination,shipment=shipment,objective=objective,intermediate_stops=stops)
        original=self.plan(user_id,original_request,network).get("recommended_plan")
        possibilities = []
        for sequence in itertools.permutations(stops):
            request = original_request.model_copy(update={"intermediate_stops": list(sequence)})
            outcome = self.plan(user_id, request, network)
            if outcome.get("recommended_plan"):
                possibilities.append((sequence, outcome))
        if not possibilities:
            return {"recommended_plan": None, "candidate_plans": [], "reason": "No feasible journey visits every required stop using connected network legs and available vehicles.",
                    "original_stop_sequence": stops, "optimized_stop_sequence": [], "unserved_stops": stops}
        metric = {"fastest": "duration_hours", "lowest-risk": "risk_score"}.get(objective, "operational_cost")
        order, result = min(possibilities, key=lambda row: row[1]["recommended_plan"][metric])
        order = list(order)
        optimized = result["recommended_plan"]
        result["original_stop_sequence"]=stops; result["optimized_stop_sequence"]=order
        result["optimization_comparison"]={"original_distance":original["distance_km"] if original else None,
            "optimized_distance":optimized["distance_km"] if optimized else None,"original_cost":original["operational_cost"] if original else None,
            "optimized_cost":optimized["operational_cost"] if optimized else None,
            "savings":round(original["operational_cost"]-optimized["operational_cost"],2) if original and optimized else None,
            "eta_hours":optimized["duration_hours"] if optimized else None}
        return result

    @staticmethod
    def transport_scope(source_country:str,destination_country:str)->dict:
        international=_norm(source_country)!=_norm(destination_country)
        return {"scope":"international" if international else "domestic",
                "recommended_modes":["air","multimodal"] if international else ["road","multimodal"],
                "gateway_required":international}

    def global_plan(self,user_id:int,request:PlanningRequest)->dict:
        network=self.load_network(user_id)
        def warehouse(value):
            wanted=_norm(value); matches=[w for w in network["warehouses"] if wanted in {_norm(w["name"]),_norm(str(w.get("city") or ""))} or wanted in _norm(w["name"])]
            return matches[0] if len(matches)==1 else None
        source_wh,dest_wh=warehouse(request.source),warehouse(request.destination)
        source_country=request.source_country or (source_wh or {}).get("country")
        destination_country=request.destination_country or (dest_wh or {}).get("country")
        if not source_country or not destination_country:
            return {"scope":"international","recommended_plan":None,"candidate_plans":[],"warnings":["Source or destination country is unavailable in the loaded warehouse data"]}
        request=request.model_copy(update={"source":source_wh["name"] if source_wh else request.source,"destination":dest_wh["name"] if dest_wh else request.destination,
                                   "source_country":source_country,"destination_country":destination_country})
        if _norm(source_country)==_norm(destination_country):
            result=self.plan(user_id,request)
            result["scope"]="domestic"; result["gateway_sequence"]=[]
            return result
        if not source_wh or not dest_wh or not source_wh.get("nearest_airport_iata") or not dest_wh.get("nearest_airport_iata"):
            return {"scope":"international","recommended_plan":None,"candidate_plans":[],
                    "warnings":["International planning requires source and destination gateway airport data"]}
        gateways=[source_wh["nearest_airport_iata"],dest_wh["nearest_airport_iata"]]
        global_request=request.model_copy(update={"intermediate_stops":[],"allowed_modes":["air","multimodal"]})
        result=self.plan(user_id,global_request,network); result["scope"]="international"; result["gateway_sequence"]=[request.source,*gateways,request.destination]
        plan=result.get("recommended_plan") or {}
        actual_modes={str(leg.get("route_type") or "").casefold() for leg in plan.get("route_legs") or []}
        if request.allowed_modes==["multimodal"] and actual_modes=={"air"}:
            result["requested_multimodal_feasible"]=False
            result["warnings"]=["The loaded network supports a direct international air leg, but has no separate origin road-to-airport and destination airport-to-facility route legs for the requested gateway chain"]
        return result

    def create_scenario(self, user_id: int, request: PlanningRequest, changes: dict, baseline: dict | None = None) -> dict:
        supported = {"demand_quantity", "demand_weight_kg", "deadline", "allowed_modes", "cost_multiplier",
                     "inventory_changes", "fuel_cost_multiplier", "blocked_routes", "unavailable_vehicles", "unavailable_warehouses", "risk_delta"}
        unknown = set(changes)-supported
        if unknown:
            raise ValueError("Unsupported scenario changes: " + ", ".join(sorted(unknown)))
        network = copy.deepcopy(self.load_network(user_id))
        baseline = copy.deepcopy(baseline) if baseline else self.plan(user_id, request, network)
        scenario_request=request.model_copy(deep=True)
        if "demand_quantity" in changes: scenario_request.shipment.quantity=int(changes["demand_quantity"])
        if "demand_weight_kg" in changes: scenario_request.shipment.weight_kg=float(changes["demand_weight_kg"])
        if "deadline" in changes: scenario_request.deadline=datetime.fromisoformat(changes["deadline"])
        if "allowed_modes" in changes: scenario_request.allowed_modes=changes["allowed_modes"]
        if "cost_multiplier" in changes:
            for route in network["routes"]:
                route["cost"]=float(route.get("cost") or 0)*float(changes["cost_multiplier"])
                if route.get("base_transport_cost") is not None:
                    route["base_transport_cost"]*=float(changes["cost_multiplier"])
        for update in changes.get("inventory_changes",[]):
            for wh in network["warehouses"]:
                if _norm(wh["name"])==_norm(update["warehouse"]): wh["inventory"]=update["inventory"]
        scenario_request = PlanningRequest.model_validate(scenario_request.model_dump())
        scenario = self.plan(user_id, scenario_request, network, changes)
        base_plan,scenario_plan=baseline.get("recommended_plan"),scenario.get("recommended_plan")
        comparison=None
        if base_plan and scenario_plan:
            comparison={"cost_difference":round(scenario_plan["operational_cost"]-base_plan["operational_cost"],2),
                        "eta_difference_hours":round(scenario_plan["duration_hours"]-base_plan["duration_hours"],2),
                        "risk_difference":round(scenario_plan["risk_score"]-base_plan["risk_score"],4),
                        "sla":{"baseline":base_plan["sla_met"],"scenario":scenario_plan["sla_met"]},
                        "vehicle_utilization":{"baseline":base_plan["vehicle_utilization"],"scenario":scenario_plan["vehicle_utilization"]},
                        "routes":{"baseline":base_plan["route_legs"],"scenario":scenario_plan["route_legs"]},
                        "modes":{"baseline":base_plan["mode"],"scenario":scenario_plan["mode"]},
                        "vehicles":{"baseline":base_plan["vehicles"],"scenario":scenario_plan["vehicles"]},
                        "inventory_allocation":{"baseline":base_plan.get("inventory_allocation"),"scenario":scenario_plan.get("inventory_allocation")}}
        scenario_id = str(uuid.uuid4())
        record = {"scenario_id": scenario_id, "status": "draft", "changes": changes,
                  "baseline": baseline, "scenario": scenario,"comparison":comparison, "created_at": datetime.now(timezone.utc).isoformat(),"applied_at":None}
        self._scenarios[scenario_id] = {"user_id": user_id, **record}
        if self.db_path != ":memory:":
            save_scenario(self.db_path, user_id, record)
        return record

    def scenario_action(self, user_id: int, scenario_id: str, action: str) -> dict:
        item = self._scenarios.get(scenario_id) or (load_scenario(self.db_path, user_id, scenario_id) if self.db_path != ":memory:" else None)
        if not item or item["user_id"] != user_id:
            raise KeyError("Scenario not found")
        if action not in {"apply", "discard", "draft"}:
            raise ValueError("Scenario action must be apply, discard, or draft")
        if item["status"] != "draft":
            raise ValueError("Scenario is no longer a draft")
        if action == "draft":
            return {key: copy.deepcopy(value) for key, value in item.items() if key != "user_id"}
        if action == "apply" and not (item.get("scenario") or {}).get("recommended_plan"):
            raise ValueError("Cannot apply an infeasible scenario; retain the baseline or revise the constraints")
        if action == "discard":
            item["status"] = "discarded"
            if self.db_path != ":memory:":
                with self._connect() as conn: conn.execute("UPDATE planning_scenarios SET status='discarded',updated_at=? WHERE scenario_id=?", (datetime.now(timezone.utc).isoformat(),scenario_id))
            return {"scenario_id": scenario_id, "status": "discarded", "live_data_changed": False}
        # Live resources are changed only here, after the explicit apply action.
        if self.db_path != ":memory:":
            with self._connect() as conn:
                changes=item.get("changes",{})
                for label in changes.get("unavailable_vehicles",[]):
                    conn.execute("UPDATE vehicles SET is_available=0,status='unavailable' WHERE user_id=? AND label=?",(user_id,label))
                for name in changes.get("unavailable_warehouses",[]):
                    conn.execute("UPDATE warehouses SET is_active=0 WHERE user_id=? AND lower(name)=lower(?)",(user_id,name))
                for update in changes.get("inventory_changes",[]):
                    conn.execute("UPDATE warehouse_inventory SET inventory=? WHERE user_id=? AND warehouse_name=?",(update["inventory"],user_id,update["warehouse"]))
                for pair in changes.get("blocked_routes",[]):
                    ids=[r[0] for r in conn.execute("SELECT route_id FROM nodes WHERE user_id=? AND lower(from_location)=lower(?) AND lower(to_location)=lower(?) UNION SELECT route_id FROM nodes_air WHERE user_id=? AND lower(from_location)=lower(?) AND lower(to_location)=lower(?)",(user_id,pair[0],pair[1],user_id,pair[0],pair[1]))]
                    for route_id in ids:
                        conn.execute("INSERT INTO route_conditions(user_id,route_id,operational_risk,reliability,status) VALUES(?,?,1,0,'closed') ON CONFLICT(user_id,route_id) DO UPDATE SET operational_risk=1,reliability=0,status='closed'",(user_id,route_id))
                applied_at=datetime.now(timezone.utc).isoformat()
                conn.execute("UPDATE planning_scenarios SET status='applied',updated_at=?,applied_at=? WHERE scenario_id=?", (applied_at,applied_at,scenario_id))
                plan = item["scenario"]["recommended_plan"]
                conn.execute("INSERT INTO planning_plans(plan_id,user_id,scenario_id,status,plan_json,created_at) VALUES(?,?,?,?,?,?)",
                             (plan["plan_id"],user_id,scenario_id,"approved",__import__('json').dumps(plan),datetime.now(timezone.utc).isoformat()))
        item["status"] = "applied"
        return {"scenario_id": scenario_id, "status": "applied", "live_data_changed": self.db_path != ":memory:",
                "approved_plan": item["scenario"]["recommended_plan"],
                "planning_request": item["scenario"].get("planning_request"), "applied_changes": item.get("changes", {})}

    def get_scenario(self,user_id:int,scenario_id:str)->dict:
        item=self._scenarios.get(scenario_id) or (load_scenario(self.db_path,user_id,scenario_id) if self.db_path != ":memory:" else None)
        if not item or item.get("user_id") != user_id:raise KeyError("Scenario not found")
        return {key:value for key,value in item.items() if key!="user_id"}

    def expansion_from_network(self,user_id:int)->dict:
        network=self.load_network(user_id)
        candidates=[{"name":w["name"],"latitude":w["latitude"],"longitude":w["longitude"],
                     "capacity":w.get("storage_capacity") or 5000,"facility_cost":w.get("fixed_operating_cost") or 0,
                     "warehouse_cost":w.get("handling_cost") or 0,"connectivity_score":w.get("reliability") or .9}
                    for w in network["warehouses"] if str(w.get("node_type")).casefold()=="retaildemand"]
        demands=[{"name":w["name"],"latitude":w["latitude"],"longitude":w["longitude"],"demand":w.get("annual_demand_units") or 0}
                 for w in network["warehouses"] if float(w.get("annual_demand_units") or 0)>0]
        if not candidates or not demands:return {"recommended_hubs":[],"candidates":[],"reason":"Loaded network data has no candidate demand nodes or demand values for expansion analysis."}
        from backend.planning.models import ExpansionRequest
        result=self.expansion(ExpansionRequest(candidate_hubs=candidates,demand_locations=demands,hubs_to_open=1,facility_cost=0))
        result["basis"]="Loaded RetailDemand nodes and annual demand values"
        return result

    @staticmethod
    def expansion(request: ExpansionRequest) -> dict:
        # Geodesic separation is a siting estimate, never a fabricated route.
        def separation(a, b):
            lat1, lat2 = math.radians(float(a["latitude"])), math.radians(float(b["latitude"]))
            dlat = lat2-lat1
            dlon = math.radians(float(b["longitude"])-float(a["longitude"]))
            term = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
            return 6371*2*math.asin(min(1, math.sqrt(term)))
        if request.hubs_to_open > len(request.candidate_hubs):
            return {"recommended_hubs": [], "candidates": [], "reason": "Fewer candidate hubs are supplied than requested facilities."}
        candidates = []
        for hub in request.candidate_hubs:
            weighted = sum(separation(hub, demand)*float(demand.get("demand", 1)) for demand in request.demand_locations)
            rate = hub.get("cost_per_km")
            facility = hub.get("facility_cost", request.facility_cost)
            transport = round(weighted*float(rate), 2) if rate is not None else None
            warehouse = hub.get("warehouse_cost")
            known = sum(float(x) for x in (transport, facility, warehouse) if x is not None)
            missing = [key for key, value in (("transport rate", rate), ("facility cost", facility), ("warehouse cost", warehouse)) if value is None]
            candidates.append({"hub": hub["name"], "transport_cost": transport, "network_servicing_cost": transport,
                "facility_operating_cost": facility, "warehouse_cost": warehouse,
                "incremental_cost": round(known, 2) if not missing else None, "known_cost_subtotal": round(known, 2),
                "missing_assumptions": missing, "capacity": hub.get("capacity"),
                "weighted_distance_km": round(weighted, 2), "cost_basis": "User-provided rates applied to geodesic siting estimates; actual network routes require validation."})
        candidates.sort(key=lambda row: (row["incremental_cost"] is None, row["incremental_cost"] if row["incremental_cost"] is not None else row["weighted_distance_km"]))
        chosen = candidates[:request.hubs_to_open]
        hubs = {hub["name"]: hub for hub in request.candidate_hubs}
        capacity = {row["hub"]: float(row["capacity"]) if row["capacity"] is not None else math.inf for row in chosen}
        assignments = []
        unserved = []
        for i, demand in enumerate(request.demand_locations):
            remaining = float(demand.get("demand", 1))
            for row in sorted(chosen, key=lambda row: separation(hubs[row["hub"]], demand)):
                amount = min(remaining, capacity[row["hub"]])
                if amount > 0:
                    assignments.append({"demand": demand.get("name", str(i)), "hub": row["hub"], "allocated_demand": amount,
                                        "geodesic_distance_km": round(separation(hubs[row["hub"]], demand), 2)})
                    remaining -= amount
                    capacity[row["hub"]] -= amount
                if remaining <= 0:
                    break
            if remaining > 0:
                unserved.append({"demand": demand.get("name", str(i)), "quantity": remaining})
        return {"recommended_hubs": chosen if not unserved else [], "candidates": candidates, "assignments": assignments,
                "unserved_demand": unserved, "status": "draft", "live_data_changed": False,
                "new_connections_required": [{"hub": x["hub"], "demand": x["demand"], "route_validated": False} for x in assignments],
                "reason": ("Candidate siting estimate using supplied coordinates, demand and capacities. Missing cost assumptions remain unknown; confirm actual connections before execution. "
                           "Multiple-hub assignment is a capacity-constrained heuristic, not a claim of global geographic optimality.") if not unserved else "Candidate facility capacity is insufficient for the supplied demand."}
