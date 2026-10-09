"""HTTP API for governed Project Permit and Permit Readiness."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.permit_readiness.schemas import (
    AdminConfigurationOut,
    AdminConfigurationPreviewIn,
    AdminConfigurationUpdateIn,
    AdminPreviewOut,
    AssessmentActionIn,
    AssessmentCreateIn,
    AssessmentUpdateIn,
    ConditionCreateIn,
    ConditionUpdateIn,
    InvestmentGatePermitEvidenceOut,
    PermitConditionOut,
    PermitCreateIn,
    PermitReadinessAssessmentOut,
    PermitReadinessOverviewOut,
    PermitStatusIn,
    PermitUpdateIn,
    ProjectPermitOut,
    ProjectPermitReadinessOut,
    ProjectSetPermitReadinessOut,
    RefreshPreviewOut,
)
from app.modules.permit_readiness.service import PermitReadinessService

router = APIRouter()

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "permit_manager",
        "permit_owner",
        "permit_assessor",
        "permit_reviewer",
        "permit_viewer",
    }
)
EDIT_ROLES = frozenset({"organization_admin", "permit_manager", "permit_owner"})
ASSESS_ROLES = frozenset({"organization_admin", "permit_manager", "permit_assessor"})
REVIEW_ROLES = frozenset({"organization_admin", "permit_manager", "permit_reviewer"})
ADMIN_ROLES = frozenset({"organization_admin", "permit_configuration_admin"})


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
) -> PermitReadinessService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    return PermitReadinessService(db, tenant_id, context.user.id, context)


@router.get("/projects/{project_id}/permits", response_model=list[ProjectPermitOut])
def permits(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "permit.read", VIEW_ROLES).permits(project_id)


@router.post("/projects/{project_id}/permits", response_model=ProjectPermitOut)
def create_permit(
    project_id: int,
    payload: PermitCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit.create", EDIT_ROLES).create_permit(project_id, payload)
    _etag(response, result.revision_version)
    return result


@router.get("/permits/{permit_id}", response_model=ProjectPermitOut)
def permit(
    permit_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit.read", VIEW_ROLES).permit(permit_id)
    _etag(response, result.revision_version)
    return result


@router.put("/permits/{permit_id}", response_model=ProjectPermitOut)
def update_permit(
    permit_id: int,
    payload: PermitUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit.edit", EDIT_ROLES).update_permit(
        permit_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.post("/permits/{permit_id}/status", response_model=ProjectPermitOut)
def change_permit_status(
    permit_id: int,
    payload: PermitStatusIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit.status.manage", EDIT_ROLES).change_permit_status(
        permit_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/permits/{permit_id}/conditions", response_model=list[PermitConditionOut])
def conditions(
    permit_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "permit.read", VIEW_ROLES).conditions(permit_id)


@router.post("/permits/{permit_id}/conditions", response_model=PermitConditionOut)
def create_condition(
    permit_id: int,
    payload: ConditionCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit.condition.manage", EDIT_ROLES).create_condition(
        permit_id, payload
    )
    _etag(response, result.revision_version)
    return result


@router.put("/permit-conditions/{condition_id}", response_model=PermitConditionOut)
def update_condition(
    condition_id: int,
    payload: ConditionUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit.condition.manage", EDIT_ROLES).update_condition(
        condition_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get(
    "/projects/{project_id}/permit-readiness-assessments",
    response_model=list[PermitReadinessAssessmentOut],
)
def assessments(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "permit_readiness.read", VIEW_ROLES).assessments(project_id)


@router.post("/projects/{project_id}/permit-readiness-assessments", response_model=PermitReadinessAssessmentOut)
def create_assessment(
    project_id: int,
    payload: AssessmentCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit_readiness.create", ASSESS_ROLES).create_assessment(
        project_id, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/permit-readiness-assessments/{assessment_id}", response_model=PermitReadinessAssessmentOut)
def assessment(
    assessment_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit_readiness.read", VIEW_ROLES).assessment(assessment_id)
    _etag(response, result.revision_version)
    return result


@router.put("/permit-readiness-assessments/{assessment_id}", response_model=PermitReadinessAssessmentOut)
def update_assessment(
    assessment_id: int,
    payload: AssessmentUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit_readiness.edit", ASSESS_ROLES).update_assessment(
        assessment_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.post("/permit-readiness-assessments/{assessment_id}/complete", response_model=PermitReadinessAssessmentOut)
def complete_assessment(
    assessment_id: int,
    payload: AssessmentActionIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit_readiness.complete", REVIEW_ROLES).complete_assessment(
        assessment_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.post("/permit-readiness-assessments/{assessment_id}/reassess", response_model=PermitReadinessAssessmentOut)
def reassess(
    assessment_id: int,
    payload: AssessmentActionIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit_readiness.reassess", ASSESS_ROLES).reassess(
        assessment_id, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/projects/{project_id}/permit-readiness", response_model=ProjectPermitReadinessOut)
def project_readiness(
    project_id: int,
    gate_profile_code: str = "PYP-FFA",
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "permit_readiness.read", VIEW_ROLES).project_readiness(
        project_id, gate_profile_code
    )


@router.get("/projects/{project_id}/permit-readiness/refresh-preview", response_model=RefreshPreviewOut)
def refresh_preview(
    project_id: int,
    gate_profile_code: str = "PYP-FFA",
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "permit_readiness.refresh", ASSESS_ROLES).refresh_preview(
        project_id, gate_profile_code
    )


@router.post("/projects/{project_id}/permit-readiness/refresh", response_model=PermitReadinessAssessmentOut)
def refresh_apply(
    project_id: int,
    payload: AssessmentActionIn,
    response: Response,
    gate_profile_code: str = "PYP-FFA",
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit_readiness.refresh", ASSESS_ROLES).refresh_apply(
        project_id, expected_version, payload, gate_profile_code
    )
    _etag(response, result.revision_version)
    return result


@router.get("/portfolios/{portfolio_id}/permit-readiness", response_model=ProjectSetPermitReadinessOut)
def portfolio_readiness(
    portfolio_id: int,
    gate_profile_code: str = "PYP-FFA",
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "permit_readiness.read", VIEW_ROLES).portfolio_readiness(
        portfolio_id, gate_profile_code
    )


@router.get("/portfolios/{portfolio_id}/projects-permit-readiness", response_model=list[ProjectPermitReadinessOut])
def portfolio_projects(
    portfolio_id: int,
    gate_profile_code: str = "PYP-FFA",
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "permit_readiness.read", VIEW_ROLES).portfolio_projects(
        portfolio_id, gate_profile_code
    )


@router.get(
    "/portfolios/{portfolio_id}/investment-gate-permit-evidence",
    response_model=InvestmentGatePermitEvidenceOut,
)
def portfolio_investment_gate_evidence(
    portfolio_id: int,
    gate_profile_code: str = "PYP-FFA",
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(
        db, tenant_id, user_id, "investment_gate_permit_evidence.read", VIEW_ROLES
    ).investment_gate_evidence(portfolio_id, gate_profile_code)


@router.get("/projects/{project_id}/investment-gate-permit-evidence", response_model=InvestmentGatePermitEvidenceOut)
def project_investment_gate_evidence(
    project_id: int,
    gate_profile_code: str = "PYP-FFA",
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(
        db, tenant_id, user_id, "investment_gate_permit_evidence.read", VIEW_ROLES
    ).project_investment_gate_evidence(project_id, gate_profile_code)


@router.get("/permit-readiness/overview", response_model=PermitReadinessOverviewOut)
def overview(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "permit_readiness.read", VIEW_ROLES).overview()


@router.get("/permit-readiness/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "permit_readiness.admin.configure", ADMIN_ROLES).configurations()


@router.post("/permit-readiness/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationOut)
def clone_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit_readiness.admin.configure", ADMIN_ROLES).clone_configuration(
        configuration_id, expected_version
    )
    _etag(response, result.version)
    return result


@router.put("/permit-readiness/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: AdminConfigurationUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit_readiness.admin.configure", ADMIN_ROLES).update_configuration(
        configuration_id,
        expected_version,
        payload.name,
        payload.description,
        payload.content_json,
    )
    _etag(response, result.version)
    return result


@router.post("/permit-readiness/admin/configurations/{configuration_id}/publish", response_model=AdminConfigurationOut)
def publish_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "permit_readiness.admin.publish", ADMIN_ROLES).publish_configuration(
        configuration_id, expected_version
    )
    _etag(response, result.version)
    return result


@router.post("/permit-readiness/admin/configurations/preview", response_model=AdminPreviewOut)
def preview_configuration(
    payload: AdminConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "permit_readiness.admin.configure", ADMIN_ROLES).admin_preview(
        portfolio_id=payload.portfolio_workspace_id,
        project_ids=payload.project_workspace_ids,
        gate_profile_code=payload.gate_profile_code,
        configuration_id=payload.configuration_id,
        content_override=payload.content_json,
    )
