from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any

class AssignVehicleInput(BaseModel):
    """Input schema for vehicle assignment"""
    user_id: int = Field(..., description="User identifier")

    # ── Route identification — provide EITHER route_id OR source+destination ──
    route_id: Optional[int] = Field(
        None,
        description="Route ID to assign vehicle to (optional if source+destination given)"
    )
    source: Optional[str] = Field(
        None,
        description="Origin city/warehouse (e.g. 'Delhi'). Required if route_id not provided."
    )
    destination: Optional[str] = Field(
        None,
        description="Destination city/warehouse (e.g. 'Mumbai'). Required if route_id not provided."
    )

    # ── Cargo & vehicle preferences ───────────────────────────────────────────
    capacity: int = Field(
        ...,
        ge=1,
        description="Required cargo capacity in kg (e.g. 1000 for '1000kg of goods')"
    )
    objective: str = Field(
        default="cost",
        description="Optimisation objective: 'cost', 'duration', or 'distance'"
    )
    vehicle_types: List[str] = Field(
        default_factory=list,
        description="Preferred vehicle types: truck, plane, ship, bike, car, auto. Leave empty for auto-select."
    )
    vehicle_id: Optional[int] = Field(
        None,
        description="Pin a specific vehicle by ID (optional)"
    )

    @model_validator(mode="after")
    def check_route_or_locations(self) -> "AssignVehicleInput":
        has_route    = self.route_id is not None
        has_locations = self.source and self.destination
        if not has_route and not has_locations:
            raise ValueError(
                "Provide either 'route_id' OR both 'source' and 'destination'."
            )
        return self


class AssignVehicleOutput(BaseModel):
    """Output schema for vehicle assignment"""

    # ── Legacy single-vehicle summary (first vehicle of first segment) ────────
    vehicle_id: int = Field(..., description="First assigned vehicle ID")
    vehicle_label: str = Field(..., description="First assigned vehicle label")
    route_id: Optional[int] = Field(None, description="Route ID (None if resolved from source/dest)")
    capacity: int = Field(..., description="Requested capacity in kg")
    departure_time: str = Field(..., description="Overall departure time")
    arrival_time: str = Field(..., description="Final arrival time")
    message: str = Field(..., description="Status message")
    data: Dict[str, Any] = Field(default_factory=dict, description="Raw assignment data")

    # ── Partial-assignment fields (multi-segment support) ─────────────────────
    success: bool = Field(default=True, description="Whether assignment succeeded")
    session_id: Optional[str] = Field(
        None,
        description="Redis session ID for multi-segment fetching (None for single segment)"
    )
    response_text: Optional[str] = Field(
        None,
        description="Pre-built human-readable summary from the solver"
    )
    actions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Structured action list for the frontend: "
            "['partial_assignment_start', 'animate_segment', ...]"
        )
    )

class ResetVehicleInput(BaseModel):
    """Input schema for resetting a vehicle"""
    user_id: int = Field(..., description="User identifier")
    vehicle_id: int = Field(..., ge=1, description="Vehicle ID to reset")
    route_id: Optional[str] = Field(None, description="Associated route ID (optional)")

class ResetVehicleOutput(BaseModel):
    """Output schema for vehicle reset"""
    vehicle_id: int = Field(..., description="Reset vehicle ID")
    message: str = Field(..., description="Status message")

class ResetAllVehiclesInput(BaseModel):
    """Input schema for resetting all vehicles"""
    user_id: int = Field(..., description="User identifier")

class ResetAllVehiclesOutput(BaseModel):
    """Output schema for resetting all vehicles"""
    vehicles_reset: List[int] = Field(..., description="List of reset vehicle IDs")
    message: str = Field(..., description="Status message")

class UpdateVehicleStatusInput(BaseModel):
    """Input schema for updating vehicle status"""
    user_id: int = Field(..., description="User identifier")
    vehicle_id: int = Field(..., ge=1, description="Vehicle ID")
    is_active: bool = Field(..., description="New status (True=active, False=inactive)")

class UpdateVehicleStatusOutput(BaseModel):
    """Output schema for vehicle status update"""
    vehicle_id: int = Field(..., description="Updated vehicle ID")
    is_active: bool = Field(..., description="New active status")
    message: str = Field(..., description="Status message")

# class AssignMultimodalVehicleInput(BaseModel):
#     """Input schema for assigning vehicles to multimodal route"""
#     user_id: int = Field(..., description="User identifier")
#     route_id: str = Field(..., description="Multimodal route ID")

# class AssignMultimodalVehicleOutput(BaseModel):
#     """Output schema for multimodal vehicle assignment"""
#     route_id: str = Field(..., description="Multimodal route ID")
#     segment_1_vehicle: Optional[int] = Field(None, description="Vehicle ID for segment 1 (road)")
#     segment_2_vehicle: Optional[int] = Field(None, description="Vehicle ID for segment 2 (air)")
#     segment_3_vehicle: Optional[int] = Field(None, description="Vehicle ID for segment 3 (road)")
#     message: str = Field(..., description="Status message")
#     success: bool = Field(..., description="Assignment success status")

# class AssignPlaneInput(BaseModel):
#     """Input schema for assigning plane to multimodal route"""
#     user_id: int = Field(..., description="User identifier")
#     route_id: str = Field(..., description="Multimodal route ID")

# class AssignPlaneOutput(BaseModel):
#     """Output schema for plane assignment"""
#     route_id: str = Field(..., description="Multimodal route ID")
#     plane_id: int = Field(..., description="Assigned plane ID")
#     segment: str = Field(..., description="Segment where plane is assigned (segment_2)")
#     message: str = Field(..., description="Status message")
#     success: bool = Field(..., description="Assignment success status")