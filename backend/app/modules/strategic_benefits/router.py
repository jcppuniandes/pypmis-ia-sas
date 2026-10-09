"""Strict USER/ADMIN REST surface for Gate 07M-BEN."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.strategic_benefits.schemas import (
    BenefitCreateIn,
    BenefitMeasureCreateIn,
    BenefitMeasureOut,
    BenefitMeasureUpdateIn,
    BenefitsConfigurationPreviewIn,
    BenefitsConfigurationPreviewOut,
    BenefitsConfigurationUpdateIn,
    BenefitsHistoryOut,
    BenefitsOptionsOut,
    BenefitsPlanCreateIn,
    BenefitsPlanOut,
    BenefitsPlanReturnIn,
    BenefitsPlanRevisionIn,
    BenefitsPlanVersionOut,
    BenefitsPlanVersionUpdateIn,
    BenefitsPlanVoidIn,
    BenefitsReadinessOut,
    BenefitsReadinessProviderOut,
    BenefitsRefreshPreviewOut,
    BenefitsTraceabilityRowOut,
    BenefitUpdateIn,
    StrategicBenefitOut,
)
from app.modules.strategic_benefits.service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    StrategicBenefitsService,
)

router = APIRouter(prefix="/strategic-benefits-plans")
project_router = APIRouter(prefix="/projects")

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "benefits_plan_author",
        "benefits_plan_reviewer",
        "benefits_plan_viewer",
        "portfolio_manager",
    }
)
AUTHOR_ROLES = frozenset({"organization_admin", "benefits_plan_author"})
REVIEWER_ROLES = frozenset({"organization_admin", "benefits_plan_reviewer"})
CONFIG_ROLES = frozenset({"organization_admin", "configuration_admin", "benefits_plan_config_admin"})


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
) -> StrategicBenefitsService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    return StrategicBenefitsService(db, tenant_id, context.user.id, context)


def _version_etag(service: StrategicBenefitsService, plan_id: int) -> int:
    plan = service.get(plan_id)
    if plan.current_version is None:
        raise HTTPException(status_code=409, detail={"code": "CURRENT_BENEFITS_PLAN_VERSION_REQUIRED"})
    return plan.current_version.revision_version


@router.get("/options", response_model=BenefitsOptionsOut)
def options(
    project_workspace_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "benefits_plan.read", VIEW_ROLES).options(project_workspace_id)


@router.get("", response_model=list[BenefitsPlanOut])
def list_plans(
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
    service = _authorized(db, tenant_id, user_id, "benefits_plan.read", VIEW_ROLES)
    items, next_cursor = service.list_page(
        queue=queue,
        project_workspace_id=project_workspace_id,
        search=search,
        limit=limit,
        cursor=cursor,
    )
    _page_headers(response, limit=limit, count=len(items), next_cursor=next_cursor)
    return items


@router.post("", response_model=BenefitsPlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(
    payload: BenefitsPlanCreateIn,
    response: Response,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "benefits_plan.create", AUTHOR_ROLES).create(
        payload.project_workspace_id, payload.version_purpose, idempotency_key
    )
    _etag(response, result.revision_version)
    return result


# ADMIN routes deliberately precede the dynamic /{plan_id} route.
@router.get("/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    records = _authorized(db, tenant_id, user_id, "benefits_plan.admin.configure", CONFIG_ROLES).configurations()
    return [AdminConfigurationOut.model_validate(item) for item in records]


@router.post("/admin/configurations/effective-preview", response_model=BenefitsConfigurationPreviewOut)
def configuration_preview(
    payload: BenefitsConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "benefits_plan.admin.configure", CONFIG_ROLES).configuration_preview(
        payload.project_workspace_id, payload.configuration_id, payload.content_json
    )


@router.post("/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationOut)
def clone_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "benefits_plan.admin.configure", CONFIG_ROLES).clone_configuration(
        configuration_id, expected_version
    )
    _etag(response, result.version)
    return AdminConfigurationOut.model_validate(result)


@router.put("/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: BenefitsConfigurationUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "benefits_plan.admin.configure", CONFIG_ROLES).update_configuration(
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
    result = _authorized(db, tenant_id, user_id, "benefits_plan.admin.publish", CONFIG_ROLES).publish_configuration(
        configuration_id, expected_version
    )
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
    result = _authorized(db, tenant_id, user_id, "benefits_plan.admin.publish", CONFIG_ROLES).archive_configuration(
        configuration_id, expected_version
    )
    _etag(response, result.version)
    return AdminConfigurationOut.model_validate(result)


@router.get("/{plan_id}", response_model=BenefitsPlanOut)
def get_plan(
    plan_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "benefits_plan.read", VIEW_ROLES).get(plan_id)
    _etag(response, result.revision_version)
    return result


@router.put("/{plan_id}/versions/{version_id}", response_model=BenefitsPlanVersionOut)
def update_version(
    plan_id: int,
    version_id: int,
    payload: BenefitsPlanVersionUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "benefits_plan.edit", AUTHOR_ROLES).update_version(
        plan_id,
        version_id,
        expected_version,
        overview_json=payload.overview_json,
        outputs_json=payload.outputs_json,
        outcomes_json=payload.outcomes_json,
        assumptions_json=payload.assumptions_json,
        constraints_json=payload.constraints_json,
        fel_stage_code=payload.fel_stage_code,
        reviewer_user_id=payload.reviewer_user_id,
    )
    _etag(response, result.revision_version)
    return result


@router.post(
    "/{plan_id}/versions/{version_id}/benefits",
    response_model=StrategicBenefitOut,
    status_code=status.HTTP_201_CREATED,
)
def add_benefit(
    plan_id: int,
    version_id: int,
    payload: BenefitCreateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    service = _authorized(db, tenant_id, user_id, "benefits_plan.edit", AUTHOR_ROLES)
    result = service.add_benefit(plan_id, version_id, expected_version, idempotency_key, payload)
    _etag(response, _version_etag(service, plan_id))
    return result


@router.put("/{plan_id}/versions/{version_id}/benefits/{benefit_id}", response_model=StrategicBenefitOut)
def update_benefit(
    plan_id: int,
    version_id: int,
    benefit_id: int,
    payload: BenefitUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    service = _authorized(db, tenant_id, user_id, "benefits_plan.edit", AUTHOR_ROLES)
    result = service.update_benefit(plan_id, version_id, benefit_id, expected_version, payload)
    _etag(response, _version_etag(service, plan_id))
    return result


@router.post(
    "/{plan_id}/versions/{version_id}/benefits/{benefit_id}/measures",
    response_model=BenefitMeasureOut,
    status_code=status.HTTP_201_CREATED,
)
def add_measure(
    plan_id: int,
    version_id: int,
    benefit_id: int,
    payload: BenefitMeasureCreateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    service = _authorized(db, tenant_id, user_id, "benefits_plan.edit", AUTHOR_ROLES)
    result = service.add_measure(plan_id, version_id, benefit_id, expected_version, idempotency_key, payload)
    _etag(response, _version_etag(service, plan_id))
    return result


@router.put(
    "/{plan_id}/versions/{version_id}/benefits/{benefit_id}/measures/{measure_id}",
    response_model=BenefitMeasureOut,
)
def update_measure(
    plan_id: int,
    version_id: int,
    benefit_id: int,
    measure_id: int,
    payload: BenefitMeasureUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    service = _authorized(db, tenant_id, user_id, "benefits_plan.edit", AUTHOR_ROLES)
    result = service.update_measure(plan_id, version_id, benefit_id, measure_id, expected_version, payload)
    _etag(response, _version_etag(service, plan_id))
    return result


def _action_endpoint(permission: str, roles: frozenset[str], method: str):
    def endpoint(
        plan_id: int,
        version_id: int,
        response: Response,
        expected_version: int = Depends(_if_match),
        idempotency_key: str = Depends(_idempotency_key),
        db: Session = Depends(get_db),
        tenant_id: int = Depends(get_tenant_id),
        user_id: int = Depends(get_user_id),
    ) -> BenefitsPlanVersionOut:
        service = _authorized(db, tenant_id, user_id, permission, roles)
        result = getattr(service, method)(plan_id, version_id, expected_version, idempotency_key)
        _etag(response, result.revision_version)
        return result

    return endpoint


router.add_api_route(
    "/{plan_id}/versions/{version_id}/submit",
    _action_endpoint("benefits_plan.submit", AUTHOR_ROLES, "submit"),
    methods=["POST"],
    response_model=BenefitsPlanVersionOut,
    operation_id="submit_strategic_benefits_plan",
)
router.add_api_route(
    "/{plan_id}/versions/{version_id}/start-review",
    _action_endpoint("benefits_plan.review", REVIEWER_ROLES, "start_review"),
    methods=["POST"],
    response_model=BenefitsPlanVersionOut,
    operation_id="start_strategic_benefits_plan_review",
)
router.add_api_route(
    "/{plan_id}/versions/{version_id}/complete",
    _action_endpoint("benefits_plan.complete", REVIEWER_ROLES, "complete"),
    methods=["POST"],
    response_model=BenefitsPlanVersionOut,
    operation_id="complete_strategic_benefits_plan",
)


@router.post("/{plan_id}/versions/{version_id}/return", response_model=BenefitsPlanVersionOut)
def return_version(
    plan_id: int,
    version_id: int,
    payload: BenefitsPlanReturnIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "benefits_plan.review", REVIEWER_ROLES).return_version(
        plan_id, version_id, expected_version, idempotency_key, payload.reason
    )
    _etag(response, result.revision_version)
    return result


@router.post("/{plan_id}/versions/{version_id}/void", response_model=BenefitsPlanVersionOut)
def void_version(
    plan_id: int,
    version_id: int,
    payload: BenefitsPlanVoidIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "benefits_plan.edit", AUTHOR_ROLES).void(
        plan_id, version_id, expected_version, idempotency_key, payload.reason
    )
    _etag(response, result.revision_version)
    return result


@router.post("/{plan_id}/new-revision", response_model=BenefitsPlanVersionOut, status_code=201)
def new_revision(
    plan_id: int,
    payload: BenefitsPlanRevisionIn,
    response: Response,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "benefits_plan.create_revision", AUTHOR_ROLES).new_revision(
        plan_id, payload.version_purpose, idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.get("/{plan_id}/readiness", response_model=BenefitsReadinessOut)
def readiness(
    plan_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "benefits_plan.read", VIEW_ROLES).readiness(plan_id)


@router.get("/{plan_id}/history", response_model=list[BenefitsHistoryOut])
def history(
    plan_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "benefits_plan.read", VIEW_ROLES).history(plan_id)


@router.get("/{plan_id}/traceability", response_model=list[BenefitsTraceabilityRowOut])
def traceability(
    plan_id: int,
    response: Response,
    version_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, max_length=256),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    service = _authorized(db, tenant_id, user_id, "benefits_plan.read", VIEW_ROLES)
    items, next_cursor = service.traceability_page(plan_id, version_id=version_id, limit=limit, cursor=cursor)
    _page_headers(response, limit=limit, count=len(items), next_cursor=next_cursor)
    return items


@router.post("/{plan_id}/refresh-preview", response_model=BenefitsRefreshPreviewOut)
def refresh_preview(
    plan_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "benefits_plan.refresh", AUTHOR_ROLES).refresh_preview(plan_id)


@router.post("/{plan_id}/refresh-apply", response_model=BenefitsPlanVersionOut)
def refresh_apply(
    plan_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "benefits_plan.refresh", AUTHOR_ROLES).refresh_apply(
        plan_id, expected_version, idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@project_router.get("/{project_id}/strategic-benefits-plan", response_model=BenefitsPlanOut)
def project_plan(
    project_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "benefits_plan.read", VIEW_ROLES).by_project(project_id)
    _etag(response, result.revision_version)
    return result


@project_router.get("/{project_id}/benefits-readiness-evidence", response_model=BenefitsReadinessProviderOut)
def project_benefits_evidence(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "benefits_plan.read", VIEW_ROLES).provider_evidence(project_id)
