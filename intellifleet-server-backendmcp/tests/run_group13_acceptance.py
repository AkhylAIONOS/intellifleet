"""Strict Group 13 vehicle-breakdown recovery acceptance runner."""
import asyncio,json,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
import httpx
from backend.config.redis import delete_data
from backend.core.security import create_access_token
from backend.mcp.tools.tool_client import load_mcp_tools
from backend.planning.service import PlanningService

def cases():
 d=(datetime.now(timezone.utc)+timedelta(hours=8)).replace(microsecond=0)
 return [
  ("TRK-003 broke down at Delhi with 500 kg remaining. Recover shipment to Mumbai.","TRK-003",500,None),
  ("TRK-002 broke down at Delhi with 6000 kg remaining. Recover shipment to Mumbai and assign enough replacement capacity.","TRK-002",6000,None),
  ("TRK-001 broke down at Delhi with 9000 kg remaining. Recover shipment to Mumbai using multiple replacements if needed.","TRK-001",9000,None),
  ("CAR-004 broke down at Delhi with 250 kg remaining. Recover shipment to Mumbai and show transfer and repositioning.","CAR-004",250,None),
  (f"BIK-005 broke down at Delhi with 50 kg remaining. Recover shipment to Mumbai by {d.isoformat()} and show SLA impact.","BIK-005",50,d),
 ]

def validate(data,label,weight,deadline):
 assert data["broken_vehicle"] and data["broken_vehicle"]["label"]==label
 plan=data["recovery_plan"]; replacements=data["replacement_vehicles"]; assert plan and replacements
 assert all(x["label"]!=label for x in replacements) and sum(float(x["capacity"]) for x in replacements)>=weight
 accepted={"road":{"truck","car","auto","bike"},"air":{"plane","aircraft"}}
 kind="air" if plan["mode"]=="air" else "road"; assert all(str(x["type"]).casefold() in accepted[kind] for x in replacements)
 assert plan["replacement_arrival_hours"]>=0 and plan["transfer_time_hours"]>=0 and plan["repositioning_cost"]>=0
 assert data["additional_cost"]==plan["repositioning_cost"] and data["new_eta"]==plan["eta"]
 assert data["transfer_load_kg"]==weight and data["remaining_journey"]["destination"] in {"Mumbai","IF Mumbai West Hub"}
 if deadline: assert data["sla_met"] is not None and (plan["sla_slack_hours"] is not None or plan["sla_delay_hours"] is not None)
 return plan

async def main():
 service=PlanningService(); op=next(x for x in await load_mcp_tools() if x.name=="supply_chain_planning_operation"); token=create_access_token({"user_id":5}); rows=[]
 async with httpx.AsyncClient(timeout=180) as client:
  for number,(question,label,weight,deadline) in enumerate(cases(),1):
   row={"group":13,"requirement":"Vehicle Breakdown Recovery","question_number":number,"question":question,"service_status":"FAIL","mcp_status":"FAIL","chat_status":"FAIL","validation":{},"latency":{},"failure_reason":None,"root_cause":None,"bugs_fixed":[],"final_status":"FAIL"}
   params={"vehicle_label":label,"current_location":"Delhi","destination":"Mumbai","remaining_weight_kg":weight,"deadline":deadline.isoformat() if deadline else None}
   try:
    t=time.perf_counter(); validate(service.breakdown_recovery(5,label,"Delhi","Mumbai",weight,deadline),label,weight,deadline); row["latency"]["planner_ms"]=round((time.perf_counter()-t)*1000,3); row["service_status"]="PASS"
    t=time.perf_counter(); validate(await op.ainvoke({"user_id":5,"operation":"breakdown_recovery","parameters":params}),label,weight,deadline); row["latency"]["mcp_ms"]=round((time.perf_counter()-t)*1000,3); row["mcp_status"]="PASS"
    await delete_data(5); t=time.perf_counter(); response=await client.post("http://127.0.0.1:4200/mcp-agent",headers={"Authorization":"Bearer "+token},json={"message":question}); row["latency"]["chat_ms"]=round((time.perf_counter()-t)*1000,3)
    body=response.json(); actions=body.get("actions") or []; assert response.status_code==200 and body.get("success") and actions and actions[0]["type"]=="supply_chain_planning_operation"
    plan=validate(actions[0]["data"],label,weight,deadline); answer=body["response"]
    assert all(x in answer for x in ("Breakdown recovery recommendation","Broken vehicle:","Replacement vehicles:","Repositioning route:","transfer time:","New total ETA:"))
    assert label in answer and all(x["label"] in answer for x in plan["vehicles"])
    row["chat_status"]="PASS"; row["final_status"]="PASS"; row["validation"]={"replacement_vehicles":[x["label"] for x in plan["vehicles"]],"additional_cost":actions[0]["data"]["additional_cost"],"duration_hours":plan["duration_hours"],"sla_met":plan["sla_met"]}
   except Exception as exc: row["failure_reason"]=f"{type(exc).__name__}: {exc}"
   rows.append(row); print(json.dumps(row),flush=True)
 p=Path("tests/acceptance_results.json"); old=json.loads(p.read_text()) if p.exists() else []; p.write_text(json.dumps([x for x in old if x.get("group")!=13]+rows,indent=2)+"\n")
 print(json.dumps({"group":13,"passed":sum(x["final_status"]=="PASS" for x in rows),"total":5}))
if __name__=="__main__": asyncio.run(main())
