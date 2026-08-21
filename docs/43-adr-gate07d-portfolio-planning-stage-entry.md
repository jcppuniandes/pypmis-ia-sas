# ADR 43 — Gate 07D as Portfolio Planning stage entry

- Status: Accepted
- Date: 2026-08-20
- Scope: USER MODE Portfolio Manager, ADMIN MODE Enterprise Strategy Manager, Project Workspace context

## Context

Gate 07C already produces an immutable `APPROVE` decision and a `READY_FOR_PORTFOLIO_INTAKE`
contract. Gate 05B already owns governed Project creation, review, four-eyes approval,
numbering and materialization. Introducing a second candidate or Project identity would
duplicate authority and break lineage.

## Decision

Gate 07D is implemented as a stage-entry bridge:

1. Consume only an eligible Gate 07C decision with matching decision/readiness hashes.
2. Create or reuse exactly one Gate 05B `ProjectCreationRequest` with immutable strategic lineage.
3. Preserve Gate 05B review, approval, numbering and materialization as the sole authority.
4. Materialize one Project Workspace in `PENDING`; no initialization or activation is triggered.
5. Represent Portfolio association through `portfolio_project_memberships` as an analytical N:M
   relation. The first active target membership is sourced from `STRATEGIC_INTAKE` and does not
   replace the enterprise hierarchy parent.
6. Persist a planning-entry snapshot/hash and expose independent Portfolio Evaluation and Project
   Definition readiness contracts.
7. Finish exclusively as `READY_FOR_PORTFOLIO_PLANNING` or `GATE07D_REWORK_REQUIRED`.

## Consequences

- There is no `PortfolioCandidate`, candidate evaluation, prioritization, PDRI/FEL score, FID,
  initialization, activation or execution authorization in Gate 07D.
- A Project may participate in multiple Portfolios without changing its enterprise tree parent.
- Target strategic membership cannot be removed; additional governed memberships can be created
  and logically deactivated using ETag/revision controls.
- Future Portfolio evaluation and FEL/PDRI capabilities consume the readiness contracts and
  framework hints, but remain outside this change.

## Controls

- Tenant scoping and dedicated RBAC permissions are applied to entry, membership, read and ADMIN
  configuration operations.
- Gate 07C hashes are checked before request creation and again during materialization.
- Gate 05B submission and approval hashes include the Gate 07D lineage snapshot.
- Security events cover request linkage, materialization, membership changes, readiness and
  configuration publication.
- Migration `20260820_0043` supports upgrade, downgrade to `20260813_0042`, and re-upgrade.
