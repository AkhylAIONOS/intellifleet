# UniFleet V2 implementation record

## Recovery and baseline

- Original branch: feature/fedex-simulation
- Original commit: 1586667ebf11cdb46f650fe9d3f40ac79d7b1a89
- Recovery branch: backup/pre-fedex-control-tower-v2
- Recovery tag: pre-fedex-control-tower-v2
- Development branch: feature/fedex-control-tower-v2
- Existing untracked backups, documentation and QA artifacts are user-owned and remain untouched. The recovery refs capture tracked code, not ignored databases or untracked files.
- Baseline backend: 400 passed, 1 warning (56.29 seconds).
- Baseline frontend: failed run-dashboard-journey-crash.mjs:64: pending refresh frame count 1, expected 0.
- Baseline build: passed; 658.25 kB main JavaScript bundle, chunk-size warning.

## Safety policy

No existing source file, function, component, route, endpoint, test or database field will be deleted. Changes are additive or reversible. No production push/deploy or unsolicited email delivery.

## Candidates for later cleanup (preserved)

- backend/main.py is an older alternate entry point; root main.py remains active.
- Legacy selected-journey/vehicle/plane animation remains available for older workflows.
- Existing .backup/.before_* files, .manual_backups, backend package-lock.json and QA artifacts.
- Legacy unverified LLM summary paths require a separately reviewed replacement.

## Control Tower boundaries

Only FEDEX_SOURCE workbook records can create operational runs. Planning alternatives never populate the operational network. Schedule source cells remain unchanged. Actual scans and synthetic events carry distinct provenance. Real FedEx feed credentials and schema must be integrated before production tracking can be claimed.

## Final implementation report — first additive pass

### 1. Development branch

`feature/fedex-control-tower-v2`. No push or deployment performed.

### 2. Recovery refs

`backup/pre-fedex-control-tower-v2` and `pre-fedex-control-tower-v2` point to the original tracked version. Existing ignored databases and untracked assets require their own backups. No pre-existing source files, functions, components, endpoints, tests, or database fields were deleted. Git reports no deleted files relative to the recovery tag. The original risk implementation remains as `legacy_risk_breakdown`; the active entry point delegates to the corrected deterministic calculation.

### 3. Implementation commits

| Commit | Change |
| --- | --- |
| d72ce24a | Recovery and baseline record |
| 9720a94a | Deterministic cost, risk and multimodal metrics |
| 3c54b6c9 | Map repaint, camera preservation and legacy movement bindings |
| 6f79b9aa | Owner-scoped operational runs, scans, alerts and CON APIs |
| 5c370f8a | Operational SLA and canonical scenario revisions |
| 6ee94c28 | Trusted scan ingestion and isolated live HTTP check |
| 69fa9303 | Grounded concise planning composer and operational chat queries |
| 3102ff81 | Air/Surface Control Tower, lane drill-down and CON map focus |
| 0e385071 | Upload progress and offline profiling script |

The final documentation commit can be found with `git log -1 --oneline` after this report is committed.

### 4. Files changed

All paths below are relative to the repository. Exact inventory: `git diff --name-only pre-fedex-control-tower-v2 HEAD`.

- Backend: root `main.py`, `.env.example`, `backend/config/config.py`, `backend/routes/upload/network_upload.py`, `backend/planning/{service.py,metrics_v2.py}`, `backend/fedex/simulator.py`, `backend/operations/{plan_journeys.py,routes.py}`, `backend/agents/{supervisor.py,grounded_composer.py}`, `backend/api/chat_api.py`, and the new `backend/control_tower/{__init__.py,database.py,status.py,service.py,routes.py,chat.py}`.
- Backend scripts: `scripts/{run_fedex_local.py,check_control_tower_local.py,profile_v2.py}`. Tests: `tests/{test_metrics_v2.py,test_control_tower.py,test_grounded_composer.py,test_plan_journeys.py}`.
- Frontend under `intellifleet-web-main/frontendmain`: `src/api/controlTower.ts`, `src/components/{ControlTower.tsx,ControlTower.css,FedExPanel.tsx,LiveOperations.tsx,MapView.tsx,NetworkUpload.tsx,PlanningPanel.tsx}`, `src/components/MapLayers/{NetworkMovementsLayer.tsx,ControlTowerLayer.tsx}`, `src/hooks/useRouteAgent.ts`, `src/pages/DashboardPage.tsx`, `src/store/{authStore.ts,controlTowerStore.ts,operationsStore.ts}`, `src/types/api.ts`, `src/utils/planMovement.ts`, and `tests/run-control-tower-v2.mjs`.
- This report.

### 5. Additive database migration

New SQLite tables: `ct_runs`, `ct_network_imports`, `ct_critical_lanes`, `ct_events`, `ct_recipients`, `ct_outbox`, `ct_cons`, `ct_con_events`. Owner-scoped keys and date/run/outbox indexes are included. `CREATE TABLE/INDEX IF NOT EXISTS` runs when the Control Tower database connection opens. Existing tables and fields remain intact. Import revisions keep old run snapshots and update an active version pointer per owner/service date.

### 6. New APIs

All require user authentication. Paths are relative to the API origin.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | /operations/control-tower/import | Import provided workbook for a service date |
| GET | /operations/control-tower/runs | Date/mode/status/critical/search/sort/pagination |
| GET | /operations/control-tower/summary | Actual imported-run KPIs |
| GET | /operations/control-tower/runs/{run_id} | Run, source cells, events and CONs |
| PUT | /operations/critical-lanes/{run_id} | Mark/unmark business lane |
| POST | /operations/control-tower/runs/{run_id}/events | Departure/arrival/ETA/location event |
| POST | /operations/control-tower/runs/{run_id}/simulation | Explicit labelled synthetic playback |
| GET/PUT | /operations/alerts/recipients | Owner recipient configuration |
| GET | /operations/alerts | Latest 100 delivery records and enablement |
| POST | /operations/cons/events | Provenance-matched departure association |
| GET | /operations/cons/{number} | Package association and operational run |
| POST | /operations/plan-journeys/{plan_id}/revise | Apply scenario to exact prior plan movement |

`FEDEX_SCAN` event and CON writes additionally require `X-FedEx-Ingest-Token`, matched against `FEDEX_SCAN_INGEST_TOKEN`. Unconfigured real ingestion returns 503; missing/incorrect ingestion credential returns 403. Keep this server-to-server credential outside the frontend.

### 7. Algorithm corrections

- Imported Air base cost is counted once. Known legacy equal base/air duplicates are normalized; distinct additional charges remain. Scenario cost multipliers normalize legacy duplicates before modifying the base.
- Risk components and aggregate are bounded to [0,1]. Explicit zero reliability is preserved. Existing weights remain 35% route, 25% vehicle, 15% weather, 10% warehouse, 15% mode.
- Multimodal availability evaluates each leg at its projected start, including prior duration and transfer overhead. Segment utilization and waits are returned; overall utilization is explicitly the arithmetic mean of segment utilization.
- Operational elapsed/remaining/actual transit calculations use timezone-aware timestamps. Remaining time is ETA minus the operational clock, never a progress percentage.
- Baseline SLA stays historical; current projected/actual SLA reflects revised ETA/arrival. Infeasibility, strict mode constraints and resource allocation retain existing pathways.

### 8. Performance changes and measurements

Control Tower loads in a separate 12.18 kB JavaScript chunk, renders 25 rows per page, debounces search by 250 ms, memoizes displayed sorting, and polls every 10 seconds only while visible. Stale refresh responses are discarded after filter changes/unmount. Workbook source parsing retains the existing cached importer; there is no automatic workbook re-import loop.

Movement polling uses 5 seconds in Network Overview, 1 second for active movement playback, and 10 seconds for a hidden document. Inactive Live Operations stops its movement polling unless AI playback remains active. Business alert observation runs separately every 10 seconds, never per telemetry tick. Existing shared animation ownership remains intact.

Map refresh invalidates size only when the container size changes; otherwise it redraws vector layers while retaining the camera. The original immediate/75 ms/250 ms refresh paths remain. The frame fallback is limited to a zero-width container.

Offline `scripts/profile_v2.py`, 100 ticks of synthetic Air snapshots: 10 movements 0.107 ms/tick; 100 movements 0.962 ms/tick; 500 movements 4.719 ms/tick. This excludes HTTP, database, road routing and browser rendering. No measured end-to-end speedup is claimed. Main bundle remains larger than the baseline.

### 9. FedEx Control Tower

Live Operations now offers Network Overview and Movement Map. Air and Surface tabs expose the requested 19 source/operational columns, search/filter/sort/pagination, KPIs and drill-down. Rail records from the supplied Surface sheet remain in Surface coverage. Static source cells are preserved alongside normalized IST clock values. Load is explicit and date-specific; planner candidates cannot populate operational runs.

Statuses: SCHEDULED before recorded departure, ARRIVED after recorded arrival, DELAYED once planned arrival plus a five-minute tolerance is exceeded, EXPECTED DELAY for projected late arrival, otherwise ON TIME. Missing facts remain missing. Latest real scan coordinates can focus the map without inventing a route. Synthetic movement links carry explicit provenance and notices.

### 10. Critical lanes

Persistence is owner/business-lane scoped across run modes and service dates. Mark/unmark, critical-only filter, count, critical-at-risk KPI, run detail and selected movement route emphasis are included. Critical flag is included in alert payloads and CON results.

### 11. Email alerts

Persistent outbox records meaningful transitions into EXPECTED DELAY/DELAYED, with recipient snapshots, previous/current status, planned/current ETA, reason, provenance, critical flag and timestamp. Independent recipient records prevent re-sending successful recipients when another fails. A lease and up to five attempts with retry backoff handle failure/restart. Disabled/unconfigured/no-recipient states are visible. Delivery requires SMTP configuration plus `FEDEX_ALERT_DELIVERY_ENABLED=true`. No email was sent during implementation.

SMTP remains at-least-once: a crash after delivery and before recording success can duplicate a message. A production provider idempotency key would improve this. A short shared ingestion token is insufficient; provision a strong secret and rotate it through the deployment secret manager.

### 12. CON architecture

CON numbers are distinct from generated shipment IDs. A recorded departure and matching provenance are required before association. Latest association and event history persist with owner scope, idempotent event IDs and stale-event rejection. Search returns carrier/run, status, ETA, available coordinates, provenance and last update, then selects its associated movement/map location. Synthetic example CONs are explicitly labelled; no real CON feed is fabricated.

### 13. AI changes

Concise/brief planning requests use an approved deterministic fact dictionary for recommendation, route IDs, assigned vehicles, cost/ETA, risk/reliability, SLA and reason. GPT may return only a permutation of known fact keys; generated prose and invented values are ignored. Invalid/unavailable model results fall back to the exact deterministic facts. Full legacy planning formatting is retained. Read-only Control Tower status/critical queries and CON lookup are owner scoped and require no LLM to calculate operational facts.

This is a constrained composer, not a complete rewrite of all legacy AI output. Other legacy general tool summaries still use their existing model pathway and are listed for a later audited replacement.

### 14. UI and map changes

Selected operational runs have separate state from planning candidates; logout clears selection. Source drill-down exposes original cells and warnings. Selection emphasizes only the linked operational movement or real location marker. Map repaint no longer resets manual camera precision for unchanged dimensions. Legacy omitted plan IDs retain exact known movement/revision bindings. Applying a scenario updates the plan card and canonical journey; stale/completed baselines are rejected, and failed playback retains the baseline with an explicit message. Three-file uploads show upload progress and returned counts/processing duration.

### 15. Test results

- Baseline: backend 400 passed, one warning; frontend initially failed the dashboard refresh-frame regression.
- Final complete backend suite: **422 passed**, one existing aioredis/distutils warning, 33.39 seconds.
- Final frontend `npm test`: **all 22 scripts passed**, including original regression coverage and new Control Tower DOM workflow. Sandboxed execution emitted Vite socket permission errors; rerun outside the sandbox passed. Existing jsdom storage warnings remain.
- Targeted operational authorization tests include absent JWT, owner separation, timestamp/email validation and additional scan ingestion credential.
- Live isolated HTTP check passed: original workbook imported **38 runs (10 Air, 28 Surface)**; critical marking, labelled synthetic departure/CON lookup, scan rejection and disabled delivery verified.
- Existing tests cover Ground/Air/multimodal, Ground → Air → Ground animation, recovery/strict modes, batch, candidate replacement, 3 → 1 → 3, camera behavior, atomic three-file uploads and workbook reading.
- No in-app browser connection was available. No visual browser, responsive screenshot or deployed environment validation is claimed.

### 16. Build

`npm run build` passed. 273 modules; main JavaScript 663.56 kB (204.69 kB gzip); Control Tower JavaScript 12.18 kB (4.24 kB gzip), CSS 2.41 kB. Existing >500 kB main-chunk warning remains. `git diff --check` passed.

### 17. Remaining limitations

- Synthetic movement runtime and remembered plans remain process-local; restart expires playback links. Persistent operational source/event/CON/outbox records survive.
- SQLite queries decorate matching runs before API pagination. Very large network histories need SQL pagination/filtering and measured database tuning.
- Five-minute delay tolerance is presently fixed. Scheduled runs without departure remain SCHEDULED, even after planned departure; a missed-departure business rule requires confirmation.
- Status/CON chat uses today's IST date and a narrow set of query patterns; the UI supports explicit dates. General conversational/date-aware operational routing remains future work.
- Scenario resource approval and movement revision are separate operations. If playback fails after approval, an explicit warning retains the baseline movement; there is no cross-store transaction.
- Legacy equal base/Air-cost deduplication is heuristic. The helper accepts `air_cost_is_additional` for an equal legitimate surcharge, but current persisted legacy route APIs do not expose that marker. Normalize such source records explicitly before production use.
- Real scan ingestion has authentication/provenance boundaries but no provider adapter, signature validation, reconciliation or feed outage monitor yet.
- No browser visual QA, production load test, live Azure composer test or live SMTP test was performed.
- UI is a first pass. Full application-wide design overhaul, broad response-composer migration and large-scale performance tuning remain outside the verified result.

### 18. Real data/integration required

Provide the licensed authoritative workbook path/version policy, authenticated scan/GPS feed schema, stable run/carrier identity, source event times and CON-to-run association events. Map coordinates must come from real feed events to claim live tracking. Provision dedicated ingestion secrets, agreed delay/missed-departure policy, SMTP credentials/approved recipients, and provider idempotency. Real road geometry for synthetic playback remains dependent on the existing routing provider. Never infer FedEx execution from a planner alternative or source timetable.

### 19. Exact local commands

Existing virtualenv and npm dependencies are used. Run in separate terminals:

```sh
cd /Users/akhilbabbar/Downloads/IntelliFleet/intellifleet-server-backendmcp
.venv/bin/python scripts/run_fedex_local.py
```

```sh
cd /Users/akhilbabbar/Downloads/IntelliFleet/intellifleet-web-main/frontendmain
VITE_API_BASE_URL=http://127.0.0.1:4208 npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

Open `http://127.0.0.1:5178`, enter demo, then Live Operations → Network Overview → Load FedEx Network Plan. The launcher uses a new temporary database, loopback only, no repository .env, no LLM, disabled alert delivery and disabled real scan ingestion. Workbook default: `~/Downloads/Sample Network plan - Air & Surface.xlsx`; set `FEDEX_WORKBOOK_PATH` in the shell for a different real path.

```sh
cd /Users/akhilbabbar/Downloads/IntelliFleet/intellifleet-server-backendmcp
.venv/bin/python scripts/check_control_tower_local.py
PYTHONPATH=. .venv/bin/python -m pytest tests -q --disable-warnings
PYTHONPATH=. .venv/bin/python scripts/profile_v2.py
```

```sh
cd /Users/akhilbabbar/Downloads/IntelliFleet/intellifleet-web-main/frontendmain
npm test
npm run build
```

The HTTP check writes only labelled synthetic events to the isolated launcher database. Restart that launcher before repeating its fixed event IDs. AI-enabled testing requires a separately configured Redis/Azure environment; this launcher intentionally does not provide it.

### 20. Safe deployment procedure

No deployment was performed. The hosting provider/process manager is not specified, so provider-specific publish/restart commands cannot be established. Use a separate release directory and staging environment; do not overwrite the running checkout.

1. Record the release with `git rev-parse feature/fedex-control-tower-v2`. Export only committed source with `git archive feature/fedex-control-tower-v2`; retain recovery refs and existing untracked assets.
2. Before opening the production database with new code, take a consistent SQLite backup: `sqlite3 /absolute/path/to/current/users.db ".backup '/absolute/path/to/backups/users-pre-v2.db'"`. Back up workbook, environment/secret configuration and uploads separately with the existing secure backup system. Do not store secrets in Git.
3. In the new backend release directory, provision the project's supported Python environment and existing requirements: `python3 -m venv .venv`, then `.venv/bin/pip install -r requirements.txt`. Configure secrets from the existing secret manager; keep `DEMO_ACCESS_ENABLED=false` and `FEDEX_ALERT_DELIVERY_ENABLED=false`. Set `FRONTEND_URL` to the exact deployed frontend origin, Redis/Azure/routing settings, and `FEDEX_WORKBOOK_PATH` to the protected workbook.
4. Copy a database backup to staging as `users.db` in the backend working directory. Run `.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 4208 --workers 1`. The active entry point is root `main.py`. Startup and Control Tower access apply additive migrations. Use one worker while simulation/planning memory remains process-local; do not introduce multiple workers without a shared runtime design.
5. In the frontend release directory run `npm ci`, `npm test`, and `VITE_API_BASE_URL=https://YOUR_STAGING_API npm run build`. Replace the uppercase URL with the actual staging origin. Serve `dist` through the existing HTTPS frontend host with SPA fallback; keep the backend behind its existing authenticated HTTPS proxy.
6. Run backend tests in a test workspace, authenticated staging import/status/critical/CON checks, existing planner demos, strict Air/recovery/multimodal flows and browser/viewport checks. Verify original schedule cells, owner separation and synthetic notices. Review delayed-source tolerance with operations.
7. At an approved cutover, stop/quiesce writers using the existing process manager, take a final consistent SQLite backup, switch the release while preserving the actual database/workbook paths, and restart with one worker. `DATABASE_URL` does not relocate every SQLite access: the current application uses `users.db` relative to the backend working directory. Verify that directory explicitly.
8. Keep alerts disabled until approved recipient configuration and a staging SMTP test pass. Provision `FEDEX_SCAN_INGEST_TOKEN` only after the verified provider adapter is ready. Enable delivery separately after reviewing pending outbox records, because enablement can release queued alerts.
9. Roll back application code by switching the process manager to the previous release/recovery commit. Additive tables can remain. Do not drop them or restore an old database over new operational data automatically; choose any data restore with operations after reconciling post-cutover events.

## Candidates for later cleanup and replacement — nothing deleted

The earlier list remains valid. Also review `legacy_risk_breakdown`, full legacy answer formatter and unconstrained general LLM summaries, duplicate legacy animation/view pathways, alternative entry point `backend/main.py`, large main bundle, old QA/backups and process-local playback persistence. Review removal only in a separately authorized pass after usage evidence and replacement tests. No pre-existing backup, source, test or generated artifact was removed in this session.
