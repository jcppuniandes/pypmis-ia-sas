"""Wave 2B Basic Data metadata, immutable assessments and command retries.

Revision ID: 20261008_0065
Revises: 20261005_0064
Risk Governance and Basic Data requirements reuse AdminConfiguration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_0065"
down_revision: str | None = "20261005_0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_basic_data_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("requirement_code", sa.String(120), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("availability", sa.String(32), nullable=False, server_default="NOT_AVAILABLE"),
        sa.Column("validation_state", sa.String(32), nullable=False, server_default="NOT_VALIDATED"),
        sa.Column("quality", sa.String(40), nullable=False, server_default="NOT_VALIDATED"),
        sa.Column("confidence", sa.String(40), nullable=False, server_default="PRELIMINARY"),
        sa.Column("source_type", sa.String(80), nullable=False, server_default="REFERENCE"),
        sa.Column("source_reference", sa.String(500), nullable=True),
        sa.Column("source_version", sa.String(120), nullable=True),
        sa.Column("source_hash", sa.String(128), nullable=True),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("source_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("limitations", sa.Text(), nullable=False, server_default=""),
        sa.Column("assumptions", sa.Text(), nullable=False, server_default=""),
        sa.Column("gaps", sa.Text(), nullable=False, server_default=""),
        sa.Column("comments", sa.Text(), nullable=False, server_default=""),
        sa.Column("validated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=True),
        sa.Column("validated_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "tenant_id", "project_workspace_id", "requirement_code", name="uq_basic_data_project_requirement"
        ),
        sa.CheckConstraint(
            "availability IN ('NOT_AVAILABLE','PARTIALLY_AVAILABLE','AVAILABLE')", name="ck_basic_data_availability"
        ),
        sa.CheckConstraint(
            "validation_state IN ('NOT_VALIDATED','UNDER_VALIDATION','VALIDATED','REJECTED')",
            name="ck_basic_data_validation",
        ),
    )
    op.create_index("ix_project_basic_data_items_tenant_id", "project_basic_data_items", ["tenant_id"])
    op.create_index(
        "ix_project_basic_data_items_project_workspace_id", "project_basic_data_items", ["project_workspace_id"]
    )
    op.create_index(
        "ix_basic_data_register", "project_basic_data_items", ["tenant_id", "project_workspace_id", "category", "id"]
    )
    op.create_index(
        "ix_basic_data_validation_queue",
        "project_basic_data_items",
        ["tenant_id", "project_workspace_id", "validation_state", "id"],
    )
    op.create_table(
        "basic_data_readiness_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("assessment_number", sa.String(40), nullable=False),
        sa.Column("assessment_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("predecessor_id", sa.Integer(), sa.ForeignKey("basic_data_readiness_assessments.id"), nullable=True),
        sa.Column("title", sa.String(240), nullable=False, server_default="Basic Data Readiness"),
        sa.Column("comments", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False),
        sa.Column("configuration_revision", sa.Integer(), nullable=False),
        sa.Column("configuration_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("assessment_hash", sa.String(64), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=True),
        sa.Column("completed_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("tenant_id", "assessment_number", name="uq_basic_data_assessment_number"),
        sa.UniqueConstraint(
            "tenant_id", "project_workspace_id", "assessment_version", name="uq_basic_data_assessment_version"
        ),
        sa.CheckConstraint("status IN ('DRAFT','IN_REVIEW','COMPLETED')", name="ck_basic_data_assessment_status"),
        sa.CheckConstraint(
            "status != 'COMPLETED' OR (completed_at IS NOT NULL AND completed_by IS NOT NULL AND assessment_hash IS NOT NULL)",
            name="ck_basic_data_assessment_completed",
        ),
    )
    op.create_index("ix_basic_data_readiness_assessments_tenant_id", "basic_data_readiness_assessments", ["tenant_id"])
    op.create_index(
        "ix_basic_data_readiness_assessments_project_workspace_id",
        "basic_data_readiness_assessments",
        ["project_workspace_id"],
    )
    op.create_index(
        "ix_basic_data_assessment_history",
        "basic_data_readiness_assessments",
        ["tenant_id", "project_workspace_id", "status", "assessment_version"],
    )
    op.create_table(
        "basic_data_commands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("command_type", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_basic_data_command_key"),
    )


def downgrade() -> None:
    op.drop_table("basic_data_commands")
    op.drop_table("basic_data_readiness_assessments")
    op.drop_table("project_basic_data_items")
