"""Strict Group 12 road/air/multimodal comparison acceptance runner."""
import asyncio,json,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
import httpx
from backend.config.redis import delete_data
from backend.core.security import create_access_token
from backend.mcp.tools.tool_client import load_mcp_tools
from backend.planning.models import PlanningRequest,Shipment
from backend.planning.service import PlanningService

def cases():
 deadline=(datetime.now(timezone.utc)+timedelta(hours=10)).replace(microsecond=0)
 return [
  ("Urgently compare road versus air for 500 kg Delhi to Mumbai and recommend the fastest option.",500,"fastest",None),
  ("Compare ground versus express for a heavy 9000 kg Delhi to Mumbai shipment and recommend the best overall tradeoff.",9000,"balanced",None),
  (f"Compare road versus air for 3000 kg Delhi to Mumbai with delivery deadline {deadline.isoformat()}. Show SLA results.",3000,"balanced",deadline),
  ("Cost matters most: compare road versus air for 6000 kg Delhi to Mumbai and recommend the cheapest.",6000,"cheapest",None),
  ("Risk matters most: compare road versus air for 2500 kg Delhi to Mumbai and recommend the safest.",2500,"lowest-risk",None),
 ]

def validate(data,weight,objective,deadline):
 assert data["planning_request"]["objective"]==objective and data["planning_request"]["shipment"]["weight_kg"]==weight
 options=data["options"]; assert options["road"] and options["air"] and options["multimodal"]
 ground,express=options["ground"],options["express"]; delta=data["express_vs_ground"]
 assert delta["additional_cost"]==round(express["operational_cost"]-ground["operational_cost"],2)
 assert delta["time_saved_hours"]==round(ground["duration_hours"]-express["duration_hours"],2)
 assert delta["risk_difference"]==round(express["risk_score"]-ground["risk_score"],4)
 assert delta["sla_comparison"]=={"ground":ground["sla_met"],"express":express["sla_met"]}
 if deadline: assert all(options[x]["sla_met"] is not None for x in ("road","air","multimodal"))
 recommended=data["recommended_plan"]
 feasible=[options[x] for x in ("road","air","multimodal")]
 if objective=="cheapest": assert recommended["operational_cost"]==min(x["operational_cost"] for x in feasible)
 if objective=="fastest": assert recommended["duration_hours"]==min(x["duration_hours"] for x in feasible)
 if objective=="lowest-risk": assert recommended["risk_score"]==min(x["risk_score"] for x in feasible)
 return recommended

async def main():
 service=PlanningService(); op=next(x for x in await load_mcp_tools() if x.name=="supply_chain_planning_operation"); token=create_access_token({"user_id":5}); rows=[]
 async with httpx.AsyncClient(timeout=180) as client:
  for number,(question,weight,objective,deadline) in enumerate(cases(),1):
   row={"group":12,"requirement":"Road vs Air","question_number":number,"question":question,"service_status":"FAIL","mcp_status":"FAIL","chat_status":"FAIL","validation":{},"latency":{},"failure_reason":None,"root_cause":None,"bugs_fixed":[],"final_status":"FAIL"}
   try:
    req=PlanningRequest(source="Delhi",destination="Mumbai",shipment=Shipment(weight_kg=weight),objective=objective,deadline=deadline)
    t=time.perf_counter(); validate(service.compare_modes(5,req),weight,objective,deadline); row["latency"]["planner_ms"]=round((time.perf_counter()-t)*1000,3); row["service_status"]="PASS"
    t=time.perf_counter(); mcp=await op.ainvoke({"user_id":5,"operation":"compare_modes","parameters":req.model_dump(mode="json")}); validate(mcp,weight,objective,deadline); row["latency"]["mcp_ms"]=round((time.perf_counter()-t)*1000,3); row["mcp_status"]="PASS"
    await delete_data(5); t=time.perf_counter(); response=await client.post("http://127.0.0.1:4200/mcp-agent",headers={"Authorization":"Bearer "+token},json={"message":question}); row["latency"]["chat_ms"]=round((time.perf_counter()-t)*1000,3)
    body=response.json(); actions=body.get("actions") or []; assert response.status_code==200 and body.get("success") and actions and actions[0]["type"]=="supply_chain_planning_operation"
    data=actions[0]["data"]; plan=validate(data,weight,objective,deadline); answer=body["response"]
    assert all(x in answer for x in ("Ground costs","Express costs","Multimodal costs","Route:","Vehicles:"))
    assert f"{data['express_vs_ground']['additional_cost']:,.2f}" in answer
    row["chat_status"]="PASS"; row["final_status"]="PASS"; row["validation"]={"recommended_mode":plan["mode"],"additional_cost":data["express_vs_ground"]["additional_cost"],"time_saved":data["express_vs_ground"]["time_saved_hours"]}
   except Exception as exc: row["failure_reason"]=f"{type(exc).__name__}: {exc}"
   rows.append(row); print(json.dumps(row),flush=True)
 p=Path("tests/acceptance_results.json"); old=json.loads(p.read_text()) if p.exists() else []; p.write_text(json.dumps([x for x in old if x.get("group")!=12]+rows,indent=2)+"\n")
 print(json.dumps({"group":12,"passed":sum(x["final_status"]=="PASS" for x in rows),"total":5}))
if __name__=="__main__": asyncio.run(main())
