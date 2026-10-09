"""API contracts for Gate 07J-PERMIT."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PermitStatus = Literal[
    "NOT_STARTED",
    "IN_PREPARATION",
    "SUBMITTED",
    "UNDER_REVIEW",
    "APPROVED",
    "APPROVED_WITH_CONDITIONS",
    "REJECTED",
    "SUSPENDED",
    "EXPIRED",
    "CANCELLED",
    "NOT_REQUIRED",
]
ConditionStatus = Literal["OPEN", "EVIDENCE_PROVIDED", "SATISFIED", "WAIVED", "EXPIRED"]


class PermitCreateIn(BaseModel):
    permit_type_code: str = Field(min_length=1, max_length=80)
    requirement_key: str | None = Field(default=None, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    description: str = ""
    issuing_authority: str = Field(default="", max_length=240)
    jurisdiction: str | None = Field(default=None, max_length=240)
    status: PermitStatus = "NOT_STARTED"
    application_reference: str | None = Field(default=None, max_length=240)
    application_date: date | None = None
    approval_date: date | None = None
    effective_from: date | None = None
    valid_until: date | None = None
    permit_identifier: str | None = Field(default=None, max_length=240)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_reference: str | None = Field(default=None, max_length=300)
    responsible_user_id: int | None = None
    next_action: str | None = None
    target_date: date | None = None
    renewal_of_permit_id: int | None = None
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_from and self.valid_until and self.valid_until < self.effective_from:
            raise ValueError("valid_until must be on or after effective_from")
        if self.application_date and self.approval_date and self.approval_date < self.application_date:
            raise ValueError("approval_date must be on or after application_date")
        return self


class PermitUpdateIn(BaseModel):
    permit_type_code: str = Field(min_length=1, max_length=80)
    requirement_key: str | None = Field(default=None, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    description: str = ""
    issuing_authority: str = Field(default="", max_length=240)
    jurisdiction: str | None = Field(default=None, max_length=240)
    application_reference: str | None = Field(default=None, max_length=240)
    application_date: date | None = None
    approval_date: date | None = None
    effective_from: date | None = None
    valid_until: date | None = None
    permit_identifier: str | None = Field(default=None, max_length=240)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_reference: str | None = Field(default=None, max_length=300)
    responsible_user_id: int | None = None
    next_action: str | None = None
    target_date: date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_from and self.valid_until and self.valid_until < self.effective_from:
            raise ValueError("valid_until must be on or after effective_from")
        if self.application_date and self.approval_date and self.approval_date < self.application_date:
            raise ValueError("approval_date must be on or after application_date")
        return self


class PermitStatusIn(BaseModel):
    status: PermitStatus
    idempotency_key: str = Field(min_length=8, max_length=160)


class ProjectPermitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    project_workspace_id: int
    permit_number: str
    permit_type_code: str
    requirement_key: str | None
    title: str
    description: str
    issuing_authority: str
    jurisdiction: str | None
    status: str
    application_reference: str | None
    application_date: date | None
    approval_date: date | None
    effective_from: date | None
    valid_until: date | None
    permit_identifier: str | None
    evidence_refs_json: list[dict[str, Any]]
    source_reference: str | None
    responsible_user_id: int | None
    next_action: str | None
    target_date: date | None
    renewal_of_permit_id: int | None
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    revision_version: int


class ConditionCreateIn(BaseModel):
    condition_key: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)
    condition_type: str = Field(default="OTHER", max_length=80)
    blocking: bool = False
    owner_id: int | None = None
    target_date: date | None = None
    status: ConditionStatus = "OPEN"
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_reference: str | None = Field(default=None, max_length=300)
    idempotency_key: str = Field(min_length=8, max_length=160)


class ConditionUpdateIn(BaseModel):
    description: str = Field(min_length=1)
    condition_type: str = Field(default="OTHER", max_length=80)
    blocking: bool = False
    owner_id: int | None = None
    target_date: date | None = None
    status: ConditionStatus
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_reference: str | None = Field(default=None, max_length=300)


class PermitConditionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    permit_id: int
    condition_key: str
    description: str
    condition_type: str
    blocking: bool
    owner_id: int | None
    target_date: date | None
    status: str
    evidence_refs_json: list[dict[str, Any]]
    source_reference: str | None
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    revision_version: int


class AssessmentCreateIn(BaseModel):
    gate_profile_code: str = Field(default="PYP-FFA", max_length=80)
    as_of_date: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=160)


class AssessmentUpdateIn(BaseModel):
    as_of_date: datetime


class AssessmentActionIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class PermitReadinessAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    project_workspace_id: int
    assessment_number: str
    assessment_version: int
    as_of_date: datetime
    valid_until: datetime
    gate_profile_code: str
    project_type_code: str
    status: str
    requirement_set_hash: str
    permit_register_hash: str
    permit_source_hash: str
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    required_permit_count: int
    approved_count: int
    approved_with_conditions_count: int
    submitted_count: int
    under_review_count: int
    missing_count: int
    rejected_count: int
    suspended_count: int
    expired_count: int
    open_blocking_conditions_count: int
    evidence_coverage_percent: float
    warnings_json: list[str]
    blockers_json: list[str]
    readiness_status: str
    permit_readiness_hash: str | None
    assessed_by: int
    completed_by: int | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    revision_version: int


class ProjectPermitReadinessOut(BaseModel):
    project_workspace_id: int
    project_type_code: str
    permit_classification: str
    gate_profile: str
    assessment_id: int | None
    assessment_hash: str | None
    as_of_date: datetime | None
    valid_until: datetime | None
    required_count: int
    approved_count: int
    conditional_count: int
    missing_count: int
    rejected_count: int
    suspended_count: int
    expired_count: int
    open_blocking_conditions: int
    evidence_coverage_percent: float
    warnings: list[str]
    blockers: list[str]
    readiness_status: str
    permit_readiness_hash: str | None
    source_current: bool
    allowed_actions: dict[str, bool]


class ProjectSetPermitReadinessOut(BaseModel):
    portfolio_workspace_id: int
    recommended_project_set_hash: str
    required_project_count: int
    valid_project_count: int
    blocked_project_count: int
    stale_project_count: int
    expired_project_count: int
    coverage_percent: float
    aggregate_required_permit_count: int
    aggregate_approved_count: int
    aggregate_conditional_count: int
    aggregate_missing_count: int
    aggregate_rejected_count: int
    aggregate_suspended_count: int
    aggregate_expired_count: int
    aggregate_blocking_condition_count: int
    warnings: list[str]
    blockers: list[str]
    readiness_status: str
    permit_readiness_hash: str
    project_readiness: list[ProjectPermitReadinessOut]


class InvestmentGatePermitEvidenceOut(BaseModel):
    final_output: str
    provider_key: str
    source_module: str
    evidence_type: str
    scope: str
    portfolio_workspace_id: int | None
    project_workspace_id: int | None
    recommended_project_set_hash: str | None
    gate_profile: str
    assessment_id: int | None
    aggregate_reference: str | None
    assessment_date: datetime | None
    valid_until: datetime | None
    permit_source_hash: str
    permit_readiness_hash: str
    required_project_count: int
    valid_project_count: int
    coverage_percent: float
    required_permit_count: int
    approved_permit_count: int
    approved_with_conditions_count: int
    missing_permit_count: int
    rejected_permit_count: int
    suspended_permit_count: int
    expired_permit_count: int
    open_blocking_conditions_count: int
    evidence_coverage_percent: float
    warnings: list[str]
    blockers: list[str]
    readiness_status: str
    source_current: bool
    can_supply_investment_gate_evidence: bool
    can_enter_fid: bool = False


class RefreshPreviewOut(BaseModel):
    project_workspace_id: int
    assessment_id: int | None
    previous_source_hash: str | None
    current_source_hash: str
    changes: dict[str, Any]
    previous_readiness: str | None
    current_readiness: str
    warnings: list[str]
    blockers: list[str]
    persisted: Literal[False] = False


class AdminConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    description: str = ""
    content_json: dict[str, Any]


class AdminConfigurationPreviewIn(BaseModel):
    portfolio_workspace_id: int | None = None
    project_workspace_ids: list[int] = Field(default_factory=list)
    gate_profile_code: str = "PYP-FFA"
    configuration_id: int | None = None
    content_json: dict[str, Any] | None = None


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
    content_json: dict[str, Any]
    content_hash: str
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminPreviewOut(BaseModel):
    portfolio_workspace_id: int | None
    project_workspace_ids: list[int]
    gate_profile_code: str
    configuration_id: int | None
    configuration_hash: str
    effective_requirements: dict[str, list[dict[str, Any]]]
    project_readiness: list[ProjectPermitReadinessOut]
    aggregate: ProjectSetPermitReadinessOut | None
    gate07j_evidence: InvestmentGatePermitEvidenceOut | None
    persisted: Literal[False] = False
    can_enter_fid: Literal[False] = False


class PermitReadinessOverviewOut(BaseModel):
    module: Literal["PERMIT_READINESS"] = "PERMIT_READINESS"
    final_output: str
    provider_key: str
    provider_status: str
    final_release_status: str
    configuration_count: int
    project_permit_count: int
    assessment_count: int
    allowed_actions: dict[str, bool]
    safeguards: list[str]
