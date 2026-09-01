"""add Gate 07G Portfolio Budget Targets and Scenarios

Revision ID: 20260825_0046
Revises: 20260820_0045
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_0046"
down_revision: str | None = "20260820_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "portfolio_budget_targets" in inspector.get_table_names():
        return
    op.create_table(
        "portfolio_budget_targets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("portfolio_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("target_code", sa.String(80), nullable=False, server_default="BUDGET-TARGET"),
        sa.Column("target_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("planning_horizon_start", sa.Date(), nullable=False),
        sa.Column("planning_horizon_end", sa.Date(), nullable=False),
        sa.Column("period_granularity", sa.String(16), nullable=False, server_default="YEAR"),
        sa.Column("budget_currency", sa.String(8), nullable=False),
        sa.Column("total_budget_target", sa.Numeric(20, 2), nullable=False),
        sa.Column("source_reference", sa.String(300), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("target_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(160)),
        sa.Column("publish_idempotency_key", sa.String(160)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime()),
        sa.UniqueConstraint(
            "tenant_id",
            "portfolio_workspace_id",
            "target_code",
            "target_revision",
            name="uq_portfolio_budget_target_revision",
        ),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_portfolio_budget_target_create_key"),
        sa.UniqueConstraint("tenant_id", "publish_idempotency_key", name="uq_portfolio_budget_target_publish_key"),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','SUPERSEDED')", name="ck_portfolio_budget_target_status"),
        sa.CheckConstraint("total_budget_target >= 0", name="ck_portfolio_budget_target_non_negative"),
        sa.CheckConstraint(
            "period_granularity IN ('YEAR','QUARTER','MONTH')", name="ck_portfolio_budget_target_granularity"
        ),
    )
    op.create_index("ix_portfolio_budget_targets_tenant_id", "portfolio_budget_targets", ["tenant_id"])
    op.create_index(
        "ix_portfolio_budget_targets_portfolio_workspace_id", "portfolio_budget_targets", ["portfolio_workspace_id"]
    )
    op.create_index("ix_portfolio_budget_targets_status", "portfolio_budget_targets", ["status"])
    op.create_index(
        "ix_portfolio_budget_target_tenant_portfolio",
        "portfolio_budget_targets",
        ["tenant_id", "portfolio_workspace_id"],
    )

    op.create_table(
        "portfolio_budget_target_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("budget_target_id", sa.Integer(), sa.ForeignKey("portfolio_budget_targets.id"), nullable=False),
        sa.Column("period_key", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.UniqueConstraint("tenant_id", "budget_target_id", "period_key", name="uq_portfolio_budget_target_period"),
        sa.CheckConstraint("amount >= 0", name="ck_portfolio_budget_target_period_non_negative"),
    )
    op.create_index("ix_portfolio_budget_target_periods_tenant_id", "portfolio_budget_target_periods", ["tenant_id"])
    op.create_index(
        "ix_portfolio_budget_target_periods_budget_target_id", "portfolio_budget_target_periods", ["budget_target_id"]
    )

    op.create_table(
        "portfolio_budget_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("portfolio_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("logical_code", sa.String(100), nullable=False),
        sa.Column("scenario_name", sa.String(180), nullable=False),
        sa.Column("scenario_code", sa.String(80)),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("analytical_status", sa.String(20), nullable=False, server_default="UNDER_BUDGET"),
        sa.Column("budget_target_id", sa.Integer(), sa.ForeignKey("portfolio_budget_targets.id"), nullable=False),
        sa.Column("source_analysis_hash", sa.String(64), nullable=False),
        sa.Column("source_prioritization_hash", sa.String(64), nullable=False),
        sa.Column("membership_set_hash", sa.String(64), nullable=False),
        sa.Column("evaluation_set_hash", sa.String(64), nullable=False),
        sa.Column("source_configuration_hash", sa.String(64), nullable=False),
        sa.Column("budget_target_hash", sa.String(64), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("scenario_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("creation_mode", sa.String(32), nullable=False, server_default="EMPTY"),
        sa.Column("time_phasing_method", sa.String(32), nullable=False, server_default="UNPHASED"),
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
            "tenant_id",
            "portfolio_workspace_id",
            "logical_code",
            "scenario_revision",
            name="uq_portfolio_budget_scenario_revision",
        ),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_portfolio_budget_scenario_create_key"),
        sa.UniqueConstraint("tenant_id", "clone_idempotency_key", name="uq_portfolio_budget_scenario_clone_key"),
        sa.UniqueConstraint("tenant_id", "freeze_idempotency_key", name="uq_portfolio_budget_scenario_freeze_key"),
        sa.UniqueConstraint("tenant_id", "void_idempotency_key", name="uq_portfolio_budget_scenario_void_key"),
        sa.UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_portfolio_budget_scenario_refresh_key"),
        sa.CheckConstraint(
            "status IN ('DRAFT','IN_REVIEW','FROZEN','SUPERSEDED','VOIDED')", name="ck_portfolio_budget_scenario_status"
        ),
        sa.CheckConstraint(
            "analytical_status IN ('WITHIN_BUDGET','OVER_BUDGET','UNDER_BUDGET')",
            name="ck_portfolio_budget_scenario_analytical_status",
        ),
        sa.CheckConstraint(
            "creation_mode IN ('EMPTY','FROM_CURRENT_PRIORITY','COPY_EXISTING_SCENARIO')",
            name="ck_portfolio_budget_scenario_creation_mode",
        ),
        sa.CheckConstraint(
            "time_phasing_method IN ('UNPHASED','LINEAR_BY_PROJECT_DATES','CUSTOM_PERIOD_PROFILE')",
            name="ck_portfolio_budget_scenario_time_phasing",
        ),
    )
    for name, columns in (
        ("ix_portfolio_budget_scenarios_tenant_id", ["tenant_id"]),
        ("ix_portfolio_budget_scenarios_portfolio_workspace_id", ["portfolio_workspace_id"]),
        ("ix_portfolio_budget_scenarios_status", ["status"]),
        ("ix_portfolio_budget_scenarios_budget_target_id", ["budget_target_id"]),
        ("ix_portfolio_budget_scenario_tenant_portfolio", ["tenant_id", "portfolio_workspace_id"]),
        ("ix_portfolio_budget_scenario_tenant_status", ["tenant_id", "status"]),
    ):
        op.create_index(name, "portfolio_budget_scenarios", columns)

    op.create_table(
        "portfolio_budget_scenario_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("scenario_id", sa.Integer(), sa.ForeignKey("portfolio_budget_scenarios.id"), nullable=False),
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
        sa.Column("cost_source_type", sa.String(80), nullable=False),
        sa.Column("cost_source_reference", sa.String(160), nullable=False),
        sa.Column("cost_source_hash", sa.String(64), nullable=False),
        sa.Column("cost_value", sa.Numeric(20, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("cost_as_of_date", sa.Date(), nullable=False),
        sa.Column("target_start", sa.Date()),
        sa.Column("target_finish", sa.Date()),
        sa.Column("strategic_objectives_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("risk_summary_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("expected_benefits", sa.Text(), nullable=False, server_default=""),
        sa.Column("project_type", sa.String(120), nullable=False, server_default=""),
        sa.Column("planning_stage", sa.String(80), nullable=False, server_default=""),
        sa.Column("selection_state", sa.String(20), nullable=False, server_default="UNSELECTED"),
        sa.Column("forced_reason", sa.Text()),
        sa.Column("forced_actor_id", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("forced_at", sa.DateTime()),
        sa.Column("forced_authority_reference", sa.String(300)),
        sa.Column("period_profile_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("warnings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("last_selection_idempotency_key", sa.String(160)),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "scenario_id", "project_workspace_id", name="uq_budget_scenario_project"),
        sa.CheckConstraint(
            "selection_state IN ('SELECTED','UNSELECTED','FORCED_IN','FORCED_OUT')",
            name="ck_budget_scenario_project_selection",
        ),
        sa.CheckConstraint(
            "selection_state NOT IN ('FORCED_IN','FORCED_OUT') OR forced_reason IS NOT NULL",
            name="ck_budget_scenario_project_forced_reason",
        ),
        sa.CheckConstraint("cost_value >= 0", name="ck_budget_scenario_project_cost_non_negative"),
    )
    for name, columns in (
        ("ix_portfolio_budget_scenario_projects_tenant_id", ["tenant_id"]),
        ("ix_portfolio_budget_scenario_projects_scenario_id", ["scenario_id"]),
        ("ix_portfolio_budget_scenario_projects_project_workspace_id", ["project_workspace_id"]),
        ("ix_portfolio_budget_scenario_projects_portfolio_membership_id", ["portfolio_membership_id"]),
        ("ix_portfolio_budget_scenario_projects_selection_state", ["selection_state"]),
        ("ix_portfolio_budget_scenario_projects_forced_actor_id", ["forced_actor_id"]),
        ("ix_portfolio_budget_scenario_projects_updated_by", ["updated_by"]),
        ("ix_budget_scenario_project_state", ["scenario_id", "selection_state"]),
    ):
        op.create_index(name, "portfolio_budget_scenario_projects", columns)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table in (
        "portfolio_budget_scenario_projects",
        "portfolio_budget_scenarios",
        "portfolio_budget_target_periods",
        "portfolio_budget_targets",
    ):
        if table in tables:
            op.drop_table(table)
