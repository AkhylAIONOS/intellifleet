"""Incremental real acceptance runner. Results are merged only after execution."""
import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx

from backend.config.redis import delete_data
from backend.core.security import create_access_token
from backend.mcp.tools.tool_client import load_mcp_tools
from backend.planning.models import PlanningRequest, Shipment
from backend.planning.service import PlanningService


CASES = [
    (2, "Cost Optimization", "Find the cheapest way to move 6000 kg from Delhi to Mumbai.", "Delhi", "Mumbai", 6000, "cheapest", None),
    (2, "Cost Optimization", "Minimize calculated transport cost for 1200 kg from Delhi to Kochi.", "Delhi", "Kochi", 1200, "cheapest", None),
    (2, "Cost Optimization", "Choose the lowest-cost feasible plan for 500 kg from Mumbai to Bengaluru.", "Mumbai", "Bengaluru", 500, "cheapest", None),
    (2, "Cost Optimization", "Find the cheapest route for a 9000 kg Delhi to Chennai shipment.", "Delhi", "Chennai", 9000, "cheapest", None),
    (2, "Cost Optimization", "Compare feasible choices and recommend minimum cost for 2500 kg Hyderabad to Kolkata.", "Hyderabad", "Kolkata", 2500, "cheapest", None),
    (3, "Fastest Routing", "Find the fastest way to move 6000 kg from Delhi to Mumbai.", "Delhi", "Mumbai", 6000, "fastest", None),
    (3, "Fastest Routing", "Minimize delivery time for 500 kg from Delhi to Kochi.", "Delhi", "Kochi", 500, "fastest", None),
    (3, "Fastest Routing", "Choose the minimum ETA plan for 1200 kg Mumbai to Bengaluru.", "Mumbai", "Bengaluru", 1200, "fastest", None),
    (3, "Fastest Routing", "What is the quickest feasible shipment plan for 8000 kg Delhi to Chennai?", "Delhi", "Chennai", 8000, "fastest", None),
    (3, "Fastest Routing", "Recommend the fastest route for 2000 kg Hyderabad to Kolkata.", "Hyderabad", "Kolkata", 2000, "fastest", None),
    (4, "Multi-Objective", "Find the cheapest plan for 3000 kg Delhi to Mumbai.", "Delhi", "Mumbai", 3000, "cheapest", None),
    (4, "Multi-Objective", "Find the fastest plan for 3000 kg Delhi to Mumbai.", "Delhi", "Mumbai", 3000, "fastest", None),
    (4, "Multi-Objective", "Find the lowest-risk plan for 3000 kg Delhi to Mumbai.", "Delhi", "Mumbai", 3000, "lowest-risk", None),
    (4, "Multi-Objective", "Balance cost, time, risk, reliability and utilization for 3000 kg Delhi to Mumbai.", "Delhi", "Mumbai", 3000, "balanced", None),
    (4, "Multi-Objective", "Plan 1000 kg Delhi to Kochi with the lowest risk and maximum risk 0.20.", "Delhi", "Kochi", 1000, "lowest-risk", .20),
]


def validate_plan(result, objective, max_risk):
    plans = result.get("candidate_plans") or []
    chosen = result.get("recommended_plan")
    assert chosen and result.get("recommended_plan_id") == chosen.get("plan_id")
    assert chosen in plans
    if objective == "cheapest":
        assert chosen["operational_cost"] == min(x["operational_cost"] for x in plans)
    elif objective == "fastest":
        assert chosen["duration_hours"] == min(x["duration_hours"] for x in plans)
    elif objective == "lowest-risk":
        feasible = [x for x in plans if max_risk is None or x["risk_score"] <= max_risk]
        assert not feasible or chosen["risk_score"] == min(x["risk_score"] for x in feasible)
    assert 0 <= chosen["risk_score"] <= 1
    assert all(v.get("utilization_percentage", 0) <= 100 for v in chosen.get("vehicles", []))
    return chosen


async def main(groups):
    service = PlanningService()
    tools = await load_mcp_tools()
    unified = next(x for x in tools if x.name == "unified_supply_chain_plan")
    token = create_access_token({"user_id": 5})
    output = []
    async with httpx.AsyncClient(timeout=180) as client:
        for number, case in enumerate((x for x in CASES if x[0] in groups), 1):
            group, requirement, question, source, destination, weight, objective, max_risk = case
            record = {"group": group, "requirement": requirement, "question_number": number,
                      "question": question, "status": "FAIL", "api_status": "FAIL",
                      "mcp_status": "FAIL", "chat_status": "FAIL", "validation": {}, "bugs_fixed": []}
            try:
                request = PlanningRequest(source=source, destination=destination,
                                          shipment=Shipment(weight_kg=weight), objective=objective,
                                          max_risk=max_risk)
                started = time.perf_counter(); api = service.plan(5, request)
                chosen = validate_plan(api, objective, max_risk)
                record["api_status"] = "PASS"; record["validation"]["planner_latency_ms"] = round((time.perf_counter()-started)*1000, 3)
                started = time.perf_counter(); mcp = await unified.ainvoke({"user_id": 5, "source": source,
                    "destination": destination, "weight_kg": weight, "objective": objective, "max_risk": max_risk})
                validate_plan(mcp, objective, max_risk)
                record["mcp_status"] = "PASS"; record["validation"]["mcp_latency_ms"] = round((time.perf_counter()-started)*1000, 3)
                await delete_data(5); started = time.perf_counter()
                response = await client.post("http://127.0.0.1:4200/mcp-agent",
                    headers={"Authorization": "Bearer " + token}, json={"message": question})
                elapsed = time.perf_counter()-started; body = response.json(); actions = body.get("actions") or []
                assert response.status_code == 200 and body.get("success") is True
                assert actions and actions[0].get("type") == "unified_supply_chain_plan"
                chat_data = actions[0].get("data") or {}; chat_plan = validate_plan(chat_data, objective, max_risk)
                intent = chat_data.get("planning_request") or {}
                assert intent.get("objective") == objective and float(intent["shipment"]["weight_kg"]) == weight
                record["chat_status"] = "PASS"; record["status"] = "PASS"
                record["validation"].update({"chat_latency_s": round(elapsed, 3),
                    "recommended_plan_id": chat_data.get("recommended_plan_id"),
                    "cost": chat_plan["operational_cost"], "eta_hours": chat_plan["duration_hours"],
                    "risk": chat_plan["risk_score"]})
            except Exception as exc:
                record["validation"]["error"] = f"{type(exc).__name__}: {exc}"
            print(json.dumps(record), flush=True)
            output.append(record)
    print("BATCH_SUMMARY", json.dumps({"total":len(output),"passed":sum(x["status"]=="PASS" for x in output),
        "chat_latencies":[x["validation"].get("chat_latency_s") for x in output if x["validation"].get("chat_latency_s")]}), flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("groups",nargs="+",type=int)
    asyncio.run(main(set(parser.parse_args().groups)))
