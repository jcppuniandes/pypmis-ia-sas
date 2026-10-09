"""Public API contracts for Gate 06D."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkspaceIdentityOut(BaseModel):
    tenant_id: int
    workspace_id: int
    workspace_type: str
    workspace_name: str
    workspace_status: str
    business_number: str
    record_code: str
    external_key: str


class WorkspaceReferenceOut(BaseModel):
    workspace_id: int
    workspace_type: str
    workspace_name: str
    business_number: str
    record_code: str
    status: str
    navigable: bool = True


class WorkspaceTemplateOut(BaseModel):
    code: str = ""
    revision: int | None = None
    content_hash: str = ""


class WorkspaceResponsibleOut(BaseModel):
    user_id: int | None = None
    name: str = ""
    email: str = ""


class WorkspaceNavigatorItemOut(BaseModel):
    code: str
    label: str
    route: str
    state: str
    permission_key: str = ""
    read_only: bool = False
    reason: str = ""


class ActiveWorkspaceContextOut(BaseModel):
    tenant_id: int
    workspace_id: int
    workspace_type: str
    workspace_name: str
    workspace_status: str
    business_number: str
    record_code: str
    external_key: str
    parent_workspace_id: int | None = None
    parent_path: list[int] = Field(default_factory=list)
    template_code: str = ""
    template_revision: int | None = None
    responsible_user_id: int | None = None
    enabled_modules: list[str] = Field(default_factory=list)
    planned_modules: list[str] = Field(default_factory=list)
    workspace_permissions: list[str] = Field(default_factory=list)
    opened_at: datetime | None = None
    last_route: str = ""


class WorkspaceContextOut(BaseModel):
    active_context: ActiveWorkspaceContextOut
    identity: WorkspaceIdentityOut
    parent: WorkspaceReferenceOut | None = None
    breadcrumb: list[WorkspaceReferenceOut]
    template: WorkspaceTemplateOut
    responsible: WorkspaceResponsibleOut
    enabled_modules: list[str]
    planned_modules: list[str]
    navigator: list[WorkspaceNavigatorItemOut]
    permissions: dict[str, bool]
    allowed_actions: list[str]
    home_configuration: dict[str, Any]
    version: int
    etag: str


class WorkspaceHomeOut(BaseModel):
    workspace: WorkspaceIdentityOut
    breadcrumb: list[WorkspaceReferenceOut]
    responsible: WorkspaceResponsibleOut
    status: str
    enabled_modules: list[str]
    planned_modules: list[str]
    recent_activity: list[dict[str, Any]] = Field(default_factory=list)
    recent_documents: list[dict[str, Any]] = Field(default_factory=list)
    my_tasks: list[dict[str, Any]] = Field(default_factory=list)
    related_workspaces: list[WorkspaceReferenceOut] = Field(default_factory=list)
    allowed_actions: list[str]
    capability_flags: dict[str, bool]


class RecentWorkspaceOut(BaseModel):
    workspace_id: int
    workspace_name: str
    workspace_type: str
    business_number: str
    status: str
    last_opened_at: datetime
    last_route: str


class MyWorkspaceOut(BaseModel):
    workspace_id: int
    workspace_name: str
    workspace_type: str
    business_number: str
    record_code: str
    status: str
    responsible: str
    parent: str
    last_route: str


class WorkspaceOpenIn(BaseModel):
    route: str = ""


class WorkspaceLastRouteIn(BaseModel):
    route: str


class WorkspaceModuleAccessOut(BaseModel):
    workspace_id: int
    module: WorkspaceNavigatorItemOut
    access: str = "READY"
    data_scope: dict[str, int]
