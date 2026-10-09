# ADR 061 — Gate 07M-FIN Economic & Financial Model

## Status

Accepted — 2026-09-02.

## Context

P&Pmis required a governed Project-level economic and financial model after the completed Business Case, while preserving the existing authorities of Portfolio Budget, Funds Manager, Treasury, Accounting and Investment Decision/FID. The result must be reproducible, tenant-scoped, versioned and usable as evidence without silently rewriting historical decisions or published Gate07J-EVID policy.

## Decision

Create one `EconomicFinancialModel` aggregate per Project Workspace and any number of immutable successor versions. A version freezes Business Case, Budget and Funding references/hashes, keeps Economic Case and Financial Case metrics distinct, records explicit currency/FX and nominal/real basis, persists inputs and calculation outputs, and reaches `COMPLETED` only through Four-Eyes review.

The deterministic `PPMIS-FIN-1.0` Decimal engine owns NPV, IRR, payback, BCR, WACC, capital structure, equity, debt, DSCR, LLCR, scenarios, sensitivity and trace hashes. It does not own budget capacity, funding authorization, cash movements, accounting, payments or FID.

`ECONOMIC_FINANCIAL_READINESS_PROVIDER` is registered as `AVAILABLE` for Project scope. Gate07J-EVID's existing published policy matrix is not changed automatically. The exclusive release output is `READY_FOR_GOVERNED_ECONOMIC_FINANCIAL_EVIDENCE`; the next controlled process is `UPDATE_GATE07J_EVID_FOR_BUSINESS_CASE_AND_ECONOMIC_FINANCIAL_READINESS`.

## Consequences

- Completed versions and their calculated evidence are immutable; changed sources require an explicit successor version.
- Funding assignments remain owned by Funds Manager and are linked by identifiers and hashes.
- Budget reconciliation consumes frozen Portfolio Budget evidence without changing it.
- Commercial, mixed, public appraisal and non-revenue models use one governed lifecycle with type-specific metrics.
- USER MODE exposes the operational model; ADMIN MODE exposes applicability, formulas, thresholds, freshness, inheritance and SoD configuration.
- The migration is additive and reversible from revision `20260902_0058` to `20260902_0057`.

## Guardrails

No Treasury, Accounting, payment execution, live market-data feed, Monte Carlo optimizer, automatic FID, automatic funding confirmation or automatic published-policy update is included in Gate 07M-FIN.
