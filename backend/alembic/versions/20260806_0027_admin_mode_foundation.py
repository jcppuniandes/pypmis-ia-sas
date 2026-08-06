"""add versioned admin mode configuration foundation

Revision ID: 20260806_0027
Revises: 20260806_0026
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_0027"
down_revision: str | None = "20260806_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if "admin_configurations" in sa.inspect(bind).get_table_names():
        return

    op.create_table(
        "admin_configurations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "kind", "code", "revision"),
    )
    op.create_table(
        "enterprise_workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("workspace_type_code", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("defaults_json", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["enterprise_workspaces.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code"),
    )
    op.create_table(
        "workspace_module_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("module_key", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["enterprise_workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "workspace_id", "module_key"),
    )
    op.create_table(
        "admin_number_sequences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("rule_code", sa.String(length=120), nullable=False),
        sa.Column("scope_key", sa.String(length=180), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "rule_code", "scope_key"),
    )

    indexed_columns = {
        "admin_configurations": ("tenant_id", "kind", "code", "status", "created_by_user_id"),
        "enterprise_workspaces": (
            "tenant_id",
            "parent_id",
            "workspace_type_code",
            "code",
            "status",
            "created_by_user_id",
        ),
        "workspace_module_settings": ("tenant_id", "workspace_id", "module_key", "updated_by_user_id"),
        "admin_number_sequences": ("tenant_id", "rule_code", "scope_key"),
    }
    for table_name, columns in indexed_columns.items():
        for column in columns:
            op.create_index(op.f(f"ix_{table_name}_{column}"), table_name, [column], unique=False)


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in (
        "admin_number_sequences",
        "workspace_module_settings",
        "enterprise_workspaces",
        "admin_configurations",
    ):
        if table_name in existing:
            op.drop_table(table_name)

