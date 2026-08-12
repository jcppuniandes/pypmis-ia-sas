"""USER MODE routes for the governed Project Creation Process (Gate 05B)."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import (
    EnterprisePermissionContext,
    require_enterprise_permission,
)
from app.modules.project_creation.schemas import (
    ProjectCreationOptionsOut,
    ProjectDecisionRequest,
    ProjectMaterializationOut,
    ProjectOverviewOut,
    ProjectRequestCreate,
    ProjectRequestOut,
    ProjectRequestPreviewOut,
    ProjectRequestUpdate,
)
from app.modules.project_creation.service import ProjectCreationService

router = APIRouter()

REVIEW_ROLES = frozenset({"organization_admin", "project_reviewer"})
APPROVAL_ROLES = frozenset({"organization_admin", "project_approver"})
MATERIALIZATION_ROLES = frozenset({"organization_admin", "project_materialization_service"})


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
    *,
    allowed_role_codes: frozenset[str] | None = None,
) -> tuple[ProjectCreationService, EnterprisePermissionContext]:
    context = require_enterprise_permission(
        db,
        tenant_id,
        user_id,
        permission,
        allowed_role_codes=allowed_role_codes,
    )
    service = ProjectCreationService(db, tenant_id, context.user.id)
    service.ensure_seed()
    return service, context


def _etag(response: Response, value: ProjectRequestOut) -> ProjectRequestOut:
    response.headers["ETag"] = f'"{value.revision_version}"'
    return value


@router.get("/project-creation-requests/options", response_model=ProjectCreationOptionsOut)
def options(
    parent_workspace_id: int | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectCreationOptionsOut:
    service, _context = _authorized(db, tenant_id, user_id, "project_creation.request.create")
    return service.options(parent_workspace_id)


@router.post(
    "/project-creation-requests",
    response_model=ProjectRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def create_request(
    payload: ProjectRequestCreate,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectRequestOut:
    service, _context = _authorized(db, tenant_id, user_id, "project_creation.request.create")
    return _etag(response, service.create_request(payload))


@router.get("/project-creation-requests", response_model=list[ProjectRequestOut])
def list_requests(
    state_filter: str = Query(default="", alias="state", max_length=40),
    search: str = Query(default="", max_length=160),
    review_queue: bool = False,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProjectRequestOut]:
    service, context = _authorized(db, tenant_id, user_id, "project_creation.request.read")
    return service.list_requests(context, state=state_filter, search=search, review_queue=review_queue)


@router.get("/project-creation-requests/{request_id}", response_model=ProjectRequestOut)
def get_request(
    request_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectRequestOut:
    service, context = _authorized(db, tenant_id, user_id, "project_creation.request.read")
    return _etag(response, service.get_request(request_id, context))


@router.put("/project-creation-requests/{request_id}", response_model=ProjectRequestOut)
def update_request(
    request_id: int,
    payload: ProjectRequestUpdate,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectRequestOut:
    service, _context = _authorized(db, tenant_id, user_id, "project_creation.request.edit")
    return _etag(response, service.update_request(request_id, payload, expected_version))


@router.post("/project-creation-requests/{request_id}/preview", response_model=ProjectRequestPreviewOut)
def preview_request(
    request_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectRequestPreviewOut:
    service, context = _authorized(db, tenant_id, user_id, "project_creation.request.read")
    return service.preview(request_id, context)


@router.post("/project-creation-requests/{request_id}/submit", response_model=ProjectRequestOut)
def submit_request(
    request_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectRequestOut:
    service, _context = _authorized(db, tenant_id, user_id, "project_creation.request.submit")
    return _etag(response, service.submit(request_id, expected_version))


@router.post("/project-creation-requests/{request_id}/cancel", response_model=ProjectRequestOut)
def cancel_request(
    request_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectRequestOut:
    service, _context = _authorized(db, tenant_id, user_id, "project_creation.request.submit")
    return _etag(response, service.cancel(request_id, expected_version))


@router.post("/project-creation-requests/{request_id}/start-review", response_model=ProjectRequestOut)
def start_review(
    request_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectRequestOut:
    service, _context = _authorized(
        db,
        tenant_id,
        user_id,
        "project_creation.review",
        allowed_role_codes=REVIEW_ROLES,
    )
    return _etag(response, service.start_review(request_id, expected_version))


@router.post("/project-creation-requests/{request_id}/return", response_model=ProjectRequestOut)
def return_request(
    request_id: int,
    payload: ProjectDecisionRequest,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectRequestOut:
    service, _context = _authorized(
        db,
        tenant_id,
        user_id,
        "project_creation.review",
        allowed_role_codes=REVIEW_ROLES,
    )
    return _etag(response, service.return_request(request_id, expected_version, payload.reason))


@router.post("/project-creation-requests/{request_id}/reject", response_model=ProjectRequestOut)
def reject_request(
    request_id: int,
    payload: ProjectDecisionRequest,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectRequestOut:
    service, _context = _authorized(
        db,
        tenant_id,
        user_id,
        "project_creation.review",
        allowed_role_codes=REVIEW_ROLES,
    )
    return _etag(response, service.reject(request_id, expected_version, payload.reason))


@router.post("/project-creation-requests/{request_id}/approve", response_model=ProjectRequestOut)
def approve_request(
    request_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectRequestOut:
    service, _context = _authorized(
        db,
        tenant_id,
        user_id,
        "project_creation.approve",
        allowed_role_codes=APPROVAL_ROLES,
    )
    return _etag(response, service.approve(request_id, expected_version))


@router.post("/project-creation-requests/{request_id}/materialize", response_model=ProjectMaterializationOut)
def materialize_request(
    request_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectMaterializationOut:
    service, _context = _authorized(
        db,
        tenant_id,
        user_id,
        "project_creation.materialize",
        allowed_role_codes=MATERIALIZATION_ROLES,
    )
    return service.materialize(request_id)


@router.get("/project-workspaces/{workspace_id}/overview", response_model=ProjectOverviewOut)
def project_overview(
    workspace_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectOverviewOut:
    service, context = _authorized(db, tenant_id, user_id, "enterprise_structure.read")
    return service.project_overview(workspace_id, context)
