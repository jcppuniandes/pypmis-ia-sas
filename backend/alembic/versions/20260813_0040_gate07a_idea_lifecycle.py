"""add governed Idea lifecycle and immutable evaluation snapshots

Revision ID: 20260813_0040
Revises: 20260813_0039
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0040"
down_revision: str | None = "20260813_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "ideas" not in tables:
        op.create_table(
            "ideas",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("idea_number", sa.String(40), nullable=False),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("idea_type", sa.String(80), nullable=False),
            sa.Column("category", sa.String(120), nullable=False),
            sa.Column("expected_benefit", sa.Text(), nullable=False),
            sa.Column("estimated_value", sa.Numeric(18, 2), nullable=True),
            sa.Column("currency_code", sa.String(8), nullable=False),
            sa.Column("owning_workspace_id", sa.Integer(), nullable=False),
            sa.Column("target_portfolio_workspace_id", sa.Integer(), nullable=True),
            sa.Column("strategic_objective_codes", sa.JSON(), nullable=False),
            sa.Column("requestor_user_id", sa.Integer(), nullable=False),
            sa.Column("owner_user_id", sa.Integer(), nullable=True),
            sa.Column("state", sa.String(40), nullable=False),
            sa.Column("screening_json", sa.JSON(), nullable=False),
            sa.Column("routing_json", sa.JSON(), nullable=False),
            sa.Column("configuration_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("attachment_refs_json", sa.JSON(), nullable=False),
            sa.Column("accepted_evaluation_id", sa.Integer(), nullable=True),
            sa.Column("decision_reason", sa.Text(), nullable=True),
            sa.Column("decision_by_user_id", sa.Integer(), nullable=True),
            sa.Column("readiness_json", sa.JSON(), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("last_modified_by_user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
            sa.Column("screened_at", sa.DateTime(), nullable=True),
            sa.Column("evaluated_at", sa.DateTime(), nullable=True),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["owning_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["target_portfolio_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["requestor_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["owner_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["decision_by_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["last_modified_by_user_id"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "idea_number", name="uq_idea_tenant_number"),
        )
        for column in (
            "tenant_id",
            "idea_number",
            "idea_type",
            "category",
            "owning_workspace_id",
            "target_portfolio_workspace_id",
            "requestor_user_id",
            "owner_user_id",
            "state",
            "accepted_evaluation_id",
            "decision_by_user_id",
        ):
            op.create_index(op.f(f"ix_ideas_{column}"), "ideas", [column])
    if "idea_evaluations" not in tables:
        op.create_table(
            "idea_evaluations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("idea_id", sa.Integer(), nullable=False),
            sa.Column("evaluation_version", sa.Integer(), nullable=False),
            sa.Column("matrix_configuration_id", sa.Integer(), nullable=False),
            sa.Column("matrix_revision", sa.Integer(), nullable=False),
            sa.Column("matrix_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("ratings_json", sa.JSON(), nullable=False),
            sa.Column("total_score", sa.Numeric(9, 4), nullable=False),
            sa.Column("result", sa.String(80), nullable=False),
            sa.Column("comments", sa.Text(), nullable=False),
            sa.Column("evaluator_user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"]),
            sa.ForeignKeyConstraint(["matrix_configuration_id"], ["admin_configurations.id"]),
            sa.ForeignKeyConstraint(["evaluator_user_id"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "idea_id", "evaluation_version", name="uq_idea_evaluation_version"),
        )
        for column in ("tenant_id", "idea_id", "matrix_configuration_id", "evaluator_user_id"):
            op.create_index(op.f(f"ix_idea_evaluations_{column}"), "idea_evaluations", [column])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "idea_evaluations" in tables:
        op.drop_table("idea_evaluations")
    if "ideas" in tables:
        op.drop_table("ideas")
