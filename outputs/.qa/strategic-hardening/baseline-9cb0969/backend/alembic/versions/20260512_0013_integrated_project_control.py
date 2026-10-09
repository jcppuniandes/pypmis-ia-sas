"""add integrated project control structures

Revision ID: 20260512_0013
Revises: 20260511_0012
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260512_0013"
down_revision: str | None = "20260511_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PROJECT_COLUMNS = (
    ("calendar_base", sa.Column("calendar_base", sa.String(length=120), nullable=False, server_default="")),
    ("owner", sa.Column("owner", sa.String(length=160), nullable=False, server_default="")),
    ("status", sa.Column("status", sa.String(length=40), nullable=False, server_default="draft")),
    ("authorization_date", sa.Column("authorization_date", sa.Date(), nullable=True)),
    ("authorization_ref", sa.Column("authorization_ref", sa.String(length=160), nullable=False, server_default="")),
    ("configuration", sa.Column("configuration", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))),
)

WBS_COLUMNS = (
    ("level", sa.Column("level", sa.Integer(), nullable=False, server_default="1")),
    ("description", sa.Column("description", sa.Text(), nullable=False, server_default="")),
    ("dictionary", sa.Column("dictionary", sa.Text(), nullable=False, server_default="")),
    ("responsible", sa.Column("responsible", sa.String(length=160), nullable=False, server_default="")),
    ("status", sa.Column("status", sa.String(length=40), nullable=False, server_default="draft")),
)

CONTROL_ACCOUNT_COLUMNS = (
    ("awp_package_id", sa.Column("awp_package_id", sa.Integer(), sa.ForeignKey("work_packages.id"), nullable=True)),
    ("scope", sa.Column("scope", sa.Text(), nullable=False, server_default="")),
    ("budget", sa.Column("budget", sa.Float(), nullable=False, server_default="0")),
    ("start_date", sa.Column("start_date", sa.Date(), nullable=True)),
    ("finish_date", sa.Column("finish_date", sa.Date(), nullable=True)),
    ("earned_value", sa.Column("earned_value", sa.Float(), nullable=False, server_default="0")),
    ("actual_cost", sa.Column("actual_cost", sa.Float(), nullable=False, server_default="0")),
    ("forecast", sa.Column("forecast", sa.Float(), nullable=False, server_default="0")),
)

WORK_PACKAGE_COLUMNS = (
    ("wbs_id", sa.Column("wbs_id", sa.Integer(), sa.ForeignKey("wbs.id"), nullable=True)),
    ("description", sa.Column("description", sa.Text(), nullable=False, server_default="")),
    ("planned_release_date", sa.Column("planned_release_date", sa.Date(), nullable=True)),
    ("main_constraints", sa.Column("main_constraints", sa.Text(), nullable=False, server_default="")),
)

FUNDING_COLUMNS = (
    ("source_of_funds", sa.Column("source_of_funds", sa.String(length=180), nullable=False, server_default="")),
    ("funding_type", sa.Column("funding_type", sa.String(length=80), nullable=False, server_default="")),
    ("authorization_ref", sa.Column("authorization_ref", sa.String(length=160), nullable=False, server_default="")),
    ("usage_restrictions", sa.Column("usage_restrictions", sa.Text(), nullable=False, server_default="")),
    ("usage_rules", sa.Column("usage_rules", sa.Text(), nullable=False, server_default="")),
    ("funds_available", sa.Column("funds_available", sa.Float(), nullable=False, server_default="0")),
    ("funds_committed", sa.Column("funds_committed", sa.Float(), nullable=False, server_default="0")),
    ("funds_executed", sa.Column("funds_executed", sa.Float(), nullable=False, server_default="0")),
)

CONTRACT_COLUMNS = (
    ("funding_source_id", sa.Column("funding_source_id", sa.Integer(), sa.ForeignKey("funding_sources.id"), nullable=True)),
)

PURCHASE_ORDER_COLUMNS = (
    ("funding_source_id", sa.Column("funding_source_id", sa.Integer(), sa.ForeignKey("funding_sources.id"), nullable=True)),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    _add_missing_columns(inspector, table_names, "projects", PROJECT_COLUMNS)
    _add_missing_columns(inspector, table_names, "wbs", WBS_COLUMNS)
    _add_missing_columns(inspector, table_names, "control_accounts", CONTROL_ACCOUNT_COLUMNS)
    _add_missing_columns(inspector, table_names, "work_packages", WORK_PACKAGE_COLUMNS)
    _add_missing_columns(inspector, table_names, "funding_sources", FUNDING_COLUMNS)
    _add_missing_columns(inspector, table_names, "contracts", CONTRACT_COLUMNS)
    _add_missing_columns(inspector, table_names, "purchase_orders", PURCHASE_ORDER_COLUMNS)
    _create_integrated_control_tables(table_names)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    for table_name in ("cost_codes", "cost_breakdown_structures", "control_account_funding_allocations"):
        if table_name in table_names:
            op.drop_table(table_name)

    for table_name, columns in (
        ("purchase_orders", reversed(PURCHASE_ORDER_COLUMNS)),
        ("contracts", reversed(CONTRACT_COLUMNS)),
        ("funding_sources", reversed(FUNDING_COLUMNS)),
        ("work_packages", reversed(WORK_PACKAGE_COLUMNS)),
        ("control_accounts", reversed(CONTROL_ACCOUNT_COLUMNS)),
        ("wbs", reversed(WBS_COLUMNS)),
        ("projects", reversed(PROJECT_COLUMNS)),
    ):
        if table_name not in table_names:
            continue
        for column_name, _column in columns:
            if _has_column(inspector, table_name, column_name):
                op.drop_column(table_name, column_name)


def _create_integrated_control_tables(table_names: set[str]) -> None:
    if "control_account_funding_allocations" not in table_names:
        op.create_table(
            "control_account_funding_allocations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("control_account_id", sa.Integer(), sa.ForeignKey("control_accounts.id"), nullable=False),
            sa.Column("funding_source_id", sa.Integer(), sa.ForeignKey("funding_sources.id"), nullable=False),
            sa.Column("allocated_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("committed_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("actual_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("forecast_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("distribution_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "project_id", "control_account_id", "funding_source_id"),
        )

    if "cost_breakdown_structures" not in table_names:
        op.create_table(
            "cost_breakdown_structures",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("parent_id", sa.Integer(), sa.ForeignKey("cost_breakdown_structures.id"), nullable=True),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("cost_category", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "project_id", "code"),
        )

    if "cost_codes" not in table_names:
        op.create_table(
            "cost_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("wbs_id", sa.Integer(), sa.ForeignKey("wbs.id"), nullable=False),
            sa.Column("control_account_id", sa.Integer(), sa.ForeignKey("control_accounts.id"), nullable=False),
            sa.Column("cbs_id", sa.Integer(), sa.ForeignKey("cost_breakdown_structures.id"), nullable=False),
            sa.Column("fbs_id", sa.Integer(), sa.ForeignKey("funding_sources.id"), nullable=False),
            sa.Column("contract_ref", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("code", sa.String(length=160), nullable=False),
            sa.Column("budget", sa.Float(), nullable=False, server_default="0"),
            sa.Column("funds_available", sa.Float(), nullable=False, server_default="0"),
            sa.Column("commitments", sa.Float(), nullable=False, server_default="0"),
            sa.Column("actual_costs", sa.Float(), nullable=False, server_default="0"),
            sa.Column("forecast", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "project_id", "code"),
        )


def _add_missing_columns(
    inspector: sa.Inspector,
    table_names: set[str],
    table_name: str,
    columns: Sequence[tuple[str, sa.Column]],
) -> None:
    if table_name not in table_names:
        return
    for column_name, column in columns:
        if not _has_column(inspector, table_name, column_name):
            op.add_column(table_name, column)


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))
