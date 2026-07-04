"""guided flow currency metadata

Revision ID: 20260515_0018
Revises: 20260514_0017
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260515_0018"
down_revision: str | None = "20260514_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tenant_columns = {column["name"] for column in inspector.get_columns("tenants")}
    import_columns = {column["name"] for column in inspector.get_columns("schedule_imports")}

    if "base_currency" not in tenant_columns:
        op.add_column("tenants", sa.Column("base_currency", sa.String(length=8), nullable=False, server_default="COP"))
    if "detected_currency" not in import_columns:
        op.add_column(
            "schedule_imports", sa.Column("detected_currency", sa.String(length=8), nullable=False, server_default="")
        )
    if "currency_confidence" not in import_columns:
        op.add_column(
            "schedule_imports",
            sa.Column("currency_confidence", sa.String(length=40), nullable=False, server_default="unknown"),
        )
    if "currency_source" not in import_columns:
        op.add_column(
            "schedule_imports", sa.Column("currency_source", sa.String(length=160), nullable=False, server_default="")
        )
    if "currency_confirmed" not in import_columns:
        op.add_column(
            "schedule_imports",
            sa.Column("currency_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "total_imported_cost" not in import_columns:
        op.add_column(
            "schedule_imports", sa.Column("total_imported_cost", sa.Float(), nullable=False, server_default="0")
        )
    if "cost_loaded_activity_count" not in import_columns:
        op.add_column(
            "schedule_imports",
            sa.Column("cost_loaded_activity_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if "cost_loaded_activity_percent" not in import_columns:
        op.add_column(
            "schedule_imports",
            sa.Column("cost_loaded_activity_percent", sa.Float(), nullable=False, server_default="0"),
        )
    if "cost_source_summary" not in import_columns:
        op.add_column(
            "schedule_imports",
            sa.Column("cost_source_summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )


def downgrade() -> None:
    op.drop_column("schedule_imports", "cost_source_summary")
    op.drop_column("schedule_imports", "cost_loaded_activity_percent")
    op.drop_column("schedule_imports", "cost_loaded_activity_count")
    op.drop_column("schedule_imports", "total_imported_cost")
    op.drop_column("schedule_imports", "currency_confirmed")
    op.drop_column("schedule_imports", "currency_source")
    op.drop_column("schedule_imports", "currency_confidence")
    op.drop_column("schedule_imports", "detected_currency")
    op.drop_column("tenants", "base_currency")
