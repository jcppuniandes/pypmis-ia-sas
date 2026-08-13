"""Tenant-safe USER MODE APIs for Workspace Operational Context."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.models import SecurityEvent
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext, require_enterprise_permission
from app.modules.workspace_context.schemas import (
    MyWorkspaceOut,
    RecentWorkspaceOut,
    WorkspaceContextOut,
    WorkspaceHomeOut,
    WorkspaceLastRouteIn,
    WorkspaceModuleAccessOut,
    WorkspaceNavigatorItemOut,
    WorkspaceOpenIn,
)
from app.modules.workspace_context.service import WorkspaceOperationalContextService

router = APIRouter(prefix="/workspaces")


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    *,
    workspace_id: int | None = None,
) -> tuple[WorkspaceOperationalContextService, EnterprisePermissionContext]:
    try:
        context = require_enterprise_permission(db, tenant_id, user_id, permission)
    except HTTPException:
        db.rollback()
        db.add(
            SecurityEvent(
                tenant_id=tenant_id,
                user_id=user_id,
                event_type="workspace.context_denied",
                outcome="denied",
                target_type="workspace",
                target_id=workspace_id,
                metadata_json={"reason": "MISSING_PERMISSION", "permission": permission},
            )
        )
        db.commit()
        raise
    return WorkspaceOperationalContextService(db, tenant_id, context.user.id, context), context


def _etag(response: Response, context: WorkspaceContextOut) -> WorkspaceContextOut:
    response.headers["ETag"] = f'"{context.etag}"'
    response.headers["Cache-Control"] = "private, no-store"
    return context


@router.get("", response_model=list[MyWorkspaceOut])
def my_workspaces(
    workspace_type: str = Query("", max_length=40),
    status: str = Query("", max_length=40),
    responsible: str = Query("", max_length=180),
    parent: str = Query("", max_length=180),
    business_number: str = Query("", max_length=120),
    name: str = Query("", max_length=180),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[MyWorkspaceOut]:
    service, _context = _authorized(db, tenant_id, user_id, "workspace.home.read")
    return service.my_workspaces(
        workspace_type=workspace_type,
        status=status,
        responsible=responsible,
        parent=parent,
        business_number=business_number,
        name=name,
    )


@router.get("/recent", response_model=list[RecentWorkspaceOut])
def recent_workspaces(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[RecentWorkspaceOut]:
    service, _context = _authorized(db, tenant_id, user_id, "workspace.recent.read")
    return service.recent()


@router.post("/{workspace_id}/open", response_model=WorkspaceContextOut)
def open_workspace(
    workspace_id: int,
    payload: WorkspaceOpenIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WorkspaceContextOut:
    service, _context = _authorized(db, tenant_id, user_id, "workspace.open", workspace_id=workspace_id)
    return _etag(response, service.open(workspace_id, payload.route))


@router.get("/{workspace_id}/context", response_model=WorkspaceContextOut)
def workspace_context(
    workspace_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WorkspaceContextOut:
    service, _context = _authorized(db, tenant_id, user_id, "workspace.open", workspace_id=workspace_id)
    return _etag(response, service.context(workspace_id))


@router.get("/{workspace_id}/home", response_model=WorkspaceHomeOut)
def workspace_home(
    workspace_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WorkspaceHomeOut:
    service, _context = _authorized(db, tenant_id, user_id, "workspace.home.read", workspace_id=workspace_id)
    return service.home(workspace_id)


@router.get("/{workspace_id}/navigator", response_model=list[WorkspaceNavigatorItemOut])
def workspace_navigator(
    workspace_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[WorkspaceNavigatorItemOut]:
    service, _context = _authorized(db, tenant_id, user_id, "workspace.navigator.read", workspace_id=workspace_id)
    return service.navigator(workspace_id)


@router.get("/{workspace_id}/modules/{module_code}", response_model=WorkspaceModuleAccessOut)
def workspace_module_access(
    workspace_id: int,
    module_code: str,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WorkspaceModuleAccessOut:
    service, _context = _authorized(db, tenant_id, user_id, "workspace.navigator.read", workspace_id=workspace_id)
    return service.module_access(workspace_id, module_code)


@router.put("/{workspace_id}/last-route", response_model=RecentWorkspaceOut)
def update_last_route(
    workspace_id: int,
    payload: WorkspaceLastRouteIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RecentWorkspaceOut:
    service, _context = _authorized(db, tenant_id, user_id, "workspace.recent.write", workspace_id=workspace_id)
    return service.update_last_route(workspace_id, payload.route)

