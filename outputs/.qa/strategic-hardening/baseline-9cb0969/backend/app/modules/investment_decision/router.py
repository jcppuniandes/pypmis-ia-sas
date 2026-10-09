"""HTTP routes for Gate 07K Investment Decision / FID governance."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.investment_decision.schemas import (
    ConfigurationPreviewIn,
    ConfigurationPreviewOut,
    ConfigurationUpdateIn,
    DecisionCreateIn,
    DecisionDecideIn,
    DecisionHistoryItemOut,
    DecisionReadinessOut,
    DecisionReadyIn,
    DecisionUpdateIn,
    DecisionVoteIn,
    IdempotencyIn,
    InvestmentDecisionOut,
)
from app.modules.investment_decision.service import InvestmentDecisionService

router = APIRouter()

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "portfolio_manager",
        "investment_decision_preparer",
        "investment_decision_reviewer",
        "investment_decision_maker",
        "investment_decision_committee_member",
        "investment_decision_committee_chair",
        "investment_decision_viewer",
    }
)
PREPARER_ROLES = frozenset({"organization_admin", "portfolio_manager", "investment_decision_preparer"})
REVIEWER_ROLES = frozenset({"organization_admin", "investment_decision_reviewer"})
DECIDER_ROLES = frozenset(
    {
        "organization_admin",
        "investment_decision_maker",
        "investment_decision_committee_member",
        "investment_decision_committee_chair",
    }
)
CONFIG_ROLES = frozenset({"organization_admin", "investment_decision_configuration_admin"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    normalized = if_match.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"})
    return int(normalized)


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def _authorized(db, tenant_id, user_id, permission, roles) -> InvestmentDecisionService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = InvestmentDecisionService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/investment-decisions", response_model=list[InvestmentDecisionOut])
def decisions(
    status: str = Query(default=""),
    outcome: str = Query(default=""),
    profile_code: str = Query(default=""),
    portfolio_workspace_id: int | None = Query(default=None, gt=0),
    queue: str = Query(default=""),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "investment_decision.read", VIEW_ROLES).list(
        status=status,
        outcome=outcome,
        profile_code=profile_code,
        portfolio_workspace_id=portfolio_workspace_id,
        queue=queue,
    )


@router.post("/investment-decisions", response_model=InvestmentDecisionOut)
def create_decision(
    payload: DecisionCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "investment_decision.create", PREPARER_ROLES).create(payload)
    _etag(response, result.revision_version)
    return result


@router.get("/investment-decisions/{decision_id}", response_model=InvestmentDecisionOut)
def decision(
    decision_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "investment_decision.read", VIEW_ROLES).get(decision_id)
    _etag(response, result.revision_version)
    return result


@router.put("/investment-decisions/{decision_id}", response_model=InvestmentDecisionOut)
def update_decision(
    decision_id: int,
    payload: DecisionUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "investment_decision.edit", PREPARER_ROLES).update(
        decision_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


def _transition(decision_id, payload, response, expected_version, db, tenant_id, user_id, action):
    permission, roles = {
        "submit": ("investment_decision.submit", PREPARER_ROLES),
        "start-review": ("investment_decision.review", REVIEWER_ROLES),
        "void": ("investment_decision.void", PREPARER_ROLES | REVIEWER_ROLES),
    }[action]
    service = _authorized(db, tenant_id, user_id, permission, roles)
    method = {
        "submit": service.submit,
        "start-review": service.start_review,
        "void": service.void,
    }[action]
    result = method(decision_id, expected_version, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.post("/investment-decisions/{decision_id}/submit", response_model=InvestmentDecisionOut)
def submit_decision(
    decision_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _transition(decision_id, payload, response, expected_version, db, tenant_id, user_id, "submit")


@router.post("/investment-decisions/{decision_id}/start-review", response_model=InvestmentDecisionOut)
def start_review(
    decision_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _transition(decision_id, payload, response, expected_version, db, tenant_id, user_id, "start-review")


@router.post("/investment-decisions/{decision_id}/ready", response_model=InvestmentDecisionOut)
def ready_decision(
    decision_id: int,
    payload: DecisionReadyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "investment_decision.review", REVIEWER_ROLES).ready(
        decision_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.post("/investment-decisions/{decision_id}/decide", response_model=InvestmentDecisionOut)
def decide(
    decision_id: int,
    payload: DecisionDecideIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "investment_decision.decide", DECIDER_ROLES).decide(
        decision_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.post("/investment-decisions/{decision_id}/void", response_model=InvestmentDecisionOut)
def void_decision(
    decision_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _transition(decision_id, payload, response, expected_version, db, tenant_id, user_id, "void")


@router.get("/investment-decisions/{decision_id}/committee")
def committee(decision_id: int, db=Depends(get_db), tenant_id=Depends(get_tenant_id), user_id=Depends(get_user_id)):
    return _authorized(db, tenant_id, user_id, "investment_decision.read", VIEW_ROLES).committee(decision_id)


@router.post("/investment-decisions/{decision_id}/votes", response_model=InvestmentDecisionOut)
def vote(
    decision_id: int,
    payload: DecisionVoteIn,
    response: Response,
    db=Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    user_id=Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "investment_decision.vote", DECIDER_ROLES).cast_vote(
        decision_id, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/investment-decisions/{decision_id}/package")
def package(decision_id: int, db=Depends(get_db), tenant_id=Depends(get_tenant_id), user_id=Depends(get_user_id)):
    return _authorized(db, tenant_id, user_id, "investment_decision.read", VIEW_ROLES).package(decision_id)


@router.get("/investment-decisions/{decision_id}/readiness", response_model=DecisionReadinessOut)
def readiness(decision_id: int, db=Depends(get_db), tenant_id=Depends(get_tenant_id), user_id=Depends(get_user_id)):
    return _authorized(db, tenant_id, user_id, "investment_decision.read", VIEW_ROLES).readiness(decision_id)


@router.get("/investment-decisions/{decision_id}/history", response_model=list[DecisionHistoryItemOut])
def history(decision_id: int, db=Depends(get_db), tenant_id=Depends(get_tenant_id), user_id=Depends(get_user_id)):
    return _authorized(db, tenant_id, user_id, "investment_decision.read", VIEW_ROLES).history(decision_id)


@router.get("/investment-decisions/{decision_id}/authorization-output")
def authorization_output(
    decision_id: int, db=Depends(get_db), tenant_id=Depends(get_tenant_id), user_id=Depends(get_user_id)
):
    return _authorized(db, tenant_id, user_id, "investment_decision.read", VIEW_ROLES).authorization_output(decision_id)


@router.get("/investment-decision/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(db=Depends(get_db), tenant_id=Depends(get_tenant_id), user_id=Depends(get_user_id)):
    return _authorized(db, tenant_id, user_id, "investment_decision.admin.configure", CONFIG_ROLES).configurations()


@router.post("/investment-decision/admin/configurations/preview", response_model=ConfigurationPreviewOut)
def configuration_preview(
    payload: ConfigurationPreviewIn,
    db=Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    user_id=Depends(get_user_id),
):
    return _authorized(
        db, tenant_id, user_id, "investment_decision.admin.configure", CONFIG_ROLES
    ).configuration_preview(payload.portfolio_workspace_id, payload.configuration_id, payload.content_json)


@router.post("/investment-decision/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationOut)
def clone_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db=Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    user_id=Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "investment_decision.admin.configure", CONFIG_ROLES
    ).clone_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result


@router.put("/investment-decision/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: ConfigurationUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db=Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    user_id=Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "investment_decision.admin.configure", CONFIG_ROLES
    ).update_configuration(configuration_id, expected_version, payload.name, payload.description, payload.content_json)
    _etag(response, result.version)
    return result


@router.post(
    "/investment-decision/admin/configurations/{configuration_id}/publish", response_model=AdminConfigurationOut
)
def publish_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db=Depends(get_db),
    tenant_id=Depends(get_tenant_id),
    user_id=Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "investment_decision.admin.publish", CONFIG_ROLES
    ).publish_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result
