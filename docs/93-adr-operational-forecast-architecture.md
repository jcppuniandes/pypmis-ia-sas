# ADR 93: Forecast architecture

Status: PROPOSED_DESIGN

Requirement alias: ADR-O-008

Date: 2026-10-19

## Context

Existing forecast_scenarios/control_snapshots can be reused, but a scenario is neither strategic investment approval nor source transaction.

## Proposed decision

Forecast is an independently approved versioned derivation of governed snapshots plus explicit assumptions; preserves source baseline/current/actual and P6 CPM authority.

## Consequences and implementation boundary

ETC/EAC and finish/milestone predictions disclose method/currency/period/input hashes and approval. Reforecast creates a new version, never edits approved history.

This increment is architecture only. No production implementation, broad migration, strategic approval or business release is recorded.

## Evidence inspected (not tests executed)

- `backend/app/domain/models.py:1234`
- `backend/app/domain/models.py:1260`
- `backend/app/services/integrated_control.py:253`
