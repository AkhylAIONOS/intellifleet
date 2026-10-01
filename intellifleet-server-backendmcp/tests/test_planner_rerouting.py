from copy import deepcopy
import pytest
from test_operations import loaded
from test_journey_lifecycle import session
from backend.planning.lifecycle import is_action, explicit_live_recovery


@pytest.mark.parametrize('prompt', [
    'The current route is unavailable. Use another route.',
    'The current route is blocked.', 'Use another route.', 'Avoid this route.',
    'Find an alternative route.', 'Use the cheapest alternative.',
    'Use the fastest alternative.', 'Use the lowest-risk alternative.',
])
def test_normal_alternative_reroutes_after_simulation_progress(session, prompt):
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Bengaluru');identity=memory['journey_id'];movement=memory['movement_id']
    sim=runtime.get(1,movement);sim.progress=.35
    previous=set(sim.network_route_ids)
    response=ask(prompt)
    assert response and response['actions'], response
    assert 'transfer/rejoin' not in response['response']
    assert response['actions'][0]['type']=='supply_chain_planning_operation',response
    data=response['actions'][0]['data'];current=data['recommended_plan']
    assert current and not previous.intersection(leg['route_id'] for leg in current['route_legs'])
    assert memory['journey_id']==identity and memory['movement_id']==movement
    assert len(runtime.entries)==1 and data['movement']['simulation_id']==movement
    assert runtime.get(1,movement).progress==0
    assert previous.issubset(set(memory['planning_changes']['blocked_route_ids']))
    for objective in ('cheapest','fastest','lowest-risk'):
        if objective in prompt: assert memory['planning_request']['objective']==objective


def test_followup_cheapest_keeps_blocks_and_same_journey(session):
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Bengaluru');movement=memory['movement_id'];identity=memory['journey_id']
    runtime.get(1,movement).progress=.2
    first=ask('The current route is unavailable. Use another route.')
    assert first['actions'][0]['data']['recommended_plan']
    blocked=set(memory['planning_changes']['blocked_route_ids'])
    runtime.get(1,movement).progress=.4
    second=ask('Use the cheapest alternative route.')
    assert len(runtime.entries)==1 and memory['journey_id']==identity and memory['movement_id']==movement
    assert 'transfer/rejoin' not in second['response']
    assert blocked.issubset(memory['planning_changes']['blocked_route_ids'])
    assert second['actions'][0]['type']=='supply_chain_planning_operation',second
    if second['actions'][0]['type']=='supply_chain_planning_operation':
        result=second['actions'][0]['data']
        assert result['recommended_plan']
        assert memory['planning_request']['objective']=='cheapest'
        assert not set(memory['planning_changes']['blocked_route_ids']).intersection(l['route_id'] for l in result['recommended_plan']['route_legs'])
    else:
        assert 'No feasible' in second['response']


@pytest.mark.parametrize('prompt', [
    'The truck is already in transit and the road ahead is blocked.',
    'Re-route the live vehicle from its current position.',
    'The truck is currently at Jaipur and needs recovery.',
])
def test_explicit_live_requests_keep_rejoin_guard(session,prompt):
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Bengaluru');movement=memory['movement_id']
    runtime.get(1,movement).progress=.3
    before=deepcopy(runtime.get(1,movement).network_route_ids)
    response=ask(prompt)
    assert is_action(prompt) and explicit_live_recovery(prompt)
    assert 'transfer/rejoin' in response['response'],response
    assert len(runtime.entries)==1 and runtime.get(1,movement).network_route_ids==before


def test_infeasible_returns_exact_planner_reason(session,monkeypatch):
    from backend.planning.service import PlanningService
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Bengaluru');movement=memory['movement_id'];runtime.get(1,movement).progress=.5
    reason='No feasible Ground path: all remaining links exceed the vehicle capacity constraint.'
    monkeypatch.setattr(PlanningService,'plan',lambda *a,**kw:{'recommended_plan':None,'reason':reason})
    response=ask('Avoid this route. Find an alternative route.')
    assert reason in response['response'] and 'transfer/rejoin' not in response['response']
    assert len(runtime.entries)==1 and response['actions'][0]['data']['simulation_id']==movement


def test_api_alternatives_after_elapsed_simulation_reuse_registration(session,monkeypatch):
    import asyncio
    from backend.api import chat_api
    from backend.operations.plan_journeys import start
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Bengaluru');movement=memory['movement_id'];journey=memory['journey_id']
    async def context(_):return deepcopy(memory)
    monkeypatch.setattr(chat_api,'get_active_planning_context',context)
    class NoSupervisor:
        llm=None
        async def process_message(self,*args,**kwargs):raise AssertionError('Reroute reached LLM')
    monkeypatch.setattr(chat_api,'supervisor',NoSupervisor())
    for prompt in ['The current route is unavailable. Use another route.','Use the cheapest alternative route.']:
        clock[0]+=10
        runtime.tick()
        assert runtime.get(1,movement).progress>0
        result=asyncio.run(chat_api.agent_chat(chat_api.ChatRequest(message=prompt,selected_simulation_id=movement),{'user_id':1}))
        assert result['actions'][0]['type']=='supply_chain_planning_operation',result
        plan_result=result['actions'][0]['data']['recommended_plan']
        assert plan_result['journey_id']==journey
        assert start(1,plan_result['plan_id'])['simulation_id']==movement
        assert len(runtime.entries)==1
        assert 'transfer/rejoin' not in result['response']
