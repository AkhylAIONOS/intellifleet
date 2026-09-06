# PS30 changes — in-progress acceptance record

Existing uncommitted work was preserved. No API keys, authentication implementation, production network rows or Git history were intentionally changed. Real Azure testing uses an isolated SQLite copy and a separate Redis chat identity.

## Root causes addressed

- Cost/duration shortest paths could hide feasible alternatives; actual simple paths are enumerated with a disclosed search limit.
- Vehicle selection ignored full operational costs, speeds and availability. Small source fleets now use subset enumeration; daily dispatch windows and absolute availability timestamps are distinguished.
- Mixed-mode plans previously assigned a road vehicle to an air leg. Each mode segment now requires its own feasible vehicles; structured segment assignments feed the journey marker.
- Hard risk limits incorrectly fell back to risky plans; SLA-compliant candidates now receive priority.
- Explicit warehouse scope was cleared during context routing and aliases were exact-only at MCP.
- Fulfilment allocated from inactive/excluded warehouses and reused costs calculated for larger loads. Allocations now use actual per-option deterministic plans and integer allocation search.
- Multi-stop optimization silently dropped unreachable stops. It now compares complete permutations for up to seven stops and returns specific infeasibility.
- Consolidation only grouped identical destinations. Common-source loads now evaluate connected delivery orders with conservative full-load pricing.
- Breakdown context substituted origin for unknown recovery location; recovery now asks for location and can reposition compatible replacement vehicles over actual edges.
- Future replanning used substring vehicle matching and could double-book replacements. It now matches parsed labels and tracks overlapping reservations.
- Expansion silently invented facility and transport costs. Missing assumptions now remain unknown, with geodesic siting estimates explicitly distinguished from network routes.
- Unknown scenario actions fell through to APPLY. Only apply/discard/draft are accepted; infeasible scenarios cannot apply; unsupported changes are rejected.
- Relative deadline changes now have a canonical numeric field resolved against the stored baseline arrival.

## Production files changed in this task

Backend: `backend/planning/service.py`, `models.py`, new `intent.py`; `backend/mcp/tools/planning_tools.py`; `backend/agents/supervisor.py`.
Frontend: `src/store/appStore.ts`, `src/components/PlanVisuals.tsx`, new `OperationDetails.tsx`, `src/utils/planVisuals.ts`, `src/components/MapLayers/SelectedJourneyLayer.tsx`.

## Tests

New: `tests/test_ps30_acceptance.py`, `tests/run_ps30_live.py`, `tests/run_ps30_network.py`; frontend `tests/run-operation-details.mjs`.
Updated backend tests: `tests/test_planning.py`, `tests/test_chat_configuration.py`. Changes correct prior unsafe expectations: missing breakdown location must clarify; a multimodal fixture needs actual gateway vehicles; unspecified expansion costs are unknown; recovery spend includes replacement transport.

## Architecture and frontend contracts

The canonical intent envelope resolves numeric relative deadlines before MCP. Existing supervisor compatibility parsing remains and is not yet fully replaced. Deterministic service outputs remain authoritative.

Added structured `operationResult` state, cleared with New Chat, and guarded tables for warehouse allocations, future shipments, consolidation, candidate facilities and demand assignments. Missing values display as unavailable. Added `leg_assignments` for mode-segment vehicle binding. Existing route animation, replay, focus and Plan Snapshot remain.

## Known limitations

See `PS_30_FINAL_VALIDATION.md` for the acceptance matrix. This is not a 30/30 acceptance claim. Large search spaces and several optimization objectives remain bounded or heuristic; source inventory attribution, complete cascading resource constraints, all scenario modifiers, expansion assignment/cost completeness, and the full requested multi-turn flow need further acceptance work.
