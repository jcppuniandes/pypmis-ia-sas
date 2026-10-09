"""Canonical Nivel 2B contracts and dry-run report models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NodeType(StrEnum):
    ENTERPRISE = "ENTERPRISE"
    BUSINESS_UNIT = "BUSINESS_UNIT"
    PORTFOLIO = "PORTFOLIO"
    PROGRAM = "PROGRAM"
    PROJECT = "PROJECT"
    PROPERTY = "PROPERTY"
    FACILITY = "FACILITY"


class RecordStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class ReconciliationAction(StrEnum):
    ADOPT = "ADOPT"


class ImportMetadata(StrictModel):
    tenant_code: str = Field(min_length=1)
    release_code: str = Field(min_length=1)
    release_name: str = Field(min_length=1)
    source_date: date | None = None
    requested_by: str | None = None
    description: str | None = None


class StrategicObjectiveInput(StrictModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    strategic_line: str | None = None
    priority: str | None = None
    horizon: str | None = None
    responsible_area: str | None = None
    active: bool = True
    description: str | None = None


class EnterpriseNodeInput(StrictModel):
    external_key: str = Field(min_length=1)
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    node_type: NodeType
    parent_external_key: str | None = None
    description: str | None = None
    organization_unit_code: str | None = None
    responsible_email: str | None = None
    region_code: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: RecordStatus
    sort_order: int | None = None
    publish_candidate: bool = False


class ClassificationInput(StrictModel):
    workspace_external_key: str = Field(min_length=1)
    category_set_code: str = Field(min_length=1)
    category_item_code: str = Field(min_length=1)
    category_item_name: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: RecordStatus = RecordStatus.ACTIVE


class WorkspaceLinkInput(StrictModel):
    source_external_key: str = Field(min_length=1)
    target_external_key: str = Field(min_length=1)
    relationship_type: str = Field(min_length=1)
    valid_from: date | None = None
    valid_to: date | None = None
    status: RecordStatus = RecordStatus.ACTIVE
    description: str | None = None


class WorkspaceReconciliationInput(StrictModel):
    external_key: str = Field(min_length=1)
    existing_id: int = Field(gt=0)
    action: ReconciliationAction = ReconciliationAction.ADOPT
    rationale: str = Field(min_length=1)


class EnterpriseStructureImport(StrictModel):
    metadata: ImportMetadata
    strategic_objectives: list[StrategicObjectiveInput] = Field(default_factory=list)
    nodes: list[EnterpriseNodeInput] = Field(min_length=1)
    classifications: list[ClassificationInput] = Field(default_factory=list)
    links: list[WorkspaceLinkInput] = Field(default_factory=list)
    reconciliation: list[WorkspaceReconciliationInput] = Field(default_factory=list)


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class DiffAction(StrEnum):
    ADOPT = "adopt"
    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"


class ValidationFinding(StrictModel):
    severity: Severity
    code: str
    section: str
    reference: str = ""
    message: str
    recommendation: str


class DiffEntry(StrictModel):
    entity: str
    key: str
    action: DiffAction
    reason: str
    record_code: str | None = None
    existing_id: int | None = None
    old_record_code: str | None = None


class DryRunReport(StrictModel):
    tenant_code: str
    release_code: str
    input_hash: str
    valid: bool
    findings: list[ValidationFinding]
    diff: list[DiffEntry]
    topological_order: list[str]
    summary: dict[str, int]

    @property
    def exit_code(self) -> int:
        if any(item.severity == Severity.ERROR for item in self.findings):
            return 1
        if any(item.severity == Severity.WARNING for item in self.findings):
            return 2
        return 0


class TenantIdentityChange(StrictModel):
    tenant_id: int
    old_name: str
    new_name: str
    old_slug: str
    new_slug: str
    currency: str
    changed: bool


class AppliedWorkspace(StrictModel):
    id: int
    external_key: str
    record_code: str
    workspace_type: str
    name: str
    action: DiffAction


class CoreApplyReport(StrictModel):
    outcome: str
    release_code: str
    tenant_code: str
    actor: str
    input_hash: str
    canonical_input_hash: str
    reconciliation_hash: str
    source_snapshot_hash: str
    approved_source_snapshot_hash: str
    idempotent_replay: bool
    tenant_change: TenantIdentityChange
    adopted_ids: dict[str, int]
    created_workspace_ids: list[int]
    objective_codes: list[str]
    classification_keys: list[str]
    workspaces: list[AppliedWorkspace]
    summary: dict[str, int]
    audit_event_id: int
    occurred_at: datetime


class CorePublishReport(StrictModel):
    outcome: str
    release_id: int
    release_code: str
    release_name: str
    state: str
    tenant_id: int
    tenant_code: str
    actor: str
    input_hash: str
    canonical_input_hash: str
    source_snapshot_hash: str
    approved_source_snapshot_hash: str
    content_fingerprint: str
    workspace_count: int
    objective_count: int
    classification_count: int
    link_count: int
    operational_statuses: dict[str, int]
    status_transitions: list[str]
    previous_release: str | None = None
    mutation_count: int
    audit_event_id: int | None = None
    published_at: datetime


@dataclass(frozen=True)
class ExistingNode:
    id: int
    parent_id: int | None
    external_key: str
    code: str
    name: str
    node_type: str
    status: str
    sort_order: int
    metadata: dict[str, Any]
    record_code: str
    references: dict[str, int] = field(default_factory=dict)
    child_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class SnapshotIntegrityIssue:
    code: str
    reference: str
    message: str


@dataclass
class TenantSnapshot:
    tenant_id: int
    tenant_code: str
    nodes: list[ExistingNode] = field(default_factory=list)
    classifications: set[tuple[int, str, str]] = field(default_factory=set)
    links: set[tuple[int, int, str]] = field(default_factory=set)
    published_type_codes: set[str] = field(default_factory=set)
    published_categories: dict[str, dict[str, Any]] = field(default_factory=dict)
    user_emails: set[str] = field(default_factory=set)
    organization_unit_codes: set[str] = field(default_factory=set)
    existing_release_codes: set[str] = field(default_factory=set)
    requester_has_manage_permission: bool | None = None
    workspace_tenant_ids: dict[int, int] = field(default_factory=dict)
    integrity_issues: list[SnapshotIntegrityIssue] = field(default_factory=list)
