from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_operations import loaded
from backend.operations import fleet, service, routes, plan_journeys
from backend.planning.service import PlanningService
from backend.planning.models import PlanningRequest
from backend.routes.auth import get_current_user
from backend.fedex.models import DisruptionInput
from backend.fedex.disruptions import inject


def active(result):
    return [m for m in result['movements'] if m['status'] != 'SCHEDULE_TEMPLATE' and not m.get('stopped')]


def test_loaded_fleet_population_and_reuse(loaded):
    network, runtime, clock = loaded
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _: fleet.initialize(1), range(2)))
    live=active(results[0]); ids={m['simulation_id'] for m in live}
    assert ids == {m['simulation_id'] for m in active(results[1])}
    assert len(live) > 10
    assert len(live) == len({m['network_vehicle_ids'][0] for m in live})
    vehicles={v['id']:v for v in network['vehicles']}; edges={r['route_id']:r for r in network['routes']}
    for m in live:
        vehicle=vehicles[m['network_vehicle_ids'][0]]; edge=edges[m['network_route_ids'][0]]
        assert vehicle['current_location'].upper() == m['origin_station']
        assert edge['from_location'] == vehicle['current_location']
        assert edge['to_location'].upper() == m['gateway']
        assert m['data_source'] == vehicle['data_source']
        assert len(m['route']) > (2 if m['mode']=='SURFACE' else 1)
        assert m['progress'] == 0 and m['simulation_speed'] == 120
    clock[0] += 1; runtime.tick()
    for _ in range(3): assert ids == {m['simulation_id'] for m in active(fleet.initialize(1))}
    target=runtime.get(1,live[0]['simulation_id']); target.control('stop',clock[0]);fleet.initialize(1)
    assert target.stopped and len(runtime.entries)==len(live)
    assert not active(service.movements(2))
    print('LOADED FLEET COUNTS', {mode:sum(m['mode']==mode for m in live) for mode in ('SURFACE','AIR','RAIL')}, 'ALL',len(live))


def test_four_sequential_ground_plans_and_controls(loaded, monkeypatch):
    import backend.fedex.telemetry as telemetry
    network,runtime,clock=loaded; monkeypatch.setattr(telemetry,'runtime',runtime)
    sims=[]
    for origin,destination in [('Delhi','Bengaluru'),('Mumbai','Bengaluru'),('Mumbai','Chennai'),('Kolkata','Delhi')]:
        result=PlanningService().plan(1,PlanningRequest(source=origin,destination=destination,shipment={'weight_kg':6000},allowed_modes=['road']))
        plan=result['recommended_plan']; assert plan, (origin,destination,result['reason'])
        assert all(k in plan for k in ('route_legs','vehicles','operational_cost','eta','risk_score','reliability'))
        m=plan_journeys.start(1,plan['plan_id']); sim=runtime.get(1,m['simulation_id']);sim.control('resume',clock[0]);sims.append(sim)
        assert len(active(service.movements(1)))==len(sims)
    assert len({s.id for s in sims})==4
    before=[s.progress for s in sims];clock[0]+=1;runtime.tick();assert all(s.progress>p for s,p in zip(sims,before))
    for selected in sims:
        before=[s.progress for s in sims];runtime.get(1,selected.id);clock[0]+=1;runtime.tick()
        assert all(s.progress>p for s,p in zip(sims,before))
    for kind in ('DELAY','BREAKDOWN'):
        a=sims[0];before=a.snapshot();inject(a,DisruptionInput(event_type=kind,expected_delay_minutes=30))
        other=[s.progress for s in sims[1:]];clock[0]+=1;runtime.tick();after=a.snapshot()
        assert after['progress']==before['progress'] and (after['latitude'],after['longitude'])==(before['latitude'],before['longitude'])
        assert datetime.fromisoformat(after['current_eta'])==datetime.fromisoformat(before['current_eta'])+timedelta(minutes=30)
        assert all(s.progress>p for s,p in zip(sims[1:],other));a.control('resume',clock[0])
    sims[0].control('pause',clock[0]);before=[s.progress for s in sims];clock[0]+=1;runtime.tick()
    assert sims[0].progress==before[0] and all(s.progress>p for s,p in zip(sims[1:],before[1:]))
    sims[0].control('resume',clock[0]);sims[1].control('stop',clock[0]);before=[s.progress for s in sims];clock[0]+=1;runtime.tick()
    assert sims[1].progress==before[1] and all(sims[i].progress>before[i] for i in (0,2,3))
    fleet.initialize(1);assert all(s.id in runtime.entries for s in sims)
    full=service.movements(1);compact=service.movements(1,include_geometry=False)
    assert all('route' not in m for m in compact['movements']) and len(full['movements'])==len(compact['movements'])


def test_initialize_requires_auth_and_reports_road_failures(loaded, monkeypatch):
    from backend.operations.road_routing_engine import RoadRoutingError
    from backend.fedex import simulator
    def fail(*args, **kwargs): raise RoadRoutingError('OSRM unavailable','ROAD_ROUTE_UNAVAILABLE')
    monkeypatch.setattr(simulator.road_routing_engine,'get_route',fail)
    app=FastAPI();app.include_router(routes.router)
    with TestClient(app) as c:
        assert c.post('/operations/movements/initialize').status_code==401
        app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
        result=c.post('/operations/movements/initialize'); assert result.status_code==200
        assert result.json()['skipped']
        assert all(m['mode']!='SURFACE' for m in active(result.json()))


def test_ahmedabad_guwahati_rejects_insufficient_vehicle_range(loaded):
    from backend.agents.supervisor import _format_planning_result
    network, runtime, _ = loaded
    result=PlanningService().plan(1,PlanningRequest(source='Ahmedabad',destination='Guwahati',shipment={'weight_kg':6000},allowed_modes=['road']))
    path=PlanningService._shortest(network['routes'],'Ahmedabad','Guwahati','distance',{'road'},set())
    distance=sum(r['distance'] for r in path)
    limits=[v['max_range_km'] for v in network['vehicles'] if v['current_location']=='Ahmedabad' and v['type'].lower()=='truck']
    assert path and distance>max(limits)
    assert result['recommended_plan'] is None and not runtime.entries
    answer=_format_planning_result(result)
    assert 'range' in answer and 'No journey was created' in answer
    print('AHMEDABAD GUWAHATI: shortest loaded path',distance,'km; source truck ranges',limits)
