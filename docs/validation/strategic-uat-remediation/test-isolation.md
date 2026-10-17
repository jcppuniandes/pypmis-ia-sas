# UAT-S3-002 — test-only isolation remediation

Baseline: `10a2442`; local cut 2026-10-14 (America/Bogota). No operational
database, policy, migration, protected Project or application permission was
changed by this test-harness remediation.

## Cause and boundary

The former `tests/conftest.py` created a single SQLite file for the entire pytest
process. Acceptance modules intentionally retain their own lifecycle fixtures,
but their rows then leaked to later modules. The original broad execution had
clean-seed assumption failures and the reused Gate05C fixture attempted to insert
the same `gate05c_outsider` role against an earlier module's database.

The shared module-autouse fixture now disposes pooled connections and resets only
the verified invocation-owned SQLite file at module boundaries. The engine object
and imported SessionLocal bindings are preserved. Each module then uses its normal
application lifespan and seed. No reset occurs inside assertions or between the
deliberate stages of a module's lifecycle. No product service, readiness rule,
assertion, permission, state machine or requirement was weakened.

This is database-namespace isolation: a tenant or Workspace identifier reused by a
legacy fixture refers to a fresh private SQLite database, not another module's
records. It establishes independence between modules. It does not claim that the
individual stages of existing ordered lifecycle tests may be arbitrarily shuffled.

`tests/sqlite_isolation.py` rejects a database outside the configured runtime tree,
an unexpected engine URL, a memory engine or a non-database file extension. All
resolved final targets, including SQLite sidecars and symlinks, are checked before
any unlink. Only that database file and its `-wal`, `-shm`, `-journal` sidecars are
eligible. Explicit `PYPMIS_TEST_DATABASE_URL` profiles are never reset; dedicated
PostgreSQL fixtures must own their own database/schema/tenant.

## Focused proof

One Docker pytest invocation collected these six files together:

```text
tests/test_sqlite_test_isolation.py
tests/test_enterprise_structure.py
tests/test_enterprise_structure_importer.py
tests/test_portfolio_planning_gate07d.py
tests/test_project_workspace_initialization.py
tests/test_strategic_final_uat_routes.py
```

`isolation-probe.xml`: **89 cases, 87 PASS, 2 SKIP, 0 FAIL, 0 ERROR**;
pytest elapsed 322.39 seconds. The two skips are explicit PostgreSQL row-lock
cases, not passes. This invocation proves that the formerly colliding hierarchy,
importer, Portfolio preview, Gate05C and reused route fixture can run together.
Its safety file had eight cases when collected. A ninth symlink-preflight safety
case was added subsequently and is covered by the separate final safety run.

`isolation-safety-linux.xml`: **9 PASS, 0 SKIP/FAIL/ERROR**, 4.03 seconds.
The same final source on Windows produced `isolation-safety.xml`:
8 PASS, 1 SKIP (temporary symlink creation not permitted), 1.41 seconds. Do not
add these overlapping safety runs to a unique regression case count.

Ruff check and formatter check passed for all three owned files.

## Broad regression — exact original scope

The broad run recovers the **same 61 files in original order** from unique
`testcase.classname` values in the retained
`outputs/.qa/strategic-final-uat/backend-strategic-regression.xml`.
The file count is checked before launching one pytest invocation. No test is
excluded or converted to skip/xfail. In particular the obsolete FID fixture is
retained and may still fail until its current-baseline replacement is proven.

```text
docker run --rm --name pypmis-remediate-isolation-global
  --tmpfs /tmp:rw,size=768m
  -e PYPMIS_PYTEST_BASETEMP=/tmp/uat-isolation-global
  -e PYPMIS_PYTEST_RUNTIME_DIR=/tmp/uat-isolation-global/runtime
  -e PYTHONDONTWRITEBYTECODE=1
  -e ALLOWED_HOSTS=localhost,127.0.0.1,testserver
  -e OPENBLAS_NUM_THREADS=1
  -e PYPMIS_REPOSITORY_ROOT=/repo
  -v <repository>/backend:/app:ro
  -v <repository>:/repo:ro
  -v <repository>/outputs/.qa/strategic-uat-remediation:/artifacts
  -w /app pypmis-qra-engine-qra-validation:latest
  pytest -p no:cacheprovider -o addopts= --no-cov -q -rA
  <same-original-61-files>
  --junitxml=/artifacts/backend-strategic-regression-global.xml
```

Both runtime variables are set before Python starts or tests are collected. The
backend/repository mounts are readonly; only the scoped QA artifacts directory
and private `/tmp` are writable. The container has no operational DB mount or URL.
No Docker volumes are removed, no cache is pruned and no main service is stopped.

**Original invocation: INCOMPLETE / INTERRUPTED.** On resumption on 2026-10-15
(America/Bogota), its retained log stopped at 94%, included at least one failure,
and no final JUnit existed. Its `--rm` container no longer existed after Docker
restarted. The partial progress is not a case-count result and is not counted as
a completed regression or as a pass. The original log is retained unchanged.

The exact original 61 files were relaunched together, in their original order,
without exclusions, xfail or replacement of the historical FID case. The new
private container is `pypmis-remediate-isolation-global-resume`; both private
runtime paths use `/tmp/uat-isolation-global-resume`. Its separate artifacts are
`backend-strategic-regression-global-resume.xml` and
`backend-strategic-regression-global-resume.log`. This is a new single invocation,
not a continuation whose overlapping cases can be added to the interrupted run.

**Resumed invocation: COMPLETED, audited 2026-10-15 (America/Bogota).** The one
unfiltered invocation finished with pytest exit code `1`. The XML and final CLI
summary agree on **914 collected cases: 898 PASS, 1 FAIL, 0 ERROR, 15 SKIP**.
There are 61 distinct modules and 914 unique, case-sensitive `classname::name`
identities; no case is duplicated. Case-sensitive comparison is essential:
intentional taxonomy inputs such as `[project]` and `[PROJECT]` are separate
parameterized tests, not duplicates.

| Execution | Collected | PASS | FAIL | ERROR | SKIP | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Retained original broad baseline | 914 | 889 | 6 | 3 | 16 | Not green |
| Interrupted isolation attempt | No completed count | — | — | — | — | Incomplete; not added |
| One resumed invocation | 914 | 898 | 1 | 0 | 15 | Not green; genuine legacy FID readiness failure retained |

JUnit suite elapsed time is `2799.850` seconds. The CLI summary includes its
additional runner overhead and reports `2805.88` seconds (`0:46:45`) and two
warnings. Those warnings concern the Starlette BlockingPortal alias and an
intentional invalid-scope fixture's Pydantic serialization; neither is an ERROR.
The XML timestamp is `2026-10-15T12:38:49.890743+00:00`. Its SHA-256 is
`c5a5d96bcd32a6eb7eaec4519d4a261138dad8178c4514ecd763ed464eaeae58`.

The same case identities previously affected by shared-module state now PASS in
this single invocation: Enterprise importer readonly validation; the three
Enterprise structure/configuration cases; Portfolio 07D preview without number
consumption; and all three reused final-UAT route cases. This is five former
FAIL cases and three former ERROR cases, verified by exact case identity, not by
adding isolated reruns. The one former repository-only SKIP is now PASS because
the original command's readonly `/repo` mount makes its CI/Compose/Dockerfile
contracts genuinely available. No skip or assertion was removed to produce it.

The remaining 15 SKIPs are explicit environment boundaries: seven PostgreSQL
concurrency/row-lock cases, six dedicated QRA-evidence PostgreSQL cases, and two
opt-in source/real-worker performance profiles. They are not counted as passes,
and this SQLite regression is not substituted for PostgreSQL A0–A31 evidence.

### Exact retained failure and closure boundary

The only failure is:

```text
tests.test_gate07m_fid_e2e::test_new_pyp_ffa_fid_path_full_stack_revalidation
HTTP 409 BUSINESS_CASE_NOT_READY
BusinessCaseService.complete_revision
```

Its actual readiness blockers are retained without downgrade:

```text
COMMERCIAL_CASE:REQUIRED_SOURCE_MISSING:commercial_strategy
ECONOMIC_CASE:REQUIRED_SOURCE_MISSING:business_analysis
ECONOMIC_CASE:REQUIRED_SOURCE_MISSING:economic_financial_model
FINANCIAL_CASE:REQUIRED_SOURCE_MISSING:economic_financial_model
FIVE_CASE_NOT_READY:BLOCKED
MANAGEMENT_CASE:REQUIRED_SOURCE_MISSING:benefits
MANAGEMENT_CASE:REQUIRED_SOURCE_MISSING:commercial_strategy
MANAGEMENT_CASE:REQUIRED_SOURCE_MISSING:permit
MANAGEMENT_CASE:SOURCE_NOT_READY:fel:BLOCKED
STRATEGIC_CASE:REQUIRED_SOURCE_MISSING:benefits
STRATEGIC_CASE:REQUIRED_SOURCE_MISSING:business_analysis
```

**UAT-S3-002 is closed only for cross-module test database isolation.** The
focused safety proof and one completed original-scope regression show the former
shared-state failures/errors no longer reproduce. This does not close the
current-release business/FID fixture gap, change any readiness rule, establish
arbitrary individual-test ordering, or make the broad suite green. The legacy
FID case remains a real FAIL, not xfail, skip or deprecated coverage. It must not
be retired until a modern fresh replacement has actually passed its own proof.

This broad process imported its modules before the later currency-snapshot
correction and the USER-screen binding change. Its result is not claimed as
regression coverage for those later edits. Their focused evidence and any
subsequent fresh PostgreSQL journey must remain separately identified; neither
is added to the 914 cases above.

## Separate fresh PostgreSQL journey — first observed business blocker

This diagnostic is **not** an isolation result or a substitute for A0–A31.
On 2026-10-15, the first current fresh journey stopped after its normal Portfolio
Evaluation completed. No Budget/Resource Scenario, recommendation or A13 Review
from that journey is claimed as completed. Diagnostic queries used explicit
PostgreSQL `BEGIN READ ONLY` / `SET TRANSACTION READ ONLY`; they did not rebuild,
seed, backfill, rewrite or re-evaluate a business record.

The exact isolated identities are tenant `1`, Portfolio `3`, Project `4`, Proposal
`1`, membership `1` (`STRATEGIC_INTAKE`, `ACTIVE`) and completed Evaluation `1`,
version `1`, revision version `3`. Proposal `1` has USD `100000000.00` and status
`STRATEGIC_GATE_APPROVED`. Project `4` is `pending`, version `2`, external key
`PRJ-cf9fe2d6-4906-4999-83b8-974aac1cfa3d`, RecordCode `01.01.01.01`.

The Proposal and Project `_project.currency_code` contain `USD`. The frozen
planning entry's nested `project_proposal.currency_code` also contains `USD`, but
its flat `currency` / `currency_code` fields are absent. The source builder
`PortfolioPlanningService._source_snapshot` captures `source_values.currency_code`;
`_planning_entry_snapshot` fails to transfer it. `PortfolioEvaluationService`
reads the flat planning-entry currency aliases, so the completed Evaluation's
flat `currency` is null. Portfolio Analysis consequently reports:

| Actual diagnostic field | Observed value |
| --- | --- |
| Project / Evaluation / contextual rank | `4` / `1` / `1` |
| ROM cost | `100000000.00` |
| Currency | `null` |
| Currency metric coverage | `0.00` |
| Warning | `ROM_COST_CURRENCY_MISSING` |
| Budget branch entry | `false` |
| Resource branch entry | `true` |
| Analysis hash | `d07b718afe25147e570e124900f4e6a59bfd1341c96cb6a72db081a75fa49c70` |

This is a product mapping omission, not a reason to replace USD with an invented
currency, weaken an assertion, ignore currency coverage or bypass readiness.
The independent currency remediation owns new snapshot construction and focused
tests. The original failed journey and its completed Evaluation must remain
historical evidence. A subsequent corrected full journey must start at its own
fresh upstream boundary; its results must not be merged into this failed journey.

Readonly preservation fingerprints captured before that correction:

| Protected isolated record / field | Value |
| --- | --- |
| Project `4` row MD5 (`md5(to_jsonb(w)::text)`) | `b63d8a3ff64993a9153edae3271e37cc` |
| Evaluation `1` row MD5 | `58c521e8c4d6c3cb47ca0c2a39ab4949` |
| Membership `1` row MD5 | `0287e564ddc753f99cb40db52ce947db` |
| Evaluation matrix hash | `456bef629f47a67c74e1c3ac1e17d5a0d1155e28c29d5277aa1a8a8563247bc4` |
| Planning-entry hash | `5b9df4de50050fac223ec2ed128eac689628c7ed0b500e6dfceaeb5cb9a5020a` |
| Evaluation source snapshot hash | `56a0f9346188b99bacb39172cb44c8321ce6facca4a3412e2d7803c93f9a9a78` |

These tenant/record IDs belong only to `strategic_fresh_uat`; they are not IDs
from the operational database and do not authorize mutation of protected Project
`14` or any published operational policy.

## Corrected-currency fresh journey — final configuration blocker

The later fresh journey is a **different** scenario: tenant `2`, Portfolio `7`,
Project `8`, Proposal `2`, Evaluation `2`. It is not added to the failed tenant-1
journey to claim A0–A31. The new normal snapshot has `USD`; its actual Evaluation
is `COMPLETED` and preserves the denomination. Budget Scenario `1` reached
`FROZEN` (hash
`dd4e8a3c5e0405fb03ff198cc16af67be9b803b1f4a844dd8d35e31c059d1c35`), and
Capacity Plan `1` reached `PUBLISHED` (hash
`dfaeeb6fceae7b29e31771967983c18eac14496e87c22ea05d215970962eba73`).
These are planning outputs, not investment approval.

The next normal command, `PortfolioResourceService.create_demand_profile`,
returned HTTP `409`, code
`PUBLISHED_PORTFOLIO_RESOURCE_CONFIGURATION_REQUIRED`. This is an unsatisfied
configuration prerequisite in the helper, **not a product defect**. The actual
contract calls `_tenant_policy(require_published=True)` for a Project Demand
Profile. Tenant `2` has Resource starter configuration `185` in `draft` with
scope `{type: tenant, workspace_id: null}`, but published successor `186`
(revision `2`) was scoped only to Portfolio `7`. Its valid Portfolio scope does
not make it a published tenant Demand policy.

The helper is corrected **for a future fresh execution only**: Resource policy
clone/update/preview/independent publication uses its real tenant scope; the other
four planning policies retain their Portfolio scope. No SoD, readiness,
freshness, coverage or lifecycle control is disabled. This code correction is
not proof of execution and does not close A11–A31. No current configuration or
business record was edited to bypass the blocker, and no new chain was launched
as part of this diagnostic.

Readonly checks at that stopping point found **zero** tenant-2 Demand Profiles,
Resource Scenarios, convergences, Portfolio Reviews, Gate preparations and
investment decisions. Therefore no tenant-2 A12/A13, Gate07J freeze, Gate07K GO,
FID, Post-FID, initialization or activation is claimed.

Preserved isolated metadata at that checkpoint:

| Record / field | Actual value |
| --- | --- |
| Project `8` status / version | `pending` / `2` |
| Project `8` external key | `PRJ-f6e867f8-6e99-47cd-9a03-cc252eb52a37` |
| Project `8` RecordCode | `01.01.01.01` |
| Project `8` row MD5 | `6ee1de518ef8a2f63b814753095bbf73` |
| Evaluation `2` version / revision version | `1` / `3` |
| Evaluation `2` row MD5 | `0016ee10b0ccc47ed41080bc89d1f7c5` |
| Evaluation `2` matrix hash | `01f8b8e7786523d6c61f07c8d8cfdd0f639dda5af76db060d570eea945d6374e` |
| Planning-entry hash | `721862a75ccf74166912a5ca72625d1c9842a524243ec58cb6c4515eb5159831` |
| Evaluation `2` source snapshot hash | `1d2000ce33f29bcc3647917b295032f2d3715184e5ca9d5eded6bce8dcd5c21f` |

At this historical stopping checkpoint, the release assessment was
`STRATEGIC_MACROPROCESS_NOT_VALIDATED`. The incomplete single-scenario business
proof and the separately identified USER-screen binding boundary were explicit;
human sign-off was not assumed. This is the preserved assessment of that failed
journey, not a prediction of any later separately authorized screen correction or
new fresh scenario.

A later independent `BEGIN READ ONLY` verification after the helper-only scope
correction confirmed that both Project row hashes and both completed Evaluation
row hashes above remain identical. Neither failed journey was backfilled or
rewritten to conceal its stopping condition.
