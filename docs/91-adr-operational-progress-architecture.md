# ADR 91: Progress architecture

Status: PROPOSED_DESIGN

Requirement alias: ADR-O-006

Date: 2026-10-19

## Context

Existing record primitives and import percent fields are not interchangeable semantic measures.

## Proposed decision

Keep physical, quantity, milestone, schedule, cost and earned progress as typed methods with source owner, unit, denominator, weight, period, evidence and independent approval where material.

## Consequences and implementation boundary

Freeze closed approved progress snapshots; EVM consumes approved baseline/progress and reconciled cost, never mixes percentages silently.

This increment is architecture only. No production implementation, broad migration, strategic approval or business release is recorded.

## Evidence inspected (not tests executed)

- `backend/app/domain/models.py:1195`
- `backend/app/domain/models.py:283`
- `backend/app/domain/models.py:748`
