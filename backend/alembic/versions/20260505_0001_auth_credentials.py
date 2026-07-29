"""add auth credentials

Revision ID: 20260505_0001
Revises:
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260505_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "auth_credentials" in inspector.get_table_names():
        return
    op.create_table(
        "auth_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("password_hash", sa.String(length=220), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", "provider"),
    )
    op.create_index(op.f("ix_auth_credentials_tenant_id"), "auth_credentials", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_auth_credentials_user_id"), "auth_credentials", ["user_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "auth_credentials" not in inspector.get_table_names():
        return
    op.drop_index(op.f("ix_auth_credentials_user_id"), table_name="auth_credentials")
    op.drop_index(op.f("ix_auth_credentials_tenant_id"), table_name="auth_credentials")
    op.drop_table("auth_credentials")
