# Export all schemas
from .route_schemas import *
from .vehicle_schemas import *
from .multimodal_schemas import *
from .warehouse_schemas import *
from .map_schemas import *

__all__ = [
    # Route schemas
    "PlanRouteInput", "PlanRouteOutput",
    "AlternativeRouteInput", "AlternativeRouteOutput",
    "RemoveRouteInput", "RemoveRouteOutput",
    "FetchRoutesInput", "FetchRoutesOutput",
    
    # Vehicle schemas
    "AssignVehicleInput", "AssignVehicleOutput",
    "ResetVehicleInput", "ResetVehicleOutput",
    "CompleteVehicleRouteInput", "CompleteVehicleRouteOutput",
    "ResetAllVehiclesInput", "ResetAllVehiclesOutput",
    "UpdateVehicleStatusInput", "UpdateVehicleStatusOutput",
    "AssignMultimodalVehicleInput", "AssignMultimodalVehicleOutput",
    "AssignPlaneInput", "AssignPlaneOutput",
    
    # Multimodal schemas
    "PlanMultimodalRouteInput", "PlanMultimodalRouteOutput",
    "RemoveMultimodalRouteInput", "RemoveMultimodalRouteOutput",
    "ConnectHubInput", "ConnectHubOutput",
    
    # Warehouse schemas
    "UpdateWarehouseStatusInput", "UpdateWarehouseStatusOutput",
    
    # Map schemas
    "ClearMapInput", "ClearMapOutput",
    "SatelliteViewInput", "SatelliteViewOutput",
    "StreetViewInput", "StreetViewOutput",
    
    # Chat schemas
    "ClearChatHistoryInput", "ClearChatHistoryOutput",
    "GetHelpInput", "GetHelpOutput",
]