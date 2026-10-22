"""Granular 4D read and configuration routes. Scrubbing emits no business event."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.schedule_four_d.service import FourDService
from app.modules.scope_foundation.schemas import ActionIn, ProfileIn, ProfileUpdateIn

router = APIRouter()


def _authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), actor_id: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(db, tenant_id, actor_id, f"four_d.{action}", bootstrap=False)
        return FourDService(db, tenant_id, actor_id, access)

    return dependency


def _options(
    source: str = Query("CURRENT", pattern="^(CURRENT|BASELINE)$"),
    version_id: int | None = Query(None, gt=0),
    baseline_id: int | None = Query(None, gt=0),
    at: str | None = None,
    wbs: str | None = None,
    activity: str | None = None,
    scope_item_id: int | None = Query(None, gt=0),
    scope_nature: str | None = Query(None, pattern="^(INSTALL|REMOVE|TEMPORARY|MAINTENANCE)$"),
    plan_item_id: int | None = Query(None, gt=0),
    cwa_id: int | None = Query(None, gt=0),
    package_type: str | None = None,
    work_package_id: int | None = Query(None, gt=0),
    area: str | None = None,
    zone: str | None = None,
    system: str | None = None,
    activity_status: str | None = None,
    critical: bool | None = None,
    near_critical: bool | None = None,
    execution_readiness: str | None = None,
    blocked: bool | None = None,
):
    values = locals()
    return {
        "source": source,
        "version_id": version_id,
        "baseline_id": baseline_id,
        "at": at,
        "filters": {
            key: value
            for key, value in values.items()
            if key not in {"source", "version_id", "baseline_id", "at"} and value is not None
        },
    }


@router.get("/projects/{workspace_id}/4d")
def model(workspace_id: int, options=Depends(_options), service=Depends(_authorized("read"))):
    return service.model(workspace_id, **options)


@router.get("/projects/{workspace_id}/4d/traceability/{identity}")
def traceability(workspace_id: int, identity: int, options=Depends(_options), service=Depends(_authorized("read"))):
    return service.traceability(workspace_id, identity, **options)


@router.get("/projects/{workspace_id}/4d/compare")
def compare(
    workspace_id: int,
    options=Depends(_options),
    service=Depends(_authorized("read")),
):
    if options["baseline_id"] is None:
        service._error(422, "FOUR_D_EXPLICIT_BASELINE_REQUIRED")
    return service.compare(
        workspace_id, options["baseline_id"], options["version_id"], options["at"], options["filters"]
    )


def _out(response, result):
    _etag(response, result.get("version", 1))
    return result


@router.get("/4d/admin/profiles")
def profiles(service=Depends(_authorized("admin.configure"))):
    return service.profiles()


@router.post("/4d/admin/profiles", status_code=201)
def create_profile(
    payload: ProfileIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.configure")),
):
    return _out(response, service.create_profile(payload, key))


@router.put("/4d/admin/profiles/{identity}")
def update_profile(
    identity: int,
    payload: ProfileUpdateIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.configure")),
):
    return _out(response, service.update_profile(identity, payload, expected, key))


def _transition(action):
    def command(
        identity: int,
        payload: ActionIn,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized("admin.publish" if action == "publish" else "admin.configure")),
    ):
        return _out(response, getattr(service, action + "_profile")(identity, payload, expected, key))

    command.__name__ = f"four_d_profile_{action}"
    return command


for _action in ("publish", "successor"):
    router.add_api_route(f"/4d/admin/profiles/{{identity}}/{_action}", _transition(_action), methods=["POST"])
