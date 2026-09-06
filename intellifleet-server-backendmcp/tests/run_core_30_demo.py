import asyncio, json, sqlite3, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
from backend.config.redis import delete_data
from backend.core.security import create_access_token
from backend.planning.service import PlanningService

CASES=[
(1,"End-to-end network planning","Plan the best end-to-end shipment of 8000 kg from Delhi to Mumbai using road, air or multimodal transport with a balanced objective.","plan"),
(2,"Cheapest routing","Find the cheapest feasible way to move 6000 kg from Delhi to Mumbai.","plan"),
(3,"Fastest routing","Find the fastest feasible way to transport 6000 kg from Delhi to Mumbai.","plan"),
(4,"Multi-objective planning","Plan 8000 kg from Delhi to Mumbai using the best overall balance of cost, delivery time, reliability and risk.","plan"),
(5,"Express vs Ground comparison","Compare Ground and Express for 6000 kg from Delhi to Mumbai. Which should I choose?","compare_modes"),
(6,"Pricing / revenue / margin","Find the cheapest Delhi to Mumbai plan for 6000 kg and price it at a 25 percent target margin.","plan"),
(7,"Route alternatives","The route from Delhi to Jaipur is blocked. Replan 3000 kg from Delhi to Mumbai and show the best alternative.","route_alternatives"),
(8,"Route comparison","Compare the recommended route with the next best route for 3000 kg from Delhi to Mumbai and show exact changes.","route_comparison"),
(9,"Disruption risk","Which Delhi to Mumbai plan for 3000 kg has the lowest disruption risk?","risk"),
(10,"Disruption mitigation","Assume disruption risk increases by 0.2. Mitigate and replan 3000 kg from Delhi to Mumbai with a baseline comparison.","disruption_mitigation"),
(11,"Vehicle selection / multi-vehicle","Which vehicle or vehicles should I use for 18000 kg from Delhi to Mumbai?","plan"),
(12,"Road vs Air","Should I use road or air for 6000 kg from Delhi to Mumbai? Compare both.","compare_modes"),
(13,"Vehicle breakdown recovery","TRK-003 broke down at Delhi with 3000 kg remaining. Find replacement vehicles and recover the shipment to Mumbai.","breakdown_recovery"),
(14,"Alternative warehouse","Use alternative warehouses to fulfil 120 units totaling 1200 kg to Mysuru using the cheapest allocation.","fulfilment"),
(15,"Multi-warehouse fulfilment","Can warehouses cover 1500 units totaling 12000 kg to Mumbai using the cheapest multi-warehouse allocation?","fulfilment"),
(16,"Warehouse capacity","Show available inventory, available storage and utilization for every warehouse.","warehouse_capacity"),
(17,"Load consolidation","Consolidate shipment S1 of 1000 kg and shipment S2 of 1200 kg, both from Delhi to Mumbai, and compare separate versus consolidated cost and utilization.","consolidation"),
(18,"Multi-stop optimization","Optimize a 3000 kg road shipment from Delhi to Mumbai stopping at Jaipur and Ahmedabad. Show the best stop order.","multi_stop"),
(19,"Vehicle utilization","Plan 18000 kg from Delhi to Mumbai and show capacity, assigned load and utilization for every assigned vehicle.","plan"),
(20,"What-if scenarios","Create a what-if plan for 6000 kg Delhi to Mumbai if fuel cost increases by 20 percent. Do not apply it.","create_scenario"),
(21,"Baseline vs scenario","Compare the baseline with a what-if plan for 6000 kg Delhi to Mumbai if fuel cost increases by 20 percent. Show exact changes and do not apply it.","create_scenario"),
(22,"Future cascading replanning","TRK-003 is delayed by 6 hours. Show affected future shipments and replan them.","future_replan"),
(23,"SLA planning",f"Plan 6000 kg from Delhi to Mumbai by {(datetime.now(timezone.utc)+timedelta(hours=30)).isoformat()} and report whether the SLA is met.","sla_plan"),
(24,"Network expansion / facility planning","Evaluate candidate facilities Jaipur at latitude 26.9124 longitude 75.7873 and Nagpur at latitude 21.1458 longitude 79.0882, each with capacity 5000 and facility cost 1000000, against demand 1000 at Delhi latitude 28.6139 longitude 77.2090 and demand 800 at Mumbai latitude 19.076 longitude 72.8777. Recommend one facility.","expansion"),
(25,"Expansion cost","Calculate complete expansion cost for candidate Jaipur at latitude 26.9124 longitude 75.7873 with capacity 5000, facility cost 1000000 and warehouse cost 200000 against demand 1000 at Delhi latitude 28.6139 longitude 77.2090 and demand 800 at Mumbai latitude 19.076 longitude 72.8777.","expansion"),
(26,"Domestic/global multimodal","Plan 6000 kg from IF Delhi NCR Mega Hub in India to IF Frankfurt Gateway in Germany using global multimodal routing.","global_plan"),
(27,"Decision support","Considering all feasible options for 6000 kg Delhi to Mumbai, what should I do and why?","plan"),
(28,"Explainability","Explain why the recommended 6000 kg Delhi to Mumbai plan is better than alternatives using calculated cost, time and risk differences.","route_comparison"),
(29,"Plan-before-execution","Create a what-if plan for 6000 kg Delhi to Mumbai if fuel cost increases by 10 percent, but do not apply it; let me apply or discard it.","create_scenario"),
(30,"Unified planner","Plan 10000 kg from Delhi to Mumbai. Compare road, air and multimodal, choose warehouses and vehicles, evaluate cost, ETA and risk, and recommend the best overall plan.","plan"),
]

def validate(data, expected):
 op=data.get("planning_operation") or ("plan" if data.get("planning_request") else None)
 aliases={"vehicle_selection":"plan","risk":"plan","route_comparison":"plan","sla_plan":"plan","route_alternatives":"plan"}
 if aliases.get(expected,expected)!=aliases.get(op,op): return False,f"operation {op}, expected {expected}"
 if expected in {"plan","risk","route_comparison","route_alternatives","sla_plan"}:
  plan=data.get("recommended_plan");
  if not plan or not plan.get("route_legs") or plan.get("operational_cost") is None or plan.get("duration_hours") is None or not 0<=plan.get("risk_score",-1)<=1:return False,"incomplete plan"
  if any(v.get("utilization_percentage",101)>100 for v in plan.get("vehicles",[])):return False,"vehicle over capacity"
 if expected=="compare_modes" and not(data.get("options",{}).get("ground") and data.get("options",{}).get("express") and data.get("express_vs_ground")):return False,"incomplete mode comparison"
 if expected=="fulfilment" and not(data.get("allocation") and data.get("fulfilled")):return False,"fulfilment incomplete"
 if expected=="warehouse_capacity" and not data.get("warehouses"):return False,"no capacity rows"
 if expected=="consolidation" and not data.get("consolidation_opportunities"):return False,"no consolidation"
 if expected=="multi_stop" and not data.get("optimized_stop_sequence"):return False,"no optimized stops"
 if expected=="create_scenario" and not(data.get("status")=="draft" and data.get("comparison")):return False,"scenario not draft/comparable"
 if expected=="future_replan" and "affected_shipments" not in data:return False,"no future impact result"
 if expected=="breakdown_recovery" and not data.get("recovery_plan"):return False,"no recovery plan"
 if expected=="expansion" and not data.get("recommended_hubs"):return False,"no facility recommendation"
 if expected=="global_plan" and not(data.get("scope")=="international" and data.get("gateway_sequence") and data.get("recommended_plan")):return False,"no global gateway plan"
 return True,"validated"

async def main():
 now=datetime.now(timezone.utc); PlanningService().schedule_shipment(5,{"shipment_id":"DEMO-FUTURE-1","source":"IF Delhi NCR Mega Hub","destination":"IFolding Mumbai West Hub".replace("olding ",""),"weight_kg":1000,"quantity":1,"assigned_vehicle_labels":["TRK-003"],"scheduled_start":now+timedelta(hours=12),"scheduled_end":now+timedelta(hours=30),"deadline":now+timedelta(hours=36)})
 token=create_access_token({"user_id":5}); results=[]
 async with httpx.AsyncClient(timeout=180) as client:
  selected={int(x) for x in sys.argv[1:]} if len(sys.argv)>1 else set(range(1,31))
  for ps,capability,prompt,expected in (case for case in CASES if case[0] in selected):
   await delete_data(5); record={"ps":ps,"capability":capability,"expected_operation":expected,"pass":False}
   try:
    response=await client.post("http://127.0.0.1:4200/mcp-agent",headers={"Authorization":"Bearer "+token},json={"message":prompt}); body=response.json(); actions=body.get("actions") or []; data=(actions[0].get("data") or {}) if actions else {}
    answer=body.get("response",""); valid,detail=validate(data,expected); clean=all(x not in answer for x in ("Traceback","KeyError","NoneType","validation error","SLA met: None"))
    if ps==6: valid=valid and all(x in answer for x in ("Selling price:","profit:","margin:")); detail="validated pricing response" if valid else "pricing response incomplete"
    if ps==19:
     vehicles=(data.get("recommended_plan") or {}).get("vehicles") or []; valid=valid and bool(vehicles) and all(v.get("assigned_load_kg") is not None and v.get("utilization_percentage",101)<=100 for v in vehicles) and "assigned load" in answer; detail="validated per-vehicle load/utilization" if valid else "vehicle utilization response incomplete"
    if ps==30:
     requested=set((data.get("planning_request") or {}).get("allowed_modes") or []); feasible={p.get("mode") for p in data.get("candidate_plans") or []}; valid=valid and {"road","air","multimodal"}<=requested and ("multimodal" in feasible or "Unavailable requested modes: multimodal" in answer); detail="validated unified feasible/unavailable modes" if valid else "unified mode evaluation incomplete"
    record.update({"http":response.status_code,"success":body.get("success"),"action":actions[0].get("type") if actions else None,"actual_operation":data.get("planning_operation"),"planner_mcp":valid,"response":clean and bool(body.get("response")),"detail":detail,"pass":response.status_code==200 and body.get("success") is True and bool(actions) and valid and clean})
   except Exception as exc:record["detail"]=f"{type(exc).__name__}: {exc}"
   results.append(record); print(json.dumps(record),flush=True)
 path=Path("tests/demo_core_30_results.json"); prior=json.loads(path.read_text()) if path.exists() else []
 merged={x["ps"]:x for x in prior}; merged.update({x["ps"]:x for x in results}); complete=[merged[x] for x in sorted(merged)]
 path.write_text(json.dumps(complete,indent=2))
 print("SUMMARY",sum(x["pass"] for x in complete),"/",len(complete),flush=True)

if __name__=="__main__":asyncio.run(main())
