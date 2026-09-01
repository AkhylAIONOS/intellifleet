from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

class PlanMultimodalRouteInput(BaseModel):
    """Input schema for planning multimodal route"""
    user_id: int = Field(..., description="User identifier")
    source: str = Field(..., description="Starting location")
    destination: str = Field(..., description="Ending location")
    intermediate_locations: Optional[List[str]] = Field(
        default_factory=list,
        description="Optional intermediate stops"
    )

    objective: Optional[str] = Field(
        default="duration",
        description="Optimization objective (distance | duration | cost)"
    )

class PlanMultimodalRouteOutput(BaseModel):
    """Output schema for multimodal route planning"""
    status: bool = Field(..., description="Whether route was planned successfully")
    message: str = Field(..., description="Status message")
    data: Dict[str, Any] = Field(default_factory=dict, description="Segment data")
    cached: bool = Field(default=False, description="Whether route was served from cache")
    route_id: int = Field(..., description="Generated multimodal route ID")
    source: str = Field(..., description="Route source")
    destination: str = Field(..., description="Route destination")
    total_distance_km: float = Field(default=0, description="Total distance in km")
    total_duration: float = Field(default=0, description="Total duration in hours")
    total_cost: float = Field(default=0, description="Total cost")
    objective: str = Field(default="duration", description="Optimization objective")

class RemoveMultimodalRouteInput(BaseModel):
    """Input schema for removing multimodal route"""
    user_id: int = Field(..., description="User identifier")
    route_id: Optional[str] = Field(None, description="Route ID to remove")
    source: Optional[str] = Field(None, description="Route source (if route_id not provided)")
    destination: Optional[str] = Field(None, description="Route destination (if route_id not provided)")

class RemoveMultimodalRouteOutput(BaseModel):
    """Output schema for multimodal route removal"""
    route_id: int = Field(..., description="ID of removed multimodal route")
    message: str = Field(..., description="Status message")


class UpdateAirRouteStatusInput(BaseModel):
    """Input schema for updating vehicle status"""
    user_id: int = Field(..., description="User identifier")
    route_id: int = Field(..., ge=1, description="Air/Multimodal Route ID")
    is_active: bool = Field(..., description="New status (True=active, False=inactive)")

class UpdateAirRouteStatusOutput(BaseModel):
    """Output schema for vehicle status update"""
    route_id: int = Field(..., description="Updated Air/Multimodal ID")
    is_active: bool = Field(..., description="New active status")
    message: str = Field(..., description="Status message")