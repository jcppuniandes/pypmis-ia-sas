"""USER MODE routes for Gate 06B physical Workspace creation."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext, require_enterprise_permission
from app.modules.physical_workspace_creation.schemas import (
    PhysicalWorkspaceCreationOptionsOut,
    PhysicalWorkspaceDecisionRequest,
    PhysicalWorkspaceMaterializationOut,
    PhysicalWorkspaceOverviewOut,
    PhysicalWorkspaceRequestCreate,
    PhysicalWorkspaceRequestOut,
    PhysicalWorkspaceRequestPreviewOut,
    PhysicalWorkspaceRequestUpdate,
)
from app.modules.physical_workspace_creation.service import PhysicalWorkspaceCreationService

router = APIRouter()
REVIEW_ROLES = frozenset({"organization_admin", "physical_workspace_reviewer"})
APPROVAL_ROLES = frozenset({"organization_admin", "physical_workspace_approver"})
MATERIALIZATION_ROLES = frozenset({"organization_admin", "physical_workspace_materialization_service"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    value = if_match.strip()
    if value.startswith("W/"):
        value = value[2:]
    value = value.strip('"')
    if not value.isdigit() or int(value) < 1:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"})
    return int(value)


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    *,
    allowed_role_codes: frozenset[str] | None = None,
) -> tuple[PhysicalWorkspaceCreationService, EnterprisePermissionContext]:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=allowed_role_codes)
    service = PhysicalWorkspaceCreationService(db, tenant_id, context.user.id)
    service.ensure_seed()
    return service, context


def _etag(response: Response, value: PhysicalWorkspaceRequestOut) -> PhysicalWorkspaceRequestOut:
    response.headers["ETag"] = f'"{value.revision_version}"'
    return value


@router.get("/physical-workspace-creation-requests/options", response_model=PhysicalWorkspaceCreationOptionsOut)
def options(
    workspace_type_code: str | None = None,
    parent_workspace_id: int | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalWorkspaceCreationOptionsOut:
    service, _context = _authorized(db, tenant_id, user_id, "physical_workspace_creation.request.create")
    return service.options(workspace_type_code, parent_workspace_id)


@router.post(
    "/physical-workspace-creation-requests",
    response_model=PhysicalWorkspaceRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_request(
    payload: PhysicalWorkspaceRequestCreate,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalWorkspaceRequestOut:
    service, _context = _authorized(db, tenant_id, user_id, "physical_workspace_creation.request.create")
    return _etag(response, service.create_request(payload))


@router.get("/physical-workspace-creation-requests", response_model=list[PhysicalWorkspaceRequestOut])
def list_requests(
    state_filter: str = Query(default="", alias="state", max_length=40),
    workspace_type: str = Query(default="", max_length=40),
    search: str = Query(default="", max_length=160),
    review_queue: bool = False,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[PhysicalWorkspaceRequestOut]:
    service, context = _authorized(db, tenant_id, user_id, "physical_workspace_creation.request.read")
    return service.list_requests(
        context,
        state=state_filter,
        workspace_type=workspace_type,
        search=search,
        review_queue=review_queue,
    )


@router.get("/physical-workspace-creation-requests/{request_id}", response_model=PhysicalWorkspaceRequestOut)
def get_request(
    request_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalWorkspaceRequestOut:
    service, context = _authorized(db, tenant_id, user_id, "physical_workspace_creation.request.read")
    return _etag(response, service.get_request(request_id, context))


@router.put("/physical-workspace-creation-requests/{request_id}", response_model=PhysicalWorkspaceRequestOut)
def update_request(
    request_id: int,
    payload: PhysicalWorkspaceRequestUpdate,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalWorkspaceRequestOut:
    service, _context = _authorized(db, tenant_id, user_id, "physical_workspace_creation.request.edit")
    return _etag(response, service.update_request(request_id, payload, expected_version))


@router.post(
    "/physical-workspace-creation-requests/{request_id}/preview",
    response_model=PhysicalWorkspaceRequestPreviewOut,
)
def preview_request(
    request_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalWorkspaceRequestPreviewOut:
    service, context = _authorized(db, tenant_id, user_id, "physical_workspace_creation.request.read")
    return service.preview(request_id, context)


def _transition(
    action: str,
    request_id: int,
    response: Response,
    expected_version: int,
    db: Session,
    tenant_id: int,
    user_id: int,
    reason: str | None = None,
) -> PhysicalWorkspaceRequestOut:
    permission = "physical_workspace_creation.request.submit"
    roles = None
    if action in {"start_review", "return_request", "reject"}:
        permission, roles = "physical_workspace_creation.review", REVIEW_ROLES
    elif action == "approve":
        permission, roles = "physical_workspace_creation.approve", APPROVAL_ROLES
    service, _context = _authorized(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    method = getattr(service, action)
    result = (
        method(request_id, expected_version, reason) if reason is not None else method(request_id, expected_version)
    )
    return _etag(response, result)


@router.post("/physical-workspace-creation-requests/{request_id}/submit", response_model=PhysicalWorkspaceRequestOut)
def submit_request(
    request_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalWorkspaceRequestOut:
    return _transition("submit", request_id, response, expected_version, db, tenant_id, user_id)


@router.post("/physical-workspace-creation-requests/{request_id}/cancel", response_model=PhysicalWorkspaceRequestOut)
def cancel_request(
    request_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalWorkspaceRequestOut:
    return _transition("cancel", request_id, response, expected_version, db, tenant_id, user_id)


@router.post(
    "/physical-workspace-creation-requests/{request_id}/start-review", response_model=PhysicalWorkspaceRequestOut
)
def start_review(
    request_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalWorkspaceRequestOut:
    return _transition("start_review", request_id, response, expected_version, db, tenant_id, user_id)


@router.post("/physical-workspace-creation-requests/{request_id}/return", response_model=PhysicalWorkspaceRequestOut)
def return_request(
    request_id: int,
    payload: PhysicalWorkspaceDecisionRequest,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalWorkspaceRequestOut:
    return _transition("return_request", request_id, response, expected_version, db, tenant_id, user_id, payload.reason)


@router.post("/physical-workspace-creation-requests/{request_id}/reject", response_model=PhysicalWorkspaceRequestOut)
def reject_request(
    request_id: int,
    payload: PhysicalWorkspaceDecisionRequest,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalWorkspaceRequestOut:
    return _transition("reject", request_id, response, expected_version, db, tenant_id, user_id, payload.reason)


@router.post("/physical-workspace-creation-requests/{request_id}/approve", response_model=PhysicalWorkspaceRequestOut)
def approve_request(
    request_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalWorkspaceRequestOut:
    return _transition("approve", request_id, response, expected_version, db, tenant_id, user_id)


@router.post(
    "/physical-workspace-creation-requests/{request_id}/materialize",
    response_model=PhysicalWorkspaceMaterializationOut,
)
def materialize_request(
    request_id: int,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalWorkspaceMaterializationOut:
    service, _context = _authorized(
        db,
        tenant_id,
        user_id,
        "physical_workspace_creation.materialize",
        allowed_role_codes=MATERIALIZATION_ROLES,
    )
    return service.materialize(request_id, expected_version)


@router.get("/physical-workspaces/{workspace_id}/overview", response_model=PhysicalWorkspaceOverviewOut)
def physical_workspace_overview(
    workspace_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PhysicalWorkspaceOverviewOut:
    service, context = _authorized(db, tenant_id, user_id, "enterprise_structure.read")
    return service.overview(workspace_id, context)
