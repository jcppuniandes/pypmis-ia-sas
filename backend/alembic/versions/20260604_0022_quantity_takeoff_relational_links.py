"""quantity takeoff relational links

Revision ID: 20260604_0022
Revises: 20260603_0021
Create Date: 2026-06-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260604_0022"
down_revision = "20260603_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quantity_takeoff_lines", sa.Column("wbs_id", sa.Integer(), nullable=True))
    op.add_column("quantity_takeoff_lines", sa.Column("cbs_id", sa.Integer(), nullable=True))
    op.add_column("quantity_takeoff_lines", sa.Column("fbs_id", sa.Integer(), nullable=True))
    op.add_column("quantity_takeoff_lines", sa.Column("work_package_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE quantity_takeoff_lines AS q
        SET wbs_id = w.id
        FROM wbs AS w
        WHERE q.wbs_id IS NULL
          AND q.wbs_code <> ''
          AND q.tenant_id = w.tenant_id
          AND q.project_id = w.project_id
          AND q.wbs_code = w.code
        """
    )
    op.execute(
        """
        UPDATE quantity_takeoff_lines AS q
        SET cbs_id = c.id
        FROM cost_breakdown_structures AS c
        WHERE q.cbs_id IS NULL
          AND q.cbs_code <> ''
          AND q.tenant_id = c.tenant_id
          AND q.project_id = c.project_id
          AND q.cbs_code = c.code
        """
    )
    op.execute(
        """
        UPDATE quantity_takeoff_lines AS q
        SET fbs_id = f.id
        FROM funding_sources AS f
        WHERE q.fbs_id IS NULL
          AND q.fbs_code <> ''
          AND q.tenant_id = f.tenant_id
          AND q.project_id = f.project_id
          AND q.fbs_code = f.code
        """
    )
    op.execute(
        """
        UPDATE quantity_takeoff_lines AS q
        SET work_package_id = wp.id
        FROM work_packages AS wp
        WHERE q.work_package_id IS NULL
          AND q.package_code <> ''
          AND q.tenant_id = wp.tenant_id
          AND q.project_id = wp.project_id
          AND q.package_code = wp.code
        """
    )
    op.create_index("ix_quantity_takeoff_lines_wbs_id", "quantity_takeoff_lines", ["wbs_id"])
    op.create_index("ix_quantity_takeoff_lines_cbs_id", "quantity_takeoff_lines", ["cbs_id"])
    op.create_index("ix_quantity_takeoff_lines_fbs_id", "quantity_takeoff_lines", ["fbs_id"])
    op.create_index("ix_quantity_takeoff_lines_work_package_id", "quantity_takeoff_lines", ["work_package_id"])
    op.create_foreign_key(
        "fk_quantity_takeoff_lines_wbs_id_wbs",
        "quantity_takeoff_lines",
        "wbs",
        ["wbs_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_quantity_takeoff_lines_cbs_id_cost_breakdown_structures",
        "quantity_takeoff_lines",
        "cost_breakdown_structures",
        ["cbs_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_quantity_takeoff_lines_fbs_id_funding_sources",
        "quantity_takeoff_lines",
        "funding_sources",
        ["fbs_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_quantity_takeoff_lines_work_package_id_work_packages",
        "quantity_takeoff_lines",
        "work_packages",
        ["work_package_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_quantity_takeoff_lines_work_package_id_work_packages",
        "quantity_takeoff_lines",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_quantity_takeoff_lines_fbs_id_funding_sources",
        "quantity_takeoff_lines",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_quantity_takeoff_lines_cbs_id_cost_breakdown_structures",
        "quantity_takeoff_lines",
        type_="foreignkey",
    )
    op.drop_constraint("fk_quantity_takeoff_lines_wbs_id_wbs", "quantity_takeoff_lines", type_="foreignkey")
    op.drop_index("ix_quantity_takeoff_lines_work_package_id", table_name="quantity_takeoff_lines")
    op.drop_index("ix_quantity_takeoff_lines_fbs_id", table_name="quantity_takeoff_lines")
    op.drop_index("ix_quantity_takeoff_lines_cbs_id", table_name="quantity_takeoff_lines")
    op.drop_index("ix_quantity_takeoff_lines_wbs_id", table_name="quantity_takeoff_lines")
    op.drop_column("quantity_takeoff_lines", "work_package_id")
    op.drop_column("quantity_takeoff_lines", "fbs_id")
    op.drop_column("quantity_takeoff_lines", "cbs_id")
    op.drop_column("quantity_takeoff_lines", "wbs_id")
