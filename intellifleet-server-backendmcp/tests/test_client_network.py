"""Acceptance checks for the authoritative client topology and enrichment."""
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
import hashlib
import pytest

from backend.client_network import generate, network, summary, EnrichmentConfig, validate_topology
from backend.fedex.importer import load_schedules, workbook_path
from backend.fedex.models import EligibilityInput
from backend.fedex.eligibility import evaluate
from backend.planning.service import PlanningService
from backend.planning.models import PlanningRequest
from backend.control_tower.service import ControlTower
from backend.client_api import answer, ChatInput, contexts


@pytest.fixture
def planner(tmp_path):
    return PlanningService(str(tmp_path/'planning.db'))


@pytest.fixture
def planning_input():
    return PlanningRequest(source='CJBMB',destination='BLRGW',shipment={'weight_kg':2000},
        shipment_ready_datetime=datetime.fromisoformat('2026-10-08T17:00:00+05:30'))


def test_authoritative_workbook_digest():
    assert hashlib.sha256(workbook_path().read_bytes()).hexdigest()=='257378dbc959faea9db0811a56ab0c5907e12001a8898a321c7ccdbb58ee5208'


def test_only_workbook_topology():
    ss=load_schedules();model=network()
    assert len(ss)==38
    assert {n['name'] for n in model['warehouses']}=={c for s in ss for c in (s.origin_station,s.gateway)}
    assert {(r['route_id'],r['from_location'],r['to_location'],r['schedule']['lane'],r['schedule']['service'],r['schedule']['mode']) for r in model['routes']}=={(s.schedule_id,s.origin_station,s.gateway,s.lane,s.service,s.mode) for s in ss}
    assert len(model['warehouses'])==34


def test_old_csv_loader_disabled():
    from backend.operations.data import rows
    with pytest.raises(ValueError):rows('warehouse.csv')
    from backend.operations.routes import schedules_for
    assert {s.schedule_id for s in schedules_for(1)}=={s.schedule_id for s in load_schedules()}


def test_resource_counts_and_service_binding():
    model=network()
    for s in load_schedules():
        bound=[v for v in model['vehicles'] if v['service_id']==s.schedule_id]
        assert len(bound)==(s.vehicle_count if s.vehicle_count is not None else 1)
        assert all(v['current_location']==s.origin_station and v['client_service']==s.service for v in bound)


def test_shipments_bound_to_resources_and_source_endpoints():
    model=network();resources={v['id']:v for v in model['vehicles']};services={s.schedule_id:s for s in load_schedules()}
    for shipment in model['shipments']:
        assert resources[shipment['resource_id']]['service_id']==shipment['service_id']
        s=services[shipment['service_id']]
        assert (shipment['origin_station'],shipment['gateway'])==(s.origin_station,s.gateway)


def test_seed_is_deterministic_and_configurable():
    assert generate()==generate()
    a=generate(config=EnrichmentConfig(seed=42));b=generate(config=EnrichmentConfig(seed=43))
    assert a['vehicles']!=b['vehicles']
    assert [(r['route_id'],r['schedule']) for r in a['routes']]==[(r['route_id'],r['schedule']) for r in b['routes']]
    assert generate(config=EnrichmentConfig(enabled=False))['vehicles']==[]


@pytest.mark.parametrize('field,value',[('from_location','UNSUPPORTED'),('to_location','UNSUPPORTED'),('route_type','SEA')])
def test_unsupported_edges_rejected(field,value):
    model=deepcopy(network());model['routes'][0][field]=value
    with pytest.raises(ValueError):validate_topology(model)


def test_unsupported_station_and_flight_rejected():
    model=deepcopy(network());model['warehouses'][0]['name']='UNSUPPORTED'
    with pytest.raises(ValueError):validate_topology(model)
    model=deepcopy(network());model['routes'][0]['schedule']['service']='FAKE FLIGHT'
    with pytest.raises(ValueError):validate_topology(model)


def test_resource_cannot_switch_service():
    model=deepcopy(network());model['vehicles'][0]['service_id']=model['routes'][-1]['route_id']
    with pytest.raises(ValueError):validate_topology(model)


def test_cjb_plans_only_air_surface_and_no_invented_plan_c(planner,planning_input):
    result=planner.plan(1,planning_input)
    assert len(result['candidate_plans'])==2
    assert {p['client_service'] for p in result['candidate_plans']}=={'6E 5355','TATA 407'}
    assert {l['route_id'] for p in result['candidate_plans'] for l in p['route_legs']}=={'air-11','surface-25'}
    for p in result['candidate_plans']:
        assert all(v['service_id']==p['route_legs'][0]['route_id'] for v in p['vehicles'])


def test_capacity_shortage(planner,planning_input):
    result=planner.plan(1,planning_input.model_copy(update={'shipment':planning_input.shipment.model_copy(update={'weight_kg':6000})}))
    assert {p['client_service'] for p in result['candidate_plans']}=={'6E 5355'}


def test_schedule_eligibility_and_midnight():
    planning_input=EligibilityInput(origin_station='CJBMB',gateway='BLRGW',simulation_date=date(2026,10,8),
        shipment_ready_datetime=datetime.fromisoformat('2026-10-08T18:01:00+05:30'))
    result=evaluate(load_schedules(),planning_input)
    assert not next(c for c in result['candidates'] if c['service']=='6E 5355')['eligible']
    surface=next(c for c in result['candidates'] if c['service']=='TATA 407')
    assert surface['eligible'] and surface['eta'].day==9
    assert surface['etd'].hour==22 and surface['eta'].hour==6


def test_blocked_flight_legitimate_surface_only(planner,planning_input):
    result=planner.plan(1,planning_input,changes={'unavailable_flights':['6E 5355']})
    assert {p['client_service'] for p in result['candidate_plans']}=={'TATA 407'}


def test_single_vehicle_breakdown_does_not_create_spare(planner):
    result=planner.breakdown_recovery(1,'SUR-surface-25-01','CJBMB','BLRGW',2000)
    assert result['replacement_vehicles']==[] and result['recovery_plan'] is None
    assert 'No spare' in result['reason']


def test_multiple_vehicle_breakdown_same_service(planner):
    model=network()
    route=next(r for r in model['routes'] if r['schedule']['vehicle_count'] and r['schedule']['vehicle_count']>1 and r['status']=='active')
    resource=next(v for v in model['vehicles'] if v['service_id']==route['route_id'])
    result=planner.breakdown_recovery(1,resource['label'],route['from_location'],route['to_location'],100)
    assert result['recovery_plan']
    assert all(v['service_id']==resource['service_id'] and v['label']!=resource['label'] for v in result['replacement_vehicles'])


def test_fuel_and_delay_scenarios(planner,planning_input):
    before=planner.plan(1,planning_input)
    after=planner.plan(1,planning_input,changes={'fuel_cost_multiplier':1.2,'service_delays':{'air-11':30}})
    a=next(p for p in before['candidate_plans'] if p['service_id']=='air-11')
    b=next(p for p in after['candidate_plans'] if p['service_id']=='air-11')
    assert b['operational_cost']>a['operational_cost']
    assert (datetime.fromisoformat(b['eta'])-datetime.fromisoformat(a['eta'])).total_seconds()==1800
    assert b['source_schedule']==a['source_schedule']


def test_live_operations_uses_source_runs_with_enrichment(tmp_path):
    tower=ControlTower(str(tmp_path/'tower.db'));rows=tower.import_network(1,load_schedules(),date(2026,10,8))
    assert {r['schedule_id'] for r in rows}=={s.schedule_id for s in load_schedules()}
    for row in rows:
        assert all(v['service_id']==row['schedule_id'] for v in row['resources'])
        assert all(s['service_id']==row['schedule_id'] for s in row['simulated_shipments'])
        assert row['visualization']['geometry_source']


def test_chat_planning_disruption_and_breakdown(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);session='client-regression';owner=891
    def chat(message):return answer(owner,ChatInput(message=message,session_id=session))
    first=chat('Plan 2,000 kg from CJBMB to BLRGW.')
    assert len(first['planning_result']['candidate_plans'])==2
    assert '6E 5355' in chat('Compare Air and Surface.')['response']
    blocked=chat('What if 6E 5355 becomes unavailable?')
    assert {p['client_service'] for p in blocked['planning_result']['candidate_plans']}=={'TATA 407'}
    broken=chat('The assigned Surface vehicle breaks down.')
    assert broken['recovery']['replacement_vehicles']==[]
    assert 'simulation' in chat('What is its capacity?')['response']


def test_no_runtime_dependency_on_old_csvs():
    model=network();assert summary(model)['generated_resources']==40
    assert all(r['data_source']=='CLIENT_SOURCE' for r in model['routes'])
    assert all(v['data_source']=='SYNTHETIC_ENRICHMENT' for v in model['vehicles'])


def test_source_warnings_not_repaired():
    assert {s['schedule_id'] for s in network()['schedules'] if not s['valid']}=={'surface-11','surface-13'}


def test_connected_multihop_uses_each_supplied_service(planner):
    result=planner.plan(1,PlanningRequest(source='DELPA',destination='DELGW',shipment={'weight_kg':100},shipment_ready_datetime=datetime.fromisoformat('2026-10-08T10:00:00+05:30')))
    assert result['recommended_plan']
    assert [l['route_id'] for l in result['recommended_plan']['route_legs']]==['surface-18','surface-19']
    assert {v['service_id'] for v in result['recommended_plan']['vehicles']}=={'surface-18','surface-19'}
    invalid=planner.plan(1,PlanningRequest(source='CJBMB',destination='UNSUPPORTED',shipment={'weight_kg':100}))
    assert invalid['candidate_plans']==[]


def test_shipment_rejects_unsupported_service_and_resource(planner):
    with pytest.raises(ValueError):planner.schedule_shipment(1,{'source':'CJBMB','destination':'BLRGW','route_id':'FAKE'})
    with pytest.raises(ValueError):planner.schedule_shipment(1,{'source':'CJBMB','destination':'BLRGW','route_id':'surface-25','assigned_vehicle_labels':['FAKE']})


def test_no_unsupported_city_is_generated():
    source_cities={s.origin_city for s in load_schedules()}
    assert {n['city'] for n in network()['warehouses'] if n['city']}<=source_cities


def test_archived_topology_cannot_be_returned_by_operations_api(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.control_tower import routes
    from backend.routes.auth import get_current_user
    tower=ControlTower(str(tmp_path/'archive.db'))
    source=load_schedules()[0].model_copy(update={'gateway':'UNSUPPORTED'})
    row=tower.import_network(1,[source],date(2026,10,8))[0]
    monkeypatch.setattr(routes,'service',tower)
    app=FastAPI();app.include_router(routes.router);app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    client=TestClient(app)
    assert client.get('/operations/control-tower/runs?service_date=2026-10-08').json()['runs']==[]
    assert client.get('/operations/control-tower/runs/'+row['run_id']).status_code==410


def test_archived_topology_cannot_be_returned_by_operational_chat(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    tower=ControlTower()
    source=load_schedules()[0].model_copy(update={'gateway':'UNSUPPORTED'})
    tower.import_network(741,[source],date(2026,10,8))
    result=answer(741,ChatInput(message='Show operational runs',workspace='LIVE OPERATIONS',operational_service_date='2026-10-08'))
    assert 'Reimport' in result['response']
    assert 'UNSUPPORTED' not in result['response']
