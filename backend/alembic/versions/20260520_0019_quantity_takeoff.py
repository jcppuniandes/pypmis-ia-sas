"""quantity takeoff intake

Revision ID: 20260520_0019
Revises: 20260515_0018
Create Date: 2026-05-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260520_0019"
down_revision: str | None = "20260515_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quantity_takeoff_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source_file_name", sa.String(length=260), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="needs_mapping"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mapped_line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unmapped_line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("validation_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quantity_takeoff_runs_project_id", "quantity_takeoff_runs", ["project_id"])
    op.create_index("ix_quantity_takeoff_runs_tenant_id", "quantity_takeoff_runs", ["tenant_id"])

    op.create_table(
        "quantity_takeoff_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("source_row_id", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("element_id", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("element_guid", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("ifc_class", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("family", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("type_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("instance_name", sa.String(length=220), nullable=False, server_default=""),
        sa.Column("project_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("site_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("building_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("storey", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("system_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("zone_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("assembly_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("classification_system", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("classification_code", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("measurement_rule", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("wbs_code", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("cbs_code", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("fbs_code", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("package_code", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("mapping_status", sa.String(length=40), nullable=False, server_default="needs_mapping"),
        sa.Column("validation_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_data", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["quantity_takeoff_runs.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quantity_takeoff_lines_cbs_code", "quantity_takeoff_lines", ["cbs_code"])
    op.create_index("ix_quantity_takeoff_lines_element_guid", "quantity_takeoff_lines", ["element_guid"])
    op.create_index("ix_quantity_takeoff_lines_fbs_code", "quantity_takeoff_lines", ["fbs_code"])
    op.create_index("ix_quantity_takeoff_lines_package_code", "quantity_takeoff_lines", ["package_code"])
    op.create_index("ix_quantity_takeoff_lines_project_id", "quantity_takeoff_lines", ["project_id"])
    op.create_index("ix_quantity_takeoff_lines_run_id", "quantity_takeoff_lines", ["run_id"])
    op.create_index("ix_quantity_takeoff_lines_tenant_id", "quantity_takeoff_lines", ["tenant_id"])
    op.create_index("ix_quantity_takeoff_lines_wbs_code", "quantity_takeoff_lines", ["wbs_code"])


def downgrade() -> None:
    op.drop_index("ix_quantity_takeoff_lines_wbs_code", table_name="quantity_takeoff_lines")
    op.drop_index("ix_quantity_takeoff_lines_tenant_id", table_name="quantity_takeoff_lines")
    op.drop_index("ix_quantity_takeoff_lines_run_id", table_name="quantity_takeoff_lines")
    op.drop_index("ix_quantity_takeoff_lines_project_id", table_name="quantity_takeoff_lines")
    op.drop_index("ix_quantity_takeoff_lines_package_code", table_name="quantity_takeoff_lines")
    op.drop_index("ix_quantity_takeoff_lines_fbs_code", table_name="quantity_takeoff_lines")
    op.drop_index("ix_quantity_takeoff_lines_element_guid", table_name="quantity_takeoff_lines")
    op.drop_index("ix_quantity_takeoff_lines_cbs_code", table_name="quantity_takeoff_lines")
    op.drop_table("quantity_takeoff_lines")
    op.drop_index("ix_quantity_takeoff_runs_tenant_id", table_name="quantity_takeoff_runs")
    op.drop_index("ix_quantity_takeoff_runs_project_id", table_name="quantity_takeoff_runs")
    op.drop_table("quantity_takeoff_runs")
