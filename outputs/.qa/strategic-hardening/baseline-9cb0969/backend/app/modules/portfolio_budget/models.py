"""Tenant-scoped governed records for Gate 07G Budget Targets and Scenarios."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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


class PortfolioBudgetTarget(Base):
    __tablename__ = "portfolio_budget_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    portfolio_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    target_code: Mapped[str] = mapped_column(String(80), default="BUDGET-TARGET")
    target_revision: Mapped[int] = mapped_column(Integer, default=1)
    planning_horizon_start: Mapped[date] = mapped_column(Date)
    planning_horizon_end: Mapped[date] = mapped_column(Date)
    period_granularity: Mapped[str] = mapped_column(String(16), default="YEAR")
    budget_currency: Mapped[str] = mapped_column(String(8))
    total_budget_target: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    capex_budget_target: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    expense_budget_target: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    source_reference: Mapped[str] = mapped_column(String(300), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    target_hash: Mapped[str] = mapped_column(String(64), default="")
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    publish_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "portfolio_workspace_id",
            "target_code",
            "target_revision",
            name="uq_portfolio_budget_target_revision",
        ),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_portfolio_budget_target_create_key"),
        UniqueConstraint("tenant_id", "publish_idempotency_key", name="uq_portfolio_budget_target_publish_key"),
        CheckConstraint("status IN ('DRAFT','PUBLISHED','SUPERSEDED')", name="ck_portfolio_budget_target_status"),
        CheckConstraint("total_budget_target >= 0", name="ck_portfolio_budget_target_non_negative"),
        CheckConstraint(
            "capex_budget_target IS NULL OR capex_budget_target >= 0",
            name="ck_portfolio_budget_target_capex_non_negative",
        ),
        CheckConstraint(
            "expense_budget_target IS NULL OR expense_budget_target >= 0",
            name="ck_portfolio_budget_target_expense_non_negative",
        ),
        CheckConstraint(
            "COALESCE(capex_budget_target, 0) + COALESCE(expense_budget_target, 0) <= total_budget_target",
            name="ck_portfolio_budget_target_breakdown_total",
        ),
        CheckConstraint(
            "period_granularity IN ('YEAR','QUARTER','MONTH')",
            name="ck_portfolio_budget_target_granularity",
        ),
        Index("ix_portfolio_budget_target_tenant_portfolio", "tenant_id", "portfolio_workspace_id"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class PortfolioBudgetTargetPeriod(Base):
    __tablename__ = "portfolio_budget_target_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    budget_target_id: Mapped[int] = mapped_column(ForeignKey("portfolio_budget_targets.id"), index=True)
    period_key: Mapped[str] = mapped_column(String(20))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    capex_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    expense_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))

    __table_args__ = (
        UniqueConstraint("tenant_id", "budget_target_id", "period_key", name="uq_portfolio_budget_target_period"),
        CheckConstraint("amount >= 0", name="ck_portfolio_budget_target_period_non_negative"),
        CheckConstraint(
            "capex_amount IS NULL OR capex_amount >= 0",
            name="ck_portfolio_budget_target_period_capex_non_negative",
        ),
        CheckConstraint(
            "expense_amount IS NULL OR expense_amount >= 0",
            name="ck_portfolio_budget_target_period_expense_non_negative",
        ),
        CheckConstraint(
            "COALESCE(capex_amount, 0) + COALESCE(expense_amount, 0) <= amount",
            name="ck_portfolio_budget_target_period_breakdown_total",
        ),
    )


class PortfolioBudgetScenario(Base):
    __tablename__ = "portfolio_budget_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    portfolio_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    logical_code: Mapped[str] = mapped_column(String(100))
    scenario_name: Mapped[str] = mapped_column(String(180))
    scenario_code: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    analytical_status: Mapped[str] = mapped_column(String(20), default="UNDER_BUDGET")
    budget_target_id: Mapped[int] = mapped_column(ForeignKey("portfolio_budget_targets.id"), index=True)
    source_analysis_hash: Mapped[str] = mapped_column(String(64))
    source_prioritization_hash: Mapped[str] = mapped_column(String(64))
    membership_set_hash: Mapped[str] = mapped_column(String(64))
    evaluation_set_hash: Mapped[str] = mapped_column(String(64))
    source_configuration_hash: Mapped[str] = mapped_column(String(64))
    budget_target_hash: Mapped[str] = mapped_column(String(64))
    source_hash: Mapped[str] = mapped_column(String(64))
    scenario_hash: Mapped[str] = mapped_column(String(64), default="")
    creation_mode: Mapped[str] = mapped_column(String(32), default="EMPTY")
    time_phasing_method: Mapped[str] = mapped_column(String(32), default="UNPHASED")
    scenario_revision: Mapped[int] = mapped_column(Integer, default=1)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    clone_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    freeze_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    void_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    refresh_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "portfolio_workspace_id",
            "logical_code",
            "scenario_revision",
            name="uq_portfolio_budget_scenario_revision",
        ),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_portfolio_budget_scenario_create_key"),
        UniqueConstraint("tenant_id", "clone_idempotency_key", name="uq_portfolio_budget_scenario_clone_key"),
        UniqueConstraint("tenant_id", "freeze_idempotency_key", name="uq_portfolio_budget_scenario_freeze_key"),
        UniqueConstraint("tenant_id", "void_idempotency_key", name="uq_portfolio_budget_scenario_void_key"),
        UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_portfolio_budget_scenario_refresh_key"),
        CheckConstraint(
            "status IN ('DRAFT','IN_REVIEW','FROZEN','SUPERSEDED','VOIDED')",
            name="ck_portfolio_budget_scenario_status",
        ),
        CheckConstraint(
            "analytical_status IN ('WITHIN_BUDGET','OVER_BUDGET','UNDER_BUDGET')",
            name="ck_portfolio_budget_scenario_analytical_status",
        ),
        CheckConstraint(
            "creation_mode IN ('EMPTY','FROM_CURRENT_PRIORITY','COPY_EXISTING_SCENARIO')",
            name="ck_portfolio_budget_scenario_creation_mode",
        ),
        CheckConstraint(
            "time_phasing_method IN ('UNPHASED','LINEAR_BY_PROJECT_DATES','CUSTOM_PERIOD_PROFILE')",
            name="ck_portfolio_budget_scenario_time_phasing",
        ),
        Index("ix_portfolio_budget_scenario_tenant_portfolio", "tenant_id", "portfolio_workspace_id"),
        Index("ix_portfolio_budget_scenario_tenant_status", "tenant_id", "status"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class PortfolioBudgetScenarioProject(Base):
    __tablename__ = "portfolio_budget_scenario_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("portfolio_budget_scenarios.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    portfolio_membership_id: Mapped[int] = mapped_column(ForeignKey("portfolio_project_memberships.id"), index=True)
    project_number: Mapped[str] = mapped_column(String(120))
    project_name: Mapped[str] = mapped_column(String(180))
    portfolio_evaluation_score: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    portfolio_rank: Mapped[int] = mapped_column(Integer)
    strategic_alignment_score: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    risk_score: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    risk_bucket: Mapped[str] = mapped_column(String(40))
    gate07f_analysis_hash: Mapped[str] = mapped_column(String(64))
    cost_source_type: Mapped[str] = mapped_column(String(80))
    cost_source_reference: Mapped[str] = mapped_column(String(160))
    cost_source_hash: Mapped[str] = mapped_column(String(64))
    cost_value: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    capex_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    expense_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    unclassified_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=0)
    budget_breakdown_source: Mapped[str] = mapped_column(String(80), default="LEGACY_UNCLASSIFIED")
    currency: Mapped[str] = mapped_column(String(8))
    cost_as_of_date: Mapped[date] = mapped_column(Date)
    target_start: Mapped[date | None] = mapped_column(Date)
    target_finish: Mapped[date | None] = mapped_column(Date)
    strategic_objectives_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    risk_summary_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    expected_benefits: Mapped[str] = mapped_column(Text, default="")
    project_type: Mapped[str] = mapped_column(String(120), default="")
    planning_stage: Mapped[str] = mapped_column(String(80), default="")
    selection_state: Mapped[str] = mapped_column(String(20), default="UNSELECTED", index=True)
    forced_reason: Mapped[str | None] = mapped_column(Text)
    forced_actor_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    forced_at: Mapped[datetime | None] = mapped_column(DateTime)
    forced_authority_reference: Mapped[str | None] = mapped_column(String(300))
    period_profile_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    row_hash: Mapped[str] = mapped_column(String(64))
    last_selection_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "scenario_id", "project_workspace_id", name="uq_budget_scenario_project"),
        CheckConstraint(
            "selection_state IN ('SELECTED','UNSELECTED','FORCED_IN','FORCED_OUT')",
            name="ck_budget_scenario_project_selection",
        ),
        CheckConstraint(
            "selection_state NOT IN ('FORCED_IN','FORCED_OUT') OR forced_reason IS NOT NULL",
            name="ck_budget_scenario_project_forced_reason",
        ),
        CheckConstraint("cost_value >= 0", name="ck_budget_scenario_project_cost_non_negative"),
        CheckConstraint(
            "capex_amount IS NULL OR capex_amount >= 0",
            name="ck_budget_scenario_project_capex_non_negative",
        ),
        CheckConstraint(
            "expense_amount IS NULL OR expense_amount >= 0",
            name="ck_budget_scenario_project_expense_non_negative",
        ),
        CheckConstraint(
            "unclassified_amount >= 0",
            name="ck_budget_scenario_project_unclassified_non_negative",
        ),
        CheckConstraint(
            "COALESCE(capex_amount, 0) + COALESCE(expense_amount, 0) + unclassified_amount = cost_value",
            name="ck_budget_scenario_project_breakdown_total",
        ),
        Index("ix_budget_scenario_project_state", "scenario_id", "selection_state"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class ProjectDependency(Base):
    """Tenant-scoped strategic Project-to-Project dependency reused across portfolio gates."""

    __tablename__ = "project_dependencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    predecessor_project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    successor_project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    dependency_type: Mapped[str] = mapped_column(String(40), default="PREREQUISITE", index=True)
    dependency_strength: Mapped[str] = mapped_column(String(20), default="MANDATORY", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    source_reference: Mapped[str | None] = mapped_column(String(300))
    evidence_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    deactivate_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_project_dependency_create_key"),
        UniqueConstraint("tenant_id", "deactivate_idempotency_key", name="uq_project_dependency_deactivate_key"),
        CheckConstraint(
            "predecessor_project_workspace_id <> successor_project_workspace_id",
            name="ck_project_dependency_not_self",
        ),
        CheckConstraint(
            "dependency_type IN ('PREREQUISITE','ENABLING','SEQUENTIAL','SHARED_INFRASTRUCTURE','REGULATORY','FUNDING','OTHER')",
            name="ck_project_dependency_type",
        ),
        CheckConstraint(
            "dependency_strength IN ('MANDATORY','OPTIONAL')",
            name="ck_project_dependency_strength",
        ),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_project_dependency_status"),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_project_dependency_effective_range",
        ),
        Index(
            "uq_project_dependency_active",
            "tenant_id",
            "predecessor_project_workspace_id",
            "successor_project_workspace_id",
            "dependency_type",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "ix_project_dependency_tenant_projects",
            "tenant_id",
            "predecessor_project_workspace_id",
            "successor_project_workspace_id",
        ),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


@event.listens_for(PortfolioBudgetTarget, "before_update")
def _protect_published_target(_mapper, _connection, target: PortfolioBudgetTarget) -> None:
    state = inspect(target)
    history = state.attrs.status.history
    previous = history.deleted[0] if history.deleted else target.status
    changed = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
    if (
        previous == "PUBLISHED"
        and target.status == "SUPERSEDED"
        and changed
        <= {
            "status",
            "updated_at",
            "updated_by",
            "revision_version",
        }
    ):
        return
    if previous in {"PUBLISHED", "SUPERSEDED"} and changed:
        raise ValueError("Published Portfolio Budget Targets are immutable")


@event.listens_for(PortfolioBudgetScenario, "before_update")
def _protect_frozen_scenario(_mapper, _connection, scenario: PortfolioBudgetScenario) -> None:
    state = inspect(scenario)
    history = state.attrs.status.history
    previous = history.deleted[0] if history.deleted else scenario.status
    changed = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
    if previous in {"FROZEN", "SUPERSEDED", "VOIDED"} and changed:
        raise ValueError("Frozen Portfolio Budget Scenarios are immutable")


@event.listens_for(PortfolioBudgetScenarioProject, "before_update")
def _protect_frozen_rows(_mapper, connection, row: PortfolioBudgetScenarioProject) -> None:
    status = connection.execute(
        PortfolioBudgetScenario.__table__.select()
        .with_only_columns(PortfolioBudgetScenario.status)
        .where(PortfolioBudgetScenario.id == row.scenario_id)
    ).scalar_one_or_none()
    if status in {"FROZEN", "SUPERSEDED", "VOIDED"}:
        raise ValueError("Frozen Portfolio Budget Scenario rows are immutable")
