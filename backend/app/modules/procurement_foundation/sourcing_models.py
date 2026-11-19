"""Canonical sourcing identities, never written to legacy financial registers."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord


class SourcingRecord(ScopeRecord):
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ProcurementVendor(Base):
    __tablename__ = "procurement_vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    vendor_code: Mapped[str] = mapped_column(String(80))
    legal_name: Mapped[str] = mapped_column(String(240))
    display_name: Mapped[str] = mapped_column(String(200))
    business_identifier: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2))
    contact_reference: Mapped[str] = mapped_column(String(400), default="")
    qualification_reference: Mapped[str] = mapped_column(String(400), default="")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (
        UniqueConstraint("tenant_id", "vendor_code", name="uq_proc_vendor_code"),
        UniqueConstraint("tenant_id", "country", "business_identifier", name="uq_proc_vendor_business"),
        CheckConstraint("status IN ('ACTIVE','SUSPENDED','RETIRED')", name="ck_proc_vendor_status"),
    )


class ProcurementPackage(SourcingRecord, Base):
    __tablename__ = "procurement_packages"
    package_code: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    procurement_type: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(80))
    discipline: Mapped[str] = mapped_column(String(80), default="")
    responsible_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    procurement_manager_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    strategy: Mapped[str] = mapped_column(Text, default="")
    sourcing_method: Mapped[str] = mapped_column(String(80))
    long_lead_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[str] = mapped_column(String(20), default="NORMAL")
    required_on_site_date: Mapped[date] = mapped_column(Date)
    planned_rfq_date: Mapped[date | None] = mapped_column(Date)
    planned_award_date: Mapped[date | None] = mapped_column(Date)
    planned_po_date: Mapped[date | None] = mapped_column(Date)
    forecast_delivery_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "package_code", name="uq_proc_package_code"),
        Index("ix_proc_package_register", "tenant_id", "project_workspace_id", "status", "id"),
        CheckConstraint("status IN ('DRAFT','PLANNED','CLOSED','CANCELLED')", name="ck_proc_package_status"),
    )


class ProcurementRequirement(SourcingRecord, Base):
    __tablename__ = "procurement_requirements"
    requirement_code: Mapped[str] = mapped_column(String(120))
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_packages.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    item_type: Mapped[str] = mapped_column(String(80))
    required_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    uom: Mapped[str] = mapped_column(String(24))
    required_on_site_date: Mapped[date] = mapped_column(Date)
    priority: Mapped[str] = mapped_column(String(20), default="NORMAL")
    source_authority: Mapped[str] = mapped_column(String(80), default="")
    source_entity_type: Mapped[str] = mapped_column(String(80), default="")
    source_entity_id: Mapped[int | None] = mapped_column()
    source_hash: Mapped[str] = mapped_column(String(64), default="")
    source_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "requirement_code", name="uq_proc_requirement_code"),
        CheckConstraint("required_quantity > 0", name="ck_proc_requirement_qty"),
        CheckConstraint("status IN ('DRAFT','ACTIVE','CANCELLED')", name="ck_proc_requirement_status"),
    )


class ProcurementPackageItem(ScopeRecord, Base):
    __tablename__ = "procurement_package_items"
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_packages.id"), index=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("procurement_requirements.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    uom: Mapped[str] = mapped_column(String(24))
    __table_args__ = (
        UniqueConstraint("package_id", "requirement_id", name="uq_proc_package_item_req"),
        CheckConstraint("quantity > 0", name="ck_proc_package_item_qty"),
    )


class ProcurementRequisition(SourcingRecord, Base):
    __tablename__ = "procurement_requisitions"
    requisition_number: Mapped[str] = mapped_column(String(120))
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_packages.id"), index=True)
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    requested_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    prepared_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    issue_date: Mapped[date] = mapped_column(Date)
    required_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    technical_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    document_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "requisition_number", "revision", name="uq_proc_req_revision"
        ),
        CheckConstraint("status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED','CANCELLED')", name="ck_proc_req_status"),
    )


class ProcurementRequisitionLine(ScopeRecord, Base):
    __tablename__ = "procurement_requisition_lines"
    requisition_id: Mapped[int] = mapped_column(ForeignKey("procurement_requisitions.id"), index=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("procurement_requirements.id"), index=True)
    line_number: Mapped[int] = mapped_column()
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    uom: Mapped[str] = mapped_column(String(24))
    required_date: Mapped[date] = mapped_column(Date)
    technical_specification_reference: Mapped[str] = mapped_column(String(400), default="")
    engineering_revision_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    destination: Mapped[str] = mapped_column(String(240), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        UniqueConstraint("requisition_id", "line_number", name="uq_proc_req_line_no"),
        CheckConstraint("quantity > 0 AND line_number > 0", name="ck_proc_req_line_qty_no"),
    )


class ProcurementRFQ(SourcingRecord, Base):
    __tablename__ = "procurement_rfqs"
    rfq_number: Mapped[str] = mapped_column(String(120))
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_packages.id"), index=True)
    requisition_id: Mapped[int] = mapped_column(ForeignKey("procurement_requisitions.id"), index=True)
    revision: Mapped[int] = mapped_column(default=1)
    issue_date: Mapped[date] = mapped_column(Date)
    closing_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    commercial_terms_reference: Mapped[str] = mapped_column(String(400), default="")
    technical_package_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    document_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "rfq_number", "revision", name="uq_proc_rfq_revision"),
        CheckConstraint("closing_date >= issue_date", name="ck_proc_rfq_dates"),
        CheckConstraint("status IN ('DRAFT','ISSUED','CLOSED','CANCELLED')", name="ck_proc_rfq_status"),
    )


class ProcurementRFQVendor(ScopeRecord, Base):
    __tablename__ = "procurement_rfq_vendors"
    rfq_id: Mapped[int] = mapped_column(ForeignKey("procurement_rfqs.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("procurement_vendors.id"), index=True)
    vendor_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("rfq_id", "vendor_id", name="uq_proc_rfq_vendor"),)


class ProcurementBid(ScopeRecord, Base):
    __tablename__ = "procurement_bids"
    rfq_id: Mapped[int] = mapped_column(ForeignKey("procurement_rfqs.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("procurement_vendors.id"), index=True)
    bid_revision: Mapped[int] = mapped_column(default=1)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("procurement_bids.id"))
    received_at: Mapped[datetime] = mapped_column(DateTime)
    currency: Mapped[str] = mapped_column(String(3))
    total_bid_value: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    validity_date: Mapped[date] = mapped_column(Date)
    overall_status: Mapped[str] = mapped_column(String(24), default="RECEIVED")
    document_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("rfq_id", "vendor_id", "bid_revision", name="uq_proc_bid_revision"),
        UniqueConstraint("supersedes_id", name="uq_proc_bid_successor"),
        CheckConstraint("total_bid_value > 0", name="ck_proc_bid_value"),
    )


class ProcurementEvaluation(ScopeRecord, Base):
    __tablename__ = "procurement_evaluations"
    bid_id: Mapped[int] = mapped_column(ForeignKey("procurement_bids.id"), index=True)
    evaluation_type: Mapped[str] = mapped_column(String(24))
    evaluated_on: Mapped[date] = mapped_column(Date)
    result: Mapped[str] = mapped_column(String(24))
    score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    comments: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(String(24))
    engineering_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    document_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("bid_id", "evaluation_type", name="uq_proc_eval_duty"),
        CheckConstraint("evaluation_type IN ('TECHNICAL','COMMERCIAL')", name="ck_proc_eval_type"),
        CheckConstraint("result IN ('ACCEPTED','REJECTED','CONDITIONAL')", name="ck_proc_eval_result"),
    )


class ProcurementAward(ScopeRecord, Base):
    __tablename__ = "procurement_awards"
    rfq_id: Mapped[int] = mapped_column(ForeignKey("procurement_rfqs.id"), unique=True)
    bid_id: Mapped[int] = mapped_column(ForeignKey("procurement_bids.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("procurement_vendors.id"), index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_packages.id"), index=True)
    decision_date: Mapped[date] = mapped_column(Date)
    approval_reference: Mapped[str] = mapped_column(String(400))
    decision: Mapped[str] = mapped_column(String(24), default="AWARDED")
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))


class ProcurementPurchaseOrder(SourcingRecord, Base):
    __tablename__ = "procurement_purchase_orders"
    po_number: Mapped[str] = mapped_column(String(120))
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_packages.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("procurement_vendors.id"), index=True)
    award_id: Mapped[int | None] = mapped_column(ForeignKey("procurement_awards.id"), unique=True)
    currency: Mapped[str] = mapped_column(String(3))
    issue_date: Mapped[date] = mapped_column(Date)
    effective_date: Mapped[date] = mapped_column(Date)
    expected_delivery_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    original_value: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    current_value: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    current_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("procurement_po_revisions.id", use_alter=True, name="fk_proc_po_current_revision")
    )
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    legacy_purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"), unique=True)
    reference_contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"))
    reference_commitment_id: Mapped[int | None] = mapped_column()
    document_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "po_number", name="uq_proc_po_no"),
        CheckConstraint("status IN ('DRAFT','APPROVED','ISSUED','CANCELLED')", name="ck_proc_po_status"),
        CheckConstraint("original_value >= 0 AND current_value >= 0", name="ck_proc_po_value"),
    )


class ProcurementPurchaseOrderLine(ScopeRecord, Base):
    __tablename__ = "procurement_po_lines"
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("procurement_purchase_orders.id"), index=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("procurement_requirements.id"), index=True)
    line_number: Mapped[int] = mapped_column()
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    uom: Mapped[str] = mapped_column(String(24))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    requested_date: Mapped[date] = mapped_column(Date)
    promised_date: Mapped[date | None] = mapped_column(Date)
    forecast_date: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (
        UniqueConstraint("purchase_order_id", "line_number", name="uq_proc_po_line_no"),
        CheckConstraint("quantity > 0 AND unit_price >= 0 AND line_number > 0", name="ck_proc_po_line_qty_price"),
    )


class ProcurementPurchaseOrderRevision(SourcingRecord, Base):
    __tablename__ = "procurement_po_revisions"
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("procurement_purchase_orders.id"), index=True)
    previous_revision_id: Mapped[int | None] = mapped_column(ForeignKey("procurement_po_revisions.id"), unique=True)
    revision: Mapped[int] = mapped_column()
    effective_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    reason: Mapped[str] = mapped_column(Text)
    lines_snapshot: Mapped[list] = mapped_column(JSON)
    value_delta: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    total_value: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    schedule_impact_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approval_reference: Mapped[str] = mapped_column(String(400), default="")
    content_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("purchase_order_id", "revision", name="uq_proc_po_revision"),
        CheckConstraint("status IN ('DRAFT','APPROVED') AND revision > 0", name="ck_proc_po_revision_status"),
    )


class ProcurementHistory(ScopeRecord, Base):
    __tablename__ = "procurement_history"
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int] = mapped_column()
    entity_version: Mapped[int] = mapped_column()
    previous_version: Mapped[int | None] = mapped_column()
    event_type: Mapped[str] = mapped_column(String(100))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        Index(
            "ix_proc_history_workspace_entity", "tenant_id", "project_workspace_id", "entity_type", "entity_id", "id"
        ),
    )
