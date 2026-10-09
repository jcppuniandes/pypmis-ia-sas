"""HTTP routes for Gate 07I Portfolio Scenario Convergence and Recommendation."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_convergence.schemas import (
    AlternativeCompareIn,
    AlternativeCreateIn,
    ConfigurationPreviewIn,
    ConfigurationPreviewOut,
    ConfigurationUpdateIn,
    ConvergenceComparisonOut,
    ConvergenceCreateIn,
    ConvergenceRefreshPreviewOut,
    ConvergenceUpdateIn,
    IdempotencyIn,
    InvestmentGatePreparationContractOut,
    PortfolioConvergenceOverviewOut,
    PortfolioRecommendationReadinessOut,
    PortfolioScenarioConvergenceOut,
    RecommendationIn,
    RefreshApplyIn,
)
from app.modules.portfolio_convergence.service import PortfolioConvergenceService

router = APIRouter()

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "portfolio_manager",
        "portfolio_analyst",
        "portfolio_convergence_viewer",
        "portfolio_recommendation_preparer",
        "portfolio_recommendation_reviewer",
        "portfolio_recommender",
    }
)
PREPARER_ROLES = frozenset({"organization_admin", "portfolio_manager", "portfolio_recommendation_preparer"})
REVIEWER_ROLES = frozenset({"organization_admin", "portfolio_manager", "portfolio_recommendation_reviewer"})
RECOMMENDER_ROLES = frozenset({"organization_admin", "portfolio_manager", "portfolio_recommender"})
CONFIGURATION_ROLES = frozenset({"organization_admin", "portfolio_convergence_configuration_admin"})


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
) -> PortfolioConvergenceService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = PortfolioConvergenceService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/portfolios/{portfolio_id}/scenario-convergence", response_model=PortfolioConvergenceOverviewOut)
def overview(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioConvergenceOverviewOut:
    return _authorized(db, tenant_id, user_id, "portfolio_convergence.read", VIEW_ROLES).overview(portfolio_id)


@router.get(
    "/portfolios/{portfolio_id}/scenario-convergences",
    response_model=list[PortfolioScenarioConvergenceOut],
)
def convergences(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[PortfolioScenarioConvergenceOut]:
    return _authorized(db, tenant_id, user_id, "portfolio_convergence.read", VIEW_ROLES).convergences(portfolio_id)


@router.post(
    "/portfolios/{portfolio_id}/scenario-convergences",
    response_model=PortfolioScenarioConvergenceOut,
)
def create_convergence(
    portfolio_id: int,
    payload: ConvergenceCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioScenarioConvergenceOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_convergence.create", PREPARER_ROLES).create_convergence(
        portfolio_id, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get(
    "/portfolio-scenario-convergences/{convergence_id}",
    response_model=PortfolioScenarioConvergenceOut,
)
def convergence(
    convergence_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioScenarioConvergenceOut:
    return _authorized(db, tenant_id, user_id, "portfolio_convergence.read", VIEW_ROLES).convergence(convergence_id)


@router.put(
    "/portfolio-scenario-convergences/{convergence_id}",
    response_model=PortfolioScenarioConvergenceOut,
)
def update_convergence(
    convergence_id: int,
    payload: ConvergenceUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioScenarioConvergenceOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_convergence.edit", PREPARER_ROLES).update_convergence(
        convergence_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.post(
    "/portfolio-scenario-convergences/{convergence_id}/alternatives",
    response_model=PortfolioScenarioConvergenceOut,
)
def add_alternative(
    convergence_id: int,
    payload: AlternativeCreateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioScenarioConvergenceOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_convergence.edit", PREPARER_ROLES).add_alternative(
        convergence_id,
        expected_version,
        payload.alternative_name,
        payload.budget_scenario_id,
        payload.resource_scenario_id,
        payload.idempotency_key,
    )
    _etag(response, result.revision_version)
    return result


@router.delete(
    "/portfolio-scenario-convergences/{convergence_id}/alternatives/{alternative_id}",
    response_model=PortfolioScenarioConvergenceOut,
)
def remove_alternative(
    convergence_id: int,
    alternative_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioScenarioConvergenceOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_convergence.edit", PREPARER_ROLES).remove_alternative(
        convergence_id, alternative_id, expected_version
    )
    _etag(response, result.revision_version)
    return result


@router.post(
    "/portfolio-scenario-convergences/{convergence_id}/compare",
    response_model=ConvergenceComparisonOut,
)
def compare(
    convergence_id: int,
    payload: AlternativeCompareIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConvergenceComparisonOut:
    return _authorized(db, tenant_id, user_id, "portfolio_convergence.compare", VIEW_ROLES).compare(
        convergence_id, payload.alternative_ids
    )


@router.post(
    "/portfolio-scenario-convergences/{convergence_id}/refresh-preview",
    response_model=ConvergenceRefreshPreviewOut,
)
def refresh_preview(
    convergence_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConvergenceRefreshPreviewOut:
    return _authorized(db, tenant_id, user_id, "portfolio_convergence.refresh", PREPARER_ROLES).refresh_preview(
        convergence_id
    )


@router.post(
    "/portfolio-scenario-convergences/{convergence_id}/refresh",
    response_model=PortfolioScenarioConvergenceOut,
)
def apply_refresh(
    convergence_id: int,
    payload: RefreshApplyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioScenarioConvergenceOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_convergence.refresh", PREPARER_ROLES).apply_refresh(
        convergence_id, expected_version, payload.expected_source_hash, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


def _transition(
    convergence_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int,
    db: Session,
    tenant_id: int,
    user_id: int,
    action: str,
) -> PortfolioScenarioConvergenceOut:
    if action == "submit_review":
        service = _authorized(db, tenant_id, user_id, "portfolio_recommendation.submit", PREPARER_ROLES)
        result = service.submit_review(convergence_id, expected_version, payload.idempotency_key)
    elif action == "return_to_draft":
        service = _authorized(db, tenant_id, user_id, "portfolio_recommendation.return", REVIEWER_ROLES)
        result = service.return_to_draft(convergence_id, expected_version, payload.idempotency_key)
    elif action == "clone":
        service = _authorized(db, tenant_id, user_id, "portfolio_convergence.create", PREPARER_ROLES)
        result = service.clone(convergence_id, expected_version, payload.idempotency_key)
    else:
        service = _authorized(db, tenant_id, user_id, "portfolio_convergence.edit", PREPARER_ROLES)
        result = service.void(convergence_id, expected_version, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.post(
    "/portfolio-scenario-convergences/{convergence_id}/submit-review", response_model=PortfolioScenarioConvergenceOut
)
def submit_review(
    convergence_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioScenarioConvergenceOut:
    return _transition(convergence_id, payload, response, expected_version, db, tenant_id, user_id, "submit_review")


@router.post(
    "/portfolio-scenario-convergences/{convergence_id}/return-to-draft", response_model=PortfolioScenarioConvergenceOut
)
def return_to_draft(
    convergence_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioScenarioConvergenceOut:
    return _transition(convergence_id, payload, response, expected_version, db, tenant_id, user_id, "return_to_draft")


@router.post("/portfolio-scenario-convergences/{convergence_id}/clone", response_model=PortfolioScenarioConvergenceOut)
def clone(
    convergence_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioScenarioConvergenceOut:
    return _transition(convergence_id, payload, response, expected_version, db, tenant_id, user_id, "clone")


@router.post("/portfolio-scenario-convergences/{convergence_id}/void", response_model=PortfolioScenarioConvergenceOut)
def void(
    convergence_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioScenarioConvergenceOut:
    return _transition(convergence_id, payload, response, expected_version, db, tenant_id, user_id, "void")


@router.post(
    "/portfolio-scenario-convergences/{convergence_id}/recommend", response_model=PortfolioScenarioConvergenceOut
)
def recommend(
    convergence_id: int,
    payload: RecommendationIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioScenarioConvergenceOut:
    result = _authorized(db, tenant_id, user_id, "portfolio_recommendation.recommend", RECOMMENDER_ROLES).recommend(
        convergence_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get("/portfolios/{portfolio_id}/recommendation-readiness", response_model=PortfolioRecommendationReadinessOut)
def readiness(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PortfolioRecommendationReadinessOut:
    return _authorized(db, tenant_id, user_id, "portfolio_convergence.read", VIEW_ROLES).readiness(portfolio_id)


@router.get(
    "/portfolios/{portfolio_id}/investment-gate-preparation-contract",
    response_model=InvestmentGatePreparationContractOut,
)
def preparation_contract(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationContractOut:
    return _authorized(db, tenant_id, user_id, "portfolio_convergence.read", VIEW_ROLES).preparation_contract(
        portfolio_id
    )


@router.get("/portfolio-convergence/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AdminConfigurationOut]:
    return _authorized(
        db, tenant_id, user_id, "portfolio_convergence.admin.configure", CONFIGURATION_ROLES
    ).configurations()


@router.post("/portfolio-convergence/admin/configurations/preview", response_model=ConfigurationPreviewOut)
def configuration_preview(
    payload: ConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationPreviewOut:
    return _authorized(
        db, tenant_id, user_id, "portfolio_convergence.admin.configure", CONFIGURATION_ROLES
    ).configuration_preview(payload.portfolio_workspace_id, payload.configuration_id, payload.content_json)


@router.post(
    "/portfolio-convergence/admin/configurations/{configuration_id}/clone",
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
        db, tenant_id, user_id, "portfolio_convergence.admin.configure", CONFIGURATION_ROLES
    ).clone_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result


@router.put(
    "/portfolio-convergence/admin/configurations/{configuration_id}",
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
    result = _authorized(
        db, tenant_id, user_id, "portfolio_convergence.admin.configure", CONFIGURATION_ROLES
    ).update_configuration(configuration_id, expected_version, payload.name, payload.description, payload.content_json)
    _etag(response, result.version)
    return result


@router.post(
    "/portfolio-convergence/admin/configurations/{configuration_id}/publish",
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
        db, tenant_id, user_id, "portfolio_convergence.admin.publish", CONFIGURATION_ROLES
    ).publish_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result
