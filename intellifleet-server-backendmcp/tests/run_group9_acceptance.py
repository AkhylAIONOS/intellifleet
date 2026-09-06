"""Strict Group 9 deterministic-risk acceptance runner."""
import asyncio, json, math, time
from pathlib import Path
import httpx
from backend.config.redis import delete_data
from backend.core.security import create_access_token
from backend.mcp.tools.tool_client import load_mcp_tools
from backend.planning.models import PlanningRequest, Shipment
from backend.planning.service import PlanningService

CASES = [
 ("Assess disruption risk for 3000 kg Delhi to Mumbai and recommend a balanced plan.",3000,"balanced",None),
 ("Find the lowest-risk way to ship 1200 kg from Delhi to Mumbai and show the risk components.",1200,"lowest-risk",None),
 ("What is the risk of the cheapest feasible Delhi to Mumbai route for 500 kg?",500,"cheapest",None),
 ("Can 6000 kg go Delhi to Mumbai with maximum risk 0.20? Show the deterministic risk breakdown.",6000,"balanced",.20),
 ("Assess route, vehicle, warehouse, weather and mode risk for the fastest 2500 kg Delhi to Mumbai plan.",2500,"fastest",None),
]

def validate(data, weight, objective, max_risk):
 req=data["planning_request"]; assert req["objective"]==objective and math.isclose(req["shipment"]["weight_kg"],weight)
 plan=data["recommended_plan"]; assert plan and 0<=plan["risk_score"]<=1
 breakdown=plan["risk_breakdown"]; assert set(breakdown)=={"route","vehicle","weather","warehouse","mode","overall"}
 assert all(0<=float(v)<=1 for v in breakdown.values()) and breakdown["overall"]==plan["risk_score"]
 if max_risk is not None: assert plan["risk_score"]<=max_risk
 if objective=="lowest-risk": assert plan["risk_score"]==min(x["risk_score"] for x in data["candidate_plans"] if max_risk is None or x["risk_score"]<=max_risk)
 return plan

async def main():
 service=PlanningService(); operation=next(x for x in await load_mcp_tools() if x.name=="supply_chain_planning_operation")
 token=create_access_token({"user_id":5}); records=[]
 async with httpx.AsyncClient(timeout=180) as client:
  for number,(question,weight,objective,max_risk) in enumerate(CASES,1):
   rec={"group":9,"requirement":"Disruption Risk","question_number":number,"question":question,"service_status":"FAIL","mcp_status":"FAIL","chat_status":"FAIL","validation":{},"latency":{},"failure_reason":None,"root_cause":None,"bugs_fixed":[],"final_status":"FAIL"}
   try:
    req=PlanningRequest(source="Delhi",destination="Mumbai",shipment=Shipment(weight_kg=weight),objective=objective,max_risk=max_risk)
    t=time.perf_counter(); direct=service.plan(5,req); p=validate(direct,weight,objective,max_risk); rec["latency"]["planner_ms"]=round((time.perf_counter()-t)*1000,3); rec["service_status"]="PASS"
    t=time.perf_counter(); mcp=await operation.ainvoke({"user_id":5,"operation":"risk","parameters":req.model_dump(mode="json")}); validate(mcp,weight,objective,max_risk); rec["latency"]["mcp_ms"]=round((time.perf_counter()-t)*1000,3); rec["mcp_status"]="PASS"
    await delete_data(5); t=time.perf_counter(); response=await client.post("http://127.0.0.1:4200/mcp-agent",headers={"Authorization":"Bearer "+token},json={"message":question}); rec["latency"]["chat_ms"]=round((time.perf_counter()-t)*1000,3)
    body=response.json(); actions=body.get("actions") or []; assert response.status_code==200 and body.get("success") and actions
    data=actions[0]["data"]; cp=validate(data,weight,objective,max_risk); assert str(cp["risk_score"]) in body["response"]
    rec["chat_status"]="PASS"; rec["final_status"]="PASS"; rec["validation"]={"risk_score":cp["risk_score"],"risk_breakdown":cp["risk_breakdown"],"tool":actions[0]["type"]}
   except Exception as exc: rec["failure_reason"]=f"{type(exc).__name__}: {exc}"
   records.append(rec); print(json.dumps(rec),flush=True)
 path=Path("tests/acceptance_results.json"); existing=json.loads(path.read_text()) if path.exists() else []
 path.write_text(json.dumps([x for x in existing if x.get("group")!=9]+records,indent=2)+"\n")
 print(json.dumps({"group":9,"passed":sum(x["final_status"]=="PASS" for x in records),"total":5}))

if __name__=="__main__": asyncio.run(main())
