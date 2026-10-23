"""Additive Cost aggregates. Legacy monetary tables are not this write authority."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base
from app.domain.models import AdminConfiguration
from app.modules.scope_foundation.models import ScopeRecord


class MutableCost:
    revision: Mapped[int] = mapped_column(default=1)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class CostCBS(MutableCost, ScopeRecord, Base):
    __tablename__ = "cost_cbs"
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("cost_cbs.id"))
    path: Mapped[str] = mapped_column(Text)
    level: Mapped[int] = mapped_column(default=1)
    sort_order: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    __table_args__ = (UniqueConstraint("tenant_id", "project_workspace_id", "code", name="uq_cost_cbs_code"),)


class CostCode(MutableCost, ScopeRecord, Base):
    __tablename__ = "cost_code_dictionary"
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    __table_args__ = (UniqueConstraint("tenant_id", "project_workspace_id", "code", name="uq_cost_code_dictionary"),)


class ControlAccount(MutableCost, ScopeRecord, Base):
    __tablename__ = "cost_control_accounts"
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    responsible_role: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    __table_args__ = (UniqueConstraint("tenant_id", "project_workspace_id", "code", name="uq_cost_account_code"),)


class CostMapping(ScopeRecord, Base):
    __tablename__ = "cost_mappings"
    source_kind: Mapped[str] = mapped_column(String(24))
    source_id: Mapped[int | None] = mapped_column()
    schedule_version_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_versions.id"))
    source_external_id: Mapped[str] = mapped_column(String(160), default="")
    cbs_id: Mapped[int | None] = mapped_column(ForeignKey("cost_cbs.id"))
    cost_code_id: Mapped[int | None] = mapped_column(ForeignKey("cost_code_dictionary.id"))
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("cost_control_accounts.id"))
    allocation_basis: Mapped[str] = mapped_column(String(100))
    quantity_basis: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    unit: Mapped[str] = mapped_column(String(40), default="")
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    currency: Mapped[str | None] = mapped_column(String(8))
    effective_revision: Mapped[str] = mapped_column(String(120))
    source_reference: Mapped[str] = mapped_column(String(1000))
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("cost_mappings.id"))
    reason: Mapped[str] = mapped_column(Text)


class CostRate(MutableCost, ScopeRecord, Base):
    __tablename__ = "cost_rates"
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    resource_type: Mapped[str] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(40))
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(8))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source_reference: Mapped[str] = mapped_column(String(1000))
    source_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("cost_rates.id"))
    published_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "code", "revision", name="uq_cost_rate_revision"),
    )


class CostAPU(MutableCost, ScopeRecord, Base):
    __tablename__ = "cost_apus"
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    unit: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(8))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    components_json: Mapped[list] = mapped_column(JSON)
    factors_json: Mapped[list] = mapped_column(JSON, default=list)
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    source_reference: Mapped[str] = mapped_column(String(1000))
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("cost_apus.id"))
    published_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "code", "revision", name="uq_cost_apu_revision"),
    )


class BudgetVersion(MutableCost, ScopeRecord, Base):
    __tablename__ = "cost_budget_versions"
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    budget_type: Mapped[str] = mapped_column(String(80), default="ORIGINAL")
    currency: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    predecessor_id: Mapped[int | None] = mapped_column(ForeignKey("cost_budget_versions.id"))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    source_references: Mapped[dict] = mapped_column(JSON, default=dict)
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "code", "revision", name="uq_cost_budget_revision"),
    )


class BudgetLine(ScopeRecord, Base):
    __tablename__ = "cost_budget_lines"
    budget_version_id: Mapped[int] = mapped_column(ForeignKey("cost_budget_versions.id"), index=True)
    line_code: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(1000))
    cbs_id: Mapped[int | None] = mapped_column(ForeignKey("cost_cbs.id"))
    cost_code_id: Mapped[int | None] = mapped_column(ForeignKey("cost_code_dictionary.id"))
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("cost_control_accounts.id"))
    scope_item_id: Mapped[int | None] = mapped_column(ForeignKey("scope_items.id"))
    plan_item_id: Mapped[int | None] = mapped_column(ForeignKey("scope_plan_items.id"))
    work_package_id: Mapped[int | None] = mapped_column(ForeignKey("awp_work_packages.id"))
    apu_id: Mapped[int | None] = mapped_column(ForeignKey("cost_apus.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    unit: Mapped[str] = mapped_column(String(40))
    rate: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(8))
    cost_class: Mapped[str] = mapped_column(String(40), default="DIRECT")
    time_phasing_basis: Mapped[str] = mapped_column(String(100), default="UNPHASED")
    source_json: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("budget_version_id", "line_code", name="uq_cost_budget_line"),)


class CostBaseline(MutableCost, ScopeRecord, Base):
    __tablename__ = "cost_baselines"
    code: Mapped[str] = mapped_column(String(120))
    budget_version_id: Mapped[int] = mapped_column(ForeignKey("cost_budget_versions.id"))
    previous_baseline_id: Mapped[int | None] = mapped_column(ForeignKey("cost_baselines.id"))
    status: Mapped[str] = mapped_column(String(24), default="CANDIDATE")
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "code", "revision", name="uq_cost_baseline_revision"),
    )


class CostPhasing(ScopeRecord, Base):
    __tablename__ = "cost_phasing"
    baseline_id: Mapped[int] = mapped_column(ForeignKey("cost_baselines.id"), index=True)
    budget_line_id: Mapped[int] = mapped_column(ForeignKey("cost_budget_lines.id"))
    method: Mapped[str] = mapped_column(String(40))
    revision: Mapped[int] = mapped_column(default=1)
    period_id: Mapped[int | None] = mapped_column(ForeignKey("project_controls_periods.id"))
    start_date: Mapped[date] = mapped_column(Date)
    finish_date: Mapped[date] = mapped_column(Date)
    schedule_version_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_versions.id"))
    source_external_id: Mapped[str] = mapped_column(String(160), default="")
    basis_json: Mapped[dict] = mapped_column(JSON)
    spread_json: Mapped[list] = mapped_column(JSON)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(8))
    content_hash: Mapped[str] = mapped_column(String(64))
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("cost_phasing.id"))
    reason: Mapped[str] = mapped_column(Text)


class CostHistory(ScopeRecord, Base):
    __tablename__ = "cost_history"
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int] = mapped_column(index=True)
    revision: Mapped[int] = mapped_column()
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    event_type: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text)


def _immutable(_mapper, _connection, _record):
    raise ValueError("Cost immutable history, approved budget/baseline or published APU/rate")


for _model in (CostMapping, CostPhasing, CostHistory):
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)


def _approved_guard(_mapper, _connection, record):
    state = inspect(record)
    old = state.attrs.status.history.deleted
    status = old[0] if old else record.status
    if status in {"APPROVED", "PUBLISHED", "SUPERSEDED", "REJECTED"}:
        _immutable(_mapper, _connection, record)


for _model in (BudgetVersion, CostBaseline, CostRate, CostAPU):
    event.listen(_model, "before_update", _approved_guard)
    event.listen(_model, "before_delete", _immutable)


@event.listens_for(BudgetLine, "before_update")
@event.listens_for(BudgetLine, "before_delete")
def _line_guard(_mapper, connection, record):
    from sqlalchemy import select

    status = connection.scalar(select(BudgetVersion.status).where(BudgetVersion.id == record.budget_version_id))
    if status != "DRAFT":
        _immutable(_mapper, connection, record)


@event.listens_for(AdminConfiguration, "before_update")
def _profile_guard(mapper, connection, record):
    if record.kind != "cost_profile":
        return
    history = inspect(record).attrs.status.history.deleted
    if (history[0] if history else record.status) == "published":
        _immutable(mapper, connection, record)


@event.listens_for(AdminConfiguration, "before_delete")
def _profile_delete_guard(mapper, connection, record):
    if record.kind == "cost_profile" and record.status == "published":
        _immutable(mapper, connection, record)
