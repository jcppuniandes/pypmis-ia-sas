"""colombia apu catalog

Revision ID: 20260606_0023
Revises: 20260604_0022
Create Date: 2026-06-06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260606_0023"
down_revision = "20260604_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "colombia_apu_catalog_items" in inspector.get_table_names():
        existing_indexes = {index["name"] for index in inspector.get_indexes("colombia_apu_catalog_items")}
        for index_name, columns in (
            ("ix_colombia_apu_catalog_items_tenant_id", ["tenant_id"]),
            ("ix_colombia_apu_catalog_items_project_id", ["project_id"]),
            ("ix_colombia_apu_catalog_items_source_key", ["source_key"]),
            ("ix_colombia_apu_catalog_items_external_id", ["external_id"]),
            ("ix_colombia_apu_catalog_items_item_code", ["item_code"]),
            ("ix_colombia_apu_catalog_items_item_name", ["item_name"]),
        ):
            if index_name not in existing_indexes:
                op.create_index(index_name, "colombia_apu_catalog_items", columns)
        return

    op.create_table(
        "colombia_apu_catalog_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=80), nullable=False),
        sa.Column("external_id", sa.String(length=160), nullable=False),
        sa.Column("item_code", sa.String(length=80), nullable=False),
        sa.Column("item_name", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("unit_rate", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("group_name", sa.String(length=160), nullable=False),
        sa.Column("chapter", sa.String(length=220), nullable=False),
        sa.Column("region", sa.String(length=160), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("license_note", sa.Text(), nullable=False),
        sa.Column("update_frequency", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "project_id", "source_key", "external_id"),
    )
    op.create_index("ix_colombia_apu_catalog_items_tenant_id", "colombia_apu_catalog_items", ["tenant_id"])
    op.create_index("ix_colombia_apu_catalog_items_project_id", "colombia_apu_catalog_items", ["project_id"])
    op.create_index("ix_colombia_apu_catalog_items_source_key", "colombia_apu_catalog_items", ["source_key"])
    op.create_index("ix_colombia_apu_catalog_items_external_id", "colombia_apu_catalog_items", ["external_id"])
    op.create_index("ix_colombia_apu_catalog_items_item_code", "colombia_apu_catalog_items", ["item_code"])
    op.create_index("ix_colombia_apu_catalog_items_item_name", "colombia_apu_catalog_items", ["item_name"])


def downgrade() -> None:
    op.drop_index("ix_colombia_apu_catalog_items_item_name", table_name="colombia_apu_catalog_items")
    op.drop_index("ix_colombia_apu_catalog_items_item_code", table_name="colombia_apu_catalog_items")
    op.drop_index("ix_colombia_apu_catalog_items_external_id", table_name="colombia_apu_catalog_items")
    op.drop_index("ix_colombia_apu_catalog_items_source_key", table_name="colombia_apu_catalog_items")
    op.drop_index("ix_colombia_apu_catalog_items_project_id", table_name="colombia_apu_catalog_items")
    op.drop_index("ix_colombia_apu_catalog_items_tenant_id", table_name="colombia_apu_catalog_items")
    op.drop_table("colombia_apu_catalog_items")
