"""HTTP routes for Gate 07H Portfolio Resource Planning."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_resource.schemas import (
    CapacityDemandCellOut,
    CapacityPlanCreateIn,
    CapacityPlanOut,
    CapacityPlanUpdateIn,
    ConfigurationPreviewIn,
    ConfigurationPreviewOut,
    ConfigurationUpdateIn,
    DemandProfileCreateIn,
    DemandProfileOut,
    DemandProfileUpdateIn,
    IdempotencyIn,
    PortfolioResourcePlanningReadinessOut,
    ResourcePlanningOverviewOut,
    ResourceRecommendationContractOut,
    ResourceScenarioCreateIn,
    ResourceScenarioOut,
    ResourceScenarioUpdateIn,
    ScenarioCompareIn,
    ScenarioComparisonOut,
    ScenarioRefreshApplyIn,
    ScenarioRefreshPreviewOut,
    ScenarioSelectionIn,
    ScenarioTimingIn,
)
from app.modules.portfolio_resource.service import PortfolioResourceService

router = APIRouter()

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "portfolio_manager",
        "portfolio_analyst",
        "portfolio_resource_planner",
        "portfolio_resource_viewer",
    }
)
PLANNER_ROLES = frozenset({"organization_admin", "portfolio_manager", "portfolio_resource_planner"})
CONFIGURATION_ROLES = frozenset({"organization_admin", "portfolio_resource_configuration_admin"})


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
) -> PortfolioResourceService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = PortfolioResourceService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/portfolios/{portfolio_id}/resource-planning", response_model=ResourcePlanningOverviewOut)
def overview(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ResourcePlanningOverviewOut:
    return _authorized(db, tenant_id, user_id, "portfolio_resource.read", VIEW_ROLES).overview(portfolio_id)


@router.get("/portfolios/{portfolio_id}/resource-capacity-plans", response_model=list[CapacityPlanOut])
def capacity_plans(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[CapacityPlanOut]:
    return _authorized(db, tenant_id, user_id, "portfolio_resource.read", VIEW_ROLES).capacity_plans(portfolio_id)


@router.post("/portfolios/{portfolio_id}/resource-capacity-plans", response_model=CapacityPlanOut)
def create_capacity_plan(
    portfolio_id: int,
    payload: CapacityPlanCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CapacityPlanOut:
    result = _authorized(
        db, tenant_id, user_id, "portfolio_resource_capacity.create", PLANNER_ROLES
    ).create_capacity_plan(portfolio_id, payload)
    _etag(response, result.revision_version)
    return result


@router.get("/portfolio-resource-capacity-plans/{plan_id}", response_model=CapacityPlanOut)
def capacity_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CapacityPlanOut:
    return _authorized(db, tenant_id, user_id, "portfolio_resource.read", VIEW_ROLES).capacity_plan(plan_id)


@router.put("/portfolio-resource-capacity-plans/{plan_id}", response_model=CapacityPlanOut)
def update_capacity_plan(
    plan_id: int,
    payload: CapacityPlanUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CapacityPlanOut:
    result = _authorized(
        db, tenant_id, user_id, "portfolio_resource_capacity.create", PLANNER_ROLES
    ).update_capacity_plan(plan_id, expected_version, payload)
    _etag(response, result.revision_version)
    return result


@router.post("/portfolio-resource-capacity-plans/{plan_id}/publish", response_model=CapacityPlanOut)
def publish_capacity_plan(
    plan_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CapacityPlanOut:
    result = _authorized(
        db, tenant_id, user_id, "portfolio_resource_capacity.publish", PLANNER_ROLES
    ).publish_capacity_plan(plan_id, expected_version, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.get("/projects/{project_id}/resource-demand-profiles", response_model=list[DemandProfileOut])
def demand_profiles(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[DemandProfileOut]:
    return _authorized(db, tenant_id, user_id, "portfolio_resource_demand.read", VIEW_ROLES).demand_profiles(project_id)


@router.post("/projects/{project_id}/resource-demand-profiles", response_model=DemandProfileOut)
def create_demand_profile(
    project_id: int,
    payload: DemandProfileCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DemandProfileOut:
    result = _authorized(
        db, tenant_id, user_id, "portfolio_resource_demand.create", PLANNER_ROLES
    ).create_demand_profile(project_id, payload)
    _etag(response, result.revision_version)
    return result


@router.get("/project-resource-demand-profiles/{profile_id}", response_model=DemandProfileOut)
def demand_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DemandProfileOut:
    return _authorized(db, tenant_id, user_id, "portfolio_resource_demand.read", VIEW_ROLES).demand_profile(profile_id)


@router.put("/project-resource-demand-profiles/{profile_id}", response_model=DemandProfileOut)
def update_demand_profile(
    profile_id: int,
    payload: DemandProfileUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DemandProfileOut:
    result = _authorized(
        db, tenant_id, user_id, "portfolio_resource_demand.create", PLANNER_ROLES
    ).update_demand_profile(profile_id, expected_version, payload)
    _etag(response, result.revision_version)
    return result


@router.post("/project-resource-demand-profiles/{profile_id}/publish", response_model=DemandProfileOut)
def publish_demand_profile(
    profile_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DemandProfileOut:
    result = _authorized(
        db, tenant_id, user_id, "portfolio_resource_demand.publish", PLANNER_ROLES
    ).publish_demand_profile(profile_id, expected_version, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.get("/portfolios/{portfolio_id}/resource-scenarios", response_model=list[ResourceScenarioOut])
def scenarios(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ResourceScenarioOut]:
    return _authorized(db, tenant_id, user_id, "portfolio_resource.read", VIEW_ROLES).scenarios(portfolio_id)


@router.post("/portfolios/{portfolio_id}/resource-scenarios", response_model=ResourceScenarioOut)
def create_scenario(
    portfolio_id: int,
    payload: ResourceScenarioCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ResourceScenarioOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_resource_scenario.create", PLANNER_ROLES).create_scenario(
        portfolio_id, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/portfolio-resource-scenarios/{scenario_id}", response_model=ResourceScenarioOut)
def scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ResourceScenarioOut:
    return _authorized(db, tenant_id, user_id, "portfolio_resource.read", VIEW_ROLES).scenario(scenario_id)


@router.put("/portfolio-resource-scenarios/{scenario_id}", response_model=ResourceScenarioOut)
def update_scenario(
    scenario_id: int,
    payload: ResourceScenarioUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ResourceScenarioOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_resource_scenario.edit", PLANNER_ROLES).update_scenario(
        scenario_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


def _lifecycle(
    scenario_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int,
    db: Session,
    tenant_id: int,
    user_id: int,
    action: str,
) -> ResourceScenarioOut:
    permission = "portfolio_resource_scenario.create" if action == "clone" else f"portfolio_resource_scenario.{action}"
    service = _authorized(db, tenant_id, user_id, permission, PLANNER_ROLES)
    method = (
        service.clone_scenario
        if action == "clone"
        else service.freeze_scenario
        if action == "freeze"
        else service.void_scenario
    )
    result = method(scenario_id, expected_version, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.post("/portfolio-resource-scenarios/{scenario_id}/clone", response_model=ResourceScenarioOut)
def clone_scenario(
    scenario_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ResourceScenarioOut:
    return _lifecycle(scenario_id, payload, response, expected_version, db, tenant_id, user_id, "clone")


@router.post("/portfolio-resource-scenarios/{scenario_id}/freeze", response_model=ResourceScenarioOut)
def freeze_scenario(
    scenario_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ResourceScenarioOut:
    return _lifecycle(scenario_id, payload, response, expected_version, db, tenant_id, user_id, "freeze")


@router.post("/portfolio-resource-scenarios/{scenario_id}/void", response_model=ResourceScenarioOut)
def void_scenario(
    scenario_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ResourceScenarioOut:
    return _lifecycle(scenario_id, payload, response, expected_version, db, tenant_id, user_id, "void")


@router.post(
    "/portfolio-resource-scenarios/{scenario_id}/projects/{project_id}/selection",
    response_model=ResourceScenarioOut,
)
def select_project(
    scenario_id: int,
    project_id: int,
    payload: ScenarioSelectionIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ResourceScenarioOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_resource_scenario.force", PLANNER_ROLES).select_project(
        scenario_id, project_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.post(
    "/portfolio-resource-scenarios/{scenario_id}/projects/{project_id}/timing",
    response_model=ResourceScenarioOut,
)
def adjust_timing(
    scenario_id: int,
    project_id: int,
    payload: ScenarioTimingIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ResourceScenarioOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_resource_scenario.edit", PLANNER_ROLES).adjust_timing(
        scenario_id, project_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get(
    "/portfolio-resource-scenarios/{scenario_id}/capacity-demand",
    response_model=list[CapacityDemandCellOut],
)
@router.get("/portfolio-resource-scenarios/{scenario_id}/heatmap", response_model=list[CapacityDemandCellOut])
def heatmap(
    scenario_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[CapacityDemandCellOut]:
    return _authorized(db, tenant_id, user_id, "portfolio_resource.read", VIEW_ROLES).scenario(scenario_id).heatmap


@router.post("/portfolio-resource-scenarios/{scenario_id}/refresh/preview", response_model=ScenarioRefreshPreviewOut)
def refresh_preview(
    scenario_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ScenarioRefreshPreviewOut:
    return _authorized(db, tenant_id, user_id, "portfolio_resource_scenario.edit", PLANNER_ROLES).refresh_preview(
        scenario_id
    )


@router.post("/portfolio-resource-scenarios/{scenario_id}/refresh", response_model=ResourceScenarioOut)
def apply_refresh(
    scenario_id: int,
    payload: ScenarioRefreshApplyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ResourceScenarioOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_resource_scenario.edit", PLANNER_ROLES).apply_refresh(
        scenario_id, expected_version, payload.expected_source_hash, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.post("/portfolios/{portfolio_id}/resource-scenarios/compare", response_model=ScenarioComparisonOut)
def compare(
    portfolio_id: int,
    payload: ScenarioCompareIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ScenarioComparisonOut:
    return _authorized(db, tenant_id, user_id, "portfolio_resource_scenario.compare", VIEW_ROLES).compare(
        portfolio_id, payload.scenario_ids
    )


@router.get(
    "/portfolios/{portfolio_id}/resource-planning/readiness",
    response_model=PortfolioResourcePlanningReadinessOut,
)
def readiness(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioResourcePlanningReadinessOut:
    return _authorized(db, tenant_id, user_id, "portfolio_resource.read", VIEW_ROLES).readiness(portfolio_id)


@router.get(
    "/portfolios/{portfolio_id}/resource-planning/recommendation-contract",
    response_model=ResourceRecommendationContractOut,
)
def recommendation_contract(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ResourceRecommendationContractOut:
    return _authorized(db, tenant_id, user_id, "portfolio_resource.read", VIEW_ROLES).recommendation_contract(
        portfolio_id
    )


@router.get("/portfolio-resource/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AdminConfigurationOut]:
    return _authorized(
        db, tenant_id, user_id, "portfolio_resource.admin.configure", CONFIGURATION_ROLES
    ).configurations()


@router.post("/portfolio-resource/admin/configurations/preview", response_model=ConfigurationPreviewOut)
def configuration_preview(
    payload: ConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationPreviewOut:
    return _authorized(
        db, tenant_id, user_id, "portfolio_resource.admin.configure", CONFIGURATION_ROLES
    ).configuration_preview(payload.portfolio_workspace_id, payload.configuration_id, payload.content_json)


@router.post(
    "/portfolio-resource/admin/configurations/{configuration_id}/clone",
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
    result = _authorized(
        db, tenant_id, user_id, "portfolio_resource.admin.configure", CONFIGURATION_ROLES
    ).clone_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result


@router.put("/portfolio-resource/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
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
        db, tenant_id, user_id, "portfolio_resource.admin.configure", CONFIGURATION_ROLES
    ).update_configuration(configuration_id, expected_version, payload.name, payload.description, payload.content_json)
    _etag(response, result.version)
    return result


@router.post(
    "/portfolio-resource/admin/configurations/{configuration_id}/publish",
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
    result = _authorized(
        db, tenant_id, user_id, "portfolio_resource.admin.publish", CONFIGURATION_ROLES
    ).publish_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result
