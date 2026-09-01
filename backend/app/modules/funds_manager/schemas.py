"""Typed HTTP contracts for Gate 07J-FUND Funds Manager."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IdempotencyIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class FundingSourceCreateIn(IdempotencyIn):
    source_code: str | None = Field(default=None, min_length=3, max_length=80)
    source_name: str = Field(min_length=3, max_length=180)
    source_type: str = Field(min_length=3, max_length=64)
    description: str = Field(default="", max_length=6000)
    legal_entity_provider_reference: str | None = Field(default=None, max_length=300)
    currency: str = Field(min_length=3, max_length=8)
    effective_from: date | None = None
    effective_to: date | None = None
    restrictions: dict = Field(default_factory=dict)
    evidence_refs: list[dict] = Field(default_factory=list)
    source_reference: str | None = Field(default=None, max_length=300)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("source_type")
    @classmethod
    def normalize_source_type(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self


class FundingSourceUpdateIn(BaseModel):
    source_name: str = Field(min_length=3, max_length=180)
    source_type: str = Field(min_length=3, max_length=64)
    description: str = Field(default="", max_length=6000)
    legal_entity_provider_reference: str | None = Field(default=None, max_length=300)
    currency: str = Field(min_length=3, max_length=8)
    effective_from: date | None = None
    effective_to: date | None = None
    restrictions: dict = Field(default_factory=dict)
    evidence_refs: list[dict] = Field(default_factory=list)
    source_reference: str | None = Field(default=None, max_length=300)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("source_type")
    @classmethod
    def normalize_source_type(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self


class FundingSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    source_code: str
    source_name: str
    source_type: str
    description: str
    legal_entity_provider_reference: str | None
    currency: str
    status: str
    effective_from: date | None
    effective_to: date | None
    restrictions: dict
    evidence_refs: list[dict]
    source_reference: str | None
    source_hash: str
    revision_version: int
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    allowed_actions: list[str]


class PeriodAmountIn(BaseModel):
    period_key: str = Field(min_length=1, max_length=24)
    amount: Decimal = Field(ge=0)
    period_start: date | None = None
    period_end: date | None = None


class FundCreateIn(IdempotencyIn):
    fund_code: str | None = Field(default=None, min_length=3, max_length=80)
    fund_name: str = Field(min_length=3, max_length=180)
    funding_source_id: int | None = Field(default=None, gt=0)
    description: str = Field(default="", max_length=6000)
    currency: str = Field(min_length=3, max_length=8)
    authorized_amount: Decimal = Field(ge=0)
    available_from: date | None = None
    available_to: date | None = None
    period_granularity: str = Field(default="TOTAL")
    authorized_amount_by_period: list[PeriodAmountIn] = Field(default_factory=list)
    restrictions: dict = Field(default_factory=dict)
    applicable_workspace_scope: dict = Field(default_factory=dict)
    evidence_refs: list[dict] = Field(default_factory=list)
    source_reference: str | None = Field(default=None, max_length=300)

    @field_validator("currency", "period_granularity")
    @classmethod
    def normalize_upper(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_periods(self):
        if self.available_from and self.available_to and self.available_to < self.available_from:
            raise ValueError("available_to must be on or after available_from")
        if self.period_granularity not in {"TOTAL", "YEAR", "QUARTER", "MONTH"}:
            raise ValueError("Unsupported period_granularity")
        if self.authorized_amount_by_period:
            total = sum((item.amount for item in self.authorized_amount_by_period), Decimal("0"))
            if total > self.authorized_amount:
                raise ValueError("Period funding cannot exceed authorized_amount")
        return self


class FundUpdateIn(BaseModel):
    fund_name: str = Field(min_length=3, max_length=180)
    funding_source_id: int | None = Field(default=None, gt=0)
    description: str = Field(default="", max_length=6000)
    currency: str = Field(min_length=3, max_length=8)
    authorized_amount: Decimal = Field(ge=0)
    available_from: date | None = None
    available_to: date | None = None
    period_granularity: str = Field(default="TOTAL")
    authorized_amount_by_period: list[PeriodAmountIn] = Field(default_factory=list)
    restrictions: dict = Field(default_factory=dict)
    applicable_workspace_scope: dict = Field(default_factory=dict)
    evidence_refs: list[dict] = Field(default_factory=list)
    source_reference: str | None = Field(default=None, max_length=300)

    @field_validator("currency", "period_granularity")
    @classmethod
    def normalize_upper(cls, value: str) -> str:
        return value.strip().upper()


class FundOut(BaseModel):
    id: int
    tenant_id: int
    fund_code: str
    fund_name: str
    funding_source_id: int | None
    funding_source_name: str | None
    description: str
    currency: str
    authorized_amount: Decimal
    assigned_amount: Decimal
    confirmed_assigned_amount: Decimal
    reserved_assigned_amount: Decimal
    available_amount: Decimal
    available_from: date | None
    available_to: date | None
    period_granularity: str
    authorized_amount_by_period: list[dict]
    assigned_amount_by_period: list[dict]
    available_amount_by_period: list[dict]
    status: str
    restrictions: dict
    applicable_workspace_scope: dict
    evidence_refs: list[dict]
    source_reference: str | None
    fund_hash: str
    revision_version: int
    authorized_by: int | None
    authorized_at: datetime | None
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    allowed_actions: list[str]


class FundingAssignmentCreateIn(IdempotencyIn):
    fund_id: int = Field(gt=0)
    parent_assignment_id: int | None = Field(default=None, gt=0)
    scope_type: str
    portfolio_workspace_id: int | None = Field(default=None, gt=0)
    project_workspace_id: int | None = Field(default=None, gt=0)
    recommended_project_set_hash: str | None = Field(default=None, min_length=64, max_length=64)
    source_convergence_id: int | None = Field(default=None, gt=0)
    source_recommendation_hash: str | None = Field(default=None, min_length=64, max_length=64)
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=8)
    normalized_amount: Decimal | None = Field(default=None, gt=0)
    normalized_currency: str | None = Field(default=None, min_length=3, max_length=8)
    fx_source_reference: str | None = Field(default=None, max_length=300)
    fx_as_of_date: date | None = None
    fx_hash: str | None = Field(default=None, min_length=64, max_length=64)
    period_start: date | None = None
    period_end: date | None = None
    period_profile: list[PeriodAmountIn] = Field(default_factory=list)
    assignment_purpose: str = Field(min_length=3, max_length=6000)
    conditions: list[dict] = Field(default_factory=list)
    evidence_refs: list[dict] = Field(default_factory=list)

    @field_validator("scope_type", "currency")
    @classmethod
    def normalize_upper(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("normalized_currency")
    @classmethod
    def normalize_optional_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope_type == "PORTFOLIO":
            if not self.portfolio_workspace_id or self.project_workspace_id or self.recommended_project_set_hash:
                raise ValueError("PORTFOLIO assignments require only portfolio_workspace_id")
        elif self.scope_type == "PROJECT":
            if not self.project_workspace_id or self.recommended_project_set_hash:
                raise ValueError("PROJECT assignments require project_workspace_id")
        elif self.scope_type == "RECOMMENDED_PROJECT_SET":
            if not (
                self.portfolio_workspace_id
                and self.recommended_project_set_hash
                and self.source_convergence_id
                and self.source_recommendation_hash
            ):
                raise ValueError("RECOMMENDED_PROJECT_SET assignments require governed Gate 07I references")
        else:
            raise ValueError("Unsupported assignment scope")
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        normalized_fields = (
            self.normalized_amount,
            self.normalized_currency,
            self.fx_source_reference,
            self.fx_as_of_date,
            self.fx_hash,
        )
        if any(item is not None for item in normalized_fields) and not all(
            item is not None for item in normalized_fields
        ):
            raise ValueError("Governed normalized funding requires amount, currency, FX source, date and hash")
        return self


class FundingAssignmentUpdateIn(BaseModel):
    amount: Decimal = Field(gt=0)
    period_start: date | None = None
    period_end: date | None = None
    period_profile: list[PeriodAmountIn] = Field(default_factory=list)
    assignment_purpose: str = Field(min_length=3, max_length=6000)
    conditions: list[dict] = Field(default_factory=list)
    evidence_refs: list[dict] = Field(default_factory=list)


class FundingAssignmentOut(BaseModel):
    id: int
    tenant_id: int
    fund_id: int
    fund_code: str
    parent_assignment_id: int | None
    assignment_number: str
    scope_type: str
    portfolio_workspace_id: int | None
    project_workspace_id: int | None
    recommended_project_set_hash: str | None
    source_convergence_id: int | None
    source_recommendation_hash: str | None
    amount: Decimal
    currency: str
    normalized_amount: Decimal | None
    normalized_currency: str | None
    fx_source_reference: str | None
    fx_as_of_date: date | None
    fx_hash: str | None
    period_start: date | None
    period_end: date | None
    period_profile: list[dict]
    status: str
    assignment_purpose: str
    eligibility_status: str
    conditions: list[dict]
    evidence_refs: list[dict]
    assignment_hash: str
    coverage_contribution: Decimal
    warnings: list[str]
    revision_version: int
    prepared_by: int
    confirmed_by: int | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_by: int
    updated_at: datetime
    allowed_actions: list[str]


class FundingReadinessOut(BaseModel):
    snapshot_id: int | None = None
    tenant_id: int
    scope_type: str
    portfolio_workspace_id: int | None
    project_workspace_id: int | None
    source_convergence_id: int | None
    source_recommendation_hash: str | None
    recommended_project_set_hash: str | None
    budget_scenario_id: int | None
    budget_scenario_hash: str | None
    funding_requirement_source: dict
    funding_requirement_hash: str
    required_amount: Decimal
    required_currency: str
    confirmed_funding_amount: Decimal
    reserved_funding_amount: Decimal
    funding_gap: Decimal
    confirmed_coverage_percent: Decimal
    potential_coverage_percent: Decimal
    project_coverage_summary: list[dict]
    period_coverage_summary: list[dict]
    restriction_summary: dict
    conditions_summary: dict
    warnings: list[str]
    blockers: list[str]
    funding_readiness_status: str
    funding_readiness_hash: str
    source_hash: str
    source_current: bool
    can_supply_investment_gate_evidence: bool
    allowed_actions: list[str]
    final_output: str


class FundingOverviewOut(BaseModel):
    portfolio_workspace_id: int | None
    governance_model_applicable: bool
    active_funds: int
    comparable_currency: str | None
    authorized_funding: Decimal | None
    confirmed_assigned: Decimal | None
    reserved_assigned: Decimal | None
    available_funding: Decimal | None
    funding_gap: Decimal | None
    coverage_percent: Decimal | None
    funding_readiness: str
    funding_sources: list[FundingSourceOut]
    funds: list[FundOut]
    assignments: list[FundingAssignmentOut]
    readiness: FundingReadinessOut | None
    boundaries: list[str]


class FundingRefreshPreviewOut(BaseModel):
    portfolio_workspace_id: int
    current_source_hash: str | None
    proposed_source_hash: str
    source_current: bool
    fund_changes: list[dict]
    assignment_changes: list[dict]
    requirement_changes: list[dict]
    coverage_changes: dict
    project_set_changes: list[dict]
    period_gaps: list[dict]
    restriction_changes: list[dict]
    condition_changes: list[dict]
    expiry_changes: list[dict]
    warnings: list[str]
    blockers: list[str]
    persisted: bool = False


class RefreshApplyIn(IdempotencyIn):
    expected_source_hash: str = Field(min_length=64, max_length=64)


class InvestmentGateFundingEvidenceOut(BaseModel):
    source_module: str = "FUNDS_MANAGER"
    evidence_type: str = "FUNDING_READINESS"
    requirement_type: str = "FUNDING_READINESS"
    evidence_origin: str = "GOVERNED_SOURCE"
    scope_type: str
    portfolio_workspace_id: int | None
    project_workspace_id: int | None
    source_recommendation_hash: str | None
    recommended_project_set_hash: str | None
    funding_requirement_source: dict
    funding_requirement_hash: str
    required_amount: Decimal
    required_currency: str
    confirmed_funding_amount: Decimal
    reserved_funding_amount: Decimal
    confirmed_coverage_percent: Decimal
    potential_coverage_percent: Decimal
    project_coverage: list[dict]
    period_coverage: list[dict]
    restriction_status: str
    open_blocking_conditions: int
    funding_readiness_status: str
    funding_readiness_hash: str
    source_current: bool
    can_supply_investment_gate_evidence: bool
    snapshot_id: int | None


class ConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    content_json: dict


class ConfigurationCloneIn(BaseModel):
    configuration_id: int = Field(gt=0)


class ConfigurationPreviewIn(BaseModel):
    portfolio_workspace_id: int | None = Field(default=None, gt=0)
    configuration_id: int | None = Field(default=None, gt=0)
    content_json: dict | None = None
    fund_assumptions: list[dict] = Field(default_factory=list)


class ConfigurationPreviewOut(BaseModel):
    portfolio_workspace_id: int | None
    path: list[dict]
    effective: dict
    source: dict
    funding_requirement: dict | None
    eligible_active_funds: list[dict]
    eligible_assignments: list[dict]
    currency_compatibility: dict
    confirmed_coverage_preview: Decimal | None
    potential_coverage_preview: Decimal | None
    project_coverage: list[dict]
    period_coverage: list[dict]
    restrictions: dict
    conditions: dict
    warnings: list[str]
    blockers: list[str]
    gate07j_funding_evidence_preview: dict | None
    validation_issues: list[str]
    publishable: bool
    persisted: bool = False


class AdminConfigurationRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    kind: str
    code: str
    name: str
    description: str
    status: str
    revision: int
    version: int
    content_json: dict
    content_hash: str
    published_at: datetime | None
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime
