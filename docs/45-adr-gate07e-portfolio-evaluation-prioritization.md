# ADR 45 — Gate 07E Portfolio Evaluation and Prioritization

- Status: Accepted
- Date: 2026-08-20
- Release readiness: `READY_FOR_PORTFOLIO_ANALYSIS`
- Scope: USER MODE Portfolio Manager, ADMIN MODE Enterprise Strategy Manager, Project Workspace context

## Context

Gate 07D already creates the canonical Project Workspace, links it to one or more Portfolios through
`portfolio_project_memberships`, and emits `READY_FOR_PORTFOLIO_PLANNING`. Gate 07E must evaluate and
prioritize those Projects without introducing a candidate identity, replacing the Project, or granting an
investment or execution decision.

The evaluation policy must vary by organization and Portfolio, retain historical evidence, and produce a
deterministic contextual ranking. A Project may therefore have different valid positions in different
Portfolios at the same time.

## Decision

1. `enterprise_workspaces` with `workspace_type_code=project` remains the canonical Project identity.
2. The evaluation unit is the tuple Portfolio + Project + active Portfolio membership. No
   `PortfolioCandidate` or global ranking model is introduced.
3. Gate 07E accepts only `CAPITAL_OWNER` Projects that are `READY_FOR_PORTFOLIO_PLANNING` and have an
   active membership in the selected Portfolio. Contractor Delivery, Direct Internal, and unclassified
   legacy Projects are excluded.
4. A versioned `portfolio_project_evaluations` record stores configuration, source, planning, rating,
   score-component, and hash snapshots. `COMPLETED` evaluations are immutable; reevaluation creates a new
   version and supersedes the prior completed version.
5. Evaluation matrices reuse `AdminConfiguration` with nearest published inheritance in the order
   Portfolio → Business Unit → Enterprise → Tenant. The P&P starter matrix is created only as `DRAFT` and
   is never auto-published.
6. The score is deterministic. Contextual ordering uses normalized score, strategic alignment, lower risk,
   earlier planned completion, and Project number. Ranking is calculated per Portfolio and is not persisted
   as a second source of truth.
7. Portfolio readiness is derived from eligible active memberships and completed current evaluations. Any
   in-progress or blocked Project prevents the Portfolio from entering analysis.
8. The exclusive successful output is `READY_FOR_PORTFOLIO_ANALYSIS`; it is a Gate 07F handoff contract,
   not `READY_FOR_INVESTMENT`, `READY_FOR_FID`, initialization, activation, or execution authorization.

## Controls

- Tenant and Portfolio scoping apply to every query and write.
- Dedicated RBAC permissions separate evaluation, completion, reevaluation, ranking, configuration, and
  publication authority.
- `If-Match` protects mutable evaluations and configurations; start, complete, and reevaluation commands
  use independent idempotency keys.
- Security events record configuration governance, evaluation lifecycle, rank computation, readiness, and
  blocked governance attempts with source and configuration hashes.
- Migration `20260820_0045` is additive and supports upgrade, downgrade to `20260820_0044`, and re-upgrade.

## Consequences

- USER MODE exposes evaluation queues, evidence-based scoring, contextual Prioritization Matrix, Project
  evaluation history, and a read-only readiness contract.
- ADMIN MODE governs matrix criteria, scale, evidence requirements, inheritance, validation, preview,
  publication, permissions, and audit without duplicating the Enterprise configuration engine.
- Inactive memberships disappear from the current ranking but their completed evaluation history remains
  auditable.
- Gate 07A, 07B, 07C, 07D, Project creation, Gate 05C, workspace context, and Enterprise Explorer retain
  their existing ownership boundaries.

## Explicitly deferred

Gate 07F analysis, budget allocation, resource optimization, FID, investment authorization, Project
initialization, activation, execution, benefits realization, and manual ranking overrides are outside this
decision.
