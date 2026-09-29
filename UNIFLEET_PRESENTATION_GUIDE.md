# UniFleet presentation guide

## What UniFleet is

UniFleet brings network planning, timed services and simulated live operations into one workspace. It answers two different questions: **“What is the best feasible plan?”** and **“What is happening to this movement now?”**

The current synthetic network has **30 warehouses, 97 vehicles and 72 routes**, plus **36 synthetic schedules**. The FedEx workbook is a separate source of supplied service timings.

## Understand the input files

| Input | What it means | What it enables |
|---|---|---|
| `warehouse.csv` | Facilities, locations, inventory and operating assumptions | Where freight starts, ends or transfers; stock and capacity checks |
| `vehicle.csv` | Vehicles, their locations, capacities, costs and availability | Feasible vehicle selection and utilization |
| `routes.csv` | Connections, modes, distances, durations, costs and risks | Direct and multihop route planning |
| `schedules.csv` | Synthetic timed station-to-gateway services | Cutoff, departure and arrival evaluation, including overnight services |
| FedEx workbook | Supplied Air/Surface/Rail service and handover times | Exact workbook station/gateway service eligibility |

The three network CSVs are uploaded together. UniFleet validates all three and their references before replacing the network in one database transaction. An invalid file leaves the existing network intact. Schedule upload is separate and does not replace the fleet.

## How the system makes a decision

1. **Azure GPT understands the request.** It identifies intent, locations, weight, objective and conversational context.
2. **Python calculates the answer.** The deterministic PlanningService checks routes, compatible vehicles, capacity, cost, duration, risk, reliability and deadlines.
3. **The answer explains those results.** GPT does not invent cost, capacity, ETA, cutoff or a recovery vehicle. Default answers show the decision and main tradeoff; detailed scoring remains available when requested.
4. **The map makes the result visible.** Network connections, the selected plan and live simulations are distinct layers. The selected plan is independent of live movement filters.

“Cheapest,” “fastest” and “balanced” can select different feasible plans. A missing Air or multimodal option is not a software failure: UniFleet should say it is infeasible when the loaded network cannot support it.

## Planning versus live operations

**Plan** finds a feasible route and fleet assignment in the loaded network. Its ETA is a calculated plan, not a GPS observation. User-facing arrival times are shown in IST.

**Schedules** checks whether a shipment is ready before the service’s handover cutoff, then selects the earliest scheduled arrival among eligible services. It can start a simulated movement for a mapped lane.

**Live Operations** shows the wider simulated fleet. Surface uses truck icons, Air uses planes and Rail uses trains. Filters affect that fleet layer. The “Last planning result” is preserved separately and collapses while presenting live work.

**Network** is the single place for the three-file network upload and the separate synthetic schedule upload.

## The FedEx example

Use the exact station codes **UDRPU → DELGW**, dated **29 September 2026**:

- Ready **16:00 IST**: Air and Surface are eligible. Air **6E 6229** has a **16:30** cutoff, **20:00** departure and **21:20** arrival, so it arrives first.
- Ready **18:00 IST**: Air has missed cutoff. Surface **Bolero pickup** remains eligible: **21:30** cutoff, **22:00** departure, **12:00 the next day** arrival.
- Inject a **30-minute delay while in transit**: scheduled arrival remains **30 September 12:00 IST**; revised arrival becomes **12:30 IST**.

The disruption engine generates the warning and recommendation: notify the gateway, confirm onward handover readiness and continue monitoring. It does not automatically reroute when verified recovery capacity, transfer geometry or onward services are absent.

## Simulator, telemetry and revised ETA

The Python simulator advances a simulation clock through assignment, waiting, movement, delay and arrival. Pause, resume and speed controls change simulation time, not workbook timings. Server-sent events send updated state to the selected movement; the wider fleet uses periodic updates.

Telemetry means the movement’s position, status, progress and current ETA. **Today these positions are synthetic.** A revised ETA includes the deterministic disruption impact. The original scheduled ETA remains visible for comparison.

The workbook does not supply real GPS, authoritative road geometry or operating calendars. FedEx movement geometry is still approximate straight-line demo geometry; it must never be described as actual FedEx tracking. A mapped city coordinate is not a verified depot coordinate.

## Source data versus synthetic data

- **FEDEX_SOURCE**: service facts imported from the local workbook.
- **SYNTHETIC_NETWORK**: generated network assumptions used for planning.
- **SYNTHETIC_SCHEDULE**: generated service schedules.
- **DEMO_SIMULATION**: synthetic movement telemetry, including simulations based on FedEx service facts.

“FedEx source-derived simulation” means the timings came from the workbook; it does not mean FedEx supplied the vehicle’s location. Network batch simulations are hypothetical and do not reserve fleet capacity.

## When real GPS/API data becomes available

An authenticated adapter can feed real movement events into the operational layer while keeping the existing planning engine. That future work must define shipment identity, timestamp quality, source provenance, access controls and error handling. Real recovery decisions also require verified capacity and onward-service data.

The separation of planning, schedule rules and event state allows the architecture to grow. The present demo runtime is single-process and ephemeral; multi-worker deployment and durable event storage still require engineering. Do not describe the demo as production-scale tracking.

## What we changed from the old UniFleet

- Separate planning and schedule prototypes → one dashboard with clear workspace roles.
- Three network files alone → the same planning foundation plus a separate timed-service layer.
- Static plan visualization → plan visualization plus simulated live movements and disruptions.
- Entire telemetry collection in a shipment answer → owner-scoped selection by lane, shipment ID or selected movement.
- Missing live recommendation → the existing deterministic recommendation appears with the relevant shipment.
- UTC planner arrivals and long score dumps → IST arrivals and concise default summaries; details on request.
- Duplicate upload forms → one Network workspace.
- Old plan labeled “Current shipment” → preserved “Last planning result,” separate from live operations.
- Raw live timestamps and schedule-template marker clutter → readable IST timestamps and actual simulation markers only.

## A safe closing sentence

“Today we demonstrate deterministic planning and source-based schedule decisions using simulated telemetry. With verified GPS and operational APIs, the same separation lets us connect real events without asking an LLM to invent logistics facts.”
