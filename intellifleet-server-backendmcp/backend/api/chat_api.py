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
    
    
    input_message = req.message
    logger.info(f'input_message {type(input_message)}: {input_message}')
    print(f"🔄 Processing message for user {user_id}: {req.message}")
    
    # Use enhanced schema-aware supervisor
    result = await supervisor.process_message(user_id, req.message)
    print(f"🔄 Raw agent result:======================================================================")
    print(f"==>> result:  {result}")
    
    
    print(f"✅ Agent result: {result.get('success', False)}")
    
    return {
        "success": result.get("success", True),
        "response": result.get("response", "No response generated"),
        "actions": result.get("actions", [])
    }

