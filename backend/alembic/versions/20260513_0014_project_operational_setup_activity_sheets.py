"""add project operational setup and activity sheets

Revision ID: 20260513_0014
Revises: 20260512_0013
Create Date: 2026-05-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260513_0014"
down_revision: str | None = "20260512_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "project_operational_setups" not in table_names:
        op.create_table(
            "project_operational_setups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("project_number", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("setup_template", sa.String(length=180), nullable=False, server_default=""),
            sa.Column("attribute_form", sa.String(length=180), nullable=False, server_default=""),
            sa.Column("permissions_configured", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("modules_configured", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("cost_sheet_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("funding_sheet_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("p6_mapping_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
            sa.Column("readiness_status", sa.String(length=40), nullable=False, server_default="not_ready"),
            sa.Column("readiness_notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "project_id"),
        )

    if "activity_sheets" not in table_names:
        op.create_table(
            "activity_sheets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("schedule_import_id", sa.Integer(), sa.ForeignKey("schedule_imports.id"), nullable=True),
            sa.Column("source_file_name", sa.String(length=260), nullable=False),
            sa.Column("source", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("data_date", sa.Date(), nullable=True),
            sa.Column("baseline_name", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("validation_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    if "activity_sheet_rows" not in table_names:
        op.create_table(
            "activity_sheet_rows",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("activity_sheet_id", sa.Integer(), sa.ForeignKey("activity_sheets.id"), nullable=False),
            sa.Column("external_activity_id", sa.String(length=120), nullable=False),
            sa.Column("wbs_code", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("activity_name", sa.String(length=260), nullable=False, server_default=""),
            sa.Column("planned_start", sa.Date(), nullable=True),
            sa.Column("planned_finish", sa.Date(), nullable=True),
            sa.Column("total_float_days", sa.Float(), nullable=False, server_default="0"),
            sa.Column("critical_path", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("planned_cost", sa.Float(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    for table_name in ("activity_sheet_rows", "activity_sheets", "project_operational_setups"):
        if table_name in table_names:
            op.drop_table(table_name)
