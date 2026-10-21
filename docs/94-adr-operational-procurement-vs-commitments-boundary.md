# ADR 94: Procurement vs Commitments boundary

Status: PROPOSED_DESIGN

Requirement alias: ADR-O-009

Date: 2026-10-19

## Context

Two menu concepts currently reserve PO access but one table/API exists; strategy/funding are explicitly separate strategic bounded contexts.

## Proposed decision

Procurement owns sourcing and recommendation; Contract Administration/Commitments owns one legal obligation register for Contract/PO/subcontract and approved contractual variations. Cost consumes net obligations once.

## Consequences and implementation boundary

Do not create new Procurement Manager until duplicate concepts and canonical binding are resolved. Define call-off/included/additive PO, client-contract direction and economic-origin dedupe before rollout.

This increment is architecture only. No production implementation, broad migration, strategic approval or business release is recorded.

## Evidence inspected (not tests executed)

- `backend/app/domain/models.py:1400`
- `backend/app/domain/models.py:1524`
- `backend/app/services/integrated_control.py:417`
- `backend/app/modules/commercial_strategy/models.py:1`
- `frontend/src/navigation/applicationNavigation.ts:370`
- `frontend/src/navigation/applicationNavigation.ts:447`
