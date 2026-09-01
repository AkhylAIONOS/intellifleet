from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from enum import Enum

class MessageType(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class ChatMessage(BaseModel):
    type: MessageType
    content: str
    timestamp: Optional[str] = None
    data: Optional[Dict[str, Any]] = None  
    
class ChatSession(BaseModel):
    user_id: int
    messages: List[ChatMessage]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
