# ADR 44 — Project governance model and multi-source Project creation

- Status: Accepted
- Date: 2026-08-20
- Release readiness: `READY_FOR_MULTI_SOURCE_PROJECT_CREATION`
- Scope: Project creation foundation only

## Context

P&Pmis already had one canonical `PROJECT` workspace, the Gate 05B
`ProjectCreationRequest` lifecycle, Gate 05C initialization/activation, and the
Gate 07D strategic planning entry. Projects must now also be created from an
awarded contract or a direct internal authorization without duplicating the
Project entity, creator, numbering, approval, materialization, or navigation
engines.

The governance model is independent from `project_type`. It describes why and
under which controls the Project is created; `project_type` remains an optional
business classification.

## Decision

Keep `enterprise_workspaces` with `workspace_type_code=project` as the only
canonical Project identity and extend `project_creation_requests` additively.
All sources pass through the existing Four-eyes state machine and the same
idempotent materializer.

| Governance model | Source context | Entry route | Default readiness |
| --- | --- | --- | --- |
| `CAPITAL_OWNER` | `STRATEGIC_GATE_DECISION` | Gate 07D Strategic Project Planning Entry | Portfolio/FEL planning required |
| `CONTRACTOR_DELIVERY` | `CONTRACT_AWARD` | Shared Create Project workspace | Initialization and mobilization required |
| `DIRECT_INTERNAL` | `DIRECT_AUTHORIZATION` | Shared Create Project workspace | Initialization and authorization required |

Each request stores a normalized immutable lineage fingerprint, source
snapshot/hash, and the exact governance-policy identifier/revision/hash used
for validation. Policies are published `AdminConfiguration` records resolved
tenant-first with optional workspace inheritance. Preview operations are
non-persistent.

## Invariants

1. A source cannot create more than one active Project request in a tenant.
2. A Project Number is reserved only during materialization and is never reused.
3. Every materialized Project starts `pending`.
4. The requestor cannot perform the approval step; reviewer and approver remain
   separate controls.
5. Tenant filters are mandatory on request, source, policy, and workspace reads.
6. Legacy requests remain readable and are not reclassified. Only existing
   Gate 07D strategic requests are deterministically backfilled as
   `CAPITAL_OWNER`.
7. Workspace Type PROJECT classification ID 14 is not mutated by this release.

## API contract

- `GET /api/v1/project-creation/options`
- `POST /api/v1/project-creation/from-contract/preview`
- `POST /api/v1/project-creation/from-contract`
- `POST /api/v1/project-creation/direct/preview`
- `POST /api/v1/project-creation/direct`
- Existing `/api/v1/project-creation-requests/*` lifecycle routes
- `PUT /api/v1/admin-configuration/enterprise-structure/project-governance-models/{model}`
- `POST /api/v1/admin-configuration/enterprise-structure/project-governance-models/preview`

The specialized endpoints are adapters. They do not introduce a second
creation service.

## Data and migration

Alembic revision `20260820_0044` adds governance/source/policy lineage columns,
tenant-scoped partial unique indexes, and the policy foreign key. It upgrades
from `20260820_0043` and downgrades cleanly to that revision. PostgreSQL
validation checks both schema states and an upgrade/downgrade/upgrade cycle.

## Security and audit

RBAC adds read/configure/publish governance-policy permissions and separate
source-create permissions for contract/direct entry. Organization administrators
retain tenant-wide authority through the existing permission seed. Creation,
source validation, model selection, submission, review, approval, and
materialization emit security events with request lineage.

## Consequences

- USER MODE renders one dynamic form rather than three applications.
- ADMIN MODE manages three versioned governance-policy variants alongside the
  existing Gate 05B creation policy.
- Gate 05C evaluates source-specific activation authorization without requiring
  strategic objectives for contract/direct Projects.
- Gate 07D remains the sole Capital Owner entry path and its regression suite is
  preserved.

## Explicitly deferred

Gate 07E, FEL, PDRI, FID, contract management, procurement, execution modules,
and operational integrations are outside this decision.
