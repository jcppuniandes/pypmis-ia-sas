# ADR 97: Operational checkpoints vs Strategic Gates

Status: PROPOSED_DESIGN

Requirement alias: ADR-O-012

Date: 2026-10-19

## Context

Existing Post-FID/canonical lifecycle is distinct and has separate scope/currentness/condition/SoD controls.

## Proposed decision

Baseline Approved, Ready to Execute, Workfront Ready, Ready for Commissioning/Handover and Closeout Ready are operational readiness checkpoints; they never substitute for Investment Gate/FID or reactivate a Workspace automatically.

## Consequences and implementation boundary

Operational checkpoint approval references source evidence and constraints; applicable authorization checked without new strategic approval authority.

This increment is architecture only. No production implementation, broad migration, strategic approval or business release is recorded.

## Evidence inspected (not tests executed)

- `backend/app/modules/post_fid_governance/service.py:492`
- `backend/app/modules/project_workspace_initialization/governance.py:58`
- `backend/app/modules/project_workspace_initialization/router.py:126`
- `backend/tests/test_project_initialization_post_fid_bridge.py:161`
