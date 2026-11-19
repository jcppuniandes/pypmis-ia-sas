"""Field Operations commands and queries under the existing project shell."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.field_operations.schemas import (
    ConditionIn,
    CrewActionIn,
    CrewIn,
    DailyReportActionIn,
    DailyReportIn,
    EquipmentReferenceActionIn,
    EquipmentReferenceIn,
    EquipmentUsageIn,
    LaborIn,
    ProfileIn,
    ProfileUpdateIn,
    ReasonIn,
    ShiftActionIn,
    ShiftIn,
    WorkfrontActionIn,
    WorkfrontIn,
)
from app.modules.field_operations.service import COLLECTIONS, FieldOperationsService
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match

router = APIRouter()
PROJECT = "/projects/{workspace_id}"


def authorized(action, service_class=FieldOperationsService):
    def dependency(
        db: Session = Depends(get_db),
        tenant: int = Depends(get_tenant_id),
        actor: int = Depends(get_user_id),
    ):
        access = require_enterprise_permission(db, tenant, actor, f"field_operations.{action}", bootstrap=False)
        return service_class(db, tenant, actor, access)

    return dependency


def out(response, value):
    if isinstance(value, dict) and "version" in value:
        _etag(response, value["version"])
    return value


@router.get(PROJECT + "/configuration")
def configuration(workspace_id: int, service=Depends(authorized("read"))):
    return service.configuration(workspace_id)


@router.get(PROJECT + "/document-targets")
def document_targets(
    workspace_id: int,
    limit: int = Query(100, ge=1, le=200),
    after: int = Query(0, ge=0),
    service=Depends(authorized("read")),
):
    return service.document_targets(workspace_id, limit, after)


@router.get(PROJECT + "/reference-targets")
def reference_targets(
    workspace_id: int,
    target_kind: str = Query(min_length=1, max_length=80),
    limit: int = Query(100, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    service=Depends(authorized("read")),
):
    return service.reference_targets(workspace_id, target_kind, limit, after_id)


@router.get(PROJECT + "/source")
def source(
    workspace_id: int,
    source_type: str = Query(min_length=1, max_length=80),
    source_id: int = Query(gt=0),
    service=Depends(authorized("read")),
):
    service._read_project(workspace_id)
    return service.source_pin(workspace_id, source_type, source_id)


def _queries(resource):
    def collection(
        workspace_id: int,
        limit: int = Query(50, ge=1, le=200),
        after_id: int = Query(0, ge=0),
        shift_id: int | None = Query(None, gt=0),
        workfront_id: int | None = Query(None, gt=0),
        service=Depends(authorized("read")),
    ):
        return service.collection(
            workspace_id, resource, limit=limit, after_id=after_id, shift_id=shift_id, workfront_id=workfront_id
        )

    def detail(workspace_id: int, identity: int, response: Response, service=Depends(authorized("read"))):
        return out(response, service.detail(workspace_id, resource, identity))

    router.add_api_route(PROJECT + f"/{resource}", collection, methods=["GET"], name=f"field_list_{resource}")
    router.add_api_route(PROJECT + f"/{resource}/{{identity}}", detail, methods=["GET"], name=f"field_get_{resource}")


for _resource in COLLECTIONS:
    _queries(_resource)


def _create(resource, dto, method, duty):
    def command(
        workspace_id: int,
        payload: dto,
        response: Response,
        key=Depends(_idempotency_key),
        service=Depends(authorized(duty)),
    ):
        return out(response, getattr(service, method)(workspace_id, payload, key))

    router.add_api_route(
        PROJECT + f"/{resource}", command, methods=["POST"], status_code=201, name=f"field_create_{resource}"
    )


for _resource, _dto, _method, _duty in (
    ("workfronts", WorkfrontIn, "save_workfront", "workfront.edit"),
    ("shifts", ShiftIn, "save_shift", "shift.edit"),
    ("daily-reports", DailyReportIn, "save_report", "daily.prepare"),
    ("crews", CrewIn, "save_crew", "crew.edit"),
    ("equipment-references", EquipmentReferenceIn, "create_equipment_reference", "equipment.edit"),
    ("labor", LaborIn, "create_labor", "labor.record"),
    ("equipment", EquipmentUsageIn, "create_equipment_usage", "equipment.record"),
    ("conditions", ConditionIn, "create_condition", "condition.record"),
):
    _create(_resource, _dto, _method, _duty)


def _update(resource, dto, method, duty):
    def command(
        workspace_id: int,
        identity: int,
        payload: dto,
        response: Response,
        key=Depends(_idempotency_key),
        expected=Depends(_if_match),
        service=Depends(authorized(duty)),
    ):
        return out(response, getattr(service, method)(workspace_id, payload, key, identity, expected))

    router.add_api_route(
        PROJECT + f"/{resource}/{{identity}}", command, methods=["PUT"], name=f"field_update_{resource}"
    )


for _resource, _dto, _method, _duty in (
    ("workfronts", WorkfrontIn, "save_workfront", "workfront.edit"),
    ("shifts", ShiftIn, "save_shift", "shift.edit"),
    ("daily-reports", DailyReportIn, "save_report", "daily.prepare"),
    ("crews", CrewIn, "save_crew", "crew.edit"),
):
    _update(_resource, _dto, _method, _duty)


def _action(resource, dto, method):
    def command(
        workspace_id: int,
        identity: int,
        payload: dto,
        response: Response,
        key=Depends(_idempotency_key),
        expected=Depends(_if_match),
        service=Depends(authorized("read")),
    ):
        return out(response, getattr(service, method)(workspace_id, identity, payload, expected, key))

    router.add_api_route(
        PROJECT + f"/{resource}/{{identity}}/actions", command, methods=["POST"], name=f"field_action_{resource}"
    )


for _resource, _dto, _method in (
    ("workfronts", WorkfrontActionIn, "workfront_action"),
    ("shifts", ShiftActionIn, "shift_action"),
    ("daily-reports", DailyReportActionIn, "report_action"),
    ("crews", CrewActionIn, "crew_action"),
    ("equipment-references", EquipmentReferenceActionIn, "equipment_reference_action"),
):
    _action(_resource, _dto, _method)


@router.post(PROJECT + "/daily-reports/{identity}/successor", status_code=201)
def report_successor(
    workspace_id: int,
    identity: int,
    payload: ReasonIn,
    response: Response,
    key=Depends(_idempotency_key),
    expected=Depends(_if_match),
    service=Depends(authorized("daily.prepare")),
):
    return out(response, service.report_successor(workspace_id, identity, payload, expected, key))


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
