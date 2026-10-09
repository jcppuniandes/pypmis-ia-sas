"""Strictly separated USER and ADMIN APIs for Business Analysis."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.business_analysis.schemas import (
    BusinessAnalysisConfigurationPreviewIn,
    BusinessAnalysisConfigurationPreviewOut,
    BusinessAnalysisConfigurationUpdateIn,
    BusinessAnalysisCreate,
    BusinessAnalysisHistoryOut,
    BusinessAnalysisOptionsOut,
    BusinessAnalysisOut,
    BusinessAnalysisPayload,
    BusinessAnalysisReadinessOut,
    BusinessAnalysisReturnIn,
    BusinessAnalysisVoidIn,
)
from app.modules.business_analysis.service import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, BusinessAnalysisService
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext, require_enterprise_permission

router = APIRouter(prefix="/business-analyses")
idea_router = APIRouter(prefix="/ideas")

AUTHOR_ROLES = frozenset({"organization_admin", "business_analysis_author"})
REVIEWER_ROLES = frozenset({"organization_admin", "business_analysis_reviewer"})
CONFIG_ROLES = frozenset({"organization_admin", "configuration_admin", "business_analysis_config_admin"})
VALID_QUEUES = frozenset({"", "all", "mine", "draft", "submitted", "review", "returned", "ready", "completed"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    normalized = if_match.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        raise HTTPException(status_code=400, detail={"reason": "INVALID_IF_MATCH"})
    return int(normalized)


def _idempotency_key(value: str = Header(..., alias="Idempotency-Key")) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 120:
        raise HTTPException(status_code=400, detail={"reason": "INVALID_IDEMPOTENCY_KEY"})
    return normalized


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    roles: frozenset[str] | None = None,
) -> tuple[BusinessAnalysisService, EnterprisePermissionContext]:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = BusinessAnalysisService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service, context


def _etag(response: Response, value: BusinessAnalysisOut) -> BusinessAnalysisOut:
    response.headers["ETag"] = f'"{value.revision_version}"'
    response.headers["Cache-Control"] = "private, no-store"
    return value


def _page_headers(response: Response, *, limit: int, count: int, next_cursor: str | None) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Page-Limit"] = str(limit)
    response.headers["X-Result-Count"] = str(count)
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor


@router.get("/options", response_model=BusinessAnalysisOptionsOut)
def options(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessAnalysisOptionsOut:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.create", AUTHOR_ROLES)
    return service.options()


@router.post("", response_model=BusinessAnalysisOut, status_code=status.HTTP_201_CREATED)
def create(
    payload: BusinessAnalysisCreate,
    response: Response,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessAnalysisOut:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.create", AUTHOR_ROLES)
    return _etag(response, service.create(payload.source_idea_id, idempotency_key))


@router.get("", response_model=list[BusinessAnalysisOut])
def list_analyses(
    response: Response,
    queue: str = Query("", max_length=30),
    search: str = Query("", max_length=180),
    owning_workspace_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=256),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[BusinessAnalysisOut]:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.read")
    if queue not in VALID_QUEUES:
        raise HTTPException(status_code=422, detail={"reason": "INVALID_BUSINESS_ANALYSIS_QUEUE"})
    items, next_cursor = service.list_page(
        queue="" if queue == "all" else queue,
        search=search,
        owning_workspace_id=owning_workspace_id,
        limit=limit,
        cursor=cursor,
    )
    _page_headers(response, limit=limit, count=len(items), next_cursor=next_cursor)
    return items


@router.get("/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AdminConfigurationOut]:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.admin.configure", CONFIG_ROLES)
    return [AdminConfigurationOut.model_validate(item) for item in service.configurations()]


@router.post("/admin/configuration/preview", response_model=BusinessAnalysisConfigurationPreviewOut)
def configuration_preview(
    payload: BusinessAnalysisConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessAnalysisConfigurationPreviewOut:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.admin.configure", CONFIG_ROLES)
    return service.configuration_preview(payload.owning_workspace_id)


@router.post("/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationOut)
def clone_configuration(
    configuration_id: int,
    expected: int = Depends(_if_match),
    owning_workspace_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.admin.configure", CONFIG_ROLES)
    return AdminConfigurationOut.model_validate(
        service.clone_configuration(configuration_id, expected, owning_workspace_id=owning_workspace_id)
    )


@router.put("/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: BusinessAnalysisConfigurationUpdateIn,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.admin.configure", CONFIG_ROLES)
    return AdminConfigurationOut.model_validate(
        service.update_configuration(
            configuration_id,
            expected,
            name=payload.name,
            description=payload.description,
            content=payload.content_json,
        )
    )


@router.post("/admin/configurations/{configuration_id}/publish", response_model=AdminConfigurationOut)
def publish_configuration(
    configuration_id: int,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.admin.publish", CONFIG_ROLES)
    return AdminConfigurationOut.model_validate(service.publish_configuration(configuration_id, expected))


@router.post("/admin/configurations/{configuration_id}/archive", response_model=AdminConfigurationOut)
def archive_configuration(
    configuration_id: int,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.admin.publish", CONFIG_ROLES)
    return AdminConfigurationOut.model_validate(service.archive_configuration(configuration_id, expected))


@router.get("/{analysis_id}", response_model=BusinessAnalysisOut)
def get_analysis(
    analysis_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessAnalysisOut:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.read")
    return _etag(response, service.get(analysis_id))


@router.put("/{analysis_id}", response_model=BusinessAnalysisOut)
def update_analysis(
    analysis_id: int,
    payload: BusinessAnalysisPayload,
    response: Response,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessAnalysisOut:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.edit", AUTHOR_ROLES)
    return _etag(response, service.update(analysis_id, payload, expected))


def _transition(permission: str, roles: frozenset[str], method: str):
    def endpoint(
        analysis_id: int,
        response: Response,
        expected: int = Depends(_if_match),
        db: Session = Depends(get_db),
        tenant_id: int = Depends(get_tenant_id),
        user_id: int = Depends(get_user_id),
    ) -> BusinessAnalysisOut:
        service, _context = _authorized(db, tenant_id, user_id, permission, roles)
        return _etag(response, getattr(service, method)(analysis_id, expected))

    return endpoint


router.add_api_route(
    "/{analysis_id}/submit",
    _transition("business_analysis.submit", AUTHOR_ROLES, "submit"),
    methods=["POST"],
    response_model=BusinessAnalysisOut,
)
router.add_api_route(
    "/{analysis_id}/start-review",
    _transition("business_analysis.review", REVIEWER_ROLES, "start_review"),
    methods=["POST"],
    response_model=BusinessAnalysisOut,
)
router.add_api_route(
    "/{analysis_id}/complete",
    _transition("business_analysis.review", REVIEWER_ROLES, "complete"),
    methods=["POST"],
    response_model=BusinessAnalysisOut,
)


@router.post("/{analysis_id}/return", response_model=BusinessAnalysisOut)
def return_analysis(
    analysis_id: int,
    payload: BusinessAnalysisReturnIn,
    response: Response,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessAnalysisOut:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.review", REVIEWER_ROLES)
    return _etag(response, service.return_analysis(analysis_id, payload.reason, expected))


@router.post("/{analysis_id}/void", response_model=BusinessAnalysisOut)
def void_analysis(
    analysis_id: int,
    payload: BusinessAnalysisVoidIn,
    response: Response,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessAnalysisOut:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.edit", AUTHOR_ROLES)
    return _etag(response, service.void(analysis_id, payload.reason, expected))


@router.post("/{analysis_id}/new-revision", response_model=BusinessAnalysisOut, status_code=status.HTTP_201_CREATED)
def clone_revision(
    analysis_id: int,
    response: Response,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessAnalysisOut:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.create", AUTHOR_ROLES)
    return _etag(response, service.clone_revision(analysis_id, idempotency_key))


@router.get("/{analysis_id}/readiness", response_model=BusinessAnalysisReadinessOut)
def readiness(
    analysis_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessAnalysisReadinessOut:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.read")
    return service.readiness(analysis_id)


@router.get("/{analysis_id}/history", response_model=list[BusinessAnalysisHistoryOut])
def history(
    analysis_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[BusinessAnalysisHistoryOut]:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.read")
    return service.history(analysis_id)


@idea_router.get("/{idea_id}/business-analyses", response_model=list[BusinessAnalysisOut])
def idea_business_analyses(
    idea_id: int,
    response: Response,
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=256),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[BusinessAnalysisOut]:
    service, _context = _authorized(db, tenant_id, user_id, "business_analysis.read")
    items, next_cursor = service.list_for_idea_page(idea_id, limit=limit, cursor=cursor)
    _page_headers(response, limit=limit, count=len(items), next_cursor=next_cursor)
    return items
