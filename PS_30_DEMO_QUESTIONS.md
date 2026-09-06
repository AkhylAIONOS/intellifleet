# PS30 demo questions

Demo safety is conservative: a question is not client-approved solely because an HTTP request succeeded. Variations are candidate rehearsals; only observations in the validation report are evidence. Never invent a deadline, SKU, schedule or demand dataset.

## PS01 — Network planning

- Safest question: Plan 6000 kg from Mumbai to Bengaluru using Ground.
- Variation 1: Bengaluru to Chennai
- Variation 2: Ahmedabad to Surat
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS02 — Cost optimization

- Safest question: Find the cheapest feasible route for 6000 kg from Bengaluru to Chennai.
- Variation 1: Mumbai to Pune
- Variation 2: Ahmedabad to Mumbai
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS03 — Fastest planning

- Safest question: Find the fastest feasible route for 6000 kg from Delhi to Bengaluru.
- Variation 1: Delhi to Chennai
- Variation 2: Mumbai to Bengaluru
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS04 — Multi-objective

- Safest question: Plan 6000 kg from Ahmedabad to Surat balancing cost, time and risk.
- Variation 1: Mumbai to Pune
- Variation 2: Bengaluru to Hyderabad
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS05 — Ground / Express

- Safest question: Compare Ground and Express for 6000 kg from Kolkata to Guwahati.
- Variation 1: Mumbai to Bengaluru
- Variation 2: Delhi to Bengaluru
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS06 — Pricing / margin

- Safest question: Plan 6000 kg from Mumbai to Pune at a 20% margin.
- Variation 1: Bengaluru to Chennai
- Variation 2: Kolkata to Guwahati
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS07 — Route alternatives

- Safest question: Plan 6000 kg Delhi to Mumbai using Ground. Then say: The direct route is unavailable; replan this shipment.
- Variation 1: The selected direct leg is closed.
- Variation 2: Exclude the specified start/end leg and evaluate alternatives.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS08 — Route comparison

- Safest question: Compare the recommended and next-best routes for 6000 kg Mumbai to Bengaluru.
- Variation 1: Delhi to Bengaluru
- Variation 2: Kolkata to Guwahati
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS09 — Risk

- Safest question: Find the lowest-risk plan for 6000 kg Mumbai to Bengaluru and show risk components.
- Variation 1: Bengaluru to Chennai
- Variation 2: Ahmedabad to Surat
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS10 — Mitigation

- Safest question: Assume disruption risk increases by 0.2. Mitigate and replan 3000 kg Mumbai to Bengaluru with a baseline comparison.
- Variation 1: Delhi to Mumbai
- Variation 2: Kolkata to Guwahati
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS11 — Vehicle selection

- Safest question: Plan 18000 kg Mumbai to Pune using Ground; show exact vehicle loads.
- Variation 1: 6000 kg Mumbai to Bengaluru
- Variation 2: 10000 kg Delhi to Mumbai
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS12 — Road / air

- Safest question: Should I use road or air for 6000 kg Mumbai to Bengaluru?
- Variation 1: Kolkata to Guwahati
- Variation 2: Delhi to Bengaluru
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS13 — Breakdown recovery

- Safest question: Plan 6000 kg Mumbai to Bengaluru using Ground. Then: The assigned truck broke down at Mumbai; recover the remaining shipment.
- Variation 1: Use the current known recovery hub.
- Variation 2: Give a different explicitly named recovery location.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS14 — Alternative warehouse

- Safest question: Use alternative warehouses to fulfil 5 units totaling 500 kg to Mysuru using the cheapest allocation.
- Variation 1: Coimbatore
- Variation 2: Mumbai
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS15 — Multi-warehouse

- Safest question: Given structured SKU demand exceeding any single compatible warehouse inventory, find a multi-warehouse allocation to Mumbai.
- Variation 1: Use a valid SKU-specific fixture for Chennai.
- Variation 2: Use a valid fixture for Bengaluru with exact quantities.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS16 — Warehouse capacity

- Safest question: Show inventory, available storage and utilization for Bengaluru South Hub.
- Variation 1: Show capacity for Mumbai West Hub.
- Variation 2: Inspect available stock and storage at Kolkata East Hub.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Scoped capacity query validated through MCP and Azure; UI regression coverage available.

## PS17 — Consolidation

- Safest question: Consolidate shipment A of 1000 kg and shipment B of 1200 kg, both from Mumbai to Pune.
- Variation 1: Delhi to Mumbai
- Variation 2: Bengaluru to Chennai
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS18 — Multi-stop

- Safest question: Optimize a multi-stop 3000 kg shipment from Delhi to Mumbai stopping at Jaipur and Ahmedabad.
- Variation 1: Use a structured connected stop list for Mumbai/Pune/Bengaluru.
- Variation 2: Use a disconnected stop and expect infeasibility.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS19 — Utilization optimization

- Safest question: Optimize utilization for shipment A 1000 kg Mumbai to Pune and shipment B 1200 kg Mumbai to Pune.
- Variation 1: Can these compatible loads share a truck?
- Variation 2: Find capacity savings for the supplied shipment list.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS20 — What-if

- Safest question: Plan 6000 kg Mumbai to Bengaluru. Then: What happens if fuel cost increases by 20%? Keep it as a draft.
- Variation 1: Fuel rises by 10%.
- Variation 2: Demand weight increases to 10000 kg.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS21 — Baseline comparison

- Safest question: After creating a fuel draft: Compare it with my baseline.
- Variation 1: Show Before and After.
- Variation 2: Compare the current draft with its original plan.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS22 — Future cascade

- Safest question: After supplying a scheduled-shipment fixture: The assigned vehicle is delayed by 6 hours; replan affected future shipments.
- Variation 1: Use another exact vehicle label from the fixture.
- Variation 2: Use a fixture with no spare vehicle and expect rescheduling.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS23 — SLA

- Safest question: Plan 6000 kg Mumbai to Bengaluru with a delivery deadline of <future ISO timestamp with timezone>.
- Variation 1: Use an explicit +05:30 deadline.
- Variation 2: Use an impossible deadline and expect an SLA miss.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS24 — Expansion

- Safest question: Evaluate facility A at latitude 26.9 longitude 75.8 with capacity 5000 against demand 1000 at latitude 28.6 longitude 77.2. Do not assume construction costs.
- Variation 1: Supply a second hub and named demand points.
- Variation 2: Supply insufficient capacity and expect unserved demand.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS25 — Expansion cost

- Safest question: Estimate expansion cost for Jaipur at latitude 26.9 longitude 75.8, capacity 5000, facility cost 1000000, warehouse cost 200000, transport cost per km 10; demand 1000 at Delhi latitude 28.6 longitude 77.2.
- Variation 1: Omit property costs and expect unknown total.
- Variation 2: Provide all cost assumptions explicitly.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS26 — International

- Safest question: Plan 5000 kg Delhi to Frankfurt using the best feasible international option.
- Variation 1: Bengaluru to Dubai
- Variation 2: Chennai to Singapore
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS27 — Decision support

- Safest question: Plan 6000 kg Mumbai to Bengaluru and explain what I should do.
- Variation 1: Bengaluru to Chennai
- Variation 2: Ahmedabad to Surat
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS28 — Explainability

- Safest question: Explain the calculated cost, ETA and risk tradeoffs for 6000 kg Kolkata to Guwahati.
- Variation 1: Mumbai to Bengaluru
- Variation 2: Delhi to Bengaluru
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS29 — Lifecycle

- Safest question: After creating a fuel draft: Apply it. For a separate draft: Discard it.
- Variation 1: Keep this scenario as draft.
- Variation 2: Discard the scenario and retain the baseline.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

## PS30 — Unified context

- Safest question: Plan 6000 kg Mumbai to Bengaluru; compare Ground and Express; create a fuel +20% draft; compare baseline; discard it.
- Variation 1: Use Kolkata to Guwahati for the same shorter workflow.
- Variation 2: Use Delhi to Bengaluru with an explicit deadline.
- Expected result: A structured deterministic result or a specific infeasibility/missing-input explanation.
- Client demo: Rehearse first; not approved as complete PS coverage. See acceptance limitations.

