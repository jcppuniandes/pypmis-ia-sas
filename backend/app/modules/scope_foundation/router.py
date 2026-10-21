"""Canonical Workspace-scoped Scope API, never addressed by legacy Project ID."""

import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.scope_foundation.schemas import (
    ActionIn,
    DerivedIn,
    ItemIn,
    PlanIn,
    ProfileIn,
    ProfileUpdateIn,
    RevisionIn,
    SegmentIn,
    StrategyIn,
    TransformIn,
)
from app.modules.scope_foundation.service import ScopeFoundationService

router = APIRouter()


def _authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), actor_id: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(db, tenant_id, actor_id, f"scope_foundation.{action}", bootstrap=False)
        return ScopeFoundationService(db, tenant_id, actor_id, access)

    return dependency


def _out(response, result):
    _etag(response, result.get("version", 1))
    return result


@router.get("/projects/{workspace_id}/overview")
def overview(workspace_id: int, service=Depends(_authorized("read"))):
    return service.overview(workspace_id)


def _listing(field):
    def query(workspace_id: int, service=Depends(_authorized("read"))):
        items = service.overview(workspace_id)[field]
        return {"items": items, "total": len(items)}

    query.__name__ = f"list_{field}"
    return query


for _path, _field in {
    "models": "models",
    "items": "items",
    "revisions": "revisions",
    "baselines": "baselines",
    "strategies": "strategies",
    "plan-items": "plan_items",
    "derived-models": "derived_models",
    "excel-imports": "imports",
}.items():
    router.add_api_route(f"/projects/{{workspace_id}}/{_path}", _listing(_field), methods=["GET"])


@router.get("/projects/{workspace_id}/items/hierarchy")
def hierarchy(workspace_id: int, service=Depends(_authorized("read"))):
    records = service.overview(workspace_id)["items"]
    nodes = {row["id"]: {**row, "children": []} for row in records}
    roots = []
    for row in nodes.values():
        parent = row.get("parent_scope_item_id")
        if parent in nodes:
            nodes[parent]["children"].append(row)
        else:
            roots.append(row)
    return {"items": roots, "total": len(records), "authority": "SCOPE_NOT_WBS"}


@router.get("/projects/{workspace_id}/models/{model_id}/objects")
def model_objects(workspace_id: int, model_id: int, service=Depends(_authorized("read"))):
    return service.model_objects(workspace_id, model_id)


@router.get("/projects/{workspace_id}/models/{model_id}/source")
def model_source(workspace_id: int, model_id: int, service=Depends(_authorized("read"))):
    row = service.model_source(workspace_id, model_id)
    return Response(
        content=row.source_content,
        media_type="application/x-step",
        headers={
            "ETag": f'"{row.source_hash}"',
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(row.source_file_name)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/projects/{workspace_id}/models", status_code=201)
async def stage_model(
    workspace_id: int,
    response: Response,
    file: UploadFile = File(...),
    model_code: str = Form("MAIN"),
    reason: str = Form("Governed IFC import"),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("model.import")),
):
    return _out(
        response,
        service.stage_model(
            workspace_id, await file.read(40 * 1024 * 1024 + 1), file.filename or "source.ifc", model_code, reason, key
        ),
    )


def _model_transition(action):
    def command(
        workspace_id: int,
        model_id: int,
        payload: ActionIn,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized("model.accept" if action == "accept" else "model.review")),
    ):
        return _out(response, service.transition_model(workspace_id, model_id, action, payload, expected, key))

    command.__name__ = f"model_{action}"
    return command


for _action in ("review", "accept", "reject"):
    router.add_api_route(
        f"/projects/{{workspace_id}}/models/{{model_id}}/{_action}", _model_transition(_action), methods=["POST"]
    )


@router.post("/projects/{workspace_id}/excel-imports", status_code=201)
async def stage_excel(
    workspace_id: int,
    response: Response,
    file: UploadFile = File(...),
    field_mapping: str = Form("{}"),
    reason: str = Form("Governed Excel import"),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("item.edit")),
):
    try:
        mapping = json.loads(field_mapping)
        if not isinstance(mapping, dict):
            raise ValueError("mapping object")
    except (ValueError, TypeError) as error:
        raise HTTPException(422, detail={"code": "SCOPE_FIELD_MAPPING_INVALID"}) from error
    return _out(
        response,
        service.stage_excel(
            workspace_id, await file.read(40 * 1024 * 1024 + 1), file.filename or "scope.xlsx", mapping, reason, key
        ),
    )


@router.post("/projects/{workspace_id}/excel-imports/{import_id}/candidate")
def excel_candidate(
    workspace_id: int,
    import_id: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("item.edit")),
):
    return _out(response, service.excel_candidate(workspace_id, import_id, payload, expected, key))


@router.post("/projects/{workspace_id}/items", status_code=201)
def create_item(
    workspace_id: int,
    payload: ItemIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("item.edit")),
):
    return _out(response, service.create_item(workspace_id, payload, key))


@router.put("/projects/{workspace_id}/items/{item_id}")
def update_item(
    workspace_id: int,
    item_id: int,
    payload: ItemIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("item.edit")),
):
    return _out(response, service.update_item(workspace_id, item_id, payload, expected, key))


@router.post("/projects/{workspace_id}/revisions", status_code=201)
def create_revision(
    workspace_id: int,
    payload: RevisionIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("revision.prepare")),
):
    return _out(response, service.create_revision(workspace_id, payload, key))


def _revision_transition(action):
    def command(
        workspace_id: int,
        revision_id: int,
        payload: ActionIn,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized(f"revision.{action}")),
    ):
        return _out(response, service.transition_revision(workspace_id, revision_id, action, payload, expected, key))

    command.__name__ = f"revision_{action}"
    return command


for _action in ("submit", "review", "approve"):
    router.add_api_route(
        f"/projects/{{workspace_id}}/revisions/{{revision_id}}/{_action}",
        _revision_transition(_action),
        methods=["POST"],
    )


@router.post("/projects/{workspace_id}/strategies", status_code=201)
def create_strategy(
    workspace_id: int,
    payload: StrategyIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("strategy.edit")),
):
    return _out(response, service.create_strategy(workspace_id, payload, key))


@router.put("/projects/{workspace_id}/strategies/{strategy_id}")
def update_strategy(
    workspace_id: int,
    strategy_id: int,
    payload: StrategyIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("strategy.edit")),
):
    return _out(response, service.update_strategy(workspace_id, strategy_id, payload, expected, key))


@router.post("/projects/{workspace_id}/strategies/{strategy_id}/segment", status_code=201)
def segment_strategy(
    workspace_id: int,
    strategy_id: int,
    payload: SegmentIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("plan.edit")),
):
    return _out(response, service.segment_strategy(workspace_id, strategy_id, payload, expected, key))


def _strategy_transition(action):
    def command(
        workspace_id: int,
        strategy_id: int,
        payload: ActionIn,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized("strategy.publish" if action == "publish" else "strategy.edit")),
    ):
        return _out(response, service.transition_strategy(workspace_id, strategy_id, action, payload, expected, key))

    command.__name__ = f"strategy_{action}"
    return command


for _action in ("publish", "successor"):
    router.add_api_route(
        f"/projects/{{workspace_id}}/strategies/{{strategy_id}}/{_action}",
        _strategy_transition(_action),
        methods=["POST"],
    )


@router.post("/projects/{workspace_id}/plan-items", status_code=201)
def create_plan(
    workspace_id: int,
    payload: PlanIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("plan.edit")),
):
    return _out(response, service.create_plan(workspace_id, payload, key))


@router.post("/projects/{workspace_id}/plan-items/transform", status_code=201)
def transform_plans(
    workspace_id: int,
    payload: TransformIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("plan.edit")),
):
    return _out(response, service.transform_plans(workspace_id, payload, key))


@router.post("/projects/{workspace_id}/plan-items/{plan_id}/publish")
def publish_plan(
    workspace_id: int,
    plan_id: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("plan.publish")),
):
    return _out(response, service.publish_plan(workspace_id, plan_id, payload, expected, key))


@router.post("/projects/{workspace_id}/derived-models", status_code=201)
def create_derived(
    workspace_id: int,
    payload: DerivedIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("derived.edit")),
):
    return _out(response, service.create_derived(workspace_id, payload, key))


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
