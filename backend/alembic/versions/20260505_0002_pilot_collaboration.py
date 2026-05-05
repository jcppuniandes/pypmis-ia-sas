"""add pilot collaboration version fields

Revision ID: 20260505_0002
Revises: 20260505_0001
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260505_0002"
down_revision: str | None = "20260505_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


VERSIONED_TABLES = (
    "control_accounts",
    "work_packages",
    "work_package_constraints",
    "business_process_instances",
    "claim_entitlement_items",
    "claim_impact_analyses",
)

UPDATED_AT_TABLES = (
    "control_accounts",
    "work_packages",
    "work_package_constraints",
    "claim_entitlement_items",
    "claim_impact_analyses",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    for table_name in VERSIONED_TABLES:
        if table_name not in table_names or _has_column(inspector, table_name, "version"):
            continue
        op.add_column(
            table_name,
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )

    for table_name in UPDATED_AT_TABLES:
        if table_name not in table_names or _has_column(inspector, table_name, "updated_at"):
            continue
        op.add_column(
            table_name,
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    for table_name in UPDATED_AT_TABLES:
        if table_name in table_names and _has_column(inspector, table_name, "updated_at"):
            op.drop_column(table_name, "updated_at")

    for table_name in VERSIONED_TABLES:
        if table_name in table_names and _has_column(inspector, table_name, "version"):
            op.drop_column(table_name, "version")


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))
