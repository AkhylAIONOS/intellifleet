#backend/agents/graph.py
from langgraph.graph import StateGraph, END
from langchain_core.messages import ToolMessage, HumanMessage
from .state import AgentState
from backend.mcp.tools.tool_client import load_mcp_tools
from .token_logger import log_token_usage
import logging
import json
import time
import asyncio
from backend.utilities.response import *

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

log = logging.getLogger(__name__)

class LogisticsAgentGraph:
    """Enhanced LangGraph with schema-aware execution"""
    
    # def __init__(self):
    #     log.info("=" * 80)
    #     log.info("INITIALIZING LOGISTICS AGENT GRAPH")
    #     log.info("=" * 80)
        
    #     self.tools = load_mcp_tools()
    #     # self.tools = asyncio.run(load_mcp_tools())
    #     log.info(f"✅ Loaded {len(self.tools)} tools for graph")
        
    #     self.graph = self._build_graph()
    #     log.info("✅ Graph built and compiled successfully")
    
    
    def __init__(self, tools):
        log.info("=" * 80)
        log.info("INITIALIZING LOGISTICS AGENT GRAPH")
        log.info("=" * 80)

        self.tools = tools
        log.info(f"✅ Using {len(self.tools)} preloaded tools")

        self.graph = self._build_graph()
        log.info("✅ Graph built and compiled successfully")
    
    def _build_graph(self):
        """Build schema-aware LangGraph"""
        log.info("🔨 Building LangGraph workflow...")
        
        graph = StateGraph(AgentState)
        
        # Add nodes
        log.info("  - Adding nodes:")
        graph.add_node("analyze_request", self.analyze_request_node)
        log.info("    ✅ analyze_request")
        
        graph.add_node("extract_parameters", self.extract_parameters_node)
        log.info("    ✅ extract_parameters")
        
        graph.add_node("execute_tools", self.tool_node)
        log.info("    ✅ execute_tools")
        
        graph.add_node("format_response", self.format_response_node)
        log.info("    ✅ format_response")
        
        # Add edges
        log.info("  - Setting up edges:")
        graph.set_entry_point("analyze_request")
        log.info("    ✅ entry_point -> analyze_request")
        
        graph.add_edge("analyze_request", "extract_parameters")
        log.info("    ✅ analyze_request -> extract_parameters")
        
        graph.add_edge("extract_parameters", "execute_tools")
        log.info("    ✅ extract_parameters -> execute_tools")
        
        graph.add_edge("execute_tools", "format_response")
        log.info("    ✅ execute_tools -> format_response")
        
        graph.add_edge("format_response", END)
        log.info("    ✅ format_response -> END")
        
        compiled = graph.compile()
        log.info("✅ Graph compilation complete")
        
        return compiled
    
    async def analyze_request_node(self, state: AgentState) -> dict:
        """Analyze user request to determine needed tools"""
        node_start = time.time()
        log.info(f"🔍 [NODE] analyze_request - User: {state['user_id']}")
        log.debug(f"  Message: '{state['user_message'][:100]}...'")
        
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate
        from backend.config.config import settings
        
        llm = ChatOpenAI(
            model="gpt-5.2-2025-12-11",
            api_key=settings.OPENAI_API_KEY,
            temperature=0
        )
        
        # Build tool descriptions
        tool_descriptions = "\n".join([
            f"- {tool.name}: {tool.description}"
            for tool in self.tools
        ])
        log.debug(f"📋 Tool descriptions prepared for {len(self.tools)} tools")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are a logistics request analyzer. Determine which tool(s) to use.

Available tool names (choose ONLY from this exact list):
{[tool.name for tool in self.tools]}

Tool details:
{tool_descriptions}

You MUST return tool names EXACTLY as written above.
Do NOT invent new names.


User request: {state['user_message']}

Return JSON with:
1. tools: list of tool names needed
2. confidence: confidence score (0-1)
3. reasoning: brief explanation"""),
            ("human", state['user_message'])
        ])
        
        messages = prompt.format_messages()
        log.debug("📤 Sending analysis prompt to LLM")
        
        try:
            response = await llm.ainvoke(messages)
            log_token_usage("graph_tool_selection", state["user_id"], response)
            log.debug(f"📥 LLM response: {response.content[:200]}...")

            import json
            analysis = json.loads(response.content)
            
            tools = analysis.get("tools", [])
            confidence = analysis.get("confidence", 0.5)
            reasoning = analysis.get("reasoning", "")
            
            log.info(f"  - Tools identified: {tools}")
            log.info(f"  - Confidence: {confidence}")
            log.info(f"  - Reasoning: {reasoning}")
            
            elapsed = time.time() - node_start
            log.info(f"⏱️ analyze_request completed in {elapsed:.2f}s")
            
            return {
                "tool_calls": [{"name": tool} for tool in tools],
                "confidence": confidence,
                "messages": state.get("messages", []) + [HumanMessage(content=state['user_message'])]
            }
            
        except json.JSONDecodeError as e:
            log.error(f"❌ Failed to parse LLM response as JSON: {str(e)}")
            log.error(f"Raw response: {response.content}")
            
            elapsed = time.time() - node_start
            log.info(f"⏱️ analyze_request failed in {elapsed:.2f}s")
            
            # Fallback to simple tool detection
            return {
                "tool_calls": [],
                "confidence": 0.3,
                "messages": state.get("messages", []) + [HumanMessage(content=state['user_message'])]
            }
            
        except Exception as e:
            log.error(f"❌ Error in analyze_request: {str(e)}", exc_info=True)
            
            elapsed = time.time() - node_start
            log.info(f"⏱️ analyze_request failed in {elapsed:.2f}s")
            
            return {
                "tool_calls": [],
                "confidence": 0.3,
                "messages": state.get("messages", []) + [HumanMessage(content=state['user_message'])]
            }
    
    async def extract_parameters_node(self, state: AgentState) -> dict:
        """Extract parameters for each tool"""
        node_start = time.time()
        log.info(f"🔧 [NODE] extract_parameters")
        
        if not state.get("tool_calls"):
            log.info("  - No tool calls to extract parameters for")
            elapsed = time.time() - node_start
            log.info(f"⏱️ extract_parameters completed in {elapsed:.2f}s (no-op)")
            return state
        
        tool_calls = state["tool_calls"]
        log.info(f"  - Extracting parameters for {len(tool_calls)} tool(s)")
        
        from langchain_openai import ChatOpenAI
        from backend.config.config import settings
        
        llm = ChatOpenAI(
            model="gpt-5.2-2025-12-11",
            api_key=settings.OPENAI_API_KEY,
            temperature=0
        )
        
        tool_calls_with_params = []
        
        for i, tool_call in enumerate(tool_calls):
            tool_name = tool_call["name"]
            log.info(f"    [{i+1}/{len(tool_calls)}] Processing tool: {tool_name}")
            
            tool = next((t for t in self.tools if t.name == tool_name), None)
            
            if tool:
                # Get tool schema info
                schema_info = ""
                if hasattr(tool, 'args_schema') and tool.args_schema:
                    schema = tool.args_schema.schema()
                    properties = schema.get("properties", {})
                    schema_info = "Required parameters:\n"
                    for param, details in properties.items():
                        schema_info += f"- {param}: {details.get('type', 'any')}"
                        if "description" in details:
                            schema_info += f" ({details['description']})"
                        schema_info += "\n"
                    
                    log.debug(f"      Schema: {list(properties.keys())}")
                
                prompt = f"""Extract parameters for tool '{tool_name}' from user message.
                
                User message: {state['user_message']}
                Tool description: {tool.description}
                
                {schema_info}
                
                Include user_id: {state['user_id']}
                Only include parameters mentioned in user message.
                Return as JSON."""
                
                log.debug(f"      📤 Sending parameter extraction prompt to LLM")
                
                try:
                    response = await llm.ainvoke(prompt)
                    log_token_usage("graph_param_extraction", state["user_id"], response)
                    log.debug(f"      📥 LLM response: {response.content[:200]}...")
                    
                    import json
                    params = json.loads(response.content)
                    params["user_id"] = state["user_id"]
                    
                    log.info(f"      ✅ Extracted parameters: {json.dumps(params, indent=2)}")
                    
                    tool_calls_with_params.append({
                        "name": tool_name,
                        "args": params,
                        "id": f"call_{len(tool_calls_with_params)}"
                    })
                    
                except json.JSONDecodeError as e:
                    log.error(f"      ❌ Failed to parse parameters as JSON: {str(e)}")
                    log.error(f"      Raw response: {response.content}")
                    
                    # Use minimal params
                    log.warning(f"      ⚠️ Using minimal params (user_id only)")
                    tool_calls_with_params.append({
                        "name": tool_name,
                        "args": {"user_id": state["user_id"]},
                        "id": f"call_{len(tool_calls_with_params)}"
                    })
                    
                except Exception as e:
                    log.error(f"      ❌ Error extracting parameters: {str(e)}", exc_info=True)
                    
                    # Use minimal params
                    log.warning(f"      ⚠️ Using minimal params (user_id only)")
                    tool_calls_with_params.append({
                        "name": tool_name,
                        "args": {"user_id": state["user_id"]},
                        "id": f"call_{len(tool_calls_with_params)}"
                    })
            else:
                log.error(f"      ❌ Tool '{tool_name}' not found")
        
        log.info(f"  ✅ Extracted parameters for {len(tool_calls_with_params)}/{len(tool_calls)} tools")
        
        elapsed = time.time() - node_start
        log.info(f"⏱️ extract_parameters completed in {elapsed:.2f}s")
        
        return {"tool_calls": tool_calls_with_params}
    
    async def tool_node(self, state: AgentState) -> dict:
        """Execute tools directly without ToolExecutor"""
        node_start = time.time()
        log.info(f"⚙️ [NODE] execute_tools")
        
        tool_results = []
        tool_calls = state.get("tool_calls", [])
        
        if not tool_calls:
            log.info("  - No tool calls to execute")
            elapsed = time.time() - node_start
            log.info(f"⏱️ execute_tools completed in {elapsed:.2f}s (no-op)")
            return {"tool_results": []}
        
        log.info(f"  - Executing {len(tool_calls)} tool(s)")
        
        for i, tool_call in enumerate(tool_calls):
            tool_name = tool_call["name"]
            args = tool_call.get("args", {})
            
            log.info(f"    [{i+1}/{len(tool_calls)}] Executing: {tool_name}")
            log.debug(f"      Args: {json.dumps(args, indent=2)}")
            
            try:
                tool = next(
                    (t for t in self.tools if t.name == tool_name),
                    None
                )
                
                if not tool:
                    error_msg = f"Tool '{tool_name}' not found"
                    log.error(f"      ❌ {error_msg}")
                    
                    tool_results.append({
                        "tool": tool_name,
                        "result": {"error": error_msg},
                        "success": False,
                        "call_id": tool_call.get("id", f"call_{i}")
                    })
                    continue
                
                log.debug(f"      🔧 Tool found: {tool_name}")
                
                # Execute tool
                tool_start = time.time()
                # result = await tool.arun(**args)
                result = await tool.ainvoke(args)

                
                tool_elapsed = time.time() - tool_start
                
                log.info(f"      ✅ Execution completed in {tool_elapsed:.2f}s")
                log.debug(f"      Result: {json.dumps(result, indent=2)[:500]}...")
                
                # Keep path in result for actions but strip it from graph state
                result_for_state = {k: v for k, v in result.items() if k != "path"}
                tool_results.append({
                    "tool": tool_name,
                    "result": result_for_state,
                    "full_result": result,
                    "success": True,
                    "call_id": tool_call.get("id", f"call_{i}")
                })
                
            except Exception as e:
                log.error(f"      ❌ Tool execution failed: {str(e)}", exc_info=True)
                
                tool_results.append({
                    "tool": tool_name,
                    "result": {"error": str(e)},
                    "success": False,
                    "call_id": tool_call.get("id", f"call_{i}")
                })
        
        successful = sum(1 for r in tool_results if r["success"])
        log.info(f"  ✅ {successful}/{len(tool_calls)} tools executed successfully")
        
        elapsed = time.time() - node_start
        log.info(f"⏱️ execute_tools completed in {elapsed:.2f}s")
        
        return {"tool_results": tool_results}
    
    # async def format_response_node(self, state: AgentState) -> dict:
    #     """Format final response from tool results"""
    #     node_start = time.time()
    #     log.info(f"📝 [NODE] format_response")
        
    #     tool_results = state.get("tool_results", [])
        
    #     if not tool_results:
    #         log.info("  - No tool results to format")
            
    #         elapsed = time.time() - node_start
    #         log.info(f"⏱️ format_response completed in {elapsed:.2f}s")
            
    #         return {
    #             "response": "I couldn't determine the right action. Can you rephrase?",
    #             "success": False,
    #             "actions": []
    #         }
        
    #     log.info(f"  - Formatting {len(tool_results)} tool result(s)")
        
    #     # Build response from successful tool executions
    #     successful_results = [r for r in tool_results if r["success"]]
    #     failed_results = [r for r in tool_results if not r["success"]]
        
    #     log.info(f"    ✅ Successful: {len(successful_results)}")
    #     log.info(f"    ❌ Failed: {len(failed_results)}")
        
    #     if not successful_results:
    #         log.warning("  ⚠️ No successful tool executions")
            
    #         elapsed = time.time() - node_start
    #         log.info(f"⏱️ format_response completed in {elapsed:.2f}s")
            
    #         return {
    #             "response": "Failed to execute the requested actions.",
    #             "success": False,
    #             "actions": []
    #         }
        
    #     actions = []

    #     for result in successful_results:
    #         # Use full_result (includes path) for actions sent to frontend
    #         tool_result = result.get("full_result", result["result"])

    #         if isinstance(tool_result, dict):
    #             clean_data = {k: v for k, v in tool_result.items() if k != "message"}
    #             actions.append({
    #                 "type": result["tool"],
    #                 "data": clean_data
    #             })

    #     # Ask LLM for a conversational summary (no path, no message)
    #     from langchain_openai import ChatOpenAI
    #     from langchain_core.messages import HumanMessage as LCHumanMessage
    #     from backend.config.config import settings

    #     llm = ChatOpenAI(
    #         model="gpt-5.2-2025-12-11",
    #         api_key=settings.OPENAI_API_KEY,
    #         temperature=0
    #     )

    #     def strip_encoded(obj):
    #         """Recursively remove path/polyline/message fields."""
    #         if isinstance(obj, dict):
    #             return {k: strip_encoded(v) for k, v in obj.items() if k not in ("path", "polyline", "message")}
    #         if isinstance(obj, list):
    #             return [strip_encoded(i) for i in obj]
    #         return obj

    #     results_for_llm = [
    #         strip_encoded(r["result"])
    #         for r in successful_results
    #         if isinstance(r.get("result"), dict)
    #     ]

    #     prompt = (
    #         f"The user asked: \"{state['user_message']}\"\n\n"
    #         f"The following actions were executed successfully:\n"
    #         f"{json.dumps(results_for_llm, indent=2)}\n\n"
    #         "Reply to the user in a natural, conversational tone summarising what was done. "
    #         "Include key details (locations, distance, duration, cost, etc.) where relevant. "
    #         "Keep it concise — 1-3 sentences."
    #     )

    #     try:
    #         llm_response = await llm.ainvoke([LCHumanMessage(content=prompt)])
    #         log_token_usage("graph_format_response", state["user_id"], llm_response)
    #         final_response = llm_response.content
    #     except Exception as e:
    #         log.warning(f"⚠️ LLM response generation failed, using fallback: {e}")
    #         final_response = "Actions completed successfully."

    #     log.info(f"  ✅ Final response: '{final_response[:200]}...'")

    #     elapsed = time.time() - node_start
    #     log.info(f"⏱️ format_response completed in {elapsed:.2f}s")

    #     return {
    #         "response": final_response,
    #         "success": True,
    #         "actions": actions,
    #     }

    # async def format_response_node(self, state: AgentState) -> dict:
    #     """Format final response from tool results"""
    #     node_start = time.time()
    #     log.info(f"📝 [NODE] format_response")

    #     tool_results = state.get("tool_results", [])

    #     if not tool_results:
    #         log.info("  - No tool results to format")
    #         elapsed = time.time() - node_start
    #         log.info(f"⏱️ format_response completed in {elapsed:.2f}s")
    #         return {
    #             "response": "I couldn't determine the right action. Can you rephrase?",
    #             "success": False,
    #             "actions": [],
    #         }

    #     log.info(f"  - Formatting {len(tool_results)} tool result(s)")

    #     successful_results = [r for r in tool_results if r["success"]]
    #     failed_results     = [r for r in tool_results if not r["success"]]

    #     log.info(f"    ✅ Successful: {len(successful_results)}")
    #     log.info(f"    ❌ Failed: {len(failed_results)}")

    #     if not successful_results:
    #         log.warning("  ⚠️ No successful tool executions")
    #         elapsed = time.time() - node_start
    #         log.info(f"⏱️ format_response completed in {elapsed:.2f}s")
    #         return {
    #             "response": "Failed to execute the requested actions.",
    #             "success": False,
    #             "actions": [],
    #         }

    #     actions = []

    #     for result in successful_results:
    #         tool_result = result.get("full_result", result["result"])

    #         if not isinstance(tool_result, dict):
    #             continue

    #         # ── If the tool already produced a structured actions list
    #         #    (e.g. partial_assignment_start + animate_segment), pass them
    #         #    straight through — no re-wrapping needed.
    #         if tool_result.get("actions"):
    #             actions.extend(tool_result["actions"])
    #             log.info(
    #                 f"    ↪ Passthrough {len(tool_result['actions'])} actions "
    #                 f"from tool '{result['tool']}'"
    #             )
    #             continue

    #         # ── Legacy path: wrap the whole result as a single action ──────────
    #         clean_data = {k: v for k, v in tool_result.items() if k != "message"}
    #         actions.append({"type": result["tool"], "data": clean_data})

    #     # ── LLM conversational summary ──────────────────────────────────────────
    #     from langchain_openai import ChatOpenAI
    #     from langchain_core.messages import HumanMessage as LCHumanMessage
    #     from backend.config.config import settings

    #     llm = ChatOpenAI(
    #         model="gpt-5.2-2025-12-11",
    #         api_key=settings.OPENAI_API_KEY,
    #         temperature=0,
    #     )

    #     def strip_encoded(obj):
    #         if isinstance(obj, dict):
    #             return {
    #                 k: strip_encoded(v)
    #                 for k, v in obj.items()
    #                 if k not in ("path", "polyline", "message", "actions")
    #             }
    #         if isinstance(obj, list):
    #             return [strip_encoded(i) for i in obj]
    #         return obj

    #     # Prefer response_text from the tool if available (already summarised)
    #     pre_built_summary = next(
    #         (
    #             r["result"].get("response_text")
    #             for r in successful_results
    #             if isinstance(r.get("result"), dict) and r["result"].get("response_text")
    #         ),
    #         None,
    #     )

    #     if pre_built_summary:
    #         final_response = pre_built_summary
    #         log.info("  ↪ Using pre-built response_text from tool result")
    #     else:
    #         results_for_llm = [
    #             strip_encoded(r["result"])
    #             for r in successful_results
    #             if isinstance(r.get("result"), dict)
    #         ]

    #         prompt = (
    #             f"The user asked: \"{state['user_message']}\"\n\n"
    #             f"The following actions were executed successfully:\n"
    #             f"{json.dumps(results_for_llm, indent=2)}\n\n"
    #             "Reply to the user in a natural, conversational tone summarising what was done. "
    #             "Include key details (locations, distance, duration, cost, etc.) where relevant. "
    #             "Keep it concise — 1-3 sentences."
    #         )

    #         try:
    #             llm_response  = await llm.ainvoke([LCHumanMessage(content=prompt)])
    #             log_token_usage("graph_format_response", state["user_id"], llm_response)
    #             final_response = llm_response.content
    #         except Exception as e:
    #             log.warning(f"⚠️ LLM response generation failed, using fallback: {e}")
    #             final_response = "Actions completed successfully."

    #     log.info(f"  ✅ Final response: '{final_response[:200]}...'")

    #     elapsed = time.time() - node_start
    #     log.info(f"⏱️ format_response completed in {elapsed:.2f}s")

    #     return {
    #         "response": final_response,
    #         "success": True,
    #         "actions": actions,
    #     }
    

    async def format_response_node(self, state: AgentState) -> dict:
        """Format final response from tool results"""
        node_start = time.time()
        log.info(f"📝 [NODE] format_response")

        tool_results = state.get("tool_results", [])

        if not tool_results:
            log.info("  - No tool results to format")
            elapsed = time.time() - node_start
            log.info(f"⏱️ format_response completed in {elapsed:.2f}s")
            return {
                "response": "I couldn't determine the right action. Can you rephrase?",
                "success": False,
                "actions": [],
            }

        log.info(f"  - Formatting {len(tool_results)} tool result(s)")

        successful_results = [r for r in tool_results if r["success"]]
        failed_results     = [r for r in tool_results if not r["success"]]

        log.info(f"    ✅ Successful: {len(successful_results)}")
        log.info(f"    ❌ Failed: {len(failed_results)}")

        if not successful_results:
            log.warning("  ⚠️ No successful tool executions")
            elapsed = time.time() - node_start
            log.info(f"⏱️ format_response completed in {elapsed:.2f}s")
            return {
                "response": "Failed to execute the requested actions.",
                "success": False,
                "actions": [],
            }

        def normalize_to_dict(obj) -> dict | None:
            """Coerce Pydantic models, dataclasses, or plain dicts to dict."""
            if isinstance(obj, dict):
                return obj
            if hasattr(obj, "model_dump"):   # Pydantic v2
                return obj.model_dump()
            if hasattr(obj, "dict"):         # Pydantic v1
                return obj.dict()
            log.warning(f"  ⚠️ Cannot normalize tool result of type {type(obj)} — skipping")
            return None

        actions = []

        for result in successful_results:
            raw = result.get("full_result", result["result"])
            tool_result = normalize_to_dict(raw)

            if tool_result is None:
                continue

            # ── If the tool logically failed, produce no actions ───────────────
            if tool_result.get("success") is False:
                log.info(
                    f"    ↪ Tool '{result['tool']}' reported success=False — skipping action"
                )
                continue

            # ── If the tool already produced a structured actions list
            #    (e.g. partial_assignment_start + animate_segment), pass them
            #    straight through — no re-wrapping needed.
            if tool_result.get("actions"):
                actions.extend(tool_result["actions"])
                log.info(
                    f"    ↪ Passthrough {len(tool_result['actions'])} actions "
                    f"from tool '{result['tool']}'"
                )
                continue

            # ── Legacy path: wrap the whole result as a single action ──────────
            # Exclude "message" and "actions" — actions belong at top level only
            clean_data = {k: v for k, v in tool_result.items() if k not in ("message", "actions")}
            actions.append({"type": result["tool"], "data": clean_data})

        # ── LLM conversational summary ──────────────────────────────────────────
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage as LCHumanMessage
        from backend.config.config import settings

        llm = ChatOpenAI(
            model="gpt-5.2-2025-12-11",
            api_key=settings.OPENAI_API_KEY,
            temperature=0,
        )

        def strip_encoded(obj):
            if isinstance(obj, dict):
                return {
                    k: strip_encoded(v)
                    for k, v in obj.items()
                    if k not in ("path", "polyline", "message", "actions")
                }
            if isinstance(obj, list):
                return [strip_encoded(i) for i in obj]
            return obj

        # Prefer response_text from the tool if available (already summarised),
        # fall back to "message" field for tools that only set that field on failure.
        def _get_summary(r) -> str | None:
            d = normalize_to_dict(r.get("result"))
            if not isinstance(d, dict):
                return None
            return d.get("response_text") or d.get("message") or None

        pre_built_summary = next(
            (s for r in successful_results if (s := _get_summary(r))),
            None,
        )

        if pre_built_summary:
            final_response = clean_llm_response(pre_built_summary)
            log.info("  ↪ Using pre-built response_text from tool result")
        else:
            results_for_llm = [
                strip_encoded(normalize_to_dict(r["result"]))
                for r in successful_results
                if normalize_to_dict(r.get("result")) is not None
            ]

            prompt = (
                f"The user asked: \"{state['user_message']}\"\n\n"
                f"The following actions were executed successfully:\n"
                f"{json.dumps(results_for_llm, indent=2)}\n\n"
                "Reply to the user in a natural, conversational tone summarising what was done. "
                "Include key details (locations, distance, duration, cost, etc.) where relevant. "
                "Keep it concise — 1-3 sentences."
            )

            try:
                llm_response  = await llm.ainvoke([LCHumanMessage(content=prompt)])
                log_token_usage("graph_format_response", state["user_id"], llm_response)
                final_response = clean_llm_response(llm_response.content)
            except Exception as e:
                log.warning(f"⚠️ LLM response generation failed, using fallback: {e}")
                final_response = "Actions completed successfully."

        log.info(f"  ✅ Final response: '{final_response[:200]}...'")

        elapsed = time.time() - node_start
        log.info(f"⏱️ format_response completed in {elapsed:.2f}s")

        return {
            "response": final_response,
            "success": True,
            "actions": actions,
        }


    async def invoke(self, user_id: int, message: str) -> dict:
        """Main entry point"""
        log.info("=" * 80)
        log.info(f"GRAPH INVOKE - User: {user_id}")
        log.info(f"Message: '{message}'")
        log.info("=" * 80)
        
        start_time = time.time()
        
        initial_state = AgentState(
            user_id=user_id,
            user_message=message,
            tool_calls=[],
            tool_results=[],
            messages=[],
            response=None,
            confidence=1.0,
            intent=None,
            actions=[],
            success=True
        )
        
        log.info("🚀 Invoking graph workflow...")
        
        try:
            result = await self.graph.ainvoke(initial_state)
            
            elapsed = time.time() - start_time
            log.info(f"✅ Graph invocation completed in {elapsed:.2f}s")
            log.info(f"📤 Result: success={result.get('success', True)}, response='{result.get('response', '')[:100]}...'")
            
            return {
                "success": result.get("success", True),
                "response": result.get("response", "No response generated"),
                "actions": result.get("actions", [])
            }
            
        except Exception as e:
            elapsed = time.time() - start_time
            log.error(f"❌ Graph invocation failed in {elapsed:.2f}s: {str(e)}", exc_info=True)
            
            return {
                "success": False,
                "response": f"Graph execution failed: {str(e)}",
                "actions": []
            }