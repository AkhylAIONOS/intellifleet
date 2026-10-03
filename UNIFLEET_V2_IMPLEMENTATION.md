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
