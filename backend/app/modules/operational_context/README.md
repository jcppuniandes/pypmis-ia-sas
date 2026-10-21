# O1A operational foundation

Canonical identity is `enterprise_workspaces` with `workspace_type_code=project`.
`projects.id` is only a legacy operational reference. The three additive tables
do not create another Project master. Activation never creates a legacy row.

## Explicit installation and provisioning

Run the normal deployment migration, `alembic upgrade head`, against the intended
database after backup/review. Revision `20261019_0069` is additive. No production
tenant or Project is automatically reconciled by this migration or by startup.

From `backend`, an existing organization administrator can explicitly provision
the permission catalog and duty roles:

```powershell
python -m app.modules.operational_context.provision --tenant-id 1 --actor-id 2 --reason "Approved O1A rollout"
```

Replace the example IDs with verified tenant/administrator IDs. The command
requires existing `organization_admin` organization scope, creates an audit
event, assigns no new actor role, creates no Project and creates no binding.
GET endpoints never invoke provisioning. Assign the required tenant/Workspace-
scoped duties through existing Organization & Security administration. Publishing
is a separate duty; default policy prohibits author self-publication and period
closer self-publication.

## API

Prefix: `/api/v1/operational`.

| Query/command | Permission suffix (`operational_context.`) |
|---|---|
| `GET /options`, `/projects/{workspace_id}/context`, `/binding`, `/authorization`, `/periods` | `read` |
| `POST /projects/{workspace_id}/binding`, `/binding/reconcile`, `/binding/revoke` | `binding.manage` |
| `POST /projects/{workspace_id}/periods` | `period.open` |
| `POST /projects/{workspace_id}/periods/{id}/review`, `/close`, `/publish`, `/reopen` | `period.review`, `period.close`, `period.publish`, `period.reopen` respectively |
| `GET /admin/profiles`, `POST /admin/profiles`, `PUT /admin/profiles/{id}`, `POST /admin/profiles/{id}/successor` | `admin.configure` plus organization scope |
| `POST /admin/profiles/{id}/publish` | `admin.publish` plus organization scope |

Commands require `Idempotency-Key` (8–160 characters). Binding creation and
reconciliation require `If-Match` matching current binding version; an absent
binding is version `0`. Period transitions and profile updates/publication/
successors require positive `If-Match`. Stale requests return `412`; identical
actor/key/payload retries return the original command result. Reusing a key with
another actor or payload fails closed.

Bindings explicitly select a legacy reference, or record
`NO_LEGACY_BINDING_REQUIRED`. Verified reconciliation accepts only existing
explicit forward/reverse references and rejects ambiguous candidates. No numeric
ID, name or code matching is performed. Reconciliation creates successor history;
revocation preserves the record. Database constraints enforce tenant/type and
active uniqueness in both directions.

## Source authority and period boundary

Owner authorization reads current Gate 07K and Post-FID references without
mutating those sources. Contractor uses contract/award/mobilization/NTP source
metadata; Direct uses approved internal sponsor authorization. An ACTIVE Project
never defaults commitment authorization to true. Unresolved commitment-only
conditions remain visible and do not become activation blockers.

Operational profiles reuse `AdminConfiguration` (`kind=operational_profile`),
DRAFT/PUBLISHED lifecycle, explicit effective window, scoped inheritance and
governance/Project-Type applicability. Equal-priority competing policies fail
closed. Historical periods retain the exact configuration ID/revision/hash.

Common period commands enforce `OPEN → REVIEW → CLOSED → PUBLISHED`. Weekly,
biweekly, monthly and custom calendars have an explicit IANA timezone and an
offset-bearing cutoff; schedule data date remains independent. PUBLISHED is an
immutable **period header** only: no Cost/Schedule/Progress/Forecast/EVM source
bundle or full controls report is fabricated. Reopening creates a successor
revision with the original policy and preserves the prior publication.

`guard_legacy_operational_write` is the compatibility adapter for existing
material write routes. It requires a unique active binding, canonical Workspace
scope and current operational authorization before the legacy domain command.
It is not an O1B baseline policy and does not grant downstream authority.

This increment does not resume Strategic UAT sign-off or implement O1B/O1C.
