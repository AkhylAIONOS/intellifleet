"""Focused real-Azure validation of active planning context and clarifications."""
import asyncio
import json
import time

import httpx

from backend.config.redis import delete_data
from backend.core.security import create_access_token


URL="http://127.0.0.1:4200/mcp-agent"
GENERIC=("i couldn't complete", "missing required information", "validation error", "internal server error")


async def ask(client, token, message):
    response=await client.post(URL,headers={"Authorization":"Bearer "+token},json={"message":message})
    body=response.json(); text=str(body.get("response") or "")
    action=(body.get("actions") or [{}])[0]; data=action.get("data") or {}
    return {"http":response.status_code,"success":body.get("success"),"answer":text,"action":action.get("type"),
            "operation":data.get("planning_operation"),"data":data,
            "clean":response.status_code==200 and not any(x in text.casefold() for x in GENERIC)}


async def main():
    started=time.perf_counter(); token=create_access_token({"user_id":5}); results={}
    async with httpx.AsyncClient(timeout=180) as client:
        await delete_data(5)
        turn1=await ask(client,token,"Find the cheapest feasible way to move 6,000 kg from Delhi to Mumbai.")
        results["initial_plan"]=bool(turn1["clean"] and turn1["data"].get("recommended_plan"))
        disruption=await ask(client,token,"A route in my shipment is disrupted. Replan it and tell me what changes.")
        results["disruption"]=bool(disruption["clean"] and disruption["operation"]=="route_alternatives" and disruption["data"].get("recommended_plan"))
        breakdown=await ask(client,token,"The assigned vehicle broke down. Find a replacement.")
        results["breakdown"]=bool(breakdown["clean"] and breakdown["operation"]=="breakdown_recovery" and breakdown["data"].get("recovery_plan"))
        scenario=await ask(client,token,"What happens to my current plan if fuel cost increases by 20%? Do not apply it.")
        results["what_if"]=bool(scenario["clean"] and scenario["operation"]=="create_scenario" and scenario["data"].get("status")=="draft")

        await delete_data(5)
        warehouse=await ask(client,token,"No single warehouse has enough inventory. Can multiple warehouses fulfil the order? Show the allocations.")
        results["multi_warehouse"]=bool(warehouse["clean"] and "quantity" in warehouse["answer"].casefold())
        await delete_data(5)
        global_flow=await ask(client,token,"Plan a shipment from Delhi to Frankfurt using road, gateway, international air and destination legs.")
        results["global_flow"]=bool(global_flow["clean"] and global_flow["answer"]=="What shipment weight should I plan for?")

    results["elapsed_seconds"]=round(time.perf_counter()-started,3)
    print(json.dumps(results))
    assert all(value for key,value in results.items() if key!="elapsed_seconds"), results


if __name__=="__main__": asyncio.run(main())
