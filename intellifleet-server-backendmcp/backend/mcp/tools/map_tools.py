from fastmcp import FastMCP
from backend.routes.clearAll import clear_all_routes_function
from backend.config.redis import delete_data
from backend.mcp.schemas import (
    ClearMapInput, ClearMapOutput,
    SatelliteViewInput, SatelliteViewOutput,
    StreetViewInput, StreetViewOutput,
    ClearChatHistoryInput, ClearChatHistoryOutput,
    GetHelpInput, GetHelpOutput
)
from backend.routes.agent_routes import *

def register_map_tools(mcp: FastMCP):
    """Register map and display tools with schemas"""
    
    @mcp.tool()
    async def clear_map(input: ClearMapInput) -> ClearMapOutput:
        """
        Clear all routes and reset vehicles.
        Removes all routes from map and returns vehicles to warehouses.
        """

        print("input......", input)
        
        result = await clear_all_routes_function(input.user_id)
        print(f"==>> result:  {result}")
        
        return ClearMapOutput(
            message=result.get("message", "Map cleared"),
            total_routes_deleted=result.get("total_routes_deleted", 0),
            total_multimodal_routes_deleted=result.get("total_multimodal_routes_deleted", 0),
            total_nodes_deleted=result.get("total_nodes_deleted", 0),
            total_nodes_air_deleted=result.get("total_nodes_air_deleted", 0),
            total_vehicles_reset=result.get("total_vehicles_reset", 0),
        )
    
    @mcp.tool()
    async def satellite_view(input: SatelliteViewInput) -> SatelliteViewOutput:
        """
        Activate satellite map view. Switches map to satellite imagery.
        """
        return SatelliteViewOutput(
            message="Satellite view activated",
            action="satellite_view"
        )
    
    @mcp.tool()
    async def street_view(input: StreetViewInput) -> StreetViewOutput:
        """
        Activate street map view. Switches map to street-level view.
        """
        return StreetViewOutput(
            message="Street view activated",
            action="street_view"
        )
    
    @mcp.tool()
    async def clear_chat(input: ClearChatHistoryInput) -> ClearChatHistoryOutput:
        """
        Clear chat conversation history. Removes all previous chat messages.
        Does not affect routes or vehicles.
        """
        user_id = input.user_id

        await delete_data(user_id)
        
        return ClearChatHistoryOutput(
            message="Chat history cleared",
            action="clear_chat"
        )
    
    @mcp.tool()
    async def help(input: GetHelpInput) -> GetHelpOutput:
        """
        Get help information about available features. Use when user asks for help or instructions.
        """
        help_text = (
            "I'm your logistics assistant. You can:"
            "Route Planning:"
            "• Plan road routes between warehouses (plan_route)"
            "• Plan multimodal routes with air segments (plan_multimodal_route)"
            "• Get alternative routes for disruptions (get_alternative_route)"
            "Vehicle Management:"
            "• Assign vehicles to routes (assign_vehicle)"
            "• Reset vehicles to warehouses (reset_vehicle)"
            "System Control:"
            "• Clear all routes (clear_map)"
            "• Activate/deactivate warehouses (update_warehouse_status)"
            "• Switch map views (satellite_view, street_view)"
            "• Clear chat history (clear_chat_history)"
            "💡 Tip: Always mention warehouse names from your uploaded CSV!"
        )
        
        return GetHelpOutput(
            message=help_text
        )