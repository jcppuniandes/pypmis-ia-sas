"""add Gate 07I Portfolio Scenario Convergence and Recommendation

Revision ID: 20260826_0048
Revises: 20260825_0047
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_0048"
down_revision: str | None = "20260825_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "portfolio_scenario_convergences" in inspector.get_table_names():
        return
    op.create_table(
        "portfolio_scenario_convergences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "portfolio_workspace_id",
            sa.Integer(),
            sa.ForeignKey("enterprise_workspaces.id"),
            nullable=False,
        ),
        sa.Column("logical_code", sa.String(100), nullable=False, server_default="PORTFOLIO-CONVERGENCE"),
        sa.Column("convergence_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("required_budget_branch", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("required_resource_branch", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_analysis_hash", sa.String(64), nullable=False),
        sa.Column("source_membership_set_hash", sa.String(64), nullable=False),
        sa.Column("source_evaluation_set_hash", sa.String(64), nullable=False),
        sa.Column("budget_planning_hash", sa.String(64)),
        sa.Column("resource_planning_hash", sa.String(64)),
        sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("admin_configurations.id")),
        sa.Column("configuration_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("configuration_hash", sa.String(64), nullable=False),
        sa.Column("convergence_source_hash", sa.String(64), nullable=False),
        sa.Column("source_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("recommended_alternative_id", sa.Integer()),
        sa.Column("recommendation_reason", sa.Text()),
        sa.Column("conditions_json", sa.JSON(), nullable=False),
        sa.Column("risks_acknowledged_json", sa.JSON(), nullable=False),
        sa.Column("decision_support_summary", sa.Text()),
        sa.Column("recommendation_hash", sa.String(64)),
        sa.Column("recommended_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("recommended_at", sa.DateTime()),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("blockers_json", sa.JSON(), nullable=False),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(160)),
        sa.Column("refresh_idempotency_key", sa.String(160)),
        sa.Column("submit_idempotency_key", sa.String(160)),
        sa.Column("return_idempotency_key", sa.String(160)),
        sa.Column("recommend_idempotency_key", sa.String(160)),
        sa.Column("clone_idempotency_key", sa.String(160)),
        sa.Column("void_idempotency_key", sa.String(160)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("voided_at", sa.DateTime()),
        sa.UniqueConstraint(
            "tenant_id",
            "portfolio_workspace_id",
            "logical_code",
            "convergence_revision",
            name="uq_portfolio_convergence_revision",
        ),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_convergence_create_key"),
        sa.UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_convergence_refresh_key"),
        sa.UniqueConstraint("tenant_id", "submit_idempotency_key", name="uq_convergence_submit_key"),
        sa.UniqueConstraint("tenant_id", "return_idempotency_key", name="uq_convergence_return_key"),
        sa.UniqueConstraint("tenant_id", "recommend_idempotency_key", name="uq_convergence_recommend_key"),
        sa.UniqueConstraint("tenant_id", "clone_idempotency_key", name="uq_convergence_clone_key"),
        sa.UniqueConstraint("tenant_id", "void_idempotency_key", name="uq_convergence_void_key"),
        sa.CheckConstraint(
            "status IN ('DRAFT','IN_REVIEW','RECOMMENDED','SUPERSEDED','VOIDED')",
            name="ck_portfolio_convergence_status",
        ),
        sa.CheckConstraint(
            "required_budget_branch OR required_resource_branch",
            name="ck_portfolio_convergence_branch_required",
        ),
        sa.CheckConstraint(
            "status != 'RECOMMENDED' OR (recommended_alternative_id IS NOT NULL AND recommendation_hash IS NOT NULL)",
            name="ck_portfolio_convergence_recommended_evidence",
        ),
    )
    for name, columns in (
        ("ix_portfolio_scenario_convergences_tenant_id", ["tenant_id"]),
        ("ix_portfolio_scenario_convergences_portfolio_workspace_id", ["portfolio_workspace_id"]),
        ("ix_portfolio_scenario_convergences_status", ["status"]),
        ("ix_portfolio_scenario_convergences_configuration_id", ["configuration_id"]),
        ("ix_portfolio_scenario_convergences_convergence_source_hash", ["convergence_source_hash"]),
        ("ix_portfolio_scenario_convergences_recommended_alternative_id", ["recommended_alternative_id"]),
        ("ix_portfolio_scenario_convergences_recommendation_hash", ["recommendation_hash"]),
        ("ix_portfolio_scenario_convergences_recommended_by", ["recommended_by"]),
        ("ix_portfolio_scenario_convergences_created_by", ["created_by"]),
        ("ix_portfolio_scenario_convergences_updated_by", ["updated_by"]),
        ("ix_convergence_tenant_portfolio", ["tenant_id", "portfolio_workspace_id"]),
        ("ix_convergence_tenant_status", ["tenant_id", "status"]),
    ):
        op.create_index(name, "portfolio_scenario_convergences", columns)

    op.create_table(
        "portfolio_converged_alternatives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "convergence_id",
            sa.Integer(),
            sa.ForeignKey("portfolio_scenario_convergences.id"),
            nullable=False,
        ),
        sa.Column("alternative_name", sa.String(180), nullable=False),
        sa.Column("budget_scenario_id", sa.Integer(), sa.ForeignKey("portfolio_budget_scenarios.id")),
        sa.Column("budget_scenario_hash", sa.String(64)),
        sa.Column("resource_scenario_id", sa.Integer(), sa.ForeignKey("portfolio_resource_scenarios.id")),
        sa.Column("resource_scenario_hash", sa.String(64)),
        sa.Column("alignment_status", sa.String(24), nullable=False, server_default="ALIGNED"),
        sa.Column("budget_feasibility", sa.String(24), nullable=False, server_default="NOT_REQUIRED"),
        sa.Column("resource_feasibility", sa.String(24), nullable=False, server_default="NOT_REQUIRED"),
        sa.Column("feasibility_status", sa.String(24), nullable=False, server_default="BLOCKED"),
        sa.Column("selected_project_set_hash", sa.String(64), nullable=False),
        sa.Column("budget_summary_json", sa.JSON(), nullable=False),
        sa.Column("resource_summary_json", sa.JSON(), nullable=False),
        sa.Column("strategic_summary_json", sa.JSON(), nullable=False),
        sa.Column("risk_summary_json", sa.JSON(), nullable=False),
        sa.Column("project_matrix_json", sa.JSON(), nullable=False),
        sa.Column("forced_conflicts_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("blockers_json", sa.JSON(), nullable=False),
        sa.Column("alternative_hash", sa.String(64), nullable=False),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(160)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "convergence_id",
            "budget_scenario_id",
            "resource_scenario_id",
            name="uq_converged_alternative_pair",
        ),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_converged_alternative_create_key"),
        sa.CheckConstraint(
            "alignment_status IN ('ALIGNED','PARTIALLY_ALIGNED','MISALIGNED')",
            name="ck_converged_alternative_alignment",
        ),
        sa.CheckConstraint(
            "budget_feasibility IN ('BUDGET_FEASIBLE','CONDITIONAL','INFEASIBLE','NOT_REQUIRED')",
            name="ck_converged_alternative_budget_feasibility",
        ),
        sa.CheckConstraint(
            "resource_feasibility IN ('RESOURCE_FEASIBLE','CONDITIONAL','INFEASIBLE','NOT_REQUIRED')",
            name="ck_converged_alternative_resource_feasibility",
        ),
        sa.CheckConstraint(
            "feasibility_status IN ('FEASIBLE','CONDITIONAL','INFEASIBLE','BLOCKED','STALE')",
            name="ck_converged_alternative_feasibility",
        ),
    )
    for name, columns in (
        ("ix_portfolio_converged_alternatives_tenant_id", ["tenant_id"]),
        ("ix_portfolio_converged_alternatives_convergence_id", ["convergence_id"]),
        ("ix_portfolio_converged_alternatives_budget_scenario_id", ["budget_scenario_id"]),
        ("ix_portfolio_converged_alternatives_resource_scenario_id", ["resource_scenario_id"]),
        ("ix_portfolio_converged_alternatives_alignment_status", ["alignment_status"]),
        ("ix_portfolio_converged_alternatives_feasibility_status", ["feasibility_status"]),
        ("ix_portfolio_converged_alternatives_alternative_hash", ["alternative_hash"]),
        ("ix_portfolio_converged_alternatives_created_by", ["created_by"]),
        ("ix_portfolio_converged_alternatives_updated_by", ["updated_by"]),
        ("ix_converged_alternative_convergence_status", ["convergence_id", "feasibility_status"]),
    ):
        op.create_index(name, "portfolio_converged_alternatives", columns)
    op.create_foreign_key(
        "fk_convergence_recommended_alternative",
        "portfolio_scenario_convergences",
        "portfolio_converged_alternatives",
        ["recommended_alternative_id"],
        ["id"],
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "portfolio_scenario_convergences" not in inspector.get_table_names():
        return
    op.drop_constraint(
        "fk_convergence_recommended_alternative",
        "portfolio_scenario_convergences",
        type_="foreignkey",
    )
    op.drop_table("portfolio_converged_alternatives")
    op.drop_table("portfolio_scenario_convergences")
