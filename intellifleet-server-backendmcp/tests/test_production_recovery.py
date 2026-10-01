import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import pytest
from test_journey_lifecycle import session
from test_operations import loaded
from backend.operations.batch_planning import answer as batch_answer, parse
from backend.operations.journey_display import answer as display
from backend.planning.recovery import recover_air, strict_air_only
from backend.planning.service import PlanningService
from backend.planning.models import PlanningRequest


@pytest.mark.parametrize('text', ['Air-only', 'aircraft only', 'keep it Air', 'do not use Ground', 'no Ground fallback'])
def test_explicit_air_constraint(text):
    assert strict_air_only(text)


def test_recovery_revision_and_sla(session):
    memory, runtime, clock, plan, ask = session
    plan('Mumbai','Bengaluru',['air'],5000)
    before=deepcopy(memory)
    old_route=runtime.get(1,memory['movement_id']).snapshot()['route']
    response=ask('The current Air route is unavailable. Find the fastest feasible recovery. It still must arrive before tomorrow at 6 PM.')
    assert response['actions']
    data=response['actions'][0]['data'];p=data['recommended_plan']
    assert not set(before['route_ids']).intersection(l['route_id'] for l in p['route_legs'])
    assert memory['journey_id']==before['journey_id'] and memory['movement_id']==before['movement_id']
    assert len(runtime.entries)==1
    assert p['deadline'] and 'SLA before disruption:' in response['response']
    assert 'Old ETA:' in response['response'] and 'New ETA:' in response['response']
    snapshot=runtime.get(1,memory['movement_id']).snapshot()
    assert snapshot['revision']==2
    assert snapshot['route'] != old_route


def test_strict_air_disruption(session):
    memory,runtime,clock,plan,ask=session
    plan('Mumbai','Bengaluru',['air'],5000)
    response=ask('The current Air route is unavailable. Keep this shipment Air-only and find another feasible route.')
    if response['actions'][0]['type']=='supply_chain_planning_operation':
        assert {l['route_type'] for l in response['actions'][0]['data']['recommended_plan']['route_legs']}=={'air'}
    else:
        assert 'No feasible' in response['response']
    assert memory['strict_air_only']


def test_batch_and_ordinals(session):
    memory,runtime,clock,plan,ask=session
    network=PlanningService().load_network(1)
    roads=[r for r in network['routes'] if r['route_type']=='road'][:3]
    lanes='\n'.join(f"{r['from_location']} → {r['to_location']}" for r in roads)
    message='Create 6,000 kg Ground shipments:\n'+lanes
    result=asyncio.run(batch_answer(1,message,memory))
    assert 'Created: 3' in result['response']
    assert len(memory['journeys'])==3 and len(runtime.entries)==3
    assert len(set(memory['map_comparison_ids']))==3
    for ctx in memory['journeys'].values():
        assert ctx['weight_kg']==6000 and ctx['selected_plan']['revision']==1
    for message,count in [('Show these three routes together.',3),('Show only the second shipment.',1),('Show all three again.',3)]:
        action=display(1,message,memory)['actions'][0]['data']
        assert len(action['simulation_ids'])==count
        if count==1:assert action['simulation_ids']==[memory['map_comparison_ids'][1]]
    # A valid but impossible load does not discard feasible siblings.
    result=asyncio.run(batch_answer(1,'Create Ground shipments:\n'+f"{roads[0]['from_location']} to {roads[0]['to_location']} 1000 kg\n"+f"{roads[1]['from_location']} to {roads[1]['to_location']} 999999999 kg",memory))
    assert 'Created: 1' in result['response'] and 'Infeasible: 1' in result['response']
    assert len(memory['journeys'])==4
    names=[r['from_location'] for r in roads]
    destination=roads[0]['to_location']
    assert len(parse(f"Create Ground shipments from {', '.join(names[:-1])} and {names[-1]} to {destination}.",network))==3


def test_multimodal_segment_timing_and_carriers(session):
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Chennai',['multimodal'],5000)
    sim=runtime.get(1,memory['movement_id'])
    snapshots=[]
    for index,segment in enumerate(sim.journey_segments):
        for fraction in (.2,.8):
            sim.progress=segment['start_progress']+fraction*(segment['end_progress']-segment['start_progress'])
            snap=sim.snapshot();snapshots.append(snap)
            assert snap['active_leg_index']==index and snap['mode']==segment['mode']
            assert snap['active_vehicles']==segment['vehicles'] and snap['active_vehicles']
            assert snap['segment_progress']==pytest.approx(fraction)
            assert all((v['type'].lower() in {'plane','aircraft'})==(snap['mode']=='AIR') for v in snap['active_vehicles'])
        assert snapshots[-1]['latitude']!=snapshots[-2]['latitude'] or snapshots[-1]['longitude']!=snapshots[-2]['longitude']
    assert 'AIR' in {s['mode'] for s in snapshots}


def test_objectives_deadline_budget_and_strict_alternative(loaded):
    network,_,_=loaded
    service=PlanningService()
    air=next(r for r in service.load_network(1)['routes'] if r['route_type']=='air')
    request=PlanningRequest(source=air['from_location'],destination=air['to_location'],shipment={'weight_kg':1},allowed_modes=['air'])
    changes={'blocked_route_ids':[air['route_id']]}
    for objective,metric in [('fastest','duration_hours'),('cheapest','operational_cost'),('lowest-risk','risk_score')]:
        result=recover_air(service,1,request.model_dump(mode='json'),changes,f'Find the {objective} recovery')
        p=result['recommended_plan']
        if p:assert p[metric]==min(x[metric] for x in result['candidate_plans'])
    result=recover_air(service,1,request.model_dump(mode='json'),changes,'Keep it under ₹800,000 if possible')
    if result['recommended_plan'] and result['recommended_plan']['operational_cost']>800000:assert result['warnings']
    request.deadline=datetime.now(timezone.utc)-timedelta(hours=1);request.sla_mandatory=True
    result=recover_air(service,1,request.model_dump(mode='json'),changes)
    assert result['recommended_plan'] and result['recommended_plan']['sla_met'] is False
    assert 'misses SLA' in result['recovery_explanation']


def test_batch_http_dispatch_and_unknown_city_partial_failure(session, monkeypatch):
    from backend.api import chat_api
    memory,runtime,clock,plan,ask=session
    async def get_context(owner):return deepcopy(memory)
    monkeypatch.setattr(chat_api,'get_active_planning_context',get_context)
    class NoLLM:
        llm=None
        async def process_message(self,*args,**kwargs):raise AssertionError('Batch entered single shipment extraction')
    monkeypatch.setattr(chat_api,'supervisor',NoLLM())
    prompt='Create 6,000 kg Ground shipments:\nDelhi → Bengaluru\nSurat → Bengaluru\nMumbai → Bengaluru'
    result=asyncio.run(chat_api.agent_chat(chat_api.ChatRequest(message=prompt),{'user_id':1}))
    assert 'Created: 3' in result['response'] and len(runtime.entries)==3
    assert result['actions'][-1]['data']['mode']=='MULTI_ROUTE'
    for text,count in [('Show these three routes together.',3),('Show only the second shipment.',1),('Show all three again.',3)]:
        result=asyncio.run(chat_api.agent_chat(chat_api.ChatRequest(message=text),{'user_id':1}))
        assert len(result['actions'][0]['data']['simulation_ids'])==count
    result=asyncio.run(chat_api.agent_chat(chat_api.ChatRequest(message='Create 1000 kg Ground shipments:\nDelhi → Mumbai\nMissingCity → Bengaluru'),{'user_id':1}))
    assert 'Created: 1' in result['response'] and 'Infeasible: 1' in result['response']
    result=asyncio.run(chat_api.agent_chat(chat_api.ChatRequest(message='Create:\nDelhi → Mumbai\nSurat → Bengaluru'),{'user_id':1}))
    assert 'weight' in result['response'] and not result['actions']


def test_batch_row_attributes_override_common_header(session):
    memory,runtime,clock,plan,ask=session
    result=asyncio.run(batch_answer(1, 'Plan 1000 kg Ground shipments before tomorrow at 6 PM:\nDelhi to Mumbai cheapest\nMumbai to Bengaluru 5000 kg Air fastest',memory))
    assert 'Created: 2' in result['response']
    rows=list(memory['journeys'].values())
    assert [r['weight_kg'] for r in rows]==[1000,5000]
    assert [r['objective'] for r in rows]==['cheapest','fastest']
    assert [r['allowed_modes'] for r in rows]==[['road'],['air']]
    assert all(r['deadline'] for r in rows)


def test_known_ground_regression_and_recovery(session):
    memory,runtime,clock,plan,ask=session
    result=plan('Delhi','Bengaluru',['road'],6000)
    assert result['recommended_plan']
    blocked=set(memory['route_ids'])
    result=ask('The current Ground route is unavailable. Find the fastest feasible recovery.')
    if result['actions'][0]['type']=='supply_chain_planning_operation':
        p=result['actions'][0]['data']['recommended_plan']
        assert {l['route_type'] for l in p['route_legs']}=={'road'}
        assert not blocked.intersection(l['route_id'] for l in p['route_legs'])
    else:assert 'No feasible' in result['response']


def test_legacy_segment_serialization(session):
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Chennai',['multimodal'],5000)
    sim=runtime.get(1,memory['movement_id'])
    for segment in sim.journey_segments:
        segment.pop('start_progress');segment.pop('end_progress')
    for index,segment in enumerate(sim.journey_segments):
        sim.progress=(sim._cumulative[segment['start_index']]+sim._cumulative[segment['end_index']])/2/sim._geometry_distance
        snapshot=sim.snapshot()
        assert snapshot['active_leg_index']==index and snapshot['mode']==segment['mode']
