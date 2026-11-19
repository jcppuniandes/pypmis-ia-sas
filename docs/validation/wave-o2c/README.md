# Wave O2C Contracts and Commitments Foundation

Technical closeout: 18 November 2026.

Status: WAVE_O2C_CONTRACTS_COMMITMENTS_FOUNDATION_RELEASE_VALIDATED

This is a local technical validation, not a production deployment, a production migration or business signoff. Project 14 was observed read-only. No next wave was started.

## Authority

Procurement retains PO and vendor ownership. Contracts owns its canonical packages, instruments, immutable approved versions, execution, commercial commitments, SOV, changes, applications, certificates, notices and claim register.

Cost owns explicit adoption and native financial proposal/independent verification. The O2C financial adapter allows REFERENCE_ONLY with zero net commitment contribution. It does not recognize Actual Cost, post accounting, issue an invoice, execute payment or change Budget/EAC.

Scope, Progress, Schedule/P6, Forecast, AWP and CDE retain their existing authority. Legacy commercial tables are not backfilled or overwritten.

## Observed checks

| Check | Result |
| --- | --- |
| Policies and navigation | 437 passed |
| Schedule policy on PostgreSQL | 27 passed |
| Core contract and Cost HTTP chain | 1 integrated test passed |
| Commercial HTTP chain | 1 integrated test passed |
| Signed approval caps | 2 passed |
| Future change guard | 1 passed |
| Cross-domain and cross-workspace HTTP boundaries | 1 integrated test passed |
| Chromium lifecycle | 1 passed |
| Chromium settled UI read verification | 1 passed |
| Frontend Contracts and Cost | 40 passed |
| TypeScript, bundle, ESLint and Prettier | Passed; existing BIM/Scope warnings retained |
| Backend Ruff | Passed |
| PostgreSQL migration | Historical bootstrap, upgrade 0078, upgrade 0079, downgrade 0078, upgrade 0079 |
| DDL and metadata | 72 normalized statements match |
| Project 14 | Before and after rows/hashes and 70 legacy + 74 workspace FK catalogs match |
| Performance | Ten reads, three samples, median and response size; no SLA |
| Word | Seven pages rendered and inspected; accessibility audit has zero findings |
| Workbook | Seventeen sheets rendered, inspected and exported/imported with matching values |

The legacy projects.id 14 row is absent in this environment. The canonical enterprise workspace 14 exists and was preserved. This distinction is intentional.

## Evidence

Task-local evidence is retained under ignored outputs/.qa/wave-o2c-20261118. Private fixtures and browser traces may contain disposable credentials and must not be published.

- core-attempt-a/junit.xml, scenario.json and proof.json
- commercial-junit.xml, commercial-policy-junit.xml and commercial-evidence.json
- unit-attempt-a/junit.xml and schedule-attempt-a/junit.xml
- security-final-junit.xml, boundary-junit.xml and final-boundary-http.json
- browser-attempt-b-junit.xml and chromium-attempt-b/o2c-browser-evidence.json
- readonly-ui-junit.xml and readonly-ui/readonly-verification.json
- migration/proof.json and commands.log
- project-14/preservation-before.json and preservation-after.json
- frontend-checks.json, backend-checks.json and ddl-compare.json
- performance-final.json, release-decision.json and release-evidence.json

Earlier failed attempts are retained, not presented as passing results. The final Chromium run reused the independently published profile from the preceding UI attempt after verifying its identity and contents.

## Reproduction

The helpers deliberately target disposable loopback databases. Do not substitute a production URL.

From the repository root, with the backend virtual environment:

    backend/.venv/Scripts/python.exe scripts/wave-o2c/run_validation.py unit new-attempt
    backend/.venv/Scripts/python.exe scripts/wave-o2c/run_validation.py schedule new-attempt
    backend/.venv/Scripts/python.exe scripts/wave-o2c/run_validation.py core new-attempt

Use unique attempt identifiers. Commercial tests require PYPMIS_O2C_FIXTURE=disposable-only and the exact PYPMIS_TEST_DATABASE_URL used by the O2C test guard; use -o addopts= for the focused regression instead of asserting project-wide coverage from a narrow slice.

Alembic revision 20261113_0079 follows 20261111_0078. Its frozen SQL is shipped alongside the migration. Ordinary startup does not create the new governed tables.

Contract permissions can be provisioned only by the explicit audited organization-admin command in app.modules.contracts_foundation.provision. The migration does not assign users, enable the module or create records in existing tenants.

## Remaining nonblocking items

- S3: local workspace-context latency under concurrent validation. The final browser lifecycle passed with a 180-second initial loading allowance. No SLA is claimed.
- S3: additional database-level scope guards for simple parent foreign keys. HTTP services validate tenant/workspace scope; direct SQL administration remains restricted.
- The future-effective Change Order defect is closed. Preparation/review are allowed, but approval before its effective date is rejected in this foundation.

Deliverables are under outputs/wave-o2c. No commit or push was performed by this increment.
