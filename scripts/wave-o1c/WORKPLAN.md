# Wave O1C implementation and verification

Task started 6 November 2026. User explicitly authorizes implementation of
PROMPT_WAVE_O1C_FORECAST_PERFORMANCE_REPORTING.md and technical Word report.
Prompt also requires the nineteen-sheet traceability workbook.

## Baseline and boundaries

- Start HEAD 19baf10, clean worktree. O1B-D release evidence is retained under
  docs/validation/wave-o1bd-20261104. No historical migrations may change.
- New single successor 20261106_0075 of 20261104_0074. Static frozen DDL.
- Do not alter App.tsx, global domain models/schemas or the IFC viewer.
- No normal database migration, no commit/push, no actor autoassignment.
- Project14 before observation saved under docs/validation/wave-o1c-20261106.
  Canonical SHA 6042e74503bdb761a443665d789e70cea71e5435d46023159cc17243edd1b114.
- O2 is not authorized. Only recommend WAVE O2 — PROCUREMENT, CONTRACTS &
  ENGINEERING if every O1C criterion passes.

## Work allocation

- o1c_forecast_core: forecast_foundation models/schemas/policy/service/router,
  permissions, provision, README; forecast core fixture/policy/PG tests.
- o1c_reporting: reporting_models/schemas/policy/service/router in same module;
  reporting PG/policy tests, look-ahead, dashboards, immutable reports/trends.
- o1c_frontend: feature folder, minimal ADMIN/Workspace adapters, component
  tests and real Chromium E2E. No heavy job without root coordination.
- Root: integration, navigation/catalog, migration0075/guards, startup test,
  isolation, source-fresh final runner, preservation, artifacts and final QA.

## Isolation and resource discipline

Compose docker-compose.wave-o1c.yml project pypmis-wave-o1c. DB o1c port5550;
migrationDB o1c_migration port5551; browserDB o1c_browser internal; API8858;
frontend5518. User/password o1c/disposable-o1c are synthetic local credentials.
Mandatory PYPMIS_O1C_FIXTURE=disposable-only. Never point fixtures at normal DB.
Three fresh databases clone ONLY schema from actually migrated isolated O1BD.
This setup is not claimed as an empty-to-head migration test.
Host8GB; serialize native PG suite, Vite build and Chromium/API workloads.
Normal application services stay unchanged. O1BD source DB was started solely
for schema-only reads and should return to stopped after clone completion.

## Acceptance sequence

1. Freeze DTO/model contracts; implement and scoped lint/type/component checks.
2. Freeze0075 and prove PostgreSQL upgrade/downgrade/reupgrade, SQL invariants.
3. Real disposable lifecycles, broad upstream regression, source freshness.
4. Real Chromium ADMIN publication, USER forecast, approvals, lookahead,
   reporting, immutable history; no business response mocks.
5. Eleven timed operations with context/volumes, no production SLA claims.
6. Project14 after comparison, protected-source and historical migration hashes.
7. Evidence-based report37chapters and workbook19sheets, no invented PASS.
8. Render and inspect all Word pages and every workbook sheet/range; native
   package/type/relationship checks and document a11y; release manifest.

## Artifact instructions and runtime

Main read entire current DOCX and Spreadsheets skills, DOCX template-distill,
template-create, writing_quality, create_edit, verify_render, fields_update,
accessibility_a11y; spreadsheet create_workflows, style_guidelines, full
API_QUICK_START. Artifact is technical traceability, not a financial model.
Retain O1BD Word as visual template, inspect all eight source pages again
before distillation. Source DOCX SHA ea1934490194120ed7d6ae6045145e12b4e219dfb5d41816cf6b4e33f670e0a0.
Current bundled dependencies (load_workspace_dependencies, version26.1105.12137):
C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1105-1297-0_26.1105.1297.0_x64__3k8sg7r9htsxt/dependencies
Use its Python, Node and node/node_modules exclusively for artifact work.
No authoring markers or DOCX/XLSX creation have run yet for O1C. Run each
skill's create marker exactly once immediately before its first author run.
Do not remove old runtime junctions. Create a new ignored junction under the
new scripts folder if needed. Never inspect package internals/prototypes.
Use packaged render_docx.py; if no bundled LibreOffice, reuse verified hidden
read-only Word PDF export/provenance bridge. Never installed desktop LO.
Only final DOCX/XLSX delivered, not private PNG/PDF/builders.

## Deliverables and release decision

outputs/wave-o1c-20261106/P&Pmis_Wave_O1C_Forecast_Performance_Reporting_Technical_Report.docx
outputs/wave-o1c-20261106/P&Pmis_Wave_O1C_Forecast_Performance_Reporting_Traceability.xlsx
Private QA outputs/.qa/wave-o1c-20261106; public evidence docs/validation/wave-o1c-20261106.
Exact success only after all prompt criteria:
WAVE_O1C_FORECAST_PERFORMANCE_REPORTING_RELEASE_VALIDATED
READY_FOR_WAVE_O2_PROCUREMENT_CONTRACTS_ENGINEERING
Final reply thirty concise numbered results requested by prompt plus artifacts.
