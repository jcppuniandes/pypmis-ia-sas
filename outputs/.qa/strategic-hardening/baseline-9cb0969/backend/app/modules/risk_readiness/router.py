"""HTTP API for governed Project Risk and Risk Readiness."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.risk_readiness.schemas import (
    AdminConfigurationOut,
    AdminConfigurationPreviewIn,
    AdminConfigurationUpdateIn,
    AdminPreviewOut,
    AssessmentActionIn,
    AssessmentCreateIn,
    AssessmentUpdateIn,
    InvestmentGateRiskEvidenceOut,
    PortfolioReadinessOut,
    ProjectReadinessOut,
    ProjectRiskOut,
    RefreshPreviewOut,
    RiskAcceptanceIn,
    RiskCreateIn,
    RiskReadinessAssessmentOut,
    RiskReadinessOverviewOut,
    RiskStatusIn,
    RiskUpdateIn,
)
from app.modules.risk_readiness.service import RiskReadinessService

router = APIRouter()

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "risk_manager",
        "risk_owner",
        "risk_assessor",
        "risk_reviewer",
        "risk_acceptance_authority",
        "risk_viewer",
    }
)
EDIT_ROLES = frozenset({"organization_admin", "risk_manager", "risk_owner", "risk_assessor"})
ASSESS_ROLES = frozenset({"organization_admin", "risk_manager", "risk_assessor"})
ACCEPT_ROLES = frozenset({"organization_admin", "risk_manager", "risk_acceptance_authority"})
ADMIN_ROLES = frozenset({"organization_admin", "risk_configuration_admin"})


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
) -> RiskReadinessService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    return RiskReadinessService(db, tenant_id, context.user.id, context)


@router.get("/projects/{project_id}/risks", response_model=list[ProjectRiskOut])
def risks(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "project_risk.read", VIEW_ROLES).risks(project_id)


@router.post("/projects/{project_id}/risks", response_model=ProjectRiskOut)
def create_risk(
    project_id: int,
    payload: RiskCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "project_risk.create", EDIT_ROLES).create_risk(project_id, payload)
    _etag(response, result.revision_version)
    return result


@router.get("/risks/{risk_id}", response_model=ProjectRiskOut)
def risk(
    risk_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "project_risk.read", VIEW_ROLES).risk(risk_id)
    _etag(response, result.revision_version)
    return result


@router.put("/risks/{risk_id}", response_model=ProjectRiskOut)
def update_risk(
    risk_id: int,
    payload: RiskUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "project_risk.edit", EDIT_ROLES).update_risk(
        risk_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.post("/risks/{risk_id}/status", response_model=ProjectRiskOut)
def change_risk_status(
    risk_id: int,
    payload: RiskStatusIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "project_risk.manage_status", EDIT_ROLES).change_status(
        risk_id, expected_version, payload.status
    )
    _etag(response, result.revision_version)
    return result


@router.post("/risks/{risk_id}/accept-residual", response_model=ProjectRiskOut)
def accept_residual(
    risk_id: int,
    payload: RiskAcceptanceIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "project_risk.accept", ACCEPT_ROLES).accept_residual(
        risk_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/projects/{project_id}/risk-readiness-assessments", response_model=list[RiskReadinessAssessmentOut])
def assessments(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "risk_readiness.read", VIEW_ROLES).assessments(project_id)


@router.post("/projects/{project_id}/risk-readiness-assessments", response_model=RiskReadinessAssessmentOut)
def create_assessment(
    project_id: int,
    payload: AssessmentCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "risk_readiness_assessment.create", ASSESS_ROLES).create_assessment(
        project_id, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/risk-readiness-assessments/{assessment_id}", response_model=RiskReadinessAssessmentOut)
def assessment(
    assessment_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "risk_readiness.read", VIEW_ROLES).assessment(assessment_id)
    _etag(response, result.revision_version)
    return result


@router.put("/risk-readiness-assessments/{assessment_id}", response_model=RiskReadinessAssessmentOut)
def update_assessment(
    assessment_id: int,
    payload: AssessmentUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "risk_readiness_assessment.edit", ASSESS_ROLES).update_assessment(
        assessment_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.post("/risk-readiness-assessments/{assessment_id}/complete", response_model=RiskReadinessAssessmentOut)
def complete_assessment(
    assessment_id: int,
    payload: AssessmentActionIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "risk_readiness_assessment.complete", ASSESS_ROLES
    ).complete_assessment(assessment_id, expected_version, payload)
    _etag(response, result.revision_version)
    return result


@router.post("/risk-readiness-assessments/{assessment_id}/reassess", response_model=RiskReadinessAssessmentOut)
def reassess(
    assessment_id: int,
    payload: AssessmentActionIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "risk_readiness_assessment.reassess", ASSESS_ROLES).reassess(
        assessment_id, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/projects/{project_id}/risk-readiness", response_model=ProjectReadinessOut)
def project_readiness(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "risk_readiness.read", VIEW_ROLES).project_readiness(project_id)


@router.get("/projects/{project_id}/risk-readiness/refresh-preview", response_model=RefreshPreviewOut)
def refresh_preview(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "risk_readiness.refresh", ASSESS_ROLES).refresh_preview(project_id)


@router.post("/projects/{project_id}/risk-readiness/refresh", response_model=RiskReadinessAssessmentOut)
def refresh_apply(
    project_id: int,
    payload: AssessmentActionIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "risk_readiness.refresh", ASSESS_ROLES).refresh_apply(
        project_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/portfolios/{portfolio_id}/risk-readiness", response_model=PortfolioReadinessOut)
def portfolio_readiness(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "risk_readiness.read", VIEW_ROLES).portfolio_readiness(portfolio_id)


@router.get("/portfolios/{portfolio_id}/projects-risk-readiness", response_model=list[ProjectReadinessOut])
def portfolio_projects(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "risk_readiness.read", VIEW_ROLES).portfolio_projects(portfolio_id)


@router.get("/portfolios/{portfolio_id}/investment-gate-risk-evidence", response_model=InvestmentGateRiskEvidenceOut)
def investment_gate_evidence(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(
        db, tenant_id, user_id, "investment_gate_risk_evidence.read", VIEW_ROLES
    ).investment_gate_evidence(portfolio_id)


@router.get("/risk-readiness/overview", response_model=RiskReadinessOverviewOut)
def overview(
    db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), user_id: int = Depends(get_user_id)
):
    return _authorized(db, tenant_id, user_id, "risk_readiness.read", VIEW_ROLES).overview()


@router.get("/risk-readiness/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), user_id: int = Depends(get_user_id)
):
    return _authorized(db, tenant_id, user_id, "risk_readiness.admin.configure", ADMIN_ROLES).configurations()


@router.post("/risk-readiness/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationOut)
def clone_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "risk_readiness.admin.configure", ADMIN_ROLES).clone_configuration(
        configuration_id, expected_version
    )
    _etag(response, result.version)
    return result


@router.put("/risk-readiness/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: AdminConfigurationUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "risk_readiness.admin.configure", ADMIN_ROLES).update_configuration(
        configuration_id, expected_version, payload.name, payload.description, payload.content_json
    )
    _etag(response, result.version)
    return result


@router.post("/risk-readiness/admin/configurations/{configuration_id}/publish", response_model=AdminConfigurationOut)
def publish_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "risk_readiness.admin.publish", ADMIN_ROLES).publish_configuration(
        configuration_id, expected_version
    )
    _etag(response, result.version)
    return result


@router.post("/risk-readiness/admin/configurations/preview", response_model=AdminPreviewOut)
def preview_configuration(
    payload: AdminConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "risk_readiness.admin.configure", ADMIN_ROLES).admin_preview(
        portfolio_id=payload.portfolio_workspace_id,
        project_ids=payload.project_workspace_ids,
        gate_profile_code=payload.gate_profile_code,
        configuration_id=payload.configuration_id,
        content_override=payload.content_json,
    )
