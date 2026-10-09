"""add Gate 07H Portfolio Resource Planning and Scenarios

Revision ID: 20260825_0047
Revises: 20260825_0046
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0047"
down_revision: str | None = "20260825_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "portfolio_resource_capacity_plans" in inspector.get_table_names():
        return
    op.create_table(
        "portfolio_resource_capacity_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("portfolio_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("logical_code", sa.String(100), nullable=False, server_default="RESOURCE-CAPACITY"),
        sa.Column("plan_name", sa.String(180), nullable=False),
        sa.Column("planning_horizon_start", sa.Date(), nullable=False),
        sa.Column("planning_horizon_end", sa.Date(), nullable=False),
        sa.Column("period_granularity", sa.String(16), nullable=False, server_default="MONTH"),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("plan_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_reference", sa.String(300), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("capacity_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(160)),
        sa.Column("publish_idempotency_key", sa.String(160)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime()),
        sa.UniqueConstraint(
            "tenant_id", "portfolio_workspace_id", "logical_code", "plan_revision",
            name="uq_portfolio_resource_capacity_revision",
        ),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_resource_capacity_create_key"),
        sa.UniqueConstraint("tenant_id", "publish_idempotency_key", name="uq_resource_capacity_publish_key"),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','SUPERSEDED')", name="ck_resource_capacity_status"),
        sa.CheckConstraint(
            "period_granularity IN ('YEAR','QUARTER','MONTH')", name="ck_resource_capacity_granularity"
        ),
        sa.CheckConstraint("planning_horizon_end >= planning_horizon_start", name="ck_resource_capacity_horizon"),
    )
    for name, columns in (
        ("ix_portfolio_resource_capacity_plans_tenant_id", ["tenant_id"]),
        ("ix_portfolio_resource_capacity_plans_portfolio_workspace_id", ["portfolio_workspace_id"]),
        ("ix_portfolio_resource_capacity_plans_status", ["status"]),
        ("ix_resource_capacity_tenant_portfolio", ["tenant_id", "portfolio_workspace_id"]),
    ):
        op.create_index(name, "portfolio_resource_capacity_plans", columns)

    op.create_table(
        "portfolio_resource_capacity_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "capacity_plan_id", sa.Integer(), sa.ForeignKey("portfolio_resource_capacity_plans.id"), nullable=False
        ),
        sa.Column("resource_role_key", sa.String(100), nullable=False),
        sa.Column("resource_role_name", sa.String(180), nullable=False),
        sa.Column("role_category", sa.String(40), nullable=False, server_default="OTHER"),
        sa.Column("period_key", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("capacity_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False, server_default="FTE"),
        sa.Column("source_reference", sa.String(300), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "tenant_id", "capacity_plan_id", "resource_role_key", "period_key",
            name="uq_resource_capacity_role_period",
        ),
        sa.CheckConstraint("capacity_value >= 0", name="ck_resource_capacity_non_negative"),
        sa.CheckConstraint("unit IN ('FTE','HOURS','CREW_EQUIVALENT')", name="ck_resource_capacity_unit"),
        sa.CheckConstraint("period_end >= period_start", name="ck_resource_capacity_period_range"),
    )
    for name, columns in (
        ("ix_portfolio_resource_capacity_periods_tenant_id", ["tenant_id"]),
        ("ix_portfolio_resource_capacity_periods_capacity_plan_id", ["capacity_plan_id"]),
        ("ix_portfolio_resource_capacity_periods_resource_role_key", ["resource_role_key"]),
        ("ix_resource_capacity_period_lookup", ["capacity_plan_id", "resource_role_key", "period_start"]),
    ):
        op.create_index(name, "portfolio_resource_capacity_periods", columns)

    op.create_table(
        "project_resource_demand_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("logical_code", sa.String(100), nullable=False, server_default="RESOURCE-DEMAND"),
        sa.Column("profile_name", sa.String(180), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("profile_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("source_reference", sa.String(300), nullable=False, server_default=""),
        sa.Column("source_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("planning_start", sa.Date(), nullable=False),
        sa.Column("planning_finish", sa.Date(), nullable=False),
        sa.Column("generation_method", sa.String(40), nullable=False, server_default="EXPLICIT_PERIOD_PROFILE"),
        sa.Column("approximation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("demand_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(160)),
        sa.Column("publish_idempotency_key", sa.String(160)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime()),
        sa.UniqueConstraint(
            "tenant_id", "project_workspace_id", "logical_code", "profile_revision",
            name="uq_project_resource_demand_revision",
        ),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_resource_demand_create_key"),
        sa.UniqueConstraint("tenant_id", "publish_idempotency_key", name="uq_resource_demand_publish_key"),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','SUPERSEDED')", name="ck_resource_demand_status"),
        sa.CheckConstraint(
            "source_type IN ('PROJECT_RESOURCE_DEMAND_PROFILE','PROJECT_DEFINITION_RESOURCE_ESTIMATE',"
            "'TEMPLATE_RESOURCE_PROFILE','MANUAL_PORTFOLIO_PLANNING_PROFILE')",
            name="ck_resource_demand_source_type",
        ),
        sa.CheckConstraint(
            "generation_method IN ('EXPLICIT_PERIOD_PROFILE','LINEAR_BY_PROJECT_DATES','TEMPLATE_BASED')",
            name="ck_resource_demand_generation",
        ),
        sa.CheckConstraint("planning_finish >= planning_start", name="ck_resource_demand_horizon"),
    )
    for name, columns in (
        ("ix_project_resource_demand_profiles_tenant_id", ["tenant_id"]),
        ("ix_project_resource_demand_profiles_project_workspace_id", ["project_workspace_id"]),
        ("ix_project_resource_demand_profiles_status", ["status"]),
        ("ix_resource_demand_tenant_project", ["tenant_id", "project_workspace_id"]),
    ):
        op.create_index(name, "project_resource_demand_profiles", columns)

    op.create_table(
        "project_resource_demand_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "demand_profile_id", sa.Integer(), sa.ForeignKey("project_resource_demand_profiles.id"), nullable=False
        ),
        sa.Column("resource_role_key", sa.String(100), nullable=False),
        sa.Column("resource_role_name", sa.String(180), nullable=False),
        sa.Column("role_category", sa.String(40), nullable=False, server_default="OTHER"),
        sa.Column("period_key", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("demand_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False, server_default="FTE"),
        sa.Column("source_reference", sa.String(300), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "tenant_id", "demand_profile_id", "resource_role_key", "period_key",
            name="uq_resource_demand_role_period",
        ),
        sa.CheckConstraint("demand_value >= 0", name="ck_resource_demand_non_negative"),
        sa.CheckConstraint("unit IN ('FTE','HOURS','CREW_EQUIVALENT')", name="ck_resource_demand_unit"),
        sa.CheckConstraint("period_end >= period_start", name="ck_resource_demand_period_range"),
    )
    for name, columns in (
        ("ix_project_resource_demand_periods_tenant_id", ["tenant_id"]),
        ("ix_project_resource_demand_periods_demand_profile_id", ["demand_profile_id"]),
        ("ix_project_resource_demand_periods_resource_role_key", ["resource_role_key"]),
        ("ix_resource_demand_period_lookup", ["demand_profile_id", "resource_role_key", "period_start"]),
    ):
        op.create_index(name, "project_resource_demand_periods", columns)

    op.create_table(
        "portfolio_resource_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("portfolio_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("logical_code", sa.String(100), nullable=False),
        sa.Column("scenario_name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column(
            "capacity_plan_id", sa.Integer(), sa.ForeignKey("portfolio_resource_capacity_plans.id"), nullable=False
        ),
        sa.Column("capacity_plan_hash", sa.String(64), nullable=False),
        sa.Column("source_analysis_hash", sa.String(64), nullable=False),
        sa.Column("source_prioritization_hash", sa.String(64), nullable=False),
        sa.Column("membership_set_hash", sa.String(64), nullable=False),
        sa.Column("evaluation_set_hash", sa.String(64), nullable=False),
        sa.Column("source_configuration_hash", sa.String(64), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("scenario_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("creation_mode", sa.String(40), nullable=False, server_default="EMPTY"),
        sa.Column("overload_policy", sa.String(32), nullable=False, server_default="ALLOW_WITH_WARNING"),
        sa.Column("scenario_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(160)),
        sa.Column("clone_idempotency_key", sa.String(160)),
        sa.Column("freeze_idempotency_key", sa.String(160)),
        sa.Column("void_idempotency_key", sa.String(160)),
        sa.Column("refresh_idempotency_key", sa.String(160)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("frozen_at", sa.DateTime()),
        sa.Column("voided_at", sa.DateTime()),
        sa.UniqueConstraint(
            "tenant_id", "portfolio_workspace_id", "logical_code", "scenario_revision",
            name="uq_portfolio_resource_scenario_revision",
        ),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_resource_scenario_create_key"),
        sa.UniqueConstraint("tenant_id", "clone_idempotency_key", name="uq_resource_scenario_clone_key"),
        sa.UniqueConstraint("tenant_id", "freeze_idempotency_key", name="uq_resource_scenario_freeze_key"),
        sa.UniqueConstraint("tenant_id", "void_idempotency_key", name="uq_resource_scenario_void_key"),
        sa.UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_resource_scenario_refresh_key"),
        sa.CheckConstraint(
            "status IN ('DRAFT','IN_REVIEW','FROZEN','SUPERSEDED','VOIDED')", name="ck_resource_scenario_status"
        ),
        sa.CheckConstraint(
            "creation_mode IN ('EMPTY','FROM_CURRENT_PRIORITY','COPY_EXISTING_SCENARIO')",
            name="ck_resource_scenario_creation_mode",
        ),
        sa.CheckConstraint(
            "overload_policy IN ('ALLOW_WITH_WARNING','BLOCK_READY_STATE')", name="ck_resource_overload_policy"
        ),
    )
    for name, columns in (
        ("ix_portfolio_resource_scenarios_tenant_id", ["tenant_id"]),
        ("ix_portfolio_resource_scenarios_portfolio_workspace_id", ["portfolio_workspace_id"]),
        ("ix_portfolio_resource_scenarios_status", ["status"]),
        ("ix_portfolio_resource_scenarios_capacity_plan_id", ["capacity_plan_id"]),
        ("ix_resource_scenario_tenant_portfolio", ["tenant_id", "portfolio_workspace_id"]),
        ("ix_resource_scenario_tenant_status", ["tenant_id", "status"]),
    ):
        op.create_index(name, "portfolio_resource_scenarios", columns)

    op.create_table(
        "portfolio_resource_scenario_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("portfolio_resource_scenarios.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column(
            "portfolio_membership_id", sa.Integer(), sa.ForeignKey("portfolio_project_memberships.id"), nullable=False
        ),
        sa.Column("project_number", sa.String(120), nullable=False),
        sa.Column("project_name", sa.String(180), nullable=False),
        sa.Column("portfolio_evaluation_score", sa.Numeric(9, 4), nullable=False),
        sa.Column("portfolio_rank", sa.Integer(), nullable=False),
        sa.Column("strategic_alignment_score", sa.Numeric(9, 4), nullable=False),
        sa.Column("risk_score", sa.Numeric(9, 4), nullable=False),
        sa.Column("risk_bucket", sa.String(40), nullable=False),
        sa.Column("gate07f_analysis_hash", sa.String(64), nullable=False),
        sa.Column("resource_demand_profile_id", sa.Integer(), sa.ForeignKey("project_resource_demand_profiles.id")),
        sa.Column("resource_demand_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("source_project_start", sa.Date()),
        sa.Column("source_project_finish", sa.Date()),
        sa.Column("scenario_start", sa.Date()),
        sa.Column("scenario_finish", sa.Date()),
        sa.Column("schedule_shift_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timing_method", sa.String(40), nullable=False, server_default="NO_SHIFT"),
        sa.Column("selection_state", sa.String(20), nullable=False, server_default="UNSELECTED"),
        sa.Column("forced_reason", sa.Text()),
        sa.Column("forced_actor_id", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("forced_at", sa.DateTime()),
        sa.Column("forced_authority_reference", sa.String(300)),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("last_selection_idempotency_key", sa.String(160)),
        sa.Column("last_timing_idempotency_key", sa.String(160)),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "scenario_id", "project_workspace_id", name="uq_resource_scenario_project"),
        sa.CheckConstraint(
            "selection_state IN ('SELECTED','UNSELECTED','FORCED_IN','FORCED_OUT')",
            name="ck_resource_scenario_project_selection",
        ),
        sa.CheckConstraint(
            "selection_state NOT IN ('FORCED_IN','FORCED_OUT') OR forced_reason IS NOT NULL",
            name="ck_resource_scenario_project_forced_reason",
        ),
        sa.CheckConstraint(
            "timing_method IN ('NO_SHIFT','SHIFT_START_KEEP_DURATION','CUSTOM_SCENARIO_DATES')",
            name="ck_resource_scenario_project_timing",
        ),
        sa.CheckConstraint(
            "scenario_start IS NULL OR scenario_finish IS NULL OR scenario_finish >= scenario_start",
            name="ck_resource_scenario_project_dates",
        ),
    )
    for name, columns in (
        ("ix_portfolio_resource_scenario_projects_tenant_id", ["tenant_id"]),
        ("ix_portfolio_resource_scenario_projects_scenario_id", ["scenario_id"]),
        ("ix_portfolio_resource_scenario_projects_project_workspace_id", ["project_workspace_id"]),
        ("ix_portfolio_resource_scenario_projects_portfolio_membership_id", ["portfolio_membership_id"]),
        ("ix_portfolio_resource_scenario_projects_selection_state", ["selection_state"]),
        ("ix_portfolio_resource_scenario_projects_forced_actor_id", ["forced_actor_id"]),
        ("ix_portfolio_resource_scenario_projects_updated_by", ["updated_by"]),
        ("ix_resource_scenario_project_state", ["scenario_id", "selection_state"]),
    ):
        op.create_index(name, "portfolio_resource_scenario_projects", columns)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table in (
        "portfolio_resource_scenario_projects",
        "portfolio_resource_scenarios",
        "project_resource_demand_periods",
        "project_resource_demand_profiles",
        "portfolio_resource_capacity_periods",
        "portfolio_resource_capacity_plans",
    ):
        if table in tables:
            op.drop_table(table)
