# ADR 96: AWP optional architecture

Status: PROPOSED_DESIGN

Requirement alias: ADR-O-011

Date: 2026-10-19

## Context

Existing WorkPackage/constraint primitives can be reused but do not establish a mandatory linear package chain.

## Proposed decision

AWP is configurable by Project Type/execution strategy, not a universal hierarchy. CWA/CWP containment, EWP/PWP support dependencies, IWP executable scope and TWP configured turnover/test relation are explicit typed links.

## Consequences and implementation boundary

No forced CWA→CWP→EWP→PWP→IWP→TWP sequence. Enforce package readiness and optional engineering/material dependencies by published policy.

This increment is architecture only. No production implementation, broad migration, strategic approval or business release is recorded.

## Evidence inspected (not tests executed)

- `backend/app/domain/models.py:822`
- `backend/app/domain/models.py:852`
- `backend/tests/test_unifier_priority_flow.py:397`
