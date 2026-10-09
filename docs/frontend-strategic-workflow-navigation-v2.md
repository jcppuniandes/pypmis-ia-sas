# Frontend Strategic Workflow Navigation V2

## Purpose

The Enterprise Strategy Manager presents the governed strategic lifecycle in business order. Enterprise Foundation is Phase 0 and a prerequisite; Idea & Demand is Phase 1 and the first strategic transaction. The frontend reuses existing services, routes and feature workspaces. It does not add backend states, permissions, migrations or lifecycle rules.

## Previous navigation inventory

The USER navigation grouped strategic capabilities by implementation area. Enterprise Structure appeared after Idea and Strategic Gate. Portfolio Intake, Evaluation, Analysis, Budget, Resources, Convergence and Investment Gate Preparation were mixed inside Portfolio Manager. Business Case, financial modeling, FEL, Funding, Risk, Permits, FID and post-FID governance were separate modules without one visible lifecycle.

The ADMIN navigation exposed one flat Enterprise Strategy Manager list. Enterprise Structure lived in a separate module, and evidence policy appeared after Gate preparation. The flat list did not distinguish Foundation from transactions, parallel scenario branches or evidence convergence.

## Authoritative blueprint

`frontend/src/features/enterprise-strategy/navigation/strategicNavigationBlueprint.ts` is the single source of truth for USER and ADMIN strategic navigation. Every node declares:

- identity, label, description, phase and display order;
- existing frontend view and deterministic deep-link route;
- mode and existing permission intent;
- applicable Workspace types and Governance Models;
- Foundation flag and predecessor relationships;
- parallel group and convergence target;
- nested children for existing detailed feature views.

`frontend/src/navigation/applicationNavigation.ts` derives the application sidebar from this blueprint. It retains non-strategic macroprocesses and moves alternate Project creation and commercial Workspace capabilities to Project Workspace Governance, outside the universal Idea flow.

## USER hierarchy

0. Enterprise Foundation — Foundation Status, Enterprise Explorer and Workspace Context.
1. Idea & Demand — Idea Lifecycle.
2. Project Proposal — Project Proposals.
3. Strategic Gate — Strategic Gate Decision.
4. Portfolio Planning — Portfolio Intake & Planning, Evaluation & Prioritization and Portfolio Analysis. Investor Map and Portfolio Scorecard remain children of Portfolio Analysis.
5. Portfolio Scenario Planning — Budget Planning & Scenarios and Resource Planning & Scenarios are parallel inputs to Scenario Convergence & Recommendation.
6. Project Definition & Investment Case — FEL, Business Case, Funding, economic and financial modeling, Risk and Permits contribute evidence in parallel.
7. Investment Governance — Investment Gate Preparation, Investment Decision or FID and Post-FID Project Governance.

Business Case remains longitudinal. Its menu position is a principal access point and does not redefine its lifecycle. Funding retains capacity and assignment ownership; the Economic & Financial Model consumes funding references for modeling. Project Activation is not part of FID.

## ADMIN hierarchy

ADMIN mirrors Phases 0 through 7. Phase 0 contains Enterprise Structure & Workspace Manager, Workspace Types, Composition Rules, Strategic Objectives, Foundation preview and the reused workspace configuration views. Phase 7 places Investment Decision Evidence Policy before Investment Gate Preparation, FID and post-FID governance.

Organization, security and shared platform configuration remain available under Platform Administration.

## Foundation behavior

The landing page reads existing Enterprise Structure and Idea option services. It presents four existing signals:

- published Enterprise Structure;
- backend-authorized owning Workspaces of type ENTERPRISE, BUSINESS UNIT or PORTFOLIO;
- Strategic Objectives from the existing catalog;
- an existing Idea configuration source.

The Start Strategic Workflow action appears only when all four signals are returned. The backend remains authoritative for eligibility and mutation. The frontend does not create a Workspace from the Idea form and does not auto-publish configuration.

## Deep links and breadcrumbs

Strategic views use deterministic paths under `/app/strategy/<view>` for USER and `/app/admin/strategy/<view>` for ADMIN. `/app` and `/app/schedule-control` remain valid. Existing feature view keys remain unchanged. Breadcrumbs are generated from the same blueprint, so nested views include the macroprocess, phase, logical capability and selected detailed view.

## Workspace Navigator

The frontend orders backend-returned navigator entries without changing state, permission, reason or route. Enterprise, Business Unit and Portfolio contexts prioritize Ideas, Proposals, Strategic Gate, Portfolio planning, Analysis, Budget, Resources and Convergence. Project context prioritizes Strategic Context, FEL, Business Case, Funding, financial modeling, Risk, Permits, Gate preparation, FID and post-FID governance. Unknown or non-strategic entries keep their backend order after the preferred entries.

## Governance Model applicability

CAPITAL OWNER nodes carry the owner-path applicability metadata. CONTRACTOR DELIVERY, DIRECT INTERNAL and legacy or unclassified contexts are not marked applicable to owner-only phases. Their existing alternate Project creation capabilities remain outside the strategic owner flow. Individual workspaces and feature services continue to expose backend-controlled N/A, blocker and readiness behavior.

## Accessibility and responsive behavior

The sidebar uses nested buttons with `aria-expanded`, `aria-controls`, `aria-current` and named groups. Foundation and workflow-start badges remain visible in the phase labels. The landing page uses named regions for Foundation, parallel scenario branches and evidence convergence. Desktop, tablet and mobile layouts preserve phase order; cards reduce from four columns to two and then one without reordering.

## Validation evidence

- TypeScript compilation and the Vite production build pass.
- ESLint reports zero errors. The thirteen remaining warnings are pre-existing in the BIM viewer and economic/financial-model components; the new Enterprise Strategy feature contributes none.
- Nineteen focused unit, integration and characterization tests pass.
- The complete `AppShell` navigation regression passes after accounting for the new Project Workspace Governance grouping.
- Two Chromium E2E scenarios pass against Docker `localhost:5173`, covering USER/ADMIN hierarchy, deep links, breadcrumbs, convergence and tablet/mobile layouts.
- The BIM oversized-file regression also passes after adding a minimal accessible `role="status"` overlay for the existing backend-cache safeguard; rendering policy and backend behavior are unchanged.

The reproducible capture utility is `frontend/scripts/capture-strategic-navigation.mjs`. Before and after evidence is stored under `docs/validation/strategic-navigation-v2/`.
