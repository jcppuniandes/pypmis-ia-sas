"""Separate reusable ADMIN policy and USER read-only Risk context APIs."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.risk_governance.schemas import (
    ConfigurationCloneIn,
    ConfigurationPreviewIn,
    ConfigurationUpdateIn,
    EffectiveContextIn,
    EffectiveContextOut,
    RiskConfigurationOut,
    ThresholdEvaluationIn,
    ThresholdEvaluationOut,
)
from app.modules.risk_governance.service import THRESHOLD_OPERATORS, RiskGovernanceService

router = APIRouter()
CONFIG_ROLES = frozenset({"organization_admin", "configuration_admin", "risk_configuration_admin"})


def _authorized(db: Session, tenant_id: int, user_id: int, permission: str) -> RiskGovernanceService:
    context = require_enterprise_permission(
        db,
        tenant_id,
        user_id,
        permission,
        allowed_role_codes=CONFIG_ROLES if permission.startswith("risk_governance.admin.") else None,
        bootstrap=False,
    )
    return RiskGovernanceService(db, tenant_id, context.user.id, context)


def _effective_input(
    workspace_id: int | None = Query(default=None, gt=0),
    effective_date: date | None = None,
    project_type: str | None = Query(default=None, max_length=120),
    governance_model: str | None = Query(default=None, max_length=120),
    strategic_theme: str | None = Query(default=None, max_length=120),
    investment_category: str | None = Query(default=None, max_length=120),
) -> EffectiveContextIn:
    return EffectiveContextIn(
        workspace_id=workspace_id,
        effective_date=effective_date,
        project_type=project_type,
        governance_model=governance_model,
        strategic_theme=strategic_theme,
        investment_category=investment_category,
    )


@router.get("/risk-governance/effective", response_model=EffectiveContextOut)
def effective(
    payload: EffectiveContextIn = Depends(_effective_input),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EffectiveContextOut:
    return _authorized(db, tenant_id, user_id, "risk_governance.read").effective(payload)


@router.get("/risk-governance/operators", response_model=list[str])
def operators(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[str]:
    _authorized(db, tenant_id, user_id, "risk_governance.read")
    return list(THRESHOLD_OPERATORS)


@router.post("/risk-governance/threshold-evaluation", response_model=ThresholdEvaluationOut)
def evaluate_threshold(
    payload: ThresholdEvaluationIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ThresholdEvaluationOut:
    return _authorized(db, tenant_id, user_id, "risk_governance.read").evaluate_threshold(payload)


@router.get("/risk-governance/admin/configurations", response_model=list[RiskConfigurationOut])
@router.get("/risk-governance/admin/history", response_model=list[RiskConfigurationOut])
def configurations(
    code: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[RiskConfigurationOut]:
    service = _authorized(db, tenant_id, user_id, "risk_governance.admin.configure")
    return [service.configuration_output(row) for row in service.configurations(code=code)]


@router.get("/risk-governance/admin/configurations/{configuration_id}", response_model=RiskConfigurationOut)
def configuration(
    configuration_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RiskConfigurationOut:
    service = _authorized(db, tenant_id, user_id, "risk_governance.admin.configure")
    row = service.configuration(configuration_id)
    _etag(response, row.version)
    return service.configuration_output(row)


@router.get("/risk-governance/admin/effective-preview", response_model=EffectiveContextOut)
def effective_preview(
    payload: EffectiveContextIn = Depends(_effective_input),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EffectiveContextOut:
    return _authorized(db, tenant_id, user_id, "risk_governance.admin.configure").effective(payload)


@router.post("/risk-governance/admin/preview", response_model=EffectiveContextOut)
def preview(
    payload: ConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EffectiveContextOut:
    return _authorized(db, tenant_id, user_id, "risk_governance.admin.configure").preview(payload)


@router.post("/risk-governance/admin/configurations/{configuration_id}/clone", response_model=RiskConfigurationOut)
def clone_configuration(
    configuration_id: int,
    response: Response,
    payload: ConfigurationCloneIn | None = None,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RiskConfigurationOut:
    result = _authorized(db, tenant_id, user_id, "risk_governance.admin.configure").clone_configuration(
        configuration_id,
        expected_version,
        idempotency_key,
        target_workspace_id=payload.target_workspace_id if payload is not None else None,
    )
    _etag(response, result.version)
    return result


@router.put("/risk-governance/admin/configurations/{configuration_id}", response_model=RiskConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: ConfigurationUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RiskConfigurationOut:
    result = _authorized(db, tenant_id, user_id, "risk_governance.admin.configure").update_configuration(
        configuration_id,
        expected_version,
        name=payload.name,
        description=payload.description,
        content=payload.content_json,
    )
    _etag(response, result.version)
    return result


@router.post("/risk-governance/admin/configurations/{configuration_id}/publish", response_model=RiskConfigurationOut)
def publish_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RiskConfigurationOut:
    result = _authorized(db, tenant_id, user_id, "risk_governance.admin.publish").publish_configuration(
        configuration_id, expected_version, idempotency_key
    )
    _etag(response, result.version)
    return result


@router.post("/risk-governance/admin/configurations/{configuration_id}/archive", response_model=RiskConfigurationOut)
def archive_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    idempotency_key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RiskConfigurationOut:
    result = _authorized(db, tenant_id, user_id, "risk_governance.admin.publish").archive_configuration(
        configuration_id, expected_version, idempotency_key
    )
    _etag(response, result.version)
    return result
