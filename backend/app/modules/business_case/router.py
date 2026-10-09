"""REST surface for Gate 07M-BC."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.business_case.schemas import (
    BusinessCaseOut,
    BusinessCaseRevisionOut,
    CompleteRevisionIn,
    ConfigurationPreviewIn,
    ConfigurationPreviewOut,
    ConfigurationUpdateIn,
    CreateBusinessCaseIn,
    CreateRevisionIn,
    DecisionSnapshotOut,
    IdempotencyIn,
    MaterialChangeReviewIn,
    ReadinessOut,
    RefreshPreviewOut,
    SnapshotCreateIn,
    UpdateRevisionIn,
)
from app.modules.business_case.service import BusinessCaseService
from app.modules.enterprise_structure.permissions import require_enterprise_permission

router = APIRouter()

VIEW_ROLES = frozenset(
    {
        "organization_admin",
        "business_case_preparer",
        "business_case_reviewer",
        "business_case_viewer",
        "portfolio_manager",
    }
)
PREPARER_ROLES = frozenset({"organization_admin", "business_case_preparer"})
REVIEWER_ROLES = frozenset({"organization_admin", "business_case_reviewer"})
CONFIG_ROLES = frozenset({"organization_admin", "business_case_configuration_admin"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    value = if_match.strip().removeprefix("W/").strip('"')
    if not value.isdigit() or int(value) < 1:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IF_MATCH"})
    return int(value)


def _idempotency_key(value: str = Header(..., alias="Idempotency-Key")) -> str:
    value = value.strip()
    if len(value) < 8 or len(value) > 160:
        raise HTTPException(status_code=400, detail={"code": "INVALID_IDEMPOTENCY_KEY"})
    return value


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def _authorized(db, tenant_id, user_id, permission, roles) -> BusinessCaseService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission, allowed_role_codes=roles)
    service = BusinessCaseService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service


@router.get("/business-cases", response_model=list[BusinessCaseOut])
def list_business_cases(
    project_workspace_id: int | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "business_case.read", VIEW_ROLES).list(project_workspace_id)


@router.post("/business-cases", response_model=BusinessCaseOut, status_code=201)
def create_business_case(
    payload: CreateBusinessCaseIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "business_case.create", PREPARER_ROLES).create(
        payload.project_workspace_id,
        payload.source_project_proposal_id,
        payload.owner_user_id,
        payload.sponsor_user_id,
        payload.idempotency_key,
    )
    _etag(response, result.revision_version)
    return result


@router.get("/business-cases/{business_case_id}", response_model=BusinessCaseOut)
def get_business_case(
    business_case_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "business_case.read", VIEW_ROLES).get(business_case_id)
    _etag(response, result.revision_version)
    return result


@router.get("/projects/{project_id}/business-case", response_model=BusinessCaseOut)
def get_project_business_case(
    project_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "business_case.read", VIEW_ROLES).by_project(project_id)
    _etag(response, result.revision_version)
    return result


@router.get("/business-cases/{business_case_id}/revisions", response_model=list[BusinessCaseRevisionOut])
def list_revisions(
    business_case_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "business_case.read", VIEW_ROLES).revisions(business_case_id)


@router.post("/business-cases/{business_case_id}/revisions", response_model=BusinessCaseRevisionOut, status_code=201)
def create_revision(
    business_case_id: int,
    payload: CreateRevisionIn,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "business_case.create_revision", PREPARER_ROLES).create_revision(
        business_case_id, payload.purpose, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.get("/business-case-revisions/{revision_id}", response_model=BusinessCaseRevisionOut)
def get_revision(
    revision_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "business_case.read", VIEW_ROLES).revision_out(revision_id)
    _etag(response, result.revision_version)
    return result


@router.put("/business-case-revisions/{revision_id}", response_model=BusinessCaseRevisionOut)
def update_revision(
    revision_id: int,
    payload: UpdateRevisionIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "business_case.edit", PREPARER_ROLES).update_revision(
        revision_id, expected_version, payload.model_dump(exclude_unset=True)
    )
    _etag(response, result.revision_version)
    return result


@router.post("/business-case-revisions/{revision_id}/submit-review", response_model=BusinessCaseRevisionOut)
def submit_review(
    revision_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "business_case.submit_review", PREPARER_ROLES).submit_review(
        revision_id, expected_version, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.post("/business-case-revisions/{revision_id}/complete", response_model=BusinessCaseRevisionOut)
def complete_revision(
    revision_id: int,
    payload: CompleteRevisionIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "business_case.complete", REVIEWER_ROLES).complete_revision(
        revision_id, expected_version, payload.idempotency_key, payload.reviewer_user_id
    )
    _etag(response, result.revision_version)
    return result


@router.get("/business-cases/{business_case_id}/readiness", response_model=ReadinessOut)
def readiness(
    business_case_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "business_case.read", VIEW_ROLES).readiness(business_case_id)


@router.post("/business-cases/{business_case_id}/refresh/preview", response_model=RefreshPreviewOut)
def refresh_preview(
    business_case_id: int,
    _key: str = Depends(_idempotency_key),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "business_case.refresh", PREPARER_ROLES).refresh_preview(
        business_case_id
    )


@router.post("/business-cases/{business_case_id}/refresh", response_model=BusinessCaseRevisionOut)
def refresh(
    business_case_id: int,
    payload: IdempotencyIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "business_case.refresh", PREPARER_ROLES).refresh(
        business_case_id, expected_version, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.get("/business-cases/{business_case_id}/decision-snapshots", response_model=list[DecisionSnapshotOut])
def list_snapshots(
    business_case_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "business_case.read", VIEW_ROLES).snapshots(business_case_id)


@router.post(
    "/business-cases/{business_case_id}/decision-snapshots",
    response_model=DecisionSnapshotOut,
    status_code=201,
)
def create_snapshot(
    business_case_id: int,
    payload: SnapshotCreateIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "business_case.snapshot", REVIEWER_ROLES).create_snapshot(
        business_case_id,
        payload.business_case_revision_id,
        payload.snapshot_type,
        payload.decision_reference_type,
        payload.decision_reference_id,
        payload.decision_reference_hash,
        payload.idempotency_key,
    )


@router.get("/business-cases/{business_case_id}/material-change", response_model=RefreshPreviewOut)
def material_change(
    business_case_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "business_case.read", VIEW_ROLES).material_change(business_case_id)


@router.post("/business-cases/{business_case_id}/material-change/review", response_model=BusinessCaseOut)
def material_change_review(
    business_case_id: int,
    payload: MaterialChangeReviewIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(
        db, tenant_id, user_id, "business_case.material_change.review", REVIEWER_ROLES
    ).review_material_change(
        business_case_id, expected_version, payload.outcome, payload.rationale, payload.idempotency_key
    )
    _etag(response, result.revision_version)
    return result


@router.get("/business-cases/admin/configurations", response_model=list[AdminConfigurationOut])
def configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "business_case.admin.configure", CONFIG_ROLES).configurations()


@router.post("/business-cases/admin/configurations/preview", response_model=ConfigurationPreviewOut)
def configuration_preview(
    payload: ConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    return _authorized(db, tenant_id, user_id, "business_case.admin.configure", CONFIG_ROLES).configuration_preview(
        payload.project_workspace_id, payload.configuration_id, payload.content_json
    )


@router.post("/business-cases/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationOut)
def clone_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "business_case.admin.configure", CONFIG_ROLES).clone_configuration(
        configuration_id, expected_version
    )
    _etag(response, result.version)
    return result


@router.put("/business-cases/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: ConfigurationUpdateIn,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "business_case.admin.configure", CONFIG_ROLES).update_configuration(
        configuration_id,
        expected_version,
        name=payload.name,
        description=payload.description,
        content_json=payload.content_json,
    )
    _etag(response, result.version)
    return result


@router.post("/business-cases/admin/configurations/{configuration_id}/publish", response_model=AdminConfigurationOut)
def publish_configuration(
    configuration_id: int,
    response: Response,
    expected_version: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
):
    result = _authorized(db, tenant_id, user_id, "business_case.admin.publish", CONFIG_ROLES).publish_configuration(
        configuration_id, expected_version
    )
    _etag(response, result.version)
    return result
