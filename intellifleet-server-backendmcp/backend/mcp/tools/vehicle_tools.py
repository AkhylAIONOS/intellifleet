
#backend/mcp/tools/vehicle_tools.py
from fastmcp import FastMCP
from backend.routes.vehicles.vehicle_api import (
    assign_vehicle_to_route_function,
    reset_single_vehicle_function,
)

from backend.routes.vehicles.multimodalVehicle import reset_all_vehicles_function
from backend.routes.vehicles.vehicle_status import set_vehicle_active_status
from backend.routes.vehicles.multimodalVehicle import (
    assign_vehicle_multimodal,
    assign_segment_2_air
)
from backend.database.database import (
    get_available_vehicles_with_capacity,
    get_multimodal_route_by_id,
    get_persistent_route_by_id
)
from backend.models.vechileSchema import (
    VehicleAssignmentRequest,
    ResetSingleVehicleRequest
)
from backend.mcp.schemas.vehicle_schemas import (
    AssignVehicleInput, AssignVehicleOutput,
    ResetVehicleInput, ResetVehicleOutput,
    ResetAllVehiclesInput, ResetAllVehiclesOutput,
    UpdateVehicleStatusInput, UpdateVehicleStatusOutput,
)
import asyncio
from backend.routes.vehicles.partial_vehicle import start_partial_assignment
from backend.config.logger import *

def register_vehicle_tools(mcp: FastMCP):
    """Register all vehicle-related tools with schemas"""
    

    @mcp.tool()
    async def assign_vehicle(input: AssignVehicleInput) -> AssignVehicleOutput:
        
        """
        Trigger this if the user mentions transporting/shipping goods, any quantity (e.g., 5000 kg), or 
        assigning vehicles between a source and destination (always trigger if quantity + locations are present, regardless of road/air/fastest).
        User may mention the transport_mode whether road or air, otherwise transport_mode is None.
        This must not be called in case of any disruption on route or on delivery.
        """
        try:
            # ── Resolve source/destination from route_id if not directly provided ──
            source      = input.source
            destination = input.destination
            objective   = input.objective or "cost"

            if not source or not destination:
                if not input.route_id:
                    return AssignVehicleOutput(
                        vehicle_id=0, vehicle_label="Unknown", route_id=None,
                        capacity=input.capacity, departure_time="N/A", arrival_time="N/A",
                        message="Please provide either source+destination or a route_id.",
                        data={}, success=False,
                    )

                route = get_persistent_route_by_id(input.user_id, input.route_id) \
                    or get_multimodal_route_by_id(input.user_id, input.route_id)

                if not route:
                    return AssignVehicleOutput(
                        vehicle_id=0, vehicle_label="Unknown", route_id=input.route_id,
                        capacity=input.capacity, departure_time="N/A", arrival_time="N/A",
                        message=f"Route {input.route_id} not found.",
                        data={}, success=False,
                    )

                route_data  = route.get("route_data") or route.get("multimodal_data", {})
                source      = route_data.get("source", "unknown")
                destination = route_data.get("destination", "unknown")
                objective   = route_data.get("objective", objective)

            # ── Input validation ───────────────────────────────────────────────────
            if not source:
                return AssignVehicleOutput(
                    vehicle_id=0, vehicle_label="Unknown", route_id=input.route_id,
                    capacity=input.capacity, departure_time="N/A", arrival_time="N/A",
                    message="Please provide the source location.",
                    data={}, success=False,
                )

            if not destination:
                return AssignVehicleOutput(
                    vehicle_id=0, vehicle_label="Unknown", route_id=input.route_id,
                    capacity=input.capacity, departure_time="N/A", arrival_time="N/A",
                    message="Please provide the destination location.",
                    data={}, success=False,
                )

            # ── Delegate entirely to partial-assignment engine ─────────────────────
            result = await start_partial_assignment(
                user_id         = input.user_id,
                source          = source,
                destination     = destination,
                required_capacity = input.capacity,
                objective       = objective,
                vehicle_type    = input.vehicle_types[0] if input.vehicle_types else None,
            )

            if not result or not result.get("success"):
                return AssignVehicleOutput(
                    vehicle_id=0, vehicle_label="Unknown", route_id=input.route_id,
                    capacity=input.capacity, departure_time="N/A", arrival_time="N/A",
                    message=result.get("response_text", "Could not find a suitable vehicle or route."),
                    data={}, success=False,
                )

            # ── Map result → AssignVehicleOutput ───────────────────────────────────
            actions    = result.get("actions", [])
            start_data = next(
                (a["data"] for a in actions if a["type"] == "partial_assignment_start"), {}
            )
            first_seg     = next(
                (a["data"]["segment"] for a in actions if a["type"] == "animate_segment"), {}
            )
            first_vehicle = (first_seg.get("assigned_vehicles") or [{}])[0]

            return AssignVehicleOutput(
                vehicle_id    = first_vehicle.get("vehicle_id", 0),
                vehicle_label = first_vehicle.get("label", "Unknown"),
                route_id      = input.route_id,
                capacity      = input.capacity,
                departure_time= start_data.get("overall_departure", "N/A"),
                arrival_time  = start_data.get("final_arrival", "N/A"),
                message       = result.get("response_text", "Vehicles assigned."),
                data          = start_data,
                session_id    = start_data.get("session_id"),
                actions       = actions,
                response_text = result.get("response_text"),
                success       = True,
            )

        except Exception as e:
            logger.error(f"Error in assign_vehicle MCP tool: {e}", exc_info=True)
            return AssignVehicleOutput(
                vehicle_id=0, vehicle_label="Unknown", route_id=input.route_id,
                capacity=input.capacity, departure_time="N/A", arrival_time="N/A",
                message="Could not assign vehicle due to an internal error.",
                data={}, success=False,
            )

    @mcp.tool()
    async def reset_vehicle(input: ResetVehicleInput) -> ResetVehicleOutput:
        """
        Reset vehicle to its original warehouse. Stops vehicle movement and returns it to warehouse.
        """
        request = ResetSingleVehicleRequest(
            vehicle_id=input.vehicle_id,
            route_id=input.route_id
        )
        
        result = await reset_single_vehicle_function(request, input.user_id)
        
        return ResetVehicleOutput(
            vehicle_id=input.vehicle_id,
            message=result.get("message", f"Vehicle {input.vehicle_id} reset")
        )
    
    
    @mcp.tool()
    async def reset_all_vehicles(input: ResetAllVehiclesInput) -> ResetAllVehiclesOutput:
        """
        Reset all vehicles for user to their warehouses. Clears all active assignments and returns vehicles to warehouses.
        """
        result = await reset_all_vehicles_function(input.user_id)
        
        return ResetAllVehiclesOutput(
            vehicles_reset=result.get("vehicles_reset", []),
            message=result.get("message", "All vehicles reset")
        )
    
    @mcp.tool()
    async def vehicle_status_update(input: UpdateVehicleStatusInput) -> UpdateVehicleStatusOutput:
        """
        Activate or deactivate a vehicle.
        Trigger this When user wants to activate or deactivate a vehicle by its ID. or say vehicle id is funcitional or non functional or not working or damaged.
        """
        result = await set_vehicle_active_status(
            user_id=input.user_id,
            vehicle_id=input.vehicle_id,
            is_active=input.is_active
        )
        
        # print(f"==>> result:  {result}")

        data = result.get("data", {})
        
        return UpdateVehicleStatusOutput(
            vehicle_id=input.vehicle_id,
            is_active=input.is_active,
            message=result.get("message", f"Vehicle {input.vehicle_id} status updated"),
        )
    
    # @mcp.tool()
    # async def assign_multimodal_vehicle(input: AssignMultimodalVehicleInput) -> AssignMultimodalVehicleOutput:
    #     """
    #     Assign vehicles to all segments of a multimodal route.
        
    #     Automatically assigns road vehicles to segments 1 & 3,
    #     and plane to segment 2 if available.
    #     """
    #     route = get_multimodal_route_by_id(input.user_id, input.route_id)
    #     if not route:
    #         return AssignMultimodalVehicleOutput(
    #             route_id=input.route_id,
    #             message="Multimodal route not found",
    #             success=False
    #         )
        
    #     result = await assign_vehicle_multimodal(
    #         route=route,
    #         route_id=input.route_id,
    #         user_id=input.user_id
    #     )
        
    #     return AssignMultimodalVehicleOutput(
    #         route_id=input.route_id,
    #         segment_1_vehicle=result.get("segment_1", {}).get("vehicle_id"),
    #         segment_2_vehicle=result.get("segment_2", {}).get("vehicle_id"),
    #         segment_3_vehicle=result.get("segment_3", {}).get("vehicle_id"),
    #         message=result.get("message", "Vehicles assigned to multimodal route"),
    #         success=bool(result.get("segment_1"))
    #     )
    
    # @mcp.tool()
    # async def assign_plane(input: AssignPlaneInput) -> AssignPlaneOutput:
    #     """
    #     Assign plane to the air segment of multimodal route.
        
    #     Only assigns to segment 2 (air segment).
    #     Plane must be available at airport.
    #     """
    #     route = get_multimodal_route_by_id(input.user_id, input.route_id)
    #     if not route:
    #         return AssignPlaneOutput(
    #             route_id=input.route_id,
    #             plane_id=0,
    #             segment="segment_2",
    #             message="Multimodal route not found",
    #             success=False
    #         )
        
    #     result = await assign_segment_2_air(
    #         route=route,
    #         route_id=input.route_id,
    #         user_id=input.user_id
    #     )
        
    #     return AssignPlaneOutput(
    #         route_id=input.route_id,
    #         plane_id=result.get("plane_id", 0),
    #         segment="segment_2",
    #         message=result.get("message", "Plane assigned"),
    #         success=bool(result.get("plane_id"))
    #     )