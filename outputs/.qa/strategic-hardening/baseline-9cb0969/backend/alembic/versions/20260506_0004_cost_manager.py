"""add cost manager funding and cash flow

Revision ID: 20260506_0004
Revises: 20260506_0003
Create Date: 2026-05-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260506_0004"
down_revision: str | None = "20260506_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "funding_sources" not in table_names:
        op.create_table(
            "funding_sources",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="approved"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "project_id", "code"),
        )
        op.create_index(op.f("ix_funding_sources_code"), "funding_sources", ["code"], unique=False)
        op.create_index(op.f("ix_funding_sources_project_id"), "funding_sources", ["project_id"], unique=False)
        op.create_index(op.f("ix_funding_sources_tenant_id"), "funding_sources", ["tenant_id"], unique=False)

    if "cash_flow_periods" not in table_names:
        op.create_table(
            "cash_flow_periods",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("period_label", sa.String(length=40), nullable=False),
            sa.Column("planned_inflow", sa.Float(), nullable=False, server_default="0"),
            sa.Column("planned_outflow", sa.Float(), nullable=False, server_default="0"),
            sa.Column("actual_inflow", sa.Float(), nullable=False, server_default="0"),
            sa.Column("actual_outflow", sa.Float(), nullable=False, server_default="0"),
            sa.Column("forecast_outflow", sa.Float(), nullable=False, server_default="0"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "project_id", "period_label"),
        )
        op.create_index(op.f("ix_cash_flow_periods_period_label"), "cash_flow_periods", ["period_label"], unique=False)
        op.create_index(op.f("ix_cash_flow_periods_project_id"), "cash_flow_periods", ["project_id"], unique=False)
        op.create_index(op.f("ix_cash_flow_periods_tenant_id"), "cash_flow_periods", ["tenant_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "cash_flow_periods" in table_names:
        op.drop_index(op.f("ix_cash_flow_periods_tenant_id"), table_name="cash_flow_periods")
        op.drop_index(op.f("ix_cash_flow_periods_project_id"), table_name="cash_flow_periods")
        op.drop_index(op.f("ix_cash_flow_periods_period_label"), table_name="cash_flow_periods")
        op.drop_table("cash_flow_periods")

    if "funding_sources" in table_names:
        op.drop_index(op.f("ix_funding_sources_tenant_id"), table_name="funding_sources")
        op.drop_index(op.f("ix_funding_sources_project_id"), table_name="funding_sources")
        op.drop_index(op.f("ix_funding_sources_code"), table_name="funding_sources")
        op.drop_table("funding_sources")
