"""add generic physical Workspace creation requests

Revision ID: 20260812_0037
Revises: 20260812_0036
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0037"
down_revision: str | None = "20260812_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "physical_workspace_creation_requests" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "physical_workspace_creation_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("request_number", sa.String(length=40), nullable=False),
        sa.Column("workspace_type_code", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("requestor_user_id", sa.Integer(), nullable=False),
        sa.Column("parent_workspace_id", sa.Integer(), nullable=False),
        sa.Column("template_config_id", sa.Integer(), nullable=False),
        sa.Column("workspace_name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("responsible_user_id", sa.Integer(), nullable=False),
        sa.Column("business_number_preview", sa.String(length=80), nullable=True),
        sa.Column("record_code_preview", sa.String(length=255), nullable=True),
        sa.Column("attributes_json", sa.JSON(), nullable=False),
        sa.Column("classification_values_json", sa.JSON(), nullable=False),
        sa.Column("submitted_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("submitted_hash", sa.String(length=64), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approval_hash", sa.String(length=64), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("materialized_workspace_id", sa.Integer(), nullable=True),
        sa.Column("materialized_business_number", sa.String(length=80), nullable=True),
        sa.Column("materialized_record_code", sa.String(length=255), nullable=True),
        sa.Column("revision_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_modified_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("materialized_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["requestor_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["parent_workspace_id"], ["enterprise_workspaces.id"]),
        sa.ForeignKeyConstraint(["template_config_id"], ["admin_configurations.id"]),
        sa.ForeignKeyConstraint(["responsible_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["materialized_workspace_id"], ["enterprise_workspaces.id"]),
        sa.ForeignKeyConstraint(["last_modified_by_user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "request_number", name="uq_physical_workspace_request_number"),
        sa.UniqueConstraint("materialized_workspace_id", name="uq_physical_workspace_materialized_workspace"),
    )
    for column in (
        "tenant_id",
        "request_number",
        "workspace_type_code",
        "state",
        "requestor_user_id",
        "parent_workspace_id",
        "template_config_id",
        "responsible_user_id",
        "approved_by_user_id",
        "materialized_workspace_id",
        "last_modified_by_user_id",
    ):
        op.create_index(
            op.f(f"ix_physical_workspace_creation_requests_{column}"),
            "physical_workspace_creation_requests",
            [column],
        )


def downgrade() -> None:
    if "physical_workspace_creation_requests" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("physical_workspace_creation_requests")
