import redis
import json
from fastapi import APIRouter, HTTPException, Depends
from openai import OpenAI
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.chat_history import BaseChatMessageHistory
from backend.models.models import ChatPrompt
from backend.config.config import settings
from backend.config.logger import logger
from backend.routes.auth import get_current_user
from backend.database.database import get_warehouses_by_userall, get_vehicles_by_user
from fastapi.responses import JSONResponse
import pickle

router = APIRouter()

OPENAI_API_KEY = settings.OPENAI_API_KEY
if not settings.OPENAI_API_KEY:
    print("OPENAI API key not configured")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

REDIS_URL = settings.REDIS_URL


class CustomRedisChatMessageHistory(BaseChatMessageHistory):
    """Custom Redis chat message history without langchain_community"""
    
    def __init__(self, session_id: str, url: str = "redis://localhost:6379", ttl: int = 86400):
        """Initialize Redis chat message history.
        
        Args:
            session_id: ID for the chat session
            url: Redis URL (format: redis://:password@host:port/db)
            ttl: Time to live in seconds (default 24 hours)
        """
        self.session_id = f"chat_history:{session_id}"
        self.ttl = ttl
        
        # ALWAYS use redis.from_url - it handles all Redis URL formats correctly
        try:
            # redis.from_url handles all formats including passwords and database numbers
            self.redis_client = redis.from_url(url, decode_responses=False)
            logger.info(f"Connected to Redis with URL: {url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis at {url}: {e}")
            # Fallback to default without password
            try:
                # Try parsing the URL manually for debugging
                if url.startswith("redis://"):
                    url = url[8:]  # Remove redis://
                
                # For your URL format: ":87654321@localhost:6379/0"
                if url.startswith(":"):
                    # Has password
                    password_part = url.split("@")[0][1:]  # Get "87654321"
                    server_part = url.split("@")[1]  # Get "localhost:6379/0"
                    
                    # Extract host, port, db
                    if "/" in server_part:
                        server, db = server_part.split("/")
                        db = int(db)
                    else:
                        server = server_part
                        db = 0
                    
                    if ":" in server:
                        host, port = server.split(":")
                        port = int(port)
                    else:
                        host = server
                        port = 6379
                    
                    logger.info(f"Manual parsing - Host: {host}, Port: {port}, DB: {db}")
                    self.redis_client = redis.Redis(
                        host=host,
                        port=port,
                        password=password_part,
                        db=db,
                        decode_responses=False
                    )
                else:
                    # No password
                    self.redis_client = redis.Redis(host='localhost', port=6379, decode_responses=False)
            except Exception as e2:
                logger.error(f"Fallback connection also failed: {e2}")
                # Last resort
                self.redis_client = redis.Redis(host='localhost', port=6379, decode_responses=False)
    
    @property
    def messages(self):
        """Get all messages from Redis"""
        try:
            data = self.redis_client.get(self.session_id)
            if data:
                try:
                    return pickle.loads(data)
                except:
                    # Try JSON if pickle fails
                    try:
                        messages_data = json.loads(data.decode('utf-8'))
                        # Convert dicts to message objects
                        messages = []
                        for msg_data in messages_data:
                            if isinstance(msg_data, dict):
                                if msg_data.get("type") == "human" or msg_data.get("role") == "user":
                                    messages.append(HumanMessage(content=msg_data.get("content", "")))
                                elif msg_data.get("type") == "ai" or msg_data.get("role") == "assistant":
                                    messages.append(AIMessage(content=msg_data.get("content", "")))
                        return messages
                    except:
                        return []
            return []
        except Exception as e:
            logger.error(f"Error retrieving messages: {e}")
            return []
    
    def add_message(self, message):
        """Add a message to Redis"""
        try:
            messages = self.messages
            messages.append(message)
            
            # Serialize with pickle
            serialized = pickle.dumps(messages)
            self.redis_client.setex(self.session_id, self.ttl, serialized)
            return True
        except Exception as e:
            logger.error(f"Error adding message: {e}")
            # Fallback to JSON
            try:
                messages_data = []
                for msg in messages:
                    if isinstance(msg, HumanMessage):
                        messages_data.append({"type": "human", "content": msg.content})
                    elif isinstance(msg, AIMessage):
                        messages_data.append({"type": "ai", "content": msg.content})
                    elif hasattr(msg, 'content'):
                        messages_data.append({"type": "unknown", "content": msg.content})
                
                self.redis_client.setex(
                    self.session_id, 
                    self.ttl, 
                    json.dumps(messages_data).encode('utf-8')
                )
                return True
            except Exception as e2:
                logger.error(f"JSON fallback also failed: {e2}")
                return False
    
    def clear(self):
        """Clear all messages"""
        try:
            self.redis_client.delete(self.session_id)
            return True
        except Exception as e:
            logger.error(f"Error clearing messages: {e}")
            return False
    
    def __len__(self):
        """Get number of messages"""
        return len(self.messages)
    
    def __str__(self):
        """String representation"""
        return f"CustomRedisChatMessageHistory(session_id={self.session_id}, messages={len(self.messages)})"

def get_chat_memory(user_id: int) -> CustomRedisChatMessageHistory:
    """Get chat memory for user"""
    return CustomRedisChatMessageHistory(
        session_id=f"user_id:{user_id}:history",
        url=REDIS_URL,
        ttl=86400  # 24 hours
    )

# -------------------------
# ALTERNATIVE: Simple Redis Wrapper (Even Simpler)
# -------------------------

class SimpleRedisChatHistory:
    """Simple Redis chat history wrapper"""
    
    def __init__(self, session_id: str, redis_url: str):
        self.session_id = f"chat:{session_id}"
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.messages = []
        self._load_messages()
    
    def _load_messages(self):
        """Load messages from Redis"""
        data = self.redis_client.get(self.session_id)
        if data:
            try:
                self.messages = json.loads(data)
            except:
                self.messages = []
        else:
            self.messages = []
    
    def _save_messages(self):
        """Save messages to Redis"""
        self.redis_client.setex(self.session_id, 86400, json.dumps(self.messages))
    
    def add_message(self, message):
        """Add a message"""
        # Convert LangChain messages to dict
        if hasattr(message, 'content') and hasattr(message, 'type'):
            msg_dict = {
                "content": message.content,
                "type": message.type if hasattr(message, 'type') else type(message).__name__,
                "role": "user" if isinstance(message, HumanMessage) else "assistant"
            }
            self.messages.append(msg_dict)
        elif isinstance(message, dict):
            self.messages.append(message)
        else:
            self.messages.append({"content": str(message), "type": "unknown"})
        
        self._save_messages()
    
    def clear(self):
        """Clear all messages"""
        self.messages = []
        self.redis_client.delete(self.session_id)
    
    def __len__(self):
        return len(self.messages)
    
    def __iter__(self):
        return iter(self.messages)

def get_simple_chat_memory(user_id: int) -> SimpleRedisChatHistory:
    """Get simple chat memory for user"""
    return SimpleRedisChatHistory(
        session_id=f"user_{user_id}",
        redis_url=REDIS_URL
    )

# -------------------------
# UNIFIED CHAT FUNCTION (Updated)
# -------------------------

class Parameters(BaseModel):
    source: Optional[str] = Field(
        default=None,
        description="Starting location of the route. This source can be from the warehouses shared by the user."
    )
    destination: Optional[str] = Field(
        default=None,
        description="Ending location of the route warehouses shared by the user."
    )
    intermediate_locations: List[str] = Field(
        default_factory=list,
        description="List of intermediate stop locations between source and destination. These only can be from the warehouses shared by the user."
    )
    vehicle_types: List[str] = Field(
        default_factory=list,
        description="Allowed or requested vehicle types (e.g., truck, car, auto, bike)"
    )
    transport_mode: Optional[Literal["road", "air"]] = Field(
        default=None,
        description="Mode of transport for the route"
    )
    route_id: Optional[int] = Field(
        default=None,
        description="Existing route ID if referring to a saved route"
    )
    vehicle_id: Optional[int] = Field(
        default=None,
        description="Vehicle ID if a specific vehicle is referenced"
    )
    warehouse_name: Optional[str] = Field(
        default=None,
        description="Warehouse name involved in the query"
    )
    is_active: Optional[bool] = Field(
        default=None,
        description="Whether the warehouse is active or inactive"
    )
    capacity: Optional[int] = Field(
        default=None,
        description="Capacity of the vehicles"
    )

class IntentResponse(BaseModel):
    intent: str = Field(
        ...,
        description="Detected user intent derived from the query"
    )
    parameters: Parameters = Field(
        ...,
        description="Structured parameters extracted from the user query"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score of the intent detection (0 to 1)"
    )
    reply: str = Field(
        ...,
        description="Natural language assistant response to the user"
    )

async def unified_chat_endpoint_function(chat_prompt: ChatPrompt, user_id: int):
    print(f"==>> chat_prompt: {chat_prompt}")
    
    user_message = chat_prompt.prompt
    
    # Use our custom chat memory (no langchain_community)
    memory = get_chat_memory(user_id)  # or get_simple_chat_memory(user_id)
    print(f"==>> memory created: {memory}")

    # Fetch warehouses and vehicles for user
    warehouses = get_warehouses_by_userall(user_id)
    vehicles = get_vehicles_by_user(user_id)

    warehouse_names = [w["name"] for w in warehouses]
    vehicle_types = sorted({v["type"] for v in vehicles})

    # -------------------------
    # SYSTEM PROMPT
    # -------------------------

    system_prompt = f"""You are an intelligent backend assistant responsible for understanding user queries related to routes, vehicles, warehouses, and maps, and converting them into a strictly structured JSON response.
You have to understand the user question intent and check what user want to do.User want to travel from one warehouse to another we need to check names only from the given list of the warehouse names.
Your output is consumed by backend services.
You MUST follow all rules precisely.
You MUST output ONLY valid JSON.
DO NOT add explanations, markdown, comments, or extra text.

────────────────────────────────────────
INTENT DETECTION
────────────────────────────────────────
Identify EXACTLY ONE intent from the list below:

1. plan_route - Trigger this when user asked to Plan a new route between locations (by road)
2. complete_vehicle_route - Trigger this when user asked to when the user prompt that vehicle (any one of them truck, car, bike, or auto) with id ___ reached its destination (destination name) on route id ___
3. assign_vehicle - Trigger this when user asked to Assign vehicle(s) to routes
4. stop_vehicle - Trigger this when user asked to Stop, reset or remove vehicle movement, user can mention (any one of them truck id, car id, bike id, or auto id or vehicle id.)  
5. remove_route - Trigger this when user asked to Remove route from display
6. help - Trigger this when user asked to Show help information
7. alternative_route - Trigger this when user asked to Request alternative route due to road blocks, traffic, disruption or any other reason or just the user wants alternative route, etc.
8. clear_map - Trigger this when user asked to Clear the map display (remove routes, vehicles, etc.)
9. satellite_view: Trigger this when user asked to Activate satellite map view
10. street_view: Trigger this when user asked to Activate street map view
11. clear_chat - Trigger this when user asked to Clear the chat conversation history
12. list_vehicles - Trigger this when user asked to List all available vehicles at a location
13. fetch_routes - Trigger this when user asked to When users wants the route details but he doesn't wants to plan route again. just fetch the existing routes from database.
14. multimodal_route - Trigger this when user asked to When user mention that he want to plan a route from source to destination via plane or mentions air route or multimodal 
15. remove_multimodal_route - Trigger this when user asked to When user mention remove multi modal route with id or remove multi modal route id
16. reset_all_vehicles - Trigger this when user asked to When user says reset or stop all the vehicles etc.
17. assign_vehicle_multimodal - Trigger this when user asked to When users says assign vehicle or truck on multimodal route id
18. connect_hub - Trigger this when user asked to When user says connect hub to capital routes etc. or Connect UPS Worldport to all capital cities etc. or similar as UPS Worldport is hub or connect all capitals to hub.
19. warehouse_status_update - Trigger this when user asked to When user wants to activate or deactivate a warehouse by its name. or say warehouse name is funcitional or non functional etc.
20. vehicle_status_update: Trigger this When user wants to activate or deactivate a vehicle by its ID. or say vehicle id is funcitional or non functional or not working or damaged.
21. assign_plane: Trigger this when user asked to Assign plane to routes by specifying route_id
 
────────────────────────────────────────
IMPORTANT NOTE
────────────────────────────────────────
If warehouse_names is EMPTY or NOT PROVIDED:
- You MUST respond with intent = "help"
- Reply must instruct the user to upload the warehouse CSV first
- Do NOT attempt intent execution

────────────────────────────────────────
ROUTE & ENTITY EXTRACTION RULES
────────────────────────────────────────
Extract values ONLY when explicitly mentioned by the user.

Search only from the valid warehouse/location names:

Valid vehicle types:
{vehicle_types}

❌ NEVER invent warehouse names or vehicle types from your own knowledge
❌ NEVER autocorrect or guess names  
❌ If a mentioned name is NOT in the allowed list → set it to null

────────────────────────────────────────
FIELDS TO EXTRACT
────────────────────────────────────────

parameters object must contain ALL fields below:

Rules:
- If user mentions "route 10" → route_id = 10
- If user mentions "truck id 5" → vehicle_id = 5 and vehicle_types = ["truck"]
- If route_id is present, it takes priority over source/destination
- For multimodal or air routes → transport_mode = "air"
- For normal routes → transport_mode = "road"
- For warehouse activation/deactivation → set warehouse_name and is_active

REPLY FIELD
────────────────────────────────────────
- Must be natural, conversational, and helpful
- Must explain what action was understood
- If any entity is invalid or null, explain it politely
- If CSV is missing, instruct user to upload it

────────────────────────────────────────
FINAL OUTPUT FORMAT (STRICT)
────────────────────────────────────────

⚠️ Any response that is not valid JSON is considered a FAILURE."""

    # -------------------------
    # BUILD CONTEXT (LAST 10 MSGS)
    # -------------------------
    messages = [{"role": "system", "content": system_prompt}]
    print(f"==>> system prompt set")

    # Load history from our custom memory
    history_messages = memory.messages if hasattr(memory, 'messages') else []
    
    for msg in history_messages[-10:]:  # Last 10 messages
        # Handle both our custom format and LangChain format
        if isinstance(msg, HumanMessage):
            messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            messages.append({"role": "assistant", "content": msg.content})
        elif isinstance(msg, dict) and "content" in msg:
            role = msg.get("role", "user" if msg.get("type") == "human" else "assistant")
            messages.append({"role": role, "content": msg["content"]})

    user_message = user_message.lower()

    new_warehouse_names = [f"{index}. {n}\n" for index, n in enumerate(warehouse_names, start=1)]
    new_warehouse_names = ", ".join(new_warehouse_names)
    messages.append({"role": "user", "content": "User message: "+user_message + f"These are the current warehouses names we need to check make this check properly ignore the lower or upper case need to check the names :\n {new_warehouse_names}"})

    print("\n" + "="*50)
    print(f"Final messages: {len(messages)} total")
    print("="*50 + "\n")

    try:
        if client is None:
            raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")

        response = client.responses.parse(
            model="gpt-5.2-2025-12-11",
            input=messages,
            text_format=IntentResponse
        )
        print(f"==>> OpenAI response received")
        
        try:
            content = response.choices[0].message.content
        except Exception as e:
            content = response.output_parsed
            content = json.dumps(content.model_dump())

        logger.info("OPENAI response: %s", content)

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            result = {
                "intent": "help",
                "parameters": {},
                "reply": "Sorry, I couldn't understand. Can you rephrase?",
                "confidence": 0.0
            }

        # -------------------------
        # SANITIZE PARAMETERS
        # -------------------------
        params = result.get("parameters", {})

        if params.get("source", "") not in warehouse_names:
            params["source"] = None

        if params.get("destination", "") not in warehouse_names:
            params["destination"] = None

        params["intermediate_locations"] = [
            loc for loc in params.get("intermediate_locations", [])
            if loc in warehouse_names
        ]

        result["parameters"] = params

        # -------------------------
        # STORE MEMORY
        # -------------------------
        memory.add_message(HumanMessage(content=user_message))
        memory.add_message(AIMessage(content=result.get("reply", "")))

        return result

    except Exception as e:
        logger.error(f"Error in unified_chat_endpoint_function: {e}", exc_info=True)
        return {
            "intent": "help",
            "parameters": {},
            "reply": "Sorry, something went wrong processing your request.",
            "confidence": 0.0
        }





# -------------------------
# CUSTOM REDIS MEMORY IMPLEMENTATION (No langchain_community)
# -------------------------

# class CustomRedisChatMessageHistory(BaseChatMessageHistory):
#     """Custom Redis chat message history without langchain_community"""
    
#     def __init__(self, session_id: str, url: str = "redis://localhost:6379", ttl: int = 86400):
#         """Initialize Redis chat message history.
        
#         Args:
#             session_id: ID for the chat session
#             url: Redis URL
#             ttl: Time to live in seconds (default 24 hours)
#         """
#         self.session_id = f"chat_history:{session_id}"
#         self.ttl = ttl
        
#         # Parse Redis URL
#         if url.startswith("redis://"):
#             url = url[8:]
        
#         if ":" in url:
#             host, port = url.split(":")
#             self.redis_client = redis.Redis(host=host, port=int(port), decode_responses=False)
#         else:
#             self.redis_client = redis.Redis(host=url, port=6379, decode_responses=False)
    
#     @property
#     def messages(self):
#         """Get all messages from Redis"""
#         data = self.redis_client.get(self.session_id)
#         if data:
#             try:
#                 return pickle.loads(data)
#             except:
#                 # Try JSON if pickle fails
#                 try:
#                     return json.loads(data.decode('utf-8'))
#                 except:
#                     return []
#         return []
    
#     def add_message(self, message):
#         """Add a message to Redis"""
#         messages = self.messages
#         messages.append(message)
        
#         # Serialize with pickle for complex objects
#         serialized = pickle.dumps(messages)
#         self.redis_client.setex(self.session_id, self.ttl, serialized)
    
#     def clear(self):
#         """Clear all messages"""
#         self.redis_client.delete(self.session_id)
    
#     def __len__(self):
#         """Get number of messages"""
#         return len(self.messages)
    
#     def __str__(self):
#         """String representation"""
#         return f"CustomRedisChatMessageHistory(session_id={self.session_id}, messages={len(self.messages)})"
