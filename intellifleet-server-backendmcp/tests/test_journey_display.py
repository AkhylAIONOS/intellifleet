from copy import deepcopy
import pytest
from test_journey_lifecycle import session
from test_operations import loaded
from backend.operations.journey_display import answer, display_intent


@pytest.mark.parametrize('message', [
    'Show multiple routes for comparison: Delhi to Bengaluru and Gujarat to Bengaluru.',
    'Compare Delhi to Bengaluru and Gujarat to Bengaluru on the map.',
    'Show both routes together.', 'Display these routes simultaneously.',
    'Keep both routes visible.', 'Let me see these journeys side by side.',
    'Put these paths on the map at the same time.', 'Visualize all my routes.',
    'Overlay both shipments.', 'Show two routes.', 'Display these routes concurrently.',
    'Keep both visible.', 'Show them together.',
])
def test_explicit_multi_language(message):
    assert display_intent(message)=='MULTI_ROUTE'


@pytest.mark.parametrize('message', [
    'Plan Delhi to Bengaluru.', 'Make it cheapest.', 'Make it fastest.',
    'Delay this shipment by 30 minutes.', 'Road blocked; replan this shipment.',
    'Change the truck.', 'The assigned truck has broken down.',
    'Change destination to Mumbai.', 'Change warehouse.',
    'Compare cheapest and fastest options.', 'Compare Ground and Air.',
    'Compare both Ground and Air.',
    'Show current shipment status.',
])
def test_normal_requests_do_not_enable_multi(message):
    assert display_intent(message) is None


@pytest.mark.parametrize('message', ['Show only the current route.', 'Display just this shipment.', 'Show routes one at a time.', "Don't show both routes together."])
def test_explicit_single_language(message):
    assert display_intent(message)=='SINGLE_ROUTE'


def test_display_does_not_plan_or_create_movements(session, monkeypatch):
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Bengaluru');first=memory['movement_id']
    plan('Mumbai','Bengaluru');second=memory['movement_id']
    before=deepcopy(memory);identities=set(runtime.entries)
    from backend.planning.service import PlanningService
    def no_planning(*args,**kwargs):raise AssertionError('Display must not calculate a plan')
    monkeypatch.setattr(PlanningService,'plan',no_planning)
    result=answer(1,'Compare Delhi to Bengaluru and Mumbai to Bengaluru on the map.',memory)
    data=result['actions'][0]['data']
    assert data['mode']=='MULTI_ROUTE' and set(data['simulation_ids'])=={first,second}
    assert set(runtime.entries)==identities and memory==before
    single=answer(1,'Show only the current route.',memory,first)
    assert single['actions'][0]['data']['simulation_ids']==[first]
    assert set(runtime.entries)==identities


def test_missing_or_ambiguous_routes_do_not_invent_shipments(session):
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Bengaluru')
    result=answer(1,'Show multiple routes for comparison: Delhi to Bengaluru and Gujarat to Bengaluru.',memory)
    assert not result['actions'] and 'Plan those shipments first' in result['response']
    assert len(runtime.entries)==1
    plan('Delhi','Bengaluru');plan('Mumbai','Bengaluru')
    result=answer(1,'Compare Delhi to Bengaluru and Mumbai to Bengaluru on the map.',memory)
    assert not result['actions'] and 'journey IDs' in result['response']
    result=answer(1,'Show both routes together.',memory)
    assert not result['actions'] and 'Which two' in result['response']


def test_display_dispatch_precedes_supervisor(session, monkeypatch):
    import asyncio
    from backend.api import chat_api
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Bengaluru');plan('Mumbai','Bengaluru')
    async def context(_):return deepcopy(memory)
    monkeypatch.setattr(chat_api,'get_active_planning_context',context)
    class NoPlanning:
        llm=None
        async def process_message(self,*args,**kwargs):raise AssertionError('Display reached planner')
    monkeypatch.setattr(chat_api,'supervisor',NoPlanning())
    result=asyncio.run(chat_api.agent_chat(chat_api.ChatRequest(message='Show both routes together.'),{'user_id':1}))
    assert result['actions'][0]['type']=='set_journey_display'
    assert len(runtime.entries)==2


def test_comparison_member_revision_keeps_two_backend_movements(session):
    memory,runtime,clock,plan,ask=session
    plan('Delhi','Bengaluru');first=memory['movement_id']
    plan('Mumbai','Bengaluru');second=memory['movement_id']
    result=answer(1,'Show both routes together.',memory)
    assert len(result['actions'][0]['data']['movements'])==2
    before=deepcopy(runtime.get(1,second).snapshot())
    revision=ask('Make this same Delhi to Bengaluru shipment the cheapest feasible Ground plan.')
    assert revision['actions'] and len(runtime.entries)==2
    assert memory['movement_id']==first
    after=runtime.get(1,second).snapshot()
    assert {k:v for k,v in after.items() if k!='sequence'}=={k:v for k,v in before.items() if k!='sequence'}
    result=answer(1,'Keep both routes visible.',memory)
    assert set(result['actions'][0]['data']['simulation_ids'])=={first,second}


def test_display_intent_does_not_consume_air_recovery_request():
    from backend.operations.journey_display import display_intent

    message = (
        "The current Air route is unavailable. "
        "Keep this shipment Air-only and do not use Ground. "
        "Find another feasible Air recovery if one exists. "
        "Show the result and explain why if no Air-only recovery is feasible."
    )

    assert display_intent(message) is None
