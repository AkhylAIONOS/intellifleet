import asyncio, json
import httpx
from backend.config.redis import delete_data
from backend.core.security import create_access_token

CASES = [
 ("cheapest", "Find the cheapest feasible way to move 6000 kg from Delhi to Mumbai."),
 ("fastest", "Find the fastest feasible way to transport 6000 kg from Delhi to Mumbai."),
 ("balanced", "Plan 8000 kg from Delhi to Mumbai using the best overall balance of cost, time, reliability and risk."),
 ("modes", "Compare road and air for 6000 kg from Delhi to Mumbai. Which should I choose?"),
 ("disruption", "The route from Delhi to Jaipur is blocked. Replan 3000 kg from Delhi to Mumbai and show the alternative."),
 ("vehicles", "Which vehicle or vehicles should I use for 18000 kg from Delhi to Mumbai?"),
 ("fulfilment", "Can warehouses cover 1500 units totaling 12000 kg to Mumbai using the cheapest multi-warehouse allocation?"),
 ("scenario", "Create a what-if plan for 6000 kg Delhi to Mumbai if fuel cost increases by 20 percent. Do not apply it."),
 ("global", "Plan 6000 kg from IF Delhi NCR Mega Hub in India to IF Frankfurt Gateway Hub in Germany using a global multimodal plan."),
 ("unified", "Plan 10000 kg from Delhi to Mumbai. Compare road, air and multimodal, choose warehouses and vehicles, evaluate cost, ETA and risk, and recommend the best overall plan."),
]

async def main():
 token=create_access_token({"user_id":5}); output=[]
 async with httpx.AsyncClient(timeout=180) as client:
  for name,prompt in CASES:
   await delete_data(5)
   try:
    response=await client.post("http://127.0.0.1:4200/mcp-agent",headers={"Authorization":"Bearer "+token},json={"message":prompt})
    body=response.json(); actions=body.get("actions") or []; action=actions[0] if actions else {}; data=action.get("data") or {}
    record={"name":name,"http":response.status_code,"success":body.get("success"),"action":action.get("type"),"operation":data.get("operation") or data.get("planning_operation"),"has_plan":bool(data.get("recommended_plan") or data.get("recovery_plan") or data.get("allocation") or data.get("scenario")),"response_clean":all(x not in body.get("response","") for x in ("Traceback","KeyError","NoneType","validation error","SLA met: None"))}
   except Exception as exc: record={"name":name,"error":f"{type(exc).__name__}: {exc}"}
   output.append(record); print(json.dumps(record),flush=True)
 print("SUMMARY",sum(x.get("http")==200 and x.get("success") and x.get("action") and x.get("response_clean") for x in output),"/",len(output))

if __name__=="__main__": asyncio.run(main())
