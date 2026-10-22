# Schedule-driven 4D projection

This module reads existing authority. It owns no geometry, Scope Items, Plan Items,
Activities, dates, baselines, float, or CPM logic. It introduces no tables or
persisted cache. A published `AdminConfiguration.kind = four_d_profile` controls
display styling, scope inheritance and mapping-completeness policy. Semantic
meaning is fixed to the four existing Scope Natures.

## Sources and lineage

`CURRENT` requires an `ACCEPTED_CURRENT` ScheduleVersion that is the selected
Register's current pointer. Multiple current streams require an explicit
`version_id`. `BASELINE` requires an explicit approved ScheduleBaseline and reads
its frozen Schedule snapshot and frozen Schedule mappings. A superseded version
remains a valid approved Baseline source. Staged and rejected sources are never
presented as Current.

Each result groups an approved Scope Item and a published historical Plan Item.
M:N Schedule mappings and source-qualified AWP mappings determine Activities.
Existing ScopeModelMapping and PlanItemModelLink provide IFC objects. Existing
DerivedModelVersion memberships provide immutable logical 3D subsets. Recorded
Schedule lineage selects historical Derived model identities. No mesh is copied.

An AWP Activity mapping has an explicit `EXECUTE`, `INSTALL`, `USE` or `REMOVE`
phase. A temporary item requires explicit install and removal phases and validates
their order. Names never determine phases. Missing dates, broken mappings and
ambiguous temporary semantics remain `UNKNOWN` with diagnostics.

Dates are interpreted in the declared Schedule Register timezone. Date playback
is a projection of Schedule dates, not physical completion certification. Actual
dates take precedence for Current; Baseline uses frozen planned dates. Milestones
reuse their one explicit source date without computing duration. Unknown float
or criticality remains unknown. Near-critical classification compares the imported
float to the existing published Schedule Profile's threshold in the same unit.

Readiness and constraints are a separately labelled **current operational overlay**,
including when viewing a historical Schedule Baseline. They are not misrepresented
as historical facts frozen inside that Schedule Baseline. A blocker never changes
Schedule dates, relations, P6 constraints or the base temporal semantic state.

`DELAYED` is an overlay only at explicit Data Date when a known imported incomplete
status is beyond its planned finish, or in a same-date comparison behind Baseline.
It does not calculate forecast dates. WBS filters include existing source ancestors.

## Read-only APIs

- `GET /api/v1/schedule/projects/{workspace_id}/4d`
- `GET /api/v1/schedule/projects/{workspace_id}/4d/traceability/{scope_item_id}`
- `GET /api/v1/schedule/projects/{workspace_id}/4d/compare`

The primary read supports source, version, baseline, selected date, WBS, Activity,
Scope Item, Scope Nature, Plan Item, CWA, Package Type, Package, Area, Zone, System,
imported Activity Status, Critical, Near-critical, Execution Readiness and Blocked
filters. Default selected date is the selected source's explicit Data Date, never
the machine date. Comparison evaluates both sources at the same selected instant
and rejects different Register streams.

Responses expose source hashes, configuration revision, original IFC identities,
derived subset identities, Schedule Version, Baseline/Current references and
Project Controls Period associations. The source-aware read-model hash is
rebuildable. GETs do not seed permissions, create business facts, write a cache,
or audit timeline scrubbing.

## Configuration and security

`/api/v1/schedule/4d/admin/profiles` provides GET, POST, PUT and explicit
`publish`/`successor` commands. Publication requires a different actor from the
author and last editor. Published configuration is immutable. Commands reuse the
O1A receipt, Idempotency-Key, If-Match and SecurityEvent patterns. Schema migration
0072 adds the PostgreSQL guard for `four_d_profile`; no separate 4D migration is
needed. Generic ADMIN configuration cannot bypass the dedicated publication API.

`four_d.read`, `four_d.admin.configure` and `four_d.admin.publish` are explicit
catalog permissions. Canonical Project Workspace and tenant isolation are checked
before loading sources. Permission provisioning is an explicit setup operation,
never a GET side effect. The inherited read also enforces AWP read access for the
operational overlay.

## Boundaries

No CPM, float, early/late date computation, resource leveling, P6 API sync, XER
export, full P6 exchange parity or physical-progress authority is added. A 4D date
projection cannot certify installed quantities, earned value or completion.

Pure state tests and PostgreSQL/HTTP integration tests are separate. Neither a
successful import nor these tests prove an executed Primavera P6 roundtrip or a
production performance SLA. Browser validation belongs to the isolated release
suite maintained with this increment.
