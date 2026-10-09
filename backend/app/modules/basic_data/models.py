"""Project-scoped Basic Data evidence and immutable assessment history."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
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


class ProjectBasicDataItem(Base):
    __tablename__ = "project_basic_data_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    requirement_code: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(120))
    availability: Mapped[str] = mapped_column(String(32), default="NOT_AVAILABLE")
    validation_state: Mapped[str] = mapped_column(String(32), default="NOT_VALIDATED")
    quality: Mapped[str] = mapped_column(String(40), default="NOT_VALIDATED")
    confidence: Mapped[str] = mapped_column(String(40), default="PRELIMINARY")
    source_type: Mapped[str] = mapped_column(String(80), default="REFERENCE")
    source_reference: Mapped[str | None] = mapped_column(String(500))
    source_version: Mapped[str | None] = mapped_column(String(120))
    source_hash: Mapped[str | None] = mapped_column(String(128))
    source_date: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    source_current: Mapped[bool] = mapped_column(default=True)
    evidence_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    limitations: Mapped[str] = mapped_column(Text, default="")
    assumptions: Mapped[str] = mapped_column(Text, default="")
    gaps: Mapped[str] = mapped_column(Text, default="")
    comments: Mapped[str] = mapped_column(Text, default="")
    validated_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "requirement_code", name="uq_basic_data_project_requirement"
        ),
        CheckConstraint(
            "availability IN ('NOT_AVAILABLE','PARTIALLY_AVAILABLE','AVAILABLE')", name="ck_basic_data_availability"
        ),
        CheckConstraint(
            "validation_state IN ('NOT_VALIDATED','UNDER_VALIDATION','VALIDATED','REJECTED')",
            name="ck_basic_data_validation",
        ),
        Index("ix_basic_data_register", "tenant_id", "project_workspace_id", "category", "id"),
        Index("ix_basic_data_validation_queue", "tenant_id", "project_workspace_id", "validation_state", "id"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class BasicDataReadinessAssessment(Base):
    __tablename__ = "basic_data_readiness_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    assessment_number: Mapped[str] = mapped_column(String(40))
    assessment_version: Mapped[int] = mapped_column(Integer, default=1)
    predecessor_id: Mapped[int | None] = mapped_column(ForeignKey("basic_data_readiness_assessments.id"))
    title: Mapped[str] = mapped_column(String(240), default="Basic Data Readiness")
    comments: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64))
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    assessment_hash: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "assessment_number", name="uq_basic_data_assessment_number"),
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "assessment_version", name="uq_basic_data_assessment_version"
        ),
        CheckConstraint("status IN ('DRAFT','IN_REVIEW','COMPLETED')", name="ck_basic_data_assessment_status"),
        CheckConstraint(
            "status != 'COMPLETED' OR (completed_at IS NOT NULL AND completed_by IS NOT NULL AND assessment_hash IS NOT NULL)",
            name="ck_basic_data_assessment_completed",
        ),
        Index("ix_basic_data_assessment_history", "tenant_id", "project_workspace_id", "status", "assessment_version"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class BasicDataCommand(Base):
    """Payload-bound retry ledger for live evidence and configuration commands."""

    __tablename__ = "basic_data_commands"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    idempotency_key: Mapped[str] = mapped_column(String(160))
    command_type: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_basic_data_command_key"),)


@event.listens_for(BasicDataReadinessAssessment, "before_update")
def _protect_completed(_mapper, _connection, record: BasicDataReadinessAssessment) -> None:
    state = inspect(record)
    old_status = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else record.status
    if old_status == "COMPLETED" and any(attr.history.has_changes() for attr in state.attrs):
        raise ValueError("Completed Basic Data assessment is immutable")


@event.listens_for(BasicDataReadinessAssessment, "before_delete")
def _protect_completed_delete(_mapper, _connection, record: BasicDataReadinessAssessment) -> None:
    if record.status == "COMPLETED":
        raise ValueError("Completed Basic Data assessment cannot be deleted")


@event.listens_for(BasicDataCommand, "before_update")
@event.listens_for(BasicDataCommand, "before_delete")
def _protect_command(_mapper, _connection, _record: BasicDataCommand) -> None:
    raise ValueError("Basic Data retry ledger is immutable")
