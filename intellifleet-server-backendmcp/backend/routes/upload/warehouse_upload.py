# routes/warehouse_upload.py

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
import pandas as pd
import io
from backend.utilities.geocode import geocode_address
from backend.utilities.airportHelper import fetch_nearest_airport
from backend.config.logger import logger
from ..auth import get_current_user
from backend.database.database import (
    create_warehouse, save_nearest_airport
)

router = APIRouter()


def read_csv(file: UploadFile):
    if not file.filename.endswith(".csv"):
        return {"success": False, "status_code": 500, "message": "File must be CSV"}
        

    content = file.file.read()
    df = pd.read_csv(io.StringIO(content.decode("utf-8")))
    df.columns = [c.strip() for c in df.columns]
    return df


def validate_warehouse_columns(df):
    required = ["Name", "Address", "Country", "City", "NodeType"]
    inventory_cols = ["Inventory", "ReorderLevel"]
    for col in required + inventory_cols:
        if col not in df.columns:
            return {"success": False, "status_code": 500, "message": f"Missing column: {col}"}
            
    return df


def extract_warehouse_row(row, idx):
    return {
        "name": str(row["Name"]).strip() or f"Unknown_{idx}",
        "address": str(row["Address"]).strip(),
        "country": str(row["Country"]).strip(),
        "city": str(row["City"]).strip(),
        "node_type": str(row["NodeType"]).strip(),
        "inventory": int(row["Inventory"]) if pd.notna(row["Inventory"]) else 0,
        "reorder_level": int(row["ReorderLevel"]) if pd.notna(row["ReorderLevel"]) else 0
    }

async def upload_warehouses_function(user_id: int, file: UploadFile = File(...)):

    try:

        df = validate_warehouse_columns(read_csv(file))
        processed = []
        failed_geo = []

        for idx, row in df.iterrows():
            wh = extract_warehouse_row(row, idx)

            lat, lng = geocode_address(wh["address"])
            if not lat or not lng:
                failed_geo.append(wh["name"])
                wh["latitude"] = None
                wh["longitude"] = None
            else:
                wh["latitude"] = lat
                wh["longitude"] = lng

            # Save warehouse
            wid = create_warehouse(user_id, wh)
            wh["id"] = wid

            # Find nearest airport
            try:
                airport = fetch_nearest_airport(lat, lng)
                wh["nearest_airport"] = airport
                if airport:
                    save_nearest_airport(user_id, wid, wh["name"], airport)
            except:
                wh["nearest_airport"] = None

            processed.append(wh)

        return {
            "success": True,
            "message": f"Your warehouse file has been uploaded with {len(processed)} warehouses.",
            "data": processed,
            "total_warehouses": len(processed),
            "failed_geocoding": failed_geo
        }

    except Exception as e:
        logger.error(f"Warehouse upload error: {e}")
        return {
            "success": False,
            "status_code": 500,
            "message": "Warehouse not uploaded. Please try again!"
        }
    


# ======================================================= API ======================================================

# @router.post("/upload_warehouses")
# async def upload_warehouses(current_user = Depends(get_current_user), file: UploadFile = File(...)):

#     user_id = current_user.get("user_id")
        
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
        
#     result = upload_warehouses_function(user_id, file)
#     return result
