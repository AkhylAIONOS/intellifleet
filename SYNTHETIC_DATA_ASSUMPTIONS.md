# UniFleet synthetic V2 assumptions

All values below are demonstration modelling assumptions, not FedEx operating rules or manufacturer specifications. Generate the public CSVs with `python3 intellifleet-server-backendmcp/scripts/generate_synthetic_v2.py`. The generator never reads the FedEx workbook.

## Sources and import

`intellifleet-web-main/frontendmain/public/synthetic_v2/` contains 30 warehouse locations, 97 fleet allocations (91 road vehicles and six illustrative cargo aircraft allocations), 72 directed routes (66 road, six air), and 36 schedules (12 each Air/Surface/Rail).

Every CSV row has `data_source=SYNTHETIC`. The network importer retains `SYNTHETIC_NETWORK`; schedule objects retain `SYNTHETIC_SCHEDULE`. The supplied, locally configured workbook remains `FEDEX_SOURCE`; it is neither copied nor committed. All simulated positions retain `location_source=DEMO_SIMULATION` independently of their source schedule/network. Legacy uploads with unspecified provenance remain `USER_NETWORK`: we do not infer that they are synthetic or FedEx data.

The Network workspace offers downloads and the existing atomic three-file import. Schedules are imported separately in the same workspace. Cross-file references and numeric checks run before the network transaction. Existing user data is not automatically replaced. The old small sample CSVs remain available for compatibility.

## Facilities

Coordinates are approximate city centres, not warehouse entrances, airports, or actual FedEx facilities. Names and addresses explicitly describe synthetic nodes. Thirty Indian cities include Delhi, Mumbai, Bengaluru, Chennai, Kolkata, Hyderabad, Udaipur, Ludhiana, Mohali, and southern and northeastern nodes. Storage and inventory are generic units, not kg; shipment capacity is kg. Inventory, reserved stock, and capacity are ordered consistently. Handling is INR/unit, fixed operating cost INR/day. Reliability/risk are illustrative scores in [0,1]. Airport identifiers describe nearby city airports; 30 km access distances are a demo assumption, not measured routes.

## Vehicles and costs

Conservative payload classes: Tata Ace 750 kg, Tata 407 2,000 kg, Ashok Leyland Partner 3,500 kg, Eicher Pro 5,000 kg, Tata Ultra 7,000 kg, BharatBenz linehaul 16,000 kg. These are class-level assumptions, not certified limits for a specific variant. Road costs range from INR 10–34/km; loading and unloading each 20–90 minutes. Road speed assumptions are 35–55 km/h; route and fleet speeds both constrain the original planner. Maximum range 250–3,000 km is a demo dispatch range including planned refuelling, not a single fuel-tank range. Regional cargo allocation assumes 12,000 kg, 650 km/h cruise and additional ground handling.

Route base cost is INR 28/km for road and INR 70/km for air; road toll is INR 2/km. The original planner combines base transport, fleet distance/time/dispatch, handling and toll components. These are distinct illustrative accounting components, not carrier quotes. Vehicle availability is hypothetical and simulation does not reserve stock or fleet.

## Route timing and connectivity

Road distance is city-to-city great-circle distance ×1.22, rounded to km. It is a rough network modelling estimate, not surveyed road distance. Timings use distance/speed plus a buffer:

| Class | Speed before buffer | Buffer |
|---|---:|---:|
| Regional, below 250 km | 40 km/h | 30 min |
| Intercity, below 800 km | 52 km/h | 60 min |
| Long haul | 58 km/h | 120 min |
| Dehradun/Guwahati access | 32 km/h | distance-based buffer above |

Effective speed is calculated again as distance / total transit hours. The strict V2 validator rejects road averages outside 10–65 km/h, non-finite/negative values, invalid coordinates, duplicate identifiers, orphan references, SLA shorter than transit, and distances shorter than geodesic distance (with rounding tolerance). Tests check the generated effective speeds directly. Legacy unlabelled imports retain a wider compatibility ceiling (90 km/h) and receive a modelling-review warning; that is not an endorsement of those assumptions.

Direct active edges are preferred for live route selection. Otherwise the existing planner's directed graph traversal supplies a connected sequence. Missing connections return `NO CONNECTED ROUTE`; reverse edges and arbitrary logistics links are never invented. The existing capacity/range planner must approve a route simulation. Network map lines connect loaded node coordinates; they are not turn-by-turn road geometry.

## Schedules

Synthetic station/gateway codes have a `SYN-` prefix. Six lanes have two runs per mode, with 20:00/23:00 ETDs and cutoffs two hours earlier. Air time uses geodesic distance/650 +1 hour; Surface uses estimated road distance/52 +2 hours; Rail uses estimated distance/48 +2 hours. This illustrates a schedule structure, not actual railway or airline services. Schedule transit is separate from network vehicle selection.

All times use IST. `eta_day_offset` preserves overnight and multi-day journeys; `retrieval_or_tt` is explicitly transit minutes in this synthetic CSV. The synthetic operating template is daily demo. The real workbook retains its original interpretation, including unknown operating days and separate retrieval milestones. Source selection never silently combines eligibility candidates across FedEx and synthetic schedules.

## Runtime, recovery and limitations

One Python runtime advances all movements; browser polling retrieves a batch every second. Demo seed 42 makes lane choices and initial progress reproducible for the same loaded network/date. Simulation IDs remain unique. Batches replace only the current user's prior network-demo batch; independent user runs remain. Each service appears once per batch and schedule templates are suppressed when represented by a run. Only mapped templates receive stationary icons; unmapped templates remain in the list.

10/50/100 demo batches require enough distinct feasible services; the V2 dataset supplies them. Demo clocks deliberately start from template midnight and stagger progress; timestamps are simulated time. Telemetry is not actual GPS. Single-process memory, 500-run global cap, six-hour retention, and restart loss apply. Schedule CSV uploads are also ephemeral and user-scoped.

Delay injection shifts ETA through the shared disruption engine. FedEx schedule-only recovery cannot assert compatible network fleet availability. Explicit network route simulations can calculate hypothetical origin recovery using the original planner, with return/transfer feasibility still unverified. No automatic reassignment occurs. Without a shipment deadline/onward calendar the system labels SLA feasibility unverified.

Map updates do not continuously fit bounds. Initial show-all, explicit fit, and selected route changes may fit; users can then pan/zoom normally. Road, air and rail markers use lightweight SVG icons and compact hover data. The 100-marker DOM test checks filters, geometry, deduplication and preserved map position; it is not a frame-rate benchmark on physical hardware.
