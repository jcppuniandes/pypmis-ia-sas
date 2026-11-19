"""Small persisted projection regressions; PostgreSQL/UAT are separate release proofs."""

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from app.database.session import Base
from app.modules.awp.models import WorkPackage
from app.modules.basic_data.service import _hash
from app.modules.procurement_foundation.availability import (
    material_acceptance_hash,
    material_allocation_hash,
    material_availability,
)
from app.modules.procurement_foundation.integration import mapping_content
from app.modules.procurement_foundation.integration_models import ProcurementMapping
from app.modules.procurement_foundation.materials_models import (
    MATERIAL_MODELS,
    ProcurementInspection,
    ProcurementMaterialAcceptance,
    ProcurementMaterialAllocation,
    ProcurementMaterialItem,
    ProcurementMaterialReceipt,
    ProcurementMaterialReceiptLine,
    ProcurementMaterialRequirement,
    ProcurementShipment,
    ProcurementShipmentLine,
)
from app.modules.procurement_foundation.materials_schemas import MaterialAcceptanceIn, MaterialAllocationIn
from app.modules.procurement_foundation.sourcing_models import (
    ProcurementHistory,
    ProcurementPurchaseOrder,
    ProcurementPurchaseOrderLine,
    ProcurementPurchaseOrderRevision,
    ProcurementRequirement,
)

TENANT = 40
WORKSPACE = 80
PACKAGE = 50


def stamp(day):
    return datetime(2026, 1, day, 12)


def source(day):
    return {
        "tenant_id": TENANT,
        "project_workspace_id": WORKSPACE,
        "created_at": stamp(day),
        "created_by": 2,
        "version": 1,
    }


def _history(day, kind, identity, snapshot):
    return ProcurementHistory(
        **source(day),
        entity_type=kind,
        entity_id=identity,
        entity_version=1,
        event_type="UNIT_FIXTURE",
        snapshot_json=snapshot,
        reason="Persisted chronological source",
    )


def _allocation(identity, day, *, state="ACTIVE", previous=None):
    material = {
        "receipt_line_id": 1,
        "acceptance_id": 1,
        "material_requirement_id": 1,
        "work_package_id": PACKAGE,
        "quantity": Decimal(4),
        "uom": "EA",
        "allocation_date": stamp(day).date(),
        "expires_on": stamp(10).date(),
        "source_location": "Site Store",
        "state": state,
        "supersedes_id": previous,
    }
    return ProcurementMaterialAllocation(
        **source(day), **material, id=identity, content_hash=material_allocation_hash(material)
    )


@pytest.fixture
def inventory():
    engine = create_engine("sqlite+pysqlite://")
    models = (
        *MATERIAL_MODELS,
        WorkPackage,
        ProcurementMapping,
        ProcurementHistory,
        ProcurementRequirement,
        ProcurementPurchaseOrder,
        ProcurementPurchaseOrderLine,
        ProcurementPurchaseOrderRevision,
    )
    Base.metadata.create_all(engine, tables=[model.__table__ for model in models])
    with Session(engine) as db:
        item = ProcurementMaterialItem(
            **source(1), id=1, material_code="M1", description="Valve", uom="EA", category="GENERAL"
        )
        demand = ProcurementMaterialRequirement(
            **source(1),
            id=1,
            requirement_code="MAT1",
            material_item_id=1,
            procurement_requirement_id=1,
            required_quantity=Decimal(8),
            uom="EA",
            required_on_site_date=stamp(10).date(),
        )
        package = WorkPackage(
            **source(1), id=PACKAGE, updated_by=2, package_code="IWP-1", package_type="IWP", name="Install valve"
        )
        requisition = ProcurementRequirement(
            **source(1),
            id=1,
            updated_by=2,
            requirement_code="REQ1",
            package_id=1,
            description="Sourcing for valve demand",
            item_type="MATERIAL",
            required_quantity=Decimal(10),
            uom="EA",
            status="ACTIVE",
            required_on_site_date=stamp(10).date(),
        )
        order = ProcurementPurchaseOrder(
            **source(1),
            id=1,
            updated_by=2,
            po_number="PO1",
            package_id=1,
            vendor_id=1,
            currency="USD",
            issue_date=stamp(1).date(),
            effective_date=stamp(1).date(),
            expected_delivery_date=stamp(4).date(),
            status="ISSUED",
            original_value=Decimal(100),
            current_value=Decimal(100),
            configuration_id=1,
            configuration_hash="a" * 64,
        )
        order_line = ProcurementPurchaseOrderLine(
            **source(1),
            id=1,
            purchase_order_id=1,
            requirement_id=1,
            line_number=1,
            description="Valve",
            quantity=Decimal(10),
            uom="EA",
            unit_price=Decimal(10),
            requested_date=stamp(4).date(),
        )
        link = ProcurementMapping(
            **(source(1) | {"version": 2}),
            id=1,
            source_kind="MATERIAL_REQUIREMENT",
            source_id=1,
            target_kind="IWP",
            target_id=PACKAGE,
            action="SET",
            effective_date=stamp(1).date(),
            target_snapshot_json={},
            reason="Governed demand destination",
            content_hash="a" * 64,
        )
        link.content_hash = _hash(mapping_content(link))
        shipment = ProcurementShipment(
            **source(1),
            id=1,
            shipment_number="S1",
            vendor_id=1,
            origin="Factory",
            destination="Site Store",
            transport_mode="ROAD",
            dispatch_date=stamp(2).date(),
            actual_arrival=stamp(3).date(),
            status="RECEIVED",
        )
        shipment_line = ProcurementShipmentLine(
            **source(1),
            id=1,
            shipment_id=1,
            po_line_id=1,
            material_requirement_id=1,
            quantity=Decimal(10),
            uom="EA",
            po_revision_hash="a" * 64,
        )
        receipt = ProcurementMaterialReceipt(
            **source(4), id=1, receipt_number="R1", shipment_id=1, location="Site Store", received_at=stamp(4)
        )
        receipt_line = ProcurementMaterialReceiptLine(
            **source(4),
            id=1,
            receipt_id=1,
            shipment_line_id=1,
            po_line_id=1,
            material_item_id=1,
            material_requirement_id=1,
            quantity=Decimal(10),
            uom="EA",
        )
        inspection = ProcurementInspection(
            **source(3),
            id=1,
            po_line_id=1,
            vendor_id=1,
            inspection_type="SITE",
            inspection_date=stamp(4).date(),
            status="ACCEPTED",
            decided_at=stamp(5),
            decided_by=3,
        )
        quantities = {
            "receipt_line_id": 1,
            "inspection_id": 1,
            "accepted_quantity": Decimal(8),
            "rejected_quantity": Decimal(2),
            "quarantine_quantity": Decimal(0),
            "detail": "Verified segregated stock",
        }
        accepted = ProcurementMaterialAcceptance(
            **source(5), **quantities, id=1, content_hash=material_acceptance_hash(quantities)
        )
        db.add_all(
            [
                item,
                demand,
                package,
                requisition,
                order,
                order_line,
                link,
                shipment,
                shipment_line,
                receipt,
                receipt_line,
                inspection,
                accepted,
                _allocation(1, 6),
                _allocation(2, 7),
                _allocation(3, 8, state="RELEASED", previous=1),
                _history(1, "ProcurementMaterialRequirement", 1, {"procurement_requirement_id": 1}),
                _history(1, "ProcurementPurchaseOrder", 1, {"status": "ISSUED"}),
                _history(1, "ProcurementShipment", 1, {"status": "PLANNED"}),
                _history(3, "ProcurementShipment", 1, {"status": "ARRIVED", "dispatch_date": "2026-01-02"}),
            ]
        )
        db.commit()
        yield db
    engine.dispose()


def get_availability(db, day):
    return material_availability(db, TENANT, WORKSPACE, PACKAGE, stamp(day).date())


def test_material_timeline_does_not_infer_receipt_acceptance_allocation_or_awp_release(inventory):
    projected = {day: get_availability(inventory, day) for day in (2, 3, 4, 5, 6, 7, 8, 11)}
    assert projected[2]["requirements"][0]["shipped_quantity"] == "0"  # Backdated dispatch recorded on day 3.
    assert projected[3]["requirements"][0]["received_quantity"] == "0"  # Arrived does not imply received.
    assert projected[4]["requirements"][0]["accepted_quantity"] == "0"  # Received does not imply accepted.
    assert projected[5]["requirements"][0]["accepted_quantity"] == "8"
    assert projected[5]["requirements"][0]["rejected_quantity"] == "2"
    assert projected[5]["status"] == "NOT_READY"  # Accepted does not imply allocated.
    assert projected[6]["status"] == "PARTIALLY_READY"
    assert projected[7]["status"] == "READY"
    assert projected[8]["status"] == "PARTIALLY_READY"  # Append-only release of a reservation.
    assert projected[11]["status"] == "STALE"
    assert inventory.get(WorkPackage, PACKAGE).release_state == "NOT_RELEASED"


def test_material_evidence_hash_stable_for_same_facts_and_fails_closed_on_tamper(inventory):
    ready = get_availability(inventory, 7)
    assert ready == get_availability(inventory, 7)
    inventory.execute(
        update(ProcurementMaterialAllocation).where(ProcurementMaterialAllocation.id == 2).values(content_hash="0" * 64)
    )
    inventory.commit()
    broken = get_availability(inventory, 7)
    assert broken["status"] == "BROKEN_REFERENCE"
    assert broken["requirements"][0]["available_quantity"] == "0"
    assert "MATERIAL_ALLOCATION_SOURCE_INVALID" in broken["reason_codes"]
    assert ready["evidence_hash"] != broken["evidence_hash"]
    assert material_availability(inventory, TENANT + 1, WORKSPACE, PACKAGE) is None
    assert material_availability(inventory, TENANT, WORKSPACE + 1, PACKAGE) is None


def test_material_allocations_are_decimal_and_quantities_fail_closed():
    facts = {
        "receipt_line_id": 1,
        "inspection_id": None,
        "accepted_quantity": Decimal("8"),
        "rejected_quantity": Decimal("2"),
        "quarantine_quantity": Decimal("0"),
        "detail": "",
    }
    assert material_acceptance_hash(facts) == material_acceptance_hash(
        facts | {"accepted_quantity": Decimal("8.000000")}
    )
    with pytest.raises(ValidationError):
        MaterialAcceptanceIn(**(facts | {"quarantine_quantity": Decimal("-1")}), reason="Invalid partition")
    with pytest.raises(ValidationError):
        MaterialAllocationIn(
            receipt_line_id=1,
            material_requirement_id=1,
            work_package_id=1,
            quantity="NaN",
            uom="EA",
            allocation_date=stamp(6).date(),
            source_location="Site Store",
            reason="Invalid quantity",
        )
