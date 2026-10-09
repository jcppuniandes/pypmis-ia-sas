"""HTTP routes for Gate 07E."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_evaluation.schemas import (
    ConfigurationPreviewIn,
    ConfigurationPreviewOut,
    ConfigurationUpdateIn,
    EvaluationCompleteIn,
    EvaluationOut,
    EvaluationQueueItemOut,
    EvaluationReevaluateIn,
    EvaluationStartIn,
    EvaluationUpdateIn,
    PrioritizationOut,
    PrioritizationPreviewIn,
    PrioritizationReadinessOut,
)
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService

router = APIRouter()

EVALUATOR_ROLES = frozenset({"organization_admin", "portfolio_evaluator"})
PRIORITIZATION_ROLES = frozenset(
    {"organization_admin", "portfolio_evaluator", "portfolio_prioritization_viewer", "portfolio_intake_planner"}
)
CONFIGURATION_ROLES = frozenset({"organization_admin", "portfolio_evaluation_configuration_admin"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    normalized = if_match.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"})
    return int(normalized)


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    roles: frozenset[str] | None = None,
) -> PortfolioEvaluationService:
    context = require_enterprise_permission(
        db,
        tenant_id,
        user_id,
        permission,
        allowed_role_codes=roles,
    )
    service = PortfolioEvaluationService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/portfolios/{portfolio_id}/evaluations", response_model=list[EvaluationQueueItemOut])
def evaluations(
    portfolio_id: int,
    queue: str | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[EvaluationQueueItemOut]:
    return _authorized(db, tenant_id, user_id, "portfolio_evaluation.read").evaluation_queue(portfolio_id, queue)


@router.post(
    "/portfolios/{portfolio_id}/projects/{project_id}/evaluations",
    response_model=EvaluationOut,
    status_code=status.HTTP_201_CREATED,
)
def start_evaluation(
    portfolio_id: int,
    project_id: int,
    payload: EvaluationStartIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EvaluationOut:
    record = _authorized(db, tenant_id, user_id, "portfolio_evaluation.create", EVALUATOR_ROLES).start_evaluation(
        portfolio_id, project_id, payload.idempotency_key
    )
    response.headers["ETag"] = f'"{record.revision_version}"'
    return record


@router.get("/portfolio-evaluations/{evaluation_id}", response_model=EvaluationOut)
def get_evaluation(
    evaluation_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EvaluationOut:
    record = _authorized(db, tenant_id, user_id, "portfolio_evaluation.read").get_evaluation(evaluation_id)
    response.headers["ETag"] = f'"{record.revision_version}"'
    return record


@router.put("/portfolio-evaluations/{evaluation_id}", response_model=EvaluationOut)
def update_evaluation(
    evaluation_id: int,
    payload: EvaluationUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EvaluationOut:
    record = _authorized(db, tenant_id, user_id, "portfolio_evaluation.edit", EVALUATOR_ROLES).update_evaluation(
        evaluation_id, expected_version, payload
    )
    response.headers["ETag"] = f'"{record.revision_version}"'
    return record


@router.post("/portfolio-evaluations/{evaluation_id}/complete", response_model=EvaluationOut)
def complete_evaluation(
    evaluation_id: int,
    payload: EvaluationCompleteIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EvaluationOut:
    record = _authorized(db, tenant_id, user_id, "portfolio_evaluation.complete", EVALUATOR_ROLES).complete_evaluation(
        evaluation_id, expected_version, payload.idempotency_key
    )
    response.headers["ETag"] = f'"{record.revision_version}"'
    return record


@router.post("/portfolio-evaluations/{evaluation_id}/reevaluate", response_model=EvaluationOut)
def reevaluate(
    evaluation_id: int,
    payload: EvaluationReevaluateIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EvaluationOut:
    record = _authorized(db, tenant_id, user_id, "portfolio_evaluation.reevaluate", EVALUATOR_ROLES).reevaluate(
        evaluation_id, payload.idempotency_key
    )
    response.headers["ETag"] = f'"{record.revision_version}"'
    return record


@router.get("/portfolios/{portfolio_id}/prioritization", response_model=PrioritizationOut)
def prioritization(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PrioritizationOut:
    return _authorized(db, tenant_id, user_id, "portfolio_prioritization.read", PRIORITIZATION_ROLES).prioritization(
        portfolio_id
    )


@router.get("/portfolios/{portfolio_id}/prioritization/readiness", response_model=PrioritizationReadinessOut)
def readiness(
    portfolio_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PrioritizationReadinessOut:
    return _authorized(db, tenant_id, user_id, "portfolio_prioritization.read", PRIORITIZATION_ROLES).readiness(
        portfolio_id
    )


@router.post("/portfolios/{portfolio_id}/prioritization/preview", response_model=PrioritizationOut)
def prioritization_preview(
    portfolio_id: int,
    payload: PrioritizationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PrioritizationOut:
    return _authorized(
        db, tenant_id, user_id, "portfolio_prioritization.read", PRIORITIZATION_ROLES
    ).prioritization_preview(portfolio_id, payload)


@router.get("/portfolio-evaluation/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AdminConfigurationOut]:
    return _authorized(
        db,
        tenant_id,
        user_id,
        "portfolio_evaluation.admin.configure",
        CONFIGURATION_ROLES,
    ).configurations()


@router.post("/portfolio-evaluation/admin/configurations/preview", response_model=ConfigurationPreviewOut)
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
        "portfolio_evaluation.admin.configure",
        CONFIGURATION_ROLES,
    ).configuration_preview(payload.workspace_id, payload.configuration_id, payload.content_json)


@router.post(
    "/portfolio-evaluation/admin/configurations/{configuration_id}/clone",
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
        "portfolio_evaluation.admin.configure",
        CONFIGURATION_ROLES,
    ).clone_configuration(configuration_id, expected_version)


@router.put(
    "/portfolio-evaluation/admin/configurations/{configuration_id}",
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
        "portfolio_evaluation.admin.configure",
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
    "/portfolio-evaluation/admin/configurations/{configuration_id}/publish",
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
        "portfolio_evaluation.admin.publish",
        CONFIGURATION_ROLES,
    ).publish_configuration(configuration_id, expected_version)
    response.headers["ETag"] = f'"{record.version}"'
    return record
