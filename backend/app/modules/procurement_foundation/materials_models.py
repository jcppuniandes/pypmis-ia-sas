"""O2B operational physical facts; legacy WarehouseReceipt is never counted as stock."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord

QTY = Numeric(20, 6)


def code_unique(column, label):
    return UniqueConstraint("tenant_id", "project_workspace_id", column, name=f"uq_procurement_{label}_code")


class ProcurementMaterialItem(ScopeRecord, Base):
    __tablename__ = "procurement_material_items"

    material_code: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(300))
    specification: Mapped[str] = mapped_column(Text, default="")
    uom: Mapped[str] = mapped_column(String(24))
    category: Mapped[str] = mapped_column(String(80))

    __table_args__ = (code_unique("material_code", "material_item"),)


class ProcurementMaterialRequirement(ScopeRecord, Base):
    __tablename__ = "procurement_material_requirements"

    requirement_code: Mapped[str] = mapped_column(String(120))
    material_item_id: Mapped[int] = mapped_column(ForeignKey("procurement_material_items.id"), index=True)
    procurement_requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("procurement_requirements.id"), index=True
    )
    required_quantity: Mapped[Decimal] = mapped_column(QTY)
    uom: Mapped[str] = mapped_column(String(24))
    required_on_site_date: Mapped[date | None] = mapped_column(Date)
    source_reference_json: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        code_unique("requirement_code", "material_requirement"),
        UniqueConstraint(
            "tenant_id",
            "project_workspace_id",
            "procurement_requirement_id",
            name="uq_procurement_material_demand_link",
        ),
        CheckConstraint("required_quantity > 0", name="ck_procurement_material_required_quantity"),
    )


class ProcurementVendorMilestone(ScopeRecord, Base):
    __tablename__ = "procurement_vendor_milestones"

    po_line_id: Mapped[int] = mapped_column(ForeignKey("procurement_po_lines.id"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    planned_date: Mapped[date] = mapped_column(Date)
    forecast_date: Mapped[date | None] = mapped_column(Date)
    actual_date: Mapped[date | None] = mapped_column(Date)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("procurement_vendor_milestones.id"), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (UniqueConstraint("po_line_id", "code", "version", name="uq_procurement_milestone_version"),)


class ProcurementExpeditingEvent(ScopeRecord, Base):
    __tablename__ = "procurement_expediting_events"

    po_line_id: Mapped[int] = mapped_column(ForeignKey("procurement_po_lines.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    observation_date: Mapped[date] = mapped_column(Date)
    forecast_date: Mapped[date | None] = mapped_column(Date)
    progress_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    detail: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (CheckConstraint("progress_percent BETWEEN 0 AND 100", name="ck_procurement_vendor_progress"),)


class ProcurementInspection(ScopeRecord, Base):
    __tablename__ = "procurement_inspections"

    po_line_id: Mapped[int] = mapped_column(ForeignKey("procurement_po_lines.id"), index=True)
    vendor_id: Mapped[int] = mapped_column()
    inspection_type: Mapped[str] = mapped_column(String(80))
    inspection_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="PLANNED")
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    detail: Mapped[str] = mapped_column(Text, default="")
    ncr_reference: Mapped[str] = mapped_column(String(240), default="")
    document_reference_json: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        CheckConstraint(
            "status IN ('PLANNED','ACCEPTED','REJECTED','CONDITIONAL')", name="ck_procurement_inspection_status"
        ),
    )


class ProcurementShipment(ScopeRecord, Base):
    __tablename__ = "procurement_shipments"

    shipment_number: Mapped[str] = mapped_column(String(120))
    vendor_id: Mapped[int] = mapped_column()
    origin: Mapped[str] = mapped_column(String(240))
    destination: Mapped[str] = mapped_column(String(240))
    transport_mode: Mapped[str] = mapped_column(String(80))
    carrier_reference: Mapped[str] = mapped_column(String(240), default="")
    customs_reference: Mapped[str] = mapped_column(String(240), default="")
    status: Mapped[str] = mapped_column(String(30), default="PLANNED")
    dispatch_date: Mapped[date | None] = mapped_column(Date)
    planned_arrival: Mapped[date | None] = mapped_column(Date)
    forecast_arrival: Mapped[date | None] = mapped_column(Date)
    actual_arrival: Mapped[date | None] = mapped_column(Date)
    last_event_date: Mapped[date | None] = mapped_column(Date)
    document_reference_json: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        code_unique("shipment_number", "shipment"),
        CheckConstraint(
            "status IN ('PLANNED','READY_FOR_DISPATCH','DISPATCHED','IN_TRANSIT','ARRIVED',"
            "'PARTIALLY_RECEIVED','RECEIVED','CANCELLED')",
            name="ck_procurement_shipment_status",
        ),
    )


class ProcurementShipmentLine(ScopeRecord, Base):
    __tablename__ = "procurement_shipment_lines"

    shipment_id: Mapped[int] = mapped_column(ForeignKey("procurement_shipments.id"), index=True)
    po_line_id: Mapped[int] = mapped_column(ForeignKey("procurement_po_lines.id"), index=True)
    material_requirement_id: Mapped[int] = mapped_column(ForeignKey("procurement_material_requirements.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    uom: Mapped[str] = mapped_column(String(24))
    po_revision_hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("shipment_id", "po_line_id", name="uq_procurement_shipment_po_line"),
        CheckConstraint("quantity > 0", name="ck_procurement_shipment_line_qty"),
    )


class ProcurementMaterialReceipt(ScopeRecord, Base):
    __tablename__ = "procurement_material_receipts"

    receipt_number: Mapped[str] = mapped_column(String(120))
    shipment_id: Mapped[int] = mapped_column(ForeignKey("procurement_shipments.id"), index=True)
    location: Mapped[str] = mapped_column(String(240))
    received_at: Mapped[datetime] = mapped_column(DateTime)
    document_reference_json: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (code_unique("receipt_number", "material_receipt"),)


class ProcurementMaterialReceiptLine(ScopeRecord, Base):
    __tablename__ = "procurement_material_receipt_lines"

    receipt_id: Mapped[int] = mapped_column(ForeignKey("procurement_material_receipts.id"), index=True)
    shipment_line_id: Mapped[int] = mapped_column(ForeignKey("procurement_shipment_lines.id"), index=True)
    po_line_id: Mapped[int] = mapped_column(ForeignKey("procurement_po_lines.id"), index=True)
    material_item_id: Mapped[int] = mapped_column(ForeignKey("procurement_material_items.id"), index=True)
    material_requirement_id: Mapped[int] = mapped_column(ForeignKey("procurement_material_requirements.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    uom: Mapped[str] = mapped_column(String(24))

    __table_args__ = (
        UniqueConstraint("receipt_id", "shipment_line_id", name="uq_procurement_receipt_shipment_line"),
        CheckConstraint("quantity > 0", name="ck_procurement_material_receipt_qty"),
    )


class ProcurementMaterialAcceptance(ScopeRecord, Base):
    __tablename__ = "procurement_material_acceptances"

    receipt_line_id: Mapped[int] = mapped_column(ForeignKey("procurement_material_receipt_lines.id"), unique=True)
    inspection_id: Mapped[int | None] = mapped_column(ForeignKey("procurement_inspections.id"))
    accepted_quantity: Mapped[Decimal] = mapped_column(QTY)
    rejected_quantity: Mapped[Decimal] = mapped_column(QTY)
    quarantine_quantity: Mapped[Decimal] = mapped_column(QTY)
    detail: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint(
            "accepted_quantity >= 0 AND rejected_quantity >= 0 AND quarantine_quantity >= 0 "
            "AND accepted_quantity + rejected_quantity + quarantine_quantity > 0",
            name="ck_procurement_material_acceptance_qty",
        ),
    )


class ProcurementMaterialAllocation(ScopeRecord, Base):
    __tablename__ = "procurement_material_allocations"

    receipt_line_id: Mapped[int] = mapped_column(ForeignKey("procurement_material_receipt_lines.id"), index=True)
    acceptance_id: Mapped[int] = mapped_column(ForeignKey("procurement_material_acceptances.id"))
    material_requirement_id: Mapped[int] = mapped_column(ForeignKey("procurement_material_requirements.id"), index=True)
    work_package_id: Mapped[int] = mapped_column(ForeignKey("awp_work_packages.id"))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    uom: Mapped[str] = mapped_column(String(24))
    allocation_date: Mapped[date] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    source_location: Mapped[str] = mapped_column(String(240))
    state: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("procurement_material_allocations.id"), unique=True)
    content_hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_procurement_material_allocation_qty"),
        CheckConstraint(
            "(state='ACTIVE' AND supersedes_id IS NULL) OR (state='RELEASED' AND supersedes_id IS NOT NULL)",
            name="ck_procurement_material_allocation_state",
        ),
        Index("ix_procurement_alloc_destination", "tenant_id", "project_workspace_id", "work_package_id", "state"),
    )


MATERIAL_MODELS = (
    ProcurementMaterialItem,
    ProcurementMaterialRequirement,
    ProcurementVendorMilestone,
    ProcurementExpeditingEvent,
    ProcurementInspection,
    ProcurementShipment,
    ProcurementShipmentLine,
    ProcurementMaterialReceipt,
    ProcurementMaterialReceiptLine,
    ProcurementMaterialAcceptance,
    ProcurementMaterialAllocation,
)

MATERIAL_IMMUTABLE_MODELS = (
    ProcurementMaterialItem,
    ProcurementVendorMilestone,
    ProcurementExpeditingEvent,
    ProcurementShipmentLine,
    ProcurementMaterialReceiptLine,
    ProcurementMaterialAcceptance,
    ProcurementMaterialAllocation,
)
