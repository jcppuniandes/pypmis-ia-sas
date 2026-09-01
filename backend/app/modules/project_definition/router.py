"""HTTP routes for Project Definition / FEL Manager."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.project_definition.schemas import (
    ActionCreateIn,
    ActionUpdateIn,
    AssessmentCreateIn,
    AssessmentOut,
    AssessmentUpdateIn,
    ConfigurationPreviewIn,
    ConfigurationPreviewOut,
    ConfigurationUpdateIn,
    DefinitionActionOut,
    DefinitionOverviewOut,
    DefinitionReadinessOut,
    IdempotencyIn,
    InvestmentGateEvidenceOut,
    ProjectFELStatusOut,
    RefreshApplyIn,
    StageReviewIn,
    StartFELIn,
)
from app.modules.project_definition.service import ProjectDefinitionService

router = APIRouter()

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "portfolio_manager",
        "project_definition_manager",
        "definition_assessor",
        "definition_reviewer",
        "project_definition_viewer",
    }
)
MANAGER_ROLES = frozenset({"organization_admin", "portfolio_manager", "project_definition_manager"})
ASSESSOR_ROLES = frozenset({"organization_admin", "project_definition_manager", "definition_assessor"})
REVIEWER_ROLES = frozenset({"organization_admin", "definition_reviewer"})
CONFIG_ROLES = frozenset({"organization_admin", "project_definition_configuration_admin"})


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
) -> ProjectDefinitionService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = ProjectDefinitionService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/project-definition", response_model=DefinitionOverviewOut)
def overview(
    project_workspace_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DefinitionOverviewOut:
    return _authorized(db, tenant_id, user_id, "project_definition.read", VIEW_ROLES).overview(project_workspace_id)


@router.get("/projects/{project_id}/definition", response_model=DefinitionOverviewOut)
def project_overview(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DefinitionOverviewOut:
    return _authorized(db, tenant_id, user_id, "project_definition.read", VIEW_ROLES).overview(project_id)


@router.get("/projects/{project_id}/fel-status", response_model=ProjectFELStatusOut)
def fel_status(
    project_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectFELStatusOut:
    result = _authorized(db, tenant_id, user_id, "project_definition.read", VIEW_ROLES).fel_status(project_id)
    _etag(response, result.revision_version)
    return result


@router.post("/projects/{project_id}/fel/start", response_model=ProjectFELStatusOut)
def start_fel(
    project_id: int,
    payload: StartFELIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectFELStatusOut:
    result = _authorized(db, tenant_id, user_id, "project_definition.status.manage", MANAGER_ROLES).start_fel(
        project_id, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/projects/{project_id}/definition-assessments", response_model=list[AssessmentOut])
def assessments(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AssessmentOut]:
    return _authorized(db, tenant_id, user_id, "project_definition.read", VIEW_ROLES).assessments(project_id)


@router.post("/projects/{project_id}/definition-assessments", response_model=AssessmentOut)
def create_assessment(
    project_id: int,
    payload: AssessmentCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AssessmentOut:
    result = _authorized(
        db, tenant_id, user_id, "project_definition_assessment.create", ASSESSOR_ROLES
    ).create_assessment(project_id, payload)
    _etag(response, result.revision_version)
    return result


@router.get("/project-definition-assessments/{assessment_id}", response_model=AssessmentOut)
def assessment(
    assessment_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AssessmentOut:
    result = _authorized(db, tenant_id, user_id, "project_definition.read", VIEW_ROLES).assessment(assessment_id)
    _etag(response, result.revision_version)
    return result


@router.put("/project-definition-assessments/{assessment_id}", response_model=AssessmentOut)
def update_assessment(
    assessment_id: int,
    payload: AssessmentUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AssessmentOut:
    result = _authorized(
        db, tenant_id, user_id, "project_definition_assessment.edit", ASSESSOR_ROLES
    ).update_assessment(assessment_id, expected_version, payload)
    _etag(response, result.revision_version)
    return result


@router.post("/project-definition-assessments/{assessment_id}/complete", response_model=AssessmentOut)
def complete_assessment(
    assessment_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AssessmentOut:
    result = _authorized(
        db, tenant_id, user_id, "project_definition_assessment.complete", ASSESSOR_ROLES
    ).complete_assessment(assessment_id, expected_version, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.post("/project-definition-assessments/{assessment_id}/reevaluate", response_model=AssessmentOut)
def reevaluate(
    assessment_id: int,
    payload: IdempotencyIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AssessmentOut:
    result = _authorized(
        db, tenant_id, user_id, "project_definition_assessment.reevaluate", ASSESSOR_ROLES
    ).reevaluate(assessment_id, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.get("/projects/{project_id}/definition-actions", response_model=list[DefinitionActionOut])
def actions(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[DefinitionActionOut]:
    return _authorized(db, tenant_id, user_id, "project_definition.read", VIEW_ROLES).actions(project_id)


@router.post("/projects/{project_id}/definition-actions", response_model=DefinitionActionOut)
def create_action(
    project_id: int,
    payload: ActionCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DefinitionActionOut:
    result = _authorized(
        db, tenant_id, user_id, "project_definition_action.manage", ASSESSOR_ROLES
    ).create_action(project_id, payload)
    _etag(response, result.revision_version)
    return result


@router.put("/project-definition-actions/{action_id}", response_model=DefinitionActionOut)
def update_action(
    action_id: int,
    payload: ActionUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DefinitionActionOut:
    result = _authorized(
        db, tenant_id, user_id, "project_definition_action.manage", ASSESSOR_ROLES
    ).update_action(action_id, expected_version, payload)
    _etag(response, result.revision_version)
    return result


@router.get("/projects/{project_id}/definition-readiness", response_model=DefinitionReadinessOut)
def readiness(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DefinitionReadinessOut:
    return _authorized(db, tenant_id, user_id, "project_definition.read", VIEW_ROLES).readiness(project_id)


@router.post("/projects/{project_id}/fel-stage/submit-review", response_model=ProjectFELStatusOut)
def submit_review(
    project_id: int,
    payload: StageReviewIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectFELStatusOut:
    result = _authorized(
        db, tenant_id, user_id, "project_definition_stage.submit", MANAGER_ROLES
    ).submit_stage_review(project_id, expected_version, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.post("/projects/{project_id}/fel-stage/complete", response_model=ProjectFELStatusOut)
def complete_stage(
    project_id: int,
    payload: StageReviewIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectFELStatusOut:
    result = _authorized(
        db, tenant_id, user_id, "project_definition_stage.review", REVIEWER_ROLES
    ).complete_stage(project_id, expected_version, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.post("/projects/{project_id}/fel-stage/return", response_model=ProjectFELStatusOut)
def return_stage(
    project_id: int,
    payload: StageReviewIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectFELStatusOut:
    result = _authorized(
        db, tenant_id, user_id, "project_definition_stage.review", REVIEWER_ROLES
    ).return_stage(project_id, expected_version, payload.idempotency_key, payload.note)
    _etag(response, result.revision_version)
    return result


@router.post("/projects/{project_id}/definition/refresh/preview")
def refresh_preview(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> dict:
    return _authorized(db, tenant_id, user_id, "project_definition.refresh", MANAGER_ROLES).refresh_preview(project_id)


@router.post("/projects/{project_id}/definition/refresh", response_model=ProjectFELStatusOut)
def refresh(
    project_id: int,
    payload: RefreshApplyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectFELStatusOut:
    result = _authorized(db, tenant_id, user_id, "project_definition.refresh", MANAGER_ROLES).refresh(
        project_id, expected_version, payload.expected_source_hash, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.get("/projects/{project_id}/definition/investment-gate-evidence", response_model=InvestmentGateEvidenceOut)
def investment_gate_evidence(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGateEvidenceOut:
    return _authorized(db, tenant_id, user_id, "project_definition.read", VIEW_ROLES).investment_gate_evidence(project_id)


@router.get("/project-definition/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AdminConfigurationOut]:
    return _authorized(db, tenant_id, user_id, "project_definition.admin.configure", CONFIG_ROLES).configurations()


@router.post("/project-definition/admin/configurations/preview", response_model=ConfigurationPreviewOut)
def configuration_preview(
    payload: ConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationPreviewOut:
    return _authorized(db, tenant_id, user_id, "project_definition.admin.configure", CONFIG_ROLES).configuration_preview(
        payload.project_workspace_id,
        payload.project_type,
        payload.governance_model,
        payload.current_FEL_stage,
        payload.configuration_id,
        payload.content_json,
    )


@router.post("/project-definition/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationOut)
def clone_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    result = _authorized(
        db, tenant_id, user_id, "project_definition.admin.configure", CONFIG_ROLES
    ).clone_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result


@router.put("/project-definition/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: ConfigurationUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    result = _authorized(
        db, tenant_id, user_id, "project_definition.admin.configure", CONFIG_ROLES
    ).update_configuration(configuration_id, expected_version, payload.name, payload.description, payload.content_json)
    _etag(response, result.version)
    return result


@router.post("/project-definition/admin/configurations/{configuration_id}/publish", response_model=AdminConfigurationOut)
def publish_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    result = _authorized(
        db, tenant_id, user_id, "project_definition.admin.publish", CONFIG_ROLES
    ).publish_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result
