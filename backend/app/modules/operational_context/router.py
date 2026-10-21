"""Permission-scoped canonical Project operational context and commands."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.operational_context.schemas import ActionIn, BindingIn, PeriodOpenIn, ProfileCreateIn, ProfileUpdateIn
from app.modules.operational_context.service import OperationalContextService
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match

router = APIRouter()


def _binding_match(value: str = Header(..., alias="If-Match")) -> int:
    normalized = value.strip().removeprefix("W/").strip('"')
    if not normalized.isdigit():
        raise HTTPException(400, detail={"code": "INVALID_IF_MATCH"})
    return int(normalized)


def _authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), actor_id: int = Depends(get_user_id)
    ):
        context = require_enterprise_permission(
            db, tenant_id, actor_id, f"operational_context.{action}", bootstrap=False
        )
        return OperationalContextService(db, tenant_id, actor_id, context)

    return dependency


def _out(response, result):
    _etag(response, result["version"])
    return result


@router.get("/options")
def options(service=Depends(_authorized("read"))):
    return service.options()


@router.get("/projects/{workspace_id}/context")
def context(workspace_id: int, service=Depends(_authorized("read"))):
    return service.context(workspace_id)


@router.get("/projects/{workspace_id}/binding")
def binding(workspace_id: int, response: Response, service=Depends(_authorized("read"))):
    return _out(response, service.binding(workspace_id))


@router.get("/projects/{workspace_id}/authorization")
def authorization(workspace_id: int, service=Depends(_authorized("read"))):
    return service.authorization(workspace_id)


@router.post("/projects/{workspace_id}/binding", status_code=201)
def create_binding(
    workspace_id: int,
    payload: BindingIn,
    response: Response,
    expected: int = Depends(_binding_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("binding.manage")),
):
    return _out(response, service.create_binding(workspace_id, payload, expected, key))


@router.post("/projects/{workspace_id}/binding/reconcile", status_code=201)
def reconcile_binding(
    workspace_id: int,
    payload: BindingIn,
    response: Response,
    expected: int = Depends(_binding_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("binding.manage")),
):
    return _out(response, service.create_binding(workspace_id, payload, expected, key, reconcile=True))


@router.get("/projects/{workspace_id}/periods")
def periods(workspace_id: int, service=Depends(_authorized("read"))):
    return service.periods(workspace_id)


@router.post("/projects/{workspace_id}/binding/revoke")
def revoke_binding(
    workspace_id: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("binding.manage")),
):
    return _out(response, service.revoke_binding(workspace_id, payload, expected, key))


@router.post("/projects/{workspace_id}/periods", status_code=201)
def open_period(
    workspace_id: int,
    payload: PeriodOpenIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("period.open")),
):
    return _out(response, service.open_period(workspace_id, payload, key))


def _transition(action):
    def command(
        workspace_id: int,
        period_id: int,
        payload: ActionIn,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized(f"period.{action}")),
    ):
        return _out(response, service.transition_period(workspace_id, period_id, action, payload, expected, key))

    command.__name__ = f"{action}_period"
    return command


for _action in ("review", "close", "publish", "reopen"):
    router.add_api_route(
        f"/projects/{{workspace_id}}/periods/{{period_id}}/{_action}", _transition(_action), methods=["POST"]
    )


@router.get("/admin/profiles")
def profiles(service=Depends(_authorized("admin.configure"))):
    return service.profiles()


@router.post("/admin/profiles", status_code=201)
def create_profile(
    payload: ProfileCreateIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.configure")),
):
    return _out(response, service.create_profile(payload, key))


@router.put("/admin/profiles/{profile_id}")
def update_profile(
    profile_id: int,
    payload: ProfileUpdateIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.configure")),
):
    return _out(response, service.update_profile(profile_id, payload, expected, key))


@router.post("/admin/profiles/{profile_id}/publish")
def publish_profile(
    profile_id: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.publish")),
):
    return _out(response, service.publish_profile(profile_id, payload, expected, key))


@router.post("/admin/profiles/{profile_id}/successor", status_code=201)
def successor_profile(
    profile_id: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.configure")),
):
    return _out(response, service.successor_profile(profile_id, payload, expected, key))
