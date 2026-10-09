"""Two additive aggregate/receipt tables, preserving canonical Project identity."""

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


class OwnerCapabilityAssessment(Base):
    __tablename__ = "owner_capability_assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    assessment_number: Mapped[str] = mapped_column(String(40))
    assessment_version: Mapped[int] = mapped_column(Integer, default=1)
    predecessor_id: Mapped[int | None] = mapped_column(ForeignKey("owner_capability_assessments.id"))
    title: Mapped[str] = mapped_column(String(240), default="Owner Capability Readiness")
    comments: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64))
    aggregate_json: Mapped[dict] = mapped_column(JSON, default=dict)
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    assessment_hash: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "assessment_number", name="uq_owner_capability_number"),
        UniqueConstraint("tenant_id", "project_workspace_id", "assessment_version", name="uq_owner_capability_version"),
        CheckConstraint("status IN ('DRAFT','IN_REVIEW','COMPLETED')", name="ck_owner_capability_status"),
        CheckConstraint("assessment_version > 0 AND revision_version > 0", name="ck_owner_capability_versions"),
        CheckConstraint(
            "status != 'COMPLETED' OR (completed_at IS NOT NULL AND completed_by IS NOT NULL AND reviewed_by IS NOT NULL AND assessment_hash IS NOT NULL)",
            name="ck_owner_capability_completed",
        ),
        Index("ix_owner_capability_history", "tenant_id", "project_workspace_id", "status", "assessment_version"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class OwnerCapabilityCommand(Base):
    __tablename__ = "owner_capability_commands"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    idempotency_key: Mapped[str] = mapped_column(String(160))
    command_type: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_owner_capability_command_key"),)


@event.listens_for(OwnerCapabilityAssessment, "before_update")
def _protect_completed(_mapper, _connection, record):
    state = inspect(record)
    previous = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else record.status
    if previous == "COMPLETED" and any(a.history.has_changes() for a in state.attrs):
        raise ValueError("Completed Owner Capability assessment is immutable")


@event.listens_for(OwnerCapabilityAssessment, "before_delete")
def _protect_completed_delete(_mapper, _connection, record):
    if record.status == "COMPLETED":
        raise ValueError("Completed Owner Capability assessment cannot be deleted")


@event.listens_for(OwnerCapabilityCommand, "before_update")
@event.listens_for(OwnerCapabilityCommand, "before_delete")
def _protect_receipt(_mapper, _connection, _record):
    raise ValueError("Owner Capability retry ledger is immutable")
