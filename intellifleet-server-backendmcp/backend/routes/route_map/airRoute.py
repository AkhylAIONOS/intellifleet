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
    delete_nodes_by_route_air,
    delete_nodes_combined_by_user_and_route
)
from ...routes.route_map.googleRoute import calculate_route_with_google

router = APIRouter()

async def combined_route_function(payload: AirRouteRequest, user_id: int):

    logger.info(
        f"[MULTIMODAL ROUTE] User {user_id} requested multimodal route | "
        f"source={payload.source} | destination={payload.destination}"
    )

    try:
        # ============================
        # ✅ 1. CHECK DATABASE FIRST
        # ============================
        existing_route = get_multimodal_route_by_source_dest(
            user_id,
            payload.source,
            payload.destination,
            payload.objective
        )

        if existing_route:
            route_id = existing_route["route_id"]
            
            logger.info(
                f"[DB HIT] Multimodal route found in database | user_id={user_id} | route_id={route_id}"
            )
            
            # Parse the route data from database
            multimodal_data = existing_route["multimodal_data"]
            if isinstance(multimodal_data, str):
                multimodal_data = json.loads(multimodal_data)
            
            # Get full route details including segments
            full_route = get_multimodal_route_by_id(user_id, route_id)
            if full_route:
                logger.info(
                    f"[DB HIT] Returning multimodal route from database | "
                    f"user_id={user_id} | route_id={route_id}"
                )
                
                return {
                    "status": True,
                    "message": "Multimodal route served from database",
                    "data": multimodal_data,
                    "cached": True,
                    "route_id": route_id,
                    "source": existing_route["source"],
                    "destination": existing_route["destination"],
                    "objective": existing_route["objective"]
                }

        # ============================
        # ✅ 2. CACHE MISS → CALL GOOGLE
        # ============================
        logger.info(
            f"[NEW MULTIMODAL ROUTE] Not found in DB. Calling Google API | user_id={user_id}"
        )
        # ========================
        # AIRPORT LOOKUP
        # ========================
        src_airport = get_nearest_airport_by_city(payload.source, user_id)
        if not src_airport:
            return {"message": f"No airport mapped for {payload.source}"}
        
        dst_airport = get_nearest_airport_by_city(payload.destination, user_id)
        if not dst_airport:
            return {"message": f"No airport mapped for {payload.destination}"}
        
        src_airport_label = src_airport['airport_name']
        dst_airport_label = dst_airport['airport_name']

        vehicle = "truck"
        vehicle_type_details = VEHICLE_TYPES.get(vehicle.lower())

        # ========================
        # SEGMENT 1 (WAREHOUSE → SOURCE AIRPORT)
        # ========================
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
            return {"message": "No routes returned from Google (Segment 1)"}

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

        # ========================
        # SEGMENT 2 (AIR → AIR)
        # ========================
        air_distance_km = haversine_distance_km(
            src_airport["latitude"],
            src_airport["longitude"],
            dst_airport["latitude"],
            dst_airport["longitude"]
        )

        air_duration_hours = estimate_flight_duration(air_distance_km)

        # ========================
        # SEGMENT 2 – AIRPORT CHECK
        # ========================
        if (
            src_airport_label == dst_airport_label or
            (
                src_airport.get("latitude") == dst_airport.get("latitude") and
                src_airport.get("longitude") == dst_airport.get("longitude")
            )
        ):
            # Instead of returning → Execute CENTRALIZED GOOGLE ROUTE
            logger.info("[AIR CHECK] Airports are same. Falling back to centralized Google route.")

            waypoints = (
                [payload.source]
                + [payload.destination]
            )

            objective = payload.objective

            if len(waypoints) < 2:
                return {
                    "response_text": "At least source and destination are required.",
                    "actions": []
                }

            # Centralized Google Call
            google_centralized_result = await calculate_route_with_google(
                
                user_id,
                waypoints,
                objective
            )

            # print(f"==>> google_centralized_result:  {google_centralized_result}")

            # Explicit check for failure
            if (not google_centralized_result):
                logger.warning("[CENTRAL GOOGLE] Failed → no air alternative & no centralized route.")
                return {
                    "message": "No air route found and Google fallback also failed."
                }

            logger.info("[CENTRAL GOOGLE] Successfully served centralized multimodal route.")

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

        # ========================
        # SEGMENT 3 (DEST AIRPORT → DEST WAREHOUSE)
        # ========================
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
            return {"message": "No routes returned from Google (Segment 3)"}

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

        # ========================
        # TOTAL DISTANCE & DURATION
        # ========================
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

        # ========================
        # ✅ FINAL MULTIMODAL DATA
        # ========================
        multimodal_data = {
            "segment_1": segment_1,
            "segment_2": segment_2,
            "segment_3": segment_3,
            "source": payload.source,
            "destination": payload.destination,
            "total_distance_km": round(total_distance_km, 2),
            "total_duration": round(total_duration, 2),
            "objective": payload.objective
        }

        final_result = {
            "status": True,
            "message": "Multimodal Route Calculated.",
            "data": multimodal_data,
            "objective": payload.objective,
            "cached": False
        }

        # ============================
        # ✅ 3. SAVE TO DATABASE
        # ============================
        route_id = save_multimodal_route(
            user_id=user_id,
            multimodal_data=multimodal_data
        )

        logger.info(
            f"[DB SAVE] Multimodal route saved to database | user_id={user_id} | route_id={route_id}"
        )

        final_result["route_id"] = route_id

        return final_result

    except Exception as e:
        logger.critical(
            f"[MULTIMODAL ROUTE FAILED] user_id={user_id} | error={str(e)}"
        )
        return {"message": "No routes found."}



async def remove_multimodal_route_function(req, user_id):
    """Remove multimodal route from database"""

    try:

        if not req.route_id and not req.multimodal_data and not req.source:
            return {"message": "Provide route_id or multimodal_data or source/destination"}


        source = None
        destination = None

        # ✅ Case 1: From multimodal_data
        if req.multimodal_data:
            source = (
                req.multimodal_data.get("segment_1", {})
                .get("source")
            )
            destination = (
                req.multimodal_data.get("segment_3", {})
                .get("destination")
            )

        # ✅ Case 2: Direct source + destination
        if req.source and req.destination:
            source = req.source
            destination = req.destination

        route_id = req.route_id

        # ✅ Case 3: Resolve ID if not provided
        if not route_id:
            if not source or not destination:
                return {"message": "Provide route_id or multimodal_data or source/destination"}


            route_record = get_multimodal_route_by_source_dest(
                user_id,
                source,
                destination
            )

            if not route_record:
                return {"message": "Multimodal route not found using provided details"}


            route_id = route_record["route_id"]

        # ================================
        # ✅ DELETE FROM DATABASE
        # ================================
        delete_multimodal_route(user_id, route_id)
        delete_nodes_by_route_air(user_id, route_id)
        delete_nodes_combined_by_user_and_route(user_id, route_id)
        
        logger.info(f"Multimodal route {route_id} deleted from database")

        return {
            "message": "Multimodal route removed successfully",
            "route_id": route_id,
            "source": source,
            "destination": destination
        }

    except Exception as e:
        logger.error(f"Error deleting multimodal route {route_id} from database: {e}")
        return {"message": "Unable to delete route"}



async def generate_hub_to_capital_routes(user_id):
    """Generate multimodal routes from hub to all capital nodes"""
        
    try:

        hub, capitals = get_hub_and_capitals(user_id)

        if not hub:
            return {"success": False, "status_code": 500, "message": "Hub (UPS Worldport) not found"}
           

        if not capitals:
            return {"success": False, "status_code": 500, "message": "No capital nodes found"}
    
        routes = []
        failures = []

        for capital in capitals:
            try:
                payload = AirRouteRequest(
                    source=hub,
                    destination=capital
                )

                result = await combined_route_function(payload, user_id)

                if result.get("status"):
                    route_id = result.get("route_id")

                    routes.append({
                        "route_id": route_id,
                        "source": hub,
                        "destination": capital,
                        "route": result
                    })
                else:
                    failures.append({
                        "destination": capital,
                        "error": result.get("message", "Unknown error")
                    })

            except Exception as e:
                logger.error(f"Route failed {hub} → {capital}: {e}")
                failures.append({"destination": capital, "error": str(e)})
                return {"success": False, "status_code": 500, "message": "Unable to connect with Hub"}


        return {
            "status": True,
            "hub": hub,
            "routes": routes,
            "failures": failures
        }
    
    except Exception as e:
        logger.error(f"Error connecting Hub to Capitals: {e}")
        return {"success": False, "status_code": 500, "message": "Unable to connect Hub to capitals."}


# ======================================================= API ======================================================


# @router.post("/generate_hub_routes")
# async def generate_hub_routes(current_user = Depends(get_current_user)):
#     """Generate all routes from hub to capital nodes"""

#     user_id = current_user.get("user_id")
        
#     if not user_id:
#         return {"success": False, "status_code": 500, "message": "Invalid token: user_id not found"}
    
    
#     result = await generate_hub_to_capital_routes(user_id)
#     return result

# @router.post("/air_route")
# async def air_route(payload: AirRouteRequest, current_user = Depends(get_current_user)):
#     """Generate or retrieve multimodal air route"""

#     user_id = current_user.get("user_id")
        
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
    
#     result = await combined_route_function(payload, user_id)
#     return result

# @router.post("/remove_multimodal_route")
# async def removeMultimodal_route(payload: RemoveMultimodalRoute, current_user = Depends(get_current_user)):
#     """Remove a multimodal route"""
    
#     user_id = current_user.get("user_id")
        
#     if not user_id:
#         return {"success": False, "status_code": 500, "message": "Invalid token: user_id not found"}
    
    
#     result = await remove_multimodal_route_function(payload, user_id)
#     return result