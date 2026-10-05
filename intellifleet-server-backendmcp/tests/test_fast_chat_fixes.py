import asyncio
from copy import deepcopy
from datetime import date
import pytest
from backend.operations.planner_followups import answer
from backend.agents.supervisor import _context_from_result
from backend.operations.journey_scenarios import changes_from_message
from backend.control_tower import chat
from backend.control_tower.service import ControlTower
from backend.fedex.importer import load_schedules, workbook_path
from backend.api import chat_api
from backend.mcp.schemas.route_schemas import FetchRoutesOutput


def context():
    plans=[dict(plan_id=f'p{i}',mode=mode,operational_cost=cost,duration_hours=i+2,risk_score=.1,reliability=.95,vehicle_utilization=.8,vehicles=[{'id':i,'label':f'V{i}'}],route_legs=[{'route_id':i,'route_type':mode}]) for i,mode,cost in [(1,'road',100),(2,'air',300)]]
    return _context_from_result({'planning_request':{'source':'A','destination':'B','objective':'balanced'},'recommended_plan':plans[0],'candidate_plans':plans})


def test_saved_candidates_no_recompute_and_explanation():
    c=context();before=deepcopy(c)
    second=answer(1,'Show only the second option.',c)
    assert 'Plan p2' in second['response'] and 'Plan p1' not in second['response']
    all_options=answer(1,'Show all options again.',c)
    assert 'Plan p1' in all_options['response'] and 'Plan p2' in all_options['response']
    why=answer(1,'Why did you choose this option?',c)['response']
    assert all(k in why for k in ['cost','ETA','risk','reliability','utilization','Alternative'])
    ground=answer(1,'Compare it with Ground.',c)['response']
    assert 'already Ground' in ground and 'Plan p2' in ground
    assert c==before


def test_that_route_exclusion():
    c=context();c['route_ids']=[1]
    assert changes_from_message('What if that route becomes unavailable?',c,{'routes':[], 'vehicles':[], 'warehouses':[]})=={'blocked_route_ids':[1]}


def test_packaged_workbook_persistence_and_queries(tmp_path,monkeypatch):
    assert workbook_path().is_file()
    schedules=load_schedules()
    assert len(schedules)==38
    assert sum(s.mode=='AIR' for s in schedules)==10
    assert sum(s.source_sheet=='Surface' for s in schedules)==28
    assert all(s.lane!='UNSUPPORTED_FORMULA' for s in schedules)
    assert any(s.lane=='CJB-BLR' and '5355' in s.service for s in schedules)
    tower=ControlTower(str(tmp_path/'ct.db'))
    d=date(2030,1,1)
    first=tower.import_network(1,schedules,d)
    assert len(tower.import_network(1,schedules,d))==38
    assert len(ControlTower(tower.db_path).runs(1,d))==38
    assert all(r['data_source']=='FEDEX_SOURCE' for r in first)
    monkeypatch.setattr(chat,'ControlTower',lambda:tower)
    for prompt in ['Which Air runs are currently delayed?','Show Surface runs for Delhi.','Which critical lanes are currently at risk?']:
        result=chat.answer(1,prompt,service_date=str(d))
        assert result and 'Network status' in result['response']
    assert 'No operational runs are loaded' in chat.answer(1,'Which Air runs are currently delayed?',service_date='2031-01-01')['response']
    assert 'No CON association' in chat.answer(1,'Find CON CT-LOCAL-SYNTHETIC.')['response']
    assert 'No Control Tower run is selected' in chat.answer(1,'If the current delayed run becomes 30 minutes later, what should the operator do?',service_date=str(d))['response']
    run=first[0]
    result=chat.answer(1,'If the current delayed run becomes 30 minutes later, what should the operator do?',run['run_id'],str(d))
    assert 'Hypothetical ETA' in result['response'] and 'Operator:' in result['response']


def test_operational_dispatch_does_not_read_planner_context(monkeypatch,tmp_path):
    monkeypatch.setattr(chat,'ControlTower',lambda:ControlTower(str(tmp_path/'ct.db')))
    async def fail(*args):raise AssertionError('Planner context must not be read')
    monkeypatch.setattr(chat_api,'get_active_planning_context',fail)
    for prompt in ['Which Air runs are currently delayed?','Show Surface runs for Delhi.','If the current delayed run becomes 30 minutes later, what should the operator do?']:
        result=asyncio.run(chat_api.guarded_chat(chat_api.ChatRequest(message=prompt),{'user_id':1}))
        assert 'No operational runs' in result['response']


def test_no_route_id_is_valid():
    assert FetchRoutesOutput(answer='No routes',message='OK').route_id is None


def test_internal_errors_are_sanitized(monkeypatch):
    async def fail(*args):raise ValueError('FetchRoutesOutput route_id Input should be a valid integer')
    monkeypatch.setattr(chat_api,'get_active_planning_context',fail)
    with pytest.raises(chat_api.HTTPException) as exc:
        asyncio.run(chat_api.guarded_chat(chat_api.ChatRequest(message='Why did you choose this option?'),{'user_id':1}))
    assert exc.value.status_code==503 and 'FetchRoutesOutput' not in exc.value.detail


def test_route_unavailable_creates_deterministic_alternate(monkeypatch):
    from backend.planning.service import PlanningService
    from backend.planning.models import PlanningRequest
    from backend.operations import journey_scenarios
    from backend.config import redis
    from tests.test_contextual_disruption import NETWORK
    service=PlanningService(':memory:')
    monkeypatch.setattr(service,'load_network',lambda _:deepcopy(NETWORK))
    monkeypatch.setattr(journey_scenarios,'PlanningService',lambda:service)
    request=PlanningRequest(source='Origin Hub',destination='Destination Hub',shipment={'weight_kg':6000},allowed_modes=['road'])
    baseline=service.plan(1,request)
    c=_context_from_result(baseline)
    saved={}
    async def save(_,value):saved.update(value)
    monkeypatch.setattr(redis,'set_active_planning_context',save)
    result=asyncio.run(journey_scenarios.answer(1,'What if that route becomes unavailable?',c))
    assert 'No supported scenario' not in result['response']
    draft=saved['current_scenario']
    assert draft['changes']['blocked_route_ids']==[11]
    assert [r['route_id'] for r in draft['scenario']['recommended_plan']['route_legs']]==[21,31,41]
    assert c['selected_plan']['plan_id']==baseline['recommended_plan']['plan_id']


def test_load_api_refresh_and_scope(monkeypatch,tmp_path):
    from backend.control_tower import routes
    from backend.fedex import routes as fedex_routes
    from backend.routes.auth import get_current_user
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    tower=ControlTower(str(tmp_path/'ct.db'))
    monkeypatch.setattr(routes,'service',tower)
    fedex_routes.schedules.cache_clear()
    app=FastAPI();app.include_router(routes.router)
    app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    client=TestClient(app)
    for _ in range(2):
        response=client.post('/operations/control-tower/import',json={'service_date':'2030-01-01'})
        assert response.status_code==200 and len(response.json()['runs'])==38
    assert client.get('/operations/control-tower/summary?service_date=2030-01-01').json()['total_runs']==38
    assert client.get('/operations/control-tower/runs?service_date=2030-01-01&mode=AIR').json()['total']==10
    assert client.get('/operations/control-tower/runs?service_date=2030-01-01&mode=SURFACE').json()['total']==28


def test_graph_exception_is_not_returned():
    from types import SimpleNamespace
    from backend.agents.graph import LogisticsAgentGraph
    async def fail(*args):raise RuntimeError('private traceback schema error')
    graph=object.__new__(LogisticsAgentGraph);graph.graph=SimpleNamespace(ainvoke=fail)
    result=asyncio.run(graph.invoke(1,'Show data'))
    assert result['success'] is False and 'private' not in result['response'] and 'schema' not in result['response']
