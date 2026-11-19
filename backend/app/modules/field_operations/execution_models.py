"""Field execution facts; no downstream measurements or financial authority."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.modules.field_operations.models import FieldRecord
from app.modules.scope_foundation.models import ScopeRecord

QTY = Numeric(24, 8)


class ProductionRecord(FieldRecord, Base):
    """Installed evidence and rework are typed facts in one revisioned authority."""

    __tablename__ = "field_production_records"
    production_code: Mapped[str] = mapped_column(String(120))
    revision: Mapped[int] = mapped_column(default=1)
    workfront_id: Mapped[int] = mapped_column(ForeignKey("field_workfronts.id"), index=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("field_shifts.id"), index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("field_daily_reports.id"))
    scope_item_id: Mapped[int] = mapped_column(ForeignKey("scope_items.id"), index=True)
    plan_item_id: Mapped[int | None] = mapped_column(ForeignKey("scope_plan_items.id"))
    iwp_id: Mapped[int | None] = mapped_column(ForeignKey("awp_work_packages.id"))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    planned_quantity: Mapped[Decimal | None] = mapped_column(QTY)
    uom: Mapped[str] = mapped_column(String(40))
    production_type: Mapped[str] = mapped_column(String(80))
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    source_reference: Mapped[str] = mapped_column(String(500))
    location_reference: Mapped[dict] = mapped_column(JSON)
    scope_reference: Mapped[dict] = mapped_column(JSON)
    plan_reference: Mapped[dict | None] = mapped_column(JSON)
    iwp_reference: Mapped[dict | None] = mapped_column(JSON)
    engineering_reference: Mapped[dict | None] = mapped_column(JSON)
    material_reference: Mapped[dict | None] = mapped_column(JSON)
    document_reference: Mapped[dict] = mapped_column(JSON)
    execution_condition: Mapped[str] = mapped_column(String(80))
    exception_reason: Mapped[str | None] = mapped_column(Text)
    variance_reason: Mapped[str | None] = mapped_column(Text)
    evidence_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="RECORDED")
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("field_production_records.id"))
    original_production_id: Mapped[int | None] = mapped_column(ForeignKey("field_production_records.id"))
    rework_reason: Mapped[str | None] = mapped_column(Text)
    responsible_party: Mapped[str | None] = mapped_column(String(300))
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "production_code", "revision", name="uq_field_prod_code_revision"
        ),
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "evidence_key", "revision", name="uq_field_prod_evidence_revision"
        ),
        CheckConstraint(
            "quantity > 0 AND revision > 0 AND (planned_quantity IS NULL OR planned_quantity >= 0)",
            name="ck_field_prod_quantity",
        ),
        CheckConstraint("status IN ('RECORDED','VERIFIED','REJECTED')", name="ck_field_prod_status"),
        CheckConstraint(
            "(status = 'RECORDED' AND verified_by IS NULL AND verified_at IS NULL) OR (status <> 'RECORDED' AND verified_by IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_field_prod_verification",
        ),
        Index(
            "uq_field_prod_successor",
            "supersedes_id",
            unique=True,
            postgresql_where=text("status <> 'REJECTED'"),
            sqlite_where=text("status <> 'REJECTED'"),
        ),
    )


class FieldEvent(FieldRecord, Base):
    __tablename__ = "field_events"
    event_code: Mapped[str] = mapped_column(String(120))
    workfront_id: Mapped[int] = mapped_column(ForeignKey("field_workfronts.id"), index=True)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("field_shifts.id"))
    event_type: Mapped[str] = mapped_column(String(80))
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16))
    duration_hours: Mapped[Decimal | None] = mapped_column(QTY)
    document_reference: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="RECORDED")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "event_code", name="uq_field_event_code"),
        CheckConstraint(
            "status IN ('RECORDED','REVIEWED','CLOSED') AND severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_field_event_status",
        ),
        CheckConstraint("duration_hours IS NULL OR duration_hours >= 0", name="ck_field_event_hours"),
    )


class SiteInstruction(FieldRecord, Base):
    __tablename__ = "field_site_instructions"
    instruction_number: Mapped[str] = mapped_column(String(120))
    instruction_type: Mapped[str] = mapped_column(String(80))
    instruction_date: Mapped[date] = mapped_column(Date)
    issuer: Mapped[str] = mapped_column(String(300))
    recipient: Mapped[str] = mapped_column(String(300))
    workfront_id: Mapped[int] = mapped_column(ForeignKey("field_workfronts.id"), index=True)
    scope_item_id: Mapped[int | None] = mapped_column(ForeignKey("scope_items.id"))
    iwp_id: Mapped[int | None] = mapped_column(ForeignKey("awp_work_packages.id"))
    description: Mapped[str] = mapped_column(Text)
    document_reference: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "instruction_number", name="uq_field_instruction_number"),
        CheckConstraint("status IN ('DRAFT','ISSUED','ACKNOWLEDGED','CLOSED')", name="ck_field_instruction_status"),
    )


class FieldConstraintObservation(FieldRecord, Base):
    __tablename__ = "field_constraint_observations"
    observation_code: Mapped[str] = mapped_column(String(120))
    constraint_type: Mapped[str] = mapped_column(String(80))
    workfront_id: Mapped[int] = mapped_column(ForeignKey("field_workfronts.id"), index=True)
    iwp_id: Mapped[int | None] = mapped_column(ForeignKey("awp_work_packages.id"))
    observation_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16))
    document_reference: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="REPORTED")
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "observation_code", name="uq_field_observation_code"),
        CheckConstraint(
            "status IN ('REPORTED','VERIFIED','REJECTED') AND severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_field_observation_status",
        ),
    )


class MaterialConsumption(FieldRecord, Base):
    __tablename__ = "field_material_consumption"
    consumption_code: Mapped[str] = mapped_column(String(120))
    production_record_id: Mapped[int] = mapped_column(ForeignKey("field_production_records.id"), index=True)
    material_item_id: Mapped[int] = mapped_column(ForeignKey("procurement_material_items.id"))
    allocation_id: Mapped[int] = mapped_column(ForeignKey("procurement_material_allocations.id"))
    workfront_id: Mapped[int] = mapped_column(ForeignKey("field_workfronts.id"))
    consumption_date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    uom: Mapped[str] = mapped_column(String(40))
    allocation_reference: Mapped[dict] = mapped_column(JSON)
    document_reference: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="RECORDED")
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "consumption_code", name="uq_field_consumption_code"),
        CheckConstraint("quantity > 0 AND status = 'RECORDED'", name="ck_field_consumption_quantity"),
    )


class FieldMapping(ScopeRecord, Base):
    __tablename__ = "field_mappings"
    source_kind: Mapped[str] = mapped_column(String(24))
    source_id: Mapped[int] = mapped_column()
    target_kind: Mapped[str] = mapped_column(String(32))
    target_reference: Mapped[dict] = mapped_column(JSON)
    action: Mapped[str] = mapped_column(String(12))
    reason: Mapped[str] = mapped_column(Text)
    source_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        CheckConstraint("action IN ('SET','REMOVE') AND source_id > 0", name="ck_field_mapping_action"),
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "source_kind", "source_id", "version", name="uq_field_mapping_stream"
        ),
        Index("ix_field_mapping_source", "tenant_id", "project_workspace_id", "source_kind", "source_id", "id"),
    )


APPEND_ONLY = (MaterialConsumption, FieldMapping)
TERMINAL = {
    ProductionRecord: {"VERIFIED", "REJECTED"},
    FieldEvent: {"CLOSED"},
    SiteInstruction: {"CLOSED"},
    FieldConstraintObservation: {"VERIFIED", "REJECTED"},
}
MODELS = (*TERMINAL, *APPEND_ONLY)


def _immutable(_mapper, _connection, _row):
    raise ValueError("Field execution evidence is immutable")


def _terminal(_mapper, _connection, row):
    history = inspect(row).attrs.status.history
    old = history.deleted[0] if history.deleted else row.status
    if old in TERMINAL[type(row)]:
        _immutable(_mapper, _connection, row)


for _model in MODELS:
    event.listen(_model, "before_delete", _immutable)
    event.listen(_model, "before_update", _immutable if _model in APPEND_ONLY else _terminal)
