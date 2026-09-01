#backend/agents/supervisor.py
import time
import json
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from .graph import LogisticsAgentGraph
from backend.config.config import settings
from backend.database.database import get_warehouses_by_userall, get_vehicles_by_user
from ..mcp.tools.tool_client import load_mcp_tools
from .token_logger import log_token_usage
from backend.config.redis import add_data, get_data
from backend.utilities.response import *
import logging


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: build a single history entry
# ---------------------------------------------------------------------------
def _make_entry(role: str, content: str) -> dict:
    """Return a normalised chat history entry."""
    return {"role": role, "content": content}

HISTORY_WINDOW = 10

def _history_to_lc_messages(history: list, n: int = HISTORY_WINDOW) -> list:
    from langchain_core.messages import AIMessage
    windowed = history[-n:] if len(history) > n else history
    lc = []
    for entry in windowed:
        if entry["role"] == "user":
            lc.append(HumanMessage(content=entry["content"]))
        else:
            lc.append(AIMessage(content=entry["content"]))
    return lc

# At the top of supervisor.py, after imports
from difflib import get_close_matches

def _fuzzy_match_warehouse(value: str, warehouse_names: list[str]) -> str | None:
    """
    Case-insensitive + fuzzy match a user-supplied string against known warehouse names.
    Returns the best match or None if nothing is close enough.
    """
    if not value or not warehouse_names:
        return None

    # Exact case-insensitive match first (fastest path)
    lower_map = {w.lower(): w for w in warehouse_names}
    if value.lower() in lower_map:
        return lower_map[value.lower()]

    # Fuzzy match against lowercased names
    close = get_close_matches(
        value.lower(),
        lower_map.keys(),
        n=1,
        cutoff=0.6   # 0.6 = tolerates ~1-2 char typos; lower = more permissive
    )
    if close:
        matched = lower_map[close[0]]
        logger.info(f"  🔤 Fuzzy matched '{value}' → '{matched}'")
        return matched

    logger.warning(f"  ⚠️ No fuzzy match found for '{value}' in {warehouse_names}")
    return None

class SchemaAwareSupervisor:
    """Enhanced supervisor with schema-aware tool selection and Redis chat memory."""

    def __init__(self):
        logger.info("=" * 80)
        logger.info("INITIALIZING SCHEMA AWARE SUPERVISOR")
        logger.info("=" * 80)

        self.llm = None
        if settings.OPENAI_API_KEY:
            self.llm = ChatOpenAI(
                model="gpt-5.2-2025-12-11",
                api_key=settings.OPENAI_API_KEY,
                temperature=0
            )
            logger.info("✅ LLM initialized with model: gpt-5.2-2025-12-11")
        else:
            logger.warning("OPENAI_API_KEY is not configured; AI chat is unavailable")

        self.tools = []
        self.tool_metadata = {}
        logger.info("⏳ Tools will be initialized asynchronously")


    def _normalize_warehouse_params(self, params: dict, user_id: int) -> dict:
        """
        For any warehouse-name fields in params, fuzzy-correct them
        against the actual warehouse list for this user.
        """
        warehouses = get_warehouses_by_userall(user_id)
        warehouse_names = [w["name"] for w in warehouses]

        # All field names that carry a warehouse name
        warehouse_fields = {"source", "destination", "warehouse_name", "origin", "from", "to"}

        for field in warehouse_fields:
            if field in params and isinstance(params[field], str):
                original = params[field]
                corrected = _fuzzy_match_warehouse(original, warehouse_names)
                if corrected and corrected != original:
                    logger.info(f"  📍 Corrected '{field}': '{original}' → '{corrected}'")
                    params[field] = corrected
                elif not corrected:
                    # Leave as-is; schema validation will catch it as missing/invalid
                    logger.warning(f"  ⚠️ Could not resolve warehouse '{original}' for field '{field}'")

        return params
    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    async def _load_history(self, user_id: int) -> list:
        """Load conversation history from Redis (returns [] if none)."""
        data = await get_data(user_id)
        if data is None:
            return []
        # get_data already returns a parsed list
        return data if isinstance(data, list) else []

    async def _save_history(self, user_id: int, history: list) -> None:
        """Persist updated conversation history to Redis."""
        await add_data(user_id, history)

    async def _append_and_save(
        self,
        user_id: int,
        history: list,
        role: str,
        content: str,
    ) -> list:
        """Append one entry to history, persist, and return the updated list."""
        history.append(_make_entry(role, content))
        await self._save_history(user_id, history)
        return history
    # ------------------------------------------------------------------
    # Existing private helpers (unchanged logic, history param added)
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_encoded_fields(obj):
        if isinstance(obj, dict):
            return {
                k: SchemaAwareSupervisor._strip_encoded_fields(v)
                for k, v in obj.items()
                if k not in ("path", "polyline")
            }
        if isinstance(obj, list):
            return [SchemaAwareSupervisor._strip_encoded_fields(i) for i in obj]
        return obj

    @staticmethod
    def _is_tool_success(tool_name: str, result: dict) -> bool:
        # 1. Explicit bool `success` field always wins (assign_vehicle, alternative_route, …)
        if "success" in result:
            return result["success"] is True

        # 2. Bool `status` field (PlanMultimodalRouteOutput uses status: bool)
        if isinstance(result.get("status"), bool):
            return result["status"] is True

        # 3. Tool-specific checks for outputs that have neither flag
        if tool_name == "plan_route":
            return bool(result.get("optimal_routes")) and result.get("route_id", 0) != 0

        # 4. Default: success when no error key is present
        return "error" not in result

    async def _llm_response(
        self,
        user_message: str,
        tool_name: str,
        result: dict,
        user_id: int = 0,
    ) -> str:
        try:
            result_for_llm = self._strip_encoded_fields(result)
            prompt = (
                f"The user asked: \"{user_message}\"\n\n"
                f"The action '{tool_name}' was executed successfully with this result:\n"
                f"{json.dumps(result_for_llm, indent=2)}\n\n"
                "Reply to the user in a natural, conversational tone summarising what was done. "
                "Include key details (locations, distance, duration, cost, etc.) where relevant. "
                "Keep it concise — 1-3 sentences."
            )
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            log_token_usage("llm_response", user_id, response)
            return clean_llm_response(response.content)
        except Exception as e:
            logger.warning(f"⚠️ LLM response generation failed, using fallback: {e}")
            return str(result.get("message", "Operation completed successfully."))

    def _build_tool_metadata(self) -> Dict[str, Dict]:
        logger.info("🔧 Building tool metadata...")
        metadata = {}
        for tool in self.tools:
            if hasattr(tool, "get_tool_metadata"):
                metadata[tool.name] = tool.get_tool_metadata()
            else:
                metadata[tool.name] = {
                    "name": tool.name,
                    "description": tool.description,
                    "has_schema": False,
                }
        logger.info(f"✅ Built metadata for {len(metadata)} tools")
        return metadata

    def _get_domain_prompt(self, user_id: int) -> str:
        warehouses = get_warehouses_by_userall(user_id)
        vehicles = get_vehicles_by_user(user_id)
        warehouse_names = [w["name"] for w in warehouses]
        vehicle_types = sorted({v["type"] for v in vehicles})

        tools_by_domain = {
            "Route Planning": [
                "plan_route", "multimodal_route",
                "alternative_route", "fetch_routes",
            ],
            "Vehicle Management": [
                "assign_vehicle", "reset_vehicle", "complete_vehicle_route",
                "reset_all_vehicles", "vehicle_status_update"
            ],
            "Route Management": [
                "remove_route", "remove_multimodal_route", "route_status_update",
            ],
            "Warehouse Management": ["warehouse_status_update"],
            "Map & Display": ["clear_map", "satellite_view", "street_view"],
            "Chat & Help": ["clear_chat", "help"],
            "Disruption Management": ["manage_disruption_tool"]
        }

        tool_info = []
        for domain, tools in tools_by_domain.items():
            available_tools = [t for t in tools if t in self.tool_metadata]
            if available_tools:
                tool_info.append(f"\n**{domain}:**")
                for tool_name in available_tools:
                    meta = self.tool_metadata[tool_name]
                    tool_info.append(f"• {tool_name}: {meta.get('description', 'No description')}")

        tool_list = "\n".join(tool_info)

        return f"""You are an intelligent logistics assistant. Help users with route planning, vehicle assignment, and logistics management.

**Available Warehouses:** {', '.join(warehouse_names) if warehouse_names else 'None (upload CSV first)'}
**Available Vehicle Types:** {', '.join(vehicle_types) if vehicle_types else 'None'}

**IMPORTANT RULES:**
1. Only use warehouse names from the list above
2. Check vehicle availability before assignment
3. For route planning, you need source and destination
4. For vehicle assignment, you need route_id and capacity

**AVAILABLE TOOLS:**
{tool_list}

**RESPONSE FORMAT:**
1. Understand user request
2. Select appropriate tool(s)
3. Extract required parameters from user message
4. If missing required parameters, ask for clarification
5. Execute tool(s) and return results

**PARAMETER EXTRACTION:**
- route_id: numeric ID (e.g., "route 5" -> 5)
- vehicle_id: numeric ID (e.g., "truck 3" -> 3)
- capacity: integer (e.g., "capacity 100" -> 100)
- warehouse_name: exact name from warehouse list
- source/destination: warehouse names only

If warehouses list is empty, ask user to upload CSV first."""

    async def _select_tools_for_intent(
        self, user_message: str, user_id: int, history: list
    ) -> List[str]:
        logger.info(f"🎯 Selecting tools - User: {user_id}, Message: '{user_message[:50]}...'")
        start_time = time.time()

        # Prepend conversation history so the LLM has context
        history_messages = _history_to_lc_messages(history)[:-1]

        messages = (
            [SystemMessage(content=self._get_domain_prompt(user_id))]
            + history_messages
            + [HumanMessage(content=(
                f"User message: {user_message}\n\n"
                "Which tools are needed? Return tool names only, comma-separated."
            ))]
        )

        try:
            response = await self.llm.ainvoke(messages)
            log_token_usage("tool_selection", user_id, response)

            tool_names = [n.strip() for n in response.content.split(",") if n.strip()]
            available_tools = [n for n in tool_names if n in self.tool_metadata]

            logger.info(f"  - LLM suggested: {tool_names} → available: {available_tools}")
            logger.info(f"⏱️ Tool selection in {time.time() - start_time:.2f}s")
            return available_tools

        except Exception as e:
            logger.error(f"❌ Error in tool selection: {str(e)}", exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_message(self, user_id: int, message: str) -> Dict[str, Any]:
        logger.info("=" * 80)
        logger.info(f"PROCESSING MESSAGE - User: {user_id}  |  '{message}'")
        logger.info("=" * 80)
        start_time = time.time()

        # ── 1. Load history & record the incoming user message ──────────
        history = await self._load_history(user_id)
        history = await self._append_and_save(user_id, history, "user", message)

        try:
            # ── 2. Select tools ─────────────────────────────────────────
            selected_tools = await self._select_tools_for_intent(message, user_id, history)

            # ── 3a. No tool needed → direct LLM response ────────────────
            if not selected_tools:
                logger.info("ℹ️ No tools needed — direct LLM response")

                history_messages = _history_to_lc_messages(history[:-1])  # exclude current user msg (already in list)
                messages = (
                    [SystemMessage(content=self._get_domain_prompt(user_id))]
                    + history_messages
                    + [HumanMessage(content=message)]
                )

                response = await self.llm.ainvoke(messages)
                log_token_usage("direct_response", user_id, response)
                reply = clean_llm_response(response.content)

                # Save assistant reply
                history = await self._append_and_save(user_id, history, "assistant", reply)

                logger.info(f"⏱️ Direct response in {time.time() - start_time:.2f}s")
                return {"success": True, "response": reply, "actions": []}

            # ── 3b. Single tool ──────────────────────────────────────────
            if len(selected_tools) == 1:
                tool_name = selected_tools[0]
                logger.info(f"🛠️ Single tool: {tool_name}")
                tool = next((t for t in self.tools if t.name == tool_name), None)

                if not tool:
                    error_msg = f"Tool '{tool_name}' not available"
                    history = await self._append_and_save(user_id, history, "assistant", error_msg)
                    return {"success": False, "response": error_msg, "actions": []}

                # Extract parameters
                schema_dict = tool.args_schema.model_json_schema()
                param_messages = [
                    SystemMessage(content=f"""
You are extracting parameters for tool: {tool_name}

User message:
{message}

Tool description:
{tool.description}

EXPECTED JSON SCHEMA:
{json.dumps(schema_dict, indent=2)}

STRICT RULES:
- Use EXACT field names from schema
- Do NOT invent new fields
- Do NOT rename fields
- Do NOT add extra attributes
- Return ONLY valid JSON
- Include user_id: {user_id}
- If a required field is missing, return an empty JSON object {{}}
"""),
                    HumanMessage(content=message),
                ]

                param_response = await self.llm.ainvoke(param_messages)
                log_token_usage("param_extraction", user_id, param_response)

                try:
                    params = json.loads(param_response.content)
                    params["user_id"] = user_id
                    
                    params = self._normalize_warehouse_params(params, user_id)

                    # Validate schema
                    try:
                        validated = tool.args_schema.model_validate(params)
                    except Exception as e:
                        missing_fields = [
                            err["loc"][0]
                            for err in e.errors()
                            if err["type"] == "missing"
                        ]
                        clarify_msg = (
                            f"Missing required information: {', '.join(missing_fields)}. Please provide it."
                            if missing_fields
                            else "Invalid input provided."
                        )
                        # Save clarification request as assistant turn
                        history = await self._append_and_save(
                            user_id, history, "assistant", clarify_msg
                        )
                        return {"success": False, "response": clarify_msg, "actions": []}

                    # Execute tool
                    logger.info(f"⚙️ Executing {tool_name}")
                    tool_start = time.time()
                    result = await tool.ainvoke(validated.model_dump())
                    logger.info(f"✅ Tool done in {time.time() - tool_start:.2f}s")

                    # Tool failure (domain-level) — return empty actions regardless of tool
                    if not self._is_tool_success(tool_name, result):
                        failure_msg = await self._llm_response(message, tool_name, result, user_id)
                        history = await self._append_and_save(
                            user_id, history, "assistant", failure_msg
                        )
                        return {"success": True, "response": failure_msg, "actions": []}

                    # Build conversational reply
                    llm_reply = await self._llm_response(message, tool_name, result, user_id)

                    # Persist the assistant's reply
                    # history = await self._append_and_save(
                    #     user_id, history, "assistant", llm_reply
                    # )

                    HISTORY_CLEARING_TOOLS = {"clear_chat"}

                    if tool_name not in HISTORY_CLEARING_TOOLS:
                        history = await self._append_and_save(
                            user_id, history, "assistant", llm_reply
                        )


                    if tool_name != "plan_multimodal_route":
                        result.pop("message", None)

                    if result.get("actions"):
                        # Tool produced its own structured action list — pass through directly
                        actions_out = result["actions"]
                    else:
                        # Legacy wrap — exclude "actions" so it never appears nested in data
                        clean_data = {k: v for k, v in result.items() if k != "actions"}
                        actions_out = [{"type": tool_name, "data": clean_data}]

                    logger.info(f"⏱️ Total: {time.time() - start_time:.2f}s")
                    return {
                        "success": True,
                        "response": llm_reply,
                        "actions": actions_out,
                    }

                except json.JSONDecodeError as e:
                    error_msg = "Could not extract parameters: Invalid JSON format"
                    logger.error(f"❌ JSON parse error: {e}")
                    history = await self._append_and_save(
                        user_id, history, "assistant", error_msg
                    )
                    return {"success": False, "response": error_msg, "actions": []}

                except Exception as e:
                    error_msg = f"Tool execution failed: {str(e)}"
                    logger.error(f"❌ {error_msg}", exc_info=True)
                    history = await self._append_and_save(
                        user_id, history, "assistant", error_msg
                    )
                    return {"success": False, "response": error_msg, "actions": []}

            # ── 3c. Multiple tools → delegate to graph ───────────────────
            logger.info(f"🔗 {len(selected_tools)} tools → LangGraph")
            graph = LogisticsAgentGraph(self.tools)
            result = await graph.invoke(user_id, message)

            # Save whatever the graph returned
            graph_reply = result.get("response", "")
            if graph_reply:
                history = await self._append_and_save(
                    user_id, history, "assistant", graph_reply
                )

            logger.info(f"⏱️ Total: {time.time() - start_time:.2f}s")
            return result

        except Exception as e:
            error_msg = f"Error processing request: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            history = await self._append_and_save(user_id, history, "assistant", error_msg)
            return {"success": False, "response": error_msg, "actions": []}

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    async def initialize(self):
        logger.info("🚀 Loading MCP tools...")
        try:
            self.tools = await load_mcp_tools()
            logger.info(f"✅ Loaded {len(self.tools)} tools: {[t.name for t in self.tools]}")
            self.tool_metadata = self._build_tool_metadata()
            logger.info("✅ Supervisor ready")
        except Exception as e:
            logger.error(f"❌ Init failed: {str(e)}", exc_info=True)
            raise


# Singleton
supervisor = SchemaAwareSupervisor()
