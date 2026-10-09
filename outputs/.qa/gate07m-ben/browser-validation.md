# Gate07M-BEN browser validation

Date: 2026-09-17

## Executed Chromium scenarios

1. `USER/ADMIN separation and canonical navigation` — PASS.
2. `Direct-route guard and bounded traceability requests` — PASS.
3. `USER Plan/Benefit/KPI/lineage/readiness/lifecycle contract` — PASS.
4. `ADMIN catalogs/rules/applicability/inheritance/numbering/SoD/revision lifecycle contract` — PASS after correcting a strict locator; the isolated rerun finished `1 passed` in 44 seconds.

The current Playwright state file records `status=passed` and an empty `failedTests` list for the last isolated run.

## Consolidated rerun note

A final single-command rerun of all four scenarios against the rebuilt localhost deployment was requested. The host permission reviewer rejected browser process creation because its usage allowance was temporarily exhausted. This is an execution-environment limitation, not an application or test failure. No alternate browser-launch workaround was attempted.

## Deployment checked separately

- `http://127.0.0.1:8000/api/v1/health/ready` returned HTTP 200 with API, database and Redis healthy.
- `http://127.0.0.1:5173/app` returned HTTP 200.
- Docker API, frontend, worker, beat, PostgreSQL and Redis services were running after rebuild/recreate.
- Alembic reported `20260916_0061 (head)` inside the deployed API container.
