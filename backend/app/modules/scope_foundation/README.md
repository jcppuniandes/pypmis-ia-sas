# O1B A Scope foundation

The Project identity remains `enterprise_workspaces` of type PROJECT. Scope is
the authority for deliverables and controlled quantities. IFC and Excel are
immutable sources, not approved Scope. Legacy takeoff/APU records remain intact.

## Explicit deployment

Back up and review the intended database before the additive Alembic upgrade.
Revision `20261020_0070` follows O1A `20261019_0069` and creates twelve Scope tables,
not another Project master. It never backfills Project 14 or invents bindings.
Downgrade refuses to delete populated Scope history. The historical repository
requires its initial ORM schema before the Alembic chain; the isolated validation
proves the additive successor, not an empty-database-to-head initialization.

An existing organization administrator explicitly provisions the catalog:

```powershell
python -m app.modules.scope_foundation.provision --tenant-id VERIFIED_ID --actor-id VERIFIED_ADMIN_ID --reason "Approved Scope rollout"
```

Replace the placeholders with verified numeric identities. The command grants
no actor assignments or Project authority. Reads never provision security data.
Use existing Organization and Security administration for scoped assignments.
Operational and Scope profiles must be separately published by authorized actors.

## Source and approval boundaries

API prefix `/api/v1/scope` addresses canonical `/projects/{workspace_id}` only.
Source uploads create staging versions with original bytes/hash and validation.
An IFC version moves STAGED to REVIEW to ACCEPTED, or is rejected; GUID is stable
source identity and ExpressID remains version-local. Excel is valid without IFC.
Mappings between BIM objects, Scope Items and Plan Items are explicit M:N links.

Scope Items support INSTALL, REMOVE, TEMPORARY and MAINTENANCE. Source quantity,
controlled quantity and approved quantity are distinct. Known units and explicit
IFC quantity selection prevent silent conversion; draft edits retain source
lineage. Approved Scope uses immutable baseline snapshots and successor revisions.
The Approved Change contract reads an existing approved legacy source only after
an explicit canonical binding; no new Change approval authority is introduced.

Execution paths and segmentation generate candidate Plan Items, never activities.
Group, split and recompose conserve allocation by Scope Item and unit. Logical
derived subsets retain source versions/GUIDs and Scope/Plan membership. They do
not cut or overwrite the original IFC. Physical geometry fragments, Schedule,
P6/CPM, Cost authority, full Progress and a 4D timeline remain outside this increment.

## Security and verification

Material commands reuse current O1A authorization and published profiles, granular
Scope duties, If-Match, immutable idempotency receipts and audit events. Default
SoD separates model import/acceptance, baseline preparation/approval, strategy
editing/publication and Plan publication. Generic configuration mutation routes
cannot bypass the dedicated Scope Profile API. PostgreSQL guards protect tenant,
canonical Project references, original source and published history.

Use `docker-compose.wave-o1ba.yml` for isolated tests on API8852/frontend5512,
separate migration and regression databases. The normal runtime database and
Project14 are not test fixtures. See the validation package for actual outcomes;
this README alone is not release evidence or business signoff.
