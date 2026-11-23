"""Quality queries and guarded commands under the existing operational API."""

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.quality.schemas import (
    ControlDecisionIn,
    InspectionRecordIn,
    InspectionRequestIn,
    ITPIn,
    ITPItemIn,
    PlanIn,
    ProfileIn,
    ProfileUpdateIn,
    ReasonIn,
    RequestActionIn,
    ResultActionIn,
    TestRecordIn,
    TestRequestIn,
    VersionActionIn,
)
from app.modules.quality.service import COLLECTIONS, QualityService

router = APIRouter()
PROJECT = "/projects/{workspace_id}"


def authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant: int = Depends(get_tenant_id), actor: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(db, tenant, actor, f"quality.{action}", bootstrap=False)
        return QualityService(db, tenant, actor, access)

    return dependency


def out(response, value):
    if isinstance(value, dict) and "version" in value:
        _etag(response, value["version"])
    return value


@router.get(PROJECT + "/configuration")
def configuration(workspace_id: int, service=Depends(authorized("read"))):
    return service.configuration(workspace_id)


@router.get(PROJECT + "/source")
def source(
    workspace_id: int,
    source_type: str = Query(min_length=2, max_length=80),
    source_id: int = Query(gt=0),
    as_of: AwareDatetime | None = None,
    service=Depends(authorized("read")),
):
    service._read_project(workspace_id)
    return service.source_lookup(workspace_id, source_type, source_id, as_of=as_of)


@router.get(PROJECT + "/document-targets")
def documents(
    workspace_id: int,
    limit: int = Query(100, ge=1, le=200),
    after: int = Query(0, ge=0),
    service=Depends(authorized("read")),
):
    return service.document_targets(workspace_id, limit, after)


@router.get(PROJECT + "/reference-targets")
def references(
    workspace_id: int,
    target_kind: str = Query(min_length=2, max_length=80),
    limit: int = Query(100, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    service=Depends(authorized("read")),
):
    return service.reference_targets(workspace_id, target_kind, limit, after_id)


def queries(resource):
    def listing(
        workspace_id: int,
        response: Response,
        limit: int = Query(50, ge=1, le=200),
        after_id: int = Query(0, ge=0),
        itp_id: int | None = Query(None, gt=0),
        itp_item_id: int | None = Query(None, gt=0),
        subject_key: str | None = Query(None, max_length=240),
        status: str | None = Query(None, max_length=32),
        service=Depends(authorized("read")),
    ):
        return out(
            response,
            service.collection(
                workspace_id,
                resource,
                limit=limit,
                after_id=after_id,
                itp_id=itp_id,
                itp_item_id=itp_item_id,
                subject_key=subject_key,
                status=status,
            ),
        )

    def detail(workspace_id: int, identity: int, response: Response, service=Depends(authorized("read"))):
        return out(response, service.detail(workspace_id, resource, identity))

    router.add_api_route(PROJECT + f"/{resource}", listing, methods=["GET"], name=f"quality_list_{resource}")
    router.add_api_route(PROJECT + f"/{resource}/{{identity}}", detail, methods=["GET"], name=f"quality_get_{resource}")


for _resource in COLLECTIONS:
    queries(_resource)


def write_route(resource, dto, method, duty, *, update=False):
    def dispatch(service, workspace, payload, key, identity=None, expected=None):
        if method == "save_item":
            return service.save_item(workspace, payload, key, identity, expected)
        if method == "create_request":
            return service.create_request(workspace, resource, payload, key)
        return getattr(service, method)(workspace, resource, payload, key, identity, expected)

    if update:

        def command(
            workspace_id: int,
            identity: int,
            payload: dto,
            response: Response,
            key=Depends(_idempotency_key),
            expected=Depends(_if_match),
            service=Depends(authorized(duty)),
        ):
            return out(response, dispatch(service, workspace_id, payload, key, identity, expected))

        router.add_api_route(
            PROJECT + f"/{resource}/{{identity}}", command, methods=["PUT"], name=f"quality_update_{resource}"
        )
    else:

        def command(
            workspace_id: int,
            payload: dto,
            response: Response,
            key=Depends(_idempotency_key),
            service=Depends(authorized(duty)),
        ):
            return out(response, dispatch(service, workspace_id, payload, key))

        router.add_api_route(
            PROJECT + f"/{resource}", command, methods=["POST"], status_code=201, name=f"quality_create_{resource}"
        )


for _resource, _dto, _method, _duty, _editable in (
    ("plans", PlanIn, "save_version", "plan.edit", True),
    ("itps", ITPIn, "save_version", "itp.edit", True),
    ("itp-items", ITPItemIn, "save_item", "itp.edit", True),
    ("inspection-requests", InspectionRequestIn, "create_request", "inspection.request", False),
    ("test-requests", TestRequestIn, "create_request", "test.request", False),
    ("inspections", InspectionRecordIn, "save_result", "inspection.perform", True),
    ("tests", TestRecordIn, "save_result", "test.perform", True),
):
    write_route(_resource, _dto, _method, _duty)
    if _editable:
        write_route(_resource, _dto, _method, _duty, update=True)


def action_route(resource, dto, method):
    def command(
        workspace_id: int,
        identity: int,
        payload: dto,
        response: Response,
        key=Depends(_idempotency_key),
        expected=Depends(_if_match),
        service=Depends(authorized("read")),
    ):
        return out(response, getattr(service, method)(workspace_id, resource, identity, payload, expected, key))

    router.add_api_route(
        PROJECT + f"/{resource}/{{identity}}/actions", command, methods=["POST"], name=f"quality_action_{resource}"
    )


for _resource, _dto, _method in (
    ("plans", VersionActionIn, "version_action"),
    ("itps", VersionActionIn, "version_action"),
    ("inspection-requests", RequestActionIn, "request_action"),
    ("test-requests", RequestActionIn, "request_action"),
    ("inspections", ResultActionIn, "result_action"),
    ("tests", ResultActionIn, "result_action"),
):
    action_route(_resource, _dto, _method)


def successor_route(resource):
    def command(
        workspace_id: int,
        identity: int,
        payload: ReasonIn,
        response: Response,
        key=Depends(_idempotency_key),
        expected=Depends(_if_match),
        service=Depends(authorized("read")),
    ):
        return out(response, service.version_successor(workspace_id, resource, identity, payload, expected, key))

    router.add_api_route(
        PROJECT + f"/{resource}/{{identity}}/successor",
        command,
        methods=["POST"],
        status_code=201,
        name=f"quality_successor_{resource}",
    )


for _resource in ("plans", "itps"):
    successor_route(_resource)


def stream_expected(value: str = Header(..., alias="If-Match")):
    return 0 if value.strip() in {"0", '"0"'} else _if_match(value)


@router.post(PROJECT + "/control-point-decisions", status_code=201)
def control_decision(
    workspace_id: int,
    payload: ControlDecisionIn,
    response: Response,
    key=Depends(_idempotency_key),
    expected=Depends(stream_expected),
    service=Depends(authorized("control.release")),
):
    return out(response, service.control_decision(workspace_id, payload, expected, key))


@router.get("/admin/profiles")
def profiles(service=Depends(authorized("admin.configure"))):
    return service.profiles()


@router.post("/admin/profiles", status_code=201)
def create_profile(
    payload: ProfileIn,
    response: Response,
    key=Depends(_idempotency_key),
    service=Depends(authorized("admin.configure")),
):
    return out(response, service.create_profile(payload, key))


@router.put("/admin/profiles/{identity}")
def update_profile(
    identity: int,
    payload: ProfileUpdateIn,
    response: Response,
    key=Depends(_idempotency_key),
    expected=Depends(_if_match),
    service=Depends(authorized("admin.configure")),
):
    return out(response, service.update_profile(identity, payload, expected, key))


@router.post("/admin/profiles/{identity}/publish")
def publish_profile(
    identity: int,
    payload: ReasonIn,
    response: Response,
    key=Depends(_idempotency_key),
    expected=Depends(_if_match),
    service=Depends(authorized("admin.publish")),
):
    return out(response, service.publish_profile(identity, payload, expected, key))


@router.post("/admin/profiles/{identity}/successor", status_code=201)
def successor_profile(
    identity: int,
    payload: ReasonIn,
    response: Response,
    key=Depends(_idempotency_key),
    expected=Depends(_if_match),
    service=Depends(authorized("admin.configure")),
):
    return out(response, service.successor_profile(identity, payload, expected, key))
