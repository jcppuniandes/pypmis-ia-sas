"""API contracts for the Gate 05B Project Creation Process."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.project_creation.governance import ProjectGovernanceModel, ProjectSourceContextType


class ProjectCreationState(StrEnum):
    draft = "draft"
    submitted = "submitted"
    under_review = "under_review"
    returned = "returned"
    rejected = "rejected"
    approved = "approved"
    materializing = "materializing"
    created = "created"
    failed = "failed"
    cancelled = "cancelled"


class ProjectRequestPayload(BaseModel):
    governance_model: ProjectGovernanceModel | None = None
    source_context_type: ProjectSourceContextType | None = None
    source_context_id: int | None = Field(default=None, ge=1)
    source_external_key: str | None = Field(default=None, max_length=160)
    idempotency_key: str | None = Field(default=None, max_length=160)
    source_snapshot: dict[str, Any] = Field(default_factory=dict)
    parent_workspace_id: int
    project_template_config_id: int
    project_name: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=5000)
    project_manager_user_id: int
    planned_start: date | None = None
    planned_finish: date | None = None
    currency_code: str = Field(default="COP", min_length=3, max_length=8)
    estimated_budget: Decimal | None = Field(default=None, ge=0)
    project_type: str | None = Field(default=None, max_length=120)
    project_phase: str | None = Field(default=None, max_length=120)
    priority: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    strategic_objective_codes: list[str] = Field(default_factory=list, max_length=20)

    @field_validator(
        "project_name",
        "description",
        "currency_code",
        "project_type",
        "project_phase",
        "priority",
        "country",
        "region",
        "source_external_key",
        "idempotency_key",
        mode="before",
    )
    @classmethod
    def _strip_strings(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("strategic_objective_codes")
    @classmethod
    def _normalize_objectives(cls, values: list[str]) -> list[str]:
        normalized = sorted({value.strip().lower() for value in values if value.strip()})
        return normalized

    @model_validator(mode="after")
    def _dates_are_ordered(self):
        if self.planned_start and self.planned_finish and self.planned_finish < self.planned_start:
            raise ValueError("Planned Finish must not be earlier than Planned Start")
        return self


class ProjectRequestCreate(ProjectRequestPayload):
    pass


class ProjectRequestUpdate(ProjectRequestPayload):
    pass


class ProjectDecisionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, value: str) -> str:
        return value.strip()


class ProjectRequestOut(ProjectRequestPayload):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_number: str
    state: ProjectCreationState
    requestor_user_id: int
    requestor_name: str
    parent_name: str
    parent_record_code: str
    template_code: str
    template_name: str
    project_manager_name: str
    revision_version: int
    governance_model: ProjectGovernanceModel | None = None
    source_context_type: ProjectSourceContextType | None = None
    source_context_id: int | None = None
    source_external_key: str | None = None
    idempotency_key: str | None = None
    source_snapshot: dict[str, Any] = Field(default_factory=dict)
    source_hash: str | None = None
    creation_policy_id: int | None = None
    creation_policy_revision: int | None = None
    creation_policy_hash: str | None = None
    strategic_gate_decision_id: int | None = None
    source_project_proposal_id: int | None = None
    source_idea_id: int | None = None
    source_decision_hash: str | None = None
    source_readiness_hash: str | None = None
    strategic_target_portfolio_workspace_id: int | None = None
    strategic_mapping_configuration_id: int | None = None
    strategic_mapping_revision: int | None = None
    strategic_mapping_hash: str | None = None
    strategic_source_snapshot: dict = Field(default_factory=dict)
    decision_reason: str | None = None
    failure_reason: str | None = None
    approved_by_user_id: int | None = None
    approved_at: datetime | None = None
    materialized_workspace_id: int | None = None
    materialized_project_number: str | None = None
    materialized_record_code: str | None = None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    materialized_at: datetime | None = None


class ProjectRequestPreviewOut(BaseModel):
    allowed: bool
    issues: list[str]
    parent_workspace_id: int
    parent_name: str
    parent_record_code: str
    projected_record_code: str
    projected_project_number: str
    inherited_classifications: list[dict[str, str]]
    selected_classifications: list[dict[str, str]]
    enabled_modules: list[str]
    initial_workspace_status: str
    template: dict[str, object]
    creation_policy: dict[str, object]
    governance_model: ProjectGovernanceModel | None = None
    source_context_type: ProjectSourceContextType | None = None
    effective_policy: dict[str, Any] = Field(default_factory=dict)
    policy_source_workspace_id: int | None = None
    policy_resolution_chain: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    optional_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    activation_readiness: str = "NOT_EVALUATED"
    persisted: bool = False
    notice: str = "Preview only - final number assigned at creation"


class ProjectLocationOption(BaseModel):
    id: int
    workspace_type_code: str
    name: str
    record_code: str
    path: list[str]


class ProjectTemplateOption(BaseModel):
    id: int
    code: str
    name: str
    applicable_parent_types: list[str]
    enabled_modules: list[str]


class ProjectManagerOption(BaseModel):
    id: int
    name: str
    email: str


class ProjectCreationOptionsOut(BaseModel):
    locations: list[ProjectLocationOption]
    templates: list[ProjectTemplateOption]
    managers: list[ProjectManagerOption]
    strategic_objectives: list[dict[str, str]]
    classifications: dict[str, list[dict[str, str]]]
    allowed_governance_models: list[dict[str, Any]] = Field(default_factory=list)
    allowed_source_context_types: list[str] = Field(default_factory=list)
    can_create_direct: bool = False
    can_create_from_contract: bool = False
    can_create_from_strategic_gate: bool = False
    blocked_reason: str | None = None


class ProjectSourcePreviewOut(BaseModel):
    governance_model: ProjectGovernanceModel
    source_context_type: ProjectSourceContextType
    source_context_id: int | None = None
    source_external_key: str | None = None
    source_hash: str
    effective_policy: dict[str, Any]
    source_workspace_id: int | None = None
    resolution_chain: list[str]
    required_fields: list[str]
    optional_fields: list[str]
    required_source: list[str]
    initialization_requirements: list[str]
    activation_requirements: list[str]
    warnings: list[str]
    blockers: list[str]
    persisted: bool = False


class ProjectMaterializationOut(BaseModel):
    result: str
    request_id: int
    request_number: str
    state: ProjectCreationState
    materialized_workspace_id: int
    project_number: str
    record_code: str
    mutation_count: int
    portfolio_planning_status: str | None = None


class ProjectOverviewOut(BaseModel):
    workspace_id: int
    project_name: str
    project_number: str
    record_code: str
    status: str
    parent_workspace: str
    project_manager: str
    template: str
    strategic_objectives: list[str]
    governance_model: str | None = None
    governance_label: str
    creation_source: str | None = None
    source_reference: str | None = None
    source_snapshot: dict[str, Any] = Field(default_factory=dict)
    creation_policy: dict[str, Any] = Field(default_factory=dict)
    pending_reason: str | None = None
    planning_stage: str | None = None
    activation_readiness: str
    planned_start: date | None = None
    planned_finish: date | None = None
    currency: str
    estimated_budget: str | None = None
    enabled_modules: list[str]
    initialization_state: str
    initialization_progress_percent: int
    initialization_blocker_count: int
    initialization_warning_count: int
    blocking_issues: list[str]
    warnings: list[str]
    template_revision: int | None = None
    module_states: dict[str, str]
    activated_at: datetime | None = None
    activated_by_user_id: int | None = None
    initialization_revision_version: int
    can_initialize: bool
    can_activate: bool
