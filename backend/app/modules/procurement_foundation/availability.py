"""Read-only dated provider; physical evidence never changes an AWP package."""

from datetime import date
from decimal import Decimal

from sqlalchemy import inspect

from app.domain.models import Document, DocumentAttachment
from app.modules.awp.models import WorkPackage
from app.modules.basic_data.service import _hash
from app.modules.engineering_foundation.integration import (
    _cde_binding,
    _cde_reference,
    _cde_rows,
    _observed_at,
    _scoped,
    _sha_eligible,
)
from app.modules.procurement_foundation.integration import effective_mappings, mapping_content
from app.modules.procurement_foundation.integration_models import ProcurementMapping
from app.modules.procurement_foundation.materials_models import (
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
from app.modules.procurement_foundation.sourcing_models import (
    ProcurementHistory,
    ProcurementPurchaseOrder,
    ProcurementPurchaseOrderLine,
    ProcurementPurchaseOrderRevision,
    ProcurementRequirement,
)

ACCEPTANCE_FIELDS = (
    "receipt_line_id",
    "inspection_id",
    "accepted_quantity",
    "rejected_quantity",
    "quarantine_quantity",
    "detail",
)
ALLOCATION_FIELDS = (
    "receipt_line_id",
    "acceptance_id",
    "material_requirement_id",
    "work_package_id",
    "quantity",
    "uom",
    "allocation_date",
    "expires_on",
    "source_location",
    "state",
    "supersedes_id",
)


def _quantity(value):
    return format(Decimal(str(value)).normalize(), "f")


def _fact_hash(row, fields):
    material = {key: row[key] if isinstance(row, dict) else getattr(row, key) for key in fields}
    for key in material:
        if key.endswith("quantity"):
            material[key] = _quantity(material[key])
    return _hash(material)


def material_acceptance_hash(row):
    return _fact_hash(row, ACCEPTANCE_FIELDS)


def material_allocation_hash(row):
    return _fact_hash(row, ALLOCATION_FIELDS)


def active_allocations(db, tenant, workspace, *, receipt_line_id=None, requirement_id=None, as_of=None):
    instant = _observed_at(as_of)
    model = ProcurementMaterialAllocation
    statement = _scoped(model, tenant, workspace).where(
        model.created_at <= instant, model.allocation_date <= instant.date()
    )
    if receipt_line_id is not None:
        statement = statement.where(model.receipt_line_id == receipt_line_id)
    if requirement_id is not None:
        statement = statement.where(model.material_requirement_id == requirement_id)
    rows = list(db.scalars(statement.order_by(model.id)))
    removed = {row.supersedes_id for row in rows if row.state == "RELEASED"}
    return [row for row in rows if row.state == "ACTIVE" and row.id not in removed]


def _load(db, model, tenant, workspace, identities, instant):
    ids = set(identities) - {None}
    if not ids:
        return {}
    return {
        row.id: row
        for row in db.scalars(_scoped(model, tenant, workspace).where(model.id.in_(ids), model.created_at <= instant))
    }


def _valid_document(db, tenant, workspace, ref, instant):
    if not ref:
        return True
    binding = _cde_binding(db, tenant, workspace, instant=instant)
    if binding is None:
        return False
    pair = db.execute(
        _cde_rows(db, tenant, binding.legacy_project_id).where(
            Document.id == ref.get("document_id"),
            DocumentAttachment.id == ref.get("attachment_id"),
            DocumentAttachment.created_at <= instant,
        )
    ).one_or_none()
    return bool(
        pair and _sha_eligible(pair[1]) and all(ref.get(k) == v for k, v in _cde_reference(binding, *pair).items())
    )


def _history(db, tenant, workspace, kind, identities, instant):
    ids = set(identities)
    if not ids:
        return {}
    return {
        event.entity_id: event
        for event in db.scalars(
            _scoped(ProcurementHistory, tenant, workspace)
            .where(
                ProcurementHistory.entity_type == kind,
                ProcurementHistory.entity_id.in_(ids),
                ProcurementHistory.created_at <= instant,
            )
            .order_by(ProcurementHistory.id)
        )
    }


def _ordered(db, tenant, workspace, demand, sourcing_id, instant):
    if not sourcing_id:
        return Decimal(0), []
    lines = list(
        db.scalars(
            _scoped(ProcurementPurchaseOrderLine, tenant, workspace)
            .where(
                ProcurementPurchaseOrderLine.requirement_id == sourcing_id,
                ProcurementPurchaseOrderLine.created_at <= instant,
            )
            .order_by(ProcurementPurchaseOrderLine.id)
        )
    )
    orders = _load(db, ProcurementPurchaseOrder, tenant, workspace, (line.purchase_order_id for line in lines), instant)
    if not orders:
        return Decimal(0), []
    history = _history(db, tenant, workspace, "ProcurementPurchaseOrder", orders, instant)
    revisions = {
        revision.id: revision
        for revision in db.scalars(
            _scoped(ProcurementPurchaseOrderRevision, tenant, workspace).where(
                ProcurementPurchaseOrderRevision.purchase_order_id.in_(orders),
                ProcurementPurchaseOrderRevision.status == "APPROVED",
                ProcurementPurchaseOrderRevision.created_at <= instant,
            )
        )
    }
    total, source = Decimal(0), []
    for line in lines:
        order, event = orders.get(line.purchase_order_id), history.get(line.purchase_order_id)
        if (
            not order
            or not event
            or event.snapshot_json.get("status") != "ISSUED"
            or order.effective_date > instant.date()
        ):
            continue
        revision = revisions.get(event.snapshot_json.get("current_revision_id"))
        while revision is not None and revision.effective_date > instant.date():
            revision = revisions.get(revision.previous_revision_id)
        amount = line.quantity
        if revision is not None:
            snapshots = [item for item in revision.lines_snapshot if item.get("line_id", item.get("id")) == line.id]
            if not snapshots:
                continue
            amount = Decimal(str(snapshots[0]["quantity"]))
        if line.uom.upper() != demand.uom:
            continue
        total += amount
        source.append(
            {
                "po_line_id": line.id,
                "po_history_id": event.id,
                "revision_hash": revision.content_hash if revision else None,
                "quantity": _quantity(amount),
            }
        )
    return total, source


def _evaluate_requirement(db, tenant, workspace, package_id, mapping, demand, instant):
    model = ProcurementMaterialReceiptLine
    code = set()
    if mapping.content_hash != _hash(mapping_content(mapping)) or demand is None:
        return {
            "material_requirement_id": mapping.source_id,
            "mapping_id": mapping.id,
            "status": "BROKEN_REFERENCE",
            "reason_codes": ["MATERIAL_REQUIREMENT_REFERENCE_INVALID"],
        }
    item = _load(db, ProcurementMaterialItem, tenant, workspace, (demand.material_item_id,), instant).get(
        demand.material_item_id
    )
    if (
        not item
        or item.uom != demand.uom
        or not _valid_document(db, tenant, workspace, demand.source_reference_json, instant)
    ):
        code.add("MATERIAL_DEMAND_SOURCE_INVALID")
    demand_history = _history(db, tenant, workspace, "ProcurementMaterialRequirement", (demand.id,), instant).get(
        demand.id
    )
    sourcing_id = demand_history.snapshot_json.get("procurement_requirement_id") if demand_history else None
    if sourcing_id and not _load(db, ProcurementRequirement, tenant, workspace, (sourcing_id,), instant):
        code.add("MATERIAL_PROCUREMENT_SOURCE_INVALID")
    ordered, order_sources = _ordered(db, tenant, workspace, demand, sourcing_id, instant)
    ordered_ids = {entry["po_line_id"] for entry in order_sources}
    shipments = list(
        db.scalars(
            _scoped(ProcurementShipmentLine, tenant, workspace)
            .where(
                ProcurementShipmentLine.material_requirement_id == demand.id,
                ProcurementShipmentLine.created_at <= instant,
            )
            .order_by(ProcurementShipmentLine.id)
        )
    )
    parents = _load(db, ProcurementShipment, tenant, workspace, (row.shipment_id for row in shipments), instant)
    dispatches = _history(db, tenant, workspace, "ProcurementShipment", parents, instant)
    shipped_rows = []
    for row in shipments:
        history = dispatches.get(row.shipment_id)
        if not history or not history.snapshot_json.get("dispatch_date"):
            continue
        try:
            dispatched = date.fromisoformat(history.snapshot_json["dispatch_date"])
        except (ValueError, TypeError):
            code.add("MATERIAL_SHIPMENT_DISPATCH_SOURCE_INVALID")
            continue
        if dispatched <= instant.date() and row.uom == demand.uom:
            if row.po_line_id not in ordered_ids:
                code.add("MATERIAL_SHIPMENT_ORDER_SOURCE_INVALID")
            shipped_rows.append(row)
    shipped = sum((row.quantity for row in shipped_rows), Decimal(0))
    shipment_lines = {row.id: row for row in shipped_rows}
    lines = list(
        db.scalars(
            _scoped(model, tenant, workspace)
            .where(model.material_requirement_id == demand.id, model.created_at <= instant)
            .order_by(model.id)
        )
    )
    receipts = _load(db, ProcurementMaterialReceipt, tenant, workspace, (row.receipt_id for row in lines), instant)
    receipts = {identity: row for identity, row in receipts.items() if row.received_at <= instant}
    line_rows = {
        row.id: row
        for row in lines
        if row.receipt_id in receipts
        and row.shipment_line_id in shipment_lines
        and row.uom == demand.uom
        and row.material_item_id == demand.material_item_id
        and row.po_line_id == shipment_lines[row.shipment_line_id].po_line_id
        and receipts[row.receipt_id].shipment_id == shipment_lines[row.shipment_line_id].shipment_id
    }
    if any(row.receipt_id in receipts and row.id not in line_rows for row in lines):
        code.add("MATERIAL_RECEIPT_SOURCE_INVALID")
    if any(
        not _valid_document(db, tenant, workspace, row.document_reference_json, instant) for row in receipts.values()
    ):
        code.add("MATERIAL_RECEIPT_DOCUMENT_INVALID")
    received = sum((row.quantity for row in line_rows.values()), Decimal(0))
    model = ProcurementMaterialAcceptance
    decisions = list(
        db.scalars(
            _scoped(model, tenant, workspace)
            .where(model.receipt_line_id.in_(line_rows), model.created_at <= instant)
            .order_by(model.id)
        )
    )
    inspections = _load(db, ProcurementInspection, tenant, workspace, (row.inspection_id for row in decisions), instant)
    accepted_rows = {}
    for row in decisions:
        line = line_rows[row.receipt_line_id]
        inspection = inspections.get(row.inspection_id)
        if (
            row.content_hash != material_acceptance_hash(row)
            or row.accepted_quantity + row.rejected_quantity + row.quarantine_quantity != line.quantity
            or (
                row.inspection_id is not None
                and (
                    not inspection
                    or inspection.po_line_id != line.po_line_id
                    or not inspection.decided_at
                    or inspection.decided_at > instant
                    or (row.accepted_quantity > 0 and inspection.status != "ACCEPTED")
                    or not _valid_document(db, tenant, workspace, inspection.document_reference_json, instant)
                )
            )
        ):
            code.add("MATERIAL_ACCEPTANCE_SOURCE_INVALID")
            continue
        accepted_rows[row.id] = row
    accepted = sum((row.accepted_quantity for row in accepted_rows.values()), Decimal(0))
    reserved = available = stale = Decimal(0)
    allocation_ids, allocation_hashes = [], []
    totals = {}
    for allocation in active_allocations(db, tenant, workspace, requirement_id=demand.id, as_of=instant):
        line = line_rows.get(allocation.receipt_line_id)
        fact = accepted_rows.get(allocation.acceptance_id)
        if (
            not line
            or not fact
            or fact.receipt_line_id != line.id
            or allocation.uom != demand.uom
            or allocation.source_location != receipts[line.receipt_id].location
            or allocation.content_hash != material_allocation_hash(allocation)
        ):
            code.add("MATERIAL_ALLOCATION_SOURCE_INVALID")
            continue
        totals[fact.id] = totals.get(fact.id, Decimal(0)) + allocation.quantity
        if allocation.work_package_id == package_id:
            reserved += allocation.quantity
            allocation_ids.append(allocation.id)
            allocation_hashes.append(allocation.content_hash)
            if allocation.expires_on and allocation.expires_on < instant.date():
                stale += allocation.quantity
            else:
                available += allocation.quantity
    if any(total > accepted_rows[key].accepted_quantity for key, total in totals.items()):
        code.add("MATERIAL_ALLOCATION_CONSERVATION_INVALID")
    if code:
        status, available = "BROKEN_REFERENCE", Decimal(0)
    elif available >= demand.required_quantity:
        status = "READY"
    elif stale:
        status = "STALE"
        code.add("MATERIAL_ALLOCATION_EVIDENCE_EXPIRED")
    elif available:
        status = "PARTIALLY_READY"
        code.add("MATERIAL_AVAILABLE_QUANTITY_BELOW_REQUIREMENT")
    else:
        status = "NOT_READY"
        code.add("MATERIAL_ACCEPTED_ALLOCATION_REQUIRED")
    return {
        "material_requirement_id": demand.id,
        "requirement_code": demand.requirement_code,
        "material_item_id": demand.material_item_id,
        "uom": demand.uom,
        "status": status,
        "required_on_site_date": demand.required_on_site_date.isoformat() if demand.required_on_site_date else None,
        "required_quantity": _quantity(demand.required_quantity),
        "ordered_quantity": _quantity(ordered),
        "shipped_quantity": _quantity(shipped),
        "received_quantity": _quantity(received),
        "accepted_quantity": _quantity(accepted),
        "rejected_quantity": _quantity(sum((row.rejected_quantity for row in accepted_rows.values()), Decimal(0))),
        "quarantine_quantity": _quantity(sum((row.quarantine_quantity for row in accepted_rows.values()), Decimal(0))),
        "reserved_quantity": _quantity(reserved),
        "available_quantity": _quantity(available),
        "stale_quantity": _quantity(stale),
        "mapping_id": mapping.id,
        "mapping_hash": mapping.content_hash,
        "po_line_sources": order_sources,
        "shipment_line_ids": sorted(shipment_lines),
        "receipt_line_ids": sorted(line_rows),
        "acceptance_sources": [{"id": row.id, "content_hash": row.content_hash} for row in accepted_rows.values()],
        "allocation_ids": allocation_ids,
        "allocation_hashes": allocation_hashes,
        "reason_codes": sorted(code),
    }


def material_availability(db, tenant, workspace, package_id, as_of=None):
    if not inspect(db.connection()).has_table(ProcurementMapping.__tablename__):
        return None
    instant = _observed_at(as_of)
    package = _load(db, WorkPackage, tenant, workspace, (package_id,), instant).get(package_id)
    if not package or package.package_type not in {"CWP", "IWP"}:
        return None
    mappings = effective_mappings(
        db,
        tenant,
        workspace,
        source_kind="MATERIAL_REQUIREMENT",
        target_kind=package.package_type,
        target_id=package_id,
        as_of=instant,
    )
    if not mappings:
        return None
    demands = _load(db, ProcurementMaterialRequirement, tenant, workspace, (row.source_id for row in mappings), instant)
    requirements = [
        _evaluate_requirement(db, tenant, workspace, package_id, row, demands.get(row.source_id), instant)
        for row in sorted(mappings, key=lambda item: item.source_id)
    ]
    states = {row["status"] for row in requirements}
    covered = sum(row["status"] == "READY" for row in requirements)
    status = (
        "BROKEN_REFERENCE"
        if "BROKEN_REFERENCE" in states
        else "STALE"
        if "STALE" in states
        else "READY"
        if covered == len(requirements)
        else "PARTIALLY_READY"
        if covered or "PARTIALLY_READY" in states
        else "NOT_READY"
    )
    material = {
        "provider_key": "MATERIAL_AVAILABILITY_PROVIDER",
        "work_package_id": package_id,
        "status": status,
        "coverage": {"required": len(requirements), "covered": covered},
        "requirements": requirements,
        "reason_codes": sorted({reason for row in requirements for reason in row["reason_codes"]}),
    }
    freshness = "BROKEN_REFERENCE" if status == "BROKEN_REFERENCE" else "STALE" if status == "STALE" else "CURRENT"
    return material | {
        "as_of": instant.date().isoformat(),
        "source_freshness": freshness,
        "evidence_hash": _hash(material),
    }
