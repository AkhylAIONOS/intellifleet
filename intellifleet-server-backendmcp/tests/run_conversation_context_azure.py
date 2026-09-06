"""Live Azure/HTTP conversation regressions on the loaded network (clears chat only)."""
import argparse
import asyncio
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import httpx
from backend.config.redis import delete_data,get_active_planning_context
from backend.core.security import create_access_token

BASE='Plan 6,000 kg from Delhi to Mumbai using the best overall option. Show the route, assigned vehicle, operational cost, ETA, risk and reliability.'
GROUND='Plan 6,000 kg from Delhi to Mumbai using Ground transport.'
FASTEST='Find the fastest feasible way to move this shipment. Compare it with my current plan and tell me the extra cost, time saved and risk difference.'
COMPARE='Compare Ground and Express for this shipment. Show cost, ETA, risk and reliability, and recommend which one I should choose.'
DISRUPT='The direct route in my current plan is unavailable. Replan this shipment using the best feasible alternative and show the old route, new route, vehicle, cost, ETA and risk differences.'
FUEL='What happens if fuel cost increases by 20%? Keep this as a draft scenario, do not apply it, and compare it with my current baseline.'
GLOBAL='Plan a 5,000 kg shipment from Delhi to Frankfurt using the best feasible international option in the currently loaded network. Show the route, transport mode, vehicle, cost, ETA and risk.'

async def main(url):
    records=[]
    async with httpx.AsyncClient(timeout=180) as client:
        async def ask(prompt):
            r=await client.post(url+'/mcp-agent',headers={'Authorization':'Bearer '+create_access_token({'user_id':5})},json={'message':prompt})
            body=r.json();ctx=await get_active_planning_context(5)
            record={'prompt':prompt,'http':r.status_code,'body':body,'context':ctx};records.append(record)
            Path('tests/conversation_context_azure_results.json').write_text(json.dumps(records,indent=2))
            data=(body.get('actions') or [{}])[0].get('data') or {}
            print(json.dumps({'prompt':prompt,'success':body.get('success'),'operation':data.get('planning_operation'),'response':body.get('response','')[:350]}),flush=True)
            assert r.status_code==200 and body.get('success') and data,record
            return data,ctx
        for followup in [FASTEST,COMPARE]:
            await delete_data(5);initial,old=await ask(BASE)
            data,ctx=await ask(followup)
            assert data['planning_request']['shipment']['weight_kg']==6000
            assert data['planning_request']['source']==old['source'] and data['planning_request']['destination']==old['destination']
            if followup==FASTEST:
                assert data['recommended_plan']['mode']=='air' and data['planning_request']['objective']=='fastest'
                assert data['baseline']['recommended_plan']==initial['recommended_plan']
            else:assert data['options']['ground'] and data['options']['express']
            assert ctx['selected_plan_id']==data['recommended_plan']['plan_id']
        await delete_data(5);await ask(GROUND)
        revised,old=await ask(DISRUPT);draft,ctx=await ask(FUEL)
        assert draft['status']=='draft' and draft['baseline']['recommended_plan']==revised['recommended_plan']
        assert draft['scenario']['recommended_plan']['route_legs']==revised['recommended_plan']['route_legs']
        assert draft['changes']['fuel_cost_multiplier']==1.2 and draft['changes']['blocked_routes']
        assert ctx['selected_plan']==old['selected_plan'] and ctx['planning_request']==old['planning_request']
        await delete_data(5);assert await get_active_planning_context(5) is None
        data,_=await ask(GLOBAL)
        assert data['scope']=='international' and data['recommended_plan']
        assert data['recommended_plan']['mode']=='air' and len(data['recommended_plan']['route_legs'])==1
        await delete_data(5)
        data,_=await ask('Plan 10,000 kg from Delhi to Mumbai with a delivery deadline of 5 September 2026 at 10:00 PM IST. Compare Ground and Express with cost, ETA, risk and SLA, and recommend the best overall option.')
        assert data['planning_request']['deadline']=='2026-09-05T22:00:00+05:30'
        for option in data['options'].values():
            if option: assert option['sla_met']==(datetime.fromisoformat(option['eta'])<=datetime.fromisoformat(data['planning_request']['deadline']))
        ground,air=data['options']['ground'],data['options']['air']
        deadline=datetime.now(timezone.utc)+timedelta(hours=(ground['duration_hours']+air['duration_hours'])/2)
        await delete_data(5)
        data,_=await ask(f'Plan 10,000 kg from Delhi to Mumbai with a delivery deadline of {deadline.isoformat()}. Compare Ground and Express and recommend the fastest feasible option. Show cost, ETA, risk and SLA.')
        assert data['options']['ground']['sla_met'] is False and data['options']['air']['sla_met'] is True
        assert data['recommended_plan']['mode']=='air'
        await delete_data(5);await ask('Plan 18,000 kg from Delhi to Mumbai using Ground transport.')
        before=await get_active_planning_context(5);data,ctx=await ask(DISRUPT)
        assert data['recommended_plan'] is None and ctx['selected_plan']==before['selected_plan']
        data,ctx=await ask('Show available inventory and warehouse capacity selected for my current shipment.')
        assert data['warehouses'] and ctx['weight_kg']==18000
    print('PASS: five requested Azure/chat flows, future SLA, safe 18t disruption, warehouse follow-up and New Chat',flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:4201');args=parser.parse_args();asyncio.run(main(args.url))
