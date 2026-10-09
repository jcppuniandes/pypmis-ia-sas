"""add unifier priority operational flow tables

Revision ID: 20260514_0015
Revises: 20260513_0014
Create Date: 2026-05-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260514_0015"
down_revision: str | None = "20260513_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "business_process_line_items" not in table_names:
        op.create_table(
            "business_process_line_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("process_instance_id", sa.Integer(), sa.ForeignKey("business_process_instances.id"), nullable=False),
            sa.Column("line_type", sa.String(length=40), nullable=False),
            sa.Column("wbs_id", sa.Integer(), sa.ForeignKey("wbs.id"), nullable=True),
            sa.Column("cbs_id", sa.Integer(), sa.ForeignKey("cost_breakdown_structures.id"), nullable=False),
            sa.Column("funding_source_id", sa.Integer(), sa.ForeignKey("funding_sources.id"), nullable=True),
            sa.Column("control_account_id", sa.Integer(), sa.ForeignKey("control_accounts.id"), nullable=True),
            sa.Column("cost_code_id", sa.Integer(), sa.ForeignKey("cost_codes.id"), nullable=True),
            sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    if "schedule_of_value_lines" not in table_names:
        op.create_table(
            "schedule_of_value_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False),
            sa.Column("line_no", sa.String(length=80), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("cbs_id", sa.Integer(), sa.ForeignKey("cost_breakdown_structures.id"), nullable=False),
            sa.Column("wbs_id", sa.Integer(), sa.ForeignKey("wbs.id"), nullable=True),
            sa.Column("control_account_id", sa.Integer(), sa.ForeignKey("control_accounts.id"), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "project_id", "contract_id", "line_no"),
        )

    if "commitment_funding_lines" not in table_names:
        op.create_table(
            "commitment_funding_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id"), nullable=False),
            sa.Column("sov_line_id", sa.Integer(), sa.ForeignKey("schedule_of_value_lines.id"), nullable=True),
            sa.Column("funding_source_id", sa.Integer(), sa.ForeignKey("funding_sources.id"), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("consumed_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    if "rate_sheets" not in table_names:
        op.create_table(
            "rate_sheets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=180), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "project_id", "code"),
        )

    if "rate_sheet_lines" not in table_names:
        op.create_table(
            "rate_sheet_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("rate_sheet_id", sa.Integer(), sa.ForeignKey("rate_sheets.id"), nullable=False),
            sa.Column("cbs_code", sa.String(length=120), nullable=False),
            sa.Column("unit_rate", sa.Float(), nullable=False, server_default="0"),
            sa.Column("multiplier", sa.Float(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "project_id", "rate_sheet_id", "cbs_code"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    for table_name in (
        "rate_sheet_lines",
        "rate_sheets",
        "commitment_funding_lines",
        "schedule_of_value_lines",
        "business_process_line_items",
    ):
        if table_name in table_names:
            op.drop_table(table_name)
