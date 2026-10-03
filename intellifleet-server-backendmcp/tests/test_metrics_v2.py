from copy import deepcopy
from datetime import datetime, timezone, timedelta
import pytest
from backend.planning.metrics_v2 import risk, additional_air_cost
from backend.planning.service import PlanningService
from backend.planning.models import PlanningRequest


@pytest.mark.parametrize('mode', ['road','air'])
def test_risk_bounds_and_zero(mode):
    legs=[dict(route_type=mode,reliability=0,distance=100,operational_risk=0)]
    resources=[dict(reliability=0)]
    result=risk(legs, 1, resources, resources)
    assert result['vehicle']==1 and result['warehouse']==1 and result['route']==1
    for delta in [-100,100]:
        assert all(0<=v<=1 for v in risk(legs, 1, resources, resources, {'risk_delta':delta}).values())


def test_air_cost_keeps_legitimate_additions():
    assert additional_air_cost(dict(route_type='air',base_transport_cost=100,air_cost=100))==0
    assert additional_air_cost(dict(route_type='air',base_transport_cost=100,air_cost=25))==25
    assert additional_air_cost(dict(route_type='air',base_transport_cost=100,air_cost=100,air_cost_is_additional=True))==100


def test_multimodal_projected_availability_and_utilization():
    start=datetime(2030,1,1,tzinfo=timezone.utc)
    legs=[dict(route_id=1,from_location='A',to_location='B',distance=100,duration=2,cost=100,route_type='road',reliability=0),
          dict(route_id=2,from_location='B',to_location='C',distance=200,duration=1,cost=200,route_type='air',reliability=.9)]
    vehicles=[dict(id=1,label='T',type='truck',capacity=1000,current_location='A',is_available=1),
              dict(id=2,label='P',type='plane',capacity=2000,current_location='B',is_available=1,available_from=(start+timedelta(hours=3)).isoformat())]
    req=PlanningRequest(source='A',destination='C',shipment={'weight_kg':500})
    plan=PlanningService(':memory:')._candidate(legs,req,vehicles,start_at=start)
    assert plan['segment_utilizations']==[.5,.25]
    assert plan['vehicle_utilization']==.375
    assert plan['departure_wait_hours']==.5
    assert plan['reliability']==0
    assert all(0<=v<=1 for v in plan['risk_breakdown'].values())
    assert plan['duration_hours']==4.75
    expired=deepcopy(vehicles)
    expired[1]['available_until']=(start+timedelta(hours=2)).isoformat()
    assert PlanningService(':memory:')._candidate(legs,req,expired,start_at=start) is None
