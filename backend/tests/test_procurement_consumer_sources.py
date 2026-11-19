"""Deterministic read-only Procurement consumer fact and pin regressions."""

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.session import Base
from app.modules.basic_data.service import _hash
from app.modules.cost_foundation.models import CostCode
from app.modules.procurement_foundation import consumer_sources
from app.modules.procurement_foundation.availability import material_acceptance_hash
from app.modules.procurement_foundation.consumer_sources import resolve_procurement_source
from app.modules.procurement_foundation.integration import mapping_content
from app.modules.procurement_foundation.integration_models import ProcurementMapping
from app.modules.procurement_foundation.materials_models import (
    MATERIAL_MODELS,
    ProcurementMaterialAcceptance,
    ProcurementMaterialItem,
    ProcurementMaterialReceipt,
    ProcurementMaterialReceiptLine,
    ProcurementMaterialRequirement,
    ProcurementShipment,
    ProcurementShipmentLine,
    ProcurementVendorMilestone,
)
from app.modules.procurement_foundation.sourcing import po_revision_material
from app.modules.procurement_foundation.sourcing_models import (
    ProcurementHistory,
    ProcurementPackage,
    ProcurementPurchaseOrder,
    ProcurementPurchaseOrderLine,
    ProcurementPurchaseOrderRevision,
    ProcurementRequirement,
    ProcurementVendor,
)

TENANT, WORKSPACE, PACKAGE = 10, 20, 30


def stamp(day):
    return datetime(2026, 1, day, 12)


def day(value):
    return stamp(value).date()


def base(created=10, version=1):
    return {
        "tenant_id": TENANT,
        "project_workspace_id": WORKSPACE,
        "created_by": 3,
        "created_at": stamp(created),
        "version": version,
    }


def mutable(created=10, version=1):
    return base(created, version) | {"updated_at": stamp(created), "updated_by": 3}


def history(row, event, observed, version=None, **snapshot):
    version = version or row.version
    return ProcurementHistory(
        **base(observed),
        entity_type=type(row).__name__,
        entity_id=row.id,
        entity_version=version,
        event_type=event,
        snapshot_json={"version": version, **snapshot},
        reason="Synthetic test evidence",
    )


@pytest.fixture
def procurement(monkeypatch):
    monkeypatch.setattr(consumer_sources, "utc_now", lambda: stamp(20))
    engine = create_engine("sqlite+pysqlite://")
    models = (
        *MATERIAL_MODELS,
        ProcurementMapping,
        CostCode,
        ProcurementHistory,
        ProcurementPackage,
        ProcurementRequirement,
        ProcurementVendor,
        ProcurementPurchaseOrder,
        ProcurementPurchaseOrderLine,
        ProcurementPurchaseOrderRevision,
    )
    Base.metadata.create_all(engine, tables=[model.__table__ for model in models])
    with Session(engine) as db:
        package = ProcurementPackage(
            **mutable(),
            id=PACKAGE,
            package_code="PKG-01",
            title="Pump purchase",
            procurement_type="GOODS",
            category="MECH",
            responsible_user_id=3,
            procurement_manager_id=3,
            sourcing_method="RFQ",
            required_on_site_date=day(29),
            planned_award_date=day(18),
            planned_po_date=day(21),
            forecast_delivery_date=day(27),
            status="PLANNED",
            configuration_id=1,
            configuration_hash="a" * 64,
        )
        vendor = ProcurementVendor(
            id=1,
            tenant_id=TENANT,
            vendor_code="V-01",
            legal_name="Synthetic vendor",
            display_name="Vendor",
            business_identifier="SYNTHETIC",
            country="CO",
            created_at=stamp(9),
            created_by=3,
            status="ACTIVE",
        )
        requirement = ProcurementRequirement(
            **mutable(),
            id=1,
            requirement_code="REQ-01",
            package_id=package.id,
            description="Pump",
            item_type="GOODS",
            required_quantity=Decimal(4),
            uom="EA",
            required_on_site_date=day(29),
            status="ACTIVE",
        )
        order = ProcurementPurchaseOrder(
            **mutable(11, 3),
            id=1,
            po_number="PO-01",
            package_id=package.id,
            vendor_id=1,
            currency="USD",
            issue_date=day(11),
            effective_date=day(11),
            expected_delivery_date=day(28),
            status="ISSUED",
            original_value=Decimal(80),
            current_value=Decimal(80),
            current_revision_id=1,
            approved_by=4,
            issued_by=5,
            configuration_id=1,
            configuration_hash="a" * 64,
        )
        line = ProcurementPurchaseOrderLine(
            **base(11),
            id=1,
            purchase_order_id=1,
            requirement_id=1,
            line_number=1,
            description="Pump",
            quantity=Decimal(4),
            uom="EA",
            unit_price=Decimal(20),
            requested_date=day(29),
        )
        snapshot = {"line_id": 1, "uom": "EA", "quantity": "4", "unit_price": "20"}
        revision = ProcurementPurchaseOrderRevision(
            **mutable(11),
            id=1,
            purchase_order_id=1,
            revision=1,
            effective_date=day(11),
            status="APPROVED",
            reason="Original issue",
            lines_snapshot=[snapshot],
            value_delta=Decimal(0),
            total_value=Decimal(80),
            schedule_impact_reference={},
            approved_by=4,
            content_hash="",
        )
        revision.content_hash = _hash(po_revision_material(revision))
        item = ProcurementMaterialItem(
            **base(),
            id=1,
            material_code="M-01",
            description="Pump",
            uom="EA",
            category="MECH",
        )
        demand = ProcurementMaterialRequirement(
            **base(),
            id=1,
            requirement_code="MREQ-01",
            material_item_id=1,
            procurement_requirement_id=1,
            required_quantity=Decimal(4),
            uom="EA",
            required_on_site_date=day(29),
        )
        shipment = ProcurementShipment(
            **base(12),
            id=1,
            shipment_number="S-01",
            vendor_id=1,
            origin="Supplier",
            destination="Site",
            transport_mode="ROAD",
            status="PLANNED",
            forecast_arrival=day(24),
        )
        shipment_line = ProcurementShipmentLine(
            **base(12),
            id=1,
            shipment_id=1,
            po_line_id=1,
            material_requirement_id=1,
            quantity=Decimal(4),
            uom="EA",
            po_revision_hash=_hash(snapshot),
        )
        db.add_all([package, vendor, requirement, order, line, revision, item, demand, shipment, shipment_line])
        db.add(history(shipment, "SHIPMENT_PLANNED", 12, forecast_arrival="2026-01-24"))
        db.commit()
        yield db, order, revision, shipment
    engine.dispose()


def resolve(db, source_type, identity=1, **kwargs):
    return resolve_procurement_source(db, TENANT, WORKSPACE, source_type, identity, **kwargs)


def rejects(code, call, status=409):
    with pytest.raises(HTTPException) as result:
        call()
    assert result.value.detail == f"PROCUREMENT_CONSUMER_{code}"
    assert result.value.status_code == status


def test_scoped_current_pin_and_governed_cost_mapping(procurement):
    db, order, revision, _ = procurement
    target = CostCode(**mutable(), id=1, code="C-01", name="Equipment", category="MECH", status="ACTIVE")
    target_snapshot = {
        "target_kind": "COST_CODE",
        "target_id": 1,
        "target_version": 1,
        "code": "C-01",
        "title": "Equipment",
    }
    link = ProcurementMapping(
        **base(12, 2),
        id=1,
        source_kind="PACKAGE",
        source_id=PACKAGE,
        target_kind="COST_CODE",
        target_id=1,
        effective_date=day(12),
        action="SET",
        target_snapshot_json=target_snapshot | {"source_hash": _hash(target_snapshot)},
        reason="Approved code assignment",
        content_hash="",
    )
    link.content_hash = _hash(mapping_content(link))
    db.add_all([target, link])
    db.commit()
    pin = resolve(db, "PO_REVISION", consumer="COST")
    assert pin["observed_at"] == "2026-01-11T12:00:00+00:00"
    assert [row["id"] for row in pin["cost_mappings"]] == [1]
    assert pin == resolve(db, "PO_REVISION", as_of=day(19), expected_version=1, expected_hash=pin["source_hash"])
    assert not db.new and not db.dirty and not db.deleted
    rejects("SOURCE_VERSION_MISMATCH", lambda: resolve(db, "PO_REVISION", expected_version=2))
    rejects("SOURCE_HASH_MISMATCH", lambda: resolve(db, "PO_REVISION", expected_hash="f" * 64))
    rejects("SOURCE_TYPE_INVALID", lambda: resolve(db, "PO_REVISION", consumer="PROGRESS"), 422)
    rejects("SOURCE_NOT_FOUND", lambda: resolve_procurement_source(db, TENANT, WORKSPACE + 1, "PO_REVISION", 1), 404)
    rejects("SOURCE_NOT_FOUND", lambda: resolve_procurement_source(db, TENANT + 1, WORKSPACE, "VENDOR", 1), 404)
    target.status = "INACTIVE"
    db.commit()
    rejects("STALE_COST_MAPPING", lambda: resolve(db, "PO_REVISION"))
    target.status = "ACTIVE"
    replacement = ProcurementPurchaseOrderRevision(
        **mutable(18, 2),
        id=2,
        purchase_order_id=1,
        previous_revision_id=revision.id,
        revision=2,
        effective_date=day(18),
        status="APPROVED",
        reason="Revised delivery",
        lines_snapshot=revision.lines_snapshot,
        value_delta=Decimal(0),
        total_value=Decimal(80),
        schedule_impact_reference={},
        approved_by=4,
        content_hash="",
    )
    replacement.content_hash = _hash(po_revision_material(replacement))
    order.current_revision_id = 2
    order.updated_at = stamp(18)
    db.add(replacement)
    db.commit()
    rejects("PO_REVISION_SUPERSEDED", lambda: resolve(db, "PO_REVISION"))
    assert resolve(db, "PO_REVISION", 2)["source_version"] == 2
    rejects("SOURCE_NOT_YET_OBSERVED", lambda: resolve(db, "PO", as_of=day(15)))


def test_shipment_freshness_and_conditional_forecast(procurement):
    db, _, _, shipment = procurement
    shipment.status, shipment.version, shipment.dispatch_date = "DISPATCHED", 2, day(18)
    db.add(history(shipment, "SHIPMENT_DISPATCHED", 18, dispatch_date="2026-01-18", forecast_arrival="2026-01-24"))
    db.commit()
    source = resolve(db, "SHIPMENT_FORECAST")
    assert source["observed_at"] == "2026-01-12T12:00:00+00:00"
    assert source["facts"]["signals"]["forecast_arrival"] == "2026-01-24"
    forecast = resolve(db, "MATERIAL_AVAILABILITY_FORECAST")
    assert forecast["facts"]["requires_receipt_acceptance_allocation"]
    rejects("FORECAST_OBSERVATION_STALE", lambda: resolve(db, "SHIPMENT_FORECAST", max_age_days=7))
    rejects("SOURCE_NOT_YET_OBSERVED", lambda: resolve(db, "SHIPMENT_FORECAST", as_of=day(14)))
    shipment.forecast_arrival = day(16)
    db.commit()
    rejects("SHIPMENT_FORECAST_DATE_INVALID", lambda: resolve(db, "SHIPMENT_FORECAST"))
    rejects("INVALID_AS_OF", lambda: resolve(db, "SHIPMENT_FORECAST", as_of=day(21)), 422)


def test_dispatch_arrival_receipt_and_negative_disposition_are_separate(procurement):
    db, _, _, shipment = procurement
    shipment.status, shipment.version = "ARRIVED", 3
    shipment.dispatch_date, shipment.actual_arrival = day(15), day(16)
    db.add_all(
        [
            history(shipment, "SHIPMENT_DISPATCHED", 15, 2, dispatch_date="2026-01-15"),
            history(shipment, "SHIPMENT_ARRIVED", 16, 3, actual_arrival="2026-01-16"),
        ]
    )
    db.commit()
    dispatch, arrival = resolve(db, "DISPATCH"), resolve(db, "ARRIVAL")
    assert dispatch["source_version"] == 2 and arrival["source_version"] == 3
    assert arrival["facts"]["evidence_type"] == "ARRIVAL" and "received_quantity" not in arrival["facts"]
    rejects("SOURCE_NOT_FOUND", lambda: resolve(db, "RECEIPT"), 404)
    receipt = ProcurementMaterialReceipt(
        **base(17),
        id=1,
        receipt_number="R-01",
        shipment_id=1,
        location="Site",
        received_at=stamp(17),
    )
    line = ProcurementMaterialReceiptLine(
        **base(17),
        id=1,
        receipt_id=1,
        shipment_line_id=1,
        po_line_id=1,
        material_item_id=1,
        material_requirement_id=1,
        quantity=Decimal(4),
        uom="EA",
    )
    shipment.status, shipment.version = "RECEIVED", 4
    db.add_all([receipt, line, history(receipt, "MATERIAL_RECEIPT_RECORDED", 17)])
    db.commit()
    receipt_pin = resolve(db, "RECEIPT")
    assert receipt_pin["facts"]["lines"][0]["received_quantity"] == "4"
    assert "accepted_quantity" not in receipt_pin["facts"]["lines"][0]
    disposition = {
        "receipt_line_id": 1,
        "inspection_id": None,
        "accepted_quantity": Decimal(0),
        "rejected_quantity": Decimal(1),
        "quarantine_quantity": Decimal(3),
        "detail": "Rejected and quarantined",
    }
    acceptance = ProcurementMaterialAcceptance(
        **base(18),
        **disposition,
        id=1,
        content_hash=material_acceptance_hash(disposition),
    )
    receipt.version = 2
    db.add(acceptance)
    db.commit()
    evidence = resolve(db, "ACCEPTANCE")["facts"]
    assert evidence["classifications"] == ["REJECTED", "QUARANTINE"]
    assert evidence["accepted_quantity"] == "0" and "installed_quantity" not in evidence
    assert receipt_pin == resolve(db, "RECEIPT", expected_hash=receipt_pin["source_hash"])
    assert dispatch == resolve(db, "DISPATCH", expected_hash=dispatch["source_hash"])


def test_milestone_successor_and_staleness(procurement):
    db, *_ = procurement

    def milestone(identity, observed, forecast, previous=None):
        material = {
            "po_line_id": 1,
            "code": "MANUFACTURING_COMPLETE",
            "planned_date": day(25),
            "forecast_date": day(forecast),
            "actual_date": None,
            "supersedes_id": previous,
            "version": identity,
        }
        return ProcurementVendorMilestone(
            **base(observed, identity),
            id=identity,
            content_hash=_hash(material),
            **{key: value for key, value in material.items() if key != "version"},
        )

    db.add(milestone(1, 13, 25))
    db.commit()
    old = resolve(db, "MILESTONE_FORECAST")
    assert old["facts"]["signals"]["forecast_date"] == "2026-01-25"
    rejects("FORECAST_OBSERVATION_STALE", lambda: resolve(db, "MILESTONE_FORECAST", max_age_days=6))
    db.add(milestone(2, 18, 27, 1))
    db.commit()
    rejects(
        "MILESTONE_SUPERSEDED",
        lambda: resolve(db, "MILESTONE_FORECAST", as_of=day(14), expected_hash=old["source_hash"]),
    )
    assert resolve(db, "MILESTONE_FORECAST", 2)["facts"]["signals"]["forecast_date"] == "2026-01-27"
