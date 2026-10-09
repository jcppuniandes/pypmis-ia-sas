"""HTTP routes for Gate 07L Post-FID Project Governance."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.post_fid_governance.schemas import (
    ConfigurationPreviewIn,
    ConfigurationPreviewOut,
    ConfigurationUpdateIn,
    EligibilityOut,
    HandoffOut,
    HistoryItemOut,
    IdempotencyIn,
    PostFIDDecisionOut,
    RefreshPreviewOut,
)
from app.modules.post_fid_governance.service import PostFIDGovernanceService

router = APIRouter()

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "portfolio_manager",
        "post_fid_governance_manager",
        "post_fid_governance_viewer",
        "project_workspace_initializer",
        "project_workspace_activator",
    }
)
MANAGER_ROLES = frozenset({"organization_admin", "post_fid_governance_manager"})
CONFIG_ROLES = frozenset({"organization_admin", "post_fid_governance_configuration_admin"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    normalized = if_match.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"})
    return int(normalized)


def _idempotency_key(value: str = Header(..., alias="Idempotency-Key")) -> str:
    if len(value.strip()) < 8 or len(value) > 160:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IDEMPOTENCY_KEY"})
    return value.strip()


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def _authorized(db, tenant_id, user_id, permission, roles) -> PostFIDGovernanceService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = PostFIDGovernanceService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/post-fid-governance", response_model=list[PostFIDDecisionOut])
def queue(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "post_fid_governance.read", VIEW_ROLES).list()


@router.get("/post-fid-governance/{decision_id}", response_model=PostFIDDecisionOut)
def decision(
    decision_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "post_fid_governance.read", VIEW_ROLES).get(decision_id)
    _etag(response, max((item.revision_version for item in result.projects), default=1))
    return result


@router.get("/post-fid-governance/{decision_id}/projects", response_model=list[EligibilityOut])
def projects(
    decision_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "post_fid_governance.read", VIEW_ROLES).projects(decision_id)


@router.post("/post-fid-governance/{decision_id}/evaluate", response_model=list[EligibilityOut])
def evaluate(
    decision_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    if expected_version < 1:
        raise HTTPException(status_code=409, detail={"code": "POST_FID_VERSION_CONFLICT"})
    result = _authorized(db, tenant_id, user_id, "post_fid_governance.evaluate", MANAGER_ROLES).evaluate(
        decision_id, payload.idempotency_key, expected_version
    )
    _etag(response, max((item.revision_version for item in result), default=1))
    return result


@router.post("/post-fid-governance/{decision_id}/refresh/preview", response_model=RefreshPreviewOut)
def refresh_preview(
    decision_id: int,
    _key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "post_fid_governance.refresh", MANAGER_ROLES).refresh_preview(
        decision_id
    )


@router.post("/post-fid-governance/{decision_id}/refresh", response_model=list[EligibilityOut])
def refresh(
    decision_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    if expected_version < 1:
        raise HTTPException(status_code=409, detail={"code": "POST_FID_VERSION_CONFLICT"})
    result = _authorized(db, tenant_id, user_id, "post_fid_governance.refresh", MANAGER_ROLES).refresh(
        decision_id, payload.idempotency_key, expected_version
    )
    _etag(response, max((item.revision_version for item in result), default=1))
    return result


@router.get(
    "/post-fid-governance/{decision_id}/projects/{project_id}/eligibility",
    response_model=EligibilityOut,
)
def eligibility(
    decision_id: int,
    project_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "post_fid_governance.read", VIEW_ROLES).project_eligibility(
        decision_id, project_id
    )
    _etag(response, result.revision_version)
    return result


@router.get(
    "/post-fid-governance/{decision_id}/projects/{project_id}/initialization-handoff",
    response_model=HandoffOut,
)
def initialization_handoff(
    decision_id: int,
    project_id: int,
    key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "post_fid_governance.read", VIEW_ROLES).initialization_handoff(
        decision_id, project_id, key
    )


@router.get(
    "/post-fid-governance/{decision_id}/projects/{project_id}/activation-handoff",
    response_model=HandoffOut,
)
def activation_handoff(
    decision_id: int,
    project_id: int,
    key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "post_fid_governance.read", VIEW_ROLES).activation_handoff(
        decision_id, project_id, key
    )


@router.get("/post-fid-governance/{decision_id}/history", response_model=list[HistoryItemOut])
def history(
    decision_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "post_fid_governance.read", VIEW_ROLES).history(decision_id)


@router.get("/post-fid-governance/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "post_fid_governance.admin.configure", CONFIG_ROLES).configurations()


@router.post("/post-fid-governance/admin/configurations/preview", response_model=ConfigurationPreviewOut)
def configuration_preview(
    payload: ConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(
        db, tenant_id, user_id, "post_fid_governance.admin.configure", CONFIG_ROLES
    ).configuration_preview(
        investment_decision_id=payload.investment_decision_id,
        project_workspace_ids=payload.project_workspace_ids,
        configuration_id=payload.configuration_id,
        content_json=payload.content_json,
    )


@router.post(
    "/post-fid-governance/admin/configurations/{configuration_id}/clone",
    response_model=AdminConfigurationOut,
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
        db, tenant_id, user_id, "post_fid_governance.admin.configure", CONFIG_ROLES
    ).clone_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result


@router.put(
    "/post-fid-governance/admin/configurations/{configuration_id}",
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
):
    result = _authorized(
        db, tenant_id, user_id, "post_fid_governance.admin.configure", CONFIG_ROLES
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
    "/post-fid-governance/admin/configurations/{configuration_id}/publish",
    response_model=AdminConfigurationOut,
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
        db, tenant_id, user_id, "post_fid_governance.admin.publish", CONFIG_ROLES
    ).publish_configuration(configuration_id, expected_version)
    _etag(response, result.version)
    return result
