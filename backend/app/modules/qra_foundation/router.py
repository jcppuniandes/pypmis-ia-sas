"""USER source/model lifecycle and separate ADMIN methodology APIs. No execution route."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.qra_foundation.schemas import (
    ActionIn,
    ConfigurationCloneIn,
    ConfigurationPreviewIn,
    ConfigurationUpdateIn,
    ModelCreateIn,
    ModelUpdateIn,
    SourceCreateIn,
    SourceUpdateIn,
)
from app.modules.qra_foundation.service import QraFoundationService

router = APIRouter()


def _authorized(permission):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), user_id: int = Depends(get_user_id)
    ):
        context = require_enterprise_permission(db, tenant_id, user_id, permission, bootstrap=False)
        return QraFoundationService(db, tenant_id, user_id, context)

    return dependency


def _out(response, result, config=False):
    _etag(response, result["version" if config else "revision_version"])
    return result


@router.get("/options")
def options(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    search: str | None = Query(None, max_length=180),
    service=Depends(_authorized("qra_foundation.read")),
):
    return service.options(page=page, page_size=page_size, search=search)


@router.get("/projects/{project_id}/requirements")
def requirements(project_id: int, service=Depends(_authorized("qra_foundation.read"))):
    return service.requirements(project_id)


@router.get("/projects/{project_id}/contexts")
def contexts(project_id: int, service=Depends(_authorized("qra_foundation.read"))):
    return service.contexts(project_id)


def _source_routes(kind):
    path = f"/{kind}-assessments"
    permission = f"qra_{kind}_source"

    def source_options(
        project_id: int,
        page: int = Query(1, ge=1),
        page_size: int = Query(100, ge=1, le=200),
        service=Depends(_authorized("qra_foundation.read")),
    ):
        return service.source_options(project_id, kind, page=page, page_size=page_size)

    def history(
        project_id: int,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        service=Depends(_authorized("qra_foundation.read")),
    ):
        return service.records(project_id, kind, page=page, page_size=page_size)

    def create(
        project_id: int,
        payload: SourceCreateIn,
        response: Response,
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized(f"{permission}.create")),
    ):
        return _out(response, service.create(project_id, kind, payload, key))

    def get(
        record_id: int, response: Response, summary: bool = False, service=Depends(_authorized("qra_foundation.read"))
    ):
        return _out(response, service.record(kind, record_id, summary=summary))

    def record_items(
        record_id: int,
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=200),
        service=Depends(_authorized("qra_foundation.read")),
    ):
        return service.record_items(kind, record_id, page=page, page_size=page_size)

    def update(
        record_id: int,
        payload: SourceUpdateIn,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized(f"{permission}.edit")),
    ):
        return _out(response, service.update(kind, record_id, expected, payload, key))

    def preview(record_id: int, service=Depends(_authorized("qra_foundation.read"))):
        return service.preview(kind, record_id)

    def current(project_id: int, summary: bool = False, service=Depends(_authorized("qra_foundation.read"))):
        return service.current_readiness(project_id, kind, summary=summary)

    def provider(project_id: int, service=Depends(_authorized("qra_foundation.read"))):
        return service.provider_evidence(project_id, kind)

    def refresh_preview(record_id: int, service=Depends(_authorized("qra_foundation.read"))):
        return service.refresh_preview(kind, record_id)

    def refresh_apply(
        record_id: int,
        payload: ActionIn,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized(f"{permission}.create")),
    ):
        return _out(response, service.refresh_apply(kind, record_id, expected, payload, key))

    router.add_api_route(
        f"/projects/{{project_id}}/{kind}-source-options", source_options, methods=["GET"], name=f"qra_{kind}_options"
    )
    router.add_api_route(f"/projects/{{project_id}}{path}", history, methods=["GET"], name=f"qra_{kind}_history")
    router.add_api_route(
        f"/projects/{{project_id}}{path}", create, methods=["POST"], status_code=201, name=f"qra_{kind}_create"
    )
    router.add_api_route(f"{path}/{{record_id}}", get, methods=["GET"], name=f"qra_{kind}_get")
    router.add_api_route(f"{path}/{{record_id}}/items", record_items, methods=["GET"], name=f"qra_{kind}_items")
    router.add_api_route(f"{path}/{{record_id}}", update, methods=["PUT"], name=f"qra_{kind}_update")
    router.add_api_route(f"{path}/{{record_id}}/preview", preview, methods=["POST"], name=f"qra_{kind}_preview")
    router.add_api_route(
        f"/projects/{{project_id}}/{kind}-readiness", current, methods=["GET"], name=f"qra_{kind}_readiness"
    )
    router.add_api_route(
        f"/projects/{{project_id}}/{kind}-provider-evidence", provider, methods=["GET"], name=f"qra_{kind}_provider"
    )
    router.add_api_route(
        f"{path}/{{record_id}}/refresh-preview",
        refresh_preview,
        methods=["GET", "POST"],
        name=f"qra_{kind}_refresh_preview",
    )
    router.add_api_route(
        f"{path}/{{record_id}}/refresh-apply",
        refresh_apply,
        methods=["POST"],
        status_code=201,
        name=f"qra_{kind}_refresh_apply",
    )

    def action_endpoint(action, action_permission):
        def endpoint(
            record_id: int,
            payload: ActionIn,
            response: Response,
            expected: int = Depends(_if_match),
            key: str = Depends(_idempotency_key),
            service=Depends(_authorized(action_permission)),
        ):
            return _out(response, service.action(kind, record_id, expected, payload, key, action))

        router.add_api_route(f"{path}/{{record_id}}/{action}", endpoint, methods=["POST"], name=f"qra_{kind}_{action}")

    for action in ("submit", "review", "complete"):
        action_endpoint(action, f"{permission}.{'submit' if action == 'submit' else 'review'}")


for _kind in ("cost", "schedule"):
    _source_routes(_kind)


@router.get("/projects/{project_id}/models")
def models(
    project_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service=Depends(_authorized("qra_foundation.read")),
):
    return service.records(project_id, "model", page=page, page_size=page_size)


@router.post("/projects/{project_id}/models", status_code=201)
def create_model(
    project_id: int,
    payload: ModelCreateIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("qra_model.create")),
):
    return _out(response, service.create(project_id, "model", payload, key))


@router.get("/models/{record_id}")
def model(
    record_id: int, response: Response, summary: bool = False, service=Depends(_authorized("qra_foundation.read"))
):
    return _out(response, service.record("model", record_id, summary=summary))


@router.get("/models/{record_id}/items")
def model_items(
    record_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    service=Depends(_authorized("qra_foundation.read")),
):
    return service.record_items("model", record_id, page=page, page_size=page_size)


@router.put("/models/{record_id}")
def update_model(
    record_id: int,
    payload: ModelUpdateIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("qra_model.edit")),
):
    return _out(response, service.update("model", record_id, expected, payload, key))


@router.post("/models/{record_id}/preview")
def preview_model(record_id: int, service=Depends(_authorized("qra_foundation.read"))):
    return service.preview("model", record_id)


def _model_action(action):
    def endpoint(
        record_id: int,
        payload: ActionIn,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized(f"qra_model.{action}")),
    ):
        return _out(response, service.action("model", record_id, expected, payload, key, action))

    router.add_api_route(f"/models/{{record_id}}/{action}", endpoint, methods=["POST"], name=f"qra_model_{action}")


for _action in ("submit", "review", "approve"):
    _model_action(_action)


@router.get("/projects/{project_id}/model-readiness")
@router.get("/projects/{project_id}/current-model")
def model_readiness(project_id: int, summary: bool = False, service=Depends(_authorized("qra_foundation.read"))):
    return service.current_readiness(project_id, "model", summary=summary)


@router.get("/models/{record_id}/refresh-preview")
@router.post("/models/{record_id}/refresh-preview")
def model_refresh_preview(record_id: int, service=Depends(_authorized("qra_foundation.read"))):
    return service.refresh_preview("model", record_id)


@router.post("/models/{record_id}/refresh-apply", status_code=201)
def model_refresh_apply(
    record_id: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("qra_model.create")),
):
    return _out(response, service.refresh_apply("model", record_id, expected, payload, key))


@router.get("/admin/configurations")
def configurations(service=Depends(_authorized("qra_methodology.admin.configure"))):
    return service.configurations()


@router.get("/admin/configurations/{configuration_id}")
def configuration(
    configuration_id: int, response: Response, service=Depends(_authorized("qra_methodology.admin.configure"))
):
    return _out(response, service.configuration(configuration_id), config=True)


@router.get("/admin/configurations/{configuration_id}/history")
def configuration_history(configuration_id: int, service=Depends(_authorized("qra_methodology.admin.configure"))):
    return service.configuration_history(configuration_id)


@router.put("/admin/configurations/{configuration_id}")
def update_configuration(
    configuration_id: int,
    payload: ConfigurationUpdateIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("qra_methodology.admin.configure")),
):
    return _out(response, service.update_configuration(configuration_id, expected, payload, key), config=True)


@router.post("/admin/configurations/{configuration_id}/clone", status_code=201)
def clone_configuration(
    configuration_id: int,
    payload: ConfigurationCloneIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("qra_methodology.admin.configure")),
):
    return _out(response, service.clone_configuration(configuration_id, expected, payload, key), config=True)


@router.post("/admin/configurations/{configuration_id}/publish")
def publish_configuration(
    configuration_id: int,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("qra_methodology.admin.publish")),
):
    return _out(response, service.publish_configuration(configuration_id, expected, key), config=True)


@router.post("/admin/configurations/{configuration_id}/archive")
def archive_configuration(
    configuration_id: int,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("qra_methodology.admin.publish")),
):
    return _out(response, service.archive_configuration(configuration_id, expected, key), config=True)


@router.post("/admin/preview")
@router.post("/admin/effective-preview")
def config_preview(payload: ConfigurationPreviewIn, service=Depends(_authorized("qra_methodology.admin.configure"))):
    return service.configuration_preview(payload)
