"""API contracts for Gate 07M-FIN."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class IdempotencyIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class CreateModelIn(IdempotencyIn):
    project_workspace_id: int
    business_case_id: int | None = None
    model_type: str = "COMMERCIAL_PROJECT"
    base_currency: str = Field(default="USD", min_length=3, max_length=8)
    cash_flow_basis: str = "NOMINAL"
    periodicity: str = "MONTHLY"
    model_start_date: date
    model_end_date: date
    construction_start: date
    operations_start: date | None = None
    operations_end: date | None = None
    terminal_date: date | None = None
    budget_scenario_id: int | None = None
    funding_readiness_id: int | None = None
    owner_user_id: int | None = None
    sponsor_user_id: int | None = None


class CreateVersionIn(IdempotencyIn):
    purpose: str


class UpdateVersionIn(BaseModel):
    model_type: str | None = None
    base_currency: str | None = Field(default=None, min_length=3, max_length=8)
    cash_flow_basis: str | None = None
    periodicity: str | None = None
    model_start_date: date | None = None
    model_end_date: date | None = None
    construction_start: date | None = None
    operations_start: date | None = None
    operations_end: date | None = None
    terminal_date: date | None = None


class AssumptionCreateIn(BaseModel):
    assumption_key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=180)
    category: str
    numeric_value: Decimal | None = None
    text_value: str | None = None
    unit: str = ""
    periodicity: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    source: str = "MANUAL"
    source_reference: str | None = None
    rationale: str = ""
    is_override: bool = False


class PeriodCreateIn(BaseModel):
    period_index: int = Field(ge=0)
    period_label: str = Field(min_length=1, max_length=40)
    period_start: date
    period_end: date
    currency: str = Field(min_length=3, max_length=8)
    revenue: Decimal = Decimal("0")
    economic_benefits: Decimal = Decimal("0")
    opex: Decimal = Decimal("0")
    taxes: Decimal = Decimal("0")
    working_capital_change: Decimal = Decimal("0")
    capex: Decimal = Decimal("0")
    debt_drawdown: Decimal = Decimal("0")
    interest: Decimal = Decimal("0")
    principal: Decimal = Decimal("0")
    equity_contribution: Decimal = Decimal("0")
    distribution: Decimal = Decimal("0")
    source_reference: str | None = None
    source_hash: str | None = None


class InstrumentCreateIn(IdempotencyIn):
    instrument_key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=180)
    instrument_type: str
    currency: str = Field(min_length=3, max_length=8)
    committed_amount: Decimal = Field(ge=0)
    drawn_amount: Decimal = Field(default=Decimal("0"), ge=0)
    funding_assignment_id: int | None = None
    interest_basis: str | None = None
    fixed_rate: Decimal | None = None
    reference_rate_key: str | None = None
    spread_rate: Decimal | None = None
    commitment_fee: Decimal | None = None
    upfront_fee: Decimal | None = None
    other_fee: Decimal | None = None
    principal_grace_periods: int = Field(default=0, ge=0)
    interest_grace_periods: int = Field(default=0, ge=0)
    tenor_periods: int | None = Field(default=None, ge=1)
    maturity_date: date | None = None
    drawdown_method: str = "CUSTOM"
    amortization_method: str = "CUSTOM"
    interest_during_construction: str = "CASH_PAY"
    minimum_dscr: Decimal | None = None
    minimum_llcr: Decimal | None = None
    covenants_json: list[dict] = Field(default_factory=list)


class InvestorCreateIn(IdempotencyIn):
    financing_instrument_id: int
    investor_key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=180)
    investor_type: str
    committed_equity: Decimal = Field(ge=0)
    ownership_percent: Decimal | None = Field(default=None, ge=0, le=100)
    preferred_return: Decimal | None = None
    distribution_priority: int | None = None
    capital_call_profile_json: list[dict] = Field(default_factory=list)
    distribution_profile_json: list[dict] = Field(default_factory=list)
    hurdle_rate: Decimal | None = None


class ScenarioCreateIn(IdempotencyIn):
    scenario_key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=180)
    scenario_type: str
    description: str = ""
    is_official: bool = False
    overrides: list[dict] = Field(default_factory=list)


class SensitivityRunIn(IdempotencyIn):
    scenario_id: int
    variable_key: str
    shock_value: Decimal
    target_metric: str = "PROJECT_FINANCIAL_NPV"


class CompleteVersionIn(IdempotencyIn):
    reviewer_user_id: int | None = None


class ConfigurationPreviewIn(BaseModel):
    project_workspace_id: int
    business_case_id: int | None = None
    configuration_id: int | None = None
    content_json: dict | None = None


class ConfigurationUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    content_json: dict


class AssumptionOut(AssumptionCreateIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    model_version_id: int
    created_by: int
    created_at: datetime


class PeriodOut(PeriodCreateIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    model_version_id: int


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    model_version_id: int
    instrument_key: str
    name: str
    instrument_type: str
    currency: str
    committed_amount: Decimal
    drawn_amount: Decimal
    funding_source_id: int | None
    fund_id: int | None
    funding_assignment_id: int | None
    funding_assignment_hash: str | None
    funding_readiness_hash: str | None
    interest_basis: str | None
    fixed_rate: Decimal | None
    reference_rate_key: str | None
    spread_rate: Decimal | None
    commitment_fee: Decimal | None
    upfront_fee: Decimal | None
    other_fee: Decimal | None
    principal_grace_periods: int
    interest_grace_periods: int
    tenor_periods: int | None
    maturity_date: date | None
    drawdown_method: str
    amortization_method: str
    interest_during_construction: str
    minimum_dscr: Decimal | None
    minimum_llcr: Decimal | None
    covenants_json: list[dict]
    readiness_status: str
    created_at: datetime


class InvestorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    model_version_id: int
    financing_instrument_id: int
    investor_key: str
    name: str
    investor_type: str
    committed_equity: Decimal
    ownership_percent: Decimal | None
    preferred_return: Decimal | None
    distribution_priority: int | None
    capital_call_profile_json: list[dict]
    distribution_profile_json: list[dict]
    hurdle_rate: Decimal | None
    total_contributions: Decimal
    total_distributions: Decimal
    equity_irr: Decimal | None
    moic: Decimal | None
    status: str
    created_at: datetime


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    model_version_id: int
    scenario_key: str
    name: str
    scenario_type: str
    is_official: bool
    description: str
    status: str
    output_summary_json: dict
    scenario_hash: str
    created_at: datetime


class CashFlowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scenario_id: int
    period_id: int
    period_index: int
    revenue: Decimal
    economic_benefits: Decimal
    opex: Decimal
    taxes: Decimal
    working_capital_change: Decimal
    capex: Decimal
    unlevered_project_cf: Decimal
    cfads: Decimal
    debt_drawdown: Decimal
    interest: Decimal
    principal: Decimal
    equity_contribution: Decimal
    distribution: Decimal
    cash_flow_to_equity: Decimal
    row_hash: str


class MetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scenario_id: int
    metric_key: str
    numeric_value: Decimal | None
    status_value: str | None
    unit: str
    formula_version: str
    input_references_json: list[dict]
    trace_hash: str


class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_id: int
    version_number: int
    version_label: str
    purpose: str
    status: str
    model_type: str
    base_currency: str
    cash_flow_basis: str
    periodicity: str
    model_start_date: date
    model_end_date: date
    construction_start: date
    operations_start: date | None
    operations_end: date | None
    terminal_date: date | None
    as_of_date: datetime
    business_case_revision_id: int
    business_case_hash: str
    budget_scenario_id: int | None
    budget_scenario_hash: str | None
    funding_readiness_id: int | None
    funding_readiness_hash: str | None
    source_references_json: dict
    source_hashes_json: dict
    source_snapshot_hash: str
    total_investment_requirement: Decimal
    total_model_financing: Decimal
    governed_funding_assigned: Decimal
    funding_gap: Decimal
    funding_reconciliation_status: str
    project_financial_npv: Decimal | None
    project_irr: Decimal | None
    economic_npv: Decimal | None
    economic_irr: Decimal | None
    benefit_cost_ratio: Decimal | None
    simple_payback: Decimal | None
    discounted_payback: Decimal | None
    equity_irr: Decimal | None
    moic: Decimal | None
    minimum_dscr: Decimal | None
    average_dscr: Decimal | None
    llcr: Decimal | None
    debt_to_equity: Decimal | None
    economic_readiness: str
    financial_model_readiness: str
    funding_reconciliation_readiness: str
    debt_readiness: str
    equity_readiness: str
    covenant_readiness: str
    scenario_readiness: str
    overall_readiness: str
    warnings_json: list[str]
    blockers_json: list[str]
    source_current: bool
    readiness_hash: str
    model_hash: str
    calculation_engine_version: str
    calculation_trace_json: list[dict]
    preparer_user_id: int
    reviewer_user_id: int | None
    submitted_at: datetime | None
    completed_at: datetime | None
    completed_by: int | None
    revision_version: int
    created_at: datetime
    updated_at: datetime


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_number: str
    project_workspace_id: int
    business_case_id: int
    owner_user_id: int
    sponsor_user_id: int | None
    status: str
    current_version_id: int | None
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    configuration_source_workspace_id: int | None
    configuration_resolution_chain_json: list[dict]
    revision_version: int
    created_at: datetime
    updated_at: datetime
    current_version: ModelVersionOut | None
    final_output: str
    next_process: str


class ReadinessOut(BaseModel):
    model_id: int
    model_version_id: int
    status: str
    dimensions: dict[str, str]
    warnings: list[str]
    blockers: list[str]
    source_current: bool
    readiness_hash: str
    final_output: str
    persisted: bool


class RefreshPreviewOut(BaseModel):
    model_id: int
    current_version_id: int
    source_changes: list[dict]
    impacted_sections: list[str]
    proposed_purpose: str
    persisted: bool = False


class ProviderEvidenceOut(BaseModel):
    provider_key: str
    source_module: str
    evidence_type: str
    project_workspace_id: int
    business_case_id: int
    business_case_revision_id: int
    business_case_hash: str
    economic_financial_model_id: int
    model_version_id: int
    model_version: int
    model_type: str
    base_currency: str
    as_of_date: datetime
    model_hash: str
    project_financial_npv: Decimal | None
    project_irr: Decimal | None
    economic_npv: Decimal | None
    economic_irr: Decimal | None
    benefit_cost_ratio: Decimal | None
    equity_irr: Decimal | None
    moic: Decimal | None
    minimum_dscr: Decimal | None
    llcr: Decimal | None
    debt_to_equity: Decimal | None
    total_investment_requirement: Decimal
    total_model_financing: Decimal
    governed_funding_assigned: Decimal
    funding_gap: Decimal
    funding_reconciliation_status: str
    economic_readiness: str
    financial_model_readiness: str
    debt_readiness: str
    equity_readiness: str
    covenant_readiness: str
    overall_readiness: str
    scenario_summary: list[dict]
    warnings: list[str]
    blockers: list[str]
    source_current: bool
    can_supply_investment_gate_evidence: bool


class ConfigurationPreviewOut(BaseModel):
    persisted: bool = False
    effective_requirements: dict
    applicable_metrics: list[str]
    required_assumptions: list[str]
    funding_linkage_requirements: dict
    thresholds: dict
    readiness_preview: str
    warnings: list[str]
    blockers: list[str]
    publishable: bool
