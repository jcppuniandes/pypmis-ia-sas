"""Typed Materials and Logistics API under the shared Procurement authority."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response

from app.modules.portfolio_review.router import _idempotency_key, _if_match
from app.modules.procurement_foundation.materials_schemas import (
    ExpeditingEventIn,
    InspectionDecisionIn,
    InspectionIn,
    MaterialAcceptanceIn,
    MaterialAllocationIn,
    MaterialItemIn,
    MaterialRequirementIn,
    MaterialRequirementLinkIn,
    ReasonIn,
    ReceiptIn,
    ShipmentIn,
    ShipmentTransitionIn,
    VendorMilestoneIn,
    VendorMilestoneSuccessorIn,
)
from app.modules.procurement_foundation.router import _authorized, _out

router = APIRouter()
BASE = "/projects/{workspace_id}"


def _collection(name, action, schema, method):
    def list_rows(
        workspace_id: int,
        limit: int = Query(50, ge=1, le=200),
        after_id: int = Query(0, ge=0),
        service=Depends(_authorized("read")),
    ):
        return service.material_list(workspace_id, name, limit=limit, after_id=after_id)

    def detail(workspace_id: int, identity: int, response: Response, service=Depends(_authorized("read"))):
        return _out(response, service.material_detail(workspace_id, name, identity))

    def create(
        workspace_id: int,
        payload: schema,
        response: Response,
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized(action)),
    ):
        return _out(response, getattr(service, method)(workspace_id, payload, key))

    resource = name.replace("-", "_")
    path = f"{BASE}/{name}"
    router.add_api_route(path, list_rows, methods=["GET"], name=f"procurement_list_{resource}")
    router.add_api_route(path + "/{identity}", detail, methods=["GET"], name=f"procurement_detail_{resource}")
    router.add_api_route(path, create, methods=["POST"], status_code=201, name=f"procurement_create_{resource}")


def _command(path, method, action, schema, handler, status=200):
    def command(
        workspace_id: int,
        identity: int,
        payload: schema,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(_authorized(action)),
    ):
        return _out(response, getattr(service, handler)(workspace_id, identity, payload, expected, key))

    router.add_api_route(BASE + path, command, methods=[method], status_code=status, name=f"procurement_{handler}")


for _args in (
    ("material-items", "material.catalog", MaterialItemIn, "create_material_item"),
    ("material-requirements", "material.requirement", MaterialRequirementIn, "create_material_requirement"),
    ("vendor-milestones", "expediting.record", VendorMilestoneIn, "create_vendor_milestone"),
    ("expediting-events", "expediting.record", ExpeditingEventIn, "create_expediting_event"),
    ("inspections", "inspection.plan", InspectionIn, "create_inspection"),
    ("shipments", "shipment.manage", ShipmentIn, "create_shipment"),
    ("material-receipts", "receipt.record", ReceiptIn, "create_material_receipt"),
    ("material-allocations", "allocation.manage", MaterialAllocationIn, "create_material_allocation"),
):
    _collection(*_args)

for _args in (
    (
        "/material-requirements/{identity}/procurement-link",
        "PUT",
        "material.requirement",
        MaterialRequirementLinkIn,
        "link_material_requirement",
    ),
    (
        "/vendor-milestones/{identity}/successor",
        "POST",
        "expediting.record",
        VendorMilestoneSuccessorIn,
        "supersede_vendor_milestone",
        201,
    ),
    ("/inspections/{identity}/decision", "POST", "inspection.decide", InspectionDecisionIn, "decide_inspection"),
    ("/shipments/{identity}/transition", "POST", "shipment.manage", ShipmentTransitionIn, "transition_shipment"),
    (
        "/material-receipts/{identity}/acceptance",
        "POST",
        "receipt.accept",
        MaterialAcceptanceIn,
        "accept_material_receipt",
        201,
    ),
    (
        "/material-allocations/{identity}/release",
        "POST",
        "allocation.manage",
        ReasonIn,
        "release_material_allocation",
        201,
    ),
):
    _command(*_args)


@router.get(BASE + "/material-availability")
def availability(
    workspace_id: int,
    work_package_id: int = Query(gt=0),
    as_of: date | None = None,
    service=Depends(_authorized("read")),
):
    return service.get_material_availability(workspace_id, work_package_id, as_of)
