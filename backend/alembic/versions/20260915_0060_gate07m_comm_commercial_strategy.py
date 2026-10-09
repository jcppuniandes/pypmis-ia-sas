"""add Gate 07M-COMM commercial strategy and controlled versions

Revision ID: 20260915_0060
Revises: 20260910_0059
Create Date: 2026-09-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_0060"
down_revision: str | None = "20260910_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if "commercial_contracting_strategies" not in existing:
        op.create_table(
            "commercial_contracting_strategies",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_workspace_id", sa.Integer(), nullable=False),
            sa.Column("strategy_number", sa.String(40), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("current_version_id", sa.Integer(), nullable=True),
            sa.Column("configuration_id", sa.Integer(), nullable=False),
            sa.Column("configuration_revision", sa.Integer(), nullable=False),
            sa.Column("configuration_hash", sa.String(64), nullable=False),
            sa.Column("configuration_source_workspace_id", sa.Integer(), nullable=True),
            sa.Column("configuration_resolution_chain_json", sa.JSON(), nullable=False),
            sa.Column("create_idempotency_key", sa.String(160), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["project_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["configuration_id"], ["admin_configurations.id"]),
            sa.ForeignKeyConstraint(["configuration_source_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["updated_by"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "project_workspace_id", name="uq_commercial_strategy_project"),
            sa.UniqueConstraint("tenant_id", "strategy_number", name="uq_commercial_strategy_number"),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_commercial_strategy_create_key"),
            sa.CheckConstraint(
                "status IN ('DRAFT','IN_REVIEW','COMPLETED','SUPERSEDED','VOIDED')",
                name="ck_commercial_strategy_status",
            ),
        )
        for column in (
            "tenant_id",
            "project_workspace_id",
            "strategy_number",
            "status",
            "current_version_id",
            "configuration_id",
            "configuration_hash",
            "configuration_source_workspace_id",
            "created_by",
            "updated_by",
            "updated_at",
        ):
            op.create_index(
                op.f(f"ix_commercial_contracting_strategies_{column}"),
                "commercial_contracting_strategies",
                [column],
            )
        op.create_index(
            "ix_commercial_strategy_queue",
            "commercial_contracting_strategies",
            ["tenant_id", "status", "updated_at", "id"],
        )

    existing = set(sa.inspect(bind).get_table_names())
    if "commercial_strategy_versions" not in existing:
        op.create_table(
            "commercial_strategy_versions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("commercial_strategy_id", sa.Integer(), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("version_purpose", sa.String(48), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("fel_stage_code", sa.String(32), nullable=True),
            sa.Column("content_json", sa.JSON(), nullable=False),
            sa.Column("readiness_json", sa.JSON(), nullable=False),
            sa.Column("readiness_status", sa.String(24), nullable=False),
            sa.Column("readiness_warnings_json", sa.JSON(), nullable=False),
            sa.Column("readiness_blockers_json", sa.JSON(), nullable=False),
            sa.Column("source_references_json", sa.JSON(), nullable=False),
            sa.Column("source_hashes_json", sa.JSON(), nullable=False),
            sa.Column("source_bundle_hash", sa.String(64), nullable=False),
            sa.Column("source_current", sa.Boolean(), nullable=False),
            sa.Column("configuration_id", sa.Integer(), nullable=False),
            sa.Column("configuration_revision", sa.Integer(), nullable=False),
            sa.Column("configuration_hash", sa.String(64), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("commercial_strategy_hash", sa.String(64), nullable=False),
            sa.Column("preparer_user_id", sa.Integer(), nullable=False),
            sa.Column("reviewer_user_id", sa.Integer(), nullable=True),
            sa.Column("return_reason", sa.Text(), nullable=True),
            sa.Column("void_reason", sa.Text(), nullable=True),
            sa.Column("create_idempotency_key", sa.String(160), nullable=True),
            sa.Column("submit_idempotency_key", sa.String(160), nullable=True),
            sa.Column("review_idempotency_key", sa.String(160), nullable=True),
            sa.Column("return_idempotency_key", sa.String(160), nullable=True),
            sa.Column("complete_idempotency_key", sa.String(160), nullable=True),
            sa.Column("void_idempotency_key", sa.String(160), nullable=True),
            sa.Column("refresh_idempotency_key", sa.String(160), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
            sa.Column("review_started_at", sa.DateTime(), nullable=True),
            sa.Column("returned_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("completed_by", sa.Integer(), nullable=True),
            sa.Column("voided_at", sa.DateTime(), nullable=True),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(
                ["commercial_strategy_id"], ["commercial_contracting_strategies.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(["configuration_id"], ["admin_configurations.id"]),
            sa.ForeignKeyConstraint(["preparer_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["reviewer_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["updated_by"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["completed_by"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id", "commercial_strategy_id", "version_number", name="uq_commercial_strategy_version"
            ),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_commercial_version_create_key"),
            sa.UniqueConstraint("tenant_id", "submit_idempotency_key", name="uq_commercial_version_submit_key"),
            sa.UniqueConstraint("tenant_id", "review_idempotency_key", name="uq_commercial_version_review_key"),
            sa.UniqueConstraint("tenant_id", "return_idempotency_key", name="uq_commercial_version_return_key"),
            sa.UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_commercial_version_complete_key"),
            sa.UniqueConstraint("tenant_id", "void_idempotency_key", name="uq_commercial_version_void_key"),
            sa.UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_commercial_version_refresh_key"),
            sa.CheckConstraint("version_number > 0", name="ck_commercial_version_number"),
            sa.CheckConstraint(
                "status IN ('DRAFT','IN_REVIEW','COMPLETED','SUPERSEDED','VOIDED')",
                name="ck_commercial_version_status",
            ),
            sa.CheckConstraint(
                "readiness_status IN ('NOT_STARTED','IN_PROGRESS','READY','BLOCKED','STALE','NOT_APPLICABLE')",
                name="ck_commercial_version_readiness",
            ),
        )
        for column in (
            "tenant_id",
            "commercial_strategy_id",
            "version_purpose",
            "status",
            "fel_stage_code",
            "readiness_status",
            "source_bundle_hash",
            "source_current",
            "configuration_id",
            "configuration_hash",
            "content_hash",
            "commercial_strategy_hash",
            "preparer_user_id",
            "reviewer_user_id",
            "created_by",
            "updated_by",
            "updated_at",
            "completed_by",
        ):
            op.create_index(
                op.f(f"ix_commercial_strategy_versions_{column}"),
                "commercial_strategy_versions",
                [column],
            )
        op.create_index(
            "ix_commercial_version_history",
            "commercial_strategy_versions",
            ["tenant_id", "commercial_strategy_id", "version_number"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if "commercial_strategy_versions" in existing:
        op.drop_table("commercial_strategy_versions")
    if "commercial_contracting_strategies" in existing:
        op.drop_table("commercial_contracting_strategies")

