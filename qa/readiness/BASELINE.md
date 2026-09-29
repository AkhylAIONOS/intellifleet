# Readiness baseline — 29 September 2026

Branch: feature/fedex-simulation; HEAD d9abe606ce78449b68d64995dae5afff16d48dff.
Existing dirty files are recorded verbatim in baseline-git.txt and preserved.

- Backend: 206 passed, 0 failed (baseline-backend.txt).
- Frontend scripts: passed (baseline-frontend.txt).
- Production build: passed; existing chunk-size warning (baseline-build.txt).
- Existing manual servers: API 4200 / frontend 5178; Vite .env targets localhost:4200.
- Isolated QA: API 4219 / frontend 5189; disposable SQLite and in-memory Redis; normal signed JWT via supported demo access; existing AI configuration loaded without copying credentials.
- Browser tooling: no connected Browser plugin instance; installed Chrome available; Playwright development dependency added for requested browser QA. Browser baseline pending first run.

## Defects confirmed by inspection before fixes

1. P1: Operational chat enumerates every active movement for a current lane query; no origin/gateway filter. Alerts/recommendations shown only for risk wording.
2. P1: Planner narrative converts aware timestamps to UTC despite India demo presentation.
3. P2: Planner default narrative dumps score components, cost/risk internals and all alternatives.
4. P1: Planner form async actions have no catch/error display; infeasibility yields no visible explanation when no plan is returned.
5. P2: Chat labels last planning snapshot “Current shipment” even in live/schedule workspaces.
6. P2: Live movement panel/tooltips print raw ISO timestamps, unlike schedule panel.
7. P2: UI workspace labels do not explain schedule versus fleet movement responsibilities.

Prior upload CORS fix is present in working tree. Auth, importer validation, atomic rollback and V2 counts passed prior targeted tests. No new source fixes made before this record.

## Initial Chrome evidence

Chrome rendered the actual app and imported the V2 network. Planner Delhi–Mumbai and 100-movement setup passed. Browser screenshot confirmed two NetworkUpload instances (chat + Network workspace), last plan mislabeled as current shipment, and duplicated planner overlay counted as a 73rd network route. No JS/console/HTTP errors in the completed baseline browser run. The live answer saved in baseline-live-answer.txt dumped the unrelated fleet. Baseline cutoff checks were blocked by overly strict accessible-label selectors, not an established product failure; those selectors were corrected. Upload response-body reading raced with the intended page reload; summary retrieval is the browser assertion instead.
