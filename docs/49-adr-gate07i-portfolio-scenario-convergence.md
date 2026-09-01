# ADR 49 — Gate 07I Portfolio Scenario Convergence & Recommendation

## Status

Accepted — 2026-08-26.

## Context

Gate 07G and Gate 07H independently produce governed, frozen and current budget and resource scenarios. Portfolio decision makers need to compare compatible pairings without reopening either source engine, inventing a third selection state or confusing a recommendation with investment approval.

## Decision

Introduce a tenant-scoped `PortfolioScenarioConvergence` aggregate and immutable `PortfolioConvergedAlternative` snapshots.

- Gate 07I consumes only the public recommendation contracts of Gate 07G and Gate 07H.
- A published `portfolio_convergence_configuration` resolves required branches. At least one branch is mandatory; both are required by default.
- Shared Gate 07F analysis, membership and evaluation hashes must be compatible.
- Each alternative references eligible frozen source scenario IDs and hashes. Project inclusion and forced-state ownership remain with the source branches.
- Alignment, forced conflicts and combined feasibility are derived decision support. Gate 07I does not mutate source scenarios and does not optimize or choose a winner.
- Lifecycle is `DRAFT → IN_REVIEW → RECOMMENDED`, with controlled return to `DRAFT`, void and clone-to-new-revision actions.
- `RECOMMENDED` revisions and their alternatives are immutable. ETag/`If-Match`, idempotency keys, source hashes and `SecurityEvent` records protect concurrency and traceability.
- The exclusive ready output is `READY_FOR_INVESTMENT_GATE_PREPARATION`. Every response keeps `can_enter_fid=false`.
- USER MODE exposes Overview, Alternatives, Comparison, Recommendation and History. ADMIN MODE configures policies and provides non-persistent preview only.

## Consequences

The portfolio obtains a reproducible recommendation handoff that preserves independent budget/resource evidence and explicitly blocks stale, misaligned or forced-conflict alternatives. A future Investment Gate may consume the contract but must implement its own authority, evidence and approval workflow.

The design intentionally excludes Funds, funding commitments, FEL/PDRI decisions, FID, project initialization, activation, execution, named-resource allocation and schedule leveling.

## Rejected alternatives

- Reopening or editing Gate 07G/07H scenarios from Gate 07I.
- Creating a third project selection state owned by convergence.
- Auto-selecting a recommended alternative through an optimizer or AI.
- Treating recommendation as investment approval or FID authority.
