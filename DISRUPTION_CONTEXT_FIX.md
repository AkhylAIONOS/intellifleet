IntelliFleet disruption-context regression fix

Root cause and reproduction

The exact two-turn request was reproduced over POST /mcp-agent on the original port 4200 service. Turn 1 returned a 6000 kg Ground direct plan and listed the feasible three-leg Ground alternative. Turn 2 returned the reported generic failure and no actions.

A real Azure supervisor trace captured the canonical extraction:

```json
{"operation":"future_replan","parameters":{"route_status":"direct route unavailable","selection":"best feasible alternative","compare":["old route","new route","vehicle","cost","ETA","risk"]}}
```

The central context resolver required the substring `disrupt`. The user's `unavailable` wording did not enter that branch, so the incorrect operation and incomplete parameters passed through unchanged. The planning-operation tool dispatched to `future_replan` and raised `KeyError: 'vehicle_label'`. Alternative candidate generation was never reached: the valid route was not lost by the deterministic search or vehicle evaluator.

Two related context/output gaps were confirmed: active context did not retain `allowed_modes` or the complete original request/selected plan, and the old-plan metadata used during formatting was removed before frontend action creation. Before/after text was also gated on the literal phrase `what changed`, which the reported request did not contain.

Correction

Only production file changed: `intellifleet-server-backendmcp/backend/agents/supervisor.py`.

- Central route-outage detection handles unavailable/blocked/closed/cancelled/disrupted and contextual route/plan/shipment references. It does not depend on city names, route IDs or a complete fixed sentence.
- Current context supplies source, destination, shipment weight/quantity/SKU, Ground/Road restriction and the other original planning-request constraints.
- The complete selected plan, selected mode, request, assigned vehicles and successful disruption exclusions remain in active context.
- A single selected leg is resolved unambiguously; explicitly named endpoints must match a selected leg. An ambiguous multi-leg reference requests the affected leg rather than arbitrarily blocking the first one.
- The canonical operation becomes `route_alternatives`; selected endpoints enter `changes.blocked_routes` before the unchanged deterministic planner executes.
- Existing vehicle feasibility still determines the new assignment. The previous vehicle is recorded for comparison, not forced onto a route beyond its range.
- Successful results retain structured baseline data and cost/ETA/risk differences. Route-alternative replies include before/after text without requiring the exact words `what changed`.
- Infeasible results preserve the active selected plan and the existing safe vehicle-capacity/range explanation.

Frontend contract

No frontend file was changed. The action remains `supply_chain_planning_operation`, with `planning_operation: route_alternatives` and the usual `recommended_plan` field. Additive fields are `baseline` (using the already-supported `baseline.recommended_plan` shape), `replan_comparison` and `applied_changes`. The existing candidate `comparison` list was preserved. No frontend migration is required. Captured real actions were executed through the existing frontend store to verify route replacement, baseline comparison and infeasible-plan retention.

Files added

- `intellifleet-server-backendmcp/tests/test_contextual_disruption.py`: ten regression cases through the real supervisor/MCP path with deterministic mocked Azure extraction and isolated network/context fixtures. This includes the exact incorrect `future_replan` extraction that caused the failure, 6000 kg feasible/explicit cases, 18000 kg range/capacity infeasibility, context correctness, reference vocabulary and ambiguity handling.
- `intellifleet-server-backendmcp/tests/run_contextual_disruption_azure.py`: real HTTP/Azure validation of three clean two-turn flows.
- `intellifleet-server-backendmcp/tests/check_disruption_frontend_state.mjs`: captured actions exercised against the unchanged frontend store.
- `intellifleet-server-backendmcp/tests/contextual_disruption_azure_results.json`: complete captured validation results and before/after contexts.
- `DISRUPTION_CONTEXT_FIX.md`: this record.

Real Azure calls also appended to the existing `backend/agents/token_usage.txt` runtime log. No production planning-service, formula, feasibility, warehouse-calculation, frontend animation or map code was edited.

Validation results

1. Targeted first: `.venv/bin/python -m pytest tests/test_contextual_disruption.py -q` — 10 passed.
2. Full backend suite: `.venv/bin/python -m pytest tests -q` — 98 passed in 2.16 seconds. One existing aioredis/distutils deprecation warning.
3. Real Azure/HTTP: `PYTHONPATH=. .venv/bin/python tests/run_contextual_disruption_azure.py --url http://127.0.0.1:4201` — all three two-turn cases passed on a temporary updated-code server.
4. Existing frontend state: `node tests/check_disruption_frontend_state.mjs` — all three captured action flows passed. Non-failing Zustand browser-storage warnings occur in this SSR harness.
5. Main service was restarted on its existing port 4200; the temporary server was stopped. The exact original two-turn request was repeated on port 4200 and passed, with context remaining Ground/Road and changing from the direct selected route to the revised three-leg route.
6. `git diff --check` passed.

Observed live 6000 kg result (both contextual and explicit disruption)

Before: IF Delhi NCR Mega Hub → IF Mumbai West Hub; TRK-002.
After: IF Delhi NCR Mega Hub → IF Jaipur North Hub → IF Ahmedabad West Hub → IF Mumbai West Hub; TRK-001, assigned load 6000 kg, capacity 12000 kg.

| Metric | Before | After | Difference |
| --- | --- | --- | --- |
| Cost | ₹349,155.00 | ₹350,284.60 | +₹1,129.60 |
| ETA | 19.67 h | 24.49 h | +4.82 h |
| Risk | 17.65% | 15.30% | −2.35 percentage points |

These route/vehicle names and values are validation observations from the loaded network, not implementation constants.

Observed live 18000 kg result

The deterministic search found the same 1515 km geographical alternative, but returned no recommended plan with `feasibility.constraint: vehicle_capacity_or_full_route_range`. The response retained the safe explanation and the prior selected plan/context. The existing frontend store also retained its selected plan when given this action.

No live-browser map rendering was needed or claimed for this backend fix; frontend action/state integration was tested without changing frontend code.
