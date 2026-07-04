"""link quantity takeoff runs to BIM model revisions

Revision ID: 20260619_0025
Revises: 20260606_0024
Create Date: 2026-06-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20260619_0025"
down_revision = "20260606_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bim_models", sa.Column("source_sha256", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("bim_models", sa.Column("revision_id", sa.String(length=120), nullable=False, server_default=""))
    op.create_index("ix_bim_models_source_sha256", "bim_models", ["source_sha256"])
    op.execute(
        """
        UPDATE bim_models
        SET source_sha256 = model_identity->'geometry_cache'->>'source_sha256'
        WHERE source_sha256 = ''
          AND model_identity->'geometry_cache'->>'source_sha256' IS NOT NULL
        """
    )
    op.execute("UPDATE bim_models SET revision_id = 'IFC-M' || id || '-LEGACY' WHERE revision_id = ''")

    op.add_column("quantity_takeoff_runs", sa.Column("bim_model_id", sa.Integer(), nullable=True))
    op.add_column(
        "quantity_takeoff_runs",
        sa.Column("source_sha256", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "quantity_takeoff_runs",
        sa.Column("bim_revision_id", sa.String(length=120), nullable=False, server_default=""),
    )
    op.add_column("quantity_takeoff_runs", sa.Column("model_linked_at", sa.DateTime(), nullable=True))
    op.create_index("ix_quantity_takeoff_runs_bim_model_id", "quantity_takeoff_runs", ["bim_model_id"])
    op.create_foreign_key(
        "fk_quantity_takeoff_runs_bim_model_id_bim_models",
        "quantity_takeoff_runs",
        "bim_models",
        ["bim_model_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        UPDATE quantity_takeoff_runs AS q
        SET bim_model_id = matched.id,
            bim_revision_id = matched.revision_id,
            model_linked_at = q.created_at
        FROM (
            SELECT DISTINCT ON (tenant_id, project_id, lower(source_file_name))
                id, tenant_id, project_id, source_file_name, revision_id
            FROM bim_models
            ORDER BY tenant_id, project_id, lower(source_file_name), created_at DESC, id DESC
        ) AS matched
        WHERE q.bim_model_id IS NULL
          AND q.source_type = 'ifc'
          AND q.tenant_id = matched.tenant_id
          AND q.project_id = matched.project_id
          AND lower(q.source_file_name) = lower(matched.source_file_name)
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_quantity_takeoff_runs_bim_model_id_bim_models",
        "quantity_takeoff_runs",
        type_="foreignkey",
    )
    op.drop_index("ix_quantity_takeoff_runs_bim_model_id", table_name="quantity_takeoff_runs")
    op.drop_column("quantity_takeoff_runs", "model_linked_at")
    op.drop_column("quantity_takeoff_runs", "bim_revision_id")
    op.drop_column("quantity_takeoff_runs", "source_sha256")
    op.drop_column("quantity_takeoff_runs", "bim_model_id")
    op.drop_index("ix_bim_models_source_sha256", table_name="bim_models")
    op.drop_column("bim_models", "revision_id")
    op.drop_column("bim_models", "source_sha256")
