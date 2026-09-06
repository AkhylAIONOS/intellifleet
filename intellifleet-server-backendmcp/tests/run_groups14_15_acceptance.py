"""Strict Groups 14–15 warehouse fulfilment acceptance runner."""
import asyncio,json,time
from pathlib import Path
import httpx
from backend.config.redis import delete_data
from backend.core.security import create_access_token
from backend.mcp.tools.tool_client import load_mcp_tools
from backend.planning.service import PlanningService

CASES=[
 (14,"Alternative Warehouse","Find the best alternative warehouse to fulfill 100 units totaling 1000 kg to Noida using the cheapest option.","Noida",100,1000,"cheapest",False),
 (14,"Alternative Warehouse","Which alternative warehouse should fulfill 80 units totaling 800 kg to Gurugram with the fastest delivery?","Gurugram",80,800,"fastest",False),
 (14,"Alternative Warehouse","Rank alternative warehouses to fulfill 120 units totaling 1200 kg to Mysuru with the lowest risk.","Mysuru",120,1200,"lowest-risk",False),
 (14,"Alternative Warehouse","Find an alternative warehouse to fulfill 90 units totaling 900 kg to Nashik using the best overall tradeoff.","Nashik",90,900,"balanced",False),
 (14,"Alternative Warehouse","Rank connected alternative warehouses to fulfill 100 units totaling 1000 kg to Coimbatore using the cheapest allocation.","Coimbatore",100,1000,"cheapest",False),
 (15,"Multi-Warehouse Fulfilment","Can multiple warehouses cover 1,500 units totaling 12000 kg to Mumbai using the cheapest allocation?","Mumbai",1500,12000,"cheapest",True),
 (15,"Multi-Warehouse Fulfilment","Build a multi-warehouse allocation to fulfill 1,000 units totaling 8000 kg to Kochi using the cheapest option.","Kochi",1000,8000,"cheapest",True),
 (15,"Multi-Warehouse Fulfilment","Can warehouses cover 1,200 units totaling 9000 kg to Nashik with the fastest feasible allocation?","Nashik",1200,9000,"fastest",True),
 (15,"Multi-Warehouse Fulfilment","Use multiple warehouses to fulfill 1,000 units totaling 8000 kg to Mysuru with the lowest risk.","Mysuru",1000,8000,"lowest-risk",True),
 (15,"Multi-Warehouse Fulfilment","Find a multi-warehouse allocation to fulfill 1,200 units totaling 9000 kg to Coimbatore using the best overall tradeoff.","Coimbatore",1200,9000,"balanced",True),
]

def validate(data,quantity,multi):
 assert data["fulfilled"] and data["unfulfilled_quantity"]==0 and data["allocation"]
 assert sum(x["allocation"] for x in data["allocation"])==quantity
 if multi: assert len(data["allocation"])>=2
 assert data["ranked_alternatives"] and data["allocation"][0]["warehouse"]==data["ranked_alternatives"][0]["warehouse"]
 for item in data["allocation"]:
  assert 0<item["allocation"]<=item["available"]
  plan=item["plan"]; assert plan and plan["operational_cost"]>=0 and plan["duration_hours"]>=0 and 0<=plan["risk_score"]<=1
  if plan["mode"]!="local": assert plan["route_legs"] and plan["vehicles"]
 assert data["total_cost"]==round(sum(x["plan"]["operational_cost"] for x in data["allocation"]),2)
 assert data["eta_hours"]==max(x["plan"]["duration_hours"] for x in data["allocation"])
 return data["allocation"]

async def main():
 service=PlanningService(); op=next(x for x in await load_mcp_tools() if x.name=="supply_chain_planning_operation"); token=create_access_token({"user_id":5}); rows=[]
 async with httpx.AsyncClient(timeout=180) as client:
  for group,requirement,question,destination,quantity,weight,objective,multi in CASES:
   number=1+sum(x["group"]==group for x in rows); row={"group":group,"requirement":requirement,"question_number":number,"question":question,"service_status":"FAIL","mcp_status":"FAIL","chat_status":"FAIL","validation":{},"latency":{},"failure_reason":None,"root_cause":None,"bugs_fixed":[],"final_status":"FAIL"}
   params={"destination":destination,"quantity":quantity,"weight_kg":weight,"objective":objective}
   try:
    t=time.perf_counter(); validate(service.fulfilment(5,destination,quantity,weight,objective),quantity,multi); row["latency"]["planner_ms"]=round((time.perf_counter()-t)*1000,3); row["service_status"]="PASS"
    t=time.perf_counter(); validate(await op.ainvoke({"user_id":5,"operation":"fulfilment","parameters":params}),quantity,multi); row["latency"]["mcp_ms"]=round((time.perf_counter()-t)*1000,3); row["mcp_status"]="PASS"
    await delete_data(5); t=time.perf_counter(); response=await client.post("http://127.0.0.1:4200/mcp-agent",headers={"Authorization":"Bearer "+token},json={"message":question}); row["latency"]["chat_ms"]=round((time.perf_counter()-t)*1000,3)
    body=response.json(); actions=body.get("actions") or []; assert response.status_code==200 and body.get("success") and actions and actions[0]["type"]=="supply_chain_planning_operation"
    data=actions[0]["data"]; allocations=validate(data,quantity,multi); answer=body["response"]
    assert all(x in answer for x in ("Warehouse fulfilment succeeds","Recommended allocation:","Total cost:","overall ETA:","Ranked alternatives:","Recommendation:"))
    assert all(x["warehouse"] in answer and str(x["allocation"]) in answer for x in allocations)
    row["chat_status"]="PASS"; row["final_status"]="PASS"; row["validation"]={"warehouses":[x["warehouse"] for x in allocations],"allocation_total":sum(x["allocation"] for x in allocations),"total_cost":data["total_cost"],"eta_hours":data["eta_hours"]}
   except Exception as exc: row["failure_reason"]=f"{type(exc).__name__}: {exc}"
   rows.append(row); print(json.dumps(row),flush=True)
   p=Path("tests/acceptance_results.json"); old=json.loads(p.read_text()) if p.exists() else []; p.write_text(json.dumps([x for x in old if x.get("group") not in {14,15}]+rows,indent=2)+"\n")
 print(json.dumps({"groups":{"14":sum(x["group"]==14 and x["final_status"]=="PASS" for x in rows),"15":sum(x["group"]==15 and x["final_status"]=="PASS" for x in rows)}}))
if __name__=="__main__": asyncio.run(main())
