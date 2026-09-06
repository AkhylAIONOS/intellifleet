IntelliFleet / UniFleet — selected-plan visualization delivery

A. Files changed for this task

All frontend paths below are relative to `intellifleet-web-main/frontendmain/`. The workspace already contained substantial changes before this task; this list describes only files edited or added for this enhancement.

| File | Change |
| --- | --- |
| `src/store/appStore.ts` | Canonical selected plan, exact assignment projection, previous vehicle restoration, comparisons, warehouse focus, infeasible retention, scenario isolation, visual reset |
| `src/types/api.ts` | Optional warehouse metrics and exact assignment fields |
| `src/utils/planVisuals.ts` (new) | Typed visualization contract, supplied geometry validation, journey interpolation and route labels |
| `src/utils/journeyPlayback.ts` (new) | One cancellable 10-second requestAnimationFrame scheduler |
| `src/components/MapLayers/SelectedJourneyLayer.tsx` (new) | Selected route pane, vehicle playback, bounded camera follow, popups, replay and cleanup |
| `src/components/MapLayers/WarehouseFocusLayer.tsx` (new) | Warehouse lookup, focus, emphasis and real-value popup |
| `src/components/MapLayers/MapLegend.tsx` (new) | Conditional compact legend |
| `src/components/MapLayers/RoutesLayer.tsx` | Secondary network styling, dashed alternatives, removal of duplicate planning overlay and competing plan zoom |
| `src/components/MapLayers/VehiclesLayer.tsx` | Hand selected vehicles to the journey layer; keep background vehicles static during selected-plan playback |
| `src/components/MapLayers/PlanesLayer.tsx` | Exclude duplicate selected aircraft; keep background aircraft static while a plan is selected |
| `src/components/MapLayers/WarehousesLayer.tsx` | Display available warehouse metrics; treat only explicitly inactive warehouses as inactive |
| `src/components/MapView.tsx` | Mount new map layers and prevent legacy zoom from overriding selected-plan focus |
| `src/components/PlanVisuals.tsx` (new) | Plan Snapshot, exact assignment list, leg strip, comparison table and retained-plan notices |
| `src/components/PlanVisuals.css` (new) | Compact responsive summary, markers, comparison styling and map controls |
| `src/components/ChatPanel.tsx` | Current shipment summary above the conversation scroll area; New Chat clears planning visuals |
| `src/components/PlanningPanel.tsx` | Structured snapshot/comparison and scenario actions through the shared selection action |
| `src/components/VehicleDashboard.tsx` | Current selected assignments and exact plan snapshot |
| `src/pages/DashboardPage.tsx` | Assigned Vehicles metric uses the current plan's assignment list |
| `tests/run-plan-visual-state.mjs` (new) | Store, geometry, assignment, comparison and scheduler regressions |
| `tests/run-map-journey-dom.mjs` (new) | Actual Leaflet component tests in JSDOM, including full network-sized fixtures |
| `tests/run-planner-controls-dom.mjs` (new) | Planner, scenarios, route management and New Chat interaction tests with API stubs |
| `package.json` | `npm test`, JSDOM and React Testing Library development dependencies |
| `package-lock.json` | Local dependency lock updated by npm; this file is ignored by the existing repository rules |
| `../../MAP_VISUALIZATION_NOTES.md` (new) | This delivery and demo record |

B. Architecture

Both existing entry points continue to call `applyPlanningMapPlan`: the chat action handler and Supply-Chain Planner. `selectedPlan` is the visualization source of truth. The temporary negative-ID route and master-vehicle assignment fields are derived compatibility views for existing dashboards. Previous master-vehicle values are restored when a plan is replaced or cleared. Selected overlays remain excluded from editable Route Management and persisted network counts.

The map layer reads structured plan legs and assignments. It owns one animation scheduler, directly updates Leaflet marker position, and never sends tracking/completion requests or writes per-frame React/Zustand state. Its dedicated pane renders the selected route above the base network. Route framing happens when selection changes or Replay Journey is clicked, not on every frame. Camera pans are bounded to keep the entire supplied journey visible; pointer, wheel, keyboard and drag interaction relinquish follow. Warehouse discussion relinquishes follow without restarting playback.

C. UI fixes

Selected routes now auto-fit with padding and a maximum zoom. Road/air replacement clears the previous selected overlay and markers. Exact multi-vehicle assignments determine the current count and appear in snapshots and popups. Draft scenarios do not replace live selection. Infeasible replacements retain the current selection with a visible notice. Warehouse capacity results resolve the discussed warehouse by structured ID or exact name. Existing full-network routes are visually secondary.

D. New visual features

10-second road/air journey playback; compatible multimodal icon transitions; Replay Journey; reduced-motion final positioning; compact Plan Snapshot; backend-provided reliability and assignment metrics; actual-leg journey strip; before/after cost, ETA and risk comparisons; warehouse emphasis and real-value popup; conditional map legend. Multiple vehicles on the same leg share one counted marker and a popup listing each assignment, avoiding overlapping duplicate markers.

Comparison totals come directly from structured results. Backend-provided deltas are preferred; otherwise the UI only subtracts the displayed authoritative totals. It does not recalculate cost, ETA, risk, reliability, capacities or assigned loads. Risk changes are shown in percentage points. Lower cost, ETA and risk use the decrease style; increases use the tradeoff style, with explicit text so color is not the sole signal.

E. Frontend build

Final `npm run build`: PASS (exit 0). TypeScript compiled and Vite transformed 252 modules; production bundling completed in 1.24 seconds. JavaScript: 619.36 kB (190.29 kB gzip); CSS: 59.15 kB (15.93 kB gzip). The build reports a bundle-size warning above 500 kB; code splitting was left outside this focused change.

F. Tests and evidence

The original four frontend scripts passed before implementation. The backend suite passed before implementation: 88 tests.

Final frontend test run: PASS (exit 0), all seven scripts: the original four plus three new scripts. The DOM map test mounts actual Leaflet/React-Leaflet components with 30 warehouses, 97 vehicles, 62 persisted routes and one selected overlay. It checks fit bounds and padding, secondary network styling, sequential movement, one pending shipment animation, manual camera release, road/air replacement, exact popup data, replay, scoped warehouse focus, absent coordinates, reduced motion, infeasible retention, multimodal transitions and cancellation during active unmount.

The controls test clicks Calculate Plan, closes results with ESC, runs and applies a scenario, filters/searches/edits/adds persisted routes and starts New Chat. API responses are stubbed in this test; it does not modify production routes or network data. The store test checks exact fractional assignments, comparison values, scenario isolation, recovery replacement, no-feasible retention, geometry validation and animation endpoints.

The final backend regression run: `cd intellifleet-server-backendmcp && .venv/bin/python -m pytest tests -q` — 88 passed in 4.64 seconds, with one existing aioredis/distutils deprecation warning.

Frontend rerun: `cd intellifleet-web-main/frontendmain && npm test`. Existing SSR state tests emit non-failing Zustand warnings because browser storage is absent in those tests.

G. Backend contract changes

None. The existing structured `recommended_plan`, `approved_plan`, `recovery_plan`, `baseline`, `scenario`, comparison, assignment and warehouse-capacity payloads provide the necessary information. No backend source was edited for this task, including planning formulas, feasibility, scenario calculations, authentication or upload semantics.

H. Remaining limitations

- The browser bridge was unavailable (`privileged native pipe bridge is not available; browser-client is not trusted`). No live-browser screenshots, visual appearance certification, signed-in end-to-end chat session or live 30-prompt demo run is claimed. DOM tests verify behavior, not real-browser paint quality or device frame rate.
- Supplied detailed polylines are used when available. Otherwise playback follows supplied leg endpoints. Missing or disconnected geometry disables playback with a notice instead of inventing connections; available geometry can still be shown.
- A warehouse is automatically focused only when the structured result identifies one warehouse. Multiple unscoped rows update available data without guessing which warehouse the AI discussed. Missing coordinates leave the camera unchanged.
- Multiple same-leg assignments are grouped in a counted vehicle marker and listed individually in the popup and snapshot. No independent real-time vehicle tracks are invented.
- Optional Pause/Resume was not added. Replay and manual follow cancellation are available.
- Real network counts and feasibility depend on the user's uploaded data. The 30/97/62 verification used a synthetic fixture of that size; it was not a performance benchmark of a signed-in session.

I. Manual demo steps (not executed in a live browser in this session)

1. Start the existing configured backend. In `intellifleet-web-main/frontendmain`, run `npm run dev` and open the local URL printed by Vite. Sign in with an existing account. If needed, upload the existing three CSV files through unified upload. Confirm Network Ready and the expected master counts for those files.
2. Send `Plan 6000 kg from Delhi to Mumbai with a balanced objective.` Check the structured recommendation. For its road selection, check full-route framing, the thick blue selected line, the truck at origin, sequential movement for about ten seconds and final arrival. Open Current shipment to inspect Plan Snapshot. Click the vehicle to inspect exact load/capacity values.
3. Click Replay Journey. Drag the map or use its zoom control while playback runs. Check that the vehicle continues moving while the camera stops following. Replay again to restore automatic framing/follow.
4. Send `Find the fastest feasible way to transport 6000 kg from Delhi to Mumbai.` If the backend selects air, check that the selected truck/road overlay is replaced by aircraft/air geometry, the assigned count follows the new result and the comparison reflects the two structured plans.
5. Send `Plan 18000 kg from Delhi to Mumbai and show capacity, assigned load and utilization for every assigned vehicle.` If the result assigns two vehicles, check Assigned Vehicles = 2, the counted marker, both popup/snapshot assignments and the exact returned loads. Do not expect two if the current network returns a different allocation.
6. Send `Show warehouse capacity for my current shipment.` For a scoped warehouse result, check its map focus, highlighted marker and real inventory/storage/utilization values. Click another existing warehouse to inspect its available data. No focus should occur if coordinates are missing.
7. Send `Plan 6000 kg from Delhi to Mumbai with a balanced objective.` Then send `The Delhi to Mumbai road route is blocked. Find a feasible alternative for my current shipment.` Inspect the actual returned legs. When a feasible revised plan exists, check replacement, bounds, leg strip, movement through all returned stops and the before/after card. Do not expect a particular alternative unless returned by the backend.
8. Exercise a genuinely infeasible disruption in the current network, for example `The Delhi to Mumbai road route is blocked. Replan my current shipment using road only with maximum risk 0.` Confirm the backend actually returns no feasible recommendation/recovery plan. Check `No feasible revised plan — current plan retained.` The automated tests directly exercise a `recovery_plan: null` response; natural-language resolution and current feasibility must be checked in this live step.
9. Send `Create a what-if plan for 6000 kg Delhi to Mumbai if fuel cost increases by 20 percent. Do not apply it.` Check Baseline → Scenario values and that the current map selection remains unchanged. Also run the form's What-if Scenario controls; Apply Plan should update shared selection only after the apply response succeeds.
10. Use the Supply-Chain Planner Source/Destination/Weight/Objective fields and Calculate Plan. Check the same map state and summary update. Close Recommended Plan with its close button or ESC; the selected map plan should remain.
11. Open + Add Route / Route Management. Check All/Road/Air, search by an existing source or ID, Edit Route and + Add New Route. Verify selected overlays do not appear as editable rows. Use a disposable test route/account if saving edits or additions during the demo.
12. Copy an assistant response. Click New Chat. Check that messages, current shipment visuals and planning conversation context clear while warehouse/vehicle/master-route data and Network Ready remain. Check logout/login using the existing flow.
13. Enable reduced motion in the OS/browser and create or replay a plan. Check route framing and final vehicle positioning without playback. If a real multimodal plan is returned, disable reduced motion and check truck/aircraft transitions only on its actual road/air legs.
