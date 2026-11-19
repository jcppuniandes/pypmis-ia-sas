"""Canonical field-operation records, not HR, inventory or financial postings."""

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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord

QUANTITY = Numeric(24, 8)


class FieldRecord(ScopeRecord):
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    source_hash: Mapped[str] = mapped_column(String(64), default="")


class Workfront(FieldRecord, Base):
    __tablename__ = "field_workfronts"
    workfront_code: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    location_reference: Mapped[dict] = mapped_column(JSON)
    cwa_id: Mapped[int | None] = mapped_column(ForeignKey("awp_cwas.id"))
    cwp_id: Mapped[int | None] = mapped_column(ForeignKey("awp_work_packages.id"))
    iwp_id: Mapped[int | None] = mapped_column(ForeignKey("awp_work_packages.id"))
    source_references: Mapped[list] = mapped_column(JSON, default=list)
    responsible_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    status: Mapped[str] = mapped_column(String(24), default="PLANNED")
    planned_start: Mapped[date] = mapped_column(Date)
    planned_finish: Mapped[date] = mapped_column(Date)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_finish: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "workfront_code", name="uq_o3a_workfront_code"),
        CheckConstraint("planned_start <= planned_finish", name="ck_o3a_workfront_plan_dates"),
        CheckConstraint("actual_finish IS NULL OR actual_start <= actual_finish", name="ck_o3a_workfront_actual_dates"),
        CheckConstraint("status IN ('PLANNED','ACTIVE','SUSPENDED','COMPLETE')", name="ck_o3a_workfront_status"),
    )


class FieldShift(FieldRecord, Base):
    __tablename__ = "field_shifts"
    shift_code: Mapped[str] = mapped_column(String(120))
    shift_type: Mapped[str] = mapped_column(String(80))
    shift_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[datetime] = mapped_column(DateTime)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    workfront_id: Mapped[int] = mapped_column(ForeignKey("field_workfronts.id"), index=True)
    supervisor_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    weather_reference: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "shift_code", name="uq_o3a_shift_code"),
        CheckConstraint("start_time < end_time", name="ck_o3a_shift_window"),
        CheckConstraint("status IN ('OPEN','SUBMITTED','APPROVED','CLOSED')", name="ck_o3a_shift_status"),
    )


class DailyConstructionReport(FieldRecord, Base):
    """A correction is a successor row, never a replacement of approved content."""

    __tablename__ = "field_daily_reports"
    report_number: Mapped[str] = mapped_column(String(120))
    revision: Mapped[int] = mapped_column(default=1)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("field_daily_reports.id"), unique=True)
    report_date: Mapped[date] = mapped_column(Date)
    shift_id: Mapped[int] = mapped_column(ForeignKey("field_shifts.id"), index=True)
    workfront_ids: Mapped[list] = mapped_column(JSON)
    reporting_party: Mapped[str] = mapped_column(String(240))
    weather: Mapped[dict] = mapped_column(JSON, default=dict)
    work_conditions: Mapped[str] = mapped_column(Text, default="")
    comments: Mapped[str] = mapped_column(Text, default="")
    summaries: Mapped[dict] = mapped_column(JSON, default=dict)
    source_references: Mapped[list] = mapped_column(JSON, default=list)
    document_references: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "report_number", "revision", name="uq_o3a_daily_revision"
        ),
        CheckConstraint("revision > 0", name="ck_o3a_daily_revision"),
        CheckConstraint("status IN ('DRAFT','SUBMITTED','REVIEWED','APPROVED')", name="ck_o3a_daily_status"),
    )


class Crew(FieldRecord, Base):
    __tablename__ = "field_crews"
    crew_code: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    trade: Mapped[str] = mapped_column(String(80))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("procurement_vendors.id"))
    supervisor_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "crew_code", name="uq_o3a_crew_code"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_o3a_crew_status"),
    )


class FieldEquipmentReference(FieldRecord, Base):
    """External equipment identity for field use; no asset registry or valuation."""

    __tablename__ = "field_equipment_references"
    source_system: Mapped[str] = mapped_column(String(120))
    external_id: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    equipment_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), default="AVAILABLE")
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "source_system", "external_id", name="uq_o3a_equipment_identity"
        ),
        CheckConstraint("status IN ('AVAILABLE','UNAVAILABLE')", name="ck_o3a_equipment_status"),
    )


class LaborUsage(FieldRecord, Base):
    __tablename__ = "field_labor_usage"
    record_code: Mapped[str] = mapped_column(String(120))
    shift_id: Mapped[int] = mapped_column(ForeignKey("field_shifts.id"), index=True)
    workfront_id: Mapped[int] = mapped_column(ForeignKey("field_workfronts.id"))
    crew_id: Mapped[int] = mapped_column(ForeignKey("field_crews.id"))
    trade: Mapped[str] = mapped_column(String(80))
    headcount: Mapped[int] = mapped_column()
    regular_hours: Mapped[Decimal] = mapped_column(QUANTITY)
    overtime_hours: Mapped[Decimal] = mapped_column(QUANTITY)
    productive_hours: Mapped[Decimal | None] = mapped_column(QUANTITY)
    nonproductive_hours: Mapped[Decimal | None] = mapped_column(QUANTITY)
    activity_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    document_references: Mapped[list] = mapped_column(JSON, default=list)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("field_labor_usage.id"), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="RECORDED")
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "record_code", name="uq_o3a_labor_code"),
        CheckConstraint("headcount > 0 AND regular_hours >= 0 AND overtime_hours >= 0", name="ck_o3a_labor_amount"),
        CheckConstraint("productive_hours IS NULL OR productive_hours >= 0", name="ck_o3a_labor_productive"),
        CheckConstraint("nonproductive_hours IS NULL OR nonproductive_hours >= 0", name="ck_o3a_labor_nonproductive"),
        CheckConstraint("status='RECORDED'", name="ck_o3a_labor_status"),
    )


class EquipmentUsage(FieldRecord, Base):
    __tablename__ = "field_equipment_usage"
    record_code: Mapped[str] = mapped_column(String(120))
    equipment_id: Mapped[int] = mapped_column(ForeignKey("field_equipment_references.id"))
    shift_id: Mapped[int] = mapped_column(ForeignKey("field_shifts.id"), index=True)
    workfront_id: Mapped[int] = mapped_column(ForeignKey("field_workfronts.id"))
    usage_type: Mapped[str] = mapped_column(String(80))
    operating_hours: Mapped[Decimal] = mapped_column(QUANTITY)
    idle_hours: Mapped[Decimal] = mapped_column(QUANTITY)
    standby_hours: Mapped[Decimal] = mapped_column(QUANTITY)
    downtime_hours: Mapped[Decimal] = mapped_column(QUANTITY)
    activity_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    document_references: Mapped[list] = mapped_column(JSON, default=list)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("field_equipment_usage.id"), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="RECORDED")
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "record_code", name="uq_o3a_equipment_usage_code"),
        CheckConstraint(
            "operating_hours >= 0 AND idle_hours >= 0 AND standby_hours >= 0 AND downtime_hours >= 0",
            name="ck_o3a_equipment_hours",
        ),
        CheckConstraint("status='RECORDED'", name="ck_o3a_equipment_usage_status"),
    )


class FieldCondition(FieldRecord, Base):
    __tablename__ = "field_conditions"
    condition_code: Mapped[str] = mapped_column(String(120))
    condition_date: Mapped[date] = mapped_column(Date)
    shift_id: Mapped[int] = mapped_column(ForeignKey("field_shifts.id"), index=True)
    workfront_id: Mapped[int] = mapped_column(ForeignKey("field_workfronts.id"))
    location_reference: Mapped[dict] = mapped_column(JSON)
    weather_condition: Mapped[str] = mapped_column(String(80))
    temperature: Mapped[Decimal | None] = mapped_column(QUANTITY)
    rainfall: Mapped[Decimal | None] = mapped_column(QUANTITY)
    wind: Mapped[Decimal | None] = mapped_column(QUANTITY)
    access_condition: Mapped[str] = mapped_column(String(80))
    site_condition: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    document_references: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="RECORDED")
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "condition_code", name="uq_o3a_condition_code"),
        CheckConstraint("rainfall IS NULL OR rainfall >= 0", name="ck_o3a_condition_rainfall"),
        CheckConstraint("wind IS NULL OR wind >= 0", name="ck_o3a_condition_wind"),
        CheckConstraint("status='RECORDED'", name="ck_o3a_condition_status"),
    )


class FieldClosure(ScopeRecord, Base):
    """Closing an approved report adds a fact without replacing its approved bytes."""

    __tablename__ = "field_record_closures"
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int] = mapped_column()
    entity_version: Mapped[int] = mapped_column()
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "entity_type", "entity_id", name="uq_o3a_closure"),
        CheckConstraint("entity_type='DailyConstructionReport'", name="ck_o3a_closure_type"),
    )


class FieldHistory(ScopeRecord, Base):
    __tablename__ = "field_history"
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int] = mapped_column()
    entity_version: Mapped[int] = mapped_column()
    previous_version: Mapped[int | None] = mapped_column()
    previous_state: Mapped[str | None] = mapped_column(String(32))
    new_state: Mapped[str | None] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        Index("ix_o3a_field_history_entity", "tenant_id", "project_workspace_id", "entity_type", "entity_id"),
    )


CORE_MODELS = (
    Workfront,
    FieldShift,
    DailyConstructionReport,
    Crew,
    FieldEquipmentReference,
    LaborUsage,
    EquipmentUsage,
    FieldCondition,
    FieldClosure,
    FieldHistory,
)
APPEND_ONLY = (LaborUsage, EquipmentUsage, FieldCondition, FieldClosure, FieldHistory)
TERMINAL = {DailyConstructionReport: {"APPROVED"}, FieldShift: {"CLOSED"}, Workfront: {"COMPLETE"}}


def _immutable(_mapper, _connection, _row):
    raise ValueError("Governed field fact is immutable")


def _terminal(_mapper, _connection, row):
    change = inspect(row).attrs.status.history
    old = change.deleted[0] if change.deleted else row.status
    if old in TERMINAL[type(row)]:
        _immutable(_mapper, _connection, row)


for _model in CORE_MODELS:
    event.listen(_model, "before_delete", _immutable)
    if _model in APPEND_ONLY:
        event.listen(_model, "before_update", _immutable)
    elif _model in TERMINAL:
        event.listen(_model, "before_update", _terminal)
