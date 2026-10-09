"""HTTP routes for Gate 07J Investment Gate Preparation."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.investment_gate_preparation.schemas import (
    ConditionUpdateIn,
    ConfigurationPreviewIn,
    ConfigurationPreviewOut,
    ConfigurationUpdateIn,
    EvidenceValidationIn,
    HandoffOut,
    IdempotencyIn,
    InvestmentGatePreparationOut,
    ManualEvidenceIn,
    ManualEvidenceUpdateIn,
    PreparationCreateIn,
    PreparationOverviewOut,
    PreparationReadinessOut,
    PreparationUpdateIn,
    ProjectReadinessOut,
    RefreshApplyIn,
    RefreshPreviewOut,
)
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService

router = APIRouter()

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "portfolio_manager",
        "investment_gate_preparer",
        "investment_evidence_reviewer",
        "investment_gate_preparation_viewer",
    }
)
PREPARER_ROLES = frozenset({"organization_admin", "portfolio_manager", "investment_gate_preparer"})
REVIEWER_ROLES = frozenset({"organization_admin", "portfolio_manager", "investment_evidence_reviewer"})
CONFIGURATION_ROLES = frozenset({"organization_admin", "investment_gate_configuration_admin"})


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
) -> InvestmentGatePreparationService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = InvestmentGatePreparationService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get(
    "/portfolios/{portfolio_id}/investment-gate-preparation",
    response_model=PreparationOverviewOut,
)
def overview(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PreparationOverviewOut:
    return _authorized(db, tenant_id, user_id, "investment_gate_preparation.read", VIEW_ROLES).overview(portfolio_id)


@router.get("/investment-gate-preparations", response_model=list[InvestmentGatePreparationOut])
def preparations(
    portfolio_workspace_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[InvestmentGatePreparationOut]:
    return _authorized(db, tenant_id, user_id, "investment_gate_preparation.read", VIEW_ROLES).preparations(
        portfolio_workspace_id
    )


@router.post("/investment-gate-preparations", response_model=InvestmentGatePreparationOut)
def create(
    payload: PreparationCreateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationOut:
    result = _authorized(db, tenant_id, user_id, "investment_gate_preparation.create", PREPARER_ROLES).create(payload)
    _etag(response, result.revision_version)
    return result


@router.get("/investment-gate-preparations/{preparation_id}", response_model=InvestmentGatePreparationOut)
def preparation(
    preparation_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationOut:
    result = _authorized(db, tenant_id, user_id, "investment_gate_preparation.read", VIEW_ROLES).preparation(
        preparation_id
    )
    _etag(response, result.revision_version)
    return result


@router.put("/investment-gate-preparations/{preparation_id}", response_model=InvestmentGatePreparationOut)
def update(
    preparation_id: int,
    payload: PreparationUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationOut:
    result = _authorized(db, tenant_id, user_id, "investment_gate_preparation.edit", PREPARER_ROLES).update(
        preparation_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get(
    "/investment-gate-preparations/{preparation_id}/readiness",
    response_model=PreparationReadinessOut,
)
def readiness(
    preparation_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PreparationReadinessOut:
    return _authorized(db, tenant_id, user_id, "investment_gate_preparation.read", VIEW_ROLES).readiness(preparation_id)


@router.post(
    "/investment-gate-preparations/{preparation_id}/evidence",
    response_model=InvestmentGatePreparationOut,
)
def add_evidence(
    preparation_id: int,
    payload: ManualEvidenceIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationOut:
    result = _authorized(db, tenant_id, user_id, "investment_gate_evidence.add", PREPARER_ROLES).add_evidence(
        preparation_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.put("/investment-gate-evidence/{evidence_id}", response_model=InvestmentGatePreparationOut)
def update_evidence(
    evidence_id: int,
    payload: ManualEvidenceUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationOut:
    result = _authorized(db, tenant_id, user_id, "investment_gate_evidence.add", PREPARER_ROLES).update_evidence(
        evidence_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.delete("/investment-gate-evidence/{evidence_id}", response_model=InvestmentGatePreparationOut)
def remove_evidence(
    evidence_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationOut:
    result = _authorized(db, tenant_id, user_id, "investment_gate_evidence.add", PREPARER_ROLES).remove_evidence(
        evidence_id, expected_version
    )
    _etag(response, result.revision_version)
    return result


@router.post("/investment-gate-evidence/{evidence_id}/validate", response_model=InvestmentGatePreparationOut)
def validate_evidence(
    evidence_id: int,
    payload: EvidenceValidationIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationOut:
    result = _authorized(db, tenant_id, user_id, "investment_gate_evidence.validate", REVIEWER_ROLES).validate_evidence(
        evidence_id, expected_version, payload
    )
    _etag(response, result.revision_version)
    return result


@router.get(
    "/investment-gate-preparations/{preparation_id}/project-readiness",
    response_model=ProjectReadinessOut,
)
def project_readiness(
    preparation_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectReadinessOut:
    return _authorized(db, tenant_id, user_id, "investment_gate_preparation.read", VIEW_ROLES).project_readiness(
        preparation_id
    )


@router.post(
    "/investment-gate-preparations/{preparation_id}/refresh/preview",
    response_model=RefreshPreviewOut,
)
def refresh_preview(
    preparation_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RefreshPreviewOut:
    return _authorized(db, tenant_id, user_id, "investment_gate_preparation.refresh", PREPARER_ROLES).refresh_preview(
        preparation_id
    )


@router.post("/investment-gate-preparations/{preparation_id}/refresh", response_model=InvestmentGatePreparationOut)
def refresh(
    preparation_id: int,
    payload: RefreshApplyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationOut:
    result = _authorized(db, tenant_id, user_id, "investment_gate_preparation.refresh", PREPARER_ROLES).refresh(
        preparation_id, expected_version, payload.expected_source_hash, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.put(
    "/investment-gate-preparations/{preparation_id}/conditions/{condition_index}",
    response_model=InvestmentGatePreparationOut,
)
def update_condition(
    preparation_id: int,
    condition_index: int,
    payload: ConditionUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationOut:
    result = _authorized(db, tenant_id, user_id, "investment_gate_preparation.edit", PREPARER_ROLES).update_condition(
        preparation_id, condition_index, expected_version, payload.model_dump(mode="json")
    )
    _etag(response, result.revision_version)
    return result


def _transition(
    preparation_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int,
    db: Session,
    tenant_id: int,
    user_id: int,
    action: str,
) -> InvestmentGatePreparationOut:
    permission = {
        "ready": "investment_gate_preparation.edit",
        "freeze": "investment_gate_preparation.freeze",
        "clone": "investment_gate_preparation.clone",
        "void": "investment_gate_preparation.void",
    }[action]
    service = _authorized(db, tenant_id, user_id, permission, PREPARER_ROLES if action != "freeze" else REVIEWER_ROLES)
    method = {
        "ready": service.ready_for_review,
        "freeze": service.freeze,
        "clone": service.clone,
        "void": service.void,
    }[action]
    result = method(preparation_id, expected_version, payload.idempotency_key)
    _etag(response, result.revision_version)
    return result


@router.post(
    "/investment-gate-preparations/{preparation_id}/ready-for-review",
    response_model=InvestmentGatePreparationOut,
)
def ready_for_review(
    preparation_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationOut:
    return _transition(preparation_id, payload, response, expected_version, db, tenant_id, user_id, "ready")


@router.post("/investment-gate-preparations/{preparation_id}/freeze", response_model=InvestmentGatePreparationOut)
def freeze(
    preparation_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationOut:
    return _transition(preparation_id, payload, response, expected_version, db, tenant_id, user_id, "freeze")


@router.post("/investment-gate-preparations/{preparation_id}/clone", response_model=InvestmentGatePreparationOut)
def clone(
    preparation_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationOut:
    return _transition(preparation_id, payload, response, expected_version, db, tenant_id, user_id, "clone")


@router.post("/investment-gate-preparations/{preparation_id}/void", response_model=InvestmentGatePreparationOut)
def void(
    preparation_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> InvestmentGatePreparationOut:
    return _transition(preparation_id, payload, response, expected_version, db, tenant_id, user_id, "void")


@router.get("/investment-gate-preparations/{preparation_id}/handoff", response_model=HandoffOut)
def handoff(
    preparation_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> HandoffOut:
    return _authorized(db, tenant_id, user_id, "investment_gate_preparation.read", VIEW_ROLES).handoff(preparation_id)


@router.get("/investment-gate-preparation/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AdminConfigurationOut]:
    return _authorized(
        db, tenant_id, user_id, "investment_gate_preparation.admin.configure", CONFIGURATION_ROLES
    ).configurations()


@router.post(
    "/investment-gate-preparation/admin/configurations/preview",
    response_model=ConfigurationPreviewOut,
)
def configuration_preview(
    payload: ConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationPreviewOut:
    return _authorized(
        db, tenant_id, user_id, "investment_gate_preparation.admin.configure", CONFIGURATION_ROLES
    ).configuration_preview(payload.portfolio_workspace_id, payload.configuration_id, payload.content_json)


@router.post(
    "/investment-gate-preparation/admin/configurations/{configuration_id}/clone",
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
        db, tenant_id, user_id, "investment_gate_preparation.admin.configure", CONFIGURATION_ROLES
    ).clone_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result


@router.put(
    "/investment-gate-preparation/admin/configurations/{configuration_id}",
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
        db, tenant_id, user_id, "investment_gate_preparation.admin.configure", CONFIGURATION_ROLES
    ).update_configuration(configuration_id, expected_version, payload.name, payload.description, payload.content_json)
    _etag(response, result.version)
    return result


@router.post(
    "/investment-gate-preparation/admin/configurations/{configuration_id}/publish",
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
        db, tenant_id, user_id, "investment_gate_preparation.admin.publish", CONFIGURATION_ROLES
    ).publish_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result
