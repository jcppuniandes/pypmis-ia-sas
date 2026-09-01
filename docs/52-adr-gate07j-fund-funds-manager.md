# ADR 52 — Gate 07J-FUND Funds Manager

## Status

Accepted for the additive `20260827_0051` release.

## Context

Investment Gate Preparation can require governed `FUNDING_READINESS` evidence, but it deliberately does not calculate funding coverage. The existing `funding_sources` table belongs to the Project/FBS cost-control context and does not represent strategic capital origins, Funds or governed Portfolio assignments.

## Decision

Implement a tenant-scoped Funds Manager with the canonical hierarchy `Funding Source → Fund → Funding Assignment`. Preserve the existing Project/FBS model and use `strategic_funding_sources` for the strategic bounded context. Reuse `AdminConfiguration`, workspace inheritance, RBAC, `SecurityEvent`, ETag/If-Match, idempotency and the governed Gate 07G/07I source contracts.

Readiness derives confirmed and reserved coverage without recalculating Budget demand. It records immutable snapshots and hashes, detects stale sources, evaluates common-currency comparability, period/project coverage, restrictions, conditions and expiry, and supplies the read-only `FUNDING_READINESS` evidence contract to Gate 07J.

## Invariants

- Budget is not Funding, and Funding availability is not Investment Approval.
- Funds Manager is strategic capital governance, not Treasury, Accounting, Commitments or payment execution.
- `CAPITAL_OWNER` is applicable by default; Contractor Delivery and Direct Internal remain optional by policy.
- Child assignments explain distribution and never double-count their parent in aggregate coverage.
- No silent FX calculation is performed; only same-currency or externally governed normalized amounts are comparable.
- Funding Readiness and Project Definition/FEL remain independent Gate 07J evidence providers.
- The module stops at `READY_FOR_GOVERNED_FUNDING_EVIDENCE`; it cannot perform FID, Project initialization, activation or execution.

## Consequences

P&Pmis can now govern funding origins, envelopes, availability and assignments, produce current and auditable Funding Readiness, and let Gate 07J consume that evidence without duplicating business logic. The separation from the legacy FBS catalog avoids implicit cross-domain joins and keeps future Treasury or Commitment capabilities outside this release.
