"""Dedicated Procurement command and query API, scoped to canonical PROJECT."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.engineering_foundation.schemas import ProfileIn, ProfileUpdateIn, ReasonIn
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.procurement_foundation.service import ProcurementFoundationService
from app.modules.procurement_foundation.sourcing import SOURCING_COLLECTIONS
from app.modules.procurement_foundation.sourcing_schemas import (
    ActionIn,
    AwardIn,
    BidIn,
    EvaluationIn,
    InvitationIn,
    PackageIn,
    PackageItemIn,
    PurchaseOrderIn,
    PurchaseOrderRevisionApprovalIn,
    PurchaseOrderRevisionIn,
    RequirementIn,
    RequisitionIn,
    RFQIn,
    VendorIn,
)

router = APIRouter()
PROJECT = "/projects/{workspace_id}"


def _authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), actor_id: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(db, tenant_id, actor_id, f"procurement.{action}", bootstrap=False)
        return ProcurementFoundationService(db, tenant_id, actor_id, access)

    return dependency


def _out(response, result):
    if isinstance(result, dict):
        _etag(response, result.get("version", 1))
    return result


@router.get(PROJECT + "/configuration")
def configuration(workspace_id: int, service=Depends(_authorized("read"))):
    return service.configuration(workspace_id)


def _queries(collection):
    def list_rows(
        workspace_id: int,
        limit: int = Query(50, ge=1, le=200),
        after_id: int = Query(0, ge=0),
        service=Depends(_authorized("read")),
    ):
        return service.sourcing_list(workspace_id, collection, limit=limit, after_id=after_id)

    def detail(workspace_id: int, identity: int, response: Response, service=Depends(_authorized("read"))):
        return _out(response, service.sourcing_detail(workspace_id, collection, identity))

    name = collection.replace("-", "_")
    router.add_api_route(PROJECT + f"/{collection}", list_rows, methods=["GET"], name=f"procurement_list_{name}")
    router.add_api_route(
        PROJECT + f"/{collection}/{{identity}}", detail, methods=["GET"], name=f"procurement_get_{name}"
    )


for _collection in SOURCING_COLLECTIONS:
    _queries(_collection)


def _create_route(collection, dto, method, action="read"):
    def create(
        workspace_id: int,
        payload: dto,
        response: Response,
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized(action)),
    ):
        return _out(response, getattr(service, method)(workspace_id, payload, key))

    name = collection.replace("-", "_")
    router.add_api_route(
        PROJECT + f"/{collection}", create, methods=["POST"], status_code=201, name=f"procurement_create_{name}"
    )


for _collection, _dto, _method, _action in (
    ("vendors", VendorIn, "create_vendor", "vendor.create"),
    ("packages", PackageIn, "save_package", "package.create"),
    ("requirements", RequirementIn, "create_requirement", "requirement.create"),
    ("requisitions", RequisitionIn, "create_requisition", "requisition.create"),
    ("rfqs", RFQIn, "create_rfq", "rfq.create"),
    ("bids", BidIn, "create_bid", "bid.create"),
    ("evaluations", EvaluationIn, "create_evaluation", "read"),
    ("awards", AwardIn, "create_award", "award.approve"),
    ("purchase-orders", PurchaseOrderIn, "create_purchase_order", "po.create"),
):
    _create_route(_collection, _dto, _method, _action)


def _action_route(collection, entity):
    def action(
        workspace_id: int,
        identity: int,
        payload: ActionIn,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized("read")),
    ):
        return _out(response, service.transition_sourcing(workspace_id, entity, identity, payload, expected, key))

    router.add_api_route(
        PROJECT + f"/{collection}/{{identity}}/actions", action, methods=["POST"], name=f"procurement_action_{entity}"
    )


for _collection, _entity in (
    ("packages", "package"),
    ("requirements", "requirement"),
    ("vendors", "vendor"),
    ("requisitions", "requisition"),
    ("rfqs", "rfq"),
    ("purchase-orders", "po"),
):
    _action_route(_collection, _entity)


@router.put(PROJECT + "/packages/{identity}")
def update_package(
    workspace_id: int,
    identity: int,
    payload: PackageIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("package.edit")),
):
    return _out(response, service.save_package(workspace_id, payload, key, identity, expected))


@router.post(PROJECT + "/packages/{identity}/items", status_code=201)
def add_package_item(
    workspace_id: int,
    identity: int,
    payload: PackageItemIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("package.item.add")),
):
    return _out(response, service.add_package_item(workspace_id, identity, payload, expected, key))


@router.post(PROJECT + "/rfqs/{identity}/invitations", status_code=201)
def invite_vendor(
    workspace_id: int,
    identity: int,
    payload: InvitationIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("rfq.invite")),
):
    return _out(response, service.invite_vendor(workspace_id, identity, payload, expected, key))


@router.post(PROJECT + "/purchase-orders/{identity}/revisions", status_code=201)
def create_po_revision(
    workspace_id: int,
    identity: int,
    payload: PurchaseOrderRevisionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("po.revise")),
):
    return _out(response, service.create_po_revision(workspace_id, identity, payload, expected, key))


@router.post(PROJECT + "/purchase-orders/{identity}/revisions/{revision_id}/approve")
def approve_po_revision(
    workspace_id: int,
    identity: int,
    revision_id: int,
    payload: PurchaseOrderRevisionApprovalIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("po.revision.approve")),
):
    return _out(response, service.approve_po_revision(workspace_id, identity, revision_id, payload, expected, key))


@router.get(PROJECT + "/history")
def history(
    workspace_id: int,
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    entity_type: str | None = Query(None, max_length=80),
    entity_id: int | None = Query(None, gt=0),
    service=Depends(_authorized("read")),
):
    return service.history(workspace_id, limit=limit, after_id=after_id, entity_type=entity_type, entity_id=entity_id)


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
