# ADR 90: Scope/WBS/CBS alignment

Status: PROPOSED_DESIGN

Requirement alias: ADR-O-005

Date: 2026-10-19

## Context

Existing control-account/SOV/mapping primitives link multiple structures; one-to-one assumptions lose valid allocation relationships.

## Proposed decision

Use explicit versioned many-to-many mappings among Scope Item, WBS, activity, CBS/CostCode, budget, contract and package. WBS is a structural source, not the sole identity of all cost or scope.

## Consequences and implementation boundary

Map cardinality/units/coverage, allocation denominator and historical mapping revisions; no silent auto-join by label.

This increment is architecture only. No production implementation, broad migration, strategic approval or business release is recorded.

## Evidence inspected (not tests executed)

- `backend/app/domain/models.py:698`
- `backend/app/domain/models.py:714`
- `backend/app/domain/models.py:767`
- `backend/app/domain/models.py:1418`
- `backend/tests/test_unifier_priority_flow.py:11`
