"""add Gate 07E Portfolio evaluation snapshots

Revision ID: 20260820_0045
Revises: 20260820_0044
Create Date: 2026-08-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0045"
down_revision: str | None = "20260820_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "portfolio_project_evaluations" in inspector.get_table_names():
        return
    op.create_table(
        "portfolio_project_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("portfolio_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column(
            "portfolio_membership_id",
            sa.Integer(),
            sa.ForeignKey("portfolio_project_memberships.id"),
            nullable=False,
        ),
        sa.Column("evaluation_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("matrix_configuration_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False),
        sa.Column("matrix_revision", sa.Integer(), nullable=False),
        sa.Column("matrix_hash", sa.String(64), nullable=False),
        sa.Column("matrix_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("source_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("source_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("planning_entry_hash", sa.String(64), nullable=False),
        sa.Column("ratings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("score_components_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("normalized_score", sa.Numeric(9, 4), nullable=False, server_default="0"),
        sa.Column("strategic_alignment_score", sa.Numeric(9, 4), nullable=False, server_default="0"),
        sa.Column("risk_score", sa.Numeric(9, 4), nullable=False, server_default="0"),
        sa.Column("comments", sa.Text(), nullable=False, server_default=""),
        sa.Column("evaluator_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("start_idempotency_key", sa.String(160), nullable=True),
        sa.Column("complete_idempotency_key", sa.String(160), nullable=True),
        sa.Column("reevaluation_idempotency_key", sa.String(160), nullable=True),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "portfolio_workspace_id",
            "project_workspace_id",
            "evaluation_version",
            name="uq_portfolio_project_evaluation_version",
        ),
        sa.UniqueConstraint("tenant_id", "start_idempotency_key", name="uq_portfolio_evaluation_start_key"),
        sa.UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_portfolio_evaluation_complete_key"),
        sa.UniqueConstraint("tenant_id", "reevaluation_idempotency_key", name="uq_portfolio_evaluation_reeval_key"),
    )
    for name, columns in (
        ("ix_portfolio_project_evaluations_tenant_id", ["tenant_id"]),
        ("ix_portfolio_project_evaluations_portfolio_workspace_id", ["portfolio_workspace_id"]),
        ("ix_portfolio_project_evaluations_project_workspace_id", ["project_workspace_id"]),
        ("ix_portfolio_project_evaluations_portfolio_membership_id", ["portfolio_membership_id"]),
        ("ix_portfolio_project_evaluations_status", ["status"]),
        ("ix_portfolio_project_evaluations_matrix_configuration_id", ["matrix_configuration_id"]),
        ("ix_portfolio_project_evaluations_evaluator_user_id", ["evaluator_user_id"]),
    ):
        op.create_index(name, "portfolio_project_evaluations", columns)


def downgrade() -> None:
    connection = op.get_bind()
    if "portfolio_project_evaluations" in sa.inspect(connection).get_table_names():
        op.drop_table("portfolio_project_evaluations")
