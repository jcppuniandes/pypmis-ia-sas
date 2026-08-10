"""add controlled CORE identity and strategic objectives

Revision ID: 20260809_0030
Revises: 20260809_0029
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0030"
down_revision: str | None = "20260809_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    workspace_columns = {column["name"] for column in inspector.get_columns("enterprise_workspaces")}
    if "external_key" not in workspace_columns:
        op.add_column(
            "enterprise_workspaces",
            sa.Column("external_key", sa.String(length=160), nullable=True),
        )
        op.create_index(
            "ix_enterprise_workspaces_external_key",
            "enterprise_workspaces",
            ["external_key"],
        )
        op.create_unique_constraint(
            "uq_enterprise_workspace_external_key",
            "enterprise_workspaces",
            ["tenant_id", "external_key"],
        )

    if "enterprise_strategic_objectives" not in inspector.get_table_names():
        op.create_table(
            "enterprise_strategic_objectives",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=220), nullable=False),
            sa.Column("strategic_line", sa.String(length=180), nullable=True),
            sa.Column("priority", sa.String(length=80), nullable=True),
            sa.Column("horizon", sa.String(length=80), nullable=True),
            sa.Column("responsible_area", sa.String(length=120), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("source_release_code", sa.String(length=160), nullable=False),
            sa.Column("created_by_user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "code",
                name="uq_enterprise_strategic_objective_code",
            ),
        )
        op.create_index(
            "ix_enterprise_strategic_objectives_tenant_id",
            "enterprise_strategic_objectives",
            ["tenant_id"],
        )
        op.create_index(
            "ix_enterprise_strategic_objectives_code",
            "enterprise_strategic_objectives",
            ["code"],
        )
        op.create_index(
            "ix_enterprise_strategic_objectives_active",
            "enterprise_strategic_objectives",
            ["active"],
        )
        op.create_index(
            "ix_enterprise_strategic_objectives_source_release_code",
            "enterprise_strategic_objectives",
            ["source_release_code"],
        )
        op.create_index(
            "ix_enterprise_strategic_objectives_created_by_user_id",
            "enterprise_strategic_objectives",
            ["created_by_user_id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "enterprise_strategic_objectives" in inspector.get_table_names():
        op.drop_table("enterprise_strategic_objectives")
    workspace_columns = {column["name"] for column in inspector.get_columns("enterprise_workspaces")}
    if "external_key" in workspace_columns:
        op.drop_constraint(
            "uq_enterprise_workspace_external_key",
            "enterprise_workspaces",
            type_="unique",
        )
        op.drop_index("ix_enterprise_workspaces_external_key", table_name="enterprise_workspaces")
        op.drop_column("enterprise_workspaces", "external_key")
