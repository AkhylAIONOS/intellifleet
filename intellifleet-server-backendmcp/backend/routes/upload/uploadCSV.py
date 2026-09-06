from backend.utilities.geocode import *
from backend.routes.auth import get_current_user
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse
from backend.config.logger import logger
from backend.utilities.airportHelper import *
from .vehicle_upload import *
from .warehouse_upload import *
from .route_upload import upload_routes_function
from ...utilities.vehicleConstants import *
from ...database.database import (
    delete_user_data_vehicle, 
    delete_user_data_warehouse,
    get_warehouses_by_userall,
    get_vehicles_by_user,
    fetch_warehouse_inventory_summary
)
import pandas as pd
import io

router = APIRouter(tags=["Upload CSV"])

@router.post("/upload_csv")
async def upload_csv_unified(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):

    try:
        user_id = current_user.get("user_id")
        
        if not user_id:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": "Invalid token: user_id not found"
                }
            )
        
        # ---------------------------------------------------------
        # READ CSV ONCE
        # ---------------------------------------------------------
        content = await file.read()
        df = pd.read_csv(io.StringIO(content.decode("utf-8")))
        df.columns = [c.strip() for c in df.columns]

        # Detect upload type
        warehouse_cols = {"Name", "Address", "Country"}
        vehicle_cols = {"WarehouseName", "VehicleType", "VehicleCapacity", "DepartureTime"}
        route_cols = {"Source", "Destination", "IntermediateLocation", "RouteType"}

        if warehouse_cols.issubset(df.columns):
            upload_type = "warehouse"
        elif vehicle_cols.issubset(df.columns):
            upload_type = "vehicle"
        elif route_cols.issubset(df.columns):
            upload_type = "route"
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "CSV does not match warehouse, vehicle, or route upload schema."
                }
            )

        # Reset file pointer
        file.file.seek(0)

        # --------------------------------------------------------------------
        # WAREHOUSE UPLOAD
        # --------------------------------------------------------------------
        if upload_type == "warehouse":

            delete_user_data_warehouse(user_id)

            result = await upload_warehouses_function(user_id, file)

            return JSONResponse(
                status_code=200,
                content={
                    "upload_type": "warehouse",
                    **result
                }
            )

        # --------------------------------------------------------------------
        # VEHICLE UPLOAD
        # --------------------------------------------------------------------
        if upload_type == "vehicle":
            
            delete_user_data_vehicle(user_id)

            result = await upload_vehicles_function(user_id, file)

            return JSONResponse(
                status_code=200,
                content={
                    "upload_type": "vehicle",
                    **result
                }
            )

        # --------------------------------------------------------------------
        # ROUTE UPLOAD (ROAD + MULTIMODAL)
        # --------------------------------------------------------------------
        if upload_type == "route":

            result = await upload_routes_function(user_id, file)

            return JSONResponse(
                status_code=200,
                content={
                    "upload_type": "route",
                    **result
                }
            )

    except Exception as e:
        logger.error(f"Unified CSV upload error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "File not uploaded. Please try again!"
            }
        )


@router.get("/warehouses")
def get_warehouses(current_user = Depends(get_current_user)):

    try:
        user_id = current_user.get("user_id")
            
        if not user_id:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": "Invalid token: user_id not found"
                },
            )
        
        warehouses = get_warehouses_by_userall(user_id)
        
        data = {
            "warehouses": warehouses,
            "total_warehouses": len(warehouses)
        }

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Available warehouses",
                "data": data
            },
        )
    
    except Exception as e:
        logger.error(f"Error fetching warehouse: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error"
            },
        )

@router.get("/vehicles")
def get_vehicles(current_user = Depends(get_current_user)):
    """Get all vehicles for current user"""

    try:
        user_id = current_user.get("user_id")
            
        if not user_id:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": "Invalid token: user_id not found"
                },
            )
            
        
        vehicles = get_vehicles_by_user(user_id)

        for vehicle in vehicles:
            vehicle["is_available"] = bool(vehicle.get("is_available"))

        data = {
            "vehicles": vehicles,
            "total_vehicles": len(vehicles)
        }
    
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Available vehicles at warehouses.",
                "data": data
            },
        )
    
    except Exception as e:
        logger.error(f"Error fetching vehicles: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error"
            },
        )


@router.get("/inventory")
def get_warehouse_inventory_summary_api(current_user = Depends(get_current_user)):

    try:
        user_id = current_user.get("user_id")
            
        if not user_id:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": "Invalid token: user_id not found"
                },
            )
            
        
        inventory = fetch_warehouse_inventory_summary(user_id)

        data = {
            "inventory": inventory
        }

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Inventory at Warehouses.",
                "data": data
            },
        )
        

    except Exception as e:
        logger.error(f"Error fetching Inventory: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error"
            },
        )
