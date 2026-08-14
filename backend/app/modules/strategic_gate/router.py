"""FastAPI routes for Gate 07C Strategic Gate Decision."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id, get_user_id
from app.api.v1.routers.admin_configuration import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.strategic_gate.schemas import (
    PortfolioIntakeReadinessOut,
    StrategicGateConfigurationPreviewIn,
    StrategicGateConfigurationPreviewOut,
    StrategicGateConfigurationUpdateIn,
    StrategicGateCreate,
    StrategicGateDecideIn,
    StrategicGateDecisionOut,
    StrategicGateHistoryItemOut,
    StrategicGateOptionsOut,
    StrategicGatePreviewOut,
    StrategicGateReturnIn,
    StrategicGateUpdate,
)
from app.modules.strategic_gate.service import StrategicGateService

router = APIRouter(prefix="/strategic-gate-decisions")
proposal_router = APIRouter(prefix="/project-proposals")
idea_router = APIRouter(prefix="/ideas")

PREPARER_ROLES = frozenset({"organization_admin", "gate_preparer"})
REVIEWER_ROLES = frozenset({"organization_admin", "gate_reviewer"})
DECISION_ROLES = frozenset({"organization_admin", "gate_decision_maker", "gate_committee_member"})
CONFIG_ROLES = frozenset({"organization_admin", "configuration_admin", "gate_configuration_admin"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    normalized = if_match.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail={"reason": "INVALID_IF_MATCH"})
    return int(normalized)


def _idempotency(value: str | None = Header(default=None, alias="Idempotency-Key")) -> str:
    return (value or "").strip()[:180]


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    roles: frozenset[str] | None = None,
) -> StrategicGateService:
    context = require_enterprise_permission(
        db,
        tenant_id,
        user_id,
        permission,
        allowed_role_codes=roles,
    )
    service = StrategicGateService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


def _etag(response: Response, value: StrategicGateDecisionOut) -> StrategicGateDecisionOut:
    response.headers["ETag"] = f'"{value.revision_version}"'
    response.headers["Cache-Control"] = "private, no-store"
    return value


@router.get("/options", response_model=StrategicGateOptionsOut)
def options(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicGateOptionsOut:
    return _authorized(db, tenant_id, user_id, "strategic_gate.read").options()


@router.post("/preview", response_model=StrategicGatePreviewOut)
def preview(
    payload: StrategicGateCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicGatePreviewOut:
    return _authorized(db, tenant_id, user_id, "strategic_gate.create", PREPARER_ROLES).preview(
        payload.project_proposal_id
    )


@router.post("", response_model=StrategicGateDecisionOut, status_code=status.HTTP_201_CREATED)
def create(
    payload: StrategicGateCreate,
    response: Response,
    idempotency_key: str = Depends(_idempotency),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicGateDecisionOut:
    service = _authorized(db, tenant_id, user_id, "strategic_gate.create", PREPARER_ROLES)
    return _etag(response, service.create(payload.project_proposal_id, idempotency_key))


@router.get("", response_model=list[StrategicGateDecisionOut])
def list_decisions(
    state_filter: str = Query("", alias="state", max_length=32),
    outcome: str = Query("", max_length=24),
    search: str = Query("", max_length=180),
    owning_workspace_id: int | None = None,
    queue: str = Query("", max_length=30),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[StrategicGateDecisionOut]:
    return _authorized(db, tenant_id, user_id, "strategic_gate.read").list(
        state_filter=state_filter,
        outcome_filter=outcome,
        search=search,
        owning_workspace_id=owning_workspace_id,
        queue=queue,
    )


@router.get("/admin/configurations/list", response_model=list[AdminConfigurationOut])
def admin_configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AdminConfigurationOut]:
    service = _authorized(
        db,
        tenant_id,
        user_id,
        "strategic_gate.admin.configure",
        CONFIG_ROLES,
    )
    return [AdminConfigurationOut.model_validate(item) for item in service.admin_configurations()]


@router.post("/admin/configuration/preview", response_model=StrategicGateConfigurationPreviewOut)
def configuration_preview(
    payload: StrategicGateConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicGateConfigurationPreviewOut:
    return _authorized(
        db,
        tenant_id,
        user_id,
        "strategic_gate.admin.configure",
        CONFIG_ROLES,
    ).configuration_preview(payload.project_proposal_id)


@router.post("/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationOut)
def clone_configuration(
    configuration_id: int,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    service = _authorized(
        db,
        tenant_id,
        user_id,
        "strategic_gate.admin.configure",
        CONFIG_ROLES,
    )
    return AdminConfigurationOut.model_validate(service.clone_configuration(configuration_id, expected))


@router.put("/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: StrategicGateConfigurationUpdateIn,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    service = _authorized(
        db,
        tenant_id,
        user_id,
        "strategic_gate.admin.configure",
        CONFIG_ROLES,
    )
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
    service = _authorized(
        db,
        tenant_id,
        user_id,
        "strategic_gate.admin.publish",
        CONFIG_ROLES,
    )
    return AdminConfigurationOut.model_validate(service.publish_configuration(configuration_id, expected))


@router.get("/{decision_id}", response_model=StrategicGateDecisionOut)
def get_decision(
    decision_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicGateDecisionOut:
    return _etag(response, _authorized(db, tenant_id, user_id, "strategic_gate.read").get(decision_id))


@router.put("/{decision_id}", response_model=StrategicGateDecisionOut)
def update_decision(
    decision_id: int,
    payload: StrategicGateUpdate,
    response: Response,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicGateDecisionOut:
    service = _authorized(db, tenant_id, user_id, "strategic_gate.edit", PREPARER_ROLES)
    return _etag(response, service.update(decision_id, payload, expected))


def _transition_route(permission: str, roles: frozenset[str], method: str):
    def endpoint(
        decision_id: int,
        response: Response,
        expected: int = Depends(_if_match),
        idempotency_key: str = Depends(_idempotency),
        db: Session = Depends(get_db),
        tenant_id: int = Depends(get_tenant_id),
        user_id: int = Depends(get_user_id),
    ) -> StrategicGateDecisionOut:
        service = _authorized(db, tenant_id, user_id, permission, roles)
        return _etag(response, getattr(service, method)(decision_id, expected, idempotency_key))

    return endpoint


router.add_api_route(
    "/{decision_id}/submit",
    _transition_route("strategic_gate.submit", PREPARER_ROLES, "submit"),
    methods=["POST"],
    response_model=StrategicGateDecisionOut,
)
router.add_api_route(
    "/{decision_id}/start-review",
    _transition_route("strategic_gate.review", REVIEWER_ROLES, "start_review"),
    methods=["POST"],
    response_model=StrategicGateDecisionOut,
)
router.add_api_route(
    "/{decision_id}/void",
    _transition_route("strategic_gate.void", PREPARER_ROLES | REVIEWER_ROLES, "void"),
    methods=["POST"],
    response_model=StrategicGateDecisionOut,
)
router.add_api_route(
    "/{decision_id}/new-round",
    _transition_route("strategic_gate.create", PREPARER_ROLES, "new_round"),
    methods=["POST"],
    response_model=StrategicGateDecisionOut,
)


@router.post("/{decision_id}/return-to-preparer", response_model=StrategicGateDecisionOut)
def return_to_preparer(
    decision_id: int,
    payload: StrategicGateReturnIn,
    response: Response,
    expected: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicGateDecisionOut:
    service = _authorized(db, tenant_id, user_id, "strategic_gate.review", REVIEWER_ROLES)
    return _etag(
        response,
        service.return_to_preparer(decision_id, payload, expected, idempotency_key),
    )


@router.post("/{decision_id}/decide", response_model=StrategicGateDecisionOut)
def decide(
    decision_id: int,
    payload: StrategicGateDecideIn,
    response: Response,
    expected: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicGateDecisionOut:
    service = _authorized(db, tenant_id, user_id, "strategic_gate.decide", DECISION_ROLES)
    return _etag(response, service.decide(decision_id, payload, expected, idempotency_key))


@router.get("/{decision_id}/history", response_model=list[StrategicGateHistoryItemOut])
def history(
    decision_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[StrategicGateHistoryItemOut]:
    return _authorized(db, tenant_id, user_id, "strategic_gate.read").history(decision_id)


@router.get("/{decision_id}/portfolio-intake-readiness", response_model=PortfolioIntakeReadinessOut)
def portfolio_intake_readiness(
    decision_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioIntakeReadinessOut:
    return _authorized(db, tenant_id, user_id, "strategic_gate.read").portfolio_intake_readiness(decision_id)


@proposal_router.get(
    "/{proposal_id}/strategic-gate-decisions",
    response_model=list[StrategicGateDecisionOut],
)
def proposal_decisions(
    proposal_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[StrategicGateDecisionOut]:
    return _authorized(db, tenant_id, user_id, "strategic_gate.read").related_to_proposal(proposal_id)


@proposal_router.post(
    "/{proposal_id}/strategic-gate-decisions/preview",
    response_model=StrategicGatePreviewOut,
)
def proposal_decision_preview(
    proposal_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicGatePreviewOut:
    return _authorized(db, tenant_id, user_id, "strategic_gate.create", PREPARER_ROLES).preview(proposal_id)


@idea_router.get("/{idea_id}/strategic-gate-decisions", response_model=list[StrategicGateDecisionOut])
def idea_decisions(
    idea_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[StrategicGateDecisionOut]:
    return _authorized(db, tenant_id, user_id, "strategic_gate.read").related_to_idea(idea_id)
