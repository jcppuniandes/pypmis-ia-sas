"""add Workspace Operational Context recency persistence

Revision ID: 20260813_0039
Revises: 20260813_0038
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0039"
down_revision: str | None = "20260813_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "recent_workspaces" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "recent_workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("last_route", sa.String(length=320), nullable=False),
        sa.Column("last_opened_at", sa.DateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["enterprise_workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", "workspace_id", name="uq_recent_workspace_user_context"),
    )
    for column in ("tenant_id", "user_id", "workspace_id", "last_opened_at"):
        op.create_index(op.f(f"ix_recent_workspaces_{column}"), "recent_workspaces", [column])


def downgrade() -> None:
    if "recent_workspaces" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("recent_workspaces")

