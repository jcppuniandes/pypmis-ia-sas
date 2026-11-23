"""Quality dispositions, corrections and granular acceptance facts.

These objects never own Field production, Progress quantities, AWP releases or
contractual/financial consequences. Reinspection reuses InspectionRequest.
"""

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

from app.database.session import Base
from app.modules.quality.models import QualityRecord


class QualityNCR(QualityRecord, Base):
    __tablename__ = "quality_ncrs"
    ncr_number: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(40))
    responsible_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    subject_key: Mapped[str] = mapped_column(String(500), index=True)
    subject_reference: Mapped[dict] = mapped_column(JSON)
    inspection_record_id: Mapped[int | None] = mapped_column(ForeignKey("quality_inspection_records.id"))
    test_record_id: Mapped[int | None] = mapped_column(ForeignKey("quality_test_records.id"))
    requirement_reference: Mapped[str] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime)
    due_date: Mapped[date | None] = mapped_column(Date)
    document_reference: Mapped[dict] = mapped_column(JSON)
    disposition_id: Mapped[int | None] = mapped_column(ForeignKey("quality_dispositions.id"))
    disposition_reference: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    issued_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "ncr_number", name="uq_quality_ncr_number"),
        CheckConstraint(
            "status IN ('DRAFT','ISSUED','UNDER_REVIEW','DISPOSITIONED','CORRECTED','VERIFIED','CLOSED','REJECTED','CANCELLED')",
            name="ck_quality_ncr_status",
        ),
        CheckConstraint("inspection_record_id IS NULL OR test_record_id IS NULL", name="ck_quality_ncr_single_result"),
        CheckConstraint(
            "status NOT IN ('DISPOSITIONED','CORRECTED','VERIFIED','CLOSED') OR disposition_id IS NOT NULL",
            name="ck_quality_ncr_disposition_required",
        ),
        Index("ix_quality_ncr_subject_status", "tenant_id", "project_workspace_id", "subject_key", "status"),
    )


class QualityDisposition(QualityRecord, Base):
    __tablename__ = "quality_dispositions"
    ncr_id: Mapped[int] = mapped_column(ForeignKey("quality_ncrs.id"), index=True)
    disposition_code: Mapped[str] = mapped_column(String(120))
    disposition_type: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    engineering_decision_reference: Mapped[dict | None] = mapped_column(JSON)
    document_reference: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="PROPOSED")
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "disposition_code", name="uq_quality_disposition_code"),
        CheckConstraint("status IN ('PROPOSED','APPROVED','REJECTED')", name="ck_quality_disposition_status"),
    )


class QualityCorrectiveAction(QualityRecord, Base):
    __tablename__ = "quality_corrective_actions"
    action_code: Mapped[str] = mapped_column(String(120))
    action_kind: Mapped[str] = mapped_column(String(40), default="CORRECTIVE")
    ncr_id: Mapped[int | None] = mapped_column(ForeignKey("quality_ncrs.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    due_date: Mapped[date] = mapped_column(Date)
    subject_key: Mapped[str] = mapped_column(String(500), index=True)
    subject_reference: Mapped[dict] = mapped_column(JSON)
    document_reference: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    completion_reference: Mapped[dict | None] = mapped_column(JSON)
    completion_document_reference: Mapped[dict | None] = mapped_column(JSON)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    verification_reference: Mapped[dict | None] = mapped_column(JSON)
    verification_document_reference: Mapped[dict | None] = mapped_column(JSON)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "action_code", name="uq_quality_action_code"),
        CheckConstraint("action_kind IN ('CORRECTIVE','PREVENTIVE','IMPROVEMENT')", name="ck_quality_action_kind"),
        CheckConstraint("action_kind <> 'CORRECTIVE' OR ncr_id IS NOT NULL", name="ck_quality_corrective_ncr_required"),
        CheckConstraint(
            "status IN ('OPEN','IN_PROGRESS','COMPLETED','VERIFIED','CLOSED')", name="ck_quality_action_status"
        ),
        CheckConstraint(
            "status NOT IN ('COMPLETED','VERIFIED','CLOSED') OR completed_by IS NOT NULL",
            name="ck_quality_action_completion",
        ),
    )


class QualityPunchItem(QualityRecord, Base):
    __tablename__ = "quality_punch_items"
    item_number: Mapped[str] = mapped_column(String(120))
    subject_key: Mapped[str] = mapped_column(String(500), index=True)
    subject_reference: Mapped[dict] = mapped_column(JSON)
    location_reference: Mapped[dict] = mapped_column(JSON)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(80))
    responsible_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    due_date: Mapped[date] = mapped_column(Date)
    document_reference: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    completion_document_reference: Mapped[dict | None] = mapped_column(JSON)
    verification_document_reference: Mapped[dict | None] = mapped_column(JSON)
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "item_number", name="uq_quality_punch_number"),
        CheckConstraint(
            "status IN ('OPEN','IN_PROGRESS','READY_FOR_VERIFICATION','CLOSED')", name="ck_quality_punch_status"
        ),
        CheckConstraint("status <> 'CLOSED' OR verified_by IS NOT NULL", name="ck_quality_punch_verification"),
    )


class QualityAcceptance(QualityRecord, Base):
    __tablename__ = "quality_acceptances"
    acceptance_code: Mapped[str] = mapped_column(String(120))
    revision: Mapped[int] = mapped_column(default=1)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("quality_acceptances.id"), unique=True)
    subject_key: Mapped[str] = mapped_column(String(500), index=True)
    subject_reference: Mapped[dict] = mapped_column(JSON)
    itp_id: Mapped[int] = mapped_column(ForeignKey("quality_itps.id"), index=True)
    acceptance_profile_code: Mapped[str] = mapped_column(String(80), default="COMPLETE_CONTROLS")
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    uom: Mapped[str] = mapped_column(String(40))
    effective_at: Mapped[datetime] = mapped_column(DateTime)
    document_reference: Mapped[dict] = mapped_column(JSON)
    source_references: Mapped[list] = mapped_column(JSON)
    readiness_snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="APPROVED")
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "acceptance_code", "revision", name="uq_quality_acceptance_revision"
        ),
        CheckConstraint("status='APPROVED' AND revision>0 AND quantity>0", name="ck_quality_acceptance_fact"),
    )


APPEND_ONLY = (QualityAcceptance,)
TERMINAL = {
    QualityNCR: {"CLOSED", "REJECTED", "CANCELLED"},
    QualityDisposition: {"APPROVED", "REJECTED"},
    QualityCorrectiveAction: {"CLOSED"},
    QualityPunchItem: {"CLOSED"},
}
MODELS = (*TERMINAL, *APPEND_ONLY)


def _immutable(_mapper, _connection, _row):
    raise ValueError("Quality terminal facts and acceptances are immutable")


def _terminal(_mapper, _connection, row):
    history = inspect(row).attrs.status.history
    previous = history.deleted[0] if history.deleted else row.status
    if previous in TERMINAL[type(row)]:
        _immutable(_mapper, _connection, row)


for _model in MODELS:
    event.listen(_model, "before_delete", _immutable)
    event.listen(_model, "before_update", _immutable if _model in APPEND_ONLY else _terminal)
