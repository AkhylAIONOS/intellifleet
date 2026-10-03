from datetime import datetime, timedelta
import pytest
from test_operations import loaded
from backend.operations import plan_journeys
from backend.planning.service import PlanningService
from backend.planning.models import PlanningRequest
from backend.fedex.disruptions import inject
from backend.fedex.models import DisruptionInput

@pytest.mark.parametrize('origin,destination,weight',[('Mumbai','Bengaluru',1000),('Delhi','Mumbai',1000)])
def test_authoritative_plan_replay(loaded,monkeypatch,origin,destination,weight):
    _,runtime,clock=loaded
    import backend.fedex.telemetry as telemetry
    monkeypatch.setattr(telemetry,'runtime',runtime)
    plan=PlanningService().plan(1,PlanningRequest(source=origin,destination=destination,shipment={'weight_kg':weight},allowed_modes=['road']))['recommended_plan']
    original={k:plan[k] for k in ('operational_cost','eta','duration_hours','risk_score','reliability','vehicles')}
    a=plan_journeys.start(1,plan['plan_id']);sim=runtime.get(1,a['simulation_id'])
    assert a['progress']==0 and a['paused'] and a['simulation_speed']==120
    assert len(a['route'])>2 and (a['latitude'],a['longitude'])==a['route'][0]
    assert datetime.fromisoformat(a['current_eta'])==datetime.fromisoformat(plan['eta'])
    clock[0]+=300;assert runtime.get(1,sim.id).progress==0
    sim.control('resume',clock[0]);clock[0]+=2;before=runtime.get(1,sim.id).snapshot()
    inject(sim,DisruptionInput(expected_delay_minutes=30));clock[0]+=.1
    delayed=runtime.get(1,sim.id).snapshot()
    assert delayed['latitude']==before['latitude'] and delayed['longitude']==before['longitude']
    assert datetime.fromisoformat(delayed['current_eta'])==datetime.fromisoformat(plan['eta'])+timedelta(minutes=30)
    clock[0]+=(sim.duration+1800)/sim.speed+1;end=runtime.get(1,sim.id).snapshot()
    assert end['progress']==1 and (end['latitude'],end['longitude'])==end['route'][-1]
    replay=plan_journeys.start(1,plan['plan_id']);assert replay['progress']==0 and replay['simulation_id']!=sim.id
    assert original=={k:plan[k] for k in original}
    with pytest.raises(KeyError):plan_journeys.start(2,plan['plan_id'])

def test_expired_plan_cannot_be_replayed():
    with pytest.raises(KeyError):plan_journeys.start(1,'not-a-real-plan')


def test_form_scenario_revision_reuses_movement_and_rejects_stale_baseline(loaded,monkeypatch):
    from copy import deepcopy
    _,runtime,_=loaded
    import backend.fedex.telemetry as telemetry
    monkeypatch.setattr(telemetry,'runtime',runtime)
    plan=PlanningService().plan(1,PlanningRequest(source='Mumbai',destination='Bengaluru',shipment={'weight_kg':1000},allowed_modes=['road']))['recommended_plan']
    baseline=plan_journeys.start(1,plan['plan_id'])
    revised=deepcopy(plan)
    revised.update(plan_id=plan['plan_id']+'-scenario',operational_cost=plan['operational_cost']+100)
    plan_journeys.remember(1,[revised])
    applied=plan_journeys.revise(1,revised['plan_id'],plan['plan_id'])
    assert applied['simulation_id']==baseline['simulation_id']
    assert applied['plan_id']==revised['plan_id'] and applied['revision']==2
    assert len([x for x in runtime.entries.values() if x.owner==1])==1
    with pytest.raises(ValueError):plan_journeys.revise(1,revised['plan_id'],plan['plan_id'])
