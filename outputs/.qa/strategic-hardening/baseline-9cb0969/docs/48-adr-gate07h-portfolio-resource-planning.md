# ADR 48 — Gate 07H Portfolio Resource Planning and Scenarios

- Status: Accepted
- Date: 2026-08-25
- Scope: `CAPITAL_OWNER` strategic portfolio planning

## Context

Gate 07F produces the controlled analysis contract `READY_FOR_PORTFOLIO_SCENARIO_PLANNING` with independent permissions to enter budget and resource planning. Gate 07H must model strategic capacity and project demand without allocating named people, performing schedule leveling, selecting a winning scenario, approving investment, or creating Funds/FID state.

## Decision

Implement Gate 07H as an additive sibling of Gate 07G. It consumes Gate 07F directly and never reads or mutates Gate 07G records. Strategic Resource Roles remain configuration-owned catalog entries; operational records store immutable role/period snapshots with an explicit unit (`FTE`, `HOURS`, or `CREW_EQUIVALENT`). No implicit conversion is permitted.

The domain uses six tenant-scoped PostgreSQL tables: capacity plan/revision and periods, demand profile/revision and periods, resource scenario/revision and project snapshot rows. Published capacity and demand revisions and frozen scenarios are immutable. Scenario edits support explicit selection state and project date shifts while preserving source project dates. Hashes, ETags, idempotency keys, audit events, staleness preview/apply, readiness, overload policy, and comparison deltas govern the lifecycle.

The USER workspace exposes Overview, Capacity Plans, Project Resource Demand, Resource Scenarios, and Scenario Comparison. The ADMIN workspace governs roles, units, source hierarchy, timing, overload, constraints, readiness, inheritance, permissions, and a non-persistent preview.

## Consequences

- Gate 07H can reach `READY_FOR_PORTFOLIO_RESOURCE_RECOMMENDATION` only from a ready frozen scenario with governed capacity and required demand coverage.
- Overload is visible and governed; it is never hidden or silently optimized.
- Budget and resource scenarios can evolve independently and converge only through an explicit downstream contract.
- Migration `20260825_0047` is additive and reversible to `20260825_0046`.
- Named-person assignment, CPM recalculation, schedule leveling, optimization, Funds, FEL approval, scenario winner, investment approval, and FID remain outside this gate.
