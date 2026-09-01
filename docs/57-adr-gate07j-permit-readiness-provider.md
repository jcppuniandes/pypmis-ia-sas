# ADR 57 — Gate 07J-PERMIT governed Permit Readiness provider

## Status

Accepted — 2026-08-31.

## Context

The published Investment Decision Evidence Policy already classifies Permit Readiness as controlled Class B evidence for the standard selection and FFA profiles. It also contains a contextual, configuration-driven override that elevates Mining projects under `PYP-FFA` to Class A. Before this change, `PERMIT_READINESS_PROVIDER` was reserved and unavailable, leaving the last declared Class A provider gap.

The implementation must not become a regulatory interpretation engine, a government filing integration, a GIS/environmental compliance engine, an Investment Decision, FID, or Project activation mechanism.

## Decision

Implement a tenant-scoped Permit Readiness bounded context with three additive records:

- `ProjectPermit`: the controlled Project permit register, lifecycle, dates, authority references, evidence and renewal lineage;
- `PermitCondition`: normalized conditions used for explicit blocking and audit-safe concurrency;
- `PermitReadinessAssessment`: versioned, immutable completed snapshots with source/configuration hashes.

Permit applicability comes exclusively from versioned `AdminConfiguration` content. The starter configuration contains an illustrative Mining FFA requirement set but remains `DRAFT`; nothing is auto-published and no code infers legal obligations from the word “Mining”. Effective classification continues to come from the existing Investment Decision Evidence Policy.

The provider registry entry `PERMIT_READINESS_PROVIDER` is now `AVAILABLE`, reports source module `PERMIT_READINESS`, and supplies the common governed evidence contract at Project and Project Set scopes. Only contextual Class A projects enter the Project Set denominator. Class B behavior, manual validation rules and every Gate 07J-RISK behavior remain unchanged.

## Governance and safeguards

- Tenant and workspace scope are enforced through the shared permission context.
- Create/status/complete/refresh commands are idempotent.
- Mutable records use ETag/revision checks.
- Published configurations and completed assessments are immutable.
- Readiness becomes stale when any configured source component changes and expires at the earliest assessment or permit validity boundary.
- Blocking conditions are normalized and counted per permit; non-blocking conditions remain visible without silently becoming blockers.
- Provider output always reports `can_enter_fid=false`.

## Consequences

The Gate 07J provider gap analysis can now return `READY_TO_DESIGN_GATE07K` when all other Class A sources are present. This status authorizes only a future design step; this ADR does not implement Gate 07K or grant investment authority.

The migration `20260831_0054` is additive and reverses cleanly to `20260830_0053`. Existing Project, portfolio, risk, funds, evidence policy and preparation records are not rewritten.
