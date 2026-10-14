"""Typed contracts for Gate 07J-RISK."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RiskCreateIn(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(default="", max_length=6000)
    risk_category: str = Field(min_length=2, max_length=60)
    identified_date: date
    risk_owner_id: int | None = Field(default=None, gt=0)
    cause: str = Field(default="", max_length=4000)
    event: str = Field(default="", max_length=4000)
    impact_description: str = Field(default="", max_length=4000)
    likelihood_before: int | None = Field(default=None, ge=1, le=5)
    impact_before: int | None = Field(default=None, ge=1, le=5)
    treatment_required: bool = False
    treatment_strategy: str | None = Field(default=None, pattern="^(AVOID|REDUCE|TRANSFER|ACCEPT)$")
    treatment_description: str | None = Field(default=None, max_length=6000)
    treatment_owner_id: int | None = Field(default=None, gt=0)
    target_treatment_date: date | None = None
    treatment_status: str | None = Field(default=None, pattern="^(OPEN|IN_PROGRESS|COMPLETED|CANCELLED)$")
    likelihood_after: int | None = Field(default=None, ge=1, le=5)
    impact_after: int | None = Field(default=None, ge=1, le=5)
    residual_acceptance_required: bool = False
    due_date: date | None = None
    source_reference: str | None = Field(default=None, max_length=300)
    evidence_refs: list[dict] = Field(default_factory=list, max_length=100)
    idempotency_key: str = Field(min_length=8, max_length=160)


class RiskUpdateIn(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(default="", max_length=6000)
    risk_category: str = Field(min_length=2, max_length=60)
    identified_date: date
    risk_owner_id: int | None = Field(default=None, gt=0)
    cause: str = Field(default="", max_length=4000)
    event: str = Field(default="", max_length=4000)
    impact_description: str = Field(default="", max_length=4000)
    likelihood_before: int | None = Field(default=None, ge=1, le=5)
    impact_before: int | None = Field(default=None, ge=1, le=5)
    treatment_required: bool = False
    treatment_strategy: str | None = Field(default=None, pattern="^(AVOID|REDUCE|TRANSFER|ACCEPT)$")
    treatment_description: str | None = Field(default=None, max_length=6000)
    treatment_owner_id: int | None = Field(default=None, gt=0)
    target_treatment_date: date | None = None
    treatment_status: str | None = Field(default=None, pattern="^(OPEN|IN_PROGRESS|COMPLETED|CANCELLED)$")
    likelihood_after: int | None = Field(default=None, ge=1, le=5)
    impact_after: int | None = Field(default=None, ge=1, le=5)
    residual_acceptance_required: bool = False
    due_date: date | None = None
    source_reference: str | None = Field(default=None, max_length=300)
    evidence_refs: list[dict] = Field(default_factory=list, max_length=100)


class RiskStatusIn(BaseModel):
    status: str = Field(pattern="^(DRAFT|OPEN|UNDER_TREATMENT|MONITORING|CLOSED|VOIDED)$")


class RiskAcceptanceIn(BaseModel):
    acceptance_comment: str = Field(min_length=5, max_length=4000)
    acceptance_authority_level: str = Field(min_length=2, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=160)


class ProjectRiskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    project_workspace_id: int
    risk_number: str
    title: str
    description: str
    risk_category: str
    status: str
    identified_date: date
    risk_owner_id: int | None
    cause: str
    event: str
    impact_description: str
    likelihood_before: int | None
    impact_before: int | None
    inherent_rating: str | None
    treatment_required: bool
    treatment_strategy: str | None
    treatment_description: str | None
    treatment_owner_id: int | None
    target_treatment_date: date | None
    treatment_status: str | None
    likelihood_after: int | None
    impact_after: int | None
    residual_rating: str | None
    residual_acceptance_required: bool
    accepted_by: int | None
    accepted_at: datetime | None
    acceptance_comment: str | None
    acceptance_authority_level: str | None
    due_date: date | None
    source_reference: str | None
    evidence_refs_json: list[dict]
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    revision_version: int


class AssessmentCreateIn(BaseModel):
    as_of_date: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=160)


class AssessmentUpdateIn(BaseModel):
    as_of_date: datetime


class AssessmentActionIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class RiskReadinessAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    project_workspace_id: int
    assessment_number: str
    assessment_version: int
    as_of_date: datetime
    valid_until: datetime
    status: str
    risk_register_hash: str
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    total_active_risks: int
    high_risk_count: int
    critical_risk_count: int
    risks_without_owner: int
    risks_without_treatment: int
    overdue_treatments: int
    residual_high_count: int
    residual_critical_count: int
    risks_requiring_acceptance: int
    risks_without_acceptance: int
    evidence_coverage_percent: float
    warnings_json: list[str]
    blockers_json: list[str]
    readiness_status: str
    risk_readiness_hash: str | None
    assessed_by: int
    completed_by: int | None
    completed_at: datetime | None
    revision_version: int


class ProjectReadinessOut(BaseModel):
    project_workspace_id: int
    assessment_id: int | None
    assessment_hash: str | None
    as_of_date: datetime | None
    valid_until: datetime | None
    active_risk_count: int
    high_count: int
    critical_count: int
    unowned_high_critical_count: int
    untreated_high_critical_count: int
    overdue_treatment_count: int
    unaccepted_residual_count: int
    evidence_coverage: float
    warnings: list[str]
    blockers: list[str]
    readiness_status: str
    risk_readiness_hash: str | None
    source_current: bool
    allowed_actions: dict[str, bool]


class PortfolioReadinessOut(BaseModel):
    portfolio_workspace_id: int
    recommended_project_set_hash: str
    required_project_count: int
    valid_project_count: int
    blocked_project_count: int
    stale_project_count: int
    expired_project_count: int
    coverage_percent: float
    aggregate_high_count: int
    aggregate_critical_count: int
    aggregate_unaccepted_residual_count: int
    warnings: list[str]
    blockers: list[str]
    readiness_status: str
    risk_readiness_hash: str
    project_readiness: list[ProjectReadinessOut]


class InvestmentGateRiskEvidenceOut(BaseModel):
    final_output: str
    provider_key: str
    source_module: str
    evidence_type: str
    scope: str
    portfolio_workspace_id: int | None
    project_workspace_id: int | None
    recommended_project_set_hash: str | None
    assessment_id: int | None
    aggregate_reference: str | None
    assessment_date: datetime | None
    valid_until: datetime | None
    risk_source_hash: str
    risk_readiness_hash: str
    required_project_count: int
    valid_project_count: int
    coverage_percent: float
    active_risk_count: int
    high_risk_count: int
    critical_risk_count: int
    unowned_high_critical_count: int
    untreated_high_critical_count: int
    overdue_treatment_count: int
    unaccepted_residual_count: int
    warnings: list[str]
    blockers: list[str]
    readiness_status: str
    source_current: bool
    can_supply_investment_gate_evidence: bool
    evidence_origin: str = "GOVERNED_SOURCE"
    can_enter_fid: bool = False
    project_source_references: list[dict] = Field(default_factory=list)


class RefreshPreviewOut(BaseModel):
    project_workspace_id: int
    assessment_id: int | None
    previous_source_hash: str | None
    current_source_hash: str
    changes: dict
    previous_readiness: str | None
    current_readiness: str
    warnings: list[str]
    blockers: list[str]
    persisted: bool = False


class AdminConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    content_json: dict


class AdminConfigurationPreviewIn(BaseModel):
    portfolio_workspace_id: int | None = Field(default=None, gt=0)
    project_workspace_ids: list[int] = Field(default_factory=list, max_length=1000)
    gate_profile_code: str = Field(default="PYP-FFA", pattern="^(PYP-INV-SELECT|PYP-FFA)$")
    configuration_id: int | None = Field(default=None, gt=0)
    content_json: dict | None = None


class AdminConfigurationOut(BaseModel):
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


class AdminPreviewOut(BaseModel):
    configuration: dict
    gate_profile_code: str
    project_readiness: list[ProjectReadinessOut]
    portfolio_readiness: PortfolioReadinessOut | None
    effective_policy: dict
    warnings: list[str]
    blockers: list[str]
    would_be_ready: bool
    gate07j_evidence_preview: InvestmentGateRiskEvidenceOut | None
    persisted: bool = False
    can_enter_fid: bool = False


class RiskReadinessOverviewOut(BaseModel):
    configurations: list[AdminConfigurationOut]
    allowed_actions: dict[str, bool]
    provider: dict
    final_output: str
    final_release_status: str
    boundaries: list[str]


class RiskFilter(BaseModel):
    statuses: list[str] = Field(default_factory=list)
    high_critical_only: bool = False
    no_owner: bool = False
    no_treatment: bool = False
    overdue: bool = False
    needs_acceptance: bool = False

    @model_validator(mode="after")
    def validate_statuses(self):
        allowed = {"DRAFT", "OPEN", "UNDER_TREATMENT", "MONITORING", "CLOSED", "VOIDED"}
        if not set(self.statuses).issubset(allowed):
            raise ValueError("Invalid risk status filter")
        return self
