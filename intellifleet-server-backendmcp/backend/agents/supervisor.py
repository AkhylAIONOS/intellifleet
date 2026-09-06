#backend/agents/supervisor.py
import time
import json
from typing import Dict, Any, List
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from .graph import LogisticsAgentGraph
from backend.config.config import settings
from backend.database.database import get_warehouses_by_userall, get_vehicles_by_user
from ..mcp.tools.tool_client import load_mcp_tools
from .token_logger import log_token_usage
from backend.config.redis import add_data, get_data, get_active_planning_context, set_active_planning_context
from backend.utilities.response import *
from backend.llm import LLMConfigurationError, create_chat_model, provider_status
import logging
import re


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: build a single history entry
# ---------------------------------------------------------------------------
def _make_entry(role: str, content: str) -> dict:
    """Return a normalised chat history entry."""
    return {"role": role, "content": content}

HISTORY_WINDOW = 10


def _response_text(content: Any) -> str:
    """Normalize LangChain chat-completions and Responses API content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("output_text")
                if isinstance(text, dict):
                    text = text.get("value")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return str(content or "")


def _normalize_target_margin(value: Any) -> Any:
    """Convert percentages above 1 to decimals; leave boundary values for schema rejection."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 1 < value <= 100:
        return value / 100
    return value


OBJECTIVE_ALIASES = {
    "cheapest": ("cost", "cheap", "minimum-cost", "lowest-cost", "minimize-cost", "save-money", "economical"),
    "fastest": ("fast", "quick", "earliest", "minimum-eta", "time", "speed", "soon-as-possible"),
    "lowest-risk": ("risk", "safe", "safest", "reliable", "reliability"),
    "balanced": ("balance", "best-overall", "best-tradeoff", "tradeoff"),
}
MODE_ALIASES = {
    "ground": "road", "truck": "road", "road-transport": "road",
    "express": "air", "air-express": "air", "flight": "air", "air-transport": "air",
}


def _is_mode_comparison(message: str) -> bool:
    text = message.casefold()
    comparison = any(token in text for token in ("compare", "difference", " versus ", " vs ", "which is better", "should i use"))
    road_terms=("ground","road","truck"); air_terms=("express","air","flight","fly")
    explicit_pair = any(x in text for x in road_terms) and any(x in text for x in air_terms)
    return comparison and explicit_pair and "multimodal" not in text


def _normalize_objective(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    token = value.strip().casefold().replace("_", "-").replace(" ", "-")
    for canonical, aliases in OBJECTIVE_ALIASES.items():
        if token == canonical or any(alias in token for alias in aliases):
            return canonical
    return token


def _weight_kg_from_message(message: str) -> float | None:
    match=re.search(r"([\d,]+(?:\.\d+)?)\s*(kg|kilograms?|tonnes?|tons?)\b",message,re.I)
    if not match: return None
    value=float(match.group(1).replace(",",""))
    return value*1000 if match.group(2).casefold().startswith(("ton","tonne")) else value


def _canonicalize_planning_values(values: dict) -> dict:
    """Normalize Azure intent once, before adapting it to an MCP operation schema."""
    values = dict(values)
    raw_shipment=values.get("shipment")
    shipment = dict(raw_shipment) if isinstance(raw_shipment,dict) else {}
    if raw_shipment is not None and not isinstance(raw_shipment,dict):
        values.pop("shipment",None)
    for source_key in ("origin", "from"):
        if not values.get("source") and isinstance(values.get(source_key), str):
            values["source"] = values.pop(source_key)
            break
    if not values.get("destination") and isinstance(values.get("to"), str):
        values["destination"] = values.pop("to")
    for key in ("weight_kg", "shipment_weight_kg"):
        if shipment.get("weight_kg") is None and values.get(key) is not None:
            shipment["weight_kg"] = values.pop(key)
    if shipment.get("quantity") is None and values.get("quantity") is not None:
        shipment["quantity"] = values.pop("quantity")
    if shipment:
        values["shipment"] = shipment
    if "objective" not in values and isinstance(values.get("priority"), str):
        values["objective"] = values.pop("priority")
    if "objective" in values:
        values["objective"] = _normalize_objective(values["objective"])
    if "allowed_modes" not in values and isinstance(values.get("modes"), list):
        values["allowed_modes"] = values.pop("modes")
    if isinstance(values.get("allowed_modes"), list):
        values["allowed_modes"] = list(dict.fromkeys(
            MODE_ALIASES.get(str(mode).strip().casefold().replace(" ", "-"),
                             str(mode).strip().casefold()) for mode in values["allowed_modes"]
        ))
    if values.get("risk_constraint") is not None and values.get("max_risk") is None:
        values["max_risk"] = values.pop("risk_constraint")
    if values.get("target_margin") is None:
        values.pop("target_margin", None)
    elif "target_margin" in values:
        values["target_margin"] = _normalize_target_margin(values["target_margin"])
    return values


def _adapt_canonical_params(tool_name: str, params: dict) -> dict:
    """Convert canonical planning fields to the selected MCP tool's external contract."""
    result = dict(params)
    if isinstance(result.get("parameters"), dict):
        result["parameters"] = _canonicalize_planning_values(result["parameters"])
    else:
        result = _canonicalize_planning_values(result)
    if tool_name == "unified_supply_chain_plan" and isinstance(result.get("shipment"), dict):
        shipment = result.pop("shipment")
        result.setdefault("weight_kg", shipment.get("weight_kg"))
        if shipment.get("quantity") is not None:
            result.setdefault("quantity", shipment["quantity"])
    if tool_name == "supply_chain_planning_operation" and isinstance(result.get("parameters"), dict):
        operation=result.get("operation"); nested=result["parameters"]
        if operation=="fulfilment" and isinstance(nested.get("shipment"),dict):
            shipment=nested.pop("shipment")
            nested.setdefault("weight_kg",shipment.get("weight_kg"))
            nested.setdefault("quantity",shipment.get("quantity",1))
    return result


def _money(value: Any) -> str:
    return f"₹{float(value):,.2f}"


def _readable_time(value: Any) -> str:
    if not value: return "not available"
    try:
        from datetime import datetime, timezone
        parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if parsed.tzinfo is None:
            return parsed.strftime("%d %b %Y, %H:%M (timezone not supplied)")
        return parsed.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    except (TypeError,ValueError): return str(value)


def _breakdown_text(title: str, values: dict, *, percent: bool=False, money: bool=True) -> str:
    useful=[]
    def items(mapping, prefix=""):
        for key,value in mapping.items():
            label=f"{prefix} {key}".strip()
            if isinstance(value,dict): yield from items(value,label)
            else: yield label,value
    for key,value in items(values or {}):
        if value in (None,0,0.0,"",False) or key == "overall": continue
        if not isinstance(value,(int,float)): continue
        label=key.replace("_"," ").title()
        shown=f"{float(value)*100:.2f}%" if percent else (_money(value) if money else f"{float(value):.4f}")
        useful.append(f"- {label}: {shown}")
    return f"{title}\n"+("\n".join(useful) if useful else "- No additional components")


def _route_text(plan: dict) -> str:
    legs = plan.get("route_legs") or []
    if not legs:
        return "No feasible route legs were found."
    return "\n".join(
        f"- {leg.get('from_location')} → {leg.get('to_location')} "
        f"({leg.get('route_type', 'configured')}, {leg.get('distance')} km, {leg.get('duration')} hours)"
        for leg in legs
    )


def _actual_mode(plan: dict) -> str:
    """Derive presentation mode from route legs, never from a stale plan label."""
    modes = {str(leg.get("route_type") or "road").casefold() for leg in plan.get("route_legs") or []}
    if not modes:
        return str(plan.get("mode") or "plan").casefold()
    return next(iter(modes)) if len(modes) == 1 else "multimodal"


def _mode_label(plan: dict) -> str:
    return {"road": "Ground / Road", "air": "Express / Air", "multimodal": "Multimodal"}.get(
        _actual_mode(plan), "Plan"
    )


def _risk_delta_text(value: float, subject: str) -> str:
    """Present planner risk-score deltas as human-readable percentage points."""
    delta=float(value)
    direction="lowers" if delta < 0 else "raises" if delta > 0 else "does not change"
    if delta == 0:
        return f"{subject} does not change risk"
    return f"{subject} {direction} risk by {abs(delta) * 100:.2f} percentage points"


def _objective_is_explicit(user_message: str, objective: str) -> bool:
    text=user_message.casefold()
    terms={
        "balanced": ("balanced", "balance of"),
        "cheapest": ("cheapest", "lowest cost", "cost matters", "cost most"),
        "fastest": ("fastest", "shortest time", "time matters", "time most"),
        "lowest-risk": ("lowest risk", "lowest-risk", "safest", "risk matters"),
    }
    return any(term in text for term in terms.get(objective, (objective,)))


def _vehicle_text(plan: dict, shipment: dict) -> str:
    vehicles = plan.get("vehicles") or []
    if not vehicles:
        return "No currently available compatible vehicle covers this load."
    total=shipment.get("weight_kg")
    displayed=[]; allocated=0.0
    for index,vehicle in enumerate(vehicles):
        raw=float(vehicle.get("assigned_load_kg",total or 0))
        load=round(float(total)-allocated,2) if total is not None and index==len(vehicles)-1 else round(raw,2)
        allocated+=load
        shown=f"{load:,.2f}".rstrip("0").rstrip(".")
        displayed.append(
            f"- {vehicle.get('label') or vehicle.get('id')} ({vehicle.get('type')}): capacity {vehicle.get('capacity')} kg, "
            f"assigned load {shown} kg, utilization {vehicle.get('utilization_percentage')}%"
        )
    return "\n".join(displayed)


def _sla_text(plan: dict) -> str:
    if plan.get("deadline") is None:
        return "SLA was not evaluated because no delivery deadline was provided."
    status = "met" if plan.get("sla_met") else "missed"
    return (f"SLA {status}; deadline {_readable_time(plan.get('deadline'))}, expected arrival {_readable_time(plan.get('eta'))}, "
            f"slack {plan.get('sla_slack_hours')} hours, delay {plan.get('sla_delay_hours')} hours.")


def _format_planning_result(result: dict, user_message: str = "") -> str:
    """Complete deterministic customer response; every number is copied from planner output."""
    if result.get("scope")=="international" and result.get("requested_multimodal_feasible") is False:
        direct=result.get("recommended_plan") or {}
        return ("The exact requested global multimodal chain is not available in the loaded network. "
                + "; ".join(str(x) for x in result.get("warnings") or []) + ". "
                + (f"A direct Express / Air alternative is available at {_money(direct.get('operational_cost',0))} with ETA {direct.get('duration_hours')} hours."
                   if direct else "No complete international alternative is currently feasible."))
    if result.get("status") == "draft" and result.get("baseline") and result.get("scenario"):
        baseline=result["baseline"].get("recommended_plan") or {}; scenario=result["scenario"].get("recommended_plan") or {}; delta=result.get("comparison") or {}
        return ("I've created a draft what-if plan. No live network data has been changed.\n\n"
                f"Baseline: {_money(baseline.get('operational_cost',0))}, {baseline.get('duration_hours')} hours, risk {baseline.get('risk_score')}.\n\n"
                f"Scenario: {_money(scenario.get('operational_cost',0))}, {scenario.get('duration_hours')} hours, risk {scenario.get('risk_score')}.\n\n"
                f"Exact differences: cost {delta.get('cost_difference')}, ETA {delta.get('eta_difference_hours')} hours, risk {delta.get('risk_difference')}.\n\n"
                "Recommendation: Review these calculated changes, then explicitly apply or discard the scenario.")
    if "warehouses" in result and result.get("planning_operation") == "warehouse_capacity":
        rows=result.get("warehouses") or []
        return "Warehouse capacity\n\n"+"\n".join(f"- {x['warehouse']}: inventory {x['current_inventory']}, available inventory {x['available_inventory']}, available storage {x['available_storage']}, utilization {x['utilization_percentage'] if x['utilization_percentage'] is not None else 'not available'}%" for x in rows)
    if "consolidation_opportunities" in result:
        rows=result.get("consolidation_opportunities") or []
        if not rows: return "No feasible consolidation opportunity was found for the supplied shipments and timing constraints."
        return "Consolidation recommendation\n\n"+"\n".join(f"- Shipments {', '.join(x['shipment_ids'])}: separate cost {_money(x['original_cost'])}, consolidated cost {_money(x['consolidated_cost'])}, savings {_money(x['savings'])}, utilization {x['utilization_before']:.1%} → {x['utilization_after']:.1%}; vehicles {', '.join(str(v.get('label')) for v in x.get('plan',{}).get('vehicles',[])) or 'none'}. Recommendation: consolidate when the shared delivery window remains valid." for x in rows)
    if "inventory_case" in result:
        case=result.get("inventory_case")
        if not case:return "No loaded SKU requires multiple warehouses while remaining fully fulfilable by the current network inventory."
        result=dict(result); result.pop("inventory_case",None)
        return f"Loaded SKU: {case['sku']}; required quantity: {case['required_quantity']}.\n\n"+_format_planning_result(result,user_message)
    if result.get("scenario_id") and result.get("status") in {"applied","discarded"} and not result.get("scenario"):
        return (f"Draft scenario {result['status']}. " +
                ("The approved scenario plan is now active." if result['status']=="applied" else "The baseline plan remains active and unchanged."))
    if "affected_shipments" in result:
        rows=result.get("affected_shipments") or []
        return (f"Future shipment impact for {result.get('delayed_vehicle')}\n\n"+
                ("\n".join(f"- {x['shipment_id']}: {x['action']}; assignment {x['before_assignment']} → {x['after_assignment']}; cascading delay {x['cascading_delay_hours']} hours; SLA {x['sla_met']}." for x in rows) or "No scheduled future shipments are affected."))
    if "recommended_hubs" in result:
        rows=result.get("recommended_hubs") or []
        return (f"Facility recommendation\n\n{result.get('reason')}\n\n"+
                "\n".join(f"- {x['hub']}: incremental cost {'unknown (missing assumptions)' if x.get('incremental_cost') is None else _money(x['incremental_cost'])}; weighted geodesic distance {x['weighted_distance_km']} km. Missing assumptions: {', '.join(x.get('missing_assumptions', [])) or 'none'}." for x in rows))
    if "ranked_alternatives" in result and "allocation" in result:
        allocations=result.get("allocation") or []
        alternatives=result.get("ranked_alternatives") or []
        allocation_lines=[]
        for item in allocations:
            plan=item["plan"]
            sla_part="" if plan.get("deadline") is None else f", SLA {'met' if plan.get('sla_met') else 'missed'}"
            allocation_lines.append(
                f"- {item['warehouse']}: allocate {item['allocation']} units (available {item['available']}); "
                f"cost {_money(plan['operational_cost'])}, ETA {plan['duration_hours']} hours, risk {plan['risk_score']}"
                f"{sla_part}. Route: {' → '.join([str(x.get('from_location')) for x in plan.get('route_legs', [])] + ([str(plan.get('route_legs', [])[-1].get('to_location'))] if plan.get('route_legs') else ['local']))}. "
                f"Vehicles: {', '.join(str(x.get('label')) for x in plan.get('vehicles', [])) or 'none required'}"
            )
        ranked_lines=[]
        for item in alternatives:
            candidate=item["plan"]; sla_part="" if candidate.get("deadline") is None else f", SLA {'met' if candidate.get('sla_met') else 'missed'}"
            ranked_lines.append(f"- {item['warehouse']}: available {item['available']}, candidate allocation {item['allocation']}, cost {_money(candidate['operational_cost'])}, ETA {candidate['duration_hours']} hours, risk {candidate['risk_score']}{sla_part}, score {candidate['score']}")
        return (
            f"Warehouse fulfilment {'succeeds' if result.get('fulfilled') else 'is incomplete'}. "
            f"Unfulfilled quantity: {result.get('unfulfilled_quantity')}.\n\nRecommended allocation:\n"
            f"{chr(10).join(allocation_lines) or '- No feasible allocation'}\n\n"
            f"Total cost: {_money(result.get('total_cost', 0))}; overall ETA: {result.get('eta_hours')} hours.\n\n"
            f"Ranked alternatives:\n{chr(10).join(ranked_lines) or '- No connected warehouse has sufficient transport capacity.'}\n\n"
            f"Recommendation: {result.get('recommendation')}"
        )
    if result.get("recovery_plan") and result.get("broken_vehicle"):
        plan=result["recovery_plan"]; broken=result["broken_vehicle"]
        before=result.get("_active_plan_before") or {}
        before_route=" → ".join([str(x.get("from_location")) for x in before.get("route_legs") or []] +
                                ([str((before.get("route_legs") or [])[-1].get("to_location"))] if before.get("route_legs") else []))
        after_route=" → ".join([str(x.get("from_location")) for x in plan.get("route_legs") or []] +
                               ([str((plan.get("route_legs") or [])[-1].get("to_location"))] if plan.get("route_legs") else []))
        before_vehicles=", ".join(str(v.get("label") or v.get("id")) for v in before.get("vehicles") or []) or "none"
        after_vehicles=", ".join(str(v.get("label") or v.get("id")) for v in plan.get("vehicles") or []) or "none"
        comparison=""
        if before:
            comparison=("\n\nWhat changed (before → after):\n"
                        f"- Mode: {_mode_label(before)} → {_mode_label(plan)}\n"
                        f"- Route: [{before_route}] → [{after_route}]\n"
                        f"- Vehicle: {before_vehicles} → {after_vehicles}\n"
                        f"- Cost: {_money(before.get('cost',0))} → {_money(plan.get('operational_cost',0))} "
                        f"(delta {_money(float(plan.get('operational_cost',0))-float(before.get('cost',0)))})\n"
                        f"- ETA: {before.get('duration_hours')} hours → {plan.get('duration_hours')} hours "
                        f"(delta {float(plan.get('duration_hours',0))-float(before.get('duration_hours',0)):+.2f} hours)\n"
                        f"- Risk: {float(before.get('risk',0)):.2%} → {float(plan.get('risk_score',0)):.2%} "
                        f"(delta {(float(plan.get('risk_score',0))-float(before.get('risk',0)))*100:+.2f} percentage points)")
        approach_text=(_route_text({'route_legs': plan.get('replacement_approach_legs', [])})
                       if plan.get('replacement_approach_legs') else
                       "Replacement is already at the current shipment location; no repositioning leg is required.")
        return (
            f"Breakdown recovery recommendation\n\nBroken vehicle: {broken.get('label')} at {result.get('remaining_journey', {}).get('source')}. "
            f"It is excluded from the recovery assignment.\n\nRemaining load: {result.get('transfer_load_kg')} kg.\n\n"
            f"Replacement vehicles:\n{_vehicle_text(plan, {'weight_kg': result.get('transfer_load_kg')})}\n\n"
            f"Repositioning route:\n{approach_text}\n"
            f"Replacement arrival: {plan.get('replacement_arrival_hours')} hours; transfer time: {plan.get('transfer_time_hours')} hours; "
            f"repositioning/additional cost: {_money(result.get('additional_cost') or 0)}.\n\n"
            f"Remaining route:\n{_route_text(plan)}\n\nNew total ETA: {plan.get('duration_hours')} hours, expected arrival {_readable_time(result.get('new_eta'))}. "
            f"Total operational cost: {_money(plan.get('operational_cost', 0))}. Risk: {plan.get('risk_score')}. {_sla_text(plan)}{comparison}"
        )
    if result.get("recovery_plan") and isinstance(result.get("scenario"), dict):
        scenario = dict(result["scenario"])
        scenario["reason"] = "This is the deterministic recovery recommendation after excluding affected resources."
        affected=result.get("affected_resources") or {}
        affected_lines="\n".join(f"- {key.replace('_',' ').title()}: {value}" for key,value in affected.items())
        comparison=result.get("comparison") or {}
        comparison_lines="\n".join(f"- {key.replace('_',' ').title()}: {value}" for key,value in comparison.items() if value is not None and not isinstance(value,(dict,list)))
        return (
            "Disruption mitigation plan\n\n"
            f"Affected resources\n{affected_lines}\n\n"
            f"{_format_planning_result(scenario)}\n\n"
            f"Baseline comparison\n{comparison_lines}"
        )
    options = result.get("options") or {}
    mode_delta = result.get("express_vs_ground")
    if options.get("ground") and options.get("express") and mode_delta:
        ground, express = options["ground"], options["express"]
        multimodal = options.get("multimodal")
        ground_label,express_label=_mode_label(ground),_mode_label(express)
        recommended = result.get("recommended_plan") or ground
        multimodal_text = ""
        if multimodal:
            multimodal_label=_mode_label(multimodal)
            multimodal_text = (
                f"\n\n{multimodal_label} costs {_money(multimodal['operational_cost'])}, takes {multimodal['duration_hours']} hours, "
                f"and has risk {multimodal['risk_score']}.\nRoute:\n{_route_text(multimodal)}\n"
                f"Vehicles:\n{_vehicle_text(multimodal, result.get('planning_request', {}).get('shipment', {}))}"
            )
        recommendation=_mode_label(recommended)
        objective=result.get('planning_request',{}).get('objective','balanced')
        objective_phrase=(f"Using the default balanced objective, {recommendation} has the best deterministic score."
                          if objective == "balanced" and not _objective_is_explicit(user_message, objective)
                          else f"{recommendation} best matches the requested {objective} objective.")
        risk_phrase=_risk_delta_text(mode_delta['risk_difference'],express_label)
        reason=(f"{objective_phrase} {ground_label} is {_money(abs(mode_delta['additional_cost']))} cheaper, while "
                f"{express_label} saves {mode_delta['time_saved_hours']} hours and {risk_phrase}.")
        sla=mode_delta.get("sla_comparison") or {}
        sla_text="" if sla.get("ground") is None and sla.get("express") is None else f"\nSLA comparison\n- Ground: {'met' if sla.get('ground') else 'missed'}\n- Express: {'met' if sla.get('express') else 'missed'}"
        return (
            f"For this shipment, I'd recommend {recommendation}.\n\n{reason}\n\nHere's the comparison.\n\n"
            f"{ground_label} costs {_money(ground['operational_cost'])}, takes {ground['duration_hours']} hours, and has risk {ground['risk_score']:.2%}.\n"
            f"Route:\n{_route_text(ground)}\nVehicles:\n{_vehicle_text(ground, result.get('planning_request', {}).get('shipment', {}))}\n"
            f"{_breakdown_text('Ground cost breakdown',ground.get('cost_breakdown',{}))}\n\n"
            f"{express_label} costs {_money(express['operational_cost'])}, takes {express['duration_hours']} hours, and has risk {express['risk_score']:.2%}.\n"
            f"Route:\n{_route_text(express)}\nVehicles:\n{_vehicle_text(express, result.get('planning_request', {}).get('shipment', {}))}\n"
            f"{_breakdown_text('Express cost breakdown',express.get('cost_breakdown',{}))}"
            f"{multimodal_text}\n\n"
            f"{express_label} costs {_money(mode_delta['additional_cost'])} more and saves {mode_delta['time_saved_hours']} hours; "
            f"{risk_phrase}.{sla_text}"
        )
    plan = result.get("recommended_plan") or result.get("recommendation")
    if not isinstance(plan, dict) or not plan.get("plan_id"):
        request=result.get("planning_request") or {}
        if result.get("scope") == "international" and result.get("warnings"):
            return "International multimodal planning could not be completed: " + "; ".join(str(x) for x in result["warnings"]) + "."
        if result.get("planning_operation") == "route_alternatives" and result.get("feasibility"):
            detail=result["feasibility"]
            route=" → ".join(detail.get("alternative_route") or [])
            route_text=f" An alternate route exists ({route})," if route else ""
            return (f"I could not produce a safe revised plan for the current shipment.{route_text} but no available compatible "
                    f"source-vehicle combination satisfies the {detail.get('shipment_weight_kg')} kg load and full-route range "
                    "requirements. The current plan remains unchanged.")
        modes=request.get("allowed_modes") or []
        if len(modes)==1 and request.get("source") and request.get("destination"):
            mode={"road":"road","air":"air","multimodal":"multimodal"}.get(str(modes[0]).casefold(),str(modes[0]))
            return f"No feasible {mode} route from {request['source']} to {request['destination']} exists in the currently loaded network."
        return str(result.get("message") or "No feasible plan was found for the supplied constraints.")
    request = result.get("planning_request") or {}
    shipment = request.get("shipment") or {}
    objective=request.get("objective","balanced")
    product=plan.get("product",plan.get("mode","selected plan"))
    objective_reason={
        "cheapest":f"It has the lowest calculated operational cost among the feasible options.",
        "fastest":f"It has the shortest calculated ETA among the feasible options.",
        "lowest-risk":f"It has the lowest calculated disruption risk among the feasible options.",
        "balanced":f"It provides the strongest calculated balance of cost, time, reliability, risk and utilization.",
    }.get(objective,"It has the best deterministic result for the requested objective.")
    pricing_requested=any(term in user_message.casefold() for term in ("price it","pricing","revenue","profit","margin","selling price"))
    cost_line=f"Operational cost: {_money(plan.get('operational_cost',0))}."
    if pricing_requested:
        cost_line+=(f" Selling price/revenue: {_money(plan.get('selling_price',0))}. "
                    f"Profit: {_money(plan.get('profit',0))}. Margin: {plan.get('margin_percentage')}%.")
    parts = [
        f"For this shipment, I'd recommend the {product} plan.",
        f"Why: {objective_reason}",
        f"Shipment: {request.get('source')} → {request.get('destination')}; weight {shipment.get('weight_kg')} kg; quantity {shipment.get('quantity')}.",
        f"Route:\n{_route_text(plan)}",
        f"Vehicles:\n{_vehicle_text(plan, shipment)}",
        cost_line+"\n"+_breakdown_text("Cost breakdown",plan.get("cost_breakdown",{})),
        f"ETA: {plan.get('duration_hours')} hours; expected arrival {_readable_time(plan.get('eta'))}.",
        f"Risk: {plan.get('risk_score'):.2%}; reliability {plan.get('reliability'):.2%}.\n"+_breakdown_text("Risk profile",plan.get("risk_breakdown",{}),percent=True)+f"\n- Overall: {plan.get('risk_score'):.2%}",
        _sla_text(plan),
    ]
    before=result.get("_active_plan_before")
    if isinstance(before,dict) and (result.get("planning_operation") == "route_alternatives" or "what changed" in user_message.casefold() or "compare" in user_message.casefold()):
        before_cost=before.get("cost"); after_cost=plan.get("operational_cost")
        before_eta=before.get("duration_hours"); after_eta=plan.get("duration_hours")
        before_risk=before.get("risk"); after_risk=plan.get("risk_score")
        before_vehicle=", ".join(str(v.get("label") or v.get("id")) for v in before.get("vehicles") or []) or "none"
        after_vehicle=", ".join(str(v.get("label") or v.get("id")) for v in plan.get("vehicles") or []) or "none"
        before_route=" → ".join([str(x.get("from_location")) for x in before.get("route_legs") or []] +
                                ([str((before.get("route_legs") or [])[-1].get("to_location"))] if before.get("route_legs") else []))
        after_route=" → ".join([str(x.get("from_location")) for x in plan.get("route_legs") or []] +
                               ([str((plan.get("route_legs") or [])[-1].get("to_location"))] if plan.get("route_legs") else []))
        delta_lines=[
            "What changed (before → after):",
            f"- Mode: {_mode_label(before)} → {_mode_label(plan)}",
            f"- Route: {before_route} → {after_route}",
            f"- Vehicle: {before_vehicle} → {after_vehicle}",
            f"- Cost: {_money(before_cost)} → {_money(after_cost)} (delta {_money(float(after_cost)-float(before_cost))})",
            f"- ETA: {before_eta} hours → {after_eta} hours (delta {float(after_eta)-float(before_eta):+.2f} hours)",
            f"- Risk: {float(before_risk):.2%} → {float(after_risk):.2%} (delta {(float(after_risk)-float(before_risk))*100:+.2f} percentage points)",
        ]
        if before.get("deadline") is not None or plan.get("deadline") is not None:
            delta_lines.append(f"- SLA: {before.get('sla_met')} → {plan.get('sla_met')}")
        parts.insert(2,"\n".join(delta_lines))
    if request.get("objective") == "balanced":
        parts.append(f"Balanced score: {plan.get('score')}.\n"+_breakdown_text("Balanced scoring",plan.get("score_components",{}),money=False))
    comparisons = result.get("comparison") or []
    candidates = {x.get("plan_id"): x for x in result.get("candidate_plans") or []}
    if comparisons:
        rows = []
        for delta in comparisons:
            other = candidates.get(delta.get("plan_id"), {})
            sla_delta=delta.get("sla_difference")
            sla_phrase="" if not isinstance(sla_delta,dict) or all(value is None for value in sla_delta.values()) else f", SLA recommended {'met' if sla_delta.get('recommended') else 'missed'} / alternative {'met' if sla_delta.get('alternative') else 'missed'}"
            rows.append(
                f"- {_mode_label(other)} alternative: cost {_money(other.get('operational_cost', 0))}, "
                f"ETA {other.get('duration_hours')} hours, risk {other.get('risk_score')}, reliability {other.get('reliability')}, "
                f"score {other.get('score')}; cost delta {delta.get('cost_difference')}, ETA delta {delta.get('time_difference_hours')} hours, "
                f"{_risk_delta_text(delta.get('risk_difference',0),_mode_label(other))}, utilization delta {delta.get('utilization_difference')}{sla_phrase}. "
                f"Route: {' → '.join([str(x.get('from_location')) for x in other.get('route_legs', [])] + ([str(other.get('route_legs', [])[-1].get('to_location'))] if other.get('route_legs') else []))}"
            )
        parts.append("Feasible alternatives:\n" + "\n".join(rows))
    requested_modes=set(request.get("allowed_modes") or [])
    feasible_modes={x.get("mode") for x in result.get("candidate_plans") or []}
    unavailable=sorted(requested_modes-feasible_modes)
    if unavailable:
        parts.append("Unavailable requested modes: " + ", ".join(unavailable) + ". No feasible route-and-vehicle combination exists for those modes in the current network.")
    return "\n\n".join(parts)


def _route_disruption_params(message: str) -> dict | None:
    pattern = re.compile(
        r"route from (?P<blocked_from>.+?) to (?P<blocked_to>.+?) is (?:blocked|unavailable|cancelled).*?"
        r"(?:replan|plan) (?P<weight>[\d,]+(?:\.\d+)?)\s*kg from (?P<source>.+?) to (?P<destination>.+?)(?:,|\.|$)",
        re.IGNORECASE,
    )
    match = pattern.search(message)
    if not match:
        return None
    values = match.groupdict()
    return {
        "source": values["source"].strip(), "destination": values["destination"].strip(),
        "shipment": {"weight_kg": float(values["weight"].replace(",", "")), "quantity": 1},
        "objective": "balanced", "changes": {"blocked_routes": [[
            values["blocked_from"].strip(), values["blocked_to"].strip()
        ]]},
    }


def _disruption_mitigation_params(message: str, warehouse_names: list[str]) -> dict | None:
    """Extract the shared canonical contract for explicit mitigation requests."""
    text = message.strip()
    lower = text.casefold()
    if not any(word in lower for word in ("mitigate", "mitigation", "mode disruption")):
        return None
    shipment = re.search(r"(?P<weight>[\d,]+(?:\.\d+)?)\s*kg\s+(?:from\s+)?(?P<source>.+?)\s+to\s+(?P<destination>.+?)(?:[.,]|\s+and\s+|\s+with\s+|$)", text, re.I)
    if not shipment:
        return None

    def resolve(value: str) -> str:
        wanted = value.strip().casefold()
        matches = [name for name in warehouse_names if wanted == name.casefold() or wanted in name.casefold()]
        return matches[0] if len(matches) == 1 else value.strip()

    groups = shipment.groupdict()
    changes: dict[str, Any] = {}
    route = re.search(r"(?:direct\s+)?route\s+from\s+(.+?)\s+to\s+(.+?)\s+is\s+(?:blocked|unavailable|cancelled)", text, re.I)
    vehicle = re.search(r"\b([A-Za-z]{2,5}-\d+)\b.*?\b(?:unavailable|broken|failed)\b", text, re.I)
    warehouse = re.search(r"(?:the\s+)?(.+?)\s+warehouse\s+is\s+(?:unavailable|blocked|closed)", text, re.I)
    risk = re.search(r"risk\s+(?:increases?|rises?)\s+by\s+(\d+(?:\.\d+)?)", text, re.I)
    mode = re.search(r"\b(road|ground|air|express|multimodal)\b\s+is\s+the\s+only\s+available\s+mode", text, re.I)
    if route:
        changes["blocked_routes"] = [[resolve(route.group(1)), resolve(route.group(2))]]
    elif vehicle:
        changes["unavailable_vehicles"] = [vehicle.group(1).upper()]
    elif warehouse:
        changes["unavailable_warehouses"] = [resolve(warehouse.group(1))]
    elif risk:
        changes["risk_delta"] = float(risk.group(1))
    elif mode:
        changes["allowed_modes"] = [MODE_ALIASES.get(mode.group(1).casefold(), mode.group(1).casefold())]
    if not changes:
        return None
    return {"user_id": 0, "operation": "disruption_mitigation", "parameters": {
        "source": resolve(groups["source"]), "destination": resolve(groups["destination"]),
        "shipment": {"weight_kg": float(groups["weight"].replace(",", "")), "quantity": 1},
        "objective": "balanced", "changes": changes}}


def _is_vehicle_planning_request(message: str) -> bool:
    text = message.casefold()
    if any(word in text for word in ("consolidat", "separate versus consolidated")): return False
    return bool(re.search(r"\d[\d,]*(?:\.\d+)?\s*kg", text)) and " to " in text and any(
        word in text for word in ("vehicle", "truck", "capacity", "utilization"))


def _is_shipment_plan_request(message: str) -> bool:
    text=message.casefold()
    return (_weight_kg_from_message(message) is not None and " to " in text and
            any(word in text for word in ("plan", "move", "transport", "ship")) and
            not any(word in text for word in ("broke down", "breakdown", "what if", "what-if", "disrupt")))


def _vehicle_selection_params(message: str, warehouse_names: list[str]) -> dict | None:
    if not _is_vehicle_planning_request(message):
        return None
    match = re.search(r"(?P<weight>[\d,]+(?:\.\d+)?)\s*kg(?:\s+(?:road\s+)?(?:shipment|load))?\s+(?:from\s+)?(?P<source>.+?)\s+to\s+(?P<destination>.+?)(?:[.;,]|$)", message, re.I)
    if not match:
        return None
    def resolve(value: str) -> str:
        wanted=value.strip().casefold(); found=[x for x in warehouse_names if wanted==x.casefold() or wanted in x.casefold()]
        return found[0] if len(found)==1 else value.strip()
    g=match.groupdict(); text=message.casefold()
    objective="lowest-risk" if any(x in text for x in ("reliable","lowest risk","safest")) else "balanced"
    parameters={"source":resolve(g["source"]),"destination":resolve(g["destination"]),
                "shipment":{"weight_kg":float(g["weight"].replace(",","")),"quantity":1},
                "objective":objective,"allowed_modes":["road"]}
    unavailable=re.search(r"\b([A-Za-z]{2,5}-\d+)\b.*?\bunavailable\b",message,re.I)
    if unavailable: parameters["changes"]={"unavailable_vehicles":[unavailable.group(1).upper()]}
    return {"user_id":0,"operation":"vehicle_selection","parameters":parameters}


def _deadline_from_message(message: str) -> str | None:
    match = re.search(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?", message)
    if match:return match.group(0)
    natural=re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4}),?\s+(?:at\s+)?(\d{1,2}):?(\d{2})?\s*(AM|PM)\s*(IST)\b",message,re.I)
    if natural:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        day,month,year,hour,minute,period,_=natural.groups()
        parsed=datetime.strptime(f"{day} {month[:3]} {year} {hour}:{minute or '00'} {period}","%d %b %Y %I:%M %p")
        return parsed.replace(tzinfo=ZoneInfo("Asia/Kolkata")).isoformat()
    return None


def _objective_from_message(message: str) -> str | None:
    text = message.casefold()
    if any(x in text for x in ("cost matters most", "recommend the cheapest", "lowest cost", "minimum cost", "minimize cost", "cheapest")):
        return "cheapest"
    if any(x in text for x in ("risk matters most", "recommend the safest", "lowest risk", "minimize risk", "most reliable", "safest")):
        return "lowest-risk"
    if any(x in text for x in ("recommend the fastest", "fastest feasible", "minimum eta", "quickest", "earliest", "fastest")):
        return "fastest"
    if any(x in text for x in ("best overall", "best tradeoff", "balanced objective", "balance cost")):
        return "balanced"
    return None


def _breakdown_recovery_params(message: str, warehouse_names: list[str]) -> dict | None:
    text=message.strip(); lower=text.casefold()
    if not any(x in lower for x in ("broke down","breakdown","broken vehicle")):
        return None
    label=re.search(r"\b([A-Za-z]{2,5}-\d+)\b",text)
    weight=re.search(r"([\d,]+(?:\.\d+)?)\s*kg",text,re.I)
    location=re.search(r"(?:broke down|breakdown|broken vehicle)\s+(?:at|in|near)\s+(.+?)(?:[.,]|\s+with\s+)",text,re.I)
    destination=re.search(r"(?:recover(?: the)? shipment|continue|deliver|move|replan)(?:\s+it)?\s+to\s+(.+?)(?:[.,]|\s+by\s+|\s+and\s+|\s+using\s+|$)",text,re.I)
    if not all((label,weight,location,destination)):
        return None
    def resolve(value: str) -> str:
        wanted=value.strip().casefold(); found=[x for x in warehouse_names if wanted==x.casefold() or wanted in x.casefold()]
        return found[0] if len(found)==1 else value.strip()
    parameters={"vehicle_label":label.group(1).upper(),"current_location":resolve(location.group(1)),
                "destination":resolve(destination.group(1)),"remaining_weight_kg":float(weight.group(1).replace(",",""))}
    deadline=_deadline_from_message(message)
    if deadline: parameters["deadline"]=deadline
    return {"user_id":0,"operation":"breakdown_recovery","parameters":parameters}


def _fulfilment_params(message: str, warehouse_names: list[str]) -> dict | None:
    text=message.strip(); lower=text.casefold()
    if not any(x in lower for x in ("fulfil", "fulfill", "warehouses cover", "warehouse allocation", "alternative warehouse")):
        return None
    quantity=re.search(r"([\d,]+)\s*(?:units?|items?|orders?)",text,re.I)
    weight=re.search(r"([\d,]+(?:\.\d+)?)\s*kg",text,re.I)
    destination=re.search(r"\bkg\s+to\s+(.+?)(?:[.,]|\s+using\s+|\s+with\s+|\s+by\s+|$)",text,re.I)
    if not all((quantity,weight,destination)):
        return None
    wanted=destination.group(1).strip().casefold(); found=[x for x in warehouse_names if wanted==x.casefold() or wanted in x.casefold()]
    resolved=found[0] if len(found)==1 else destination.group(1).strip()
    objective=_objective_from_message(message) or "balanced"
    parameters={"destination":resolved,"quantity":int(quantity.group(1).replace(",","")),
                "weight_kg":float(weight.group(1).replace(",","")),"objective":objective}
    deadline=_deadline_from_message(message)
    if deadline: parameters["deadline"]=deadline
    return {"user_id":0,"operation":"fulfilment","parameters":parameters}


def _scenario_params(message: str) -> dict | None:
    lower=message.casefold()
    if not any(x in lower for x in ("what-if","what if","scenario")): return None
    route=re.search(r"([\d,]+(?:\.\d+)?)\s*(kg|kilograms?|tonnes?|tons?)\s+(?:from\s+)?(.+?)\s+to\s+(.+?)(?:\s+if\s+|[.,]|$)",message,re.I)
    fuel=re.search(r"fuel cost (?:increases?|rises?) by\s*([\d.]+)\s*(?:%|percent)",message,re.I)
    if not route or not fuel: return None
    weight=float(route.group(1).replace(",",""))*(1000 if route.group(2).casefold().startswith("ton") else 1)
    return {"user_id":0,"operation":"create_scenario","parameters":{"source":route.group(3).strip(),"destination":route.group(4).strip(),"shipment":{"weight_kg":weight,"quantity":1},"objective":"balanced","changes":{"fuel_cost_multiplier":1+float(fuel.group(1))/100}}}


def _specialized_operation_params(message: str) -> dict | None:
    text=message.strip(); lower=text.casefold()
    if "consolidat" in lower:
        weights=re.findall(r"shipment\s+([\w-]+)\s+of\s+([\d,]+(?:\.\d+)?)\s*kg",text,re.I)
        route=re.search(r"from\s+(.+?)\s+to\s+(.+?)(?:[,.]|$)",text,re.I)
        if len(weights)>=2 and route:
            shipments=[{"shipment_id":sid,"source":route.group(1).strip(),"destination":route.group(2).strip(),"weight_kg":float(weight.replace(',',''))} for sid,weight in weights]
            return {"user_id":0,"operation":"consolidation","parameters":{"shipments":shipments}}
        pairs=re.findall(r"([\d,]+(?:\.\d+)?)\s*kg\s+(?:shipment\s+)?(?:from\s+)?(.+?)\s*(?:→|->|\bto\b)\s*([A-Za-z][A-Za-z ]+?)(?=\s+and\s+[\d,]+(?:\.\d+)?\s*kg|\s+with\s+same|[.,]|$)",text,re.I)
        if len(pairs)>=2:
            shipments=[{"shipment_id":f"S{index+1}","source":source.strip(),"destination":destination.strip(),"weight_kg":float(weight.replace(',',''))}
                       for index,(weight,source,destination) in enumerate(pairs)]
            return {"user_id":0,"operation":"consolidation","parameters":{"shipments":shipments}}
    if "multi-stop" in lower or "stop order" in lower or "required stops" in lower:
        route=re.search(r"([\d,]+(?:\.\d+)?)\s*kg.*?from\s+(.+?)\s+to\s+(.+?)\s+(?:stopping at|with required stops at)\s+(.+?)(?:\.|$)",text,re.I)
        if route:
            stops=[x.strip() for x in re.split(r"\s+and\s+|,",route.group(4)) if x.strip()]
            return {"user_id":0,"operation":"multi_stop","parameters":{"source":route.group(2).strip(),"destination":route.group(3).strip(),"stops":stops,"shipment":{"weight_kg":float(route.group(1).replace(',','')),"quantity":1},"objective":"balanced"}}
    if "future shipment" in lower or "affected future" in lower:
        vehicle=re.search(r"\b([A-Za-z]{2,5}-\d+)\b",text); delay=re.search(r"(?:delayed by|delay(?:ed)?)\s*([\d.]+)\s*hours?",text,re.I)
        if vehicle and delay:return {"user_id":0,"operation":"future_replan","parameters":{"vehicle_label":vehicle.group(1).upper(),"delay_hours":float(delay.group(1))}}
    if "existing sku" in lower and "multiple warehouses" in lower:
        return {"user_id":0,"operation":"auto_fulfilment","parameters":{}}
    if any(x in lower for x in ("global multimodal", "international", "gateway")):
        route=re.search(r"([\d,]+(?:\.\d+)?)\s*kg from\s+(.+?)\s+in\s+([A-Za-z]+)\s+to\s+(.+?)\s+in\s+([A-Za-z]+)",text,re.I)
        if route:return {"user_id":0,"operation":"global_plan","parameters":{"source":route.group(2).strip(),"destination":route.group(4).strip(),"source_country":route.group(3),"destination_country":route.group(5),"shipment":{"weight_kg":float(route.group(1).replace(',','')),"quantity":1},"objective":"balanced","allowed_modes":["multimodal"]}}
        route=re.search(r"([\d,]+(?:\.\d+)?)\s*kg\s+(?:shipment\s+)?(?:from\s+)?(.+?)\s*(?:→|->|\bto\b)\s*(.+?)(?=\s+using\b|[.!?]|$)",text,re.I)
        if route:return {"user_id":0,"operation":"global_plan","parameters":{"source":route.group(2).strip(),"destination":route.group(3).strip(),"shipment":{"weight_kg":float(route.group(1).replace(',','')),"quantity":1},"objective":"balanced","allowed_modes":["multimodal"]}}
    return None


def _context_from_result(result: dict, previous: dict | None = None) -> dict:
    """Create the per-session planning context from deterministic tool output."""
    context = dict(previous or {})
    request = result.get("planning_request") or {}
    plan = result.get("recommended_plan") or result.get("recovery_plan")
    if isinstance(result.get("approved_plan"),dict):plan=result["approved_plan"]
    if result.get("status") == "draft":
        context["current_scenario"] = result
        context["scenario_id"] = result.get("scenario_id")
        context["scenario_status"] = "draft"
        context["scenario_changes"] = result.get("changes") or {}
        context["scenario_comparison"] = result.get("comparison")
        context["baseline_plan"] = (result.get("baseline") or {}).get("recommended_plan")
        # A draft is inspectable context, not the active plan. Keep the existing
        # active baseline until an explicit scenario_action(apply).
        plan = None if previous else (result.get("baseline") or {}).get("recommended_plan")
        request = {} if previous else (result.get("baseline") or {}).get("planning_request") or request
    if isinstance(request, dict):
        if request:
            context["planning_request"] = request
            if request.get("allowed_modes"):
                context["allowed_modes"] = request["allowed_modes"]
        shipment = request.get("shipment") or {}
        for key in ("source", "destination", "objective", "deadline"):
            if request.get(key) is not None:
                context[key] = request[key]
        if shipment.get("weight_kg") is not None:
            context["weight_kg"] = shipment["weight_kg"]
        if shipment.get("quantity") is not None:
            context["quantity"] = shipment["quantity"]
        for key in ("sku", "product", "product_id"):
            if shipment.get(key) is not None:
                context["sku"] = shipment[key]
    if isinstance(plan, dict):
        context.update({
            "selected_plan": plan,
            "selected_mode": plan.get("mode"),
            "selected_plan_id": plan.get("plan_id"),
            "route_legs": plan.get("route_legs") or [],
            "route_ids": [leg.get("route_id") for leg in plan.get("route_legs") or [] if leg.get("route_id") is not None],
            "assigned_vehicles": plan.get("vehicles") or [],
            "selected_warehouses": plan.get("inventory_allocation") or [],
            "cost": plan.get("operational_cost"),
            "eta": plan.get("eta") or plan.get("duration_hours"),
            "duration_hours": plan.get("duration_hours"),
            "risk": plan.get("risk_score"),
            "reliability": plan.get("reliability"),
            "deadline": plan.get("deadline") or context.get("deadline"),
            "sla_met": plan.get("sla_met"),
        })
    if isinstance(plan, dict) and result.get("applied_changes") is not None:
        context["planning_changes"] = result["applied_changes"]
    for key in ("shipment_id", "order_id"):
        if result.get(key) is not None:
            context[key] = result[key]
    if result.get("scenario_id") and result.get("status") in {"applied","discarded"}:
        context["scenario_status"] = result["status"]
        context.pop("current_scenario",None); context.pop("scenario_id",None)
    if result.get("recommended_hubs"):
        context["expansion_recommendation"] = result
    return {key: value for key, value in context.items() if value is not None}


def _is_context_route_disruption(message: str) -> bool:
    """Recognize a route outage plus a reference to the active shipment, not city-specific wording."""
    lower = message.casefold()
    outage = re.search(r"\b(?:unavailable|blocked|closed|cancelled|canceled|disrupted|disruption)\b", lower)
    reference = re.search(r"\b(?:current|this|my|new|direct)\s+(?:selected\s+)?(?:route|plan|shipment)\b|\breplan\s+it\b", lower)
    return bool(outage and reference and "route" in lower)


def _attach_replan_baseline(result: dict, context: dict, changes: dict | None) -> None:
    """Expose the actual prior selection without recomputing a baseline or changing plan totals."""
    before = context.get("selected_plan") or {
        "plan_id": context.get("selected_plan_id"),
        "mode": context.get("selected_mode") or _actual_mode({"route_legs": context.get("route_legs") or []}),
        "route_legs": context.get("route_legs") or [], "vehicles": context.get("assigned_vehicles") or [],
        "operational_cost": context.get("cost"), "duration_hours": context.get("duration_hours"),
        "risk_score": context.get("risk"), "reliability": context.get("reliability"),
    }
    result["baseline"] = {"planning_request": context.get("planning_request") or {}, "recommended_plan": before}
    result["applied_changes"] = changes or {}
    after = result.get("recommended_plan")
    if after:
        result["replan_comparison"] = {
            "cost_difference": round(after["operational_cost"] - before["operational_cost"], 2),
            "eta_difference_hours": round(after["duration_hours"] - before["duration_hours"], 2),
            "risk_difference": round(after["risk_score"] - before["risk_score"], 4),
        }


def _contextual_planning_params(message: str, params: dict, context: dict | None) -> tuple[dict, str | None]:
    """Resolve referential follow-ups centrally before MCP validation/execution."""
    context = context or {}
    lower = message.casefold()
    resolved = dict(params)
    nested = dict(resolved.get("parameters") or {})
    operation = resolved.get("operation")
    shipment = {"weight_kg": context.get("weight_kg"), "quantity": context.get("quantity", 1)}
    base = {
        "source": context.get("source"), "destination": context.get("destination"),
        "shipment": shipment, "objective": context.get("objective") or "balanced",
    }

    if any(x in lower for x in ("compare the draft","compare draft","draft scenario with")):
        scenario=context.get("current_scenario")
        if not scenario:return resolved,"There is no active draft scenario to compare. Create a what-if scenario first."
        operation="compare_scenario"; nested={"scenario_id":scenario.get("scenario_id")}
    elif any(x in lower for x in ("apply this draft","apply the draft","apply draft plan")):
        scenario=context.get("current_scenario")
        if not scenario:return resolved,"There is no active draft scenario to apply."
        operation="scenario_action"; nested={"scenario_id":scenario.get("scenario_id"),"action":"apply"}
    elif any(x in lower for x in ("discard the draft","discard draft","discard this draft")):
        scenario=context.get("current_scenario")
        if not scenario:return resolved,"There is no active draft scenario to discard."
        operation="scenario_action"; nested={"scenario_id":scenario.get("scenario_id"),"action":"discard"}
    elif "need it much faster" in lower or "need this much faster" in lower:
        if not all((base["source"],base["destination"],shipment.get("weight_kg"))):return resolved,"Which shipment should I make faster?"
        operation="plan"; nested={**base,"objective":"fastest"}
    elif any(x in lower for x in ("which option should i finally use","which plan should i finally use")):
        if not all((base["source"],base["destination"],shipment.get("weight_kg"))):return resolved,"Which shipment options should I compare?"
        operation="plan"; nested={**base,"objective":"balanced"}
    elif "current" in lower and "delayed by" in lower and "future shipment" in lower:
        vehicles=context.get("assigned_vehicles") or []
        delay=re.search(r"delayed by\s*([\d.]+)\s*hours?",lower)
        if not vehicles:return resolved,"Which vehicle or current shipment is delayed?"
        operation="future_replan"; nested={"vehicle_label":vehicles[0].get("label") or vehicles[0].get("id"),"delay_hours":float(delay.group(1)) if delay else 0}
    elif "facility expansion" in lower and any(x in lower for x in ("complete estimated cost","calculate complete","expansion cost")):
        expansion=context.get("expansion_recommendation")
        if not expansion:return resolved,"Which facility recommendation should I cost?"
        operation="expansion_cost"; nested={"recommendation":expansion}
    elif any(x in lower for x in ("where should we add a new facility","where should i add a new facility")):
        operation="expansion_network"; nested={}
    elif ("available inventory" in lower or "available storage" in lower or "warehouse capacity" in lower) and any(
            phrase in lower for phrase in ("selected for my current shipment", "selected warehouse", "current shipment")):
        warehouse=context.get("source")
        selected=context.get("selected_warehouses") or []
        names=[x.get("warehouse") for x in selected if isinstance(x,dict) and x.get("warehouse")]
        if warehouse and warehouse not in names:names.insert(0,warehouse)
        if not names:
            return resolved, "Which warehouse should I inspect?"
        operation="warehouse_capacity"
        nested={"warehouse_names":names}
    elif any(phrase in lower for phrase in ("preferred warehouse cannot fulfil", "preferred warehouse cannot fulfill", "alternative warehouse")):
        if all(nested.get(key) is not None for key in ("destination","quantity","weight_kg")):
            operation="fulfilment"
        else:
            if not context.get("destination") or not context.get("source"):
                return resolved, "Which preferred warehouse and delivery destination should I evaluate?"
            if not context.get("sku") or context.get("quantity") in (None,1):
                return resolved, "Which product/SKU and quantity should I check across alternative warehouses?"
            operation="fulfilment"
            nested={"destination":context["destination"],"quantity":context["quantity"],"weight_kg":context.get("weight_kg"),
                    "objective":context.get("objective") or "balanced","excluded_warehouses":[context["source"]],"sku":context["sku"]}
    elif any(x in lower for x in ("available inventory","available storage","warehouse utilization","utilization for every warehouse")):
        operation="warehouse_capacity"; nested=dict(nested)
    elif _is_context_route_disruption(message):
        operation = "route_alternatives"
        legs = context.get("route_legs") or []
        if not all((base["source"], base["destination"], shipment.get("weight_kg"))):
            return resolved, "Which shipment route should I replan? Please share its origin, destination, and weight."
        # Explicit endpoints must identify a selected leg. Otherwise a single-leg
        # current plan is unambiguous; never silently choose a leg in a multi-leg plan.
        named = re.search(r"route\s+from\s+(.+?)\s+to\s+(.+?)\s+(?:is|has become)\s+(?:blocked|unavailable|closed|cancelled|disrupted)", message, re.I)
        matches = legs
        if named:
            matches = [leg for leg in legs if all(
                re.search(r"(?<!\w)" + re.escape(name.strip()) + r"(?!\w)", str(leg.get(field) or ""), re.I)
                for name, field in zip(named.groups(), ("from_location", "to_location")))]
        if len(matches) != 1:
            return resolved, "Which leg of the current route is unavailable? Please name its start and end locations."
        blocked = matches[0]
        if not blocked.get("from_location") or not blocked.get("to_location"):
            return resolved, "Which route should I treat as disrupted?"
        inherited = dict(context.get("planning_request") or {})
        modes = context.get("allowed_modes") or inherited.get("allowed_modes")
        if not modes:
            mode = context.get("selected_mode") or _actual_mode({"route_legs": legs})
            modes = [mode] if mode in {"road", "air", "multimodal"} else ["road", "air", "multimodal"]
        changes = dict(context.get("planning_changes") or {})
        pairs = list(changes.get("blocked_routes") or [])
        pair = [blocked["from_location"], blocked["to_location"]]
        if pair not in pairs:
            pairs.append(pair)
        changes["blocked_routes"] = pairs
        nested = {**inherited, **base, "shipment": {**(inherited.get("shipment") or {}), **shipment},
                  "allowed_modes": modes, "changes": changes}
    elif any(x in lower for x in ("assigned vehicle broke down", "assigned vehicle breaks down", "assigned vehicle for my shipment broke down")):
        operation = "breakdown_recovery"
        vehicles = context.get("assigned_vehicles") or []
        if not vehicles:
            return resolved, "Which vehicle broke down? Please provide its vehicle label."
        if not context.get("destination") or context.get("weight_kg") is None:
            return resolved, "What is the remaining shipment destination and weight?"
        nested = {
            "vehicle_label": vehicles[0].get("label") or vehicles[0].get("id"),
            "current_location": context.get("source"), "destination": context["destination"],
            "remaining_weight_kg": context["weight_kg"], "plan_id": context.get("selected_plan_id"),
        }
    elif any(x in lower for x in ("multiple warehouses fulfil", "multiple warehouses fulfill")):
        operation = "fulfilment"
        quantity = context.get("quantity")
        destination = context.get("destination")
        weight = context.get("weight_kg")
        if not context.get("sku") or quantity in (None, 1):
            return resolved, "Which product/SKU and quantity should I check across the warehouses?"
        if not destination:
            return resolved, "Where should the inventory be delivered?"
        nested = {"destination": destination, "quantity": quantity, "weight_kg": weight or float(quantity), "objective": context.get("objective") or "balanced"}

    # Operation-driven reference resolution also covers wording unseen by the
    # compatibility parser. Never infer a post-dispatch location from origin.
    if operation == "breakdown_recovery":
        explicit = dict((params.get("parameters") or {}))
        nested.update({key: value for key, value in explicit.items() if value is not None})
        if not explicit.get("current_location"):
            return resolved, "Where is the broken-down vehicle now? Provide the current recovery location."
        vehicles = context.get("assigned_vehicles") or []
        if not nested.get("vehicle_label") and len(vehicles) == 1:
            nested["vehicle_label"] = vehicles[0].get("label")
        if not nested.get("vehicle_label"):
            return resolved, "Which assigned vehicle broke down?"
        nested.setdefault("destination", context.get("destination"))
        nested.setdefault("remaining_weight_kg", context.get("weight_kg"))
        nested.setdefault("deadline", context.get("deadline"))
    if operation == "warehouse_capacity":
        explicit = params.get("parameters") or {}
        for key in ("warehouse_names", "warehouse_name"):
            if explicit.get(key):
                nested[key] = explicit[key]
    if operation == "fulfilment":
        for key in ("destination", "quantity", "weight_kg", "objective", "deadline", "sku"):
            if nested.get(key) is None and context.get(key) is not None:
                nested[key] = context[key]
    if operation == "future_replan":
        vehicles = context.get("assigned_vehicles") or []
        if not nested.get("vehicle_label") and len(vehicles) == 1:
            nested["vehicle_label"] = vehicles[0].get("label")

    # Shared request merge precedes each operation's MCP adapter. Missing values
    # are not defaults: current-turn values win, including nested shipment fields.
    if any(x in lower for x in ("international", "global multimodal", "gateway")):
        operation = "global_plan"
    fuel = re.search(r"fuel cost (?:increases?|rises?) by\s*([\d.]+)\s*(?:%|percent)", message, re.I)
    if fuel:
        operation = "create_scenario"
        nested["changes"] = {**(nested.get("changes") or {}), "fuel_cost_multiplier": 1 + float(fuel.group(1)) / 100}
    request_operations = {"plan", "route_alternatives", "route_comparison", "risk", "vehicle_selection",
                          "sla_plan", "compare_modes", "global_plan", "create_scenario", "what_if", "disruption_mitigation", "mitigate_disruption"}
    if operation in request_operations:
        nested = _canonicalize_planning_values(nested)
        inherited = {**base, **(context.get("planning_request") or {})}
        explicit = {key: value for key, value in nested.items() if value is not None}
        nested = {**inherited, **explicit, "shipment": {
            **(inherited.get("shipment") or {}),
            **{key: value for key, value in (explicit.get("shipment") or {}).items() if value is not None}}}
        missing = [key for key in ("source", "destination") if not nested.get(key)]
        if not nested["shipment"].get("weight_kg"): missing.append("weight_kg")
        if missing:
            return resolved, "Missing required information: " + ", ".join(missing) + ". Please provide it."
        changes = {**(context.get("planning_changes") or {}), **(nested.get("changes") or {})}
        if changes: nested["changes"] = changes
        if operation in {"create_scenario", "what_if"} and context.get("selected_plan"):
            nested["baseline"] = {"planning_request": context.get("planning_request") or inherited,
                                  "recommended_plan": context["selected_plan"]}
    if operation in {"scenario_action", "compare_scenario"}:
        nested.setdefault("scenario_id", context.get("scenario_id"))

    if operation:
        from backend.planning.intent import CanonicalPlanningIntent
        try:
            nested = CanonicalPlanningIntent(operation=operation, parameters=nested).resolve(context)
        except ValueError as exc:
            return resolved, str(exc)
        resolved = {"user_id": resolved.get("user_id", 0), "operation": operation, "parameters": nested}
    return resolved, None

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
        self.llm_status = provider_status()
        try:
            self.llm = create_chat_model()
            logger.info("LLM initialized: provider=%s deployment=%s",
                        self.llm_status.provider, self.llm_status.deployment)
        except LLMConfigurationError:
            logger.warning("LLM is unavailable: %s", self.llm_status.error_code)

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

        params = _adapt_canonical_params("canonical", params)
        operation = params.get("operation")
        if isinstance(operation, str):
            normalized_operation = operation.strip().casefold().replace("-", "_").replace(" ", "_")
            if normalized_operation in {"express_vs_ground", "road_vs_air", "mode_comparison", "compare_transport_modes"}:
                normalized_operation = "compare_modes"
            if normalized_operation in {"breakdown", "vehicle_breakdown", "breakdown_plan", "recover_breakdown"}:
                normalized_operation = "breakdown_recovery"
            if normalized_operation in {"fulfillment", "alternative_warehouse", "alternative_warehouse_fulfillment", "multi_warehouse_fulfillment"}:
                normalized_operation = "fulfilment"
            if normalized_operation in {"what_if_plan", "what_if_scenario", "scenario", "scenario_analysis", "simulate_scenario"}:
                normalized_operation = "create_scenario"
            if normalized_operation in {"international_plan", "global_routing", "global_multimodal_plan"}:
                normalized_operation = "global_plan"
            params["operation"] = normalized_operation

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
        if tool_name in {"unified_supply_chain_plan", "supply_chain_planning_operation"}:
            return _format_planning_result(result, user_message)
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
            return clean_llm_response(_response_text(response.content))
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
            "Disruption Management": ["manage_disruption_tool"],
            "Supply Chain Planning": [
                "unified_supply_chain_plan", "supply_chain_planning_operation"
            ],
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
5. Use unified_supply_chain_plan for shipment optimization, intermediate-hub shipment plans, mode comparison, cost, ETA, risk, SLA, vehicle and warehouse decisions
6. Use supply_chain_planning_operation for scenarios, fulfilment, breakdown recovery, consolidation, optimizing the order of multiple stops, future replanning, expansion and transport-scope analysis
7. Never invent operational values; route, cost, ETA, risk, SLA, vehicle, inventory, revenue and margin values must come from tool results

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

            content = _response_text(response.content)
            tool_names = [n.strip() for n in content.split(",") if n.strip()]
            available_tools = [n for n in tool_names if n in self.tool_metadata]
            # Unified planning already performs route, warehouse and vehicle
            # selection deterministically. Do not re-enter the legacy graph for
            # redundant operational tools selected alongside it.
            if "supply_chain_planning_operation" in available_tools:
                available_tools = ["supply_chain_planning_operation"]
            elif "unified_supply_chain_plan" in available_tools:
                available_tools = ["unified_supply_chain_plan"]
            elif "supply_chain_planning_operation" in available_tools:
                available_tools = ["supply_chain_planning_operation"]
            message_lower = user_message.casefold()
            if (_is_shipment_plan_request(user_message) and
                    "unified_supply_chain_plan" in self.tool_metadata):
                available_tools = ["unified_supply_chain_plan"]
            if ("route" in message_lower and
                    any(word in message_lower for word in ("blocked", "unavailable", "cancelled", "disrupted", "disruption"))):
                available_tools = ["supply_chain_planning_operation"]
            mode_comparison = _is_mode_comparison(user_message)
            if (mode_comparison and
                    "supply_chain_planning_operation" in self.tool_metadata):
                available_tools = ["supply_chain_planning_operation"]
            if _is_vehicle_planning_request(user_message):
                available_tools = (["supply_chain_planning_operation"] if "unavailable" in message_lower
                                   else ["unified_supply_chain_plan"])
            if any(x in message_lower for x in ("broke down", "breakdown", "broken vehicle")):
                available_tools = ["supply_chain_planning_operation"]
            if any(x in message_lower for x in ("fulfil", "fulfill", "warehouses cover", "warehouse allocation", "alternative warehouse")):
                available_tools = ["supply_chain_planning_operation"]
            if any(x in message_lower for x in ("what-if", "what if", "scenario", "mitigate", "mitigation", "consolidat", "multi-stop", "stop order", "required stops", "warehouse capacity", "available storage", "future shipment", "affected future", "network expansion", "new facility", "candidate facilit", "expansion cost", "international", "global multimodal", "frankfurt", "singapore", "london", "dubai")):
                available_tools = ["supply_chain_planning_operation"]
            if any(x in message_lower for x in ("need it much faster","need this much faster","apply this draft","discard the draft","compare the draft","which option should i finally use","new route becomes disrupted")):
                available_tools = ["supply_chain_planning_operation"]

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

        if self.llm is None:
            return {
                "success": False,
                "response": (
                    self.llm_status.message or "AI chat is unavailable due to incomplete configuration."
                ),
                "actions": [],
                "error_code": self.llm_status.error_code or "LLM_NOT_CONFIGURED",
            }

        # ── 1. Load history & record the incoming user message ──────────
        history = await self._load_history(user_id)
        active_context = await get_active_planning_context(user_id) or {}
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
                reply = clean_llm_response(_response_text(response.content))

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
- Extract only explicitly supplied current-turn values; omit missing fields and defaults.
- Use operation plan for optimization, compare_modes for transport comparison, create_scenario for what-if drafts.
- Available operations: plan, compare_modes, route_alternatives, route_comparison, risk, vehicle_selection, sla_plan, disruption_mitigation, breakdown_recovery, fulfilment, warehouse_capacity, consolidation, optimize_utilization, multi_stop, future_replan, expansion, global_plan, create_scenario, compare_scenario, scenario_action.
- warehouse_capacity parameters: warehouse_names (list of the explicitly requested warehouse names). Omit this only for an all-warehouse query.
- breakdown_recovery parameters: vehicle_label, current_location, destination, remaining_weight_kg, deadline. Never substitute shipment origin for an unknown breakdown location.
- fulfilment parameters: destination, quantity, weight_kg, objective, deadline, sku, excluded_warehouses.
- For fleet utilization improvement use optimize_utilization; it takes shipments with origins, destinations, weights and deadlines.
- consolidation parameters: shipments, a list of shipment_id/source/destination/weight_kg/deadline/planned_departure.
- multi_stop parameters: source, destination, stops, shipment with weight_kg and quantity, objective.
- future_replan parameters: vehicle_label, delay_hours.
- scenario_action parameters: action (apply, discard, draft), scenario_id only if supplied. "Keep as draft" uses action draft.
- compare_scenario compares the current draft with its baseline without changing either.
- For an earlier relative deadline, use create_scenario with deadline_advance_hours as a positive number of hours. Do not invent an absolute timestamp.
- disruption_mitigation uses the same shipment fields and changes object as create_scenario; a risk increase is changes.risk_delta.
- create_scenario requires changes. Supported keys: fuel_cost_multiplier, demand_quantity, demand_weight_kg, deadline, allowed_modes, blocked_routes (endpoint pairs), unavailable_vehicles (labels), unavailable_warehouses (names), inventory_changes (warehouse/inventory), cost_multiplier, risk_delta.
- Fuel rises by X percent means fuel_cost_multiplier = 1 + X/100. Keep explicit current-turn changes even when a prior scenario used different values.
- expansion parameters: demand_locations and candidate_hubs with names, coordinates, demand/capacity, only explicitly supplied costs; hubs_to_open. Never assume property, construction or transport rates.
- References to a current shipment or plan are resolved by the server; do not put these phrases in source or destination.
- Never invent source/destination countries. Use the supplied endpoints; authoritative network metadata resolves countries.
"""),
                    HumanMessage(content=message),
                ]

                param_response = await self.llm.ainvoke(param_messages)
                log_token_usage("param_extraction", user_id, param_response)

                try:
                    params = json.loads(_response_text(param_response.content))
                    params["user_id"] = user_id
                    
                    params = self._normalize_warehouse_params(params, user_id)
                    params = _adapt_canonical_params(tool_name, params)
                    explicit_deadline = _deadline_from_message(message)
                    explicit_objective = _objective_from_message(message)
                    if explicit_objective:
                        target = params.get("parameters") if isinstance(params.get("parameters"), dict) else params
                        target["objective"] = explicit_objective
                    if explicit_deadline:
                        target = params.get("parameters") if isinstance(params.get("parameters"), dict) else params
                        target["deadline"] = explicit_deadline
                    explicit_weight = _weight_kg_from_message(message)
                    if explicit_weight is not None:
                        target = params.get("parameters") if isinstance(params.get("parameters"), dict) else params
                        if isinstance(target.get("shipment"),dict): target["shipment"]["weight_kg"]=explicit_weight
                        elif tool_name == "unified_supply_chain_plan": target["weight_kg"]=explicit_weight
                    message_lower = message.casefold()
                    mitigation = _disruption_mitigation_params(
                        message, [w["name"] for w in get_warehouses_by_userall(user_id)])
                    vehicle_selection = _vehicle_selection_params(
                        message, [w["name"] for w in get_warehouses_by_userall(user_id)])
                    breakdown = _breakdown_recovery_params(
                        message, [w["name"] for w in get_warehouses_by_userall(user_id)])
                    fulfilment = _fulfilment_params(
                        message, [w["name"] for w in get_warehouses_by_userall(user_id)])
                    scenario_params = _scenario_params(message)
                    specialized_params = _specialized_operation_params(message)
                    disruption = _route_disruption_params(message)
                    if tool_name == "supply_chain_planning_operation" and mitigation:
                        mitigation["user_id"] = user_id
                        params = mitigation
                    elif tool_name == "supply_chain_planning_operation" and specialized_params:
                        specialized_params["user_id"] = user_id
                        params = specialized_params
                    elif tool_name == "supply_chain_planning_operation" and breakdown:
                        breakdown["user_id"] = user_id
                        params = breakdown
                    elif tool_name == "supply_chain_planning_operation" and fulfilment:
                        fulfilment["user_id"] = user_id
                        params = fulfilment
                    elif tool_name == "supply_chain_planning_operation" and scenario_params:
                        scenario_params["user_id"] = user_id
                        params = scenario_params
                    elif tool_name == "supply_chain_planning_operation" and vehicle_selection:
                        vehicle_selection["user_id"] = user_id
                        params = vehicle_selection
                    elif tool_name == "supply_chain_planning_operation" and disruption:
                        params = {"user_id": user_id, "operation": "route_alternatives", "parameters": disruption}
                    if tool_name == "supply_chain_planning_operation" and _is_mode_comparison(message):
                        params["operation"] = "compare_modes"
                    if tool_name == "unified_supply_chain_plan" and "compare" in message.casefold():
                        if params.get("objective") not in {"cheapest", "fastest", "lowest-risk", "balanced"}:
                            params["objective"] = "balanced"
                    message_lower = message.casefold()
                    if tool_name == "supply_chain_planning_operation" and _is_mode_comparison(message):
                        params["operation"] = "compare_modes"

                    if tool_name in {"supply_chain_planning_operation", "unified_supply_chain_plan"}:
                        if tool_name == "unified_supply_chain_plan":
                            params = {"user_id": user_id, "operation": "plan", "parameters": _canonicalize_planning_values(params)}
                        params, contextual_clarification = _contextual_planning_params(
                            message, params, active_context
                        )
                        params["user_id"] = user_id
                        if contextual_clarification:
                            history = await self._append_and_save(
                                user_id, history, "assistant", contextual_clarification
                            )
                            return {"success": True, "response": contextual_clarification, "actions": []}

                        # Use the operation adapter for inherited network changes too.
                        if tool_name == "unified_supply_chain_plan" and params.get("operation") == "plan" and not params.get("parameters", {}).get("changes"):
                            params = {**params["parameters"], "user_id": user_id}
                        else:
                            tool_name = "supply_chain_planning_operation"
                            tool = next(t for t in self.tools if t.name == tool_name)
                        params = _adapt_canonical_params(tool_name, params)

                    # Validate schema
                    try:
                        validated = tool.args_schema.model_validate(params)
                    except Exception as e:
                        logger.warning("Tool parameter validation failed tool=%s params=%s errors=%s",
                                       tool_name, params, e.errors() if hasattr(e, "errors") else str(e))
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

                    if active_context and (tool_name == "unified_supply_chain_plan" or
                            params.get("operation") in {"route_alternatives","breakdown_recovery","plan"}):
                        result["_active_plan_before"] = {
                            "mode": _actual_mode({"route_legs": active_context.get("route_legs") or []}),
                            "route_legs": active_context.get("route_legs") or [],
                            "vehicles": active_context.get("assigned_vehicles") or [],
                            "cost": active_context.get("cost"),
                            "duration_hours": active_context.get("duration_hours"),
                            "risk": active_context.get("risk"), "deadline": active_context.get("deadline"),
                            "sla_met": active_context.get("sla_met"),
                        }

                    if active_context and (tool_name == "unified_supply_chain_plan" or
                            params.get("operation") in {"route_alternatives", "plan"}):
                        _attach_replan_baseline(result, active_context, params.get("parameters", {}).get("changes"))

                    # Tool failure (domain-level) — return empty actions regardless of tool
                    if not self._is_tool_success(tool_name, result):
                        failure_msg = await self._llm_response(message, tool_name, result, user_id)
                        history = await self._append_and_save(
                            user_id, history, "assistant", failure_msg
                        )
                        return {"success": True, "response": failure_msg, "actions": []}

                    # Build conversational reply
                    llm_reply = await self._llm_response(message, tool_name, result, user_id)
                    result.pop("_active_plan_before", None)

                    if tool_name in {"unified_supply_chain_plan", "supply_chain_planning_operation"}:
                        updated_context = _context_from_result(result, active_context)
                        if updated_context:
                            await set_active_planning_context(user_id, updated_context)

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

                except (ValueError, KeyError) as exc:
                    error_msg = "Planning inputs need correction: " + str(exc)
                    history = await self._append_and_save(user_id, history, "assistant", error_msg)
                    return {"success": False, "response": error_msg, "actions": []}

                except Exception:
                    error_msg = "I couldn't complete that planning request. Please check the locations and constraints and try again."
                    logger.error("Tool execution failed for tool=%s", tool_name, exc_info=True)
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

        except Exception:
            error_msg = "The AI request could not be completed. Please retry shortly."
            logger.exception("AI request processing failed")
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
