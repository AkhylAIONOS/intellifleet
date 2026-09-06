# IntelliFleet Demo Core-30 Matrix

Validated through the real `/mcp-agent` path with Azure GPT-5.6 Sol. `Planner/MCP` means the returned action contained a deterministic PlanningService result that passed capability-specific structural and numeric checks. Failed cases were repaired and rerun individually.

| PS | Capability | Real Chat | Planner/MCP | Response | Final |
|---:|---|---|---|---|---|
| PS1 | End-to-end network planning | PASS | PASS | PASS | PASS |
| PS2 | Cheapest routing | PASS | PASS | PASS | PASS |
| PS3 | Fastest routing | PASS | PASS | PASS | PASS |
| PS4 | Multi-objective planning | PASS | PASS | PASS | PASS |
| PS5 | Express vs Ground comparison | PASS | PASS | PASS | PASS |
| PS6 | Pricing / revenue / margin | PASS | PASS | PASS | PASS |
| PS7 | Route alternatives | PASS | PASS | PASS | PASS |
| PS8 | Route comparison | PASS | PASS | PASS | PASS |
| PS9 | Disruption risk | PASS | PASS | PASS | PASS |
| PS10 | Disruption mitigation | PASS | PASS | PASS | PASS |
| PS11 | Vehicle selection / multi-vehicle | PASS | PASS | PASS | PASS |
| PS12 | Road vs Air | PASS | PASS | PASS | PASS |
| PS13 | Vehicle breakdown recovery | PASS | PASS | PASS | PASS |
| PS14 | Alternative warehouse | PASS | PASS | PASS | PASS |
| PS15 | Multi-warehouse fulfilment | PASS | PASS | PASS | PASS |
| PS16 | Warehouse capacity | PASS | PASS | PASS | PASS |
| PS17 | Load consolidation | PASS | PASS | PASS | PASS |
| PS18 | Multi-stop optimization | PASS | PASS | PASS | PASS |
| PS19 | Vehicle utilization | PASS | PASS | PASS | PASS |
| PS20 | What-if scenarios | PASS | PASS | PASS | PASS |
| PS21 | Baseline vs scenario | PASS | PASS | PASS | PASS |
| PS22 | Future shipment cascading replanning | PASS | PASS | PASS | PASS |
| PS23 | SLA planning | PASS | PASS | PASS | PASS |
| PS24 | Network expansion / facility planning | PASS | PASS | PASS | PASS |
| PS25 | Expansion cost | PASS | PASS | PASS | PASS |
| PS26 | Domestic/global multimodal | PASS | PASS | PASS | PASS |
| PS27 | Decision support | PASS | PASS | PASS | PASS |
| PS28 | Explainability | PASS | PASS | PASS | PASS |
| PS29 | Plan-before-execution | PASS | PASS | PASS | PASS |
| PS30 | Unified planner | PASS | PASS | PASS | PASS |

Result evidence: `tests/demo_core_30_results.json`.
