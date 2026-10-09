"""add Gate 07G-A Waterline dependencies and budget breakdown

Revision ID: 20260830_0052
Revises: 20260827_0051
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0052"
down_revision: str | None = "20260827_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "project_dependencies" not in tables:
        op.create_table(
            "project_dependencies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column(
                "predecessor_project_workspace_id",
                sa.Integer(),
                sa.ForeignKey("enterprise_workspaces.id"),
                nullable=False,
            ),
            sa.Column(
                "successor_project_workspace_id",
                sa.Integer(),
                sa.ForeignKey("enterprise_workspaces.id"),
                nullable=False,
            ),
            sa.Column("dependency_type", sa.String(40), nullable=False, server_default="PREREQUISITE"),
            sa.Column("dependency_strength", sa.String(20), nullable=False, server_default="MANDATORY"),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("effective_from", sa.Date()),
            sa.Column("effective_to", sa.Date()),
            sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
            sa.Column("source_reference", sa.String(300)),
            sa.Column("evidence_refs_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("create_idempotency_key", sa.String(160)),
            sa.Column("deactivate_idempotency_key", sa.String(160)),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_project_dependency_create_key"),
            sa.UniqueConstraint(
                "tenant_id", "deactivate_idempotency_key", name="uq_project_dependency_deactivate_key"
            ),
            sa.CheckConstraint(
                "predecessor_project_workspace_id <> successor_project_workspace_id",
                name="ck_project_dependency_not_self",
            ),
            sa.CheckConstraint(
                "dependency_type IN ('PREREQUISITE','ENABLING','SEQUENTIAL','SHARED_INFRASTRUCTURE','REGULATORY','FUNDING','OTHER')",
                name="ck_project_dependency_type",
            ),
            sa.CheckConstraint(
                "dependency_strength IN ('MANDATORY','OPTIONAL')",
                name="ck_project_dependency_strength",
            ),
            sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_project_dependency_status"),
            sa.CheckConstraint(
                "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
                name="ck_project_dependency_effective_range",
            ),
        )
        for name, columns in (
            ("ix_project_dependencies_tenant_id", ["tenant_id"]),
            (
                "ix_project_dependencies_predecessor_project_workspace_id",
                ["predecessor_project_workspace_id"],
            ),
            (
                "ix_project_dependencies_successor_project_workspace_id",
                ["successor_project_workspace_id"],
            ),
            ("ix_project_dependencies_dependency_type", ["dependency_type"]),
            ("ix_project_dependencies_dependency_strength", ["dependency_strength"]),
            ("ix_project_dependencies_status", ["status"]),
            ("ix_project_dependencies_created_by", ["created_by"]),
            ("ix_project_dependencies_updated_by", ["updated_by"]),
            (
                "ix_project_dependency_tenant_projects",
                ["tenant_id", "predecessor_project_workspace_id", "successor_project_workspace_id"],
            ),
        ):
            op.create_index(name, "project_dependencies", columns)
        op.create_index(
            "uq_project_dependency_active",
            "project_dependencies",
            [
                "tenant_id",
                "predecessor_project_workspace_id",
                "successor_project_workspace_id",
                "dependency_type",
            ],
            unique=True,
            postgresql_where=sa.text("status = 'ACTIVE'"),
        )

    target_columns = {item["name"] for item in inspector.get_columns("portfolio_budget_targets")}
    with op.batch_alter_table("portfolio_budget_targets") as batch:
        if "capex_budget_target" not in target_columns:
            batch.add_column(sa.Column("capex_budget_target", sa.Numeric(20, 2)))
        if "expense_budget_target" not in target_columns:
            batch.add_column(sa.Column("expense_budget_target", sa.Numeric(20, 2)))
    target_checks = {item["name"] for item in sa.inspect(bind).get_check_constraints("portfolio_budget_targets")}
    with op.batch_alter_table("portfolio_budget_targets") as batch:
        if "ck_portfolio_budget_target_capex_non_negative" not in target_checks:
            batch.create_check_constraint(
                "ck_portfolio_budget_target_capex_non_negative",
                "capex_budget_target IS NULL OR capex_budget_target >= 0",
            )
        if "ck_portfolio_budget_target_expense_non_negative" not in target_checks:
            batch.create_check_constraint(
                "ck_portfolio_budget_target_expense_non_negative",
                "expense_budget_target IS NULL OR expense_budget_target >= 0",
            )
        if "ck_portfolio_budget_target_breakdown_total" not in target_checks:
            batch.create_check_constraint(
                "ck_portfolio_budget_target_breakdown_total",
                "COALESCE(capex_budget_target, 0) + COALESCE(expense_budget_target, 0) <= total_budget_target",
            )

    period_columns = {item["name"] for item in inspector.get_columns("portfolio_budget_target_periods")}
    with op.batch_alter_table("portfolio_budget_target_periods") as batch:
        if "capex_amount" not in period_columns:
            batch.add_column(sa.Column("capex_amount", sa.Numeric(20, 2)))
        if "expense_amount" not in period_columns:
            batch.add_column(sa.Column("expense_amount", sa.Numeric(20, 2)))
    period_checks = {
        item["name"] for item in sa.inspect(bind).get_check_constraints("portfolio_budget_target_periods")
    }
    with op.batch_alter_table("portfolio_budget_target_periods") as batch:
        if "ck_portfolio_budget_target_period_capex_non_negative" not in period_checks:
            batch.create_check_constraint(
                "ck_portfolio_budget_target_period_capex_non_negative",
                "capex_amount IS NULL OR capex_amount >= 0",
            )
        if "ck_portfolio_budget_target_period_expense_non_negative" not in period_checks:
            batch.create_check_constraint(
                "ck_portfolio_budget_target_period_expense_non_negative",
                "expense_amount IS NULL OR expense_amount >= 0",
            )
        if "ck_portfolio_budget_target_period_breakdown_total" not in period_checks:
            batch.create_check_constraint(
                "ck_portfolio_budget_target_period_breakdown_total",
                "COALESCE(capex_amount, 0) + COALESCE(expense_amount, 0) <= amount",
            )

    row_columns = {item["name"] for item in inspector.get_columns("portfolio_budget_scenario_projects")}
    with op.batch_alter_table("portfolio_budget_scenario_projects") as batch:
        if "capex_amount" not in row_columns:
            batch.add_column(sa.Column("capex_amount", sa.Numeric(20, 2)))
        if "expense_amount" not in row_columns:
            batch.add_column(sa.Column("expense_amount", sa.Numeric(20, 2)))
        if "unclassified_amount" not in row_columns:
            batch.add_column(sa.Column("unclassified_amount", sa.Numeric(20, 2)))
        if "budget_breakdown_source" not in row_columns:
            batch.add_column(sa.Column("budget_breakdown_source", sa.String(80)))
    op.execute(
        sa.text(
            "UPDATE portfolio_budget_scenario_projects "
            "SET unclassified_amount = cost_value, budget_breakdown_source = 'LEGACY_UNCLASSIFIED' "
            "WHERE unclassified_amount IS NULL OR budget_breakdown_source IS NULL"
        )
    )
    with op.batch_alter_table("portfolio_budget_scenario_projects") as batch:
        batch.alter_column("unclassified_amount", existing_type=sa.Numeric(20, 2), nullable=False)
        batch.alter_column("budget_breakdown_source", existing_type=sa.String(80), nullable=False)
        batch.create_check_constraint(
            "ck_budget_scenario_project_capex_non_negative",
            "capex_amount IS NULL OR capex_amount >= 0",
        )
        batch.create_check_constraint(
            "ck_budget_scenario_project_expense_non_negative",
            "expense_amount IS NULL OR expense_amount >= 0",
        )
        batch.create_check_constraint(
            "ck_budget_scenario_project_unclassified_non_negative",
            "unclassified_amount >= 0",
        )
        batch.create_check_constraint(
            "ck_budget_scenario_project_breakdown_total",
            "COALESCE(capex_amount, 0) + COALESCE(expense_amount, 0) + unclassified_amount = cost_value",
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "portfolio_budget_scenario_projects" in inspector.get_table_names():
        checks = {item["name"] for item in inspector.get_check_constraints("portfolio_budget_scenario_projects")}
        with op.batch_alter_table("portfolio_budget_scenario_projects") as batch:
            for name in (
                "ck_budget_scenario_project_breakdown_total",
                "ck_budget_scenario_project_unclassified_non_negative",
                "ck_budget_scenario_project_expense_non_negative",
                "ck_budget_scenario_project_capex_non_negative",
            ):
                if name in checks:
                    batch.drop_constraint(name, type_="check")
            for column in ("budget_breakdown_source", "unclassified_amount", "expense_amount", "capex_amount"):
                if column in {item["name"] for item in inspector.get_columns("portfolio_budget_scenario_projects")}:
                    batch.drop_column(column)
    if "portfolio_budget_target_periods" in inspector.get_table_names():
        checks = {item["name"] for item in inspector.get_check_constraints("portfolio_budget_target_periods")}
        with op.batch_alter_table("portfolio_budget_target_periods") as batch:
            for name in (
                "ck_portfolio_budget_target_period_breakdown_total",
                "ck_portfolio_budget_target_period_expense_non_negative",
                "ck_portfolio_budget_target_period_capex_non_negative",
            ):
                if name in checks:
                    batch.drop_constraint(name, type_="check")
            for column in ("expense_amount", "capex_amount"):
                if column in {item["name"] for item in inspector.get_columns("portfolio_budget_target_periods")}:
                    batch.drop_column(column)
    if "portfolio_budget_targets" in inspector.get_table_names():
        checks = {item["name"] for item in inspector.get_check_constraints("portfolio_budget_targets")}
        with op.batch_alter_table("portfolio_budget_targets") as batch:
            for name in (
                "ck_portfolio_budget_target_breakdown_total",
                "ck_portfolio_budget_target_expense_non_negative",
                "ck_portfolio_budget_target_capex_non_negative",
            ):
                if name in checks:
                    batch.drop_constraint(name, type_="check")
            for column in ("expense_budget_target", "capex_budget_target"):
                if column in {item["name"] for item in inspector.get_columns("portfolio_budget_targets")}:
                    batch.drop_column(column)
    if "project_dependencies" in inspector.get_table_names():
        op.drop_table("project_dependencies")
