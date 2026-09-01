# ADR 46 — Gate 07F Portfolio Analysis as a derived, governed read model

- Status: Accepted
- Date: 2026-08-25
- Decision gate: Gate 07F — Portfolio Analysis / Investor Map / Scorecard

## Context

Gate 07E already owns immutable Project evaluations, contextual Portfolio ranking and the
`READY_FOR_PORTFOLIO_ANALYSIS` hand-off. Gate 07F must compare eligible CAPITAL_OWNER Projects without becoming a
second source of ranking, membership, evaluation, budget, resource or investment-decision truth.

## Decision

Portfolio Analysis is derived on demand from the current active Portfolio membership and the latest completed Gate
07E evaluation for each eligible Project. The dataset reuses `PortfolioEvaluationService.ranking_projection`; it does
not recalculate or persist a parallel rank.

The controlled `AdminConfiguration` aggregate is reused for the Metric Catalog, Investor Map, Scorecard, filters,
buckets, reference lines and readiness rules. The starter configuration is created as DRAFT and requires explicit
publication. Effective configuration follows the existing Tenant → Enterprise → Business Unit → Portfolio inheritance
path and uses optimistic concurrency through ETags.

No Gate 07F snapshot table or migration is introduced. Dataset identity is expressed through deterministic hashes of
the membership set, completed evaluations, Gate 07E prioritization and effective Gate 07F configuration. Preview is
non-persistent. A stale expected analysis hash is rejected with HTTP 412.

Investor Map and Scorecard are two projections of the same derived dataset. Multi-currency ROM values are never
aggregated or used as bubble size unless normalized; this condition blocks only the budget-planning readiness branch.
Resource-planning and Portfolio Scenario Planning readiness remain independently evaluated.

## Consequences

- Gate 07F remains auditable without duplicating upstream truth.
- Filters and drilldowns cannot mutate membership, evaluation or prioritization data.
- The accessible Scorecard is the semantic alternative to the visual Investor Map.
- The only successful Gate 07F hand-off is `READY_FOR_PORTFOLIO_SCENARIO_PLANNING`; otherwise the result is
  `GATE07F_REWORK_REQUIRED`.
- Budget allocation, resource allocation, scenario optimization, Project selection, FID and FEL remain out of scope.

## Validation

Validation is performed with backend unit tests, an ephemeral PostgreSQL acceptance suite, frontend component tests,
Playwright USER/ADMIN flows and the existing full regression pipeline. PostgreSQL validation explicitly verifies the
absence of a Portfolio Analysis snapshot table and the stability of derived hashes.
