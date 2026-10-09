from datetime import date, datetime, timezone
from copy import deepcopy
import pytest
from backend.control_tower import chat, visualization as viz
from backend.control_tower.service import ControlTower
from backend.fedex.models import Schedule

@pytest.fixture
def loaded(tmp_path,monkeypatch):
    monkeypatch.setattr(viz,'city_coordinates',lambda:{'CJB':(11,77),'BLR':(13,78)})
    tower=ControlTower(str(tmp_path/'test.db'),clock=lambda:datetime(2030,1,1,3,tzinfo=timezone.utc))
    schedules=[Schedule(schedule_id=mode,source_sheet='Air' if mode=='AIR' else 'Surface',source_row=2,origin_city='Coimbatore',origin_station='CJB',gateway='BLR',lane='CJB-BLR',run='1',mode=mode,source_mode=mode,service='Workbook service',etd_minutes=120,eta_minutes=720,source={'ETD':'02:00','ETA':'12:00'}) for mode in ['AIR','SURFACE']]
    rows=tower.import_network(1,schedules,date(2030,1,1))
    monkeypatch.setattr(chat,'ControlTower',lambda:tower)
    return tower,rows

def test_visualization_does_not_mutate_source(loaded):
    tower,rows=loaded
    run=rows[0];original=deepcopy(run)
    v=viz.visualization(run,tower.clock())
    assert v['origin']==(11,77) and v['destination']==(13,78)
    assert v['position'] is not None
    assert v['location_source']=='Schedule-derived position'
    assert run==original and run['latest_location'] is None and run['actual_source'] is None
    with tower.db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM ct_events').fetchone()[0]==0

def test_unknown_coordinates_and_times_are_unavailable(loaded,monkeypatch):
    tower,rows=loaded
    monkeypatch.setattr(viz,'city_coordinates',lambda:{})
    v=viz.visualization(rows[0],tower.clock())
    assert v['position'] is None and v['origin'] is None

def test_selected_followup_and_missing_facts(loaded):
    tower,rows=loaded
    args=dict(selected_run_id=rows[0]['run_id'],service_date='2030-01-01',workspace='LIVE OPERATIONS')
    assert '2030-01-01' in chat.answer(1,'What is its ETA?',**args)['response']
    assert 'unavailable' in chat.answer(1,'What is its driver?',**args)['response']
    before=tower.detail(1,rows[0]['run_id'])
    result=chat.answer(1,'Assume this run is delayed by 30 minutes. What is the revised ETA?',**args)
    assert 'Hypothetical ETA' in result['response']
    assert tower.detail(1,rows[0]['run_id'])==before
    assert chat.answer(1,'Plan from Delhi to Mumbai with 100 kg',**args) is None
    comparison=chat.answer(1,f"Compare {rows[0]['run_id']} and {rows[1]['run_id']}",service_date='2030-01-01',workspace='LIVE OPERATIONS')['response']
    assert 'Operational comparison' in comparison and 'AIR' in comparison and 'SURFACE' in comparison
    tower.event(1,rows[0]['run_id'],dict(event_id='provided-reason',event_type='DEPARTURE',source='FEDEX_SCAN',event_at=tower.clock().isoformat(),reason='Provided scan reason'))
    assert 'Provided scan reason' in chat.answer(1,'Why is it delayed?',**args)['response']

def test_operational_workspace_cannot_fall_through_to_generic_fleet(loaded):
    assert chat.answer(1,'Show all movements',service_date='2030-01-01',workspace='LIVE OPERATIONS') is not None
    response=chat.answer(1,'Show all Air operational runs',service_date='2030-01-01',workspace='LIVE OPERATIONS')['response']
    assert 'Matching Air runs: 1' in response
    response=chat.answer(1,'Show all Surface operational runs',service_date='2030-01-01',workspace='LIVE OPERATIONS')['response']
    assert 'Matching Surface runs: 1' in response


def test_real_scan_coordinates_win_over_retained_demo_link(loaded):
    tower,rows=loaded
    run=rows[0]
    tower.event(1,run['run_id'],dict(event_id='real-scan',event_type='DEPARTURE',source='FEDEX_SCAN',event_at=tower.clock().isoformat(),latitude=12.1,longitude=77.2))
    with tower.db() as conn:
        conn.execute("UPDATE ct_runs SET movement_id='retained-demo' WHERE owner=1 AND run_id=?",(run['run_id'],))
    result=tower.detail(1,run['run_id'])
    assert result['location_source']=='FEDEX_SCAN'
    assert result['latest_location']=={'latitude':12.1,'longitude':77.2}
    assert result['schedule']['source']==run['schedule']['source']
