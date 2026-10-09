# ADR 51 — Gate 07J-FEL Project Definition / FEL Manager

## Status

Accepted for the additive `20260826_0050` release.

## Context

Investment Gate Preparation already defines evidence requirements for FEL and definition maturity, but deliberately does not calculate those results. A governed source is required without turning FEL into a universal Project Creation prerequisite or mixing it with investment approval.

## Decision

Implement a tenant-scoped Project Definition / FEL capability over canonical `EnterpriseWorkspace` records of type `PROJECT`. Reuse `AdminConfiguration` for versioned frameworks, RBAC, `SecurityEvent`, ETag/If-Match and idempotency. Persist only FEL status, immutable assessment revisions and definition-gap actions.

Framework types are `CUSTOM`, `PDRI_COMPATIBLE` and `FEL_INDEX_COMPATIBLE`. Score direction, thresholds, maturity levels, elements and stages are configuration-owned and version-specific. No proprietary CII PDRI or IPA FEL Index content is distributed by the product.

Gate 07J consumes the read-only governed `PROJECT_DEFINITION_FEL` contract. It does not recalculate scores or silently replace unavailable evidence with a manual reference.

## Invariants

- FEL Stage and Definition Maturity are independent dimensions.
- PDRI-compatible and FEL-index-compatible frameworks never share global thresholds.
- `CAPITAL_OWNER` is the default applicability; Contractor Delivery and Direct Internal remain optional.
- Completed assessments are immutable; reevaluation creates a new version.
- Stage completion is not Investment Approval, FID, Project Initialization, Activation or Execution.
- Funding remains a separate evidence source.

## Consequences

The platform can now provide versioned Project Definition Readiness evidence to Gate 07J while preserving history, source hashes, segregation of duties and configuration inheritance. Future engineering, estimate, schedule, risk, permits and BIM sources may be integrated through governed references without extending this module into their operational domains.
