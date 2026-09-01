from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class AirRouteRequest(BaseModel):
    source: str
    destination: str
    intermediate_locations: Optional[List[str]] = None
    objective: Optional[str] = "duration"

class RemoveMultimodalRoute(BaseModel):
    route_id: Optional[int] = None
    source: Optional[str] = None
    destination: Optional[str] = None
    multimodal_data: Optional[Dict] = None

class MultimodalRouteInput(BaseModel):
    route_id: int