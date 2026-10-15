# Strategic frontend validation and scoped closeout

This is repository/static and focused component-test evidence. It is not real Chromium/PostgreSQL business UAT, a performance SLA, accessibility certification or authorized business sign-off.

Baseline inspected: commit `a9a62de3258b0fe86c7b4f2a580da72762a8f557`. The full controlling closeout prompt was read. Product changes were limited to the confirmed ADMIN live-creation defect and the approved Review sequencing correction. No feature/module was added; no history/data was deleted. No change was made to `App.tsx`.

## Reproduce the inventories

From the repository root, run:

```powershell
& 'C:\Users\Ricardo\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' docs/validation/strategic-final-uat/frontend_inventory_audit.cjs --write
```

The script evaluates only canonical navigation metadata and inert renderer registrations, parses production TypeScript imports/JSX/API declarations, and writes derived JSON/CSV beside itself. It does not execute React components, open a browser, call the backend or change product data. `--output=frontend-before` was used before the approved fixes to preserve the original inventory. Do not overwrite that snapshot when reproducing the current state.

The inventories include:

- `frontend_navigation_nodes`: every 227 blueprint node, mode/classification, order path, ancestry, applicability, predecessors, parallel/convergence metadata and canonical status.
- `frontend_routes`: every 197 canonical strategic URL (160 USER, 37 ADMIN), renderer component, breadcrumb, navigation order, context types, API import dependencies and placeholder status.
- `frontend_components`: reachable strategic JSX screens/components, route reuse, lexical controls and shared header/context references. Lexical control counts are not rendered accessibility results.
- `frontend_api_consumers`: 561 exported client API methods from 34 API files, source references, request templates/methods, direct production property consumers, consumer modes and version/idempotency header evidence. Shared governance-policy factory methods are expanded per API root. This is not the server endpoint/security inventory.
- `frontend_legacy_renderers`, `frontend_cleanup_candidates`: evidence-backed retention/deprecation candidates; none authorized as SAFE_TO_REMOVE.
- `frontend_supplemental_routes`: Workspace-scoped shell and embedded USER Project Creation states.
- `frontend_guide_routes.md`: current exact entry paths for the final User/Admin guides, derived from the blueprint rather than a second navigation source.

Results: no duplicate node IDs, no unresolved predecessor IDs, no cross-mode classification entries, no missing canonical renderer beyond two explicitly planned placeholders. Thirty ancestor/leaf landing aliases canonicalize to one route each: they are not duplicate screens or separate authorities. The two explicit placeholders (`portfolio-structure`, `portfolio-cash-flow`) are recorded as existing planned UI, not assumed business defects. The working Budget workspace must be assessed separately for its actual cash-flow capability.

API-consumer limitations: direct property references are not a whole-program proof. Consumer mode is a file-import-graph overapproximation, not proof a given prop/state-dependent branch executes on every importing route. Dynamic access, renamed/external clients and backend callers may exist. Sixty-one methods without a direct production property reference are UNKNOWN, not dead-code deletion candidates. Runtime backend RBAC, tenant isolation, SoD and ETag behavior require the independent backend/browser evidence.

## Approved remediations

`FE-S2-001`: before, ADMIN Composition Rules opened the legacy generic Workspace creation form and could request a directly active PROJECT Workspace through the old API. The canonical route now opens the existing rules editor (`AdminEnterpriseStructurePage`, `initialTab="rules"`). The manager now preserves an explicitly requested tab after remote load; default unrequested behavior remains hierarchy/revisions. Permission denial happens in the strategic outlet before configuration rendering. The backend agent separately owns 409 `PROJECT_CREATION_PROCESS_REQUIRED` on legacy PROJECT creation/bypass paths; frontend testing does not substitute for that regression.

`FE-S3-001`: USER Periodic Portfolio Review moved into phase5 after Scenario Convergence, including its detail metadata and derived landing action. Its twelve deep-link URLs are unchanged. The phase labels, eight-phase structure and decision authorities remain unchanged. The breadcrumb now passes through Portfolio Scenario Planning. ADMIN Review policy remains in phase4 because reusable setup precedes USER transactions.

Legacy `AdminConfigurationView` code was not deleted: the strategic route was rewired, and retained compatibility/deprecation is documented. No new menu array was introduced. No operational delivery, advanced/integrated QRA, procurement or other new strategic capability was implemented.

## Boundaries, remaining observations and guides

`frontend_findings.json` contains the severity/classification/evidence register. Three remaining S4 observations concern applicability metadata not used for runtime menu filtering, eleven historical BC renderer names outside the canonical route registry, and Explorer's READ_ONLY_SHARED metadata despite embedded USER creation controls. None is proof of a backend security bypass or an absent approved business capability. They remain explicit review/deprecation items.

USER Project Creation / Initialization / Activation are reached from `/app/strategy/enterprise-explorer`, using Create Project / My Project Requests / My Project Workspaces and the lifecycle overview. These are embedded view states, not separate invented URLs. Project remains the canonical PROJECT Workspace Instance. Contractor Delivery and Direct Internal can choose their configured governance/source options there; this audit did not execute their end-to-end workflows.

The separate `/workspaces/:workspaceId/*` shell is a legitimate backend-scoped compatibility navigator. It passes `workspaceId`/`portfolioId` to supported embedded modules, derives its ordering via the canonical adapter, and obtains navigator availability from backend context. It does not itself render every later investment domain. The global strategic workspace components frequently select their own Project; route metadata is not a guarantee of shared active-context propagation.

CompactModuleHeader reuse is inventoried. Additional global Current Module guides, Workspace headers and nested module headers exist; their mere presence is not proof of duplicate UI. Actual keyboard navigation, labels, table behavior, modal focus, warnings and representative local latency remain browser UAT work, not claimed PASS here.

`App.tsx` SHA256 observed after scoped frontend edits: `8a1692d5adb7c8fefced6daa7bb63ce65f6fa5daf31ab064da2520020ead8879`; its git diff is empty.

## Focused regression

Before fixes: 3 files / 29 tests PASS. `strategicNavigationBlueprint` 14 tests, `StrategicViewOutlet` 12 tests, `applicationNavigation` 3 tests. Vitest duration 140.47s (test bodies 3.22s; transform 11.92s, setup10.06s, collect69.50s, environment50.09s, prepare4.07s). These mocked/component tests did not detect the legacy Composition Rules defect before its explicit regression was added.

After fixes: 5 files / 44 tests PASS, exit0. Blueprint14, outlet13, landing3, applicationNavigation3, real enterprise-structure component11. Duration72.42s (test bodies11.83s; transform8.41s, setup2.94s, collect30.54s, environment18.47s, prepare3.36s). Raw result: `frontend_focused_after_tests.json`. React Router v7 future-flag warnings were emitted by the existing Explorer test; no test failed. No AppFlow or full frontend suite was run by this audit.

Exact after-fix command, from `frontend`:

```powershell
& 'C:\Users\Ricardo\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' node_modules/vitest/vitest.mjs run src/features/enterprise-strategy/navigation/strategicNavigationBlueprint.test.ts src/navigation/applicationNavigation.test.ts src/features/enterprise-strategy/StrategicViewOutlet.test.tsx src/features/enterprise-strategy/EnterpriseStrategyLanding.test.tsx tests/enterprise-structure.test.tsx --maxWorkers=1 --minWorkers=1 --reporter=default --reporter=json --outputFile=../docs/validation/strategic-final-uat/frontend_focused_after_tests.json
```

`git diff --check` passed for all eight changed frontend files. `App.tsx` diff remained empty.

Release decision, open backend blocker closure, real UAT coverage and authorized business acceptance belong to the integrated closeout report. Do not infer GO from this frontend inventory or the focused test result.
