"""Strict, resumable Group 8 route-comparison acceptance runner."""
import asyncio
import json
import math
import time
from pathlib import Path

import httpx

from backend.config.redis import delete_data
from backend.core.security import create_access_token
from backend.mcp.tools.tool_client import load_mcp_tools
from backend.planning.models import PlanningRequest, Shipment
from backend.planning.service import PlanningService


CASES = [
    ("Compare the feasible route alternatives for 3000 kg Delhi to Mumbai. Show exact cost, ETA, risk, SLA and utilization differences and recommend one.", 3000, "balanced"),
    ("For 1200 kg Delhi to Mumbai, compare every route by cost, travel time, risk, SLA and vehicle utilization. Which route should I take?", 1200, "balanced"),
    ("What are the exact differences between the cheapest route alternatives from Delhi to Mumbai for a 500 kg load?", 500, "cheapest"),
    ("Compare Delhi to Mumbai routes for 6000 kg and recommend the fastest feasible one, with exact deltas.", 6000, "fastest"),
    ("I need the lowest-risk route for 2500 kg Delhi to Mumbai. Compare alternatives including cost, ETA, SLA, risk, and utilization differences.", 2500, "lowest-risk"),
]


def validate(result, weight, objective):
    request = result["planning_request"]
    assert request["objective"] == objective
    assert math.isclose(request["shipment"]["weight_kg"], weight)
    chosen = result["recommended_plan"]
    candidates = result["candidate_plans"]
    assert chosen and len(candidates) >= 2 and result["recommended_plan_id"] == chosen["plan_id"]
    if objective == "cheapest":
        assert chosen["operational_cost"] == min(x["operational_cost"] for x in candidates)
    elif objective == "fastest":
        assert chosen["duration_hours"] == min(x["duration_hours"] for x in candidates)
    elif objective == "lowest-risk":
        assert chosen["risk_score"] == min(x["risk_score"] for x in candidates)
    indexed = {x["plan_id"]: x for x in candidates}
    assert len(result["comparison"]) == len(candidates) - 1
    for delta in result["comparison"]:
        other = indexed[delta["plan_id"]]
        assert delta["cost_difference"] == round(other["operational_cost"] - chosen["operational_cost"], 2)
        assert delta["time_difference_hours"] == round(other["duration_hours"] - chosen["duration_hours"], 2)
        assert delta["risk_difference"] == round(other["risk_score"] - chosen["risk_score"], 4)
        assert delta["sla_difference"] == {"recommended": chosen["sla_met"], "alternative": other["sla_met"]}
        assert delta["utilization_difference"] == round(other["vehicle_utilization"] - chosen["vehicle_utilization"], 4)
    return chosen


def validate_answer(answer, result):
    chosen = result["recommended_plan"]
    for value in (chosen["operational_cost"], chosen["duration_hours"], chosen["risk_score"]):
        assert str(value) in answer
    for delta in result["comparison"]:
        for field in ("cost_difference", "time_difference_hours", "risk_difference", "utilization_difference"):
            assert str(delta[field]) in answer


async def main():
    service = PlanningService()
    operation = next(x for x in await load_mcp_tools() if x.name == "supply_chain_planning_operation")
    token = create_access_token({"user_id": 5})
    records = []
    async with httpx.AsyncClient(timeout=180) as client:
        for number, (question, weight, objective) in enumerate(CASES, 1):
            record = {"group": 8, "requirement": "Route Comparison", "question_number": number,
                      "question": question, "service_status": "FAIL", "mcp_status": "FAIL",
                      "chat_status": "FAIL", "validation": {}, "latency": {}, "failure_reason": None,
                      "root_cause": None, "bugs_fixed": [], "final_status": "FAIL"}
            try:
                request = PlanningRequest(source="Delhi", destination="Mumbai",
                                          shipment=Shipment(weight_kg=weight), objective=objective)
                started = time.perf_counter(); direct = service.plan(5, request)
                validate(direct, weight, objective)
                record["latency"]["planner_ms"] = round((time.perf_counter() - started) * 1000, 3)
                record["service_status"] = "PASS"
                started = time.perf_counter()
                mcp = await operation.ainvoke({"user_id": 5, "operation": "route_comparison",
                                               "parameters": request.model_dump(mode="json")})
                validate(mcp, weight, objective)
                record["latency"]["mcp_ms"] = round((time.perf_counter() - started) * 1000, 3)
                record["mcp_status"] = "PASS"
                await delete_data(5); started = time.perf_counter()
                response = await client.post("http://127.0.0.1:4200/mcp-agent",
                    headers={"Authorization": "Bearer " + token}, json={"message": question})
                record["latency"]["chat_ms"] = round((time.perf_counter() - started) * 1000, 3)
                body = response.json(); actions = body.get("actions") or []
                assert response.status_code == 200 and body.get("success") is True
                assert actions and actions[0]["type"] in {"unified_supply_chain_plan", "supply_chain_planning_operation"}
                data = actions[0]["data"]; chosen = validate(data, weight, objective)
                validate_answer(body["response"], data)
                record["chat_status"] = "PASS"; record["final_status"] = "PASS"
                record["validation"] = {"candidate_count": len(data["candidate_plans"]),
                    "comparison_count": len(data["comparison"]), "recommended_plan_id": chosen["plan_id"]}
            except Exception as exc:
                record["failure_reason"] = f"{type(exc).__name__}: {exc}"
            records.append(record)
            print(json.dumps(record), flush=True)
    path = Path("tests/acceptance_results.json")
    existing = json.loads(path.read_text()) if path.exists() else []
    existing = [x for x in existing if x.get("group") != 8] + records
    path.write_text(json.dumps(existing, indent=2) + "\n")
    print(json.dumps({"group": 8, "passed": sum(x["final_status"] == "PASS" for x in records), "total": 5}))


if __name__ == "__main__":
    asyncio.run(main())
