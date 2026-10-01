"""API boundary tests using the loaded network and real deterministic services."""
import asyncio
from copy import deepcopy
import pytest
from test_operations import loaded
from test_journey_lifecycle import session
from backend.api import chat_api
from backend.operations.journey_selection import current_journeys


@pytest.fixture
def chat(session,monkeypatch):
    memory,runtime,clock,plan,ask=session
    async def context(_):return deepcopy(memory)
    monkeypatch.setattr(chat_api,'get_active_planning_context',context)
    class NoLLM:
        llm=None
        async def process_message(self,*args,**kwargs):raise AssertionError('Deterministic query reached LLM')
    monkeypatch.setattr(chat_api,'supervisor',NoLLM())
    def send(message):
        return asyncio.run(chat_api.agent_chat(chat_api.ChatRequest(message=message,selected_simulation_id=memory.get('movement_id')),{'user_id':1}))
    return memory,runtime,clock,plan,send


def test_current_and_specific_ids_read_only(chat):
    memory,runtime,clock,plan,send=chat
    result=plan('Delhi','Chennai',['multimodal'],5000)
    before=deepcopy(memory);keys=set(runtime.entries)
    for prompt,ids in [('Show route IDs for the current shipment.',[l['route_id'] for l in memory['route_legs']]),
                       ('Show me the route IDs used in the current shipment and tell me which route ID belongs to each leg.',[l['route_id'] for l in memory['route_legs']]),
                       ('Show vehicle IDs assigned to the current shipment, capacity, assigned load and utilization.',[v['id'] for v in memory['assigned_vehicles']])]:
        answer=send(prompt)
        assert not answer['actions'] and all(str(i) in answer['response'] for i in ids),answer
    for leg in memory['route_legs']:
        answer=send(f"What is route {leg['route_id']}?")
        assert leg['from_location'] in answer['response'] and str(leg['route_id']) in answer['response']
    for v in memory['assigned_vehicles']:
        answer=send(f"Show details for {v['label']}.")
        assert v['label'] in answer['response'] and str(v['capacity']) in answer['response']
    assert memory==before and set(runtime.entries)==keys


def test_warehouse_analytics(chat):
    from backend.planning.service import PlanningService
    memory,runtime,clock,plan,send=chat
    network=PlanningService().load_network(1);active=[w for w in network['warehouses'] if w['is_active']]
    result=send('How many warehouses are currently active? Show names, cities, status and available capacity.')
    assert f'warehouses: {len(active)}' in result['response'] and not result['actions']
    capacity=PlanningService().warehouse_capacity(1)['warehouses'];ordered=sorted(capacity,key=lambda w:w['available_storage'])
    text=send('Which warehouses have highest and lowest available capacity?')['response']
    assert ordered[-1]['warehouse'] in text and ordered[0]['warehouse'] in text
    assert len([l for l in text.splitlines() if l.startswith('- ')])==2
    assert len([l for l in send('Top 5 warehouses by available storage')['response'].splitlines() if l.startswith('- ')])==5
    located=send('Show all active warehouses and where they are located.')['response']
    assert 'coordinates' in located and 'current inventory' not in located
    name=active[0].get('city') or active[0]['name']
    assert name in send(f'Show warehouses in {name}.')['response']


def test_draft_compare_discard_apply_keeps_journey(chat):
    memory,runtime,clock,plan,send=chat
    plan('Delhi','Bengaluru');identity=memory['journey_id'];movement=memory['movement_id'];baseline=deepcopy(memory['selected_plan'])
    message='Create a what-if scenario for the current shipment where fuel cost increases by 20%. Do not apply it yet.'
    draft=send(message)
    assert 'Draft scenario' in draft['response'] and not draft['actions'],draft
    assert memory['selected_plan']==baseline and len(runtime.entries)==1
    assert memory['current_scenario']['changes']['fuel_cost_multiplier']==1.2
    assert 'delta' in send('Compare this draft scenario with the current baseline plan.')['response']
    assert 'discarded' in send('Discard this draft scenario.')['response']
    assert memory['selected_plan']==baseline and 'current_scenario' not in memory
    send(message)
    applied=send('Apply this draft scenario.')
    assert applied['actions'][0]['data']['recommended_plan']
    assert memory['journey_id']==identity and memory['movement_id']==movement and len(runtime.entries)==1
    assert memory['planning_changes']['fuel_cost_multiplier']==1.2
    assert memory['selected_plan']['operational_cost']>baseline['operational_cost']


def test_display_three_one_three_and_revision_histories(chat):
    memory,runtime,clock,plan,send=chat
    lanes=[('Delhi','Bengaluru'),('Surat','Bengaluru'),('Mumbai','Bengaluru')]
    for a,b in lanes:plan(a,b)
    # Repeated snapshots of a logical journey are not independent shipments.
    first=next(iter(memory['journeys'].values()))
    old=deepcopy(first);old['selected_plan']['revision']=0;old.pop('journey_id')
    memory['journeys']['legacy-copy']=old
    assert len(current_journeys(memory))==3
    message='Show the Delhi to Bengaluru, Surat to Bengaluru, and Mumbai to Bengaluru shipments together on the same map.'
    multi=send(message);assert len(multi['actions'][0]['data']['movements'])==3,multi
    one=send('Now show only the Delhi to Bengaluru shipment on the map.')
    assert len(one['actions'][0]['data']['movements'])==1,one
    again=send('Show all three again.');assert len(again['actions'][0]['data']['movements'])==3,again
    before=deepcopy(memory)
    compare=send('Compare all three by cost, ETA, risk, reliability and utilization.')
    assert not compare['actions'] and compare['response'].count('utilization')==3
    assert memory==before


def test_independent_same_lane_not_deduped(chat):
    memory,runtime,clock,plan,send=chat
    plan('Delhi','Bengaluru',weight=6000);plan('Delhi','Bengaluru',weight=3000);plan('Mumbai','Bengaluru')
    assert len(current_journeys(memory))==3
    answer=send('Show Delhi to Bengaluru and Mumbai to Bengaluru together on the map.')
    assert not answer['actions'] and 'journey IDs' in answer['response']


def test_operational_summary_and_disruption_impact_read_only(chat):
    memory,runtime,clock,plan,send=chat
    plan('Delhi','Bengaluru');send('The current route is unavailable. Use another route.')
    before=deepcopy(memory)
    impact=send('What is the operational impact of this disruption and what mitigation do you recommend?')
    assert 'Previous route:' in impact['response'] and 'Cost before' in impact['response'] and not impact['actions']
    assert memory==before
    plan('Mumbai','Bengaluru')
    before=deepcopy(memory)
    summary=send('Summarize the current active shipments, routes, assigned vehicles, major disruptions and SLA risks. Do not modify any plan.')
    assert 'active=2' in summary['response'] and not summary['actions'],summary
    assert memory==before


@pytest.mark.parametrize('objective',['fastest','cheapest','lowest-risk','balanced'])
def test_multimodal_sequence_loads_and_objectives(chat,objective):
    from backend.planning.models import PlanningRequest
    from backend.planning.service import PlanningService
    memory,runtime,clock,plan,send=chat
    plan('Delhi','Chennai',['multimodal'],5000)
    memory['planning_request']['required_mode_sequence']=['road','air','road']
    result=send(f'Make this same multimodal shipment {objective} while keeping Ground → Air → Ground mandatory.')
    p=result['actions'][0]['data']['recommended_plan']
    import itertools
    assert [k for k,g in itertools.groupby(l['route_type'] for l in p['route_legs'])]==['road','air','road']
    for segment in p['leg_assignments']:
        assert sum(v['assigned_load_kg'] for v in segment['vehicles'])==5000
        assert all(0<=v['assigned_load_kg']<=v['capacity'] for v in segment['vehicles'])
    assert len(runtime.entries)==1


def test_air_disruption_and_diversion_no_fabrication(chat):
    from backend.planning.service import PlanningService
    memory,runtime,clock,plan,send=chat
    plan('Mumbai','Bengaluru',['air'],5000);blocked=set(memory['route_ids'])
    result=send('The current Air route is unavailable. Find another feasible Air-only option.')
    assert blocked.issubset(memory['planning_changes']['blocked_route_ids'])
    if result['actions'][0]['type']=='supply_chain_planning_operation':
        p=result['actions'][0]['data']['recommended_plan']
        assert all(l['route_type']=='air' and l['route_id'] not in blocked for l in p['route_legs'])
    else:assert 'No feasible' in result['response']
    plan('Mumbai','Bengaluru',['air'],5000)
    result=send('The destination airport is closed and the aircraft cannot land there. Find the best feasible alternative airport then Ground to destination.')
    network=PlanningService().load_network(1)
    if result['actions']:
        p=result['actions'][0]['data']['recommended_plan'];ids={r['route_id'] for r in network['routes']}
        assert all(l['route_id'] in ids for l in p['route_legs'])
        assert p['route_legs'][-1]['route_type']=='road'
        assert 'additional cost' in result['response'] and 'additional duration' in result['response']
    else:assert 'No verified alternate' in result['response']


@pytest.mark.parametrize('message,objective',[
    ('Make this shipment lowest cost.','cheapest'),('Make it quickest.','fastest'),
    ('Make it safest.','lowest-risk'),('Make it least risk.','lowest-risk'),
    ('Make it cost-efficient considering both cost and time.','balanced'),
    ('Make it best overall.','balanced'),
])
def test_objective_paraphrases(chat,message,objective):
    memory,runtime,clock,plan,send=chat
    plan('Delhi','Bengaluru');result=send(message)
    assert result['actions'][0]['data']['planning_request']['objective']==objective
    assert len(runtime.entries)==1


@pytest.mark.parametrize('phrase',['road first, then Air, then road','Ground → Air → Ground','use truck, aircraft, then truck'])
def test_ordered_mode_intent(phrase):
    from backend.agents.supervisor import _enforce_message_mode_constraints
    normalized=_enforce_message_mode_constraints(phrase,{'allowed_modes':['air']})
    assert normalized['allowed_modes']==['multimodal']
    assert normalized['required_mode_sequence']==['road','air','road']


def test_readonly_alternatives_and_status_never_mutate(chat):
    memory,runtime,clock,plan,send=chat
    plan('Delhi','Bengaluru');before=deepcopy(memory);entry=runtime.get(1,memory['movement_id'])
    old=deepcopy(entry.snapshot())
    for prompt in ['Compare Ground and Air for the current shipment.','Show the cheapest alternative options for this shipment.','What is the current shipment status?']:
        result=send(prompt);assert not result['actions'],result
        assert memory==before
        after=runtime.get(1,memory['movement_id']).snapshot()
        assert {k:v for k,v in after.items() if k!='sequence'}=={k:v for k,v in old.items() if k!='sequence'}


def test_documented_acceptance_28_steps(chat):
    """Plan creation uses typed planner input; all follow-ups use the real chat API.

    LLM extraction and external road geometry are isolated by the shared fixtures.
    """
    import json
    from pathlib import Path
    from backend.planning.models import PlanningRequest
    from backend.planning.service import PlanningService
    from backend.planning.lifecycle import record
    from backend.agents.supervisor import _context_from_result
    memory,runtime,clock,plan,send=chat
    rows=[]
    def note(step,prompt,result):
        rows.append({'step':step,'prompt':prompt,'response':result.get('response',result.get('reason','')),
                     'actions':[a['type'] for a in result.get('actions',[])],'active_movements':len(runtime.entries)})
        return result
    def query(step,prompt):return note(step,prompt,send(prompt))
    note(1,'Plan 6000 kg Ground Delhi to Bengaluru; show route IDs.',plan('Delhi','Bengaluru'))
    query(2,'The current Ground route is unavailable. Replan this same shipment using another feasible Ground route.')
    query(3,'What is the operational impact of this disruption and what mitigation do you recommend?')
    for step,objective in [(4,'cheapest'),(5,'fastest'),(6,'lowest-risk')]:
        query(step,f'Make this shipment the {objective} feasible Ground plan.')
        assert len(runtime.entries)==1
    note(7,'Plan 5000 kg Air Mumbai to Bengaluru; show IDs.',plan('Mumbai','Bengaluru',['air'],5000))
    query(8,'The current Air route is unavailable. Find another feasible Air-only option.')
    note(9,'Plan 5000 kg Delhi to Chennai Ground Air Ground.',plan('Delhi','Chennai',['multimodal'],5000))
    memory['planning_request']['required_mode_sequence']=['road','air','road']
    query(10,'Make this same shipment fastest while keeping Ground → Air → Ground mandatory.')
    query(11,'Make this same shipment cheapest while keeping Ground → Air → Ground mandatory.')
    query(12,'Show route IDs for the current shipment.')
    query(13,'Show vehicle IDs for the current shipment.')
    query(14,f"Show details for route ID {memory['route_ids'][0]}.")
    query(15,f"Show details for {memory['assigned_vehicles'][0]['label']}.")
    query(16,'How many warehouses are active? Show names, cities, status and available capacity.')
    query(17,'Which warehouse has the highest available capacity and which has the lowest?')
    for source in ('Delhi','Surat','Mumbai'):plan(source,'Bengaluru')
    note(18,'Plan three independent shipments: Delhi, Surat and Mumbai to Bengaluru.',{'response':'Created three logical journeys.'})
    multi=query(19,'Show those three routes together.');assert len(multi['actions'][0]['data']['movements'])==3
    single=query(20,'Show only the Delhi to Bengaluru shipment on the map.');assert len(single['actions'][0]['data']['movements'])==1
    multi=query(21,'Show all three again.');assert len(multi['actions'][0]['data']['movements'])==3
    compare=query(22,'Compare all three by cost, ETA, risk, reliability and utilization.');assert not compare['actions']
    query(23,'Create a draft what-if scenario with fuel cost +20%.')
    query(24,'Compare this draft scenario with the current baseline plan.')
    query(25,'Discard this draft scenario.')
    send('Create a draft what-if scenario with fuel cost +20%.')
    query(26,'Apply this draft scenario.')
    request=PlanningRequest(source='Delhi',destination='Bengaluru',shipment={'weight_kg':5000},allowed_modes=['road'],deadline='tomorrow at 6 PM')
    assert request.deadline.hour==18 and request.deadline.utcoffset().total_seconds()==19800
    result=PlanningService().plan(1,request)
    updated=record(1,result,memory,_context_from_result(result,memory),revise=False)
    memory.clear();memory.update(deepcopy(updated));note(27,'Plan Ground shipment with tomorrow 6 PM SLA.',result)
    query(28,'Summarize all current active shipments and operational risks. Do not modify any plan.')
    assert len(rows)==28
    Path('/private/tmp/unifleet-acceptance-28.json').write_text(json.dumps(rows,indent=2))


@pytest.mark.parametrize('kind',['fuel','risk','weight','deadline','route','vehicle','warehouse','mode'])
def test_supported_scenario_changes_are_drafts(chat,kind):
    memory,runtime,clock,plan,send=chat
    plan('Delhi','Bengaluru');baseline=deepcopy(memory['selected_plan'])
    snippets={'fuel':'fuel increases by 20%','risk':'risk increases by 10%',
              'weight':'shipment weight becomes 4000 kg','deadline':'deadline 2 hours earlier',
              'route':f"route ID {memory['route_ids'][0]} is blocked",
              'vehicle':f"vehicle {memory['assigned_vehicles'][0]['label']} is unavailable",
              'warehouse':f"warehouse {memory['source']} is unavailable",'mode':'allow Air only'}
    result=send('Create a draft scenario where '+snippets[kind]+'. Do not apply it yet.')
    assert not result['actions'] and memory.get('current_scenario'),result
    assert memory['selected_plan']==baseline and len(runtime.entries)==1
    key={'fuel':'fuel_cost_multiplier','risk':'risk_delta','weight':'demand_weight_kg','deadline':'deadline','route':'blocked_route_ids','vehicle':'unavailable_vehicles','warehouse':'unavailable_warehouses','mode':'allowed_modes'}[kind]
    assert key in memory['current_scenario']['changes']


def test_aliases_survive_revision_and_ids_remain_real(chat,monkeypatch):
    from backend.planning.service import PlanningService
    from backend.planning.models import PlanningRequest
    from backend.planning.lifecycle import record
    from backend.agents.supervisor import _context_from_result
    memory,runtime,clock,plan,send=chat
    service=PlanningService();network=service.load_network(1)
    mapping={w['name']:'Loaded Hub '+w['name'] for w in network['warehouses']}
    for w in network['warehouses']:w['name']=mapping[w['name']]
    for r in network['routes']:
        r['from_location']=mapping[r['from_location']];r['to_location']=mapping[r['to_location']]
    for v in network['vehicles']:v['current_location']=mapping[v['current_location']]
    monkeypatch.setattr(PlanningService,'load_network',lambda self,owner:deepcopy(network))
    # Pick a real feasible edge from the renamed data, not a specific city.
    edge=next(r for r in network['routes'] if r['route_type']=='road')
    names={w['name']:w['city'] for w in network['warehouses']}
    a,b=names[edge['from_location']],names[edge['to_location']]
    result=service.plan(1,PlanningRequest(source=a,destination=b,shipment={'weight_kg':1},allowed_modes=['road']))
    updated=record(1,result,{},_context_from_result(result),revise=False);memory.update(updated)
    send('Make this shipment cheapest.')
    assert memory['requested_source']==a and memory['requested_destination']==b
    answer=send(f'Show only the {a} to {b} route on the map.')
    assert len(answer['actions'][0]['data']['movements'])==1


@pytest.mark.parametrize('message',['The current Air leg is cancelled.','The current flight is unavailable.','Cannot use this route.'])
def test_air_disruption_paraphrases(chat,message):
    memory,runtime,clock,plan,send=chat
    plan('Mumbai','Bengaluru',['air'],5000)
    ids=set(memory['route_ids'])
    result=send(message)
    assert ids.issubset(memory['planning_changes']['blocked_route_ids'])
    assert len(runtime.entries)==1
    if result['actions'][0]['type']=='supply_chain_planning_operation':
        assert not ids.intersection(l['route_id'] for l in result['actions'][0]['data']['recommended_plan']['route_legs'])
    else:assert 'No feasible' in result['response']
