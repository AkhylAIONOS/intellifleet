from pydantic import BaseModel, Field

class ClearMapInput(BaseModel):
    """Input schema for clearing map"""
    user_id: int = Field(..., description="User identifier")

class ClearMapOutput(BaseModel):
    """Output schema for clearing map"""
    message: str = Field(..., description="Status message")
    total_routes_deleted: int = Field(..., description="Number of road routes cleared")
    total_multimodal_routes_deleted: int = Field(..., description="Number of air routes cleared")
    total_nodes_deleted: int = Field(..., description="Number of road routes edges cleared")
    total_nodes_air_deleted: int = Field(..., description="Number of air routes edges cleared")
    total_vehicles_reset: int = Field(..., description="Number of vehicles reset")

class SatelliteViewInput(BaseModel):
    """Input schema for satellite view"""
    user_id: int = Field(..., description="User identifier")

class SatelliteViewOutput(BaseModel):
    """Output schema for satellite view"""
    message: str = Field(..., description="Status message")
    action: str = Field(default="satellite_view", description="Action type")

class StreetViewInput(BaseModel):
    """Input schema for street view"""
    user_id: int = Field(..., description="User identifier")

class StreetViewOutput(BaseModel):
    """Output schema for street view"""
    message: str = Field(..., description="Status message")
    action: str = Field(default="street_view", description="Action type")

class ClearChatHistoryInput(BaseModel):
    """Input schema for clearing chat history"""
    user_id: int = Field(..., description="User identifier")

class ClearChatHistoryOutput(BaseModel):
    """Output schema for clearing chat history"""
    message: str = Field(..., description="Status message")
    action: str = Field(default="clear_chat", description="Action type")

class GetHelpInput(BaseModel):
    """Input schema for getting help"""
    user_id: int = Field(..., description="User identifier")

class GetHelpOutput(BaseModel):
    """Output schema for help"""
    message: str = Field(..., description="Help text")