# Strategic final UAT — reconciliation method

Cut: 2026-10-14 (America/Bogota). No operational database, running API, migration,
seed or source publication was accessed by these regression commands.

## Original execution remains non-green

`backend-strategic-regression.xml`: 914 executed cases, 889 PASS, 6 FAIL,
3 ERROR, 16 SKIP, suite time 3011.673 seconds. The original artifact is retained.
There is no claim that this single invocation passed.

## Fresh module-isolated reruns

Each rerun uses `docker run --rm`, the existing image
`pypmis-qra-engine-qra-validation:latest`, `/app` bound to `backend:ro`,
`/tmp` on disposable tmpfs and only the QA artifact directory writable.
The two pytest runtime variables are explicitly set before collection.

Common command shape:

```text
docker run --rm --name pypmis-uat-regression-<module>
  --tmpfs /tmp:rw,size=768m
  -e PYPMIS_PYTEST_BASETEMP=/tmp/uat-<module>
  -e PYPMIS_PYTEST_RUNTIME_DIR=/tmp/uat-<module>/runtime
  -e PYTHONDONTWRITEBYTECODE=1
  -e ALLOWED_HOSTS=localhost,127.0.0.1,testserver
  -e OPENBLAS_NUM_THREADS=1
  -v <absolute-repository>/backend:/app:ro
  -v <absolute-repository>/outputs/.qa/strategic-final-uat:/artifacts
  -w /app pypmis-qra-engine-qra-validation:latest
  pytest -p no:cacheprovider -o addopts= --no-cov -q -rA
  tests/<module>.py --junitxml=/artifacts/<artifact>.xml
```

Mapping:

| Module | Artifact |
| --- | --- |
| test_enterprise_structure_importer.py | backend-importer-isolated-final.xml |
| test_enterprise_structure.py | backend-enterprise-isolated-final.xml |
| test_portfolio_planning_gate07d.py | backend-preview-isolated-final.xml |
| test_strategic_final_uat_routes.py | backend-routes-isolated-final.xml |
| test_enterprise_structure_hardening_contract.py | backend-repository-contract-final.xml |
| test_strategic_final_uat_project_authority.py + test_strategic_final_uat_core_project_authority.py | backend-authority-guard-final.xml |
| test_gate07m_fid_e2e.py | backend-full-fid-isolated-final.xml |

The repository-contract rerun additionally binds the repository to `/repo:ro`
and sets `PYPMIS_REPOSITORY_ROOT=/repo`; this provides the real workflow,
Compose and Dockerfile omitted by the runtime image. It does not skip assertions.

## Cause classification (not hidden)

1. Importer, Enterprise root-count/record-code/publish and Portfolio preview:
   shared global SQLite state from unrelated earlier modules violated their
   clean-seed assumptions. Fresh module databases retain all original assertions.
   Preview had encountered legacy `STANDALONE`/`materialized` rows introduced
   elsewhere, outside the current ProjectRequestOut enum.
2. The three compact-route setup errors were duplicate `gate05c_outsider`
   security-role insertion when the reused Gate05C module fixture was registered
   twice against the same global database. Isolated execution retains the same
   normal HTTP commands, independent actors and full lifecycle assertions.
3. Old full FID case lacks the actual governed FiveCase sources now required:
   business analysis, benefits, economic/financial, commercial, permit and current
   FEL readiness. `BUSINESS_CASE_NOT_READY` is fail-closed product behavior. Do not
   downgrade policy requirements or force ready/completed/FID states to pass it.
4. PostgreSQL-only row-lock/concurrency and dedicated evidence-stack skips are
   not replaced by SQLite PASS. Dedicated PostgreSQL compact-route evidence
   remains separate and is not an extra unique count of the same tests.
5. Two large profiling cases are opt-in and have not been executed in this cut.

## Exact accounting

Final verified inventory: `backend-reconciled-final.json`, SHA256
`DF3020BC461BA81F713596F79301F1091B93083015B84B1B5E1D958EBE4700FF`.
Eight actual JUnit artifacts, 1013 raw executions, **952 unique identities**:
**936 PASS, 1 FAIL, 15 SKIP, 0 ERROR**. The unresolved isolated FullFID case is
retained as NO_GO evidence, not converted to a negative-test PASS.

| Latest rerun | Cases | Result | JUnit suite seconds |
| --- | ---: | --- | ---: |
| Importer | 12 | PASS | 113.642 |
| Enterprise | 8 | PASS | 196.504 |
| Portfolio07D | 2 | PASS | 200.306 |
| Compact routes SQLite | 3 | PASS | 228.338 |
| Repository contract | 3 | PASS | 37.932 |
| ADMIN/Project + CORE guards | 70 | PASS | 337.553 |
| Old full FID fixture | 1 | FAIL (FiveCase prerequisites missing) | 160.242 |

The latest guard run has 32 ADMIN/Project cases plus 38 CORE cases; those 32
already occur in the original 914 and are not additional unique cases. The
separate PostgreSQL compact-route run has 3 PASS in 239.293 JUnit seconds and
is not an extra 3 unique cases in the above SQLite/contract reconciliation.

Reproduction of final accounting, from the repository root:

```text
python outputs/.qa/strategic-final-uat/reconcile_junit.py
  --output outputs/.qa/strategic-final-uat/backend-reconciled-final.json
  outputs/.qa/strategic-final-uat/backend-strategic-regression.xml
  outputs/.qa/strategic-final-uat/backend-importer-isolated-final.xml
  outputs/.qa/strategic-final-uat/backend-enterprise-isolated-final.xml
  outputs/.qa/strategic-final-uat/backend-preview-isolated-final.xml
  outputs/.qa/strategic-final-uat/backend-routes-isolated-final.xml
  outputs/.qa/strategic-final-uat/backend-repository-contract-final.xml
  outputs/.qa/strategic-final-uat/backend-authority-guard-final.xml
  outputs/.qa/strategic-final-uat/backend-full-fid-isolated-final.xml
```

The private `reconcile_junit.py` accepts source JUnit files in explicit order.
Later sources take precedence for `classname::parameterized-test-name` only.
The JSON records every source SHA256, raw counts, unique current result,
changed outcomes, unresolved failures, skips and test identities. Failed original
executions stay present in the source list and changed-outcome history.

It is not valid to sum the raw case totals as additional unique tests, to count
SKIP as PASS, or to claim a successful single global run from this reconciliation.

## Test-only formatting remediation

`test_strategic_final_uat_project_authority.py`: replaced two assigned lambdas
with local functions (E731), sorted imports and formatted with the existing Ruff
executable. No assertion, requested state, permission, timeout or product file was
changed. Ruff check and format pass for the file.

## Final update after live Project adoption remediation

The final `backend-authority-guard-final.xml` now contains **78 PASS** in
227.566 JUnit seconds: the prior32 ADMIN/Project tests plus46 CORE tests
(including8 added adoption cases). The original70-case result is retained as
`backend-authority-guard-before-adoption.xml` and
`backend-authority-guard-initial.xml`. These are prior executions, not new cases.

Re-running the same eight-source reconciliation with this latest78-case source
produced **960 unique cases:944 PASS,1 FAIL,15 SKIP,0 ERROR** and1021 raw
executions. Final manifest SHA256:
`2A5A5D5F632ED5F5029229338A3CC5E7B423245BC1E3E34F5E8F3C35E4147A63`.
The earlier952/936 and70-case timings above are retained historical checkpoints,
not the final accounting. This is still not one successful global run.

A first adoption-only source had45 PASS and1 FAIL because its new fixture tried
to mutate an immutable published snapshot. The existing immutability guard
correctly refused it. The fixture now tests a corrupted candidate copy without
altering history. A separate8-case recheck and then a fresh78-case set passed.
The failed raw source is retained in `backend-core-adoption-final.xml`; see
`guard-adoption-validation.md`. No readiness requirement was weakened.
