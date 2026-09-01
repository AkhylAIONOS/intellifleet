from pydantic import BaseModel, Field
from typing import Optional, List, Any

# class DisruptionInput(BaseModel):
#     """Input schema for disruption management operations"""

#     user_id: int = Field(..., description="User identifier")

#     operation: str = Field(
#         ...,
#         description="Operation type: 'handle_disruption', 'find_warehouses', or 'estimate_delivery'"
#     )

#     # ── handle_disruption ────────────────────────────────────────────────────
#     source_warehouse: Optional[str] = Field(None, description="Source warehouse name")
#     destination_city: Optional[str] = Field(None, description="Destination city")
#     demand_kg: Optional[float] = Field(None, description="Demand weight in kg")
#     repair_hours: Optional[int] = Field(None, description="Repair duration in hours")
#     disruption_location: Optional[str] = Field(None, description="Location of disruption")

#     # ── find_warehouses ──────────────────────────────────────────────────────
#     origin_lat: Optional[float] = Field(None, description="Origin latitude")
#     origin_lon: Optional[float] = Field(None, description="Origin longitude")
#     demand_weight: Optional[int] = Field(None, description="Required demand weight in kg")
#     exclude_cities: Optional[List[str]] = Field(None, description="Cities to exclude")
#     max_results: Optional[int] = Field(None, description="Max warehouses to return")

#     # ── estimate_delivery ────────────────────────────────────────────────────
#     source_city: Optional[str] = Field(None, description="Source city")
#     repair_duration_hours: Optional[int] = Field(None, description="Repair duration in hours")

#     # ── shared ───────────────────────────────────────────────────────────────
#     disruption_time: Optional[str] = Field(None, description="Disruption time (HH:MM)")
#     required_delivery_time: Optional[str] = Field(None, description="Required delivery time (HH:MM)")

from pydantic import BaseModel, Field
from typing import Optional, Union

# class DisruptionInput(BaseModel):
#     """
#     Minimal unified schema used ONLY for manage_disruption().
#     Includes only the fields actually required by the logic.
#     """
#     user_id: int = Field(..., description="User identifier")
#     # route selection
#     route_type: str = Field(..., description="Route type: 'air' or 'road'")

#     # common fields
#     source_warehouse: Optional[str] = Field(..., description="Source name")
#     destination_city: Optional[str] = Field(..., description="Destination name")
#     demand_kg: Optional[float] = Field(..., description="Demand weight in kg")
#     disruption_time: str = Field(..., description="Time of disruption")
#     required_delivery_time: str = Field(..., description="Delivery deadline")

#     # road-specific
#     repair_hours: Optional[Union[str, int]] = Field(
#         None, description="Repair duration for road disruptions"
#     )
#     disruption_location: Optional[str] = Field(
#         None, description="Disruption location"
#     )

#     # air-specific
#     flight_delay_minutes: Optional[Union[str, int]] = Field(
#         None, description="Flight delay for air disruptions"
#     )

class DisruptionInput(BaseModel):
    user_id: int = Field(..., description="User identifier")
    route_type: str = Field(..., description="Route type: 'air' or 'road'")

    source_warehouse: Optional[str] = Field(None, description="Source warehouse or airport name")
    destination_city: Optional[str] = Field(None, description="Destination city or airport name")
    demand_kg: Optional[float] = Field(None, description="Demand weight in kg")
    disruption_time: str = Field(..., description="Time of disruption, e.g. '7am', 'today 7am'")
    required_delivery_time: str = Field(..., description="Delivery deadline, e.g. '8pm', 'today 8pm'")

    # road-specific — only populate when route_type='road'
    repair_hours: Optional[Union[str, int]] = Field(
        None,
        description="[ROAD ONLY] Repair duration, e.g. 4 or '4 hours'. Leave None for air."
    )
    disruption_location: Optional[str] = Field(
        None,
        description="[ROAD ONLY] Location of the disruption, e.g. 'near Indore'."
    )

    # air-specific — only populate when route_type='air'
    flight_delay_minutes: Optional[Union[str, int]] = Field(
        None,
        description="[AIR ONLY] Flight delay in minutes or string e.g. 240 or '4 hours'. Leave None for road."
    )

# ── Output Schema ────────────────────────────────────────────────────────────

class DisruptionOutput(BaseModel):
    """Output schema for disruption operations"""

    message: str = Field(..., description="Status message")
    data: Optional[Any] = Field(None, description="Result data")