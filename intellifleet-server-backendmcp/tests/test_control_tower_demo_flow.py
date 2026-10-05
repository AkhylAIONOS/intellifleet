"""Offline Control Tower answers and per-run timestamp-derived demo lifecycle."""
import asyncio
import json
from datetime import date, datetime, timezone
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.control_tower import chat, routes
from backend.control_tower.service import ControlTower
from backend.fedex.importer import load_schedules
from backend.fedex import telemetry
from backend.routes.auth import get_current_user

DATE=date(2030,1,1)


@pytest.fixture
def tower(tmp_path,monkeypatch):
    service=ControlTower(str(tmp_path/'ct.db'),clock=lambda:datetime(2030,1,1,tzinfo=timezone.utc))
    service.import_network(1,load_schedules(),DATE)
    monkeypatch.setattr(chat,'ControlTower',lambda:service)
    monkeypatch.setattr(routes,'service',service)
    monkeypatch.setattr(telemetry,'runtime',telemetry.Runtime(clock=lambda:0))
    return service


def ask(message,run_id=None):
    return chat.answer(1,message,run_id,str(DATE))['response']


@pytest.mark.parametrize('mode,count',[('Air',10),('Surface',28)])
def test_scheduled_and_zero_delay(tower,mode,count):
    text=ask(f'Which {mode} runs are currently delayed?')
    assert f'No {mode} runs are currently delayed.' in text
    assert str(count) in text and 'all are currently Scheduled' in text
    assert 'inspect' not in text
    text=ask(f'Show scheduled {mode} runs.')
    assert f'Matching {mode} runs: {count}' in text and 'All matching runs are currently Scheduled' in text


def test_queries_and_scoped_followups(tower):
    assert 'No critical lanes are currently at risk. 38 operational runs' in ask('Which critical lanes are currently at risk?')
    for question in ['How many runs are there today?','How many Air runs?','How many Surface runs?']:
        assert '38 operational runs are loaded: 10 Air and 28 Surface' in ask(question)
    for question,code in [('Show Surface runs for Delhi.','DELGW'),('Show Surface runs through DELGW.','DELGW'),('Show runs through NDLS.','NDLS')]:
        result=chat.answer(1,question,service_date=str(DATE))
        ids=tower.chat_context(1,DATE)
        assert ids and code in str([tower.detail(1,i)['schedule'] for i in ids])
    assert 'No Surface runs matching Atlantis' in ask('Show Surface runs for Atlantis.')
    assert '28 Surface runs are currently loaded' in ask('Show Surface runs for Atlantis.')
    ask('Show Surface runs for Delhi.')
    ids=tower.chat_context(1,DATE);tower.mark_critical(1,ids[0],True)
    text=ask('Which of those are critical?')
    assert tower.chat_context(1,DATE)
    assert set(tower.chat_context(1,DATE))<=set(ids)
    assert all(tower.detail(1,i)['critical'] for i in tower.chat_context(1,DATE))
    assert 'Critical yes' in text and 'not currently at risk' in text
    for question in ['What is the status of CJB-BLR?','What is the ETA of CJB-BLR?','Show run 1 for CJB-BLR.']:
        text=ask(question)
        assert 'CJB-BLR' in text and 'Scheduled ETA' in text
    assert 'Load the FedEx Network Plan' in chat.answer(1,'Which runs have arrived?',service_date='2031-01-01')['response']
    tower.chat_context(1,DATE,[])
    assert 'No Control Tower run is selected/referenced' in ask('What is the current ETA of the critical delayed run?')


@pytest.mark.parametrize('mode',['AIR','SURFACE'])
def test_complete_lifecycle_api_con_alerts(tower,mode,monkeypatch):
    app=FastAPI();app.include_router(routes.router)
    app.dependency_overrides[get_current_user]=lambda:{'user_id':1}
    client=TestClient(app)
    run=next(r for r in tower.runs(1,DATE) if r['schedule']['mode']==mode and r['schedule']['origin_station']=='UDRPU')
    rid=run['run_id'];planned=(run['planned_etd'],run['planned_eta'])
    tower.personal_email(1,'test-session','demo@example.com')
    tower.mark_critical(1,rid,True)
    s=run['schedule']
    response=client.post(f'/operations/control-tower/runs/{rid}/simulation',json=dict(origin_station=s['origin_station'],gateway=s['gateway'],simulation_date=str(DATE),shipment_ready_datetime='2030-01-01T00:00:00+05:30',speed=120,demo_playback=True))
    assert response.status_code==200,response.text
    run=response.json();assert run['status']=='ON TIME' and run['actual_departure_at']
    assert run['elapsed_hours']>0 and run['estimated_time_left_hours']>0
    assert s['lane'] in ask(f'Which {"Air" if mode=="AIR" else "Surface"} runs are on time?')
    assert 'Hypothetical ETA' in ask('If the current delayed run becomes 30 minutes later, what should the operator do?',rid)
    con=run['cons'][0]['con_number']
    assert con.startswith('CT-SYNTHETIC-')
    for action,status in [('delay10','EXPECTED DELAY'),('delay30','DELAYED'),('arrive','ARRIVED')]:
        response=client.post(f'/operations/control-tower/runs/{rid}/synthetic-action',json={'action':action})
        assert response.status_code==200,response.text
        run=response.json();assert run['status']==status
        assert (run['planned_etd'],run['planned_eta'])==planned
        assert run['actual_source']==run['location_source']=='SYNTHETIC_TELEMETRY'
        assert tower.con(1,con)['run']['status']==status
        if status!='ARRIVED':
            assert datetime.fromisoformat(run['current_eta'])>datetime.fromisoformat(run['planned_eta'])
            assert tower.summary(tower.runs(1,DATE))['critical_lanes_at_risk']==1
            assert rid in [r['run_id'] for r in tower.runs(1,DATE,critical=True,status=status)]
            assert s['lane'] in ask('Which critical lanes are currently at risk?')
            assert s['lane'] in ask(f'Which {"Air" if mode=="AIR" else "Surface"} runs are delayed?')
            assert s['lane'] in ask('What are their ETAs?')
            if status=='EXPECTED DELAY':assert s['lane'] in ask('Which runs are expected delayed?')
        else:
            assert run['actual_arrival_at'] and run['actual_tt_hours']>0
            assert run['estimated_time_left_hours']==0
            assert run['elapsed_hours']==run['actual_tt_hours']
            assert s['lane'] in ask('Which runs have arrived?')
    assert len(tower.alerts(1))==2
    assert len(tower.personal_alerts(1,'test-session'))==2
    assert all(json.loads(a['payload_json'])['actual_source']=='SYNTHETIC_TELEMETRY' for a in tower.alerts(1))
    assert all(json.loads(a['payload_json'])['critical'] for a in tower.alerts(1))
    for _ in range(3):tower.observe(1)
    assert len(tower.alerts(1))==2
    async def forbidden(*args):raise AssertionError('Never send real email')
    asyncio.run(tower.deliver(sender=forbidden,enabled=False))
    assert all(a['attempts']==0 for a in tower.alerts(1))
    assert len([r for r in tower.runs(1,DATE) if r['status']=='SCHEDULED'])==37
    assert 'Real live FedEx GPS is unavailable' in ask('Tell me the exact live FedEx GPS location of this CON right now.')
    assert 'SYNTHETIC_TELEMETRY' in ask('Find CON '+con)
    assert 'No CON association' in ask('Find CON CT-MISSING')
    app.dependency_overrides[get_current_user]=lambda:{'user_id':2}
    assert client.post(f'/operations/control-tower/runs/{rid}/synthetic-action',json={'action':'delay10'}).status_code==404


def test_all_operational_queries_bypass_planner(tower,monkeypatch):
    from backend.api import chat_api
    async def forbidden(*args):raise AssertionError('Planner must not be queried')
    monkeypatch.setattr(chat_api,'get_active_planning_context',forbidden)
    for message in ['Which runs are expected delayed?','Which runs are on time?','Which runs have arrived?','Show scheduled Air runs.','Show scheduled Surface runs.','Show runs through NDLS.','What is the status of CJB-BLR?','What is the ETA of CJB-BLR?','How many runs are there today?','Which lanes are delayed?','Which runs are critical?','Which Air runs are on time?']:
        result=asyncio.run(chat_api.guarded_chat(chat_api.ChatRequest(message=message,operational_service_date=str(DATE)),{'user_id':1}))
        assert result['response'] and 'traceback' not in result['response'].casefold()


def test_chat_followups_isolated_by_session_and_date(tower):
    chat.answer(1,'Show Surface runs for Delhi.',service_date=str(DATE),session_id='chat-one')
    assert tower.chat_context(1,DATE,session_id='chat-one')
    for session in ['chat-two',None]:
        text=chat.answer(1,'Which of those are critical?',service_date=str(DATE),session_id=session)['response']
        assert 'No previous Control Tower result set' in text
    chat.answer(1,'Which Air runs are delayed?',service_date=str(DATE),session_id='chat-one')
    assert tower.chat_context(1,DATE,session_id='chat-one')==[]
    text=chat.answer(1,'What are their ETAs?',service_date=str(DATE),session_id='chat-one')['response']
    assert 'No matching' in text and 'Current ETA' not in text
