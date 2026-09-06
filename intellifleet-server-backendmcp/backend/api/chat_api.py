#backend/api/chat_api.py
from unittest import result

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from backend.routes.auth import get_current_user
from backend.agents.supervisor import supervisor  # Using enhanced supervisor
import logging
from fastapi.responses import JSONResponse
from backend.config.redis import *

# Basic configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Create logger
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agent Service"])

class ChatRequest(BaseModel):
    message: str

@router.post("/mcp-agent")
async def agent_chat(
    req: ChatRequest,
    current_user = Depends(get_current_user)
):
    """
    Main chat endpoint using enhanced MCP + LangGraph architecture
    """
    user_id = current_user.get("user_id")
    # user_id = 1
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: user_id not found")

    if supervisor.llm is None:
        raise HTTPException(
            status_code=503,
            detail=supervisor.llm_status.message or "AI chat is unavailable due to incomplete configuration.",
        )
    
    
    input_message = req.message
    logger.info(f'input_message {type(input_message)}: {input_message}')
    
    # Use enhanced schema-aware supervisor
    result = await supervisor.process_message(user_id, req.message)
    logger.info("Agent request completed for user=%s success=%s", user_id, result.get("success", False))
    
    return {
        "success": result.get("success", True),
        "response": result.get("response", "No response generated"),
        "actions": result.get("actions", [])
    }
