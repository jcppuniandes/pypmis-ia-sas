"""API contracts for Gate 06B physical Workspace creation."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PhysicalWorkspaceCreationState(StrEnum):
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


class ClassificationValue(BaseModel):
    category_set_code: str = Field(min_length=1, max_length=120)
    category_item_code: str = Field(min_length=1, max_length=120)

    @field_validator("category_set_code", "category_item_code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return value.strip().lower()


class PhysicalWorkspaceRequestPayload(BaseModel):
    workspace_type_code: str
    parent_workspace_id: int
    template_config_id: int
    workspace_name: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=5000)
    responsible_user_id: int
    attributes: dict[str, Any] = Field(default_factory=dict)
    classifications: list[ClassificationValue] = Field(default_factory=list, max_length=50)

    @field_validator("workspace_type_code")
    @classmethod
    def _normalize_type(cls, value: str) -> str:
        return value.strip().lower().replace("_", "-")

    @field_validator("workspace_name", "description", mode="before")
    @classmethod
    def _strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class PhysicalWorkspaceRequestCreate(PhysicalWorkspaceRequestPayload):
    pass


class PhysicalWorkspaceRequestUpdate(PhysicalWorkspaceRequestPayload):
    pass


class PhysicalWorkspaceDecisionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, value: str) -> str:
        return value.strip()


class PhysicalWorkspaceRequestOut(PhysicalWorkspaceRequestPayload):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_number: str
    state: PhysicalWorkspaceCreationState
    requestor_user_id: int
    requestor_name: str
    parent_name: str
    parent_record_code: str
    template_code: str
    template_name: str
    responsible_name: str
    revision_version: int
    decision_reason: str | None = None
    failure_reason: str | None = None
    approved_by_user_id: int | None = None
    approved_at: datetime | None = None
    materialized_workspace_id: int | None = None
    materialized_business_number: str | None = None
    materialized_record_code: str | None = None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    materialized_at: datetime | None = None


class PhysicalWorkspaceTypeOption(BaseModel):
    code: str
    name: str
    domain_description: str = ""


class PhysicalDynamicAttribute(BaseModel):
    code: str
    label: str
    input_type: str
    required: bool = False
    read_only: bool = False
    options: list[dict[str, str]] = Field(default_factory=list)


class PhysicalLocationOption(BaseModel):
    id: int
    workspace_type_code: str
    name: str
    record_code: str
    path: list[str]


class PhysicalTemplateOption(BaseModel):
    id: int
    code: str
    name: str
    workspace_type_code: str
    applicable_parent_types: list[str]
    enabled_modules: list[str]


class PhysicalResponsibleOption(BaseModel):
    id: int
    name: str
    email: str


class PhysicalWorkspaceCreationOptionsOut(BaseModel):
    workspace_types: list[PhysicalWorkspaceTypeOption]
    selected_workspace_type: str | None = None
    locations: list[PhysicalLocationOption]
    templates: list[PhysicalTemplateOption]
    responsibles: list[PhysicalResponsibleOption]
    dynamic_attributes: list[PhysicalDynamicAttribute]
    classifications: dict[str, list[dict[str, str]]]
    creation_policy: dict[str, Any] | None = None
    blocked_reason: str | None = None


class PhysicalWorkspaceRequestPreviewOut(BaseModel):
    allowed: bool
    issues: list[str]
    warnings: list[str]
    workspace_type: dict[str, Any]
    parent: dict[str, Any]
    parent_record_code: str
    projected_record_code: str
    projected_business_number: str
    template: dict[str, Any]
    creation_policy: dict[str, Any]
    applicable_classifications: list[str]
    selected_classifications: list[dict[str, str]]
    enabled_modules: list[str]
    planned_modules: list[str]
    initial_workspace_status: str
    persisted: bool = False


class PhysicalWorkspaceMaterializationOut(BaseModel):
    result: str
    request_id: int
    request_number: str
    state: PhysicalWorkspaceCreationState
    materialized_workspace_id: int
    business_number: str
    record_code: str
    mutation_count: int


class PhysicalWorkspaceOverviewOut(BaseModel):
    workspace_id: int
    workspace_type_code: str
    workspace_name: str
    business_number: str
    record_code: str
    status: str
    parent_workspace: str
    responsible: str
    template: str
    creation_request_id: int | None = None
    creation_request_number: str
    created_at: datetime
    attributes: dict[str, Any]
    classifications: list[dict[str, str]]
    enabled_modules: list[str]
    planned_modules: list[str]
