"""Strict Group 10 disruption-mitigation acceptance runner."""
import asyncio,json,time
from pathlib import Path
import httpx
from backend.config.redis import delete_data
from backend.core.security import create_access_token
from backend.mcp.tools.tool_client import load_mcp_tools
from backend.planning.models import PlanningRequest,Shipment
from backend.planning.service import PlanningService

CASES=[
 ("The direct route from Delhi to Mumbai is blocked. Run disruption mitigation for 3000 kg Delhi to Mumbai and compare the recovery plan.",{"blocked_routes":[["IF Delhi NCR Mega Hub","IF Mumbai West Hub"]]}),
 ("Truck TRK-003 is unavailable. Mitigate that vehicle disruption and replan 3000 kg from Delhi to Mumbai.",{"unavailable_vehicles":["TRK-003"]}),
 ("The Jaipur warehouse is unavailable. Run warehouse disruption mitigation for 3000 kg from Delhi to Mumbai.",{"unavailable_warehouses":["IF Jaipur North Hub"]}),
 ("Assume disruption risk increases by 0.2. Mitigate and replan 3000 kg from Delhi to Mumbai with a baseline comparison.",{"risk_delta":.2}),
 ("Air is the only available mode after a mode disruption. Replan 3000 kg Delhi to Mumbai and compare it with baseline.",{"allowed_modes":["air"]}),
]

def validate(result,changes):
 assert result["status"]=="draft" and result["affected_resources"]==changes
 base=result["baseline"]["recommended_plan"]; recovery=result["recovery_plan"]; assert base and recovery and result["comparison"]
 c=result["comparison"]
 assert c["cost_difference"]==round(recovery["operational_cost"]-base["operational_cost"],2)
 assert c["eta_difference_hours"]==round(recovery["duration_hours"]-base["duration_hours"],2)
 assert c["risk_difference"]==round(recovery["risk_score"]-base["risk_score"],4)
 if changes.get("blocked_routes"):
  blocked={tuple(x) for x in changes["blocked_routes"]}; assert all((x["from_location"],x["to_location"]) not in blocked for x in recovery["route_legs"])
 if changes.get("unavailable_vehicles"): assert all(x["label"] not in changes["unavailable_vehicles"] for x in recovery["vehicles"])
 if changes.get("unavailable_warehouses"): assert all(x["from_location"] not in changes["unavailable_warehouses"] and x["to_location"] not in changes["unavailable_warehouses"] for x in recovery["route_legs"])
 if changes.get("allowed_modes"): assert recovery["mode"] in changes["allowed_modes"]
 return recovery

async def main():
 service=PlanningService(); op=next(x for x in await load_mcp_tools() if x.name=="supply_chain_planning_operation"); token=create_access_token({"user_id":5}); records=[]
 request=PlanningRequest(source="Delhi",destination="Mumbai",shipment=Shipment(weight_kg=3000))
 async with httpx.AsyncClient(timeout=180) as client:
  for number,(question,changes) in enumerate(CASES,1):
   row={"group":10,"requirement":"Disruption Mitigation","question_number":number,"question":question,"service_status":"FAIL","mcp_status":"FAIL","chat_status":"FAIL","validation":{},"latency":{},"failure_reason":None,"root_cause":None,"bugs_fixed":[],"final_status":"FAIL"}
   try:
    t=time.perf_counter(); validate(service.disruption_mitigation(5,request,changes),changes); row["latency"]["planner_ms"]=round((time.perf_counter()-t)*1000,3); row["service_status"]="PASS"
    params=request.model_dump(mode="json")|{"changes":changes}; t=time.perf_counter(); validate(await op.ainvoke({"user_id":5,"operation":"disruption_mitigation","parameters":params}),changes); row["latency"]["mcp_ms"]=round((time.perf_counter()-t)*1000,3); row["mcp_status"]="PASS"
    await delete_data(5); t=time.perf_counter(); response=await client.post("http://127.0.0.1:4200/mcp-agent",headers={"Authorization":"Bearer "+token},json={"message":question}); row["latency"]["chat_ms"]=round((time.perf_counter()-t)*1000,3)
    body=response.json(); actions=body.get("actions") or []; assert response.status_code==200 and body.get("success") and actions and actions[0]["type"]=="supply_chain_planning_operation"
    recovery=validate(actions[0]["data"],changes); answer=body["response"]
    assert all(x in answer for x in ("Affected resources:","Route:","Vehicles:","Baseline comparison:"))
    assert f"{recovery['operational_cost']:,.2f}" in answer
    row["chat_status"]="PASS"; row["final_status"]="PASS"; row["validation"]={"mode":recovery["mode"],"cost":recovery["operational_cost"],"risk":recovery["risk_score"]}
   except Exception as exc: row["failure_reason"]=f"{type(exc).__name__}: {exc}"
   records.append(row); print(json.dumps(row),flush=True)
 p=Path("tests/acceptance_results.json"); old=json.loads(p.read_text()) if p.exists() else []; p.write_text(json.dumps([x for x in old if x.get("group")!=10]+records,indent=2)+"\n")
 print(json.dumps({"group":10,"passed":sum(x["final_status"]=="PASS" for x in records),"total":5}))
if __name__=="__main__": asyncio.run(main())
