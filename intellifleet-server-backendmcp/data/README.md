FedEx Control Tower workbook

`fedex-network-plan.xlsx` is the supplied `Sample Network plan - Air & Surface.xlsx`, copied without modification. It contains 38 source schedules (10 Air, 28 Surface); these are schedule/network facts, not live telemetry.

The importer resolves this file relative to the backend package, independent of the server's home directory or working directory. `FEDEX_WORKBOOK_PATH` remains an explicit override; an invalid configured path returns a structured 503 rather than silently using another workbook.

Include this data directory in the backend deployment. Load the Network Plan for the desired service date through `/operations/control-tower/import`. Imports are owner/date scoped and idempotent. Keep the backend's `users.db` on persistent storage to retain operational imports and events across deployment restarts. No external FedEx feed is enabled by this workbook.
