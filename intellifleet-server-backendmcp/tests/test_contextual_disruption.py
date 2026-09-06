import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from backend.agents import supervisor as sup
from backend.mcp.tools import planning_tools
from backend.mcp.tools.tool_client import load_mcp_tools
from backend.planning.service import PlanningService

FOLLOWUP = ('The direct route in my current plan is unavailable. Replan this shipment using the best feasible alternative. '
            'Show the old route, new route, vehicle, cost, ETA and risk differences.')
NETWORK = {
    'warehouses': [{'warehouse_id': i, 'name': name, 'inventory': 100, 'is_active': 1}
                   for i, name in enumerate(['Origin Hub', 'Transfer One', 'Transfer Two', 'Destination Hub'], 1)],
    'routes': [dict(route_id=i, from_location=a, to_location=b, distance=d, duration=t, cost=c, route_type='road',
                    source_coords={'lat':i,'lng':i},destination_coords={'lat':i+1,'lng':i+1})
               for i,a,b,d,t,c in [(11,'Origin Hub','Destination Hub',100,2,10),
                                    (21,'Origin Hub','Transfer One',100,1,6),
                                    (31,'Transfer One','Transfer Two',100,1,6),
                                    (41,'Transfer Two','Destination Hub',100,1,6)]],
    'vehicles': [dict(id=1,label='Long-range',type='truck',capacity=12000,max_range_km=400,current_location='Origin Hub',is_available=1),
                 dict(id=2,label='Short-range',type='truck',capacity=7000,max_range_km=150,current_location='Origin Hub',is_available=1)],
}

@pytest.mark.parametrize('weight,message,feasible', [
    (6000,FOLLOWUP,True),
    (6000,'The direct route from Origin Hub to Destination Hub is unavailable. Replan this shipment.',True),
    (18000,FOLLOWUP,False),
])
def test_two_turn_real_supervisor_and_mcp(monkeypatch,weight,message,feasible):
    service=PlanningService(':memory:')
    monkeypatch.setattr(service,'load_network',lambda _:copy.deepcopy(NETWORK))
    monkeypatch.setattr(planning_tools,'PlanningService',lambda:service)
    monkeypatch.setattr(sup,'get_warehouses_by_userall',lambda _:NETWORK['warehouses'])
    monkeypatch.setattr(sup,'get_vehicles_by_user',lambda _:NETWORK['vehicles'])
    monkeypatch.setattr(sup,'log_token_usage',lambda *args:None)
    memory={}
    async def history(_):return copy.deepcopy(memory.get('history',[]))
    async def save_history(_,value):memory['history']=copy.deepcopy(value)
    async def context(_):return copy.deepcopy(memory.get('context'))
    async def save_context(_,value):memory['context']=copy.deepcopy(value)
    monkeypatch.setattr(sup,'get_data',history);monkeypatch.setattr(sup,'add_data',save_history)
    monkeypatch.setattr(sup,'get_active_planning_context',context);monkeypatch.setattr(sup,'set_active_planning_context',save_context)
    replies=iter(['unified_supply_chain_plan',json.dumps({'source':'Origin Hub','destination':'Destination Hub','weight_kg':weight,'allowed_modes':['ground']}),
                  'supply_chain_planning_operation',json.dumps({'operation':'future_replan','parameters':{'route_status':'direct route unavailable'}})])
    async def invoke(_):return SimpleNamespace(content=next(replies))
    async def run():
        agent=object.__new__(sup.SchemaAwareSupervisor);agent.llm=SimpleNamespace(ainvoke=invoke)
        agent.tools=await load_mcp_tools();agent.tool_metadata=agent._build_tool_metadata()
        first=await agent.process_message(7,f'Plan {weight:,} kg from Origin Hub to Destination Hub using Ground transport.')
        assert first['success'],first
        before=copy.deepcopy(memory['context']);assert before['allowed_modes']==['road']
        assert before['selected_plan']['route_legs'][0]['route_id']==11
        second=await agent.process_message(7,message)
        assert second['success'],second
        assert 'couldn\'t complete' not in second['response']
        action=second['actions'][0];data=action['data']
        assert action['type']=='supply_chain_planning_operation'
        assert data['planning_operation']=='route_alternatives'
        assert data['planning_request']['allowed_modes']==['road']
        assert data['planning_request']['shipment']['weight_kg']==weight
        assert data['applied_changes']['blocked_routes']==[['Origin Hub','Destination Hub']]
        assert data['baseline']['recommended_plan']==before['selected_plan']
        if feasible:
            plan=data['recommended_plan'];assert [leg['route_id'] for leg in plan['route_legs']]==[21,31,41]
            assert plan['vehicles'][0]['label']=='Long-range'
            assert memory['context']['selected_plan_id']==plan['plan_id']
            assert memory['context']['route_ids']==[21,31,41]
            assert memory['context']['weight_kg']==weight and memory['context']['allowed_modes']==['road']
            assert memory['context']['assigned_vehicles']==plan['vehicles']
            assert memory['context']['planning_changes']==data['applied_changes']
            assert data['replan_comparison']['cost_difference']==round(plan['operational_cost']-before['cost'],2)
            assert 'What changed (before → after)' in second['response']
            assert 'percentage points' in second['response']
        else:
            assert data['recommended_plan'] is None
            assert data['feasibility']['constraint']=='vehicle_capacity_or_full_route_range'
            assert memory['context']['selected_plan_id']==before['selected_plan_id']
            assert memory['context']['route_legs']==before['route_legs']
            assert 'current plan remains unchanged' in second['response']
    asyncio.run(run())

@pytest.mark.parametrize('reference',['current route','this route','direct route','route in my current plan','my route','new route'])
def test_route_reference_vocabulary(reference):
    context={'source':'A','destination':'B','weight_kg':6000,'allowed_modes':['road'],
             'route_legs':[{'from_location':'A','to_location':'B','route_type':'road'}]}
    resolved,clarify=sup._contextual_planning_params(f'The {reference} is unavailable. Replan this shipment.',{'operation':'future_replan'},context)
    assert clarify is None and resolved['operation']=='route_alternatives'
    assert resolved['parameters']['changes']['blocked_routes']==[['A','B']]


def test_ambiguous_multileg_reference_does_not_invent_blocked_leg():
    context={'source':'A','destination':'C','weight_kg':6000,'allowed_modes':['road'],
             'route_legs':[{'from_location':'A','to_location':'B'},{'from_location':'B','to_location':'C'}]}
    _,clarification=sup._contextual_planning_params('My current route is unavailable.',{},context)
    assert 'Which leg' in clarification
