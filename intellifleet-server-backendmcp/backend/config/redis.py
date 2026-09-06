import aioredis
import json
from ..database.database import get_persistent_route_by_id, get_multimodal_route_by_id
from fastapi import HTTPException
from ..config.logger import logger
from typing import Any, Dict 
from .config import settings

redis_client = aioredis.from_url(
    settings.REDIS_URL or "redis://localhost:6379/1",
    decode_responses=True,
)

async def user_history_key(user_id: int) -> str:
    key_prefix = "message_store:"
    return key_prefix+ f"user_id:{user_id}:history"

async def add_data(user_id: int, history: list):
    key = await user_history_key(user_id)
    await redis_client.set(key, json.dumps(history))

async def get_data(user_id: int):
    key = await user_history_key(user_id)
    data = await redis_client.get(key)
    return json.loads(data) if data else None

async def delete_data(user_id: int):
    key = await user_history_key(user_id)
    await redis_client.delete(key, f"message_store:user_id:{user_id}:active_planning_context")

async def get_active_planning_context(user_id: int):
    data = await redis_client.get(f"message_store:user_id:{user_id}:active_planning_context")
    return json.loads(data) if data else None

async def set_active_planning_context(user_id: int, context: dict):
    await redis_client.set(
        f"message_store:user_id:{user_id}:active_planning_context",
        json.dumps(context),
    )
