"""Permission-scoped Wave 2B APIs; ADMIN config never completes live evidence."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.basic_data.schemas import (
    AssessmentActionIn,
    AssessmentCreateIn,
    ConfigurationCloneIn,
    ConfigurationPreviewIn,
    ConfigurationUpdateIn,
    ItemCreateIn,
    ItemUpdateIn,
    ItemValidateIn,
)
from app.modules.basic_data.service import BasicDataService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag as _write_etag
from app.modules.portfolio_review.router import _idempotency_key as _key
from app.modules.portfolio_review.router import _if_match

router = APIRouter()


def _authorized(permission: str):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), user_id: int = Depends(get_user_id)
    ):
        context = require_enterprise_permission(db, tenant_id, user_id, permission, bootstrap=False)
        return BasicDataService(db, tenant_id, context.user.id, context)

    return dependency


def _etag(response: Response, result: dict, *, config=False) -> dict:
    _write_etag(response, result["version" if config else "revision_version"])
    return result


@router.get("/options")
def options(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    search: str | None = Query(None, max_length=180),
    service: BasicDataService = Depends(_authorized("basic_data.read")),
):
    return service.options(page=page, page_size=page_size, search=search)


@router.get("/projects/{project_id}/requirements")
def requirements(project_id: int, service: BasicDataService = Depends(_authorized("basic_data.read"))):
    result = service.requirements(project_id)
    result.pop("policy", None)
    return result


@router.get("/projects/{project_id}/items")
def items(
    project_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    category: str | None = None,
    validation_state: str | None = None,
    service: BasicDataService = Depends(_authorized("basic_data.read")),
):
    return service.items(
        project_id, page=page, page_size=page_size, category=category, validation_state=validation_state
    )


@router.post("/projects/{project_id}/items", status_code=201)
def create_item(
    project_id: int,
    payload: ItemCreateIn,
    response: Response,
    key: str = Depends(_key),
    service: BasicDataService = Depends(_authorized("basic_data.item.create")),
):
    return _etag(response, service.create_item(project_id, payload, key))


@router.get("/items/{item_id}")
def item(item_id: int, response: Response, service: BasicDataService = Depends(_authorized("basic_data.read"))):
    return _etag(response, service.item(item_id))


@router.put("/items/{item_id}")
def update_item(
    item_id: int,
    payload: ItemUpdateIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_key),
    service: BasicDataService = Depends(_authorized("basic_data.item.edit")),
):
    return _etag(response, service.update_item(item_id, expected, payload, key))


@router.post("/items/{item_id}/validate")
def validate_item(
    item_id: int,
    payload: ItemValidateIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_key),
    service: BasicDataService = Depends(_authorized("basic_data.item.validate")),
):
    return _etag(response, service.validate_item(item_id, expected, payload, key))


@router.get("/projects/{project_id}/assessments")
def assessments(
    project_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: BasicDataService = Depends(_authorized("basic_data.read")),
):
    return service.assessments(project_id, page=page, page_size=page_size)


@router.post("/projects/{project_id}/assessments", status_code=201)
def create_assessment(
    project_id: int,
    payload: AssessmentCreateIn,
    response: Response,
    key: str = Depends(_key),
    service: BasicDataService = Depends(_authorized("basic_data.assessment.create")),
):
    return _etag(response, service.create_assessment(project_id, payload, key))


@router.get("/assessments/{assessment_id}")
def assessment(
    assessment_id: int, response: Response, service: BasicDataService = Depends(_authorized("basic_data.read"))
):
    return _etag(response, service.assessment(assessment_id))


@router.post("/assessments/{assessment_id}/preview")
def preview(assessment_id: int, service: BasicDataService = Depends(_authorized("basic_data.read"))):
    return service.preview(assessment_id)


@router.post("/assessments/{assessment_id}/submit")
def submit(
    assessment_id: int,
    payload: AssessmentActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_key),
    service: BasicDataService = Depends(_authorized("basic_data.assessment.submit")),
):
    return _etag(response, service.submit(assessment_id, expected, payload, key))


@router.post("/assessments/{assessment_id}/complete")
def complete(
    assessment_id: int,
    payload: AssessmentActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_key),
    service: BasicDataService = Depends(_authorized("basic_data.assessment.complete")),
):
    return _etag(response, service.complete(assessment_id, expected, payload, key))


@router.get("/projects/{project_id}/current-readiness")
def current_readiness(project_id: int, service: BasicDataService = Depends(_authorized("basic_data.read"))):
    return service.current_readiness(project_id)


@router.get("/projects/{project_id}/fel-context")
def fel_context(project_id: int, service: BasicDataService = Depends(_authorized("basic_data.read"))):
    return service.requirements(project_id)["context"]


@router.get("/projects/{project_id}/provider-evidence")
def provider_evidence(project_id: int, service: BasicDataService = Depends(_authorized("basic_data.read"))):
    return service.provider_evidence(project_id)


@router.get("/assessments/{assessment_id}/refresh-preview")
def refresh_preview(assessment_id: int, service: BasicDataService = Depends(_authorized("basic_data.read"))):
    return service.refresh_preview(assessment_id)


@router.post("/assessments/{assessment_id}/refresh-apply", status_code=201)
def refresh_apply(
    assessment_id: int,
    payload: AssessmentActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_key),
    service: BasicDataService = Depends(_authorized("basic_data.assessment.create")),
):
    return _etag(response, service.refresh_apply(assessment_id, expected, payload, key))


@router.get("/admin/configurations")
def configurations(service: BasicDataService = Depends(_authorized("basic_data.admin.configure"))):
    return service.configurations()


@router.post("/admin/configurations/{configuration_id}/clone", status_code=201)
def clone(
    configuration_id: int,
    payload: ConfigurationCloneIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_key),
    service: BasicDataService = Depends(_authorized("basic_data.admin.configure")),
):
    return _etag(response, service.clone_configuration(configuration_id, expected, payload, key), config=True)


@router.put("/admin/configurations/{configuration_id}")
def update_configuration(
    configuration_id: int,
    payload: ConfigurationUpdateIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_key),
    service: BasicDataService = Depends(_authorized("basic_data.admin.configure")),
):
    return _etag(response, service.update_configuration(configuration_id, expected, payload, key), config=True)


@router.post("/admin/configurations/{configuration_id}/publish")
def publish(
    configuration_id: int,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_key),
    service: BasicDataService = Depends(_authorized("basic_data.admin.publish")),
):
    return _etag(response, service.publish_configuration(configuration_id, expected, key), config=True)


@router.post("/admin/configurations/{configuration_id}/archive")
def archive(
    configuration_id: int,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_key),
    service: BasicDataService = Depends(_authorized("basic_data.admin.publish")),
):
    return _etag(response, service.archive_configuration(configuration_id, expected, key), config=True)


@router.post("/admin/preview")
def config_preview(
    payload: ConfigurationPreviewIn, service: BasicDataService = Depends(_authorized("basic_data.admin.configure"))
):
    return service.configuration_preview(payload)
