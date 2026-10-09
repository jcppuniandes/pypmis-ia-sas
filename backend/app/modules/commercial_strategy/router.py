"""Strict USER/ADMIN REST surface for Gate 07M-COMM."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.commercial_strategy.schemas import (
    CommercialConfigurationPreviewIn,
    CommercialConfigurationPreviewOut,
    CommercialConfigurationUpdateIn,
    CommercialReadinessProviderOut,
    CommercialStrategyCreateIn,
    CommercialStrategyHistoryOut,
    CommercialStrategyOptionsOut,
    CommercialStrategyOut,
    CommercialStrategyReadinessOut,
    CommercialStrategyRefreshPreviewOut,
    CommercialStrategyReturnIn,
    CommercialStrategyRevisionIn,
    CommercialStrategyUpdateIn,
    CommercialStrategyVersionOut,
    CommercialStrategyVoidIn,
)
from app.modules.commercial_strategy.service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    CommercialStrategyService,
)
from app.modules.enterprise_structure.permissions import require_enterprise_permission

router = APIRouter(prefix="/commercial-strategies")
project_router = APIRouter(prefix="/projects")

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "commercial_strategy_author",
        "commercial_strategy_reviewer",
        "commercial_strategy_viewer",
        "portfolio_manager",
    }
)
AUTHOR_ROLES = frozenset({"organization_admin", "commercial_strategy_author"})
REVIEWER_ROLES = frozenset({"organization_admin", "commercial_strategy_reviewer"})
CONFIG_ROLES = frozenset({"organization_admin", "configuration_admin", "commercial_strategy_config_admin"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    normalized = if_match.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"})
    return int(normalized)


def _idempotency_key(value: str = Header(..., alias="Idempotency-Key")) -> str:
    normalized = value.strip()
    if len(normalized) < 8 or len(normalized) > 160:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IDEMPOTENCY_KEY"})
    return normalized


def _etag(response: Response, value: int) -> None:
    response.headers["ETag"] = f'"{value}"'
    response.headers["Cache-Control"] = "private, no-store"


def _page_headers(response: Response, *, limit: int, count: int, next_cursor: str | None) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Page-Limit"] = str(limit)
    response.headers["X-Result-Count"] = str(count)
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    roles: frozenset[str],
) -> CommercialStrategyService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    return CommercialStrategyService(db, tenant_id, context.user.id, context)


@router.get("/options", response_model=CommercialStrategyOptionsOut)
def options(
    project_workspace_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "commercial_strategy.read", VIEW_ROLES).options(project_workspace_id)


@router.get("", response_model=list[CommercialStrategyOut])
def list_strategies(
    response: Response,
    queue: str = Query(default="", max_length=30),
    project_workspace_id: int | None = Query(default=None, gt=0),
    search: str = Query(default="", max_length=180),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=256),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    service = _authorized(db, tenant_id, user_id, "commercial_strategy.read", VIEW_ROLES)
    items, next_cursor = service.list_page(
        queue=queue,
        project_workspace_id=project_workspace_id,
        search=search,
        limit=limit,
        cursor=cursor,
    )
    _page_headers(response, limit=limit, count=len(items), next_cursor=next_cursor)
    return items


@router.post("", response_model=CommercialStrategyOut, status_code=status.HTTP_201_CREATED)
def create_strategy(
    payload: CommercialStrategyCreateIn,
    response: Response,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "commercial_strategy.create", AUTHOR_ROLES).create(
        payload.project_workspace_id,
        payload.version_purpose,
        idempotency_key,
    )
    _etag(response, result.revision_version)
    return result


# ADMIN endpoints precede the dynamic /{strategy_id} route intentionally.
@router.get("/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    records = _authorized(db, tenant_id, user_id, "commercial_strategy.admin.configure", CONFIG_ROLES).configurations()
    return [AdminConfigurationOut.model_validate(item) for item in records]


@router.post("/admin/configurations/effective-preview", response_model=CommercialConfigurationPreviewOut)
def configuration_preview(
    payload: CommercialConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(
        db, tenant_id, user_id, "commercial_strategy.admin.configure", CONFIG_ROLES
    ).configuration_preview(payload.project_workspace_id, payload.configuration_id, payload.content_json)


@router.post("/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationOut)
def clone_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "commercial_strategy.admin.configure", CONFIG_ROLES
    ).clone_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return AdminConfigurationOut.model_validate(result)


@router.put("/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: CommercialConfigurationUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "commercial_strategy.admin.configure", CONFIG_ROLES
    ).update_configuration(
        configuration_id,
        expected_version,
        payload.name,
        payload.description,
        payload.content_json,
    )
    _etag(response, result.version)
    return AdminConfigurationOut.model_validate(result)


@router.post("/admin/configurations/{configuration_id}/publish", response_model=AdminConfigurationOut)
def publish_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "commercial_strategy.admin.publish", CONFIG_ROLES
    ).publish_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return AdminConfigurationOut.model_validate(result)


@router.post("/admin/configurations/{configuration_id}/archive", response_model=AdminConfigurationOut)
def archive_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "commercial_strategy.admin.publish", CONFIG_ROLES
    ).archive_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return AdminConfigurationOut.model_validate(result)


@router.get("/{strategy_id}", response_model=CommercialStrategyOut)
def get_strategy(
    strategy_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "commercial_strategy.read", VIEW_ROLES).get(strategy_id)
    _etag(response, result.revision_version)
    return result


@router.put("/{strategy_id}/versions/{version_id}", response_model=CommercialStrategyVersionOut)
def update_version(
    strategy_id: int,
    version_id: int,
    payload: CommercialStrategyUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "commercial_strategy.edit", AUTHOR_ROLES).update_version(
        strategy_id,
        version_id,
        expected_version,
        content_json=payload.content_json,
        fel_stage_code=payload.fel_stage_code,
        reviewer_user_id=payload.reviewer_user_id,
    )
    _etag(response, result.revision_version)
    return result


def _action_endpoint(permission: str, roles: frozenset[str], method: str):
    def endpoint(
        strategy_id: int,
        version_id: int,
        response: Response,
        expected_version: int = Depends(_if_match),
        idempotency_key: str = Depends(_idempotency_key),
        db: Session = Depends(get_db),
        tenant_id: int = Depends(get_tenant_id),
        user_id: int = Depends(get_user_id),
    ) -> CommercialStrategyVersionOut:
        service = _authorized(db, tenant_id, user_id, permission, roles)
        result = getattr(service, method)(strategy_id, version_id, expected_version, idempotency_key)
        _etag(response, result.revision_version)
        return result

    return endpoint


router.add_api_route(
    "/{strategy_id}/versions/{version_id}/submit",
    _action_endpoint("commercial_strategy.submit", AUTHOR_ROLES, "submit"),
    methods=["POST"],
    response_model=CommercialStrategyVersionOut,
    name="submit_commercial_strategy",
    operation_id="submit_commercial_strategy",
)
router.add_api_route(
    "/{strategy_id}/versions/{version_id}/start-review",
    _action_endpoint("commercial_strategy.review", REVIEWER_ROLES, "start_review"),
    methods=["POST"],
    response_model=CommercialStrategyVersionOut,
    name="start_commercial_strategy_review",
    operation_id="start_commercial_strategy_review",
)
router.add_api_route(
    "/{strategy_id}/versions/{version_id}/complete",
    _action_endpoint("commercial_strategy.complete", REVIEWER_ROLES, "complete"),
    methods=["POST"],
    response_model=CommercialStrategyVersionOut,
    name="complete_commercial_strategy",
    operation_id="complete_commercial_strategy",
)


@router.post("/{strategy_id}/versions/{version_id}/return", response_model=CommercialStrategyVersionOut)
def return_version(
    strategy_id: int,
    version_id: int,
    payload: CommercialStrategyReturnIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "commercial_strategy.review", REVIEWER_ROLES).return_version(
        strategy_id, version_id, expected_version, idempotency_key, payload.reason
    )
    _etag(response, result.revision_version)
    return result


@router.post("/{strategy_id}/versions/{version_id}/void", response_model=CommercialStrategyVersionOut)
def void_version(
    strategy_id: int,
    version_id: int,
    payload: CommercialStrategyVoidIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "commercial_strategy.edit", AUTHOR_ROLES).void(
        strategy_id, version_id, expected_version, idempotency_key, payload.reason
    )
    _etag(response, result.revision_version)
    return result


@router.post("/{strategy_id}/new-revision", response_model=CommercialStrategyVersionOut, status_code=201)
def new_revision(
    strategy_id: int,
    payload: CommercialStrategyRevisionIn,
    response: Response,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "commercial_strategy.create_revision", AUTHOR_ROLES).new_revision(
        strategy_id, payload.version_purpose, idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.get("/{strategy_id}/readiness", response_model=CommercialStrategyReadinessOut)
def readiness(
    strategy_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "commercial_strategy.read", VIEW_ROLES).readiness(strategy_id)


@router.get("/{strategy_id}/history", response_model=list[CommercialStrategyHistoryOut])
def history(
    strategy_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "commercial_strategy.read", VIEW_ROLES).history(strategy_id)


@router.post("/{strategy_id}/refresh-preview", response_model=CommercialStrategyRefreshPreviewOut)
def refresh_preview(
    strategy_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "commercial_strategy.refresh", AUTHOR_ROLES).refresh_preview(strategy_id)


@router.post("/{strategy_id}/refresh-apply", response_model=CommercialStrategyVersionOut)
def refresh_apply(
    strategy_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "commercial_strategy.refresh", AUTHOR_ROLES).refresh_apply(
        strategy_id, expected_version, idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@project_router.get("/{project_id}/commercial-strategy", response_model=CommercialStrategyOut)
def project_strategy(
    project_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "commercial_strategy.read", VIEW_ROLES).by_project(project_id)
    _etag(response, result.revision_version)
    return result


@project_router.get("/{project_id}/commercial-readiness-evidence", response_model=CommercialReadinessProviderOut)
def project_commercial_evidence(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "commercial_strategy.read", VIEW_ROLES).provider_evidence(project_id)
