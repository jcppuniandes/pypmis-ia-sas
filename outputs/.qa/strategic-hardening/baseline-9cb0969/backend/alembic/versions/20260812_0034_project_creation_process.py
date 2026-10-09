"""add governed project creation process

Revision ID: 20260812_0034
Revises: 20260810_0033
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0034"
down_revision: str | None = "20260810_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    assignment_columns = {item["name"] for item in inspector.get_columns("security_access_assignments")}
    if "workspace_id" not in assignment_columns:
        op.add_column("security_access_assignments", sa.Column("workspace_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_security_access_assignment_workspace",
            "security_access_assignments",
            "enterprise_workspaces",
            ["workspace_id"],
            ["id"],
        )
        op.create_index(
            "ix_security_access_assignments_workspace_id",
            "security_access_assignments",
            ["workspace_id"],
        )
    if "project_creation_requests" in tables:
        return
    op.create_table(
        "project_creation_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("request_number", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("requestor_user_id", sa.Integer(), nullable=False),
        sa.Column("parent_workspace_id", sa.Integer(), nullable=False),
        sa.Column("project_template_config_id", sa.Integer(), nullable=False),
        sa.Column("project_name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("project_manager_user_id", sa.Integer(), nullable=False),
        sa.Column("planned_start", sa.Date(), nullable=True),
        sa.Column("planned_finish", sa.Date(), nullable=True),
        sa.Column("currency_code", sa.String(length=8), nullable=False),
        sa.Column("estimated_budget", sa.Numeric(18, 2), nullable=True),
        sa.Column("project_type", sa.String(length=120), nullable=True),
        sa.Column("project_phase", sa.String(length=120), nullable=True),
        sa.Column("priority", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("strategic_objective_codes", sa.JSON(), nullable=False),
        sa.Column("preview_record_code", sa.String(length=255), nullable=True),
        sa.Column("preview_project_number", sa.String(length=80), nullable=True),
        sa.Column("submission_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("submission_hash", sa.String(length=64), nullable=True),
        sa.Column("approval_hash", sa.String(length=64), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("materialized_workspace_id", sa.Integer(), nullable=True),
        sa.Column("materialized_project_number", sa.String(length=80), nullable=True),
        sa.Column("materialized_record_code", sa.String(length=255), nullable=True),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_modified_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("materialized_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["requestor_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["parent_workspace_id"], ["enterprise_workspaces.id"]),
        sa.ForeignKeyConstraint(["project_template_config_id"], ["admin_configurations.id"]),
        sa.ForeignKeyConstraint(["project_manager_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["materialized_workspace_id"], ["enterprise_workspaces.id"]),
        sa.ForeignKeyConstraint(["last_modified_by_user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "request_number", name="uq_project_creation_request_number"),
        sa.UniqueConstraint("materialized_workspace_id", name="uq_project_creation_materialized_workspace"),
    )
    for column in (
        "tenant_id",
        "request_number",
        "state",
        "requestor_user_id",
        "parent_workspace_id",
        "project_template_config_id",
        "project_manager_user_id",
        "approved_by_user_id",
        "materialized_workspace_id",
        "last_modified_by_user_id",
    ):
        op.create_index(op.f(f"ix_project_creation_requests_{column}"), "project_creation_requests", [column])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "project_creation_requests" in set(inspector.get_table_names()):
        op.drop_table("project_creation_requests")
    assignment_columns = {item["name"] for item in inspector.get_columns("security_access_assignments")}
    if "workspace_id" in assignment_columns:
        op.drop_index("ix_security_access_assignments_workspace_id", table_name="security_access_assignments")
        op.drop_constraint(
            "fk_security_access_assignment_workspace",
            "security_access_assignments",
            type_="foreignkey",
        )
        op.drop_column("security_access_assignments", "workspace_id")
