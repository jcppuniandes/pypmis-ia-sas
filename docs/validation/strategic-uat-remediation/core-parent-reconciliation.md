# CORE exact parent reconciliation — UAT-S3-003

Baseline: `10a2442bfb69b97dc72f9c78e2419f157b400973`.

## Scope

The normal CORE clone retains `PROJECT_PARENT_RECONCILIATION_REQUIRED` (409)
before draft creation when an existing live Project has a parent absent from
the historical snapshot. That guard is not disabled or caught as success.

The explicit controlled alternative adopts **existing identities into a draft**;
it does not create a parent Workspace or Project, transition a live Project,
alter an old published snapshot, approve a draft, or publish automatically.
No schema migration, new role, permission, module, or parallel identity exists.

## API sequence

Base path: `/api/v1/admin-configuration/enterprise-structure`.

1. `GET /enterprise-core-releases/{release_id}/parent-reconciliation`.
   Read-only diagnosis returns exact tenant-scoped missing parent IDs, keys,
   Record Codes, parent IDs, and affected Project IDs. Requires existing read
   permission with organization-wide scope, because the diagnostic enumerates
   tenant-wide live identities. A workspace-scoped reader receives 403 without
   those IDs/keys; no bootstrap writes occur. This is independently asserted
   through real RBAC and emitted-SQL no-DML checks.
2. Explicitly confirm every returned missing existing ancestor by ID. No names,
   taxonomy, ancestry, status, or arbitrary snapshot JSON may be supplied.
3. `POST /enterprise-core-releases/{release_id}/reconcile-live-parents`,
   body `{"parent_workspace_ids": [<confirmed existing IDs>]}` and
   `If-Match: "<revision_version>"`.
   Both existing revision create/edit permissions and organization-wide
   `structure_editor` duty are required; permission bootstrap is disabled.
4. If no draft exists, use the current published release ID/ETag. The explicit
   command checks the entire parent set before creating its successor DRAFT.
   Normal clone still fails closed in the same missing-parent circumstance.
5. If a draft already exists, a published target returns `DRAFT_ALREADY_EXISTS`
   with the draft ID. Review that draft, then explicitly reconcile using its
   own ID/ETag. Existing ADMIN edits are preserved. Content changes refresh
   fingerprints/diff and clear prior validation and approval.
6. Run normal validate, approval and publication duties. Publication remains a
   separate existing command with unchanged authority/hash/Project guards.

## Rejections and immutability

- Foreign or nonexistent parent ID: 404, no DML.
- Project ID supplied as a parent identity: 409, no DML.
- Incomplete missing ancestor list: original 409 reconciliation guard, no DML.
- Unrelated absent non-Project identity: 409 scope mismatch, no DML.
- Snapshot key with another technical ID/type: 409 identity mismatch.
- Duplicate/nonpositive IDs: 422; unknown request fields are forbidden.
- Stale ETag: 409 version conflict; absent ETag: FastAPI 422.
- Identical successful DRAFT replay: no DML and no version bump.
- Reconciled parents have a hash-covered snapshot provenance list (existing ID,
  key and type). Publish/materialize recheck those exact tenant-scoped live
  identities before DML. Concurrent replacement/renaming cannot be interpreted
  as authority to recreate a parent under a stale key. Generic CORE snapshots
  without reconciled-parent provenance retain their existing behavior.

Existing Project identity, parent, Record Code and lifecycle status remain the
same through publication. Reconciliation itself also leaves every live row's
version/defaults unchanged. Published source snapshot/fingerprint are preserved;
normal supersession metadata during publication follows the existing lifecycle.

## Evidence boundary

`test_strategic_core_parent_reconciliation.py` uses disposable structural
fixtures, not a claim that a Project Creation lifecycle has run. HTTP contract
tests and actual scoped RBAC tests are separate. Existing authority/revision
tests are included in the scoped run. Results belong in the current raw XML and
the final report; do not infer a whole strategic regression PASS from these
focused tests.

No operational database, Project ID14, historical policy or published CORE was
modified while implementing/testing this change. No commit or push was made.

## Final scoped execution

Authoritative current-code run: `core-parent-focused-current.xml`.

- Final post-scope-hardening run: 72 PASS, 0 FAIL, 0 ERROR, 0 SKIP;
  CLI duration 351.77 seconds. This rerun includes the tenant-wide GET's
  organization-scope guard and its negative real-RBAC/no-DML assertion.
- 17 new controlled reconciliation / HTTP / actual RBAC cases.
- 46 existing Project authority guards and 9 existing revision regressions.
- Disposable Docker runner, read-only backend mount, SQLite memory fixtures;
  **not** a PostgreSQL whole-strategic or A0–A31 proof.
- Runner exit 0. Ruff check/format and `git diff --check` passed.
- One existing Starlette/AnyIO deprecation warning, no test failure.

Raw initial/intermediate evidence is retained. The initial 67-case run had one
test-fixture duplicate Record Code failure; its unrelated-parent fixture now
allocates a distinct sibling code, with the negative product assertion kept.
The 70-case intermediate rerun passed before the additional exact-identity
provenance preflight. Do not add those reruns together as unique-case counts.

Scoped UAT-S3-003 technical criteria are now proven; this does not close other
strategic UAT defects or authorize business release.

The earlier 104-case scope diagnostic is retained separately as
`core-parent-scope-fixture-104.xml` (103 PASS, 1 FAIL). Its new positive fixture
had two missing live parents but confirmed only one; the product correctly
returned 409 with both required IDs. The fixture now explicitly confirms both
real parents, without weakening that guard. The final 72-case invocation above
uses the same three-file scope as the original focused proof; the extra 32
ordinary Project authority cases were already part of the completed broad
regression. Neither rerun is added to a unique global denominator. Three
pre-collection read-only runner setup failures are preserved as separate logs;
they produced no JUnit and are not represented as executed product tests.
