# UniFleet final QA report — 29 September 2026

**FINAL RESULT: PASS — ready in the verified local QA environment (5189 frontend / 4219 backend).**

No known presentation-blocking P0 or practical P1 remains in the tested demo flow. This is a local demo readiness result, not a production deployment certification. No push, merge, Azure deployment or production change was performed.

## Before

Baseline: branch `feature/fedex-simulation`, HEAD `d9abe606ce78449b68d64995dae5afff16d48dff`. Existing uncommitted integration work was preserved. The initial file list is in [baseline-git.txt](qa/readiness/baseline-git.txt); baseline observations are in [BASELINE.md](qa/readiness/BASELINE.md).

- Backend: **206 passed**; frontend scripts and production build passed.
- Browser reproduced the live-answer fleet dump, duplicate upload UI, misleading current-shipment label and planning-overlay route count.
- Source inspection identified missing recommendation retrieval, UTC planner presentation, verbose score dumps, unhandled planner form failures and lost selected-simulation context after refresh.
- Initial E2E selectors were too strict for nested labels, and reading an upload response raced with the intended page reload. Those test defects were corrected; they are not claimed as product failures.
- The earlier explicit-origin CORS fix was already present in the working tree and is retained and covered by regression tests.

## Fixed

| # | Priority | Root cause and fix | Files/components | User-visible result |
|---|---|---|---|---|
| 1 | P1 | Live chat used the entire collection without lane filtering. Added exact identifier boundaries, lane filters, selected context, ambiguity handling and bounded list responses. | `backend/operations/chat.py` | A current-shipment query returns the relevant owner-scoped movement, not 100 unrelated entries. Arbitrary shipment IDs and other lanes are tested. |
| 2 | P1 | Existing alerts were consulted only for “risk” wording. Read the latest deterministic alert for relevant shipment answers. | `backend/operations/chat.py` | Delay, original/revised ETA, recommendation and recovery limitation appear together. |
| 3 | P1 | Planner formatter explicitly converted to UTC; movement UI displayed raw ISO strings. Convert aware instants with Asia/Kolkata/Intl formatting; preserve unknown timezone honesty. | `backend/agents/supervisor.py`, `operationalTime.ts`, movement panels/layers | Planner and live arrivals are readable in IST, including day rollover. |
| 4 | P2 | Default formatter emitted every internal score and all alternatives. Gate breakdowns on explicit requests and show the most relevant alternative by default. | `backend/agents/supervisor.py` | Concise recommendation, route, vehicles, cost, ETA, risk, reliability and tradeoff; detailed calculations remain available. |
| 5 | P1 | Planner async actions had no catch/display and null recommendations disappeared silently. Add safe error/infeasibility messages and transport-mode selection. | `PlanningPanel.tsx` | Backend failure and infeasible Air/load requests have useful visible results. |
| 6 | P2 | Chat and Network workspace both mounted NetworkUpload. Remove the redundant chat instance. | `ChatPanel.tsx`, `DashboardPage.tsx` | One upload location, more room for chat, no duplicate file controls. |
| 7 | P2 | Persistent planning snapshot was labeled “Current shipment” across workspaces. Label it as last planning result and collapse it during live work. | `PlanVisuals.tsx`, `ChatPanel.tsx` | Previous plan is preserved without implying it belongs to the current live shipment. |
| 8 | P2 | Map metric counted a planning overlay as another base route. Exclude planning overlays from the network count. | `DashboardPage.tsx` | Summary remains **72 routes**, not 73 after planning. |
| 9 | P2 | Schedule templates and stopped runs were drawn as fleet vehicles. Exclude them from the batch map layer; retain templates in the labeled inspection list. | `NetworkMovementsLayer.tsx`, `MapLegend.tsx` | Less marker clutter; filtered simulation icons have clearer layer semantics. |
| 10 | P1 | Selected live state lived only in memory. Retain non-secret simulation ID/source in session storage and restore through the protected owner-scoped endpoint. | `FedExPanel.tsx`, `api/fedex.ts` | Refresh reconnects to the selected simulation while the backend remains running. Reset removes saved selection. |
| 11 | P2 | Leaflet replay/legend controls shared the bottom area with network metric cards. Reserve vertical space and assert non-overlap in Chrome. | `Dashboard.css` | Replay, legend and metric cards remain separate at tested desktop sizes. |
| 12 | P1 | Empty/malformed/non-UTF8 CSV parsing could escape as a server error. Return safe 422 validation errors before a transaction. | `network_upload.py` | Clean validation feedback; existing network unchanged. |
| 13 | P2 | Separate schedule imports reused the “Network ready” success message. Display schedule-specific status/count. | `NetworkUpload.tsx` | “Schedules ready” and **36 synthetic schedules imported**. |

## UI/UX improvements and cleanup

The existing visual design and workspaces are preserved. Workspace descriptions explain that Schedules follows one timed service, Live Operations shows the wider fleet, and Network manages the planning files. Active workspace styling is clearer. Selected planner and live-operation layers remain explicitly independent.

Removed the duplicate chat upload component/import and routine dashboard success console logs. No functioning planner, FedEx panel, simulator, AI integration, SSE path or old route-management capability was removed. No repository-wide cleanup or architectural rewrite was attempted.

## AI improvements

Before: a lane-specific live question dumped the wider fleet; recommendations were missing; normal planning answers included normalized scores and UTC timestamps.

After: live responses select by shipment ID, exact lane or selected movement and retrieve backend alerts. Ambiguous references ask for a shipment rather than guessing. List queries are bounded to ten entries with a total count. Default planning answers use concise professional language and IST. A real configured Azure planning request was exercised in Chrome; all logistics figures still come from PlanningService. Unit regressions verify detailed scoring remains available on request.

Evidence: [live answer](qa/readiness/final-live-answer.txt), [planner answer](qa/readiness/final-planner-answer.txt), [live AI screenshot](qa/readiness/final-live-ai.png).

## Backend improvements

Operational retrieval and presentation changed; deterministic logistics calculations did not. Import parsing now classifies malformed CSVs as validation errors. Existing authentication, cross-file validation and atomic transaction behavior remain intact. Tests inject a database failure after writes begin and verify a complete unchanged database snapshot after rollback.

The QA runner uses temporary SQLite and in-memory Redis to isolate destructive tests. It loads the existing AI configuration in process without copying credentials. Global authentication is not disabled.

## Data validation

Files were **not regenerated**. Validation passed for **30 warehouses, 97 vehicles, 72 routes, 36 schedules**.

- 66 road routes: 92–1,401 km; implied route speeds **28.36–53.58 km/h**.
- 6 air routes: 515–1,561 km; scheduled durations **108–204 minutes**, inclusive route assumptions rather than aircraft cruise speed.
- Vehicle capacities: **2,000–16,000 kg**.
- Synthetic route base-cost assumptions: road ₹28/km; air ₹70/km. Planner total cost additionally reflects the existing deterministic load/vehicle/handling calculation; these are demo assumptions, not quoted carrier tariffs.
- Nonnegative cost/capacity, unique IDs, coordinate bounds, cross-file references, risk/reliability ranges, road-speed plausibility, geodesic distance and schedule rollover are covered by the consistency tests.

Detailed numeric audit: [data-audit.json](qa/readiness/data-audit.json). FedEx source values were not changed.

## FedEx flow result

**PASS in actual Chrome:** UDRPU → DELGW on 29 September 2026.

- 16:00 ready: Air and Surface eligible; Air 6E 6229 selected for earlier scheduled arrival.
- 18:00 ready: Air misses the 16:30 cutoff; Surface Bolero pickup remains eligible before 21:30.
- Surface: ETD 22:00; scheduled arrival **30 Sep 12:00 IST**.
- In-transit 30-minute delay: revised arrival **12:30 IST**; original schedule unchanged; warning and conservative recommendation visible.
- Pause/resume, speed change, arrival, stop, reset, browser refresh and interrupted SSE reconnect passed.
- Additional exact workbook lanes AGRGA→DELGW, AWY→BNC and BDQA→BOMA were evaluated through the browser API client, without gateway equivalence inference.
- Ready 23:59 correctly reports no confirmed eligible service.

## Planner result

**PASS:** Delhi→Mumbai, Delhi→Bengaluru, Mumbai→Bengaluru, Kochi→Chennai and Kolkata→Guwahati. Chrome exercised balanced, cheapest, fastest, Ground and Air; Kochi→Chennai Ground has multiple legs. Kochi→Chennai Air and a 999,999 kg load correctly return infeasibility. An 18,000 kg request exercises capacity combinations. SLA and what-if comparison/discard passed. Existing backend regression coverage also preserves multimodal, alternatives and disruption/recovery behavior; every pair is not assumed to support every mode.

V2 Delhi→Mumbai 6,000 kg example: Ground, TRK-031, ₹275,796.50, 31.19 h, risk 14.05%, reliability 95%, utilization 85.71%. Air tradeoff: ₹382,623.50 more and 25.67 h faster. Arrival timestamp varies with request time and is displayed in IST.

## Map and stress result

**PASS:** truck/plane/train icons; Surface/Air/Rail/All filters; hover information; selection; pan; zoom; fit; separate selected-plan layer. Chrome tested 1440×900, 1280×800 and 1920×1080 layouts, no horizontal overflow, usable chat/map, and no replay/legend overlap with metrics.

Chrome rendered **10, 50 and 100** demo movements. Initial render timings are recorded in `final-browser.json`; they are local observations, not a sustained-FPS benchmark. Python stress measured zero errors and zero dropped updates for each batch over 40 ticks; batch snapshot time was below 1 ms locally. [Stress evidence](qa/readiness/stress-backend.txt).

## Final regression gate

| Gate | Result | Evidence |
|---|---|---|
| Full backend | **214 passed / 0 failed** | `qa/readiness/final-backend.txt` |
| Full frontend scripts | **16 passed / 0 failed** | `qa/readiness/final-frontend.txt` |
| Real Chrome E2E | **21 passed / 0 failed** | `qa/readiness/final-browser.json`, `final-e2e.log` |
| Production build | **PASS** | `qa/readiness/final-build.txt` |
| Runtime JS/React errors | **None in final browser suite** | browser issues array |
| Unexpected HTTP/console/network failures | **None** | controlled 401/403/422/503 and connection-abort probes are explicitly recorded as expected |

The E2E suite includes real UI actions and browser-originated API calls through the same authenticated Axios client. It does not mock planner, schedule, importer or simulation responses. Only failure-handling scenarios inject controlled network/status faults. Test selector/race corrections are documented in the baseline; no assertions were weakened to hide product failures.

## Known limitations

1. FedEx GPS/road geometry is not provided. Selected FedEx Surface still uses labeled approximate straight-line demo geometry. No authoritative route geometry was invented.
2. Workbook calendars, verified recovery fleet/capacity and onward schedules are unavailable. Recommendations remain conservative and no automatic reroute is claimed.
3. Simulation runtime and custom schedule imports are single-process/ephemeral. Browser refresh restores a valid selected run, but backend restart clears runs; QA database itself is disposable.
4. Dense overlapping movements can still occur on shared corridors; selection and mode filters help. No new clustering architecture was added before presentation.
5. Tile imagery and Azure calls require network access. The build has the existing >500 kB chunk warning; unit tests have existing dependency/storage warnings. These are not observed browser crashes.
6. Final end-to-end evidence is for the isolated **4219/5189** environment. Existing user-owned 4200/5178 processes were not stopped; they need their own restart to load source changes.

## Git and handoff

Stay on `feature/fedex-simulation`. The validated integration/readiness changes and evidence are suitable for a local-only commit. Runtime `backend/agents/token_usage.txt` changes are intentionally excluded because they include prior activity and QA accounting, not product code. The FedEx workbook and environment files remain excluded. See the final chat handoff for the local commit identifier and final working-tree status.

Presentation: [demo runbook](UNIFLEET_DEMO_RUNBOOK.md) and [simple-English guide](UNIFLEET_PRESENTATION_GUIDE.md).
