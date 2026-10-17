# Fresh Capital Owner: same-record Chromium validation

The executable test is `frontend/e2e/strategic-capital-current.spec.ts`.
It uses the existing Playwright installation and current frontend; it does not
modify `App.tsx`, mock API responses, provision terminal business records,
freeze evidence or record a decision.

## Required isolated environment

- API: `http://127.0.0.1:8840`, the disposable `strategic_fresh_uat` PostgreSQL stack.
- Frontend: `http://127.0.0.1:5543`, with `VITE_DEV_PROXY_TARGET=http://127.0.0.1:8840`.
- Credentials: the fresh `actors.author` identity from the execution artifact;
  `1234` is an isolated-test password only, overridable using
  `E2E_STRATEGIC_FRESH_PASSWORD`.
- Metadata: `outputs/.qa/strategic-uat-remediation/fresh-setup.json` and
  `fresh-capital-owner-chain.json`, produced by the actual governed backend
  lifecycle, not assembled from unrelated scenarios. The chain's own `setup`
  takes precedence so a later setup file cannot substitute different records.

The test refuses the operational frontend port `5173` and API port `8000`.
It checks positive integer IDs, the actual tenant/user returned by login, the
Idea → Business Analysis → Proposal → Strategic Gate lineage, the canonical
Project and Portfolio, and then the same Project's completed Five Case revision,
frozen Gate 07J package, FFA FID authorization and Post-FID eligibility.

The current login form sends no tenant selector. Therefore authentication uses
the real `/api/v1/auth/login` endpoint with the fresh tenant slug and then
hydrates the existing persisted authentication store from that actual response.
This is authenticated browser navigation coverage, **not** coverage of a
tenant-selecting UI login or browser creation of every lifecycle record.

## Run

From the repository's `frontend` directory in PowerShell:

```powershell
$env:E2E_API_URL = 'http://127.0.0.1:8840'
$env:E2E_BASE_URL = 'http://127.0.0.1:5543'
./node_modules/.bin/playwright.cmd test e2e/strategic-capital-current.spec.ts --project=chromium --workers=1 --output=../outputs/.qa/strategic-uat-remediation/browser-current --reporter=line
```

Optional artifact-path overrides are `E2E_STRATEGIC_FRESH_SETUP`,
`E2E_STRATEGIC_FRESH_CHAIN` and `E2E_STRATEGIC_FRESH_BROWSER_RESULT`.
They must refer to the same fresh execution and its disposable database.

## Evidence and interpretation

- `fresh-browser-result.json` always records actual visited views, tenant/actor
  IDs, record IDs, read timings, HTTP/runtime errors and the first blocker.
- Playwright writes screenshots, the failure screenshot and retained-on-failure
  trace beneath the supplied output directory. Bearer tokens are not written
  into the result JSON or visible screenshots. Private trace files may include
  authenticated requests and must not be published as unrestricted evidence.
- The browser performs no intentional business write. Canonical Project
  Overview, Business Case revision history and the selected frozen preparation
  are compared before/after the read-only traversal.
- Missing IDs, missing stages or an incomplete backend chain cause an explicit
  `BLOCKED_*` failure, never `test.skip`, an expected failure or a fabricated
  success. A genuinely completed current Business Case and its actual blocked
  DRAFT Gate package may be inspected read-only before the explicit
  `BLOCKED_NO_COMPLETED_FRESH_CHAIN_NO_FID` failure. These partial reads never
  substitute for a frozen package, FID, approved manual references or Post-FID.
  Upstream and partial-source screenshots remain partial evidence only.
- Screenshots now wait for actual read-only API readiness values and related
  Proposal/Strategic Gate records to hydrate in the UI; no READY status is
  manufactured merely to remove a loading indicator.
- Local request durations are single observations, not an SLA or load test.
- A green test supports same-record browser navigation. It does not independently
  establish all A0–A31 lifecycle transitions, the complete regression baseline,
  policy-negative cases or authorized human UAT sign-off.

## Observed execution — 15 October 2026

Actual Chromium/JUnit result: **1 test, 0 passed, 1 failed, 0 skipped**.
The selected execution is tenant 4 / author 43 / canonical Project 16, with Idea,
BA, Proposal and Strategic Gate IDs 4 and Portfolio 15. Chromium reached eight
same-record USER strategic views: Idea, BA, Proposal, Strategic Gate,
Enterprise Explorer / Project Overview, Portfolio Projects, Business Case Manager,
and Investment Gate Preparation. The JUnit duration is 147.708392 seconds;
the test body took 135.968 seconds.

Root's authorized App fallback to the reusable `StrategicWorkspaceShell` closes
**UAT-S2-004 as CLOSED_SCOPED_UI**, not as a completed browser A0–A31 chain. No
operational workaround Project was created. The browser agent did not edit App.

The same execution's Business Case 4 / revision number 2 (revision ID 6) is actually COMPLETED / READY
with current sources. Its Gate preparation 1 is actually DRAFT / BLOCKED with
current sources: 19 requirements, 11 valid and 0% Project coverage. Four blocking
Class B manual references remain absent under the unchanged effective policy:
Contracting, Execution Plan, Permit and Schedule Maturity. No reference was
invented or validated. Freeze is disabled; no frozen package, FID or Post-FID
was claimed. The test retains its explicit
`BLOCKED_NO_COMPLETED_FRESH_CHAIN_NO_FID` failure after read-only inspection.

Three denied physical-creation options reads from Explorer are retained in the
result; no clean-network PASS is claimed. Nine progress screenshots were
visually reviewed with no visible secrets. Readiness hydration waited for actual
API states: BA READY, Proposal GATE07B_REWORK_REQUIRED, Intake
READY_FOR_PORTFOLIO_INTAKE. The last value for the Proposal was not replaced
with an invented READY. UI presentation observations for the BC source matrix
and post-APPROVE Proposal readiness remain explicitly documented; the displayed
Funding STALE label is not evidence of a stale live funding provider.

The failure screenshot is a hash-identical copy of the last Gate evidence
screen. The canonical Project, BC revision history and selected DRAFT Gate
were unchanged by the read-only browser inspection.

The token-free versioned summary and screenshot hashes are in
`docs/validation/strategic-uat-remediation/browser-current-validation.json`.
The actual JUnit file is
`outputs/.qa/strategic-uat-remediation/browser/strategic-capital-current.xml`.

Prior tenant 1 / Project 4, tenant 2 / Project 8 and tenant 3 / Project 12 executions were preserved
before the selected fresh-chain rerun in
`outputs/.qa/strategic-uat-remediation/browser-prior-tenant1-project4` and
`outputs/.qa/strategic-uat-remediation/browser-prior-tenant2-project8` and
`outputs/.qa/strategic-uat-remediation/browser-prior-tenant3-project12`.
Their original JUnit and screenshot hashes remain unchanged. The current summary
records the selected latest execution and those historical archives; results are
not merged into a false successful release denominator.
