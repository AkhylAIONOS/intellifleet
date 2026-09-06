IntelliFleet frontend runtime crash fix

Exact root cause

The original `journeyPlayback.ts:20` executed `scheduler.request(tick)`. The default scheduler was constructed as `{ request: requestAnimationFrame, cancel: cancelAnimationFrame }`. These properties held browser-native Window methods, but calling them through `scheduler` supplied the scheduler object as `this`. Chrome rejected that receiver with `TypeError: Illegal invocation`. The synchronous exception escaped the SelectedJourneyLayer effect and React unmounted the unprotected dashboard.

The correction in `src/utils/journeyPlayback.ts` is:

```ts
request: (callback: FrameRequestCallback) => window.requestAnimationFrame(callback),
cancel: (id: number) => window.cancelAnimationFrame(id),
```

Both native methods now execute with the Window receiver. The other journey browser APIs were reviewed: `performance.now()` remains a method call on Performance; timers, matchMedia and event listeners are invoked on their owning objects.

This is not intrinsically a two-vehicle array bug: any default animated playback can reach the same offending call. The reported multi-vehicle request exposed it. The supplied exception does not establish why earlier single-vehicle attempts did not expose it, and this fix does not assume a different backend result or invent an explanation for that observation.

Why previous tests missed it

The existing tests replaced RAF methods with arrow functions that ignored `this`. They checked animation timing and positions but did not enforce the receiver requirement. The new scheduler regression deliberately requires `this === window` while using the production default scheduler. Before the correction it failed with `TypeError: Illegal invocation` at `scheduler.request(tick)`; after the correction it passes for request, rescheduling and cancellation. This is a receiver-contract regression test, not a claim of live Chrome execution.

Files changed in this crash-fix task

All code/test paths are relative to `intellifleet-web-main/frontendmain/`:

- `src/utils/journeyPlayback.ts`: correct Window calls; route asynchronous frame failures to scoped containment; preserve ten-second playback and cancellation.
- `src/utils/planVisuals.ts`: normalize optional assignment/leg arrays without recalculating loads; reject invalid geometry; recognize optional explicit route/leg assignment metadata.
- `src/store/appStore.ts`: normalize selected plans at ingestion and retain valid assignment details when geometry is missing.
- `src/components/PlanVisuals.tsx`: use normalized optional arrays in Plan Snapshot.
- `src/components/MapLayers/SelectedJourneyLayer.tsx`: validate geometry, avoid a loop for zero assignments, preserve one grouped marker, clean partially initialized effects, and surface frame errors to the boundary.
- `src/components/JourneyBoundary.tsx` (new): narrowly scoped React boundary and Leaflet fallback, reset by new plan selection. Errors remain logged.
- `src/components/MapView.tsx`: mount the guarded selected journey.
- `tests/run-browser-scheduler.mjs` (new): regression for the production scheduler's Window receiver, timing, cancellation and reduced motion.
- `tests/run-dashboard-journey-crash.mjs` (new): complete dashboard under StrictMode with 30 warehouses, 97 vehicles and 62 persisted route fixtures; verify exact assignments, count, visibility, transitions, replay and error containment.
- `tests/run-map-journey-dom.mjs`: make RAF mocks enforce the Window receiver while retaining real Leaflet tests.
- `../../MAP_RUNTIME_CRASH_FIX.md` (new): this record.

No backend source, planning formula, feasibility rule, allocation logic, authentication or network upload behavior was changed. An actual 18,000 kg deterministic result was also inspected using read-only database access; its assignments were 11368.421053 and 6631.578947 kg. The requested regression fixture separately verifies the supplied 11368.42 and 6631.58 values. Both are displayed/preserved as supplied, never reconstructed from 94.74% utilization.

Containment and lifecycle

A synchronous setup failure releases any created layer/listeners and reaches the local boundary. A failure during an animation callback stops scheduling and reaches the same boundary through React state. The fallback reads “Journey visualization unavailable for this plan.” Chat, Plan Snapshot, Network Ready, Supply-Chain Planner, Add Route, metrics and upload UI remain outside that boundary. A new selection resets it. Tests inject failures both during Leaflet setup and during marker movement, and assert dashboard survival and recovery.

The grouped marker retains both assignments, uses one playback loop, and shows both exact loads in its details. Missing/empty assignments and missing optional metadata are normalized; missing or invalid geometry leaves the dashboard/result visible and skips playback. Development StrictMode, Road → Air → multi-vehicle replacement, replay and active unmount cancellation are exercised.

Verification

- Frontend suite: all 9 scripts passed (exit 0). This includes the existing warehouse, scenario/disruption, route-management, planner and New Chat checks.
- After the final asynchronous-containment adjustment, both affected scheduler/full-dashboard regression scripts were rerun and passed.
- Full-dashboard tests cover zero, one Road, one Air, two Ground, missing optional metadata, null entries, missing/invalid geometry, exact 18000 kg assignments, Assigned Vehicles = 2, both IDs/loads, one animation, replay, reduced motion, Copy, New Chat, scoped failures/recovery and active unmount.
- Production build: `npm run build` passed (exit 0), 253 modules, 621.30 kB JavaScript / 191.00 kB gzip. Vite retains the non-failing warning for a chunk above 500 kB.
- TypeScript and `git diff --check` passed.
- No live manual Chrome run is claimed. Browser setup failed with “privileged native pipe bridge is not available; browser-client is not trusted.” The provided Chrome stack trace and the reproduced receiver-contract exception identify the root cause; manual browser confirmation remains required.

Manual confirmation

Reload the updated frontend in Chrome. Run the 6000 kg balanced plan, fastest plan, warehouse follow-up, then the 18,000 kg request. Confirm the dashboard stays visible, the metric reads 2, both assignments appear, the grouped truck moves, and Replay Journey works. Drag/zoom to release follow, then test New Chat. Confirm no new `Illegal invocation` appears in the console. Repeat with reduced motion enabled to confirm static final positioning.
