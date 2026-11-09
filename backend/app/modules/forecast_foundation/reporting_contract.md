# O1C reporting read contract

Reporting consumes pinned Forecast and published period snapshots. Dashboard and
Executive views classify CPI, SPI, and calendar-day finish variance using the
selected Forecast's published profile, not the latest editable Admin settings.
The same profile selects the S-Curve series and trend metrics. Trends without a
selected Forecast use the latest published report's pinned profile. Published
facts and prior report revisions are not rewritten by any of these reads.

Readiness percentages require a usable assessment for every included package.
Incomplete or stale assessment coverage is `NOT_COMPUTABLE`, with observed
counts preserved separately. Look-Ahead uses imported dates, float units, and
explicit Schedule/Scope/Plan/Package mappings. A shared Plan or Scope identity
is context, not a new execution assignment. AWP package dependencies and
constraints remain separate from P6 relationships and do not infer a driving
path or recalculate CPM.

`GET /api/v1/reporting/projects/{workspace_id}/analytics-contract` exposes the
versioned read contract. The `trend_event_linkage` object describes future
references to `TREND`, `POTENTIAL_CHANGE`, `RISK`, `ISSUE`, or `CLAIM`. Source
anchors are workspace, period, immutable report ID and content hash, Forecast
version, and metric. The future target is a kind and an external reference.
This is metadata only: O1C does not create those records, validate external
references, implement their workflows, or support analytics write-back.
