import asyncio

from backend.agents.supervisor import (SchemaAwareSupervisor, _normalize_target_margin,
                                       _adapt_canonical_params, _format_planning_result,
                                       _disruption_mitigation_params, _is_mode_comparison,
                                       _is_vehicle_planning_request, _response_text,
                                       _route_disruption_params, _vehicle_selection_params,
                                       _deadline_from_message, _objective_from_message,
                                       _breakdown_recovery_params, _fulfilment_params)
from backend.agents.supervisor import (_weight_kg_from_message, _normalize_objective,
                                       _specialized_operation_params, _scenario_params,
                                       _context_from_result, _contextual_planning_params,
                                       _actual_mode, _mode_label, _is_shipment_plan_request,
                                       _vehicle_text)
from langchain_core.messages import HumanMessage, SystemMessage


def test_missing_azure_deployment_returns_actionable_error_without_ainvoke(monkeypatch):
    from backend.agents import supervisor as supervisor_module

    monkeypatch.setattr(supervisor_module.settings, "AI_PROVIDER", "azure")
    monkeypatch.setattr(supervisor_module.settings, "AZURE_AI_DEPLOYMENT", None)
    instance = SchemaAwareSupervisor()
    result = asyncio.run(instance.process_message(5, "Plan 8,000 kg from Delhi to Kochi"))

    assert result["success"] is False
    assert result["error_code"] == "AZURE_AI_DEPLOYMENT_MISSING"
    assert "AZURE_AI_DEPLOYMENT" in result["response"]
    assert "NoneType" not in result["response"]


def test_foundry_responses_payload_uses_supported_string_input():
    from backend.llm import create_chat_model

    model = create_chat_model()
    payload = model._get_request_payload([
        SystemMessage(content="system rules"),
        HumanMessage(content="hello"),
    ])

    assert isinstance(payload["input"], str)
    assert "[SYSTEM]" in payload["input"]
    assert "[USER]" in payload["input"]


def test_responses_content_blocks_are_normalized_to_text():
    assert _response_text([{"type": "text", "text": "hello"}]) == "hello"
    assert _response_text([{"type": "output_text", "text": {"value": "world"}}]) == "world"


def test_margin_normalization_preserves_invalid_boundaries():
    assert _normalize_target_margin(20) == .20
    assert _normalize_target_margin(25.0) == .25
    assert _normalize_target_margin(.25) == .25
    assert _normalize_target_margin(1.0) == 1.0
    assert _normalize_target_margin(100) == 1.0
    assert _normalize_target_margin(-.1) == -.1


def test_route_disruption_language_preserves_blocked_edge_and_shipment():
    parsed = _route_disruption_params(
        "The route from Delhi Hub to Jaipur Hub is blocked. Replan 1,000 kg from Delhi to Mumbai."
    )
    assert parsed["changes"]["blocked_routes"] == [["Delhi Hub", "Jaipur Hub"]]
    assert parsed["shipment"]["weight_kg"] == 1000
    assert parsed["source"] == "Delhi" and parsed["destination"] == "Mumbai"


def test_objective_alias_is_normalized_before_tool_validation(monkeypatch):
    instance = SchemaAwareSupervisor()
    monkeypatch.setattr("backend.agents.supervisor.get_warehouses_by_userall", lambda _: [])
    params = instance._normalize_warehouse_params({"objective": "cost"}, 5)
    assert params["objective"] == "cheapest"
    assert instance._normalize_warehouse_params({"objective": "minimize_cost"}, 5)["objective"] == "cheapest"
    assert instance._normalize_warehouse_params({"objective": "minimum ETA"}, 5)["objective"] == "fastest"
    assert instance._normalize_warehouse_params({"objective": "lowest risk"}, 5)["objective"] == "lowest-risk"
    assert instance._normalize_warehouse_params({"objective": "reliable"}, 5)["objective"] == "lowest-risk"
    nested = instance._normalize_warehouse_params({"operation": "express-vs-ground", "parameters": {
        "allowed_modes": ["ground", "express"], "objective": "minimum ETA"}}, 5)
    assert nested["operation"] == "compare_modes"
    assert nested["parameters"]["allowed_modes"] == ["road", "air"]
    assert nested["parameters"]["objective"] == "fastest"
    extracted = instance._normalize_warehouse_params({"operation": "transport_scope_analysis", "parameters": {
        "origin": "Delhi", "destination": "Mumbai", "weight_kg": 6000,
        "modes": ["ground", "express"], "priority": "cost"}}, 5)
    assert extracted["parameters"]["source"] == "Delhi"
    assert extracted["parameters"]["shipment"] == {"weight_kg": 6000}
    assert extracted["parameters"]["allowed_modes"] == ["road", "air"]
    assert extracted["parameters"]["objective"] == "cheapest"


def test_canonical_adapter_handles_nested_and_flat_shipment_shapes():
    assert _adapt_canonical_params("unified_supply_chain_plan", {
        "source": "Delhi", "destination": "Mumbai", "shipment": {"weight_kg": 6000}
    })["weight_kg"] == 6000
    nested = _adapt_canonical_params("supply_chain_planning_operation", {"parameters": {
        "origin": "Delhi", "to": "Mumbai", "weight_kg": 6000,
        "priority": "best overall", "modes": ["truck", "flight"]}})
    assert nested["parameters"]["shipment"] == {"weight_kg": 6000}
    assert nested["parameters"]["objective"] == "balanced"
    assert nested["parameters"]["allowed_modes"] == ["road", "air"]


def test_complete_planning_response_never_exposes_none_sla():
    plan = {"plan_id":"p1", "mode":"road", "product":"Ground", "route_legs":[
        {"from_location":"Delhi", "to_location":"Mumbai", "route_type":"road", "distance":1400,"duration":20}],
        "vehicles":[{"label":"T1","type":"Truck","capacity":7000,"utilization_percentage":85.71}],
        "operational_cost":100, "selling_price":125, "profit":25, "margin_percentage":20,
        "cost_breakdown":{"base_transport":100}, "duration_hours":20,
        "eta":"tomorrow", "risk_score":.2, "risk_breakdown":{"overall":.2}, "reliability":.95,
        "deadline":None, "sla_met":None, "score":.3, "score_components":{"normalized_cost":1}}
    result={"planning_request":{"source":"Delhi","destination":"Mumbai","shipment":{"weight_kg":6000,"quantity":1},"objective":"balanced"},
            "recommended_plan":plan,"reason":"deterministic winner","candidate_plans":[plan],"comparison":[]}
    answer=_format_planning_result(result)
    for required in ("I'd recommend the Ground plan", "Route:","Vehicles:","Cost breakdown", "Risk:","Risk profile", "Balanced score:","SLA was not evaluated"):
        assert required in answer
    assert "Selling price" not in answer and "{\"" not in answer and "plan p1" not in answer
    priced=_format_planning_result(result,"Price it at a 20% margin and show profit")
    assert "Selling price/revenue: ₹125.00" in priced and "Profit: ₹25.00" in priced and "Margin: 20%" in priced
    assert "SLA met: None" not in answer


def test_mode_response_is_conversational_grounded_and_has_no_raw_structures():
    def option(product,cost,hours,risk):
        return {"plan_id":product,"product":product,"mode":product.casefold(),"operational_cost":cost,
                "duration_hours":hours,"risk_score":risk,"deadline":None,"sla_met":None,
                "route_legs":[{"from_location":"Delhi","to_location":"Mumbai","route_type":"road","distance":100,"duration":hours}],
                "vehicles":[{"label":"V1","type":"Truck","capacity":10000,"assigned_load_kg":6000,"utilization_percentage":60}],
                "cost_breakdown":{"base_transport":cost,"air_cost":0}}
    ground=option("Ground",100,10,.2); express=option("Express",300,4,.1)
    result={"planning_request":{"objective":"cheapest","shipment":{"weight_kg":6000}},"options":{"ground":ground,"express":express},
            "recommended_plan":ground,"express_vs_ground":{"additional_cost":200,"time_saved_hours":6,"risk_difference":-.1,
            "sla_comparison":{"ground":None,"express":None}}}
    answer=_format_planning_result(result,"Compare Ground and Express")
    assert "I'd recommend Ground" in answer and "₹200.00" in answer and "saves 6 hours" in answer
    assert "SLA" not in answer and "{" not in answer and "Ground" in answer and "Express" in answer


def test_mode_comparison_uses_leg_modes_readable_risk_delta_and_default_objective_wording():
    def option(plan_id, mode, legs, cost, hours, risk):
        return {"plan_id":plan_id,"product":"Multimodal","mode":mode,"operational_cost":cost,
                "duration_hours":hours,"risk_score":risk,"deadline":None,"sla_met":None,
                "route_legs":[{"from_location":a,"to_location":b,"route_type":leg_mode,"distance":100,"duration":2}
                              for a,b,leg_mode in legs],
                "vehicles":[{"label":"V1","type":"Truck","capacity":10000,"assigned_load_kg":6000,"utilization_percentage":60}],
                "cost_breakdown":{"base_transport":cost}}
    ground=option("ground","road",[("Delhi","Mumbai","road")],100,10,.1765)
    express=option("express","air",[("Delhi","Mumbai","air")],300,4,.1076)
    all_road=option("alternate","multimodal",[("Delhi","Jaipur","road"),("Jaipur","Ahmedabad","road"),("Ahmedabad","Mumbai","road")],120,12,.15)
    result={"planning_request":{"objective":"balanced","shipment":{"weight_kg":6000}},
            "options":{"ground":ground,"express":express,"multimodal":all_road},"recommended_plan":ground,
            "express_vs_ground":{"additional_cost":200,"time_saved_hours":6,"risk_difference":-.0689,
                                  "sla_comparison":{"ground":None,"express":None}}}
    answer=_format_planning_result(result,"Compare Ground and Express for 6,000 kg from Delhi to Mumbai and tell me which one I should choose.")
    assert "Using the default balanced objective" in answer
    assert "Express / Air lowers risk by 6.89 percentage points" in answer
    assert "Ground / Road costs ₹120.00" in answer
    assert "Multimodal costs ₹120.00" not in answer
    mixed=dict(all_road,route_legs=[{"from_location":"Delhi","to_location":"Airport","route_type":"road"},{"from_location":"Airport","to_location":"Mumbai","route_type":"air"}])
    assert _mode_label(mixed)=="Multimodal"


def test_mode_comparison_does_not_steal_multimodal_candidate_requests():
    assert _is_mode_comparison("Compare Ground versus Express for this shipment")
    assert _is_mode_comparison("Which is better, road or air?")
    assert not _is_mode_comparison("Compare road, air and multimodal options")
    assert not _is_mode_comparison("Compare ground, express and multimodal options")


def test_disruption_mitigation_is_canonicalized_for_all_resource_classes():
    names=["IF Delhi NCR Mega Hub","IF Mumbai West Hub","IF Jaipur North Hub"]
    cases={
      "Truck TRK-003 is unavailable. Mitigate that vehicle disruption and replan 3000 kg from Delhi to Mumbai.":{"unavailable_vehicles":["TRK-003"]},
      "The Jaipur warehouse is unavailable. Run warehouse disruption mitigation for 3000 kg from Delhi to Mumbai.":{"unavailable_warehouses":["IF Jaipur North Hub"]},
      "Assume disruption risk increases by 0.2. Mitigate and replan 3000 kg from Delhi to Mumbai with a baseline comparison.":{"risk_delta":.2},
      "Air is the only available mode after a mode disruption. Replan 3000 kg Delhi to Mumbai and compare it with baseline.":{"allowed_modes":["air"]},
    }
    for message,changes in cases.items():
        parsed=_disruption_mitigation_params(message,names)
        assert parsed["operation"]=="disruption_mitigation"
        assert parsed["parameters"]["changes"]==changes
        assert parsed["parameters"]["shipment"]["weight_kg"]==3000


def test_vehicle_planning_request_uses_deterministic_planning_contract():
    names=["IF Delhi NCR Mega Hub","IF Mumbai West Hub"]
    message="TRK-003 is unavailable. Select other road vehicles for 3000 kg Delhi to Mumbai."
    assert _is_vehicle_planning_request(message)
    parsed=_vehicle_selection_params(message,names)
    assert parsed["operation"]=="vehicle_selection"
    assert parsed["parameters"]["source"]==names[0]
    assert parsed["parameters"]["shipment"]["weight_kg"]==3000
    assert parsed["parameters"]["changes"]=={"unavailable_vehicles":["TRK-003"]}


def test_explicit_iso_deadline_is_preserved_from_language():
    assert _deadline_from_message("deliver by 2026-09-04T10:30:00+00:00 please") == "2026-09-04T10:30:00+00:00"


def test_explicit_objective_language_overrides_nondeterministic_extraction():
    assert _objective_from_message("Cost matters most; recommend the cheapest") == "cheapest"
    assert _objective_from_message("Risk matters most; recommend the safest") == "lowest-risk"
    assert _objective_from_message("recommend the fastest option") == "fastest"
    assert _objective_from_message("best overall tradeoff") == "balanced"


def test_breakdown_recovery_language_has_operation_specific_contract():
    parsed=_breakdown_recovery_params(
        "TRK-003 broke down at Delhi with 500 kg remaining. Recover shipment to Mumbai.",
        ["IF Delhi NCR Mega Hub","IF Mumbai West Hub"])
    assert parsed["operation"]=="breakdown_recovery"
    assert parsed["parameters"]=={"vehicle_label":"TRK-003","current_location":"IF Delhi NCR Mega Hub",
                                  "destination":"IF Mumbai West Hub","remaining_weight_kg":500.0}
    multi=_breakdown_recovery_params(
        "TRK-001 broke down at Delhi with 9000 kg remaining. Recover shipment to Mumbai using multiple replacements if needed.",
        ["IF Delhi NCR Mega Hub","IF Mumbai West Hub"])
    assert multi["parameters"]["destination"]=="IF Mumbai West Hub"


def test_fulfilment_language_has_flat_operation_contract():
    parsed=_fulfilment_params("Can warehouses cover 1,500 units totaling 12000 kg to Mumbai using the cheapest allocation?",
                              ["IF Mumbai West Hub"])
    assert parsed["operation"]=="fulfilment"
    assert parsed["parameters"]=={"destination":"IF Mumbai West Hub","quantity":1500,
                                  "weight_kg":12000.0,"objective":"cheapest"}


def test_central_language_variants_cover_demo_phrasing():
    for phrase in ("lowest cost", "save money", "most economical"):
        assert _normalize_objective(phrase) == "cheapest"
    for phrase in ("quickest", "minimum ETA", "as soon as possible"):
        assert _normalize_objective(phrase) == "fastest"
    assert _is_mode_comparison("Should I use truck or flight?")
    assert _weight_kg_from_message("Move 6 tonnes from Delhi") == 6000
    assert _weight_kg_from_message("Move 6,000 kilograms from Delhi") == 6000
    assert _is_shipment_plan_request("Plan 6,000 kg from Delhi to Mumbai using air transport. Show the assigned aircraft.")


def test_specialized_demo_operations_use_stable_adapters():
    assert _specialized_operation_params("TRK-003 is delayed by 6 hours. Show affected future shipments.")["operation"] == "future_replan"
    multi=_specialized_operation_params("Optimize a 3000 kg road shipment from Delhi to Mumbai stopping at Jaipur and Ahmedabad. Show the best stop order.")
    assert multi["operation"] == "multi_stop" and multi["parameters"]["stops"] == ["Jaipur", "Ahmedabad"]
    consolidation=_specialized_operation_params("Consolidate shipment S1 of 1000 kg and shipment S2 of 1200 kg, both from Delhi to Mumbai.")
    assert consolidation["operation"] == "consolidation" and len(consolidation["parameters"]["shipments"]) == 2
    scenario=_scenario_params("Create a what-if plan for 6 tonnes from Delhi to Mumbai if fuel cost increases by 20 percent.")
    assert scenario["parameters"]["shipment"]["weight_kg"] == 6000
    assert scenario["parameters"]["changes"]["fuel_cost_multiplier"] == 1.2


def test_advanced_natural_language_operations_use_canonical_adapters():
    consolidation=_specialized_operation_params("Evaluate whether these two shipments can be consolidated: 3000 kg Delhi→Mumbai and 2500 kg Delhi→Mumbai with same delivery window.")
    assert consolidation["operation"]=="consolidation" and [x["weight_kg"] for x in consolidation["parameters"]["shipments"]]==[3000,2500]
    multi=_specialized_operation_params("Optimize an 8000 kg road shipment from Delhi to Mumbai with required stops at Jaipur and Ahmedabad.")
    assert multi["operation"]=="multi_stop" and multi["parameters"]["stops"]==["Jaipur","Ahmedabad"]
    global_plan=_specialized_operation_params("Plan 5000 kg Delhi→Frankfurt using road to gateway, international air and destination-side transport.")
    assert global_plan["operation"]=="global_plan" and global_plan["parameters"]["destination"]=="Frankfurt"
    deadline=_deadline_from_message("Deliver by 5 Sep 2026, 8:00 PM IST")
    from backend.agents.supervisor import _readable_time
    assert deadline.endswith("+05:30") and _readable_time(deadline)=="05 Sep 2026, 14:30 UTC"


def test_scenario_and_stress_followups_merge_active_context():
    scenario={"scenario_id":"draft-1","status":"draft","changes":{"fuel_cost_multiplier":1.2},"baseline":{},"scenario":{},"comparison":{}}
    context={"source":"Delhi","destination":"Mumbai","weight_kg":6000,"quantity":1,"objective":"balanced",
             "route_legs":[{"from_location":"Delhi","to_location":"Mumbai"}],"assigned_vehicles":[{"label":"T1"}],
             "current_scenario":scenario,"expansion_recommendation":{"recommended_hubs":[{"hub":"Nashik","incremental_cost":10}]}}
    cases={
      "What if I need it much faster?":"plan",
      "What if the assigned vehicle breaks down?":"breakdown_recovery",
      "What if the new route becomes disrupted?":"route_alternatives",
      "Which option should I finally use and why?":"plan",
      "Compare the draft scenario with my current baseline.":"compare_scenario",
      "Apply this draft plan.":"scenario_action",
      "Discard the draft scenario.":"scenario_action",
      "Calculate complete estimated cost of the facility expansion you just recommended.":"expansion_cost",
    }
    for message,operation in cases.items():
        resolved,clarification=_contextual_planning_params(message,{"user_id":5},context)
        if operation == "breakdown_recovery":
            assert clarification and "location" in clarification
        else:
            assert clarification is None and resolved["operation"]==operation
    future,clarification=_contextual_planning_params("Assume my current Delhi to Mumbai shipment is delayed by 8 hours. Identify future shipments affected by same vehicles.",{"user_id":5},context)
    assert clarification is None and future["operation"]=="future_replan" and future["parameters"]["delay_hours"]==8
    active={**context,"selected_plan_id":"baseline-plan","cost":100}
    draft_result={"scenario_id":"draft-2","status":"draft","changes":{"fuel_cost_multiplier":1.2},
                  "baseline":{"planning_request":{"source":"Delhi","destination":"Mumbai","shipment":{"weight_kg":6000,"quantity":1}},"recommended_plan":{"plan_id":"baseline-plan"}},
                  "scenario":{"recommended_plan":{"plan_id":"draft-plan","operational_cost":120}},"comparison":{"cost_difference":20}}
    merged=_context_from_result(draft_result,active)
    assert merged["selected_plan_id"]=="baseline-plan" and merged["scenario_id"]=="draft-2" and merged["cost"]==100
    explicit={"user_id":5,"operation":"fulfilment","parameters":{"destination":"Mysuru","quantity":120,"weight_kg":1200,"objective":"cheapest"}}
    resolved,clarification=_contextual_planning_params("Use alternative warehouses to fulfil 120 units totaling 1200 kg to Mysuru using the cheapest allocation.",explicit,{})
    assert clarification is None and resolved["operation"]=="fulfilment" and resolved["parameters"]["quantity"]==120
    capacity,clarification=_contextual_planning_params("Show available inventory, available storage and utilization for every warehouse.",{"user_id":5},{})
    assert clarification is None and capacity=={"user_id":5,"operation":"warehouse_capacity","parameters":{}}


def test_active_planning_context_resolves_referential_followups():
    result={"planning_request":{"source":"Delhi","destination":"Mumbai","shipment":{"weight_kg":6000,"quantity":10},"objective":"cheapest"},
            "recommended_plan":{"plan_id":"p1","operational_cost":100,"duration_hours":5,"risk_score":.1,"reliability":.9,
                                "route_legs":[{"route_id":7,"from_location":"Delhi","to_location":"Mumbai","route_type":"road"}],
                                "vehicles":[{"label":"TRK-003"}]}}
    context=_context_from_result(result)
    disruption, clarification=_contextual_planning_params("A route in my shipment is disrupted. Replan it and tell me what changes.",{"user_id":5},context)
    assert clarification is None and disruption["operation"]=="route_alternatives"
    assert disruption["parameters"]["shipment"]["weight_kg"]==6000
    breakdown, clarification=_contextual_planning_params("The assigned vehicle broke down. Find a replacement.",{"user_id":5},context)
    assert clarification and "location" in clarification
    explicit={"operation":"breakdown_recovery","parameters":{"current_location":"Jaipur"}}
    breakdown, clarification=_contextual_planning_params("Recover the assigned truck from Jaipur.",explicit,context)
    assert clarification is None and breakdown["parameters"]["vehicle_label"]=="TRK-003"
    assert breakdown["parameters"]["current_location"]=="Jaipur"
    scenario, clarification=_contextual_planning_params("What happens to my current plan if fuel cost increases by 20%? Do not apply it.",{"user_id":5},context)
    assert clarification is None and scenario["parameters"]["changes"]["fuel_cost_multiplier"]==1.2


def test_resource_and_recovery_followups_reuse_active_plan_context():
    context={"source":"IF Delhi NCR Mega Hub","destination":"IF Mumbai West Hub","weight_kg":18000,
             "quantity":1,"objective":"balanced","route_legs":[{"from_location":"IF Delhi NCR Mega Hub","to_location":"IF Mumbai West Hub"}],
             "assigned_vehicles":[{"label":"TRK-001"},{"label":"TRK-002"}]}
    capacity,clarification=_contextual_planning_params(
        "Show the available inventory, available storage and utilization for the warehouse selected for my current shipment.",
        {"user_id":5},context)
    assert clarification is None and capacity["operation"]=="warehouse_capacity"
    assert capacity["parameters"]["warehouse_names"]==["IF Delhi NCR Mega Hub"]
    _,alternative_clarification=_contextual_planning_params(
        "My preferred warehouse cannot fulfil the order. Which alternative warehouse should I use and why?",
        {"user_id":5},context)
    assert alternative_clarification=="Which product/SKU and quantity should I check across alternative warehouses?"
    disruption,clarification=_contextual_planning_params(
        "The current route is disrupted. Replan it using the best available alternative and show me what changed in cost, ETA, risk, route and vehicle.",
        {"user_id":5},context)
    assert clarification is None and disruption["operation"]=="route_alternatives"
    assert disruption["parameters"]["shipment"]["weight_kg"]==18000
    assert "shipment" not in _adapt_canonical_params("canonical",{"parameters":{"shipment":"current shipment"}})["parameters"]


def test_vehicle_load_display_is_rounded_and_conserves_total():
    text=_vehicle_text({"vehicles":[
        {"label":"TRK-001","type":"Truck","capacity":12000,"assigned_load_kg":11368.421053,"utilization_percentage":94.74},
        {"label":"TRK-002","type":"Truck","capacity":7000,"assigned_load_kg":6631.578947,"utilization_percentage":94.74},
    ]},{"weight_kg":18000})
    assert "11,368.42 kg" in text and "6,631.58 kg" in text
    assert "11368.421053" not in text and "6631.578947" not in text


def test_breakdown_formatter_shows_active_plan_before_after_changes():
    leg=lambda mode:{"from_location":"Delhi","to_location":"Mumbai","route_type":mode,"distance":100,"duration":2}
    vehicle=lambda label,kind:{"label":label,"type":kind,"capacity":20000,"assigned_load_kg":18000,"utilization_percentage":90}
    recovery={"plan_id":"new","route_legs":[leg("air")],"vehicles":[vehicle("AIR-079","Plane")],
              "operational_cost":300,"duration_hours":4,"risk_score":.10,"deadline":None,
              "replacement_approach_legs":[],"replacement_arrival_hours":0,"transfer_time_hours":.5}
    result={"broken_vehicle":{"label":"TRK-001"},"remaining_journey":{"source":"Delhi","destination":"Mumbai"},
            "transfer_load_kg":18000,"recovery_plan":recovery,"additional_cost":0,"new_eta":"tomorrow",
            "_active_plan_before":{"route_legs":[leg("road")],"vehicles":[vehicle("TRK-001","Truck"),vehicle("TRK-002","Truck")],
                                   "cost":100,"duration_hours":10,"risk":.2}}
    answer=_format_planning_result(result,"The assigned vehicle broke down. Show what changed.")
    for expected in ("What changed (before → after)","Ground / Road → Express / Air","[Delhi → Mumbai] → [Delhi → Mumbai]","TRK-001, TRK-002 → AIR-079",
                     "₹100.00 → ₹300.00","10 hours → 4 hours","20.00% → 10.00%","no repositioning leg"):
        assert expected in answer


def test_contextual_missing_business_inputs_get_human_clarifications():
    _, warehouse_message=_contextual_planning_params(
        "No single warehouse has enough inventory. Can multiple warehouses fulfil the order? Show the allocations.",
        {"user_id":5}, {})
    assert "product/sku" in warehouse_message.casefold() and "quantity" in warehouse_message.casefold() and "required information" not in warehouse_message.casefold()
    _, global_message=_contextual_planning_params(
        "Plan a shipment from Delhi to Frankfurt using road, gateway, international air and destination legs.",
        {"user_id":5}, {})
    assert "weight_kg" in global_message


def test_mode_label_is_derived_from_actual_route_legs():
    all_road={"mode":"multimodal","route_legs":[
        {"route_type":"road"},{"route_type":"road"},{"route_type":"road"}]}
    mixed={"mode":"road","route_legs":[{"route_type":"road"},{"route_type":"air"}]}
    assert _actual_mode(all_road)=="road" and _mode_label(all_road)=="Ground / Road"
    assert _actual_mode(mixed)=="multimodal" and _mode_label(mixed)=="Multimodal"


def test_disruption_explanation_shows_deterministic_before_after_deltas():
    leg=lambda route_id,a,b:{"route_id":route_id,"from_location":a,"to_location":b,"route_type":"road","distance":100,"duration":2,
                              "source_coords":{"lat":1,"lng":1},"destination_coords":{"lat":2,"lng":2}}
    plan={"plan_id":"after","mode":"road","product":"Ground","route_legs":[leg(2,"Delhi","Jaipur"),leg(3,"Jaipur","Mumbai")],
          "operational_cost":120,"duration_hours":6,"risk_score":.2,"reliability":.9,"vehicles":[{"label":"TRK-002","type":"Truck","capacity":7000,"assigned_load_kg":6000,"utilization_percentage":85.71}],
          "cost_breakdown":{},"risk_breakdown":{},"deadline":None,"score":.5,"score_components":{}}
    result={"planning_request":{"source":"Delhi","destination":"Mumbai","shipment":{"weight_kg":6000,"quantity":1},"objective":"cheapest","allowed_modes":["road"]},
            "recommended_plan":plan,"candidate_plans":[plan],"_active_plan_before":{"mode":"road","route_legs":[leg(1,"Delhi","Mumbai")],
              "vehicles":[{"label":"TRK-001"}],"cost":100,"duration_hours":5,"risk":.1,"deadline":None}}
    answer=_format_planning_result(result,"The current route is disrupted. Replan it and show me what changed.")
    for expected in ("What changed (before → after)","Ground / Road → Ground / Road","TRK-001 → TRK-002","₹100.00 → ₹120.00","delta ₹20.00","5 hours → 6 hours","10.00% → 20.00%"):
        assert expected in answer


def test_mode_specific_no_route_message_does_not_claim_network_is_unavailable():
    answer=_format_planning_result({"planning_request":{"source":"IF Delhi NCR Mega Hub","destination":"IF Bengaluru South Hub","allowed_modes":["road"]},"recommended_plan":None})
    assert answer=="No feasible road route from IF Delhi NCR Mega Hub to IF Bengaluru South Hub exists in the currently loaded network."
