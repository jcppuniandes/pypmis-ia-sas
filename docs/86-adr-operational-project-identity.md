# ADR 86: Project identity

Status: IMPLEMENTED_O1A_RELEASE_VALIDATED

Requirement alias: ADR-O-001

Date: 2026-10-19

## Context

Canonical project creation already intentionally creates no legacy Project; operational Contract/PO/Schedule still use projects.id.

## Decision implemented in O1A

Keep enterprise_workspaces of type project as sole canonical Project identity. Bind existing legacy operational records through an explicit tenant-scoped canonical reference/projection adapter; no second Project master and no ID equality shortcut.

## Consequences and implementation boundary

O1A resolves mapping, missing/ambiguous references, tenant, lifecycle, scope and authorization through `operational_context`. Migration 20261019_0069 is additive; it creates binding, period and command receipt tables, not another Project master. No production data backfill or implicit canonical activation side effect occurs.

Canonical `enterprise_workspaces.id` and legacy `projects.id` remain independent. An active binding is unique in both directions within a tenant. No ID/name/code matching is authoritative. Reconciliation may consume an explicit trustworthy forward/reverse source relationship and fails closed on conflicts. Revocation/supersession preserves history; published period policy references are immutable.

Legacy HTTP material commands cross `legacy_boundary` before domain execution. Queued control jobs require an explicit authorized actor and resolve the binding again. Anonymous scheduled cycles skip without writes. Existing legacy reads retain their characterized behavior. Technical release is determined by the O1A validation package, not by the architectural decision alone. No production rollout or business signoff is implied.

## Release validation

On 2026-10-20 the O1A package completed 229 distinct backend/PostgreSQL cases,
11 frontend cases and a real Chromium journey with 12 checks. Additive migration
0068 to 0069 and rollback/reapply passed in an isolated database. Project 14 and
the strategic source modules remained unchanged. This validates only identity,
binding and the O1A operational foundation; deployment and business signoff are
not implied. Evidence is indexed in `docs/validation/wave-o1a-20261019/package-data.json`.

## Original architectural evidence inspected

- `docs/44-adr-project-governance-multi-source-creation.md:21`
- `backend/app/domain/models.py:486`
- `backend/tests/test_project_creation_process.py:642`
