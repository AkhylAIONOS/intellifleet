import json 
from ...models.routeSchema import *
from fastapi import APIRouter, Depends, HTTPException
from backend.config.logger import logger
from backend.utilities.vehicleConstants import *
from ..auth import get_current_user
from backend.utilities.routeUtils import compute_route_for_user, fetch_warehouse_addresses
from backend.database.database import (
    deactivate_route, 
    get_persistent_route_by_locations, 
    save_persistent_route, 
    get_persistent_route_by_id, 
    get_warehouse_by_name, 
    get_persistent_route_by_waypoints, 
    delete_persistent_route,
    delete_nodes_by_route,
    combined_route_summary,
    delete_nodes_combined_by_user_and_route,
    delete_persistent_route_by_user_and_route

)
from fastapi.responses import JSONResponse
from backend.database.database import road_route_summary

router = APIRouter()


# # ----------------------------------------------------------
# # Generates meta segments exactly like air routing version
# # ----------------------------------------------------------
# def generate_meta_segments(source: str, intermediate_locations: List[str], destination: str):
#     locations = [source] + intermediate_locations + [destination]
#     segments = []

#     for i in range(len(locations) - 1):
#         segments.append((locations[i], locations[i + 1]))

#     return segments


# # =====================================================================
# # MAIN ROAD ROUTING WRAPPER: Same behavior as AIR INTERMEDIATE HANDLING
# # =====================================================================
# async def calculate_route_with_google_function(user_id: int, waypoints: List[str], objective="duration"):

#     # No intermediates → use existing logic
#     if len(waypoints) <= 2:
#         return await calculate_route_with_google(user_id, waypoints, objective)

#     source = waypoints[0]
#     destination = waypoints[-1]
#     intermediate = waypoints[1:-1]

#     logger.info(f"[INTERMEDIATE-ROAD] User={user_id} | Via={intermediate}")

#     # Build meta segments
#     segments = generate_meta_segments(source, intermediate, destination)
#     logger.info(f"[INTERMEDIATE-ROAD] Segments generated → {segments}")

#     final_output = []

#     for src, dst in segments:
#         logger.info(f"[SUBROUTE START] {src} → {dst}")

#         sub_waypoints = [src, dst]

#         sub_result = await calculate_route_with_google(
#             user_id=user_id,
#             waypoints=sub_waypoints,
#             objective=objective
#         )

#         final_output.append({
#             "route_id": sub_result.get("route_id"),
#             "data": sub_result,
#             "source": src,
#             "destination": dst,
#             "distance": sub_result.get("distance"),
#             "duration": sub_result.get("duration"),
#             "cost": sub_result.get("route_cost"),
#             "objective": objective,
#             "cached": sub_result.get("cached", False)
#         })

#         logger.info(f"[SUBROUTE END] {src} → {dst}")

#     return {
#         "status": True,
#         "message": "Intermediate road route computed successfully",
#         "routes": final_output
#     }

    
async def calculate_route_with_google(user_id: int, waypoints: List[str], objective: str = "duration"):
    """
    Calculate route using Google API with database caching
    """
    logger.info(f"[ROUTE] User {user_id} requested route for waypoints: {waypoints}")

    try:
    
        # Checking DB by waypoints
        existing_route = get_persistent_route_by_locations(
            user_id,
            waypoints[0],
            waypoints[-1],
            waypoints[1:-1], 
            objective
        )

        if existing_route:
            route_id = existing_route["route_id"]
            route_data = existing_route["route_data"]

            if isinstance(route_data, str):
                route_data = json.loads(route_data)

            logger.info(
                f"[DB HIT] Returning route from database | user_id={user_id} | route_id={route_id}"
            )

            # ---- SAFETY NORMALIZATION ----
            optimal_routes = route_data.get("optimal_routes") or []

            if isinstance(optimal_routes, str):
                optimal_routes = json.loads(optimal_routes)

            if optimal_routes:
                optimal_routes[0]["isOptimal"] = True

            # Parse waypoints
            db_waypoints = existing_route.get("waypoints")
            if isinstance(db_waypoints, str):
                db_waypoints = json.loads(db_waypoints)

            return {
                "route_id": route_id,
                "source": route_data.get("source"),
                "destination": route_data.get("destination"),
                "intermediate_locations": route_data.get("intermediate_locations", []),
                "optimal_routes": optimal_routes,
                "locations": db_waypoints or waypoints,
                "distance": route_data.get("distance"),
                "duration": route_data.get("duration"),
                "route_cost": route_data.get("route_cost"),
                "source_coords": route_data.get("source_coords"),
                "dest_coords": route_data.get("dest_coords"),
                "objective": route_data.get("objective"),
                "cached": True
            }

        logger.info(
            f"[NEW ROUTE] Route not found in DB. Calling Google API | user_id={user_id}"
        )

        addresses = fetch_warehouse_addresses(user_id, waypoints)

        source = addresses[0]
        destination = addresses[-1]
        intermediate_locations = addresses[1:-1] if len(addresses) > 2 else []

        google_payload = GoogleRouteRequest(
            source=source,
            destination=destination,
            intermediate_locations=intermediate_locations,
            objective=objective
        )

        result = await compute_route_for_user(google_payload, user_id)

        # if not result.get("status"):
        #     logger.error(
        #         f"[GOOGLE ERROR] Google routing failed | user_id={user_id} | payload={google_payload}"
        #     )
        #     return {"message": "No routes available"}


        routes = result["data"]["best_route"]
        # print(f"==>> routes:  {routes}")

        if not routes or len(routes) == 0:
            logger.error(
                f"[GOOGLE ERROR] No routes returned | user_id={user_id} | payload={google_payload}"
            )
            return {"message": "No routes available"}


        optimal_route = routes
        # print(f"==>> optimal_route:  {optimal_route}")
        
        src = get_warehouse_by_name(user_id, waypoints[0])
        dst = get_warehouse_by_name(user_id, waypoints[-1])

        distance = optimal_route.get("distance")
        duration = optimal_route.get("duration")
        
        vehicle = "truck"
        vehicle_type_details = VEHICLE_TYPES.get(vehicle.lower())

        if vehicle_type_details:
            fuel_needed = distance / vehicle_type_details["fuel_consumption"]
            route_cost = fuel_needed * vehicle_type_details["fuel_price"]
        else:
            route_cost = 0

        optimal_route["isOptimal"] = True

        final_result = {
            "source": waypoints[0],
            "destination": waypoints[-1],
            "intermediate_locations": waypoints[1:-1],
            "distance": distance,
            "duration": duration,
            "route_cost": route_cost,
            "source_coords": {"lat": src["latitude"], "lng": src["longitude"]},
            "dest_coords": {"lat": dst["latitude"], "lng": dst["longitude"]},
            "optimal_routes": [optimal_route],
            "locations": waypoints,
            "cached": False,
            "objective": objective
        }

        route_id = save_persistent_route(
            user_id=user_id,
            route_data=final_result
        )

        logger.info(
            f"[DB SAVE] Route successfully saved to database | user_id={user_id} | route_id={route_id}"
        )

        final_result["route_id"] = route_id

        road_route_summary(
            user_id=user_id,
            route_id=route_id,
            from_loc=final_result["source"],
            to_loc=final_result["destination"],
            distance=distance,
            duration=duration,
            cost=route_cost,
            route_type="road"
        )

        combined_route_summary(
            user_id=user_id,
            route_id=route_id,
            from_loc=final_result["source"],
            to_loc=final_result["destination"],
            distance=distance,
            duration=duration,
            cost=route_cost,
            route_type="road"
        )

        logger.info(
            f"[SUMMARY SAVE] Summary route saved | route_id={route_id}"
        )

        return final_result
    
    except Exception as e:
        logger.error(f"Error creating route: {e}")
        return {"message": "Unable to create route"}



async def get_alternative_function(req: AlternativeRouteRequest, user_id):
    """Get alternative route for an existing route"""

    try:

        # FETCHING ORIGINAL ROUTE FROM DATABASE
        original_route = get_persistent_route_by_id(user_id, req.route_id)
        
        if not original_route:
            return {"message": "Original route not found"}
            

        # Parse route data
        route_data = original_route.get("route_data")
        if isinstance(route_data, str):
            route_data = json.loads(route_data)

        # RESOLVING WAYPOINTS
        source = req.source or original_route.get("source")
        destination = req.destination or original_route.get("destination")
        
        # Get intermediate locations
        intermediate_raw = original_route.get("intermediate_locations")
        if intermediate_raw:
            if isinstance(intermediate_raw, str):
                intermediate = json.loads(intermediate_raw)
            else:
                intermediate = intermediate_raw
        else:
            intermediate = []
        
        # Use requested intermediate locations if provided
        if req.intermediate_locations:
            intermediate = req.intermediate_locations

        if not source or not destination:
            return {"message": "Source or destination missing"}
           

        waypoints = [source]
        if intermediate:
            waypoints.extend(intermediate)
        waypoints.append(destination)

        if len(waypoints) < 2:
            return {"message": "Invalid or missing waypoints"}
           

        addresses = fetch_warehouse_addresses(user_id, waypoints)

        google_payload = GoogleRouteRequest(
            source=addresses[0],
            destination=addresses[-1],
            intermediate_locations=addresses[1:-1]
        )

        result = await compute_route_for_user(google_payload, user_id)

        # print(f"==>> len(routes):  {len(routes)}")

        # if not result.get("status"):
        #     return {"message": "No route available"}

        routes = result["data"].get("routes", [])

        if len(routes) < 2:
            return {"message": "No alternative routes available"}
            

        alt_index = 1 if len(routes) > 1 else None

        if len(routes) > 2:
            alt_index = 2  

        print(f"==>> alt_index:  {alt_index}")
        
        alternative = routes[alt_index]

        raw_distance = alternative.get("distance")
        if isinstance(raw_distance, str):
            distance = float(raw_distance.replace("km", "").strip())
        else:
            distance = float(raw_distance or 0)

        vehicle = "truck"
        vehicle_type_details = VEHICLE_TYPES.get(vehicle.lower())

        if vehicle_type_details:
            fuel_needed = distance / vehicle_type_details["fuel_consumption"]
            route_cost = fuel_needed * vehicle_type_details["fuel_price"]
        else:
            fuel_needed = 0
            route_cost = 0

        alternative["fuel_needed"] = fuel_needed
        alternative["route_cost"] = route_cost
        distance = alternative.get("distance")
        duration = alternative.get("duration")

        data = {
            "message": "Alternative route calculated",
            "parent_route_id": req.route_id,
            "source": source,
            "destination": destination,
            "intermediate_locations": intermediate,
            "distance": distance,
            "duration": duration,
            "alternative_route": alternative,
            "reason": req.reason,
            "waypoints": waypoints,
            "is_alternative": True,
            "fuel_needed": fuel_needed,
            "route_cost": route_cost
        }

        alt_route_id = save_persistent_route(
            user_id=user_id,
            route_data=data,
            parent_route_id=req.route_id
        )

        data["route_id"] = alt_route_id

        logger.info(
            f"[DB] Alternative route saved | alt_route_id={alt_route_id} | parent_route_id={req.route_id}"
        )

        # Deactivate original route
        deactivate_route(req.route_id, user_id)
        logger.info(f"[DB] Parent route deactivated | parent_route_id={req.route_id}")

        alternative["isOptimal"] = False
    
        return data

    except Exception as e:
        logger.error(f"Error creating alternative route: {e}")
        return {"message": "Unable to create alternative route"}



# async def remove_route_function(req, user_id):
#     """Remove route from database"""

#     try:
#         if not req.route_id and not req.route_data and not req.source:
#             return {"message": "Provide route_id to remove the route."}
            

#         waypoints = None

#         if req.route_data:
#             waypoints = (
#                 req.route_data.get("waypoints") or
#                 req.route_data.get("locations") or
#                 None
#             )

#         if req.source:
#             waypoints = [req.source] + (req.intermediate_locations or []) + [req.destination]

#         route_id = req.route_id

#         if not route_id:
#             if not waypoints or len(waypoints) < 2:
#                 return {"message": "Waypoints required to identify route"}
                

#             route_record = get_persistent_route_by_waypoints(user_id, waypoints)

#             if not route_record:
#                 return {"message": "Route not found using provided details"}
               

#             route_id = route_record["route_id"]

#         # Deleting from persistent DB
#         delete_persistent_route(user_id, route_id)
#         delete_nodes_by_route(user_id, route_id)
#         delete_nodes_combined_by_user_and_route(user_id, route_id)
        
#         logger.info(f"Route {route_id} deleted from database")

#         return {
#             "message": "Route removed successfully",
#             "route_id": route_id,
#             "waypoints": waypoints
#         }
    
#     except Exception as e:
#         logger.error(f"Error deleting route {route_id} from database: {e}")
#         return {"message": "Unable to delete route"}

async def remove_route_function(req, user_id):
    """Remove route from database (works for both active & inactive routes)"""

    route_id = req.route_id

    try:
        # ❌ Nothing provided
        if not req.route_id:
            return {"message": "Provide route_id or route details to remove the route."}


        # ✅ Delete from persistent_routes (NEW FUNCTION)
        deleted_routes = delete_persistent_route_by_user_and_route(user_id, route_id)

        # ✅ Delete from nodes_combined
        deleted_nodes = delete_nodes_combined_by_user_and_route(user_id, route_id)

        if deleted_routes == 0:
            return {
                "message": "Route not found or already deleted",
                "route_id": route_id
            }

        logger.info(f"Route {route_id} deleted | routes={deleted_routes}, nodes={deleted_nodes}")

        return {
            "message": "Route removed successfully",
            "route_id": route_id,
            "deleted_routes": deleted_routes,
            "deleted_nodes": deleted_nodes
        }

    except Exception as e:
        logger.error(f"Error deleting route {route_id}: {str(e)}")
        return {"message": "Unable to delete route"}

# ======================================================= API ======================================================


# @router.post("/remove_route")
# async def remove_route(req: RemoveRouteRequest, current_user = Depends(get_current_user)):
#     """Remove a route from the system"""

#     user_id = current_user.get("user_id")
        
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
    
    
#     result = await remove_route_function(req, user_id)
#     return result

# @router.post("/get_alternative_route")
# async def get_alternative(req: AlternativeRouteRequest, current_user = Depends(get_current_user)):
#     """Get alternative route for an existing route"""

#     user_id = current_user.get("user_id")
        
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
        
    
#     logger.info(f"user_id {user_id}")
#     result = await get_alternative_function(req, user_id)
#     return result

# @router.post("/google_route")
# async def google_route(route_request: GoogleRouteRequest, current_user = Depends(get_current_user)):
#     """Calculate or retrieve route using Google Maps API"""
    
#     user_id = current_user.get("user_id")
        
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
    
    
#     waypoints = (
#         [route_request.source]
#         + (route_request.intermediate_locations or [])
#         + [route_request.destination]
#     )

#     objective = route_request.objective or "duration"

#     result = await calculate_route_with_google(user_id, waypoints, objective)
#     return result



# @router.post("/google_route")
# async def google_route(route_request: GoogleRouteRequest, current_user = Depends(get_current_user)):
#     """Calculate or retrieve route using Google Maps API"""

#     try:
#         user_id = current_user.get("user_id")

#         if not user_id:
#             return JSONResponse(
#                 status_code=401,
#                 content={
#                     "success": False,
#                     "message": "Invalid token: user_id not found"
#                 }
#             )

#         # Build waypoints list
#         waypoints = (
#             [route_request.source]
#             + (route_request.intermediate_locations or [])
#             + [route_request.destination]
#         )

#         objective = route_request.objective or "duration"

#         # Call Google route service
#         result = await calculate_route_with_google_function(user_id, waypoints, objective)

#         return JSONResponse(
#             status_code=200,
#             content={
#                 "success": True,
#                 "data": result
#             }
#         )

#     except Exception as e:
#         logger.error(f"[GOOGLE_ROUTE_ERROR] {str(e)}")

#         return JSONResponse(
#             status_code=500,
#             content={
#                 "success": False,
#                 "message": "Internal server error",
#             }
#         )