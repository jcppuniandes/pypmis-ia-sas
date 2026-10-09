# ADR 56 — Gate 07J-RISK governed Risk Readiness provider

## Status

Accepted — 2026-08-30. Release marker: `GATE07J_RISK_RELEASE_VALIDATED`.

## Context

The published Investment Decision Evidence Policy already classified `RISK_READINESS` as Class B, nonblocking and valid for 90 days in `PYP-INV-SELECT`, and as Class A, blocking, 100% coverage and valid for 90 days in `PYP-FFA`. Its provider registry reserved `RISK_READINESS_PROVIDER`, but no governed source existed. Gate 07J therefore had to reject manual substitution for the Class A requirement.

The repository did not contain a reusable Project Risk master or Risk Readiness assessment. It did contain reusable tenant/workspace scope, RBAC, `AdminConfiguration`, audit events, ETag, idempotency and Gate 07J evidence contracts.

## Decision

Implement one canonical `ProjectRisk` register and a separate versioned `RiskReadinessAssessment` aggregate.

- `ProjectRisk` owns identification, inherent scoring, treatment, residual scoring, acceptance and evidence references.
- `RiskReadinessAssessment` freezes the Project source hash, published configuration hash, calculated gaps, validity, readiness and evidence hash.
- Completed assessments are immutable. A changed risk or configuration makes derived evidence `STALE` until a governed reassessment is completed.
- Portfolio readiness aggregates the exact recommended Project Set from Gate 07I. It requires every Project to be `READY`, current and within validity; missing Projects are not averaged away.
- `RISK_READINESS_PROVIDER` now exposes `InvestmentGateRiskEvidenceOut` with source module `RISK_READINESS`, hashes, source-current flag, warnings, blockers and readiness.
- `PYP-FFA` keeps Class A, blocking, 100% coverage, 90-day validity and no manual fallback. `PYP-INV-SELECT` keeps Class B, nonblocking and 90-day validity.
- Configuration reuses `AdminConfiguration`; the starter remains DRAFT and requires explicit publish. Scope inheritance is tenant → enterprise → business unit → portfolio, with the nearest applicable published override winning.
- ETag and idempotency protect mutations; residual acceptance applies configured authority and separation of functions.

## Boundaries

This release does not implement enterprise ERM, Monte Carlo/QRA, contingency quantification, Permit Readiness, Investment Decision/FID, Project initialization, Project activation or execution.

## Consequences

Gate 07J can consume current governed risk evidence and can explicitly show `BLOCKED`, `STALE` or `EXPIRED` evidence. A Class A provider payload that exists but does not meet readiness is marked invalid, never valid, and never silently degraded to a manual Class B reference. The next unresolved provider remains context-dependent: Permit Readiness where the published policy makes it Class A; otherwise the evidence layer is ready for downstream Gate 07K design.
