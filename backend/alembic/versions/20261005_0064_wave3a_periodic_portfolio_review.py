"""Wave 3A periodic portfolio review and governance cycle.

Revision ID: 20261005_0064
Revises: 20261001_0063
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261005_0064"
down_revision: str | None = "20261001_0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolio_review_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("review_number", sa.String(length=40), nullable=False),
        sa.Column("portfolio_workspace_id", sa.Integer(), nullable=False),
        sa.Column("scope_workspace_id", sa.Integer(), nullable=False),
        sa.Column("planning_cycle_id", sa.Integer(), nullable=True),
        sa.Column("allocation_plan_id", sa.Integer(), nullable=True),
        sa.Column("review_type", sa.String(length=80), nullable=False),
        sa.Column("review_date", sa.Date(), nullable=False),
        sa.Column("review_period_start", sa.Date(), nullable=True),
        sa.Column("review_period_end", sa.Date(), nullable=True),
        sa.Column("actual_review_date", sa.Date(), nullable=True),
        sa.Column("next_planned_review_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("chair_user_id", sa.Integer(), nullable=False),
        sa.Column("secretary_user_id", sa.Integer(), nullable=True),
        sa.Column("agenda_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("configuration_id", sa.Integer(), nullable=False),
        sa.Column("configuration_revision", sa.Integer(), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("configuration_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("current_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("current_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("snapshot_frozen_at", sa.DateTime(), nullable=True),
        sa.Column("snapshot_frozen_by_user_id", sa.Integer(), nullable=True),
        sa.Column("completion_snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("completion_hash", sa.String(length=64), nullable=True),
        sa.Column("create_idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("create_request_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("last_modified_by_user_id", sa.Integer(), nullable=False),
        sa.Column("prepared_by_user_id", sa.Integer(), nullable=True),
        sa.Column("review_authority_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("prepared_at", sa.DateTime(), nullable=True),
        sa.Column("review_started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('DRAFT','PREPARING','READY_FOR_REVIEW','IN_REVIEW','STALE','RETURNED',"
            "'COMPLETED','CANCELLED','SUPERSEDED')",
            name="ck_portfolio_review_status",
        ),
        sa.CheckConstraint(
            "review_period_end IS NULL OR review_period_start IS NULL OR review_period_end >= review_period_start",
            name="ck_portfolio_review_period",
        ),
        sa.CheckConstraint(
            "status != 'COMPLETED' OR (completed_at IS NOT NULL AND completion_hash IS NOT NULL "
            "AND current_snapshot_hash IS NOT NULL)",
            name="ck_portfolio_review_completed",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["portfolio_workspace_id"], ["enterprise_workspaces.id"]),
        sa.ForeignKeyConstraint(["scope_workspace_id"], ["enterprise_workspaces.id"]),
        sa.ForeignKeyConstraint(["planning_cycle_id"], ["capital_planning_cycles.id"]),
        sa.ForeignKeyConstraint(["allocation_plan_id"], ["strategic_capital_allocation_plans.id"]),
        sa.ForeignKeyConstraint(["chair_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["secretary_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["configuration_id"], ["admin_configurations.id"]),
        sa.ForeignKeyConstraint(["snapshot_frozen_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["last_modified_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["prepared_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["review_authority_user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "review_number", name="uq_portfolio_review_number"),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_portfolio_review_create_key"),
    )
    for column in (
        "tenant_id",
        "review_number",
        "portfolio_workspace_id",
        "scope_workspace_id",
        "planning_cycle_id",
        "allocation_plan_id",
        "review_type",
        "review_date",
        "actual_review_date",
        "next_planned_review_date",
        "status",
        "chair_user_id",
        "secretary_user_id",
        "configuration_id",
        "configuration_hash",
        "current_snapshot_id",
        "current_snapshot_hash",
        "snapshot_frozen_by_user_id",
        "completion_hash",
        "created_by_user_id",
        "last_modified_by_user_id",
        "prepared_by_user_id",
        "review_authority_user_id",
        "updated_at",
        "completed_at",
    ):
        op.create_index(f"ix_portfolio_review_sessions_{column}", "portfolio_review_sessions", [column])
    op.create_index(
        "ix_portfolio_review_queue",
        "portfolio_review_sessions",
        ["tenant_id", "portfolio_workspace_id", "status", "review_date", "id"],
    )
    op.create_index(
        "ix_portfolio_review_history",
        "portfolio_review_sessions",
        ["tenant_id", "portfolio_workspace_id", "completed_at", "id"],
    )

    op.create_table(
        "portfolio_review_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("review_session_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_index_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("readiness_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("warnings_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("blockers_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("freeze_idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("freeze_request_hash", sa.String(length=64), nullable=False),
        sa.Column("frozen_by_user_id", sa.Integer(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["review_session_id"], ["portfolio_review_sessions.id"]),
        sa.ForeignKeyConstraint(["frozen_by_user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "review_session_id", "snapshot_version", name="uq_portfolio_review_snapshot_version"
        ),
        sa.UniqueConstraint("tenant_id", "freeze_idempotency_key", name="uq_portfolio_review_snapshot_freeze_key"),
    )
    for column in ("tenant_id", "review_session_id", "snapshot_hash", "frozen_by_user_id", "frozen_at"):
        op.create_index(f"ix_portfolio_review_snapshots_{column}", "portfolio_review_snapshots", [column])
    op.create_index(
        "ix_portfolio_review_snapshot_hash",
        "portfolio_review_snapshots",
        ["review_session_id", "snapshot_hash"],
    )

    op.create_table(
        "portfolio_review_conclusions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("review_session_id", sa.Integer(), nullable=False),
        sa.Column("conclusion_type", sa.String(length=120), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("conditions_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["review_session_id"], ["portfolio_review_sessions.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "review_session_id", "conclusion_type", name="uq_portfolio_review_conclusion_type"
        ),
    )
    for column in ("tenant_id", "review_session_id", "conclusion_type", "created_by_user_id", "updated_by_user_id"):
        op.create_index(f"ix_portfolio_review_conclusions_{column}", "portfolio_review_conclusions", [column])
    op.create_index(
        "ix_portfolio_review_conclusion_session",
        "portfolio_review_conclusions",
        ["review_session_id", "conclusion_type"],
    )

    op.create_table(
        "portfolio_review_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("action_number", sa.String(length=48), nullable=False),
        sa.Column("review_session_id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=40), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("subject_key", sa.String(length=120), nullable=True),
        sa.Column("action_type", sa.String(length=120), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=24), nullable=False, server_default="MEDIUM"),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="OPEN"),
        sa.Column("source_evidence_references_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("requested_source_authority", sa.String(length=120), nullable=True),
        sa.Column("dispatch_status", sa.String(length=32), nullable=False, server_default="NOT_REQUESTED"),
        sa.Column("execution_reference", sa.String(length=300), nullable=True),
        sa.Column("create_idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("create_request_hash", sa.String(length=64), nullable=False),
        sa.Column("approve_idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("approve_request_hash", sa.String(length=64), nullable=True),
        sa.Column("dispatch_idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("dispatch_request_hash", sa.String(length=64), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("last_modified_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('OPEN','ACCEPTED','IN_PROGRESS','COMPLETED','REJECTED','CANCELLED')",
            name="ck_portfolio_review_action_status",
        ),
        sa.CheckConstraint(
            "priority IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_portfolio_review_action_priority",
        ),
        sa.CheckConstraint(
            "dispatch_status IN ('NOT_REQUESTED','REQUEST_RECORDED','EXECUTED_BY_GOVERNED_ADAPTER','FAILED')",
            name="ck_portfolio_review_action_dispatch_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["review_session_id"], ["portfolio_review_sessions.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["last_modified_by_user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "action_number", name="uq_portfolio_review_action_number"),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_portfolio_review_action_create_key"),
        sa.UniqueConstraint("tenant_id", "approve_idempotency_key", name="uq_portfolio_review_action_approve_key"),
        sa.UniqueConstraint("tenant_id", "dispatch_idempotency_key", name="uq_portfolio_review_action_dispatch_key"),
    )
    for column in (
        "tenant_id",
        "action_number",
        "review_session_id",
        "subject_type",
        "subject_id",
        "action_type",
        "priority",
        "owner_user_id",
        "due_date",
        "status",
        "requested_source_authority",
        "dispatch_status",
        "created_by_user_id",
        "approved_by_user_id",
        "last_modified_by_user_id",
        "updated_at",
    ):
        op.create_index(f"ix_portfolio_review_actions_{column}", "portfolio_review_actions", [column])
    op.create_index(
        "ix_portfolio_review_action_queue",
        "portfolio_review_actions",
        ["tenant_id", "status", "due_date", "owner_user_id", "id"],
    )
    op.create_index(
        "ix_portfolio_review_action_subject",
        "portfolio_review_actions",
        ["tenant_id", "subject_type", "subject_id", "status"],
    )

    op.create_table(
        "portfolio_review_commands",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("review_session_id", sa.Integer(), nullable=True),
        sa.Column("review_action_id", sa.Integer(), nullable=True),
        sa.Column("command_type", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["review_session_id"], ["portfolio_review_sessions.id"]),
        sa.ForeignKeyConstraint(["review_action_id"], ["portfolio_review_actions.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_portfolio_review_command_key"),
    )
    for column in (
        "tenant_id",
        "review_session_id",
        "review_action_id",
        "command_type",
        "actor_user_id",
        "occurred_at",
    ):
        op.create_index(f"ix_portfolio_review_commands_{column}", "portfolio_review_commands", [column])
    op.create_index(
        "ix_portfolio_review_command_scope",
        "portfolio_review_commands",
        ["tenant_id", "review_session_id", "command_type", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("portfolio_review_commands")
    op.drop_table("portfolio_review_actions")
    op.drop_table("portfolio_review_conclusions")
    op.drop_table("portfolio_review_snapshots")
    op.drop_table("portfolio_review_sessions")
