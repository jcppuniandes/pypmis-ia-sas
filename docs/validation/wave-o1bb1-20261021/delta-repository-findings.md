# O1B B1 delta and authority boundaries

The baseline is the already implemented uncommitted O1B B Schedule increment.
The implementation preserves earlier work and does not create a commit or push.

| Existing capability | Treatment in B1 | Authority retained |
| --- | --- | --- |
| Canonical Project Workspace and O1A authorization | Reused with tenant and Workspace scope | Enterprise and Operational Context |
| Idempotent commands and audit receipts | Reused for versioned AWP and configuration writes | Operational command infrastructure |
| Accepted IFC source and BIM objects | Read as immutable bytes and identities | Scope Foundation |
| Approved Scope Baseline and published Plan Items | Referenced by many to many package mappings | Scope Foundation |
| Derived 3D logical subsets | Reused by source qualified 4D projections | Scope Foundation |
| Schedule Register and accepted versions | Referenced without rewriting snapshots | Schedule Foundation |
| Approved Schedule Baselines | Read frozen snapshots and mappings | Schedule Foundation |
| Existing P6 constraint payloads | Preserved separately from execution constraints | Imported Schedule source |
| Legacy WorkPackage and work package constraints | Preserved behind compatibility routes, not promoted to canonical AWP | Existing legacy project workflows |
| Existing web ifc and Three.js geometry stack | Reused in a transient source adapter and Y up renderer | Original IFC remains the geometry source |
| ADMIN configuration | Dedicated awp_profile and four_d_profile publication with generic bypass guards | Existing configuration aggregate |

Eight additive tables store CWA, Work Packages, mappings, dependencies, execution
constraints, constraint mappings, readiness assessments and append only history.
There is no additional 4D master or source table. Configuration and read models
cannot alter source IFC, Scope quantities, Schedule snapshots or P6 CPM logic.

App.tsx, BimIfcModelViewer.tsx and the global domain model and schema files retain
their baseline SHA256 hashes. The normal application database was observed read
only. All writable fixtures and migration cycles used dedicated B1 databases.

The new CI workflow is saved but was not run remotely. Local PostgreSQL, real
Chromium, component, lint, type and document checks are recorded separately.
GitHub execution awaits a later authorized commit and push.
