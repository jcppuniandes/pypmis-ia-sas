"""add Gate 07C Strategic Gate Decision lifecycle

Revision ID: 20260813_0042
Revises: 20260813_0041
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260813_0042"
down_revision: str | None = "20260813_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())
    if "project_proposals" in tables:
        connection.execute(
            sa.text(
                "UPDATE project_proposals "
                "SET status = 'READY_FOR_STRATEGIC_GATE' "
                "WHERE status = 'READY_FOR_STRATEGIC_GATE_DECISION'"
            )
        )
    if "strategic_gate_decisions" in tables:
        return
    op.create_table(
        "strategic_gate_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("decision_number", sa.String(40), nullable=False),
        sa.Column("context_type", sa.String(48), nullable=False),
        sa.Column("context_id", sa.Integer(), nullable=False),
        sa.Column("project_proposal_id", sa.Integer(), nullable=False),
        sa.Column("gate_type", sa.String(80), nullable=False),
        sa.Column("gate_round", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=True),
        sa.Column("proposal_status_at_entry", sa.String(48), nullable=False),
        sa.Column("proposal_readiness_status", sa.String(64), nullable=False),
        sa.Column("proposal_readiness_hash", sa.String(64), nullable=False),
        sa.Column("proposal_readiness_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("proposal_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("source_idea_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("accepted_idea_evaluation_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("proposal_evaluation_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("source_idea_id", sa.Integer(), nullable=False),
        sa.Column("accepted_idea_evaluation_id", sa.Integer(), nullable=False),
        sa.Column("proposal_evaluation_id", sa.Integer(), nullable=False),
        sa.Column("owning_workspace_id", sa.Integer(), nullable=False),
        sa.Column("target_portfolio_workspace_id", sa.Integer(), nullable=True),
        sa.Column("strategic_objectives_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("proposal_score", sa.Numeric(9, 4), nullable=True),
        sa.Column("proposal_evaluation_revision", sa.Integer(), nullable=False),
        sa.Column("configuration_id", sa.Integer(), nullable=False),
        sa.Column("configuration_revision", sa.Integer(), nullable=False),
        sa.Column("configuration_hash", sa.String(64), nullable=False),
        sa.Column("configuration_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("decision_criteria_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("decision_checklist_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("conditions_json", sa.JSON(), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column("decision_comments", sa.Text(), nullable=False),
        sa.Column("decision_maker_user_id", sa.Integer(), nullable=True),
        sa.Column("committee_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("decision_hash", sa.String(64), nullable=False),
        sa.Column("prepared_by_user_id", sa.Integer(), nullable=False),
        sa.Column("prepared_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("review_started_at", sa.DateTime(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("deferred_until", sa.Date(), nullable=True),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_proposal_id"], ["project_proposals.id"]),
        sa.ForeignKeyConstraint(["source_idea_id"], ["ideas.id"]),
        sa.ForeignKeyConstraint(["accepted_idea_evaluation_id"], ["idea_evaluations.id"]),
        sa.ForeignKeyConstraint(["proposal_evaluation_id"], ["project_proposal_evaluations.id"]),
        sa.ForeignKeyConstraint(["owning_workspace_id"], ["enterprise_workspaces.id"]),
        sa.ForeignKeyConstraint(["target_portfolio_workspace_id"], ["enterprise_workspaces.id"]),
        sa.ForeignKeyConstraint(["configuration_id"], ["admin_configurations.id"]),
        sa.ForeignKeyConstraint(["decision_maker_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["prepared_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "decision_number", name="uq_sgd_tenant_number"),
        sa.UniqueConstraint(
            "tenant_id",
            "project_proposal_id",
            "gate_type",
            "gate_round",
            name="uq_sgd_proposal_gate_round",
        ),
    )
    for column in (
        "tenant_id",
        "decision_number",
        "context_type",
        "context_id",
        "project_proposal_id",
        "gate_type",
        "state",
        "outcome",
        "source_idea_id",
        "accepted_idea_evaluation_id",
        "proposal_evaluation_id",
        "owning_workspace_id",
        "target_portfolio_workspace_id",
        "configuration_id",
        "decision_maker_user_id",
        "prepared_by_user_id",
        "created_by",
        "updated_by",
    ):
        op.create_index(
            op.f(f"ix_strategic_gate_decisions_{column}"),
            "strategic_gate_decisions",
            [column],
        )
    op.create_index(
        "uq_sgd_one_active_per_proposal_gate",
        "strategic_gate_decisions",
        ["tenant_id", "project_proposal_id", "gate_type"],
        unique=True,
        postgresql_where=sa.text("state IN ('DRAFT','SUBMITTED','IN_REVIEW')"),
        sqlite_where=sa.text("state IN ('DRAFT','SUBMITTED','IN_REVIEW')"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())
    if "strategic_gate_decisions" in tables:
        op.drop_table("strategic_gate_decisions")
    if "project_proposals" in tables:
        connection.execute(
            sa.text(
                "UPDATE project_proposals "
                "SET status = 'READY_FOR_STRATEGIC_GATE_DECISION' "
                "WHERE status IN ('READY_FOR_STRATEGIC_GATE', 'STRATEGIC_GATE_APPROVED', "
                "'STRATEGIC_GATE_REJECTED', 'STRATEGIC_GATE_DEFERRED')"
            )
        )
