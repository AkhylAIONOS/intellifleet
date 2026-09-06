"""Real Azure regressions for the five customer-reported response defects."""
import asyncio, json, time
from pathlib import Path
import httpx
from backend.config.redis import delete_data
from backend.core.security import create_access_token

CASES = [
 ("PS1", "Plan the best end-to-end shipment of 8,000 kg from Delhi to Kochi using road, air or multimodal transport. Use a balanced objective. Compare the feasible options and recommend the best one.", ("Route:","Vehicles:","Cost:","Time:","Risk:","Balanced score:","Feasible alternatives:")),
 ("PS2", "Find the cheapest feasible way to transport 6,000 kg from Delhi to Mumbai. Compare ground, express and multimodal options and show the complete route, vehicles, cost breakdown, ETA, risk and recommendation.", ("Route:","Vehicles:","Cost breakdown:","Feasible alternatives:")),
 ("PS3", "Find the fastest feasible way to transport 6,000 kg from Delhi to Mumbai. Compare road, air and multimodal options. Show the fastest recommended plan, complete route legs, assigned vehicle(s), total cost, ETA, risk, and tell me exactly how much time it saves compared with the other feasible options.", ("Route:","Vehicles:","Cost:","Time:","Risk:","Feasible alternatives:")),
 ("PS4", "Balance cost, time, risk, reliability and vehicle utilization for 3,000 kg from Delhi to Mumbai. Compare candidates and explain the deterministic score that makes the best overall plan win.", ("Balanced score:","scoring factors:","reliability","Feasible alternatives:")),
 ("PS5", "Compare Ground versus Express for transporting 6,000 kg from Delhi to Mumbai. Show both plans with route, assigned vehicle(s), operational cost, ETA, risk and SLA. Calculate the exact extra cost of Express, time saved, risk difference, and recommend which service I should choose and why.", ("Ground costs","Express costs","Route:","Vehicles:","costs ₹","saves")),
]

async def main():
 token=create_access_token({"user_id":5}); output=[]
 async with httpx.AsyncClient(timeout=180) as client:
  for name,question,required in CASES:
   row={"case":name,"status":"FAIL","latency_ms":None,"failure":None}
   try:
    await delete_data(5); started=time.perf_counter()
    response=await client.post("http://127.0.0.1:4200/mcp-agent",headers={"Authorization":"Bearer "+token},json={"message":question})
    row["latency_ms"]=round((time.perf_counter()-started)*1000,3); body=response.json(); answer=body.get("response",""); actions=body.get("actions") or []
    assert response.status_code==200 and body.get("success") and actions
    assert all(value in answer for value in required), [value for value in required if value not in answer]
    assert "SLA met: None" not in answer
    assert not any(value in answer for value in ("validation error","pydantic.dev","NoneType","KeyError","Traceback"))
    data=actions[0].get("data") or {}; plan=data.get("recommended_plan") or {}
    assert plan and plan.get("route_legs") and plan.get("vehicles") and plan.get("cost_breakdown")
    row.update(status="PASS",tool=actions[0].get("type"),mode=plan.get("mode"),candidate_count=len(data.get("candidate_plans") or data.get("options") or []))
   except Exception as exc: row["failure"]=f"{type(exc).__name__}: {exc}"
   output.append(row); print(json.dumps(row),flush=True)
 Path("tests/manual_response_regressions.json").write_text(json.dumps(output,indent=2)+"\n")
 print(json.dumps({"passed":sum(x["status"]=="PASS" for x in output),"total":5}))

if __name__=="__main__": asyncio.run(main())
