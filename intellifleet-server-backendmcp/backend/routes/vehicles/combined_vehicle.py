import json
from datetime import datetime, timedelta
from fastapi.responses import JSONResponse
from ...config.logger import logger
from ...models.vechileSchema import *
from ...utilities.vehicleConstants import *
from ...database.database import (
    get_vehicles_by_user,
    update_vehicle,
    get_persistent_route_by_id,
    get_multimodal_route_by_id
)
from pulp import *
import pandas as pd

#======================================================================= ROAD ROUTE =======================================================================

class VehicleAssignmentRequest(BaseModel):
    route_id: int
    capacity: int
    vehicle_type: Optional[str] = None
    objective: Optional[str] = "cost"


async def assign_vehicle_to_route_function(assignment: VehicleAssignmentRequest, user_id: int):
    
    try:
        # ----------------------------
        # Fetch Route
        # ----------------------------
        route = get_persistent_route_by_id(user_id, assignment.route_id)
        if not route:
            return {"message": "Route not found"}

        route_data = route.get("route_data") or {}
        distance = route_data.get("distance", 0)
        duration = route_data.get("duration", 0)

        # ----------------------------
        # Fetch Vehicles
        # ----------------------------
        vehicles = get_vehicles_by_user(user_id)
        if not vehicles:
            return {"message": "Vehicle not found"}

        vehicles_df = pd.DataFrame(vehicles)
        if vehicles_df.empty:
            return {"message": "Vehicle not found"}

        # Only available vehicles
        vehicles_df = vehicles_df[vehicles_df["is_available"] == 1]
        if vehicles_df.empty:
            return {"message": "Vehicle not available"}

        # Normalize fields
        vehicles_df["vehicle_id"] = vehicles_df["id"]
        vehicles_df["capacity_kg"] = vehicles_df["capacity"]
        vehicles_df["speed_kmph"] = vehicles_df.get("speed_kmph", 40)
        vehicles_df["cost_per_km"] = vehicles_df.get("cost_per_km", 10)
        vehicles_df["base_city"] = vehicles_df.get("warehouse_name", "")

        # Exclude planes
        vehicles_df = vehicles_df[vehicles_df["type"].str.lower() != "plane"]

        # Filter vehicles at source
        route_source = str(route.get("source")).lower()
        vehicles_df = vehicles_df[
            vehicles_df["base_city"].str.lower() == route_source
        ]

        if vehicles_df.empty:
            return {"message": "No vehicle available at route source location"}

        # Optional type filter
        if assignment.vehicle_type:
            req_type = assignment.vehicle_type.lower()
            vehicles_df = vehicles_df[
                vehicles_df["type"].str.lower() == req_type
            ]
            if vehicles_df.empty:
                return {"message": f"No '{req_type}' vehicle available at source"}

        # ----------------------------
        # Single Vehicle Check
        # ----------------------------
        single_vehicle_df = vehicles_df[vehicles_df["capacity_kg"] >= assignment.capacity]

        if not single_vehicle_df.empty:
            # Choose cheapest
            selected_df = single_vehicle_df.sort_values("cost_per_km").head(1)
            vehicle_records = [selected_df.iloc[0].to_dict()]
        else:
            # ----------------------------
            # Multi-Vehicle Optimization
            # ----------------------------
            model = LpProblem("MultiVehicleAssignment", LpMinimize)
            x = LpVariable.dicts("veh", vehicles_df.index, cat="Binary")

            # Objective cost or time
            if assignment.objective == "time":
                model += lpSum(
                    x[i] * (distance / vehicles_df.loc[i, "speed_kmph"])
                    for i in vehicles_df.index
                )
            else:
                model += lpSum(
                    x[i] * vehicles_df.loc[i, "cost_per_km"] * distance
                    for i in vehicles_df.index
                )

            # Capacity constraint
            model += lpSum(
                x[i] * vehicles_df.loc[i, "capacity_kg"]
                for i in vehicles_df.index
            ) >= assignment.capacity

            result = model.solve(PULP_CBC_CMD(msg=0))
            if result != 1:
                return {"message": "No feasible vehicle combination found"}

            # Extract selected vehicles
            vehicle_records = []
            for i in vehicles_df.index:
                if x[i].varValue == 1:
                    vehicle_records.append(vehicles_df.loc[i].to_dict())

        # ----------------------------
        # Prepare Response + Update DB
        # ----------------------------
        assigned_vehicle_responses = []
        total_capacity = 0

        for v in vehicle_records:
            vehicle_id = v["vehicle_id"]
            vehicle_type = v["type"].lower()
            vehicle_type_details = VEHICLE_TYPES.get(vehicle_type, {})

            # Time calc
            duration_minutes = duration * 60 if duration else 0
            now = datetime.now()
            departure_dt = datetime.strptime(now.strftime("%H:%M"), "%H:%M")
            arrival_dt = departure_dt + timedelta(minutes=duration_minutes)

            # Route info for this vehicle
            route_info = {
                "route_id": assignment.route_id,
                "assigned_at": datetime.now().isoformat(),
                "vehicle_type": v.get("type"),
                "source": route.get("source"),
                "destination": route.get("destination"),
                "waypoints": route_data.get("waypoints") or route_data.get("locations") or []
            }

            # Update vehicle in DB
            update_vehicle(
                vehicle_id,
                user_id,
                {
                    "is_available": False,
                    "assigned_route": route_info,
                    "status": "assigned",
                    "type": vehicle_type,
                    "vehicle_details": vehicle_type_details,
                    "departure_time": departure_dt.strftime("%H:%M"),
                    "arrival_time": arrival_dt.strftime("%H:%M"),
                }
            )

            # Build response record
            assigned_vehicle_responses.append({
                "vehicle_id": vehicle_id,
                "vehicle_type": vehicle_type,
                "label": v.get("label"),
                "capacity_kg": v.get("capacity_kg"),
                "speed_kmph": v.get("speed_kmph"),
                "cost_per_km": v.get("cost_per_km"),
                "base_city": v.get("base_city"),
                "vehicle_details": vehicle_type_details,
                "departure_time": departure_dt.strftime("%H:%M"),
                "arrival_time": arrival_dt.strftime("%H:%M"),
            })

            total_capacity += v.get("capacity_kg")

        # ----------------------------
        # Final Response
        # ----------------------------
        return {
            "success": True,
            "message": "Vehicles assigned successfully",
            "data": {
                "route_id": assignment.route_id,
                "required_capacity": assignment.capacity,
                "total_assigned_capacity": total_capacity,
                "distance": distance,
                "duration": duration,
                "assigned_vehicles": assigned_vehicle_responses,
                "departure_time": departure_dt.strftime("%H:%M"),
                "arrival_time": arrival_dt.strftime("%H:%M")
            }
        }

    except Exception as e:
        logger.error(f"Error assigning vehicle: {e}")
        return {"message": "Unable to assign vehicle on the route."}

#=======================================================================  MULTIMODAL ROUTE =======================================================================

async def assign_vehicle_multimodal(req: VehicleAssignmentRequest, user_id):
    """
    Multimodal Assignment (Updated for MULTI-VEHICLE SUPPORT):
      - Plane → assign to Segment-2 (air)
      - Other vehicles → assign to Segment-1 (road)
      - Supports MULTIPLE vehicles to satisfy required capacity.
    """

    try:
        route_id = req.route_id
        if not route_id:
            return {"message": "Route ID is required"}

        route = get_multimodal_route_by_id(user_id, route_id)
        if not route:
            return {"message": "Route not found"}

        multimodal = route.get("multimodal_data") or {}
        segment_1 = multimodal.get("segment_1")
        segment_2 = multimodal.get("segment_2")

        if not segment_1:
            return {"message": "Segment 1 missing"}

        required_capacity = req.capacity
        source_city = route.get("source")
        now = datetime.now()

        # --------------------------------------------------------
        # USER VEHICLES
        # --------------------------------------------------------
        vehicles = get_vehicles_by_user(user_id)
        if not vehicles:
            return {"message": "No vehicles found"}

        df = pd.DataFrame(vehicles)
        df = df[df["is_available"] == 1]
        df = df[df["warehouse_name"].str.lower() == str(source_city).lower()]

        if df.empty:
            return {"message": f"No vehicle available at {source_city}"}

        df["vehicle_id"] = df["id"]
        df["capacity_kg"] = df.get("capacity", 0)
        df["speed_kmph"] = df.get("speed_kmph", 40)
        df["cost_per_km"] = df.get("cost_per_km", 10)
        df["vehicle_type"] = df["type"].str.lower()

        # --------------------------------------------------------
        # OPTIMIZATION (MULTIPLE VEHICLES POSSIBLE)
        # --------------------------------------------------------
        road_distance = segment_1.get("distance", 0)
        air_distance = segment_2.get("distance", 0) if segment_2 else 0

        model = LpProblem("Multimodal_Optimizer", LpMinimize)
        x = LpVariable.dicts("v", df.index, cat="Binary")
        objective_terms = []

        for i in df.index:
            v_type = df.loc[i, "vehicle_type"]

            if v_type == "plane" and segment_2:
                cost = df.loc[i, "cost_per_km"] * air_distance
            else:
                cost = df.loc[i, "cost_per_km"] * road_distance

            objective_terms.append(x[i] * cost)

        model += lpSum(objective_terms)

        # MULTIPLE VEHICLES ALLOWED → Capacity >= required
        model += lpSum(x[i] * df.loc[i, "capacity_kg"] for i in df.index) >= required_capacity

        result = model.solve(PULP_CBC_CMD(msg=0))
        if result != 1:
            return {"message": "No feasible vehicle found"}

        # --------------------------------------------------------
        # FIND SELECTED VEHICLES (MAY BE MULTIPLE)
        # --------------------------------------------------------
        selected_vehicles = []
        for i in df.index:
            if x[i].varValue == 1:
                selected_vehicles.append(df.loc[i].to_dict())

        if not selected_vehicles:
            return {"message": "Vehicle selection failed"}

        # ----------------------------------------------------------
        # CASE A → ANY PLANE SELECTED → ASSIGN ALL PLANES TO SEGMENT-2
        # ----------------------------------------------------------
        planes = [v for v in selected_vehicles if v["vehicle_type"] == "plane"]

        if planes:
            if not segment_2:
                return {"message": "Plane selected but air segment missing"}

            assigned_list = []
            for sel in planes:
                plane_specs = VEHICLE_TYPES.get("plane", {})
                duration = segment_2.get("duration", 0)

                departure_time = now.strftime("%H:%M")
                arrival_time = (now + timedelta(hours=duration)).strftime("%H:%M")

                cost = (air_distance /
                        plane_specs.get("fuel_consumption", 1)) * \
                       plane_specs.get("fuel_price", 1)

                assigned_list.append({
                    "vehicle_id": sel["vehicle_id"],
                    "vehicle_type": "plane",
                    "vehicle_capacity": sel.get("capacity", 0),
                    "required_capacity": required_capacity,
                    "start_location": segment_2["source_airport_name"],
                    "start_coords": segment_2["source_airport"],
                    "end_location": segment_2["destination_airport_name"],
                    "end_coords": segment_2["destination_airport"],
                    "route_cost": cost,
                    "departure_time": departure_time,
                    "arrival_time": arrival_time,
                    "duration": duration,
                    "assigned_at": now.isoformat(),
                    "vehicle_details": plane_specs
                })

                # UPDATE DB FOR EACH VEHICLE
                update_vehicle(
                    sel["vehicle_id"],
                    user_id,
                    {
                        "is_available": False,
                        "assigned_route": {
                            "route_id": route_id,
                            "source": segment_2["source_airport_name"],
                            "destination": segment_2["destination_airport_name"],
                            "assigned_at": now.isoformat(),
                        },
                        "vehicle_details": plane_specs,
                        "departure_time": departure_time,
                        "arrival_time": arrival_time,
                        "status": "assigned",
                    }
                )

            # Attach all plane vehicles to segment 2
            segment_2["assigned_vehicle"] = assigned_list

            return {
                "success": True,
                "message": "Plane assigned to air segment",
                "data": assigned_list,
                "vehicle_type": "plane",
            }

        # --------------------------------------------------------
        # CASE B — ROAD VEHICLES SELECTED → SEGMENT-1 ASSIGNMENT
        # --------------------------------------------------------
        assigned_list = []
        total_capacity = 0

        for sel in selected_vehicles:
            v_type = sel["vehicle_type"]
            road_specs = VEHICLE_TYPES.get(v_type, {})
            duration_hours = segment_1.get("duration", 0)

            departure_time = now.strftime("%H:%M")
            arrival_time = (now + timedelta(hours=duration_hours)).strftime("%H:%M")

            if road_distance:
                fuel = road_distance / road_specs.get("fuel_consumption", 1)
                cost = fuel * road_specs.get("fuel_price", 1)
            else:
                cost = 0

            total_capacity += sel.get("capacity", 0)

            assigned_list.append({
                "vehicle_id": sel["vehicle_id"],
                "vehicle_type": v_type,
                "label": sel.get("label", f"{v_type}_{sel['vehicle_id']}"),
                "capacity_kg": sel.get("capacity", 0),
                "speed_kmph": sel.get("speed_kmph", 40),
                "cost_per_km": sel.get("cost_per_km", 10),
                "base_city": sel.get("warehouse_name"),
                "vehicle_details": road_specs,
                "departure_time": departure_time,
                "arrival_time": arrival_time
            })

            # DB update
            update_vehicle(
                sel["vehicle_id"],
                user_id,
                {
                    "is_available": False,
                    "assigned_route": {
                        "route_id": route_id,
                        "source": segment_1["source"],
                        "destination": segment_1["destination"],
                        "assigned_at": now.isoformat(),
                    },
                    "vehicle_details": road_specs,
                    "departure_time": departure_time,
                    "arrival_time": arrival_time,
                    "status": "assigned",
                }
            )

        segment_1["assigned_vehicle"] = assigned_list

        return {
            "success": True,
            "message": "Vehicles assigned successfully",
            "data": {
                "route_id": route_id,
                "required_capacity": required_capacity,
                "total_assigned_capacity": total_capacity,
                "distance": road_distance,
                "duration": segment_1.get("duration", 0),
                "assigned_vehicles": assigned_list,
                "departure_time": assigned_list[0]["departure_time"],
                "arrival_time": assigned_list[0]["arrival_time"]
            }
        }


    except Exception as e:
        logger.error(f"Multimodal error: {e}")
        return {"message": "Error assigning multimodal vehicle"}


#====================================================================== Combined ========================================================================

class VehicleRequest(BaseModel):
    route_id: int
    capacity: int
    vehicle_type: Optional[str] = None
    objective: Optional[str] = "cost"

async def assign_vehicle(req: VehicleRequest, user_id: int):
    try:        
        route_id = req.route_id

        input = VehicleAssignmentRequest(
                route_id=route_id,
                capacity=req.capacity,
                vehicle_type=req.vehicle_type,
                objective=req.objective
            )
        
        route = get_persistent_route_by_id(user_id, route_id)
        if route:
            
            result = await assign_vehicle_to_route_function(input, user_id)

            return result
    
        route = get_multimodal_route_by_id(user_id, route_id)
        if route:
            
            result = await assign_vehicle_multimodal(input, user_id)

            return result
        
        return {"message": "Route not found"}

    except Exception as e:
        logger.error(f"Vehicle assignment error: {e}")
        return {"message": "Error assigning vehicle"}