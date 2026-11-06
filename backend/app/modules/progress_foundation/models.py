"""Progress aggregates and append-only, actor-attributed revision history."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
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

from app.database.session import Base
from app.domain.models import AdminConfiguration
from app.modules.scope_foundation.models import ScopeRecord


class ProgressRule(ScopeRecord, Base):
    __tablename__ = "progress_rules"
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    method: Mapped[str] = mapped_column(String(60))
    steps_json: Mapped[list] = mapped_column(JSON)
    ordered: Mapped[bool] = mapped_column(Boolean, default=True)
    scope_natures: Mapped[list] = mapped_column(JSON)
    package_types: Mapped[list] = mapped_column(JSON)
    measurement_basis: Mapped[dict] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(default=1)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("progress_rules.id"))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    published_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "code", "revision", name="uq_progress_rule_revision"),
    )


class ProgressMeasurement(ScopeRecord, Base):
    __tablename__ = "progress_measurements"
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    subject_key: Mapped[str] = mapped_column(String(300), index=True)
    progress_type: Mapped[str] = mapped_column(String(24))
    method: Mapped[str] = mapped_column(String(60))
    source_domain: Mapped[str] = mapped_column(String(80))
    source_reference: Mapped[str] = mapped_column(String(1000))
    scope_item_id: Mapped[int | None] = mapped_column(ForeignKey("scope_items.id"))
    plan_item_id: Mapped[int | None] = mapped_column(ForeignKey("scope_plan_items.id"))
    work_package_id: Mapped[int | None] = mapped_column(ForeignKey("awp_work_packages.id"))
    activity_external_id: Mapped[str] = mapped_column(String(160), default="")
    schedule_version_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_versions.id"))
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("cost_control_accounts.id"))
    wbs_external_id: Mapped[str] = mapped_column(String(160), default="")
    area: Mapped[str] = mapped_column(String(150), default="")
    system: Mapped[str] = mapped_column(String(150), default="")
    discipline: Mapped[str] = mapped_column(String(150), default="")
    scope_nature: Mapped[str] = mapped_column(String(24))
    phase: Mapped[str] = mapped_column(String(24))
    period_id: Mapped[int] = mapped_column(ForeignKey("project_controls_periods.id"), index=True)
    measurement_date: Mapped[date] = mapped_column(Date)
    as_of: Mapped[date] = mapped_column(Date)
    numerator: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    denominator: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    unit: Mapped[str] = mapped_column(String(40))
    weight: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    weighting_basis: Mapped[str] = mapped_column(String(60))
    progress_value: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    period_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    cumulative_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    period_progress: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    overrun: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    revision: Mapped[int] = mapped_column(default=1)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("progress_measurements.id"))
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("progress_rules.id"))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    input_json: Mapped[dict] = mapped_column(JSON)
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    source_hash: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    evidence_json: Mapped[list] = mapped_column(JSON)
    correction_kind: Mapped[str] = mapped_column(String(40), default="NONE")
    prepared_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    certified_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    certified_at: Mapped[datetime | None] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "code", "revision", name="uq_progress_measurement_revision"
        ),
    )


class ProgressHistory(ScopeRecord, Base):
    __tablename__ = "progress_history"
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[int] = mapped_column(index=True)
    revision: Mapped[int] = mapped_column()
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    event_type: Mapped[str] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(Text)


def _immutable(_mapper, _connection, _record):
    raise ValueError("Approved Progress, published rule/profile and history are immutable; create a successor")


def _terminal_guard(mapper, connection, record):
    deleted = inspect(record).attrs.status.history.deleted
    if (deleted[0] if deleted else record.status) in {"APPROVED", "PUBLISHED", "SUPERSEDED", "REJECTED"}:
        _immutable(mapper, connection, record)


for _model in (ProgressMeasurement, ProgressRule):
    event.listen(_model, "before_update", _terminal_guard)
    event.listen(_model, "before_delete", _immutable)
event.listen(ProgressHistory, "before_update", _immutable)
event.listen(ProgressHistory, "before_delete", _immutable)


@event.listens_for(AdminConfiguration, "before_update")
@event.listens_for(AdminConfiguration, "before_delete")
def _profile_guard(mapper, connection, record):
    if record.kind == "progress_profile":
        old = inspect(record).attrs.status.history.deleted
        if (old[0] if old else record.status) == "published":
            _immutable(mapper, connection, record)
