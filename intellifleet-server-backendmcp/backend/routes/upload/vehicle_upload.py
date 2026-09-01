# routes/vehicle_upload.py

import pandas as pd
import io
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from backend.database.database import get_warehouse_by_name, create_vehicle
from backend.config.logger import logger
from ..auth import get_current_user
from ...utilities.vehicleConstants import *

router = APIRouter()


def read_vehicle_csv(file: UploadFile):
    if not file.filename.endswith(".csv"):
        return {"success": False, "status_code": 500, "message": "File must be CSV"}
        

    content = file.file.read()
    df = pd.read_csv(io.StringIO(content.decode("utf-8")))
    df.columns = [c.strip() for c in df.columns]
    return df


def validate_vehicle_columns(df):
    required = ["WarehouseName", "VehicleType", "VehicleCapacity", "DepartureTime"]
    for col in required:
        if col not in df.columns:
            return {"success": False, "status_code": 500, "message": f"Missing column: {col}"}
           
    return df


async def upload_vehicles_function(user_id: int, file: UploadFile = File(...)):

    try:
        df = validate_vehicle_columns(read_vehicle_csv(file))
        
        inserted = 0
        missing_warehouses = []

        for _, row in df.iterrows():

            warehouse_name = str(row["WarehouseName"]).strip()
            vehicle_type = str(row["VehicleType"]).strip()
            vehicle_capacity = int(str(row["VehicleCapacity"]).strip())
            departure_time = str(row["DepartureTime"]).strip()

            vehicle_details = VEHICLE_TYPES.get(vehicle_type.lower())

            wh = get_warehouse_by_name(user_id, warehouse_name)

            if not wh:
                missing_warehouses.append(warehouse_name)
                continue

            vehicle_label = f"{row['VehicleType']}_{inserted + 1}"

            vehicle = {
                "warehouse_id": wh["warehouse_id"],
                "type": vehicle_type,
                "capacity": vehicle_capacity,
                "schedule_departure_time": departure_time,
                "departure_time": departure_time,
                "current_location": warehouse_name,
                "current_position": {
                    "lat": wh["latitude"],
                    "lng": wh["longitude"]
                },
                "is_available": True,
                "status": "available",
                "assigned_route": None,
                "label": vehicle_label,
                "vehicle_details": vehicle_details
            }

            create_vehicle(user_id, vehicle)
            inserted += 1

        return {
            "success": True,
            "message": f"Your vehicles file has been uploaded with {inserted} vehicles.",
            "missing_warehouses": list(set(missing_warehouses))
        }

    except Exception as e:
        logger.error(f"Vehicle upload error: {e}")
        return {
            "success": False,
            "message": "Vehicles not uploaded. Please try again!"
        }


# ======================================================= API ======================================================

# @router.post("/upload_vehicles")
# async def upload_vehicles(current_user = Depends(get_current_user), file: UploadFile = File(...)):
    
#     user_id = current_user.get("user_id")
        
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
        
    
#     result = await upload_vehicles_function(user_id, file)
#     return result