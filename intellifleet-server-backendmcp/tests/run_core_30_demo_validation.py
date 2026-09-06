"""Fast, independent real-chat validation for IntelliFleet's 30 demo capabilities."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from backend.config.redis import delete_data
from backend.core.security import create_access_token


BASE_URL = "http://127.0.0.1:4200"
JSON_REPORT = Path("tests/core_30_demo_run.json")
MARKDOWN_REPORT = Path("tests/core_30_demo_run.md")
FORBIDDEN = (
    "validation error", "NoneType", "KeyError", "Traceback",
    "Internal Server Error", "Field required", "SLA met: None",
)


def validate_decision_support_answer(answer: str) -> tuple[bool, str]:
    """Require both a decision and a planner-grounded explanation for PS27."""
    lower = answer.casefold()
    has_decision = any(term in lower for term in ("recommend", "recommendation", "should choose", "should use"))
    factors = ("cost", "eta", "time", "risk", "reliability", "utilization", "score", "alternative")
    mentioned_factors = [factor for factor in factors if factor in lower]
    has_explanation = any(term in lower for term in ("why:", "because", "reason", "trade-off", "tradeoff"))
    if not has_decision:
        return False, "answer missing recommendation/decision"
    if not mentioned_factors or not (has_explanation or len(mentioned_factors) >= 2):
        return False, "answer missing planner-grounded reason"
    return True, "recommendation and planner-grounded explanation validated"


def golden_cases() -> list[dict[str, Any]]:
    deadline = (datetime.now(timezone.utc) + timedelta(hours=30)).isoformat()
    rows = [
        (1, "End-to-end network planning", "Plan the best end-to-end shipment of 8000 kg from Delhi to Mumbai using road, air or multimodal transport with a balanced objective.", "plan"),
        (2, "Cheapest routing", "Find the cheapest feasible way to move 6000 kg from Delhi to Mumbai.", "plan"),
        (3, "Fastest routing", "Find the fastest feasible way to transport 6000 kg from Delhi to Mumbai.", "plan"),
        (4, "Multi-objective planning", "Plan 8000 kg from Delhi to Mumbai using the best overall balance of cost, delivery time, reliability and risk.", "plan"),
        (5, "Express vs Ground comparison", "Compare Ground and Express for 6000 kg from Delhi to Mumbai. Which should I choose?", "compare_modes"),
        (6, "Pricing / revenue / margin", "Find the cheapest Delhi to Mumbai plan for 6000 kg and price it at a 25 percent target margin.", "plan"),
        (7, "Route alternatives", "The route from Delhi to Jaipur is blocked. Replan 3000 kg from Delhi to Mumbai and show the best alternative.", "route_alternatives"),
        (8, "Route comparison", "Compare the recommended route with the next best route for 3000 kg from Delhi to Mumbai and show exact changes.", "route_comparison"),
        (9, "Disruption risk", "Which Delhi to Mumbai plan for 3000 kg has the lowest disruption risk?", "risk"),
        (10, "Disruption mitigation", "Assume disruption risk increases by 0.2. Mitigate and replan 3000 kg from Delhi to Mumbai with a baseline comparison.", "disruption_mitigation"),
        (11, "Vehicle selection / multi-vehicle", "Which vehicle or vehicles should I use for 18000 kg from Delhi to Mumbai?", "plan"),
        (12, "Road vs Air", "Should I use road or air for 6000 kg from Delhi to Mumbai? Compare both.", "compare_modes"),
        (13, "Vehicle breakdown recovery", "TRK-003 broke down at Delhi with 3000 kg remaining. Find replacement vehicles and recover the shipment to Mumbai.", "breakdown_recovery"),
        (14, "Alternative warehouse", "Use alternative warehouses to fulfil 120 units totaling 1200 kg to Mysuru using the cheapest allocation.", "fulfilment"),
        (15, "Multi-warehouse fulfilment", "Can warehouses cover 1500 units totaling 12000 kg to Mumbai using the cheapest multi-warehouse allocation?", "fulfilment"),
        (16, "Warehouse capacity", "Show available inventory, available storage and utilization for every warehouse.", "warehouse_capacity"),
        (17, "Load consolidation", "Consolidate shipment S1 of 1000 kg and shipment S2 of 1200 kg, both from Delhi to Mumbai, and compare separate versus consolidated cost and utilization.", "consolidation"),
        (18, "Multi-stop optimization", "Optimize a 3000 kg road shipment from Delhi to Mumbai stopping at Jaipur and Ahmedabad. Show the best stop order.", "multi_stop"),
        (19, "Vehicle utilization", "Plan 18000 kg from Delhi to Mumbai and show capacity, assigned load and utilization for every assigned vehicle.", "plan"),
        (20, "What-if scenarios", "Create a what-if plan for 6000 kg Delhi to Mumbai if fuel cost increases by 20 percent. Do not apply it.", "create_scenario"),
        (21, "Baseline vs scenario", "Compare the baseline with a what-if plan for 6000 kg Delhi to Mumbai if fuel cost increases by 20 percent. Show exact changes and do not apply it.", "create_scenario"),
        (22, "Future shipment cascading replanning", "TRK-003 is delayed by 6 hours. Show affected future shipments and replan them.", "future_replan"),
        (23, "SLA planning", f"Plan 6000 kg from Delhi to Mumbai by {deadline} and report whether the SLA is met.", "sla_plan"),
        (24, "Network expansion / facility planning", "Evaluate candidate facilities Jaipur at latitude 26.9124 longitude 75.7873 and Nagpur at latitude 21.1458 longitude 79.0882, each with capacity 5000 and facility cost 1000000, against demand 1000 at Delhi latitude 28.6139 longitude 77.2090 and demand 800 at Mumbai latitude 19.076 longitude 72.8777. Recommend one facility.", "expansion"),
        (25, "Expansion cost", "Calculate complete expansion cost for candidate Jaipur at latitude 26.9124 longitude 75.7873 with capacity 5000, facility cost 1000000 and warehouse cost 200000 against demand 1000 at Delhi latitude 28.6139 longitude 77.2090 and demand 800 at Mumbai latitude 19.076 longitude 72.8777.", "expansion"),
        (26, "Domestic/global multimodal", "Plan 6000 kg from IF Delhi NCR Mega Hub in India to IF Frankfurt Gateway in Germany using global multimodal routing.", "global_plan"),
        (27, "Decision support", "Considering all feasible options for 6000 kg Delhi to Mumbai, what should I do and why?", "plan"),
        (28, "Explainability", "Explain why the recommended 6000 kg Delhi to Mumbai plan is better than alternatives using calculated cost, time and risk differences.", "route_comparison"),
        (29, "Plan-before-execution", "Create a what-if plan for 6000 kg Delhi to Mumbai if fuel cost increases by 10 percent, but do not apply it; let me apply or discard it.", "create_scenario"),
        (30, "Unified planner", "Plan 10000 kg from Delhi to Mumbai. Compare road, air and multimodal, choose warehouses and vehicles, evaluate cost, ETA and risk, and recommend the best overall plan.", "plan"),
    ]
    return [{"ps": ps, "capability": capability, "question": question, "expected": expected} for ps, capability, question, expected in rows]


def validate_plan(data: dict[str, Any]) -> tuple[bool, str]:
    plan = data.get("recommended_plan")
    if not isinstance(plan, dict):
        return False, "missing recommended plan"
    required = ("route_legs", "operational_cost", "duration_hours", "risk_score")
    if any(plan.get(field) is None for field in required) or not plan.get("route_legs"):
        return False, "route, cost, ETA, or risk is missing"
    if not 0 <= float(plan["risk_score"]) <= 1:
        return False, "risk is outside 0–1"
    if any(float(vehicle.get("utilization_percentage", 101)) > 100 for vehicle in plan.get("vehicles", [])):
        return False, "vehicle utilization exceeds 100%"
    return True, "calculated plan validated"


def validate_capability(ps: int, expected: str, data: dict[str, Any], answer: str) -> tuple[bool, str]:
    operation = data.get("planning_operation") or ("plan" if data.get("planning_request") else None)
    plan_aliases = {"risk", "route_comparison", "route_alternatives", "sla_plan"}
    if expected == "plan" or expected in plan_aliases:
        ok, reason = validate_plan(data)
    elif operation != expected:
        return False, f"expected {expected}, received {operation or 'no operation'}"
    elif expected == "compare_modes":
        options = data.get("options") or {}
        ok = bool(options.get("ground") and options.get("express") and data.get("express_vs_ground"))
        reason = "Ground and Express calculations validated" if ok else "two-mode comparison is incomplete"
    elif expected == "disruption_mitigation":
        ok = bool(data.get("recovery_plan") and data.get("comparison") and data.get("affected_resources"))
        reason = "disruption recovery and deltas validated" if ok else "disruption recovery is incomplete"
    elif expected == "breakdown_recovery":
        ok = bool(data.get("broken_vehicle") and data.get("replacement_vehicles") and data.get("recovery_plan"))
        reason = "breakdown recovery validated" if ok else "breakdown recovery is incomplete"
    elif expected == "fulfilment":
        ok = bool(data.get("fulfilled") and data.get("allocation"))
        reason = "warehouse allocation validated" if ok else "warehouse allocation is incomplete"
    elif expected == "warehouse_capacity":
        rows = data.get("warehouses") or []
        ok = bool(rows) and all("available_storage" in row and "utilization_percentage" in row for row in rows)
        reason = "capacity and utilization validated" if ok else "warehouse capacity is incomplete"
    elif expected == "consolidation":
        rows = data.get("consolidation_opportunities") or []
        ok = bool(rows) and all("savings" in row and "utilization_after" in row for row in rows)
        reason = "consolidation calculations validated" if ok else "consolidation result is incomplete"
    elif expected == "multi_stop":
        ok = bool(data.get("optimized_stop_sequence") and data.get("optimization_comparison"))
        reason = "optimized stop order validated" if ok else "multi-stop result is incomplete"
    elif expected == "create_scenario":
        ok = data.get("status") == "draft" and bool(data.get("baseline") and data.get("scenario") and data.get("comparison"))
        reason = "draft scenario and baseline deltas validated" if ok else "draft scenario is incomplete"
    elif expected == "future_replan":
        ok = isinstance(data.get("affected_shipments"), list) and "cascading_delays" in data
        reason = "future impact result validated" if ok else "future replanning result is incomplete"
    elif expected == "expansion":
        rows = data.get("recommended_hubs") or []
        ok = bool(rows) and all("incremental_cost" in row for row in rows)
        reason = "facility and expansion cost validated" if ok else "expansion calculation is incomplete"
    elif expected == "global_plan":
        ok = data.get("scope") == "international" and bool(data.get("gateway_sequence") and data.get("recommended_plan"))
        reason = "international gateways and plan validated" if ok else "global multimodal plan is incomplete"
    else:
        ok, reason = False, "no capability validator"

    if not ok:
        return False, reason
    if ps == 27:
        return validate_decision_support_answer(answer)
    lower = answer.casefold()
    checks = {
        2: ("recommend", "cost"), 3: ("recommend", "time"), 4: ("score", "risk"),
        5: ("ground", "express"), 6: ("selling price", "profit", "margin"),
        7: ("route", "alternative"), 8: ("delta",), 9: ("risk",),
        10: ("baseline", "scenario", "risk"), 11: ("vehicle",), 12: ("ground", "express"),
        13: ("replacement",), 14: ("warehouse",), 15: ("allocation",),
        16: ("available storage", "utilization"), 17: ("consolidat", "savings"),
        18: ("route",), 19: ("assigned load", "utilization"), 20: ("draft", "scenario"),
        21: ("baseline", "difference"), 22: ("future shipment",), 23: ("sla",),
        24: ("facility",), 25: ("incremental cost",), 26: ("route",),
        28: ("delta",), 29: ("draft", "apply", "discard"),
        30: ("recommend", "vehicles", "risk"),
    }
    missing = [term for term in checks.get(ps, ()) if term not in lower]
    return (False, "answer missing " + ", ".join(missing)) if missing else (True, reason)


async def main() -> None:
    started = time.perf_counter()
    token = create_access_token({"user_id": 5})
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=180) as client:
        selected = {int(value) for value in sys.argv[1:]}
        cases = [case for case in golden_cases() if not selected or case["ps"] in selected]
        for case in cases:
            await delete_data(5)
            item = {key: case[key] for key in ("ps", "capability", "question")}
            request_started = time.perf_counter()
            try:
                response = await client.post(
                    "/mcp-agent",
                    headers={"Authorization": "Bearer " + token},
                    json={"message": case["question"]},
                )
                latency = time.perf_counter() - request_started
                body = response.json()
                actions = body.get("actions") or []
                action = actions[0] if actions else {}
                data = action.get("data") or {}
                answer = str(body.get("response") or "")
                forbidden = [text for text in FORBIDDEN if text.casefold() in answer.casefold()]
                valid, reason = validate_capability(case["ps"], case["expected"], data, answer)
                passed = response.status_code == 200 and body.get("success") is True and bool(actions) and bool(answer) and valid and not forbidden
                if forbidden:
                    reason = "forbidden error text: " + ", ".join(forbidden)
                elif response.status_code != 200:
                    reason = f"HTTP {response.status_code}"
                elif body.get("success") is not True:
                    reason = "chat response success was false"
                elif not actions:
                    reason = "no MCP/planning action returned"
                item.update({
                    "http_status": response.status_code,
                    "success": body.get("success"),
                    "tool": action.get("type"),
                    "operation": data.get("planning_operation"),
                    "full_answer": answer,
                    "latency_seconds": round(latency, 3),
                    "basic_validation": "PASS" if passed else "FAIL",
                    "failure_reason": None if passed else reason,
                })
            except Exception as exc:
                item.update({
                    "http_status": None, "success": False, "tool": None, "operation": None,
                    "full_answer": "", "latency_seconds": round(time.perf_counter() - request_started, 3),
                    "basic_validation": "FAIL", "failure_reason": f"{type(exc).__name__}: {exc}",
                })
            results.append(item)

    total_time = round(time.perf_counter() - started, 3)
    JSON_REPORT.write_text(json.dumps({"total_time_seconds": total_time, "results": results}, indent=2))
    lines = [
        "# Core 30 Demo Validation", "",
        f"Executed sequentially through `{BASE_URL}/mcp-agent` using the configured real Azure provider.", "",
        "| PS | Capability | Result | Latency | Short reason |",
        "|---:|---|---|---:|---|",
    ]
    for item in results:
        reason = item["failure_reason"] or "Validated real chat, MCP operation, planner data, and answer"
        lines.append(f"| PS{item['ps']} | {item['capability']} | {item['basic_validation']} | {item['latency_seconds']:.3f}s | {reason.replace('|', '/')} |")
    MARKDOWN_REPORT.write_text("\n".join(lines) + "\n")
    failed = [f"PS{item['ps']}" for item in results if item["basic_validation"] != "PASS"]
    print(f"CORE CHAT TESTS: {len(results) - len(failed)}/{len(results)} PASS")
    print(f"FAILED PS: {failed}")
    print(f"TOTAL TIME: {total_time:.3f}s")
    print("REPORT: tests/core_30_demo_run.md")


if __name__ == "__main__":
    asyncio.run(main())
