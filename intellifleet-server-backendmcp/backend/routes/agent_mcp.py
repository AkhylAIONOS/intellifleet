# """
# COMPLETE MCP + LANGGRAPH AGENT WITH ALL 21 TOOLS
# """

# import json
# from typing import Dict, List, Any, Optional, TypedDict, Annotated
# import operator
# # LangGraph imports
# from langgraph.graph import StateGraph, END
# from langgraph.checkpoint import MemorySaver
# from langchain_openai import ChatOpenAI
# from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
# import logging

# from backend.services.chat_tool_service import chat_service
# # FastAPI imports
# from fastapi import APIRouter, Depends, HTTPException
# from pydantic import BaseModel
# from backend.routes.agent_routes import calculate_route_with_google
# # Your existing imports
# from ..models.agentSchema import *
# from ..config.logger import logger
# from ..database.database import *
# from ..routes.api import unified_chat_endpoint_function, get_chat_memory
# from ..models.models import ChatPrompt
# from backend.routes.auth import get_current_user
# # from backend.routes.agent_routes import chat_service
# logger = logging.getLogger(__name__)

# router = APIRouter()

# # ==============================================
# # 1. STATE DEFINITION
# # ==============================================

# class AgentState(TypedDict):
#     """State for LangGraph workflow"""
#     user_message: str
#     user_id: int
#     intents: List[Dict]
#     parameters: Dict[str, Any]
#     confidence: float
#     messages: Annotated[List[Any], operator.add]
#     warehouses: List[Dict]
#     vehicles: List[Dict]
#     tool_outputs: List[Dict]
#     final_response: Optional[Dict]
#     actions: List[Dict]

# # ==============================================
# # 2. COMPLETE MCP MANAGER (21 TOOLS)
# # ==============================================

# class CompleteMCPServerManager:
#     """Complete MCP manager"""
    
#     def __init__(self):
#         self.tools = self._create_complete_tool_registry()
#         logger.info(f"✅ Complete MCP Manager initialized with {len(self.tools)} tools")
    
#     def _create_complete_tool_registry(self) -> Dict[str, Dict]:
#         """Create a registry of ALL available tools"""
#         return {
#             # ==================== ROUTE MANAGEMENT (6 tools) ====================
#             "plan_route": {
#                 "description": "Plan a new route between locations (by road)",
#                 "handler": self._call_plan_route,
#                 "parameters": ["source", "destination"]
#             },
#             "alternative_route": {
#                 "description": "Request alternative route due to road blocks, traffic, disruption",
#                 "handler": self._call_alternative_route,
#                 "parameters": ["route_id", "reason"]
#             },
#             "remove_route": {
#                 "description": "Remove route from display",
#                 "handler": self._call_remove_route,
#                 "parameters": ["route_id"]
#             },
#             "fetch_routes": {
#                 "description": "Fetch existing route details without planning new route",
#                 "handler": self._call_fetch_routes,
#                 "parameters": ["query"]
#             },
#             "multimodal_route": {
#                 "description": "Plan multimodal route (air + road) or via plane",
#                 "handler": self._call_multimodal_route,
#                 "parameters": ["source", "destination"]
#             },
#             "remove_multimodal_route": {
#                 "description": "Remove multimodal route with ID",
#                 "handler": self._call_remove_multimodal_route,
#                 "parameters": ["route_id"]
#             },
            
#             # ==================== VEHICLE MANAGEMENT (8 tools) ====================
#             "assign_vehicle": {
#                 "description": "Assign vehicle(s) to routes",
#                 "handler": self._call_assign_vehicle,
#                 "parameters": ["route_id", "vehicle_types", "capacity", "source", "destination"]
#             },
#             "stop_vehicle": {
#                 "description": "Stop, reset or remove vehicle movement by vehicle ID",
#                 "handler": self._call_stop_vehicle,
#                 "parameters": ["vehicle_id"]
#             },
#             "complete_vehicle_route": {
#                 "description": "Mark vehicle as reached destination on route",
#                 "handler": self._call_complete_vehicle_route,
#                 "parameters": ["vehicle_id", "route_id", "destination"]
#             },
#             "reset_all_vehicles": {
#                 "description": "Reset or stop all vehicles",
#                 "handler": self._call_reset_all_vehicles,
#                 "parameters": []
#             },
#             "assign_vehicle_multimodal": {
#                 "description": "Assign vehicle or truck on multimodal route",
#                 "handler": self._call_assign_vehicle_multimodal,
#                 "parameters": ["route_id", "vehicle_types"]
#             },
#             "vehicle_status_update": {
#                 "description": "Activate or deactivate vehicle by ID",
#                 "handler": self._call_vehicle_status,
#                 "parameters": ["vehicle_id", "is_active"]
#             },
#             "assign_plane": {
#                 "description": "Assign plane to routes by specifying route_id",
#                 "handler": self._call_assign_plane,
#                 "parameters": ["route_id"]
#             },
            
#             # ==================== WAREHOUSE MANAGEMENT (2 tools) ====================
#             "warehouse_status_update": {
#                 "description": "Activate or deactivate warehouse by name",
#                 "handler": self._call_warehouse_status,
#                 "parameters": ["warehouse_name", "is_active"]
#             },
            
#             # ==================== SYSTEM OPERATIONS (4 tools) ====================
#             "clear_map": {
#                 "description": "Clear the map display (remove routes, vehicles, etc.)",
#                 "handler": self._call_clear_map,
#                 "parameters": []
#             },
#             "satellite_view": {
#                 "description": "Activate satellite map view",
#                 "handler": self._call_satellite_view,
#                 "parameters": []
#             },
#             "street_view": {
#                 "description": "Activate street map view",
#                 "handler": self._call_street_view,
#                 "parameters": []
#             },
#             "clear_chat": {
#                 "description": "Clear the chat conversation history",
#                 "handler": self._call_clear_chat,
#                 "parameters": []
#             },
            
#             # ==================== SPECIAL OPERATIONS (2 tools) ====================
#             "connect_hub": {
#                 "description": "Connect hub to capital routes (e.g., UPS Worldport to capitals)",
#                 "handler": self._call_connect_hub,
#                 "parameters": ["hub_name"]
#             },
            
#             # ==================== HELP (1 tool) ====================
#             "help": {
#                 "description": "Show help information",
#                 "handler": self._call_help,
#                 "parameters": []
#             }
#         }
    
#     async def call_tool(self, tool_name: str, params: Dict, user_id: int) -> Dict:
#         """Calling the tool"""
#         if tool_name not in self.tools:
#             return {"error": f"Tool '{tool_name}' not found. Available: {list(self.tools.keys())}"}
        
#         try:
#             logger.info(f'tool_name {type(tool_name)}: {tool_name}')
#             handler = self.tools[tool_name]["handler"]            
#             logger.info(f'handler {type(handler)}: {handler}')
#             result = await handler(params, user_id)
#             logger.info(f'result {type(result)}: {result}')
            
#             return {
#                 "success": True,
#                 "tool": tool_name,
#                 "result": result
#             }
#         except Exception as e:
#             logger.error(f"Tool '{tool_name}' execution error: {e}")
#             return {
#                 "error": str(e),
#                 "tool": tool_name
#             }   
    
#     # ==============================================
#     # COMPLETE TOOL HANDLERS 
#     # ==============================================
    
#     async def _call_plan_route(self, params: Dict, user_id: int) -> Dict:
#         """Call plan_route function"""
#         try:
#             waypoints = [params.get("source")]
#             # logger.info(f'waypoints  {type(waypoints )}: {waypoints }')
#             if params.get("intermediate_locations"):
#                 waypoints.extend(params["intermediate_locations"])
#             waypoints.append(params.get("destination"))
#             # logger.info(f'waypoints {type(waypoints)}: {waypoints}')
            
#             if len(waypoints) < 2:
#                 return {"error": "Need source and destination"}
            
#             result = await calculate_route_with_google(user_id, waypoints)
#             logger.info(f'result {type(result)}: {result}')
#             return result
            
#         except Exception as e:
#             logger.error(f"Plan route error: {e}")
#             return {"error": str(e)}
    
#     async def _call_assign_vehicle(self, params: Dict, user_id: int) -> Dict:
#         """Call assign_vehicle function"""
#         try:
            
#             return await chat_service._handle_assign_vehicle(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Assign vehicle error: {e}")
#             return {"error": str(e)}
    
#     async def _call_stop_vehicle(self, params: Dict, user_id: int) -> Dict:
#         """Call stop_vehicle function"""
#         try:
            
#             return await chat_service._handle_reset_single_vehicle(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Stop vehicle error: {e}")
#             return {"error": str(e)}
    
#     async def _call_remove_route(self, params: Dict, user_id: int) -> Dict:
#         """Call remove_route function"""
#         try:
            
#             return await chat_service._handle_remove_route(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Remove route error: {e}")
#             return {"error": str(e)}
    
#     async def _call_alternative_route(self, params: Dict, user_id: int) -> Dict:
#         """Call alternative_route function"""
#         try:
           
#             return await chat_service._handle_alternative_route(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Alternative route error: {e}")
#             return {"error": str(e)}
    
#     async def _call_multimodal_route(self, params: Dict, user_id: int) -> Dict:
#         """Call multimodal_route function"""
#         try:
          
#             return await chat_service._handle_multimodal_route(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Multimodal route error: {e}")
#             return {"error": str(e)}
    
#     async def _call_remove_multimodal_route(self, params: Dict, user_id: int) -> Dict:
#         """Call remove_multimodal_route function"""
#         try:
         
#             return await chat_service._handle_remove_multimodal_route(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Remove multimodal route error: {e}")
#             return {"error": str(e)}
    
#     async def _call_fetch_routes(self, params: Dict, user_id: int) -> Dict:
#         """Call fetch_routes function"""
#         try:
           
#             return await chat_service._handle_fetch_routes(
#                 message=params.get("query", ""),
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Fetch routes error: {e}")
#             return {"error": str(e)}
    
#     async def _call_assign_vehicle_multimodal(self, params: Dict, user_id: int) -> Dict:
#         """Call assign_vehicle_multimodal function"""
#         try:
            
#             return await chat_service._handle_multimodal_assign_vehicle(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Assign vehicle multimodal error: {e}")
#             return {"error": str(e)}
    
#     async def _call_complete_vehicle_route(self, params: Dict, user_id: int) -> Dict:
#         """Call complete_vehicle_route function"""
#         try:
            
#             return await chat_service._complete_vehicle_route(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Complete vehicle route error: {e}")
#             return {"error": str(e)}
    
#     async def _call_reset_all_vehicles(self, params: Dict, user_id: int) -> Dict:
#         """Call reset_all_vehicles function"""
#         try:
    
#             return await chat_service._handle_reset_all_vehicles(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Reset all vehicles error: {e}")
#             return {"error": str(e)}
    
#     async def _call_warehouse_status(self, params: Dict, user_id: int) -> Dict:
#         """Call warehouse_status function"""
#         try:
         
#             return await chat_service._handle_warehouse_status(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Warehouse status error: {e}")
#             return {"error": str(e)}
    
#     async def _call_vehicle_status(self, params: Dict, user_id: int) -> Dict:
#         """Call vehicle_status function"""
#         try:
            
#             return await chat_service._handle_vehicle_status(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Vehicle status error: {e}")
#             return {"error": str(e)}
    
#     async def _call_assign_plane(self, params: Dict, user_id: int) -> Dict:
#         """Call assign_plane function"""
#         try:
            
#             return await chat_service._handle_assign_plane(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Assign plane error: {e}")
#             return {"error": str(e)}
    
#     async def _call_clear_map(self, params: Dict, user_id: int) -> Dict:
#         """Call clear_map function"""
#         try:
            
#             return await chat_service._handle_clear_all_routes(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Clear map error: {e}")
#             return {"error": str(e)}
    
#     async def _call_satellite_view(self, params: Dict, user_id: int) -> Dict:
#         """Call satellite_view function"""
#         try:
            
#             return await chat_service._handle_satellite_view(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Satellite view error: {e}")
#             return {"error": str(e)}
    
#     async def _call_street_view(self, params: Dict, user_id: int) -> Dict:
#         """Call street_view function"""
#         try:
            
#             return await chat_service._handle_street_view(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Street view error: {e}")
#             return {"error": str(e)}
    
#     async def _call_clear_chat(self, params: Dict, user_id: int) -> Dict:
#         """Call clear_chat function"""
#         try:
            
#             return await chat_service._handle_clear_chat(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Clear chat error: {e}")
#             return {"error": str(e)}
    
#     async def _call_connect_hub(self, params: Dict, user_id: int) -> Dict:
#         """Call connect_hub function"""
#         try:
            
#             return await chat_service._handle_hub_to_capital_routes(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Connect hub error: {e}")
#             return {"error": str(e)}
    
#     async def _call_help(self, params: Dict, user_id: int) -> Dict:
#         """Call help function"""
#         try:
            
#             return await chat_service._handle_help(
#                 message="",
#                 params=params,
#                 user_id=user_id,
#                 reply=None
#             )
#         except Exception as e:
#             logger.error(f"Help error: {e}")
#             return {"error": str(e)}
    
#     def get_tools_list(self) -> List[Dict]:
#         """Get list of ALL available tools"""
#         tools_list = []
#         for name, info in self.tools.items():
#             tools_list.append({
#                 "name": name,
#                 "description": info["description"],
#                 "parameters": info["parameters"]
#             })
#         return tools_list
    
#     def _get_tool_category(self, tool_name: str) -> str:
#         """Categorize tools for better organization"""
#         categories = {
#             "plan_route": "Route",
#             "alternative_route": "Route",
#             "remove_route": "Route",
#             "fetch_routes": "Route",
#             "multimodal_route": "Route",
#             "remove_multimodal_route": "Route",
#             "assign_vehicle": "Vehicle",
#             "stop_vehicle": "Vehicle",
#             "complete_vehicle_route": "Vehicle",
#             "reset_all_vehicles": "Vehicle",
#             "assign_vehicle_multimodal": "Vehicle",
#             "vehicle_status_update": "Vehicle",
#             "assign_plane": "Vehicle",
#             "warehouse_status_update": "Warehouse",
#             "clear_map": "System",
#             "satellite_view": "System",
#             "street_view": "System",
#             "clear_chat": "System",
#             "connect_hub": "Special",
#             "help": "Help"
#         }
#         return categories.get(tool_name, "General")

# # ==============================================
# # 3. LANGGRAPH AGENTS
# # ==============================================

# class EnhancedIntentDetector:
#     """Detects intents with multi-intent support for all 21 tools"""
    
#     def __init__(self, mcp_manager: CompleteMCPServerManager):
#         self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
#         self.mcp = mcp_manager
#         self.all_tools = mcp_manager.get_tools_list()
     
#     async def detect_intents(self, state: AgentState) -> AgentState:
#         """Detect intents from user message (supports multiple intents)"""
#         user_message = state["user_message"]
        
# #         prompt = f"""Analyze this logistics command and extract ALL possible intents:

# # User: "{user_message}"

# # Available operations:
# # {json.dumps(self.all_tools, indent=2)}

# # Rules:
# # 1. Extract ALL intents in one message
# # 2. Example: "Plan route SF→NY and remove truck 123" → plan_route + stop_vehicle
# # 3. Return JSON: {{"intents": [{{"name": "...", "parameters": {{...}}, "confidence": 0.95}}]}}
# # 4. Include "help" if unclear

# # Respond ONLY with JSON."""


#         prompt = f"""
# You are an expert Logistics Command Interpreter.

# Your job is to convert a user's natural language command into one or more
# STRICT tool invocations from the list below.

# ========================================
# AVAILABLE TOOLS (YOU MUST USE THESE NAMES ONLY)
# ========================================
# {json.dumps(self.all_tools, indent=2)}

# ========================================
# CRITICAL RULES (READ CAREFULLY)
# ========================================

# 1. You MUST choose tool names ONLY from the list above.
#    ❌ Do NOT invent tools
#    ❌ Do NOT rename tools

# 2. Extract ALL intents if the user asks for multiple actions.
#    Example:
#    "Plan route Delhi to Mumbai and assign a truck"
#    → plan_route + assign_vehicle

# 3. Parameters MUST strictly match the tool’s parameter list.
#    ❌ Do NOT add extra parameters
#    ❌ Do NOT omit required parameters if clearly present

# 4. If a required parameter is NOT explicitly mentioned:
#    → set it to null (NOT empty string, NOT guessed)

# 5. Confidence scoring:
#    - 0.9–1.0 → very clear command
#    - 0.7–0.89 → clear but missing minor detail
#    - 0.5–0.69 → ambiguous
#    - <0.5 → DO NOT return this intent

# 6. If the command is vague, unclear, or conversational:
#    → return ONLY the "help" tool

# 7. NEVER explain.
#    NEVER add commentary.
#    OUTPUT JSON ONLY.

# ========================================
# INTENT → TOOL MAPPING HINTS
# ========================================

# Route Planning:
# - "plan", "create", "show route", "go from X to Y" → plan_route
# - "alternate", "avoid traffic", "blocked road" → alternative_route
# - "remove route", "delete route" → remove_route
# - "air + road", "flight + truck", "via plane" → multimodal_route

# Vehicle Operations:
# - "assign vehicle", "add truck", "deploy vehicle" → assign_vehicle
# - "stop vehicle", "reset vehicle", "remove truck" → stop_vehicle
# - "vehicle reached", "completed delivery" → complete_vehicle_route
# - "disable vehicle", "activate vehicle" → vehicle_status_update

# Warehouse:
# - "activate warehouse", "deactivate warehouse" → warehouse_status_update

# System / Map:
# - "clear map", "reset screen" → clear_map
# - "satellite view" → satellite_view
# - "street view" → street_view
# - "clear chat", "reset conversation" → clear_chat

# Special:
# - "connect hub", "hub to capitals" → connect_hub

# ========================================
# USER COMMAND
# ========================================
# "{user_message}"

# ========================================
# OUTPUT FORMAT (STRICT)
# ========================================
# {{
#   "intents": [
#     {{
#       "name": "<tool_name>",
#       "parameters": {{
#         "<param1>": "<value or null>",
#         "<param2>": "<value or null>"
#       }},
#       "confidence": 0.0
#     }}
#   ]
# }}
# """
        
#         messages = [
#             SystemMessage(content="Extract logistics intents from user messages."),
#             HumanMessage(content=prompt)
#         ]
        
#         try:
#             response = await self.llm.ainvoke(messages)
#             result = json.loads(response.content)
            
#             # Validate intents
#             valid_intents = []
#             for intent in result.get("intents", []):
#                 if intent.get("confidence", 0) > 0.5 and intent["name"] in self.mcp.tools:
#                     valid_intents.append(intent)
            
#             state["intents"] = valid_intents
            
#             if valid_intents:
#                 logger.info(f"Detected {len(valid_intents)} intent(s): {[i['name'] for i in valid_intents]}")
#             else:
#                 # Fallback to your existing detection
#                 try:
#                     intent_result = await unified_chat_endpoint_function(
#                         chat_prompt=ChatPrompt(prompt=user_message),
#                         user_id=state["user_id"]
#                     )
                    
#                     if isinstance(intent_result, dict):
#                         state["intents"] = [{
#                             "name": intent_result.get("intent", "help"),
#                             "parameters": intent_result.get("parameters", {}),
#                             "confidence": intent_result.get("confidence", 0.7)
#                         }]
#                     else:
#                         state["intents"] = [{"name": "help", "parameters": {}, "confidence": 1.0}]
#                 except:
#                     state["intents"] = [{"name": "help", "parameters": {}, "confidence": 1.0}]
        
#         except Exception as e:
#             logger.error(f"Intent detection error: {e}")
#             state["intents"] = [{"name": "help", "parameters": {}, "confidence": 1.0}]
        
#         return state

# class MultiToolExecutor:
#     """Executes multiple tools sequentially"""
    
#     def __init__(self, mcp_manager: CompleteMCPServerManager):
#         self.mcp = mcp_manager
    
#     async def execute_all_tools(self, state: AgentState) -> AgentState:
#         """Execute all detected intents in sequence"""
#         if not state.get("intents"):
#             return state
        
#         tool_outputs = []
#         actions = []
#         responses = []
        
#         for intent in state["intents"]:
#             tool_name = intent["name"]
#             params = intent["parameters"]
#             user_id = state["user_id"]
            
#             # Add user_id to params
#             params["user_id"] = user_id
            
#             logger.info(f"Executing {tool_name} with params: {params}")
            
#             try:
#                 result = await self.mcp.call_tool(tool_name, params, user_id)
#                 logger.info(f'result  {type(result )}: {result }')
                
#                 tool_outputs.append({
#                     "tool": tool_name,
#                     "params": params,
#                     # "result": result
#                 })
                
#                 if result.get("success"):
#                     tool_result = result.get("result", {})
#                     logger.info(f'tool_result {type(tool_result)}: {tool_result}')
                    
#                     # Extract response
#                     response_text = self._extract_response(tool_name, tool_result)
#                     responses.append(response_text)
#                     state["messages"].append(AIMessage(content=response_text))
                    
#                     # Extract actions
#                     if isinstance(tool_result, dict):
#                         if "actions" in tool_result:
#                             actions.extend(tool_result["actions"])
#                         elif "action" in tool_result:
#                             actions.append(tool_result["action"])
#                 else:
#                     error_msg = result.get("error", f"Failed to execute {tool_name}")
#                     responses.append(f"❌ {error_msg}")
#                     state["messages"].append(AIMessage(content=f"❌ {error_msg}"))
                    
#             except Exception as e:
#                 error_msg = f"Error executing {tool_name}: {str(e)}"
#                 responses.append(f"❌ {error_msg}")
#                 state["messages"].append(AIMessage(content=f"❌ {error_msg}"))
                
#                 tool_outputs.append({
#                     "tool": tool_name,
#                     "params": params,
#                     # "result": {"error": str(e)}
#                 })
        
#         state["tool_outputs"] = tool_outputs
#         state["actions"] = actions
        
#         # Create final response
#         if responses:
#             if len(responses) == 1:
#                 state["final_response"] = {
#                     "response": responses[0],
#                     "actions": actions
#                 }
#             else:
#                 combined = f"✅ Processed {len(responses)} operations:\n"
#                 for i, resp in enumerate(responses, 1):
#                     combined += f"{i}. {resp}\n"
                
#                 state["final_response"] = {
#                     "response": combined,
#                     "actions": actions
#                 }
        
#         return state
    
#     def _extract_response(self, tool_name: str, result: Any) -> str:
#         """Extract user-friendly response from tool result"""
#         if isinstance(result, dict):
#             if "response_text" in result:
#                 return result["response_text"]
#             elif "message" in result:
#                 return result["message"]
#             elif "response" in result:
#                 return result["response"]
        
#         # Default responses for each tool
#         default_responses = {
#             "plan_route": "✅ Route planned successfully",
#             "assign_vehicle": "✅ Vehicle assigned to route",
#             "stop_vehicle": "✅ Vehicle stopped/reset",
#             "remove_route": "✅ Route removed",
#             "alternative_route": "✅ Alternative route calculated",
#             "multimodal_route": "✈️ Multimodal route planned",
#             "remove_multimodal_route": "✅ Multimodal route removed",
#             "fetch_routes": "📋 Routes information retrieved",
#             "assign_vehicle_multimodal": "✅ Vehicle assigned to multimodal route",
#             "complete_vehicle_route": "✅ Vehicle marked as completed",
#             "reset_all_vehicles": "🔄 All vehicles reset",
#             "warehouse_status_update": "🏢 Warehouse status updated",
#             "vehicle_status_update": "🚚 Vehicle status updated",
#             "assign_plane": "✈️ Plane assigned to route",
#             "clear_map": "🗺️ Map cleared",
#             "satellite_view": "🛰️ Satellite view activated",
#             "street_view": "🏙️ Street view activated",
#             "clear_chat": "💬 Chat cleared",
#             "connect_hub": "🌍 Hub connected to capitals",
#             "help": "Here's what I can help you with:"
#         }
        
#         return default_responses.get(tool_name, f"✅ {tool_name.replace('_', ' ').title()} completed")

# # ==============================================
# # 4. LANGGRAPH WORKFLOW
# # ==============================================

# def build_complete_agent_graph():
#     """Build complete LangGraph workflow with all 21 tools"""
    
#     # Initialize manager
#     mcp_manager = CompleteMCPServerManager()
    
#     # Initialize agents
#     intent_agent = EnhancedIntentDetector(mcp_manager)
#     tool_agent = MultiToolExecutor(mcp_manager)
    
#     # Build graph
#     workflow = StateGraph(AgentState)
    
#     # Add nodes
#     workflow.add_node("detect_intents", intent_agent.detect_intents)
#     workflow.add_node("execute_tools", tool_agent.execute_all_tools)
    
#     # Set entry point
#     workflow.set_entry_point("detect_intents")
    
#     # Route to execution
#     workflow.add_edge("detect_intents", "execute_tools")
#     workflow.add_edge("execute_tools", END)
    
#     # Add memory
#     memory = MemorySaver()
    
#     # Compile
#     app = workflow.compile(checkpointer=memory)
    
#     return app, mcp_manager

# # ==============================================
# # 5. MAIN SERVICE
# # ==============================================

# class CompleteMCPLangGraphService:
#     """Complete service with all 21 tools"""
    
#     def __init__(self):
#         self.graph, self.mcp_manager = build_complete_agent_graph()
#         logger.info("✅ Complete MCP + LangGraph service initialized with 21 tools")
    
#     async def process_message(self, chat_request, user_id: int) -> Dict:
#         """Process message using complete agent"""
#         try:
#             # Get context
#             warehouses = get_warehouses_by_userall(user_id)
#             logger.info(f'warehouses  {type(warehouses )}: {warehouses }')
#             vehicles = get_vehicles_by_user(user_id)
#             logger.info(f'vehicles  {type(vehicles )}: {vehicles }')
            
#             # Prepare state
#             initial_state = AgentState(
                
#                 user_message=chat_request.message,
#                 user_id=user_id,
#                 intents=[],
#                 parameters={},
#                 confidence=0.0,
#                 messages=[],
#                 warehouses=warehouses,
#                 vehicles=vehicles,
#                 tool_outputs=[],
#                 final_response=None,
#                 actions=[]
#             )
#             logger.info(f'initial_state {type(initial_state)}: {initial_state}')
            
#             # Execute graph
#             config = {"configurable": {"thread_id": f"user_{user_id}"}}
#             logger.info(f'config  {type(config )}: {config }')
#             final_state = await self.graph.ainvoke(initial_state, config)
#             logger.info(f'final_state {type(final_state)}: {final_state}')
            
#             # Get response
#             final_response = final_state.get("final_response", {})
#             logger.info(f'final_response  {type(final_response )}: {final_response }')
            
#             # Update chat history
#             memory = get_chat_memory(user_id)
#             memory.add_message(HumanMessage(content=chat_request.message))
            
#             if final_state.get("messages"):
#                 last_assistant_msg = None
#                 for msg in reversed(final_state["messages"]):
#                     if isinstance(msg, AIMessage):
#                         last_assistant_msg = msg
#                         break
                
#                 if last_assistant_msg:
#                     memory.add_message(last_assistant_msg)
            
#             # Format response
#             response_text = final_response.get("response", 
            
#                                               "How can I help you with logistics operations?")
#             logger.info(f'response_text  {type(response_text )}: {response_text }')
#             return {
#                 "success": True,
#                 "response": response_text,
#                 # "actions": final_response.get("actions", []),
#                 "actions": final_response.get("actions", []),
#                 # "tools_used": len(final_state.get("tool_outputs", []))
#             }
            
#         except Exception as e:
#             logger.error(f"Agent processing error: {e}", exc_info=True)
#             return {
#                 "success": False,
#                 "response": "Sorry, something went wrong processing your request.",
#                 "actions": []
#             }
    
#     def get_all_tools(self) -> List[Dict]:
#         """Get complete list of 21 tools"""
#         return self.mcp_manager.get_tools_list()
    
#     async def direct_tool_call(self, tool_name: str, params: Dict, user_id: int) -> Dict:
#         """Direct tool call for testing"""
#         return await self.mcp_manager.call_tool(tool_name, params, user_id)

# # ==============================================
# # 6. FASTAPI ROUTES
# # ==============================================

# # Initialize service

# complete_service = CompleteMCPLangGraphService()

# class ChatRequest(BaseModel):
#     message: str

# class ToolCallRequest(BaseModel):
#     tool: str
#     params: Dict[str, Any]

# @router.on_event("startup")
# async def startup_event():
#     """Initialize on startup"""
#     logger.info("🚀 MCP + LangGraph Agent ready with 21 tools")

# @router.post("/agent-enhanced")
# async def chat_enhanced(req:ChatRequest):
#     """
#     Use this for multi-intent queries
#     """
#     # user_id = current_user.get("user_id")
#     user_id = 1
    
#     if not user_id:
#         raise HTTPException(status_code=401, detail="Invalid token: user_id not found")
    
#     chat_request = ChatRequest(message=req.message)
    
#     return await complete_service.process_message(chat_request, user_id)

# @router.post("/agent-complete")
# async def chat_complete(req: dict, current_user = Depends(get_current_user)):
#     """Complete agent endpoint"""
#     user_id = current_user.get("user_id")
    
#     if not user_id:
#         raise HTTPException(status_code=401, detail="Invalid token")
    
#     chat_request = ChatRequest(message=req["message"])
    
#     return await complete_service.process_message(chat_request, user_id)

# @router.post("/agent-complete/direct")
# async def direct_tool(req: ToolCallRequest, current_user = Depends(get_current_user)):
#     """Direct tool call"""
#     user_id = current_user.get("user_id")
    
#     if not user_id:
#         raise HTTPException(status_code=401, detail="Invalid token")
    
#     result = await complete_service.direct_tool_call(req.tool, req.params, user_id)
    
#     return {
#         "success": "error" not in result,
#         "result": result
#     }

# @router.get("/agent-complete/tools")
# async def list_all_tools():
#     """List all 21 available tools"""
#     tools = complete_service.get_all_tools()
    
#     # Group by category
#     categorized = {}
#     for tool in tools:
#         category = tool.pop("category", "General")
#         if category not in categorized:
#             categorized[category] = []
#         categorized[category].append(tool)
    
#     return {
#         "success": True,
#         "total_tools": len(tools),
#         "tools_by_category": categorized
#     }

# @router.get("/agent-complete/health")
# async def health_check():
#     """Health check"""
#     tools = complete_service.get_all_tools()
    
#     return {
#         "status": "healthy",
#         "service": "Complete MCP + LangGraph Agent",
#         "tools_available": len(tools),
#         "categories": len(set(tool.get("category", "General") for tool in tools))
#     }

# # ==============================================
# # 7. EXPORT
# # ==============================================

# complete_service = CompleteMCPLangGraphService()

# class ChatRequest(BaseModel):
#     message: str
    
# @router.post("/agent-enhanced")
# async def chat_enhanced(req: dict):
#     """
#     Use this for multi-intent queries
#     """
#     # user_id = current_user.get("user_id")
#     user_id = 1
    
#     if not user_id:
#         raise HTTPException(status_code=401, detail="Invalid token: user_id not found")
    
#     chat_request = ChatRequest(message=req["message"])
    
#     return await complete_service.process_message(chat_request, user_id)