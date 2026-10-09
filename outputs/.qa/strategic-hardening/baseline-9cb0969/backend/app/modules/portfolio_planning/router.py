"""HTTP routes for Gate 07D Portfolio Planning stage entry."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_planning.schemas import (
    PortfolioMembershipCreateIn,
    PortfolioMembershipOut,
    PortfolioPlanningConfigurationPreviewIn,
    PortfolioPlanningConfigurationPreviewOut,
    PortfolioPlanningConfigurationUpdateIn,
    PortfolioProjectRegisterOut,
    ReadinessOut,
    StrategicPlanningCreateIn,
    StrategicPlanningEntryOut,
    StrategicPlanningPreviewIn,
    StrategicPlanningPreviewOut,
)
from app.modules.portfolio_planning.service import PortfolioPlanningService

router = APIRouter()

INTAKE_ROLES = frozenset({"organization_admin", "portfolio_intake_planner"})
MEMBERSHIP_ROLES = frozenset({"organization_admin", "portfolio_membership_manager"})
CONFIGURATION_ROLES = frozenset({"organization_admin", "portfolio_configuration_admin"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    normalized = if_match.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        raise HTTPException(
            status_code=400,
            detail={"reason": "INVALID_IF_MATCH", "message": 'Use If-Match: "<revision_version>"'},
        )
    return int(normalized)


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    roles: frozenset[str] | None = None,
) -> PortfolioPlanningService:
    context = require_enterprise_permission(
        db,
        tenant_id,
        user_id,
        permission,
        allowed_role_codes=roles,
    )
    service = PortfolioPlanningService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/strategic-project-planning/options", response_model=list[dict])
def options(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[dict]:
    return _authorized(db, tenant_id, user_id, "portfolio_project.read").eligible_decisions()


@router.get("/strategic-project-planning/portfolio-options", response_model=list[dict])
def portfolio_options(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[dict]:
    return _authorized(db, tenant_id, user_id, "portfolio_project.read").portfolio_options()


@router.post("/strategic-project-planning/preview", response_model=StrategicPlanningPreviewOut)
def preview(
    payload: StrategicPlanningPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicPlanningPreviewOut:
    return _authorized(db, tenant_id, user_id, "portfolio_project.intake", INTAKE_ROLES).preview(
        payload.strategic_gate_decision_id
    )


@router.post(
    "/strategic-project-planning",
    response_model=StrategicPlanningEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def create(
    payload: StrategicPlanningCreateIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicPlanningEntryOut:
    return _authorized(db, tenant_id, user_id, "portfolio_project.intake", INTAKE_ROLES).create(payload)


@router.get("/strategic-project-planning/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AdminConfigurationOut]:
    return _authorized(
        db,
        tenant_id,
        user_id,
        "portfolio_project.admin.configure",
        CONFIGURATION_ROLES,
    ).configurations()


@router.post(
    "/strategic-project-planning/admin/configuration/preview",
    response_model=PortfolioPlanningConfigurationPreviewOut,
)
def configuration_preview(
    payload: PortfolioPlanningConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioPlanningConfigurationPreviewOut:
    return _authorized(
        db,
        tenant_id,
        user_id,
        "portfolio_project.admin.configure",
        CONFIGURATION_ROLES,
    ).configuration_preview(payload.workspace_id)


@router.post(
    "/strategic-project-planning/admin/configurations/{configuration_id}/clone",
    response_model=AdminConfigurationOut,
)
def clone_configuration(
    configuration_id: int,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    return _authorized(
        db,
        tenant_id,
        user_id,
        "portfolio_project.admin.configure",
        CONFIGURATION_ROLES,
    ).clone_configuration(configuration_id, expected_version)


@router.put(
    "/strategic-project-planning/admin/configurations/{configuration_id}",
    response_model=AdminConfigurationOut,
)
def update_configuration(
    configuration_id: int,
    payload: PortfolioPlanningConfigurationUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    record = _authorized(
        db,
        tenant_id,
        user_id,
        "portfolio_project.admin.configure",
        CONFIGURATION_ROLES,
    ).update_configuration(
        configuration_id,
        expected_version,
        payload.name,
        payload.description,
        payload.content_json,
    )
    response.headers["ETag"] = f'"{record.version}"'
    return record


@router.post(
    "/strategic-project-planning/admin/configurations/{configuration_id}/publish",
    response_model=AdminConfigurationOut,
)
def publish_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    record = _authorized(
        db,
        tenant_id,
        user_id,
        "portfolio_project.admin.publish",
        CONFIGURATION_ROLES,
    ).publish_configuration(configuration_id, expected_version)
    response.headers["ETag"] = f'"{record.version}"'
    return record


@router.get("/strategic-project-planning/{decision_id}", response_model=StrategicPlanningEntryOut)
def get_entry(
    decision_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicPlanningEntryOut:
    return _authorized(db, tenant_id, user_id, "portfolio_project.read").entry(decision_id)


@router.get("/strategic-project-planning/{decision_id}/readiness", response_model=StrategicPlanningEntryOut)
def get_entry_readiness(
    decision_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicPlanningEntryOut:
    return _authorized(db, tenant_id, user_id, "portfolio_planning.readiness.read").entry(decision_id)


@router.get("/portfolios/{portfolio_id}/projects", response_model=list[PortfolioProjectRegisterOut])
def portfolio_projects(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[PortfolioProjectRegisterOut]:
    return _authorized(db, tenant_id, user_id, "portfolio_project.read").portfolio_projects(portfolio_id)


@router.get("/projects/{project_id}/portfolio-memberships", response_model=list[PortfolioMembershipOut])
def project_memberships(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[PortfolioMembershipOut]:
    return _authorized(db, tenant_id, user_id, "portfolio_project.read").project_memberships(project_id)


@router.post("/projects/{project_id}/portfolio-memberships", response_model=PortfolioMembershipOut)
def add_project_membership(
    project_id: int,
    payload: PortfolioMembershipCreateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioMembershipOut:
    membership = _authorized(
        db,
        tenant_id,
        user_id,
        "portfolio_project.membership.manage",
        MEMBERSHIP_ROLES,
    ).create_membership(project_id, payload, expected_version)
    response.headers["ETag"] = f'"{membership.revision_version}"'
    return membership


@router.post(
    "/projects/{project_id}/portfolio-memberships/{membership_id}/remove",
    response_model=PortfolioMembershipOut,
)
def remove_project_membership(
    project_id: int,
    membership_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioMembershipOut:
    membership = _authorized(
        db,
        tenant_id,
        user_id,
        "portfolio_project.membership.manage",
        MEMBERSHIP_ROLES,
    ).remove_membership(project_id, membership_id, expected_version)
    response.headers["ETag"] = f'"{membership.revision_version}"'
    return membership


@router.get("/projects/{project_id}/portfolio-planning-readiness", response_model=StrategicPlanningEntryOut)
def project_planning_readiness(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> StrategicPlanningEntryOut:
    return _authorized(db, tenant_id, user_id, "portfolio_planning.readiness.read").project_readiness(project_id)


@router.get("/projects/{project_id}/portfolio-evaluation-readiness", response_model=ReadinessOut)
def portfolio_evaluation_readiness(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ReadinessOut:
    return (
        _authorized(
            db,
            tenant_id,
            user_id,
            "portfolio_planning.readiness.read",
        )
        .project_readiness(project_id)
        .portfolio_evaluation_readiness
    )


@router.get("/projects/{project_id}/project-definition-readiness", response_model=ReadinessOut)
def project_definition_readiness(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ReadinessOut:
    return (
        _authorized(
            db,
            tenant_id,
            user_id,
            "project_definition.readiness.read",
        )
        .project_readiness(project_id)
        .project_definition_readiness
    )
