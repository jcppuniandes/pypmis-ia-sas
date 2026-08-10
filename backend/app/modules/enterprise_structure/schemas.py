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


class CoreReleaseOut(BaseModel):
    id: int
    release_code: str
    release_name: str
    revision_number: int
    revision_version: int
    state: str
    previous_release_id: int | None
    source_hash: str
    canonical_hash: str
    content_fingerprint: str
    workspace_count: int
    objective_count: int
    classification_count: int
    link_count: int
    published_at: datetime | None
    published_by: str | None


class RevisionClassificationIn(BaseModel):
    category_set_code: str
    category_item_code: str


class RevisionWorkspaceCreate(BaseModel):
    name: str
    workspace_type_code: str
    parent_key: str
    description: str = ""
    responsible_user_id: int | None = None
    status: str = "draft"
    applicable_classifications: list[RevisionClassificationIn] = Field(default_factory=list)


class RevisionWorkspaceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    responsible_user_id: int | None = None
    status: str | None = None


class RevisionMoveRequest(BaseModel):
    new_parent_key: str


class RevisionClassificationsUpdate(BaseModel):
    classifications: list[RevisionClassificationIn]


class RevisionRecordCodePreviewRequest(BaseModel):
    parent_key: str
    workspace_type_code: str
    workspace_key: str | None = None


class RevisionRecordCodeImpact(BaseModel):
    workspace_key: str
    before: str
    after: str


class RevisionRecordCodePreviewOut(BaseModel):
    current_record_code: str | None = None
    record_code: str
    affected_descendants: list[RevisionRecordCodeImpact] = Field(default_factory=list)


class RevisionApprovalRequest(BaseModel):
    draft_hash: str
    diff_hash: str


class RevisionPublishRequest(RevisionApprovalRequest):
    pass


class RevisionRollbackRequest(BaseModel):
    reason: str = Field(min_length=4, max_length=500)
    confirm: bool = False


class RevisionReleaseUpdate(BaseModel):
    release_name: str = Field(min_length=1, max_length=220)


class RevisionWorkspaceOut(BaseModel):
    workspace_key: str
    technical_id: int | None
    parent_key: str | None
    record_code: str
    code: str
    name: str
    workspace_type_code: str
    description: str
    responsible_user_id: int | None
    status: str
    sort_order: int
    change_state: str
    classifications: list[RevisionClassificationIn] = Field(default_factory=list)


class RevisionDiffItem(BaseModel):
    action: str
    workspace_key: str
    old_record_code: str | None = None
    new_record_code: str | None = None
    workspace_type: str
    name: str
    parent_before: str | None = None
    parent_after: str | None = None
    classifications_before: list[RevisionClassificationIn] = Field(default_factory=list)
    classifications_after: list[RevisionClassificationIn] = Field(default_factory=list)
    status_before: str | None = None
    status_after: str | None = None
    affected_descendants: list[str] = Field(default_factory=list)


class RevisionDiffOut(BaseModel):
    release_id: int
    draft_hash: str
    diff_hash: str
    summary: dict[str, int]
    items: list[RevisionDiffItem]


class RevisionValidationOut(BaseModel):
    valid: bool
    errors: list[str]
    conflicts: list[str]
    checks: dict[str, bool]
    draft_hash: str
    diff_hash: str
    validated_at: datetime | None = None


class CoreRevisionOut(CoreReleaseOut):
    base_content_fingerprint: str
    created_at: datetime
    created_by: str
    updated_at: datetime
    last_modified_by: str | None
    validated_at: datetime | None
    approved_at: datetime | None
    approved_by: str | None
    draft_hash: str
    diff_hash: str
    validation: RevisionValidationOut | None
    workspaces: list[RevisionWorkspaceOut]


class EnterpriseStructureConfigurationOut(BaseModel):
    workspace_types: list[ConfigurationVersionOut]
    categories: list[ConfigurationVersionOut]
    composition_rules: list[CompositionRuleOut]
    drafts: list[ConfigurationVersionOut]
    tree: list[EnterpriseTreeNodeOut]
    classifications: list[ClassificationOut]
    links: list[WorkspaceLinkOut]
    summary: dict[str, int]
    published_release: CoreReleaseOut | None = None
    draft_release: CoreRevisionOut | None = None


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
    published_release: CoreReleaseOut | None = None
