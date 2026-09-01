from pydantic import BaseModel
from typing import Any, Dict, List, Optional

class AvailableVehiclesRequest(BaseModel):
    location: str

class VehicleAssignmentRequest(BaseModel):
    route_id: int
    vehicle_id: int
    vehicle_type: str
    capacity: int

class VehicleCompleteRequest(BaseModel):
    route_id: int
    vehicle_id: int
    destination: str

class ResetSingleVehicleRequest(BaseModel):
    route_id: Optional[int] = None
    vehicle_id: int

class MultipleVehicleAssignmentRequest(BaseModel):
    route_id: int
    assignments: List[Dict[str, Any]]

class ResetAllVehiclesRequest(BaseModel):
    route_id: int
