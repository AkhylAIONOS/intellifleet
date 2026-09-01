import json
import asyncio
from pydantic import BaseModel
from typing import List, Optional
import json
from fastapi import APIRouter, HTTPException, Depends
from ...models.airRouteSchema import AirRouteRequest, RemoveMultimodalRoute
from ...utilities.routeUtils import fetch_warehouse_addresses, compute_route_for_user
from ...utilities.airportHelper import *
from ...config.logger import logger
from ...models.routeSchema import GoogleRouteRequest
from ..auth import get_current_user
from ...utilities.vehicleConstants import *
from ...database.database import (
    get_nearest_airport_by_city, 
    delete_multimodal_route, 
    get_multimodal_route_by_source_dest, 
    save_multimodal_route,
    get_multimodal_route_by_id,
    get_hub_and_capitals,
    combined_route_summary
)
from ...routes.route_map.googleRoute import calculate_route_with_google
from backend.database.database import air_route_summary

# ---------------------------------------
# Pydantic Model
# ---------------------------------------
class AirRouteRequest(BaseModel):
    source: str
    destination: str
    objective: Optional[str] = "duration"
    intermediate_locations: Optional[List[str]] = None


# ---------------------------------------
# Generate meta segments for intermediate routing
# ---------------------------------------
def generate_meta_segments(source: str, intermediate_locations: List[str], destination: str):

    locations = [source] + intermediate_locations + [destination]
    segments = []

    for i in range(len(locations) - 1):
        segments.append((locations[i], locations[i + 1]))

    return segments


# ---------------------------------------
# New combined_route_function handling intermediate logic
# ---------------------------------------
async def combined_route_function(payload: AirRouteRequest, user_id: int):

    # No intermediates → original logic
    if not payload.intermediate_locations:
        return await combined_route_core_logic(payload, user_id)

    logger.info(
        f"[INTERMEDIATE ROUTING] User={user_id} | Via={payload.intermediate_locations}"
    )

    # Create small segments
    segments = generate_meta_segments(
        payload.source,
        payload.intermediate_locations,
        payload.destination
    )

    logger.info(f"[INTERMEDIATE] Generated segments → {segments}")

    final_output = []

    for src, dst in segments:
        logger.info(f"[SUBROUTE START] {src} → {dst}")

        route_payload = AirRouteRequest(
            source=src,
            destination=dst,
            objective=payload.objective
        )

        sub_result = await combined_route_core_logic(route_payload, user_id)

        final_output.append({
            "route_id": sub_result.get("route_id"),
            "data": sub_result.get("data"),
            "source": src,
            "destination": dst,
            "total_distance_km": sub_result.get("total_distance_km"),
            "total_duration": sub_result.get("total_duration"),
            "total_cost": sub_result.get("total_cost"),
            "objective": sub_result.get("objective"),
            "cached": sub_result.get("cached", False)
        })

        logger.info(f"[SUBROUTE END] {src} → {dst}")


    return {
        "status": True,
        "message": "Intermediate multimodal route computed successfully",
        "routes": final_output
    }


# ---------------------------------------
# CORE MULTIMODAL ROUTE LOGIC (your original function)
# ---------------------------------------
async def combined_route_core_logic(payload: AirRouteRequest, user_id: int):

    logger.info(
        f"[MULTIMODAL ROUTE] User {user_id} requested multimodal route | "
        f"source={payload.source} | destination={payload.destination}"
    )

    try:
        # ============================================================
        # CHECK DATABASE FOR EXISTING ROUTE
        # ============================================================
        existing_route = get_multimodal_route_by_source_dest(
            user_id,
            payload.source,
            payload.destination,
            payload.objective
        )

        if existing_route:
            route_id = existing_route["route_id"]
            logger.info(f"[DB HIT] Multimodal route found | route_id={route_id}")

            multimodal_data = existing_route["multimodal_data"]
            if isinstance(multimodal_data, str):
                multimodal_data = json.loads(multimodal_data)

            full_route = get_multimodal_route_by_id(user_id, route_id)
            if full_route:
                return {
                    "status": True,
                    "message": "Multimodal route served from database",
                    "data": multimodal_data,
                    "cached": True,
                    "route_id": route_id,
                    "source": existing_route["source"],
                    "destination": existing_route["destination"],
                    "total_distance_km": multimodal_data.get("total_distance_km"),
                    "total_duration": multimodal_data.get("total_duration"),
                    "total_cost": multimodal_data.get("total_cost"),
                    "objective": existing_route["objective"]
                }

        # ============================================================
        # CACHE MISS → START NEW MULTIMODAL COMPUTATION
        # ============================================================
        logger.info(f"[NEW MULTIMODAL] Cache miss → calling Google APIs")

        # ---------------------------
        # Airport lookup
        # ---------------------------
        src_airport = get_nearest_airport_by_city(payload.source, user_id)
        if not src_airport:
            return {"message": f"No airport mapped for {payload.source}"}

        dst_airport = get_nearest_airport_by_city(payload.destination, user_id)
        if not dst_airport:
            return {"message": f"No airport mapped for {payload.destination}"}

        src_airport_label = src_airport["airport_name"]
        dst_airport_label = dst_airport["airport_name"]

        vehicle = "truck"
        vehicle_type_details = VEHICLE_TYPES.get(vehicle.lower())

        # ---------------------------
        # SEGMENT 1: Warehouse → Airport
        # ---------------------------
        src_address_list = fetch_warehouse_addresses(user_id, [payload.source])
        if not src_address_list:
            return {"message": "Source warehouse address not found"}

        src_address = src_address_list[0]

        segment1_payload = GoogleRouteRequest(
            source=src_address,
            destination=src_airport_label,
            objective=payload.objective
        )

        segment1 = await compute_route_for_user(segment1_payload, user_id)
        routes1 = segment1["data"]["best_route"]

        if not routes1:
            return {"message": "No Google result (Segment 1)"}

        segment_1 = routes1
        distance1 = segment_1.get("distance", 0)

        route_cost1 = 0
        if vehicle_type_details:
            fuel_needed = distance1 / vehicle_type_details["fuel_consumption"]
            route_cost1 = fuel_needed * vehicle_type_details["fuel_price"]

        segment_1.update({
            "source": payload.source,
            "destination": src_airport_label,
            "isOptimal": True,
            "route_cost": route_cost1,
            "objective": payload.objective,
            "transport_mode": "road"
        })

        # ---------------------------
        # SEGMENT 2: Air transport
        # ---------------------------
        air_distance_km = haversine_distance_km(
            src_airport["latitude"], src_airport["longitude"],
            dst_airport["latitude"], dst_airport["longitude"]
        )
        air_duration_hours = estimate_flight_duration(air_distance_km)

        if (
            src_airport_label == dst_airport_label or
            (
                src_airport.get("latitude") == dst_airport.get("latitude") and
                src_airport.get("longitude") == dst_airport.get("longitude")
            )
        ):
            logger.info("[AIR CHECK] Same airports → fallback to central Google")

            waypoints = [payload.source, payload.destination]
            google_centralized_result = await calculate_route_with_google(
                user_id, waypoints, payload.objective
            )

            if not google_centralized_result:
                return {"message": "No air route and no fallback route"}

            return google_centralized_result

        segment_2 = {
            "source_airport_name": src_airport_label,
            "destination_airport_name": dst_airport_label,
            "transport_mode": "air",
            "distance": air_distance_km,
            "duration": air_duration_hours,
            "source_airport": {
                "lat": src_airport["latitude"],
                "lng": src_airport["longitude"]
            },
            "destination_airport": {
                "lat": dst_airport["latitude"],
                "lng": dst_airport["longitude"]
            },
            "calculation_method": "haversine",
            "average_speed_kmph": CRUISE_SPEED_KMPH,
            "isOptimal": True
        }


                # ---------------------------
        # AIR COST CALCULATION  (ADDED)
        # ---------------------------
        plane_config = VEHICLE_TYPES.get("plane")  # ADDED

        if plane_config:
            air_fuel_needed = air_distance_km * plane_config["fuel_consumption"]   # ADDED
            air_cost = air_fuel_needed * plane_config["fuel_price"]                # ADDED
        else:
            air_cost = 0  # fallback (ADDED)

        segment_2.update({
            "air_cost": round(air_cost, 2)   # ADDED
        })

        # ---------------------------
        # SEGMENT 3: Destination Airport → Warehouse
        # ---------------------------
        dst_address_list = fetch_warehouse_addresses(user_id, [payload.destination])
        if not dst_address_list:
            return {"message": "Destination warehouse address not found"}

        dst_address = dst_address_list[0]

        segment3_payload = GoogleRouteRequest(
            source=dst_airport_label,
            destination=dst_address,
            objective=payload.objective
        )

        segment3 = await compute_route_for_user(segment3_payload, user_id)
        routes3 = segment3["data"]["best_route"]

        if not routes3:
            return {"message": "No Google result (Segment 3)"}

        segment_3 = routes3
        distance3 = segment_3.get("distance", 0)

        route_cost3 = 0
        if vehicle_type_details:
            fuel_needed = distance3 / vehicle_type_details["fuel_consumption"]
            route_cost3 = fuel_needed * vehicle_type_details["fuel_price"]

        segment_3.update({
            "source": dst_airport_label,
            "destination": payload.destination,
            "isOptimal": True,
            "route_cost": route_cost3,
            "objective": payload.objective,
            "transport_mode": "road"
        })

        # ---------------------------
        # TOTAL METRICS
        # ---------------------------
        total_distance_km = round(
            segment_1["distance"] +
            segment_2["distance"] +
            segment_3["distance"], 2
        )

        total_duration = round(
            segment_1["duration"] +
            segment_2["duration"] +
            segment_3["duration"], 2
        )

                # ---------------------------
        # TOTAL COST INCLUDING AIR (ADDED)
        # ---------------------------
        total_cost = round(
            segment_1.get("route_cost", 0) +
            air_cost +                               # ADDED
            segment_3.get("route_cost", 0), 2
        )

        multimodal_data = {
            "segment_1": segment_1,
            "segment_2": segment_2,
            "segment_3": segment_3,
            "source": payload.source,
            "destination": payload.destination,
            "total_distance_km": total_distance_km,
            "total_duration": total_duration,
            "objective": payload.objective,
            "total_cost": total_cost
        }

        final_result = {
            "status": True,
            "message": "Multimodal Route Calculated",
            "data": multimodal_data,
            "total_cost": total_cost,
            "objective": payload.objective,
            "cached": False
        }

        # ---------------------------
        # SAVE ROUTE IN DATABASE
        # ---------------------------
        route_id = save_multimodal_route(
            user_id=user_id,
            multimodal_data=multimodal_data
        )
        final_result["route_id"] = route_id

        air_route_summary(
            user_id=user_id,
            route_id=route_id,
            from_loc=payload.source,       # warehouse name e.g. "Delhi"
            to_loc=payload.destination,    # warehouse name e.g. "Mumbai"
            distance=total_distance_km,
            duration=total_duration,
            cost=total_cost,
            route_type="air"
        )
                
        combined_route_summary(
            user_id=user_id,
            route_id=route_id,
            from_loc=payload.source,       # warehouse name e.g. "Delhi"
            to_loc=payload.destination,    # warehouse name e.g. "Mumbai"
            distance=total_distance_km,
            duration=total_duration,
            cost=total_cost,
            route_type="air"
        )

        return final_result

    except Exception as e:
        logger.critical(
            f"[MULTIMODAL FAILED] user={user_id} | error={str(e)}"
        )
        return {"message": "No routes found."}




router = APIRouter()

# ------------------------------
# Test API Route
# ------------------------------
@router.post("/test-multimodal-route")
async def test_multimodal_route(payload: AirRouteRequest):

    # Hardcode user_id = 1 for testing
    user_id = 1

    try:
        result = await combined_route_function(payload, user_id)
        return {
            "status": True,
            **result
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating route: {str(e)}"
        )