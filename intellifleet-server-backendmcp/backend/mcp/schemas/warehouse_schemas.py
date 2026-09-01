from pydantic import BaseModel, Field

class UpdateWarehouseStatusInput(BaseModel):
    """Input schema for updating warehouse status"""
    user_id: int = Field(..., description="User identifier")
    warehouse_name: str = Field(..., description="Warehouse name")
    is_active: bool = Field(..., description="New status (True=active, False=inactive)")

class UpdateWarehouseStatusOutput(BaseModel):
    """Output schema for warehouse status update"""
    warehouse_name: str = Field(..., description="Updated warehouse name")
    is_active: bool = Field(..., description="New active status")
    warehouse_id: int = Field(..., description="Warehouse ID")