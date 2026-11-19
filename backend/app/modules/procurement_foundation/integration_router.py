"""Procurement reference queries and append-only mapping commands."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response

from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.procurement_foundation.integration import ProcurementMappingIn
from app.modules.procurement_foundation.router import _authorized

router = APIRouter()
PROJECT = "/projects/{workspace_id}"


@router.get(PROJECT + "/mappings")
def mappings(
    workspace_id: int,
    response: Response,
    source_kind: str | None = None,
    source_id: int | None = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    service=Depends(_authorized("read")),
):
    result = service.procurement_mappings(workspace_id, source_kind, source_id, limit, after_id)
    _etag(response, result["version"])
    return result


@router.post(PROJECT + "/mappings", status_code=201)
def map_reference(
    workspace_id: int,
    payload: ProcurementMappingIn,
    response: Response,
    expected=Depends(_if_match),
    key=Depends(_idempotency_key),
    service=Depends(_authorized("mapping.edit")),
):
    result = service.write_procurement_mapping(workspace_id, payload, expected, key)
    _etag(response, result["version"])
    return result


@router.get(PROJECT + "/mapping-targets")
def mapping_targets(
    workspace_id: int,
    target_kind: str,
    schedule_version_id: int | None = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    service=Depends(_authorized("read")),
):
    return service.procurement_mapping_targets(workspace_id, target_kind, schedule_version_id, limit, after_id)


@router.get(PROJECT + "/document-targets")
def document_targets(
    workspace_id: int,
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    service=Depends(_authorized("read")),
):
    return service.document_targets(workspace_id, limit, after_id)


@router.get(PROJECT + "/status")
def status(workspace_id: int, service=Depends(_authorized("read"))):
    return service.procurement_status(workspace_id)


@router.get(PROJECT + "/lookahead")
def lookahead(
    workspace_id: int,
    horizon_days: int = Query(28, ge=1, le=366),
    package_id: int | None = Query(None, gt=0),
    status: str | None = None,
    category: str | None = None,
    discipline: str | None = None,
    responsible_id: int | None = Query(None, gt=0),
    vendor_id: int | None = Query(None, gt=0),
    target_kind: str | None = None,
    target_id: int | None = Query(None, gt=0),
    start: date | None = None,
    end: date | None = None,
    service=Depends(_authorized("read")),
):
    return service.procurement_lookahead(
        workspace_id,
        horizon_days=horizon_days,
        package_id=package_id,
        status=status,
        category=category,
        discipline=discipline,
        responsible_id=responsible_id,
        vendor_id=vendor_id,
        target_kind=target_kind,
        target_id=target_id,
        start=start,
        end=end,
    )


@router.get(PROJECT + "/trace")
def trace(workspace_id: int, package_id: int = Query(gt=0), service=Depends(_authorized("read"))):
    return service.procurement_trace(workspace_id, package_id)


@router.get(PROJECT + "/readiness")
def readiness(workspace_id: int, package_id: int = Query(gt=0), service=Depends(_authorized("read"))):
    return service.procurement_readiness(workspace_id, package_id)


@router.get(PROJECT + "/source-facts")
def source_facts(workspace_id: int, package_id: int = Query(gt=0), service=Depends(_authorized("read"))):
    return service.procurement_source_facts(workspace_id, package_id)
