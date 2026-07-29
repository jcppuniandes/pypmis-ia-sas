"""add unifier production hardening tables

Revision ID: 20260514_0016
Revises: 20260514_0015
Create Date: 2026-05-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260514_0016"
down_revision: str | None = "20260514_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "business_process_policies" not in table_names:
        op.create_table(
            "business_process_policies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("process_code", sa.String(length=80), nullable=False),
            sa.Column("action", sa.String(length=80), nullable=False),
            sa.Column("required_role", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("permission_key", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "project_id", "process_code", "action"),
        )

    if "business_process_line_item_revisions" not in table_names:
        op.create_table(
            "business_process_line_item_revisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("line_item_id", sa.Integer(), sa.ForeignKey("business_process_line_items.id"), nullable=False),
            sa.Column("process_instance_id", sa.Integer(), sa.ForeignKey("business_process_instances.id"), nullable=False),
            sa.Column("previous_version", sa.Integer(), nullable=False),
            sa.Column("new_version", sa.Integer(), nullable=False),
            sa.Column("previous_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("new_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("previous_quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("new_quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("previous_description", sa.Text(), nullable=False, server_default=""),
            sa.Column("new_description", sa.Text(), nullable=False, server_default=""),
            sa.Column("previous_status", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("new_status", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("change_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("changed_by", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    if "activity_sheet_recost_runs" not in table_names:
        op.create_table(
            "activity_sheet_recost_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("activity_sheet_id", sa.Integer(), sa.ForeignKey("activity_sheets.id"), nullable=False),
            sa.Column("rate_sheet_id", sa.Integer(), sa.ForeignKey("rate_sheets.id"), nullable=False),
            sa.Column("run_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_planned_cost", sa.Float(), nullable=False, server_default="0"),
            sa.Column("total_planned_value", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "project_id", "activity_sheet_id", "run_no"),
        )

    if "activity_sheet_recost_run_lines" not in table_names:
        op.create_table(
            "activity_sheet_recost_run_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("recost_run_id", sa.Integer(), sa.ForeignKey("activity_sheet_recost_runs.id"), nullable=False),
            sa.Column("activity_sheet_row_id", sa.Integer(), sa.ForeignKey("activity_sheet_rows.id"), nullable=False),
            sa.Column("external_activity_id", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("cbs_code", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("previous_planned_cost", sa.Float(), nullable=False, server_default="0"),
            sa.Column("new_planned_cost", sa.Float(), nullable=False, server_default="0"),
            sa.Column("previous_planned_value", sa.Float(), nullable=False, server_default="0"),
            sa.Column("new_planned_value", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    for table_name in (
        "activity_sheet_recost_run_lines",
        "activity_sheet_recost_runs",
        "business_process_line_item_revisions",
        "business_process_policies",
    ):
        if table_name in table_names:
            op.drop_table(table_name)
