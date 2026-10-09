from datetime import date, datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.control_tower import routes
from backend.control_tower.service import ControlTower
from backend.fedex.importer import load_schedules
from backend.fedex.telemetry import Runtime
from backend.routes.auth import get_current_user


def test_cjb_blr_explicit_demo_has_location_and_starts_at_etd(tmp_path,monkeypatch):
    import backend.fedex.telemetry as telemetry
    clock=[0.0];runtime=Runtime(clock=lambda:clock[0])
    monkeypatch.setattr(telemetry,'runtime',runtime)
    tower=ControlTower(str(tmp_path/'demo.db'))
    rows=tower.import_network(1,load_schedules(),date(2030,1,1))
    row=next(r for r in rows if r['schedule']['lane']=='CJB-BLR' and r['schedule']['mode']=='AIR')
    original=row['schedule']['source'].copy()
    monkeypatch.setattr(routes,'service',tower)
    app=FastAPI();app.include_router(routes.router);app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    client=TestClient(app)
    request=dict(origin_station=row['schedule']['origin_station'],gateway=row['schedule']['gateway'],simulation_date='2030-01-01',shipment_ready_datetime='2030-01-01T00:00:00+05:30',demo_playback=True,speed=120)
    response=client.post('/operations/control-tower/runs/'+row['run_id']+'/simulation',json=request)
    assert response.status_code==200,response.text
    started=response.json()
    assert started['location_source']=='SYNTHETIC_TELEMETRY' and started['latest_location']
    movement=started['movement']
    assert 0 < movement['progress'] < 0.001  # Existing explicit playback advances one second.
    assert datetime.fromisoformat(movement['simulation_timestamp'])==datetime.fromisoformat(movement['scheduled_etd'])+timedelta(seconds=1)
    assert movement['location_notice'].startswith('Approximate city centres')
    clock[0]=1
    tower.observe(1)
    active=tower.detail(1,row['run_id'])
    assert active['status']=='ON TIME' and active['actual_departure_at']
    assert active['movement']['progress']>0 and active['latest_location']==started['latest_location']  # Quick controls remain paused between steps.
    assert active['schedule']['source']==original
    assert len(tower.runs(1))==38
    repeated=client.post('/operations/control-tower/runs/'+row['run_id']+'/simulation',json=request).json()
    assert repeated['movement_id']==started['movement_id'] and len(runtime.entries)==1
