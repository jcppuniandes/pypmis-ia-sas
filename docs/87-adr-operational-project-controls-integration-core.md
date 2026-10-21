# ADR 87: Project Controls integration core

Status: IMPLEMENTED_O1A_FOUNDATION_ONLY

Requirement alias: ADR-O-002

Date: 2026-10-19

## Context

High coupling exists in legacy aggregate router/App; a monolithic controls master would duplicate source ownership.

## Proposed decision

Project Controls coordinates common period/baseline/mapping and integrates governed source snapshots; it does not own every source transaction.

## Consequences and implementation boundary

Domain-owner command boundaries and typed read models; reporting never writes source facts.

The O1A implementation now supplies canonical context, applicable ADMIN profile and common reporting period. OPEN, REVIEW, CLOSED and PUBLISHED are explicit commands with RBAC/SoD, ETag and idempotency. Publication issues only an immutable header snapshot. Baseline bundles, governed source-domain approval, Forecast and full Project Controls reports remain future O1B/O1C decisions; this status does not mark them implemented. No strategic approval or business release is recorded.

## Evidence inspected (not tests executed)

- `backend/app/domain/models.py:685`
- `backend/app/services/integrated_control.py:176`
- `frontend/src/views/DashboardView.tsx:379`
