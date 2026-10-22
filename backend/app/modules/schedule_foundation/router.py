"""Schedule API addressed only by canonical Project Workspace identity."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.schedule_foundation.models import ScheduleBaseline, ScheduleRegister, ScheduleVersion
from app.modules.schedule_foundation.schemas import (
    ActionIn,
    BaselineIn,
    ExportIn,
    MappingIn,
    PeriodAssociationIn,
    ProfileIn,
    ProfileUpdateIn,
    RegisterIn,
    VersionIn,
)
from app.modules.schedule_foundation.service import ScheduleFoundationService

router = APIRouter()


def _authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), actor_id: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(
            db, tenant_id, actor_id, f"schedule_foundation.{action}", bootstrap=False
        )
        return ScheduleFoundationService(db, tenant_id, actor_id, access)

    return dependency


def _out(response, result):
    _etag(response, result.get("version", 1))
    return result


@router.get("/projects/{workspace_id}/overview")
def overview(workspace_id: int, service=Depends(_authorized("read"))):
    return service.overview(workspace_id)


@router.get("/projects/{workspace_id}/registers/{register_id}")
def register_detail(workspace_id: int, register_id: int, service=Depends(_authorized("read"))):
    service._permission("read", service._project(workspace_id))
    return service._out(service._get(ScheduleRegister, workspace_id, register_id))


@router.get("/projects/{workspace_id}/versions/{version_id}")
def version_detail(workspace_id: int, version_id: int, service=Depends(_authorized("read"))):
    service._permission("read", service._project(workspace_id))
    return service._version_out(service._get(ScheduleVersion, workspace_id, version_id))


@router.get("/projects/{workspace_id}/baselines/{baseline_id}")
def baseline_detail(workspace_id: int, baseline_id: int, service=Depends(_authorized("read"))):
    service._permission("read", service._project(workspace_id))
    return service._out(service._get(ScheduleBaseline, workspace_id, baseline_id))


def _listing(field):
    def query(workspace_id: int, service=Depends(_authorized("read"))):
        items = service.overview(workspace_id)[field]
        return {"items": items, "total": len(items)}

    query.__name__ = f"list_schedule_{field}"
    return query


for _field in ("registers", "versions", "baselines", "mappings", "exports", "period_associations"):
    router.add_api_route(f"/projects/{{workspace_id}}/{_field.replace('_', '-')}", _listing(_field), methods=["GET"])


@router.post("/projects/{workspace_id}/registers", status_code=201)
def create_register(
    workspace_id: int,
    payload: RegisterIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("register.edit")),
):
    return _out(response, service.create_register(workspace_id, payload, key))


@router.post("/projects/{workspace_id}/registers/{register_id}/imports", status_code=201)
async def import_version(
    workspace_id: int,
    register_id: int,
    response: Response,
    file: UploadFile = File(...),
    reason: str = Form(...),
    kind: str = Form("UPDATE"),
    predecessor_version_id: int | None = Form(None),
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("import")),
):
    return _out(
        response,
        service.stage_import(
            workspace_id,
            register_id,
            await file.read(40 * 1024 * 1024 + 1),
            file.filename or "schedule.xml",
            reason,
            kind,
            predecessor_version_id,
            expected,
            key,
        ),
    )


@router.post("/projects/{workspace_id}/registers/{register_id}/versions", status_code=201)
def create_version(
    workspace_id: int,
    register_id: int,
    payload: VersionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("version.edit")),
):
    return _out(response, service.create_version(workspace_id, register_id, payload, expected, key))


def _transition(action):
    def command(
        workspace_id: int,
        version_id: int,
        payload: ActionIn,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized("review" if action == "reject" else action)),
    ):
        return _out(response, service.transition_version(workspace_id, version_id, action, payload, expected, key))

    command.__name__ = f"schedule_version_{action}"
    return command


for _action in ("validate", "review", "accept", "reject"):
    router.add_api_route(
        f"/projects/{{workspace_id}}/versions/{{version_id}}/{_action}", _transition(_action), methods=["POST"]
    )


@router.post("/projects/{workspace_id}/versions/{version_id}/mappings", status_code=201)
def set_mapping(
    workspace_id: int,
    version_id: int,
    payload: MappingIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("mapping.edit")),
):
    return _out(response, service.set_mapping(workspace_id, version_id, payload, expected, key))


@router.post("/projects/{workspace_id}/versions/{version_id}/baselines", status_code=201)
def prepare_baseline(
    workspace_id: int,
    version_id: int,
    payload: BaselineIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("baseline.prepare")),
):
    return _out(response, service.prepare_baseline(workspace_id, version_id, payload, expected, key))


def _baseline_transition(action):
    def command(
        workspace_id: int,
        baseline_id: int,
        payload: ActionIn,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized("baseline." + action)),
    ):
        return _out(response, service.transition_baseline(workspace_id, baseline_id, action, payload, expected, key))

    command.__name__ = f"schedule_baseline_{action}"
    return command


for _action in ("submit", "review", "approve"):
    router.add_api_route(
        f"/projects/{{workspace_id}}/baselines/{{baseline_id}}/{_action}",
        _baseline_transition(_action),
        methods=["POST"],
    )


@router.post("/projects/{workspace_id}/versions/{version_id}/exports", status_code=201)
def export_version(
    workspace_id: int,
    version_id: int,
    payload: ExportIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("export")),
):
    return _out(response, service.export_version(workspace_id, version_id, payload, expected, key))


@router.get("/projects/{workspace_id}/exports/{export_id}/download")
def export_download(workspace_id: int, export_id: int, service=Depends(_authorized("read"))):
    row = service.export_file(workspace_id, export_id)
    return Response(
        content=row.source_content,
        media_type="application/xml",
        headers={
            "ETag": f'"{row.source_hash}"',
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.source_file_name)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/projects/{workspace_id}/versions/{version_id}/period-associations", status_code=201)
def associate_period(
    workspace_id: int,
    version_id: int,
    payload: PeriodAssociationIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("period.associate")),
):
    return _out(response, service.associate_period(workspace_id, version_id, payload, expected, key))


def _version_listing(field):
    def query(workspace_id: int, version_id: int, service=Depends(_authorized("read"))):
        return service.version_query(workspace_id, version_id, field)

    query.__name__ = f"schedule_version_{field}"
    return query


for _field in (
    "wbs",
    "activities",
    "calendars",
    "relationships",
    "constraints",
    "codes",
    "code_assignments",
    "external_links",
    "mappings",
    "health",
):
    router.add_api_route(
        f"/projects/{{workspace_id}}/versions/{{version_id}}/{_field.replace('_', '-')}",
        _version_listing(_field),
        methods=["GET"],
    )


@router.get("/projects/{workspace_id}/versions/{version_id}/look-ahead")
def look_ahead(
    workspace_id: int,
    version_id: int,
    horizon_days: int | None = Query(None, ge=1, le=366),
    service=Depends(_authorized("read")),
):
    return service.look_ahead(workspace_id, version_id, horizon_days)


@router.get("/admin/profiles")
def profiles(service=Depends(_authorized("admin.configure"))):
    return service.profiles()


@router.post("/admin/profiles", status_code=201)
def create_profile(
    payload: ProfileIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.configure")),
):
    return _out(response, service.create_profile(payload, key))


@router.put("/admin/profiles/{identity}")
def update_profile(
    identity: int,
    payload: ProfileUpdateIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.configure")),
):
    return _out(response, service.update_profile(identity, payload, expected, key))


def _profile_transition(action):
    def command(
        identity: int,
        payload: ActionIn,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized("admin.publish" if action == "publish" else "admin.configure")),
    ):
        return _out(response, getattr(service, action + "_profile")(identity, payload, expected, key))

    command.__name__ = f"schedule_profile_{action}"
    return command


for _action in ("publish", "successor"):
    router.add_api_route(f"/admin/profiles/{{identity}}/{_action}", _profile_transition(_action), methods=["POST"])
