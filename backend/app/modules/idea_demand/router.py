"""USER/ADMIN APIs for Idea & Demand Manager Gate 07A."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext, require_enterprise_permission
from app.modules.idea_demand.schemas import (
    DecisionIn,
    EvaluationIn,
    IdeaConfigurationPreviewIn,
    IdeaConfigurationPreviewOut,
    IdeaConfigurationUpdateIn,
    IdeaCreate,
    IdeaHistoryItemOut,
    IdeaOptionsOut,
    IdeaOut,
    IdeaUpdate,
    OwnerAssignmentIn,
    ProposalReadinessOut,
    RoutingIn,
    ScreeningIn,
)
from app.modules.idea_demand.service import IdeaDemandService

router = APIRouter(prefix="/ideas")

INTAKE_ROLES = frozenset({"organization_admin", "idea_intake_reviewer"})
OWNER_ROLES = frozenset({"organization_admin", "idea_owner"})
DECISION_ROLES = frozenset({"organization_admin", "idea_decision_maker"})
CONFIG_ROLES = frozenset({"organization_admin", "configuration_admin", "idea_configuration_admin"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    normalized = if_match.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        raise HTTPException(status_code=400, detail={"reason": "INVALID_IF_MATCH"})
    return int(normalized)


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    roles: frozenset[str] | None = None,
) -> tuple[IdeaDemandService, EnterprisePermissionContext]:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = IdeaDemandService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service, context


def _etag(response: Response, value: IdeaOut) -> IdeaOut:
    response.headers["ETag"] = f'"{value.revision_version}"'
    response.headers["Cache-Control"] = "private, no-store"
    return value


@router.get("/options", response_model=IdeaOptionsOut)
def options(
    owning_workspace_id: int | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> IdeaOptionsOut:
    service, _ = _authorized(db, tenant_id, user_id, "idea.create")
    return service.options(owning_workspace_id)


@router.post("", response_model=IdeaOut, status_code=status.HTTP_201_CREATED)
def create(
    payload: IdeaCreate,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> IdeaOut:
    service, _ = _authorized(db, tenant_id, user_id, "idea.create")
    return _etag(response, service.create(payload))


@router.get("", response_model=list[IdeaOut])
def list_ideas(
    state_filter: str = Query("", alias="state", max_length=40),
    search: str = Query("", max_length=180),
    owning_workspace_id: int | None = None,
    queue: str = Query("", max_length=30),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[IdeaOut]:
    service, _ = _authorized(db, tenant_id, user_id, "idea.read")
    return service.list(state=state_filter, search=search, owning_workspace_id=owning_workspace_id, queue=queue)


@router.get("/{idea_id}", response_model=IdeaOut)
def get_idea(
    idea_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> IdeaOut:
    service, _ = _authorized(db, tenant_id, user_id, "idea.read")
    return _etag(response, service.get(idea_id))


@router.put("/{idea_id}", response_model=IdeaOut)
def update_idea(
    idea_id: int,
    payload: IdeaUpdate,
    response: Response,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> IdeaOut:
    service, _ = _authorized(db, tenant_id, user_id, "idea.edit")
    return _etag(response, service.update(idea_id, payload, expected))


def _transition_route(permission: str, roles: frozenset[str] | None, method: str):
    def endpoint(
        idea_id: int,
        response: Response,
        expected: int = Depends(_if_match),
        db: Session = Depends(get_db),
        tenant_id: int = Depends(get_tenant_id),
        user_id: int = Depends(get_user_id),
    ) -> IdeaOut:
        service, _ = _authorized(db, tenant_id, user_id, permission, roles)
        return _etag(response, getattr(service, method)(idea_id, expected))

    return endpoint


router.add_api_route("/{idea_id}/submit", _transition_route("idea.submit", None, "submit"), methods=["POST"], response_model=IdeaOut)
router.add_api_route("/{idea_id}/cancel", _transition_route("idea.cancel", None, "cancel"), methods=["POST"], response_model=IdeaOut)
router.add_api_route(
    "/{idea_id}/evaluation/start",
    _transition_route("idea.evaluate", OWNER_ROLES, "start_evaluation"),
    methods=["POST"],
    response_model=IdeaOut,
)


@router.post("/{idea_id}/screen", response_model=IdeaOut)
def screen(
    idea_id: int,
    payload: ScreeningIn,
    response: Response,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> IdeaOut:
    service, _ = _authorized(db, tenant_id, user_id, "idea.screen", INTAKE_ROLES)
    return _etag(response, service.screen(idea_id, payload, expected))


@router.post("/{idea_id}/route", response_model=IdeaOut)
def route(
    idea_id: int,
    payload: RoutingIn,
    response: Response,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> IdeaOut:
    service, _ = _authorized(db, tenant_id, user_id, "idea.route", INTAKE_ROLES)
    return _etag(response, service.route(idea_id, payload, expected))


@router.post("/{idea_id}/assign-owner", response_model=IdeaOut)
def assign_owner(
    idea_id: int,
    payload: OwnerAssignmentIn,
    response: Response,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> IdeaOut:
    service, _ = _authorized(db, tenant_id, user_id, "idea.assign_owner", INTAKE_ROLES)
    return _etag(response, service.assign_owner(idea_id, payload, expected))


@router.post("/{idea_id}/evaluation/complete", response_model=IdeaOut)
def complete_evaluation(
    idea_id: int,
    payload: EvaluationIn,
    response: Response,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> IdeaOut:
    service, _ = _authorized(db, tenant_id, user_id, "idea.evaluate", OWNER_ROLES)
    return _etag(response, service.complete_evaluation(idea_id, payload, expected))


def _decision_route(method: str, permission: str, roles: frozenset[str], *, accept: bool | None = None):
    def endpoint(
        idea_id: int,
        payload: DecisionIn,
        response: Response,
        expected: int = Depends(_if_match),
        db: Session = Depends(get_db),
        tenant_id: int = Depends(get_tenant_id),
        user_id: int = Depends(get_user_id),
    ) -> IdeaOut:
        service, _ = _authorized(db, tenant_id, user_id, permission, roles)
        result = service.decide(idea_id, payload, expected, accept=bool(accept)) if method == "decide" else service.return_idea(idea_id, payload, expected)
        return _etag(response, result)

    return endpoint


router.add_api_route("/{idea_id}/accept", _decision_route("decide", "idea.decide", DECISION_ROLES, accept=True), methods=["POST"], response_model=IdeaOut)
router.add_api_route("/{idea_id}/reject", _decision_route("decide", "idea.decide", DECISION_ROLES, accept=False), methods=["POST"], response_model=IdeaOut)
router.add_api_route("/{idea_id}/return", _decision_route("return", "idea.screen", INTAKE_ROLES), methods=["POST"], response_model=IdeaOut)


@router.get("/{idea_id}/proposal-readiness", response_model=ProposalReadinessOut)
def readiness(
    idea_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProposalReadinessOut:
    service, _ = _authorized(db, tenant_id, user_id, "idea.read")
    return service.readiness(idea_id)


@router.get("/{idea_id}/history", response_model=list[IdeaHistoryItemOut])
def history(
    idea_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[IdeaHistoryItemOut]:
    service, _ = _authorized(db, tenant_id, user_id, "idea.read")
    return service.history(idea_id)


@router.get("/admin/configurations/list", response_model=list[AdminConfigurationOut])
def admin_configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AdminConfigurationOut]:
    service, _ = _authorized(db, tenant_id, user_id, "idea.admin.configure", CONFIG_ROLES)
    return [AdminConfigurationOut.model_validate(item) for item in service.admin_configurations()]


@router.post("/admin/configuration/preview", response_model=IdeaConfigurationPreviewOut)
def configuration_preview(
    payload: IdeaConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> IdeaConfigurationPreviewOut:
    service, _ = _authorized(db, tenant_id, user_id, "idea.admin.configure", CONFIG_ROLES)
    return service.configuration_preview(payload.owning_workspace_id)


@router.post("/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationOut)
def clone_configuration(
    configuration_id: int,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    service, _ = _authorized(db, tenant_id, user_id, "idea.admin.configure", CONFIG_ROLES)
    return AdminConfigurationOut.model_validate(service.clone_configuration(configuration_id, expected))


@router.put("/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: IdeaConfigurationUpdateIn,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    service, _ = _authorized(db, tenant_id, user_id, "idea.admin.configure", CONFIG_ROLES)
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
    service, _ = _authorized(db, tenant_id, user_id, "idea.admin.publish", CONFIG_ROLES)
    return AdminConfigurationOut.model_validate(service.publish_configuration(configuration_id, expected))
