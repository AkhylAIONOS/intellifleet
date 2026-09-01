#backend/mcp/tools/warehouse_tools.py
from fastmcp import FastMCP
from backend.routes.warehouse import set_warehouse_active_status
from backend.mcp.schemas.warehouse_schemas import (
    UpdateWarehouseStatusInput,
    UpdateWarehouseStatusOutput
)

def register_warehouse_tools(mcp: FastMCP):
    """Register warehouse management tools with schemas"""
    
    @mcp.tool()
    async def warehouse_status_update(input: UpdateWarehouseStatusInput) -> UpdateWarehouseStatusOutput:
        """
        Trigger this When user wants to activate or deactivate a warehouse by its name. or say warehouse name is funcitional or non functional etc.
        Only Active warehouses can be used in routes.
        """
        result = await set_warehouse_active_status(
            user_id=input.user_id,
            warehouse_name=input.warehouse_name,
            is_active=input.is_active
        )
        
        # print(f"==>> result:  {result}")

        data = result.get("data", {})
        
        return UpdateWarehouseStatusOutput(
            warehouse_name=input.warehouse_name,
            warehouse_id=data.get("warehouse_id"),
            is_active=input.is_active
        )