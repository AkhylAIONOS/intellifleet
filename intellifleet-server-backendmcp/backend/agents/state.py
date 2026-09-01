#backend/agents/state.py
from typing import TypedDict, Optional, Dict, Any, List, Annotated
from typing_extensions import TypedDict
import operator

class AgentState(TypedDict):
    """State for the LangGraph agent"""
    user_id: int
    user_message: str
    tool_calls: List[dict]
    tool_results: List[dict]
    messages: Annotated[List[dict], operator.add]
    response: Optional[str]
    confidence: float
    intent: Optional[str]
    actions: List[dict]
    success: bool