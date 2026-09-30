"""Offline behavior regressions; real provider evidence is recorded separately."""
from datetime import datetime, timedelta
import pytest
from test_operations import loaded
from backend.operations import plan_journeys, routes
from backend.planning.service import PlanningService
from backend.planning.models import PlanningRequest
from backend.fedex.models import DisruptionInput, EligibilityInput
from backend.fedex.disruptions import inject
from backend.fedex.eligibility import evaluate


def test_four_persistent_independent_journeys(loaded, monkeypatch):
    _,runtime,clock=loaded
    import backend.fedex.telemetry as telemetry
    monkeypatch.setattr(telemetry,'runtime',runtime)
    sims=[]
    for a,b,w in [('Delhi','Bengaluru',1000),('Mumbai','Hyderabad',2000),('Kolkata','Lucknow',1500),('Ahmedabad','Jaipur',2500)]:
        plan=PlanningService().plan(1,PlanningRequest(source=a,destination=b,shipment={'weight_kg':w},allowed_modes=['road']))['recommended_plan']
        snap=plan_journeys.start(1,plan['plan_id'])
        assert plan_journeys.start(1,plan['plan_id'])['simulation_id']==snap['simulation_id']
        sim=runtime.get(1,snap['simulation_id']);sims.append(sim)
        assert sim.speed==120 and sim.current_eta==datetime.fromisoformat(plan['eta'])
        sim.control('resume',clock[0])
    assert len(runtime.entries)==len({s.id for s in sims})==4
    clock[0]+=2;runtime.tick();a,b,c,d=sims
    a.control('pause',clock[0]);before=[s.progress for s in sims]
    clock[0]+=2;runtime.tick()
    assert a.progress==before[0] and all(s.progress>p for s,p in zip(sims[1:],before[1:]))
    a.control('resume',clock[0])
    for s in [b,d]:
        before=s.snapshot();inject(s,DisruptionInput(expected_delay_minutes=30));clock[0]+=1;runtime.tick();after=s.snapshot()
        assert (before['latitude'],before['longitude'],before['progress'])==(after['latitude'],after['longitude'],after['progress'])
        assert datetime.fromisoformat(after['current_eta'])==datetime.fromisoformat(before['current_eta'])+timedelta(minutes=30)
        assert after['alerts'][-1]['previous_eta']==before['current_eta']
        assert after['alerts'][-1]['recommended_action']
        s.control('resume',clock[0]);assert s.progress==before['progress']
        clock[0]+=1;runtime.tick();assert s.progress>before['progress']
    c.control('stop',clock[0]);before=[s.progress for s in sims]
    clock[0]+=2;runtime.tick()
    assert c.progress==before[2] and all(sims[i].progress>before[i] for i in [0,1,3])
    eta=a.current_eta;a.control('speed',clock[0],600);assert a.current_eta==eta


@pytest.mark.parametrize('source,origin,gateway',[('SYNTHETIC','SYN-UDR-STN','SYN-DEL-GTW'),('FEDEX','UDRPU','DELGW')])
@pytest.mark.parametrize('ready,expected',[('09:00','AIR'),('16:00','AIR'),('16:30','AIR'),('17:00','SURFACE'),('18:00','SURFACE'),('21:00','SURFACE'),('21:30','SURFACE'),('22:00',None)])
def test_source_cutoff_matrix(source,origin,gateway,ready,expected):
    result=evaluate(routes.schedules_for(111,source),EligibilityInput(origin_station=origin,gateway=gateway,simulation_date='2026-09-30',shipment_ready_datetime=f'2026-09-30T{ready}:00+05:30'))
    assert (result['selected']['mode'] if result['selected'] else None)==expected
    assert all(c['data_source']==('FEDEX_SOURCE' if source=='FEDEX' else 'SYNTHETIC_SCHEDULE') for c in result['candidates'])
    if source=='SYNTHETIC':assert any(c['mode']=='RAIL' for c in result['candidates'])


def test_custom_schedules_remain_authoritative(monkeypatch):
    from backend.operations.data import synthetic_schedules
    custom=synthetic_schedules()
    monkeypatch.setitem(routes.custom_schedules,111,custom)
    assert routes.schedules_for(111,'SYNTHETIC') is custom
    assert all(s.data_source=='FEDEX_SOURCE' for s in routes.schedules_for(111,'FEDEX'))


def test_route_requires_explicit_positive_weight():
    from pydantic import ValidationError
    for weight in [None,0,-1,float('nan')]:
        with pytest.raises(ValidationError):routes.RouteInput(origin='Delhi',destination='Mumbai',**({} if weight is None else {'weight':weight}))


def test_compact_poll_retains_runtime_geometry(loaded):
    from backend.operations import service
    _,runtime,clock=loaded
    service.start_demo(1,10)
    full=service.movements(1)
    compact=service.movements(1,include_geometry=False)
    assert all('route' not in m for m in compact['movements'])
    assert any(len(m['route'])>2 for m in full['movements'])
    again=service.movements(1)
    assert {m['simulation_id']:m['route'] for m in full['movements']}=={m['simulation_id']:m['route'] for m in again['movements']}


def test_infeasible_warehouse_eta_is_client_readable():
    from backend.agents.supervisor import _format_planning_result
    answer=_format_planning_result({'fulfilled':False,'unfulfilled_quantity':10,'allocation':[],'ranked_alternatives':[],'eta_hours':None,'recommendation':'No feasible allocation'})
    assert 'None hours' not in answer and 'unavailable (no feasible allocation)' in answer


def test_missing_plan_coordinates_are_explicit(loaded,monkeypatch):
    import backend.fedex.telemetry as telemetry
    monkeypatch.setattr(telemetry,'runtime',loaded[1])
    plan={'plan_id':'missing-coordinates','route_legs':[{'route_type':'road','source_coords':None}],'vehicles':[{'id':1}]}
    plan_journeys.remember(1,[plan])
    with pytest.raises(ValueError,match='Valid coordinates'):plan_journeys.start(1,plan['plan_id'])


def test_large_local_fulfilment_exact_dominance(loaded,monkeypatch):
    service=PlanningService()
    def unnecessary(*args,**kwargs):
        pytest.fail('Remote base costs prove local stock cheaper; remote replanning is unnecessary')
    monkeypatch.setattr(service,'plan',unnecessary)
    result=service.fulfilment(1,'Mumbai',1500,12000,'cheapest')
    assert result['fulfilled'] and result['total_cost']==3750
    assert result['allocation'][0]['warehouse']=='Mumbai'
    assert result['allocation'][0]['allocation']==1500
    assert result['eta_hours']==0


def test_local_shortcut_does_not_skip_cheaper_remote_option(loaded,monkeypatch):
    import copy
    network=copy.deepcopy(loaded[0])
    for w in network['warehouses']:
        w['inventory']=10 if w['name'] in {'Mumbai','Pune'} else 0
        w['reserved_inventory']=0
        if w['name']=='Mumbai':w['handling_cost']=100000
    service=PlanningService();monkeypatch.setattr(service,'load_network',lambda _:network)
    result=service.fulfilment(1,'Mumbai',1,1,'cheapest')
    assert result['fulfilled'] and result['allocation'][0]['warehouse']=='Pune'
    assert result['total_cost']<100000
