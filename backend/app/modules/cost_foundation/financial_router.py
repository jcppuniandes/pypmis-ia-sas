"""Cost financial read/recognition contracts; no legal or payment commands."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.cost_foundation.financial_schemas import (
    ActualAdjustmentIn,
    ActualDecisionIn,
    ActualIn,
    CommitmentDecisionIn,
    CommitmentIn,
    EACReferenceIn,
    FinancialInput,
    FXRateIn,
)
from app.modules.cost_foundation.financials import CostFinancialService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match

router = APIRouter()


def _authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), actor_id: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(db, tenant_id, actor_id, f"cost.{action}", bootstrap=False)
        return CostFinancialService(db, tenant_id, actor_id, access)

    return dependency


def _out(response, result):
    _etag(response, result.get("version", 1))
    return result


@router.get("/projects/{workspace_id}/fx-rates")
def fx_rates(workspace_id: int, service=Depends(_authorized("read"))):
    return service.fx_rates(workspace_id)


@router.post("/projects/{workspace_id}/fx-rates", status_code=201)
def create_fx(
    workspace_id: int,
    payload: FXRateIn,
    response: Response,
    key=Depends(_idempotency_key),
    service=Depends(_authorized("fx.edit")),
):
    return _out(response, service.create_fx(workspace_id, payload, key))


@router.post("/projects/{workspace_id}/fx-rates/{identity}/publish")
def publish_fx(
    workspace_id: int,
    identity: int,
    payload: FinancialInput,
    response: Response,
    expected=Depends(_if_match),
    key=Depends(_idempotency_key),
    service=Depends(_authorized("fx.publish")),
):
    return _out(response, service.publish_fx(workspace_id, identity, payload, expected, key))


@router.get("/projects/{workspace_id}/actuals")
def actuals(workspace_id: int, target_currency: str | None = None, service=Depends(_authorized("read"))):
    return service.actuals(workspace_id, target_currency)


@router.post("/projects/{workspace_id}/actuals", status_code=201)
def import_actual(
    workspace_id: int,
    payload: ActualIn,
    response: Response,
    key=Depends(_idempotency_key),
    service=Depends(_authorized("actual.import")),
):
    return _out(response, service.import_actual(workspace_id, payload, key))


@router.post("/projects/{workspace_id}/actuals/{identity}/adjustments", status_code=201)
def adjust_actual(
    workspace_id: int,
    identity: int,
    payload: ActualAdjustmentIn,
    response: Response,
    key=Depends(_idempotency_key),
    service=Depends(_authorized("actual.adjust")),
):
    return _out(response, service.import_actual(workspace_id, payload, key, identity))


@router.post("/projects/{workspace_id}/actuals/{identity}/decision")
def decide_actual(
    workspace_id: int,
    identity: int,
    payload: ActualDecisionIn,
    response: Response,
    expected=Depends(_if_match),
    key=Depends(_idempotency_key),
    service=Depends(_authorized("actual.approve")),
):
    return _out(response, service.decide_actual(workspace_id, identity, payload, expected, key))


@router.get("/projects/{workspace_id}/commitments/sources")
def legacy_sources(workspace_id: int, service=Depends(_authorized("read"))):
    return service.legacy_sources(workspace_id)


@router.get("/projects/{workspace_id}/commitments/reconciliation")
def commitments(workspace_id: int, target_currency: str | None = None, service=Depends(_authorized("read"))):
    return service.commitments(workspace_id, target_currency)


@router.post("/projects/{workspace_id}/commitments", status_code=201)
def propose_commitment(
    workspace_id: int,
    payload: CommitmentIn,
    response: Response,
    key=Depends(_idempotency_key),
    service=Depends(_authorized("commitment.reconcile")),
):
    return _out(response, service.propose_commitment(workspace_id, payload, key))


@router.post("/projects/{workspace_id}/commitments/{identity}/verify")
def verify_commitment(
    workspace_id: int,
    identity: int,
    payload: CommitmentDecisionIn,
    response: Response,
    expected=Depends(_if_match),
    key=Depends(_idempotency_key),
    service=Depends(_authorized("commitment.verify")),
):
    return _out(response, service.verify_commitment(workspace_id, identity, payload, expected, key))


@router.get("/projects/{workspace_id}/financial-overview")
def overview(workspace_id: int, service=Depends(_authorized("read"))):
    return service.financial_overview(workspace_id)


@router.get("/projects/{workspace_id}/cash-flow")
def cash_flow(workspace_id: int, service=Depends(_authorized("read"))):
    return service.cash_flow(workspace_id)


@router.get("/projects/{workspace_id}/accruals")
def accrual_contract(workspace_id: int, service=Depends(_authorized("read"))):
    return service.accrual_contract(workspace_id)


@router.post("/projects/{workspace_id}/eac-reference-preview")
def eac_preview(workspace_id: int, payload: EACReferenceIn, service=Depends(_authorized("read"))):
    return service.eac_preview(workspace_id, payload)
