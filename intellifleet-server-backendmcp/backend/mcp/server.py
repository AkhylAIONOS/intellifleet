#backend/mcp/server.py
from fastmcp import FastMCP

mcp = FastMCP("logistics-mcp")

def register_all_tools(mcp_instance: FastMCP):
    from backend.mcp.tools.route_tools import register_route_tools
    from backend.mcp.tools.vehicle_tools import register_vehicle_tools
    from backend.mcp.tools.multimodal_tools import register_multimodal_tools
    from backend.mcp.tools.warehouse_tools import register_warehouse_tools
    from backend.mcp.tools.map_tools import register_map_tools
    from backend.mcp.tools.disruption_tool import register_disruption_tools

    register_route_tools(mcp_instance)
    register_vehicle_tools(mcp_instance)
    register_multimodal_tools(mcp_instance)
    register_warehouse_tools(mcp_instance)
    register_map_tools(mcp_instance)
    register_disruption_tools(mcp_instance)


register_all_tools(mcp)


# if __name__ == "__main__":
#     # Optional HTTP mode (for future scaling)
#     mcp.run(transport="http", port=8001)


