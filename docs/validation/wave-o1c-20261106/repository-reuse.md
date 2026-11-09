# O1C reuse audit

Observed before implementation at HEAD19baf10. This is an architecture audit,
not a substitute for executed lifecycle and regression evidence.

| Area | Classification | Treatment |
| --- | --- | --- |
| O1A operational_context | REUSE | Canonical Project authorization, legacy identity binding and common period commands. |
| Scope Foundation | REUSE | Scope and Plan identities, approved denominator, baseline and allocations remain in Scope. |
| Schedule Foundation and P6 | REUSE | Accepted Current, approved baseline, data date, imported dates, float and relationships. No local CPM or P6 writeback. |
| AWP and Readiness | REUSE | Canonical packages, mappings, constraints and persisted assessment references. No automatic Schedule update from constraint state. |
| Cost Foundation | REUSE | Approved budget and baseline, phasing, cost codes, accounts, commitments and recognized Actual. |
| Progress Integration | EXTEND | Consume approved bundle, effective approved measurements, EVM and published immutable period snapshots. Preserve original authority. |
| Generic governed ADMIN editor | EXTEND | Dedicated Forecast profile lifecycle and namespace; retain generic visual components. |
| CompactModuleHeader and workspace navigator | EXTEND | Dedicated Forecast operational page and twelve views, existing scoped navigation. |
| app/services/evm.py and frontend/src/lib/evm.ts | KEEP_BEHIND_ADAPTER | Existing float-based formula projections do not become approved O1C Forecast versions. |
| Legacy ForecastScenario and Control Core | KEEP_BEHIND_ADAPTER | Existing Progress adoption boundary already blocks manual legacy integrated writes and automatic legacy recalculation. Forecast requires approved canonical bundle. |
| ProjectControlsHandbook local CPM and legacy forensic lookahead | KEEP_BEHIND_ADAPTER | Do not use as the O1C Schedule authority or recalculate critical path. |
| Native Power BI connected model | UNKNOWN | No governed connected Power BI semantic model was identified. Publish a versioned read-model contract, not an invented connector. |

## Analytics contract

Read models are projections. The transactional writers remain Scope, Schedule,
Cost, Progress, AWP and Forecast in their dedicated APIs. Analytics consumers
must not call write endpoints to refresh a chart. Immutable report identity,
revision, predecessor, content hash, as_of and pinned source IDs form the
historical refresh key. A live dashboard uses current authorized sources and
may change as they change. A published report remains frozen. A newer report
for the same period is a new revision. Trend selection uses the latest
published revision per period while retaining all prior revisions.

The read-model schema version is separate from the business Forecast revision.
Consumers must reject an unknown schema version, preserve units and currency,
and show NOT_COMPUTABLE with reasons rather than fabricate zero. A refresh
cannot turn current Schedule dates into Forecast or claim a statistical
confidence interval from a qualitative confidence label. Power BI deployment,
credentials and scheduled refresh are outside this increment.
