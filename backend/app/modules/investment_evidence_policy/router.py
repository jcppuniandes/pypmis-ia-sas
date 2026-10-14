"""HTTP routes for Gate 07J-EVID policy governance."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.investment_evidence_policy.schemas import (
    EffectivePreviewIn,
    PolicyConfigurationOut,
    PolicyOverviewOut,
    PolicyPreviewOut,
    PolicyUpdateIn,
    ProviderOut,
)
from app.modules.investment_evidence_policy.service import InvestmentEvidencePolicyService

router = APIRouter(prefix="/investment-evidence-policy")

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "investment_evidence_policy_admin",
        "investment_evidence_policy_viewer",
        "investment_gate_configuration_admin",
    }
)
CONFIGURATION_ROLES = frozenset({"organization_admin", "investment_evidence_policy_admin"})


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
) -> InvestmentEvidencePolicyService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = InvestmentEvidencePolicyService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/overview", response_model=PolicyOverviewOut)
def overview(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PolicyOverviewOut:
    return _authorized(db, tenant_id, user_id, "investment_evidence_policy.read", VIEW_ROLES).overview()


@router.get("/configurations", response_model=list[PolicyConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[PolicyConfigurationOut]:
    records = _authorized(db, tenant_id, user_id, "investment_evidence_policy.read", VIEW_ROLES).configurations()
    return [PolicyConfigurationOut.model_validate(item) for item in records]


@router.post("/configurations/{configuration_id}/clone", response_model=PolicyConfigurationOut)
def clone_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=160),
) -> PolicyConfigurationOut:
    result = _authorized(
        db, tenant_id, user_id, "investment_evidence_policy.configure", CONFIGURATION_ROLES
    ).clone_configuration(configuration_id, expected_version, idempotency_key=idempotency_key)
    _etag(response, result.version)
    return PolicyConfigurationOut.model_validate(result)


@router.post(
    "/configurations/{configuration_id}/clone-gate07j-evid2",
    response_model=PolicyConfigurationOut,
)
def clone_gate07j_evid2_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PolicyConfigurationOut:
    """Create/reuse the additive Gate07J-EVID-2 draft from a governed revision."""

    result = _authorized(
        db, tenant_id, user_id, "investment_evidence_policy.configure", CONFIGURATION_ROLES
    ).clone_gate07j_evid2_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return PolicyConfigurationOut.model_validate(result)


@router.put("/configurations/{configuration_id}", response_model=PolicyConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: PolicyUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PolicyConfigurationOut:
    result = _authorized(
        db, tenant_id, user_id, "investment_evidence_policy.configure", CONFIGURATION_ROLES
    ).update_configuration(
        configuration_id,
        expected_version,
        payload.name,
        payload.description,
        payload.content_json,
    )
    _etag(response, result.version)
    return PolicyConfigurationOut.model_validate(result)


@router.post("/configurations/{configuration_id}/preview", response_model=PolicyPreviewOut)
def configuration_preview(
    configuration_id: int,
    payload: EffectivePreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PolicyPreviewOut:
    return _authorized(db, tenant_id, user_id, "investment_evidence_policy.configure", CONFIGURATION_ROLES).preview(
        portfolio_id=payload.portfolio_workspace_id,
        gate_profile_code=payload.gate_profile_code,
        project_ids=payload.project_workspace_ids,
        configuration_id=configuration_id,
        content_override=payload.content_json,
        project_type_code=payload.project_type_code,
        governance_model=payload.governance_model,
    )


@router.post("/configurations/{configuration_id}/publish", response_model=PolicyConfigurationOut)
def publish_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PolicyConfigurationOut:
    result = _authorized(
        db, tenant_id, user_id, "investment_evidence_policy.publish", CONFIGURATION_ROLES
    ).publish_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return PolicyConfigurationOut.model_validate(result)


@router.get("/providers", response_model=list[ProviderOut])
def providers(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProviderOut]:
    return _authorized(db, tenant_id, user_id, "investment_evidence_provider.read", VIEW_ROLES).providers()


@router.get("/providers/{provider_key}", response_model=ProviderOut)
def provider(
    provider_key: str,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProviderOut:
    return _authorized(db, tenant_id, user_id, "investment_evidence_provider.read", VIEW_ROLES).provider(provider_key)


@router.post("/effective/preview", response_model=PolicyPreviewOut)
def effective_preview(
    payload: EffectivePreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PolicyPreviewOut:
    return _authorized(db, tenant_id, user_id, "investment_evidence_policy.configure", CONFIGURATION_ROLES).preview(
        portfolio_id=payload.portfolio_workspace_id,
        gate_profile_code=payload.gate_profile_code,
        project_ids=payload.project_workspace_ids,
        configuration_id=payload.configuration_id,
        content_override=payload.content_json,
        project_type_code=payload.project_type_code,
        governance_model=payload.governance_model,
    )


@router.get("/missing-providers", response_model=list[dict])
def missing_providers(
    gate_profile_code: str | None = Query(default=None, pattern="^(PYP-INV-SELECT|PYP-FFA)$"),
    portfolio_workspace_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[dict]:
    return _authorized(db, tenant_id, user_id, "investment_evidence_policy.read", VIEW_ROLES).missing_providers(
        gate_profile_code, portfolio_workspace_id
    )
