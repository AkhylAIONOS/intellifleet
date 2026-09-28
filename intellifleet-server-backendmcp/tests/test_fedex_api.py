from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from backend.fedex import routes
from backend.fedex.telemetry import Runtime
from backend.routes.auth import get_current_user
from test_fedex_eligibility import schedules


@pytest.fixture
def api(schedules, monkeypatch):
    now=[0.0]
    runtime=Runtime(clock=lambda:now[0])
    monkeypatch.setattr(routes,'runtime',runtime)
    monkeypatch.setattr(routes,'schedules',lambda:schedules)
    app=FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    return TestClient(app),app,now,runtime


INPUT={'origin_station':'UDRPU','gateway':'DELGW','simulation_date':'2026-09-29','shipment_ready_datetime':'2026-09-29T18:00:00','speed':600}


def test_bad_workbook_fails_without_internal_details(monkeypatch):
    import zipfile
    from fastapi import HTTPException
    routes.schedules.cache_clear()
    monkeypatch.setattr(routes,'load_schedules',lambda: (_ for _ in ()).throw(zipfile.BadZipFile('internal path')))
    with pytest.raises(HTTPException) as error:
        routes.schedules()
    assert error.value.status_code==503 and 'internal path' not in error.value.detail
    routes.schedules.cache_clear()


def test_api_lifecycle_and_reconnect(api):
    client,app,now,runtime=api
    assert client.get('/fedex/schedules').status_code==200
    eligible=client.get('/fedex/eligible-services',params={k:v for k,v in INPUT.items() if k!='speed'}).json()
    assert eligible['selected']['mode']=='SURFACE'
    created=client.post('/fedex/simulations',json=INPUT)
    assert created.status_code==201
    sid=created.json()['simulation_id']; url=f'/fedex/simulations/{sid}'
    now[0]=40
    state=client.post(url+'/events',json={'expected_delay_minutes':30}).json()
    assert state['alerts'] and state['current_eta']!=state['scheduled_eta']
    assert client.post(url+'/control',json={'action':'pause'}).json()['paused']
    assert not client.post(url+'/control',json={'action':'resume'}).json()['paused']
    now[0]=150
    for _ in range(2):
        response=client.get(url+'/stream')
        assert 'event: telemetry' in response.text and 'ARRIVED_AT_GTW' in response.text
    assert client.post(url+'/control',json={'action':'reset'}).json()['reset']
    assert client.get(url).status_code==404


def test_auth_and_isolation(api):
    client,app,now,runtime=api
    sid=client.post('/fedex/simulations',json=INPUT).json()['simulation_id']
    app.dependency_overrides[get_current_user]=lambda:{'user_id':2}
    for suffix in ('','/stream'):
        assert client.get(f'/fedex/simulations/{sid}{suffix}').status_code==404
    assert client.post(f'/fedex/simulations/{sid}/events',json={}).status_code==404
    app.dependency_overrides.clear()
    assert client.get('/fedex/schedules').status_code in (401,403)


def test_limits_and_validation(api):
    client,app,now,runtime=api
    runtime.limit=1
    assert client.post('/fedex/simulations',json=INPUT).status_code==201
    assert client.post('/fedex/simulations',json=INPUT).status_code==422
    now[0]=21601
    assert client.post('/fedex/simulations',json=INPUT).status_code==201
    assert client.post('/fedex/simulations',json={**INPUT,'speed':0}).status_code==422
