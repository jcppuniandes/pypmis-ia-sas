"""add project control plan

Revision ID: 20260506_0003
Revises: 20260505_0002
Create Date: 2026-05-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260506_0003"
down_revision: str | None = "20260505_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "project_control_plans" in inspector.get_table_names():
        return
    op.create_table(
        "project_control_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("execution_strategy", sa.Text(), nullable=False, server_default=""),
        sa.Column("control_strategy", sa.Text(), nullable=False, server_default=""),
        sa.Column("progress_measurement_rule", sa.Text(), nullable=False, server_default=""),
        sa.Column("cost_measurement_rule", sa.Text(), nullable=False, server_default=""),
        sa.Column("change_management_rule", sa.Text(), nullable=False, server_default=""),
        sa.Column("risk_management_rule", sa.Text(), nullable=False, server_default=""),
        sa.Column("procurement_strategy", sa.Text(), nullable=False, server_default=""),
        sa.Column("document_control_rule", sa.Text(), nullable=False, server_default=""),
        sa.Column("reporting_cadence", sa.String(length=120), nullable=False, server_default="Weekly"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "project_id"),
    )
    op.create_index(op.f("ix_project_control_plans_project_id"), "project_control_plans", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_control_plans_tenant_id"), "project_control_plans", ["tenant_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "project_control_plans" not in inspector.get_table_names():
        return
    op.drop_index(op.f("ix_project_control_plans_tenant_id"), table_name="project_control_plans")
    op.drop_index(op.f("ix_project_control_plans_project_id"), table_name="project_control_plans")
    op.drop_table("project_control_plans")
