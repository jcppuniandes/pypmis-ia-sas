"""Quality remediation commands and queries inside the shared project shell."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.quality.execution_schemas import (
    AcceptanceIn,
    CorrectiveActionActionIn,
    CorrectiveActionIn,
    DispositionActionIn,
    DispositionIn,
    NCRActionIn,
    NCRIn,
    PunchActionIn,
    PunchIn,
)
from app.modules.quality.execution_service import RESOURCES, QualityExecutionService

router = APIRouter()
PROJECT = "/projects/{workspace_id}"


def authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant: int = Depends(get_tenant_id), actor: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(db, tenant, actor, f"quality.{action}", bootstrap=False)
        return QualityExecutionService(db, tenant, actor, access)

    return dependency


def out(response, value):
    if isinstance(value, dict) and "version" in value:
        _etag(response, value["version"])
    return value


def queries(resource):
    def listing(
        workspace_id: int,
        limit: int = Query(50, ge=1, le=200),
        after_id: int = Query(0, ge=0),
        status: str | None = Query(None, max_length=40),
        ncr_id: int | None = Query(None, gt=0),
        service=Depends(authorized("read")),
    ):
        return service.execution_collection(
            workspace_id, resource, limit=limit, after_id=after_id, status=status, ncr_id=ncr_id
        )

    def detail(workspace_id: int, identity: int, response: Response, service=Depends(authorized("read"))):
        return out(response, service.execution_detail(workspace_id, resource, identity))

    router.add_api_route(PROJECT + f"/{resource}", listing, methods=["GET"], name=f"quality_list_{resource}")
    router.add_api_route(PROJECT + f"/{resource}/{{identity}}", detail, methods=["GET"], name=f"quality_get_{resource}")


def create_route(resource, dto, method, duty):
    def create(
        workspace_id: int,
        payload: dto,
        response: Response,
        key=Depends(_idempotency_key),
        service=Depends(authorized(duty)),
    ):
        return out(response, getattr(service, method)(workspace_id, payload, key))

    router.add_api_route(
        PROJECT + f"/{resource}", create, methods=["POST"], status_code=201, name=f"quality_create_{resource}"
    )


def action_route(resource, dto, method):
    def action(
        workspace_id: int,
        identity: int,
        payload: dto,
        response: Response,
        expected=Depends(_if_match),
        key=Depends(_idempotency_key),
        service=Depends(authorized("read")),
    ):
        return out(response, getattr(service, method)(workspace_id, identity, payload, expected, key))

    router.add_api_route(
        PROJECT + f"/{resource}/{{identity}}/actions", action, methods=["POST"], name=f"quality_action_{resource}"
    )


for _resource in RESOURCES:
    queries(_resource)

for _resource, _dto, _method, _duty in (
    ("ncrs", NCRIn, "create_ncr", "ncr.record"),
    ("dispositions", DispositionIn, "create_disposition", "ncr.disposition"),
    ("corrective-actions", CorrectiveActionIn, "create_corrective_action", "action.record"),
    ("punch-items", PunchIn, "create_punch", "punch.record"),
    ("acceptances", AcceptanceIn, "create_acceptance", "acceptance.approve"),
):
    create_route(_resource, _dto, _method, _duty)

for _resource, _dto, _method in (
    ("ncrs", NCRActionIn, "ncr_action"),
    ("dispositions", DispositionActionIn, "disposition_action"),
    ("corrective-actions", CorrectiveActionActionIn, "corrective_action_action"),
    ("punch-items", PunchActionIn, "punch_action"),
):
    action_route(_resource, _dto, _method)


@router.get(PROJECT + "/quality-source")
def quality_source(
    workspace_id: int,
    source_entity_type: str = Query(pattern=r"^(INSPECTION|TEST)$"),
    source_entity_id: int = Query(gt=0),
    service=Depends(authorized("read")),
):
    return service.quality_source(workspace_id, source_entity_type, source_entity_id)


@router.get(PROJECT + "/dashboard")
def dashboard(workspace_id: int, service=Depends(authorized("read"))):
    return service.dashboard(workspace_id)


@router.get(PROJECT + "/readiness")
def readiness(
    workspace_id: int,
    itp_id: int = Query(gt=0),
    source_type: str = Query(pattern=r"^[A-Z_]{2,60}$"),
    source_id: int = Query(gt=0),
    as_of: datetime | None = None,
    service=Depends(authorized("read")),
):
    return service.readiness_query(workspace_id, itp_id, source_type, source_id, as_of=as_of)


@router.get(PROJECT + "/lookahead")
def lookahead(
    workspace_id: int,
    horizon_days: int = Query(14, ge=1, le=90),
    as_of: datetime | None = None,
    status: str | None = Query(None, max_length=40),
    iwp_id: int | None = Query(None, gt=0),
    workfront_id: int | None = Query(None, gt=0),
    cwp_id: int | None = Query(None, gt=0),
    discipline: str | None = Query(None, min_length=1, max_length=80),
    vendor_id: int | None = Query(None, gt=0),
    inspector_user_id: int | None = Query(None, gt=0),
    date_from: date | None = None,
    date_to: date | None = None,
    location: str | None = Query(None, min_length=1, max_length=500),
    service=Depends(authorized("read")),
):
    return service.lookahead(
        workspace_id,
        horizon_days=horizon_days,
        as_of=as_of,
        status=status,
        iwp_id=iwp_id,
        workfront_id=workfront_id,
        cwp_id=cwp_id,
        discipline=discipline,
        vendor_id=vendor_id,
        inspector_user_id=inspector_user_id,
        date_from=date_from,
        date_to=date_to,
        location=location,
    )


@router.get(PROJECT + "/trace")
def trace(
    workspace_id: int,
    entity_type: str = Query(
        pattern=r"^(NCR|CORRECTIVE_ACTION|PUNCH|ACCEPTANCE|INSPECTION|TEST|PLAN|ITP|ITP_ITEM|INSPECTION_REQUEST|TEST_REQUEST)$"
    ),
    entity_id: int = Query(gt=0),
    service=Depends(authorized("read")),
):
    return service.trace(workspace_id, entity_type, entity_id)
