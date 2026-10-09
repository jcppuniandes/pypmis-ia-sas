"""Typed API contracts for Gate 07J Investment Gate Preparation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IdempotencyIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class PreparationCreateIn(IdempotencyIn):
    portfolio_workspace_id: int = Field(gt=0)
    investment_gate_profile_id: int = Field(gt=0)
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=4000)


class PreparationUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=180)
    description: str | None = Field(default=None, max_length=4000)


class ManualEvidenceIn(IdempotencyIn):
    requirement_key: str = Field(min_length=2, max_length=160)
    scope_type: str = Field(pattern="^(PORTFOLIO|PROJECT_SET|EACH_PROJECT|SELECTED_PROJECTS_ONLY)$")
    scope_id: int | None = Field(default=None, gt=0)
    reference_id: str = Field(min_length=2, max_length=180)
    evidence_date: datetime
    valid_until: datetime | None = None
    issuer: str = Field(min_length=2, max_length=180)
    owner: str = Field(min_length=2, max_length=180)
    summary: str = Field(min_length=5, max_length=6000)
    evidence_refs: list[dict] = Field(default_factory=list, max_length=50)
    scope_reference_hash: str | None = Field(default=None, min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope_type == "EACH_PROJECT" and self.scope_id is None:
            raise ValueError("scope_id is required for EACH_PROJECT evidence")
        if self.valid_until is not None and self.valid_until < self.evidence_date:
            raise ValueError("valid_until must not be before evidence_date")
        return self


class ManualEvidenceUpdateIn(BaseModel):
    evidence_date: datetime | None = None
    valid_until: datetime | None = None
    issuer: str | None = Field(default=None, min_length=2, max_length=180)
    owner: str | None = Field(default=None, min_length=2, max_length=180)
    summary: str | None = Field(default=None, min_length=5, max_length=6000)
    evidence_refs: list[dict] | None = Field(default=None, max_length=50)
    scope_reference_hash: str | None = Field(default=None, min_length=64, max_length=64)


class EvidenceValidationIn(IdempotencyIn):
    decision: str = Field(pattern="^(VALID|INVALID)$")
    validation_note: str = Field(min_length=3, max_length=3000)


class RefreshApplyIn(IdempotencyIn):
    expected_source_hash: str = Field(min_length=64, max_length=64)


class ConditionUpdateIn(BaseModel):
    condition_owner: str | None = Field(default=None, max_length=180)
    target_resolution_date: datetime | None = None
    preparation_status: str = Field(pattern="^(OPEN|EVIDENCE_PROVIDED|RESOLVED_FOR_PREPARATION|DEFERRED)$")
    evidence_reference: str | None = Field(default=None, max_length=500)


class EvidenceItemOut(BaseModel):
    id: int
    preparation_id: int
    requirement_key: str
    evidence_type: str
    classification: str | None = None
    blocking: bool = False
    provider_key: str | None = None
    coverage_requirement: float | None = None
    scope_type: str
    scope_id: int | None
    evidence_revision: int
    evidence_origin: str
    source_module: str | None
    source_record_id: str | None
    source_hash: str | None
    scope_reference_hash: str | None
    status: str
    evidence_date: datetime | None
    valid_until: datetime | None
    issuer: str | None
    owner: str | None
    summary: str
    evidence_refs: list[dict]
    submitted_by: int | None
    submitted_at: datetime | None
    validated_by: int | None
    validated_at: datetime | None
    validation_note: str | None
    warnings: list[str]
    blockers: list[str]
    source_current: bool | None = None
    source_readiness_status: str | None = None
    evidence_quality: str | None = None
    evidence_confidence: str | None = None
    quality_origin: str | None = None
    source_version: str | int | None = None
    as_of: str | None = None
    resolution_status: str
    revision_version: int


class PreparationReadinessOut(BaseModel):
    preparation_id: int
    status: str
    readiness_status: str
    source_current: bool
    required_requirement_count: int
    valid_requirement_count: int
    required_project_count: int
    valid_project_count: int
    blocked_project_count: int
    coverage_percent: float
    category_summary: dict
    evidence_coverage: dict = Field(default_factory=dict)
    evidence_readiness_status: str = "NOT_EVALUATED"
    business_evaluation_status: str = "NOT_APPLICABLE"
    portfolio_context_status: str = "NOT_EVALUATED"
    decision_package_status: str = "NOT_READY_FOR_INVESTMENT_DECISION"
    criterion_evaluations: list[dict] = Field(default_factory=list)
    unresolved_mandatory_criteria: list[str] = Field(default_factory=list)
    cross_source_consistency: list[dict] = Field(default_factory=list)
    success_criteria_candidates: list[dict] = Field(default_factory=list)
    criterion_policy: dict = Field(default_factory=dict)
    warnings: list[str]
    blockers: list[str]
    investment_gate_preparation_ready: bool
    can_enter_investment_decision: bool
    can_enter_fid: bool = False
    final_output: str


class InvestmentGatePreparationOut(BaseModel):
    id: int
    tenant_id: int
    portfolio_workspace_id: int
    preparation_number: str
    logical_code: str
    revision: int
    name: str
    description: str
    investment_gate_profile_id: int
    profile_code: str
    profile_revision: int
    profile_hash: str
    source_convergence_id: int
    source_convergence_revision: int
    source_recommendation_hash: str
    recommended_alternative_id: int
    recommended_project_set_hash: str
    status: str
    readiness_status: str
    source_snapshot: dict
    evidence_summary: dict
    criterion_policy_snapshot: dict = Field(default_factory=dict)
    criterion_evaluations: list[dict] = Field(default_factory=list)
    portfolio_context_snapshot: dict = Field(default_factory=dict)
    success_criteria_candidates: list[dict] = Field(default_factory=list)
    conditions: list[dict]
    warnings: list[str]
    blockers: list[str]
    preparation_source_hash: str
    preparation_hash: str | None
    revision_version: int
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    frozen_by: int | None
    frozen_at: datetime | None
    voided_at: datetime | None
    evidence: list[EvidenceItemOut]
    readiness: PreparationReadinessOut
    allowed_actions: list[str]


class PreparationOverviewOut(BaseModel):
    portfolio_workspace_id: int
    governance_eligible: bool
    source_contract: dict | None
    profiles: list[dict]
    preparations: list[InvestmentGatePreparationOut]
    boundaries: list[str]


class RefreshPreviewOut(BaseModel):
    preparation_id: int
    current_source_hash: str
    proposed_source_hash: str
    source_current: bool
    source_revision_changes: dict
    policy_changes: dict = Field(default_factory=dict)
    project_set_changes: dict
    evidence_changes: list[dict]
    blockers_added: list[str]
    blockers_removed: list[str]
    persisted: bool = False


class ProjectReadinessOut(BaseModel):
    preparation_id: int
    required_project_count: int
    valid_project_count: int
    blocked_project_count: int
    coverage_percent: float
    projects: list[dict]


class HandoffOut(BaseModel):
    tenant_id: int
    portfolio_workspace_id: int
    preparation_id: int
    preparation_number: str
    preparation_revision: int
    investment_gate_profile_id: int
    profile_code: str
    profile_revision: int
    profile_hash: str
    source_convergence_id: int
    source_recommendation_hash: str
    recommended_alternative_id: int
    recommended_project_set_hash: str
    budget_scenario_ref: dict | None
    resource_scenario_ref: dict | None
    budget_planning_hash: str | None
    resource_planning_hash: str | None
    portfolio_analysis_hash: str
    evidence_package_hash: str
    project_evidence_coverage: dict
    portfolio_evidence_summary: dict
    definition_FEL_summary: dict
    definition_maturity_summary: dict
    risk_summary: dict
    funding_summary: dict
    permit_summary: dict
    contracting_summary: dict
    execution_plan_summary: dict
    business_case_summary: dict
    economic_financial_summary: dict
    criterion_policy_snapshot: dict = Field(default_factory=dict)
    criterion_evaluations: list[dict] = Field(default_factory=list)
    portfolio_context_snapshot: dict = Field(default_factory=dict)
    success_criteria_candidates: list[dict] = Field(default_factory=list)
    evidence_readiness_status: str = "READY"
    business_evaluation_status: str = "NOT_APPLICABLE"
    portfolio_context_status: str = "AVAILABLE"
    decision_package_status: str = "READY_FOR_INVESTMENT_DECISION"
    open_conditions: list[dict]
    warnings: list[str]
    blockers: list[str]
    preparation_hash: str
    investment_gate_preparation_ready: bool = True
    can_enter_investment_decision: bool = True
    can_enter_fid: bool = False
    final_output: str = "READY_FOR_INVESTMENT_DECISION"


class ConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    content_json: dict


class ConfigurationPreviewIn(BaseModel):
    portfolio_workspace_id: int | None = Field(default=None, gt=0)
    configuration_id: int | None = Field(default=None, gt=0)
    content_json: dict | None = None


class ConfigurationPreviewOut(BaseModel):
    portfolio_workspace_id: int | None
    path: list[dict]
    effective: dict
    source: dict
    requirements: list[dict]
    projected_readiness: dict
    validation_issues: list[str]
    warnings: list[str]
    blockers: list[str]
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
