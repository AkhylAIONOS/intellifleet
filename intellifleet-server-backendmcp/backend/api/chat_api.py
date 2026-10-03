#backend/api/chat_api.py
from unittest import result

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from backend.routes.auth import get_current_user
from backend.agents.supervisor import supervisor  # Using enhanced supervisor
import logging
from fastapi.responses import JSONResponse
from backend.config.redis import *
import re

# Basic configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Create logger
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agent Service"])

class ChatRequest(BaseModel):
    message: str
    selected_simulation_id: str | None = None

@router.post("/mcp-agent")
async def agent_chat(
    req: ChatRequest,
    current_user = Depends(get_current_user)
):
    """
    Main chat endpoint using enhanced MCP + LangGraph architecture
    """
    user_id = current_user.get("user_id")
    # user_id = 1
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: user_id not found")

    from backend.control_tower.chat import answer as control_tower_answer
    tower_result=control_tower_answer(user_id,req.message)
    if tower_result is not None:
        return tower_result

    from backend.operations.journey_chat import answer as journey_answer
    context = await get_active_planning_context(user_id) or {}

    from backend.operations.batch_planning import answer as batch_answer
    batch_result = await batch_answer(user_id, req.message, context)
    if batch_result is not None:
        return batch_result

    # A complete explicit Plan/Create request with its own origin and
    # destination is always a NEW planning request.
    #
    # It must bypass journey/display/operations handlers so stale selected
    # shipment context cannot turn it into "No matching shipment".
    explicit_new_plan = bool(
        re.search(
            r'^\s*(?:please\s+)?(?:plan|create)\b.*\bfrom\s+.+?\s+to\s+.+',
            req.message,
            re.I | re.S,
        )
    )

    from backend.operations.journey_scenarios import answer as scenario_answer, intent as scenario_intent
    explicit_new_plan = explicit_new_plan and not scenario_intent(req.message)
    if explicit_new_plan:
        if supervisor.llm is None:
            raise HTTPException(
                status_code=503,
                detail=supervisor.llm_status.message
                or "AI chat is unavailable due to incomplete configuration.",
            )

        result = await supervisor.process_message(
            user_id,
            req.message,
            selected_id=req.selected_simulation_id,
        )

        logger.info(
            "Explicit new planning request completed for user=%s success=%s",
            user_id,
            result.get("success", False),
        )

        return {
            "success": result.get("success", True),
            "response": result.get("response", "No response generated"),
            "actions": result.get("actions", []),
        }

    scenario_result = await scenario_answer(user_id, req.message, context, req.selected_simulation_id)
    if scenario_result is not None:
        return scenario_result

    from backend.operations.journey_diversion import answer as diversion_answer
    diversion_result=await diversion_answer(user_id,req.message,context,req.selected_simulation_id)
    if diversion_result is not None:
        return diversion_result

    # Read-only disruption/mitigation questions must never enter scenario mutation.
    from backend.operations.journey_mitigation import answer as mitigation_answer
    from backend.planning.lifecycle import resolve
    mitigation_context, mitigation_error=resolve(context,req.message,req.selected_simulation_id)
    mitigation_result = mitigation_answer(req.message, mitigation_context or context)
    if mitigation_result is not None:
        return mitigation_result


    # Existing-journey comparison is read-only and must never fall through
    # into planning/replanning.
    from backend.operations.journey_compare import answer as compare_answer
    compare_result = compare_answer(user_id, req.message, context, req.selected_simulation_id)
    if compare_result is not None:
        return compare_result

    from backend.operations.journey_queries import answer as query_answer
    query_result = query_answer(user_id, req.message, context, req.selected_simulation_id)
    if query_result is not None:
        return query_result

    from backend.operations.journey_display import answer as display_answer
    display_result = display_answer(user_id, req.message, context, req.selected_simulation_id)
    if display_result is not None:
        actions=display_result.get('actions') or []
        if actions and actions[0]['data']['mode']=='MULTI_ROUTE':
            context['map_comparison_ids']=actions[0]['data']['simulation_ids']
            from backend.config.redis import set_active_planning_context as save_display_context
            await save_display_context(user_id,context)
        return display_result
    action_result = await journey_answer(user_id, req.message, context, req.selected_simulation_id)
    if action_result is not None:
        return action_result
    from backend.operations.chat import answer
    operations_result = answer(user_id, req.message, req.selected_simulation_id or context.get("movement_id"))
    if operations_result is not None:
        return operations_result

    if supervisor.llm is None:
        raise HTTPException(
            status_code=503,
            detail=supervisor.llm_status.message or "AI chat is unavailable due to incomplete configuration.",
        )
    
    
    input_message = req.message
    logger.info(f'input_message {type(input_message)}: {input_message}')
    
    # Use enhanced schema-aware supervisor
    result = await supervisor.process_message(user_id, req.message, selected_id=req.selected_simulation_id)
    logger.info("Agent request completed for user=%s success=%s", user_id, result.get("success", False))
    
    return {
        "success": result.get("success", True),
        "response": result.get("response", "No response generated"),
        "actions": result.get("actions", [])
    }
