"""Only governed aggregate snapshots and receipts; schedule authority stays external."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class AggregateColumns:
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    number: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(240), default="QRA Foundation")
    comments: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64))
    aggregate_json: Mapped[dict] = mapped_column(JSON, default=dict)
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    hash: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CostSourceReadinessAssessment(AggregateColumns, Base):
    __tablename__ = "qra_cost_source_assessments"
    predecessor_id: Mapped[int | None] = mapped_column(ForeignKey("qra_cost_source_assessments.id"))
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_qra_cost_number"),
        UniqueConstraint("tenant_id", "project_workspace_id", "version", name="uq_qra_cost_version"),
        CheckConstraint("status IN ('DRAFT','IN_REVIEW','COMPLETED')", name="ck_qra_cost_status"),
        CheckConstraint("version > 0 AND revision_version > 0", name="ck_qra_cost_versions"),
        CheckConstraint(
            "status != 'COMPLETED' OR (hash IS NOT NULL AND completed_at IS NOT NULL AND approved_by IS NOT NULL AND reviewed_by IS NOT NULL)",
            name="ck_qra_cost_completed",
        ),
        Index("ix_qra_cost_history", "tenant_id", "project_workspace_id", "status", "version"),
    )
    __mapper_args__ = {"version_id_col": AggregateColumns.revision_version, "version_id_generator": False}


class ScheduleSourceReadinessAssessment(AggregateColumns, Base):
    __tablename__ = "qra_schedule_source_assessments"
    predecessor_id: Mapped[int | None] = mapped_column(ForeignKey("qra_schedule_source_assessments.id"))
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_qra_schedule_number"),
        UniqueConstraint("tenant_id", "project_workspace_id", "version", name="uq_qra_schedule_version"),
        CheckConstraint("status IN ('DRAFT','IN_REVIEW','COMPLETED')", name="ck_qra_schedule_status"),
        CheckConstraint("version > 0 AND revision_version > 0", name="ck_qra_schedule_versions"),
        CheckConstraint(
            "status != 'COMPLETED' OR (hash IS NOT NULL AND completed_at IS NOT NULL AND approved_by IS NOT NULL AND reviewed_by IS NOT NULL)",
            name="ck_qra_schedule_completed",
        ),
        Index("ix_qra_schedule_history", "tenant_id", "project_workspace_id", "status", "version"),
    )
    __mapper_args__ = {"version_id_col": AggregateColumns.revision_version, "version_id_generator": False}


class QraModelDefinition(AggregateColumns, Base):
    __tablename__ = "qra_model_definitions"
    predecessor_id: Mapped[int | None] = mapped_column(ForeignKey("qra_model_definitions.id"))
    analysis_type: Mapped[str] = mapped_column(String(40), default="COST_QRA")
    model_number: Mapped[str] = mapped_column(String(40), index=True)
    cost_source_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("qra_cost_source_assessments.id"), index=True
    )
    schedule_source_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("qra_schedule_source_assessments.id"), index=True
    )
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_qra_model_number"),
        UniqueConstraint("tenant_id", "model_number", "version", name="uq_qra_model_identity_version"),
        UniqueConstraint("tenant_id", "project_workspace_id", "version", name="uq_qra_model_version"),
        CheckConstraint("status IN ('DRAFT','IN_REVIEW','APPROVED_FOR_ANALYSIS')", name="ck_qra_model_status"),
        CheckConstraint("version > 0 AND revision_version > 0", name="ck_qra_model_versions"),
        CheckConstraint(
            "analysis_type IN ('COST_QRA','SCHEDULE_QRA','INTEGRATED_COST_SCHEDULE_QRA')",
            name="ck_qra_model_analysis_type",
        ),
        CheckConstraint(
            "status != 'APPROVED_FOR_ANALYSIS' OR (hash IS NOT NULL AND completed_at IS NOT NULL AND approved_by IS NOT NULL AND reviewed_by IS NOT NULL)",
            name="ck_qra_model_approved",
        ),
        Index("ix_qra_model_history", "tenant_id", "project_workspace_id", "status", "version"),
    )
    __mapper_args__ = {"version_id_col": AggregateColumns.revision_version, "version_id_generator": False}


class QraCommand(Base):
    __tablename__ = "qra_commands"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    idempotency_key: Mapped[str] = mapped_column(String(160))
    command_type: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_qra_command_key"),)


def _protect(_mapper, _connection, record):
    state = inspect(record)
    history = state.attrs.status.history
    previous = history.deleted[0] if history.deleted else record.status
    if previous in {"COMPLETED", "APPROVED_FOR_ANALYSIS"} and any(a.history.has_changes() for a in state.attrs):
        raise ValueError("Completed QRA source / approved model definition is immutable")


def _protect_delete(_mapper, _connection, record):
    if record.status in {"COMPLETED", "APPROVED_FOR_ANALYSIS"}:
        raise ValueError("Completed QRA source / approved model definition cannot be deleted")


for _model in (CostSourceReadinessAssessment, ScheduleSourceReadinessAssessment, QraModelDefinition):
    event.listen(_model, "before_update", _protect)
    event.listen(_model, "before_delete", _protect_delete)


@event.listens_for(QraCommand, "before_update")
@event.listens_for(QraCommand, "before_delete")
def _protect_receipt(_mapper, _connection, _record):
    raise ValueError("QRA command receipt is immutable")
