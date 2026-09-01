# import json

import json
from fastapi import APIRouter, HTTPException, Depends
from openai import OpenAI
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage
from backend.models.models import ChatPrompt
from backend.config.config import settings
from backend.config.logger import logger
from backend.routes.auth import get_current_user
from backend.database.database import get_warehouses_by_userall, get_vehicles_by_user
from fastapi.responses import JSONResponse
from backend.config.redis import *

router = APIRouter(tags=["Chat Service"])

OPENAI_API_KEY = settings.OPENAI_API_KEY
if not settings.OPENAI_API_KEY:
    print("OPENAI API key not configured")

client = OpenAI(api_key=OPENAI_API_KEY)


REDIS_URL = settings.REDIS_URL


# -------------------------
# REDIS MEMORY CONFIG
# -------------------------
  
# def get_chat_memory(user_id: int) -> RedisChatMessageHistory:
#     return RedisChatMessageHistory(session_id=f"user_id:{user_id}:history", url=REDIS_URL)

# -------------------------
# UNIFIED CHAT FUNCTION
# -------------------------

class Parameters(BaseModel):
    source: Optional[str] = Field(
        default=None,
        description="Starting location of the route.This source can be from the warehouses shared by the user." ###add better description 
    )
    destination: Optional[str] = Field(
        default=None,
        description="Ending location of the route warehouses shared by the user." ##remove the optaional destincation can not be optional 
    )
    intermediate_locations: List[str] = Field(
        default_factory=list,
        description="List of intermediate stop locations between source and destination.These only can be from the warehouses shared by the user."
    )
    vehicle_types: List[str] = Field(
        default_factory=list,
        description="Allowed or requested vehicle types (e.g., truck, car, auto, bike, plane)"
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
        description="Whether the warehouse, vehicle or multimodal route is active or inactive"
    )
    capacity: Optional[int] = Field(
        default=None,
        description="Capacity of the vehicles"
    )
    objective: Optional[str] = Field(
        default="duration",
        description="Objective for route planning, e.g., if it is related to time take duration, if related to cost take cost, if related to distance take distance. Objective must be either duration, cost or distance"
        # description="Objective for route planning (fastest, cheapest, shortest, longest, costliest, slowest)."
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
    # print(f"==>> chat_prompt: {chat_prompt}")
    
    user_message = chat_prompt.prompt
    # memory = get_chat_memory(user_id)

    history_list = await get_data(user_id) or []   # list of dicts with 'role' and 'content'
    # print(f"==>> history_list:  {history_list}")

    # Convert last 10 messages to LangChain message objects for context
    messages_for_context = []
    for msg_dict in history_list[-10:]:
        if msg_dict["role"] == "user":
            messages_for_context.append(HumanMessage(content=msg_dict["content"]))
        elif msg_dict["role"] == "assistant":
            messages_for_context.append(AIMessage(content=msg_dict["content"]))
    
    
    # print(f"==>> memory: {messages_for_context}")

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
2. complete_vehicle_route - Trigger this when user asked to  when the user prompt that vehicle (any one of them truck, car, bike, or auto) with id ___ reached its destination (destination name) on route id ___
3. assign_vehicle - Trigger this when user asked to  Assign vehicle(s) to routes or transport goods from source to destianation or on route id, user may mention the transport_mode whether road or air otherwise transport_mode is None.
4. stop_vehicle - Trigger this when user asked to  Stop, reset or remove vehicle movement, user can mention (any one of them truck id, car id, bike id, or auto id or vehicle id.)  
5. remove_route - Trigger this when user asked to  Remove route from display
6. help - Trigger this when user asked to  Show help information
7. alternative_route - Trigger this when user asked to Request alternative route due to road blocks, traffic, disruption or any other reason or just the user wants alternative route, etc.
8. clear_map - Trigger this when user asked to  Clear the map display (remove routes, vehicles, etc.)
9. satellite_view: Trigger this when user asked to Activate satellite map view
10. street_view: Trigger this when user asked to Activate street map view
11. clear_chat - Trigger this when user asked to  Clear the chat conversation history
12. list_vehicles - Trigger this when user asked to  List all available vehicles at a location
13. fetch_routes - Trigger this when user asked to  When users wants the route details but he doesn't wants to plan route again. just fetch the existing routes from database. User can ask about which is the fastest route, costliest route, cheapest route, fastest and least time etc.
14. multimodal_route - Trigger this when user asked to When user mention that he want to plan a route from source to destination via plane or mentions air route or multimodal or plan the fastest route etc. Use this always in case of fastest.
15. remove_multimodal_route - Trigger this when user asked to When user mention remove multi modal route with id or remove multi modal route id
16. reset_all_vehicles - Trigger this when user asked to When user says reset or stop all the vehicles etc.
17. connect_hub - Trigger this when user asked to When user says connect hub to capital routes etc. or Connect UPS Worldport to all capital cities etc. or similar as UPS Worldport is hub or connect all capitals to hub.
18. warehouse_status_update - Trigger this When user wants to activate or deactivate a warehouse by its name. or say warehouse name is funcitional or non functional etc.
19. vehicle_status_update: Trigger this When user wants to activate or deactivate a vehicle by its ID. or say vehicle id is funcitional or non functional or not working or damaged.
20. route_status_update: Trigger this when the user meniton multimodal/air route and indicates an emergency, disruption, blockage, or any situation requiring the activation or deactivation of a multimodal/air route by its ID. The user needs to mention the route (multimodal/air) either it will be considered as road route

- If the user indicates a problem, hazard, emergency, or disruption → set `"is_active": false`.
- If the user says the issue is resolved, clear, restored, working, reopened → set `"is_active": true`.

Do NOT omit "is_active". Never set it to null. Always return either false (inactive) or true (active).

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

❌ NEVER invent warehouse names or vehicle types from your nown
❌ NEVER autocorrect or guess names  
❌ If a mentioned name is NOT in the allowed list → set it to null

────────────────────────────────────────
FIELDS TO EXTRACT
────────────────────────────────────────

parameters object must contain ALL fields below:

Rules:
- If user mentions “route 10” → route_id = 10
- If user mentions “truck id 5” → vehicle_id = 5 and vehicle_types = ["truck"]
- If route_id is present, it takes priority over source/destination
- For multimodal or air routes → transport_mode = "air"
- For normal routes → transport_mode = "road"
- For warehouse activation/deactivation → set warehouse_name and is_active

For intent = "assign_vehicle":
    - If user mentions air → transport_mode = "air"
    - If user mentions road → transport_mode = "road"
    - If user does NOT mention mode → transport_mode = null

INTENT PRIORITY FIX
If the user mentions transporting goods, shipping goods, moving goods, or provides a capacity (e.g., 4500 kg),
then the intent MUST be "assign_vehicle" regardless of whether the user says road, air, or fastest.
Do NOT use "multimodal_route" or "plan_route" for goods movement. Use it only when the user explicitly asks to plan a route.

OBJECTIVE EXTRACTION RULE (MANDATORY)

The objective field can be null.

Always map natural language words to one of:
- "duration"
- "cost"
- "distance"

Mapping rules:
- fastest, quickest, earliest, minimum time → "duration"
- cheapest, lowest cost, minimum cost → "cost"
- shortest, minimum distance → "distance"


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
    # print(f"==>> messages: {messages}")

    # for msg in memory.messages[-10:]:
    #     if isinstance(msg, HumanMessage):
    #         messages.append({"role": "user", "content": msg.content})
    #     elif isinstance(msg, AIMessage):
    #         messages.append({"role": "assistant", "content": msg.content})

    for msg in messages_for_context:
        if isinstance(msg, HumanMessage):
            messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            messages.append({"role": "assistant", "content": msg.content})


    user_message = user_message.lower()

    new_warehouse_names = [f"{index}. {n}\n" for index, n in enumerate(warehouse_names, start=1)]
    new_warehouse_names = ", ".join(new_warehouse_names)
    messages.append({"role": "user", "content": "User message: "+user_message + f"These are the current warehouses names we need to check make this check properly ignore the lower or upper case need to check the names :\n {new_warehouse_names}"})


    # print("\n\n\n\n\n\n\n\n")
    # print(f"==>> Final messages---------: {messages}")
    # print("\n\n\n\n\n\n\n\n")

    response = client.responses.parse(
        model="gpt-5.2-2025-12-11",
        # model="gpt-4.1-2025-04-14",
        input=messages,
        text_format=IntentResponse
    )
    # print(f"==>> initial response for intent and reply: {response}")

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
    # HANDLE CLEAR CHAT INTENT
    # -------------------------
    # if result.get("intent") == "clear_chat":
    #     memory.clear()
    #     return {
    #         "intent": "clear_chat",
    #         "reply": "Chat history cleared.",
    #         "confidence": 1.0,
    #         "parameters": {}
    #     }

    # -------------------------
    # STORE MEMORY
    # -------------------------
    # memory.add_message(HumanMessage(content=user_message))
    # memory.add_message(AIMessage(content=result.get("reply", "")))


    # history_list.append({"role": "user", "content": user_message})
    # history_list.append({"role": "assistant", "content": result.get("reply", "")})
    # await add_data(user_id, history_list)

    return result



# @router.get("/chat/history")
# async def get_chat_history(current_user = Depends(get_current_user)):

#     try:
#         user_id = current_user.get("user_id")
        
#         if not user_id:
#             return JSONResponse(
#                 status_code=401,
#                 content={
#                     "success": False,
#                     "message": "Invalid token: user_id not found"
#                 },
#             )
        
        
#         memory = get_chat_memory(user_id)

#         history = [
#             {"role": "user" if isinstance(m, HumanMessage) else "assistant", "content": m.content}
#             for m in memory.messages
#         ]
#         return JSONResponse(
#                 status_code=200,
#                 content={
#                     "success": True,
#                     "message": "User's chat history", 
#                     "data": history
#                 },
#             )


#     except Exception as e:
#         logger.error(f"Error in fetching chat: {e}")
#         return JSONResponse(
#                 status_code=500,
#                 content={
#                     "success": False,
#                     "message": "Unable to fetch history"
#                 },
#             )

    
    

# @router.delete("/chat/history")
# async def clear_chat_history(current_user = Depends(get_current_user)):


#     try:
#         user_id = current_user.get("user_id")
            
#         if not user_id:
#             return JSONResponse(
#                 status_code=401,
#                 content={
#                     "success": False,
#                     "message": "Invalid token: user_id not found"
#                 },
#             )
        
#         memory = get_chat_memory(user_id)
#         memory.clear()
#         return JSONResponse(
#                 status_code=200,
#                 content={
#                     "success": True,
#                     "message": "User's chat history deleted"
#                 },
#             )


#     except Exception as e:
#         logger.error(f"Error deleting chat: {e}")
#         return JSONResponse(
#                 status_code=500,
#                 content={
#                     "success": False,
#                     "message": "Unable to delete history"
#                 },
#             )
    

@router.get("/chat/history")
async def get_chat_history(current_user=Depends(get_current_user)):
    try:
        user_id = current_user.get("user_id")
        if not user_id:
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "Invalid token: user_id not found"}
            )

        history_list = await get_data(user_id) or []
        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "User's chat history", "data": history_list}
        )

    except Exception as e:
        logger.error(f"Error in fetching chat: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Unable to fetch history"}
        )


@router.delete("/chat/history")
async def clear_chat_history(current_user=Depends(get_current_user)):
    try:
        user_id = current_user.get("user_id")
        if not user_id:
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "Invalid token: user_id not found"}
            )

        await delete_data(user_id)
        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "User's chat history deleted"}
        )

    except Exception as e:
        logger.error(f"Error deleting chat: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Unable to delete history"}
        )

