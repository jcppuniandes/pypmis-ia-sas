"""API contracts for Gate 06C physical Workspace initialization."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PhysicalInitializationState(StrEnum):
    not_started = "NOT_STARTED"
    initializing = "INITIALIZING"
    blocked = "BLOCKED"
    ready = "READY_FOR_ACTIVATION"
    activated = "ACTIVATED"
    failed = "FAILED"


class PhysicalChecklistItemOut(BaseModel):
    code: str
    status: str
    message: str
    blocking: bool
    evidence: dict[str, Any] = Field(default_factory=dict)


class PhysicalModuleReadinessOut(BaseModel):
    module_key: str
    state: str
    operational_module_created: bool = False
    planned: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)


class PhysicalInitializationOut(BaseModel):
    result: str
    persisted: bool
    initialization_id: int | None = None
    workspace_id: int
    workspace_type_code: str
    workspace_name: str
    workspace_status: str
    business_number: str
    record_code: str
    external_key: str
    parent: str
    responsible: str
    state: PhysicalInitializationState
    progress_percent: int
    blocker_count: int
    warning_count: int
    common_checklist: list[PhysicalChecklistItemOut]
    type_specific_checklist: list[PhysicalChecklistItemOut]
    template_config_id: int | None = None
    template_code: str = ""
    template_revision: int | None = None
    template_content_hash: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    classifications: list[dict[str, str]] = Field(default_factory=list)
    enabled_modules: list[str] = Field(default_factory=list)
    planned_modules: list[str] = Field(default_factory=list)
    modules: list[PhysicalModuleReadinessOut] = Field(default_factory=list)
    defaults_applied: dict[str, Any] = Field(default_factory=dict)
    assignments: list[dict[str, Any]] = Field(default_factory=list)
    validation_hash: str | None = None
    checklist_hash: str | None = None
    revision_version: int
    started_at: datetime | None = None
    ready_at: datetime | None = None
    activated_at: datetime | None = None
    activated_by_user_id: int | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    mutation_count: int = 0


class PhysicalWorkspaceListItemOut(BaseModel):
    workspace_id: int
    workspace_type_code: str
    workspace_name: str
    business_number: str
    record_code: str
    workspace_status: str
    initialization_state: PhysicalInitializationState
    parent: str
    responsible: str
    template_code: str
    blocker_count: int
    warning_count: int
    revision_version: int
    can_initialize: bool
    can_activate: bool
