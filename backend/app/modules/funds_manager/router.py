"""HTTP routes for Gate 07J-FUND Funds Manager."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.funds_manager.schemas import (
    AdminConfigurationRecordOut,
    ConfigurationCloneIn,
    ConfigurationPreviewIn,
    ConfigurationPreviewOut,
    ConfigurationUpdateIn,
    FundCreateIn,
    FundingAssignmentCreateIn,
    FundingAssignmentOut,
    FundingAssignmentUpdateIn,
    FundingOverviewOut,
    FundingReadinessOut,
    FundingRefreshPreviewOut,
    FundingSourceCreateIn,
    FundingSourceOut,
    FundingSourceUpdateIn,
    FundOut,
    FundUpdateIn,
    IdempotencyIn,
    InvestmentGateFundingEvidenceOut,
    RefreshApplyIn,
)
from app.modules.funds_manager.service import FundsManagerService

router = APIRouter()

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "portfolio_manager",
        "funding_manager",
        "funding_planner",
        "funding_reviewer",
        "funding_viewer",
    }
)
MANAGER_ROLES = frozenset({"organization_admin", "portfolio_manager", "funding_manager"})
PLANNER_ROLES = frozenset({"organization_admin", "funding_manager", "funding_planner"})
REVIEWER_ROLES = frozenset({"organization_admin", "funding_manager", "funding_reviewer"})
CONFIG_ROLES = frozenset({"organization_admin", "funding_configuration_admin"})


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


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    roles: frozenset[str],
) -> FundsManagerService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = FundsManagerService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/funding-sources", response_model=list[FundingSourceOut])
def funding_sources(
    db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), user_id: int = Depends(get_user_id)
) -> list[FundingSourceOut]:
    return _authorized(db, tenant_id, user_id, "funds.read", VIEW_ROLES).funding_sources()


@router.post("/funding-sources", response_model=FundingSourceOut)
def create_funding_source(
    payload: FundingSourceCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingSourceOut:
    result = _authorized(db, tenant_id, user_id, "funding_source.create", PLANNER_ROLES).create_funding_source(payload)
    _etag(response, result.revision_version)
    return result


@router.get("/funding-sources/{source_id}", response_model=FundingSourceOut)
def funding_source(
    source_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingSourceOut:
    result = _authorized(db, tenant_id, user_id, "funds.read", VIEW_ROLES).funding_source(source_id)
    _etag(response, result.revision_version)
    return result


@router.put("/funding-sources/{source_id}", response_model=FundingSourceOut)
def update_funding_source(
    source_id: int,
    payload: FundingSourceUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingSourceOut:
    result = _authorized(db, tenant_id, user_id, "funding_source.edit", PLANNER_ROLES).update_funding_source(
        source_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


def _source_transition(
    action: str,
    source_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int,
    db: Session,
    tenant_id: int,
    user_id: int,
) -> FundingSourceOut:
    result = _authorized(
        db, tenant_id, user_id, "funding_source.manage_status", MANAGER_ROLES
    ).transition_funding_source(source_id, expected_version, action, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.post("/funding-sources/{source_id}/activate", response_model=FundingSourceOut)
def activate_source(
    source_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingSourceOut:
    return _source_transition("activate", source_id, payload, response, expected_version, db, tenant_id, user_id)


@router.post("/funding-sources/{source_id}/suspend", response_model=FundingSourceOut)
def suspend_source(
    source_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingSourceOut:
    return _source_transition("suspend", source_id, payload, response, expected_version, db, tenant_id, user_id)


@router.post("/funding-sources/{source_id}/close", response_model=FundingSourceOut)
def close_source(
    source_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingSourceOut:
    return _source_transition("close", source_id, payload, response, expected_version, db, tenant_id, user_id)


@router.get("/funds", response_model=list[FundOut])
def funds(
    db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), user_id: int = Depends(get_user_id)
) -> list[FundOut]:
    return _authorized(db, tenant_id, user_id, "funds.read", VIEW_ROLES).funds()


@router.post("/funds", response_model=FundOut)
def create_fund(
    payload: FundCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundOut:
    result = _authorized(db, tenant_id, user_id, "fund.create", PLANNER_ROLES).create_fund(payload)
    _etag(response, result.revision_version)
    return result


@router.get("/funds/{fund_id}", response_model=FundOut)
def fund(
    fund_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundOut:
    result = _authorized(db, tenant_id, user_id, "funds.read", VIEW_ROLES).fund(fund_id)
    _etag(response, result.revision_version)
    return result


@router.put("/funds/{fund_id}", response_model=FundOut)
def update_fund(
    fund_id: int,
    payload: FundUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundOut:
    result = _authorized(db, tenant_id, user_id, "fund.edit", PLANNER_ROLES).update_fund(
        fund_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


def _fund_transition(
    action: str,
    fund_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int,
    db: Session,
    tenant_id: int,
    user_id: int,
) -> FundOut:
    permission = "fund.authorize" if action == "authorize" else "fund.manage_status"
    roles = REVIEWER_ROLES if action == "authorize" else MANAGER_ROLES
    result = _authorized(db, tenant_id, user_id, permission, roles).transition_fund(
        fund_id, expected_version, action, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.post("/funds/{fund_id}/authorize", response_model=FundOut)
def authorize_fund(
    fund_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundOut:
    return _fund_transition("authorize", fund_id, payload, response, expected_version, db, tenant_id, user_id)


@router.post("/funds/{fund_id}/activate", response_model=FundOut)
def activate_fund(
    fund_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundOut:
    return _fund_transition("activate", fund_id, payload, response, expected_version, db, tenant_id, user_id)


@router.post("/funds/{fund_id}/suspend", response_model=FundOut)
def suspend_fund(
    fund_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundOut:
    return _fund_transition("suspend", fund_id, payload, response, expected_version, db, tenant_id, user_id)


@router.post("/funds/{fund_id}/close", response_model=FundOut)
def close_fund(
    fund_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundOut:
    return _fund_transition("close", fund_id, payload, response, expected_version, db, tenant_id, user_id)


@router.get("/funding-assignments", response_model=list[FundingAssignmentOut])
def assignments(
    portfolio_id: int | None = Query(default=None, gt=0),
    project_id: int | None = Query(default=None, gt=0),
    fund_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[FundingAssignmentOut]:
    return _authorized(db, tenant_id, user_id, "funds.read", VIEW_ROLES).funding_assignments(
        portfolio_id=portfolio_id, project_id=project_id, fund_id=fund_id
    )


@router.post("/funding-assignments", response_model=FundingAssignmentOut)
def create_assignment(
    payload: FundingAssignmentCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingAssignmentOut:
    result = _authorized(db, tenant_id, user_id, "funding_assignment.create", PLANNER_ROLES).create_funding_assignment(
        payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/funding-assignments/{assignment_id}", response_model=FundingAssignmentOut)
def assignment(
    assignment_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingAssignmentOut:
    result = _authorized(db, tenant_id, user_id, "funds.read", VIEW_ROLES).funding_assignment(assignment_id)
    _etag(response, result.revision_version)
    return result


@router.put("/funding-assignments/{assignment_id}", response_model=FundingAssignmentOut)
def update_assignment(
    assignment_id: int,
    payload: FundingAssignmentUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingAssignmentOut:
    result = _authorized(db, tenant_id, user_id, "funding_assignment.edit", PLANNER_ROLES).update_funding_assignment(
        assignment_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


def _assignment_transition(
    action: str,
    assignment_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int,
    db: Session,
    tenant_id: int,
    user_id: int,
) -> FundingAssignmentOut:
    permission = f"funding_assignment.{action}"
    roles = REVIEWER_ROLES if action == "confirm" else PLANNER_ROLES
    result = _authorized(db, tenant_id, user_id, permission, roles).transition_funding_assignment(
        assignment_id, expected_version, action, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.post("/funding-assignments/{assignment_id}/reserve", response_model=FundingAssignmentOut)
def reserve_assignment(
    assignment_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingAssignmentOut:
    return _assignment_transition("reserve", assignment_id, payload, response, expected_version, db, tenant_id, user_id)


@router.post("/funding-assignments/{assignment_id}/confirm", response_model=FundingAssignmentOut)
def confirm_assignment(
    assignment_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingAssignmentOut:
    return _assignment_transition("confirm", assignment_id, payload, response, expected_version, db, tenant_id, user_id)


@router.post("/funding-assignments/{assignment_id}/release", response_model=FundingAssignmentOut)
def release_assignment(
    assignment_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingAssignmentOut:
    return _assignment_transition("release", assignment_id, payload, response, expected_version, db, tenant_id, user_id)


@router.post("/funding-assignments/{assignment_id}/cancel", response_model=FundingAssignmentOut)
def cancel_assignment(
    assignment_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingAssignmentOut:
    return _assignment_transition("cancel", assignment_id, payload, response, expected_version, db, tenant_id, user_id)


@router.get("/funds-manager", response_model=FundingOverviewOut)
def overview(
    portfolio_workspace_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingOverviewOut:
    return _authorized(db, tenant_id, user_id, "funds.read", VIEW_ROLES).overview(portfolio_workspace_id)


@router.get("/portfolios/{portfolio_id}/funding", response_model=FundingOverviewOut)
def portfolio_funding(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingOverviewOut:
    return _authorized(db, tenant_id, user_id, "funds.read", VIEW_ROLES).overview(portfolio_id)


@router.get("/portfolios/{portfolio_id}/funding/coverage", response_model=FundingReadinessOut)
def portfolio_coverage(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingReadinessOut:
    return _authorized(db, tenant_id, user_id, "funding_readiness.read", VIEW_ROLES).coverage(portfolio_id)


@router.get("/portfolios/{portfolio_id}/funding/readiness", response_model=FundingReadinessOut)
def portfolio_readiness(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingReadinessOut:
    return _authorized(db, tenant_id, user_id, "funding_readiness.read", VIEW_ROLES).readiness(portfolio_id)


@router.post("/portfolios/{portfolio_id}/funding/readiness/refresh/preview", response_model=FundingRefreshPreviewOut)
def readiness_preview(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingRefreshPreviewOut:
    return _authorized(db, tenant_id, user_id, "funding_readiness.refresh", MANAGER_ROLES).refresh_preview(portfolio_id)


@router.post("/portfolios/{portfolio_id}/funding/readiness/refresh", response_model=FundingReadinessOut)
def readiness_refresh(
    portfolio_id: int,
    payload: RefreshApplyIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingReadinessOut:
    return _authorized(db, tenant_id, user_id, "funding_readiness.refresh", MANAGER_ROLES).refresh(
        portfolio_id, payload.expected_source_hash, payload.idempotency_key
    )


@router.get(
    "/portfolios/{portfolio_id}/funding/investment-gate-evidence", response_model=InvestmentGateFundingEvidenceOut
)
def investment_gate_evidence(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGateFundingEvidenceOut:
    return _authorized(db, tenant_id, user_id, "funding_readiness.read", VIEW_ROLES).investment_gate_evidence(
        portfolio_id
    )


@router.get("/projects/{project_id}/funding", response_model=FundingOverviewOut)
def project_funding(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingOverviewOut:
    return _authorized(db, tenant_id, user_id, "funds.read", VIEW_ROLES).project_funding(project_id)


@router.get("/projects/{project_id}/funding/readiness", response_model=FundingReadinessOut)
def project_readiness(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingReadinessOut:
    service = _authorized(db, tenant_id, user_id, "funding_readiness.read", VIEW_ROLES)
    project = service._project(project_id)
    return service.readiness(service._portfolio_ancestor(project), project_id=project_id)


@router.get("/funds/admin/configurations", response_model=list[AdminConfigurationRecordOut])
def configurations(
    db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), user_id: int = Depends(get_user_id)
) -> list[AdminConfigurationRecordOut]:
    return _authorized(db, tenant_id, user_id, "funds.admin.configure", CONFIG_ROLES).configurations()


@router.post("/funds/admin/configurations/preview", response_model=ConfigurationPreviewOut)
def configuration_preview(
    payload: ConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationPreviewOut:
    return _authorized(db, tenant_id, user_id, "funds.admin.configure", CONFIG_ROLES).configuration_preview(
        payload.portfolio_workspace_id, payload.configuration_id, payload.content_json, payload.fund_assumptions
    )


@router.post("/funds/admin/configurations/clone", response_model=AdminConfigurationRecordOut)
def clone_configuration_alias(
    payload: ConfigurationCloneIn,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationRecordOut:
    return _authorized(db, tenant_id, user_id, "funds.admin.configure", CONFIG_ROLES).clone_configuration(
        payload.configuration_id, expected_version
    )


@router.post("/funds/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationRecordOut)
def clone_configuration(
    configuration_id: int,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationRecordOut:
    return _authorized(db, tenant_id, user_id, "funds.admin.configure", CONFIG_ROLES).clone_configuration(
        configuration_id, expected_version
    )


@router.put("/funds/admin/configurations/{configuration_id}", response_model=AdminConfigurationRecordOut)
def update_configuration(
    configuration_id: int,
    payload: ConfigurationUpdateIn,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationRecordOut:
    return _authorized(db, tenant_id, user_id, "funds.admin.configure", CONFIG_ROLES).update_configuration(
        configuration_id, expected_version, payload.name, payload.description, payload.content_json
    )


@router.post("/funds/admin/configurations/{configuration_id}/publish", response_model=AdminConfigurationRecordOut)
def publish_configuration(
    configuration_id: int,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationRecordOut:
    return _authorized(db, tenant_id, user_id, "funds.admin.publish", CONFIG_ROLES).publish_configuration(
        configuration_id, expected_version
    )
