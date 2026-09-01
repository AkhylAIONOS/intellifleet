import aioredis
import json
from ..database.database import get_persistent_route_by_id, get_multimodal_route_by_id
from fastapi import HTTPException
from ..config.logger import logger
from typing import Any, Dict 

redis_client = aioredis.Redis(
    host='localhost',
    port=6379,
    db=1,
    decode_responses=True
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
    await redis_client.delete(key)  


