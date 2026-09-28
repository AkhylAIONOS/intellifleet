# FedEx presentation runbook

Open **http://127.0.0.1:5178** → **Enter UniFleet** → **FedEx Simulation +**.

**Say first:** “Schedules come from the supplied workbook. GPS, movement and disruptions are labelled simulation data. Operating days are not verified.”

1. **UDRPU → DELGW**, choose presentation date, ready **16:00**, speed **300×** → **Evaluate Cutoffs**.
   Show eligible Air: cutoff **16:30**, departure **20:00**, arrival **21:20**. Click **Start Simulation** (~64 seconds). Retrieval is shown separately; do not claim onward uplift is confirmed.
2. **Reset** → ready **18:00**, speed **600×** → **Evaluate Cutoffs**.
   Show Air rejected by cutoff and eligible Surface: cutoff **21:30**, departure **22:00**, arrival **12:00 next day**.
3. **Start Simulation**. After ~24 seconds, status becomes **IN_TRANSIT**. Point to the moving orange marker and **SIMULATED TELEMETRY** label.
4. Keep **Delay Minutes = 30** → **Inject Delay**. Show alert, revised ETA **12:30 next day**, and “notify gateway / confirm onward handover” recommendation. Nothing is automatically rerouted.
5. **Pause / Resume**, pan/zoom if useful, then **Reset**. The existing planner remains above the FedEx section.

If no movement: check WAITING_FOR_DEPARTURE and simulation speed. Delay injection enables only during an active movement. If the schedule endpoint is unavailable, check the external workbook path and restart the backend. If a run expired, click Reset.

For startup commands, validation results and limitations, see [FEDEx_DEMO_READINESS.md](FEDEx_DEMO_READINESS.md).

**Do not use the Azure production URL for this upgrade.** Local launcher uses a new empty scratch database and disables Azure chat. Production deployment is unchanged. Browser visual verification should be performed before presenting.
