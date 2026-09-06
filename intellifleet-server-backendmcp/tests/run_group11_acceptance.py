"""Strict Group 11 vehicle-selection acceptance runner."""
import asyncio,json,time
from pathlib import Path
import httpx
from backend.config.redis import delete_data
from backend.core.security import create_access_token
from backend.mcp.tools.tool_client import load_mcp_tools
from backend.planning.models import PlanningRequest,Shipment
from backend.planning.service import PlanningService

CASES=[
 ("Select a suitable vehicle for a small 50 kg road shipment from Delhi to Mumbai.",50,"balanced",{}),
 ("Select vehicles for a 6000 kg road shipment from Delhi to Mumbai and show capacity and utilization.",6000,"balanced",{}),
 ("Plan road vehicle capacity for a 9000 kg load Delhi to Mumbai; use multiple vehicles if required.",9000,"balanced",{}),
 ("TRK-003 is unavailable. Select other road vehicles for 3000 kg Delhi to Mumbai.",3000,"balanced",{"unavailable_vehicles":["TRK-003"]}),
 ("Choose a reliable road vehicle with enough range and capacity for 2500 kg from Delhi to Mumbai.",2500,"lowest-risk",{}),
]

def validate(data,weight,changes):
 plan=data["recommended_plan"]; assert plan and plan["mode"]=="road" and plan["vehicles"]
 assert sum(float(x["capacity"]) for x in plan["vehicles"])>=weight
 assert 0<plan["vehicle_utilization"]<=1
 assert all(0<x["utilization_percentage"]<=100 for x in plan["vehicles"])
 assert all(x["label"] not in changes.get("unavailable_vehicles",[]) for x in plan["vehicles"])
 network=PlanningService().load_network(5); by_label={x["label"]:x for x in network["vehicles"]}
 assert all(not by_label[x["label"]].get("max_range_km") or float(by_label[x["label"]]["max_range_km"])>=plan["distance_km"] for x in plan["vehicles"])
 return plan

async def main():
 service=PlanningService(); op=next(x for x in await load_mcp_tools() if x.name=="supply_chain_planning_operation"); token=create_access_token({"user_id":5}); rows=[]
 async with httpx.AsyncClient(timeout=180) as client:
  for number,(question,weight,objective,changes) in enumerate(CASES,1):
   row={"group":11,"requirement":"Vehicle Selection","question_number":number,"question":question,"service_status":"FAIL","mcp_status":"FAIL","chat_status":"FAIL","validation":{},"latency":{},"failure_reason":None,"root_cause":None,"bugs_fixed":[],"final_status":"FAIL"}
   try:
    request=PlanningRequest(source="Delhi",destination="Mumbai",shipment=Shipment(weight_kg=weight),objective=objective,allowed_modes=["road"])
    t=time.perf_counter(); validate(service.plan(5,request,changes=changes),weight,changes); row["latency"]["planner_ms"]=round((time.perf_counter()-t)*1000,3); row["service_status"]="PASS"
    params=request.model_dump(mode="json")|({"changes":changes} if changes else {}); t=time.perf_counter(); validate(await op.ainvoke({"user_id":5,"operation":"vehicle_selection","parameters":params}),weight,changes); row["latency"]["mcp_ms"]=round((time.perf_counter()-t)*1000,3); row["mcp_status"]="PASS"
    await delete_data(5); t=time.perf_counter(); response=await client.post("http://127.0.0.1:4200/mcp-agent",headers={"Authorization":"Bearer "+token},json={"message":question}); row["latency"]["chat_ms"]=round((time.perf_counter()-t)*1000,3)
    body=response.json(); actions=body.get("actions") or []; assert response.status_code==200 and body.get("success") and actions
    data=actions[0]["data"]; plan=validate(data,weight,changes); answer=body["response"]
    assert "Vehicles:" in answer and "capacity" in answer and "utilization" in answer and all(x["label"] in answer for x in plan["vehicles"])
    row["chat_status"]="PASS"; row["final_status"]="PASS"; row["validation"]={"vehicles":[x["label"] for x in plan["vehicles"]],"capacity":sum(x["capacity"] for x in plan["vehicles"]),"utilization":plan["vehicle_utilization"]}
   except Exception as exc: row["failure_reason"]=f"{type(exc).__name__}: {exc}"
   rows.append(row); print(json.dumps(row),flush=True)
 p=Path("tests/acceptance_results.json"); old=json.loads(p.read_text()) if p.exists() else []; p.write_text(json.dumps([x for x in old if x.get("group")!=11]+rows,indent=2)+"\n")
 print(json.dumps({"group":11,"passed":sum(x["final_status"]=="PASS" for x in rows),"total":5}))
if __name__=="__main__": asyncio.run(main())
