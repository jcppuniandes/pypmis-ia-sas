"""Dedicated Progress API; all mutations supply authenticated scoped duties."""

from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.progress_foundation.models import ProgressMeasurement, ProgressRule
from app.modules.progress_foundation.schemas import (
    ActionIn,
    CertificationIn,
    MeasurementIn,
    ProfileIn,
    ProfileUpdateIn,
    RuleIn,
    TransitionIn,
)
from app.modules.progress_foundation.service import ProgressFoundationService

router = APIRouter()


def _authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), actor_id: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(db, tenant_id, actor_id, f"progress.{action}", bootstrap=False)
        return ProgressFoundationService(db, tenant_id, actor_id, access)

    return dependency


def _out(response, result):
    _etag(response, result.get("version", 1))
    return result


@router.get("/projects/{workspace_id}/overview")
def overview(workspace_id: int, service=Depends(_authorized("read"))):
    return service.overview(workspace_id)


@router.get("/projects/{workspace_id}/measurements")
def measurements(
    workspace_id: int,
    progress_type: str | None = None,
    period_id: int | None = None,
    service=Depends(_authorized("read")),
):
    return service.measurements(workspace_id, progress_type=progress_type, period_id=period_id)


@router.get("/projects/{workspace_id}/measurements/{identity}")
def measurement(workspace_id: int, identity: int, response: Response, service=Depends(_authorized("read"))):
    service._permission("read", service._project(workspace_id))
    return _out(response, service._measurement_out(service._get(ProgressMeasurement, workspace_id, identity)))


@router.post("/projects/{workspace_id}/measurements", status_code=201)
def create_measurement(
    workspace_id: int,
    payload: MeasurementIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("capture")),
):
    return _out(response, service.save_measurement(workspace_id, payload, key))


@router.put("/projects/{workspace_id}/measurements/{identity}")
def update_measurement(
    workspace_id: int,
    identity: int,
    payload: MeasurementIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("capture")),
):
    return _out(response, service.save_measurement(workspace_id, payload, key, identity, expected))


@router.post("/projects/{workspace_id}/measurements/{identity}/successor", status_code=201)
def successor_measurement(
    workspace_id: int,
    identity: int,
    payload: MeasurementIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("capture")),
):
    return _out(response, service.save_measurement(workspace_id, payload, key, identity, expected, successor=True))


@router.post("/projects/{workspace_id}/measurements/{identity}/transition")
def transition_measurement(
    workspace_id: int,
    identity: int,
    payload: TransitionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("read")),
):
    return _out(response, service.transition_measurement(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/measurements/{identity}/certify")
def certify_measurement(
    workspace_id: int,
    identity: int,
    payload: CertificationIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("read")),
):
    return _out(response, service.certify_measurement(workspace_id, identity, payload, expected, key))


@router.get("/projects/{workspace_id}/rules")
def rules(workspace_id: int, service=Depends(_authorized("read"))):
    service._permission("read", service._project(workspace_id))
    rows = service._rows(ProgressRule, workspace_id)
    replaced = {row.supersedes_id for row in rows if row.status == "PUBLISHED" and row.supersedes_id}
    return {
        "items": [
            service._out(row) | {"effective_status": "SUPERSEDED" if row.id in replaced else row.status} for row in rows
        ],
        "total": len(rows),
    }


@router.get("/projects/{workspace_id}/rules/{identity}")
def rule(workspace_id: int, identity: int, response: Response, service=Depends(_authorized("read"))):
    service._permission("read", service._project(workspace_id))
    return _out(response, service._out(service._get(ProgressRule, workspace_id, identity)))


@router.post("/projects/{workspace_id}/rules", status_code=201)
def create_rule(
    workspace_id: int,
    payload: RuleIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("rule.manage")),
):
    return _out(response, service.save_rule(workspace_id, payload, key))


@router.put("/projects/{workspace_id}/rules/{identity}")
def update_rule(
    workspace_id: int,
    identity: int,
    payload: RuleIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("rule.manage")),
):
    return _out(response, service.save_rule(workspace_id, payload, key, identity, expected))


@router.post("/projects/{workspace_id}/rules/{identity}/successor", status_code=201)
def successor_rule(
    workspace_id: int,
    identity: int,
    payload: RuleIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("rule.manage")),
):
    return _out(response, service.save_rule(workspace_id, payload, key, identity, expected, successor=True))


@router.post("/projects/{workspace_id}/rules/{identity}/publish")
def publish_rule(
    workspace_id: int,
    identity: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("rule.publish")),
):
    return _out(response, service.publish_rule(workspace_id, identity, payload, expected, key))


@router.get("/projects/{workspace_id}/quantity-progress")
def quantity_progress(workspace_id: int, period_id: int | None = None, service=Depends(_authorized("read"))):
    return service.measurements(workspace_id, progress_type="QUANTITY", period_id=period_id)


@router.get("/projects/{workspace_id}/physical-progress")
def physical_progress(workspace_id: int, period_id: int | None = None, service=Depends(_authorized("read"))):
    return service.measurements(workspace_id, progress_type="PHYSICAL", period_id=period_id)


@router.get("/projects/{workspace_id}/schedule-progress")
def schedule_progress(
    workspace_id: int, as_of: date | None = None, period_id: int | None = None, service=Depends(_authorized("read"))
):
    return service.schedule_progress(workspace_id, as_of=as_of, period_id=period_id)


@router.get("/projects/{workspace_id}/cost-progress")
def cost_progress(
    workspace_id: int, as_of: date | None = None, period_id: int | None = None, service=Depends(_authorized("read"))
):
    return service.cost_progress(workspace_id, as_of=as_of, period_id=period_id)


@router.get("/projects/{workspace_id}/aggregation")
def aggregation(
    workspace_id: int,
    progress_type: str = "PHYSICAL",
    period_id: int | None = None,
    as_of: date | None = None,
    group_by: str = "PROJECT",
    service=Depends(_authorized("read")),
):
    return service.aggregation(
        workspace_id, progress_type=progress_type, period_id=period_id, as_of=as_of, group_by=group_by
    )


@router.get("/projects/{workspace_id}/history")
def history(
    workspace_id: int, entity_type: str | None = None, identity: int | None = None, service=Depends(_authorized("read"))
):
    return service.history(workspace_id, entity_type, identity)


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
