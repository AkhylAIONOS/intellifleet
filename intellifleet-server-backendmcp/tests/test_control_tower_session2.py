"""Session 2 boundaries and ownership checks; outbound delivery is mocked only."""
from datetime import timedelta
import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.control_tower.status import operational_fields
from backend.control_tower import routes
from backend.routes.auth import get_current_user
from test_control_tower import tower, load, event, NOW


@pytest.mark.parametrize('seconds,status',[(-1,'ON TIME'),(0,'ON TIME'),(1,'DELAYED')])
def test_five_minute_elapsed_boundary(seconds,status):
    planned=NOW+timedelta(hours=1)
    facts=operational_fields(dict(actual_departure_at=NOW,planned_eta=planned,current_eta=planned),planned+timedelta(minutes=5,seconds=seconds))
    assert facts['status']==status


@pytest.mark.parametrize('seconds,status',[(-1,'ON TIME'),(0,'ON TIME'),(1,'EXPECTED DELAY')])
def test_five_minute_eta_boundary(seconds,status):
    planned=NOW+timedelta(hours=1)
    facts=operational_fields(dict(actual_departure_at=NOW,planned_eta=planned,current_eta=planned+timedelta(minutes=5,seconds=seconds)),NOW)
    assert facts['status']==status


def test_missed_departure_remains_scheduled():
    assert operational_fields(dict(planned_eta=NOW-timedelta(days=1)),NOW)['status']=='SCHEDULED'


def test_critical_at_risk_and_owner_persistence(tower):
    rid=load(tower)[0]['run_id'];load(tower,2)
    tower.mark_critical(1,rid,True)
    tower.event(1,rid,event(at=NOW-timedelta(hours=1)))
    tower.event(1,rid,event('ETA_UPDATE','late',current_eta=(NOW+timedelta(hours=3)).isoformat()))
    assert len(tower.runs(1,status='EXPECTED DELAY',critical=True))==1
    assert tower.summary(tower.runs(1))['critical_lanes_at_risk']==1
    assert tower.summary(tower.runs(2))['critical_lanes_at_risk']==0
    tower.clock=lambda:NOW+timedelta(hours=1,minutes=6)
    tower.observe(1);tower.observe(1)
    assert len(tower.runs(1,status='DELAYED',critical=True))==1
    assert len(tower.alerts(1))==2
    assert [a['status'] for a in tower.alerts(1)]==['NO_RECIPIENTS','NO_RECIPIENTS']
    tower.mark_critical(1,rid,False)
    assert tower.runs(1,critical=True)==[]


def test_disabled_and_unconfigured_never_call_sender(tower,monkeypatch):
    rid=load(tower)[0]['run_id']
    tower.personal_email(1,'session2','session2@example.com');tower.personal_email(2,'other','other@example.com')
    tower.event(1,rid,event(at=NOW-timedelta(hours=1)))
    tower.event(1,rid,event('ETA_UPDATE','delay',current_eta=(NOW+timedelta(hours=3)).isoformat()))
    async def forbidden(*args):raise AssertionError('sender must not run')
    monkeypatch.setattr(routes.settings,'SMTP_SERVER',None)
    asyncio.run(tower.deliver(sender=forbidden,enabled=False))
    assert tower.alerts(1)[0]['status']=='NOT_CONFIGURED'
    for name,value in {'SMTP_SERVER':'test.invalid','SMTP_PORT':587,'SMTP_USERNAME':'test','SMTP_PASSWORD':'test-only','EMAIL_FROM':'test@example.invalid'}.items():
        monkeypatch.setattr(routes.settings,name,value)
    tower.clock=lambda:NOW+timedelta(minutes=6)
    asyncio.run(tower.deliver(sender=forbidden,enabled=False))
    assert tower.alerts(1)[0]['status']=='DELIVERY_DISABLED'
    assert tower.alerts(1)[0]['attempts']==0
    assert tower.alerts(2)==[] and tower.personal_email(2,'other')=='other@example.com'


def test_scan_and_con_api_need_both_credentials_and_owner(tower,monkeypatch):
    app=FastAPI();app.include_router(routes.router)
    monkeypatch.setattr(routes,'service',tower)
    monkeypatch.setattr(routes.settings,'FEDEX_SCAN_INGEST_TOKEN','session2-ingest-test-only')
    client=TestClient(app)
    rid=load(tower)[0]['run_id']
    endpoint=f'/operations/control-tower/runs/{rid}/events'
    ingest={'X-FedEx-Ingest-Token':'session2-ingest-test-only'}
    assert client.post(endpoint,json=event(),headers=ingest).status_code in {401,403}
    app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    assert client.post(endpoint,json=event()).status_code==403
    assert client.post(endpoint,json=event(),headers={'X-FedEx-Ingest-Token':'wrong'}).status_code==403
    assert client.post(endpoint,json=event(),headers=ingest).status_code==200
    data=dict(con_number='SESSION2-CON',run_id=rid,event_id='session2-con',source='FEDEX_SCAN',event_at=NOW.isoformat())
    assert client.post('/operations/cons/events',json=data).status_code==403
    assert client.post('/operations/cons/events',json=data,headers=ingest).status_code==200
    assert client.get('/operations/cons/SHIPMENT-FAKE').status_code==404
    app.dependency_overrides[get_current_user]=lambda:{'user_id':2}
    assert client.post(endpoint,json=event(event_id='other-owner'),headers=ingest).status_code==404
    assert client.put('/operations/critical-lanes/'+rid,json={'critical':True}).status_code==404
    assert client.get('/operations/cons/SESSION2-CON').status_code==404
    assert client.post('/operations/cons/events',json=data,headers=ingest).status_code==404
