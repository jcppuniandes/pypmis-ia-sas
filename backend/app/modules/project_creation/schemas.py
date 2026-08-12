"""API contracts for the Gate 05B Project Creation Process."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    blocked_reason: str | None = None


class ProjectMaterializationOut(BaseModel):
    result: str
    request_id: int
    request_number: str
    state: ProjectCreationState
    materialized_workspace_id: int
    project_number: str
    record_code: str
    mutation_count: int


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
    planned_start: date | None = None
    planned_finish: date | None = None
    currency: str
    estimated_budget: str | None = None
    enabled_modules: list[str]
