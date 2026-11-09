# O1C Forecast, Performance & Reporting

This module is an additive projection authority over the existing O1A/O1B
contracts. It does not replace Scope quantities, Plan Items, AWP packages,
Primavera P6 Schedule, Cost, approved Progress or their baselines.

## Canonical source and persistence contract

`ForecastVersion` owns a complete, versioned aggregate of attributed
`ForecastAssumption` and `ForecastComponent` rows. Four component families are
kept separate: COST, TIME, MILESTONE and RESOURCE. Commands append
`ForecastHistory`; reporting owns two additional immutable snapshot tables.

The explicit Alembic migration 0075 creates these six tables. They are excluded
from application `create_all`. On an unmigrated database the module returns
`409 FORECAST_MIGRATION_REQUIRED`; GET never provisions permissions or adopts a
project. The normal user database is not migrated by fixture scripts.

Source inputs include the approved Progress Control Baseline Bundle, pinned
Scope/Schedule/Cost baselines, the accepted **Current** imported Schedule,
effective mappings, period and Data Date, recognized Cost actuals, reconciled
obligations, approved Progress, AWP constraints/readiness and effective ADMIN
policy. IDs, revisions, hashes and the source projection are stored together.
An accepted Current can differ from the historical Schedule baseline without
changing that baseline. Approval detects source/policy/mapping drift.

## Commands and lifecycle

HTTP namespace: `/api/v1/forecast`.

- `GET /projects/{id}/overview`, `/versions`, `/versions/{id}` and `/history`
  are scoped read models; `input_json` on version detail is the strict editable
  aggregate. Overview exposes only the tenant's users and Project-scoped refs.
- `POST /projects/{id}/versions` creates DRAFT. `PUT /versions/{id}` replaces
  the DRAFT aggregate, preserving earlier inputs in append-only history.
- `POST /versions/{id}/calculate` persists an explicit calculation and source
  snapshot. `GET /versions/{id}/calculation` previews a draft without writes;
  approved/rejected versions always return their frozen calculation.
- `POST /versions/{id}/transition` accepts `review`, `approve`, or `reject`.
  Approval requires a previously calculated, unchanged, computable basis and
  an independent actor, distinct from both preparer and last material editor.
- `POST /versions/{id}/successor` derives the next DRAFT from the latest
  approved version without an existing successor. Repeated competing requests
  return 409 instead of relying on a uniqueness/trigger failure. The original
  approved record is not edited; effective SUPERSEDED status is derived.
- ADMIN profile create/edit/publish/successor routes live under
  `/admin/profiles`. Publication is independent from author and last editor.

Mutations require an Idempotency-Key. Existing-record mutations also require
If-Match. Project/tenant isolation, scoped permissions, ORM guards and migration
SQL guards protect the aggregate, immutable approvals and append-only history.
Catalog provisioning is explicit, organization-admin scoped, reasoned and
audited; it never assigns a role to an actor. Source prerequisites are read-only.

An OPEN/REVIEW period supports preparation and approval. Reporting publication
requires the upstream PUBLISHED period. A published-period correction requires
an explicitly permitted Forecast successor with reason/evidence, followed by a
new report revision; it never reopens or mutates the old Progress snapshot.

## Calculation bases

All financial arithmetic uses finite bounded Decimal values (8 decimal places).
Missing/incompatible inputs produce NOT_COMPUTABLE with reason codes and null
metrics, not a plausible zero. Actual recognition is read independently of EVM:
missing EV does not erase a valid recognized Actual amount.

Eight governed COST methods are implemented:

| Method | Explicit basis |
| --- | --- |
| BOTTOM_UP | Attributed remaining amount assumption |
| QUANTITY_RATE | Approved remaining quantity, or explicit quantity assumption, times attributed unit rate |
| ACTIVITY_REMAINING_DURATION | Mapped accepted activity plus explicit duration-unit and compatible rate assumptions |
| PRODUCTIVITY_BASED | Remaining quantity divided by units/day, times compatible daily rate |
| COMMITMENT_BASED | Verified ADDITIVE_ONCE obligation less explicitly linked recognized incurred actuals |
| CONTROL_ACCOUNT | Attributed remaining amount attached to an approved control account |
| TREND_BASED | Earlier approved Forecast ETC and explicit ratio assumption |
| MANUAL_GOVERNED | Attributed remaining amount with owner/source/date/confidence/evidence |

ETC is the sum of disjoint committed, uncommitted and optional allowance
components. EAC = recognized Actual + ETC. VAC = approved Cost Baseline BAC -
EAC. Commitments are not added again to EAC. Reused commitment/actual IDs,
ambiguous incurred allocation, control/currency mismatch and overlapping cost
coverage are blocked. Commitment objects expose only financial dimensions, so
Scope lineage is checked against the approved Cost baseline while incurred
matching uses the actual financial dimensions (account/CBS/cost code).

Current Budget, original Budget, Cost Baseline, Actual, commitment, ETC and EAC
remain distinct. Group views project ETC by account/CBS/code/Scope/Plan/package/
WBS without inventing Actual allocations. Optional `inputs.phasing` points
`{date, amount, currency?}` must fall after as-of and sum exactly to component
ETC; otherwise a Forecast Cost curve is not claimed.

TIME uses imported accepted P6 finish dates or explicit governed manual date
assumptions. It never adds P6 working duration to calendar dates, calculates
CPM, levels resources or changes relationships. An explicit activity override
does not discard dates of other unmodified Current activities. Milestones keep
their independent forecast dates/types; dates and calendar-day variances are
projections rather than a P6 recalculation.

RESOURCE components use PRODUCTIVITY_BASED with an explicit unit basis:
hours/unit gives hours; units/day gives days, or person-days when an explicit
crew-size assumption is provided. Crew conversion is not applied silently to
hours/unit. Labor, equipment, crew, engineering, construction and Project
Controls hours stay grouped by resource type **and unit**. Productivity source,
planned/actual reference assumptions and forecast value remain separate.
Confidence labels LOW/MEDIUM/HIGH are qualitative; no statistical interval or
Monte Carlo result is invented. DRAFT defaults do not claim completeness or
assumption maturity has been assessed.

## Legacy classification

`app/services/evm.py`, frontend legacy EVM calculations/cards and local
ProjectControlsHandbook CPM/lookahead utilities are **KEEP_BEHIND_ADAPTER**.
They are not the O1C Forecast authority. O1BD canonical adoption already prevents
the legacy integrated cycle from becoming an alternative write path for these
Projects. No App.tsx redesign, historical migration edit, source rewrite,
payments/treasury engine, accounting subsystem or scheduling engine is added.

## Evidence and fixtures

Pure policy tests and isolated PostgreSQL/API tests cover deterministic methods,
source compatibility, independent approval, ETags/idempotency, immutability,
successors, rejected records, source-only role prerequisites, recognized Actual
versus incurred commitment, resource units, as-of and Current/baseline separation.
Reporting tests live in their separate `test_forecast_reporting_*` files.

Fixtures require exactly `o1c`/`o1c_browser` and
`PYPMIS_O1C_FIXTURE=disposable-only`. The browser helper reuses real upstream
IFC/P6 import and approval cycles, exports independent disposable actors and
leaves Forecast policy publication to the ADMIN UI. `--larger-current` imports
and accepts 36 activities without changing the pinned baseline or its AWP
package mappings. Explicit Plan/Scope links provide contextual package joins;
only the separate constraint mappings and dated readiness assessments are
added. The fixture verifies that the approved bundle's hash still matches its
live validation. Forecast readiness uses the latest persisted assessment for
each package at or before the forecast business date, with UNKNOWN when none
exists. It does not infer historical release from the live package register;
source drift is exposed by comparing material hashes. Fixture/UAT
success is technical evidence, not an authorized business signature or a claim
that the entire operational macroprocess is finished.
