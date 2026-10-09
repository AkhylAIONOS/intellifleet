"""Current source-network acceptance, context isolation and accelerated playback."""
from datetime import date,datetime,timedelta
from copy import deepcopy
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.client_api import ChatInput
from backend.client_chat import answer,contexts
from backend.client_network import network
from backend.chat_normalization import normalize,NormalizedIntent
from backend.fedex.models import EligibilityInput,Schedule,DisruptionInput,DEFAULT_PLAYBACK_SPEED
from backend.fedex.eligibility import evaluate
from backend.fedex.importer import load_schedules
from backend.control_tower.service import ControlTower
from backend.control_tower import routes
from backend.fedex.telemetry import runtime
from backend.fedex.disruptions import inject
from backend.routes.auth import get_current_user

MESSAGES=[
"What services are available from CJBMB to BLRGW?",
"Show me the Air option.","Show me the Surface option.",
"What is the ETD and ETA of flight 6E 5355?","Which option arrives first?",
"Which vehicle is assigned to the Surface service from CJBMB to BLRGW?","What is its capacity?",
"Plan 2000 kg from CJBMB to BLRGW.",
"The vehicle assigned to the CJBMB-BLRGW Surface service has broken down. Find a replacement.",
"Delay the CJBMB-BLRGW Surface run by 30 minutes.","What happens if the shipment becomes 4000 kg?",
"Which available option can carry it?","Show the capacity and utilization calculation.",
"Which option from CJBMB to BLRGW is cheapest?"]

@pytest.fixture
def environment(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);contexts.clear()
    tower=ControlTower();rows=tower.import_network(702,load_schedules(),date(2026,10,9))
    stale=next(r for r in rows if r['schedule']['origin_station']=='UDRPU' and r['schedule']['mode']=='SURFACE')
    return tower,rows,stale

def chat(message,stale,session='acceptance'):
    return answer(702,ChatInput(message=message,session_id=session,workspace='LIVE OPERATIONS',operational_service_date='2026-10-09',selected_operational_run_id=stale['run_id']))

def test_exact_fourteen_turns_with_stale_selection(environment):
    tower,rows,stale=environment
    result=[chat(m,stale) for m in MESSAGES]
    assert len(result[0]['services'])==2 and 'weight' not in result[0]['response'].lower()
    assert '6E 5355' in result[1]['response'] and 'TATA 407' in result[2]['response']
    assert '21:25 IST' in result[3]['response'] and '22:40 IST' in result[3]['response']
    assert '6E 5355' in result[4]['response']
    assert 'SUR-surface-25-01' in result[5]['response'] and '2,500' in result[6]['response']
    assert len(result[7]['planning_result']['candidate_plans'])==2
    assert result[8]['recovery']['replacement_vehicles']==[]
    assert 'No same-service spare vehicle is available' in result[8]['response']
    assert '6E 5355' in result[8]['response']
    assert '06:00 IST' in result[9]['response'] and '06:30 IST' in result[9]['response']
    assert result[10]['planning_result']['planning_request']['shipment']['weight_kg']==4000
    assert {p['client_service'] for p in result[10]['planning_result']['candidate_plans']}=={'6E 5355'}
    facts={r['service_id']:r for r in result[11]['capacity_results']}
    assert facts['surface-25']['feasible'] is False and facts['air-11']['feasible'] is True
    assert '4,000' in result[12]['response'] and 'NOT FEASIBLE' in result[12]['response']
    assert result[13]['planning_result']['planning_request']['shipment']['weight_kg']==4000
    assert 'weight in kg' not in result[13]['response']
    assert all('UDRPU' not in r['response'] for r in result)
    assert tower.detail(702,stale['run_id'])['schedule']==stale['schedule']

@pytest.mark.parametrize('message',[MESSAGES[3],'6E 5355 ka ETA kya hai?','6E 5355 की ETA क्या है?'])
def test_explicit_flight_overrides_ui_without_conversation(environment,message):
    result=chat(message,environment[2],message)
    assert '6E 5355' in result['response'] and '21:25' in result['response'] and 'UDRPU' not in result['response']

@pytest.mark.parametrize('message',['CJBMB se BLRGW ke liye kya services hain?','CJBMB से BLRGW के लिए कौन-कौन सी services available हैं?','What services are available from Coimbatore to Bengaluru?'])
def test_multilingual_lookup_same_repository(environment,message):
    result=chat(message,environment[2],message)
    assert {r['service'] for r in result['services']}=={'TATA 407','6E 5355'}

def test_unknown_explicit_flight_does_not_inherit_context(environment):
    stale=environment[2];chat(MESSAGES[0],stale)
    r=chat('What is ETA of flight 6E 9999?',stale)
    assert 'not present' in r['response'] and '6E 5355' not in r['response']

@pytest.mark.asyncio
async def test_llm_only_extracts_language_entities(monkeypatch):
    from backend import chat_normalization as module
    class Model:
        async def ainvoke(self,messages):
            class Result:content=json.dumps(dict(intent='SCHEDULE_LOOKUP',origin='UDRPU',destination='DELGW',identifier='6E 9999',weight_kg=2000,delay_minutes=30))
            return Result()
    monkeypatch.setattr(module,'language_model',lambda:Model())
    value,source=await normalize('What is ETD and ETA of flight 6E 5355?')
    assert source=='llm-normalization' and value.origin is None and value.identifier is None and value.weight_kg is None and value.delay_minutes is None

@pytest.mark.parametrize('ready,air,surface',[('17:59',True,True),('18:00',True,True),('18:01',False,True),('21:30',False,True),('21:31',False,False)])
def test_source_cutoff_boundary_and_midnight(ready,air,surface):
    r=evaluate(load_schedules(),EligibilityInput(origin_station='CJBMB',gateway='BLRGW',simulation_date=date(2026,10,9),shipment_ready_datetime=datetime.fromisoformat('2026-10-09T'+ready+':00+05:30')))
    values={c['mode']:c for c in r['candidates']}
    assert values['AIR']['eligible']==air and values['SURFACE']['eligible']==surface
    assert values['SURFACE']['eta'].strftime('%Y-%m-%d %H:%M')=='2026-10-10 06:00'
    if not surface:
        assert r['selected'] is None and r['next_eligible']['service']=='6E 5355'
        assert r['next_eligible']['etd'].date()==date(2026,10,10)

def test_accelerated_source_playback_and_delay_transitions(environment,monkeypatch):
    tower,rows,stale=environment
    monkeypatch.setattr(routes,'service',tower)
    app=FastAPI();app.include_router(routes.router);app.dependency_overrides[get_current_user]=lambda:{'user_id':702}
    client=TestClient(app)
    result=client.post('/operations/control-tower/playback',json={'service_date':'2026-10-09'})
    assert result.status_code==200 and result.json()['playback_speed']==600
    assert len(tower.runs(702,date(2026,10,9)))==38
    cjb=next(r for r in tower.runs(702) if r['schedule_id']=='surface-25')
    sim=runtime.get(702,cjb['movement_id']);assert sim.paused is False
    source=deepcopy(cjb['schedule']);start=sim.snapshot()
    sim.advance(sim.last_wall+5)
    current=tower.detail(702,cjb['run_id']);snap=current['movement']
    assert 0<start['progress']<snap['progress']<1
    assert start['latitude']!=snap['latitude'] and current['elapsed_hours']>cjb['elapsed_hours']
    assert current['estimated_time_left_hours']<cjb['estimated_time_left_hours'] and current['status']=='ON TIME'
    inject(sim,DisruptionInput(event_type='SLOWDOWN',expected_delay_minutes=30))
    assert tower.detail(702,cjb['run_id'])['status']=='EXPECTED DELAY'
    tower.mark_critical(702,cjb['run_id'],True)
    target=sim.selected['eta']+timedelta(minutes=6)
    sim.advance(sim.last_wall+(target-sim.now).total_seconds()/sim.speed)
    tower.observe(702)
    delayed=tower.detail(702,cjb['run_id']);assert delayed['status']=='DELAYED' and delayed['critical'] is True
    sim.advance(sim.last_wall+(sim.current_eta-sim.now).total_seconds()/sim.speed+1)
    tower.observe(702)
    final=tower.detail(702,cjb['run_id']);assert final['status']=='ARRIVED' and final['estimated_time_left_hours']==0
    assert final['schedule']==source and final['planned_eta']==cjb['planned_eta']

def test_playback_authentication():
    app=FastAPI();app.include_router(routes.router)
    assert TestClient(app).post('/operations/control-tower/playback',json={'service_date':'2026-10-09'}).status_code in (401,403)


def test_operational_lookup_resolves_explicit_flight_over_stale_selection(environment):
    result=chat('What is the status of flight 6E 5355?',environment[2],'operational')
    assert '6E 5355' in result['response'] and 'Current ETA' in result['response'] and 'UDRPU' not in result['response']


@pytest.mark.parametrize('message',['Compare Air and Surface.','Air vs Surface: which arrives first?','Air aur Surface compare karo.','Air और Surface में कौन पहले पहुंचेगा?'])
def test_compare_multiple_modes_keeps_both(environment,message):
    stale=environment[2];chat(MESSAGES[0],stale)
    result=chat(message,stale)
    assert {r['mode'] for r in result['services']}=={'AIR','SURFACE'}


def test_explicit_planning_mode_and_numeric_capacity_priority(environment):
    stale=environment[2]
    result=chat('Plan 2000 kg from CJBMB to BLRGW by Air.',stale)
    assert {p['mode'] for p in result['planning_result']['candidate_plans']}=={'air'}
    result=chat('Can the Surface option carry 4000 kg?',stale)
    assert result['capacity_results'][0]['required_weight_kg']==4000
    assert result['capacity_results'][0]['feasible'] is False
    result=chat('Which option can carry it?',stale)
    assert all(r['required_weight_kg']==4000 for r in result['capacity_results'])


def test_selected_multi_run_comparison_and_antecedent(environment):
    _,rows,stale=environment
    chosen=[r for r in rows if r['schedule_id'] in {'air-11','surface-25','air-2'}]
    assert len(chosen)>=2
    req=ChatInput(message='Compare selected routes.',session_id='multi',operational_service_date='2026-10-09',selected_operational_run_ids=[r['run_id'] for r in chosen],selected_operational_run_id=stale['run_id'])
    result=answer(702,req)
    assert {r['schedule_id'] for r in result['services']}=={r['schedule_id'] for r in chosen}
    result=answer(702,req.model_copy(update={'message':'Which arrives first?'}))
    assert {r['schedule_id'] for r in result['services']}=={r['schedule_id'] for r in chosen}
    result=answer(702,req.model_copy(update={'message':'What is ETA of flight 6E 5355?'}))
    assert len(result['services'])==1 and result['services'][0]['service']=='6E 5355'


def test_invalid_numeric_input_returns_validation_response(monkeypatch):
    from backend.client_api import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app=FastAPI();app.include_router(router);app.dependency_overrides[get_current_user]=lambda:{'user_id':702}
    response=TestClient(app).post('/mcp-agent',json={'message':'Plan 0 kg from CJBMB to BLRGW.'})
    assert response.status_code==422


@pytest.mark.parametrize('message',['What is ETA of flight ZZ 1234?','What is ETA of CJBMB-UNKNOWN?'])
def test_unknown_entities_never_reuse_previous_pair(environment,message):
    chat(MESSAGES[0],environment[2],'unknown')
    result=chat(message,environment[2],'unknown')
    assert 'not present' in result['response'] and '6E 5355' not in result['response']


@pytest.mark.parametrize('message',['What is the revised ETA?','What is the updated ETA?'])
def test_revised_eta_followup_uses_active_service_delay(environment,message):
    stale=environment[2];chat(MESSAGES[0],stale,'delay-followup')
    chat('Delay the CJBMB-BLRGW Surface run by 30 minutes.',stale,'delay-followup')
    result=chat(message,stale,'delay-followup')
    assert result['scenario']['service_id']=='surface-25'
    assert result['scenario']['delay_minutes']==30 and '06:30 IST' in result['response']
    explicit=chat('What is ETA of flight 6E 5355?',stale,'delay-followup')
    assert '22:40 IST' in explicit['response'] and '06:30 IST' not in explicit['response']
