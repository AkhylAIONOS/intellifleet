# FedEx outbound demo readiness

## Implementation

Additive Station → Gateway simulation on `feature/fedex-simulation`, based on baseline `26b628fba483cab07d04d1fe8846b83a595da81b`. Existing deterministic `PlanningService`, Ground/Air algorithms, auth and network upload are unchanged. No packages added, production data changed, or Azure deployment performed.

Implemented: local XLSX importer, validated schedule models, cutoff eligibility, overnight rollover, accelerated Python simulation, opt-in seeded disruptions, manual events, automatic alerts, deterministic revised ETA, conditional recovery advice, authenticated APIs, SSE, dashboard controls and an isolated Leaflet layer. `demo_inputs.json` contains inputs only. Results come from the workbook and engine.

## Architecture

`local workbook → importer → schedule eligibility → Python simulation clock → snapshots / synthetic events → deterministic alert and recovery advice → authenticated SSE → FedEx Zustand store → existing dashboard / Leaflet map`

- Root backend `main.py` registers `/fedex` and starts a 250 ms runtime tick; `backend/main.py` is untouched.
- Runtime is bounded in-process memory: 500 runs, 100 events per run, six-hour retention. Run exactly one backend worker. Process restart clears runs; the workbook is cached until restart. No FedEx database migrations, chat Redis writes or production network ingestion.
- SSE sends full snapshots every 500 ms. Reconnect receives current state and bounded event history; frontend rejects stale/wrong-run updates. Streams rotate after five minutes to reauthenticate. Tokens stay in Authorization headers, never URLs.
- Controls: create, pause, resume, speed, stop, reset. Manual disruption is the default. API also supports slowdown, unexpected stop and Surface-only breakdown. Delay/stop/breakdown hold movement for the configured simulated duration; slowdown reduces remaining movement rate to produce exactly the requested additional delay. These durations are demo inputs, not predicted repairs.
- Optional random events use a fixed seed and a 25% one-event probability after 25% progress, on runtime ticks. Reproduction assumes the same clock progression; manual mode is preferable for presentations.
- LLM is absent from FedEx calculations. An explicit adapter calls `PlanningService(':memory:').plan(...)` only when a caller supplies a compatible verified network and shipment. Schedule-only runs do not invent such inputs. Planner results still require FedEx schedule validation.
- Recovery checks provided services for the selected schedule date. Origin-ready alternatives are conditional once a shipment is in transit. It does not assume a return leg, next-day operating calendar, vehicle capacity, cost, SLA or onward flight. No corrective action executes automatically.

## Source and assumptions

Workbook: `/Users/akhilbabbar/Downloads/Sample Network plan - Air & Surface.xlsx`.

Override location with `FEDEX_WORKBOOK_PATH` if necessary. Workbook remains external, unmodified and excluded by `.gitignore`. There are 38 schedule rows: 10 Air, 21 Surface and 7 Train (canonical `RAIL`). Original mode and cell values are retained with sheet/row provenance.

- Handover is the eligibility cutoff; ready time equal to cutoff is eligible. Selection is earliest scheduled arrival among eligible provided services, with deterministic departure/ID tie-breaking, not Air-first priority.
- Simulation date means the **handover date**. A departure clock earlier than handover rolls to the next day; arrival earlier than departure rolls forward; retrieval earlier than arrival rolls forward. These are explicit template interpretation rules, not verified operating calendars.
- Asia/Kolkata is an explicit demo assumption because the workbook does not state its timezone. Offset-aware ready inputs are converted to it; naive ready inputs are interpreted in it.
- Excel time formats are read so `TT (hours)` formatted as clock/duration is interpreted as an Excel day fraction, not decimal hours. Source values are preserved. Malformed or inconsistent rows are excluded from eligibility, not repaired.
- Missing cutoff is represented as unavailable and not confirmed eligible. The current workbook's imported rows have populated cutoffs; missing-cutoff behavior is covered with independent tests.
- All rows warn that operating days are unverified. `Post Monsoon` run text is preserved; no seasonal dates are invented.

### Source validation warnings

Surface rows 11 and 13 (`DDU → NDLS`, Train 12559): ETD 22:15 → ETA 08:30 implies **10h15 / 615 minutes**, while source TT reports **14h / 840 minutes**. Both rows are retained with `TRANSIT_MISMATCH`, `valid=false`, and excluded from selection. Original values are unchanged.

### Real versus synthetic

Real supplied information: station/gateway codes, city/lane, mode, run, flight/details, handover, ETD/ETA, retrieval, vehicle count and transit time where supplied. A source vehicle count is not proof of allocatable capacity.

Synthetic: shipment identity, simulation date, accelerated clock, movement, speed, event occurrence/duration, interpolated coordinates and simulation state. Every snapshot/event carries `synthetic_data=true`; coordinates use `location_source="DEMO_SIMULATION"`.

Only UDRPU and DELGW have demo coordinates: approximate Udaipur/Delhi city centres, **not verified FedEx facilities or road geometry**. Other lanes can be evaluated but cannot start map simulation without a labelled location mapping. The `ARRIVED_AT_GTW` state is a synthetic end-of-movement milestone aligned with source ETA, not proof of physical receipt. Air retrieval is displayed separately; onward readiness/uplift is unverified.

## Tests and benchmark

- Backend: **176 passed, 0 failed** (35 new FedEx tests and 141 existing tests). Covers existing Ground/Air planning, warehouse/capacity, SLA, scenarios, disruptions/breakdowns, contextual chat/MCP, authentication/demo access and fresh startup.
- Tests run from an isolated temporary directory with a generated test signing key and inert Azure provider placeholders (`example.invalid`). No real Azure request is needed by these tests. Live Azure chat is not asserted by these results.
- Frontend: all 13 test scripts passed, including existing dashboard/auth/map/journey/state tests and new controls/stale-snapshot/reset/Leaflet tests.
- `npm run build` passes. Existing bundle-size advisory remains; no build error.
- Live HTTP/SSE + React/Leaflet DOM smoke passes: health, frontend, demo login, real workbook, both cutoff scenarios, completed Air run, moving Surface marker, +30-minute event/ETA, alert/recommendation, pause/resume/stop/reset, empty-network planner and warehouse endpoint.
- Browser plugin reported no available browser. Pixel-level visual/browser inspection is outstanding; actual React/Leaflet DOM and live SSE were exercised using existing test dependencies. No browser automation package was added.

Measured local in-process benchmark, with `tracemalloc` enabled:

| Runs | Snapshot updates/s | Mean event ms | Mean ASGI GET ms | Retained / peak growth MB | Errors / drops |
|---:|---:|---:|---:|---:|---:|
| 10 | 46,915 | 0.098 | 2.156 | 1.030 / 1.072 | 0 / 0 |
| 50 | 46,734 | 0.097 | 2.372 | 0.394 / 0.547 | 0 / 0 |
| 100 | 46,207 | 0.095 | 2.081 | 0.720 / 0.771 | 0 / 0 |

The 10-run result includes one-time library allocation. These are accelerated in-process calculations and TestClient requests, not network SSE fan-out capacity. Actual runtime is intentionally paced at four updates/second/run, with two SSE snapshots/second/client. No dropped events, simulations or expected update iterations. A 500-run benchmark was not needed for the demo.

## Exact local startup

Run these in separate terminals (existing dependencies are sufficient):

```sh
/Users/akhilbabbar/Downloads/IntelliFleet/intellifleet-server-backendmcp/.venv/bin/python /Users/akhilbabbar/Downloads/IntelliFleet/intellifleet-server-backendmcp/scripts/run_fedex_local.py
```

```sh
VITE_API_BASE_URL=http://127.0.0.1:4208 VITE_DEMO_ACCESS_ENABLED=true npm --prefix /Users/akhilbabbar/Downloads/IntelliFleet/intellifleet-web-main/frontendmain run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

Open `http://127.0.0.1:5178`. Backend health: `http://127.0.0.1:4208/health`.

The local backend launcher changes cwd to a **new temporary directory** before importing the real root app. Existing startup/auth creates a fresh scratch database there; the repository's `users.db` and `.env` are not opened by the launcher. It generates a process-local signing key, enables loopback demo access and disables LLM use. Its Redis address is isolated from production. Legacy chat is deliberately unavailable in this offline launcher; the existing network is empty. The feature itself does not disable chat in the normal application.

To rerun the live smoke while both servers are running:

```sh
cd /Users/akhilbabbar/Downloads/IntelliFleet/intellifleet-web-main/frontendmain
node scripts/check-fedex-live.mjs
```

## Exact demo sequence

1. Click **Enter UniFleet**, then **FedEx Simulation +**. Keep UDRPU → DELGW. Pick the presentation date; all times are IST.
2. Set ready time **16:00**, speed **300×**, click **Evaluate Cutoffs**. Air Run 1 (6E 6229) handover 16:30 / ETD 20:00 / ETA 21:20 is eligible. Click **Start Simulation**. Approximate total playback: 64 seconds. Air retrieval is 23:50, displayed separately.
3. Click **Reset**, set ready time **18:00**, speed **600×**, evaluate again. Air is too late; Surface Run 1 (Bolero pickup), handover 21:30 / ETD 22:00 / ETA 12:00 next day, is eligible.
4. Click **Start Simulation**. Departure begins after about 24 real seconds. Once IN_TRANSIT, click **Inject Delay** with **30** minutes. Revised ETA becomes 12:30 next day. Show the alert and recommendation; no reroute is executed. Without pause, total run is about 111 seconds including this delay.
5. Pan/zoom the map, pause/resume if useful, then **Reset**. Collapsing the FedEx panel preserves its running stream. Closing/reloading the page loses the UI run reference; runs expire server-side or disappear on restart.

## Limitations and future replacement points

- Single-process runtime is for a local demo, not multi-worker production; durable/shared state and distributed simulation ownership are not implemented.
- No customer calendar, geofenced facility receipt, exact geometry, live traffic, verified speed, capacity reservation, SLA, operating cost or onward uplift is fabricated.
- Real FedEx schedule/API feeds would replace the local importer input. Verified station/geofence/route geometry would replace demo coordinates. Real GPS/scan events would replace `Simulation` snapshot generation while keeping the telemetry contract, alert display and map layer. Operational recovery needs verified network/capacity inputs before the existing planner adapter can be used.
- Workbook input must be present on any future host. All imported rows can be inspected through the authenticated summary endpoint.
- Visual browser QA and live Azure chat remain unverified locally.

## Deployment

**DEPLOYMENT BLOCKED — USER ACTION REQUIRED**

No Azure commands, SSH, production configuration edits or deployment were performed. The local implementation intentionally uses single-process ephemeral state and an external workbook; a confirmed isolated deployment target, workbook provisioning and rollback plan are required before production action. Browser visual verification is also outstanding. The existing working deployment remains untouched.
