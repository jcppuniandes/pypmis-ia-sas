"""Dedicated Forecast API; all writes are scoped, versioned and idempotent."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.forecast_foundation.schemas import (
    ForecastIn,
    ForecastTransitionIn,
    ProfileIn,
    ProfileUpdateIn,
    ReasonIn,
)
from app.modules.forecast_foundation.service import ForecastFoundationService
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match

router = APIRouter()


def _authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), actor_id: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(db, tenant_id, actor_id, f"forecast.{action}", bootstrap=False)
        return ForecastFoundationService(db, tenant_id, actor_id, access)

    return dependency


def _out(response, result):
    _etag(response, result.get("version", 1))
    return result


@router.get("/projects/{workspace_id}/overview")
def overview(workspace_id: int, service=Depends(_authorized("read"))):
    return service.overview(workspace_id)


@router.get("/projects/{workspace_id}/versions")
def versions(workspace_id: int, service=Depends(_authorized("read"))):
    return service.versions(workspace_id)


@router.get("/projects/{workspace_id}/versions/{identity}")
def version(workspace_id: int, identity: int, response: Response, service=Depends(_authorized("read"))):
    return _out(response, service.version(workspace_id, identity))


@router.post("/projects/{workspace_id}/versions", status_code=201)
def create_version(
    workspace_id: int,
    payload: ForecastIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("create")),
):
    return _out(response, service.save_version(workspace_id, payload, key))


@router.put("/projects/{workspace_id}/versions/{identity}")
def update_version(
    workspace_id: int,
    identity: int,
    payload: ForecastIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("edit")),
):
    return _out(response, service.save_version(workspace_id, payload, key, identity, expected))


@router.post("/projects/{workspace_id}/versions/{identity}/successor", status_code=201)
def successor(
    workspace_id: int,
    identity: int,
    payload: ForecastIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("create")),
):
    return _out(response, service.save_version(workspace_id, payload, key, identity, expected, successor=True))


@router.get("/projects/{workspace_id}/versions/{identity}/calculation")
def calculation(workspace_id: int, identity: int, service=Depends(_authorized("eac.view"))):
    return service.calculation_result(workspace_id, identity)


@router.post("/projects/{workspace_id}/versions/{identity}/calculate")
def calculate(
    workspace_id: int,
    identity: int,
    payload: ReasonIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("etc.calculate")),
):
    return _out(response, service.calculate_version(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/versions/{identity}/transition")
def transition(
    workspace_id: int,
    identity: int,
    payload: ForecastTransitionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("read")),
):
    return _out(response, service.transition_version(workspace_id, identity, payload, expected, key))


@router.get("/projects/{workspace_id}/history")
def history(workspace_id: int, service=Depends(_authorized("read"))):
    return service.history(workspace_id)


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


@router.post("/admin/profiles/{identity}/publish")
def publish_profile(
    identity: int,
    payload: ReasonIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.publish")),
):
    return _out(response, service.publish_profile(identity, payload, expected, key))


@router.post("/admin/profiles/{identity}/successor", status_code=201)
def successor_profile(
    identity: int,
    payload: ReasonIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.configure")),
):
    return _out(response, service.successor_profile(identity, payload, expected, key))
