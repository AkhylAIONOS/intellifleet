import json
from fastapi import APIRouter, Depends, HTTPException
from ..routes.auth import get_current_user
from ..config.logger import logger
from ..database.database import (
    delete_persistent_route,
    fetch_persistent_routes_by_user, delete_persistent_route, get_vehicles_by_user, get_warehouses_by_user, update_vehicle, delete_multimodal_route,
    fetch_multimodal_routes_by_user, delete_nodes_by_user, delete_nodes_by_user_air, delete_nodes_combined_by_user
)
from backend.routes.vehicles.multimodalVehicle import reset_all_vehicles_function
router = APIRouter()

# async def clear_all_routes_function(user_id):
#     try:

#         routes = fetch_persistent_routes_by_user(user_id) or []
#         vehicles = get_vehicles_by_user(user_id) or []
#         warehouses = get_warehouses_by_user(user_id)
#         warehouse_map = {wh["warehouse_id"]: wh for wh in warehouses}

#         logger.info(f"[CLEAR MAP] user_id={user_id} | persistent_routes={len(routes)} | vehicles={len(vehicles)} | warehouses={len(warehouses)}")

#         reset_count = 0

#         for vehicle in vehicles:
#             ar = vehicle.get("assigned_route")
#             if not ar:
#                 continue

#             if isinstance(ar, str):
#                 try:
#                     ar_dict = json.loads(ar)
#                 except:
#                     continue
#             else:
#                 ar_dict = ar

#             route_id = ar_dict.get("route_id") if isinstance(ar_dict, dict) else None
#             if route_id is None:
#                 continue

#             wh = warehouse_map.get(vehicle["warehouse_id"])
#             if not wh:
#                 continue

#             update_data = {
#                 "current_location": wh["name"],
#                 "is_available": True,
#                 "assigned_route": None,
#                 "status": "available"
#             }

#             if wh.get("latitude") and wh.get("longitude"):
#                 update_data["current_position"] = {
#                     "lat": float(wh["latitude"]),
#                     "lng": float(wh["longitude"])
#                 }

#             if update_vehicle(vehicle["id"], user_id, update_data):
#                 reset_count += 1

#         deleted_routes = 0
#         for route in routes:
#             rid = route["route_id"]
#             ok = delete_persistent_route(user_id, rid)
#             logger.info(f"[CLEAR MAP] delete_persistent_route route_id={rid} -> {ok}")
#             if ok:
#                 deleted_routes += 1

#         multimodal_routes = fetch_multimodal_routes_by_user(user_id) or []
#         logger.info(f"[CLEAR MAP] multimodal_routes={len(multimodal_routes)}")

#         multimodal_routes_deleted = 0
#         for route in multimodal_routes:
#             multimodal_route_id = route.get("route_id")
#             if multimodal_route_id:
#                 ok = delete_multimodal_route(user_id, multimodal_route_id)
#                 logger.info(f"[CLEAR MAP] delete_multimodal_route route_id={multimodal_route_id} -> {ok}")
#                 if ok:
#                     multimodal_routes_deleted += 1

#         nodes_deleted = delete_nodes_by_user(user_id)
#         nodes_deleted_air = delete_nodes_by_user_air(user_id)
#         combined_nodes_deleted = delete_nodes_combined_by_user(user_id)
#         logger.info(f"[CLEAR MAP] nodes_deleted={nodes_deleted} nodes_air={nodes_deleted_air} combined={combined_nodes_deleted}")

#         summary = {
#             "message": "All routes cleared and active vehicles reset.",
#             "total_routes_deleted": deleted_routes,
#             "total_multimodal_routes_deleted": multimodal_routes_deleted,
#             "total_nodes_deleted": nodes_deleted,
#             "total_nodes_air_deleted": nodes_deleted_air,
#             "total_combined_nodes_deleted": combined_nodes_deleted,
#             "total_vehicles_reset": reset_count
#         }
#         logger.info(f"[CLEAR MAP] final summary: {summary}")
#         return summary

#     except Exception as e:
#         logger.error(f"Error clearing all routes: {e}", exc_info=True)
#         return {"message": "Unable to clear map"}


async def clear_all_routes_function(user_id):
    try:
        routes = fetch_persistent_routes_by_user(user_id) or []

        # ✅ Use reset_all_vehicles_function instead of manual reset logic
        vehicle_reset_result = await reset_all_vehicles_function(user_id)
        reset_count = len(vehicle_reset_result.get("vehicles_reset", []))
        logger.info(f"[CLEAR MAP] vehicle reset result: {vehicle_reset_result}")

        deleted_routes = 0
        for route in routes:
            rid = route["route_id"]
            ok = delete_persistent_route(user_id, rid)
            logger.info(f"[CLEAR MAP] delete_persistent_route route_id={rid} -> {ok}")
            if ok:
                deleted_routes += 1

        multimodal_routes = fetch_multimodal_routes_by_user(user_id) or []
        multimodal_routes_deleted = 0
        for route in multimodal_routes:
            multimodal_route_id = route.get("route_id")
            if multimodal_route_id:
                ok = delete_multimodal_route(user_id, multimodal_route_id)
                if ok:
                    multimodal_routes_deleted += 1

        nodes_deleted = delete_nodes_by_user(user_id)
        nodes_deleted_air = delete_nodes_by_user_air(user_id)
        combined_nodes_deleted = delete_nodes_combined_by_user(user_id)

        summary = {
            "message": "All routes cleared and active vehicles reset.",
            "total_routes_deleted": deleted_routes,
            "total_multimodal_routes_deleted": multimodal_routes_deleted,
            "total_nodes_deleted": nodes_deleted,
            "total_nodes_air_deleted": nodes_deleted_air,
            "total_combined_nodes_deleted": combined_nodes_deleted,
            "total_vehicles_reset": reset_count
        }
        logger.info(f"[CLEAR MAP] final summary: {summary}")
        return summary

    except Exception as e:
        logger.error(f"Error clearing all routes: {e}", exc_info=True)
        return {"message": "Unable to clear map"}
    
# ======================================================= API ======================================================

# @router.post("/clear_map")
# async def clear_all_routes(current_user = Depends(get_current_user)):
    
#     user_id = current_user.get("user_id")
        
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}

    
#     result = await clear_all_routes_function(user_id)
#     return result
