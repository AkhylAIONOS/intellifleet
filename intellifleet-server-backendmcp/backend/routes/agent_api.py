# backend/routes/agent_api.py
"""
FastAPI endpoint for the LangGraph-powered logistics agent.
This replaces the old agentChat.py file.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from backend.routes.auth import get_current_user
from backend.agent.graph import run_agent
import logging
logger = logging.getLogger(__name__)

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    
@router.get("/agent/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "logistics-agent"}

@router.get("/agent/tools")
async def list_available_tools(current_user = Depends(get_current_user)):
    """
    Lists all available tools/intents.
    Useful for debugging and documentation.
    """
    
    from backend.agent.nodes import TOOL_MAP
    
    tools = {}
    for intent, tool_class in TOOL_MAP.items():
        temp_tool = tool_class(user_id=0)
        tools[intent] = {
            "name": temp_tool.name,
            "description": temp_tool.description
        }
    
    return {
        "total_tools": len(tools),
        "tools": tools
    }

@router.post("/mcp-agent")
async def agent_chat_endpoint(
    req: ChatRequest
    # current_user = Depends(get_current_user)
):
    """
    Main chat endpoint for the logistics agent.
    
    Uses LangGraph workflow to:
    1. Load user context
    2. Classify intent
    3. Execute appropriate tool
    4. Format and return respons
    """
    print("Agent api called ..........")
    # user_id = current_user.get("user_id")
    user_id = 1 
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: user_id not found")
    
    logger.info(f"Chat request from user {user_id}: {req.message}")
    
    try:
        # Run the agent graph
        result = await run_agent(user_id=user_id, message=req.message)
        
        return result
        
    except Exception as e:
        logger.error(f"Agent execution failed for user {user_id}: {e}", exc_info=True)
        return {
            "success": False,
            "response": "Sorry, something went wrong processing your request.",
            "actions": []
        }