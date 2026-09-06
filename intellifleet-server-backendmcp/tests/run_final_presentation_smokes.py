import asyncio, json, sys
import httpx
from backend.config.redis import delete_data
from backend.core.security import create_access_token

CASES=[
 ("cheapest",6000,"Find the cheapest feasible way to move 6000 kg from Delhi to Mumbai."),
 ("fastest",6000,"Find the fastest feasible way to transport 6000 kg from Delhi to Mumbai."),
 ("balanced",8000,"Plan 8000 kg from Delhi to Mumbai using the best overall balance of cost, time, reliability and risk."),
 ("comparison",6000,"Compare Ground and Express for 6000 kg from Delhi to Mumbai. Which should I choose?"),
 ("unified",10000,"Plan 10000 kg from Delhi to Mumbai. Compare road, air and multimodal, choose warehouses and vehicles, evaluate cost, ETA and risk, and recommend the best overall plan."),
]

async def main():
 token=create_access_token({"user_id":5}); results=[]
 async with httpx.AsyncClient(timeout=180) as client:
  selected=set(sys.argv[1:])
  for name,weight,prompt in (case for case in CASES if not selected or case[0] in selected):
   await delete_data(5); response=await client.post("http://127.0.0.1:4200/mcp-agent",headers={"Authorization":"Bearer "+token},json={"message":prompt})
   body=response.json(); actions=body.get("actions") or []; data=actions[0].get("data",{}) if actions else {}; answer=body.get("response","")
   plans=[]
   if data.get("recommended_plan"):plans=[data["recommended_plan"]]
   if data.get("options"):plans=[x for x in data["options"].values() if x]
   loads_ok=all(abs(sum(float(v.get("assigned_load_kg",0)) for v in p.get("vehicles",[]))-weight)<1e-6 for p in plans)
   plan_id=str((plans[0] if plans else {}).get("plan_id") or "")
   clean=not any(x.casefold() in answer.casefold() for x in ('{"',"SLA met: None","NoneType","KeyError","Traceback",f"plan {plan_id}"))
   pricing_ok=("Selling price" not in answer and "Profit:" not in answer and "Margin:" not in answer)
   human=("I'd recommend" in answer and ("Why:" in answer or "Here's the comparison" in answer))
   passed=response.status_code==200 and body.get("success") and actions and plans and loads_ok and clean and pricing_ok and human
   results.append({"case":name,"pass":bool(passed),"load_conservation":loads_ok,"clean":clean,"conditional_pricing":pricing_ok,"conversational":human})
 print(json.dumps(results)); print(f"PASS {sum(x['pass'] for x in results)}/{len(results)}")

if __name__=="__main__":asyncio.run(main())
