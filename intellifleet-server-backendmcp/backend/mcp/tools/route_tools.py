
#backend/mcp/tools/route_tools.py
import json
from fastmcp import FastMCP
from backend.config.logger import *
from backend.routes.route_map.googleRoute import (
    calculate_route_with_google,
    get_alternative_function,
    remove_route_function
)
from backend.routes.route_map.route_query import query_route_llm
from backend.models.routeSchema import AlternativeRouteRequest, RemoveRouteRequest
from backend.mcp.schemas.route_schemas import (
    PlanRouteInput, PlanRouteOutput,
    AlternativeRouteInput, AlternativeRouteOutput,
    RemoveRouteInput, RemoveRouteOutput,
    FetchRoutesInput, FetchRoutesOutput
)
from backend.routes.route_map.optimized_route import smart_route_handler, smart_route_handler_air

def register_route_tools(mcp: FastMCP):
    """Register all route-related tools with schemas"""
    

    @mcp.tool()
    async def plan_route(input: PlanRouteInput) -> PlanRouteOutput:
        """
        Trigger this when user asked to plan a new route between locations (by road)
        Do NOT use plan_route for goods movement. Use it only when the user explicitly asks to plan a route.
        """

        try:
            user_id = input.user_id
            source = input.source
            destination = input.destination
            via_list = input.intermediate_locations or []
            objective = input.objective or "duration"

            result = await smart_route_handler(
                user_id=user_id,
                source=source,
                destination=destination,
                via_list=via_list,
                objective=objective
            )

            if not result or not isinstance(result, dict):
                raise ValueError("Invalid response.")

            optimal_routes = result.get("optimal_routes")
            if not optimal_routes:
                return PlanRouteOutput(
                    route_id=0,
                    source=source,
                    destination=destination,
                    distance=0.0,
                    duration=0.0,
                    waypoints=[],
                    message=result.get("message", "No optimal route found."),
                    optimal_routes=[],
                    locations=[],
                    route_cost=0.0,
                    source_coords={},
                    dest_coords={},
                    objective=objective,
                    cached=False,
                )

            return PlanRouteOutput(
                route_id=result.get("route_id", 0),
                source=result.get("source", source),
                destination=result.get("destination", destination),
                distance=result.get("distance", 0.0),
                duration=result.get("duration", 0.0),
                waypoints=result.get("locations", []),
                message=result.get("message", "Route planned successfully"),
                optimal_routes=result.get("optimal_routes", []),
                locations=result.get("locations", []),
                route_cost=result.get("route_cost", 0.0),
                source_coords=result.get("source_coords", {}),
                dest_coords=result.get("dest_coords", {}),
                objective=result.get("objective", objective),
                cached=result.get("cached", False),
            )

        except Exception as e:
            logger.error(f"[MCP TOOL ERROR] {e}", exc_info=True)
            return PlanRouteOutput(
                route_id=0,
                source=input.source,
                destination=input.destination,
                distance=0.0,
                duration=0.0,
                waypoints=[],
                message="Error planning route.",
                optimal_routes=[],
                locations=[],
                route_cost=0.0,
                source_coords={},
                dest_coords={},
                objective=input.objective or "duration",
                cached=False,
            )

    @mcp.tool()
    async def alternative_route(input: AlternativeRouteInput) -> AlternativeRouteOutput:
        """ 
        Trigger ONLY when the user requests a different/alternate route for travel.  
        The user may mention traffic, road block, or simply wanting another route.  
        DO NOT trigger this when the user asks to activate/deactivate/close any route or when there is delivery disruption.
        """
        
        request = AlternativeRouteRequest(
            route_id=input.route_id,
            reason=input.reason
        )

        result = await get_alternative_function(request, input.user_id)
        # print(f"==>> FULL result: {json.dumps(result, indent=2, default=str)}")

        # Extract actual route data from inside actions[0]["data"]
        action_data = {}
        actions = result.get("actions", [])
        if actions and isinstance(actions, list):
            action_data = actions[0].get("data", {})

        # Fallback: maybe data is at top-level if not nested
        data = action_data or result

        alt_route = data.get("alternative_route", {})

        return AlternativeRouteOutput(
            success=result.get("success", True),
            message=result.get("response", "Alternative route calculated"),
            route_id=data.get("route_id"),
            parent_route_id=data.get("parent_route_id", input.route_id),
            alternative_route=data.get("alternative_route", []),
            distance=alt_route.get("distance") or data.get("distance"),
            duration=alt_route.get("duration") or data.get("duration"),
            fuel_needed=alt_route.get("fuel_needed") or data.get("fuel_needed"),
            route_cost=alt_route.get("route_cost") or data.get("route_cost"),
            source=data.get("source"),
            destination=data.get("destination"),
            waypoints=data.get("waypoints", []),
            is_alternative=True,
        )
        
    @mcp.tool()
    async def remove_route(input: RemoveRouteInput) -> RemoveRouteOutput:
        """
        Remove an existing route from the system.
        Can remove by route_id or by source/destination combination.
        """
        request = RemoveRouteRequest(
            route_id=input.route_id,
            source=input.source,
            destination=input.destination,
            intermediate_locations=input.intermediate_locations
        )
        
        result = await remove_route_function(request, input.user_id)
        # print(f"==>> result:  {result}")
        
        return RemoveRouteOutput(
            route_id=result.get("route_id", "unknown"),
            message=result.get("message", "Route removed")
        )
    
    @mcp.tool()
    async def fetch_routes(input: FetchRoutesInput) -> FetchRoutesOutput:
        """
        Fetch and analyze user's existing routes.
        Use when user asks about their routes, wants summary, or needs details or shortest fastest etc routes.
        Returns natural language analysis of all routes.
        """
        result = await query_route_llm(input.query, input.user_id)
        
        return FetchRoutesOutput(
            answer=result.get("answer", "No route information available"),
            message=result.get("message", "Routes fetched successfully"),
            route_id=result.get("route_id", "Route id")
        )