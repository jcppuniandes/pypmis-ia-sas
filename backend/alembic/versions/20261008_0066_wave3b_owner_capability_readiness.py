"""Wave 3B Owner Capability aggregates and immutable command receipts.

Revision ID: 20261008_0066
Revises: 20261008_0065
Framework and requirements reuse AdminConfiguration; no historical rewrites.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_0066"
down_revision: str | None = "20261008_0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owner_capability_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("assessment_number", sa.String(40), nullable=False),
        sa.Column("assessment_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("predecessor_id", sa.Integer(), sa.ForeignKey("owner_capability_assessments.id"), nullable=True),
        sa.Column("title", sa.String(240), nullable=False, server_default="Owner Capability Readiness"),
        sa.Column("comments", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False),
        sa.Column("configuration_revision", sa.Integer(), nullable=False),
        sa.Column("configuration_hash", sa.String(64), nullable=False),
        sa.Column("aggregate_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("assessment_hash", sa.String(64), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=True),
        sa.Column("completed_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("tenant_id", "assessment_number", name="uq_owner_capability_number"),
        sa.UniqueConstraint(
            "tenant_id", "project_workspace_id", "assessment_version", name="uq_owner_capability_version"
        ),
        sa.CheckConstraint("status IN ('DRAFT','IN_REVIEW','COMPLETED')", name="ck_owner_capability_status"),
        sa.CheckConstraint("assessment_version > 0 AND revision_version > 0", name="ck_owner_capability_versions"),
        sa.CheckConstraint(
            "status != 'COMPLETED' OR (completed_at IS NOT NULL AND completed_by IS NOT NULL "
            "AND reviewed_by IS NOT NULL AND assessment_hash IS NOT NULL)",
            name="ck_owner_capability_completed",
        ),
    )
    op.create_index("ix_owner_capability_assessments_tenant_id", "owner_capability_assessments", ["tenant_id"])
    op.create_index(
        "ix_owner_capability_assessments_project_workspace_id", "owner_capability_assessments", ["project_workspace_id"]
    )
    op.create_index(
        "ix_owner_capability_history",
        "owner_capability_assessments",
        ["tenant_id", "project_workspace_id", "status", "assessment_version"],
    )
    op.create_table(
        "owner_capability_commands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("command_type", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_owner_capability_command_key"),
    )


def downgrade() -> None:
    op.drop_table("owner_capability_commands")
    op.drop_table("owner_capability_assessments")
