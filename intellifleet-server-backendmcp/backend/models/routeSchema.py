from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Union


class GoogleRouteRequest(BaseModel):
    source: str
    destination: str
    intermediate_locations: Optional[List[str]] = None
    objective: Optional[str] = "duration"

class MultiRouteRequest(BaseModel):
    source: str
    destination: str
    intermediate_locations: List[str] = Field(default_factory=list)
    waypoints: Optional[List[str]] = None

class AlternativeRouteRequest(BaseModel):
    route_id: Union[str, int]
    reason: str
    source: Optional[str] = None
    destination: Optional[str] = None
    intermediate_locations: Optional[List[str]] = []


class PlanetRouteRequest(BaseModel):
    source: str
    destination: str
    nearest_airport_source: str
    nearest_airport_destination: str

class RemoveRouteRequest(BaseModel):
    route_id: Optional[int] = None
    source: Optional[str] = None
    destination: Optional[str] = None
    intermediate_locations: Optional[List[str]] = None

class RouteSummaryRequest(BaseModel):
    source: Optional[str] = None
    destination: Optional[str] = None
    intermediate_locations: Optional[List[str]] = None
    route_id: Optional[int] = None