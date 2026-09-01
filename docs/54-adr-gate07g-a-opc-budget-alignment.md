# ADR 54 — Gate 07G-A OPC-inspired Budget Alignment enhancements

- Status: Accepted
- Date: 2026-08-30
- Decision gate: Gate 07G-A — Waterline, Project Dependencies and CAPEX/EXPENSE

## Context

Gate 07G already owns Budget Targets, immutable Scenario snapshots, selection states, time phasing, comparison and the
`READY_FOR_PORTFOLIO_BUDGET_RECOMMENDATION` hand-off. Gate 07E owns contextual rank. No reusable Project-to-Project
strategic dependency aggregate exists in the repository. The enhancement must close selected OPC capability gaps
without cloning either engine, introducing approval semantics or mutating historical scenarios.

## Decision

Extend the existing Gate 07G module additively.

- Waterline is a derived projection of the persisted Gate 07E rank snapshot, Gate 07G selection state, Project demand
  and Budget Target. It never persists cumulative values or a second rank.
- `ProjectDependency` is the only new transverse aggregate. Direction is explicit:
  `predecessor_project_workspace_id -> successor_project_workspace_id`, meaning the successor depends on the
  predecessor. Active mandatory chains are acyclic, tenant-scoped and reusable by downstream portfolio modules.
- Unmet, forced-conflict and transitive dependency states are derived in bulk for a Scenario. They are not persisted as
  parallel Scenario rows. `BLOCK_FREEZE` is the default policy for unresolved mandatory dependencies; optional
  dependencies remain warnings.
- CAPEX and EXPENSE are nullable governed breakdown values on the existing Scenario Project snapshot. The residual is
  explicit `UNCLASSIFIED`; an unknown ROM split is never fabricated. Optional CAPEX/EXPENSE targets and period targets
  extend the existing Budget Target aggregates.
- Existing Scenario rows are migrated as CAPEX/EXPENSE unknown and their full historical demand is represented as
  UNCLASSIFIED. Existing lifecycle states and selection semantics remain unchanged.
- AdminConfiguration remains the policy authority for Waterline presentation, dependency behavior and breakdown
  visibility. Preview remains `persisted=false`.

## Consequences

- Migration `20260830_0052` is additive and reversible from the current `20260827_0051` head.
- Historical Gate 07G scenarios remain readable and hashes remain deterministic.
- Scenario comparison gains breakdown and dependency metrics without selecting a winner.
- Gate 07H and Gate 07I may consume the single dependency projection read-only; neither receives a second graph engine
  or automatic selection behavior.
- Funds Manager remains the funding source of truth and can consume breakdown fields additively without new
  restriction semantics in this gate.

## Guardrails

No optimizer, automatic predecessor selection, automatic forced-state changes, Budget approval, Investment approval,
FID, GO/HOLD/RECYCLE/KILL, Project Activation, accounting classification, actuals, commitments or Project Cost Control
is introduced.

## Validation

Validation covers Waterline ordering and cumulative demand, forced-state visibility, over-budget state, accessible
table contract, mandatory/optional/transitive dependency evaluation, self/cross-tenant/duplicate/cycle rejection,
CAPEX/EXPENSE/UNCLASSIFIED arithmetic, target and period breakdown, ETag, idempotency, RBAC, SecurityEvent, migration
up/down/up, Gate 07G-07J regression, frontend component tests, Browser USER/ADMIN flows and persistent-baseline
restoration.
