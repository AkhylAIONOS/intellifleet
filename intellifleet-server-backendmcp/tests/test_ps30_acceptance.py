"""Expanded acceptance regressions: actual engines, no fabricated success responses."""
import copy
from datetime import datetime, timedelta, timezone
import pytest
from backend.planning.service import PlanningService
from test_planning import NETWORK, req


def test_feasible_path_not_hidden_by_cheaper_out_of_range_paths():
    network=copy.deepcopy(NETWORK)
    network['routes'].append({'route_id':99,'from_location':'Delhi','to_location':'Mumbai','distance':100,'duration':30,'cost':50000,'route_type':'road'})
    for v in network['vehicles']:v['max_range_km']=200
    result=PlanningService(':memory:').plan(1,req(modes=['road']),network)
    assert [x['route_id'] for x in result['recommended_plan']['route_legs']]==[99]


def test_risk_limit_is_hard_constraint():
    request=req(); request.max_risk=0
    result=PlanningService(':memory:').plan(1,request,NETWORK)
    assert result['recommended_plan'] is None
    assert 'risk' in result['reason']


def test_cheapest_prefers_sla_feasible_option():
    result=PlanningService(':memory:').plan(1,req('cheapest',datetime.now(timezone.utc)+timedelta(hours=6)),NETWORK)
    assert result['recommended_plan']['sla_met'] is True


@pytest.mark.parametrize('action',['typo','approve','delete'])
def test_unknown_scenario_action_never_applies(action):
    service=PlanningService(':memory:'); service.load_network=lambda _:NETWORK
    draft=service.create_scenario(1,req(),{})
    with pytest.raises(ValueError,match='action'):service.scenario_action(1,draft['scenario_id'],action)
    assert service.get_scenario(1,draft['scenario_id'])['status']=='draft'


def test_infeasible_scenario_cannot_apply():
    service=PlanningService(':memory:'); service.load_network=lambda _:NETWORK
    draft=service.create_scenario(1,req(),{'demand_weight_kg':100000})
    with pytest.raises(ValueError,match='infeasible'):service.scenario_action(1,draft['scenario_id'],'apply')
    assert service.get_scenario(1,draft['scenario_id'])['status']=='draft'


def test_unreachable_required_stop_never_silently_dropped():
    service=PlanningService(':memory:'); service.load_network=lambda _:NETWORK
    result=service.optimize_stops(1,'Delhi','Mumbai',['Unconnected'],{'weight_kg':100},'cheapest')
    assert result['recommended_plan'] is None and result['unserved_stops']==['Unconnected']


def test_fulfilment_excludes_inactive_and_explicit_warehouses():
    service=PlanningService(':memory:'); service.load_network=lambda _:NETWORK
    result=service.fulfilment(1,'Mumbai',10,100,'cheapest',excluded_warehouses=['Delhi','Jaipur'])
    assert not result['fulfilled'] and not result['allocation']


def test_fulfilment_recosts_exact_final_allocation():
    network=copy.deepcopy(NETWORK)
    network['warehouses'][0]['inventory']=2
    network['vehicles'].append({**network['vehicles'][0],'id':4,'label':'J1','current_location':'Jaipur'})
    service=PlanningService(':memory:'); service.load_network=lambda _:network
    result=service.fulfilment(1,'Mumbai',5,500,'cheapest')
    assert result['fulfilled'] and sum(x['allocation'] for x in result['allocation'])==5
    assert sum(x['weight_kg'] for x in result['allocation'])==pytest.approx(500)
    for item in result['allocation']:
        assert sum(x['assigned_load_kg'] for x in item['plan']['vehicles'])==pytest.approx(item['weight_kg'])


@pytest.mark.asyncio
async def test_specific_warehouse_alias_through_mcp(monkeypatch):
    from backend.mcp.tools.tool_client import load_mcp_tools
    network=copy.deepcopy(NETWORK)
    network['warehouses'].append({'warehouse_id':8,'name':'IF Bengaluru South Hub','city':'Bengaluru','inventory':50,'storage_capacity':100})
    monkeypatch.setattr(PlanningService,'load_network',lambda self,_:network)
    operation=next(x for x in await load_mcp_tools() if x.name=='supply_chain_planning_operation')
    result=await operation.ainvoke({'user_id':1,'operation':'warehouse_capacity','parameters':{'warehouse_names':['Bengaluru South Hub']}})
    assert [x['warehouse'] for x in result['warehouses']]==['IF Bengaluru South Hub']


def test_relative_deadline_is_calculated_from_baseline():
    from backend.planning.intent import CanonicalPlanningIntent
    result=CanonicalPlanningIntent(operation='create_scenario',parameters={'deadline_advance_hours':8}).resolve({'selected_plan':{'eta':'2026-09-10T20:00:00+05:30'}})
    assert result['changes']['deadline']=='2026-09-10T12:00:00+05:30'


def test_unsupported_scenario_change_is_not_silently_ignored():
    service=PlanningService(':memory:'); service.load_network=lambda _:NETWORK
    with pytest.raises(ValueError,match='Unsupported scenario'):service.create_scenario(1,req(),{'unknown_capacity':-1})


def test_mixed_mode_requires_aircraft_at_transfer_gateway():
    network=copy.deepcopy(NETWORK)
    network['routes']=[{'route_id':1,'from_location':'Delhi','to_location':'Jaipur','route_type':'road','distance':100,'duration':1,'cost':100}, {'route_id':2,'from_location':'Jaipur','to_location':'Mumbai','route_type':'air','distance':1000,'duration':2,'cost':1000}]
    result=PlanningService(':memory:').plan(1,req(weight=100),network)
    assert result['recommended_plan'] is None
    network['vehicles'].append({**network['vehicles'][2],'id':4,'label':'GATEWAY-AIR','current_location':'Jaipur'})
    result=PlanningService(':memory:').plan(1,req(weight=100),network)
    assert result['recommended_plan']['mode']=='multimodal'
    assert result['recommended_plan']['leg_assignments'][1]['vehicles'][0]['label']=='GATEWAY-AIR'


def test_recovery_can_reposition_over_actual_road_legs():
    network=copy.deepcopy(NETWORK)
    network['vehicles']=[{**network['vehicles'][0],'label':'BROKEN','current_location':'Jaipur'}, {**network['vehicles'][1],'label':'REPLACE','max_range_km':2000}]
    service=PlanningService(':memory:');service.load_network=lambda _:network
    result=service.breakdown_recovery(1,'BROKEN','Jaipur','Mumbai',400)
    assert result['recovery_plan']['replacement_approach_legs'][0]['route_id']==1
    assert result['recovery_plan']['repositioning_cost']>0
    assert sum(v['assigned_load_kg'] for v in result['replacement_vehicles'])==400


def test_expansion_does_not_invent_cost_assumptions():
    from backend.planning.models import ExpansionRequest
    result=PlanningService.expansion(ExpansionRequest(candidate_hubs=[{'name':'Hub','latitude':20,'longitude':70}],demand_locations=[{'name':'Store','latitude':21,'longitude':71,'demand':100}]))
    hub=result['recommended_hubs'][0]
    assert hub['incremental_cost'] is None and hub['facility_operating_cost'] is None
    assert result['assignments'][0]['allocated_demand']==100
    assert result['new_connections_required'][0]['route_validated'] is False
