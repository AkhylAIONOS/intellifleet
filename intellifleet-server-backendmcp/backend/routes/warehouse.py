import asyncio
from fastapi import HTTPException, APIRouter, Depends
from pydantic import BaseModel
from ..database.database import delete_warehouse, reactivate_warehouse, get_warehouse_by_name
from ..config.logger import logger
from ..routes.auth import get_current_user

class WarehouseStatusUpdateRequest(BaseModel):
    warehouse_name: str
    is_active: bool


router = APIRouter()


async def set_warehouse_active_status(user_id: int, warehouse_name: str, is_active: bool):
    """
    Activate or deactivate a warehouse using ONLY warehouse name
    """

    if not warehouse_name:
        return {"message": "Warehouse name is required."}


    try:
        loop = asyncio.get_running_loop()

        wh = await loop.run_in_executor(
            None,
            get_warehouse_by_name,
            user_id,
            warehouse_name
        )

        if not wh:
            return {"message": f"Warehouse '{warehouse_name}' not found."}


        warehouse_id = wh["warehouse_id"]

        if is_active:
            await loop.run_in_executor(
                None,
                reactivate_warehouse,
                user_id,
                warehouse_id
            )
            message = f"Warehouse '{warehouse_name}' reactivated successfully."
        else:
            await loop.run_in_executor(
                None,
                delete_warehouse,
                user_id,
                warehouse_id
            )
            message = f"Warehouse '{warehouse_name}' deactivated successfully."

        logger.info(message)
        
        data = {
            "warehouse_name": warehouse_name,
            "warehouse_id": warehouse_id,
            "is_active": is_active
        }
        
        return {
            "success": True,
            "message": message,
            "data": data
        }

    except Exception as e:
        logger.error(f"Failed to update warehouse '{warehouse_name}': {e}")
        return {
            "message": "Warehouse not updated. Please try again!"
        }


# ======================================================= API ======================================================


# @router.post("/warehouse_status")
# async def update_warehouse_status(payload: WarehouseStatusUpdateRequest, current_user = Depends(get_current_user)):


#     user_id = current_user.get("user_id")
    
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
        

#     result = await set_warehouse_active_status(
#         user_id=user_id,
#         warehouse_name=payload.warehouse_name,
#         is_active=payload.is_active
#     )

#     return result