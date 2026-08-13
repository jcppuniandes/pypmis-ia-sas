"""Contracts for Gate 06A physical and geographic Workspace configuration."""

from typing import Any

from pydantic import BaseModel, Field

from app.modules.enterprise_structure.schemas import ConfigurationVersionOut


class PhysicalWorkspaceParentOption(BaseModel):
    id: int
    name: str
    workspace_type_code: str
    record_code: str
    status: str


class PhysicalWorkspacePreviewRequest(BaseModel):
    workspace_type_code: str
    parent_id: int
    template_id: int | None = None
    minimal_attributes: dict[str, Any] = Field(default_factory=dict)


class PhysicalWorkspacePreviewOut(BaseModel):
    allowed: bool
    workspace_type_code: str
    parent: PhysicalWorkspaceParentOption
    template_code: str | None
    projected_record_code: str
    projected_business_number: str | None
    applicable_classifications: list[str]
    enabled_modules: list[str]
    planned_modules: list[str]
    initial_status: str
    issues: list[str]
    warnings: list[str]
    persisted: bool = False


class PhysicalCompositionRuleUpdate(BaseModel):
    allowed_children: list[str]
    facility_warehouse_enabled: bool = True


class PhysicalNumberingUpdate(BaseModel):
    prefix: str
    padding: int = Field(default=5, ge=3, le=12)
    start: int = Field(default=1, ge=1)
    no_reuse: bool = True


class PhysicalCreationPolicyUpdate(BaseModel):
    allowed_parent_types: list[str]
    template_required: bool = True
    responsible_required: bool = True
    approval_required: bool = True
    auto_business_number: bool = True
    auto_record_code: bool = True
    initial_workspace_status: str = "pending"
    activation_rule: str = "after_approval"


class PhysicalTemplatePayload(BaseModel):
    code: str
    name: str
    description: str = ""
    workspace_type_code: str
    applicable_parent_types: list[str] = Field(default_factory=list)
    default_classifications: list[dict[str, str]] = Field(default_factory=list)
    enabled_modules: list[str] = Field(default_factory=list)
    default_attributes: dict[str, Any] = Field(default_factory=dict)


class PhysicalTemplateUpdate(PhysicalTemplatePayload):
    expected_version: int = Field(ge=1)


class PhysicalTemplatePublishRequest(BaseModel):
    expected_hash: str = Field(min_length=64, max_length=64)


class PhysicalTemplateValidationOut(BaseModel):
    valid: bool
    issues: list[str]
    warnings: list[str]
    configuration_ids: list[int]
    content_hash: str


class PhysicalConfigurationOut(BaseModel):
    workspace_types: list[ConfigurationVersionOut]
    composition_rules: dict[str, list[str]]
    templates: list[ConfigurationVersionOut]
    numbering_rules: list[ConfigurationVersionOut]
    creation_policies: list[ConfigurationVersionOut]
    available_modules: list[ConfigurationVersionOut]
    parent_options: list[PhysicalWorkspaceParentOption]
    relationship_contract: list[dict[str, str]]
    summary: dict[str, int]
    gate_status: str
    exclusions: dict[str, Any]
