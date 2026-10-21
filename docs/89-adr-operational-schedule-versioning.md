# ADR 89: Schedule versioning

Status: PROPOSED_DESIGN

Requirement alias: ADR-O-004

Date: 2026-10-19

## Context

Existing import/baseline/version primitives coexist with activity baseline field overwrites and date-only conversions.

## Proposed decision

Separate immutable approved baseline versions, reviewed accepted current update, provisional forecast scenario and staged import. Promote by explicit approval/version check; no import-driven baseline rewrite.

## Consequences and implementation boundary

Future adapter requires version manifest, provenance/hash, data-date rules, source IDs, semantic reconciliation, rollback by pointer/reversal and retained history.

This increment is architecture only. No production implementation, broad migration, strategic approval or business release is recorded.

## Evidence inspected (not tests executed)

- `backend/app/domain/models.py:615`
- `backend/app/domain/models.py:668`
- `backend/app/services/schedule_ingestion.py:1462`
- `backend/app/services/schedule_ingestion.py:1612`
