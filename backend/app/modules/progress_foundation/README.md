# Progress Foundation

Progress is the writer of operational measurements, certification and approval.
It consumes Scope, Plan, AWP, accepted Schedule, Cost and O1A period identities
without changing any of those sources. Baseline Bundle, EVM, reporting snapshots
and the 4D comparison are implemented by the companion `integration` service.

## Reuse inventory

| Existing capability | Decision | Progress use |
| --- | --- | --- |
| O1A canonical Project Workspace, authorization and Project Controls Period | REUSE | Same identity, tenant scope, independent date semantics and period lifecycle. No competing period table writer. |
| Scope Item, approved Scope Baseline, published Plan and immutable allocated quantities | REUSE | Frozen denominator, nature, unit and source revision. No new quantity master. |
| AWP Work Packages, typed methods, mapping history and readiness | REUSE | Subject and mapping references. READY and RELEASED never imply completed work. |
| Accepted Schedule Version, Activity identity and P6 percent-complete fields | REUSE | Separate Schedule Progress projection. No CPM, date or float write-back. |
| Cost Baseline, budget lines, Control Accounts and recognized Actual | REUSE | Explicit package allocations, governed weights, Cost Progress and later EVM references. No Cost writer. |
| Existing 4D Model and immutable IFC geometry | EXTEND | Companion comparison overlay, keeping planned state distinct from approved physical state. |
| Legacy ProgressRecord, manual ControlAccount EV, BIM progress and period reports | KEEP_BEHIND_ADAPTER | Candidate or legacy reporting data. Not automatically approved canonical Physical or Earned Progress. |
| Legacy integrated-control approval and generated EVM totals | DEPRECATION_CANDIDATE behind adapter | No adoption as PV/EV/AC authority; canonical bundle and governed Progress supply the new read model. |
| Legacy S-curves and dashboards | KEEP_BEHIND_ADAPTER | Companion curves derive from canonical snapshots. No replacement of executive reporting or Forecast workflow. |

## Explicit semantics

- Persisted measurement types are QUANTITY, PHYSICAL, MILESTONE and WEIGHTED.
  SCHEDULE and COST are separately named read projections over their canonical
  authorities. EARNED is derived by the integrated approved bundle/EVM service.
  These seven types are not aliases for one editable percentage.
- `progress_value` is a Decimal percentage from 0 to 100. Quantity overrun keeps
  its uncapped value above 100 with `overrun=true`; it does not become suitable
  Earned Value by silently clipping to 100. Normal physical percentages are
  bounded. All Numeric inputs and outputs retain eight decimal places.
- `numerator`, `denominator` and `unit` describe the calculation basis.
  `cumulative_quantity` is the cumulative numerator. `period_quantity` is the
  increment from the previous approved reporting period in the same unit.
  `period_progress` is an increment in percentage points, not a cumulative
  percentage. Methods that operate in percentages have the explicit `%` unit.
- Quantity denominators come from approved Scope snapshots, compatible
  published Plan allocations, package allocations frozen in an approved Cost
  Baseline, or an explicit independently published measurement basis. Simple
  package membership never means allocation of the entire Scope quantity.
  Mixed Plan units/natures require selecting the specific Scope allocation.
- The approved denominator and Scope Baseline identity/hash cannot change in
  place or silently inside a correction chain. New control basis requires an
  explicit new governed measurement/bundle context.
- Nature semantics are explicit: INSTALL, REMOVE, TEMPORARY install/use/remove,
  and MAINTENANCE intervention/restoration. Methods are configured by nature,
  Scope type and package type. There is no universal denominator for all nature.
- Rules of Credit, step rules and milestone rules have separately versioned
  steps that sum to 100. Sequential credit is checked unless the published rule
  explicitly declares unordered milestones. Published rules are immutable and
  publication is independent of creator and last material editor.
- Manual weights only take effect after independent measurement approval.
  Quantity and Budget weights must equal the governed source value. Labor,
  engineering-hour and contract-value weights require an explicit independently
  published basis and source reference. Relabeling an arbitrary number is not
  accepted as a governed weight. No legal obligation or cost ledger is created.
  Quantity weight units and Budget weight currencies must match across a
  weighted result; a quantity of concrete is not summed with a count of items.
  Explicit Control Account references must match every selected source through
  allocations frozen in the current approved Cost Baseline.
- Weighted components must be effective approved compatible measurements of
  the same period, as-of and Scope Baseline. Weights cannot be overridden.
  Overlapping work reached through Scope/Plan/Package mappings is rejected.
  Aggregations consume latest cumulative snapshots rather than adding periods.
- Evidence is required for capture, certification and negative correction.
  Evidence supports a human decision and is not authority on its own. A negative
  correction needs enabled policy, a correction kind and a reason; cumulative
  completion cannot become negative. Real rework is not forced to be monotonic.
- Lifecycle is DRAFT, SUBMITTED, UNDER_REVIEW, APPROVED or REJECTED. An approved
  successor computes effective SUPERSEDED status while preserving the original
  row. A preparer/material editor cannot review or approve their own work;
  recorder and certifier are independent. Quantity/rule-based work requires
  certification before approval. Manual expert assessment requires independent
  review and approval, never automatic Schedule or invoice conversion.
- OPEN permits capture and DRAFT editing. REVIEW accepts only frozen candidate
  IDs and stable content hashes for certification/review/approval. CLOSED and
  PUBLISHED reject measurement writes; O1A remains period authority. Reopen uses
  a successor period, not mutation of published history.
- Measurement date, as-of, cutoff, Schedule Data Date and Cost recognition date
  are preserved separately. Measurement date belongs to its reporting period;
  as-of cannot precede the measured date. No equality is imposed with cutoff or
  source data dates. A Schedule Data Date later than the requested as-of returns
  NOT_COMPUTABLE rather than leaking a future P6 result into earlier reporting.
  Cost expenditure ratios outside 0–100 preserve `raw_ratio` and variance but
  return NOT_COMPUTABLE with no normal `progress_value`; they are never capped
  or translated into physical completion.
- Read-only freshness returns CURRENT or REQUIRES_REVIEW when baseline, profile,
  mapping, Activity identity, governed weight or an approved component changes.
  It never rewrites an approved measurement on GET.

## Security and delivery boundary

`progress.*` catalogs are provisioned explicitly and never assign actors from a
GET. Mutations require scoped authenticated permissions, reason, actor-bound
idempotency and If-Match for existing aggregates. Every accepted revision is
audited in append-only ProgressHistory and SecurityEvent. The shared tenant
command lock serializes duplicate approvals and aggregate commands.

Migration, real PostgreSQL and browser release proof belong to the root release
work. This increment does not imply normal database rollout, signatures, commit
or push. It stops before full Forecast, ETC/EAC governance, procurement,
accounting, treasury and executive reporting.
