"""add governed project workspace initialization and activation

Revision ID: 20260812_0035
Revises: 20260812_0034
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0035"
down_revision: str | None = "20260812_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "project_workspace_initializations" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "project_workspace_initializations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("template_config_id", sa.Integer(), nullable=False),
        sa.Column("template_code", sa.String(length=120), nullable=False),
        sa.Column("template_revision", sa.Integer(), nullable=False),
        sa.Column("initialization_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_by_user_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("last_modified_by_user_id", sa.Integer(), nullable=False),
        sa.Column("validated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("validated_at", sa.DateTime(), nullable=True),
        sa.Column("ready_at", sa.DateTime(), nullable=True),
        sa.Column("activated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("validation_hash", sa.String(length=64), nullable=True),
        sa.Column("checklist_hash", sa.String(length=64), nullable=True),
        sa.Column("checklist_json", sa.JSON(), nullable=False),
        sa.Column("module_states_json", sa.JSON(), nullable=False),
        sa.Column("defaults_applied_json", sa.JSON(), nullable=False),
        sa.Column("assignments_json", sa.JSON(), nullable=False),
        sa.Column("failure_code", sa.String(length=120), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["enterprise_workspaces.id"]),
        sa.ForeignKeyConstraint(["template_config_id"], ["admin_configurations.id"]),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["last_modified_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["validated_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "workspace_id", name="uq_project_workspace_initialization"),
    )
    for column in (
        "tenant_id",
        "workspace_id",
        "state",
        "template_config_id",
        "started_by_user_id",
        "last_modified_by_user_id",
        "validated_by_user_id",
        "activated_by_user_id",
    ):
        op.create_index(
            op.f(f"ix_project_workspace_initializations_{column}"), "project_workspace_initializations", [column]
        )


def downgrade() -> None:
    if "project_workspace_initializations" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("project_workspace_initializations")
