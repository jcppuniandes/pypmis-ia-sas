# ADR 92: Change cross-domain model

Status: PROPOSED_DESIGN

Requirement alias: ADR-O-007

Date: 2026-10-19

## Context

Existing ChangeRequest and reserved per-module change menus risk parallel authority if expanded independently.

## Proposed decision

One Change Event/Request coordinates impact assessment and decision across scope/schedule/cost/resources/contracts/risk/forecast. Owners implement approved changes through idempotent commands; no disconnected approval ledgers.

## Consequences and implementation boundary

Single approved decision reference, affected source versions, implementation receipts and explicit rejection/pending state; no baseline rewrite on submission.

This increment is architecture only. No production implementation, broad migration, strategic approval or business release is recorded.

## Evidence inspected (not tests executed)

- `backend/app/domain/models.py:1295`
- `frontend/src/navigation/applicationNavigation.ts:445`
- `frontend/src/navigation/applicationNavigation.ts:650`
