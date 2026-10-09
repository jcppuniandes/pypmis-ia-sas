# ADR 62 — Gate 07M-EVID Business Case and Economic/Financial evidence policy update

- Status: Accepted
- Date: 2026-09-03
- Release state: `GATE07M_EVID_POLICY_UPDATE_VALIDATED`
- Output: `READY_FOR_BUSINESS_CASE_AND_ECONOMIC_FINANCIAL_GATE_EVIDENCE`

## Context

Gate 07J-EVID already owns the contextual A/B/C evidence policy, while Gate 07M-BC owns governed Business Case revisions and Gate 07M-FIN owns economic-financial model versions and readiness. The update must connect those authoritative domains without introducing another readiness engine, duplicating data, or reinterpreting historical Gate 07J preparations and Gate 07K decisions.

## Decision

The existing `investment_evidence_policy` `AdminConfiguration` aggregate is extended in place. No new table or migration is introduced; Alembic head remains `20260902_0058`.

Two evidence types and providers are registered:

| Evidence type | Provider | Source owner | Contract |
|---|---|---|---|
| `BUSINESS_CASE_READINESS` | `BUSINESS_CASE_READINESS_PROVIDER` | Gate 07M-BC Business Case Manager | Adapter over current completed Business Case revision/readiness |
| `ECONOMIC_FINANCIAL_READINESS` | `ECONOMIC_FINANCIAL_READINESS_PROVIDER` | Gate 07M-FIN Economic-Financial Model | Existing `ProviderEvidenceOut` |

The base policy for `CAPITAL_OWNER` is:

| Gate profile | Business Case | Economic / Financial |
|---|---|---|
| `PYP-INV-SELECT` | Class A, blocking, 100% project coverage | Class B, non-blocking, 100% when evaluated |
| `PYP-FFA` | Class A, blocking, 100% project coverage | Class A, blocking, 100% project coverage |

Project-type resolution for `PYP-FFA` is contextual:

- Commercial/revenue: financial readiness is applicable.
- Public/non-revenue: economic readiness is applicable; commercial metrics may remain not applicable.
- Mixed: both economic and financial dimensions apply.
- Internal/compliance: FIN resolves to Class C unless a future published configuration explicitly enables it.
- `CONTRACTOR_DELIVERY` and `DIRECT_INTERNAL` are outside the base `CAPITAL_OWNER` policy and therefore are not forced.

Class A never degrades to Class B when a provider is missing, invalid, blocked, stale, expired, incomplete, or below the required coverage. The Business Case adapter additionally compares its frozen FIN reference hash with the current FIN provider hash and reports `BUSINESS_CASE_FIN_REFERENCE_STALE`; it never silently relinks the Business Case.

## Versioning and historical compatibility

Policy changes use the existing clone → draft → preview → publish lifecycle with ETag checks, idempotent publication, audit events, and `effective_from`. A future-dated revision does not supersede the currently effective revision.

Every new Gate 07J preparation snapshots the effective policy id, revision, hash, matrix, project context, and provider registry. An existing editable preparation changes policy only through an explicit refresh preview/apply action. Frozen preparations and Gate 07K decision packages continue to use their stored snapshots and hashes.

Gate 07J handoff now contains separate frozen `business_case_summary` and `economic_financial_summary` collections, including evidence item ids, source record ids, source hashes, statuses, provider payloads, warnings, blockers, and a deterministic summary hash. Gate 07K already freezes the complete Gate 07J handoff and source snapshot in its decision package, so no Gate 07K schema or lifecycle redesign is required.

## UI and access

The existing ADMIN Investment Decision Evidence Policy screen displays both rows in the matrix, provider availability/contract status/last validation, project-type and governance-model preview controls, effective date, coverage, and source readiness/currentness. The USER Gate 07J evidence package displays Business Case and Economic/Financial rows separately with read-only source drilldowns.

Existing tenant/workspace RBAC and separation-of-duties controls remain authoritative. This update does not add approval, investment decision, FID, fund movement, project activation, or operational execution authority.

## Consequences

- Positive: one evidence policy engine, authoritative source lineage, deterministic stale detection, preserved audit history, and zero schema growth for the integration.
- Trade-off: existing editable preparations require a deliberate refresh to adopt a newer effective policy.
- Rejected: duplicating Business Case or FIN calculations in Gate 07J, automatic relinking, backdated publication, automatic historical reinterpretation, and Class A manual fallback.

## Validation closeout

Validation covers policy/provider contracts, default and contextual matrices, stale BC↔FIN linkage, explicit refresh semantics, immutable published history, Gate 07J handoff, 1,000-project matrix resolution, PostgreSQL reuse at migration head `0058`, ADMIN/USER browser flows, frontend production build, lint, and regression tests.

`NEXT = READY_TO_REVALIDATE_NEW_FID_PATH`

`STOP`
