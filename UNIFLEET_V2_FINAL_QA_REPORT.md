# UniFleet V2 final deep QA — live record

Date: 2026-10-04 (IST). Status: IN PROGRESS; no release certification.

Starting HEAD: `dd4a3dfb58da43dd24c210e42d6ae413cc248ce1`.
Branch: `feature/fedex-control-tower-v2`.
Recovery branch and tag: `1586667ebf11cdb46f650fe9d3f40ac79d7b1a89`.
Tracked tree initially clean; pre-existing untracked user files preserved.
Read implementation, Session 2 and Session 3 records completely.

## Safety and evidence

Use native Computer Use on the existing Chrome UniFleet tab, screenshots and accessibility state for user workflows. Browser control verified by selecting the existing tab, clicking Source, typing Delhi and clearing it. No DOM/API substitution for visual tests. Supplemental unit/API checks run separately. No push/deploy, actual email, real ingestion, credential exposure or destructive changes authorized.

## Live execution

- PASS: existing dashboard loads at port 5178; Network Ready reports 30 warehouses, 97 vehicles, 72 routes.
- PASS: current browser can be seen, clicked, typed into and inspected.
- PASS: baseline backend suite and frontend suite; final frontend rerun after fixes also passes.
- INVESTIGATING: wide desktop planner Calculate Plan text clipped; screenshot captured in Computer Use conversation. Eight explicit grid columns are used for nine form children; inspect responsive/minimum sizing before fixing.

## Bug register

### FINAL-001

BUG ID: FINAL-001
AREA: Planner desktop layout
SEVERITY: P2
REPRODUCTION: Open dashboard on desktop with viewport wider than 1200px and a constrained planner workspace; observe Calculate Plan on second row.
EXPECTED: Full action label and usable Source/Destination widths.
ACTUAL: Button inherits narrow first grid track and clips its label (visible screenshot before change).
ROOT CAUSE: Eight explicit weighted tracks for nine children; sizing follows whole-window media query instead of available workspace.
FILES: PlanningPanel.css; tests/run-planner-layout-contract.mjs
FIX: Workspace-sized auto-fit tracks with 140px minimum; bounded mobile two-column form and full-row action.
REGRESSION TEST: CSS computed sizing contract passed; visible wide screen after HMR shows full label. Smaller viewport recheck pending.
STATUS: FIXED and committed as `6d9312d7`; verified at 1440×900 and wide native display. Planner controls regression and production build passed.

### FINAL-002

BUG ID: FINAL-002
AREA: Autocomplete/map stacking
SEVERITY: P2
REPRODUCTION: Empty Source, type D; dropdown extends over map.
EXPECTED: All suggestions display above map controls.
ACTUAL: Zoom controls obscure left portion of Chennai/Hyderabad suggestions.
ROOT CAUSE: Leaflet controls use z-index 800/1000 outside an isolated map stacking context; planner context is 700.
FILES: MapView.css
FIX: Local map stacking isolation contains Leaflet controls beneath form suggestions.
REGRESSION TEST: Computed stacking contract and existing network movements tests passed. Exact D reproduction at 1440×900 shows Chennai/Hyderabad fully above zoom control.
STATUS: FIXED and committed as `ed22bcd3`.

### FINAL-003

BUG ID: FINAL-003
AREA: Map resize repaint
SEVERITY: P2
REPRODUCTION: Resize desktop viewport, close recommended plan, expand/collapse scenario controls; observe newly exposed map area without zooming.
EXPECTED: Tiles fill the measured map container and manual camera remains unchanged.
ACTUAL: Lower map remained grey until another map interaction.
ROOT CAUSE: Leaflet did not observe container-only flex layout changes.
FILES: MapResizeController.tsx; MapView.tsx; tests/run-map-container-resize.mjs
FIX: Coalesced ResizeObserver invalidation on measured size change, window resize fallback, cleanup and hidden-container guard.
REGRESSION TEST: Real Leaflet container resize/hide/show, camera retention, coalescing, fallback and cleanup; full frontend suite passes. Exact visible close/collapse and viewport resize retest passed at 1280×800 and 1024×768 without zoom.
STATUS: FIXED and committed as `4824a8bd`.

## Latest validation

- PASS: all 29 top-level frontend scripts ran to exit 0 after three new regression scripts. There are 26 explicit PASS lines; script count is 29, not the line count.
- PASS: final production build, 278 modules; largest JS chunk 467.19 kB, no circular chunk/size/TypeScript warning.
- Scenario Apply passed: ₹324917.44 snapshot, one truck; applied card collapses and exposes baseline comparison.
- Desktop planner sizing checked at 1440×900, 1280×800 and 1024×768; narrower and other workspace checks remain pending.
- Control Tower local checker attempted. Sandbox network denial was retried with approval. Actual server then returned 422 for the fixed `local-smoke-departure` event ID on an already populated run. This is not recorded as a passing integration check. Investigate repeatability without resetting active data; Session 2/3 scripts remain pending.

## Verified results so far

- Backend full baseline: 435 passed, 1 warning, 37.53s.
- Frontend approved baseline: all 26 existing scripts completed (socket-restricted first attempt is excluded).
- Browser Ground: Ahmedabad → Surat → Mumbai → Bengaluru, 6000kg, strict Ground/Balanced, TRK-038, capacity 7000kg, 85.71% load, ₹309112, 35.67h, 14.40% risk, 95% reliability, one assigned vehicle and truck/map linkage. No deadline supplied.
- Browser autocomplete: D list capped at eight, Del → Delhi with Down/Enter, Ban → Bengaluru with Down/Enter; no API typing substitution.
- Browser scenario draft +20% fuel: baseline ₹309112 → ₹324917.44, +₹15805.44; route/ETA/risk unchanged. Apply/discard/responsive verification continuing.
- Browser DevTools console currently shows React development-tools informational message, no visible application exception. Issues count 15 requires inspection.
- FIXED: map container resize repaint; visible close/collapse and 1280×800 → 1024×768 repaint without zoom.

## Matrix status

All 60 requested sections remain pending except the initial network/browser observations above. PASS will distinguish browser evidence from supplemental automated evidence. External model/provider/SMTP acceptance will remain explicitly blocked if unavailable; no silent certification.

# Resumed final QA — 2026-10-04 IST

This section supersedes the earlier live matrix/status. The earlier entries above are retained as historical evidence, not a claim that all checks were completed.

## Recovery and commits

- Recovered starting HEAD: `3fa5e79d` (known pre-QA HEAD was `dd4a3dfb`).
- Interrupted backend run **finished**: 435 passed, 1 warning, 36.63s in `/private/tmp/unifleet-final-backend.log`.
- All four interrupted-session production fixes were already committed: `6d9312d7` planner sizing; `ed22bcd3` autocomplete stacking; `4824a8bd` map repaint; `3fa5e79d` stale shipment scenario isolation.
- No uncommitted tracked production changes at recovery. Existing untracked backup, docs, QA and user files preserved.
- New feature commit: `a057fd89` — Add session-scoped personal alert email.
- Ending production HEAD: `a057fd89709151280449eae9f1fe8ee82fea98c8`. The subsequent report-only commit is the ending branch HEAD; identify it with `git log -1 --oneline` (a commit cannot embed its own hash).
- Recovery branch and tag both remain `1586667ebf11cdb46f650fe9d3f40ac79d7b1a89`.
- Final tracked production tree clean. Only this report was staged for the report commit; pre-existing untracked files remain. No deploy, push, source deletion, stash, reset, real ingestion or external email.

## Personal Alert Email

PASS — browser identity generated once using `crypto.randomUUID()` and stored under `unifleet_demo_session_id`. Normal email/preferences/history endpoints require authenticated account ownership plus the browser UUID header. Settings use a separate identity dependency so future authenticated-user identity can replace browser identity.

PASS — additive SQLite tables enforce one email per `(account owner, browser identity)`. Save replaces the previous email; disable deletes that session's setting. API validates email and rejects multiple emails. Missing/malformed/non-v4 session identity rejected. Account authentication remains required.

PASS — status transitions snapshot each configured session into a separate outbox record with exactly that email. Session-specific transition keys preserve polling dedupe and independent retries. Legacy global settings are retained as archived data, excluded from new targeting; archived legacy outbox records are excluded from delivery. No-recipient transitions retain an operational audit record.

PASS — public alert history contains only that session's delivery status/attempt metadata, excluding email snapshots and operational payloads. Other sessions' settings/history are not disclosed. Anonymous UUIDs are bearer capabilities, not a substitute for personal login; tabs in the same browser profile intentionally share localStorage identity.

PASS — automated save/reload/replace/disable/invalid/multiple recipient/isolation/snapshot/poll dedupe/mock retry coverage; updated frontend test verifies identity reuse, fresh identity after storage removal, save/change/component reload/disable. Automated A/B isolation is used instead of extra Chrome profiles.

PASS — visible Chrome saved `qa-session@example.com`, refreshed dashboard, reopened Live Operations → Network Overview, and showed the same email. Change replaced it with `qa-replaced@example.com`; Disable showed disabled state and empty email field. Both addresses are dummy examples. No mail was sent.

## Final regression and evidence

- Backend full final suite: **437 passed**, 1 warning, 36.31s. Log `/private/tmp/unifleet-resumed-backend.log`.
- Frontend: **30 current top-level scripts**, exit 0. Count is `tests/*.mjs`, not nested scripts or PASS lines. Approved clean log `/private/tmp/unifleet-resumed-frontend-approved.log`. Initial sandbox run also exited 0 but reported Vite socket-denial errors; it is excluded from the clean certification. Approved rerun has no EPERM/FAIL errors. Existing test-only unavailable-storage messages remain non-blocking.
- Production build: PASS; 278 modules, largest vendor JS 467.19 kB; log `/private/tmp/unifleet-resumed-build.log`.
- Targeted backend feature/Control Tower/Session 2 checks: 26 passed before the full final suite.
- Isolated local Control Tower checker: PASS against fresh temporary data, 38 runs (10 Air/28 Surface), labelled synthetic CON, delivery false. This avoids the previous populated-run event-ID collision; repeatability on an already-populated run is still a checker limitation.
- Local Session 2 integration checker: PASS; network upload 30 warehouses/97 vehicles/72 routes, planner modes, source cells retained, CON and critical-lane deterministic tools.
- App left available at `http://127.0.0.1:5178/dashboard`; API loopback `4208`. Temporary launcher explicitly disables delivery/real ingestion and uses no production SMTP configuration. Browser devtools emulation may need closing before acceptance.

## Workflow matrix

| Area | Evidence / result |
| --- | --- |
| Previous Ground | Retained prior visible PASS: Ahmedabad → Surat → Mumbai → Bengaluru, 6000kg, TRK-038, ₹309112, 35.67h, 14.40% risk, 95% reliability. Not repeated. |
| Previous Air | Retained prior visible PASS: Delhi → Mumbai, 6000kg, AIR-001, 50% load, ₹578060, 5.52h, 11.97% risk, 95% reliability. Not repeated. |
| Previous What-if | Retained prior PASS: fuel +20%, ₹309112 → ₹324917.44, +₹15805.44. |
| Autocomplete edges | Visible PASS: Bombay→Mumbai, Bangalore→Bengaluru; Mumbay→Mumbai, Dheli→Delhi, Chenai→Chennai, Kolkatta→Kolkata suggestions. Canonical selection and arbitrary nonsense behavior covered by existing full frontend test; visible nonsense had no suggestion. |
| Multimodal | Visible PASS: Mumbai→Chennai, 6000kg, Best Available; B multimodal AIR-002 + TRK-033, ₹499012, 15.35h, 10.65% risk, 90.25% reliability. Air load 6000/12000kg, Ground load 6000/7000kg. |
| Candidate switching | Visible A→B→C→B→A updates; A road ₹272902.50/31.35h; C road via Pune/Hyderabad ₹340990.40/41.07h. Immediate geometry, one carrier and late-response isolation additionally covered by final frontend test. No console application exception. |
| Disruption / recovery | Visible PASS: zero fuel uplift and blocked Mumbai→Bengaluru; alternate Mumbai→Pune→Hyderabad→Bengaluru→Chennai, ₹340990.40, 41.07h, 14.40% risk, delta ₹68087.90/+9.72h. Apply updated current plan. Early native typing entered an incorrect arrow/fuel value; corrected native input before accepted result, not a product defect. |
| Strict Air | Automated PASS in final recovery/rerouting tests: Air remains strict and returns infeasible when no compatible alternative exists; no silent Ground fallback. Not separately replayed in visible browser. |
| SLA | Automated PASS: baseline MET remains historical while delayed current/projected SLA becomes MISSED. Requested clear visible deadline MET/MISSED flow **not completed**. |
| Schedules | Surface representative source rows visibly retain lane/run/mode/operator/handover/ETD/ETA/TT and FEDEX_SOURCE; no operator-facing UNSUPPORTED_FORMULA. Air evidence retained from previous session; source/provenance/formula regressions pass. |
| Control Tower negatives | Visible Air→Surface, no-result search then clear, run close/reopen. Status filter and selection drift/empty/stale response behavior PASS in automated frontend checks; dedicated visible status-filter check remains pending. |
| Surface playback | Visible PASS: mapped UDRPU→DELGW, SURFACE, one truck on road geometry, ON TIME, SYNTHETIC_TELEMETRY execution/location, changing approximate coordinates, planned ETA retained (05 Oct 12:00 IST). CJBMB→BLRGW has no demo mapping and correctly rejects playback; not claimed supported. |
| Previous Air playback | Prior visible PASS retained: CJB-BLR, 6E 5355, ON TIME, synthetic provenance, aircraft, scheduled ETA retained. |
| CON | Prior visible lookup PASS retained; fresh integration lookup `CT-LOCAL-SYNTHETIC` PASS. Labelled synthetic scan linkage, not real GPS. |
| Critical lanes | Prior visible mark/unmark PASS retained; fresh API/automated summary/owner isolation and deterministic critical-risk tool PASS. |
| AI | **BLOCKED EXTERNAL SERVICE**: safe launcher explicitly uses `local-demo-no-llm`, reports AI_PROVIDER_UNSUPPORTED. Full 9-question live-model conversation not performed. Deterministic operational tool checks pass; they do not certify a live LLM. Isolated Redis endpoint also has no running service. No credential debugging attempted. |
| Responsive | Control Tower/map inspected at 1440×900, 1024×768 and 768×768, no observed overlap; tablet tabs wrap. Full expanded Alert Email/form/scenario/autocomplete checks at every size **not completed**. Previous desktop planner/resize checks retained, responsive layout tests pass. |
| DevTools | No visible application exception or breaking-change indication. Three HTTP 422 console resource errors from repeated unmapped CJBMB playback attempts; do not describe this as zero console errors. Current Issues reports 20 possible improvements. Prior session had 29 form notices; no blanket claim that current issue details were all re-inspected. |

## Bugs and limits

All four earlier genuine P2 bugs remain fixed and committed. No new production bug was confirmed during resumed checks. Browser automation was repeatedly interrupted by foreground tab switching; an asynchronous request to keep UniFleet selected was issued. Browser evidence above records only observations actually completed; automated evidence is explicitly separate.

Important delivery semantics: an outbox email is an immutable snapshot of the setting at transition time. Replacement/disable affects future transitions. Previously queued snapshots are not rewritten. Delivery stays disabled throughout this task; all retry sends in tests used mocks.

No assertion of real live FedEx GPS, scans, production SMTP transport or live model-provider acceptance is made.

## Data provenance

- **REAL / SOURCE DATA:** provided FedEx workbook schedule/operator/source cells and provenance. Schedule data does not establish real execution/GPS.
- **SYNTHETIC TELEMETRY:** demo departures, CON association, road/air vehicle progress and approximate city-centre locations. Simulation timestamps can advance into the following day; they are not wall-clock FedEx observations.
- **CALCULATED PLANNER DATA:** routes, candidate costs, ETA durations, risk, reliability, load, scenario deltas and recovery against the loaded demo network. Not carrier invoices, verified dispatch commitments or reserved fleet.

## Remaining acceptance checks and external integrations

Remaining requested visible checks: one deadline baseline/current MET→MISSED flow; one operational status filter; complete expanded tablet planner/scenario/autocomplete/Alert Email inspection. Live AI requires a working configured provider and isolated Redis before the requested 9-turn conversation can be evaluated. Real FedEx telemetry/scans and backend-only SMTP transport require separate explicit integration/enablement; neither was enabled here.

FINAL RELEASE ASSESSMENT:
NOT READY FOR CLIENT ACCEPTANCE TEST

Reason: the feature and regressions pass, but the requested visible SLA/responsive/status checks and live-model acceptance evidence are incomplete. This is a QA completeness assessment, not a claim of a newly discovered production regression. No deployment performed.
