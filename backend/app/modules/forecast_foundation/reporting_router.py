"""Dedicated read models and explicit publication, separate from source writers."""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.forecast_foundation.reporting_schemas import LookAheadIn, ReportPublishIn
from app.modules.forecast_foundation.reporting_service import ForecastReportingService
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match

performance_router = APIRouter()
reporting_router = APIRouter()


def _authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), actor_id: int = Depends(get_user_id)
    ):
        context = require_enterprise_permission(db, tenant_id, actor_id, f"forecast.{action}", bootstrap=False)
        return ForecastReportingService(db, tenant_id, actor_id, context)

    return dependency


def _out(response, result):
    _etag(response, result.get("version", 1))
    return result


@performance_router.get("/projects/{workspace_id}/overview")
def overview(
    workspace_id: int,
    forecast_version_id: int,
    period_id: int | None = None,
    as_of: date | None = None,
    service=Depends(_authorized("read")),
):
    return service.performance(workspace_id, forecast_version_id, period_id=period_id, as_of=as_of)


@performance_router.get("/projects/{workspace_id}/variance")
def variance(
    workspace_id: int,
    forecast_version_id: int,
    period_id: int | None = None,
    as_of: date | None = None,
    service=Depends(_authorized("read")),
):
    return service.variance(workspace_id, forecast_version_id, period_id=period_id, as_of=as_of)


@performance_router.get("/projects/{workspace_id}/trends")
def trends(workspace_id: int, forecast_version_id: int | None = None, service=Depends(_authorized("read"))):
    return service.trends(workspace_id, forecast_version_id=forecast_version_id)


@performance_router.get("/projects/{workspace_id}/curves")
def curves(
    workspace_id: int,
    forecast_version_id: int,
    period_id: int | None = None,
    as_of: date | None = None,
    service=Depends(_authorized("read")),
):
    return service.curves(workspace_id, forecast_version_id, period_id=period_id, as_of=as_of)


@performance_router.get("/projects/{workspace_id}/dashboard")
def dashboard(
    workspace_id: int,
    forecast_version_id: int,
    period_id: int | None = None,
    as_of: date | None = None,
    service=Depends(_authorized("dashboard.view")),
):
    return service.dashboard(workspace_id, forecast_version_id, period_id=period_id, as_of=as_of)


@performance_router.get("/projects/{workspace_id}/executive")
def executive(
    workspace_id: int,
    forecast_version_id: int,
    period_id: int | None = None,
    as_of: date | None = None,
    service=Depends(_authorized("executive.view")),
):
    return service.dashboard(workspace_id, forecast_version_id, executive=True, period_id=period_id, as_of=as_of)


@performance_router.get("/projects/{workspace_id}/lookahead")
def lookahead(
    workspace_id: int,
    forecast_version_id: int = Query(gt=0),
    period_id: int | None = None,
    as_of: date | None = None,
    horizon_days: int | None = Query(default=None, ge=1, le=366),
    group_by: Literal["PARENT_WBS", "CWA", "PACKAGE", "AREA", "ZONE", "SYSTEM", "DISCIPLINE"] | None = None,
    top_n: int | None = Query(default=None, ge=1, le=10000),
    critical_only: bool = False,
    near_critical_value: Decimal | None = Query(default=None, ge=0),
    near_critical_unit: Literal["HOUR", "DAY"] | None = None,
    wbs_external_id: str | None = Query(default=None, max_length=160),
    work_package_id: int | None = Query(default=None, gt=0),
    exclude_milestones: bool | None = None,
    service=Depends(_authorized("lookahead.view")),
):
    payload = LookAheadIn(
        forecast_version_id=forecast_version_id,
        horizon_days=horizon_days,
        group_by=group_by,
        top_n=top_n,
        critical_only=critical_only,
        near_critical_value=near_critical_value,
        near_critical_unit=near_critical_unit,
        wbs_external_id=wbs_external_id,
        work_package_id=work_package_id,
        exclude_milestones=exclude_milestones,
    )
    return service.lookahead(workspace_id, payload, period_id=period_id, as_of=as_of)


@performance_router.post("/projects/{workspace_id}/lookahead/snapshots", status_code=201)
def generate_lookahead(
    workspace_id: int,
    payload: LookAheadIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("lookahead.generate")),
):
    return _out(response, service.generate_lookahead(workspace_id, payload, key))


@reporting_router.get("/projects/{workspace_id}/reports")
def reports(workspace_id: int, service=Depends(_authorized("report.read"))):
    return service.reports(workspace_id)


@reporting_router.get("/projects/{workspace_id}/reports/history")
def history(workspace_id: int, service=Depends(_authorized("report.read"))):
    return service.reports(workspace_id)


@reporting_router.post("/projects/{workspace_id}/reports", status_code=201)
def publish_report(
    workspace_id: int,
    payload: ReportPublishIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("report.publish")),
):
    return _out(response, service.publish_report(workspace_id, payload, key))


@reporting_router.get("/projects/{workspace_id}/reports/{identity}")
def report(workspace_id: int, identity: int, response: Response, service=Depends(_authorized("report.read"))):
    return _out(response, service.report(workspace_id, identity))


@reporting_router.post("/projects/{workspace_id}/reports/{identity}/successor", status_code=201)
def republish_report(
    workspace_id: int,
    identity: int,
    payload: ReportPublishIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("report.republish")),
):
    return _out(response, service.publish_report(workspace_id, payload, key, predecessor=identity, expected=expected))


@reporting_router.get("/projects/{workspace_id}/analytics-contract")
def analytics_contract(workspace_id: int, service=Depends(_authorized("report.read"))):
    return service.analytics_contract(workspace_id)
