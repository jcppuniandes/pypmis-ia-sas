"""add integration export audit log

Revision ID: 20260507_0011
Revises: 20260507_0010
Create Date: 2026-05-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260507_0011"
down_revision: str | None = "20260507_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "integration_export_logs" not in table_names:
        op.create_table(
            "integration_export_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("requested_by_user_id", sa.Integer(), nullable=False),
            sa.Column("integration_token_id", sa.Integer(), nullable=True),
            sa.Column("actor", sa.String(length=180), nullable=False, server_default=""),
            sa.Column("artifact_type", sa.String(length=40), nullable=False),
            sa.Column("datasets", sa.Text(), nullable=False, server_default=""),
            sa.Column("format", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("file_name", sa.String(length=260), nullable=False, server_default=""),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="completed"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["integration_token_id"], ["integration_tokens.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.ForeignKeyConstraint(["requested_by_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_integration_export_logs_artifact_type"), "integration_export_logs", ["artifact_type"], unique=False)
        op.create_index(op.f("ix_integration_export_logs_integration_token_id"), "integration_export_logs", ["integration_token_id"], unique=False)
        op.create_index(op.f("ix_integration_export_logs_project_id"), "integration_export_logs", ["project_id"], unique=False)
        op.create_index(op.f("ix_integration_export_logs_requested_by_user_id"), "integration_export_logs", ["requested_by_user_id"], unique=False)
        op.create_index(op.f("ix_integration_export_logs_sha256"), "integration_export_logs", ["sha256"], unique=False)
        op.create_index(op.f("ix_integration_export_logs_status"), "integration_export_logs", ["status"], unique=False)
        op.create_index(op.f("ix_integration_export_logs_tenant_id"), "integration_export_logs", ["tenant_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "integration_export_logs" in table_names:
        op.drop_index(op.f("ix_integration_export_logs_tenant_id"), table_name="integration_export_logs")
        op.drop_index(op.f("ix_integration_export_logs_status"), table_name="integration_export_logs")
        op.drop_index(op.f("ix_integration_export_logs_sha256"), table_name="integration_export_logs")
        op.drop_index(op.f("ix_integration_export_logs_requested_by_user_id"), table_name="integration_export_logs")
        op.drop_index(op.f("ix_integration_export_logs_project_id"), table_name="integration_export_logs")
        op.drop_index(op.f("ix_integration_export_logs_integration_token_id"), table_name="integration_export_logs")
        op.drop_index(op.f("ix_integration_export_logs_artifact_type"), table_name="integration_export_logs")
        op.drop_table("integration_export_logs")
