"""API contracts for Gate 07M-BEN Strategic Benefits Plans."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BenefitsPlanCreateIn(BaseModel):
    project_workspace_id: int = Field(gt=0)
    version_purpose: str = "INITIAL_BENEFITS_PLAN"


class BenefitsPlanVersionUpdateIn(BaseModel):
    overview_json: dict[str, Any] = Field(default_factory=dict)
    outputs_json: list[dict[str, Any]] = Field(default_factory=list)
    outcomes_json: list[dict[str, Any]] = Field(default_factory=list)
    assumptions_json: list[dict[str, Any]] = Field(default_factory=list)
    constraints_json: list[dict[str, Any]] = Field(default_factory=list)
    fel_stage_code: str | None = Field(default=None, max_length=32)
    reviewer_user_id: int | None = Field(default=None, gt=0)


class BenefitOwnerIn(BaseModel):
    owner_type: str | None = None
    owner_user_id: int | None = Field(default=None, gt=0)
    owner_organization_unit_id: int | None = Field(default=None, gt=0)
    owner_security_role_id: int | None = Field(default=None, gt=0)
    owner_reference: str | None = Field(default=None, max_length=180)
    effective_from: date | None = None
    effective_to: date | None = None
    accountability_statement: str = Field(default="", max_length=4000)
    acceptance_status: str | None = Field(default=None, max_length=32)


class BenefitCreateIn(BaseModel):
    benefit_name: str = Field(min_length=3, max_length=240)
    benefit_description: str = Field(default="", max_length=8000)
    benefit_direction: str = "BENEFIT"
    benefit_type: str = Field(min_length=1, max_length=80)
    benefit_category: str | None = Field(default=None, max_length=120)
    strategic_objective_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_need_reference: dict[str, Any] = Field(default_factory=dict)
    source_business_analysis_reference: dict[str, Any] = Field(default_factory=dict)
    source_project_proposal_reference: dict[str, Any] = Field(default_factory=dict)
    source_business_case_reference: dict[str, Any] = Field(default_factory=dict)
    expected_outputs: list[dict[str, Any]] = Field(default_factory=list)
    expected_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    benefit_statement: str = Field(default="", max_length=8000)
    owner: BenefitOwnerIn | None = None
    expected_value: dict[str, Any] = Field(default_factory=dict)
    monetizable_flag: bool = False
    dependencies: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    risk_references: list[dict[str, Any]] = Field(default_factory=list)


class BenefitUpdateIn(BenefitCreateIn):
    status: str = "ACTIVE"


class BenefitMeasureCreateIn(BaseModel):
    measure_code: str = Field(min_length=1, max_length=80)
    measure_name: str = Field(min_length=2, max_length=180)
    definition: str = Field(default="", max_length=8000)
    unit_of_measure: str = Field(min_length=1, max_length=80)
    direction: str
    is_primary: bool = False
    baseline_status: str = "UNKNOWN"
    baseline_value: Any | None = None
    baseline_as_of_date: date | None = None
    baseline_source: str | None = Field(default=None, max_length=240)
    baseline_evidence_reference: str | None = Field(default=None, max_length=500)
    baseline_confidence: str | None = Field(default=None, max_length=40)
    target_value: Any | None = None
    target_date: date | None = None
    target_basis: str | None = Field(default=None, max_length=4000)
    tolerance: dict[str, Any] = Field(default_factory=dict)
    measurement_method: str = Field(default="", max_length=8000)
    measurement_frequency: str | None = Field(default=None, max_length=80)
    data_source_description: str | None = Field(default=None, max_length=4000)
    measurement_owner_reference: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_baseline(self):
        if self.baseline_status == "UNKNOWN" and self.baseline_value is not None:
            raise ValueError("UNKNOWN baseline must use a null value")
        if self.baseline_status == "KNOWN" and self.baseline_value is None:
            raise ValueError("KNOWN baseline requires a value")
        return self


class BenefitMeasureUpdateIn(BenefitMeasureCreateIn):
    pass


class BenefitsPlanReturnIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class BenefitsPlanVoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class BenefitsPlanRevisionIn(BaseModel):
    version_purpose: str = "MATERIAL_CHANGE_UPDATE"


class BenefitMeasureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    benefit_snapshot_id: int
    measure_code: str
    measure_name: str
    definition: str
    unit_of_measure: str
    direction: str
    is_primary: bool
    baseline_status: str
    baseline_value: Any | None
    baseline_as_of_date: date | None
    baseline_source: str | None
    baseline_evidence_reference: str | None
    baseline_confidence: str | None
    target_value: Any | None
    target_date: date | None
    target_basis: str | None
    tolerance: dict[str, Any]
    measurement_method: str
    measurement_frequency: str | None
    data_source_description: str | None
    measurement_owner_reference: dict[str, Any]
    measure_hash: str
    created_at: datetime
    updated_at: datetime
    revision_version: int


class StrategicBenefitOut(BaseModel):
    id: int
    benefit_number: str
    identity_status: str
    snapshot_id: int
    benefit_name: str
    benefit_description: str
    benefit_direction: str
    benefit_type: str
    benefit_category: str | None
    strategic_objective_refs: list[dict[str, Any]]
    source_need_reference: dict[str, Any]
    source_business_analysis_reference: dict[str, Any]
    source_project_proposal_reference: dict[str, Any]
    source_business_case_reference: dict[str, Any]
    expected_outputs: list[dict[str, Any]]
    expected_outcomes: list[dict[str, Any]]
    benefit_statement: str
    owner: dict[str, Any]
    expected_value: dict[str, Any]
    monetizable_flag: bool
    dependencies: list[dict[str, Any]]
    assumptions: list[dict[str, Any]]
    constraints: list[dict[str, Any]]
    risk_references: list[dict[str, Any]]
    status: str
    snapshot_hash: str
    measures: list[BenefitMeasureOut] = Field(default_factory=list)
    revision_version: int


class BenefitsPlanVersionOut(BaseModel):
    id: int
    benefits_plan_id: int
    version_number: int
    version_purpose: str
    status: str
    fel_stage_code: str | None
    overview_json: dict[str, Any]
    outputs_json: list[dict[str, Any]]
    outcomes_json: list[dict[str, Any]]
    assumptions_json: list[dict[str, Any]]
    constraints_json: list[dict[str, Any]]
    benefits: list[StrategicBenefitOut] = Field(default_factory=list)
    readiness_json: dict[str, Any]
    readiness_status: str
    overall_benefits_readiness: str
    readiness_warnings_json: list[str]
    readiness_blockers_json: list[str]
    coverage: dict[str, Any]
    source_references_json: dict[str, Any]
    source_hashes_json: dict[str, Any]
    source_bundle_hash: str
    source_current: bool
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    content_hash: str
    benefit_set_hash: str
    traceability_hash: str
    benefits_plan_hash: str
    preparer_user_id: int
    reviewer_user_id: int | None
    return_reason: str | None
    void_reason: str | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    review_started_at: datetime | None
    returned_at: datetime | None
    completed_at: datetime | None
    completed_by: int | None
    voided_at: datetime | None
    revision_version: int
    can_supply_investment_gate_evidence: bool = False
    allowed_actions: dict[str, bool] = Field(default_factory=dict)


class BenefitsPlanOut(BaseModel):
    id: int
    project_workspace_id: int
    project_workspace_name: str
    plan_number: str
    status: str
    current_version_id: int | None
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    configuration_source_workspace_id: int | None
    configuration_resolution_chain_json: list[dict[str, Any]]
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    revision_version: int
    current_version: BenefitsPlanVersionOut | None = None
    allowed_actions: dict[str, bool] = Field(default_factory=dict)
    final_output: str
    next_process: str


class BenefitsReadinessOut(BaseModel):
    benefits_plan_id: int
    version_id: int
    dimensions: dict[str, str]
    coverage: dict[str, Any]
    status: str
    overall_benefits_readiness: str
    warnings: list[str]
    blockers: list[str]
    source_current: bool
    configuration_current: bool
    benefits_plan_hash: str
    source_bundle_hash: str
    configuration_hash: str
    can_supply_investment_gate_evidence: bool
    persisted: bool


class BenefitsHistoryOut(BaseModel):
    version: BenefitsPlanVersionOut
    lifecycle_events: list[dict[str, Any]] = Field(default_factory=list)


class BenefitsRefreshPreviewOut(BaseModel):
    benefits_plan_id: int
    current_version_id: int
    source_delta: list[dict[str, Any]]
    benefit_delta: list[dict[str, Any]]
    owner_delta: list[dict[str, Any]]
    measure_delta: list[dict[str, Any]]
    target_delta: list[dict[str, Any]]
    policy_delta: list[dict[str, Any]]
    readiness_delta: dict[str, Any]
    warnings: list[str]
    blockers: list[str]
    recommended_version_purpose: str
    persisted: bool = False


class BenefitsReadinessProviderOut(BaseModel):
    provider_key: str
    source_module: str
    evidence_type: str
    status: str
    project_workspace_id: int
    benefits_plan_id: int
    plan_number: str
    plan_version_id: int
    plan_version_number: int
    plan_version_purpose: str
    fel_stage_code: str | None
    benefit_count: int
    required_benefit_count: int
    ready_benefit_count: int
    benefit_owner_coverage: float
    measurement_coverage: float
    baseline_coverage: float
    target_coverage: float
    traceability_coverage: float
    overall_benefits_readiness: str
    benefit_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    benefits_plan_hash: str
    source_bundle_hash: str
    configuration_hash: str
    as_of_date: datetime
    warnings: list[str]
    blockers: list[str]
    source_current: bool
    can_supply_investment_gate_evidence: bool


class BenefitsOptionsOut(BaseModel):
    version_purposes: list[str]
    readiness_states: list[str]
    queues: list[str]
    provider_key: str
    provider_status: str
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    benefit_types: list[str]
    benefit_categories: list[str]
    measure_directions: list[str]
    units_of_measure: list[str]
    measurement_frequencies: list[str]


class BenefitsTraceabilityRowOut(BaseModel):
    strategic_objectives: list[dict[str, Any]]
    need_opportunity: dict[str, Any]
    business_analysis: dict[str, Any]
    recommended_option: dict[str, Any]
    project: dict[str, Any]
    business_case: dict[str, Any]
    expected_outputs: list[dict[str, Any]]
    expected_outcomes: list[dict[str, Any]]
    benefit_id: int
    benefit_number: str
    benefit_name: str
    measures: list[dict[str, Any]]
    owner: dict[str, Any]
    target_dates: list[date]
    expected_value: dict[str, Any]
    status: str


class BenefitsConfigurationPreviewIn(BaseModel):
    project_workspace_id: int | None = Field(default=None, gt=0)
    configuration_id: int | None = Field(default=None, gt=0)
    content_json: dict[str, Any] | None = None


class BenefitsConfigurationPreviewOut(BaseModel):
    effective: dict[str, Any]
    resolution_chain: list[dict[str, Any]]
    validation_issues: list[str]
    warnings: list[str]
    publishable: bool
    persisted: bool = False


class BenefitsConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=4000)
    content_json: dict[str, Any]
