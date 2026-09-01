# ADR 47 — Gate 07G Portfolio Budget Planning and Budget Scenarios

- Status: accepted
- Date: 2026-08-25
- Scope: USER MODE and ADMIN MODE / Enterprise Strategy Manager / Portfolio Manager

## Context

Gate 07F produces a current, deterministic Portfolio Analysis contract. The Budget branch must consume that contract independently from future Resource Planning and must not turn analytical alternatives into funding, approval, FID, activation or execution decisions.

## Decision

Implement Gate 07G as a governed write model with four tenant-scoped tables:

- `portfolio_budget_targets`: revisioned Target Budget headers with DRAFT, PUBLISHED and SUPERSEDED lifecycle.
- `portfolio_budget_target_periods`: optional YEAR, QUARTER or MONTH period targets whose sum is controlled against the total.
- `portfolio_budget_scenarios`: revisioned alternative combinations with DRAFT, IN_REVIEW, FROZEN, SUPERSEDED and VOIDED lifecycle.
- `portfolio_budget_scenario_projects`: immutable source snapshots plus SELECTED, UNSELECTED, FORCED_IN and FORCED_OUT state.

The module consumes `READY_FOR_PORTFOLIO_SCENARIO_PLANNING` only when `can_enter_budget_planning=true`. It accepts CAPITAL_OWNER Projects, preserves Gate 07E rank and Gate 07F metrics as read-only source facts, and stores source hashes so later changes mark scenarios STALE rather than silently rewriting history.

### Governance controls

- A single governed Budget Currency is mandatory; Gate 07G performs no implicit FX conversion.
- Initial cost source is the Gate 07F ROM Cost snapshot and its hash.
- Time phasing is explicit: UNPHASED, LINEAR_BY_PROJECT_DATES or CUSTOM_PERIOD_PROFILE.
- Linear spreading is labelled as an approximation and never represented as Project Cash Flow.
- Forced states require a reason and emit dedicated SecurityEvents with actor and optional authority reference.
- Published Targets and FROZEN/SUPERSEDED/VOIDED Scenarios are immutable.
- Mutations require tenant-scoped idempotency keys and optimistic concurrency through `If-Match` / ETag.
- Comparison is analytical and exposes scenario summary, Project-level matrix and pairwise deltas.
- Readiness produces `READY_FOR_PORTFOLIO_BUDGET_RECOMMENDATION` when at least one current FROZEN scenario is ready.

### Administration

Configuration reuses `AdminConfiguration` with kind `portfolio_budget_configuration`. Tenant, enterprise and Portfolio scopes use the existing workspace inheritance chain. ADMIN MODE supports clone, structured editing, non-persistent preview, save and publish. Publishing never creates a Target or Scenario.

### Explicit boundaries

Gate 07G does not create or decide:

- Resource histograms, allocation, leveling or Resource Scenarios;
- funding sources, Funds assignment or cash availability;
- recommended/winning Scenario selection;
- investment approval, FID, FEL transition, Project initialization, activation or execution;
- operational Project Cash Flow.

## Consequences

Budget alternatives become reproducible, comparable and auditable without duplicating Gate 07E/07F facts. Future convergence can consume frozen scenario references and hashes, but must implement its own authority and decision workflow. The additive Alembic revision `20260825_0046` can be downgraded to `20260820_0045` without altering prior Gate records.

## Verification evidence

- service acceptance tests cover happy path, over-budget analysis, currency guardrail, forced reason, explicit refresh, frozen immutability, inheritance, ETag and downstream boundary rejection;
- real PostgreSQL validates schema, constraints, idempotency, audit events and the 0046 → 0045 → 0046 migration cycle;
- React tests cover USER comparison and ADMIN non-persistent Preview;
- Playwright covers Target publication, two Scenario alternatives, forced selection, freezing, comparison, final readiness and ADMIN clone/preview/save/publish;
- the production frontend build and local Docker stack run at Alembic head `20260825_0046`.
