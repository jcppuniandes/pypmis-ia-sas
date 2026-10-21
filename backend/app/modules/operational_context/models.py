"""Additive binding, common period header and immutable command receipts."""

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base
from app.domain.models import AdminConfiguration


class OperationalProjectBinding(Base):
    __tablename__ = "operational_project_bindings"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"))
    legacy_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    status: Mapped[str] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    validated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    effective_from: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "revision", name="uq_operational_binding_revision"),
        CheckConstraint(
            "status IN ('ACTIVE','NO_LEGACY_BINDING_REQUIRED','SUPERSEDED','REVOKED')",
            name="ck_operational_binding_status",
        ),
        CheckConstraint(
            "(status != 'ACTIVE' OR legacy_project_id IS NOT NULL) AND (status != 'NO_LEGACY_BINDING_REQUIRED' OR legacy_project_id IS NULL)",
            name="ck_operational_binding_reference",
        ),
        CheckConstraint("version > 0 AND revision > 0", name="ck_operational_binding_versions"),
        CheckConstraint(
            "(status IN ('ACTIVE','NO_LEGACY_BINDING_REQUIRED') AND effective_to IS NULL) OR (status IN ('SUPERSEDED','REVOKED') AND effective_to IS NOT NULL)",
            name="ck_operational_binding_effective_status",
        ),
        Index(
            "uq_operational_binding_active_workspace",
            "tenant_id",
            "project_workspace_id",
            unique=True,
            postgresql_where=text("status IN ('ACTIVE','NO_LEGACY_BINDING_REQUIRED')"),
            sqlite_where=text("status IN ('ACTIVE','NO_LEGACY_BINDING_REQUIRED')"),
        ),
        Index(
            "uq_operational_binding_active_legacy",
            "tenant_id",
            "legacy_project_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_operational_binding_lookup", "tenant_id", "project_workspace_id", "revision"),
    )


class ProjectControlsPeriod(Base):
    __tablename__ = "project_controls_periods"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"))
    period_code: Mapped[str] = mapped_column(String(80))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    profile_code: Mapped[str] = mapped_column(String(120))
    active_slot: Mapped[str | None] = mapped_column(String(100))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    source_configuration_revision: Mapped[int] = mapped_column(Integer)
    source_configuration_hash: Mapped[str] = mapped_column(String(64))
    schedule_data_date: Mapped[date | None] = mapped_column(Date)
    reopen_parent_id: Mapped[int | None] = mapped_column(ForeignKey("project_controls_periods.id"))
    reason: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    opened_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_started_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "period_code", "revision", name="uq_project_controls_period_revision"
        ),
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "profile_code", "active_slot", name="uq_project_controls_active_period"
        ),
        CheckConstraint("status IN ('OPEN','REVIEW','CLOSED','PUBLISHED')", name="ck_project_controls_period_status"),
        CheckConstraint(
            "period_end >= period_start AND version > 0 AND revision > 0", name="ck_project_controls_period_dates"
        ),
        CheckConstraint(
            "(status IN ('OPEN','REVIEW') AND active_slot IS NOT NULL) OR (status IN ('CLOSED','PUBLISHED') AND active_slot IS NULL)",
            name="ck_project_controls_period_active_slot",
        ),
        CheckConstraint(
            "status != 'PUBLISHED' OR (published_at IS NOT NULL AND published_by IS NOT NULL)",
            name="ck_project_controls_period_publication",
        ),
        Index("ix_project_controls_period_lookup", "tenant_id", "project_workspace_id", "status", "period_end"),
    )
    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}


class OperationalContextCommand(Base):
    __tablename__ = "operational_context_commands"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    idempotency_key: Mapped[str] = mapped_column(String(160))
    command_type: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict] = mapped_column(JSON)
    actor_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_operational_context_command_key"),)


def _prior_status(record):
    history = inspect(record).attrs.status.history
    return history.deleted[0] if history.deleted else record.status


@event.listens_for(ProjectControlsPeriod, "before_update")
@event.listens_for(ProjectControlsPeriod, "before_delete")
def _protect_period(_mapper, _connection, record):
    if _prior_status(record) == "PUBLISHED":
        raise ValueError("Published Project Controls period header is immutable")
    allowed = {
        "status",
        "version",
        "review_started_at",
        "review_started_by",
        "closed_at",
        "closed_by",
        "published_at",
        "published_by",
        "reason",
        "notes",
        "active_slot",
        "snapshot_json",
    }
    if any(attribute.history.has_changes() for attribute in inspect(record).attrs if attribute.key not in allowed):
        raise ValueError("Project Controls period identity/cutoff/policy is immutable; reopen a revision")


@event.listens_for(AdminConfiguration, "before_update")
@event.listens_for(AdminConfiguration, "before_delete")
def _protect_profile(_mapper, _connection, record):
    if record.kind == "operational_profile" and _prior_status(record) == "published":
        raise ValueError("Published Operational Profile is immutable; create successor")


@event.listens_for(OperationalContextCommand, "before_update")
@event.listens_for(OperationalContextCommand, "before_delete")
def _protect_receipt(_mapper, _connection, _record):
    raise ValueError("Operational command receipt is immutable")


@event.listens_for(OperationalProjectBinding, "before_delete")
def _protect_binding_delete(_mapper, _connection, _record):
    raise ValueError("Operational binding history cannot be deleted")


@event.listens_for(OperationalProjectBinding, "before_update")
def _protect_binding_history(_mapper, _connection, record):
    if _prior_status(record) in {"REVOKED", "SUPERSEDED"}:
        raise ValueError("Terminal operational binding history is immutable")
    allowed = {"status", "effective_to", "version"}
    if any(attribute.history.has_changes() for attribute in inspect(record).attrs if attribute.key not in allowed):
        raise ValueError("Operational binding identity is immutable; reconcile into a successor")
