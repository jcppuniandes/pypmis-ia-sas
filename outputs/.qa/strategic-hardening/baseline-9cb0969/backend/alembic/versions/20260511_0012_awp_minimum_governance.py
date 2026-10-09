"""add awp minimum governance fields

Revision ID: 20260511_0012
Revises: 20260507_0011
Create Date: 2026-05-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260511_0012"
down_revision: str | None = "20260507_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CONTROL_ACCOUNT_COLUMNS = (
    ("cbs_code", sa.Column("cbs_code", sa.String(length=80), nullable=False, server_default="")),
    ("contract_ref", sa.Column("contract_ref", sa.String(length=120), nullable=False, server_default="")),
    ("measurement_rule", sa.Column("measurement_rule", sa.String(length=260), nullable=False, server_default="")),
    ("lifecycle_status", sa.Column("lifecycle_status", sa.String(length=40), nullable=False, server_default="active")),
    ("risk_ref", sa.Column("risk_ref", sa.String(length=120), nullable=False, server_default="")),
    ("closure_note", sa.Column("closure_note", sa.String(length=360), nullable=False, server_default="")),
)

WORK_PACKAGE_COLUMNS = (
    ("release_required_on", sa.Column("release_required_on", sa.Date(), nullable=True)),
)

CONSTRAINT_COLUMNS = (
    ("priority", sa.Column("priority", sa.String(length=40), nullable=False, server_default="medium")),
    ("evidence_ref", sa.Column("evidence_ref", sa.String(length=180), nullable=False, server_default="")),
    ("closure_note", sa.Column("closure_note", sa.String(length=360), nullable=False, server_default="")),
    ("exception_ref", sa.Column("exception_ref", sa.String(length=180), nullable=False, server_default="")),
    ("closed_by", sa.Column("closed_by", sa.String(length=160), nullable=False, server_default="")),
    ("closed_on", sa.Column("closed_on", sa.Date(), nullable=True)),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    _add_missing_columns(inspector, table_names, "control_accounts", CONTROL_ACCOUNT_COLUMNS)
    _add_missing_columns(inspector, table_names, "work_packages", WORK_PACKAGE_COLUMNS)
    _add_missing_columns(inspector, table_names, "work_package_constraints", CONSTRAINT_COLUMNS)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    for table_name, columns in (
        ("work_package_constraints", reversed(CONSTRAINT_COLUMNS)),
        ("work_packages", reversed(WORK_PACKAGE_COLUMNS)),
        ("control_accounts", reversed(CONTROL_ACCOUNT_COLUMNS)),
    ):
        if table_name not in table_names:
            continue
        for column_name, _column in columns:
            if _has_column(inspector, table_name, column_name):
                op.drop_column(table_name, column_name)


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
