# Schedule Foundation · Wave O1B-B

Schedule is downstream of canonical O1A operational authorization and the current
approved Scope baseline. It does not create or update Scope Items, Execution
Strategies, Plan Items, original/derived BIM models, budgets or progress records.
Primavera P6 remains the external CPM authority.

## Persistence and source editing

The additive migration `20261021_0071` succeeds `20261020_0070` and creates six
Schedule-owned tables: registers, source versions, append-only Scope/Plan mappings,
baseline snapshots, export manifests and explicit control-period associations.
WBS, activities/milestones, calendars, relationships, constraints and code records
belong to an immutable version snapshot rather than duplicating global/Scope
models. Each query exposes the source version and external identity.

A staged WBS move or manual activity edit creates a **new source version** through
`POST registers/{id}/versions`, naming its predecessor and explicit reason. Even
draft source snapshots are not rewritten in place. Imported CPM-derived fields
cannot be invented or changed through a manual definition. WBS paths are rebuilt
from explicit parents; no schedule structure is inferred as canonical Scope.

All writes use O1A command receipts, idempotency, optimistic concurrency and audit.
Operational writes additionally require canonical Project scope, active operational
authorization, published Operational/Scope/Schedule profiles and approved Scope.
GET handlers do not provision catalogs, configuration, bindings or business data.
Permission catalog setup is an explicit audited CLI, not a side effect of a read.

## Lifecycles

- Source: `DRAFT/STAGED → VALIDATED → UNDER_REVIEW → ACCEPTED_CURRENT`; the former
  Current becomes `SUPERSEDED`. Rejection preserves history.
- Baseline: `BASELINE_CANDIDATE → SUBMITTED → UNDER_REVIEW → APPROVED_BASELINE`.
  Accepting Current does not approve a baseline or change the baseline pointer.
- Mapping: append-only revisions with `VALID`, `STALE`, `BROKEN`,
  `REQUIRES_REVIEW` or a `REMOVED` tombstone. Changed source identities require
  explicit reconciliation; removed identities keep their broken lineage.

Acceptance excludes the source importer and last material mapping editor when
published policy requires separation of duties. Baseline approval similarly
excludes preparer/material editor. A locked register and the latest approved
baseline identity prevent approving a stale concurrent baseline candidate even
when both candidates point to the same source version. Schedule profile
publication excludes its author and latest material editor.

ORM and PostgreSQL guards protect accepted/source snapshots, mapping history,
baselines, manifest bytes, period associations and published profiles. References
are tenant/Project-scoped; populated Schedule history is not silently destroyed
by downgrade.

## Exchange and authority limits

Manual import supports the documented bounded P6 XML and XER subset implemented
in `exchange.py`. Native source bytes, hash, version manifest, preserved source
fields, unsupported fields and validation findings are retained. XML export
produces actual downloadable APIBusinessObjects XML, not JSON/CSV renamed as XML.
Its exact bytes and hash are immutable. XER export is explicitly unsupported.

Export is intentionally limited: positive numeric P6 ObjectIds, declared HOUR
units and supported XML calendar/constraint structures are required. Opaque XER
calendar definitions are preserved on import but cannot be falsely exported as
lossless XML. Baseline references belong to the governed manifest; the subset does
**not** transport native P6 BaselineProject objects. Full P6 parity, licensed P6
application roundtrip and native schema validation are not claimed.

Criticality and float remain imported evidence. Missing results are `UNKNOWN`.
Near-critical classification uses a published HOUR threshold over imported float;
it is not a local CPM calculation. Quality checks evaluate mappings, calendars,
open ends, lags, constraints and duration thresholds without calculating dates,
critical path or float. No eight-hour day, calendar or missing quantity is invented.

Current export requires current valid lineage; approved historical baseline export
remains historical evidence rather than asserting that its Scope is current.
Data Date is retained independently from O1A cutoff dates. Period association is
explicit and preserves both values without mutating the period. Look-ahead is a
read-only query; it does not activate Progress, Cost or Timeline/4D execution.

## API

Project endpoints live under `/api/v1/schedule/projects/{workspace_id}`:
`overview`, `registers`, `versions`, `mappings`, `baselines`, `exports` and
`period-associations`. Version commands cover import/manual successor, validate,
review, accept/reject, mapping revisions, baseline preparation, XML export and
period association. Version reads expose WBS, activities, calendars, relationships,
constraints, codes, assignments, external links, mapping health and look-ahead.
Profiles use the dedicated `/api/v1/schedule/admin/profiles` API; generic legacy
configuration mutation cannot bypass that boundary.

Tests are isolated PostgreSQL release/policy/migration contracts plus parser tests.
The disposable database bootstrap intentionally starts from an existing ORM
baseline before real additive O1A/Scope/Schedule migrations; it is not an
empty-database-to-head production migration claim. Normal development/production
databases must not be used for these fixtures.
