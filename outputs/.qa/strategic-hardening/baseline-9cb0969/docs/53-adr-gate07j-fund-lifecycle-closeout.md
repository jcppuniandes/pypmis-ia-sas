# ADR 53 — Gate 07J-FUND lifecycle release closeout

## Status

Accepted for the `20260827_0051` lifecycle and browser-E2E closeout. No database migration is required.

## Context

Gate 07J-FUND already persists governed Funding Sources, Funds, Funding Assignments and immutable Funding Readiness snapshots. The release closeout must distinguish durable business events from conditions that can be calculated without losing lineage or audit meaning.

## Decision

`KEEP_CURRENT`. Persist a state only when it changes allowed actions, Fund availability, readiness contribution or audit meaning. Present `EXHAUSTED` and `EXPIRED` as derived lifecycle labels while retaining the authoritative persisted state and historical record.

| Entity | State candidate | Decision | Rationale |
|---|---|---|---|
| Funding Source | `AUTHORIZED` | Keep current (`ACTIVE` implies authorization) | Activation is already the governed status transition. A second persisted state would not change actions, readiness or audit meaning. |
| Fund | `AUTHORIZED` | Keep persisted | Authorization is a Four-Eyes boundary distinct from activation and changes the actions available to the record. |
| Fund | `EXHAUSTED` | Derived | `available_amount = 0` is authoritative and automatically reverses after a release. Persisting it would create synchronization risk. |
| Fund | `SUPERSEDED` | Keep out of active workflow | Immutable configuration revisions, record history and `CLOSED` preserve replacement lineage without a new action. The schema value remains reserved for backward compatibility. |
| Funding Assignment | `RELEASED` | Keep persisted | A deliberate return of a previously effective allocation changes Fund availability and has different audit meaning from cancelling an unused allocation. |
| Funding Assignment | `EXPIRED` | Derived | Validity dates deterministically remove the allocation from current coverage while the persisted record remains visible. The readiness result becomes `EXPIRED` when expiry causes the required gap. |

## Lifecycle contracts

- Funding Source: `DRAFT → ACTIVE → SUSPENDED/CLOSED`.
- Fund: `DRAFT → AUTHORIZED → ACTIVE → SUSPENDED/CLOSED`.
- Assignment: `DRAFT → RESERVED/CONFIRMED → RELEASED`; `DRAFT/RESERVED → CANCELLED`.
- `RELEASED` remains immutable historical evidence and no longer consumes Fund availability or current coverage.
- An expired assignment remains historical, contributes zero current coverage, exposes an explicit warning and may produce `FundingReadiness = EXPIRED`.
- Child assignments explain parent distribution and always contribute zero to aggregate coverage.

## Consequences

The closeout needs no successor migration and does not rewrite `20260827_0051`. The UI may expose derived labels, but API calculations remain authoritative. Regression must prove transition validity, release/expiry impact, transactional over-allocation protection, idempotency, ETag, Four-Eyes, governed Gate 07J evidence and persistent-baseline restoration.

## Scope boundary

This decision does not introduce Treasury, Accounting, FX conversion, Commitments, Payments, Investment Decision/FID, Project Initialization or Project Activation.
