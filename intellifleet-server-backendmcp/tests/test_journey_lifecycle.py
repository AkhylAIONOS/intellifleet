import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
import pytest
from test_operations import loaded
from backend.planning.lifecycle import record, resolve
from backend.planning.models import PlanningRequest
from backend.planning.service import PlanningService
from backend.agents.supervisor import _context_from_result, _format_planning_result
from backend.operations.journey_chat import answer
from backend.operations.chat import answer as status

@pytest.fixture
def session(loaded, monkeypatch):
    network, runtime, clock = loaded
    import backend.fedex.telemetry as telemetry
    import backend.config.redis as redis
    monkeypatch.setattr(telemetry, 'runtime', runtime)
    memory = {}
    async def save(owner, context): memory.clear(); memory.update(deepcopy(context))
    monkeypatch.setattr(redis, 'set_active_planning_context', save)
    def plan(a='Bengaluru', b='Delhi', modes=None, weight=6000):
        result = PlanningService().plan(1, PlanningRequest(source=a,destination=b,shipment={'weight_kg':weight},allowed_modes=modes or ['road']))
        previous = {'journeys':deepcopy(memory.get('journeys',{}))}
        updated = record(1,result,previous,_context_from_result(result,previous),revise=False)
        memory.clear();memory.update(deepcopy(updated))
        return result
    def ask(message): return asyncio.run(answer(1,message,deepcopy(memory)))
    return memory, runtime, clock, plan, ask


def test_a_b_c_e_i_j_workflow(session):
    memory, runtime, clock, plan, ask = session
    first = plan(); first_id=memory['movement_id']; journey=memory['journey_id']
    response=ask('Find the fastest feasible Ground route for the current Bengaluru to Delhi shipment.')
    assert response['actions'] and len(runtime.entries)==1
    assert memory['journey_id']==journey and memory['movement_id']==first_id
    assert 'Route before:' in response['response'] and 'Route after:' in response['response']
    plan('Mumbai','Bengaluru'); second_id=memory['movement_id']; before=deepcopy(runtime.get(1,second_id).snapshot())
    response=ask('The current Bengaluru to Delhi road route is blocked ahead and cannot be used. Replan the same shipment using another feasible Ground route.')
    assert len(runtime.entries)==2
    unchanged=runtime.get(1,second_id).snapshot()
    assert {k:v for k,v in unchanged.items() if k!='sequence'}=={k:v for k,v in before.items() if k!='sequence'}
    if response['actions'][0]['type']=='supply_chain_planning_operation':
        data=response['actions'][0]['data']; blocked=set(data['applied_changes']['blocked_route_ids'])
        assert not blocked.intersection(l['route_id'] for l in data['recommended_plan']['route_legs'])
    else: assert 'No feasible' in response['response']
    response=ask('The current Mumbai to Bengaluru shipment has been delayed by 120 minutes. Calculate revised ETA and recommend mitigation.')
    after=runtime.get(1,second_id).snapshot()
    assert after['simulation_id']==second_id and len(runtime.entries)==2
    assert datetime.fromisoformat(after['current_eta'])==datetime.fromisoformat(before['current_eta'])+timedelta(minutes=120)
    assert after['delay_minutes']==120


def test_d_breakdown_midroute_is_recovery_not_status(session):
    memory,runtime,clock,plan,ask=session
    plan();sim=runtime.get(1,memory['movement_id']);sim.progress=.2
    response=ask('The truck assigned to the current Bengaluru to Delhi shipment has broken down. Show operational impact and revised ETA, cost and risk.')
    assert 'Breakdown recovery' in response['response'] and 'mid-route' in response['response']
    assert sim.paused and len(runtime.entries)==1
    assert status(1,'truck has broken down; revised ETA') is None


def test_f_g_same_od_context_and_ambiguity(session):
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Mumbai');first=memory['movement_id'];plan('Delhi','Mumbai');second=memory['movement_id']
    assert first!=second and len(runtime.entries)==2
    response=status(1,'Show current operational status of the active Delhi to Mumbai shipment.')
    assert 'Candidates:' in response['response']
    response=status(1,'Show current operational status of the active Delhi to Mumbai shipment.',second)
    assert response['response'].count('Current shipment:')==1
    assert response['actions'][0]['data']['selected']==second
    _,error=resolve({},'current Delhi to Mumbai shipment')
    assert error


def test_k_l_m_multimodal_real_loaded_network(session):
    memory,runtime,clock,plan,ask=session
    result=plan('Delhi','Chennai',['multimodal'],5000)
    p=result['recommended_plan'];assert p['mode']=='multimodal'
    assert {'road','air'}=={l['route_type'] for l in p['route_legs']}
    assert len(p['vehicles'])>=2 and len(runtime.entries)==1
    identity=memory['journey_id'];movement=memory['movement_id']
    snapshot=runtime.get(1,movement).snapshot()
    assert {s['mode'] for s in snapshot['journey_segments']}=={'SURFACE','AIR'}
    response=ask('The Air leg of this current shipment is disrupted. Replan the same shipment.')
    assert len(runtime.entries)==1 and memory['journey_id']==identity
    assert memory['movement_id']==movement
    pure=PlanningService().plan(1,PlanningRequest(source='Delhi',destination='Chennai',shipment={'weight_kg':5000},allowed_modes=['air']))
    assert pure['recommended_plan'] is None
    impossible=PlanningService().plan(1,PlanningRequest(source='Delhi',destination='Chennai',shipment={'weight_kg':1e9},allowed_modes=['multimodal']))
    assert impossible['recommended_plan'] is None and not impossible['candidate_plans']


def test_n_new_session_does_not_resolve_old(session):
    memory,runtime,clock,plan,ask=session
    plan();selected,error=resolve({},'current shipment')
    assert not selected and error


def test_p_q_stop_one_and_playback(session):
    memory,runtime,clock,plan,ask=session
    plan();first=memory['movement_id'];plan('Mumbai','Bengaluru');second=memory['movement_id']
    runtime.get(1,first).control('stop',clock[0]);other=runtime.get(1,second)
    other.control('resume',clock[0]);clock[0]+=1;runtime.tick()
    assert other.speed==120 and other.progress>0 and not other.stopped
    assert runtime.get(1,first).stopped


def test_normal_disruption_excludes_ground_before_scoring(loaded):
    network,_,_=loaded
    s=PlanningService();request=PlanningRequest(source='Delhi',destination='Mumbai',shipment={'weight_kg':6000})
    baseline=s.plan(1,request.model_copy(update={'allowed_modes':['road']}))['recommended_plan']
    result=s.plan(1,request,changes={'normal_ground_disrupted':True})
    excluded={leg['route_id'] for leg in baseline['route_legs']}
    assert result['recommended_plan']
    assert all(not excluded.intersection(leg['route_id'] for leg in p['route_legs']) for p in result['candidate_plans'])
    assert any(p['mode']=='air' for p in result['candidate_plans'])


def test_old_revision_cannot_rollback(session):
    from backend.operations.plan_journeys import start
    memory,runtime,clock,plan,ask=session
    original=plan()['recommended_plan'];ask('Find fastest route for current Bengaluru to Delhi shipment.')
    current=memory['selected_plan_id']
    snapshot=start(1,original['plan_id'])
    assert snapshot['plan_id']==current and len(runtime.entries)==1


def test_ai_chat_supervisor_registration_then_api_delay(session,monkeypatch):
    from types import SimpleNamespace
    import json
    from backend.agents import supervisor as sup
    from backend.api import chat_api
    from backend.mcp.tools.tool_client import load_mcp_tools
    memory,runtime,clock,plan,ask=session
    async def get_context(_):return deepcopy(memory)
    async def save_context(_,value):memory.clear();memory.update(deepcopy(value))
    async def get_history(_):return []
    async def save_history(*_):pass
    monkeypatch.setattr(sup,'get_active_planning_context',get_context)
    monkeypatch.setattr(sup,'set_active_planning_context',save_context)
    monkeypatch.setattr(chat_api,'get_active_planning_context',get_context)
    monkeypatch.setattr(sup,'get_data',get_history);monkeypatch.setattr(sup,'add_data',save_history)
    monkeypatch.setattr(sup,'log_token_usage',lambda *args:None)
    replies=['unified_supply_chain_plan',json.dumps({'source':'Mumbai','destination':'Bengaluru','weight_kg':6000,'allowed_modes':['road'],'objective':'cheapest'})]
    async def invoke(_):return SimpleNamespace(content=replies.pop(0))
    async def run():
        agent=object.__new__(sup.SchemaAwareSupervisor);agent.llm=SimpleNamespace(ainvoke=invoke)
        agent.tools=await load_mcp_tools();agent.tool_metadata=agent._build_tool_metadata()
        monkeypatch.setattr(chat_api,'supervisor',agent)
        response=await chat_api.agent_chat(chat_api.ChatRequest(message='Find the cheapest feasible Ground route for a 6000 kg shipment from Mumbai to Bengaluru.'),{'user_id':1})
        assert response['actions'] and len(runtime.entries)==1
        sid=memory['movement_id'];before=runtime.get(1,sid).current_eta
        response=await chat_api.agent_chat(chat_api.ChatRequest(message='The current Mumbai to Bengaluru shipment has been delayed by 120 minutes. Calculate revised ETA and operational impact.'),{'user_id':1})
        assert response['actions'][0]['type']=='movement_updated'
        assert runtime.get(1,sid).current_eta==before+timedelta(minutes=120)
        assert len(runtime.entries)==1 and memory['movement_id']==sid
    asyncio.run(run())


def test_verified_origin_breakdown_recovery(session):
    memory,runtime,clock,plan,ask=session
    plan();failed=memory['assigned_vehicles'][0]['label'];sid=memory['movement_id']
    response=ask('The truck assigned to the current Bengaluru to Delhi shipment has broken down. Recommend the best feasible mitigation plan.')
    assert len(runtime.entries)==1 and memory['movement_id']==sid
    if response['actions'][0]['type']=='supply_chain_planning_operation':
        result=response['actions'][0]['data'];recovery=result['recovery_plan']
        assert recovery and all(v['label']!=failed for v in recovery['vehicles'])
        assert sum(v['assigned_load_kg'] for v in recovery['vehicles'])==6000
        assert recovery['operational_cost']>0 and recovery['eta'] and recovery['risk_score']>=0
    else:
        assert 'No feasible alternative/recovery' in response['response']


def test_r_s_t_geometry_and_compact_telemetry(session,monkeypatch):
    from backend.operations.road_routing_engine import road_routing_engine
    from backend.operations.service import movements
    memory,runtime,clock,plan,ask=session
    calls=[];original=road_routing_engine.get_route
    def tracked(*args,**kwargs):calls.append(args[:4]);return original(*args,**kwargs)
    monkeypatch.setattr(road_routing_engine,'get_route',tracked)
    result=plan('Delhi','Chennai',['multimodal'],5000)
    legs=result['recommended_plan']['route_legs']
    expected=[(l['source_coords']['lat'],l['source_coords']['lng'],l['destination_coords']['lat'],l['destination_coords']['lng']) for l in legs if l['route_type']=='road']
    assert calls==expected
    snapshot=runtime.get(1,memory['movement_id']).snapshot()
    for segment in snapshot['journey_segments']:
        if segment['mode']=='AIR':assert segment['end_index']-segment['start_index']==1
        else:assert segment['end_index']-segment['start_index']>1
    compact=movements(1,include_geometry=False)
    assert all('route' not in m for m in compact['movements'])
    assert len([m for m in compact['movements'] if m['status']!='SCHEDULE_TEMPLATE'])==1


def test_stopped_logical_journey_is_not_restarted_by_followup(session):
    memory,runtime,clock,plan,ask=session
    plan();sid=memory['movement_id'];runtime.get(1,sid).control('stop',clock[0])
    response=ask('Add a 120 minute delay to this shipment.')
    assert 'stopped or completed' in response['response']
    assert len(runtime.entries)==1 and runtime.get(1,sid).stopped


def test_change_truck_excludes_current_assignment(session):
    memory,runtime,clock,plan,ask=session
    plan();failed=memory['assigned_vehicles'][0]['label'];sid=memory['movement_id']
    response=ask('Change the truck for this shipment.')
    assert len(runtime.entries)==1 and memory['movement_id']==sid
    assert failed in memory['planning_changes']['unavailable_vehicles']
    if response['actions'][0]['type']=='supply_chain_planning_operation':
        assert all(v['label']!=failed for v in memory['assigned_vehicles'])


def test_legacy_active_plan_adopts_existing_movement(session):
    from backend.operations.plan_journeys import start
    from backend.planning.lifecycle import record
    memory,runtime,clock,plan,ask=session
    service=PlanningService();request=PlanningRequest(source='Bengaluru',destination='Delhi',shipment={'weight_kg':6000},allowed_modes=['road'])
    initial=service.plan(1,request);old=initial['recommended_plan']
    original=start(1,old['plan_id']);context=_context_from_result(initial)
    revised=service.plan(1,request.model_copy(update={'objective':'fastest'}))
    updated=record(1,revised,context,_context_from_result(revised,context),revise=True)
    assert updated['movement_id']==original['simulation_id'] and len(runtime.entries)==1
    assert updated['journey_id']==old['plan_id']


def test_revision_recovers_identity_from_existing_movement(session):
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Bengaluru')
    sid=memory['movement_id'];journey=memory['journey_id']
    # Compatibility context retains a selected revision and movement, but lacks
    # the newer top-level logical ID/registry. Never adopt the revision as a journey.
    previous=deepcopy(memory);previous.pop('journey_id');previous.pop('journeys')
    previous['selected_plan'].pop('journey_id')
    request=PlanningRequest(**previous['planning_request']).model_copy(update={'objective':'cheapest'})
    result=PlanningService().plan(1,request)
    updated=record(1,result,previous,_context_from_result(result,previous),revise=True)
    assert updated['journey_id']==journey and updated['movement_id']==sid
    assert len(runtime.entries)==1


def test_recache_cannot_erase_committed_journey_identity(session):
    from backend.operations.plan_journeys import remember,start
    memory,runtime,clock,plan,ask=session
    result=plan('Delhi','Bengaluru');sid=memory['movement_id']
    raw=deepcopy(result['recommended_plan']);raw.pop('journey_id');raw.pop('revision')
    remember(1,[raw])
    assert start(1,raw['plan_id'])['simulation_id']==sid
    assert len(runtime.entries)==1


@pytest.mark.parametrize('label,canonical', [('Ground','road'),('ground','road'),('Surface','road'),('Road','road'),('road','road'),('Air','air'),('air','air'),('Airway','air'),('Multimodal','multimodal'),('Multi-modal','multimodal')])
def test_modes_normalized_at_planning_boundary(label,canonical):
    from backend.planning.intent import CanonicalPlanningIntent
    data={'source':'Delhi','destination':'Bengaluru','shipment':{'weight_kg':6000},'allowed_modes':[label]}
    assert PlanningRequest(**data).allowed_modes==[canonical]
    resolved=CanonicalPlanningIntent(operation='plan',parameters={**data,'changes':{'allowed_modes':[label]}}).resolve({})
    assert resolved['allowed_modes']==[canonical]
    assert resolved['changes']['allowed_modes']==[canonical]


def test_imperative_delay_is_action(session):
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Bengaluru');sid=memory['movement_id'];before=runtime.get(1,sid).current_eta
    response=ask('Delay this same Delhi to Bengaluru shipment by 30 minutes. Show the revised ETA, operational impact and any mitigation recommendation.')
    assert response and len(response['actions'])==1
    snapshot=response['actions'][0]['data']
    assert snapshot['simulation_id']==sid and snapshot['delay_minutes']==30
    assert datetime.fromisoformat(snapshot['current_eta'])==before+timedelta(minutes=30)
    assert len(runtime.entries)==1


@pytest.mark.parametrize('compatibility_context', [False, True])
def test_exact_delhi_bengaluru_http_lifecycle(session, monkeypatch, compatibility_context):
    """Real endpoints, planner, replay and operations; only LLM extraction is mocked."""
    from types import SimpleNamespace
    import json
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.agents import supervisor as sup
    from backend.api import chat_api
    from backend.operations import routes
    from backend.routes.auth import get_current_user
    from backend.mcp.tools.tool_client import load_mcp_tools
    memory,runtime,clock,_,_=session
    async def get_context(_):return deepcopy(memory)
    async def save_context(_,value):memory.clear();memory.update(deepcopy(value))
    async def history(_):return []
    async def save_history(*_):pass
    for module in (sup,chat_api):monkeypatch.setattr(module,'get_active_planning_context',get_context)
    monkeypatch.setattr(sup,'set_active_planning_context',save_context)
    monkeypatch.setattr(sup,'get_data',history);monkeypatch.setattr(sup,'add_data',save_history)
    monkeypatch.setattr(sup,'log_token_usage',lambda *args:None)
    replies=['unified_supply_chain_plan',json.dumps({'source':'Delhi','destination':'Bengaluru','weight_kg':6000,'allowed_modes':['Ground']})]
    async def invoke(_):return SimpleNamespace(content=replies.pop(0))
    agent=object.__new__(sup.SchemaAwareSupervisor);agent.llm=SimpleNamespace(ainvoke=invoke)
    agent.tools=asyncio.run(load_mcp_tools());agent.tool_metadata=agent._build_tool_metadata()
    monkeypatch.setattr(chat_api,'supervisor',agent)
    app=FastAPI();app.include_router(chat_api.router);app.include_router(routes.router)
    app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    prompts=[
        'Plan a 6,000 kg Ground shipment from Delhi to Bengaluru.',
        'Make this same Delhi to Bengaluru shipment the cheapest feasible Ground plan.',
        'Now make this same Delhi to Bengaluru shipment the fastest feasible Ground plan.',
        'Delay this same Delhi to Bengaluru shipment by 30 minutes. Show the revised ETA, operational impact and any mitigation recommendation.',
        'The current Delhi to Bengaluru road route is blocked ahead and cannot be used. Replan this same shipment using another feasible Ground route.',
    ]
    counts=[];sid=None;journey=None;before_delay=None;blocked=set()
    with TestClient(app) as client:
        for index,prompt in enumerate(prompts):
            if index and compatibility_context:
                memory.pop('journey_id',None);memory.pop('journeys',None)
                memory['selected_plan'].pop('journey_id',None)
                memory['planning_request']['allowed_modes']=['Ground']
            if index==3:before_delay=runtime.get(1,sid).current_eta
            if index==4:blocked=set(memory['route_ids'])
            response=client.post('/mcp-agent',json={'message':prompt,'selected_simulation_id':sid})
            assert response.status_code==200,response.text
            body=response.json();assert body['success'],body
            for action in body['actions']:
                plan=action['data'].get('recommended_plan')
                if plan:
                    # The browser's ensurePlanMovement runs after the chat response.
                    replay=client.post('/operations/plan-journeys/'+plan['plan_id'])
                    assert replay.status_code==201,replay.text
                    assert replay.json()['simulation_id']==memory['movement_id']
            all_states=client.get('/operations/movements').json()['movements']
            active=[m for m in all_states if m['shipment_id'].startswith('PLAN-') and not m.get('stopped')]
            counts.append(len(active));assert len(active)==1,(index,active)
            current=active[0]
            sid=sid or current['simulation_id'];journey=journey or current['journey_id']
            assert current['simulation_id']==sid and current['journey_id']==journey
            if index==3:
                assert current['delay_minutes']==30
                assert datetime.fromisoformat(current['current_eta'])==before_delay+timedelta(minutes=30)
                assert len(body['actions'])==1 and body['actions'][0]['type']=='movement_updated'
                assert body['response'].count(current['shipment_id'])==1
            if index==4:
                revised=next((a['data'].get('recommended_plan') for a in body['actions'] if a['data'].get('recommended_plan')),None)
                if revised:
                    assert not blocked.intersection(l['route_id'] for l in revised['route_legs'])
                    disruption_outcome='different feasible path'
                else:
                    assert 'No feasible alternative' in body['response'],body
                    disruption_outcome='explicit no feasible alternative'
        assert counts==[1,1,1,1,1]
        print({'compatibility_context':compatibility_context,'movement_counts':counts,'delay_minutes':30,'eta_delta_minutes':30,'disruption':disruption_outcome})
