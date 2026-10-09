"""HTTP routes for Gate 07F Portfolio Analysis."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_analysis.schemas import (
    AnalysisFiltersIn,
    AnalysisPreviewIn,
    AnalysisPreviewOut,
    ConfigurationPreviewIn,
    ConfigurationPreviewOut,
    ConfigurationUpdateIn,
    InvestorMapOut,
    PortfolioAnalysisDatasetOut,
    PortfolioAnalysisOverviewOut,
    PortfolioAnalysisReadinessOut,
    PortfolioScorecardOut,
    ProjectAnalysisDetailOut,
)
from app.modules.portfolio_analysis.service import PortfolioAnalysisService

router = APIRouter()

ANALYSIS_ROLES = frozenset(
    {
        "organization_admin",
        "portfolio_manager",
        "portfolio_analyst",
        "portfolio_analysis_viewer",
        "portfolio_evaluator",
        "portfolio_prioritization_viewer",
    }
)
CONFIGURATION_ROLES = frozenset({"organization_admin", "portfolio_analysis_configuration_admin"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    normalized = if_match.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"})
    return int(normalized)


def _filters(
    project_type: str | None = Query(default=None),
    strategic_objective: str | None = Query(default=None),
    risk_bucket: str | None = Query(default=None),
    priority_bucket: str | None = Query(default=None),
    membership_source: str | None = Query(default=None),
    planning_stage: str | None = Query(default=None),
    evaluation_score_min: Decimal | None = Query(default=None, ge=0, le=100),
    evaluation_score_max: Decimal | None = Query(default=None, ge=0, le=100),
    rom_cost_min: Decimal | None = Query(default=None, ge=0),
    rom_cost_max: Decimal | None = Query(default=None, ge=0),
    target_start_from: date | None = Query(default=None),
    target_finish_to: date | None = Query(default=None),
) -> AnalysisFiltersIn:
    return AnalysisFiltersIn(
        project_type=project_type,
        strategic_objective=strategic_objective,
        risk_bucket=risk_bucket,
        priority_bucket=priority_bucket,
        membership_source=membership_source,
        planning_stage=planning_stage,
        evaluation_score_min=evaluation_score_min,
        evaluation_score_max=evaluation_score_max,
        rom_cost_min=rom_cost_min,
        rom_cost_max=rom_cost_max,
        target_start_from=target_start_from,
        target_finish_to=target_finish_to,
    )


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    roles: frozenset[str] | None = None,
) -> PortfolioAnalysisService:
    context = require_enterprise_permission(
        db,
        tenant_id,
        user_id,
        permission,
        allowed_role_codes=roles,
    )
    service = PortfolioAnalysisService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/portfolios/{portfolio_id}/analysis", response_model=PortfolioAnalysisOverviewOut)
def overview(
    portfolio_id: int,
    filters: AnalysisFiltersIn = Depends(_filters),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioAnalysisOverviewOut:
    return _authorized(db, tenant_id, user_id, "portfolio_analysis.read", ANALYSIS_ROLES).overview(
        portfolio_id, filters
    )


@router.get("/portfolios/{portfolio_id}/analysis/dataset", response_model=PortfolioAnalysisDatasetOut)
def dataset(
    portfolio_id: int,
    filters: AnalysisFiltersIn = Depends(_filters),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioAnalysisDatasetOut:
    return _authorized(db, tenant_id, user_id, "portfolio_analysis.read", ANALYSIS_ROLES).dataset(portfolio_id, filters)


@router.get("/portfolios/{portfolio_id}/analysis/investor-map", response_model=InvestorMapOut)
def investor_map(
    portfolio_id: int,
    filters: AnalysisFiltersIn = Depends(_filters),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestorMapOut:
    return _authorized(db, tenant_id, user_id, "portfolio_analysis.read", ANALYSIS_ROLES).investor_map(
        portfolio_id, filters
    )


@router.get("/portfolios/{portfolio_id}/analysis/scorecard", response_model=PortfolioScorecardOut)
def scorecard(
    portfolio_id: int,
    filters: AnalysisFiltersIn = Depends(_filters),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioScorecardOut:
    return _authorized(db, tenant_id, user_id, "portfolio_analysis.read", ANALYSIS_ROLES).scorecard(
        portfolio_id, filters
    )


@router.get("/portfolios/{portfolio_id}/analysis/readiness", response_model=PortfolioAnalysisReadinessOut)
def readiness(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioAnalysisReadinessOut:
    return _authorized(db, tenant_id, user_id, "portfolio_analysis.read", ANALYSIS_ROLES).readiness(portfolio_id)


@router.post("/portfolios/{portfolio_id}/analysis/preview", response_model=AnalysisPreviewOut)
def preview(
    portfolio_id: int,
    payload: AnalysisPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AnalysisPreviewOut:
    return _authorized(db, tenant_id, user_id, "portfolio_analysis.read", ANALYSIS_ROLES).preview(
        portfolio_id,
        payload.filters,
        payload.expected_analysis_hash,
    )


@router.get(
    "/portfolios/{portfolio_id}/analysis/projects/{project_id}",
    response_model=ProjectAnalysisDetailOut,
)
def project_detail(
    portfolio_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectAnalysisDetailOut:
    return _authorized(db, tenant_id, user_id, "portfolio_analysis.read", ANALYSIS_ROLES).project_detail(
        portfolio_id, project_id
    )


@router.get("/portfolio-analysis/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AdminConfigurationOut]:
    return _authorized(
        db,
        tenant_id,
        user_id,
        "portfolio_analysis.admin.configure",
        CONFIGURATION_ROLES,
    ).configurations()


@router.post("/portfolio-analysis/admin/configurations/preview", response_model=ConfigurationPreviewOut)
def configuration_preview(
    payload: ConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationPreviewOut:
    return _authorized(
        db,
        tenant_id,
        user_id,
        "portfolio_analysis.admin.configure",
        CONFIGURATION_ROLES,
    ).configuration_preview(payload.portfolio_workspace_id, payload.configuration_id, payload.content_json)


@router.post(
    "/portfolio-analysis/admin/configurations/{configuration_id}/clone",
    response_model=AdminConfigurationOut,
)
def clone_configuration(
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
        "portfolio_analysis.admin.configure",
        CONFIGURATION_ROLES,
    ).clone_configuration(configuration_id, expected_version)
    response.headers["ETag"] = f'"{record.version}"'
    return record


@router.put(
    "/portfolio-analysis/admin/configurations/{configuration_id}",
    response_model=AdminConfigurationOut,
)
def update_configuration(
    configuration_id: int,
    payload: ConfigurationUpdateIn,
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
        "portfolio_analysis.admin.configure",
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
    "/portfolio-analysis/admin/configurations/{configuration_id}/publish",
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
        "portfolio_analysis.admin.publish",
        CONFIGURATION_ROLES,
    ).publish_configuration(configuration_id, expected_version)
    response.headers["ETag"] = f'"{record.version}"'
    return record
