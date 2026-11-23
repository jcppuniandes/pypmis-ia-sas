"""Canonical inspection and test facts; upstream evidence stays in its owning domain."""

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
    event,
    inspect,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord


class QualityRecord(ScopeRecord):
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    source_hash: Mapped[str] = mapped_column(String(64), default="")


class GovernedVersion:
    code: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(300))
    revision: Mapped[int] = mapped_column(default=1)
    effective_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)


class QualityPlan(GovernedVersion, QualityRecord, Base):
    __tablename__ = "quality_plans"
    scope: Mapped[str] = mapped_column(Text)
    responsible_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    source_references: Mapped[list] = mapped_column(JSON, default=list)
    document_references: Mapped[list] = mapped_column(JSON, default=list)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("quality_plans.id"), unique=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "code", "revision", name="uq_quality_plan_revision"),
        CheckConstraint("revision > 0 AND status IN ('DRAFT','SUBMITTED','APPROVED')", name="ck_quality_plan_state"),
    )


class InspectionTestPlan(GovernedVersion, QualityRecord, Base):
    __tablename__ = "quality_itps"
    quality_plan_id: Mapped[int] = mapped_column(ForeignKey("quality_plans.id"), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    discipline: Mapped[str] = mapped_column(String(80), default="GENERAL")
    source_references: Mapped[list] = mapped_column(JSON, default=list)
    engineering_reference: Mapped[dict] = mapped_column(JSON)
    document_references: Mapped[list] = mapped_column(JSON, default=list)
    items_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("quality_itps.id"), unique=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "code", "revision", name="uq_quality_itp_revision"),
        CheckConstraint("revision > 0 AND status IN ('DRAFT','SUBMITTED','APPROVED')", name="ck_quality_itp_state"),
    )


class ITPItem(QualityRecord, Base):
    __tablename__ = "quality_itp_items"
    itp_id: Mapped[int] = mapped_column(ForeignKey("quality_itps.id"), index=True)
    itp_item_code: Mapped[str] = mapped_column(String(120))
    sequence: Mapped[int] = mapped_column()
    activity: Mapped[str] = mapped_column(String(500))
    control_type: Mapped[str] = mapped_column(String(80))
    requirement_reference: Mapped[str] = mapped_column(Text)
    acceptance_criteria: Mapped[str] = mapped_column(Text)
    responsible_party: Mapped[str] = mapped_column(String(300))
    witness_party: Mapped[str] = mapped_column(String(300), default="")
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=True)
    next_step_rule: Mapped[str] = mapped_column(String(500), default="")
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    inspection_required: Mapped[bool] = mapped_column(Boolean, default=True)
    test_required: Mapped[bool] = mapped_column(Boolean, default=False)
    test_type: Mapped[str | None] = mapped_column(String(80))
    test_uom: Mapped[str | None] = mapped_column(String(40))
    test_lower_limit: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    test_upper_limit: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    checklist_template_code: Mapped[str] = mapped_column(String(120))
    checklist_template: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    __table_args__ = (
        UniqueConstraint("itp_id", "itp_item_code", name="uq_quality_itp_item_code"),
        UniqueConstraint("itp_id", "sequence", name="uq_quality_itp_item_sequence"),
        CheckConstraint("sequence > 0 AND status='ACTIVE'", name="ck_quality_itp_item_state"),
        CheckConstraint(
            "test_lower_limit IS NULL OR test_upper_limit IS NULL OR test_lower_limit <= test_upper_limit",
            name="ck_quality_item_limits",
        ),
    )


class RequestFields:
    request_number: Mapped[str] = mapped_column(String(120))
    itp_item_id: Mapped[int] = mapped_column(ForeignKey("quality_itp_items.id"), index=True)
    subject_key: Mapped[str] = mapped_column(String(240), index=True)
    subject_reference: Mapped[dict] = mapped_column(JSON)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    uom: Mapped[str | None] = mapped_column(String(40))
    requested_at: Mapped[datetime] = mapped_column(DateTime)
    requested_for: Mapped[datetime] = mapped_column(DateTime)
    requester_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    inspector_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    document_references: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")


class InspectionRequest(RequestFields, QualityRecord, Base):
    __tablename__ = "quality_inspection_requests"
    inspection_type: Mapped[str] = mapped_column(String(80))
    reinspection_of_id: Mapped[int | None] = mapped_column(ForeignKey("quality_inspection_records.id"), index=True)
    corrective_action_id: Mapped[int | None] = mapped_column(ForeignKey("quality_corrective_actions.id"), index=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "request_number", name="uq_quality_inspection_request"),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','SCHEDULED','IN_INSPECTION','COMPLETED','CANCELLED')",
            name="ck_quality_inspection_request_state",
        ),
        CheckConstraint(
            "requested_at <= requested_for AND (quantity IS NULL OR quantity > 0)",
            name="ck_quality_inspection_request_times",
        ),
    )


class TestRequest(RequestFields, QualityRecord, Base):
    __tablename__ = "quality_test_requests"
    test_type: Mapped[str] = mapped_column(String(80))
    laboratory_vendor_id: Mapped[int | None] = mapped_column(ForeignKey("procurement_vendors.id"))
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "request_number", name="uq_quality_test_request"),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','SCHEDULED','IN_TEST','COMPLETED','CANCELLED')",
            name="ck_quality_test_request_state",
        ),
        CheckConstraint(
            "requested_at <= requested_for AND (quantity IS NULL OR quantity > 0)", name="ck_quality_test_request_times"
        ),
    )


class ResultFields:
    record_number: Mapped[str] = mapped_column(String(120))
    itp_item_id: Mapped[int] = mapped_column(ForeignKey("quality_itp_items.id"), index=True)
    subject_key: Mapped[str] = mapped_column(String(240), index=True)
    subject_reference: Mapped[dict] = mapped_column(JSON)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    uom: Mapped[str | None] = mapped_column(String(40))
    engineering_reference: Mapped[dict] = mapped_column(JSON)
    requirement_reference: Mapped[dict] = mapped_column(JSON)
    inspector_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    result: Mapped[str] = mapped_column(String(32))
    comments: Mapped[str] = mapped_column(Text, default="")
    document_references: Mapped[list] = mapped_column(JSON, default=list)
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")


class InspectionRecord(ResultFields, QualityRecord, Base):
    __tablename__ = "quality_inspection_records"
    request_id: Mapped[int] = mapped_column(ForeignKey("quality_inspection_requests.id"), unique=True)
    inspected_at: Mapped[datetime] = mapped_column(DateTime)
    checklist_template: Mapped[dict] = mapped_column(JSON)
    checklist_responses: Mapped[list] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "record_number", name="uq_quality_inspection_record"),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','CLOSED') AND result IN ('PASS','FAIL','CONDITIONAL','NOT_APPLICABLE')",
            name="ck_quality_inspection_result",
        ),
        CheckConstraint(
            "(status <> 'CLOSED' AND closed_by IS NULL AND closed_at IS NULL) OR (status='CLOSED' AND closed_by IS NOT NULL AND closed_at IS NOT NULL)",
            name="ck_quality_inspection_closed",
        ),
    )


class TestRecord(ResultFields, QualityRecord, Base):
    __tablename__ = "quality_test_records"
    request_id: Mapped[int] = mapped_column(ForeignKey("quality_test_requests.id"), unique=True)
    tested_at: Mapped[datetime] = mapped_column(DateTime)
    method: Mapped[str] = mapped_column(String(500))
    standard: Mapped[str] = mapped_column(String(500))
    laboratory_vendor_id: Mapped[int | None] = mapped_column(ForeignKey("procurement_vendors.id"))
    equipment_reference: Mapped[dict | None] = mapped_column(JSON)
    measurements: Mapped[list] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "record_number", name="uq_quality_test_record"),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','CLOSED') AND result IN ('PASS','FAIL','CONDITIONAL','NOT_APPLICABLE')",
            name="ck_quality_test_result",
        ),
        CheckConstraint(
            "(status <> 'CLOSED' AND closed_by IS NULL AND closed_at IS NULL) OR (status='CLOSED' AND closed_by IS NOT NULL AND closed_at IS NOT NULL)",
            name="ck_quality_test_closed",
        ),
    )


class ControlPointDecision(QualityRecord, Base):
    __tablename__ = "quality_control_point_decisions"
    itp_item_id: Mapped[int] = mapped_column(ForeignKey("quality_itp_items.id"), index=True)
    subject_key: Mapped[str] = mapped_column(String(240), index=True)
    subject_reference: Mapped[dict] = mapped_column(JSON)
    inspection_record_id: Mapped[int | None] = mapped_column(ForeignKey("quality_inspection_records.id"))
    test_record_id: Mapped[int | None] = mapped_column(ForeignKey("quality_test_records.id"))
    source_references: Mapped[list] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(Text)
    document_references: Mapped[list] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "project_workspace_id",
            "itp_item_id",
            "subject_key",
            "version",
            name="uq_quality_control_decision_stream",
        ),
        CheckConstraint("decision IN ('RELEASED','WAIVED')", name="ck_quality_control_decision"),
    )


class QualityHistory(ScopeRecord, Base):
    __tablename__ = "quality_history"
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int] = mapped_column()
    entity_version: Mapped[int] = mapped_column()
    previous_version: Mapped[int | None] = mapped_column()
    previous_state: Mapped[str | None] = mapped_column(String(32))
    new_state: Mapped[str | None] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(Text)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        Index("ix_quality_history_entity", "tenant_id", "project_workspace_id", "entity_type", "entity_id"),
    )


CORE_MODELS = (
    QualityPlan,
    InspectionTestPlan,
    ITPItem,
    InspectionRequest,
    InspectionRecord,
    TestRequest,
    TestRecord,
    ControlPointDecision,
    QualityHistory,
)
APPEND_ONLY = (ControlPointDecision, QualityHistory)
TERMINAL = {
    QualityPlan: {"APPROVED"},
    InspectionTestPlan: {"APPROVED"},
    InspectionRequest: {"COMPLETED", "CANCELLED"},
    TestRequest: {"COMPLETED", "CANCELLED"},
    InspectionRecord: {"CLOSED"},
    TestRecord: {"CLOSED"},
}


def _immutable(_mapper, _connection, _row):
    raise ValueError("Governed Quality fact is immutable")


def _terminal(_mapper, _connection, row):
    history = inspect(row).attrs.status.history
    old = history.deleted[0] if history.deleted else row.status
    if old in TERMINAL[type(row)]:
        _immutable(_mapper, _connection, row)


def _itp_item_guard(_mapper, connection, row):
    state = connection.scalar(select(InspectionTestPlan.status).where(InspectionTestPlan.id == row.itp_id))
    if state != "DRAFT":
        _immutable(_mapper, connection, row)


for _model in CORE_MODELS:
    event.listen(_model, "before_delete", _immutable)
    if _model in APPEND_ONLY:
        event.listen(_model, "before_update", _immutable)
    elif _model in TERMINAL:
        event.listen(_model, "before_update", _terminal)
event.listen(ITPItem, "before_update", _itp_item_guard)
