"""One compact real-Azure final demo sequence; intentionally not part of pytest."""
import asyncio, json, httpx
from backend.config.redis import delete_data
from backend.core.security import create_access_token

PROMPTS=[
 "Plan 6,000 kg from Delhi to Mumbai using road transport. Show the route and assigned vehicle.",
 "Plan 6,000 kg from Delhi to Mumbai using air transport. Show the route and assigned aircraft.",
 "The current route is disrupted. Replan it using the best available alternative and show me what changed.",
 "Plan 10,000 kg from Delhi to Mumbai. Compare road, air and multimodal, choose warehouses and vehicles, evaluate cost, ETA, risk and SLA, and recommend the best overall plan.",
]

async def main():
 token=create_access_token({"user_id":5}); await delete_data(5); rows=[]
 async with httpx.AsyncClient(timeout=180) as client:
  for index,prompt in enumerate(PROMPTS):
   response=await client.post("http://127.0.0.1:4200/mcp-agent",headers={"Authorization":"Bearer "+token},json={"message":prompt})
   body=response.json(); action=(body.get("actions") or [{}])[0]; data=action.get("data") or {}; plan=data.get("recommended_plan") or {}
   answer=str(body.get("response") or "")
   valid=response.status_code==200 and body.get("success") is True and bool(action.get("type")) and bool(plan)
   if index==0: valid=valid and plan.get("mode")=="road" and any(str(v.get("type")).casefold()=="truck" for v in plan.get("vehicles") or [])
   if index==1: valid=valid and plan.get("mode")=="air" and any(str(v.get("type")).casefold()=="plane" for v in plan.get("vehicles") or [])
   if index==2: valid=valid and data.get("planning_operation")=="route_alternatives" and all(term in answer for term in ("What changed (before → after)","Mode:","Route:","Vehicle:","Cost:","ETA:","Risk:"))
   if index==3: valid=valid and len(data.get("candidate_plans") or [])>=2 and bool(plan.get("vehicles"))
   rows.append({"turn":index+1,"pass":bool(valid),"action":action.get("type"),"operation":data.get("planning_operation"),"mode":plan.get("mode")})
 print(json.dumps(rows)); assert all(row["pass"] for row in rows),rows

if __name__=="__main__": asyncio.run(main())
