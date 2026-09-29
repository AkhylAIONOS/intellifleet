# UniFleet — 7–10 minute demo runbook

## Before presenting

Use the verified isolated environment: **http://127.0.0.1:5189** (backend **4219**). It uses a disposable local database, normal JWT authentication through demo entry, in-memory chat history and the existing configured Azure connection. No production service is changed. The workbook remains local and uncommitted.

If these QA processes are no longer running, start from the repository root in two terminals:

```sh
intellifleet-server-backendmcp/.venv/bin/python qa/readiness/serve_backend.py
```

```sh
cd intellifleet-web-main/frontendmain
VITE_API_BASE_URL=http://127.0.0.1:4219 VITE_DEMO_ACCESS_ENABLED=true npm run dev -- --host 127.0.0.1 --port 5189 --strictPort
```

The backend runner loads the existing local environment without copying credentials. It creates a fresh database on every start, so re-upload the network after a restart. Only stop QA processes you own. For the original 4200/5178 environment, restart its backend to load the CORS/source fixes and use its supported login; the final browser evidence was captured on 4219/5189.

Open the page, click **Enter UniFleet**, then **NETWORK**. Upload these exact files from `intellifleet-web-main/frontendmain/public/synthetic_v2/`:

1. `warehouse.csv` in Warehouse CSV
2. `vehicle.csv` in Vehicle CSV
3. `routes.csv` in Routes CSV

Click **Upload & Process**. After reload, open **NETWORK** again and confirm **30 / 97 / 72**. Synthetic schedules are available by default; the separate schedule picker can import `schedules.csv` and should report **36**. Keep the local FedEx workbook available at its configured path. Do not upload it as a CSV.

Use a desktop viewport around 1440×900 or larger. Map tiles need internet connectivity. Refresh can restore the selected live simulation while the backend remains running; backend restart clears simulations and custom schedule imports.

## Presentation sequence

| Time | Action | Expected result / narration |
|---|---|---|
| 0:00–0:45 | Open **NETWORK** and show summary | “Three files define our facilities, fleet and connections. Schedule data is separate.” **30 warehouses / 97 vehicles / 72 routes.** |
| 0:45–2:00 | In AI chat enter **“Plan 6000 kg Delhi to Mumbai using the best overall option.”** | Recommended Ground plan, **TRK-031**, **6,000 / 7,000 kg (85.71%)**, **₹275,796.50**, **31.19 h**, **14.05% risk**, **95% reliability** with current calculated arrival in IST. Air is **₹382,623.50** more expensive and **25.67 h** faster. Values are from the current V2 data; arrival date/time depends on request time. |
| 2:00–2:45 | Open **LIVE OPERATIONS**, click **Simulate 50**, switch **SURFACE / AIR / RAIL / ALL**, hover a vehicle, click **Fit network** | Trucks, planes and trains represent simulated movements. Explain that the selected planning route is a separate layer. Switch **SHOW ALL MOVEMENTS** off before focusing on the FedEx lane. |
| 2:45–3:45 | Open **SCHEDULES**. Source **FedEx source workbook**. Origin **UDRPU**. Gateway **DELGW**. Date **29/09/2026**. Ready **16:00**. Click **Evaluate Cutoffs**. | Air **6E 6229** and Surface eligible. Air cutoff **16:30**, ETD **20:00**, ETA **21:20**; earliest arrival selects Air. |
| 3:45–4:30 | Change ready time to **18:00**, click **Evaluate Cutoffs** | Air missed cutoff; Surface **Bolero pickup** remains eligible. Cutoff **21:30**, ETD **22:00**, ETA **30 Sep 12:00**. Read the eligibility explanation. |
| 4:30–5:30 | Set speed **3600×**, click **Start Simulation** | Starts assigned/waiting, then becomes **IN_TRANSIT** after about four real seconds. The truck moves along approximate demo geometry. |
| 5:30–6:15 | Once **IN_TRANSIT**, click **Inject Delay** with **30** minutes. Then **Pause** promptly. Scroll the schedule panel if needed. | Warning appears. Scheduled ETA stays **30 Sep 12:00**; current ETA is **12:30**. Recommendation: notify gateway, confirm onward handover, continue monitoring. |
| 6:15–7:30 | Ask **“What is happening with the current UDRPU to DELGW shipment? Show its current status, delay, revised ETA and recommended action.”** | One relevant shipment, Surface/Bolero pickup, delay **30 min**, scheduled **12:00 IST**, revised **12:30 IST**, conservative recommendation and recovery limitation. No unrelated fleet dump. |
| 7:30–8:30 | Explain source provenance and future GPS integration | Workbook timings are source data; map positions are synthetic. Real GPS adapters can feed events later; verified recovery data is still necessary. |

At 3600×, an entire 14-hour trip takes about 14 real seconds after departure. Inject the delay promptly; pause after injection so the audience can read the result. At 600×, waiting from 18:00 to 22:00 takes about 24 seconds, leaving more time to narrate.

## Optional checks if time permits

- **PLAN**: Kochi → Chennai, Ground, 6,000 kg → a connected multihop route.
- Kochi → Chennai, Air → an honest infeasibility explanation.
- Ask for **“show score breakdown and explain calculation”** to explain that scoring is deterministic.
- **Resume**, change speed and **Apply Speed**, then **Stop** or **Reset** after the demonstration.

## Recovery during the demo

- **Network empty after QA backend restart**: re-upload the three V2 files.
- **Upload connection error**: verify backend health/port and frontend origin; do not disable authentication.
- **No eligible service**: check source, exact station/gateway, date and ready time. Reset an existing simulation before changing its inputs.
- **Trip already arrived**: Reset, keep the same 18:00 inputs, start again and inject while IN_TRANSIT.
- **AI service unavailable**: the **PLAN** form still runs the deterministic planner. Live shipment status queries use deterministic operational state. State the AI limitation honestly.
- **Map tiles slow**: geometry/vehicle overlays can still render; avoid implying a blank base map is real tracking loss.
- **No workbook**: do not substitute synthetic schedules while labeling them FedEx. Restore the configured local workbook first.
