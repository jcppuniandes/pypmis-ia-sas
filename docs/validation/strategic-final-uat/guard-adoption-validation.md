# Final guard adoption review — 2026-10-14

## Correction scope

The original authority hardening correctly blocked Project creation/status changes
through ADMIN and CORE commands, but cloning a historical published snapshot did
not adopt a Project created or activated later through its USER authority. Such a
draft could never pass the omission/status guard.

The existing `create_revision` command now reads actual tenant-scoped Project
identities and lifecycle status into the requested draft only. A new Project is
adopted with its actual identity and classifications only when its actual parent
is already represented by the exact parent ID in that draft. Existing non-Project
draft edits are preserved. Actual current Project state is observed, never set by
this command. Historical published snapshots and live Project rows are unchanged.

An explicit repeated create request reconciles an existing draft. If the draft
changes, the existing revision refresh invalidates validation and approval and
increments its optimistic version. An unchanged repeated request performs no DML.
Foreign ID/type mismatches are refused before reconciliation can conceal them.
Publication and rollback still recheck live state before materialization/DML.

No endpoint, permission, table, migration, module, business acceptance or policy
publication was added. Unit fixture state changes are not claimed as USER HTTP
lifecycle evidence; the earlier compact-route HTTP/PostgreSQL evidence is separate.

## Explicit residual boundaries

- An actual Project whose parent is missing from the draft is refused with
  `PROJECT_PARENT_RECONCILIATION_REQUIRED`. No non-Project ancestry is invented.
- Rollback to a historical snapshot that would omit a live Project or revert its
  lifecycle remains refused. Metadata-only historical rollback remains supported.
- Legacy `StructureNodeForm` still offers Project and lifecycle options; those
  forbidden commands are now backend-denied. Browser proof of no Project form is
  specifically the corrected Composition Rules screen, not all ADMIN screens.

## Source integrity

- `revisions.py` SHA256:
  `28F4A08AA0F2727753C94F77608B013E0C83F530E8DCD1D903847D315916163B`.
- `test_strategic_final_uat_core_project_authority.py` SHA256:
  `7EF12171FDDB276402E57A82F8A31EA3DA0D595D5925662B21E1C8E5B2ECF27D`.
- Ruff format/check and `git diff --check`: PASS.

## Reproduction and results

All test containers use the existing image, read-only `/app` backend mount,
disposable `/tmp`, SQLite in-memory database URLs, no service dependencies and
only the private QA artifact directory writable. No main operational database,
volume, seed, migration, policy publication, commit or push is used.

Initial full CORE run: **45 PASS / 1 FAIL / 0 ERROR / 0 SKIP**, 281.00 pytest
seconds (281.022 JUnit suite seconds), raw artifact `backend-core-adoption-final.xml`. The sole failure was a
new fixture attempting to ORM-update an immutable published CORE snapshot; the
existing history-protection guard correctly refused that setup. The corrected
fixture tests the corrupted new-draft copy without bypassing history protection.
The raw failed attempt is retained, not represented as a product PASS.

Recheck of the eight added cases: **8 PASS / 0 FAIL / 0 ERROR / 0 SKIP**,
38 other cases deselected, 125.74 pytest seconds (125.498 JUnit suite seconds),
artifact `backend-core-adoption-recheck.xml`, SHA256
`26F893B2E8D8C2AC143DA2DF33714278730D10972B14BF8148DC99D8540F7B67`.

Final fresh full authority set: **78 PASS / 0 FAIL / 0 ERROR / 0 SKIP**
(32 ADMIN/Project plus 46 CORE), 227.65 pytest seconds (227.566 JUnit suite
seconds), one Starlette/AnyIO deprecation warning, artifact
`backend-authority-guard-final.xml`, SHA256
`354BD9FC4D1C23DFBA50FB6A68A36385C3F324E4DC5C25DD0D36722E6F1A52F6`.
The earlier 70-case guard proof was preserved as
`backend-authority-guard-before-adoption.xml` before replacing the final output.

Exact final PowerShell command from the repository root:

```powershell
docker compose -f docker-compose.strategic-uat.yml run --rm --no-deps --name pypmis-uat-authority-guards-final -e DATABASE_URL=sqlite+pysqlite:///:memory: -e PYPMIS_TEST_DATABASE_URL=sqlite+pysqlite:///:memory: -e PYPMIS_PYTEST_RUNTIME_DIR=/tmp/uat-authority-guards-final/runtime -e PYPMIS_PYTEST_BASETEMP=/tmp/uat-authority-guards-final evidence-browser-api python -m pytest -p no:cacheprovider -o addopts= --no-cov -q -rA tests/test_strategic_final_uat_project_authority.py tests/test_strategic_final_uat_core_project_authority.py --junitxml=/artifacts/backend-authority-guard-final.xml
```

The eight-case recheck uses the same isolation with container name
`pypmis-uat-project-adoption-recheck`, runtime paths
`/tmp/uat-project-adoption-recheck[/runtime]`, the CORE test file only, and
`-k 'new_revision_adopts or explicit_create or reconcile_never or reconcile_does or missing_core_parent'`.
