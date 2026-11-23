"""Typed lot links, readiness evidence and explicit native consumer decisions."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.modules.quality.models import QualityRecord
from app.modules.scope_foundation.models import ScopeRecord


class QualityMapping(QualityRecord, Base):
    __tablename__ = "quality_mappings"
    receipt_line_id: Mapped[int] = mapped_column(ForeignKey("procurement_material_receipt_lines.id"), index=True)
    production_record_id: Mapped[int] = mapped_column(ForeignKey("field_production_records.id"), index=True)
    subject_key: Mapped[str] = mapped_column(String(500), index=True)
    receipt_reference: Mapped[dict] = mapped_column(JSON)
    production_reference: Mapped[dict] = mapped_column(JSON)
    lot_identifiers: Mapped[dict] = mapped_column(JSON)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    uom: Mapped[str | None] = mapped_column(String(40))
    document_reference: Mapped[dict] = mapped_column(JSON)
    action: Mapped[str] = mapped_column(String(12), default="SET")
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("quality_mappings.id"), unique=True)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "action IN ('SET','REMOVE') AND (quantity IS NULL OR quantity>0)", name="ck_quality_lot_link_values"
        ),
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "subject_key", "version", name="uq_quality_lot_link_stream"
        ),
    )


class QualityReadinessAssessment(QualityRecord, Base):
    __tablename__ = "quality_readiness_assessments"
    itp_id: Mapped[int] = mapped_column(ForeignKey("quality_itps.id"), index=True)
    subject_key: Mapped[str] = mapped_column(String(500), index=True)
    subject_reference: Mapped[dict] = mapped_column(JSON)
    as_of: Mapped[datetime] = mapped_column(DateTime)
    readiness_state: Mapped[str] = mapped_column(String(30))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "readiness_state IN ('READY','PARTIALLY_READY','NOT_READY','STALE','BROKEN_REFERENCE')",
            name="ck_quality_readiness_state",
        ),
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "itp_id", "subject_key", "version", name="uq_quality_readiness_stream"
        ),
    )


class QualityConsumerDecision(ScopeRecord, Base):
    __tablename__ = "quality_consumer_decisions"
    consumer: Mapped[str] = mapped_column(String(24), index=True)
    source_domain: Mapped[str] = mapped_column(String(24), default="QUALITY")
    source_entity_type: Mapped[str] = mapped_column(String(40))
    source_entity_id: Mapped[int] = mapped_column()
    source_root_id: Mapped[int] = mapped_column()
    source_version: Mapped[int] = mapped_column()
    source_hash: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    subject_key: Mapped[str] = mapped_column(String(500), index=True)
    decision: Mapped[str] = mapped_column(String(20))
    linked_entity_type: Mapped[str | None] = mapped_column(String(80))
    linked_entity_id: Mapped[int | None] = mapped_column()
    effective_period_id: Mapped[int | None] = mapped_column(ForeignKey("project_controls_periods.id"))
    mapping_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    previous_decision_id: Mapped[int | None] = mapped_column(ForeignKey("quality_consumer_decisions.id"))
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "consumer IN ('PROGRESS','AWP','COST','CONTRACTS','SCHEDULE','FIELD_OPERATIONS')",
            name="ck_quality_consumer",
        ),
        CheckConstraint(
            "source_domain='QUALITY' AND source_version>0 AND source_root_id>0 AND length(source_hash)=64",
            name="ck_quality_consumer_source",
        ),
        CheckConstraint("decision IN ('ADOPT','REJECT','RECONCILE')", name="ck_quality_consumer_decision"),
        UniqueConstraint(
            "tenant_id",
            "project_workspace_id",
            "consumer",
            "subject_key",
            "source_entity_type",
            "source_root_id",
            "version",
            name="uq_quality_consumer_stream",
        ),
        Index(
            "ix_quality_consumer_native_link",
            "tenant_id",
            "project_workspace_id",
            "consumer",
            "linked_entity_type",
            "linked_entity_id",
        ),
    )


MODELS = (QualityMapping, QualityReadinessAssessment, QualityConsumerDecision)
APPEND_ONLY = MODELS


def _immutable(_mapper, _connection, _row):
    raise ValueError("Quality evidence and consumer decisions are append-only")


for _model in MODELS:
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)
