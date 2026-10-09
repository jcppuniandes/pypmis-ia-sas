# Multi-Tenant Guided Control Flow Design

Date: 2026-05-15

## Purpose

Redesign the project workspace so P&Pmis Ai SaaS guides the user through the complete project controls process after login and after schedule upload. The app must always answer four questions:

1. Where am I in the process?
2. What is missing or blocking progress?
3. Who should act next?
4. What is the next button to press?

This design also formalizes the multi-tenant experience: each client workspace owns its projects, users, roles, catalogs, base currency, and configuration.

## Current Problems

The current project creation panel is visually placed below the control flow navigation, so users can read it as part of the process table instead of as a global onboarding action.

After a user uploads a XER/XML schedule, the app shows data but does not clearly tell the user what to do next. The critical post-upload questions are not elevated enough:

- Did the file include cost-loaded activity values?
- What currency should those costs use?
- Which activities have no cost?
- Should the user load rates, map CBS/FBS, or approve baseline?

The system already stores `tenant_id` across the backend, but the UI should make the client workspace explicit and should avoid mixing tenant-level and project-level actions.

## Product Decision

Use the **Mission Control guided workspace** approach.

This keeps the operational dashboard for expert users, but wraps it in a guided process rail and a next-action panel. It is better than a mandatory wizard because mature project teams need to revisit dashboards, costs, AWP, and decisions repeatedly without restarting onboarding. It is better than a loose board because upload, currency, cost loading, and baseline approval are sequential enough to need gates.

## Target Experience

### Global Header

The top of the app becomes the tenant/project command bar:

- Tenant selector or tenant identity: client name, slug, base currency.
- Project selector: only projects visible to the authenticated tenant/user.
- `+ Project` button: opens a right drawer for project creation.
- User/session controls.

Project creation must not live inside the process rail or below the flow table. It is a global action available to tenant configurators.

### Guided Rail

The left rail becomes a process map with status badges:

1. Tenant workspace
2. Project setup
3. Schedule upload
4. Cost and currency gate
5. WBS/CBS/FBS mapping
6. Baseline approval
7. Progress capture
8. Actual costs and commitments
9. Control Core
10. AWP packaging
11. Evidence and document control
12. Closeout

Each step shows one of these states:

- `not_started`
- `in_progress`
- `review_required`
- `ready`
- `blocked`
- `complete`

The active step drives the main content. Clicking a step moves to the relevant view, but gated downstream actions stay disabled until prerequisites pass.

### Next Action Panel

A persistent right-side panel shows:

- Primary next action.
- Reason for the recommendation.
- Blocking issues.
- Responsible role.
- Secondary actions.

Examples:

- `Load XER/XML schedule`
- `Confirm detected currency`
- `Load rates for activities without cost`
- `Map CBS/FBS`
- `Approve baseline`
- `Run Control Core`
- `Create draft AWP packages`

### Main Content

The main panel keeps the current dashboard/table behavior but changes its order:

1. Gate summary cards.
2. Next-action context.
3. Exceptions and tables.
4. Historical/advanced details.

Tables should no longer be the first thing the user sees after upload.

## Guided Process Details

### 1. Tenant Workspace

The app shows the current tenant identity and base currency. For the current production scope, tenant switching can be limited to users who have access to more than one tenant. If the login token only has one tenant, show it as fixed identity rather than a selector.

Tenant-owned configuration:

- Tenant name and slug.
- Base currency.
- Enabled modules.
- Role profiles.
- Business process templates.
- Default catalogs for WBS/CBS/FBS naming.

### 2. Project Setup

The project must capture:

- Code and name.
- Phase.
- Project currency.
- Calendar base.
- Owner.
- Authorization reference/date.
- Control level.
- Funding-required flag.

The project currency defaults from tenant base currency but remains editable per project.

### 3. Schedule Upload

The upload panel accepts XER/XML. After upload, the backend creates or refreshes:

- `ScheduleImport`
- `ScheduleActivityMap`
- WBS seed records
- control accounts
- baseline version
- validation findings
- schedule workflow instance

The upload result must include enough summary for the UI to guide the user immediately.

### 4. Cost And Currency Gate

This is a first-class step, not a warning hidden in the schedule gate.

The app computes:

- Detected currency.
- Currency confidence.
- Currency confirmed flag.
- Project currency.
- Total imported planned cost.
- Count and percentage of cost-loaded activities.
- Count and list of activities with zero planned cost.
- Cost source table names and fields used.
- Cost loading threshold, initially 80% of activities with planned cost greater than zero.

Gate states:

- `ready`: currency is confirmed and cost loading is above the configured threshold.
- `review_required`: currency was inferred or cost loading is partial.
- `blocked`: no currency can be resolved or cost loading is required but missing.

Baseline approval is disabled while this gate is blocked or while the detected/inherited currency has not been confirmed.

### 5. WBS/CBS/FBS Mapping

The app maps uploaded activities into control structures:

- WBS from XER/XML WBS fields.
- Control accounts from WBS/activity grouping.
- CBS from activity/resource/cost-code fields where available.
- FBS from project funding configuration.

The user sees exceptions first:

- Unmapped WBS.
- Activities without CBS.
- Control accounts without funding.
- Cost codes without contract/funding alignment.

### 6. Baseline Approval

Baseline approval requires:

- Schedule quality gate not blocked.
- Cost and currency gate not blocked.
- Mapping gate not blocked.
- User role can approve workflow.

The approval screen shows a final checklist before committing the baseline state.

### 7-12. Execution Through Closeout

After baseline, the guided flow continues:

- Progress capture: percent complete, evidence, daily/weekly updates.
- Actual costs and commitments: payment certificates, warehouse receipts, purchase orders, contracts.
- Control Core: SPI, CPI, EAC, forecast, alerts.
- AWP packaging: draft package creation, constraints, readiness.
- Evidence/document control: transmittals, reviews, attachments.
- Closeout: open commitments, unused funding, document status, final report.

## XER Cost Extraction

The parser must continue reading activity-level cost fields and resource assignment cost fields, then expand coverage for common Primavera XER tables and names.

Cost sources, in priority order:

1. `TASK` aggregate cost fields such as `target_cost`, `planned_cost`, `planned_total_cost`, `budgeted_cost`, `at_complete_cost`, `remain_cost`, and `actual_cost`.
2. `TASKRSRC`, `RSRCASSIGN`, or `RESOURCEASSIGNMENT` fields such as `target_cost`, `planned_cost`, `remain_cost`, `actual_cost`, and quantity multiplied by unit cost.
3. Resource/expense component fields: labor, equipment, material, and expense costs.
4. Optional fallback rates when the XER has hours/units but no cost values.

If XER cost values are absent, the app must say so clearly and offer `Load rates / cost sheet` as the next action. It must not imply that the schedule is fully cost-loaded.

## Currency Detection

Currency resolution uses this order:

1. Explicit currency fields in the schedule file, project properties, resource tables, or cost account tables.
2. Currency symbols in cost values.
3. Project currency if already configured.
4. Tenant base currency.
5. Manual confirmation when the source is inferred.

Confidence levels:

- `explicit`: read from file metadata or a currency field.
- `symbol`: inferred from symbols like `$`, `COP`, `USD`, `EUR`.
- `project_default`: inherited from project configuration.
- `tenant_default`: inherited from tenant configuration.
- `unknown`: user must choose before baseline approval.

The UI must display both the selected currency and the confidence/source.

## Data Model Additions

Add or extend entities so the UI can render the guided flow without duplicating business rules in React.

Required additions:

- `Tenant.base_currency`
- `ScheduleImport.detected_currency`
- `ScheduleImport.currency_confidence`
- `ScheduleImport.currency_source`
- `ScheduleImport.currency_confirmed`
- `ScheduleImport.total_imported_cost`
- `ScheduleImport.cost_loaded_activity_count`
- `ScheduleImport.cost_loaded_activity_percent`
- `ScheduleImport.cost_source_summary`
- `ScheduleValidationFinding` entries for missing cost loading and unresolved currency.

The backend must expose a guided status endpoint:

```text
GET /api/v1/projects/{project_id}/guided-flow
```

Response shape:

```json
{
  "tenant": { "id": 1, "name": "P&P MIS SAS", "base_currency": "COP" },
  "project": { "id": 1, "code": "CTRL-DEMO-001", "currency": "COP" },
  "steps": [
    {
      "key": "cost_currency",
      "label": "Cost and currency gate",
      "state": "review_required",
      "summary": "82% activities cost-loaded; currency inferred from project COP.",
      "primary_action": "Confirm currency",
      "responsible_role": "Control Manager",
      "blocking_count": 3
    }
  ],
  "next_action": {
    "key": "confirm_currency",
    "label": "Confirm detected currency",
    "target_view": "cost_currency",
    "disabled": false
  }
}
```

## Frontend Architecture

Split the current monolithic project workspace into focused UI units:

- `TenantCommandBar`
- `ProjectCreateDrawer`
- `GuidedProcessRail`
- `NextActionPanel`
- `GateSummaryCards`
- `ScheduleUploadGate`
- `CostCurrencyGate`
- `MappingGate`
- `BaselineApprovalGate`

These components consume backend step state. React can decide layout and interaction, but the backend owns process state and gating rules.

## Acceptance Criteria

The implementation is accepted when:

- Project creation is accessible from the header as a right drawer and is no longer visually below the process table.
- The guided rail covers the full process from tenant workspace through closeout.
- After XER/XML upload, the user sees currency, cost loading percentage, total imported planned cost, missing-cost activities, and the next action.
- Baseline approval is disabled when currency is unresolved, unconfirmed, or cost loading is blocked.
- Multi-tenant identity is visible in the app and all project/user/catalog data remains tenant-scoped.
- Frontend tests cover the guided rail, project create drawer, post-upload next action, and blocked baseline state.
- Backend tests cover XER cost extraction, currency detection, tenant default fallback, and guided-flow endpoint state.

## Verification Plan

Run these checks before completion:

- `docker compose exec -T api ruff check .`
- `docker compose exec -T api pytest`
- `docker compose exec -T frontend npm run lint -- --max-warnings=0`
- `docker compose exec -T frontend npm run build`
- `docker compose exec -T frontend npm run test`
- `docker compose exec -T -e E2E_API_URL=http://api:8000 frontend npm run test:e2e`
- `powershell -ExecutionPolicy Bypass -File .\tools\smoke_check.ps1`

## Out Of Scope For This Iteration

- Billing between tenants.
- Public self-service tenant signup.
- Cross-tenant project sharing.
- Full ERP integration for actual costs.
- A complete replacement of the existing dashboard charts.

## Open Design Decisions Closed

The selected UX pattern is Mission Control guided workspace. The project create form moves to a header-triggered right drawer. Currency is never silently trusted unless confidence is explicit and confirmed; inferred currency remains review-required until confirmed. The backend owns gate state through a guided-flow endpoint so frontend and API stay consistent.
