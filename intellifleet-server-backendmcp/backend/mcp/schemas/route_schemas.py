from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# class PlanRouteInput(BaseModel):
#     """Input schema for planning a route"""
#     user_id: int = Field(..., description="User identifier")
#     source: str = Field(..., description="Starting location (warehouse name)")
#     destination: str = Field(..., description="Ending location (warehouse name)")
#     intermediate_locations: List[str] = Field(
#         default=[],
#         description="Optional intermediate stops (warehouse names)"
#     )

# class PlanRouteOutput(BaseModel):
#     """Output schema for route planning"""
#     route_id: int = Field(..., description="Generated route ID")
#     source: str = Field(..., description="Route source")
#     destination: str = Field(..., description="Route destination")
#     distance: float = Field(..., description="Total distance")
#     duration: float = Field(..., description="Total duration")
#     waypoints: List[str] = Field(..., description="All waypoints in order")
#     message: str = Field(..., description="Status message")
#     data: Dict[str, Any] = Field(default_factory=dict, description="Raw route data")


class PlanRouteInput(BaseModel):
    """Input schema for planning a route"""
    user_id: int = Field(..., description="User identifier")
    source: str = Field(..., description="Starting location (warehouse name)")
    destination: str = Field(..., description="Ending location (warehouse name)")
    intermediate_locations: List[str] = Field(
        default_factory=list,
        description="Optional intermediate stops (warehouse names)"
    )
    objective: Optional[str] = Field(
        default="duration",
        description="Optimization objective: duration, distance, etc."
    )


class PlanRouteOutput(BaseModel):
    route_id: int
    source: str
    destination: str
    distance: float
    duration: float
    waypoints: List[str]
    message: str
    optimal_routes: List[Dict[str, Any]]
    locations: List[str]
    route_cost: float
    source_coords: Dict[str, float]
    dest_coords: Dict[str, float]
    objective: str
    cached: bool

# class AlternativeRouteInput(BaseModel):
#     """Input schema for alternative route request"""
#     user_id: int = Field(..., description="User identifier")
#     route_id: int = Field(..., description="Original route ID")
#     reason: str = Field(
#         default="Alternative route requested",
#         description="Reason for alternative route"
#     )


# class AlternativeRouteOutput(BaseModel):
#     """Output schema for alternative route"""
#     alternative_route_id: Optional[int] = Field(None, description="Alternative route ID")
#     parent_route_id: Optional[int] = Field(None, description="Original route ID")
#     distance: Optional[float] = Field(None, description="Distance of alternative route")
#     duration: Optional[float] = Field(None, description="Duration of alternative route")
#     reason: str = Field(..., description="Reason for alternative")
#     message: str = Field(..., description="Status message")
#     data: Dict[str, Any] = Field(default_factory=dict, description="Route data")

class AlternativeRouteInput(BaseModel):
    user_id: int = Field(..., description="User identifier")
    route_id: int = Field(..., description="Original route ID")
    reason: str = Field(
        default="Alternative route requested",
        description="Reason for alternative route"
    )


class AlternativeRouteOutput(BaseModel):
    success: bool = Field(..., description="Whether the tool execution succeeded")
    message: str = Field(..., description="Status message for logging")
    route_id: Optional[int] = Field(None, description="Alternative route ID")
    parent_route_id: Optional[int] = Field(None, description="Original route ID")
    alternative_route: Dict[str, Any] = Field(default_factory=dict)
    distance: Optional[float] = Field(None, description="Distance of alternative route")
    duration: Optional[float] = Field(None, description="Duration of alternative route")
    fuel_needed: Optional[float] = Field(None, description="Fuel needed")
    route_cost: Optional[float] = Field(None, description="Route cost")
    source: Optional[str] = Field(None, description="Source location")
    destination: Optional[str] = Field(None, description="Destination location")
    waypoints: List[str] = Field(default_factory=list, description="Waypoints")
    is_alternative: bool = Field(True, description="Flag marking this as alternative route")
    
class RemoveRouteInput(BaseModel):
    """Input schema for removing a route"""
    user_id: int = Field(..., description="User identifier")
    route_id: Optional[int] = Field(None, description="Route ID to remove")
    source: Optional[str] = Field(None, description="Route source (if route_id not provided)")
    destination: Optional[str] = Field(None, description="Route destination (if route_id not provided)")
    intermediate_locations: Optional[List[str]] = Field(
        default=[],
        description="Intermediate locations (if route_id not provided)"
    )

class RemoveRouteOutput(BaseModel):
    """Output schema for route removal"""
    route_id: int = Field(..., description="ID of removed road route")
    message: str = Field(..., description="Status message")

class FetchRoutesInput(BaseModel):
    """Input schema for fetching routes"""
    user_id: int = Field(..., description="User identifier")
    query: str = Field(
        default="",
        description="Natural language query about routes"
    )

class FetchRoutesOutput(BaseModel):
    """Output schema for route fetching"""
    answer: str = Field(..., description="Natural language answer about routes")
    message: str = Field(..., description="Status message")
    route_id: int = Field(..., description="ID of the route")
