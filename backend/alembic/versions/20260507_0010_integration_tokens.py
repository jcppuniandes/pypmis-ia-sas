"""add governed integration tokens

Revision ID: 20260507_0010
Revises: 20260507_0009
Create Date: 2026-05-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260507_0010"
down_revision: str | None = "20260507_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "integration_tokens" not in table_names:
        op.create_table(
            "integration_tokens",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("created_by_user_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("token_prefix", sa.String(length=40), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("allowed_datasets", sa.Text(), nullable=False, server_default=""),
            sa.Column("allowed_formats", sa.String(length=80), nullable=False, server_default="json,csv,both,xlsx"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "token_hash"),
        )
        op.create_index(op.f("ix_integration_tokens_created_by_user_id"), "integration_tokens", ["created_by_user_id"], unique=False)
        op.create_index(op.f("ix_integration_tokens_project_id"), "integration_tokens", ["project_id"], unique=False)
        op.create_index(op.f("ix_integration_tokens_status"), "integration_tokens", ["status"], unique=False)
        op.create_index(op.f("ix_integration_tokens_tenant_id"), "integration_tokens", ["tenant_id"], unique=False)
        op.create_index(op.f("ix_integration_tokens_token_hash"), "integration_tokens", ["token_hash"], unique=False)
        op.create_index(op.f("ix_integration_tokens_token_prefix"), "integration_tokens", ["token_prefix"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "integration_tokens" in table_names:
        op.drop_index(op.f("ix_integration_tokens_token_prefix"), table_name="integration_tokens")
        op.drop_index(op.f("ix_integration_tokens_token_hash"), table_name="integration_tokens")
        op.drop_index(op.f("ix_integration_tokens_tenant_id"), table_name="integration_tokens")
        op.drop_index(op.f("ix_integration_tokens_status"), table_name="integration_tokens")
        op.drop_index(op.f("ix_integration_tokens_project_id"), table_name="integration_tokens")
        op.drop_index(op.f("ix_integration_tokens_created_by_user_id"), table_name="integration_tokens")
        op.drop_table("integration_tokens")
