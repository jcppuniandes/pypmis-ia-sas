"""Tenant-scoped persistence for Gate 07H strategic resource planning."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class PortfolioResourceCapacityPlan(Base):
    __tablename__ = "portfolio_resource_capacity_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    portfolio_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    logical_code: Mapped[str] = mapped_column(String(100), default="RESOURCE-CAPACITY")
    plan_name: Mapped[str] = mapped_column(String(180))
    planning_horizon_start: Mapped[date] = mapped_column(Date)
    planning_horizon_end: Mapped[date] = mapped_column(Date)
    period_granularity: Mapped[str] = mapped_column(String(16), default="MONTH")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    plan_revision: Mapped[int] = mapped_column(Integer, default=1)
    source_reference: Mapped[str] = mapped_column(String(300), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    capacity_hash: Mapped[str] = mapped_column(String(64), default="")
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
            "tenant_id", "portfolio_workspace_id", "logical_code", "plan_revision",
            name="uq_portfolio_resource_capacity_revision",
        ),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_resource_capacity_create_key"),
        UniqueConstraint("tenant_id", "publish_idempotency_key", name="uq_resource_capacity_publish_key"),
        CheckConstraint("status IN ('DRAFT','PUBLISHED','SUPERSEDED')", name="ck_resource_capacity_status"),
        CheckConstraint(
            "period_granularity IN ('YEAR','QUARTER','MONTH')", name="ck_resource_capacity_granularity"
        ),
        CheckConstraint("planning_horizon_end >= planning_horizon_start", name="ck_resource_capacity_horizon"),
        Index("ix_resource_capacity_tenant_portfolio", "tenant_id", "portfolio_workspace_id"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class PortfolioResourceCapacityPeriod(Base):
    __tablename__ = "portfolio_resource_capacity_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    capacity_plan_id: Mapped[int] = mapped_column(ForeignKey("portfolio_resource_capacity_plans.id"), index=True)
    resource_role_key: Mapped[str] = mapped_column(String(100), index=True)
    resource_role_name: Mapped[str] = mapped_column(String(180))
    role_category: Mapped[str] = mapped_column(String(40), default="OTHER")
    period_key: Mapped[str] = mapped_column(String(20))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    capacity_value: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    unit: Mapped[str] = mapped_column(String(24), default="FTE")
    source_reference: Mapped[str] = mapped_column(String(300), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "capacity_plan_id", "resource_role_key", "period_key",
            name="uq_resource_capacity_role_period",
        ),
        CheckConstraint("capacity_value >= 0", name="ck_resource_capacity_non_negative"),
        CheckConstraint("unit IN ('FTE','HOURS','CREW_EQUIVALENT')", name="ck_resource_capacity_unit"),
        CheckConstraint("period_end >= period_start", name="ck_resource_capacity_period_range"),
        Index("ix_resource_capacity_period_lookup", "capacity_plan_id", "resource_role_key", "period_start"),
    )


class ProjectResourceDemandProfile(Base):
    __tablename__ = "project_resource_demand_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    logical_code: Mapped[str] = mapped_column(String(100), default="RESOURCE-DEMAND")
    profile_name: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    profile_revision: Mapped[int] = mapped_column(Integer, default=1)
    source_type: Mapped[str] = mapped_column(String(80))
    source_reference: Mapped[str] = mapped_column(String(300), default="")
    source_hash: Mapped[str] = mapped_column(String(64), default="")
    as_of_date: Mapped[date] = mapped_column(Date)
    planning_start: Mapped[date] = mapped_column(Date)
    planning_finish: Mapped[date] = mapped_column(Date)
    generation_method: Mapped[str] = mapped_column(String(40), default="EXPLICIT_PERIOD_PROFILE")
    approximation: Mapped[bool] = mapped_column(default=False)
    demand_hash: Mapped[str] = mapped_column(String(64), default="")
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
            "tenant_id", "project_workspace_id", "logical_code", "profile_revision",
            name="uq_project_resource_demand_revision",
        ),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_resource_demand_create_key"),
        UniqueConstraint("tenant_id", "publish_idempotency_key", name="uq_resource_demand_publish_key"),
        CheckConstraint("status IN ('DRAFT','PUBLISHED','SUPERSEDED')", name="ck_resource_demand_status"),
        CheckConstraint(
            "source_type IN ('PROJECT_RESOURCE_DEMAND_PROFILE','PROJECT_DEFINITION_RESOURCE_ESTIMATE',"
            "'TEMPLATE_RESOURCE_PROFILE','MANUAL_PORTFOLIO_PLANNING_PROFILE')",
            name="ck_resource_demand_source_type",
        ),
        CheckConstraint(
            "generation_method IN ('EXPLICIT_PERIOD_PROFILE','LINEAR_BY_PROJECT_DATES','TEMPLATE_BASED')",
            name="ck_resource_demand_generation",
        ),
        CheckConstraint("planning_finish >= planning_start", name="ck_resource_demand_horizon"),
        Index("ix_resource_demand_tenant_project", "tenant_id", "project_workspace_id"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class ProjectResourceDemandPeriod(Base):
    __tablename__ = "project_resource_demand_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    demand_profile_id: Mapped[int] = mapped_column(ForeignKey("project_resource_demand_profiles.id"), index=True)
    resource_role_key: Mapped[str] = mapped_column(String(100), index=True)
    resource_role_name: Mapped[str] = mapped_column(String(180))
    role_category: Mapped[str] = mapped_column(String(40), default="OTHER")
    period_key: Mapped[str] = mapped_column(String(20))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    demand_value: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    unit: Mapped[str] = mapped_column(String(24), default="FTE")
    source_reference: Mapped[str] = mapped_column(String(300), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "demand_profile_id", "resource_role_key", "period_key",
            name="uq_resource_demand_role_period",
        ),
        CheckConstraint("demand_value >= 0", name="ck_resource_demand_non_negative"),
        CheckConstraint("unit IN ('FTE','HOURS','CREW_EQUIVALENT')", name="ck_resource_demand_unit"),
        CheckConstraint("period_end >= period_start", name="ck_resource_demand_period_range"),
        Index("ix_resource_demand_period_lookup", "demand_profile_id", "resource_role_key", "period_start"),
    )


class PortfolioResourceScenario(Base):
    __tablename__ = "portfolio_resource_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    portfolio_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    logical_code: Mapped[str] = mapped_column(String(100))
    scenario_name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    capacity_plan_id: Mapped[int] = mapped_column(ForeignKey("portfolio_resource_capacity_plans.id"), index=True)
    capacity_plan_hash: Mapped[str] = mapped_column(String(64))
    source_analysis_hash: Mapped[str] = mapped_column(String(64))
    source_prioritization_hash: Mapped[str] = mapped_column(String(64))
    membership_set_hash: Mapped[str] = mapped_column(String(64))
    evaluation_set_hash: Mapped[str] = mapped_column(String(64))
    source_configuration_hash: Mapped[str] = mapped_column(String(64))
    source_hash: Mapped[str] = mapped_column(String(64))
    scenario_hash: Mapped[str] = mapped_column(String(64), default="")
    creation_mode: Mapped[str] = mapped_column(String(40), default="EMPTY")
    overload_policy: Mapped[str] = mapped_column(String(32), default="ALLOW_WITH_WARNING")
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
            "tenant_id", "portfolio_workspace_id", "logical_code", "scenario_revision",
            name="uq_portfolio_resource_scenario_revision",
        ),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_resource_scenario_create_key"),
        UniqueConstraint("tenant_id", "clone_idempotency_key", name="uq_resource_scenario_clone_key"),
        UniqueConstraint("tenant_id", "freeze_idempotency_key", name="uq_resource_scenario_freeze_key"),
        UniqueConstraint("tenant_id", "void_idempotency_key", name="uq_resource_scenario_void_key"),
        UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_resource_scenario_refresh_key"),
        CheckConstraint(
            "status IN ('DRAFT','IN_REVIEW','FROZEN','SUPERSEDED','VOIDED')", name="ck_resource_scenario_status"
        ),
        CheckConstraint(
            "creation_mode IN ('EMPTY','FROM_CURRENT_PRIORITY','COPY_EXISTING_SCENARIO')",
            name="ck_resource_scenario_creation_mode",
        ),
        CheckConstraint(
            "overload_policy IN ('ALLOW_WITH_WARNING','BLOCK_READY_STATE')", name="ck_resource_overload_policy"
        ),
        Index("ix_resource_scenario_tenant_portfolio", "tenant_id", "portfolio_workspace_id"),
        Index("ix_resource_scenario_tenant_status", "tenant_id", "status"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class PortfolioResourceScenarioProject(Base):
    __tablename__ = "portfolio_resource_scenario_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("portfolio_resource_scenarios.id"), index=True)
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
    resource_demand_profile_id: Mapped[int | None] = mapped_column(ForeignKey("project_resource_demand_profiles.id"))
    resource_demand_hash: Mapped[str] = mapped_column(String(64), default="")
    source_project_start: Mapped[date | None] = mapped_column(Date)
    source_project_finish: Mapped[date | None] = mapped_column(Date)
    scenario_start: Mapped[date | None] = mapped_column(Date)
    scenario_finish: Mapped[date | None] = mapped_column(Date)
    schedule_shift_days: Mapped[int] = mapped_column(Integer, default=0)
    timing_method: Mapped[str] = mapped_column(String(40), default="NO_SHIFT")
    selection_state: Mapped[str] = mapped_column(String(20), default="UNSELECTED", index=True)
    forced_reason: Mapped[str | None] = mapped_column(Text)
    forced_actor_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    forced_at: Mapped[datetime | None] = mapped_column(DateTime)
    forced_authority_reference: Mapped[str | None] = mapped_column(String(300))
    row_hash: Mapped[str] = mapped_column(String(64))
    last_selection_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    last_timing_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "scenario_id", "project_workspace_id", name="uq_resource_scenario_project"),
        CheckConstraint(
            "selection_state IN ('SELECTED','UNSELECTED','FORCED_IN','FORCED_OUT')",
            name="ck_resource_scenario_project_selection",
        ),
        CheckConstraint(
            "selection_state NOT IN ('FORCED_IN','FORCED_OUT') OR forced_reason IS NOT NULL",
            name="ck_resource_scenario_project_forced_reason",
        ),
        CheckConstraint(
            "timing_method IN ('NO_SHIFT','SHIFT_START_KEEP_DURATION','CUSTOM_SCENARIO_DATES')",
            name="ck_resource_scenario_project_timing",
        ),
        CheckConstraint(
            "scenario_start IS NULL OR scenario_finish IS NULL OR scenario_finish >= scenario_start",
            name="ck_resource_scenario_project_dates",
        ),
        Index("ix_resource_scenario_project_state", "scenario_id", "selection_state"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


@event.listens_for(PortfolioResourceCapacityPlan, "before_update")
def _protect_published_capacity(_mapper, _connection, target: PortfolioResourceCapacityPlan) -> None:
    state = inspect(target)
    previous = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else target.status
    changed = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
    if previous == "PUBLISHED" and target.status == "SUPERSEDED" and changed <= {
        "status", "updated_at", "updated_by", "revision_version"
    }:
        return
    if previous in {"PUBLISHED", "SUPERSEDED"} and changed:
        raise ValueError("Published Portfolio Resource Capacity Plans are immutable")


@event.listens_for(ProjectResourceDemandProfile, "before_update")
def _protect_published_demand(_mapper, _connection, target: ProjectResourceDemandProfile) -> None:
    state = inspect(target)
    previous = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else target.status
    changed = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
    if previous == "PUBLISHED" and target.status == "SUPERSEDED" and changed <= {
        "status", "updated_at", "updated_by", "revision_version"
    }:
        return
    if previous in {"PUBLISHED", "SUPERSEDED"} and changed:
        raise ValueError("Published Project Resource Demand Profiles are immutable")


@event.listens_for(PortfolioResourceScenario, "before_update")
def _protect_frozen_scenario(_mapper, _connection, scenario: PortfolioResourceScenario) -> None:
    state = inspect(scenario)
    previous = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else scenario.status
    if previous in {"FROZEN", "SUPERSEDED", "VOIDED"} and any(
        attribute.history.has_changes() for attribute in state.attrs
    ):
        raise ValueError("Frozen Portfolio Resource Scenarios are immutable")


@event.listens_for(PortfolioResourceScenarioProject, "before_update")
def _protect_frozen_rows(_mapper, connection, row: PortfolioResourceScenarioProject) -> None:
    status = connection.execute(
        PortfolioResourceScenario.__table__.select()
        .with_only_columns(PortfolioResourceScenario.status)
        .where(PortfolioResourceScenario.id == row.scenario_id)
    ).scalar_one_or_none()
    if status in {"FROZEN", "SUPERSEDED", "VOIDED"}:
        raise ValueError("Frozen Portfolio Resource Scenario rows are immutable")
