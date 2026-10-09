"""USER MODE routes for governed Project Workspace initialization and activation."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import (
    EnterprisePermissionContext,
    require_enterprise_permission,
)
from app.modules.project_workspace_initialization.schemas import (
    InitializationOut,
    ProjectWorkspaceListItemOut,
)
from app.modules.project_workspace_initialization.service import ProjectWorkspaceInitializationService

router = APIRouter()

READ_ROLES = frozenset(
    {"organization_admin", "project_workspace_initializer", "project_workspace_activator", "project_manager"}
)
INITIALIZER_ROLES = frozenset({"organization_admin", "project_workspace_initializer"})
ACTIVATOR_ROLES = frozenset({"organization_admin", "project_workspace_activator"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    normalized = if_match.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        raise HTTPException(
            status_code=400,
            detail={"reason": "INVALID_IF_MATCH", "message": 'Use If-Match: "<revision_version>"'},
        )
    return int(normalized)


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    allowed_roles: frozenset[str],
) -> tuple[ProjectWorkspaceInitializationService, EnterprisePermissionContext]:
    context = require_enterprise_permission(
        db,
        tenant_id,
        user_id,
        permission,
        allowed_role_codes=allowed_roles,
    )
    return ProjectWorkspaceInitializationService(db, tenant_id, context.user.id), context


def _etag(response: Response, value: InitializationOut) -> InitializationOut:
    response.headers["ETag"] = f'"{value.revision_version}"'
    return value


@router.get("/project-workspaces", response_model=list[ProjectWorkspaceListItemOut])
def list_project_workspaces(
    status_filter: str = Query("", alias="status"),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProjectWorkspaceListItemOut]:
    service, context = _authorized(db, tenant_id, user_id, "project_workspace.initialization.read", READ_ROLES)
    return service.list_workspaces(context, status=status_filter)


@router.get("/project-workspaces/{workspace_id}/initialization", response_model=InitializationOut)
def get_initialization(
    workspace_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InitializationOut:
    service, context = _authorized(db, tenant_id, user_id, "project_workspace.initialization.read", READ_ROLES)
    return _etag(response, service.get(workspace_id, context))


@router.post("/project-workspaces/{workspace_id}/initialization/preview", response_model=InitializationOut)
def preview_initialization(
    workspace_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InitializationOut:
    service, context = _authorized(db, tenant_id, user_id, "project_workspace.initialization.read", READ_ROLES)
    return service.preview(workspace_id, context)


@router.post("/project-workspaces/{workspace_id}/initialization/start", response_model=InitializationOut)
def start_initialization(
    workspace_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InitializationOut:
    service, context = _authorized(
        db, tenant_id, user_id, "project_workspace.initialization.execute", INITIALIZER_ROLES
    )
    return _etag(response, service.start(workspace_id, context, expected_version))


@router.post("/project-workspaces/{workspace_id}/initialization/validate", response_model=InitializationOut)
def validate_initialization(
    workspace_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InitializationOut:
    service, context = _authorized(
        db, tenant_id, user_id, "project_workspace.initialization.execute", INITIALIZER_ROLES
    )
    return _etag(response, service.validate(workspace_id, context, expected_version))


@router.post("/project-workspaces/{workspace_id}/activate", response_model=InitializationOut)
def activate_workspace(
    workspace_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InitializationOut:
    service, context = _authorized(db, tenant_id, user_id, "project_workspace.activation.execute", ACTIVATOR_ROLES)
    return _etag(response, service.activate(workspace_id, context, expected_version))
