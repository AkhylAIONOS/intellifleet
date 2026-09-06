"""Conversation boundary regressions: mocked extraction, real supervisor/MCP/planner."""
import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from backend.agents import supervisor as sup
from backend.mcp.tools import planning_tools
from backend.mcp.tools.tool_client import load_mcp_tools
from backend.planning.models import PlanningRequest, Shipment
from backend.planning.service import PlanningService
from test_contextual_disruption import NETWORK, FOLLOWUP

FASTEST='Find the fastest feasible way to move this shipment. Compare it with my current plan and tell me the extra cost, time saved and risk difference.'
COMPARE='Compare Ground and Express for this shipment. Show cost, ETA, risk and reliability, and recommend which one I should choose.'
FUEL='What happens if fuel cost increases by 20%? Keep this as a draft scenario, do not apply it, and compare it with my current baseline.'

@pytest.fixture
def chat(monkeypatch):
    network=copy.deepcopy(NETWORK)
    network['routes'].append(dict(route_id=51,from_location='Origin Hub',to_location='Destination Hub',distance=100,duration=.5,cost=500,route_type='air'))
    network['vehicles'].append(dict(id=3,label='Cargo plane',type='plane',capacity=25000,max_range_km=2000,current_location='Origin Hub',is_available=1))
    service=PlanningService(':memory:');monkeypatch.setattr(service,'load_network',lambda _:copy.deepcopy(network))
    monkeypatch.setattr(planning_tools,'PlanningService',lambda:service)
    monkeypatch.setattr(sup,'get_warehouses_by_userall',lambda _:network['warehouses'])
    monkeypatch.setattr(sup,'get_vehicles_by_user',lambda _:network['vehicles'])
    monkeypatch.setattr(sup,'log_token_usage',lambda *args:None)
    memory={};replies=[]
    async def history(_):return copy.deepcopy(memory.get('history',[]))
    async def save_history(_,value):memory['history']=copy.deepcopy(value)
    async def context(_):return copy.deepcopy(memory.get('context'))
    async def save_context(_,value):memory['context']=copy.deepcopy(value)
    monkeypatch.setattr(sup,'get_data',history);monkeypatch.setattr(sup,'add_data',save_history)
    monkeypatch.setattr(sup,'get_active_planning_context',context);monkeypatch.setattr(sup,'set_active_planning_context',save_context)
    async def invoke(_):return SimpleNamespace(content=replies.pop(0))
    async def ask(message,params,tool='supply_chain_planning_operation'):
        agent=object.__new__(sup.SchemaAwareSupervisor);agent.llm=SimpleNamespace(ainvoke=invoke)
        agent.tools=await load_mcp_tools();agent.tool_metadata=agent._build_tool_metadata()
        replies.extend([tool,json.dumps(params)])
        result=await agent.process_message(7,message)
        assert result['success'],result
        assert result['actions'],result
        return result,result['actions'][0]['data']
    async def initial(ground=False,quantity=12):
        return await ask('Plan 6000 kg from Origin Hub to Destination Hub '+('using Ground transport.' if ground else 'using the best overall option.'),
                         dict(source='Origin Hub',destination='Destination Hub',weight_kg=6000,quantity=quantity,allowed_modes=['road'] if ground else ['road','air']), 'unified_supply_chain_plan')
    return SimpleNamespace(ask=ask,initial=initial,memory=memory,network=network,service=service)

@pytest.mark.parametrize('followup,params,tool',[(FASTEST,{},'unified_supply_chain_plan'),(COMPARE,{'operation':'mode_comparison','parameters':{}},'supply_chain_planning_operation')])
def test_optimization_and_comparison_inherit_at_shared_boundary(chat,followup,params,tool):
    async def run():
        await chat.initial();before=copy.deepcopy(chat.memory['context'])
        result,data=await chat.ask(followup,params,tool)
        req=data['planning_request'];assert req['source']=='Origin Hub' and req['destination']=='Destination Hub'
        assert req['shipment']['weight_kg']==6000 and req['shipment']['quantity']==12
        assert chat.memory['context']['selected_plan_id']==data['recommended_plan']['plan_id']
        if followup==FASTEST:
            assert req['objective']=='fastest';assert data['recommended_plan']['mode']=='air'
            assert data['baseline']['recommended_plan']==before['selected_plan']
            assert 'What changed (before → after)' in result['response']
        else:
            assert data['options']['ground'] and data['options']['express']
            assert data['express_vs_ground']['time_saved_hours']>0
    asyncio.run(run())

@pytest.mark.parametrize('action',['apply','discard'])
def test_replan_then_draft_uses_exact_revised_baseline_and_lifecycle(chat,action):
    async def run():
        await chat.initial(ground=True)
        _,revised=await chat.ask(FOLLOWUP,{'operation':'future_replan'})
        baseline=copy.deepcopy(chat.memory['context']);network=copy.deepcopy(chat.network)
        assert baseline['route_ids']==[21,31,41]
        _,draft=await chat.ask(FUEL,{'operation':'scenario','parameters':{'changes':{'fuel_cost_multiplier':1.2}}})
        assert draft['status']=='draft' and draft['baseline']['recommended_plan']==revised['recommended_plan']
        assert draft['baseline']['planning_request']==baseline['planning_request']
        assert [r['route_id'] for r in draft['scenario']['recommended_plan']['route_legs']]==[21,31,41]
        assert draft['scenario']['recommended_plan']['vehicles']==baseline['assigned_vehicles']
        assert draft['changes']['blocked_routes']==[['Origin Hub','Destination Hub']]
        assert draft['comparison']['cost_difference']>0
        for key in ['selected_plan','planning_request','route_ids','assigned_vehicles','cost','weight_kg','quantity','planning_changes']:
            assert chat.memory['context'][key]==baseline[key],key
        assert chat.network==network
        _,done=await chat.ask(f'{action.title()} this draft plan.',{'operation':'scenario_action','parameters':{'action':action}})
        assert done['status']==('applied' if action=='apply' else 'discarded')
        assert not chat.memory['context'].get('current_scenario')
        if action=='apply':
            assert chat.memory['context']['selected_plan']==draft['scenario']['recommended_plan']
            assert chat.memory['context']['planning_changes']==draft['changes']
        else:assert chat.memory['context']['selected_plan']==baseline['selected_plan']
    asyncio.run(run())

@pytest.mark.parametrize('reference',['this shipment','my shipment','current shipment','current plan','this plan'])
def test_reference_vocabulary_and_explicit_nested_overrides(reference):
    ctx={'source':'A','destination':'B','weight_kg':6000,'quantity':20,'objective':'balanced','planning_request':{'source':'A','destination':'B','shipment':{'weight_kg':6000,'quantity':20},'allowed_modes':['road']}}
    params,clarify=sup._contextual_planning_params(f'Optimize {reference}',{'operation':'plan','parameters':{'destination':'C','shipment':{'weight_kg':8000},'allowed_modes':['air'],'objective':'fastest'}},ctx)
    assert not clarify
    assert params['parameters']['source']=='A' and params['parameters']['destination']=='C'
    assert params['parameters']['shipment']=={'weight_kg':8000,'quantity':20}
    assert params['parameters']['allowed_modes']==['air'] and params['parameters']['objective']=='fastest'


def test_no_context_requires_actual_missing_inputs():
    _,clarify=sup._contextual_planning_params(FASTEST,{'operation':'plan','parameters':{}},None)
    assert all(k in clarify for k in ['source','destination','weight_kg'])


def test_international_parser_uses_generic_endpoints_and_network_metadata(chat):
    for source,dest in [('Origin','Destination'),('Delhi','Frankfurt')]:
        p=sup._specialized_operation_params(f'Plan a 5,000 kg shipment from {source} to {dest} using the best feasible international option in the currently loaded network.')
        assert p['parameters']['source']==source and p['parameters']['destination']==dest
        assert 'source_country' not in p['parameters'] and 'destination_country' not in p['parameters']
    for w in chat.network['warehouses']:
        w['country']='Country A' if w['name']=='Origin Hub' else 'Country B';w['nearest_airport_iata']='SRC' if w['name']=='Origin Hub' else 'DST'
    chat.network['routes']=[r for r in chat.network['routes'] if r['route_type']=='air']
    request=PlanningRequest(source='Origin',destination='Destination',shipment=Shipment(weight_kg=5000))
    result=chat.service.global_plan(7,request)
    assert result['scope']=='international' and result['recommended_plan']['mode']=='air'
    assert len(result['recommended_plan']['route_legs'])==1
    chat.network['warehouses'][-1]['country']=None
    assert chat.service.global_plan(7,request)['recommended_plan'] is None


def test_sla_natural_deadline_and_independent_mode_feasibility(chat):
    assert sup._deadline_from_message('5 September 2026 at 10:00 PM IST')=='2026-09-05T22:00:00+05:30'
    request=PlanningRequest(source='Origin Hub',destination='Destination Hub',shipment=Shipment(weight_kg=6000))
    initial=chat.service.compare_modes(7,request)
    ground,air=initial['options']['ground'],initial['options']['air']
    deadline=datetime.now(timezone.utc)+timedelta(hours=(ground['duration_hours']+air['duration_hours'])/2)
    result=chat.service.compare_modes(7,request.model_copy(update={'deadline':deadline,'objective':'fastest'}))
    assert result['options']['ground']['sla_met'] is False
    assert result['options']['air']['sla_met'] is True
    assert result['recommended_plan']['mode']=='air'
