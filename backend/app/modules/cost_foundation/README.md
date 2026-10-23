# O1B-C — canonical operational Cost

## Authority and repository characterization

Cost is downstream of canonical `enterprise_workspaces.id`, approved Scope,
published Plan, AWP and immutable accepted Schedule snapshots. It owns CBS,
cost-code dictionaries, integrated Control Accounts, explicit M:N cost mappings,
effective-dated Rates/APUs, Budget versions/lines and immutable phased Cost
Baselines. No Project, Scope, Schedule, contract, invoice, strategic FIN, funding,
payment or accounting record is redefined here.

| Existing capability | Classification | Treatment |
| --- | --- | --- |
| O1A Project identity, authorization, controls periods | REUSE | Existing canonical context, policy, period and command-receipt infrastructure. |
| O1B-A Scope/Plan baseline and lineage | REUSE | Frozen approved Scope snapshot is the quantity source; Plan remains its own published source. |
| O1B-B Schedule/P6 and O1B-B1 AWP/4D | REUSE | References only. No CPM, date rewrite, package cost authority or 5D claim. |
| Legacy `budgets`, `control_accounts`, `cost_codes`, `cost_breakdown_structures` | KEEP_BEHIND_ADAPTER | Legacy Project foreign keys, float currency-less totals and forced WBS/FBS coupling cannot be the new approved authority. Explicit candidates only after canonical adoption; no automatic backfill. |
| `create_cbs_wbs_business_process` in legacy API | REFACTOR | Previously wrote Budget, code and account totals before business-process approval. Root boundary prevents competing Cost writes after explicit canonical adoption. |
| `ScheduleIngestionService._materialize_control_structure` | KEEP_BEHIND_ADAPTER | Previously auto-created CBS/Control Accounts/Budget from P6 cost. Canonical adoption makes imported cost candidate-only. |
| RateSheet + sheet recost | KEEP_BEHIND_ADAPTER | Retain importer provenance, not an approved cost master and never infer physical progress from it. |
| Colombia public APU catalog/BIM suggestions | REUSE behind adapter | Source/reference catalog only; snapshots can inform governed Cost APU, not publish or approve automatically. Public sync may refresh its own unapproved catalog. |
| Contract/PO/Subcontract sources | REUSE | Existing source records retain legal authority; Cost stores reconciled projections with explicit origin and inclusion mode. |
| Legacy contract+PO sums in `_cost_sheet_lines` and `integrated_control._committed_amount` | DEPRECATION_CANDIDATE | Currency-less additive totals are not canonical net commitment. Kept for legacy consumers, explicitly not re-used as canonical truth. |
| Legacy CostRecord/payment certificate/warehouse receipt totals | KEEP_BEHIND_ADAPTER | Not assumed to be recognized incurred actuals. New actual recognition has explicit source, dates, currency, period and independent approval. |
| Legacy cash-flow/EVM dashboard | KEEP_BEHIND_ADAPTER | Preserve legacy behavior, not new Treasury, approved Progress or Forecast authority. |
| Strategic Budget/Funding/FIN/Business Case/FID | REUSE read-only references | No upstream mutation. Operational Budget is not a strategic scenario. |

## Exact adopted semantics

* Original Budget is the first approved Budget with no predecessor.
* Approved Budget means each independently approved immutable version.
* Current Budget is the sole approved leaf of the explicit predecessor chain.
  Approval of a successor logically supersedes a predecessor; neither the
  predecessor's approved status nor its frozen content is edited. A competing
  approved branch is rejected. A DRAFT successor is not Current Budget.
* Rates and APUs are append-only revision identities after publication. APU
  components freeze published rate inputs, quantities, units and effective
  windows; indirect factors apply once to direct cost, not to one another.
* A Scope × APU operation produces only a DRAFT Budget Line. It uses the frozen
  approved quantity and explicit Budget pricing date, compatible unit and a
  published APU effective on that date. It does not modify Scope or approve Cost.
* Every money-bearing aggregate carries currency and Decimal `Numeric(24,8)`.
  Missing conversion returns `NO_AGGREGATION`; no implicit currency inference.
  Each operational Budget declares one currency; Budget Line amounts in another
  currency are rejected rather than implicitly converted. Multi-currency Actual
  and Commitment read models use explicit published FX references or return
  `NO_AGGREGATION`. Mixed-currency Budget approval is not claimed.
* Rate/APU and FX effectivity uses a half-open interval `[effective_from,
  effective_to)`; empty windows and pricing on the exclusive end date are denied.
* Management Reserve is owner-only, project-level and outside the control
  baseline. Contingency is explicitly inside the control baseline, project or
  package level; a reserve is not silently added twice.
  `cost.reserve.manage` is the explicit owner-delegated organizational authority:
  only Organization/Operational Administrators receive it. Ordinary Project,
  Project Controls and Cost Managers do not receive this right from Budget
  approval. Editing or reclassifying an existing Reserve line needs it as well.
* An approved Cost Baseline freezes approved Budget, selected non-reserve lines,
  CBS/code/account structures, effective mapping snapshots and fully reconciled
  phasing. Candidate edits need If-Match; approval needs an independent actor.
* Seven phasing methods are deterministic and sum-exact. Activity-based phasing
  consumes immutable Schedule source dates and hash, never rewrites them. Manual
  and curve inputs must reconcile. Effective phasing uses immutable successor
  rows; approved Baseline phasing cannot be changed.
* O1A controls periods are linked by reference and snapshot; CLOSED/PUBLISHED
  periods are not rewritten, reopened or silently remapped by Cost.
* Financial Actuals, obligations and FX are in `financials.py`; Accrual is
  `DEFERRED_WITH_CONTRACT`. ETC/EAC is an explicit interface only: EAC is recognized
  Actual plus accepted ETC and never adds Commitment again when it is already
  included. No earned progress, physical progress or full forecast governance.

## Command safeguards

`cost.*` granular permissions are explicitly provisioned, never assigned to an
actor by a GET. ADMIN profile editor and publisher are independent. Rate/APU,
Budget and Cost Baseline approvals enforce preparer/approver separation. Every
command has a reason, tenant/workspace authorization, immutable command receipt,
Idempotency-Key and append-only Cost history plus security event. Mutations of
existing aggregates require If-Match. HTTP unknown authority fields are rejected.
Canonical writes are exclusively in this module; legacy data remains unchanged
until an explicitly governed adapter proposal is accepted.

Minimal additive migration 0073 is the sole successor of 0072. It has no silent
backfill and downgrade refuses populated Cost authority. Normal database rollout,
Project 14 mutation, commit/push, production SLA and business acceptance are not
implied by isolated technical validation.

Even with local `AUTO_CREATE_SCHEMA=true`, application startup excludes all
fourteen canonical Cost tables from ORM `create_all`. They can only be created
by Alembic 0073 with its database guards. A normal restart is not a Cost rollout.
