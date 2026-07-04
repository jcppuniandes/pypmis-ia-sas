"""expand colombia apu item name

Revision ID: 20260606_0024
Revises: 20260606_0023
Create Date: 2026-06-06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260606_0024"
down_revision = "20260606_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "colombia_apu_catalog_items",
        "item_name",
        existing_type=sa.String(length=320),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "colombia_apu_catalog_items",
        "item_name",
        existing_type=sa.Text(),
        type_=sa.String(length=320),
        existing_nullable=False,
    )
