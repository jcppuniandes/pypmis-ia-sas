"""HTTP API for Wave 3A Periodic Portfolio Review."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.schemas import (
    ActionApprovalIn,
    ActionDispatchIn,
    CompleteReviewIn,
    PortfolioAllocationOut,
    PortfolioBudgetResourcesOut,
    PortfolioGateStatusOut,
    PortfolioReviewActionCreate,
    PortfolioReviewActionOut,
    PortfolioReviewActionPageOut,
    PortfolioReviewActionUpdate,
    PortfolioReviewComparisonOut,
    PortfolioReviewConclusionCreate,
    PortfolioReviewConclusionOut,
    PortfolioReviewConclusionUpdate,
    PortfolioReviewCreate,
    PortfolioReviewHistoryItemOut,
    PortfolioReviewOptionsOut,
    PortfolioReviewPageOut,
    PortfolioReviewSessionOut,
    PortfolioReviewSnapshotOut,
    PortfolioReviewTrendsOut,
    PortfolioReviewUpdate,
    ProjectMatrixPageOut,
    ReviewConfigurationCloneIn,
    ReviewConfigurationOut,
    ReviewConfigurationPreviewIn,
    ReviewConfigurationPreviewOut,
    ReviewConfigurationUpdateIn,
    ReviewTransitionIn,
    SnapshotCommandIn,
    SnapshotPreviewOut,
)
from app.modules.portfolio_review.service import PortfolioReviewService

router = APIRouter()

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "portfolio_review_viewer",
        "portfolio_review_preparer",
        "portfolio_review_authority",
        "portfolio_review_board_member",
        "portfolio_review_action_owner",
        "portfolio_review_action_approver",
        "portfolio_review_action_dispatcher",
    }
)
CREATE_ROLES = frozenset({"organization_admin", "portfolio_review_preparer"})
PREPARE_ROLES = frozenset({"organization_admin", "portfolio_review_preparer"})
FREEZE_ROLES = frozenset({"organization_admin", "portfolio_review_preparer"})
CONDUCT_ROLES = frozenset({"organization_admin", "portfolio_review_authority", "portfolio_review_board_member"})
COMPLETE_ROLES = frozenset({"organization_admin", "portfolio_review_authority"})
ACTION_CREATE_ROLES = frozenset({"organization_admin", "portfolio_review_preparer"})
ACTION_UPDATE_ROLES = frozenset({"organization_admin", "portfolio_review_preparer", "portfolio_review_action_owner"})
ACTION_APPROVE_ROLES = frozenset(
    {
        "organization_admin",
        "portfolio_review_authority",
        "portfolio_review_board_member",
        "portfolio_review_action_approver",
    }
)
ACTION_DISPATCH_ROLES = frozenset(
    {"organization_admin", "portfolio_review_authority", "portfolio_review_action_dispatcher"}
)
CONFIG_ROLES = frozenset({"organization_admin", "configuration_admin", "portfolio_review_configuration_admin"})


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


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'
    response.headers["Cache-Control"] = "private, no-store"


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    roles: frozenset[str],
) -> PortfolioReviewService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    return PortfolioReviewService(db, tenant_id, context.user.id, context)


def _authorized_action_update(db: Session, tenant_id: int, user_id: int, action_id: int) -> PortfolioReviewService:
    """Keep update privilege tied to its own grant scope, not the owner grant."""
    visible = _authorized(db, tenant_id, user_id, "portfolio_review.action.update", ACTION_UPDATE_ROLES)
    action = visible._action(action_id)
    review = visible._session(action.review_session_id)
    try:
        privileged = _authorized(
            db,
            tenant_id,
            user_id,
            "portfolio_review.action.update",
            frozenset({"organization_admin", "portfolio_review_preparer"}),
        )
        privileged._assert_scope(review.portfolio_workspace_id)
        return privileged
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
    owner = _authorized(
        db, tenant_id, user_id, "portfolio_review.action.update", frozenset({"portfolio_review_action_owner"})
    )
    owner._assert_scope(review.portfolio_workspace_id)
    if action.owner_user_id != owner.actor_id:
        raise HTTPException(status_code=403, detail={"code": "REVIEW_ACTION_OWNER_SCOPE_DENIED"})
    return owner


@router.get("/portfolio-reviews/options", response_model=PortfolioReviewOptionsOut)
def options(
    portfolio_workspace_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewOptionsOut:
    return _authorized(db, tenant_id, user_id, "portfolio_review.read", VIEW_ROLES).options(portfolio_workspace_id)


@router.get("/portfolio-reviews", response_model=PortfolioReviewPageOut)
def list_reviews(
    portfolio_workspace_id: int | None = Query(default=None, gt=0),
    review_status: str | None = Query(default=None, alias="status"),
    review_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=250),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewPageOut:
    return _authorized(db, tenant_id, user_id, "portfolio_review.read", VIEW_ROLES).list_sessions(
        portfolio_workspace_id=portfolio_workspace_id,
        status=review_status,
        review_type=review_type,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/portfolio-reviews",
    response_model=PortfolioReviewSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_review(
    payload: PortfolioReviewCreate,
    response: Response,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewSessionOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_review.create", CREATE_ROLES).create_session(
        payload, idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.get("/portfolio-reviews/trends", response_model=PortfolioReviewTrendsOut)
def trends(
    portfolio_workspace_id: int = Query(gt=0),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewTrendsOut:
    return _authorized(db, tenant_id, user_id, "portfolio_review.read", VIEW_ROLES).trends(portfolio_workspace_id)


@router.get("/portfolio-review-actions", response_model=PortfolioReviewActionPageOut)
def list_actions(
    review_session_id: int | None = Query(default=None, gt=0),
    owner_user_id: int | None = Query(default=None, gt=0),
    action_status: str | None = Query(default=None, alias="status"),
    subject_type: str | None = None,
    subject_id: int | None = Query(default=None, gt=0),
    overdue: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=250),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewActionPageOut:
    return _authorized(db, tenant_id, user_id, "portfolio_review.read", VIEW_ROLES).list_actions(
        review_session_id=review_session_id,
        owner_user_id=owner_user_id,
        status=action_status,
        subject_type=subject_type,
        subject_id=subject_id,
        overdue=overdue,
        page=page,
        page_size=page_size,
    )


# ADMIN routes are intentionally separate from live Review mutations.
@router.get("/portfolio-reviews/admin/configurations", response_model=list[ReviewConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ReviewConfigurationOut]:
    rows = _authorized(db, tenant_id, user_id, "portfolio_review.admin.configure", CONFIG_ROLES).configurations()
    return [ReviewConfigurationOut.model_validate(item) for item in rows]


@router.post("/portfolio-reviews/admin/preview", response_model=ReviewConfigurationPreviewOut)
def configuration_preview(
    payload: ReviewConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ReviewConfigurationPreviewOut:
    return _authorized(db, tenant_id, user_id, "portfolio_review.admin.configure", CONFIG_ROLES).configuration_preview(
        payload.portfolio_workspace_id, configuration_id=payload.configuration_id, content=payload.content_json
    )


@router.post(
    "/portfolio-reviews/admin/configurations/{configuration_id}/clone",
    response_model=ReviewConfigurationOut,
)
def clone_configuration(
    configuration_id: int,
    payload: ReviewConfigurationCloneIn | None = None,
    response: Response = None,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ReviewConfigurationOut:
    record = _authorized(db, tenant_id, user_id, "portfolio_review.admin.configure", CONFIG_ROLES).clone_configuration(
        configuration_id,
        expected_version,
        target_workspace_id=payload.target_workspace_id if payload else None,
    )
    if response is not None:
        _etag(response, record.version)
    return ReviewConfigurationOut.model_validate(record)


@router.put("/portfolio-reviews/admin/configurations/{configuration_id}", response_model=ReviewConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: ReviewConfigurationUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ReviewConfigurationOut:
    record = _authorized(db, tenant_id, user_id, "portfolio_review.admin.configure", CONFIG_ROLES).update_configuration(
        configuration_id,
        expected_version,
        name=payload.name,
        description=payload.description,
        content=payload.content_json,
    )
    _etag(response, record.version)
    return ReviewConfigurationOut.model_validate(record)


def _configuration_transition(permission: str, method: str):
    def endpoint(
        configuration_id: int,
        response: Response,
        expected_version: int = Depends(_if_match),
        db: Session = Depends(get_db),
        tenant_id: int = Depends(get_tenant_id),
        user_id: int = Depends(get_user_id),
    ) -> ReviewConfigurationOut:
        service = _authorized(db, tenant_id, user_id, permission, CONFIG_ROLES)
        record = getattr(service, method)(configuration_id, expected_version)
        _etag(response, record.version)
        return ReviewConfigurationOut.model_validate(record)

    return endpoint


router.add_api_route(
    "/portfolio-reviews/admin/configurations/{configuration_id}/publish",
    _configuration_transition("portfolio_review.admin.publish", "publish_configuration"),
    methods=["POST"],
    response_model=ReviewConfigurationOut,
)
router.add_api_route(
    "/portfolio-reviews/admin/configurations/{configuration_id}/archive",
    _configuration_transition("portfolio_review.admin.configure", "archive_configuration"),
    methods=["POST"],
    response_model=ReviewConfigurationOut,
)


@router.get("/portfolio-reviews/{review_session_id}", response_model=PortfolioReviewSessionOut)
def get_review(
    review_session_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewSessionOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_review.read", VIEW_ROLES).get_session(review_session_id)
    _etag(response, result.revision_version)
    return result


@router.put("/portfolio-reviews/{review_session_id}", response_model=PortfolioReviewSessionOut)
def update_review(
    review_session_id: int,
    payload: PortfolioReviewUpdate,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewSessionOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_review.prepare", PREPARE_ROLES).update_session(
        review_session_id, payload, expected_version
    )
    _etag(response, result.revision_version)
    return result


@router.post("/portfolio-reviews/{review_session_id}/prepare", response_model=PortfolioReviewSessionOut)
def prepare_review(
    review_session_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewSessionOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_review.prepare", PREPARE_ROLES).prepare_session(
        review_session_id, expected_version
    )
    _etag(response, result.revision_version)
    return result


@router.post("/portfolio-reviews/{review_session_id}/snapshot-preview", response_model=SnapshotPreviewOut)
def snapshot_preview(
    review_session_id: int,
    payload: SnapshotCommandIn | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> SnapshotPreviewOut:
    return _authorized(db, tenant_id, user_id, "portfolio_review.freeze_snapshot", FREEZE_ROLES).snapshot_preview(
        review_session_id, payload
    )


@router.post("/portfolio-reviews/{review_session_id}/freeze-snapshot", response_model=PortfolioReviewSnapshotOut)
def freeze_snapshot(
    review_session_id: int,
    payload: SnapshotCommandIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewSnapshotOut:
    service = _authorized(db, tenant_id, user_id, "portfolio_review.freeze_snapshot", FREEZE_ROLES)
    result = service.freeze_snapshot(review_session_id, payload, expected_version, idempotency_key)
    review = service.get_session(review_session_id)
    _etag(response, review.revision_version)
    return result


@router.post("/portfolio-reviews/{review_session_id}/start-review", response_model=PortfolioReviewSessionOut)
def start_review(
    review_session_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewSessionOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_review.conduct", CONDUCT_ROLES).start_review(
        review_session_id, expected_version
    )
    _etag(response, result.revision_version)
    return result


@router.post("/portfolio-reviews/{review_session_id}/complete", response_model=PortfolioReviewSessionOut)
def complete_review(
    review_session_id: int,
    payload: CompleteReviewIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewSessionOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_review.complete", COMPLETE_ROLES).complete_review(
        review_session_id, payload, expected_version, idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.post("/portfolio-reviews/{review_session_id}/return", response_model=PortfolioReviewSessionOut)
@router.post("/portfolio-reviews/{review_session_id}/cancel", response_model=PortfolioReviewSessionOut)
@router.post("/portfolio-reviews/{review_session_id}/supersede", response_model=PortfolioReviewSessionOut)
def transition_review(
    review_session_id: int,
    payload: ReviewTransitionIn,
    request: Request,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewSessionOut:
    target = {"return": "RETURNED", "cancel": "CANCELLED", "supersede": "SUPERSEDED"}[
        request.url.path.rsplit("/", 1)[-1]
    ]
    result = _authorized(db, tenant_id, user_id, "portfolio_review.conduct", CONDUCT_ROLES).transition_session(
        review_session_id, target, payload, expected_version, idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.get("/portfolio-reviews/{review_session_id}/project-matrix", response_model=ProjectMatrixPageOut)
def project_matrix(
    review_session_id: int,
    bucket: str | None = None,
    rank_min: int | None = Query(default=None, ge=1),
    rank_max: int | None = Query(default=None, ge=1),
    project_type: str | None = None,
    gate_status: str | None = None,
    fid_status: str | None = None,
    budget_status: str | None = None,
    resource_status: str | None = None,
    review_action: str | None = None,
    action_owner_user_id: int | None = Query(default=None, gt=0),
    blocked: bool | None = None,
    stale: bool | None = None,
    unclassified: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectMatrixPageOut:
    return _authorized(db, tenant_id, user_id, "portfolio_review.read", VIEW_ROLES).project_matrix(
        review_session_id,
        bucket=bucket,
        rank_min=rank_min,
        rank_max=rank_max,
        project_type=project_type,
        gate_status=gate_status,
        fid_status=fid_status,
        budget_status=budget_status,
        resource_status=resource_status,
        review_action=review_action,
        action_owner_user_id=action_owner_user_id,
        blocked=blocked,
        stale=stale,
        unclassified=unclassified,
        page=page,
        page_size=page_size,
    )


@router.get("/portfolio-reviews/{review_session_id}/allocation", response_model=PortfolioAllocationOut)
def allocation(
    review_session_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioAllocationOut:
    return _authorized(db, tenant_id, user_id, "portfolio_review.read", VIEW_ROLES).allocation(review_session_id)


@router.get("/portfolio-reviews/{review_session_id}/budget-resources", response_model=PortfolioBudgetResourcesOut)
def budget_resources(
    review_session_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioBudgetResourcesOut:
    return _authorized(db, tenant_id, user_id, "portfolio_review.read", VIEW_ROLES).budget_resources(review_session_id)


@router.get("/portfolio-reviews/{review_session_id}/gate-status", response_model=PortfolioGateStatusOut)
def gate_status(
    review_session_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioGateStatusOut:
    return _authorized(db, tenant_id, user_id, "portfolio_review.read", VIEW_ROLES).gate_status(review_session_id)


@router.get(
    "/portfolio-reviews/{review_session_id}/history",
    response_model=list[PortfolioReviewHistoryItemOut],
)
def review_history(
    review_session_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[PortfolioReviewHistoryItemOut]:
    return _authorized(db, tenant_id, user_id, "portfolio_review.read", VIEW_ROLES).history(review_session_id)


@router.get(
    "/portfolio-reviews/{review_session_id}/compare/{other_review_session_id}",
    response_model=PortfolioReviewComparisonOut,
)
def compare_reviews(
    review_session_id: int,
    other_review_session_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewComparisonOut:
    return _authorized(db, tenant_id, user_id, "portfolio_review.read", VIEW_ROLES).compare(
        review_session_id, other_review_session_id
    )


@router.post(
    "/portfolio-reviews/{review_session_id}/conclusions",
    response_model=PortfolioReviewConclusionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_conclusion(
    review_session_id: int,
    payload: PortfolioReviewConclusionCreate,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewConclusionOut:
    service = _authorized(db, tenant_id, user_id, "portfolio_review.conduct", CONDUCT_ROLES)
    result = service.create_conclusion(review_session_id, payload, expected_version)
    _etag(response, service.get_session(review_session_id).revision_version)
    return result


@router.put("/portfolio-review-conclusions/{conclusion_id}", response_model=PortfolioReviewConclusionOut)
def update_conclusion(
    conclusion_id: int,
    payload: PortfolioReviewConclusionUpdate,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewConclusionOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_review.conduct", CONDUCT_ROLES).update_conclusion(
        conclusion_id, payload, expected_version
    )
    _etag(response, result.revision_version)
    return result


@router.post(
    "/portfolio-reviews/{review_session_id}/actions",
    response_model=PortfolioReviewActionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_action(
    review_session_id: int,
    payload: PortfolioReviewActionCreate,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewActionOut:
    service = _authorized(db, tenant_id, user_id, "portfolio_review.action.create", ACTION_CREATE_ROLES)
    result = service.create_action(review_session_id, payload, expected_version, idempotency_key)
    _etag(response, service.get_session(review_session_id).revision_version)
    return result


@router.put("/portfolio-review-actions/{action_id}", response_model=PortfolioReviewActionOut)
def update_action(
    action_id: int,
    payload: PortfolioReviewActionUpdate,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewActionOut:
    result = _authorized_action_update(db, tenant_id, user_id, action_id).update_action(
        action_id, payload, expected_version
    )
    _etag(response, result.revision_version)
    return result


@router.post("/portfolio-review-actions/{action_id}/approve", response_model=PortfolioReviewActionOut)
def approve_action(
    action_id: int,
    response: Response,
    payload: ActionApprovalIn | None = None,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewActionOut:
    result = _authorized(
        db, tenant_id, user_id, "portfolio_review.action.approve", ACTION_APPROVE_ROLES
    ).approve_action(action_id, payload or ActionApprovalIn(), expected_version, idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.post("/portfolio-review-actions/{action_id}/dispatch", response_model=PortfolioReviewActionOut)
def dispatch_action(
    action_id: int,
    response: Response,
    payload: ActionDispatchIn | None = None,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioReviewActionOut:
    result = _authorized(
        db, tenant_id, user_id, "portfolio_review.action.dispatch", ACTION_DISPATCH_ROLES
    ).dispatch_action(action_id, payload or ActionDispatchIn(), expected_version, idempotency_key)
    _etag(response, result.revision_version)
    return result
