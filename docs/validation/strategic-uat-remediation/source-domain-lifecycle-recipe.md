# Fresh Capital Owner — current source-domain adapters

This is an implementation recipe, **not a UAT PASS record**. Only execution of
the single fresh current-baseline PostgreSQL chain can close UAT-S2-003.

## Reusable test-only adapters

`backend/tests/helpers/strategic_capital_sources_current.py` receives the caller's
disposable tenant, real canonical Project and independently authorized users.
It never inserts a terminal business state or modifies published content by ORM.

- `configure_current_sources(db, tenant_id, config_author_id, config_publisher_id, enterprise_workspace_id)`
  returns policy IDs/revisions/status/content hashes for Benefits, Commercial,
  Permit, Basic Data and Owner Capability.
- `complete_benefits(..., project_id, *, idea_id, analysis_id, proposal_id, business_case_id, objective_code)`
  creates a Plan, an owned benefit with exact chain references, controlled
  baseline/target measure, submits, independently reviews, and completes.
- `complete_commercial(..., project_id)` creates the strategy, applies the existing
  governed EPC/Lump Sum alternatives payload, submits, independently reviews and
  completes. It does not execute procurement.
- `complete_permits(..., project_id)` resolves the actual Mining requirement
  catalogue; progresses each permit from NOT_STARTED through preparation,
  submission and review; satisfies an actual blocking condition through the
  condition commands; approves; and independently completes the assessment.
- `complete_basic_data(..., project_id)` creates four controlled study items,
  independently validates each, submits the assessment and independently completes.
- `complete_owner_capability(..., project_id)` creates/updates the assessment,
  submits, independently reviews and completes four explicit owner controls.

The full path must resolve all effective requirements, rather than assuming the
adapter's configuration metadata represents every strategic policy.

## Effective default policy facts

Business Case Five Case at FFA requires Proposal, Business Analysis, Benefits,
Commercial, FIN, FEL, Budget, Resources, Funding, Risk and Permit. All five cases
are enforced. The services must not reduce this matrix.

Default Gate PYP-FFA Class A providers include Recommendation, Budget, Resources,
FEL/definition/PDRI-equivalent/estimate maturity, Business Case, FIN, Funding and
Risk. The existing MINING override makes Permit Class A and rejects manual
substitution. Basic Data and Owner Capability are not default matrix rows;
QRA is contextual and absent unless a published policy opts in. Record actual
effective applicability; do not fabricate an unnecessary QRA result.

Basic Data and Owner Capability starters are deliberately empty DRAFT catalogues.
The adapters configure explicit enterprise-scoped requirements, retain 100%
coverage and independent publication. Permit preserves its existing Mining
requirements and strengthens its default neutral author/reviewer separation.

## Staged BC → FIN → final Five Case flow

1. Complete an actual FEL-1 Business Case while the Project is genuinely FEL-1.
   At that stage the Five Case policy requires the strategic case, not FIN.
2. Progress FEL-1 and FEL-2 through assessment + independent stage review; complete
   the FEL-3 assessment using the unchanged actual CUSTOM framework and thresholds
   40 / 65 / 80 (do not use the old synthetic all-stages-65 helper).
3. Complete the current Portfolio scenarios/convergence, Risk, Permit and Funding.
4. Create FIN from the earlier governed completed BC. Populate assumptions,
   cash flows, governed funding assignment references and Budget reconciliation;
   calculate, submit and independently complete.
5. Complete Commercial after its FEL/Risk/FIN inputs are stable.
6. Complete Benefits after Commercial and FIN are stable.
7. Refresh/create the final FFA BC revision; capture the exact completed source
   IDs, versions and hashes; submit and independently complete it.
8. Assert current BC READY, FIN current, Commercial current and Benefits current.
   Never count stored `source_current=true` alone as live provider validation.

FIN already supports the exact completed reverse-link bridge. The minimal
Benefits/Commercial resolver correction in `business_case/source_links.py`
applies the same principle without dropping freshness requirements: only a BC
backreference delta is accepted; the current completed READY BC must belong to
the same tenant/Project and same captured aggregate, and must consume this exact
source aggregate ID + version ID + version number + hash. Every other source
hash must be identical. No record or historical hash is rewritten.

## Historical helper hazards

- `test_gate07m_fid_e2e.py` directly seeds accepted Idea/Proposal and published
  policies/IDs. It cannot supply the new fresh-chain proof.
- Its `_funding()` explicitly disables `fund_creator_cannot_authorize`, although
  the current default is true. Reuse payloads only, with separate actual fund
  authorizer. Preserve all effective SoD.
- `_framework()` in the old FEL test inserts a synthetic published framework.
  Use normal framework bootstrap/configuration and real lifecycle instead.
- `_ready_content()` from Commercial is a data payload only, not a fixture or
  state seed, and is reused by the new adapter without weakening its catalogues.

## Boundaries and focused checks

The new closed-link unit tests are pure read-only predicate contracts with record
doubles. They are not seeded business-state or fresh E2E evidence. Actual source
lifecycles are the responsibility of the one fresh PostgreSQL chain.

No schema migration, Gate policy weakening, manual READY, SoD disablement, final
FID insert, automatic activation or operational Project 14 mutation is performed
by these adapters or the resolver fix.
