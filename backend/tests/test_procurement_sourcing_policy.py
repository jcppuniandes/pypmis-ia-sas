"""O2B focused policy and command tests (in-memory; not PostgreSQL/UAT evidence)."""

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.database.session import Base
from app.domain.models import SecurityEvent, Tenant
from app.modules.operational_context.models import OperationalContextCommand
from app.modules.procurement_foundation import provision
from app.modules.procurement_foundation.materials_models import (
    ProcurementMaterialReceiptLine,
    ProcurementShipment,
    ProcurementShipmentLine,
)
from app.modules.procurement_foundation.policy import DEFAULT_PROFILE, ProcurementProfile, transition
from app.modules.procurement_foundation.service import ProcurementFoundationService
from app.modules.procurement_foundation.sourcing_models import (
    ProcurementHistory,
    ProcurementPackage,
    ProcurementPurchaseOrder,
    ProcurementPurchaseOrderLine,
    ProcurementPurchaseOrderRevision,
    ProcurementRequirement,
)
from app.modules.procurement_foundation.sourcing_schemas import (
    PurchaseOrderIn,
    PurchaseOrderRevisionApprovalIn,
    PurchaseOrderRevisionIn,
    RFQIn,
)

WORKSPACE = 27
TENANT = 18
REASON = "Approve a documented commercial scope adjustment"


class SourcingHarness(ProcurementFoundationService):
    """Isolate command policy; project setup and RBAC are covered by PG E2E."""

    def _project(self, workspace_id):
        return SimpleNamespace(id=workspace_id)

    def _ready(self, workspace, action):
        return self._project(workspace), SimpleNamespace(content_json=DEFAULT_PROFILE)

    def _pinned_profile(self, row):
        return DEFAULT_PROFILE


@pytest.fixture
def issued_order():
    engine = create_engine("sqlite+pysqlite://")
    models = (
        Tenant,
        SecurityEvent,
        OperationalContextCommand,
        ProcurementHistory,
        ProcurementPackage,
        ProcurementRequirement,
        ProcurementPurchaseOrder,
        ProcurementPurchaseOrderLine,
        ProcurementPurchaseOrderRevision,
        ProcurementShipment,
        ProcurementShipmentLine,
        ProcurementMaterialReceiptLine,
    )
    Base.metadata.create_all(engine, tables=[model.__table__ for model in models])
    with Session(engine) as db:
        date_today = utc_now().date()
        service = SourcingHarness(db, TENANT, 11)
        requirement = service._new(
            ProcurementRequirement,
            WORKSPACE,
            requirement_code="TEST-REQ",
            package_id=8,
            description="Steel",
            item_type="MATERIAL",
            required_quantity=Decimal("10"),
            uom="EA",
            required_on_site_date=date_today + timedelta(days=3),
            status="ACTIVE",
        )
        order = service._new(
            ProcurementPurchaseOrder,
            WORKSPACE,
            po_number="TEST-PO",
            package_id=8,
            vendor_id=17,
            currency="USD",
            issue_date=date_today,
            effective_date=date_today,
            expected_delivery_date=date_today + timedelta(days=3),
            status="ISSUED",
            original_value=Decimal("20"),
            current_value=Decimal("20"),
            approved_by=22,
            issued_by=22,
            configuration_id=51,
            configuration_hash="1" * 64,
        )
        line = service._new(
            ProcurementPurchaseOrderLine,
            WORKSPACE,
            purchase_order_id=order.id,
            requirement_id=requirement.id,
            line_number=1,
            description="Steel",
            quantity=Decimal("10"),
            uom="EA",
            unit_price=Decimal("2"),
            requested_date=date_today + timedelta(days=3),
        )
        approver = SourcingHarness(db, TENANT, 22)
        original = approver._make_initial_po_revision(WORKSPACE, order, [line], "Independent initial approval")
        order.current_revision_id = original.id
        service._record(order, "PO_ISSUED", "Explicit issuance", changed=True)
        db.commit()
        yield db, service, approver, order, line, original
    engine.dispose()


def _revision(line, quantity="8"):
    return PurchaseOrderRevisionIn(
        effective_date=utc_now().date(),
        changed_lines=[{"line_id": line.id, "quantity": quantity, "unit_price": "2"}],
        reason=REASON,
    )


def test_po_revision_is_explicit_and_independent(issued_order):
    db, buyer, approver, order, line, original = issued_order
    cmd = _revision(line)
    created = buyer.create_po_revision(WORKSPACE, order.id, cmd, order.version, "o2b-po-revision-test")
    assert created["status"] == "DRAFT"
    assert buyer.effective_po_line(WORKSPACE, line.id)[1]["quantity"] == "10"
    decision = PurchaseOrderRevisionApprovalIn(approval_reference="BOARD-REF-02", reason=REASON)
    with pytest.raises(HTTPException) as denied:
        buyer.approve_po_revision(WORKSPACE, order.id, created["id"], decision, created["version"], "o2b-self-approval")
    assert denied.value.status_code == 403 and denied.value.detail["code"] == "PROCUREMENT_PO_REVISION_APPROVAL_SOD"
    with pytest.raises(HTTPException) as mismatch:
        approver.approve_po_revision(WORKSPACE, order.id, created["id"], decision, 999, "o2b-bad-etag")
    assert mismatch.value.status_code == 412
    approved = approver.approve_po_revision(
        WORKSPACE, order.id, created["id"], decision, created["version"], "o2b-approve"
    )
    assert approved["status"] == "APPROVED" and approved["approved_by"] == 22
    assert Decimal(approved["value_delta"]) == -4
    assert order.current_revision_id == approved["id"] and order.current_value == 16
    assert line.quantity == 10 and order.original_value == 20 and original.lines_snapshot[0]["quantity"] == "10"
    assert approver.effective_po_line(WORKSPACE, line.id)[1]["quantity"] == "8"
    replay = approver.approve_po_revision(
        WORKSPACE, order.id, created["id"], decision, created["version"], "o2b-approve"
    )
    assert replay == approved
    with pytest.raises(HTTPException) as reused:
        approver.approve_po_revision(
            WORKSPACE,
            order.id,
            created["id"],
            decision.model_copy(update={"reason": "Different decision description"}),
            created["version"],
            "o2b-approve",
        )
    assert reused.value.status_code == 409 and reused.value.detail["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert db.scalar(select(func.count()).select_from(ProcurementPurchaseOrderRevision)) == 2


def test_po_amendment_cannot_reduce_below_reserved_shipment(issued_order):
    db, buyer, _, order, line, _ = issued_order
    shipment = buyer._new(
        ProcurementShipment,
        WORKSPACE,
        shipment_number="TEST-SHIP",
        vendor_id=order.vendor_id,
        origin="Warehouse",
        destination="Site",
        transport_mode="ROAD",
    )
    buyer._new(
        ProcurementShipmentLine,
        WORKSPACE,
        shipment_id=shipment.id,
        po_line_id=line.id,
        material_requirement_id=49,
        quantity=Decimal("9"),
        uom="EA",
        po_revision_hash="8" * 64,
    )
    db.commit()
    with pytest.raises(HTTPException) as denied:
        buyer.create_po_revision(WORKSPACE, order.id, _revision(line), order.version, "o2b-reserved-revision")
    assert (
        denied.value.status_code == 409
        and denied.value.detail["code"] == "PROCUREMENT_PO_REVISION_BELOW_PHYSICAL_QUANTITY"
    )
    assert db.scalar(select(func.count()).select_from(ProcurementPurchaseOrderRevision)) == 1


def test_scoped_lookup_hides_same_tenant_po_in_another_project(issued_order):
    _, buyer, _, order, _, _ = issued_order
    with pytest.raises(HTTPException) as denied:
        buyer._get(ProcurementPurchaseOrder, WORKSPACE + 1, order.id)
    assert denied.value.status_code == 404


def test_procurement_state_machines_never_advance_other_authorities():
    assert transition("requisition", "SUBMITTED", "approve") == "APPROVED"
    assert transition("requisition", "APPROVED", "issue") is None
    assert transition("rfq", "DRAFT", "issue") == "ISSUED"
    assert transition("rfq", "CLOSED", "approve") is None
    assert transition("po", "APPROVED", "issue") == "ISSUED"
    assert transition("po", "ISSUED", "approve") is None
    assert transition("iwp", "READY", "issue") is None


def test_policy_catalog_validation_disallows_unrecognized_lifecycle_shortcuts():
    assert ProcurementProfile.model_validate(DEFAULT_PROFILE).model_dump(mode="json") == DEFAULT_PROFILE
    invalid = deepcopy(DEFAULT_PROFILE)
    invalid["receipt_overage_percent"] = 21
    invalid["procurement_types"] = ["MATERIAL", "MATERIAL"]
    invalid["auto_release_iwp"] = True
    with pytest.raises(ValidationError):
        ProcurementProfile.model_validate(invalid)


def test_command_dto_validates_rfq_date_and_po_requires_nonempty_lines():
    today = date(2026, 11, 11)
    with pytest.raises(ValidationError, match="PROCUREMENT_RFQ_DATES_INVALID"):
        RFQIn(
            rfq_number="RFQ-NO",
            package_id=1,
            requisition_id=1,
            issue_date=today,
            closing_date=today - timedelta(days=1),
            reason=REASON,
        )
    with pytest.raises(ValidationError, match="lines"):
        PurchaseOrderIn(
            po_number="PO-NO",
            package_id=1,
            vendor_id=1,
            currency="USD",
            issue_date=today,
            effective_date=today,
            expected_delivery_date=today,
            lines=[],
            reason=REASON,
        )


def test_provision_requires_organization_scope_and_audits_without_assigning_users(monkeypatch):
    events = []
    db = SimpleNamespace(add=events.append, flush=lambda: None)
    flags = []
    monkeypatch.setattr(provision, "require_procurement_schema", lambda _: flags.append("schema"))
    monkeypatch.setattr(provision, "ensure_procurement_permissions", lambda *args: flags.append("catalog"))

    def scoped(*args, **kwargs):
        assert kwargs["bootstrap"] is False
        assert kwargs["allowed_role_codes"] == {"organization_admin"}
        return SimpleNamespace(organization_wide=False)

    monkeypatch.setattr(provision, "require_enterprise_permission", scoped)
    with pytest.raises(HTTPException) as denied:
        provision.provision_procurement_catalog(db, TENANT, 11, reason=REASON)
    assert denied.value.status_code == 403 and not events and not flags
    monkeypatch.setattr(
        provision, "require_enterprise_permission", lambda *args, **kwargs: SimpleNamespace(organization_wide=True)
    )
    provision.provision_procurement_catalog(db, TENANT, 11, reason=REASON)
    assert flags == ["schema", "catalog"] and len(events) == 1
    assert events[0].event_type == "procurement.permissions.provisioned"
    assert events[0].metadata_json["actor_role_assignments_created"] == 0
