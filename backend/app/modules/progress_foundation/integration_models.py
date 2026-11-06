"""Integrated reference bundles and append-only reporting, never source authority."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
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


class ProjectControlBaselineBundle(ScopeRecord, Base):
    __tablename__ = "progress_control_baseline_bundles"
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    revision: Mapped[int] = mapped_column(default=1)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("progress_control_baseline_bundles.id"))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    scope_baseline_id: Mapped[int] = mapped_column(ForeignKey("scope_baselines.id"))
    schedule_baseline_id: Mapped[int] = mapped_column(ForeignKey("schedule_baselines.id"))
    cost_baseline_id: Mapped[int] = mapped_column(ForeignKey("cost_baselines.id"))
    progress_profile_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    effective_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(8))
    source_snapshot_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "code", "revision", name="uq_progress_control_bundle_revision"
        ),
        CheckConstraint("status IN ('DRAFT','UNDER_REVIEW','APPROVED')", name="ck_progress_control_bundle_status"),
    )


class ProgressPeriodSnapshot(ScopeRecord, Base):
    """One report set per O1A period; O1A remains the only period state writer."""

    __tablename__ = "progress_period_snapshots"
    period_id: Mapped[int] = mapped_column(ForeignKey("project_controls_periods.id"), unique=True)
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(24), default="FROZEN")
    candidate_snapshot_json: Mapped[list] = mapped_column(JSON)
    report_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    period_source_hash: Mapped[str] = mapped_column(String(64))
    frozen_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    frozen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("status IN ('FROZEN','CLOSED','PUBLISHED')", name="ck_progress_period_snapshot_status"),
    )


class EarnedValueSnapshot(ScopeRecord, Base):
    __tablename__ = "progress_earned_value_snapshots"
    bundle_id: Mapped[int] = mapped_column(ForeignKey("progress_control_baseline_bundles.id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("project_controls_periods.id"))
    as_of: Mapped[date] = mapped_column(Date)
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(String(8))
    pv: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    ev: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    ac: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    cpi: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    spi: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("status IN ('COMPUTABLE','NOT_COMPUTABLE')", name="ck_progress_evm_snapshot_status"),
    )


def _immutable(_mapper, _connection, _row):
    raise ValueError("Progress approved bundle and reporting history are immutable; create a successor")


@event.listens_for(ProjectControlBaselineBundle, "before_update")
def _bundle_guard(_mapper, _connection, row):
    old = inspect(row).attrs.status.history.deleted
    if (old[0] if old else row.status) == "APPROVED":
        _immutable(_mapper, _connection, row)


@event.listens_for(ProgressPeriodSnapshot, "before_update")
def _period_snapshot_guard(_mapper, _connection, row):
    state = inspect(row)
    prior = state.attrs.status.history.deleted
    old = prior[0] if prior else row.status
    if old == "PUBLISHED":
        _immutable(_mapper, _connection, row)
    immutable_fields = {"candidate_snapshot_json", "period_id", "period_source_hash", "frozen_at", "frozen_by"}
    if old == "CLOSED":
        immutable_fields |= {"report_snapshot_json", "content_hash", "closed_at", "closed_by"}
    if any(state.attrs[name].history.has_changes() for name in immutable_fields):
        _immutable(_mapper, _connection, row)


for _model in (ProjectControlBaselineBundle, ProgressPeriodSnapshot, EarnedValueSnapshot):
    event.listen(_model, "before_delete", _immutable)
event.listen(EarnedValueSnapshot, "before_update", _immutable)
