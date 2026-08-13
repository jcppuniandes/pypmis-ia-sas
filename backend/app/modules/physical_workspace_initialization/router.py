"""USER MODE routes for Gate 06C physical Workspace lifecycle."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import (
    EnterprisePermissionContext,
    require_enterprise_permission,
)
from app.modules.physical_workspace_initialization.schemas import (
    PhysicalInitializationOut,
    PhysicalWorkspaceListItemOut,
)
from app.modules.physical_workspace_initialization.service import PhysicalWorkspaceInitializationService

router = APIRouter()

READ_ROLES = frozenset(
    {
        "organization_admin",
        "physical_workspace_initializer",
        "physical_workspace_activator",
        "physical_workspace_responsible",
    }
)
INITIALIZER_ROLES = frozenset({"organization_admin", "physical_workspace_initializer"})
ACTIVATOR_ROLES = frozenset({"organization_admin", "physical_workspace_activator"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    normalized = if_match.strip()
    normalized = normalized.removeprefix("W/")
    normalized = normalized.strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_IF_MATCH", "message": 'Use If-Match: "<revision_version>"'},
        )
    return int(normalized)


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    allowed_roles: frozenset[str],
) -> tuple[PhysicalWorkspaceInitializationService, EnterprisePermissionContext]:
    context = require_enterprise_permission(
        db,
        tenant_id,
        user_id,
        permission,
        allowed_role_codes=allowed_roles,
    )
    return PhysicalWorkspaceInitializationService(db, tenant_id, context.user.id), context


def _etag(response: Response, value: PhysicalInitializationOut) -> PhysicalInitializationOut:
    response.headers["ETag"] = f'"{value.revision_version}"'
    return value


@router.get("/physical-workspaces", response_model=list[PhysicalWorkspaceListItemOut])
def list_physical_workspaces(
    workspace_type: str = Query("", max_length=40),
    business_number: str = Query("", max_length=120),
    workspace_name: str = Query("", max_length=180),
    workspace_status: str = Query("", max_length=40),
    initialization_status: str = Query("", max_length=40),
    parent: str = Query("", max_length=180),
    responsible: str = Query("", max_length=180),
    template: str = Query("", max_length=180),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[PhysicalWorkspaceListItemOut]:
    service, context = _authorized(db, tenant_id, user_id, "physical_workspace.initialization.read", READ_ROLES)
    return service.list_workspaces(
        context,
        workspace_type=workspace_type,
        business_number=business_number,
        workspace_name=workspace_name,
        workspace_status=workspace_status,
        initialization_status=initialization_status,
        parent=parent,
        responsible=responsible,
        template=template,
    )


@router.get("/physical-workspaces/{workspace_id}/initialization", response_model=PhysicalInitializationOut)
def get_initialization(
    workspace_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalInitializationOut:
    service, context = _authorized(db, tenant_id, user_id, "physical_workspace.initialization.read", READ_ROLES)
    return _etag(response, service.get(workspace_id, context))


@router.post("/physical-workspaces/{workspace_id}/initialization/preview", response_model=PhysicalInitializationOut)
def preview_initialization(
    workspace_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalInitializationOut:
    service, context = _authorized(db, tenant_id, user_id, "physical_workspace.initialization.read", READ_ROLES)
    return service.preview(workspace_id, context)


@router.post("/physical-workspaces/{workspace_id}/initialization/start", response_model=PhysicalInitializationOut)
def start_initialization(
    workspace_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalInitializationOut:
    service, context = _authorized(
        db,
        tenant_id,
        user_id,
        "physical_workspace.initialization.execute",
        INITIALIZER_ROLES,
    )
    return _etag(response, service.start(workspace_id, context, expected_version))


@router.post("/physical-workspaces/{workspace_id}/initialization/validate", response_model=PhysicalInitializationOut)
def validate_initialization(
    workspace_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalInitializationOut:
    service, context = _authorized(
        db,
        tenant_id,
        user_id,
        "physical_workspace.initialization.execute",
        INITIALIZER_ROLES,
    )
    return _etag(response, service.validate(workspace_id, context, expected_version))


@router.post("/physical-workspaces/{workspace_id}/activate", response_model=PhysicalInitializationOut)
def activate_workspace(
    workspace_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalInitializationOut:
    service, context = _authorized(
        db,
        tenant_id,
        user_id,
        "physical_workspace.activation.execute",
        ACTIVATOR_ROLES,
    )
    return _etag(response, service.activate(workspace_id, context, expected_version))
