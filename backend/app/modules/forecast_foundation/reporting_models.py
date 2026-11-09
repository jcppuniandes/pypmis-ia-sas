"""Append-only projections; source domains retain their transactional authority."""

from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord


class ForecastReportSnapshot(ScopeRecord, Base):
    __tablename__ = "forecast_report_snapshots"
    forecast_version_id: Mapped[int] = mapped_column(ForeignKey("forecast_versions.id"), index=True)
    bundle_id: Mapped[int] = mapped_column(ForeignKey("progress_control_baseline_bundles.id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("project_controls_periods.id"), index=True)
    as_of: Mapped[date] = mapped_column(Date)
    schedule_version_id: Mapped[int] = mapped_column(ForeignKey("schedule_versions.id"))
    cost_baseline_id: Mapped[int] = mapped_column(ForeignKey("cost_baselines.id"))
    progress_snapshot_id: Mapped[int] = mapped_column(ForeignKey("progress_period_snapshots.id"))
    evm_snapshot_id: Mapped[int] = mapped_column(ForeignKey("progress_earned_value_snapshots.id"))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(default=1)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("forecast_report_snapshots.id"))
    status: Mapped[str] = mapped_column(String(24), default="PUBLISHED")
    source_refs_json: Mapped[dict] = mapped_column(JSON)
    source_snapshot_json: Mapped[dict] = mapped_column(JSON)
    metrics_json: Mapped[dict] = mapped_column(JSON)
    narratives_json: Mapped[list] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    published_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    published_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    reason: Mapped[str] = mapped_column(Text)
    evidence_reference: Mapped[str] = mapped_column(String(1000))
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "period_id", "revision", name="uq_forecast_report_revision"
        ),
        CheckConstraint("status = 'PUBLISHED'", name="ck_forecast_report_published"),
        CheckConstraint("revision > 0", name="ck_forecast_report_revision"),
    )


class ForecastLookAheadSnapshot(ScopeRecord, Base):
    __tablename__ = "forecast_lookahead_snapshots"
    forecast_version_id: Mapped[int] = mapped_column(ForeignKey("forecast_versions.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("project_controls_periods.id"))
    as_of: Mapped[date] = mapped_column(Date)
    schedule_version_id: Mapped[int] = mapped_column(ForeignKey("schedule_versions.id"))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    query_json: Mapped[dict] = mapped_column(JSON)
    result_snapshot_json: Mapped[dict] = mapped_column(JSON)
    source_refs_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)


def _immutable(_mapper, _connection, _row):
    raise ValueError("Published reporting and generated Look-Ahead snapshots are immutable; create a successor")


for _model in (ForecastReportSnapshot, ForecastLookAheadSnapshot):
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)
