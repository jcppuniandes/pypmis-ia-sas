# ADR 88: P6 external CPM authority

Status: PROPOSED_DESIGN

Requirement alias: ADR-O-003

Date: 2026-10-19

## Context

Existing P6 imports/raw metadata are reusable; QRA elapsed-time simulation is explicitly not P6 operational CPM.

## Proposed decision

Primavera P6 remains primary operational CPM calculator. Design manual XML/XER roundtrip only; no native operational CPM, direct P6/OPC API or silent critical-path recalculation.

## Consequences and implementation boundary

Full fidelity export is a future validated adapter, not claimed as present. Preserve imported critical/float values and raw calendars/units.

This increment is architecture only. No production implementation, broad migration, strategic approval or business release is recorded.

## Evidence inspected (not tests executed)

- `backend/app/services/schedule_ingestion.py:402`
- `backend/app/services/schedule_ingestion.py:438`
- `docs/80-adr-qra-foundation.md:13`
- `docs/82-adr-qra-calculation-engine.md:43`
