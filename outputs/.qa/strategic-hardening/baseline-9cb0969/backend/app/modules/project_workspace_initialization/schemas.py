"""API contracts for Gate 05C Project Workspace initialization."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class InitializationState(StrEnum):
    not_started = "NOT_STARTED"
    initializing = "INITIALIZING"
    blocked = "BLOCKED"
    ready = "READY_FOR_ACTIVATION"
    activated = "ACTIVATED"
    failed = "FAILED"


class ChecklistItemOut(BaseModel):
    code: str
    status: str
    message: str
    blocking: bool
    evidence: dict[str, Any] = Field(default_factory=dict)


class ModuleInitializationOut(BaseModel):
    module_key: str
    state: str
    configuration_container: str = "ready"
    evidence: dict[str, Any] = Field(default_factory=dict)


class InitializationOut(BaseModel):
    result: str
    persisted: bool
    initialization_id: int | None = None
    workspace_id: int
    workspace_status: str
    state: InitializationState
    progress_percent: int
    blocker_count: int
    warning_count: int
    checklist: list[ChecklistItemOut]
    template_config_id: int | None = None
    template_code: str = ""
    template_revision: int | None = None
    modules: list[ModuleInitializationOut] = Field(default_factory=list)
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


class ProjectWorkspaceListItemOut(BaseModel):
    workspace_id: int
    project_name: str
    project_number: str
    record_code: str
    workspace_status: str
    initialization_state: InitializationState
    template_code: str
    project_manager: str
    blocker_count: int
    warning_count: int
    revision_version: int
    can_initialize: bool
    can_activate: bool
