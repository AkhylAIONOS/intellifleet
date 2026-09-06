from fastmcp import FastMCP
from pydantic import BaseModel, Field

from backend.planning.models import PlanningRequest, Shipment
from backend.planning.service import PlanningService


class UnifiedPlanInput(BaseModel):
    user_id: int
    source: str
    destination: str
    weight_kg: float = Field(gt=0)
    quantity: int = Field(default=1, gt=0)
    objective: str = "balanced"
    deadline: str | None = None
    allowed_modes: list[str] = Field(default_factory=lambda: ["road", "air", "multimodal"])
    target_margin: float = 0.20
    max_risk: float | None = None
    intermediate_stops: list[str] = Field(default_factory=list)

class PlanningOperationInput(BaseModel):
    user_id: int
    operation: str
    parameters: dict = Field(default_factory=dict)


def register_planning_tools(mcp: FastMCP):
    @mcp.tool()
    async def unified_supply_chain_plan(input: UnifiedPlanInput) -> dict:
        """Calculate traceable cost, ETA, risk, SLA, vehicles and inventory allocation; use for shipment planning and comparisons."""
        request = PlanningRequest(
            source=input.source, destination=input.destination,
            shipment=Shipment(weight_kg=input.weight_kg, quantity=input.quantity),
            objective=input.objective, deadline=input.deadline,
            allowed_modes=input.allowed_modes, target_margin=input.target_margin,
            max_risk=input.max_risk,
            intermediate_stops=input.intermediate_stops,
        )
        return PlanningService().plan(input.user_id, request)

    @mcp.tool()
    async def supply_chain_planning_operation(input: PlanningOperationInput) -> dict:
        """Run deterministic scenario, fulfilment, breakdown, consolidation, capacity, multi-stop, future-replan, expansion, or transport-scope analysis."""
        service=PlanningService(); p=dict(input.parameters); op=input.operation
        aliases={"what_if_plan":"create_scenario","what_if_scenario":"create_scenario","scenario":"create_scenario","scenario_analysis":"create_scenario","simulate_scenario":"create_scenario",
                 "international_plan":"global_plan","global_routing":"global_plan","global_multimodal_plan":"global_plan",
                 "load_consolidation":"consolidation","multi_stop_optimization":"multi_stop","facility_planning":"expansion",
                 "network_expansion":"expansion","capacity":"warehouse_capacity"}
        op=aliases.get(op,op)
        def tagged(value: dict) -> dict:
            value["planning_operation"]=op
            return value
        if op in {"plan", "route_alternatives", "route_comparison", "risk", "vehicle_selection", "sla_plan"}:
            changes = p.pop("changes", None)
            return tagged(service.plan(input.user_id, PlanningRequest(**p), changes=changes))
        if op in {"compare_modes", "express_vs_ground", "road_vs_air"}:
            return tagged(service.compare_modes(input.user_id, PlanningRequest(**p), changes=p.get("changes")))
        if op in {"disruption_mitigation", "mitigate_disruption"}:
            changes = p.pop("changes")
            return tagged(service.disruption_mitigation(input.user_id, PlanningRequest(**p), changes))
        if op in {"create_scenario", "what_if"}:
            changes = p.pop("changes")
            return tagged(service.create_scenario(input.user_id, PlanningRequest(**p), changes, baseline=p.get("baseline")))
        if op == "scenario_action":
            return tagged(service.scenario_action(input.user_id, p["scenario_id"], p["action"]))
        if op == "compare_scenario": return tagged(service.get_scenario(input.user_id,p["scenario_id"]))
        if op == "schedule_shipment": return tagged(service.schedule_shipment(input.user_id,p))
        if op=="warehouse_capacity":
            names = p.get("warehouse_names") or ([p["warehouse_name"]] if p.get("warehouse_name") else None)
            return tagged(service.warehouse_capacity(input.user_id, names))
        if op=="fulfilment": return tagged(service.fulfilment(input.user_id,p["destination"],p["quantity"],p["weight_kg"],p.get("objective","balanced"),p.get("deadline"),p.get("excluded_warehouses"),p.get("sku")))
        if op=="auto_fulfilment": return tagged(service.auto_fulfilment(input.user_id,p.get("destination")))
        if op=="breakdown_recovery": return tagged(service.breakdown_recovery(input.user_id,p["vehicle_label"],p["current_location"],p["destination"],p["remaining_weight_kg"],p.get("deadline")))
        if op=="future_replan": return tagged(service.future_replan(input.user_id,p["vehicle_label"],p["delay_hours"]))
        if op in {"consolidation", "optimize_utilization"}:
            if not p.get("shipments"):
                return tagged({"consolidation_opportunities": [], "reason": "Provide shipment origins, destinations, weights and delivery windows to optimize compatible fleet loads.", "missing_fields": ["shipments"]})
            return tagged(service.consolidate(input.user_id,p["shipments"]))
        if op=="multi_stop": return tagged(service.optimize_stops(input.user_id,p["source"],p["destination"],p["stops"],p["shipment"],p.get("objective","balanced")))
        if op=="transport_scope": return tagged(service.transport_scope(p["source_country"],p["destination_country"]))
        if op=="global_plan":
            return tagged(service.global_plan(input.user_id,PlanningRequest(**p)))
        if op=="expansion_network": return tagged(service.expansion_from_network(input.user_id))
        if op=="expansion_cost": return tagged(p["recommendation"])
        if op=="expansion":
            from backend.planning.models import ExpansionRequest
            return tagged(service.expansion(ExpansionRequest(**p)))
        raise ValueError(f"Unsupported planning operation: {op}")
