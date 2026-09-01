from pydantic import BaseModel
from typing import Dict, Optional, Any

class ChatSchema(BaseModel):
    user_id: str
    message: str

class ChatPrompt(BaseModel):
    prompt: str

class RouteQueryRequest(BaseModel):
    question: str