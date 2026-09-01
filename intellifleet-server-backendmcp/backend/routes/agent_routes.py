# ==============================================
# MCP + LANGGRAPH INTEGRATION
# ==============================================
import logging
from langchain_core.messages import HumanMessage, AIMessage
from fastapi.responses import JSONResponse
from fastapi import Depends, HTTPException, APIRouter
from ..routes.auth import get_current_user
from pydantic import BaseModel

from ..models.agentSchema import *
from ..config.logger import logger
from ..database.database import *
from fastapi import Depends, HTTPException
from backend.routes.auth import get_current_user
# from backend.routes.api import get_chat_memory
from backend.config.redis import get_data, delete_data

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat Service"])

@router.get("/chat/history")
async def get_chat_history(current_user = Depends(get_current_user)):
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

        history = await get_data(user_id) or []
        # print(f"==>> history:  {history}")

        return {
            "success": True, 
            "status_code": 200, 
            "message": "User's chat history", 
            "data": history
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error getting chat history: {e}", exc_info=True)
        return {
            "success": False, 
            "status_code": 500, 
            "message": "Unable to fetch history"
        }

@router.delete("/chat/history")
async def clear_chat_history_function(current_user = Depends(get_current_user)):
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
        
        await delete_data(user_id)

        return {
            "success": True, 
            "status_code": 200, 
            "message": "User's chat history deleted"
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error clearing chat history: {e}", exc_info=True)
        return {
            "success": False, 
            "status_code": 500, 
            "message": "Unable to delete history"
        }
        
        
# async def clear_chat_history_for_user(user_id: int):
#     await redis_delete_data(user_id)
#     return True