from backend.database.database import deactivate_multimodal_route, activate_multimodal_route, multimodal_route_exists
from backend.config.logger import logger
from fastapi import APIRouter, Depends
from ..auth import get_current_user
import asyncio

router = APIRouter()

async def set_multimodal_route_active_status(user_id: int, route_id: int, is_active: bool):
    """
    Activate/deactivate a route by updating the is_active field.
    is_active = True  -> activate
    is_active = False -> deactivate
    """

    try:

        loop = asyncio.get_running_loop()

        exists = await loop.run_in_executor(
            None,
            multimodal_route_exists,
            route_id,
            user_id
        )

        if not exists:
            message = f"Route with route_id {route_id} does not exist."
            logger.warning(message)
            return {"message": message}
        
        if is_active:
            await loop.run_in_executor(
                None,
                activate_multimodal_route,
                route_id,
                user_id
            )
            message = f"Route {route_id} reactivated successfully."
        else:
            await loop.run_in_executor(
                None,
                deactivate_multimodal_route,
                route_id,
                user_id
            )
            message = f"Route {route_id} deactivated successfully."

        logger.info(message)
        
        data = {
            "route_id": route_id,
            "is_active": is_active
        }
        
        return {
            "message": message,
            "data": data
        }

    except Exception as e:
        logger.error(f"Error updating route status: {str(e)}")
        return {
            "message": "Failed to update route status.",
        }

# from pydantic import BaseModel

# class RouteStatusUpdateRequest(BaseModel):
#     route_id: int
#     is_active: bool  # 1 for activate, 0 for deactivate

# @router.post("/route-status")
# async def update_route_status(payload: RouteStatusUpdateRequest, current_user = Depends(get_current_user)):


#     user_id = current_user.get("user_id")
    
#     if not user_id:
#         return {"success": False, "status_code": 401, "message": "Invalid token: user_id not found"}
        

#     result = await set_multimodal_route_active_status(
#         user_id=user_id,
#         route_id=payload.route_id,
#         is_active=payload.is_active
#     )

#     return result