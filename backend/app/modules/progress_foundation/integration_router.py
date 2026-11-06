"""Dedicated Progress reference bundles, period commands and EVM projections."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.progress_foundation.integration import ProgressIntegrationService
from app.modules.progress_foundation.integration_schemas import (
    BundleIn,
    BundleSuccessorIn,
    BundleTransitionIn,
    EVMSnapshotIn,
    PeriodTransitionIn,
)

router = APIRouter()


def _authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), actor_id: int = Depends(get_user_id)
    ):
        context = require_enterprise_permission(db, tenant_id, actor_id, f"progress.{action}", bootstrap=False)
        return ProgressIntegrationService(db, tenant_id, actor_id, context)

    return dependency


def _out(response, result):
    _etag(response, result.get("version", 1))
    return result


@router.get("/projects/{workspace_id}/baseline-bundles")
def bundles(workspace_id: int, service=Depends(_authorized("read"))):
    return service.bundles(workspace_id)


@router.post("/projects/{workspace_id}/baseline-bundles", status_code=201)
def create_bundle(
    workspace_id: int,
    payload: BundleIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("baseline.prepare")),
):
    return _out(response, service.create_bundle(workspace_id, payload, key))


@router.get("/projects/{workspace_id}/baseline-bundles/{identity}")
def bundle(workspace_id: int, identity: int, response: Response, service=Depends(_authorized("read"))):
    return _out(response, service.bundle(workspace_id, identity))


@router.get("/projects/{workspace_id}/baseline-bundles/{identity}/validate")
def validate_bundle(workspace_id: int, identity: int, service=Depends(_authorized("read"))):
    return service.bundle_validation(workspace_id, identity)


@router.post("/projects/{workspace_id}/baseline-bundles/{identity}/transition")
def transition_bundle(
    workspace_id: int,
    identity: int,
    payload: BundleTransitionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("read")),
):
    return _out(response, service.transition_bundle(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/baseline-bundles/{identity}/successor", status_code=201)
def successor_bundle(
    workspace_id: int,
    identity: int,
    payload: BundleSuccessorIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("baseline.prepare")),
):
    return _out(response, service.create_bundle(workspace_id, payload, key, predecessor=identity, expected=expected))


@router.get("/projects/{workspace_id}/periods/{identity}/review")
def period_review(workspace_id: int, identity: int, service=Depends(_authorized("read"))):
    return service.period_review(workspace_id, identity)


@router.post("/projects/{workspace_id}/periods/{identity}/transition")
def transition_period(
    workspace_id: int,
    identity: int,
    payload: PeriodTransitionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("read")),
):
    result = service.transition_progress_period(workspace_id, identity, payload, expected, key)
    _etag(response, result["period"]["version"])
    return result


@router.get("/projects/{workspace_id}/evm")
def evm(
    workspace_id: int,
    bundle_id: int = Query(gt=0),
    period_id: int = Query(gt=0),
    as_of: date = Query(),
    currency: str | None = None,
    service=Depends(_authorized("evm.view")),
):
    return service.evm(workspace_id, bundle_id, period_id, as_of, currency)


@router.get("/projects/{workspace_id}/evm/snapshots")
def evm_snapshots(workspace_id: int, service=Depends(_authorized("evm.view"))):
    return service.evm_snapshots(workspace_id)


@router.post("/projects/{workspace_id}/evm/snapshots", status_code=201)
def capture_evm(
    workspace_id: int,
    payload: EVMSnapshotIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("period.publish")),
):
    return _out(response, service.save_evm_snapshot(workspace_id, payload, key))


@router.get("/projects/{workspace_id}/curves")
def curves(
    workspace_id: int,
    bundle_id: int = Query(gt=0),
    period_id: int = Query(gt=0),
    as_of: date = Query(),
    service=Depends(_authorized("read")),
):
    return service.curves(workspace_id, bundle_id, period_id, as_of)


@router.get("/projects/{workspace_id}/four-d-overlay")
def four_d_overlay(
    workspace_id: int,
    bundle_id: int = Query(gt=0),
    period_id: int = Query(gt=0),
    as_of: date = Query(),
    service=Depends(_authorized("read")),
):
    return service.four_d_overlay(workspace_id, bundle_id, period_id, as_of)
