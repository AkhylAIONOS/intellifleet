import asyncio
import copy
import io
import sqlite3
from datetime import date, datetime
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile
from backend.operations.data import DATA_DIR, rows, validate_network, synthetic_schedules
from backend.operations import service, routes
from backend.fedex.telemetry import Runtime
from backend.fedex.eligibility import candidate
from backend.fedex.models import EligibilityInput
from backend.planning.service import PlanningService
from backend.routes.auth import get_current_user


def test_v2_consistency():
    assert validate_network(rows('warehouse.csv'),rows('vehicle.csv'),rows('routes.csv'))=={'warehouses':30,'vehicles':97,'routes':72,'validation':'PASS'}
    for r in rows('routes.csv'):
        if r['RouteType']=='road':
            speed=float(r['DistanceKm'])/(float(r['TypicalDurationMin'])/60)
            assert 25<speed<=65
            assert abs(speed-float(r['EffectiveSpeedKmph']))<.01
    assert {s.mode for s in synthetic_schedules()}=={'AIR','SURFACE','RAIL'}
    assert len(synthetic_schedules())==36


@pytest.mark.parametrize('file,index,key,value',[
    ('warehouse',0,'Latitude','nan'),('warehouse',0,'Longitude',200),('warehouse',0,'Inventory',-1),
    ('vehicle',0,'VehicleCapacity',-1),('vehicle',0,'WarehouseName','missing'),('vehicle',1,'VehicleID','TRK-001'),
    ('routes',0,'TypicalDurationMin',60),('routes',0,'BaseTransportCostINR',-1),('routes',0,'Destination','missing'),
])
def test_reject_bad_data(file,index,key,value):
    data={n:rows(n+'.csv') for n in ('warehouse','vehicle','routes')}
    data[file][index][key]=value
    with pytest.raises(ValueError): validate_network(data['warehouse'],data['vehicle'],data['routes'])


def test_overnight_and_multiday():
    request=EligibilityInput(origin_station='SYN-DEL-STN',gateway='SYN-BOM-GTW',simulation_date=date(2026,9,29),shipment_ready_datetime=datetime(2026,9,29,18))
    ss=[s for s in synthetic_schedules() if s.origin_station==request.origin_station]
    for s in ss:
        c=candidate(s,request)
        assert c['cutoff']<c['etd']<c['eta']
        assert (c['eta']-c['etd']).total_seconds()/60==s.transit_minutes
        assert c['data_source']=='SYNTHETIC_SCHEDULE'
    assert any(candidate(s,request)['eta'].day==1 for s in ss) # Oct 1, >24h transit
    bad=rows('schedules.csv');bad[0]['cutoff']=bad[0]['etd']
    with pytest.raises(ValueError):synthetic_schedules(bad)


@pytest.fixture
def loaded(tmp_path,monkeypatch):
    from backend.database.database import init_db
    from backend.planning.database import migrate_planning_schema
    from backend.routes.upload.network_upload import upload_network
    monkeypatch.chdir(tmp_path);init_db();migrate_planning_schema()
    with sqlite3.connect('users.db') as c:
        c.execute("INSERT INTO users(id,first_name,last_name,email,password,verified) VALUES(1,'Test','User','operations@example.invalid','x',1)")
    files=[UploadFile(io.BytesIO((DATA_DIR/f'{name}.csv').read_bytes()),filename=f'{name}.csv') for name in ('warehouse','vehicle','routes')]
    result=asyncio.run(upload_network(*files,{'user_id':1}))
    assert result['routes']==72
    now=[0.0];runtime=Runtime(clock=lambda:now[0])
    monkeypatch.setattr(service,'runtime',runtime);monkeypatch.setattr(routes,'runtime',runtime)
    return PlanningService().load_network(1),runtime,now


@pytest.mark.parametrize('a,b,multihop',[('Delhi','Mumbai',False),('Mumbai','Bengaluru',False),('Ludhiana','Madurai',True),('Kochi','Chennai',True),('Jaipur','Lucknow',True)])
def test_arbitrary_path(loaded,a,b,multihop):
    network,_,_=loaded
    legs,path=service.network_path(network,a,b)
    assert legs[0]['from_location']==a and legs[-1]['to_location']==b
    assert len(path)==len(legs)+1
    assert (len(legs)>1)==multihop
    assert all(leg in network['routes'] for leg in legs)
    assert all(o['data_source']=='SYNTHETIC_NETWORK' for group in network.values() for o in group)
    with pytest.raises(ValueError,match='NO CONNECTED ROUTE'):service.network_path(network,a,'Atlantis')


@pytest.mark.parametrize('count',[10,50,100])
def test_batch(loaded,count):
    network,runtime,now=loaded
    first=service.start_demo(1,count)
    live=[m for m in first['movements'] if m['status']!='SCHEDULE_TEMPLATE']
    assert len(live)==count
    assert {'AIR','SURFACE','RAIL'}<={m['mode'] for m in live}
    assert len({m['simulation_id'] for m in live})==count
    assert all(m['location_source']=='DEMO_SIMULATION' for m in live)
    assert not [m for m in service.movements(2)['movements'] if m['status']!='SCHEDULE_TEMPLATE']
    now[0]=10; runtime.tick()
    assert runtime.errors==0 and runtime.updates==count
    updated=service.movements(1)['movements']
    assert any(m['progress']>live[0]['progress'] for m in updated if m['simulation_id']==live[0]['simulation_id'])
    service.start_demo(1,count)
    assert len(runtime.entries)==count


def test_route_simulation(loaded):
    network,runtime,now=loaded
    m=service.start_route(1,'Kochi','Chennai',6000)
    assert len(m['route'])>2 and m['data_source']=='SYNTHETIC_NETWORK'
    assert runtime.get(1,m['simulation_id']).route==m['route']


def test_api_and_chat(loaded,monkeypatch):
    from backend.operations.chat import answer
    app=FastAPI();app.include_router(routes.router);app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    with TestClient(app) as client:
        assert len(client.get('/operations/schedules').json()['schedules'])==36
        assert client.post('/operations/demo',json={'count':100}).status_code==200
        assert client.post('/operations/demo',json={'count':101}).status_code==422
        result=answer(1,'Show all Air movements.')
        assert result['actions'][0]['data']['filter']=='AIR'
        assert 'DEMO_SIMULATION' in result['response']
        assert answer(1,'Plan 6000 kg from Delhi to Mumbai.') is None
        assert 'SYNTHETIC' in answer(1,'Which service from Udaipur can still reach Delhi Gateway if ready at 18:00?')['response']
        assert 'Specify the shipment ID' in answer(1,'What is its revised ETA?')['response']
        app.dependency_overrides[get_current_user]=lambda:{'user_id':2}
        assert all(m['status']=='SCHEDULE_TEMPLATE' for m in client.get('/operations/movements').json()['movements'])


def test_selected_chat_delay_and_network_recovery(loaded,monkeypatch):
    from backend.operations.chat import answer
    from backend.fedex.disruptions import inject
    from backend.fedex.models import DisruptionInput
    from backend.fedex import telemetry
    network,runtime,now=loaded
    monkeypatch.setattr(telemetry,'runtime',runtime)
    snapshot=service.start_route(1,'Kochi','Chennai',6000)
    sid=snapshot['simulation_id'];now[0]=5;sim=runtime.get(1,sid)
    previous=sim.current_eta
    response=answer(1,'What happens if this truck is delayed by 30 minutes?',sid)
    assert 'Hypothetical additional delay: 30 min' in response['response']
    assert sim.current_eta==previous
    inject(sim,DisruptionInput(expected_delay_minutes=30))
    assert (sim.current_eta-previous).total_seconds()==1800
    assert sim.alerts[-1]['hypothetical_network_recovery']['data_source']=='SYNTHETIC_NETWORK'
    assert sim.alerts[-1]['automatically_executed'] is False
    assert sim.current_eta.strftime('%d %b %Y, %H:%M IST') in answer(1,'What is its revised ETA?',sid)['response']
    assert 'Specify the shipment ID' in answer(2,'What is its revised ETA?',sid)['response']


def test_schedule_import_atomic_and_source_isolation(loaded):
    app=FastAPI();app.include_router(routes.router);app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    with TestClient(app) as client:
        content=(DATA_DIR/'schedules.csv').read_bytes()
        assert client.post('/operations/schedules/import',files={'file':('schedules.csv',content)}).json()['rows']==36
        invalid=content.replace(b'SYNTHETIC',b'FEDEX_SOURCE')
        assert client.post('/operations/schedules/import',files={'file':('schedules.csv',invalid)}).status_code==422
        ss=client.get('/operations/schedules').json()['schedules']
        assert len(ss)==36 and all(s['data_source']=='SYNTHETIC_SCHEDULE' for s in ss)
    routes.custom_schedules.clear()
