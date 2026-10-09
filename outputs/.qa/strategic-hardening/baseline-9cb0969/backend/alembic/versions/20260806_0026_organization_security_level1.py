"""add level 1 organization and security records

Revision ID: 20260806_0026
Revises: 20260619_0025
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_0026"
down_revision: str | None = "20260619_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if "organization_units" in sa.inspect(bind).get_table_names():
        return

    op.create_table(
        "organization_units",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("unit_type", sa.String(length=80), nullable=False),
        sa.Column("manager_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["manager_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["organization_units.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code"),
    )
    op.create_table(
        "security_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code"),
    )
    op.create_table(
        "permission_catalog",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("resource", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_table(
        "security_roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code"),
    )
    op.create_table(
        "security_group_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("added_by_user_id", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["added_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["security_groups.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "group_id", "user_id"),
    )
    op.create_table(
        "security_role_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["permission_id"], ["permission_catalog.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["security_roles.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "role_id", "permission_id"),
    )
    op.create_table(
        "security_access_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=20), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=40), nullable=False),
        sa.Column("scope_unit_id", sa.Integer(), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["security_groups.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["security_roles.id"]),
        sa.ForeignKeyConstraint(["scope_unit_id"], ["organization_units.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    indexed_columns = {
        "organization_units": ("tenant_id", "parent_id", "code", "manager_user_id", "status"),
        "security_groups": ("tenant_id", "code", "owner_user_id", "status"),
        "permission_catalog": ("key", "resource", "status"),
        "security_roles": ("tenant_id", "code", "status"),
        "security_group_members": ("tenant_id", "group_id", "user_id", "added_by_user_id"),
        "security_role_permissions": ("tenant_id", "role_id", "permission_id", "granted_by_user_id"),
        "security_access_assignments": (
            "tenant_id",
            "subject_type",
            "user_id",
            "group_id",
            "role_id",
            "scope_type",
            "scope_unit_id",
            "status",
            "granted_by_user_id",
        ),
        "security_events": ("tenant_id", "user_id", "event_type", "outcome", "occurred_at"),
    }
    for table_name, columns in indexed_columns.items():
        for column in columns:
            op.create_index(op.f(f"ix_{table_name}_{column}"), table_name, [column], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for table_name in (
        "security_events",
        "security_access_assignments",
        "security_role_permissions",
        "security_group_members",
        "security_roles",
        "permission_catalog",
        "security_groups",
        "organization_units",
    ):
        if table_name in existing:
            op.drop_table(table_name)
