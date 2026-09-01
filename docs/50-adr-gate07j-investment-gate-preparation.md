# ADR 50 — Gate 07J Investment Gate Preparation

## Status

Accepted — 2026-08-26.

## Context

Gate 07I produces a governed Portfolio recommendation and a selected project-set contract. Capital-owner portfolios need a controlled step that assembles current decision evidence before a later investment authority acts. This step must not recalculate FEL/PDRI maturity, approve funding, create an Investment Decision or grant FID authority.

## Decision

Introduce tenant-scoped `InvestmentGatePreparation` and `InvestmentGateEvidenceItem` aggregates.

- Gate 07J consumes only a current `READY_FOR_INVESTMENT_GATE_PREPARATION` contract from Gate 07I.
- Only projects with governance model `CAPITAL_OWNER` are eligible.
- Published profiles govern purpose, required FEL stage, evidence requirements, scope, validity, project coverage, conditions, blockers, segregation of duties and inheritance. Starter profiles `PYP-INV-SELECT` and `PYP-FFA` remain drafts until explicitly published.
- Governed evidence remains read-only. Manual references are allowed only where the published requirement permits them; they retain issuer, owner, dates, scope hash, external reference and reviewer decision.
- A distinct validator is required for configured evidence types. Expired, stale, scope-mismatched or insufficient-maturity references block readiness.
- Refresh is explicit and begins with a non-persistent preview. Source and project-set changes never silently rewrite a preparation.
- Lifecycle is `DRAFT → IN_PREPARATION → READY_FOR_REVIEW → FROZEN`, with controlled clone and void paths.
- Frozen preparations and their evidence are immutable. ETag/`If-Match`, idempotency keys, source hashes and `SecurityEvent` records protect concurrency and traceability.
- The only successful handoff is `READY_FOR_INVESTMENT_DECISION`; it always declares `can_enter_investment_decision=true` and `can_enter_fid=false`.
- USER MODE exposes Preparations, Evidence Package, Project Readiness, Conditions and History. ADMIN MODE exposes profile, requirement, validity, readiness, SOD and inheritance configuration with non-persistent preview.

## Consequences

The platform can prove that a current Portfolio recommendation has a complete, scoped and independently reviewed evidence package. The package can be handed to a future Investment Decision workflow without conflating preparation with authority.

Gate 07J intentionally excludes GO/HOLD/RECYCLE/KILL, Investment Decision, FID, Funds/Funding engine, FEL/PDRI scoring, project initialization, activation and execution.

## Rejected alternatives

- Treating the Gate 07I recommendation as investment approval.
- Uploading opaque files without requirement, scope, validity and source lineage.
- Automatically refreshing source evidence or selected projects.
- Letting evidence preparers validate their own controlled references.
- Adding downstream FID or project-execution controls to Gate 07J.
