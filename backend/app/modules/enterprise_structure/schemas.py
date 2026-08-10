"""Typed contracts for Enterprise Structure ADMIN and USER APIs."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConfigurationVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
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


class EnterpriseNodeCreate(BaseModel):
    code: str
    name: str
    workspace_type_code: str
    parent_id: int | None = None
    description: str = ""
    organization_unit_id: int | None = None
    responsible_user_id: int | None = None
    region_code: str = ""
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    status: str = "active"
    sort_order: int = 0


class EnterpriseNodeUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    description: str | None = None
    organization_unit_id: int | None = None
    responsible_user_id: int | None = None
    region_code: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    status: str | None = None
    sort_order: int | None = None
    expected_version: int | None = None


class EnterpriseNodeOut(BaseModel):
    id: int
    parent_id: int | None
    workspace_type_code: str
    code: str
    external_key: str | None = None
    record_code: str
    depth: int
    name: str
    description: str
    organization_unit_id: int | None
    responsible_user_id: int | None
    region_code: str
    valid_from: datetime | None
    valid_to: datetime | None
    status: str
    sort_order: int
    version: int
    created_at: datetime
    updated_at: datetime


class EnterpriseTreeNodeOut(EnterpriseNodeOut):
    children: list["EnterpriseTreeNodeOut"] = Field(default_factory=list)


class ClassificationCreate(BaseModel):
    category_set_code: str
    category_item_code: str


class ClassificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    category_set_code: str
    category_item_code: str
    created_at: datetime


class WorkspaceLinkCreate(BaseModel):
    source_workspace_id: int
    target_workspace_id: int
    relationship_type: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    status: str = "active"


class WorkspaceLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_workspace_id: int
    target_workspace_id: int
    relationship_type: str
    valid_from: datetime | None
    valid_to: datetime | None
    status: str
    created_at: datetime


class CompositionRuleOut(BaseModel):
    parent_type_code: str
    parent_type_name: str
    configuration_id: int
    revision: int
    status: str
    allowed_children: list[str]
    max_depth: int | None
    can_be_root: bool
    required_categories: list[str]
    required_fields: list[str]


class CompositionRuleUpdate(BaseModel):
    allowed_children: list[str]
    max_depth: int | None = None
    can_be_root: bool = False
    required_categories: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=lambda: ["code", "name"])


class CategoryItem(BaseModel):
    code: str
    label: str


class CategoryUpdate(BaseModel):
    name: str
    description: str = ""
    applicable_types: list[str] = Field(default_factory=list)
    items: list[CategoryItem] = Field(default_factory=list)


class PublicationRequest(BaseModel):
    configuration_ids: list[int] = Field(default_factory=list)
    expected_hashes: dict[int, str] = Field(default_factory=dict)


class ConfigurationValidationOut(BaseModel):
    valid: bool
    issues: list[str]
    warnings: list[str]
    configuration_ids: list[int]


class PublicationOut(ConfigurationValidationOut):
    published: list[ConfigurationVersionOut]


class EnterpriseStructureConfigurationOut(BaseModel):
    workspace_types: list[ConfigurationVersionOut]
    categories: list[ConfigurationVersionOut]
    composition_rules: list[CompositionRuleOut]
    drafts: list[ConfigurationVersionOut]
    tree: list[EnterpriseTreeNodeOut]
    classifications: list[ClassificationOut]
    links: list[WorkspaceLinkOut]
    summary: dict[str, int]


class EnterpriseNodeDetailOut(BaseModel):
    node: EnterpriseNodeOut
    path: list[EnterpriseNodeOut]
    classifications: list[ClassificationOut]
    links: list[WorkspaceLinkOut]


class EnterpriseExplorerOut(BaseModel):
    tree: list[EnterpriseTreeNodeOut]
    nodes: list[EnterpriseNodeOut]
    workspace_types: list[ConfigurationVersionOut]
    objectives: list[CategoryItem]
    classifications: list[ClassificationOut]
    links: list[WorkspaceLinkOut]
    summary: dict[str, int]
