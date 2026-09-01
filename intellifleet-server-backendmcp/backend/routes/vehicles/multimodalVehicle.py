# required imports
import json
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timedelta
from ...database.database import get_vehicles_by_user, update_vehicle, get_multimodal_route_by_id, get_available_vehicles_at_location, get_available_vehicles_with_capacity
from ...utilities.vehicleConstants import *
from ..auth import get_current_user
from ...models.airRouteSchema import *
from ...config.logger import *

router = APIRouter()
   
async def assign_vehicle_multimodal(route, route_id, user_id):
    try:
        assigned_data = {
            "status": "success",
            "route_id": route_id,
        }

        vehicles = get_vehicles_by_user(user_id)
        default_vehicle_type = "Truck"
        vehicle_type_details = VEHICLE_TYPES.get(default_vehicle_type.lower())

        now = datetime.now()
        departure_dt = datetime.strptime(now.strftime("%H:%M"), "%H:%M")

        # ================================================================
        # SEGMENT 1 → ROAD (source → nearest airport)
        # ================================================================
        segment_1 = route["multimodal_data"]["segment_1"]
        route_data = route.get("multimodal_data")
        duration = segment_1.get("duration", 0)
        # duration = route_data.get("total_duration", 0)
        
        print(f"==>> duration1:  {duration}")

        if segment_1["transport_mode"] == "road":
            source = segment_1["source"]
            distance = segment_1["distance"]

            if not duration:
                duration = 0
            
            duration_minutes = duration * 60

            required_capacity = segment_1.get("required_capacity", 0)

            # ───────────────────────────────────────────────────────────
            # Fetch vehicle available at location
            # ───────────────────────────────────────────────────────────
            truck = get_available_vehicles_at_location(
                user_id,
                source,
                default_vehicle_type
            )

            if not truck:
                return {"message": f"No truck available at {source}"}

            truck = truck[0]

            # ───────────────────────────────────────────────────────────
            # Capacity Check
            # ───────────────────────────────────────────────────────────
            if truck["capacity"] < required_capacity:
                return {"message": f"Truck capacity too low. Required: {required_capacity}"}

            # ───────────────────────────────────────────────────────────
            # Calculate departure + arrival
            # ───────────────────────────────────────────────────────────
            departure_time = departure_dt.strftime("%H:%M")
            arrival_dt = departure_dt + timedelta(minutes=duration_minutes)
            arrival_time = arrival_dt.strftime("%H:%M")

            # ───────────────────────────────────────────────────────────
            # Cost Calculation
            # ───────────────────────────────────────────────────────────
            cost = (
                distance / vehicle_type_details["fuel_consumption"]
            ) * vehicle_type_details["fuel_price"]

            # ───────────────────────────────────────────────────────────
            # Save assignment
            # ───────────────────────────────────────────────────────────
            assigned_vehicle_data = {
                "vehicle_id": truck["id"],
                "vehicle_type": "truck",
                "vehicle_capacity": truck["capacity"],
                "start_location": source,
                "end_location": segment_1["destination"],
                "departure_time": departure_time,
                "arrival_time": arrival_time,
                "returns_to": source,
                "route_cost": cost,
                "duration": duration,
                "assigned_at": datetime.now().isoformat()
            }

            # Add inside segment
            segment_1["assigned_vehicle"] = assigned_vehicle_data
            assigned_data["segment_1"] = assigned_vehicle_data

            route_info = {
                "route_id": route_id,
                "source": segment_1.get("source"),
                "destination": segment_1.get("destination"),
                "assigned_at": datetime.now().isoformat(),
            }

            # Update vehicle
            update_vehicle(
                truck["id"],
                user_id,
                {
                    "is_available": False,
                    "assigned_route": route_info,
                    "vehicle_details": vehicle_type_details,
                    "departure_time": departure_time,
                    "arrival_time": arrival_time,
                    "status": "assigned"
                }
            )

        # ================================================================
        # SEGMENT 2 → AIR (airport → airport)
        # # ================================================================
        # segment_2 = route["multimodal_data"]["segment_2"]

        # if segment_2["transport_mode"] == "air":
        #     assigned_vehicle_data = {
        #         "mode": "air",
        #         "vehicle": "plane_animation",
        #         "note": "No physical vehicle assigned"
        #     }

        #     segment_2["assigned_vehicle"] = assigned_vehicle_data
        #     assigned_data["segment_2"] = assigned_vehicle_data
        
        assigned_data["vehicle_details"] = vehicle_type_details
        assigned_data["departure_time"] = departure_time
        assigned_data["arrival_time"] = arrival_time


        return assigned_data

    except Exception as e:
        logger.error(f"Error in multimodal assign: {e}")
        return {"message": "Unable to assign vehicle on multimodal route"}


async def assign_segment_3_road(route, route_id, user_id):
    try:
        segment_3 = route["multimodal_data"].get("segment_3")
        if not segment_3 or segment_3["transport_mode"] != "road":
            return {}

        assigned_data = {
            "status": "success",
            "route_id": route_id,
        }

        now = datetime.now()
        departure_dt = datetime.strptime(now.strftime("%H:%M"), "%H:%M")
        departure_time = departure_dt.strftime("%H:%M")

        source = segment_3["destination"]
        destination = segment_3["source"]
        distance = segment_3["distance"]

        required_capacity = segment_3.get("required_capacity", 0)

        # Fetch available trucks
        trucks = get_available_vehicles_at_location(user_id, source, "Truck")
        if not trucks:
            return {"message": f"No truck available at {source}"}

        truck = trucks[0]

        # Capacity check
        if truck["capacity"] < required_capacity:
            return {
                "message": f"Truck capacity too low. Required: {required_capacity}, Available: {truck['capacity']}"
            }

        # Duration calculation
        speed = 40   # km/hr (default road speed)
        duration_hours = distance / speed
        duration_minutes = duration_hours * 60

        arrival_dt = departure_dt + timedelta(minutes=duration_minutes)
        arrival_time = arrival_dt.strftime("%H:%M")

        # Cost calculation
        vehicle_type_details = VEHICLE_TYPES["truck"]
        cost = (
            distance / vehicle_type_details["fuel_consumption"]
        ) * vehicle_type_details["fuel_price"]

        # Assigned vehicle data
        assigned_vehicle_data = {
            "vehicle_id": truck["id"],
            "vehicle_type": "truck",
            "vehicle_capacity": truck["capacity"],
            "start_location": source,
            "end_location": destination,
            "route_cost": cost,
            "departure_time": departure_time,
            "arrival_time": arrival_time,
            "assigned_at": now.isoformat()
        }

        # Attach inside segment
        segment_3["assigned_vehicle"] = assigned_vehicle_data
        assigned_data["segment_3"] = assigned_vehicle_data

        # Add global return fields (same as other function)
        assigned_data["vehicle_details"] = vehicle_type_details
        assigned_data["departure_time"] = departure_time
        assigned_data["arrival_time"] = arrival_time

        # Update truck in DB
        update_vehicle(
            truck["id"],
            user_id,
            {
                "is_available": False,
                "assigned_route": {
                    "route_id": route_id,
                    "source": source,
                    "destination": destination,
                    "assigned_at": now.isoformat()
                },
                "vehicle_details": vehicle_type_details,
                "departure_time": departure_time,
                "arrival_time": arrival_time,
                "status": "assigned"
            }
        )

        return assigned_data

    except Exception as e:
        logger.error(f"Error in Segment 3: {e}")
        return {"message": "Unable to assign truck for segment 3"}



async def assign_segment_2_air(route, route_id, user_id, capacity=None):
    
    try:
        print(f"==>> capacity:  {capacity}")
        segment_2 = route["multimodal_data"].get("segment_2")
        if not segment_2 or segment_2.get("transport_mode") != "air":
            return {}

        assigned_data = {
            "status": "success",
            "route_id": route_id,
        }

        now = datetime.now()
        departure_time = now.strftime("%H:%M")

        source_airport = segment_2["source_airport_name"]
        destination_airport = segment_2["destination_airport_name"]

        source = route.get("source")
        destination = route.get("destination")

        # Fetch available plane
        if capacity:
            planes = get_available_vehicles_with_capacity(
                user_id=user_id,
                location_name=source,
                capacity=capacity,
                vehicle_type="Plane"
            )
        else:
            return {"message": "Capacity must be specified for plane assignment."}
        if not planes:
            return {"message": f"No plane available at {source}"}

        plane = planes[0]

        # Duration & arrival time
        duration_hours = segment_2.get("duration", 0)
        arrival_dt = now + timedelta(hours=duration_hours)
        arrival_time = arrival_dt.strftime("%H:%M")

        # Cost calculation (same pattern as road)
        plane_details = VEHICLE_TYPES.get("plane", {})

        cost = (
            segment_2["distance"] / plane_details.get("fuel_consumption", 1)
        ) * plane_details.get("fuel_price", 1)

        # Assigned vehicle payload (same structure as other segments)
        assigned_vehicle_data = {
            "vehicle_id": plane["id"],
            "vehicle_type": "plane",
            "vehicle_capacity": plane["capacity"],
            "start_location": source_airport,
            "start_coords": segment_2["source_airport"],
            "end_location": destination_airport,
            "end_coords": segment_2["destination_airport"],
            "route_cost": cost,
            "departure_time": departure_time,
            "arrival_time": arrival_time,
            "assigned_at": now.isoformat()
        }

        # Attach inside segment
        segment_2["assigned_vehicle"] = assigned_vehicle_data
        assigned_data["segment_2"] = assigned_vehicle_data

        # Add global return fields (same as other segments)
        assigned_data["vehicle_details"] = plane_details
        assigned_data["departure_time"] = departure_time
        assigned_data["arrival_time"] = arrival_time

        # Update plane in DB
        update_vehicle(
            plane["id"],
            user_id,
            {
                "is_available": False,
                "assigned_route": {
                    "route_id": route_id,
                    "source": source_airport,
                    "destination": destination_airport,
                    "assigned_at": now.isoformat()
                },
                "vehicle_details": plane_details,
                "departure_time": departure_time,
                "arrival_time": arrival_time,
                "status": "assigned"
            }
        )

        return assigned_data

    except Exception as e:
        logger.error(f"Error in Segment 2: {e}")
        return {"message": "Unable to assign plane for segment 2"}



async def reset_all_vehicles_function(user_id: int):
    try:
        vehicles = get_vehicles_by_user(user_id)
        if not vehicles:
            return {"message": "No vehicles found for this user"}
            

        reset_ids = []

        for v in vehicles:

            if v.get("is_available") == 0:
                update_vehicle(v["id"], user_id, {
                    "is_available": True,       
                    "assigned_route": None,
                    "status": "available"   
                })
                reset_ids.append(v["id"])

        if not reset_ids:
            return {"message": "No active vehicles found."}
        
        return {
            "status": "success",
            "message": "Vehicles reset successfully",
            "vehicles_reset": reset_ids
        }

    except Exception as e:
        return {"message": "Unable to reset vehicle"}


# ======================================================= API ======================================================

# @router.post("/assign_vehicle_seg3")
# async def assign_vehicle_seg3(payload: MultimodalRouteInput, current_user = Depends(get_current_user)):

#     try:

#         user_id = current_user.get("user_id")
            
#         if not user_id:
#             return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
            
        
#         route_id = payload.route_id

#         # print(user_id)
#         route = get_multimodal_route_by_id(user_id, route_id)
#         if not route:
#             return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}

#         # STEP 2 → Assign vehicles using your logic
#         assigned = await assign_segment_3_road(route, route_id, user_id)

#         return {
#             "status": "success",
#             "route_id": route_id,
#             "assigned_vehicles": assigned
#         }

#     except HTTPException as e:
#         raise e

#     except Exception as e:
#         return {"success": False, "status_code": 500, "message": "Unable to assign vehicle on segment 3."}
    

# @router.post("/reset_all_vehicles")
# async def reset_all_vehicles(current_user = Depends(get_current_user)):

#     user_id = current_user.get("user_id")
        
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
        
    
#     result = await reset_all_vehicles_function(user_id)
#     return result

# @router.post("/multimodal_assign_vehicle")
# async def multimodel_assign_vehicle(payload: MultimodalRouteInput, current_user = Depends(get_current_user)):

#     user_id = current_user.get("user_id")
        
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
    
    
#     route_id = payload.route_id

#     # print(user_id)
#     route = get_multimodal_route_by_id(user_id, route_id)
#     if not route:
#         return {"success": False, "status_code": 500, "message": f"Route with id {route_id} not found"}
        

#     # print("Route", route)

#     try:
#         # STEP 2 → Assign vehicles using your logic
#         assigned = await assign_vehicle_multimodal(route, route_id, user_id)

#         return {
#             "status": "success",
#             "route_id": route_id,
#             "assigned_vehicles": assigned
#         }
    
#     except Exception as e:
#         return {"success": False, "status_code": 500, "message": "Unable to assign vehicle on route"}


# class RouteRequest(BaseModel):
#     route_id: int
#     capacity: int


# @router.post("/test")
# async def test_assign_segment_2_air_api(payload: RouteRequest, user: dict = Depends(get_current_user)):
#     """
#     Test API to assign vehicle for Air Segment (segment_2) using JSON body.
#     """

#     try:
#         user_id = user.get("user_id")
#         route_id = payload.route_id

#         # Fetch multimodal route
#         route = get_multimodal_route_by_id(user_id, route_id)
#         if not route:
#             raise HTTPException(status_code=404, detail="Route not found")

#         if "multimodal_data" not in route:
#             raise HTTPException(status_code=400, detail="Route has no multimodal data")

#         # Call assignment function
#         result = await assign_segment_2_air(route, route_id, user_id, capacity=payload.capacity)

#         return {
#             "success": True,
#             "route_id": route_id,
#             "data": result
#         }

#     except Exception as e:
#         logger.error(f"Air assignment test error: {e}")
#         raise HTTPException(status_code=500, detail=str(e))