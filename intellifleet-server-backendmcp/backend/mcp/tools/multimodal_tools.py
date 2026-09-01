from fastmcp import FastMCP
from backend.routes.route_map.airRoute import (
    remove_multimodal_route_function
)
from backend.routes.route_map.route_status import set_multimodal_route_active_status
from backend.routes.route_map.testAIR import combined_route_function
from backend.models.airRouteSchema import AirRouteRequest, RemoveMultimodalRoute
from backend.mcp.schemas.multimodal_schemas import (
    PlanMultimodalRouteInput, PlanMultimodalRouteOutput,
    RemoveMultimodalRouteInput, RemoveMultimodalRouteOutput,
    UpdateAirRouteStatusInput, UpdateAirRouteStatusOutput
)
from backend.routes.route_map.optimized_route import smart_route_handler_air

def register_multimodal_tools(mcp: FastMCP):
    """Register all multimodal route tools with schemas"""
    
    @mcp.tool()
    async def multimodal_route(input: PlanMultimodalRouteInput) -> PlanMultimodalRouteOutput:
        """
        Trigger this when user asked to plan an air/multimodal route.
        Use this always in case of fastest. For multimodal or air routes → transport_mode = "air".
        Do NOT use "multimodal_route" for goods movement. Use it only when the user explicitly asks to plan an air/multimodal route.
        """
        # request = AirRouteRequest(
        #     source=input.source,
        #     destination=input.destination
        # )
        
        result = await smart_route_handler_air(
            user_id=input.user_id,
            source=input.source,
            destination=input.destination,
            via_list=input.intermediate_locations or [],
            objective=input.objective or "duration"
        )
        
        # result = await smart_route_handler_air(request, input.user_id)
        # print(f"==>> result:  {result}")
        data = result.get("data", {})

        return PlanMultimodalRouteOutput(
            status=result.get("status", True),
            message=result.get("message", "Multimodal route planned"),
            data=data,
            cached=result.get("cached", False),
            route_id=result.get("route_id", 0),
            source=result.get("source", input.source),
            destination=result.get("destination", input.destination),
            total_distance_km=result.get("total_distance_km", data.get("total_distance_km", 0)),
            total_duration=result.get("total_duration", data.get("total_duration", 0)),
            total_cost=result.get("total_cost", data.get("total_cost", 0)),
            objective=result.get("objective", "duration"),
        )
    
    @mcp.tool()
    async def remove_multimodal_route(input: RemoveMultimodalRouteInput) -> RemoveMultimodalRouteOutput:
        """
        Remove a multimodal route. Can remove by route_id or source/destination.
        """
        request = RemoveMultimodalRoute(
            route_id=input.route_id,
            source=input.source,
            destination=input.destination
        )
        
        result = await remove_multimodal_route_function(request, input.user_id)
        # print(f"==>> result:  {result}")
        
        return RemoveMultimodalRouteOutput(
            route_id=result.get("route_id", "unknown"),
            message=result.get("message", "Multimodal route removed")
        )
    
    @mcp.tool()
    async def route_status_update(input: UpdateAirRouteStatusInput) -> UpdateAirRouteStatusOutput:
        """
        Trigger ONLY when the user explicitly wants to activate, deactivate, enable, disable, close, block, mark functional or non-functional a MULTIMODAL/AIR ROUTE by its ID.  
        User MUST mention “multimodal route” or “air route” or similar.  
        DO NOT trigger this for road route issues or alternative route requests.
        """
        result = await set_multimodal_route_active_status(
            user_id=input.user_id,
            route_id=input.route_id,
            is_active=input.is_active
        )
        
        # print(f"==>> result:  {result}")

        data = result.get("data", {})
        
        return UpdateAirRouteStatusOutput(
            route_id=input.route_id,
            is_active=input.is_active,
            message=result.get("message", f"Route {input.route_id} status updated"),
        )