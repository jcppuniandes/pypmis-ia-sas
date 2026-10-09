"""REST API for Gate 07M-FIN governed economic-financial models."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.economic_financial_model.schemas import (
    AssumptionCreateIn,
    AssumptionOut,
    CashFlowOut,
    CompleteVersionIn,
    ConfigurationPreviewIn,
    ConfigurationPreviewOut,
    ConfigurationUpdateIn,
    CreateModelIn,
    CreateVersionIn,
    IdempotencyIn,
    InstrumentCreateIn,
    InstrumentOut,
    InvestorCreateIn,
    InvestorOut,
    MetricOut,
    ModelOut,
    ModelVersionOut,
    PeriodCreateIn,
    PeriodOut,
    ProviderEvidenceOut,
    ReadinessOut,
    RefreshPreviewOut,
    ScenarioCreateIn,
    ScenarioOut,
    SensitivityRunIn,
    UpdateVersionIn,
)
from app.modules.economic_financial_model.service import EconomicFinancialModelService
from app.modules.enterprise_structure.permissions import require_enterprise_permission

router = APIRouter()

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "financial_model_viewer",
        "financial_model_preparer",
        "financial_model_reviewer",
        "project_manager",
        "portfolio_manager",
    }
)
PREPARER_ROLES = frozenset({"organization_admin", "financial_model_owner", "financial_model_preparer"})
REVIEWER_ROLES = frozenset({"organization_admin", "financial_model_reviewer", "financial_model_finance_reviewer"})
ADMIN_ROLES = frozenset({"organization_admin", "financial_model_configuration_admin"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    value = if_match.strip().removeprefix("W/").strip('"')
    if not value.isdigit() or int(value) < 1:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"})
    return int(value)


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def _authorized(
    db: Session, tenant_id: int, user_id: int, permission: str, roles: frozenset[str]
) -> EconomicFinancialModelService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = EconomicFinancialModelService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/economic-financial-models", response_model=list[ModelOut])
def models(
    project_workspace_id: int | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES).list(project_workspace_id)


@router.post("/economic-financial-models", response_model=ModelOut, status_code=201)
def create_model(
    payload: CreateModelIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "economic_financial_model.create", PREPARER_ROLES).create(
        payload.model_dump()
    )
    _etag(response, result.revision_version)
    return result


@router.get("/economic-financial-models/{model_id}", response_model=ModelOut)
def model(
    model_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES).get(model_id)
    _etag(response, result.revision_version)
    return result


@router.get("/projects/{project_id}/economic-financial-model", response_model=ModelOut)
def project_model(
    project_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES).by_project(project_id)
    _etag(response, result.revision_version)
    return result


@router.get("/economic-financial-models/{model_id}/versions", response_model=list[ModelVersionOut])
def versions(
    model_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES).versions(model_id)


@router.post("/economic-financial-models/{model_id}/versions", response_model=ModelVersionOut, status_code=201)
def create_version(
    model_id: int,
    payload: CreateVersionIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "economic_financial_model.create_version", PREPARER_ROLES
    ).create_version(model_id, payload.purpose, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.put("/economic-financial-model-versions/{version_id}", response_model=ModelVersionOut)
def update_version(
    version_id: int,
    payload: UpdateVersionIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "economic_financial_model.edit", PREPARER_ROLES).update_version(
        version_id, expected_version, payload.model_dump(exclude_unset=True)
    )
    _etag(response, result.revision_version)
    return result


@router.get("/economic-financial-model-versions/{version_id}", response_model=ModelVersionOut)
def version(
    version_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = ModelVersionOut.model_validate(
        _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES)._version(version_id)
    )
    _etag(response, result.revision_version)
    return result


@router.get("/economic-financial-model-versions/{version_id}/assumptions", response_model=list[AssumptionOut])
def assumptions(
    version_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES).assumptions(version_id)


@router.put("/economic-financial-model-versions/{version_id}/assumptions", response_model=AssumptionOut)
def upsert_assumption(
    version_id: int,
    payload: AssumptionCreateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "economic_financial_model.edit", PREPARER_ROLES).upsert_assumption(
        version_id, expected_version, payload.model_dump()
    )
    _etag(response, expected_version + 1)
    return result


@router.get("/economic-financial-model-versions/{version_id}/periods", response_model=list[PeriodOut])
def periods(
    version_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES).periods(version_id)


@router.put("/economic-financial-model-versions/{version_id}/periods", response_model=PeriodOut)
def upsert_period(
    version_id: int,
    payload: PeriodCreateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "economic_financial_model.edit", PREPARER_ROLES).upsert_period(
        version_id, expected_version, payload.model_dump()
    )
    _etag(response, expected_version + 1)
    return result


@router.get("/economic-financial-model-versions/{version_id}/financing-instruments", response_model=list[InstrumentOut])
def instruments(
    version_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES).instruments(version_id)


@router.post(
    "/economic-financial-model-versions/{version_id}/financing-instruments",
    response_model=InstrumentOut,
    status_code=201,
)
def create_instrument(
    version_id: int,
    payload: InstrumentCreateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "economic_financial_model.edit", PREPARER_ROLES).create_instrument(
        version_id, expected_version, payload.model_dump()
    )
    _etag(response, expected_version + 1)
    return result


@router.get("/economic-financial-model-versions/{version_id}/investors", response_model=list[InvestorOut])
def investors(
    version_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES).investors(version_id)


@router.post("/economic-financial-model-versions/{version_id}/investors", response_model=InvestorOut, status_code=201)
def create_investor(
    version_id: int,
    payload: InvestorCreateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "economic_financial_model.edit", PREPARER_ROLES).create_investor(
        version_id, expected_version, payload.model_dump()
    )
    _etag(response, expected_version + 1)
    return result


@router.get("/economic-financial-model-versions/{version_id}/scenarios", response_model=list[ScenarioOut])
def scenarios(
    version_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES).scenarios(version_id)


@router.post("/economic-financial-model-versions/{version_id}/scenarios", response_model=ScenarioOut, status_code=201)
def create_scenario(
    version_id: int,
    payload: ScenarioCreateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "economic_financial_model.scenario.manage", PREPARER_ROLES
    ).create_scenario(version_id, expected_version, payload.model_dump())
    _etag(response, expected_version + 1)
    return result


@router.post("/economic-financial-model-versions/{version_id}/calculate", response_model=ModelVersionOut)
def calculate(
    version_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "economic_financial_model.calculate", PREPARER_ROLES).calculate(
        version_id, expected_version, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.post("/economic-financial-model-versions/{version_id}/sensitivities/run", status_code=201)
def sensitivity(
    version_id: int,
    payload: SensitivityRunIn,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(
        db, tenant_id, user_id, "economic_financial_model.sensitivity.run", PREPARER_ROLES
    ).run_sensitivity(version_id, expected_version, **payload.model_dump())


@router.post("/economic-financial-model-versions/{version_id}/submit-review", response_model=ModelVersionOut)
def submit_review(
    version_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "economic_financial_model.submit_review", PREPARER_ROLES
    ).submit_review(version_id, expected_version, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.post("/economic-financial-model-versions/{version_id}/complete", response_model=ModelVersionOut)
def complete(
    version_id: int,
    payload: CompleteVersionIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "economic_financial_model.complete", REVIEWER_ROLES).complete(
        version_id, expected_version, payload.idempotency_key, payload.reviewer_user_id
    )
    _etag(response, result.revision_version)
    return result


@router.get("/economic-financial-models/{model_id}/readiness", response_model=ReadinessOut)
def readiness(
    model_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES).readiness(model_id)


@router.get("/economic-financial-models/{model_id}/investment-gate-evidence", response_model=ProviderEvidenceOut)
def provider_evidence(
    model_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES).provider_evidence(model_id)


@router.get("/economic-financial-model-versions/{version_id}/cash-flows", response_model=list[CashFlowOut])
def cash_flows(
    version_id: int,
    scenario_id: int | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES).cash_flows(
        version_id, scenario_id
    )


@router.get("/economic-financial-model-versions/{version_id}/metrics", response_model=list[MetricOut])
def metrics(
    version_id: int,
    scenario_id: int | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "economic_financial_model.read", VIEW_ROLES).metrics(
        version_id, scenario_id
    )


@router.post("/economic-financial-models/{model_id}/refresh/preview", response_model=RefreshPreviewOut)
def refresh_preview(
    model_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "economic_financial_model.refresh", PREPARER_ROLES).refresh_preview(
        model_id
    )


@router.post("/economic-financial-models/{model_id}/refresh", response_model=ModelVersionOut)
def refresh(
    model_id: int,
    payload: IdempotencyIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "economic_financial_model.refresh", PREPARER_ROLES).refresh(
        model_id, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.get("/economic-financial-models/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), user_id: int = Depends(get_user_id)
):
    return _authorized(db, tenant_id, user_id, "economic_financial_model.admin.configure", ADMIN_ROLES).configurations()


@router.post("/economic-financial-models/admin/configurations/preview", response_model=ConfigurationPreviewOut)
def configuration_preview(
    payload: ConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(
        db, tenant_id, user_id, "economic_financial_model.admin.configure", ADMIN_ROLES
    ).configuration_preview(
        payload.project_workspace_id, payload.business_case_id, payload.configuration_id, payload.content_json
    )


@router.post(
    "/economic-financial-models/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationOut
)
def clone_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "economic_financial_model.admin.configure", ADMIN_ROLES
    ).clone_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result


@router.put("/economic-financial-models/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: ConfigurationUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "economic_financial_model.admin.configure", ADMIN_ROLES
    ).update_configuration(
        configuration_id,
        expected_version,
        name=payload.name,
        description=payload.description,
        content_json=payload.content_json,
    )
    _etag(response, result.version)
    return result


@router.post(
    "/economic-financial-models/admin/configurations/{configuration_id}/publish", response_model=AdminConfigurationOut
)
def publish_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "economic_financial_model.admin.publish", ADMIN_ROLES
    ).publish_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result
