import copy
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import math
import requests
import pytest
from backend.operations.road_routing_engine import RoadRoutingEngine, RoadRoutingError, point_along_route
from backend.fedex.simulator import Simulation
from backend.fedex.models import SimulationInput, DisruptionInput
from backend.fedex.disruptions import inject
from test_fedex_eligibility import schedules
from test_operations import loaded


def payload():
    return {'code':'Ok','routes':[{'distance':1500,'duration':180,'geometry':{'coordinates':[
        [77,28],[77.003,28.002],[77.005,28.008],[77.01,28.01]]},
        'legs':[{'steps':[{'mode':'driving'}]}]}],
        'waypoints':[{'location':[77,28]},{'location':[77.01,28.01]}]}


@pytest.fixture
def provider(tmp_path,monkeypatch):
    calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return payload()
    def get(*args,**kwargs):calls.append((args,kwargs));return Response()
    monkeypatch.setattr(requests,'get',get)
    return RoadRoutingEngine(cache_dir=tmp_path,min_interval=0,retries=1),calls


def test_real_provider_contract_snaps_geometry_metrics_and_memory_cache(provider):
    engine,calls=provider
    route=engine.get_route(28,77,28.01,77.01)
    assert len(route.geometry)==4 and route.distance_km==1.5 and route.duration_minutes==3
    assert route.geometry[0]==(route.snapped_origin.lat,route.snapped_origin.lon)
    assert route.geometry[-1]==(route.snapped_destination.lat,route.snapped_destination.lon)
    assert engine.get_route(28,77,28.01,77.01) is route and len(calls)==1
    assert calls[0][1]['params']['overview']=='full' and calls[0][1]['params']['steps']=='true'
    assert '/77,28;77.01,28.01' in calls[0][0][0]


def test_disk_cache_single_flight_and_provider_key(provider,tmp_path):
    engine,calls=provider
    with ThreadPoolExecutor(max_workers=8) as pool:
        routes=list(pool.map(lambda _:engine.get_route(28,77,28.01,77.01),range(20)))
    assert len(calls)==1 and len({r.route_id for r in routes})==1
    second=RoadRoutingEngine(base_url=engine.base_url,cache_dir=tmp_path,min_interval=0)
    assert second.get_route(28,77,28.01,77.01).geometry==routes[0].geometry
    assert len(calls)==1
    third=RoadRoutingEngine(base_url='https://different.example',cache_dir=tmp_path,min_interval=0)
    third.get_route(28,77,28.01,77.01)
    assert len(calls)==2


@pytest.mark.parametrize('options',[{'optimization':'SHORTEST'},{'optimization':'CHEAPEST'},{'avoid':('blocked-edge',)},{'profile':'rail'}])
def test_unsupported_objectives_and_avoidance_are_honest(provider,options):
    engine,calls=provider
    with pytest.raises(RoadRoutingError,match='UNSUPPORTED'):
        engine.get_route(28,77,28.01,77.01,**options)
    assert not calls


def test_timeout_retries_then_fails_safely_without_cached_fallback(provider,monkeypatch):
    engine,_=provider; calls=[]
    def fail(*a,**k):calls.append(1);raise requests.Timeout('internal secret endpoint')
    monkeypatch.setattr(requests,'get',fail)
    with pytest.raises(RoadRoutingError,match='ROAD_ROUTE_UNAVAILABLE') as error:
        engine.get_route(28,77,28.01,77.01)
    assert len(calls)==2 and 'secret' not in str(error.value)
    assert not list(engine.cache_dir.glob('*.json'))


@pytest.mark.parametrize('mutation',['empty','nonfinite','snap_missing','snap_far','snap_nonfinite','zero_duration','ferry','no_route'])
def test_bad_provider_responses_never_become_straight_fallback(provider,mutation,monkeypatch):
    engine,_=provider;p=payload()
    if mutation=='empty':p['routes'][0]['geometry']['coordinates']=[]
    if mutation=='nonfinite':p['routes'][0]['geometry']['coordinates'][1][0]=float('nan')
    if mutation=='snap_missing':p['waypoints']=[]
    if mutation=='snap_far':p['waypoints'][0]['location']=[80,30]
    if mutation=='snap_nonfinite':p['waypoints'][0]['location']=[float('nan'),28]
    if mutation=='zero_duration':p['routes'][0]['duration']=0
    if mutation=='ferry':p['routes'][0]['legs'][0]['steps'][0]['mode']='ferry'
    if mutation=='no_route':p['code']='NoRoute'
    class Response:
        def raise_for_status(self):pass
        def json(self):return p
    monkeypatch.setattr(requests,'get',lambda *a,**k:Response())
    with pytest.raises(RoadRoutingError,match='ROAD_ROUTE_UNAVAILABLE'):engine.get_route(28,77,28.01,77.01)


def make(schedules):
    return Simulation(SimulationInput(origin_station='UDRPU',gateway='DELGW',simulation_date=date(2026,9,29),
        shipment_ready_datetime=datetime(2026,9,29,18),speed=600),schedules,0)


def test_surface_follows_geometry_monotonically_and_arrives(schedules):
    s=make(schedules);previous=0
    assert len(s.route)>2 and s.route==s.road_route.geometry
    for tick in (0,25,40,70,108):
        state=s.advance(tick)
        expected=point_along_route(s.route,s.progress)
        assert (state['latitude'],state['longitude'])==pytest.approx(expected,abs=1e-9)
        assert state['progress']>=previous
        assert math.isfinite(state['heading']) and state['route_distance_km']>0
        previous=state['progress']
    assert s.progress==1 and s.snapshot()['status']=='ARRIVED_AT_GTW'
    assert (state['latitude'],state['longitude'])==s.route[-1]
    assert state['distance_remaining_km']==0


@pytest.mark.parametrize('kind',['DELAY','BREAKDOWN','UNEXPECTED_STOP'])
def test_delay_and_breakdown_freeze_exact_road_position_then_resume(schedules,kind):
    s=make(schedules);before=s.advance(40);eta=s.current_eta
    inject(s,DisruptionInput(event_type=kind,expected_delay_minutes=30))
    stopped=s.advance(42)
    for field in ('latitude','longitude','progress','distance_travelled_km'):assert stopped[field]==before[field]
    assert stopped['speed_kmph']==0 and s.current_eta==eta+timedelta(minutes=30)
    assert s.advance(44)['progress']>before['progress']
    assert s.advance(111)['progress']==1


def test_pause_stop_and_slowdown_remain_on_route(schedules):
    s=make(schedules);before=s.control('pause',40)
    assert s.advance(100)['latitude']==before['latitude']
    s.control('resume',100);assert s.advance(101)['progress']>before['progress']
    old=s.progress;eta=s.current_eta;inject(s,DisruptionInput(event_type='SLOWDOWN',expected_delay_minutes=30))
    assert s.advance(102)['progress']>old and s.current_eta==eta+timedelta(minutes=30)
    stopped=s.control('stop',102)
    assert s.advance(999)['latitude']==stopped['latitude']


@pytest.mark.parametrize('mode',['AIR','RAIL'])
def test_air_rail_never_call_road_provider(schedules,monkeypatch,mode):
    from backend.fedex import simulator
    monkeypatch.setattr(simulator.road_routing_engine,'get_route',lambda *a,**k:pytest.fail('Non-road routed over roads'))
    ss=[s.model_copy(update={'mode':mode}) for s in schedules if s.mode=='SURFACE']
    s=make(ss);state=s.advance(40)
    assert len(s.route)==2 and s.road_route is None and state['road_routing_status']=='NOT_APPLICABLE'


def test_no_routing_calls_or_distance_rebuild_during_ticks(schedules,monkeypatch):
    from backend.fedex import simulator
    s=make(schedules)
    monkeypatch.setattr(simulator.road_routing_engine,'get_route',lambda *a,**k:pytest.fail('Routing on tick'))
    monkeypatch.setattr(simulator,'distance_km',lambda *a:pytest.fail('Geometry rebuild on tick'))
    for i in range(120):s.advance(i)


def test_provider_failure_preserves_runtime_and_api_is_actionable(schedules,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.fedex import routes,simulator
    from backend.fedex.telemetry import Runtime
    from backend.routes.auth import get_current_user
    runtime=Runtime();monkeypatch.setattr(routes,'runtime',runtime);monkeypatch.setattr(routes,'schedules',lambda:schedules)
    def fail(*a,**k):raise RoadRoutingError()
    monkeypatch.setattr(simulator.road_routing_engine,'get_route',fail)
    app=FastAPI();app.include_router(routes.router);app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    response=TestClient(app).post('/fedex/simulations',json={'origin_station':'UDRPU','gateway':'DELGW','simulation_date':'2026-09-29','shipment_ready_datetime':'2026-09-29T18:00:00+05:30'})
    assert response.status_code==503 and 'ROAD_ROUTE_UNAVAILABLE' in response.json()['detail']
    assert not runtime.entries


def test_cold_batch_clock_and_grounded_road_answer(loaded,monkeypatch):
    from backend.operations import service
    from backend.operations.chat import answer
    from backend.fedex import simulator
    _,runtime,clock=loaded
    route=simulator.road_routing_engine.get_route
    def slow_route(*args,**kwargs):
        clock[0]+=100
        return route(*args,**kwargs)
    monkeypatch.setattr(simulator.road_routing_engine,'get_route',slow_route)
    result=service.start_demo(1,100)
    live=[m for m in result['movements'] if m['status']!='SCHEDULE_TEMPLATE']
    assert len(live)==100 and all(.04<m['progress']<.66 for m in live)
    selected=next(m for m in live if m['mode']=='SURFACE')
    response=answer(1,'Compare fastest road and cheapest route for this truck',selected['simulation_id'])['response']
    assert selected['shipment_id'] in response and 'Only FASTEST' in response
    assert 'toll costs' in response and 'No reroute or cost change was applied' in response
    assert response.count('Current shipment:')==1
