"""Dedicated canonical workspace Cost API."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.cost_foundation.models import CostAPU, CostRate
from app.modules.cost_foundation.schemas import (
    AccountIn,
    ActionIn,
    APUIn,
    BaselineIn,
    BudgetIn,
    BudgetLineIn,
    BudgetTransitionIn,
    CBSIn,
    CostCodeIn,
    MappingIn,
    PhasingIn,
    ProfileIn,
    ProfileUpdateIn,
    RateIn,
    ScopeCandidateIn,
)
from app.modules.cost_foundation.service import COLLECTIONS, CostFoundationService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match

router = APIRouter()


def _authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), actor_id: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(db, tenant_id, actor_id, f"cost.{action}", bootstrap=False)
        return CostFoundationService(db, tenant_id, actor_id, access)

    return dependency


def _out(response, result):
    _etag(response, result.get("version", 1))
    return result


@router.get("/projects/{workspace_id}/overview")
def overview(workspace_id: int, service=Depends(_authorized("read"))):
    return service.overview(workspace_id)


def _listing(field):
    def listing(workspace_id: int, service=Depends(_authorized("read"))):
        service._permission("read", service._project(workspace_id))
        items = [service._out(r) for r in service._rows(COLLECTIONS[field], workspace_id)]
        return {"items": items, "total": len(items)}

    listing.__name__ = f"cost_list_{field}"
    return listing


def _detail(field):
    def detail(workspace_id: int, identity: int, response: Response, service=Depends(_authorized("read"))):
        service._permission("read", service._project(workspace_id))
        return _out(response, service._out(service._get(COLLECTIONS[field], workspace_id, identity)))

    detail.__name__ = f"cost_detail_{field}"
    return detail


for _field in COLLECTIONS:
    router.add_api_route(f"/projects/{{workspace_id}}/{_field.replace('_', '-')}", _listing(_field), methods=["GET"])
    if _field != "history":
        router.add_api_route(
            f"/projects/{{workspace_id}}/{_field.replace('_', '-')}/{{identity}}", _detail(_field), methods=["GET"]
        )


@router.get("/projects/{workspace_id}/history/{entity_type}/{identity}")
def history(workspace_id: int, entity_type: str, identity: int, service=Depends(_authorized("read"))):
    return service.history(workspace_id, entity_type, identity)


@router.post("/projects/{workspace_id}/cbs", status_code=201)
def create_cbs(
    workspace_id: int,
    payload: CBSIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("cbs.edit")),
):
    return _out(response, service.save_structure(workspace_id, "cbs", payload, key))


@router.put("/projects/{workspace_id}/cbs/{identity}")
def update_cbs(
    workspace_id: int,
    identity: int,
    payload: CBSIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("cbs.edit")),
):
    return _out(response, service.save_structure(workspace_id, "cbs", payload, key, identity, expected))


@router.post("/projects/{workspace_id}/cost-codes", status_code=201)
def create_code(
    workspace_id: int,
    payload: CostCodeIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("code.edit")),
):
    return _out(response, service.save_structure(workspace_id, "cost_codes", payload, key))


@router.put("/projects/{workspace_id}/cost-codes/{identity}")
def update_code(
    workspace_id: int,
    identity: int,
    payload: CostCodeIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("code.edit")),
):
    return _out(response, service.save_structure(workspace_id, "cost_codes", payload, key, identity, expected))


@router.post("/projects/{workspace_id}/control-accounts", status_code=201)
def create_account(
    workspace_id: int,
    payload: AccountIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("account.edit")),
):
    return _out(response, service.save_structure(workspace_id, "control_accounts", payload, key))


@router.put("/projects/{workspace_id}/control-accounts/{identity}")
def update_account(
    workspace_id: int,
    identity: int,
    payload: AccountIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("account.edit")),
):
    return _out(response, service.save_structure(workspace_id, "control_accounts", payload, key, identity, expected))


@router.post("/projects/{workspace_id}/mappings", status_code=201)
def create_mapping(
    workspace_id: int,
    payload: MappingIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("mapping.edit")),
):
    return _out(response, service.map_cost(workspace_id, payload, key))


@router.post("/projects/{workspace_id}/mappings/{identity}/successor", status_code=201)
def successor_mapping(
    workspace_id: int,
    identity: int,
    payload: MappingIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("mapping.edit")),
):
    command = payload.model_copy(update={"supersedes_id": identity})
    return _out(response, service.map_cost(workspace_id, command, key, expected))


@router.post("/projects/{workspace_id}/rates", status_code=201)
def create_rate(
    workspace_id: int,
    payload: RateIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("rate.edit")),
):
    return _out(response, service.save_rate(workspace_id, payload, key))


@router.post("/projects/{workspace_id}/rates/{identity}/publish")
def publish_rate(
    workspace_id: int,
    identity: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("rate.publish")),
):
    return _out(response, service.publish_cost(workspace_id, CostRate, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/apus", status_code=201)
def create_apu(
    workspace_id: int,
    payload: APUIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("apu.edit")),
):
    return _out(response, service.save_apu(workspace_id, payload, key))


@router.post("/projects/{workspace_id}/apus/{identity}/publish")
def publish_apu(
    workspace_id: int,
    identity: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("apu.publish")),
):
    return _out(response, service.publish_cost(workspace_id, CostAPU, identity, payload, expected, key))


@router.get("/projects/{workspace_id}/apus/{identity}/calculation")
def apu_calculation(workspace_id: int, identity: int, service=Depends(_authorized("read"))):
    service._permission("read", service._project(workspace_id))
    row = service._get(CostAPU, workspace_id, identity)
    return {
        "apu_id": row.id,
        "unit_amount": str(row.unit_amount),
        "currency": row.currency,
        "unit": row.unit,
        "components": row.components_json,
        "factors": row.factors_json,
        "content_hash": row.content_hash,
        "candidate_only": True,
    }


@router.post("/projects/{workspace_id}/budgets", status_code=201)
def create_budget(
    workspace_id: int,
    payload: BudgetIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("budget.prepare")),
):
    return _out(response, service.create_budget(workspace_id, payload, key))


@router.post("/projects/{workspace_id}/budgets/{identity}/lines", status_code=201)
def add_budget_line(
    workspace_id: int,
    identity: int,
    payload: BudgetLineIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("budget.prepare")),
):
    return _out(response, service.add_line(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/budgets/{identity}/candidate-from-scope", status_code=201)
def candidate_from_scope(
    workspace_id: int,
    identity: int,
    payload: ScopeCandidateIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("budget.prepare")),
):
    return _out(response, service.candidate_from_scope(workspace_id, identity, payload, expected, key))


@router.put("/projects/{workspace_id}/budgets/{identity}/lines/{line_identity}")
def update_budget_line(
    workspace_id: int,
    identity: int,
    line_identity: int,
    payload: BudgetLineIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("budget.prepare")),
):
    return _out(response, service.add_line(workspace_id, identity, payload, expected, key, line_identity))


@router.get("/projects/{workspace_id}/budgets/{identity}/calculation")
def calculate_budget(workspace_id: int, identity: int, service=Depends(_authorized("read"))):
    return service.budget_calculation(workspace_id, identity)


@router.post("/projects/{workspace_id}/budgets/{identity}/transition")
def transition_budget(
    workspace_id: int,
    identity: int,
    payload: BudgetTransitionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("read")),
):
    return _out(response, service.transition_budget(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/budgets/{identity}/successor", status_code=201)
def successor_budget(
    workspace_id: int,
    identity: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("budget.prepare")),
):
    return _out(response, service.successor_budget(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/baselines", status_code=201)
def create_baseline(
    workspace_id: int,
    payload: BaselineIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("baseline.prepare")),
):
    return _out(response, service.create_baseline(workspace_id, payload, key))


@router.post("/projects/{workspace_id}/baselines/{identity}/phase", status_code=201)
def phase_baseline(
    workspace_id: int,
    identity: int,
    payload: PhasingIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("phasing.edit")),
):
    return _out(response, service.phase_baseline(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/baselines/{identity}/approve")
def approve_baseline(
    workspace_id: int,
    identity: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("baseline.approve")),
):
    return _out(response, service.approve_baseline(workspace_id, identity, payload, expected, key))


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
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.publish")),
):
    return _out(response, service.publish_profile(identity, payload, expected, key))


@router.post("/admin/profiles/{identity}/successor", status_code=201)
def successor_profile(
    identity: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.configure")),
):
    return _out(response, service.successor_profile(identity, payload, expected, key))
