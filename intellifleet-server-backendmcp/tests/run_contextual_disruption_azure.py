"""Real HTTP/Azure regression; uses a clean chat before each two-turn case."""
import argparse
import asyncio
import json
from pathlib import Path
import httpx
from backend.config.redis import delete_data, get_active_planning_context
from backend.core.security import create_access_token

FOLLOWUP = ('The direct route in my current plan is unavailable. Replan this shipment using the best feasible alternative. '
            'Show the old route, new route, vehicle, cost, ETA and risk differences.')

async def main(url, user_id):
    records=[]
    async with httpx.AsyncClient(timeout=180) as client:
        async def ask(message):
            response=await client.post(url+'/mcp-agent',headers={'Authorization':'Bearer '+create_access_token({'user_id':user_id})},json={'message':message})
            body=response.json()
            return {'http':response.status_code,'body':body,'context':await get_active_planning_context(user_id)}
        for name,weight,explicit in [('context_6000',6000,False),('explicit_6000',6000,True),('context_18000',18000,False)]:
            await delete_data(user_id)
            first=await ask(f'Plan {weight:,} kg from Delhi to Mumbai using Ground transport.')
            initial=first['body'].get('actions',[{}])[0].get('data',{}).get('recommended_plan')
            assert initial and first['context']['allowed_modes']==['road'],first
            old_legs=initial['route_legs'];assert len(old_legs)==1
            message=(f"The direct route from {old_legs[0]['from_location']} to {old_legs[0]['to_location']} is unavailable. "
                     'Replan this shipment using the best feasible alternative. Show the old route, new route, vehicle, cost, ETA and risk differences.') if explicit else FOLLOWUP
            second=await ask(message)
            data=(second['body'].get('actions') or [{}])[0].get('data') or {}
            revised=data.get('recommended_plan')
            passed=(second['http']==200 and second['body'].get('success') and data.get('planning_operation')=='route_alternatives'
                    and data.get('planning_request',{}).get('allowed_modes')==['road']
                    and data.get('planning_request',{}).get('shipment',{}).get('weight_kg')==weight
                    and data.get('baseline',{}).get('recommended_plan')==initial)
            if weight==6000:
                passed=passed and bool(revised) and len(revised['route_legs'])>1 and all(leg['route_id']!=old_legs[0]['route_id'] for leg in revised['route_legs'])
                passed=passed and second['context']['selected_plan_id']==revised['plan_id'] and second['context']['assigned_vehicles']==revised['vehicles']
                passed=passed and 'What changed (before → after)' in second['body']['response']
            else:
                passed=passed and revised is None and data.get('feasibility',{}).get('constraint')=='vehicle_capacity_or_full_route_range'
                passed=passed and second['context']['selected_plan_id']==initial['plan_id'] and 'current plan remains unchanged' in second['body']['response']
            records.append({'name':name,'passed':bool(passed),'first':first,'second':second})
            Path('tests/contextual_disruption_azure_results.json').write_text(json.dumps(records,indent=2))
            print(json.dumps({'case':name,'passed':bool(passed),'route':[leg['to_location'] for leg in revised['route_legs']] if revised else None,
                              'vehicles':revised['vehicles'] if revised else None,'comparison':data.get('replan_comparison'),'feasibility':data.get('feasibility')}),flush=True)
            assert passed,records[-1]
    print('PASS: all three real Azure/HTTP two-turn flows and saved contexts')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:4200');parser.add_argument('--user-id',type=int,default=5)
    args=parser.parse_args();asyncio.run(main(args.url,args.user_id))
