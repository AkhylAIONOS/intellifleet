import json
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from ...config.logger import logger
from ..auth import get_current_user
from ...models.vechileSchema import *
from ...utilities.vehicleConstants import *
from ...database.database import (
    get_vehicles_by_user,
    get_available_vehicles_at_location,
    update_vehicle,
    get_warehouse_by_name,
    get_warehouses_by_user,
    get_persistent_route_by_id
)

router = APIRouter(tags=["Vehicles Management"])

async def assign_vehicle_to_route_function(assignment: VehicleAssignmentRequest, user_id: int):
    print(f"==>> assignment:  {assignment}")
    """Assign a vehicle to a route"""
    try:
        # Fetch route from database
        route = get_persistent_route_by_id(user_id, assignment.route_id)
        # print(f"==>> route:  {route}")
        
        if not route:
            return {"message": "Route not found"}
        
        # Parse route data
        route_data = route.get("route_data")
        if isinstance(route_data, str):
            route_data = json.loads(route_data)
        
        distance = route_data.get("distance")
        print(f"==>> distance:  {distance}")
        
        duration = route_data.get("duration")  # Important for arrival-time
        print(f"==>> duration:  {duration}")
        
        if not duration:
            duration = 0

        duration_minutes = duration * 60

        vehicles = get_vehicles_by_user(user_id)
        vehicle = next((v for v in vehicles if v["id"] == assignment.vehicle_id), None)
        if not vehicle:
            return {"message": "Vehicle not found"}

        if not vehicle.get("is_available", True):
            return {"message": "Vehicle not available"}

        required_capacity = assignment.capacity
        vehicle_capacity = vehicle.get("capacity", 0)
        if vehicle_capacity < required_capacity:
            return {"message": f"Vehicle capacity too low. Required: {required_capacity}"}
        
        
        now = datetime.now()
        print(f"==>> now:  {now}")
        departure_dt = datetime.strptime(now.strftime("%H:%M"), "%H:%M")
        print(f"==>> departure_dt:  {departure_dt}")
        departure = departure_dt.strftime("%H:%M")
        print(f"==>> depature:  {departure}")
        arrival_dt = departure_dt + timedelta(minutes=duration_minutes)
        print(f"==>> arrival_dt:  {arrival_dt}")
        arrival_str = arrival_dt.strftime("%H:%M")
        print(f"==>> arrival_str:  {arrival_str}")
        
        # Create route info for vehicle assignment
        route_info = {
            "route_id": assignment.route_id,
            "assigned_at": datetime.now().isoformat(),
            "vehicle_type": assignment.vehicle_type,
            "source": route.get("source"),
            "destination": route.get("destination"),
            "waypoints": route_data.get("waypoints") or route_data.get("locations") or []
        }

        print(f"==>> route_info:  {route_info}")

        vehicle_type_details = VEHICLE_TYPES.get(assignment.vehicle_type.lower())

        # Calculate route cost
        if vehicle_type_details and distance:
            fuel_needed = distance / vehicle_type_details["fuel_consumption"]
            route_cost = fuel_needed * vehicle_type_details["fuel_price"]
        else:
            route_cost = 0

        # Update vehicle in database
        update_success = update_vehicle(
            
            assignment.vehicle_id,
            user_id,
            {
                "is_available": False,
                "assigned_route": route_info,
                "status": "assigned",
                "type": assignment.vehicle_type,
                "vehicle_details": vehicle_type_details,
                "departure_time": departure,
                "arrival_time": arrival_str
            }
        )

        print(f"==>> update_success:  {update_success}")

        if not update_success:
            return {"message": "Failed to update vehicle"}

        data = {
            "vehicle_id": assignment.vehicle_id,
            "vehicle_type": assignment.vehicle_type,
            "route_id": assignment.route_id,
            "vehicle_details": vehicle_type_details,
            "distance": distance,
            "duration": duration,
            "required_capacity": required_capacity,
            "vehicle_capacity": vehicle_capacity,
            "departure_time": departure,
            "arrival_time": arrival_str,
            "route_cost": route_cost
        }
        # result = {
        #     "vehicle_id": assignment.vehicle_id,
        #     "vehicle_type": assignment.vehicle_type,
        #     "route_id": assignment.route_id,
        #     "vehicle_details": vehicle_type_details,
        #     "distance": distance,
        #     "route_cost": route_cost
        # }
        
        return {
            "success": True,
            "message": f"{assignment.vehicle_type.title()} {vehicle.get('label','vehicle')} assigned",
            "data": data
        }

    except Exception as e:
        logger.error(f"Error assigning vehicle: {e}")
        return {"message": "Unable to assign vehicle on the route."}


async def complete_vehicle_route_function(complete_request: VehicleCompleteRequest, user_id: int):
    """Complete a vehicle's route assignment"""
    try:
        # Get vehicle information
        vehicles = get_vehicles_by_user(user_id)
        vehicle = next((v for v in vehicles if v["id"] == complete_request.vehicle_id), None)
        if not vehicle:
            return {"success": False, "status_code": 500, "message": "Vehicle not found"}
            

        # Get destination warehouse
        dest_warehouse = get_warehouse_by_name(user_id, complete_request.destination)
        if not dest_warehouse:
            return {"success": False, "status_code": 500, "message": "Destination warehouse not found"}
            

        # Update vehicle in database
        update_data = {
            "current_location": complete_request.destination,
            "is_available": True,
            "assigned_route": None,
            "status": "available"
        }

        if dest_warehouse.get("latitude") and dest_warehouse.get("longitude"):
            update_data["current_position"] = {
                "lat": float(dest_warehouse["latitude"]),
                "lng": float(dest_warehouse["longitude"])
            }

        update_success = update_vehicle(complete_request.vehicle_id, user_id, update_data)
        if not update_success:
            return {"success": False, "status_code": 500, "message": "Failed to update vehicle"}
            

        logger.info(f"Vehicle {complete_request.vehicle_id} completed route {complete_request.route_id} to {complete_request.destination}")

        return {
            "message": f"Vehicle {complete_request.vehicle_id} completed route {complete_request.route_id} to {complete_request.destination}",
            "vehicle_id": complete_request.vehicle_id,
            "destination": complete_request.destination,
            "route_id": complete_request.route_id
        }

    except Exception as e:
        logger.error(f"Error completing vehicle route: {e}")
        return {"success": False, "status_code": 500, "message": "Internal server error"}
    

async def reset_single_vehicle_function(vehicleResetRequest, user_id):
    """Reset a single vehicle to its original warehouse"""
    try:
        # Get user's vehicles
        user_vehicles = get_vehicles_by_user(user_id)
        vehicle = next((v for v in user_vehicles if v["id"] == vehicleResetRequest.vehicle_id), None)
        if not vehicle:
            return {"message": "Vehicle not found"}
            

        # Get the vehicle's original warehouse
        warehouses = get_warehouses_by_user(user_id)
        warehouse = next((wh for wh in warehouses if wh["warehouse_id"] == vehicle["warehouse_id"]), None)

        if warehouse:
            update_data = {
                "current_location": warehouse["name"],
                "is_available": True,
                "assigned_route": None,
                "status": "available"
            }

            if warehouse.get("latitude") and warehouse.get("longitude"):
                update_data["current_position"] = {
                    "lat": float(warehouse["latitude"]),
                    "lng": float(warehouse["longitude"])
                }

            update_success = update_vehicle(vehicleResetRequest.vehicle_id, user_id, update_data)
            if not update_success:
                return {"message": "Failed to reset vehicle"}
                

        logger.info(f"Vehicle {vehicleResetRequest.vehicle_id} reset")

        return {
            "message": "Vehicle reset successfully",
            "vehicle_id": vehicleResetRequest.vehicle_id
        }

    except Exception as e:
        logger.error(f"Error resetting vehicle: {e}")
        return {"message": "Unable to reset specified vehicle"}


# ======================================================= API ======================================================

@router.post("/vehicles_available")
async def get_available_vehicles_at_location_endpoint(req: AvailableVehiclesRequest, current_user = Depends(get_current_user)):
    """Get available vehicles at a specific location"""
    
    try:
        
        user_id = current_user.get("user_id")
        
        if not user_id:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": "Invalid token: user_id not found"
                },
            )
           
        location = req.location

        vehicles = get_available_vehicles_at_location(user_id, req.location)

        if not vehicles:

            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": f"No vehicles available at {req.location}."
                },
            )

        type_counts = {}
        for v in vehicles:
            vtype = v["type"]
            type_counts[vtype] = type_counts.get(vtype, 0) + 1

        formatted_lines = [f"- {vtype}: {count}" for vtype, count in type_counts.items()]
        formatted_reply = f"Available vehicles at {location}:\n" + "\n".join(formatted_lines)

        data = {
            "parameters": {"location": req.location},
            "vehicles": vehicles,    
            "counts": type_counts 
        }
        return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": formatted_reply,
                    "data": data
                },
            )

    except Exception as e:
        logger.error(f"Error listing vehicles: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Unable to get available vehicles at specified location."
            },
        )

    

@router.post("/vehicles_complete")
async def complete_vehicle_route(complete_request: VehicleCompleteRequest, current_user = Depends(get_current_user)):
    """Mark a vehicle's route as completed"""

    try:
        user_id = current_user.get("user_id")
            
        if not user_id:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": "Invalid token: user_id not found"
                },
            )
        
        result = await complete_vehicle_route_function(complete_request, user_id)
        
        return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": result.get("message"),
                    "data": result
                },
            )
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error"
            },
        )


#=============================================================================================================================================

# @router.post("/assign_vehicle")
# async def assign_vehicle_to_route(assignment: VehicleAssignmentRequest, current_user = Depends(get_current_user)):
#     """Assign a vehicle to a route using route_id"""
    
#     user_id = current_user.get("user_id")
        
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
        
    
#     result = await assign_vehicle_to_route_function(assignment, user_id)
#     return result

# @router.post("/reset_single_vehicle")
# async def reset_single_vehicle(vehicleResetRequest: ResetSingleVehicleRequest, current_user = Depends(get_current_user)):
#     """Reset a single vehicle to its original warehouse"""
    
#     user_id = current_user.get("user_id")
        
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
        
    
#     result = await reset_single_vehicle_function(vehicleResetRequest, user_id)
#     return result