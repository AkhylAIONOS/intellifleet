import asyncio
from fastapi import HTTPException, APIRouter, Depends
from pydantic import BaseModel
from ...database.database import get_vehicle_by_id, reactivate_vehicle, deactivate_vehicle, update_vehicle
from ...config.logger import logger
from ..auth import get_current_user

class VehicleStatusUpdateRequest(BaseModel):
    vehicle_id: int
    is_active: bool

router = APIRouter()

# async def set_vehicle_active_status(user_id: int, vehicle_id: int, is_active: bool):
#     """
#     Activate or deactivate a Vehicle using ONLY Vehicle name
#     """

#     if not vehicle_id:
#         return {"message": "Vehicle ID is required."}


#     try:
#         loop = asyncio.get_running_loop()

#         wh = await loop.run_in_executor(
#             None,
#             get_vehicle_by_id,
#             vehicle_id,
#             user_id
#         )

#         print(f"==>> wh:  {wh}")

#         if not wh:
#             return {"message": f"Vehicle '{vehicle_id}' not found."}


#         if is_active:
#             await loop.run_in_executor(
#                 None,
#                 reactivate_vehicle,
#                 user_id,
#                 vehicle_id
#             )
#             message = f"Vehicle '{vehicle_id}' activated successfully."
#         else:
#             await loop.run_in_executor(
#                 None,
#                 deactivate_vehicle,
#                 user_id,
#                 vehicle_id
#             )
#             message = f"Vehicle '{vehicle_id}' deactivated successfully."

#         logger.info(message)
        
#         data = {
#             "vehicle_id": vehicle_id,
#             "is_active": is_active
#         }
        
#         return {
#             "message": message,
#             "data": data
#         }

#     except Exception as e:
#         logger.error(f"Failed to update Vehicle '{vehicle_id}': {e}")
#         return {
#             "message": "Vehicle not updated. Please try again!"
#         }
    


async def set_vehicle_active_status(user_id: int, vehicle_id: int, is_active: bool):
    """
    Activate or deactivate a Vehicle and update DB fields:
    - is_available
    - status
    - assigned_route (cleared when activated)
    """

    if not vehicle_id:
        return {"message": "Vehicle ID is required."}

    try:
        loop = asyncio.get_running_loop()

        # Fetch vehicle first
        wh = await loop.run_in_executor(
            None,
            get_vehicle_by_id,
            vehicle_id,
            user_id
        )

        if not wh:
            return {"message": f"Vehicle '{vehicle_id}' not found."}

        # Prepare update_data exactly like your pattern
        if is_active:
            update_data = {
                "is_available": True,
                "assigned_route": [],       # clear routes
                "status": "available"
            }
        else:
            update_data = {
                "is_available": False,
                "status": "disrupted"
            }

        # Apply DB update using your style
        update_success = await loop.run_in_executor(
            None,
            update_vehicle,
            vehicle_id,
            user_id,
            update_data
        )

        if not update_success:
            return {"message": "Vehicle DB update failed."}

        # Still call old activate/deactivate functions
        if is_active:
            await loop.run_in_executor(None, reactivate_vehicle, user_id, vehicle_id)
            message = f"Vehicle '{vehicle_id}' activated successfully."
        else:
            await loop.run_in_executor(None, deactivate_vehicle, user_id, vehicle_id)
            message = f"Vehicle '{vehicle_id}' deactivated successfully."

        logger.info(message)

        return {
            "message": message,
            "data": {
                "vehicle_id": vehicle_id,
                "is_active": is_active
            }
        }

    except Exception as e:
        logger.error(f"Failed to update Vehicle '{vehicle_id}': {e}")
        return {"message": "Vehicle not updated. Please try again!"}



# @router.post("/vehicle-status")
# async def update_warehouse_status(payload: VehicleStatusUpdateRequest, current_user = Depends(get_current_user)):


#     user_id = current_user.get("user_id")
    
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}

#     result = await set_vehicle_active_status(
#         user_id=user_id,
#         vehicle_id=payload.vehicle_id,
#         is_active=payload.is_active
#     )

#     return result