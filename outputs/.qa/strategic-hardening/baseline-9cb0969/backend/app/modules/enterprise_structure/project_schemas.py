"""Contracts for Gate 05A Project Workspace configuration and dry-run preview."""

from typing import Any

from pydantic import BaseModel, Field

from app.modules.enterprise_structure.schemas import ConfigurationValidationOut, ConfigurationVersionOut


class ProjectTemplatePayload(BaseModel):
    code: str
    name: str
    description: str = ""
    applicable_parent_types: list[str] = Field(default_factory=lambda: ["portfolio", "program"])
    default_classifications: list[dict[str, str]] = Field(default_factory=list)
    enabled_modules: list[str] = Field(default_factory=list)
    default_role_codes: list[str] = Field(default_factory=list)
    default_group_codes: list[str] = Field(default_factory=list)
    numbering_rule_code: str = "project-workspace"
    default_attributes: dict[str, Any] = Field(default_factory=dict)
    creation_policy_code: str = "project-creation"


class ProjectTemplateUpdate(ProjectTemplatePayload):
    expected_version: int = Field(ge=1)


class ProjectTemplatePublishRequest(BaseModel):
    expected_hash: str = Field(min_length=64, max_length=64)


class ProjectNumberingUpdate(BaseModel):
    prefix: str = "PYP-PRJ"
    padding: int = Field(default=5, ge=3, le=12)
    start: int = Field(default=1, ge=1)
    no_reuse: bool = True


class ProjectCreationPolicyUpdate(BaseModel):
    allowed_parent_types: list[str] = Field(default_factory=lambda: ["portfolio", "program"])
    template_required: bool = True
    project_manager_required: bool = True
    strategic_objective_required: bool = True
    approval_required: bool = True
    auto_project_number: bool = True
    auto_record_code: bool = True
    initial_status: str = "pending"
    activation_after_approval: bool = True
    materialization_after_approval: bool = True


class ProjectGovernancePolicyUpdate(BaseModel):
    allowed_source_context_types: list[str] = Field(default_factory=list)
    allowed_parent_types: list[str] = Field(default_factory=lambda: ["portfolio", "program"])
    required_fields: list[str] = Field(default_factory=list)
    optional_fields: list[str] = Field(default_factory=list)
    required_source_fields: list[str] = Field(default_factory=list)
    template_required: bool = True
    project_manager_required: bool = True
    strategic_objective_required: bool = False
    portfolio_required: bool = False
    fel_required: bool = False
    pdri_required: bool = False
    fid_required_for_creation: bool = False
    contract_source_required: bool = False
    notice_to_proceed_required: bool = False
    approval_required: bool = True
    initialization_requirements: list[str] = Field(default_factory=list)
    activation_requirements: list[str] = Field(default_factory=list)
    pending_reason: str = "INITIALIZATION_REQUIRED"
    planning_stage: str = "PROJECT_CREATION"
    scope_workspace_id: int | None = None


class ProjectGovernancePolicyPreviewRequest(BaseModel):
    governance_model: str
    source_context_type: str | None = None
    parent_workspace_id: int | None = None
    project_type: str | None = None
    template_id: int | None = None


class ProjectParentOption(BaseModel):
    id: int
    name: str
    workspace_type_code: str
    record_code: str
    status: str


class ProjectPreviewRequest(BaseModel):
    parent_id: int
    template_id: int


class ProjectPreviewOut(BaseModel):
    allowed: bool
    parent: ProjectParentOption
    template_code: str
    projected_record_code: str
    projected_project_number: str
    inherited_classifications: list[dict[str, str]]
    enabled_modules: list[str]
    initial_status: str
    issues: list[str]
    persisted: bool = False


class ProjectConfigurationOut(BaseModel):
    project_type: ConfigurationVersionOut
    templates: list[ConfigurationVersionOut]
    numbering_rule: ConfigurationVersionOut
    creation_policy: ConfigurationVersionOut
    governance_models: list[dict[str, Any]] = Field(default_factory=list)
    classification_sets: list[ConfigurationVersionOut]
    available_modules: list[ConfigurationVersionOut]
    parent_options: list[ProjectParentOption]
    allowed_parent_types: list[str]
    summary: dict[str, int]
    gate_status: str
    gate_05b_contract: dict[str, Any]
    multi_source_status: str = "READY_FOR_MULTI_SOURCE_PROJECT_CREATION"


class ProjectTemplateValidationOut(ConfigurationValidationOut):
    content_hash: str
