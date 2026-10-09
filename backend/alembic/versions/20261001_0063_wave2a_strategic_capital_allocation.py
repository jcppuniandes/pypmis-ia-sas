"""Wave 2A strategic capital buckets and allocation framework.

Revision ID: 20261001_0063
Revises: 20260929_0062
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261001_0063"
down_revision: str | None = "20260929_0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategic_capital_allocation_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("allocation_plan_number", sa.String(length=40), nullable=False),
        sa.Column("logical_code", sa.String(length=80), nullable=False),
        sa.Column("plan_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(length=220), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("planning_cycle_id", sa.Integer(), nullable=False),
        sa.Column("scope_workspace_id", sa.Integer(), nullable=False),
        sa.Column("portfolio_workspace_id", sa.Integer(), nullable=True),
        sa.Column("base_currency", sa.String(length=8), nullable=True),
        sa.Column("allocation_basis", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="DRAFT"),
        sa.Column("assumptions_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("constraints_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("configuration_id", sa.Integer(), nullable=False),
        sa.Column("configuration_revision", sa.Integer(), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("configuration_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_context_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("plan_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("endorsed_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("endorsed_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("create_idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("submit_idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("review_idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("return_idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("endorse_idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("revision_idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("last_modified_by_user_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=True),
        sa.Column("endorser_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("review_started_at", sa.DateTime(), nullable=True),
        sa.Column("returned_at", sa.DateTime(), nullable=True),
        sa.Column("endorsed_at", sa.DateTime(), nullable=True),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "allocation_basis IN ('PERCENTAGE','INDICATIVE_AMOUNT','PERCENTAGE_AND_AMOUNT')",
            name="ck_capital_allocation_plan_basis",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED','ENDORSED','SUPERSEDED','CANCELLED')",
            name="ck_capital_allocation_plan_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["planning_cycle_id"], ["capital_planning_cycles.id"]),
        sa.ForeignKeyConstraint(["scope_workspace_id"], ["enterprise_workspaces.id"]),
        sa.ForeignKeyConstraint(["portfolio_workspace_id"], ["enterprise_workspaces.id"]),
        sa.ForeignKeyConstraint(["configuration_id"], ["admin_configurations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["last_modified_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["endorser_user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "allocation_plan_number", name="uq_capital_allocation_plan_number"),
        sa.UniqueConstraint("tenant_id", "logical_code", "plan_revision", name="uq_capital_allocation_plan_revision"),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_capital_allocation_plan_create_key"),
        sa.UniqueConstraint("tenant_id", "submit_idempotency_key", name="uq_capital_allocation_plan_submit_key"),
        sa.UniqueConstraint("tenant_id", "review_idempotency_key", name="uq_capital_allocation_plan_review_key"),
        sa.UniqueConstraint("tenant_id", "return_idempotency_key", name="uq_capital_allocation_plan_return_key"),
        sa.UniqueConstraint("tenant_id", "endorse_idempotency_key", name="uq_capital_allocation_plan_endorse_key"),
        sa.UniqueConstraint("tenant_id", "revision_idempotency_key", name="uq_capital_allocation_plan_revision_key"),
    )
    for column in (
        "tenant_id",
        "allocation_plan_number",
        "logical_code",
        "planning_cycle_id",
        "scope_workspace_id",
        "portfolio_workspace_id",
        "base_currency",
        "allocation_basis",
        "status",
        "configuration_id",
        "configuration_hash",
        "plan_hash",
        "endorsed_snapshot_hash",
        "created_by_user_id",
        "last_modified_by_user_id",
        "reviewer_user_id",
        "endorser_user_id",
        "updated_at",
    ):
        op.create_index(
            f"ix_strategic_capital_allocation_plans_{column}",
            "strategic_capital_allocation_plans",
            [column],
        )
    op.create_index(
        "ix_capital_allocation_plan_queue",
        "strategic_capital_allocation_plans",
        ["tenant_id", "status", "updated_at", "id"],
    )
    op.create_index(
        "ix_capital_allocation_plan_cycle_scope",
        "strategic_capital_allocation_plans",
        ["tenant_id", "planning_cycle_id", "scope_workspace_id"],
    )
    active_predicate = sa.text("status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED','ENDORSED')")
    op.create_index(
        "uq_capital_allocation_plan_current_no_portfolio",
        "strategic_capital_allocation_plans",
        ["tenant_id", "planning_cycle_id", "scope_workspace_id"],
        unique=True,
        postgresql_where=sa.text(f"portfolio_workspace_id IS NULL AND {active_predicate.text}"),
        sqlite_where=sa.text(f"portfolio_workspace_id IS NULL AND {active_predicate.text}"),
    )
    op.create_index(
        "uq_capital_allocation_plan_current_portfolio",
        "strategic_capital_allocation_plans",
        ["tenant_id", "planning_cycle_id", "scope_workspace_id", "portfolio_workspace_id"],
        unique=True,
        postgresql_where=sa.text(f"portfolio_workspace_id IS NOT NULL AND {active_predicate.text}"),
        sqlite_where=sa.text(f"portfolio_workspace_id IS NOT NULL AND {active_predicate.text}"),
    )

    op.create_table(
        "strategic_capital_allocation_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("allocation_plan_id", sa.Integer(), nullable=False),
        sa.Column("bucket_code", sa.String(length=120), nullable=False),
        sa.Column("target_percentage", sa.Numeric(9, 4), nullable=True),
        sa.Column("target_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("minimum_percentage", sa.Numeric(9, 4), nullable=True),
        sa.Column("maximum_percentage", sa.Numeric(9, 4), nullable=True),
        sa.Column("minimum_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("maximum_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("strategic_objective_codes_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("assumptions_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("constraints_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("line_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "target_percentage IS NULL OR (target_percentage >= 0 AND target_percentage <= 100)",
            name="ck_capital_allocation_line_target_pct",
        ),
        sa.CheckConstraint(
            "minimum_percentage IS NULL OR (minimum_percentage >= 0 AND minimum_percentage <= 100)",
            name="ck_capital_allocation_line_min_pct",
        ),
        sa.CheckConstraint(
            "maximum_percentage IS NULL OR (maximum_percentage >= 0 AND maximum_percentage <= 100)",
            name="ck_capital_allocation_line_max_pct",
        ),
        sa.CheckConstraint(
            "minimum_percentage IS NULL OR target_percentage IS NULL OR minimum_percentage <= target_percentage",
            name="ck_capital_allocation_line_min_target_pct",
        ),
        sa.CheckConstraint(
            "maximum_percentage IS NULL OR target_percentage IS NULL OR target_percentage <= maximum_percentage",
            name="ck_capital_allocation_line_target_max_pct",
        ),
        sa.CheckConstraint(
            "target_amount IS NULL OR target_amount >= 0", name="ck_capital_allocation_line_target_amount"
        ),
        sa.CheckConstraint(
            "minimum_amount IS NULL OR minimum_amount >= 0", name="ck_capital_allocation_line_min_amount"
        ),
        sa.CheckConstraint(
            "maximum_amount IS NULL OR maximum_amount >= 0", name="ck_capital_allocation_line_max_amount"
        ),
        sa.CheckConstraint(
            "minimum_amount IS NULL OR target_amount IS NULL OR minimum_amount <= target_amount",
            name="ck_capital_allocation_line_min_target_amount",
        ),
        sa.CheckConstraint(
            "maximum_amount IS NULL OR target_amount IS NULL OR target_amount <= maximum_amount",
            name="ck_capital_allocation_line_target_max_amount",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["allocation_plan_id"], ["strategic_capital_allocation_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "allocation_plan_id", "bucket_code", name="uq_capital_allocation_line_bucket"),
    )
    for column in ("tenant_id", "allocation_plan_id", "bucket_code", "currency", "line_hash"):
        op.create_index(
            f"ix_strategic_capital_allocation_lines_{column}", "strategic_capital_allocation_lines", [column]
        )
    op.create_index(
        "ix_capital_allocation_line_plan_bucket",
        "strategic_capital_allocation_lines",
        ["allocation_plan_id", "bucket_code"],
    )

    op.create_table(
        "strategic_bucket_classifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("allocation_plan_id", sa.Integer(), nullable=False),
        sa.Column("capital_demand_id", sa.Integer(), nullable=True),
        sa.Column("project_workspace_id", sa.Integer(), nullable=True),
        sa.Column("portfolio_membership_id", sa.Integer(), nullable=True),
        sa.Column("bucket_code", sa.String(length=120), nullable=False),
        sa.Column("classification_source", sa.String(length=32), nullable=False, server_default="MANUAL"),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("classification_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("classified_by_user_id", sa.Integer(), nullable=False),
        sa.Column("classified_at", sa.DateTime(), nullable=False),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "(CASE WHEN capital_demand_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN project_workspace_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN portfolio_membership_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_strategic_bucket_classification_target",
        ),
        sa.CheckConstraint(
            "classification_source IN ('MANUAL','THEME_DERIVED','RULE_DERIVED')",
            name="ck_strategic_bucket_classification_source",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["allocation_plan_id"], ["strategic_capital_allocation_plans.id"]),
        sa.ForeignKeyConstraint(["capital_demand_id"], ["strategic_capital_demands.id"]),
        sa.ForeignKeyConstraint(["project_workspace_id"], ["enterprise_workspaces.id"]),
        sa.ForeignKeyConstraint(["portfolio_membership_id"], ["portfolio_project_memberships.id"]),
        sa.ForeignKeyConstraint(["classified_by_user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_strategic_bucket_classification_key"),
    )
    for column in (
        "tenant_id",
        "allocation_plan_id",
        "capital_demand_id",
        "project_workspace_id",
        "portfolio_membership_id",
        "bucket_code",
        "classification_source",
        "classification_hash",
        "classified_by_user_id",
    ):
        op.create_index(f"ix_strategic_bucket_classifications_{column}", "strategic_bucket_classifications", [column])
    op.create_index(
        "uq_strategic_bucket_classification_demand",
        "strategic_bucket_classifications",
        ["tenant_id", "allocation_plan_id", "capital_demand_id"],
        unique=True,
        postgresql_where=sa.text("capital_demand_id IS NOT NULL"),
        sqlite_where=sa.text("capital_demand_id IS NOT NULL"),
    )
    op.create_index(
        "uq_strategic_bucket_classification_project",
        "strategic_bucket_classifications",
        ["tenant_id", "allocation_plan_id", "project_workspace_id"],
        unique=True,
        postgresql_where=sa.text("project_workspace_id IS NOT NULL"),
        sqlite_where=sa.text("project_workspace_id IS NOT NULL"),
    )
    op.create_index(
        "uq_strategic_bucket_classification_membership",
        "strategic_bucket_classifications",
        ["tenant_id", "allocation_plan_id", "portfolio_membership_id"],
        unique=True,
        postgresql_where=sa.text("portfolio_membership_id IS NOT NULL"),
        sqlite_where=sa.text("portfolio_membership_id IS NOT NULL"),
    )
    op.create_index(
        "ix_strategic_bucket_classification_plan_bucket",
        "strategic_bucket_classifications",
        ["allocation_plan_id", "bucket_code"],
    )

    op.create_table(
        "strategic_capital_allocation_commands",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("allocation_plan_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["allocation_plan_id"], ["strategic_capital_allocation_plans.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_capital_allocation_command_key"),
    )
    for column in ("tenant_id", "allocation_plan_id", "action", "request_hash", "actor_user_id", "occurred_at"):
        op.create_index(
            f"ix_strategic_capital_allocation_commands_{column}", "strategic_capital_allocation_commands", [column]
        )
    op.create_index(
        "ix_capital_allocation_command_plan_action",
        "strategic_capital_allocation_commands",
        ["allocation_plan_id", "action", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("strategic_capital_allocation_commands")
    op.drop_table("strategic_bucket_classifications")
    op.drop_table("strategic_capital_allocation_lines")
    op.drop_table("strategic_capital_allocation_plans")
