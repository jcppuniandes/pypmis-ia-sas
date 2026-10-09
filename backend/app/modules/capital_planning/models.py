"""Persistent Wave 1 Strategic Capital Planning records.

The aggregates in this module deliberately stop before Idea, Project,
Portfolio Membership, Budget, Funding and FIN authority.  A demand records a
governed capital need; explicit origin records bridge an endorsed demand to an
Idea created by the existing Idea authority.
"""

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


class CapitalPlanningCycle(Base):
    __tablename__ = "capital_planning_cycles"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    cycle_number: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(220))
    planning_horizon_start: Mapped[date] = mapped_column(Date)
    planning_horizon_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    scope_workspace_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    responsible_organization_workspace_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_workspaces.id"))
    applicable_theme_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    capital_basis_currency: Mapped[str | None] = mapped_column(String(8))
    description: Mapped[str] = mapped_column(Text, default="")
    configuration_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    configuration_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    create_idempotency_key: Mapped[str] = mapped_column(String(160))
    open_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    review_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    close_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    last_modified_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "cycle_number", name="uq_capital_planning_cycle_number"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_capital_planning_cycle_create_key"),
        UniqueConstraint("tenant_id", "open_idempotency_key", name="uq_capital_planning_cycle_open_key"),
        UniqueConstraint("tenant_id", "review_idempotency_key", name="uq_capital_planning_cycle_review_key"),
        UniqueConstraint("tenant_id", "close_idempotency_key", name="uq_capital_planning_cycle_close_key"),
        CheckConstraint(
            "status IN ('DRAFT','OPEN','IN_REVIEW','CLOSED')",
            name="ck_capital_planning_cycle_status",
        ),
        CheckConstraint(
            "planning_horizon_end >= planning_horizon_start",
            name="ck_capital_planning_cycle_dates",
        ),
        Index("ix_capital_planning_cycle_queue", "tenant_id", "status", "updated_at", "id"),
        Index("ix_cp_cycle_responsible_workspace", "responsible_organization_workspace_id"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class StrategicCapitalDemand(Base):
    __tablename__ = "strategic_capital_demands"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    demand_number: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(220))
    description: Mapped[str] = mapped_column(Text, default="")
    planning_cycle_id: Mapped[int] = mapped_column(ForeignKey("capital_planning_cycles.id"), index=True)
    theme_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    strategic_objective_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    business_or_asset_need: Mapped[str] = mapped_column(Text)
    strategic_driver: Mapped[str] = mapped_column(String(120), index=True)
    demand_category: Mapped[str | None] = mapped_column(String(120), index=True)
    urgency: Mapped[str | None] = mapped_column(String(40), index=True)
    target_horizon: Mapped[str] = mapped_column(String(80), index=True)
    sponsor_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    owning_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    location_context: Mapped[str | None] = mapped_column(String(300))
    indicative_capital_need: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    currency_code: Mapped[str | None] = mapped_column(String(8), index=True)
    indicative_capital_range_low: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    indicative_capital_range_high: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    uncertainty_level: Mapped[str | None] = mapped_column(String(80), index=True)
    potential_portfolio_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    assumptions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    constraints_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    dependencies_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    readiness_json: Mapped[dict] = mapped_column(JSON, default=dict)
    configuration_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    configuration_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    demand_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    endorsed_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    endorsed_snapshot_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    create_idempotency_key: Mapped[str] = mapped_column(String(160))
    submit_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    review_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    return_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    endorse_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    defer_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    cancel_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    last_modified_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    endorser_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime)
    endorsed_at: Mapped[datetime | None] = mapped_column(DateTime)
    deferred_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "demand_number", name="uq_strategic_capital_demand_number"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_strategic_capital_demand_create_key"),
        UniqueConstraint("tenant_id", "submit_idempotency_key", name="uq_strategic_capital_demand_submit_key"),
        UniqueConstraint("tenant_id", "review_idempotency_key", name="uq_strategic_capital_demand_review_key"),
        UniqueConstraint("tenant_id", "return_idempotency_key", name="uq_strategic_capital_demand_return_key"),
        UniqueConstraint("tenant_id", "endorse_idempotency_key", name="uq_strategic_capital_demand_endorse_key"),
        UniqueConstraint("tenant_id", "defer_idempotency_key", name="uq_strategic_capital_demand_defer_key"),
        UniqueConstraint("tenant_id", "cancel_idempotency_key", name="uq_strategic_capital_demand_cancel_key"),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED','ENDORSED','DEFERRED','CANCELLED','SUPERSEDED')",
            name="ck_strategic_capital_demand_status",
        ),
        CheckConstraint(
            "indicative_capital_need IS NULL OR indicative_capital_need >= 0", name="ck_demand_need_nonnegative"
        ),
        CheckConstraint(
            "indicative_capital_range_low IS NULL OR indicative_capital_range_low >= 0",
            name="ck_demand_range_low_nonnegative",
        ),
        CheckConstraint(
            "indicative_capital_range_high IS NULL OR indicative_capital_range_high >= 0",
            name="ck_demand_range_high_nonnegative",
        ),
        CheckConstraint(
            "indicative_capital_range_high IS NULL OR indicative_capital_range_low IS NULL "
            "OR indicative_capital_range_high >= indicative_capital_range_low",
            name="ck_demand_range_order",
        ),
        Index("ix_strategic_capital_demand_queue", "tenant_id", "status", "updated_at", "id"),
        Index("ix_strategic_capital_demand_cycle_status", "tenant_id", "planning_cycle_id", "status"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class CapitalDemandIdeaOrigin(Base):
    __tablename__ = "capital_demand_idea_origins"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    capital_demand_id: Mapped[int] = mapped_column(ForeignKey("strategic_capital_demands.id"), index=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"), index=True)
    source_demand_version: Mapped[int] = mapped_column(Integer)
    source_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_configuration_hash: Mapped[str] = mapped_column(String(64), default="")
    origin_request_hash: Mapped[str] = mapped_column(String(64), index=True)
    origin_idempotency_key: Mapped[str] = mapped_column(String(160))
    originated_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    originated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idea_id", name="uq_capital_demand_origin_idea"),
        UniqueConstraint("tenant_id", "origin_idempotency_key", name="uq_capital_demand_origin_key"),
        Index("ix_capital_demand_origin_history", "tenant_id", "capital_demand_id", "originated_at", "id"),
    )


class CapitalPlanningCycleTheme(Base):
    """Indexed relationship between a planning cycle and applicable Theme codes."""

    __tablename__ = "capital_planning_cycle_themes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    planning_cycle_id: Mapped[int] = mapped_column(ForeignKey("capital_planning_cycles.id"), index=True)
    theme_code: Mapped[str] = mapped_column(String(120), index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "planning_cycle_id", "theme_code", name="uq_capital_cycle_theme"),
        Index("ix_capital_cycle_theme_lookup", "tenant_id", "theme_code", "planning_cycle_id"),
    )


class StrategicCapitalDemandTheme(Base):
    """Indexed N:M reference from a Demand to configured Theme codes."""

    __tablename__ = "strategic_capital_demand_themes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    capital_demand_id: Mapped[int] = mapped_column(ForeignKey("strategic_capital_demands.id"), index=True)
    theme_code: Mapped[str] = mapped_column(String(120), index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "capital_demand_id", "theme_code", name="uq_capital_demand_theme"),
        Index("ix_capital_demand_theme_lookup", "tenant_id", "theme_code", "capital_demand_id"),
    )


class StrategicCapitalDemandObjective(Base):
    """Indexed N:M reference from a Demand to Strategic Objective codes."""

    __tablename__ = "strategic_capital_demand_objectives"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    capital_demand_id: Mapped[int] = mapped_column(ForeignKey("strategic_capital_demands.id"), index=True)
    objective_code: Mapped[str] = mapped_column(String(120), index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "capital_demand_id", "objective_code", name="uq_capital_demand_objective"),
        Index("ix_capital_demand_objective_lookup", "tenant_id", "objective_code", "capital_demand_id"),
    )


class StrategicCapitalAllocationPlan(Base):
    """Governed strategic allocation intent for a Planning Cycle.

    Amounts are indicative planning envelopes.  This aggregate deliberately has
    no foreign keys to Budget, Funding, Resource Scenario, Portfolio Rank or FID
    authorities.
    """

    __tablename__ = "strategic_capital_allocation_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    allocation_plan_number: Mapped[str] = mapped_column(String(40), index=True)
    logical_code: Mapped[str] = mapped_column(String(80), index=True)
    plan_revision: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(220))
    description: Mapped[str] = mapped_column(Text, default="")
    planning_cycle_id: Mapped[int] = mapped_column(ForeignKey("capital_planning_cycles.id"), index=True)
    scope_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    portfolio_workspace_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    base_currency: Mapped[str | None] = mapped_column(String(8), index=True)
    allocation_basis: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    assumptions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    constraints_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    configuration_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_context_json: Mapped[dict] = mapped_column(JSON, default=dict)
    plan_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    endorsed_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    endorsed_snapshot_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    create_idempotency_key: Mapped[str] = mapped_column(String(160))
    submit_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    review_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    return_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    endorse_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    revision_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    last_modified_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    endorser_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime)
    endorsed_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "allocation_plan_number", name="uq_capital_allocation_plan_number"),
        UniqueConstraint("tenant_id", "logical_code", "plan_revision", name="uq_capital_allocation_plan_revision"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_capital_allocation_plan_create_key"),
        UniqueConstraint("tenant_id", "submit_idempotency_key", name="uq_capital_allocation_plan_submit_key"),
        UniqueConstraint("tenant_id", "review_idempotency_key", name="uq_capital_allocation_plan_review_key"),
        UniqueConstraint("tenant_id", "return_idempotency_key", name="uq_capital_allocation_plan_return_key"),
        UniqueConstraint("tenant_id", "endorse_idempotency_key", name="uq_capital_allocation_plan_endorse_key"),
        UniqueConstraint("tenant_id", "revision_idempotency_key", name="uq_capital_allocation_plan_revision_key"),
        CheckConstraint(
            "allocation_basis IN ('PERCENTAGE','INDICATIVE_AMOUNT','PERCENTAGE_AND_AMOUNT')",
            name="ck_capital_allocation_plan_basis",
        ),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED','ENDORSED','SUPERSEDED','CANCELLED')",
            name="ck_capital_allocation_plan_status",
        ),
        Index("ix_capital_allocation_plan_queue", "tenant_id", "status", "updated_at", "id"),
        Index("ix_capital_allocation_plan_cycle_scope", "tenant_id", "planning_cycle_id", "scope_workspace_id"),
        Index(
            "uq_capital_allocation_plan_current_no_portfolio",
            "tenant_id",
            "planning_cycle_id",
            "scope_workspace_id",
            unique=True,
            postgresql_where=text(
                "portfolio_workspace_id IS NULL AND status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED','ENDORSED')"
            ),
            sqlite_where=text(
                "portfolio_workspace_id IS NULL AND status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED','ENDORSED')"
            ),
        ),
        Index(
            "uq_capital_allocation_plan_current_portfolio",
            "tenant_id",
            "planning_cycle_id",
            "scope_workspace_id",
            "portfolio_workspace_id",
            unique=True,
            postgresql_where=text(
                "portfolio_workspace_id IS NOT NULL AND status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED','ENDORSED')"
            ),
            sqlite_where=text(
                "portfolio_workspace_id IS NOT NULL AND status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED','ENDORSED')"
            ),
        ),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class StrategicCapitalAllocationLine(Base):
    __tablename__ = "strategic_capital_allocation_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    allocation_plan_id: Mapped[int] = mapped_column(ForeignKey("strategic_capital_allocation_plans.id"), index=True)
    bucket_code: Mapped[str] = mapped_column(String(120), index=True)
    target_percentage: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    target_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    minimum_percentage: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    maximum_percentage: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    minimum_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    maximum_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    currency: Mapped[str | None] = mapped_column(String(8), index=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    strategic_objective_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    assumptions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    constraints_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    line_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "allocation_plan_id", "bucket_code", name="uq_capital_allocation_line_bucket"),
        CheckConstraint(
            "target_percentage IS NULL OR (target_percentage >= 0 AND target_percentage <= 100)",
            name="ck_capital_allocation_line_target_pct",
        ),
        CheckConstraint(
            "minimum_percentage IS NULL OR (minimum_percentage >= 0 AND minimum_percentage <= 100)",
            name="ck_capital_allocation_line_min_pct",
        ),
        CheckConstraint(
            "maximum_percentage IS NULL OR (maximum_percentage >= 0 AND maximum_percentage <= 100)",
            name="ck_capital_allocation_line_max_pct",
        ),
        CheckConstraint(
            "minimum_percentage IS NULL OR target_percentage IS NULL OR minimum_percentage <= target_percentage",
            name="ck_capital_allocation_line_min_target_pct",
        ),
        CheckConstraint(
            "maximum_percentage IS NULL OR target_percentage IS NULL OR target_percentage <= maximum_percentage",
            name="ck_capital_allocation_line_target_max_pct",
        ),
        CheckConstraint(
            "target_amount IS NULL OR target_amount >= 0",
            name="ck_capital_allocation_line_target_amount",
        ),
        CheckConstraint(
            "minimum_amount IS NULL OR minimum_amount >= 0",
            name="ck_capital_allocation_line_min_amount",
        ),
        CheckConstraint(
            "maximum_amount IS NULL OR maximum_amount >= 0",
            name="ck_capital_allocation_line_max_amount",
        ),
        CheckConstraint(
            "minimum_amount IS NULL OR target_amount IS NULL OR minimum_amount <= target_amount",
            name="ck_capital_allocation_line_min_target_amount",
        ),
        CheckConstraint(
            "maximum_amount IS NULL OR target_amount IS NULL OR target_amount <= maximum_amount",
            name="ck_capital_allocation_line_target_max_amount",
        ),
        Index("ix_capital_allocation_line_plan_bucket", "allocation_plan_id", "bucket_code"),
    )


class StrategicBucketClassification(Base):
    """One governed primary Bucket for one Demand/Project/Membership in a Plan."""

    __tablename__ = "strategic_bucket_classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    allocation_plan_id: Mapped[int] = mapped_column(ForeignKey("strategic_capital_allocation_plans.id"), index=True)
    capital_demand_id: Mapped[int | None] = mapped_column(ForeignKey("strategic_capital_demands.id"), index=True)
    project_workspace_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    portfolio_membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("portfolio_project_memberships.id"), index=True
    )
    bucket_code: Mapped[str] = mapped_column(String(120), index=True)
    classification_source: Mapped[str] = mapped_column(String(32), default="MANUAL", index=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    classification_hash: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    classified_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    classified_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_strategic_bucket_classification_key"),
        CheckConstraint(
            "(CASE WHEN capital_demand_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN project_workspace_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN portfolio_membership_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_strategic_bucket_classification_target",
        ),
        CheckConstraint(
            "classification_source IN ('MANUAL','THEME_DERIVED','RULE_DERIVED')",
            name="ck_strategic_bucket_classification_source",
        ),
        Index(
            "uq_strategic_bucket_classification_demand",
            "tenant_id",
            "allocation_plan_id",
            "capital_demand_id",
            unique=True,
            postgresql_where=text("capital_demand_id IS NOT NULL"),
            sqlite_where=text("capital_demand_id IS NOT NULL"),
        ),
        Index(
            "uq_strategic_bucket_classification_project",
            "tenant_id",
            "allocation_plan_id",
            "project_workspace_id",
            unique=True,
            postgresql_where=text("project_workspace_id IS NOT NULL"),
            sqlite_where=text("project_workspace_id IS NOT NULL"),
        ),
        Index(
            "uq_strategic_bucket_classification_membership",
            "tenant_id",
            "allocation_plan_id",
            "portfolio_membership_id",
            unique=True,
            postgresql_where=text("portfolio_membership_id IS NOT NULL"),
            sqlite_where=text("portfolio_membership_id IS NOT NULL"),
        ),
        Index("ix_strategic_bucket_classification_plan_bucket", "allocation_plan_id", "bucket_code"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class StrategicCapitalAllocationCommand(Base):
    """Durable idempotency ledger for plan-scoped batch mutations."""

    __tablename__ = "strategic_capital_allocation_commands"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    allocation_plan_id: Mapped[int] = mapped_column(ForeignKey("strategic_capital_allocation_plans.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    request_hash: Mapped[str] = mapped_column(String(64), index=True)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_capital_allocation_command_key"),
        Index("ix_capital_allocation_command_plan_action", "allocation_plan_id", "action", "occurred_at"),
    )


@event.listens_for(StrategicCapitalAllocationPlan, "before_update")
def _protect_terminal_allocation_plan(_mapper, _connection, target: StrategicCapitalAllocationPlan) -> None:
    state = inspect(target)
    previous = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else target.status
    changed = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
    if previous == "ENDORSED":
        if target.status != "SUPERSEDED" or not changed <= {"status", "updated_at", "revision_version"}:
            raise ValueError("Endorsed Strategic Capital Allocation Plans are immutable")
    elif previous in {"SUPERSEDED", "CANCELLED"} and changed:
        raise ValueError("Terminal Strategic Capital Allocation Plans are immutable")


def _protect_allocation_line(_mapper, connection, target: StrategicCapitalAllocationLine) -> None:
    status = connection.execute(
        StrategicCapitalAllocationPlan.__table__.select()
        .with_only_columns(StrategicCapitalAllocationPlan.status)
        .where(StrategicCapitalAllocationPlan.id == target.allocation_plan_id)
    ).scalar_one_or_none()
    if status in {"ENDORSED", "SUPERSEDED", "CANCELLED"}:
        raise ValueError("Allocation lines of a terminal plan are immutable")


event.listen(StrategicCapitalAllocationLine, "before_update", _protect_allocation_line)
event.listen(StrategicCapitalAllocationLine, "before_delete", _protect_allocation_line)
