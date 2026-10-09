"""bim quantity rule catalog

Revision ID: 20260603_0021
Revises: 20260603_0020
Create Date: 2026-06-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260603_0021"
down_revision = "20260603_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "bim_quantity_rules" in set(inspector.get_table_names()):
        return
    op.create_table(
        "bim_quantity_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("ifc_class", sa.String(length=120), nullable=False),
        sa.Column("element_label", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("expected_measure", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("rule_hint", sa.String(length=220), nullable=False, server_default=""),
        sa.Column("expected_units", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("allow_fallback_count", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="system_default"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint("tenant_id", "project_id", "ifc_class"),
    )
    op.create_index("ix_bim_quantity_rules_tenant_id", "bim_quantity_rules", ["tenant_id"])
    op.create_index("ix_bim_quantity_rules_project_id", "bim_quantity_rules", ["project_id"])
    op.create_index("ix_bim_quantity_rules_ifc_class", "bim_quantity_rules", ["ifc_class"])


def downgrade() -> None:
    op.drop_index("ix_bim_quantity_rules_ifc_class", table_name="bim_quantity_rules")
    op.drop_index("ix_bim_quantity_rules_project_id", table_name="bim_quantity_rules")
    op.drop_index("ix_bim_quantity_rules_tenant_id", table_name="bim_quantity_rules")
    op.drop_table("bim_quantity_rules")
