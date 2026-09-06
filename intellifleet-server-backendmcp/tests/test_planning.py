from datetime import datetime, timedelta, timezone

import pytest

from backend.planning.models import PlanningRequest, Shipment
from backend.planning.service import PlanningService


NETWORK = {
    "routes": [
        {"route_id": 1, "from_location": "Delhi", "to_location": "Jaipur", "distance": 280, "duration": 5, "cost": 4000, "route_type": "road"},
        {"route_id": 2, "from_location": "Jaipur", "to_location": "Mumbai", "distance": 1150, "duration": 18, "cost": 9000, "route_type": "road"},
        {"route_id": 3, "from_location": "Delhi", "to_location": "Mumbai", "distance": 1400, "duration": 20, "cost": 16000, "route_type": "road"},
        {"route_id": 4, "from_location": "Delhi", "to_location": "Mumbai", "distance": 1160, "duration": 3, "cost": 50000, "route_type": "air"},
    ],
    "warehouses": [
        {"warehouse_id": 1, "name": "Delhi", "inventory": 60, "reserved_inventory": 0, "is_active": 1},
        {"warehouse_id": 2, "name": "Jaipur", "inventory": 70, "reserved_inventory": 10, "is_active": 1},
    ],
    "vehicles": [
        {"id": 1, "label": "T1", "type": "truck", "capacity": 800, "current_location": "Delhi", "is_available": 1, "is_active": 1},
        {"id": 2, "label": "T2", "type": "truck", "capacity": 500, "current_location": "Delhi", "is_available": 1, "is_active": 1},
        {"id": 3, "label": "P1", "type": "plane", "capacity": 2000, "current_location": "Delhi", "is_available": 1, "is_active": 1},
    ],
}


def req(objective="balanced", deadline=None, weight=1000, quantity=100, modes=None):
    return PlanningRequest(source="Delhi", destination="Mumbai", shipment=Shipment(weight_kg=weight, quantity=quantity),
                           objective=objective, deadline=deadline, allowed_modes=modes or ["road", "air", "multimodal"])


@pytest.fixture
def service():
    PlanningService._scenarios.clear()
    return PlanningService(":memory:")


def test_cheapest_route(service):
    assert service.plan(1, req("cheapest"), NETWORK)["recommended_plan"]["operational_cost"] == 13250


def test_fastest_route(service):
    assert service.plan(1, req("fastest"), NETWORK)["recommended_plan"]["mode"] == "air"


def test_balanced_route(service):
    plan = service.plan(1, req(), NETWORK)["recommended_plan"]
    assert plan["score"] >= 0
    assert plan["score_components"]["balanced_score"] == plan["score"]
    assert "weighted_contributions" in plan["score_components"]


def test_express_vs_ground(service):
    modes = {p["mode"] for p in service.plan(1, req(), NETWORK)["candidate_plans"]}
    assert {"road", "air"} <= modes


def test_sla_pass_and_fail(service):
    good = service.plan(1, req("fastest", datetime.now(timezone.utc) + timedelta(hours=5)), NETWORK)
    bad = service.plan(1, req("fastest", datetime.now(timezone.utc) + timedelta(hours=1)), NETWORK)
    assert good["recommended_plan"]["sla_met"] is True and bad["recommended_plan"]["sla_met"] is False


def test_multi_vehicle_capacity(service):
    plan = service.plan(1, req(weight=1200, modes=["road"]), NETWORK)["recommended_plan"]
    assert len(plan["vehicles"]) == 2 and plan["vehicle_utilization"] == pytest.approx(1200 / 1300, .001)


def test_insufficient_vehicle_capacity(service):
    result=service.plan(1, req(weight=5000, modes=["road"]), NETWORK)
    assert result["recommended_plan"] is None
    assert result["warnings"]==["No feasible route found"]


def test_multi_warehouse_allocation(service):
    allocation = service.plan(1, req(quantity=100), NETWORK)["recommended_plan"]["inventory_allocation"]
    assert [x["quantity"] for x in allocation] == [60, 40]


def test_disruption_rerouting(service):
    result = service.plan(1, req(modes=["road"]), NETWORK, {"blocked_routes": [["Delhi", "Jaipur"]]})
    assert [x["route_id"] for x in result["recommended_plan"]["route_legs"]] == [3]


def test_scenario_isolation_and_apply(service):
    service.load_network = lambda _: NETWORK
    scenario = service.create_scenario(1, req(), {"fuel_cost_multiplier": 1.2})
    assert scenario["status"] == "draft" and scenario["scenario"]["recommended_plan"]["operational_cost"] > scenario["baseline"]["recommended_plan"]["operational_cost"]
    applied = service.scenario_action(1, scenario["scenario_id"], "apply")
    assert applied["live_data_changed"] is False and applied["status"] == "applied"


def test_scenario_discard(service):
    service.load_network = lambda _: NETWORK
    scenario = service.create_scenario(1, req(), {})
    assert service.scenario_action(1, scenario["scenario_id"], "discard")["status"] == "discarded"


def test_risk_is_deterministic(service):
    legs = NETWORK["routes"][:1]
    assert service.risk_score(legs, .8) == service.risk_score(legs, .8)


def test_pricing_margin(service):
    plan = service.plan(1, req("cheapest"), NETWORK)["recommended_plan"]
    assert plan["selling_price"] == pytest.approx(plan["operational_cost"] / .8, .01)


def test_route_comparison(service):
    assert service.plan(1, req(), NETWORK)["comparison"]


def test_multi_stop_routing(service):
    request = req(modes=["road"])
    request.intermediate_stops = ["Jaipur"]
    assert [x["route_id"] for x in service.plan(1, request, NETWORK)["recommended_plan"]["route_legs"]] == [1, 2]

def test_warehouse_capacity(service):
    network={**NETWORK,"warehouses":[{"warehouse_id":1,"name":"Delhi","inventory":60,"reserved_inventory":10,"storage_capacity":100,"is_active":1}]}
    service.load_network=lambda _:network
    item=service.warehouse_capacity(1)["warehouses"][0]
    assert item["available_storage"]==40 and item["available_inventory"]==50 and item["utilization_percentage"]==60

def test_alternative_warehouse_fulfilment(service):
    network={**NETWORK,"vehicles":[*NETWORK["vehicles"],
        {"id":4,"label":"J1","type":"truck","capacity":800,"current_location":"Jaipur","is_available":1,"is_active":1}]}
    service.load_network=lambda _:network
    result=service.fulfilment(1,"Mumbai",100,1000,"cheapest")
    assert result["fulfilled"] and len(result["allocation"])==2
    assert len(result["ranked_alternatives"])>=2


def test_route_alternative_reports_vehicle_range_constraint(service):
    network={**NETWORK,"vehicles":[{**NETWORK["vehicles"][0],"capacity":2000,"max_range_km":150}]}
    service.load_network=lambda _:network
    request=req(modes=["road"])
    result=service.plan(1,request,changes={"blocked_routes":[["Delhi","Mumbai"]]})
    assert result["recommended_plan"] is None
    assert result["feasibility"]["constraint"]=="vehicle_capacity_or_full_route_range"
    assert "vehicle" in result["reason"] and result["feasibility"]["alternative_route"]==["Delhi","Jaipur","Mumbai"]


def test_global_multimodal_distinguishes_direct_air_from_gateway_chain(service):
    network={**NETWORK,"warehouses":[
        {**NETWORK["warehouses"][0],"country":"India","city":"Delhi","nearest_airport_iata":"DEL"},
        {"warehouse_id":3,"name":"Frankfurt","country":"Germany","city":"Frankfurt","nearest_airport_iata":"FRA","inventory":10,"is_active":1}],
        "routes":[*NETWORK["routes"],{"route_id":9,"from_location":"Delhi","to_location":"Frankfurt","distance":6000,"duration":9,"cost":500000,"route_type":"air"}]}
    service.load_network=lambda _:network
    request=PlanningRequest(source="Delhi",destination="Frankfurt",source_country="India",destination_country="Germany",
                            shipment=Shipment(weight_kg=100,quantity=1),allowed_modes=["multimodal"])
    result=service.global_plan(1,request)
    assert result["recommended_plan"] and result["requested_multimodal_feasible"] is False
    assert "road-to-airport" in result["warnings"][0]

def test_vehicle_breakdown_recovery(service):
    service.load_network=lambda _:NETWORK
    result=service.breakdown_recovery(1,"T1","Delhi","Mumbai",400)
    assert result["recovery_plan"] and all(x["label"]!="T1" for x in result["replacement_vehicles"])

def test_breakdown_recovery_recomputes_eta_sla_and_incremental_cost(service):
    service.load_network=lambda _:NETWORK
    deadline=datetime.now(timezone.utc)+timedelta(hours=1)
    result=service.breakdown_recovery(1,"T1","Delhi","Mumbai",400,deadline)
    plan=result["recovery_plan"]
    assert result["additional_cost"]==plan["operational_cost"]
    assert "sunk" in result["additional_cost_basis"]
    assert result["new_eta"]==plan["eta"]
    assert result["sla_met"] is False and plan["sla_delay_hours"]>0
    assert sum(x["capacity"] for x in result["replacement_vehicles"])>=400

def test_optimized_stop_sequence(service):
    service.load_network=lambda _:NETWORK
    result=service.optimize_stops(1,"Delhi","Mumbai",["Jaipur"],{"weight_kg":100,"quantity":1},"cheapest")
    assert result["optimized_stop_sequence"]==["Jaipur"]

def test_consolidation(service):
    service.load_network=lambda _:NETWORK
    result=service.consolidate(1,[{"shipment_id":"a","source":"Delhi","destination":"Mumbai","weight_kg":300},
                                  {"shipment_id":"b","source":"Delhi","destination":"Mumbai","weight_kg":400}])
    assert result["consolidation_opportunities"][0]["vehicle_utilization"]>0

def test_transport_scope():
    assert PlanningService.transport_scope("India","India")["scope"]=="domestic"
    assert PlanningService.transport_scope("India","France")["gateway_required"] is True

def test_expansion_cost():
    from backend.planning.models import ExpansionRequest
    result=PlanningService.expansion(ExpansionRequest(demand_locations=[{"latitude":1,"longitude":1,"demand":10}],
        candidate_hubs=[{"name":"A","latitude":1.1,"longitude":1.1}],hubs_to_open=1))
    assert result["recommended_hubs"][0]["incremental_cost"] is None
    assert "transport rate" in result["recommended_hubs"][0]["missing_assumptions"]

def test_lowest_risk_profile(service):
    result=service.plan(1,req("lowest-risk"),NETWORK)
    assert result["recommended_plan"]["risk_score"]==min(x["risk_score"] for x in result["candidate_plans"])

def test_baseline_scenario_comparison(service):
    service.load_network=lambda _:NETWORK
    result=service.create_scenario(1,req(),{"blocked_routes":[["Delhi","Jaipur"]]})
    assert result["baseline"]["recommended_plan"] and result["scenario"]["recommended_plan"]

def test_future_shipment_replanning(service,tmp_path):
    import sqlite3
    db=tmp_path/"schedule.db"; service.db_path=str(db)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE shipments(shipment_id TEXT,user_id INTEGER,assigned_vehicle_ids TEXT,scheduled_start TEXT,scheduled_end TEXT,deadline TEXT)")
        now=datetime.now(timezone.utc); conn.execute("INSERT INTO shipments VALUES(?,?,?,?,?,?)",("S1",1,'[\"T1\"]',now.isoformat(),(now+timedelta(hours=2)).isoformat(),(now+timedelta(hours=3)).isoformat()))
    service.load_network=lambda _:NETWORK
    result=service.future_replan(1,"T1",2)
    assert result["cascading_delays"]==1 and result["affected_shipments"][0]["sla_met"] is False

@pytest.mark.asyncio
async def test_atomic_three_csv_upload(tmp_path,monkeypatch):
    import io,sqlite3
    from starlette.datastructures import UploadFile
    from backend.database.database import init_db
    from backend.planning.database import migrate_planning_schema
    from backend.routes.upload.network_upload import upload_network
    monkeypatch.chdir(tmp_path); init_db(); migrate_planning_schema()
    with sqlite3.connect("users.db") as conn:
        conn.execute("INSERT INTO users(id,first_name,last_name,email,password,verified) VALUES(1,'Test','User','test@example.invalid','x',1)")
    warehouse=b"Country,City,NodeType,Name,Address,Inventory,ReorderLevel,Latitude,Longitude,StorageCapacity,ReservedInventory,HandlingCostPerUnitINR,ReliabilityScore,NearestAirportIATA\nIndia,Delhi,Hub,Delhi,A,100,10,28.6,77.2,500,15,2.5,.95,DEL\nIndia,Mumbai,Hub,Mumbai,B,80,5,19.1,72.9,400,5,3,.9,BOM\n"
    vehicle=b"WarehouseName,VehicleType,VehicleCapacity,DepartureTime,VehicleID,Mode,CostPerKmINR,FixedDispatchCostINR,ReliabilityScore,BreakdownRiskScore,MaxRangeKm,LoadingTimeMin,UnloadingTimeMin,ExpressEligible\nDelhi,Truck,2000,08:00,T1,road,20,500,.96,.03,2000,30,20,true\n"
    routes=b"Source,Destination,IntermediateLocation,RouteType,RouteID,DistanceKm,TypicalDurationMin,TollCostINR,BaseTransportCostINR,ReliabilityScore,DisruptionRiskScore,WeatherRiskScore,Status,ServiceClass,ExpressEligible\nDelhi,Mumbai,,road,101,1400,1200,900,15000,.94,.04,.02,active,ground,true\n"
    result=await upload_network(UploadFile(io.BytesIO(warehouse),filename="w.csv"),UploadFile(io.BytesIO(vehicle),filename="v.csv"),UploadFile(io.BytesIO(routes),filename="r.csv"),{"user_id":1})
    assert result["warehouses"]==2 and result["vehicles"]==1 and result["routes"]==1 and result["processing_time_ms"]<1000
    with sqlite3.connect("users.db") as conn:
        assert conn.execute("select count(*) from warehouses where user_id=1").fetchone()[0]==2
        assert conn.execute("select reserved_inventory,nearest_airport_iata from warehouse_inventory where user_id=1 and warehouse_name='Delhi'").fetchone()==(15.0,"DEL")
        assert conn.execute("select fixed_dispatch_cost,max_range_km from vehicles where user_id=1 and label='T1'").fetchone()==(500.0,2000.0)
        assert conn.execute("select toll_cost,service_class from route_conditions where user_id=1 and route_id=1").fetchone()==(900.0,"ground")
        stored=conn.execute("select route_data from persistent_routes where user_id=1 and route_id=1").fetchone()
        assert stored and '"external_route_id": "101"' in stored[0]

def test_network_plan_structure(service):
    plan=service.plan(1,req(),NETWORK)["recommended_plan"]
    assert plan["route_legs"] and plan["distance_km"]>0 and plan["vehicles"] and plan["mode"]

def test_complete_cost_breakdown(service):
    breakdown=service.plan(1,req(),NETWORK)["recommended_plan"]["cost_breakdown"]
    expected={"base_transport","distance_cost","fuel_cost","toll_cost","fixed_dispatch_cost","driver_time_cost","vehicle_cost","handling_cost","air_cost","other_cost"}
    assert expected==set(breakdown) and sum(breakdown.values())>0

def test_configurable_balanced_weights(service):
    request=req(); request.scoring_weights.cost=1; request.scoring_weights.eta=0; request.scoring_weights.risk=0; request.scoring_weights.reliability=0; request.scoring_weights.sla=0; request.scoring_weights.utilization=0
    assert service.plan(1,request,NETWORK)["recommended_plan"]["operational_cost"]==min(x["operational_cost"] for x in service.plan(1,request,NETWORK)["candidate_plans"])

def test_express_ground_numeric_comparison(service):
    service.load_network=lambda _:NETWORK
    result=service.compare_modes(1,req())
    assert result["options"]["ground"] and result["options"]["express"] and result["express_vs_ground"]["time_saved_hours"]>0
    assert result["express_vs_ground"]["sla_comparison"] == {
        "ground": result["options"]["ground"]["sla_met"],
        "express": result["options"]["express"]["sla_met"],
    }
    assert result["planning_request"]["shipment"]["weight_kg"]==1000
    assert result["options"]["multimodal"]


@pytest.mark.asyncio
async def test_compare_modes_is_exposed_through_mcp(monkeypatch):
    from backend.mcp.tools.tool_client import load_mcp_tools
    monkeypatch.setattr(PlanningService, "load_network", lambda self, _: NETWORK)
    tools = await load_mcp_tools()
    operation = next(x for x in tools if x.name == "supply_chain_planning_operation")
    result = await operation.ainvoke({"user_id": 1, "operation": "compare_modes",
                                     "parameters": req().model_dump(mode="json")})
    assert result["options"]["ground"] and result["options"]["express"]
    assert result["express_vs_ground"]

def test_route_comparison_complete_deltas(service):
    comparison=service.plan(1,req(),NETWORK)["comparison"][0]
    assert {"money_saved","money_lost","time_saved_hours","time_lost_hours","sla_difference","utilization_difference"}<=set(comparison)

def test_risk_breakdown_normalized():
    result=PlanningService.risk_breakdown(NETWORK["routes"][:1],.8,NETWORK["vehicles"][:1],NETWORK["warehouses"][:1])
    assert set(result)=={"route","vehicle","weather","warehouse","mode","overall"} and all(0<=x<=1 for x in result.values())

def test_disruption_mitigation_comparison(service):
    service.load_network=lambda _:NETWORK
    result=service.disruption_mitigation(1,req(modes=["road"]),{"blocked_routes":[["Delhi","Jaipur"]]})
    assert result["recovery_plan"] and result["comparison"] and all(x["route_id"]!=1 for x in result["recovery_plan"]["route_legs"])

def test_disruption_mitigation_reports_risk_and_mode_resources(service):
    service.load_network=lambda _:NETWORK
    risk=service.disruption_mitigation(1,req(),{"risk_delta":.2})
    mode=service.disruption_mitigation(1,req(),{"allowed_modes":["road"]})
    assert risk["affected_resources"]=={"risk_delta":.2}
    assert mode["affected_resources"]=={"allowed_modes":["road"]}

def test_unavailable_warehouse_is_excluded_from_route_graph(service):
    service.load_network=lambda _:NETWORK
    result=service.plan(1,req(modes=["road"]),changes={"unavailable_warehouses":["Jaipur"]})
    assert all("Jaipur" not in {leg["from_location"],leg["to_location"]}
               for plan in result["candidate_plans"] for leg in plan["route_legs"])

def test_vehicle_per_vehicle_utilization(service):
    plan=service.plan(1,req(weight=1200,modes=["road"]),NETWORK)["recommended_plan"]
    assert all(v["utilization_percentage"]==pytest.approx(1200/1300*100,.01) for v in plan["vehicles"])
    assert sum(v["assigned_load_kg"] for v in plan["vehicles"]) == pytest.approx(1200, .01)
    assert all(v["assigned_load_kg"] <= v["capacity"] for v in plan["vehicles"])


@pytest.mark.parametrize("weight", [6000, 8000, 10000, 18000])
def test_assigned_load_is_exact_and_conserved(service, weight):
    network={**NETWORK,
        "warehouses":[{**warehouse,"inventory":100000} for warehouse in NETWORK["warehouses"]],
        "vehicles":[
            {**NETWORK["vehicles"][0],"capacity":12000,"label":"BIG"},
            {**NETWORK["vehicles"][1],"capacity":7000,"label":"SECOND"},
            NETWORK["vehicles"][2],
        ]}
    plan=service.plan(1,req(weight=weight,quantity=1,modes=["road"]),network)["recommended_plan"]
    loads=[vehicle["assigned_load_kg"] for vehicle in plan["vehicles"]]
    assert sum(loads) == pytest.approx(weight, abs=1e-6)
    if len(loads)==1: assert loads[0] == weight
    assert all(load <= vehicle["capacity"] for load,vehicle in zip(loads,plan["vehicles"]))

def test_vehicle_selection_enforces_required_range():
    vehicles=[
      {"id":1,"label":"SHORT","type":"truck","capacity":2000,"current_location":"Delhi","is_available":1,"is_active":1,"max_range_km":500,"reliability":.99},
      {"id":2,"label":"LONG","type":"truck","capacity":2000,"current_location":"Delhi","is_available":1,"is_active":1,"max_range_km":2000,"reliability":.9},
    ]
    chosen,_=PlanningService.select_vehicles(vehicles,"Delhi",1000,"road",1400)
    assert [x["label"] for x in chosen]==["LONG"]

def test_sla_mandatory_discards_late_plans(service):
    request=req(deadline=datetime.now(timezone.utc)+timedelta(minutes=1)); request.sla_mandatory=True
    assert service.plan(1,request,NETWORK)["recommended_plan"] is None

def test_what_if_request_changes_are_isolated(service):
    service.load_network=lambda _:NETWORK
    original=repr(NETWORK)
    result=service.create_scenario(1,req(),{"demand_weight_kg":1500,"allowed_modes":["road"],"cost_multiplier":1.1,"risk_delta":.1})
    assert result["scenario"]["planning_request"]["shipment"]["weight_kg"]==1500 and repr(NETWORK)==original

def test_scenario_comparison_fields(service):
    service.load_network=lambda _:NETWORK
    comparison=service.create_scenario(1,req(),{"fuel_cost_multiplier":1.2})["comparison"]
    assert {"cost_difference","eta_difference_hours","risk_difference","sla","vehicle_utilization","routes","modes","vehicles","inventory_allocation"}==set(comparison)

def test_international_gateway_plan(service):
    network={"routes":[
        {"route_id":1,"from_location":"Delhi","to_location":"DEL","distance":20,"duration":1,"cost":500,"route_type":"road"},
        {"route_id":2,"from_location":"DEL","to_location":"FRA","distance":6100,"duration":9,"cost":90000,"route_type":"air"},
        {"route_id":3,"from_location":"FRA","to_location":"Berlin","distance":550,"duration":7,"cost":9000,"route_type":"road"}],
        "warehouses":[{"warehouse_id":1,"name":"Delhi","inventory":10,"reserved_inventory":0,"is_active":1,"nearest_airport_iata":"DEL"},{"warehouse_id":2,"name":"Berlin","inventory":0,"reserved_inventory":0,"is_active":1,"nearest_airport_iata":"FRA"}],
        "vehicles":[*NETWORK["vehicles"], {**NETWORK["vehicles"][2],"id":4,"label":"FRA-AIR","current_location":"DEL"}, {**NETWORK["vehicles"][0],"id":5,"label":"FRA-ROAD","current_location":"FRA"}]}
    service.load_network=lambda _:network
    request=PlanningRequest(source="Delhi",destination="Berlin",source_country="India",destination_country="Germany",shipment=Shipment(weight_kg=100,quantity=1))
    result=service.global_plan(1,request)
    assert result["scope"]=="international" and result["gateway_sequence"]==["Delhi","DEL","FRA","Berlin"] and result["recommended_plan"]

def test_recommendation_is_candidate(service):
    result=service.plan(1,req(),NETWORK)
    assert result["recommended_plan_id"] in {x["plan_id"] for x in result["candidate_plans"]}

def test_explanation_uses_calculated_metrics(service):
    result=service.plan(1,req(),NETWORK)
    assert result["explanation_inputs"]["recommended"]["operational_cost"]==result["recommended_plan"]["operational_cost"]

def test_network_expansion_selects_minimum_cost_hub():
    from backend.planning.models import ExpansionRequest
    result=PlanningService.expansion(ExpansionRequest(demand_locations=[{"latitude":0,"longitude":0,"demand":100}],
        candidate_hubs=[{"name":"Near","latitude":.1,"longitude":.1},{"name":"Far","latitude":10,"longitude":10}]))
    assert result["recommended_hubs"][0]["hub"]=="Near"

def test_unified_planning_workflow(service):
    result=service.plan(1,req(),NETWORK); plan=result["recommended_plan"]
    assert result["planning_request"] and plan["route_legs"] and plan["vehicles"] and plan["inventory_allocation"]
    assert plan["cost_breakdown"] and plan["risk_breakdown"] and result["recommended_plan_id"]


def test_city_names_resolve_to_uploaded_warehouse_nodes(service):
    network = {
        "routes": [{"route_id": 1, "from_location": "IF Delhi Hub", "to_location": "IF Kochi Hub",
                    "distance": 2000, "duration": 10, "cost": 10000, "route_type": "road"}],
        "warehouses": [
            {"warehouse_id": 1, "name": "IF Delhi Hub", "city": "New Delhi", "inventory": 10,
             "reserved_inventory": 0, "is_active": 1},
            {"warehouse_id": 2, "name": "IF Kochi Hub", "city": "Kochi", "inventory": 0,
             "reserved_inventory": 0, "is_active": 1},
        ],
        "vehicles": [{"id": 1, "label": "T1", "type": "truck", "capacity": 1000,
                      "current_location": "IF Delhi Hub", "is_available": 1, "is_active": 1}],
    }
    request = PlanningRequest(source="Delhi", destination="Kochi",
                              shipment=Shipment(weight_kg=500, quantity=1), allowed_modes=["road"])
    result = service.plan(1, request, network)
    assert result["recommended_plan_id"]
    assert result["planning_request"]["source"] == "IF Delhi Hub"
    assert result["planning_request"]["destination"] == "IF Kochi Hub"
