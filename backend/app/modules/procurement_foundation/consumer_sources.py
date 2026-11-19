"""Canonical, read-only O2B facts for explicit cross-domain consumer pins."""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from hmac import compare_digest

from fastapi import HTTPException
from sqlalchemy import select

from app.core.time import utc_now
from app.modules.basic_data.service import _hash
from app.modules.procurement_foundation.availability import _quantity, material_acceptance_hash
from app.modules.procurement_foundation.integration import TARGET_MODELS, mapping_content, mapping_key
from app.modules.procurement_foundation.integration_models import ProcurementMapping
from app.modules.procurement_foundation.materials_models import (
    ProcurementExpeditingEvent,
    ProcurementInspection,
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
    ProcurementAward,
    ProcurementBid,
    ProcurementHistory,
    ProcurementPackage,
    ProcurementPurchaseOrder,
    ProcurementPurchaseOrderLine,
    ProcurementPurchaseOrderRevision,
    ProcurementRequirement,
    ProcurementRFQ,
    ProcurementVendor,
)
from app.modules.scope_foundation.models import ScopeBaseline

CONSUMER_SOURCE_TYPES = {
    "COST": frozenset({"PACKAGE", "AWARD", "PO", "PO_REVISION", "VENDOR"}),
    "PROGRESS": frozenset({"ACCEPTED_INSPECTION", "DISPATCH", "ARRIVAL", "RECEIPT", "ACCEPTANCE"}),
    "FORECAST": frozenset(
        {
            "PACKAGE_FORECAST",
            "PO_FORECAST",
            "MILESTONE_FORECAST",
            "INSPECTION_FORECAST",
            "SHIPMENT_FORECAST",
            "EXPEDITING_FORECAST",
            "REQUIRED_ON_SITE",
            "MATERIAL_AVAILABILITY_FORECAST",
        }
    ),
    # Keep the legacy default authority selection intact; Contracts opts in explicitly.
    "CONTRACTS": frozenset({"PACKAGE", "AWARD", "PO", "PO_REVISION", "VENDOR"}),
}
COST_TARGETS = frozenset({"CBS", "COST_CODE", "CONTROL_ACCOUNT"})
PROGRESS_TARGETS = frozenset({"SCOPE", "PLAN", "IWP"})
ACTIVE_SHIPMENTS = frozenset({"PLANNED", "READY_FOR_DISPATCH", "DISPATCHED", "IN_TRANSIT"})


def _error(status, code):
    raise HTTPException(status, f"PROCUREMENT_CONSUMER_{code}")


def _utc(value):
    if not isinstance(value, datetime):
        _error(409, "INVALID_OBSERVATION")
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo is not None else value


def _cutoff(value, now):
    if value is None:
        return now
    try:
        if isinstance(value, str):
            value = date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value)
        if isinstance(value, datetime):
            instant = _utc(value)
        elif isinstance(value, date) and value <= now.date():
            instant = min(datetime.combine(value, time.max), now)
        else:
            raise ValueError
    except (ValueError, OverflowError):
        _error(422, "INVALID_AS_OF")
    if instant > now:
        _error(422, "INVALID_AS_OF")
    return instant


def _iso_stamp(value):
    return _utc(value).replace(tzinfo=UTC).isoformat()


def _signals(**dates):
    return {key: value.isoformat() for key, value in dates.items() if value is not None}


@dataclass
class _Fact:
    package: ProcurementPackage
    version: int
    observed_at: datetime
    effective_date: date
    facts: dict
    source_refs: set[tuple[str, int]] = field(default_factory=set)


class _Resolver:
    def __init__(self, db, tenant, workspace, kind, identity, package_id, now, cutoff, max_age_days):
        self.db, self.tenant, self.workspace = db, tenant, workspace
        self.kind, self.identity, self.package_id = kind, identity, package_id
        self.now, self.cutoff, self.max_age_days = now, cutoff, max_age_days

    def query(self, model):
        q = select(model).where(model.tenant_id == self.tenant)
        if model is not ProcurementVendor:
            q = q.where(model.project_workspace_id == self.workspace)
        return q

    def get(self, model, identity, *, source=False):
        row = self.db.scalar(self.query(model).where(model.id == identity))
        if row is None:
            _error(404, "SOURCE_NOT_FOUND") if source else _error(409, "BROKEN_SOURCE_LINEAGE")
        return row

    def source(self, model):
        return self.get(model, self.identity, source=True)

    def observe(self, stamp):
        observed = _utc(stamp)
        if observed > self.cutoff:
            _error(409, "SOURCE_NOT_YET_OBSERVED")
        return observed

    def actual(self, day, observed):
        if not isinstance(day, date) or day > self.observe(observed).date():
            _error(409, "INVALID_EFFECTIVE_DATE")
        return day

    def history(self, row, *events):
        model = ProcurementHistory
        q = self.query(model).where(model.entity_type == type(row).__name__, model.entity_id == row.id)
        if events:
            q = q.where(model.event_type.in_(events))
        return self.db.scalar(q.order_by(model.id.desc()).limit(1))

    def package(self, identity, *, source=False, historical=False):
        row = self.get(ProcurementPackage, identity, source=source)
        if row.status not in ({"PLANNED", "CLOSED"} if historical else {"PLANNED"}):
            _error(409, "PACKAGE_NOT_ACTIVE")
        self.observe(row.created_at)
        return row

    def scoped_package(self, packages):
        if not packages or self.package_id is not None and self.package_id not in packages:
            _error(404, "SOURCE_NOT_FOUND")
        if self.package_id is None and len(packages) != 1:
            _error(422, "PACKAGE_CONTEXT_REQUIRED")
        return self.package_id or next(iter(packages))

    def order(self, row, *, physical=False):
        package = self.package(row.package_id, historical=physical)
        if row.status != "ISSUED" or not row.current_revision_id:
            _error(409, "PO_NOT_ISSUED")
        revision = self.get(ProcurementPurchaseOrderRevision, row.current_revision_id)
        if (
            revision.purchase_order_id != row.id
            or revision.status != "APPROVED"
            or revision.content_hash != _hash(po_revision_material(revision))
            or revision.total_value != row.current_value
            or revision.effective_date > self.now.date()
        ):
            _error(409, "PO_REVISION_INVALID")
        if not physical:
            self.observe(row.updated_at)
            self.observe(revision.updated_at)
            if max(row.issue_date, row.effective_date, revision.effective_date) > self.cutoff.date():
                _error(409, "INVALID_EFFECTIVE_DATE")
        return package, revision

    def po_line(self, identity, *, physical=False):
        line = self.get(ProcurementPurchaseOrderLine, identity)
        order = self.get(ProcurementPurchaseOrder, line.purchase_order_id)
        package, revision = self.order(order, physical=physical)
        requirement = self.get(ProcurementRequirement, line.requirement_id)
        current = [value for value in revision.lines_snapshot if value.get("line_id") == line.id]
        if (
            requirement.package_id != package.id
            or requirement.status != "ACTIVE"
            or len(current) != 1
            or current[0].get("uom") != line.uom
        ):
            _error(409, "REQUIREMENT_NOT_ACTIVE")
        return line, order, package, revision

    def material(self, identity, *, source=False, historical=False):
        demand = self.get(ProcurementMaterialRequirement, identity, source=source)
        requirement = self.get(ProcurementRequirement, demand.procurement_requirement_id)
        item = self.get(ProcurementMaterialItem, demand.material_item_id)
        if requirement.status != "ACTIVE" or not (requirement.uom == demand.uom == item.uom):
            _error(409, "MATERIAL_REQUIREMENT_INVALID")
        return demand, requirement, self.package(requirement.package_id, historical=historical)

    def mapping_rows(self, refs, targets):
        model = ProcurementMapping
        selected = []
        for kind, identity in sorted(refs):
            q = self.query(model).where(
                model.source_kind == kind,
                model.source_id == identity,
                model.target_kind.in_(targets),
                model.created_at <= self.now,
                model.effective_date <= self.now.date(),
            )
            rows = list(self.db.scalars(q.order_by(model.version, model.id)))
            current = {mapping_key(row): row for row in rows}
            observed = {
                mapping_key(row): row
                for row in rows
                if _utc(row.created_at) <= self.cutoff and row.effective_date <= self.cutoff.date()
            }
            for key, row in observed.items():
                if row.action != "SET":
                    continue
                if current[key].id != row.id:
                    _error(409, "MAPPING_SUPERSEDED")
                selected.append(self.mapping(row))
        return sorted(selected, key=lambda item: item["id"])

    def mapping(self, row):
        if row.content_hash != _hash(mapping_content(row)):
            _error(409, "BROKEN_MAPPING")
        target = self.get(TARGET_MODELS[row.target_kind], row.target_id)
        snapshot = row.target_snapshot_json
        kind = row.target_kind
        if snapshot.get("target_id") != target.id or snapshot.get("target_kind") != kind:
            _error(409, "BROKEN_MAPPING")
        if kind in COST_TARGETS:
            current = {
                "target_kind": kind,
                "target_id": target.id,
                "target_version": target.version,
                "code": target.code,
                "title": target.name,
            }
            if target.status != "ACTIVE" or snapshot.get("source_hash") != _hash(current):
                _error(409, "STALE_COST_MAPPING")
        elif kind == "IWP" and (target.package_type != "IWP" or target.status in {"CANCELLED", "SUPERSEDED"}):
            _error(409, "INACTIVE_IWP_MAPPING")
        elif kind == "PLAN" and target.status != "PUBLISHED":
            _error(409, "INACTIVE_PLAN_MAPPING")
        elif kind == "SCOPE":
            baseline = self.db.scalar(self.query(ScopeBaseline).order_by(ScopeBaseline.revision.desc()).limit(1))
            if (
                not baseline
                or _utc(baseline.approved_at) > self.cutoff
                or not any(item.get("id") == target.id for item in baseline.snapshot_json.get("items", []))
            ):
                _error(409, "INACTIVE_SCOPE_MAPPING")
        return {
            "id": row.id,
            "version": row.version,
            "content_hash": row.content_hash,
            "source_kind": row.source_kind,
            "source_id": row.source_id,
            "target_kind": kind,
            "target_id": target.id,
            "target_version": snapshot.get("target_version"),
            "effective_date": row.effective_date.isoformat(),
        }

    def package_fact(self):
        row = self.package(self.identity, source=True)
        observed = self.observe(row.updated_at)
        facts = {"package_code": row.package_code, "title": row.title, "status": row.status}
        if self.kind == "PACKAGE_FORECAST":
            facts["signals"] = _signals(
                planned_award_date=row.planned_award_date,
                planned_po_date=row.planned_po_date,
                forecast_delivery_date=row.forecast_delivery_date,
                required_on_site_date=row.required_on_site_date,
            )
        return _Fact(row, row.version, observed, observed.date(), facts)

    def award_fact(self):
        row = self.source(ProcurementAward)
        package = self.package(row.package_id)
        rfq = self.get(ProcurementRFQ, row.rfq_id)
        bid = self.get(ProcurementBid, row.bid_id)
        vendor = self.get(ProcurementVendor, row.vendor_id)
        snapshot = row.snapshot_json
        if (
            row.decision != "AWARDED"
            or vendor.status != "ACTIVE"
            or rfq.package_id != package.id
            or bid.rfq_id != rfq.id
            or bid.vendor_id != vendor.id
            or _hash(snapshot) != row.content_hash
            or snapshot.get("bid_hash") != bid.content_hash
            or any(snapshot.get(key) != getattr(row, key) for key in ("rfq_id", "bid_id", "package_id", "vendor_id"))
        ):
            _error(409, "AWARD_INVALID")
        return _Fact(
            package,
            row.version,
            row.created_at,
            self.actual(row.decision_date, row.created_at),
            {
                "rfq_id": rfq.id,
                "vendor_id": vendor.id,
                "bid_id": bid.id,
                "currency": snapshot.get("currency"),
                "award_value": snapshot.get("award_value"),
                "status": row.decision,
                "native_hash": row.content_hash,
            },
        )

    def order_fact(self):
        if self.kind == "PO_REVISION":
            source = self.source(ProcurementPurchaseOrderRevision)
            row = self.get(ProcurementPurchaseOrder, source.purchase_order_id)
        else:
            row = source = self.source(ProcurementPurchaseOrder)
        package, revision = self.order(row)
        if self.kind == "PO_REVISION" and revision.id != source.id:
            _error(409, "PO_REVISION_SUPERSEDED")
        vendor = self.get(ProcurementVendor, row.vendor_id)
        if vendor.status != "ACTIVE":
            _error(409, "VENDOR_NOT_ACTIVE")
        observed = max(self.observe(row.updated_at), self.observe(revision.updated_at))
        effective = max(row.issue_date, row.effective_date, revision.effective_date)
        if effective > self.cutoff.date():
            _error(409, "INVALID_EFFECTIVE_DATE")
        self.actual(row.issue_date, observed)
        facts = {
            "po_id": row.id,
            "po_number": row.po_number,
            "status": row.status,
            "vendor_id": row.vendor_id,
            "award_id": row.award_id,
            "currency": row.currency,
            "original_value": _quantity(row.original_value),
            "current_value": _quantity(row.current_value),
            "revision_id": revision.id,
            "revision_number": revision.revision,
            "revision_hash": revision.content_hash,
        }
        if self.kind == "PO_FORECAST":
            facts["signals"] = _signals(expected_delivery_date=row.expected_delivery_date)
            facts["line_schedule_signals"] = [
                {
                    "po_line_id": item["line_id"],
                    **{key: item[key] for key in ("promised_date", "forecast_date") if item.get(key) is not None},
                }
                for item in revision.lines_snapshot
                if item.get("promised_date") or item.get("forecast_date")
            ]
        return _Fact(package, source.version, observed, effective, facts)

    def vendor_fact(self):
        row = self.source(ProcurementVendor)
        order = ProcurementPurchaseOrder
        award = ProcurementAward
        packages = {
            item.package_id
            for model, eligibility in ((order, order.status == "ISSUED"), (award, award.decision == "AWARDED"))
            for item in self.db.scalars(
                self.query(model).where(
                    model.vendor_id == row.id,
                    eligibility,
                    model.created_at <= self.cutoff,
                )
            )
        }
        package = self.package(self.scoped_package(packages))
        if row.status != "ACTIVE":
            _error(409, "VENDOR_NOT_ACTIVE")
        model = ProcurementHistory
        event = self.db.scalar(
            self.query(model)
            .where(
                model.entity_type == type(row).__name__,
                model.entity_id == row.id,
                model.entity_version == row.version,
            )
            .order_by(model.id.desc())
            .limit(1)
        )
        if row.version != 1 and event is None:
            _error(409, "INVALID_OBSERVATION")
        observed = self.observe(event.created_at if event else row.created_at)
        return _Fact(
            package,
            row.version,
            observed,
            observed.date(),
            {
                "vendor_code": row.vendor_code,
                "display_name": row.display_name,
                "legal_name": row.legal_name,
                "status": row.status,
            },
        )

    def inspection_fact(self):
        row = self.source(ProcurementInspection)
        forecast = self.kind == "INSPECTION_FORECAST"
        line, order, package, revision = self.po_line(row.po_line_id, physical=not forecast)
        if row.vendor_id != order.vendor_id or row.status != ("PLANNED" if forecast else "ACCEPTED"):
            _error(409, "INSPECTION_STATE_INVALID")
        facts = {
            "status": row.status,
            "po_id": order.id,
            "po_line_id": line.id,
            "vendor_id": row.vendor_id,
            "inspection_type": row.inspection_type,
        }
        if forecast:
            observed = self.observe(row.created_at)
            facts |= {
                "signals": _signals(inspection_date=row.inspection_date),
                "po_revision_id": revision.id,
                "po_revision_hash": revision.content_hash,
            }
            effective = observed.date()
        else:
            observed = self.observe(row.decided_at)
            if not row.decided_by:
                _error(409, "INSPECTION_STATE_INVALID")
            effective = self.actual(row.inspection_date, observed)
            facts["evidence_type"] = "INSPECTION_ACCEPTED"
            facts["document_pin_hash"] = _hash(row.document_reference_json)
        return _Fact(package, row.version, observed, effective, facts, {("REQUIREMENT", line.requirement_id)})

    def shipment_lines(self, row, *, forecast=False):
        model = ProcurementShipmentLine
        result = []
        for item in self.db.scalars(self.query(model).where(model.shipment_id == row.id).order_by(model.id)):
            line, order, package, revision = self.po_line(item.po_line_id, physical=not forecast)
            demand, requirement, _ = self.material(item.material_requirement_id, historical=not forecast)
            if order.vendor_id != row.vendor_id or line.requirement_id != requirement.id or item.uom != demand.uom:
                _error(409, "BROKEN_SHIPMENT_LINEAGE")
            if forecast:
                self.check_shipment_pin(item, line, revision)
            result.append((item, line, package))
        return result

    @staticmethod
    def check_shipment_pin(item, line, revision):
        snapshot = next((value for value in revision.lines_snapshot if value.get("line_id") == line.id), None)
        if snapshot is None or item.po_revision_hash != _hash(snapshot):
            _error(409, "SHIPMENT_PO_LINE_CHANGED")

    def shipment_forecast(self, row):
        event = self.history(row)
        if (
            row.status not in ACTIVE_SHIPMENTS
            or row.actual_arrival is not None
            or event is None
            or event.entity_version != row.version
            or not row.forecast_arrival
        ):
            _error(409, "SHIPMENT_FORECAST_NOT_CURRENT")
        self.observe(event.created_at)
        # Dispatch/transit status does not refresh the ETA's observation date.
        forecast_event = self.history(row, "SHIPMENT_PLANNED")
        if forecast_event is None:
            _error(409, "SHIPMENT_FORECAST_NOT_RECORDED")
        observed = self.observe(forecast_event.created_at)
        expected = row.forecast_arrival.isoformat()
        if (
            event.snapshot_json.get("forecast_arrival") != expected
            or forecast_event.snapshot_json.get("forecast_arrival") != expected
            or row.forecast_arrival < max(day for day in (observed.date(), row.dispatch_date) if day)
        ):
            _error(409, "SHIPMENT_FORECAST_DATE_INVALID")
        self.fresh(observed)
        return observed

    def shipment_fact(self):
        row = self.source(ProcurementShipment)
        forecast = self.kind == "SHIPMENT_FORECAST"
        if row.status == "CANCELLED":
            _error(409, "SHIPMENT_NOT_ACTIVE")
        lines = self.shipment_lines(row, forecast=forecast)
        package_id = self.scoped_package({package.id for _, _, package in lines})
        package = self.package(package_id, historical=not forecast)
        lines = [(item, line) for item, line, owner in lines if owner.id == package_id]
        facts = {
            "shipment_number": row.shipment_number,
            "vendor_id": row.vendor_id,
            "lines": [
                {
                    "shipment_line_id": item.id,
                    "po_line_id": line.id,
                    "quantity": _quantity(item.quantity),
                    "uom": item.uom,
                    "material_requirement_id": item.material_requirement_id,
                    "po_line_source_hash": item.po_revision_hash,
                }
                for item, line in lines
            ],
        }
        refs = {("REQUIREMENT", line.requirement_id) for _, line in lines}
        refs.update(("MATERIAL_REQUIREMENT", item.material_requirement_id) for item, _ in lines)
        if forecast:
            observed = self.shipment_forecast(row)
            facts["signals"] = _signals(
                planned_arrival=row.planned_arrival,
                forecast_arrival=row.forecast_arrival,
            )
            return _Fact(package, row.version, observed, observed.date(), facts, refs)
        field_name, event_type = (
            ("dispatch_date", "SHIPMENT_DISPATCHED")
            if self.kind == "DISPATCH"
            else ("actual_arrival", "SHIPMENT_ARRIVED")
        )
        event = self.history(row, event_type)
        if event is None or getattr(row, field_name) is None:
            _error(409, "SHIPMENT_EVENT_NOT_RECORDED")
        effective = self.actual(getattr(row, field_name), event.created_at)
        if (
            event.snapshot_json.get(field_name) != effective.isoformat()
            or event.snapshot_json.get("version") != event.entity_version
            or self.kind == "ARRIVAL"
            and (not row.dispatch_date or row.dispatch_date > effective)
        ):
            _error(409, "SHIPMENT_EVENT_INVALID")
        facts |= {"evidence_type": self.kind, "source_event_id": event.id, field_name: effective.isoformat()}
        return _Fact(package, event.entity_version, event.created_at, effective, facts, refs)

    def receipt_line(self, item, receipt):
        shipment_line = self.get(ProcurementShipmentLine, item.shipment_line_id)
        po_line, order, package, _ = self.po_line(item.po_line_id, physical=True)
        demand, requirement, _ = self.material(item.material_requirement_id, historical=True)
        shipment = self.get(ProcurementShipment, receipt.shipment_id)
        if (
            shipment_line.shipment_id != receipt.shipment_id
            or shipment_line.po_line_id != po_line.id
            or shipment_line.material_requirement_id != demand.id
            or demand.material_item_id != item.material_item_id
            or requirement.id != po_line.requirement_id
            or order.vendor_id != shipment.vendor_id
            or not (item.uom == shipment_line.uom == demand.uom)
            or shipment.status not in {"PARTIALLY_RECEIVED", "RECEIVED"}
            or shipment.actual_arrival is None
            or shipment.actual_arrival > _utc(receipt.received_at).date()
        ):
            _error(409, "BROKEN_RECEIPT_LINEAGE")
        return (
            package,
            {
                "receipt_line_id": item.id,
                "shipment_line_id": shipment_line.id,
                "po_line_id": po_line.id,
                "received_quantity": _quantity(item.quantity),
                "uom": item.uom,
                "material_requirement_id": demand.id,
            },
            {("REQUIREMENT", requirement.id), ("MATERIAL_REQUIREMENT", demand.id), ("RECEIPT", receipt.id)},
        )

    def receipt_fact(self):
        row = self.source(ProcurementMaterialReceipt)
        event = self.history(row, "MATERIAL_RECEIPT_RECORDED")
        if event is None:
            _error(409, "RECEIPT_EVENT_NOT_RECORDED")
        recorded = self.observe(event.created_at)
        received = self.observe(row.received_at)
        if received > recorded:
            _error(409, "INVALID_RECEIPT_DATE")
        model = ProcurementMaterialReceiptLine
        lines = [
            self.receipt_line(item, row)
            for item in self.db.scalars(self.query(model).where(model.receipt_id == row.id).order_by(model.id))
        ]
        package = self.package(self.scoped_package({owner.id for owner, _, _ in lines}), historical=True)
        selected = [(facts, refs) for owner, facts, refs in lines if owner.id == package.id]
        return _Fact(
            package,
            event.entity_version,
            recorded,
            received.date(),
            {
                "receipt_number": row.receipt_number,
                "shipment_id": row.shipment_id,
                "evidence_type": "RECEIPT_RECORDED",
                "received_at": _iso_stamp(received),
                "lines": [facts for facts, _ in selected],
            },
            set().union(*(refs for _, refs in selected)),
        )

    def acceptance_fact(self):
        row = self.source(ProcurementMaterialAcceptance)
        line = self.get(ProcurementMaterialReceiptLine, row.receipt_line_id)
        receipt = self.get(ProcurementMaterialReceipt, line.receipt_id)
        package, facts, refs = self.receipt_line(line, receipt)
        observed = self.observe(row.created_at)
        quantities = {
            "accepted_quantity": row.accepted_quantity,
            "rejected_quantity": row.rejected_quantity,
            "quarantine_quantity": row.quarantine_quantity,
        }
        if (
            material_acceptance_hash(row) != row.content_hash
            or min(quantities.values()) < 0
            or sum(quantities.values()) != line.quantity
            or _utc(receipt.received_at) > observed
        ):
            _error(409, "MATERIAL_ACCEPTANCE_INVALID")
        if row.inspection_id is not None:
            inspection = self.get(ProcurementInspection, row.inspection_id)
            if (
                inspection.po_line_id != line.po_line_id
                or inspection.status == "PLANNED"
                or inspection.decided_at is None
                or _utc(inspection.decided_at) > observed
                or row.accepted_quantity > 0
                and inspection.status != "ACCEPTED"
            ):
                _error(409, "MATERIAL_ACCEPTANCE_INSPECTION_INVALID")
        return _Fact(
            package,
            row.version,
            observed,
            observed.date(),
            facts
            | {
                "receipt_id": receipt.id,
                "inspection_id": row.inspection_id,
                "native_hash": row.content_hash,
                "evidence_type": "MATERIAL_DISPOSITION_RECORDED",
                "classifications": [
                    key.removesuffix("_quantity").upper() for key, qty in quantities.items() if qty > 0
                ],
                **{key: _quantity(qty) for key, qty in quantities.items()},
            },
            refs,
        )

    def fresh(self, observed):
        if (self.now.date() - self.observe(observed).date()).days > self.max_age_days:
            _error(409, "FORECAST_OBSERVATION_STALE")

    def milestone_fact(self):
        row = self.source(ProcurementVendorMilestone)
        model = ProcurementVendorMilestone
        if self.db.scalar(self.query(model).where(model.supersedes_id == row.id).limit(1)):
            _error(409, "MILESTONE_SUPERSEDED")
        line, order, package, revision = self.po_line(row.po_line_id)
        observed = self.observe(row.created_at)
        native = {
            key: getattr(row, key)
            for key in (
                "po_line_id",
                "code",
                "planned_date",
                "forecast_date",
                "actual_date",
                "supersedes_id",
                "version",
            )
        }
        if (
            row.actual_date
            or not row.forecast_date
            or row.forecast_date < observed.date()
            or _hash(native) != row.content_hash
        ):
            _error(409, "MILESTONE_FORECAST_INVALID")
        return _Fact(
            package,
            row.version,
            observed,
            observed.date(),
            {
                "milestone_code": row.code,
                "po_id": order.id,
                "po_line_id": line.id,
                "po_revision_id": revision.id,
                "po_revision_hash": revision.content_hash,
                "native_hash": row.content_hash,
                "signals": _signals(planned_date=row.planned_date, forecast_date=row.forecast_date),
            },
        )

    def expediting_fact(self):
        row = self.source(ProcurementExpeditingEvent)
        model = ProcurementExpeditingEvent
        newest = self.db.scalar(
            self.query(model)
            .where(
                model.po_line_id == row.po_line_id,
                model.event_type == row.event_type,
            )
            .order_by(model.observation_date.desc(), model.id.desc())
            .limit(1)
        )
        if newest.id != row.id:
            _error(409, "EXPEDITING_FORECAST_SUPERSEDED")
        line, order, package, revision = self.po_line(row.po_line_id)
        observed = self.observe(row.created_at)
        if (
            not row.forecast_date
            or row.observation_date > observed.date()
            or row.forecast_date < max(row.observation_date, observed.date())
        ):
            _error(409, "EXPEDITING_FORECAST_INVALID")
        if (self.now.date() - row.observation_date).days > self.max_age_days:
            _error(409, "FORECAST_OBSERVATION_STALE")
        return _Fact(
            package,
            row.version,
            observed,
            row.observation_date,
            {
                "event_type": row.event_type,
                "po_id": order.id,
                "po_line_id": line.id,
                "po_revision_id": revision.id,
                "po_revision_hash": revision.content_hash,
                "native_hash": row.content_hash,
                "signals": _signals(forecast_date=row.forecast_date),
            },
        )

    def required_on_site_fact(self):
        demand, requirement, package = self.material(self.identity, source=True)
        event = self.history(demand)
        observed = self.observe(event.created_at if event else demand.created_at)
        required = demand.required_on_site_date
        if not required:
            _error(409, "REQUIRED_ON_SITE_NOT_RECORDED")
        return _Fact(
            package,
            demand.version,
            observed,
            observed.date(),
            {
                "requirement_id": requirement.id,
                "signals": _signals(required_on_site_date=required),
            },
        )

    def material_forecast_fact(self):
        demand, requirement, package = self.material(self.identity, source=True)
        model = ProcurementShipmentLine
        self.observe(demand.created_at)
        demand_event = self.history(demand)
        if demand_event:
            self.observe(demand_event.created_at)
        candidates = []
        for item in self.db.scalars(self.query(model).where(model.material_requirement_id == demand.id)):
            shipment = self.get(ProcurementShipment, item.shipment_id)
            if shipment.status not in ACTIVE_SHIPMENTS or not shipment.forecast_arrival:
                continue
            line, order, _, revision = self.po_line(item.po_line_id)
            if line.requirement_id != requirement.id or item.uom != demand.uom or shipment.vendor_id != order.vendor_id:
                _error(409, "BROKEN_SHIPMENT_LINEAGE")
            self.check_shipment_pin(item, line, revision)
            arrival_observed = self.shipment_forecast(shipment)
            candidates.append((shipment, item, arrival_observed))
        if sum(item.quantity for _, item, _ in candidates) < demand.required_quantity:
            _error(409, "MATERIAL_FORECAST_COVERAGE_MISSING")
        # Arrival is only a conditional planning signal. It never implies receipt, acceptance, or allocation.
        selected = []
        covered = Decimal(0)
        observed = None
        for shipment, item, stamp in sorted(candidates, key=lambda value: (value[0].forecast_arrival, value[1].id)):
            observed = stamp if observed is None else max(observed, stamp)
            covered += item.quantity
            selected.append(
                {
                    "shipment_id": shipment.id,
                    "shipment_version": shipment.version,
                    "shipment_line_id": item.id,
                    "po_line_source_hash": item.po_revision_hash,
                    "quantity": _quantity(item.quantity),
                    "forecast_arrival": shipment.forecast_arrival.isoformat(),
                }
            )
            if covered >= demand.required_quantity:
                break
        return _Fact(
            package,
            demand.version,
            observed,
            observed.date(),
            {
                "signals": {"conditional_material_availability_forecast_date": selected[-1]["forecast_arrival"]},
                "availability_is_conditional": True,
                "requires_receipt_acceptance_allocation": True,
                "required_quantity": _quantity(demand.required_quantity),
                "uom": demand.uom,
                "shipment_sources": selected,
            },
        )


_METHODS = {
    "PACKAGE": _Resolver.package_fact,
    "PACKAGE_FORECAST": _Resolver.package_fact,
    "AWARD": _Resolver.award_fact,
    "PO": _Resolver.order_fact,
    "PO_REVISION": _Resolver.order_fact,
    "PO_FORECAST": _Resolver.order_fact,
    "VENDOR": _Resolver.vendor_fact,
    "ACCEPTED_INSPECTION": _Resolver.inspection_fact,
    "INSPECTION_FORECAST": _Resolver.inspection_fact,
    "DISPATCH": _Resolver.shipment_fact,
    "ARRIVAL": _Resolver.shipment_fact,
    "SHIPMENT_FORECAST": _Resolver.shipment_fact,
    "RECEIPT": _Resolver.receipt_fact,
    "ACCEPTANCE": _Resolver.acceptance_fact,
    "MILESTONE_FORECAST": _Resolver.milestone_fact,
    "EXPEDITING_FORECAST": _Resolver.expediting_fact,
    "REQUIRED_ON_SITE": _Resolver.required_on_site_fact,
    "MATERIAL_AVAILABILITY_FORECAST": _Resolver.material_forecast_fact,
}


def resolve_procurement_source(
    db,
    tenant_id,
    workspace_id,
    source_type,
    source_id,
    *,
    consumer=None,
    as_of=None,
    expected_version=None,
    expected_hash=None,
    package_id=None,
    max_age_days=30,
):
    """Resolve current scoped facts without writes; an as-of cutoff cannot resurrect a superseded source.

    Authorization and the consumer's decision to create a pin are intentionally not part of this reader.
    """
    if (
        source_type not in _METHODS
        or consumer is not None
        and source_type not in CONSUMER_SOURCE_TYPES.get(consumer, ())
    ):
        _error(422, "SOURCE_TYPE_INVALID")
    ids = (tenant_id, workspace_id, source_id, *(() if package_id is None else (package_id,)))
    if any(type(value) is not int or value < 1 for value in ids):
        _error(422, "SOURCE_ID_INVALID")
    if expected_version is not None and (type(expected_version) is not int or expected_version < 1):
        _error(422, "SOURCE_VERSION_INVALID")
    if expected_hash is not None and (
        not isinstance(expected_hash, str) or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None
    ):
        _error(422, "SOURCE_HASH_INVALID")
    if type(max_age_days) is not int or not 0 <= max_age_days <= 3650:
        _error(422, "FORECAST_MAX_AGE_INVALID")
    authority = consumer or next(key for key, values in CONSUMER_SOURCE_TYPES.items() if source_type in values)
    now = _utc(utc_now())
    reader = _Resolver(
        db, tenant_id, workspace_id, source_type, source_id, package_id, now, _cutoff(as_of, now), max_age_days
    )
    with db.no_autoflush:
        fact = _METHODS[source_type](reader)
        if package_id is not None and fact.package.id != package_id:
            _error(404, "SOURCE_NOT_FOUND")
        reader.observe(fact.observed_at)
        if authority == "FORECAST":
            reader.fresh(fact.observed_at)
            if not fact.facts.get("signals"):
                _error(409, "FORECAST_SIGNAL_NOT_RECORDED")
        if expected_version is not None and fact.version != expected_version:
            _error(409, "SOURCE_VERSION_MISMATCH")
        package_ref = {("PACKAGE", fact.package.id)}
        value = {
            "source_domain": "PROCUREMENT",
            "source_type": source_type,
            "source_id": source_id,
            "source_version": fact.version,
            "package_id": fact.package.id,
            "observed_at": _iso_stamp(fact.observed_at),
            "effective_date": fact.effective_date.isoformat(),
            "facts": fact.facts,
            "cost_mappings": reader.mapping_rows(package_ref, COST_TARGETS) if authority == "COST" else [],
            "related_mappings": reader.mapping_rows(package_ref | fact.source_refs, PROGRESS_TARGETS)
            if authority == "PROGRESS"
            else [],
        }
    digest = _hash({"tenant_id": tenant_id, "project_workspace_id": workspace_id, **value})
    if expected_hash is not None and not compare_digest(digest, expected_hash):
        _error(409, "SOURCE_HASH_MISMATCH")
    return value | {"source_hash": digest}
