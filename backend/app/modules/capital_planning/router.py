"""HTTP API for Strategic Capital Planning and Demand Wave 1."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.capital_planning.schemas import (
    AllocationComparisonOut,
    AllocationLinesReplaceIn,
    AllocationOptionsOut,
    AllocationPlanCreate,
    AllocationPlanHistoryItemOut,
    AllocationPlanOut,
    AllocationPlanPageOut,
    AllocationPlanUpdate,
    BucketClassificationBatchOut,
    BucketClassificationIn,
    BucketClassificationOut,
    BucketClassificationsReplaceIn,
    CapitalPlanningOptionsOut,
    ConfigurationCloneIn,
    ConfigurationPreviewIn,
    ConfigurationPreviewOut,
    ConfigurationRecordOut,
    ConfigurationUpdateIn,
    CycleCreate,
    CycleOut,
    CyclePageOut,
    CycleSummaryOut,
    CycleUpdate,
    DemandCreate,
    DemandHistoryItemOut,
    DemandOut,
    DemandPageOut,
    DemandUpdate,
    IdeaOriginOut,
    IdempotencyIn,
    OriginateIdeaIn,
)
from app.modules.capital_planning.service import CapitalPlanningService
from app.modules.enterprise_structure.permissions import require_enterprise_permission

router = APIRouter(prefix="/capital-planning")

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "capital_planning_cycle_manager",
        "capital_planning_author",
        "capital_planning_reviewer",
        "capital_planning_endorser",
        "capital_planning_originator",
        "capital_planning_viewer",
    }
)
AUTHOR_ROLES = frozenset({"organization_admin", "capital_planning_author"})
CYCLE_ROLES = frozenset({"organization_admin", "capital_planning_cycle_manager"})
REVIEW_ROLES = frozenset({"organization_admin", "capital_planning_reviewer"})
ENDORSE_ROLES = frozenset({"organization_admin", "capital_planning_endorser"})
ORIGIN_ROLES = frozenset({"organization_admin", "capital_planning_originator"})
CONFIG_ROLES = frozenset({"organization_admin", "configuration_admin", "capital_planning_config_admin"})
ALLOCATION_VIEW_ROLES = VIEW_ROLES | frozenset(
    {
        "capital_planning_allocation_author",
        "capital_planning_allocation_reviewer",
        "capital_planning_allocation_endorser",
        "capital_planning_bucket_classifier",
    }
)
ALLOCATION_AUTHOR_ROLES = frozenset(
    {"organization_admin", "capital_planning_author", "capital_planning_allocation_author"}
)
ALLOCATION_REVIEW_ROLES = frozenset(
    {"organization_admin", "capital_planning_reviewer", "capital_planning_allocation_reviewer"}
)
ALLOCATION_ENDORSE_ROLES = frozenset(
    {"organization_admin", "capital_planning_endorser", "capital_planning_allocation_endorser"}
)
BUCKET_CLASSIFY_ROLES = frozenset(
    {
        "organization_admin",
        "capital_planning_author",
        "capital_planning_allocation_author",
        "capital_planning_bucket_classifier",
    }
)


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
) -> CapitalPlanningService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = CapitalPlanningService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/options", response_model=CapitalPlanningOptionsOut)
def options(
    owning_workspace_id: int | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CapitalPlanningOptionsOut:
    return _authorized(db, tenant_id, user_id, "capital_planning.read", VIEW_ROLES).options(owning_workspace_id)


@router.get("/cycles", response_model=CyclePageOut)
def list_cycles(
    status_filter: str = Query("", alias="status", max_length=128),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CyclePageOut:
    return _authorized(db, tenant_id, user_id, "capital_planning.read", VIEW_ROLES).cycles(
        status=status_filter, page=page, page_size=page_size
    )


@router.post("/cycles", response_model=CycleOut, status_code=status.HTTP_201_CREATED)
def create_cycle(
    payload: CycleCreate,
    response: Response,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CycleOut:
    result = _authorized(db, tenant_id, user_id, "capital_planning.cycle.create", CYCLE_ROLES).create_cycle(
        payload, idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.get("/cycles/{cycle_id}", response_model=CycleOut)
def get_cycle(
    cycle_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CycleOut:
    result = _authorized(db, tenant_id, user_id, "capital_planning.read", VIEW_ROLES).cycle(cycle_id)
    _etag(response, result.revision_version)
    return result


@router.put("/cycles/{cycle_id}", response_model=CycleOut)
def update_cycle(
    cycle_id: int,
    payload: CycleUpdate,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CycleOut:
    result = _authorized(db, tenant_id, user_id, "capital_planning.cycle.create", CYCLE_ROLES).update_cycle(
        cycle_id, payload, expected_version
    )
    _etag(response, result.revision_version)
    return result


def _cycle_transition(
    action: str,
    cycle_id: int,
    response: Response,
    expected_version: int,
    idempotency_key: str,
    db: Session,
    tenant_id: int,
    user_id: int,
) -> CycleOut:
    permission = "capital_planning.cycle.close" if action == "close" else "capital_planning.cycle.create"
    result = _authorized(db, tenant_id, user_id, permission, CYCLE_ROLES).transition_cycle(
        cycle_id, action, expected_version, idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.post("/cycles/{cycle_id}/open", response_model=CycleOut)
def open_cycle(
    cycle_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CycleOut:
    return _cycle_transition("open", cycle_id, response, expected_version, idempotency_key, db, tenant_id, user_id)


@router.post("/cycles/{cycle_id}/review/start", response_model=CycleOut)
def review_cycle(
    cycle_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CycleOut:
    return _cycle_transition("review", cycle_id, response, expected_version, idempotency_key, db, tenant_id, user_id)


@router.post("/cycles/{cycle_id}/close", response_model=CycleOut)
def close_cycle(
    cycle_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CycleOut:
    return _cycle_transition("close", cycle_id, response, expected_version, idempotency_key, db, tenant_id, user_id)


@router.get("/cycles/{cycle_id}/summary", response_model=CycleSummaryOut)
def cycle_summary(
    cycle_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CycleSummaryOut:
    return _authorized(db, tenant_id, user_id, "capital_planning.read", VIEW_ROLES).cycle_summary(cycle_id)


@router.get("/demands/summary", response_model=CycleSummaryOut)
def demand_summary(
    planning_cycle_id: int | None = None,
    status_filter: str = Query("", alias="status", max_length=128),
    theme: str = Query("", max_length=120),
    strategic_objective: str = Query("", max_length=120),
    driver: str = Query("", max_length=120),
    sponsor_user_id: int | None = None,
    owning_workspace_id: int | None = None,
    urgency: str = Query("", max_length=40),
    target_horizon: str = Query("", max_length=80),
    potential_portfolio_id: int | None = None,
    uncertainty_level: str = Query("", max_length=80),
    search: str = Query("", max_length=220),
    mine: bool = False,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CycleSummaryOut:
    return _authorized(db, tenant_id, user_id, "capital_planning.read", VIEW_ROLES).demand_summary(
        planning_cycle_id=planning_cycle_id,
        status=status_filter,
        theme_code=theme,
        strategic_objective_code=strategic_objective,
        driver=driver,
        sponsor_user_id=sponsor_user_id,
        owning_workspace_id=owning_workspace_id,
        urgency=urgency,
        target_horizon=target_horizon,
        potential_portfolio_id=potential_portfolio_id,
        uncertainty_level=uncertainty_level,
        search=search,
        mine=mine,
    )


@router.get("/demands", response_model=DemandPageOut)
def list_demands(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    planning_cycle_id: int | None = None,
    status_filter: str = Query("", alias="status", max_length=128),
    theme: str = Query("", max_length=120),
    strategic_objective: str = Query("", max_length=120),
    driver: str = Query("", max_length=120),
    sponsor_user_id: int | None = None,
    owning_workspace_id: int | None = None,
    urgency: str = Query("", max_length=40),
    target_horizon: str = Query("", max_length=80),
    potential_portfolio_id: int | None = None,
    uncertainty_level: str = Query("", max_length=80),
    search: str = Query("", max_length=220),
    mine: bool = False,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DemandPageOut:
    return _authorized(db, tenant_id, user_id, "capital_planning.read", VIEW_ROLES).demands(
        page=page,
        page_size=page_size,
        planning_cycle_id=planning_cycle_id,
        status=status_filter,
        theme_code=theme,
        strategic_objective_code=strategic_objective,
        driver=driver,
        sponsor_user_id=sponsor_user_id,
        owning_workspace_id=owning_workspace_id,
        urgency=urgency,
        target_horizon=target_horizon,
        potential_portfolio_id=potential_portfolio_id,
        uncertainty_level=uncertainty_level,
        search=search,
        mine=mine,
    )


@router.post("/demands", response_model=DemandOut, status_code=status.HTTP_201_CREATED)
def create_demand(
    payload: DemandCreate,
    response: Response,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DemandOut:
    result = _authorized(db, tenant_id, user_id, "capital_planning.demand.create", AUTHOR_ROLES).create_demand(
        payload, idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.get("/demands/{demand_id}", response_model=DemandOut)
def get_demand(
    demand_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DemandOut:
    result = _authorized(db, tenant_id, user_id, "capital_planning.read", VIEW_ROLES).demand(demand_id)
    _etag(response, result.revision_version)
    return result


@router.put("/demands/{demand_id}", response_model=DemandOut)
def update_demand(
    demand_id: int,
    payload: DemandUpdate,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DemandOut:
    result = _authorized(db, tenant_id, user_id, "capital_planning.demand.edit", AUTHOR_ROLES).update_demand(
        demand_id, payload, expected_version
    )
    _etag(response, result.revision_version)
    return result


def _demand_transition_endpoint(action: str, permission: str, roles: frozenset[str]):
    def endpoint(
        demand_id: int,
        response: Response,
        payload: IdempotencyIn | None = None,
        expected_version: int = Depends(_if_match),
        idempotency_key: str = Depends(_idempotency_key),
        db: Session = Depends(get_db),
        tenant_id: int = Depends(get_tenant_id),
        user_id: int = Depends(get_user_id),
    ) -> DemandOut:
        result = _authorized(db, tenant_id, user_id, permission, roles).transition_demand(
            demand_id,
            action,
            expected_version,
            idempotency_key,
            payload.reason if payload else "",
        )
        _etag(response, result.revision_version)
        return result

    return endpoint


router.add_api_route(
    "/demands/{demand_id}/submit",
    _demand_transition_endpoint("submit", "capital_planning.demand.submit", AUTHOR_ROLES),
    methods=["POST"],
    response_model=DemandOut,
)
router.add_api_route(
    "/demands/{demand_id}/review/start",
    _demand_transition_endpoint("review", "capital_planning.demand.review", REVIEW_ROLES),
    methods=["POST"],
    response_model=DemandOut,
)
router.add_api_route(
    "/demands/{demand_id}/return",
    _demand_transition_endpoint("return", "capital_planning.demand.review", REVIEW_ROLES),
    methods=["POST"],
    response_model=DemandOut,
)
router.add_api_route(
    "/demands/{demand_id}/endorse",
    _demand_transition_endpoint("endorse", "capital_planning.demand.endorse", ENDORSE_ROLES),
    methods=["POST"],
    response_model=DemandOut,
)
router.add_api_route(
    "/demands/{demand_id}/defer",
    _demand_transition_endpoint("defer", "capital_planning.demand.review", REVIEW_ROLES),
    methods=["POST"],
    response_model=DemandOut,
)
router.add_api_route(
    "/demands/{demand_id}/cancel",
    _demand_transition_endpoint("cancel", "capital_planning.demand.edit", AUTHOR_ROLES),
    methods=["POST"],
    response_model=DemandOut,
)


@router.post("/demands/{demand_id}/originate-idea", response_model=IdeaOriginOut)
def originate_idea(
    demand_id: int,
    payload: OriginateIdeaIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> IdeaOriginOut:
    result = _authorized(db, tenant_id, user_id, "capital_planning.idea.originate", ORIGIN_ROLES).originate_idea(
        demand_id, payload, expected_version, idempotency_key
    )
    response.headers["Cache-Control"] = "private, no-store"
    return result


@router.get("/demands/{demand_id}/originated-ideas", response_model=list[IdeaOriginOut])
def originated_ideas(
    demand_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[IdeaOriginOut]:
    return _authorized(db, tenant_id, user_id, "capital_planning.read", VIEW_ROLES).origins(
        demand_id,
        page=page,
        page_size=page_size,
    )


@router.get("/demands/{demand_id}/history", response_model=list[DemandHistoryItemOut])
def demand_history(
    demand_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[DemandHistoryItemOut]:
    return _authorized(db, tenant_id, user_id, "capital_planning.read", VIEW_ROLES).history(demand_id)


# ---------------------------------------------------------------------------
# Wave 2A Strategic Capital Buckets and Allocation Plans
# ---------------------------------------------------------------------------


@router.get("/allocation-options", response_model=AllocationOptionsOut)
def allocation_options(
    scope_workspace_id: int | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AllocationOptionsOut:
    return _authorized(
        db,
        tenant_id,
        user_id,
        "capital_planning.allocation.read",
        ALLOCATION_VIEW_ROLES,
    ).allocation_options(scope_workspace_id)


@router.get("/allocation-plans", response_model=AllocationPlanPageOut)
def allocation_plans(
    planning_cycle_id: int | None = None,
    status_filter: str = Query("", alias="status", max_length=128),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AllocationPlanPageOut:
    return _authorized(
        db,
        tenant_id,
        user_id,
        "capital_planning.allocation.read",
        ALLOCATION_VIEW_ROLES,
    ).allocation_plans(
        planning_cycle_id=planning_cycle_id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/allocation-plans",
    response_model=AllocationPlanOut,
    status_code=status.HTTP_201_CREATED,
)
def create_allocation_plan(
    payload: AllocationPlanCreate,
    response: Response,
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AllocationPlanOut:
    result = _authorized(
        db,
        tenant_id,
        user_id,
        "capital_planning.allocation.create",
        ALLOCATION_AUTHOR_ROLES,
    ).create_allocation_plan(payload, idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.get("/allocation-plans/{plan_id}", response_model=AllocationPlanOut)
def allocation_plan(
    plan_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AllocationPlanOut:
    result = _authorized(
        db,
        tenant_id,
        user_id,
        "capital_planning.allocation.read",
        ALLOCATION_VIEW_ROLES,
    ).allocation_plan(plan_id)
    _etag(response, result.revision_version)
    return result


@router.put("/allocation-plans/{plan_id}", response_model=AllocationPlanOut)
def update_allocation_plan(
    plan_id: int,
    payload: AllocationPlanUpdate,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AllocationPlanOut:
    result = _authorized(
        db,
        tenant_id,
        user_id,
        "capital_planning.allocation.edit",
        ALLOCATION_AUTHOR_ROLES,
    ).update_allocation_plan(plan_id, payload, expected_version)
    _etag(response, result.revision_version)
    return result


@router.put("/allocation-plans/{plan_id}/lines", response_model=AllocationPlanOut)
def replace_allocation_lines(
    plan_id: int,
    payload: AllocationLinesReplaceIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AllocationPlanOut:
    result = _authorized(
        db,
        tenant_id,
        user_id,
        "capital_planning.allocation.edit",
        ALLOCATION_AUTHOR_ROLES,
    ).replace_allocation_lines(plan_id, payload, expected_version)
    _etag(response, result.revision_version)
    return result


@router.post(
    "/allocation-plans/{plan_id}/classifications",
    response_model=BucketClassificationOut,
    status_code=status.HTTP_201_CREATED,
)
def classify_bucket(
    plan_id: int,
    payload: BucketClassificationIn,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BucketClassificationOut:
    return _authorized(
        db,
        tenant_id,
        user_id,
        "capital_planning.bucket.classify",
        BUCKET_CLASSIFY_ROLES,
    ).classify_bucket(plan_id, payload, expected_version, idempotency_key)


@router.put(
    "/allocation-plans/{plan_id}/classifications",
    response_model=BucketClassificationBatchOut,
)
def replace_bucket_classifications(
    plan_id: int,
    payload: BucketClassificationsReplaceIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BucketClassificationBatchOut:
    result = _authorized(
        db,
        tenant_id,
        user_id,
        "capital_planning.bucket.classify",
        BUCKET_CLASSIFY_ROLES,
    ).replace_bucket_classifications(plan_id, payload, expected_version, idempotency_key)
    _etag(response, result.allocation_plan.revision_version)
    return result


def _allocation_transition_endpoint(action: str, permission: str, roles: frozenset[str]):
    def endpoint(
        plan_id: int,
        response: Response,
        payload: IdempotencyIn | None = None,
        expected_version: int = Depends(_if_match),
        idempotency_key: str = Depends(_idempotency_key),
        db: Session = Depends(get_db),
        tenant_id: int = Depends(get_tenant_id),
        user_id: int = Depends(get_user_id),
    ) -> AllocationPlanOut:
        result = _authorized(db, tenant_id, user_id, permission, roles).transition_allocation_plan(
            plan_id,
            action,
            expected_version,
            idempotency_key,
            payload.reason if payload else "",
        )
        _etag(response, result.revision_version)
        return result

    return endpoint


router.add_api_route(
    "/allocation-plans/{plan_id}/submit",
    _allocation_transition_endpoint("submit", "capital_planning.allocation.submit", ALLOCATION_AUTHOR_ROLES),
    methods=["POST"],
    response_model=AllocationPlanOut,
)
router.add_api_route(
    "/allocation-plans/{plan_id}/review/start",
    _allocation_transition_endpoint("review", "capital_planning.allocation.review", ALLOCATION_REVIEW_ROLES),
    methods=["POST"],
    response_model=AllocationPlanOut,
)
router.add_api_route(
    "/allocation-plans/{plan_id}/return",
    _allocation_transition_endpoint("return", "capital_planning.allocation.review", ALLOCATION_REVIEW_ROLES),
    methods=["POST"],
    response_model=AllocationPlanOut,
)
router.add_api_route(
    "/allocation-plans/{plan_id}/endorse",
    _allocation_transition_endpoint("endorse", "capital_planning.allocation.endorse", ALLOCATION_ENDORSE_ROLES),
    methods=["POST"],
    response_model=AllocationPlanOut,
)


@router.post(
    "/allocation-plans/{plan_id}/revisions",
    response_model=AllocationPlanOut,
    status_code=status.HTTP_201_CREATED,
)
def create_allocation_plan_revision(
    plan_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AllocationPlanOut:
    result = _authorized(
        db,
        tenant_id,
        user_id,
        "capital_planning.allocation.create",
        ALLOCATION_AUTHOR_ROLES,
    ).create_allocation_plan_revision(plan_id, expected_version, idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.get(
    "/allocation-plans/{plan_id}/comparison",
    response_model=AllocationComparisonOut,
)
def allocation_comparison(
    plan_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AllocationComparisonOut:
    return _authorized(
        db,
        tenant_id,
        user_id,
        "capital_planning.allocation.read",
        ALLOCATION_VIEW_ROLES,
    ).allocation_comparison(plan_id)


@router.get(
    "/allocation-plans/{plan_id}/history",
    response_model=list[AllocationPlanHistoryItemOut],
)
def allocation_plan_history(
    plan_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AllocationPlanHistoryItemOut]:
    return _authorized(
        db,
        tenant_id,
        user_id,
        "capital_planning.allocation.read",
        ALLOCATION_VIEW_ROLES,
    ).allocation_plan_history(plan_id)


@router.get("/admin/configurations", response_model=list[ConfigurationRecordOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ConfigurationRecordOut]:
    records = _authorized(db, tenant_id, user_id, "capital_planning.admin.configure", CONFIG_ROLES).configurations()
    return [ConfigurationRecordOut.model_validate(item) for item in records]


@router.post("/admin/preview", response_model=ConfigurationPreviewOut)
def preview_configuration(
    payload: ConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationPreviewOut:
    return _authorized(db, tenant_id, user_id, "capital_planning.admin.configure", CONFIG_ROLES).configuration_preview(
        payload.owning_workspace_id
    )


@router.post("/admin/configurations/{configuration_id}/clone", response_model=ConfigurationRecordOut)
def clone_configuration(
    configuration_id: int,
    payload: ConfigurationCloneIn | None = None,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationRecordOut:
    record = _authorized(db, tenant_id, user_id, "capital_planning.admin.configure", CONFIG_ROLES).clone_configuration(
        configuration_id,
        expected_version,
        target_workspace_id=payload.target_workspace_id if payload else None,
    )
    return ConfigurationRecordOut.model_validate(record)


@router.put("/admin/configurations/{configuration_id}", response_model=ConfigurationRecordOut)
def update_configuration(
    configuration_id: int,
    payload: ConfigurationUpdateIn,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationRecordOut:
    record = _authorized(db, tenant_id, user_id, "capital_planning.admin.configure", CONFIG_ROLES).update_configuration(
        configuration_id,
        expected_version,
        name=payload.name,
        description=payload.description,
        content=payload.content_json,
    )
    return ConfigurationRecordOut.model_validate(record)


def _configuration_transition(permission: str, method: str):
    def endpoint(
        configuration_id: int,
        expected_version: int = Depends(_if_match),
        db: Session = Depends(get_db),
        tenant_id: int = Depends(get_tenant_id),
        user_id: int = Depends(get_user_id),
    ) -> ConfigurationRecordOut:
        service = _authorized(db, tenant_id, user_id, permission, CONFIG_ROLES)
        return ConfigurationRecordOut.model_validate(getattr(service, method)(configuration_id, expected_version))

    return endpoint


router.add_api_route(
    "/admin/configurations/{configuration_id}/publish",
    _configuration_transition("capital_planning.admin.publish", "publish_configuration"),
    methods=["POST"],
    response_model=ConfigurationRecordOut,
)
router.add_api_route(
    "/admin/configurations/{configuration_id}/archive",
    _configuration_transition("capital_planning.admin.configure", "archive_configuration"),
    methods=["POST"],
    response_model=ConfigurationRecordOut,
)
