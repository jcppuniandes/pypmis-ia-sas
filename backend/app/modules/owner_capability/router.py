"""Permission-scoped USER aggregate and ADMIN-only framework APIs."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.owner_capability.schemas import (
    AssessmentActionIn,
    AssessmentCreateIn,
    AssessmentUpdateIn,
    ConfigurationCloneIn,
    ConfigurationPreviewIn,
    ConfigurationUpdateIn,
    MitigationIn,
)
from app.modules.owner_capability.service import OwnerCapabilityService
from app.modules.portfolio_review.router import _etag as write_etag
from app.modules.portfolio_review.router import _idempotency_key as command_key
from app.modules.portfolio_review.router import _if_match

router = APIRouter()


def _authorized(permission):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), user_id: int = Depends(get_user_id)
    ):
        context = require_enterprise_permission(
            db, tenant_id, user_id, f"owner_capability.{permission}", bootstrap=False
        )
        return OwnerCapabilityService(db, tenant_id, user_id, context)

    return dependency


def _etag(response, result, *, config=False):
    write_etag(response, result["version" if config else "revision_version"])
    return result


@router.get("/options")
def options(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    search: str | None = Query(None, max_length=180),
    service: OwnerCapabilityService = Depends(_authorized("read")),
):
    return service.options(page=page, page_size=page_size, search=search)


@router.get("/projects/{project_id}/requirements")
def requirements(project_id: int, service: OwnerCapabilityService = Depends(_authorized("read"))):
    result = service.requirements(project_id)
    result.pop("policy", None)
    return result


@router.get("/projects/{project_id}/contexts")
def contexts(project_id: int, service: OwnerCapabilityService = Depends(_authorized("read"))):
    return service.contexts(project_id)


@router.get("/projects/{project_id}/assessments")
def assessments(
    project_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: OwnerCapabilityService = Depends(_authorized("read")),
):
    return service.assessments(project_id, page=page, page_size=page_size)


@router.post("/projects/{project_id}/assessments", status_code=201)
def create(
    project_id: int,
    payload: AssessmentCreateIn,
    response: Response,
    key: str = Depends(command_key),
    service: OwnerCapabilityService = Depends(_authorized("assessment.create")),
):
    return _etag(response, service.create_assessment(project_id, payload, key))


@router.get("/assessments/{assessment_id}")
def assessment(assessment_id: int, response: Response, service: OwnerCapabilityService = Depends(_authorized("read"))):
    return _etag(response, service.assessment(assessment_id))


@router.put("/assessments/{assessment_id}")
def update(
    assessment_id: int,
    payload: AssessmentUpdateIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(command_key),
    service: OwnerCapabilityService = Depends(_authorized("assessment.edit")),
):
    return _etag(response, service.update_assessment(assessment_id, expected, payload, key))


@router.post("/assessments/{assessment_id}/preview")
def preview(assessment_id: int, service: OwnerCapabilityService = Depends(_authorized("read"))):
    return service.preview(assessment_id)


@router.post("/assessments/{assessment_id}/submit")
def submit(
    assessment_id: int,
    payload: AssessmentActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(command_key),
    service: OwnerCapabilityService = Depends(_authorized("assessment.submit")),
):
    return _etag(response, service.submit(assessment_id, expected, payload, key))


@router.post("/assessments/{assessment_id}/review")
def review(
    assessment_id: int,
    payload: AssessmentActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(command_key),
    service: OwnerCapabilityService = Depends(_authorized("assessment.review")),
):
    return _etag(response, service.review(assessment_id, expected, payload, key))


@router.post("/assessments/{assessment_id}/complete")
def complete(
    assessment_id: int,
    payload: AssessmentActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(command_key),
    service: OwnerCapabilityService = Depends(_authorized("assessment.complete")),
):
    return _etag(response, service.complete(assessment_id, expected, payload, key))


@router.get("/assessments/{assessment_id}/mitigations")
def mitigations(assessment_id: int, service: OwnerCapabilityService = Depends(_authorized("read"))):
    return service.mitigations(assessment_id)


@router.post("/assessments/{assessment_id}/mitigations", status_code=201)
def create_mitigation(
    assessment_id: int,
    payload: MitigationIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(command_key),
    service: OwnerCapabilityService = Depends(_authorized("mitigation.edit")),
):
    return _etag(response, service.save_mitigation(assessment_id, expected, payload, key))


@router.put("/assessments/{assessment_id}/mitigations/{mitigation_id}")
def update_mitigation(
    assessment_id: int,
    mitigation_id: int,
    payload: MitigationIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(command_key),
    service: OwnerCapabilityService = Depends(_authorized("mitigation.edit")),
):
    return _etag(response, service.save_mitigation(assessment_id, expected, payload, key, mitigation_id))


@router.get("/projects/{project_id}/current-readiness")
def current(project_id: int, service: OwnerCapabilityService = Depends(_authorized("read"))):
    return service.current_readiness(project_id)


@router.get("/projects/{project_id}/provider-evidence")
def evidence(project_id: int, service: OwnerCapabilityService = Depends(_authorized("read"))):
    return service.provider_evidence(project_id)


@router.get("/assessments/{assessment_id}/refresh-preview")
@router.post("/assessments/{assessment_id}/refresh-preview")
def refresh_preview(assessment_id: int, service: OwnerCapabilityService = Depends(_authorized("read"))):
    return service.refresh_preview(assessment_id)


@router.post("/assessments/{assessment_id}/refresh-apply", status_code=201)
def refresh(
    assessment_id: int,
    payload: AssessmentActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(command_key),
    service: OwnerCapabilityService = Depends(_authorized("assessment.create")),
):
    return _etag(response, service.refresh_apply(assessment_id, expected, payload, key))


@router.get("/admin/configurations")
def configurations(service: OwnerCapabilityService = Depends(_authorized("admin.configure"))):
    return service.configurations()


@router.get("/admin/configurations/{configuration_id}")
def configuration(
    configuration_id: int, response: Response, service: OwnerCapabilityService = Depends(_authorized("admin.configure"))
):
    return _etag(response, service.configuration(configuration_id), config=True)


@router.get("/admin/configurations/{configuration_id}/history")
def configuration_history(
    configuration_id: int, service: OwnerCapabilityService = Depends(_authorized("admin.configure"))
):
    return service.configuration_history(configuration_id)


@router.put("/admin/configurations/{configuration_id}")
def edit_configuration(
    configuration_id: int,
    payload: ConfigurationUpdateIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(command_key),
    service: OwnerCapabilityService = Depends(_authorized("admin.configure")),
):
    return _etag(response, service.update_configuration(configuration_id, expected, payload, key), config=True)


@router.post("/admin/configurations/{configuration_id}/clone", status_code=201)
def clone(
    configuration_id: int,
    payload: ConfigurationCloneIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(command_key),
    service: OwnerCapabilityService = Depends(_authorized("admin.configure")),
):
    return _etag(response, service.clone_configuration(configuration_id, expected, payload, key), config=True)


@router.post("/admin/configurations/{configuration_id}/publish")
def publish(
    configuration_id: int,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(command_key),
    service: OwnerCapabilityService = Depends(_authorized("admin.publish")),
):
    return _etag(response, service.publish_configuration(configuration_id, expected, key), config=True)


@router.post("/admin/configurations/{configuration_id}/archive")
def archive(
    configuration_id: int,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(command_key),
    service: OwnerCapabilityService = Depends(_authorized("admin.publish")),
):
    return _etag(response, service.archive_configuration(configuration_id, expected, key), config=True)


@router.post("/admin/preview")
@router.post("/admin/effective-preview")
def configuration_preview(
    payload: ConfigurationPreviewIn, service: OwnerCapabilityService = Depends(_authorized("admin.configure"))
):
    return service.configuration_preview(payload)
