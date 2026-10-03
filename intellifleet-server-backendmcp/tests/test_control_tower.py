from datetime import date, datetime, timedelta, timezone
import asyncio
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.control_tower.service import ControlTower
from backend.control_tower.status import operational_fields
from backend.control_tower import routes
from backend.routes.auth import get_current_user
from backend.fedex.models import Schedule

NOW=datetime(2030,1,1,6,tzinfo=timezone.utc)


@pytest.fixture
def tower(tmp_path):
    return ControlTower(str(tmp_path/'tower.db'),clock=lambda:NOW)


def schedules():
    return [Schedule(schedule_id=mode.lower()+'-2',source_sheet=mode,source_row=2,origin_city='City',origin_station='A',gateway='B',lane='A-B',run='1',mode=mode,source_mode=mode,
        service='Provided carrier',vehicle_count=2,cutoff_minutes=60,etd_minutes=120,eta_minutes=720,
        source={'ETA':'0.5','Run':'1','Details':'Provided carrier'}) for mode in ['AIR','SURFACE']]


def load(tower,owner=1):
    return tower.import_network(owner,schedules(),date(2030,1,1))


def event(kind='DEPARTURE',event_id='e1',at=NOW,**kwargs):
    return dict(event_id=event_id,event_type=kind,source=kwargs.pop('source','FEDEX_SCAN'),event_at=at.isoformat(),**kwargs)


@pytest.mark.parametrize('departure,arrival,eta,now,status',[
    (None,None,NOW,NOW,'SCHEDULED'),
    (NOW,None,NOW+timedelta(hours=1),NOW,'ON TIME'),
    (NOW,None,NOW+timedelta(hours=2),NOW,'EXPECTED DELAY'),
    (NOW,None,NOW+timedelta(hours=2),NOW+timedelta(hours=1,minutes=6),'DELAYED'),
    (NOW,NOW+timedelta(hours=2),NOW+timedelta(hours=2),NOW+timedelta(hours=3),'ARRIVED')])
def test_status_and_time(departure,arrival,eta,now,status):
    r=dict(actual_departure_at=departure,actual_arrival_at=arrival,planned_eta=NOW+timedelta(hours=1),current_eta=eta)
    fields=operational_fields(r,now)
    assert fields['status']==status
    if arrival:
        assert fields['elapsed_hours']==2 and fields['actual_tt_hours']==2 and fields['estimated_time_left_hours']==0


def test_time_remaining_is_not_progress():
    fields=operational_fields(dict(actual_departure_at=NOW-timedelta(hours=2),planned_eta=NOW+timedelta(hours=1),progress=.99),NOW)
    assert fields['elapsed_hours']==2 and fields['estimated_time_left_hours']==1


def test_operational_sla_preserves_baseline_after_delay_and_arrival():
    run=dict(actual_departure_at=NOW,planned_eta=NOW+timedelta(hours=1),current_eta=NOW+timedelta(hours=3),deadline=NOW+timedelta(hours=2))
    delayed=operational_fields(run,NOW)
    assert delayed['baseline_sla_met'] is True and delayed['current_sla_met'] is False
    run['actual_arrival_at']=NOW+timedelta(hours=3)
    arrived=operational_fields(run,NOW+timedelta(hours=4))
    assert arrived['current_sla_met'] is False and arrived['actual_tt_hours']==3


def test_network_separation_preservation_and_versioning(tower):
    rows=load(tower)
    assert len(rows)==2 and len(load(tower))==2
    assert tower.runs(1,mode='AIR')[0]['schedule']['source']==schedules()[0].source
    assert len(tower.runs(1,mode='SURFACE'))==1
    synthetic=[s.model_copy(update={'data_source':'SYNTHETIC_NETWORK'}) for s in schedules()]
    with pytest.raises(ValueError):tower.import_network(1,synthetic,date(2030,1,1))
    altered=[s.model_copy(update={'service':'New version'}) for s in schedules()]
    newest=tower.import_network(1,altered,date(2030,1,1))
    assert len(newest)==2 and newest[0]['network_version']!=rows[0]['network_version']
    assert tower.detail(1,rows[0]['run_id'])['schedule']['service']=='Provided carrier'


def test_critical_scope_and_filters(tower):
    row=load(tower)[0]
    load(tower,2)
    tower.mark_critical(1,row['run_id'],True)
    assert len(tower.runs(1,critical=True))==2  # business lane across modes
    assert tower.runs(2,critical=True)==[]
    tower.mark_critical(1,row['run_id'],False)
    assert tower.runs(1,critical=True)==[]
    with pytest.raises(KeyError):tower.detail(3,row['run_id'])


def test_events_sla_location_and_idempotency(tower):
    row=load(tower)[0];rid=row['run_id']
    e=event(latitude=10,longitude=70,carrier='Aircraft-X')
    tower.event(1,rid,e);tower.event(1,rid,e)
    detail=tower.detail(1,rid)
    assert len(detail['events'])==1 and detail['carrier']=='Aircraft-X'
    assert detail['location_source']=='FEDEX_SCAN'
    with pytest.raises(ValueError):tower.event(1,rid,event(event_id='e1',reason='Different'))
    with pytest.raises(ValueError):tower.event(1,rid,event('ETA_UPDATE','e2',source='invalid'))


def test_scan_order_and_provenance(tower):
    rid=load(tower)[0]['run_id']
    with pytest.raises(ValueError):tower.event(1,rid,event('ARRIVAL'))
    tower.event(1,rid,event())
    with pytest.raises(ValueError):tower.event(1,rid,dict(event('LOCATION','synthetic'),source='SYNTHETIC_TELEMETRY'))
    with pytest.raises(ValueError):tower.event(1,rid,event('LOCATION','stale',NOW-timedelta(hours=1)))
    tower.event(1,rid,event('ARRIVAL','arrival',NOW+timedelta(hours=1)))
    assert tower.detail(1,rid)['actual_tt_hours']==1


def test_alert_transition_dedupe_retry_disabled(tower):
    rid=load(tower)[0]['run_id']
    tower.recipients(1,['operator@example.invalid'])
    tower.event(1,rid,event(at=NOW-timedelta(hours=1)))
    tower.event(1,rid,event('ETA_UPDATE','delay',NOW,current_eta=(NOW+timedelta(hours=3)).isoformat()))
    tower.event(1,rid,event('ETA_UPDATE','delay',NOW,current_eta=(NOW+timedelta(hours=3)).isoformat()))
    assert len(tower.alerts(1))==1
    asyncio.run(tower.deliver(enabled=False))
    assert tower.alerts(1)[0]['status'] in {'NOT_CONFIGURED','DELIVERY_DISABLED'}
    tower.clock=lambda:NOW+timedelta(minutes=6)
    async def fail(*args):raise RuntimeError('secret')
    asyncio.run(tower.deliver(sender=fail,enabled=True))
    assert tower.alerts(1)[0]['status']=='RETRY' and 'secret' not in tower.alerts(1)[0]['last_error']
    tower.clock=lambda:NOW+timedelta(minutes=10)
    sent=[]
    async def sender(*args):sent.append(args)
    asyncio.run(tower.deliver(sender=sender,enabled=True))
    assert len(sent)==1 and tower.alerts(1)[0]['status']=='DELIVERED'
    asyncio.run(tower.deliver(sender=sender,enabled=True))
    assert len(sent)==1


def test_con_departure_link_lookup_scope(tower):
    rid=load(tower)[0]['run_id']
    data=dict(con_number='CON-123',run_id=rid,event_id='con1',source='FEDEX_SCAN',event_at=NOW.isoformat())
    with pytest.raises(ValueError):tower.con_event(1,data)
    tower.event(1,rid,event())
    tower.con_event(1,data);tower.con_event(1,data)
    assert tower.con(1,'CON-123')['run']['run_id']==rid
    assert len(tower.detail(1,rid)['cons'])==1
    with pytest.raises(KeyError):tower.con(2,'CON-123')


def test_api_authorization_and_validation(tower,monkeypatch):
    app=FastAPI();app.include_router(routes.router)
    monkeypatch.setattr(routes,'service',tower)
    client=TestClient(app)
    assert client.get('/operations/control-tower/runs').status_code in {401,403}
    app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    rid=load(tower)[0]['run_id']
    assert client.get('/operations/control-tower/runs?limit=201').status_code==422
    assert client.post(f'/operations/control-tower/runs/{rid}/events',json=event(at=datetime(2030,1,1))).status_code==422
    assert client.put('/operations/alerts/recipients',json={'emails':['bad']}).status_code==422
    monkeypatch.setattr(routes.settings,'FEDEX_SCAN_INGEST_TOKEN',None)
    assert client.post(f'/operations/control-tower/runs/{rid}/events',json=event()).status_code==503
    monkeypatch.setattr(routes.settings,'FEDEX_SCAN_INGEST_TOKEN','test-ingestion-token')
    assert client.post(f'/operations/control-tower/runs/{rid}/events',json=event()).status_code==403
    assert client.post(f'/operations/control-tower/runs/{rid}/events',json=event(),headers={'X-FedEx-Ingest-Token':'test-ingestion-token'}).status_code==200
    app.dependency_overrides[get_current_user]=lambda:{'user_id':2}
    assert client.get(f'/operations/control-tower/runs/{rid}').status_code==404
