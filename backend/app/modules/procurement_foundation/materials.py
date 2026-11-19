"""Explicit physical commands; O2B never writes AWP release or financial facts."""

from datetime import UTC, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.core.time import utc_now
from app.modules.awp.models import WorkPackage
from app.modules.basic_data.service import _hash
from app.modules.engineering_foundation.integration import EngineeringIntegrationMixin
from app.modules.procurement_foundation.availability import (
    active_allocations,
    material_acceptance_hash,
    material_allocation_hash,
    material_availability,
)
from app.modules.procurement_foundation.integration import effective_mappings, mapping_content
from app.modules.procurement_foundation.materials_models import (
    ProcurementExpeditingEvent,
    ProcurementInspection,
    ProcurementMaterialAcceptance,
    ProcurementMaterialAllocation,
    ProcurementMaterialItem,
    ProcurementMaterialReceipt,
    ProcurementMaterialReceiptLine,
    ProcurementMaterialRequirement,
    ProcurementShipment,
    ProcurementShipmentLine,
    ProcurementVendorMilestone,
)
from app.modules.procurement_foundation.sourcing_models import (
    ProcurementPurchaseOrder,
    ProcurementPurchaseOrderLine,
    ProcurementRequirement,
)

MATERIAL_COLLECTIONS = {
    "material-items": ProcurementMaterialItem,
    "material-requirements": ProcurementMaterialRequirement,
    "vendor-milestones": ProcurementVendorMilestone,
    "expediting-events": ProcurementExpeditingEvent,
    "inspections": ProcurementInspection,
    "shipments": ProcurementShipment,
    "material-receipts": ProcurementMaterialReceipt,
    "material-allocations": ProcurementMaterialAllocation,
}

SHIPMENT_TRANSITIONS = {
    "PLANNED": {"READY_FOR_DISPATCH", "CANCELLED"},
    "READY_FOR_DISPATCH": {"DISPATCHED", "CANCELLED"},
    "DISPATCHED": {"IN_TRANSIT", "ARRIVED"},
    "IN_TRANSIT": {"ARRIVED"},
}


class MaterialsMixin:
    def _material_query(self, model, workspace):
        return select(model).where(model.tenant_id == self.tenant_id, model.project_workspace_id == workspace)

    def _material_new(self, model, workspace, **values):
        row = model(**(self._base(workspace) | values))
        self.db.add(row)
        self.db.flush()
        return row

    def _material_profile(self, workspace, action):
        return self._ready(workspace, action)[1].content_json

    @staticmethod
    def _material_rule(profile, key, default):
        return profile.get(key, profile.get("material_rules", {}).get(key, default))

    def _material_catalog(self, profile, key, value):
        code = value.upper()
        catalog = profile.get(key, ())
        if catalog and code not in {item if isinstance(item, str) else item.get("code") for item in catalog}:
            self._error(422, "PROCUREMENT_MATERIAL_CATALOG_VALUE_INVALID")
        return code

    def _material_cde(self, workspace, evidence):
        if evidence is None:
            return {}
        return EngineeringIntegrationMixin._resolve_document(
            self, workspace, evidence.document_id, evidence.attachment_id
        )

    def _material_detail(self, workspace, row):
        out = self._out(row)
        if isinstance(row, ProcurementShipment):
            out["lines"] = [
                self._out(line)
                for line in self.db.scalars(
                    self._material_query(ProcurementShipmentLine, workspace)
                    .where(ProcurementShipmentLine.shipment_id == row.id)
                    .order_by(ProcurementShipmentLine.id)
                )
            ]
        elif isinstance(row, ProcurementMaterialReceipt):
            lines = list(
                self.db.scalars(
                    self._material_query(ProcurementMaterialReceiptLine, workspace)
                    .where(ProcurementMaterialReceiptLine.receipt_id == row.id)
                    .order_by(ProcurementMaterialReceiptLine.id)
                )
            )
            decisions = {
                fact.receipt_line_id: self._out(fact)
                for fact in self.db.scalars(
                    self._material_query(ProcurementMaterialAcceptance, workspace).where(
                        ProcurementMaterialAcceptance.receipt_line_id.in_([line.id for line in lines])
                    )
                )
            }
            out["lines"] = [self._out(line) | {"acceptance": decisions.get(line.id)} for line in lines]
        return out

    def material_list(self, workspace, collection, *, limit=50, after_id=0):
        self._read_project(workspace)
        model = MATERIAL_COLLECTIONS[collection]
        rows = list(
            self.db.scalars(
                self._material_query(model, workspace).where(model.id > after_id).order_by(model.id).limit(limit + 1)
            )
        )
        return {
            "items": [self._redact(workspace, self._out(row)) for row in rows[:limit]],
            "next_after_id": rows[limit - 1].id if len(rows) > limit else None,
        }

    def material_detail(self, workspace, collection, identity):
        self._read_project(workspace)
        row = self._get(MATERIAL_COLLECTIONS[collection], workspace, identity)
        return self._redact(workspace, self._material_detail(workspace, row))

    def _material_qty(self, workspace, model, column, *filters):
        return self.db.scalar(
            select(func.coalesce(func.sum(column), 0)).where(
                model.tenant_id == self.tenant_id, model.project_workspace_id == workspace, *filters
            )
        )

    def _material_po(self, workspace, line_id, *, lock=False):
        line = self._get(ProcurementPurchaseOrderLine, workspace, line_id)
        order = self._get(ProcurementPurchaseOrder, workspace, line.purchase_order_id, lock=lock)
        if order.status != "ISSUED" or order.effective_date > utc_now().date():
            self._error(409, "PROCUREMENT_ISSUED_EFFECTIVE_PO_REQUIRED")
        line, snapshot = self.effective_po_line(workspace, line_id)
        return order, line, snapshot

    def _demand_link(self, workspace, demand_uom, quantity, sourcing_id):
        if sourcing_id is None:
            return
        source = self._get(ProcurementRequirement, workspace, sourcing_id, lock=True)
        if source.status == "CANCELLED" or source.uom.upper() != demand_uom or quantity > source.required_quantity:
            self._error(409, "PROCUREMENT_MATERIAL_REQUIREMENT_LINK_MISMATCH")
        existing = self.db.scalar(
            self._material_query(ProcurementMaterialRequirement, workspace).where(
                ProcurementMaterialRequirement.procurement_requirement_id == sourcing_id
            )
        )
        if existing:
            self._error(409, "PROCUREMENT_MATERIAL_REQUIREMENT_LINK_EXISTS")

    def create_material_item(self, workspace, payload, key):
        profile = self._material_profile(workspace, "material.catalog")

        def apply():
            row = self._material_new(
                ProcurementMaterialItem,
                workspace,
                material_code=self._code(payload.material_code),
                description=payload.description,
                specification=payload.specification,
                uom=payload.uom.upper(),
                category=self._material_catalog(profile, "material_categories", payload.category),
            )
            return self._record(row, "MATERIAL_ITEM_CREATED", payload.reason)

        return self._write("material.item.create", workspace, payload, key, apply)

    def create_material_requirement(self, workspace, payload, key):
        self._material_profile(workspace, "material.requirement")

        def apply():
            item = self._get(ProcurementMaterialItem, workspace, payload.material_item_id)
            if item.uom != payload.uom.upper():
                self._error(422, "PROCUREMENT_MATERIAL_UOM_MISMATCH")
            if (payload.source_type is None) != (payload.evidence is None):
                self._error(422, "PROCUREMENT_MTO_BOM_REFERENCE_PAIR_REQUIRED")
            self._demand_link(workspace, item.uom, payload.required_quantity, payload.procurement_requirement_id)
            source = self._material_cde(workspace, payload.evidence)
            row = self._material_new(
                ProcurementMaterialRequirement,
                workspace,
                requirement_code=self._code(payload.requirement_code),
                material_item_id=item.id,
                procurement_requirement_id=payload.procurement_requirement_id,
                required_quantity=payload.required_quantity,
                uom=item.uom,
                required_on_site_date=payload.required_on_site_date,
                source_reference_json=({"source_type": payload.source_type, **source} if source else {}),
            )
            return self._record(row, "MATERIAL_REQUIREMENT_CREATED", payload.reason)

        return self._write("material.requirement.create", workspace, payload, key, apply)

    def link_material_requirement(self, workspace, identity, payload, expected, key):
        self._material_profile(workspace, "material.requirement")

        def apply():
            row = self._get(ProcurementMaterialRequirement, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.procurement_requirement_id is not None:
                self._error(409, "PROCUREMENT_MATERIAL_REQUIREMENT_LINK_IMMUTABLE")
            self._demand_link(workspace, row.uom, row.required_quantity, payload.procurement_requirement_id)
            row.procurement_requirement_id = payload.procurement_requirement_id
            return self._record(row, "MATERIAL_REQUIREMENT_PROCUREMENT_LINKED", payload.reason, changed=True)

        return self._write("material.requirement.link", workspace, payload, key, apply, identity, expected)

    def create_vendor_milestone(self, workspace, payload, key):
        self._material_profile(workspace, "expediting.record")

        def apply():
            self._material_po(workspace, payload.po_line_id, lock=True)
            return self._vendor_milestone(
                workspace,
                payload.po_line_id,
                payload.code.upper(),
                payload.planned_date,
                payload.forecast_date,
                payload.actual_date,
                payload.reason,
            )

        return self._write("vendor.milestone.create", workspace, payload, key, apply)

    def _vendor_milestone(self, workspace, line, code, planned, forecast, actual, reason, previous=None):
        if actual and actual > utc_now().date():
            self._error(422, "PROCUREMENT_FUTURE_MILESTONE_ACTUAL")
        values = {
            "po_line_id": line,
            "code": code,
            "planned_date": planned,
            "forecast_date": forecast,
            "actual_date": actual,
            "supersedes_id": previous.id if previous else None,
            "version": previous.version + 1 if previous else 1,
        }
        row = self._material_new(ProcurementVendorMilestone, workspace, **values, content_hash=_hash(values))
        return self._record(row, "VENDOR_MILESTONE_RECORDED", reason)

    def supersede_vendor_milestone(self, workspace, identity, payload, expected, key):
        self._material_profile(workspace, "expediting.record")

        def apply():
            row = self._get(ProcurementVendorMilestone, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.actual_date is not None or self.db.scalar(
                self._material_query(ProcurementVendorMilestone, workspace).where(
                    ProcurementVendorMilestone.supersedes_id == row.id
                )
            ):
                self._error(409, "PROCUREMENT_VENDOR_MILESTONE_IMMUTABLE")
            return self._vendor_milestone(
                workspace,
                row.po_line_id,
                row.code,
                row.planned_date,
                payload.forecast_date,
                payload.actual_date,
                payload.reason,
                row,
            )

        return self._write("vendor.milestone.supersede", workspace, payload, key, apply, identity, expected)

    def create_expediting_event(self, workspace, payload, key):
        self._material_profile(workspace, "expediting.record")

        def apply():
            self._material_po(workspace, payload.po_line_id)
            if payload.observation_date > utc_now().date():
                self._error(422, "PROCUREMENT_FUTURE_EXPEDITING_OBSERVATION")
            values = payload.model_dump(exclude={"reason"})
            row = self._material_new(ProcurementExpeditingEvent, workspace, **values, content_hash=_hash(values))
            return self._record(row, "EXPEDITING_EVENT_RECORDED", payload.reason)

        return self._write("expediting.event.create", workspace, payload, key, apply)

    def create_inspection(self, workspace, payload, key):
        profile = self._material_profile(workspace, "inspection.plan")

        def apply():
            order, _, _ = self._material_po(workspace, payload.po_line_id)
            row = self._material_new(
                ProcurementInspection,
                workspace,
                po_line_id=payload.po_line_id,
                vendor_id=order.vendor_id,
                inspection_type=self._material_catalog(profile, "inspection_types", payload.inspection_type),
                inspection_date=payload.inspection_date,
            )
            return self._record(row, "PROCUREMENT_INSPECTION_PLANNED", payload.reason)

        return self._write("inspection.create", workspace, payload, key, apply)

    def decide_inspection(self, workspace, identity, payload, expected, key):
        profile = self._material_profile(workspace, "inspection.decide")

        def apply():
            row = self._get(ProcurementInspection, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "PLANNED" or row.inspection_date > utc_now().date():
                self._error(409, "PROCUREMENT_INSPECTION_DECISION_INVALID")
            if (
                profile.get("separation_of_duties", {}).get("inspector_cannot_accept", True)
                and row.created_by == self.actor_id
            ):
                self._error(403, "PROCUREMENT_INSPECTION_SOD")
            row.status, row.decided_by, row.decided_at = payload.result, self.actor_id, utc_now()
            row.detail, row.ncr_reference = payload.detail, payload.ncr_reference
            row.document_reference_json = self._material_cde(workspace, payload.evidence)
            return self._record(row, f"PROCUREMENT_INSPECTION_{payload.result}", payload.reason, changed=True)

        return self._write("inspection.decide", workspace, payload, key, apply, identity, expected)

    def _overage(self, profile, quantity):
        return quantity * (Decimal(1) + Decimal(str(self._material_rule(profile, "receipt_overage_percent", 0))) / 100)

    def create_shipment(self, workspace, payload, key):
        profile = self._material_profile(workspace, "shipment.manage")

        def apply():
            if len({item.po_line_id for item in payload.lines}) != len(payload.lines):
                self._error(422, "PROCUREMENT_DUPLICATE_SHIPMENT_PO_LINE")
            pinned = []
            for item in sorted(payload.lines, key=lambda item: item.po_line_id):
                order, line, snapshot = self._material_po(workspace, item.po_line_id, lock=True)
                demand = self._get(ProcurementMaterialRequirement, workspace, item.material_requirement_id)
                uom = item.uom.upper()
                if order.vendor_id != payload.vendor_id or line.requirement_id != demand.procurement_requirement_id:
                    self._error(422, "PROCUREMENT_SHIPMENT_SCOPE_MISMATCH")
                if uom != demand.uom or uom != str(snapshot["uom"]).upper():
                    self._error(422, "PROCUREMENT_MATERIAL_UOM_MISMATCH")
                reserved = self._material_qty(
                    workspace,
                    ProcurementShipmentLine,
                    ProcurementShipmentLine.quantity,
                    ProcurementShipmentLine.po_line_id == line.id,
                    ProcurementShipmentLine.shipment_id.in_(
                        select(ProcurementShipment.id).where(ProcurementShipment.status != "CANCELLED")
                    ),
                )
                if reserved + item.quantity > self._overage(profile, Decimal(str(snapshot["quantity"]))):
                    self._error(409, "PROCUREMENT_SHIPMENT_QUANTITY_EXCEEDS_ORDER")
                pinned.append((item, _hash(snapshot)))
            row = self._material_new(
                ProcurementShipment,
                workspace,
                shipment_number=self._code(payload.shipment_number),
                vendor_id=payload.vendor_id,
                origin=payload.origin,
                destination=payload.destination,
                transport_mode=self._material_catalog(profile, "shipment_modes", payload.transport_mode),
                carrier_reference=payload.carrier_reference,
                customs_reference=payload.customs_reference,
                planned_arrival=payload.planned_arrival,
                forecast_arrival=payload.forecast_arrival,
                document_reference_json=self._material_cde(workspace, payload.evidence),
            )
            for item, source_hash in pinned:
                line = self._material_new(
                    ProcurementShipmentLine,
                    workspace,
                    shipment_id=row.id,
                    po_line_id=item.po_line_id,
                    material_requirement_id=item.material_requirement_id,
                    quantity=item.quantity,
                    uom=item.uom.upper(),
                    po_revision_hash=source_hash,
                )
                self._record(line, "SHIPMENT_LINE_PLANNED", payload.reason)
            self._record(row, "SHIPMENT_PLANNED", payload.reason)
            return self._material_detail(workspace, row)

        return self._write("shipment.create", workspace, payload, key, apply)

    def transition_shipment(self, workspace, identity, payload, expected, key):
        self._material_profile(workspace, "shipment.manage")

        def apply():
            row = self._get(ProcurementShipment, workspace, identity, lock=True)
            self._version(row.version, expected)
            if payload.status not in SHIPMENT_TRANSITIONS.get(row.status, set()):
                self._error(409, "PROCUREMENT_SHIPMENT_TRANSITION_INVALID")
            if (
                payload.event_date > utc_now().date()
                or row.last_event_date
                and payload.event_date < row.last_event_date
            ):
                self._error(422, "PROCUREMENT_SHIPMENT_EVENT_DATE_INVALID")
            if payload.status == "DISPATCHED":
                for shipment_line in self.db.scalars(
                    self._material_query(ProcurementShipmentLine, workspace)
                    .where(ProcurementShipmentLine.shipment_id == row.id)
                    .order_by(ProcurementShipmentLine.po_line_id)
                ):
                    order, _, snapshot = self._material_po(workspace, shipment_line.po_line_id, lock=True)
                    if payload.event_date < order.effective_date or shipment_line.po_revision_hash != _hash(snapshot):
                        self._error(409, "PROCUREMENT_SHIPMENT_ORDER_SOURCE_CHANGED")
                row.dispatch_date = payload.event_date
            if payload.status == "ARRIVED":
                row.actual_arrival = payload.event_date
            if payload.reference:
                row.carrier_reference = payload.reference
            row.status, row.last_event_date = payload.status, payload.event_date
            self._record(row, f"SHIPMENT_{row.status}", payload.reason, changed=True)
            return self._material_detail(workspace, row)

        return self._write("shipment.transition", workspace, payload, key, apply, identity, expected)

    def create_material_receipt(self, workspace, payload, key):
        profile = self._material_profile(workspace, "receipt.record")

        def apply():
            shipment = self._get(ProcurementShipment, workspace, payload.shipment_id, lock=True)
            if shipment.status not in {"ARRIVED", "PARTIALLY_RECEIVED"}:
                self._error(409, "PROCUREMENT_ARRIVED_SHIPMENT_REQUIRED")
            stamp = payload.received_at
            stamp = stamp.astimezone(UTC).replace(tzinfo=None) if stamp.tzinfo is not None else stamp
            if stamp > utc_now() or stamp.date() < shipment.actual_arrival:
                self._error(422, "PROCUREMENT_RECEIPT_DATE_INVALID")
            if len({item.shipment_line_id for item in payload.lines}) != len(payload.lines):
                self._error(422, "PROCUREMENT_DUPLICATE_RECEIPT_SHIPMENT_LINE")
            checked = []
            for item in sorted(payload.lines, key=lambda item: item.shipment_line_id):
                shipped = self._get(ProcurementShipmentLine, workspace, item.shipment_line_id)
                if shipped.shipment_id != shipment.id or shipped.uom != item.uom.upper():
                    self._error(422, "PROCUREMENT_RECEIPT_SHIPMENT_LINE_MISMATCH")
                _, line, snapshot = self._material_po(workspace, shipped.po_line_id, lock=True)
                if shipped.uom != str(snapshot["uom"]).upper():
                    self._error(409, "PROCUREMENT_RECEIPT_ORDER_UOM_CHANGED")
                at_line = self._material_qty(
                    workspace,
                    ProcurementMaterialReceiptLine,
                    ProcurementMaterialReceiptLine.quantity,
                    ProcurementMaterialReceiptLine.shipment_line_id == shipped.id,
                )
                at_order = self._material_qty(
                    workspace,
                    ProcurementMaterialReceiptLine,
                    ProcurementMaterialReceiptLine.quantity,
                    ProcurementMaterialReceiptLine.po_line_id == line.id,
                )
                if at_line + item.quantity > shipped.quantity or at_order + item.quantity > self._overage(
                    profile, Decimal(str(snapshot["quantity"]))
                ):
                    self._error(409, "PROCUREMENT_RECEIPT_QUANTITY_EXCEEDS_ALLOWED")
                demand = self._get(ProcurementMaterialRequirement, workspace, shipped.material_requirement_id)
                checked.append((item, shipped, demand))
            row = self._material_new(
                ProcurementMaterialReceipt,
                workspace,
                receipt_number=self._code(payload.receipt_number),
                shipment_id=shipment.id,
                location=payload.location,
                received_at=stamp,
                document_reference_json=self._material_cde(workspace, payload.evidence),
            )
            for item, shipped, demand in checked:
                line = self._material_new(
                    ProcurementMaterialReceiptLine,
                    workspace,
                    receipt_id=row.id,
                    shipment_line_id=shipped.id,
                    po_line_id=shipped.po_line_id,
                    material_item_id=demand.material_item_id,
                    material_requirement_id=demand.id,
                    quantity=item.quantity,
                    uom=shipped.uom,
                )
                self._record(line, "MATERIAL_RECEIPT_LINE_RECORDED", payload.reason)
            all_lines = self.db.scalars(
                self._material_query(ProcurementShipmentLine, workspace).where(
                    ProcurementShipmentLine.shipment_id == shipment.id
                )
            )
            complete = all(
                self._material_qty(
                    workspace,
                    ProcurementMaterialReceiptLine,
                    ProcurementMaterialReceiptLine.quantity,
                    ProcurementMaterialReceiptLine.shipment_line_id == line.id,
                )
                == line.quantity
                for line in all_lines
            )
            shipment.status = "RECEIVED" if complete else "PARTIALLY_RECEIVED"
            self._record(shipment, "SHIPMENT_RECEIPT_RECORDED", payload.reason, changed=True)
            self._record(row, "MATERIAL_RECEIPT_RECORDED", payload.reason)
            return self._material_detail(workspace, row)

        return self._write("material.receipt.create", workspace, payload, key, apply)

    def accept_material_receipt(self, workspace, identity, payload, expected, key):
        profile = self._material_profile(workspace, "receipt.accept")

        def apply():
            receipt = self._get(ProcurementMaterialReceipt, workspace, identity, lock=True)
            self._version(receipt.version, expected)
            if (
                profile.get("separation_of_duties", {}).get("receiver_cannot_accept", True)
                and receipt.created_by == self.actor_id
            ):
                self._error(403, "PROCUREMENT_RECEIPT_ACCEPTANCE_SOD")
            line = self._get(ProcurementMaterialReceiptLine, workspace, payload.receipt_line_id, lock=True)
            if line.receipt_id != receipt.id:
                self._error(404, "PROCUREMENT_RECEIPT_LINE_NOT_FOUND")
            exists = self.db.scalar(
                self._material_query(ProcurementMaterialAcceptance, workspace).where(
                    ProcurementMaterialAcceptance.receipt_line_id == line.id
                )
            )
            if exists:
                self._error(409, "PROCUREMENT_MATERIAL_ACCEPTANCE_IMMUTABLE")
            if payload.accepted_quantity + payload.rejected_quantity + payload.quarantine_quantity != line.quantity:
                self._error(422, "PROCUREMENT_MATERIAL_ACCEPTANCE_PARTITION_MISMATCH")
            if payload.inspection_id is not None:
                inspection = self._get(ProcurementInspection, workspace, payload.inspection_id)
                if inspection.po_line_id != line.po_line_id or inspection.status == "PLANNED":
                    self._error(422, "PROCUREMENT_RECEIPT_INSPECTION_MISMATCH")
                if payload.accepted_quantity > 0 and inspection.status != "ACCEPTED":
                    self._error(409, "PROCUREMENT_ACCEPTED_INSPECTION_REQUIRED")
                if (
                    payload.accepted_quantity > 0
                    and profile.get("separation_of_duties", {}).get("receiver_cannot_accept", True)
                    and inspection.decided_by == receipt.created_by
                ):
                    self._error(403, "PROCUREMENT_RECEIVER_INSPECTION_ACCEPTANCE_SOD")
            elif payload.accepted_quantity > 0 and self._material_rule(
                profile, "require_inspection_for_acceptance", True
            ):
                self._error(409, "PROCUREMENT_ACCEPTED_INSPECTION_REQUIRED")
            values = payload.model_dump(exclude={"reason"})
            row = self._material_new(
                ProcurementMaterialAcceptance, workspace, **values, content_hash=material_acceptance_hash(values)
            )
            result = self._record(row, "MATERIAL_ACCEPTANCE_RECORDED", payload.reason)
            self._record(receipt, "MATERIAL_RECEIPT_LINE_DISPOSITIONED", payload.reason, changed=True)
            return self._material_detail(workspace, receipt) | {"acceptance": result}

        return self._write("material.receipt.accept", workspace, payload, key, apply, identity, expected)

    def create_material_allocation(self, workspace, payload, key):
        profile = self._material_profile(workspace, "allocation.manage")

        def apply():
            line = self._get(ProcurementMaterialReceiptLine, workspace, payload.receipt_line_id, lock=True)
            receipt = self._get(ProcurementMaterialReceipt, workspace, line.receipt_id)
            package = self._get(WorkPackage, workspace, payload.work_package_id)
            if package.package_type not in {"CWP", "IWP"} or package.status == "CANCELLED":
                self._error(422, "PROCUREMENT_MATERIAL_ALLOCATION_PACKAGE_INVALID")
            if payload.material_requirement_id != line.material_requirement_id or payload.uom.upper() != line.uom:
                self._error(422, "PROCUREMENT_MATERIAL_ALLOCATION_DEMAND_MISMATCH")
            if payload.source_location != receipt.location:
                self._error(422, "PROCUREMENT_MATERIAL_ALLOCATION_LOCATION_MISMATCH")
            if not receipt.received_at.date() <= payload.allocation_date <= utc_now().date():
                self._error(422, "PROCUREMENT_MATERIAL_ALLOCATION_DATE_INVALID")
            mappings = effective_mappings(
                self.db,
                self.tenant_id,
                workspace,
                source_kind="MATERIAL_REQUIREMENT",
                target_kind=package.package_type,
                target_id=package.id,
            )
            if not any(
                item.source_id == line.material_requirement_id and item.content_hash == _hash(mapping_content(item))
                for item in mappings
            ):
                self._error(409, "PROCUREMENT_MATERIAL_REQUIREMENT_PACKAGE_LINK_REQUIRED")
            accepted = self.db.scalar(
                self._material_query(ProcurementMaterialAcceptance, workspace).where(
                    ProcurementMaterialAcceptance.receipt_line_id == line.id
                )
            )
            if not accepted or accepted.content_hash != material_acceptance_hash(accepted):
                self._error(409, "PROCUREMENT_MATERIAL_ACCEPTED_STOCK_REQUIRED")
            if payload.allocation_date < accepted.created_at.date():
                self._error(422, "PROCUREMENT_MATERIAL_ALLOCATION_DATE_INVALID")
            reserved = sum(
                (
                    row.quantity
                    for row in active_allocations(self.db, self.tenant_id, workspace, receipt_line_id=line.id)
                ),
                Decimal(0),
            )
            if reserved + payload.quantity > accepted.accepted_quantity:
                self._error(409, "PROCUREMENT_MATERIAL_ALLOCATION_EXCEEDS_ACCEPTED")
            age = self._material_rule(profile, "availability_max_age_days", 30)
            values = payload.model_dump(exclude={"reason"}) | {
                "acceptance_id": accepted.id,
                "uom": line.uom,
                "expires_on": payload.allocation_date + timedelta(days=age) if age is not None else None,
                "state": "ACTIVE",
                "supersedes_id": None,
            }
            row = self._material_new(
                ProcurementMaterialAllocation, workspace, **values, content_hash=material_allocation_hash(values)
            )
            return self._record(row, "MATERIAL_ALLOCATED", payload.reason)

        return self._write("material.allocation.create", workspace, payload, key, apply)

    def release_material_allocation(self, workspace, identity, payload, expected, key):
        self._material_profile(workspace, "allocation.manage")

        def apply():
            row = self._get(ProcurementMaterialAllocation, workspace, identity)
            self._get(ProcurementMaterialReceiptLine, workspace, row.receipt_line_id, lock=True)
            self._version(row.version, expected)
            if row.state != "ACTIVE" or self.db.scalar(
                self._material_query(ProcurementMaterialAllocation, workspace).where(
                    ProcurementMaterialAllocation.supersedes_id == row.id
                )
            ):
                self._error(409, "PROCUREMENT_MATERIAL_ALLOCATION_ALREADY_RELEASED")
            values = {
                field: getattr(row, field)
                for field in (
                    "receipt_line_id",
                    "material_requirement_id",
                    "work_package_id",
                    "quantity",
                    "uom",
                    "source_location",
                    "acceptance_id",
                    "expires_on",
                )
            }
            values |= {"allocation_date": utc_now().date(), "state": "RELEASED", "supersedes_id": row.id}
            successor = self._material_new(
                ProcurementMaterialAllocation,
                workspace,
                **values,
                version=row.version + 1,
                content_hash=material_allocation_hash(values),
            )
            return self._record(successor, "MATERIAL_ALLOCATION_RELEASED", payload.reason)

        return self._write("material.allocation.release", workspace, payload, key, apply, identity, expected)

    def get_material_availability(self, workspace, package_id, as_of=None):
        self._read_project(workspace)
        package = self._get(WorkPackage, workspace, package_id)
        if package.package_type not in {"CWP", "IWP"}:
            self._error(422, "PROCUREMENT_MATERIAL_AVAILABILITY_PACKAGE_INVALID")
        result = material_availability(self.db, self.tenant_id, workspace, package_id, as_of)
        if result is None:
            return {
                "provider_key": "MATERIAL_AVAILABILITY_PROVIDER",
                "work_package_id": package_id,
                "status": "NOT_READY",
                "requirements": [],
                "reason_codes": ["MATERIAL_REQUIREMENTS_NOT_MAPPED"],
            }
        return result
