# UniFleet integration result

**PASS — automated integration checks. Visual browser QA remains required.**

Branch: `feature/fedex-simulation`. No deployment, merge, credential change, or commit of the real FedEx workbook. Changes are left uncommitted for review. Existing user data has not been replaced with V2 demo data.

## Data

| Dataset | Rows | Result |
|---|---:|---|
| Synthetic warehouses | 30 | PASS |
| Synthetic fleet | 97 | PASS; 91 road + 6 air allocations |
| Synthetic directed routes | 72 | PASS; 66 road + 6 air |
| Synthetic schedules | 36 | PASS; 12 per mode |

Machine checks cover effective road speeds, duration, coordinates, geodesic lower bounds, costs, capacity, inventory, duplicate identifiers, orphan references, cutoff ordering, and overnight/multi-day arrival arithmetic. Source metadata persists through network import and schedule/live adapters. Legacy imports remain compatible with a wider speed ceiling and an explicit warning.

## Map and interface

- Dashboard navigation: Plan, Schedules, Live Operations, Network, AI Chat. Chat stays alongside the working map.
- Truck, plane and train SVG markers; heading rotation, selection styling, and hover details.
- Show-all with All/Surface/Air/Rail/FedEx/Synthetic filters; unmapped templates remain visible in the movement list.
- Template-only schedules never claim live physical movement. A template represented by a simulation is suppressed; the individually selected schedule simulation is not rendered twice by the all-movements layer.
- Direct active network edges preferred; connected paths use the existing directed graph engine. No connection returns `NO CONNECTED ROUTE`.
- Arbitrary node sequences render; tested Delhi–Mumbai, Mumbai–Bengaluru, Ludhiana–Madurai, Kochi–Chennai and Jaipur–Lucknow.
- One Python runtime drives 10/50/100 distinct services. Batch polling is once per second. Map fitting occurs on show-all, explicit fit, or selection, not routine telemetry updates.
- Selected movement supports pause/resume, stop and 30-minute delay injection. ETA and alert/recovery outputs come from Python.

## AI integration

Existing network planning, warehouse, cost, capacity, risk, SLA, scenario and disruption tools remain intact. A deterministic operations adapter handles live movement lists, Air/Rail/Surface queries, delayed trucks, selected shipment mapping, revised ETA, delay what-if, schedule eligibility and origin-service alternatives after a missed cutoff. The selected simulation ID is passed by the chat client and resolved only within the authenticated user's runtime.

The new adapter uses bounded phrase recognition; unrestricted paraphrase coverage is not claimed. Unrecognized planning requests retain the existing supervisor/tool flow. New operational values are calculated by Python. No Azure LLM was invoked for telemetry or stress tests, and live Azure conversational evaluation was not rerun. When a shipment is ambiguous, the adapter asks for a shipment ID. Without a deadline/onward operating calendar, SLA feasibility remains unverified. Hypothetical network recovery does not assert real FedEx fleet availability or in-transit transfer feasibility.

## Tests and regressions

- Backend: `.venv/bin/python -m pytest tests -q` — **199 passed**. Includes existing FedEx UDRPU→DELGW, original planner, atomic import, auth, context, scenario and disruption tests.
- Frontend: `npm test` — **14 scripts passed**. Includes existing full dashboard/Leaflet/planner regressions and the new 100-entity movement test.
- Build: `npm run build` — **PASS**. Vite still reports a bundle-size advisory; no build error.
- `git diff --check` — **PASS**.
- The old FedEx map test now asserts a real truck marker instead of a circular marker, retaining position, fit, pan, tooltip and reset assertions.
- Visual browser connection was unavailable (no browsers discovered). DOM tests do not replace human visual review.

## Stress results

FedEx benchmark (`PYTHONPATH=. .venv/bin/python tests/benchmark_fedex.py`):

| Runs | Snapshots/sec | Mean ASGI GET ms | Errors / drops |
|---:|---:|---:|---|
| 10 | 20,096 | 4.085 | 0 / 0 |
| 50 | 17,392 | 3.549 | 0 / 0 |
| 100 | 19,566 | 3.890 | 0 / 0 |

Unified V2 benchmark (`PYTHONPATH=. .venv/bin/python tests/benchmark_operations.py`):

| Entities | Create ms | Snapshots/sec | Batch snapshot ms | Errors / dropped updates |
|---:|---:|---:|---:|---|
| 10 | 14.02 | 42,969 | 2.18 | 0 / 0 |
| 50 | 19.51 | 45,729 | 2.19 | 0 / 0 |
| 100 | 22.83 | 48,257 | 2.60 | 0 / 0 |

Local in-process measurements, not network fan-out or browser FPS claims. The FedEx benchmark includes tracemalloc and ASGI measurements, so its throughput is not directly comparable to the unified runtime benchmark. The unified benchmark uses a temporary database.

## Files changed

- `backend/operations/{data,service,routes,chat}.py`: validation, canonical adapters, batch/network simulation, API and chat intents.
- `backend/fedex/{models,eligibility,simulator,alerts}.py`: provenance, multi-day ETA, arbitrary path telemetry, hypothetical network recovery.
- `backend/planning/{database,service}.py`, `backend/routes/upload/network_upload.py`, `backend/api/chat_api.py`, `main.py`: provenance persistence and integration.
- `scripts/generate_synthetic_v2.py`, `public/synthetic_v2/{warehouse,vehicle,routes,schedules}.csv`: reproducible datasets.
- `DashboardPage.tsx`, `FedExPanel.tsx`, `LiveOperations.tsx`, `NetworkUpload.tsx`, `MapView.tsx`: unified workspace and controls.
- `MapLayers/{FedExLayer,NetworkMovementsLayer,movementIcon}.tsx/ts`, `store/operationsStore.ts`: movement layers, filters, icons and selection.
- `api/{chat,fedex}.ts`, `hooks/useRouteAgent.ts`, `types/api.ts`: selected movement chat/map actions and source selection.
- `tests/test_operations.py`, `tests/benchmark_operations.py`, `tests/run-network-movements.mjs`, `tests/run-fedex-map.mjs`: new integration coverage and marker regression update.
- `SYNTHETIC_DATA_ASSUMPTIONS.md`, this report: assumptions, results and manual QA.

## Visual QA required

1. Open the local dashboard. Confirm all five workspace controls fit and AI chat remains usable while switching workspaces.
2. **Network:** download V2 warehouse/vehicle/routes CSVs, choose all three, then click **Upload & Process** once. Confirm 30 warehouses, 97 fleet entries and 72 routes. Inspect city labels and import the separate schedule CSV if desired.
3. **Plan:** calculate 6,000 kg Delhi→Mumbai. Inspect assigned capacity/cost/risk and map geometry. Exercise the existing disruption/scenario controls.
4. **Schedules → Synthetic:** choose `SYN-UDR-STN`→`SYN-DEL-GTW`, ready 18:00 IST. Evaluate runs, start a simulation, hover the marker, and inspect progress/ETA. Inspect Delhi→Mumbai Surface/Rail arrivals with day offsets; ready after the last cutoff must yield no confirmed eligible service.
5. **Schedules → FedEx:** reset the synthetic run, select FedEx workbook, choose UDRPU→DELGW at 18:00, evaluate and start. Confirm source labels distinguish the workbook from simulated telemetry.
6. **Live Operations:** enable **SHOW ALL MOVEMENTS**, run **Simulate 10**, then **50**, then **100**. Check truck/plane/train visibility, all six filters, compact hover fields, and stationary template labels.
7. Pan and zoom for at least ten seconds while telemetry updates. The map must stay where placed. **Fit network** should refit once.
8. Select Kochi→Chennai and click **Plan & simulate 6000 kg**. Confirm the selected path goes through loaded intermediate nodes. Select its marker and inject a 30-minute delay; verify ETA shift, alert and recovery explanation. Test pause/resume/stop.
9. Ask chat: “Show all Air movements”, “Which movements are delayed?”, “Show this shipment on the map”, “What is its revised ETA?”, and “What happens if this truck is delayed by 30 minutes?” after selecting the relevant movement. Check source labels and that what-if does not mutate the live run.
10. Repeat at narrower window width; inspect panel overflow, tooltip readability and map pan responsiveness with 100 entities.

Runtime limitations: single-process, ephemeral simulation/schedule state; six-hour simulation retention; 500-run global cap; approximate city/polyline geometry; no actual FedEx GPS or automatic fleet reservations. See the assumptions document for modelling details.
