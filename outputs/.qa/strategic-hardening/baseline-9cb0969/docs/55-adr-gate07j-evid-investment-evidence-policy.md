# ADR 55 — Gate 07J-EVID Investment Decision Evidence Policy

- Status: Accepted
- Date: 2026-08-30
- Decision gate: Gate 07J-EVID
- Functional output: `READY_FOR_INVESTMENT_DECISION_EVIDENCE_POLICY`
- Release status: `GATE07J_EVID_POLICY_VALIDATED`

## Context

Gate 07J owns Investment Gate Preparation and package readiness. Gate 07I, Gate 07G/07G-A, Gate 07H, Gate 07J-FEL
and Gate 07J-FUND already expose governed decision inputs. The missing governance layer is a contextual policy that
states which evidence is required for each Gate Profile, Governance Model and Project Type without creating another
readiness engine or silently treating an unavailable source as a manual document.

## Decision

Reuse `AdminConfiguration` for the versioned policy and keep the provider registry code-backed. The schema head remains
`20260830_0052`; Gate 07J-EVID requires no migration. A new Gate 07J Preparation snapshots the published policy revision,
hash, effective A/B/C requirements, Project Type resolutions and provider registry. Existing Preparations retain their
original snapshot, hashes and evidence.

The classifications are exclusive:

- **A — GOVERNED_SOURCE_REQUIRED:** an AVAILABLE, contract-valid, scope-compatible, current provider must resolve the
  evidence. Manual evidence is prohibited and a missing source produces `SOURCE_PROVIDER_MISSING`.
- **B — GOVERNED_EVIDENCE_SUFFICIENT:** controlled evidence is permitted but remains `SUBMITTED` until independently
  validated. Scope and expiration rules still apply.
- **C — NOT_REQUIRED:** no item, blocker or warning is required.

The default policy applies only to `CAPITAL_OWNER`. `CONTRACTOR_DELIVERY`, `DIRECT_INTERNAL` and legacy governance
resolve to C unless a published policy explicitly includes them. Mixed Project Sets resolve `EACH_PROJECT` requirements
per Project and never collapse Project Types.

## Governed provider inventory

| Evidence | Provider | Status | Scope |
|---|---|---|---|
| Portfolio Recommendation | `GATE07I_PORTFOLIO_RECOMMENDATION` | AVAILABLE | Portfolio / Project Set |
| Budget Feasibility | `GATE07G_BUDGET_FEASIBILITY` | AVAILABLE | Portfolio / Project Set |
| Resource Feasibility | `GATE07H_RESOURCE_FEASIBILITY` | AVAILABLE | Portfolio / Project Set |
| Project Definition, FEL, PDRI, Cost Estimate | `GATE07J_FEL_PROJECT_DEFINITION` | AVAILABLE | Each / Selected Projects |
| Funding Readiness | `GATE07J_FUND_FUNDING_READINESS` | AVAILABLE | Portfolio / Project Set |
| Risk Readiness | `RISK_READINESS_PROVIDER` | UNAVAILABLE | Reserved only |
| Permit Readiness | `PERMIT_READINESS_PROVIDER` | UNAVAILABLE | Reserved only |

An AVAILABLE contract must contain `evidence_type`, `scope`, `readiness_status`, `source_current`, `evidence_hash`,
`as_of_date`, `warnings` and `blockers`. Missing fields produce `PROVIDER_CONTRACT_INVALID`; unsupported scope produces
`SCOPE_UNSUPPORTED`; `source_current=false` produces `SOURCE_STALE`.

## Required evidence-domain decisions

| Evidence | Gate Profile | Project Type | Class | Provider / status | Scope | Blocking | Validity | Coverage | Rationale | Next action |
|---|---|---|---|---|---|---:|---:|---:|---|---|
| Risk Readiness | PYP-INV-SELECT | All CAPITAL_OWNER | B | Controlled evidence | Project Set | No | 90 d | Contextual | Selection can rely on validated evidence while risk is still evolving. | Use validated governed evidence. |
| Risk Readiness | PYP-FFA | All CAPITAL_OWNER | A | `RISK_READINESS_PROVIDER` / UNAVAILABLE | Project Set | Yes | 90 d | 100% | FFA needs structured, current, aggregable risk readiness whose changes invalidate readiness. | Build the missing governed Risk provider. |
| Permit Readiness | PYP-INV-SELECT | All CAPITAL_OWNER | B | Controlled evidence | Each Project | No | 180 d | 80% | A controlled permit status reference is sufficient at selection. | Use validated governed evidence. |
| Permit Readiness | PYP-FFA | Non-Mining CAPITAL_OWNER | B | Controlled evidence | Each Project | Yes | 180 d | 100% | Validated permit evidence is sufficient for the base FFA profile. | Use validated governed evidence. |
| Permit Readiness | PYP-FFA | Mining CAPITAL_OWNER | A | `PERMIT_READINESS_PROVIDER` / UNAVAILABLE | Each Project | Yes | 180 d | 100% | Mining FFA needs structured current permit status; manual evidence cannot substitute it. | Build after the higher-priority Risk provider. |
| Contracting Strategy | PYP-INV-SELECT | All CAPITAL_OWNER | B | Controlled evidence | Each Project | No | 365 d | 80% | A governed strategy document is sufficient. | Do not create a Procurement engine. |
| Contracting Strategy | PYP-FFA | All CAPITAL_OWNER | B | Controlled evidence | Each Project | Yes | 365 d | 100% | Independent validation makes the strategy reference decision-grade. | Reuse controlled evidence. |
| Execution Plan | PYP-INV-SELECT | All CAPITAL_OWNER | B | Controlled evidence | Each Project | No | 365 d | 80% | A governed Project Execution Plan reference is sufficient. | Do not create an execution engine. |
| Execution Plan | PYP-FFA | All CAPITAL_OWNER | B | Controlled evidence | Each Project | Yes | 365 d | 100% | FFA requires complete validated coverage but not a separate engine. | Reuse controlled evidence. |
| Schedule Maturity | PYP-INV-SELECT | All CAPITAL_OWNER | B | Controlled evidence | Each Project | No | 180 d | 80% | A controlled maturity assessment is sufficient at selection. | Do not create a CPM engine. |
| Schedule Maturity | PYP-FFA | All CAPITAL_OWNER | B | Controlled evidence | Each Project | Yes | 180 d | 100% | Validated maturity evidence is sufficient for FFA. | Reuse controlled evidence. |
| Cost Estimate Maturity | PYP-INV-SELECT | All CAPITAL_OWNER | B | Controlled evidence | Each Project | No | 180 d | 80% | Selection may accept validated estimate maturity evidence. | Reuse controlled evidence. |
| Cost Estimate Maturity | PYP-FFA | All CAPITAL_OWNER | A | `GATE07J_FEL_PROJECT_DEFINITION` / AVAILABLE | Each Project | Yes | 180 d | 100% | FEL already owns the structured estimate maturity source. | Reuse FEL; never duplicate it. |
| Environmental/Social | PYP-INV-SELECT | All CAPITAL_OWNER | C | Not required | Each Project | No | — | — | Not required by the starter selection policy. | No action. |
| Environmental/Social | PYP-FFA | All CAPITAL_OWNER | B | Controlled evidence | Each Project | No | 180 d | 100% | Validated evidence is sufficient until policy explicitly requires a source. | Reuse controlled evidence. |
| Land Access | PYP-INV-SELECT | All CAPITAL_OWNER | C | Not required | Each Project | No | — | — | Not required by the starter selection policy. | No action. |
| Land Access | PYP-FFA | All CAPITAL_OWNER | B | Controlled evidence | Each Project | No | 180 d | 100% | Validated land-access evidence is sufficient at FFA. | Reuse controlled evidence. |

## Reuse decisions

- Project dependencies and unmet dependencies remain detail in the Gate 07G/07G-A Budget source summary; no separate
  evidence type is introduced.
- CAPEX, EXPENSE and UNCLASSIFIED remain Budget Feasibility detail and may support funding restrictions; they do not
  become separate evidence domains.
- Cost Estimate Maturity at FFA reuses Gate 07J-FEL. Schedule Maturity starts as Class B and does not create a Schedule
  Manager.
- Gate 07J remains the sole Preparation/readiness owner. Gate 07J-EVID resolves policy and providers only.

## Lifecycle, security and concurrency

Policies use `DRAFT → PUBLISHED → SUPERSEDED`; published content is immutable. Draft writes require ETag/`If-Match`
and stale writes return `412 ETAG_MISMATCH`. Clone, update, publish and supersede actions emit `SecurityEvent` records.
RBAC is separated into read, configure, publish and provider-read permissions, with administrator and viewer roles.
ADMIN preview is a dry run (`persisted=false`) and never creates a Preparation, Evidence Item, Investment Decision or
FID.

## Final gap analysis

### AVAILABLE GOVERNED SOURCES

`PORTFOLIO_RECOMMENDATION`, `BUDGET_FEASIBILITY`, `RESOURCE_FEASIBILITY`, `PROJECT_DEFINITION_READINESS`,
`FEL_STAGE_READINESS`, `PDRI_OR_DEFINITION_ASSESSMENT`, `FUNDING_READINESS`, `COST_ESTIMATE_MATURITY` (FFA via FEL).

### MISSING GOVERNED SOURCES

`RISK_READINESS` for PYP-FFA; `PERMIT_READINESS` for PYP-FFA + Mining.

### GOVERNED EVIDENCE SUFFICIENT

`RISK_READINESS` (PYP-INV-SELECT), base `PERMIT_READINESS`, `CONTRACTING_STRATEGY_READINESS`,
`EXECUTION_PLAN_READINESS`, `SCHEDULE_MATURITY`, selection `COST_ESTIMATE_MATURITY`, FFA
`ENVIRONMENTAL_SOCIAL_READINESS`, FFA `LAND_ACCESS_READINESS`, `STAKEHOLDER_READINESS`, `TECHNICAL_ASSURANCE`.

### NOT REQUIRED

Selection `ENVIRONMENTAL_SOCIAL_READINESS`, `LAND_ACCESS_READINESS`, `STAKEHOLDER_READINESS`,
`TECHNICAL_ASSURANCE`, `OTHER_GOVERNED_EVIDENCE`, and all starter requirements for governance models outside
`CAPITAL_OWNER`.

## Deterministic next step

`NEXT = BUILD_MISSING_GOVERNED_PROVIDER`

`provider = RISK_READINESS_PROVIDER`

Risk is the first blocking Class A gap for PYP-FFA and therefore precedes the Mining Permit provider. This ADR does not
begin either implementation.

## Guardrails

No Risk, Permit, Contracting, Execution Plan, Schedule or Cost Estimate manager is created. No Investment Decision,
FID, GO/HOLD/RECYCLE/KILL, Project initialization, activation or execution is introduced.
