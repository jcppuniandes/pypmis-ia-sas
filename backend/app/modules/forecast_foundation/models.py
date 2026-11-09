"""Forecast aggregates own projections only; upstream authorities remain immutable."""

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
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord


class ForecastVersion(ScopeRecord, Base):
    __tablename__ = "forecast_versions"
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    revision: Mapped[int] = mapped_column(default=1)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("forecast_versions.id"))
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    bundle_id: Mapped[int] = mapped_column(ForeignKey("progress_control_baseline_bundles.id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("project_controls_periods.id"))
    as_of: Mapped[date] = mapped_column(Date)
    schedule_version_id: Mapped[int] = mapped_column(ForeignKey("schedule_versions.id"))
    data_date_reference: Mapped[str] = mapped_column(String(80))
    currency: Mapped[str] = mapped_column(String(8))
    method: Mapped[str] = mapped_column(String(60))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[str] = mapped_column(String(24))
    confidence_rationale: Mapped[str] = mapped_column(Text)
    data_completeness: Mapped[str] = mapped_column(String(200))
    assumption_maturity: Mapped[str] = mapped_column(String(200))
    source_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_hashes_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    prepared_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    evidence_ref: Mapped[str] = mapped_column(String(1000))
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "code", "revision", name="uq_forecast_version_revision"),
        CheckConstraint("status IN ('DRAFT','UNDER_REVIEW','APPROVED','REJECTED')", name="ck_forecast_version_status"),
        CheckConstraint("confidence IN ('LOW','MEDIUM','HIGH')", name="ck_forecast_confidence"),
    )


class ForecastAssumption(ScopeRecord, Base):
    __tablename__ = "forecast_assumptions"
    forecast_version_id: Mapped[int] = mapped_column(ForeignKey("forecast_versions.id"), index=True)
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(60))
    value: Mapped[str] = mapped_column(String(1000))
    unit: Mapped[str] = mapped_column(String(80))
    currency: Mapped[str | None] = mapped_column(String(8))
    source_reference: Mapped[str] = mapped_column(String(1000))
    owner_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    effective_date: Mapped[date] = mapped_column(Date)
    confidence: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24))
    evidence_ref: Mapped[str] = mapped_column(String(1000))
    rationale: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("forecast_version_id", "code", name="uq_forecast_assumption_code"),
        CheckConstraint("status IN ('DRAFT','CONFIRMED')", name="ck_forecast_assumption_status"),
    )


class ForecastComponent(ScopeRecord, Base):
    __tablename__ = "forecast_components"
    forecast_version_id: Mapped[int] = mapped_column(ForeignKey("forecast_versions.id"), index=True)
    component_kind: Mapped[str] = mapped_column(String(24))
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    method: Mapped[str] = mapped_column(String(60))
    assumption_codes: Mapped[list] = mapped_column(JSON)
    scope_item_id: Mapped[int | None] = mapped_column(ForeignKey("scope_items.id"))
    plan_item_id: Mapped[int | None] = mapped_column(ForeignKey("scope_plan_items.id"))
    work_package_id: Mapped[int | None] = mapped_column(ForeignKey("awp_work_packages.id"))
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("cost_control_accounts.id"))
    cbs_id: Mapped[int | None] = mapped_column(ForeignKey("cost_cbs.id"))
    cost_code_id: Mapped[int | None] = mapped_column(ForeignKey("cost_code_dictionary.id"))
    schedule_version_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_versions.id"))
    activity_external_id: Mapped[str] = mapped_column(String(160), default="")
    wbs_external_id: Mapped[str] = mapped_column(String(160), default="")
    area: Mapped[str] = mapped_column(String(150), default="")
    zone: Mapped[str] = mapped_column(String(150), default="")
    system: Mapped[str] = mapped_column(String(150), default="")
    discipline: Mapped[str] = mapped_column(String(150), default="")
    currency: Mapped[str | None] = mapped_column(String(8))
    unit: Mapped[str] = mapped_column(String(80), default="")
    inputs: Mapped[dict] = mapped_column(JSON)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    forecast_finish: Mapped[date | None] = mapped_column(Date)
    content_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("forecast_version_id", "component_kind", "code", name="uq_forecast_component_code"),
        CheckConstraint("component_kind IN ('COST','TIME','MILESTONE','RESOURCE')", name="ck_forecast_component_kind"),
    )


class ForecastHistory(ScopeRecord, Base):
    __tablename__ = "forecast_history"
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int] = mapped_column()
    revision: Mapped[int] = mapped_column()
    event_type: Mapped[str] = mapped_column(String(100))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)


def _immutable(_mapper, _connection, _row):
    raise ValueError("FORECAST_IMMUTABLE_CREATE_SUCCESSOR")


@event.listens_for(ForecastVersion, "before_update")
def _version_guard(_mapper, _connection, row):
    prior = inspect(row).attrs.status.history.deleted
    if (prior[0] if prior else row.status) in {"APPROVED", "REJECTED"}:
        _immutable(_mapper, _connection, row)


def _child_guard(_mapper, connection, row):
    state = inspect(row)
    if state.identity is not None and state.attrs.forecast_version_id.history.has_changes():
        # The old FK may be unloaded/expired; relying on ORM attribute history
        # alone would miss the original owner. Check the stored identity before
        # the parent's lifecycle check, so a DRAFT target cannot unfreeze a row.
        table = state.mapper.local_table
        stored_parent_id = connection.scalar(select(table.c.forecast_version_id).where(table.c.id == state.identity[0]))
        if stored_parent_id != row.forecast_version_id:
            raise ValueError("FORECAST_CHILD_PARENT_IMMUTABLE")
    status = connection.scalar(select(ForecastVersion.status).where(ForecastVersion.id == row.forecast_version_id))
    if status != "DRAFT":
        _immutable(_mapper, connection, row)


for _model in (ForecastAssumption, ForecastComponent):
    for _operation in ("before_insert", "before_update", "before_delete"):
        event.listen(_model, _operation, _child_guard)
event.listen(ForecastVersion, "before_delete", _immutable)
event.listen(ForecastHistory, "before_update", _immutable)
event.listen(ForecastHistory, "before_delete", _immutable)
