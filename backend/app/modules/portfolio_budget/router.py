"""HTTP routes for Gate 07G Portfolio Budget Planning."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_budget.schemas import (
    BudgetPlanningOverviewOut,
    BudgetRecommendationContractOut,
    BudgetScenarioCreateIn,
    BudgetScenarioOut,
    BudgetScenarioUpdateIn,
    BudgetTargetCreateIn,
    BudgetTargetOut,
    BudgetTargetUpdateIn,
    ConfigurationPreviewIn,
    ConfigurationPreviewOut,
    ConfigurationUpdateIn,
    IdempotencyIn,
    PortfolioBudgetPlanningReadinessOut,
    ProjectDependencyCreateIn,
    ProjectDependencyOut,
    ProjectDependencyUpdateIn,
    ScenarioCompareIn,
    ScenarioComparisonOut,
    ScenarioDependencyOut,
    ScenarioRefreshApplyIn,
    ScenarioRefreshPreviewOut,
    ScenarioSelectionIn,
    WaterlineOut,
)
from app.modules.portfolio_budget.service import PortfolioBudgetService

router = APIRouter()

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "portfolio_manager",
        "portfolio_analyst",
        "portfolio_budget_planner",
        "portfolio_budget_viewer",
    }
)
PLANNER_ROLES = frozenset({"organization_admin", "portfolio_manager", "portfolio_budget_planner"})
CONFIGURATION_ROLES = frozenset({"organization_admin", "portfolio_budget_configuration_admin"})


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
) -> PortfolioBudgetService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = PortfolioBudgetService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/portfolios/{portfolio_id}/budget-planning", response_model=BudgetPlanningOverviewOut)
def overview(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BudgetPlanningOverviewOut:
    return _authorized(db, tenant_id, user_id, "portfolio_budget.read", VIEW_ROLES).overview(portfolio_id)


@router.get("/portfolios/{portfolio_id}/budget-targets", response_model=list[BudgetTargetOut])
def targets(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[BudgetTargetOut]:
    return _authorized(db, tenant_id, user_id, "portfolio_budget.read", VIEW_ROLES).targets(portfolio_id)


@router.post("/portfolios/{portfolio_id}/budget-targets", response_model=BudgetTargetOut)
def create_target(
    portfolio_id: int,
    payload: BudgetTargetCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BudgetTargetOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_budget_target.create", PLANNER_ROLES).create_target(
        portfolio_id, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/portfolio-budget-targets/{target_id}", response_model=BudgetTargetOut)
def target(
    target_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BudgetTargetOut:
    return _authorized(db, tenant_id, user_id, "portfolio_budget.read", VIEW_ROLES).target(target_id)


@router.put("/portfolio-budget-targets/{target_id}", response_model=BudgetTargetOut)
def update_target(
    target_id: int,
    payload: BudgetTargetUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BudgetTargetOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_budget_target.create", PLANNER_ROLES).update_target(
        target_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.post("/portfolio-budget-targets/{target_id}/publish", response_model=BudgetTargetOut)
def publish_target(
    target_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BudgetTargetOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_budget_target.publish", PLANNER_ROLES).publish_target(
        target_id, expected_version, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.get("/portfolios/{portfolio_id}/budget-scenarios", response_model=list[BudgetScenarioOut])
def scenarios(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[BudgetScenarioOut]:
    return _authorized(db, tenant_id, user_id, "portfolio_budget.read", VIEW_ROLES).scenarios(portfolio_id)


@router.post("/portfolios/{portfolio_id}/budget-scenarios", response_model=BudgetScenarioOut)
def create_scenario(
    portfolio_id: int,
    payload: BudgetScenarioCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BudgetScenarioOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_budget_scenario.create", PLANNER_ROLES).create_scenario(
        portfolio_id, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/portfolio-budget-scenarios/{scenario_id}", response_model=BudgetScenarioOut)
def scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BudgetScenarioOut:
    return _authorized(db, tenant_id, user_id, "portfolio_budget.read", VIEW_ROLES).scenario(scenario_id)


@router.get("/portfolio-budget-scenarios/{scenario_id}/waterline", response_model=WaterlineOut)
def waterline(
    scenario_id: int,
    period_key: str | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WaterlineOut:
    return _authorized(db, tenant_id, user_id, "portfolio_budget.read", VIEW_ROLES).waterline(
        scenario_id, period_key
    )


@router.get(
    "/portfolio-budget-scenarios/{scenario_id}/dependencies", response_model=ScenarioDependencyOut
)
def scenario_dependencies(
    scenario_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ScenarioDependencyOut:
    return _authorized(
        db, tenant_id, user_id, "portfolio_dependency.read", VIEW_ROLES
    ).scenario_dependencies(scenario_id)


@router.get("/portfolios/{portfolio_id}/project-dependencies", response_model=list[ProjectDependencyOut])
def project_dependencies(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProjectDependencyOut]:
    return _authorized(db, tenant_id, user_id, "portfolio_dependency.read", VIEW_ROLES).project_dependencies(
        portfolio_id
    )


@router.post("/portfolios/{portfolio_id}/project-dependencies", response_model=ProjectDependencyOut)
def create_project_dependency(
    portfolio_id: int,
    payload: ProjectDependencyCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectDependencyOut:
    result = _authorized(
        db, tenant_id, user_id, "portfolio_dependency.manage", PLANNER_ROLES
    ).create_project_dependency(portfolio_id, payload)
    _etag(response, result.revision_version)
    return result


@router.get("/project-dependencies/{dependency_id}", response_model=ProjectDependencyOut)
def project_dependency(
    dependency_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectDependencyOut:
    return _authorized(db, tenant_id, user_id, "portfolio_dependency.read", VIEW_ROLES).project_dependency(
        dependency_id
    )


@router.put("/project-dependencies/{dependency_id}", response_model=ProjectDependencyOut)
def update_project_dependency(
    dependency_id: int,
    payload: ProjectDependencyUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectDependencyOut:
    result = _authorized(
        db, tenant_id, user_id, "portfolio_dependency.manage", PLANNER_ROLES
    ).update_project_dependency(dependency_id, expected_version, payload)
    _etag(response, result.revision_version)
    return result


@router.post("/project-dependencies/{dependency_id}/deactivate", response_model=ProjectDependencyOut)
def deactivate_project_dependency(
    dependency_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectDependencyOut:
    result = _authorized(
        db, tenant_id, user_id, "portfolio_dependency.manage", PLANNER_ROLES
    ).deactivate_project_dependency(dependency_id, expected_version, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.put("/portfolio-budget-scenarios/{scenario_id}", response_model=BudgetScenarioOut)
def update_scenario(
    scenario_id: int,
    payload: BudgetScenarioUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BudgetScenarioOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_budget_scenario.edit", PLANNER_ROLES).update_scenario(
        scenario_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


def _lifecycle(
    action: str,
    scenario_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int,
    db: Session,
    tenant_id: int,
    user_id: int,
) -> BudgetScenarioOut:
    permission = {
        "clone": "portfolio_budget_scenario.create",
        "freeze": "portfolio_budget_scenario.freeze",
        "void": "portfolio_budget_scenario.void",
    }[action]
    service = _authorized(db, tenant_id, user_id, permission, PLANNER_ROLES)
    result = getattr(service, f"{action}_scenario")(scenario_id, expected_version, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.post("/portfolio-budget-scenarios/{scenario_id}/clone", response_model=BudgetScenarioOut)
def clone_scenario(
    scenario_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BudgetScenarioOut:
    return _lifecycle("clone", scenario_id, payload, response, expected_version, db, tenant_id, user_id)


@router.post("/portfolio-budget-scenarios/{scenario_id}/freeze", response_model=BudgetScenarioOut)
def freeze_scenario(
    scenario_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BudgetScenarioOut:
    return _lifecycle("freeze", scenario_id, payload, response, expected_version, db, tenant_id, user_id)


@router.post("/portfolio-budget-scenarios/{scenario_id}/void", response_model=BudgetScenarioOut)
def void_scenario(
    scenario_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BudgetScenarioOut:
    return _lifecycle("void", scenario_id, payload, response, expected_version, db, tenant_id, user_id)


@router.post(
    "/portfolio-budget-scenarios/{scenario_id}/projects/{project_id}/selection",
    response_model=BudgetScenarioOut,
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
) -> BudgetScenarioOut:
    permission = (
        "portfolio_budget_scenario.force"
        if payload.selection_state.startswith("FORCED")
        else "portfolio_budget_scenario.edit"
    )
    result = _authorized(db, tenant_id, user_id, permission, PLANNER_ROLES).select_project(
        scenario_id, project_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.post("/portfolio-budget-scenarios/{scenario_id}/refresh/preview", response_model=ScenarioRefreshPreviewOut)
def refresh_preview(
    scenario_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ScenarioRefreshPreviewOut:
    return _authorized(db, tenant_id, user_id, "portfolio_budget_scenario.edit", PLANNER_ROLES).refresh_preview(
        scenario_id
    )


@router.post("/portfolio-budget-scenarios/{scenario_id}/refresh", response_model=BudgetScenarioOut)
def apply_refresh(
    scenario_id: int,
    payload: ScenarioRefreshApplyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BudgetScenarioOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_budget_scenario.edit", PLANNER_ROLES).apply_refresh(
        scenario_id, expected_version, payload.expected_source_hash, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.post("/portfolios/{portfolio_id}/budget-scenarios/compare", response_model=ScenarioComparisonOut)
def compare(
    portfolio_id: int,
    payload: ScenarioCompareIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ScenarioComparisonOut:
    return _authorized(db, tenant_id, user_id, "portfolio_budget_scenario.compare", VIEW_ROLES).compare(
        portfolio_id, payload.scenario_ids
    )


@router.get(
    "/portfolios/{portfolio_id}/budget-planning/readiness",
    response_model=PortfolioBudgetPlanningReadinessOut,
)
def readiness(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioBudgetPlanningReadinessOut:
    return _authorized(db, tenant_id, user_id, "portfolio_budget.read", VIEW_ROLES).readiness(portfolio_id)


@router.get(
    "/portfolios/{portfolio_id}/budget-planning/recommendation-contract",
    response_model=BudgetRecommendationContractOut,
)
def recommendation_contract(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BudgetRecommendationContractOut:
    return _authorized(db, tenant_id, user_id, "portfolio_budget.read", VIEW_ROLES).recommendation_contract(
        portfolio_id
    )


@router.get("/portfolio-budget/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AdminConfigurationOut]:
    return _authorized(db, tenant_id, user_id, "portfolio_budget.admin.configure", CONFIGURATION_ROLES).configurations()


@router.post("/portfolio-budget/admin/configurations/preview", response_model=ConfigurationPreviewOut)
def configuration_preview(
    payload: ConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationPreviewOut:
    return _authorized(
        db, tenant_id, user_id, "portfolio_budget.admin.configure", CONFIGURATION_ROLES
    ).configuration_preview(
        payload.portfolio_workspace_id, payload.configuration_id, payload.content_json, payload.target_assumptions
    )


@router.post("/portfolio-budget/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationOut)
def clone_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    result = _authorized(
        db, tenant_id, user_id, "portfolio_budget.admin.configure", CONFIGURATION_ROLES
    ).clone_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result


@router.put("/portfolio-budget/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
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
        db, tenant_id, user_id, "portfolio_budget.admin.configure", CONFIGURATION_ROLES
    ).update_configuration(configuration_id, expected_version, payload.name, payload.description, payload.content_json)
    _etag(response, result.version)
    return result


@router.post("/portfolio-budget/admin/configurations/{configuration_id}/publish", response_model=AdminConfigurationOut)
def publish_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    result = _authorized(
        db, tenant_id, user_id, "portfolio_budget.admin.publish", CONFIGURATION_ROLES
    ).publish_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result
