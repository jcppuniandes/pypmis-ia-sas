# AWP execution foundation

This module owns canonical Construction Work Areas, execution Work Packages,
their M:N memberships and dependencies, Execution Constraints and immutable
Readiness Assessments. Scope remains the WHAT authority. Schedule remains the
versioned date authority and Primavera P6 remains the only CPM authority.

The pre-existing `work_packages` and `work_package_constraints` tables belong to
the legacy `projects.id` workflow and retain planned dates and progress fields.
They cannot safely express canonical Project Workspace identity or governed M:N
memberships. They are preserved unchanged. No silent migration, projection back
into those legacy tables, duplicate Scope Items or new Activities is performed.

## Authority and concurrency

All records use `tenant_id` and canonical `project_workspace_id`. Domain commands
reuse the O1A receipt ledger, tenant serialization, audit, reason, `Idempotency-Key`
and `If-Match` conventions. Mutable aggregates have incrementing version/revision
and append immutable `awp_history` snapshots. Package and constraint memberships
are append-only SET/REMOVE rows. AWP never updates Schedule or Scope records.

Activity membership references the accepted source Schedule Version plus stable
external Activity identity. Explicit `EXECUTE`, `INSTALL`, `USE`, `REMOVE` phases
let the 4D read model resolve multi-Activity temporary Scope without guessing from
an Activity's name. Superseding Current does not rewrite memberships. Their live
health becomes `REQUIRES_REVIEW` or `BROKEN` until explicitly reconciled.

`ExecutionConstraint` is separate from the P6 Schedule Constraints in the accepted
Schedule snapshot. Due dates never close a condition. Closure/waiver requires an
independent authorized actor and evidence. Completing a package does not clear
its constraints. A typed blocking dependency is satisfied by explicit predecessor
completion or explicit evidence-backed dependency clearance, not P6 dates.

## Readiness and release

The published `awp_profile` configures types, constraint applicability/blocker
rules, dependency types, lifecycle transitions and required evidence dimensions
per package type. Unsupported lifecycle transitions cannot bypass review/release.
Readiness evaluates inherited CWA conditions plus Package/Scope/Plan/Activity
memberships and dependencies. It does not use Schedule dates as readiness proof.

An assessment stores the precise sources' hashes and policy revision. GET builds
a request-local, non-authoritative projection and never creates facts. A source
change makes an old assessment stale. Release requires a fresh READY assessment,
the READY lifecycle state, and explicit independent release authorization. READY
never automatically becomes RELEASED. The preparation and assessment actors are
excluded from release according to the published SoD policy. A later blocker
retains the historical release fact but appears as NOT_READY in the live overlay.

## Deployment

Migration `20261021_0072` is additive, parent `20261021_0071`, with PostgreSQL
canonical-reference, source-history and published AWP/4D profile guards. Downgrade
refuses to destroy populated execution history. No source backfill is included.

After applying migrations, an existing organization administrator explicitly runs:

```text
python -m app.modules.awp.provision --tenant-id <tenant> --actor-id <admin> --reason "Approved AWP enablement"
```

This provisions permission catalogs and role duties only. It creates no actor
assignments, Scope facts, Project bindings, packages or constraints. Publish an
applicable ADMIN AWP profile through its domain endpoints before USER commands.
The generic ADMIN configuration endpoints cannot mutate AWP or 4D profile kinds.

There is no Cost, Progress, Engineering, Procurement, Logistics or field execution
workflow implementation in this delta. Packages are execution containers only.
