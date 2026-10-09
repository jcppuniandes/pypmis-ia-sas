"""add Gate 07B Project Proposal lifecycle and immutable evaluations

Revision ID: 20260813_0041
Revises: 20260813_0040
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0041"
down_revision: str | None = "20260813_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "project_proposals" not in tables:
        op.create_table(
            "project_proposals",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("proposal_number", sa.String(40), nullable=False),
            sa.Column("source_idea_id", sa.Integer(), nullable=False),
            sa.Column("accepted_idea_evaluation_id", sa.Integer(), nullable=False),
            sa.Column("owning_workspace_id", sa.Integer(), nullable=False),
            sa.Column("target_portfolio_workspace_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(220), nullable=False),
            sa.Column("business_need", sa.Text(), nullable=False),
            sa.Column("business_justification", sa.Text(), nullable=False),
            sa.Column("project_objectives_json", sa.JSON(), nullable=False),
            sa.Column("preliminary_scope", sa.Text(), nullable=False),
            sa.Column("out_of_scope", sa.Text(), nullable=False),
            sa.Column("expected_benefits", sa.Text(), nullable=False),
            sa.Column("benefit_owner_user_id", sa.Integer(), nullable=True),
            sa.Column("rom_cost", sa.Numeric(18, 2), nullable=True),
            sa.Column("currency_code", sa.String(8), nullable=False),
            sa.Column("preliminary_duration_days", sa.Integer(), nullable=True),
            sa.Column("target_start_date", sa.Date(), nullable=True),
            sa.Column("target_finish_date", sa.Date(), nullable=True),
            sa.Column("key_risks_json", sa.JSON(), nullable=False),
            sa.Column("assumptions_json", sa.JSON(), nullable=False),
            sa.Column("constraints_json", sa.JSON(), nullable=False),
            sa.Column("strategic_objective_codes", sa.JSON(), nullable=False),
            sa.Column("sponsor_user_id", sa.Integer(), nullable=False),
            sa.Column("proposal_owner_user_id", sa.Integer(), nullable=False),
            sa.Column("origin_idea_score", sa.Numeric(9, 4), nullable=True),
            sa.Column("status", sa.String(48), nullable=False),
            sa.Column("mapping_configuration_id", sa.Integer(), nullable=False),
            sa.Column("mapping_revision", sa.Integer(), nullable=False),
            sa.Column("mapping_hash", sa.String(64), nullable=False),
            sa.Column("source_values_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("mapped_values_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("configuration_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("review_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("attachment_refs_json", sa.JSON(), nullable=False),
            sa.Column("return_reason", sa.Text(), nullable=True),
            sa.Column("returned_stage", sa.String(48), nullable=True),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
            sa.Column("review_started_at", sa.DateTime(), nullable=True),
            sa.Column("review_completed_at", sa.DateTime(), nullable=True),
            sa.Column("evaluation_started_at", sa.DateTime(), nullable=True),
            sa.Column("evaluation_completed_at", sa.DateTime(), nullable=True),
            sa.Column("ready_for_gate_at", sa.DateTime(), nullable=True),
            sa.Column("returned_at", sa.DateTime(), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(), nullable=True),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["source_idea_id"], ["ideas.id"]),
            sa.ForeignKeyConstraint(["accepted_idea_evaluation_id"], ["idea_evaluations.id"]),
            sa.ForeignKeyConstraint(["owning_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["target_portfolio_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["benefit_owner_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["sponsor_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["proposal_owner_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["mapping_configuration_id"], ["admin_configurations.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["updated_by"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "proposal_number", name="uq_project_proposal_tenant_number"),
        )
        for column in (
            "tenant_id",
            "proposal_number",
            "source_idea_id",
            "accepted_idea_evaluation_id",
            "owning_workspace_id",
            "target_portfolio_workspace_id",
            "benefit_owner_user_id",
            "sponsor_user_id",
            "proposal_owner_user_id",
            "status",
            "mapping_configuration_id",
            "created_by",
            "updated_by",
        ):
            op.create_index(op.f(f"ix_project_proposals_{column}"), "project_proposals", [column])
    if "project_proposal_evaluations" not in tables:
        op.create_table(
            "project_proposal_evaluations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_proposal_id", sa.Integer(), nullable=False),
            sa.Column("evaluation_version", sa.Integer(), nullable=False),
            sa.Column("matrix_configuration_id", sa.Integer(), nullable=False),
            sa.Column("matrix_revision", sa.Integer(), nullable=False),
            sa.Column("matrix_hash", sa.String(64), nullable=False),
            sa.Column("criteria_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("ratings_json", sa.JSON(), nullable=False),
            sa.Column("total_score", sa.Numeric(9, 4), nullable=False),
            sa.Column("recommendation", sa.String(80), nullable=False),
            sa.Column("comments", sa.Text(), nullable=False),
            sa.Column("evaluator_user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["project_proposal_id"], ["project_proposals.id"]),
            sa.ForeignKeyConstraint(["matrix_configuration_id"], ["admin_configurations.id"]),
            sa.ForeignKeyConstraint(["evaluator_user_id"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "project_proposal_id",
                "evaluation_version",
                name="uq_project_proposal_evaluation_version",
            ),
        )
        for column in (
            "tenant_id",
            "project_proposal_id",
            "matrix_configuration_id",
            "evaluator_user_id",
        ):
            op.create_index(
                op.f(f"ix_project_proposal_evaluations_{column}"),
                "project_proposal_evaluations",
                [column],
            )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "project_proposal_evaluations" in tables:
        op.drop_table("project_proposal_evaluations")
    if "project_proposals" in tables:
        op.drop_table("project_proposals")
