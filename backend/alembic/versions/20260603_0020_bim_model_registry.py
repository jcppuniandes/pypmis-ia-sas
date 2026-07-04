"""bim model registry

Revision ID: 20260603_0020
Revises: 20260520_0019
Create Date: 2026-06-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260603_0020"
down_revision = "20260520_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bim_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source_file_name", sa.String(length=260), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False, server_default="ifc"),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_storage_path", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("viewer_artifact_path", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="uploaded"),
        sa.Column("schema", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("units", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("element_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storey_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_identity", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_bim_models_tenant_id", "bim_models", ["tenant_id"])
    op.create_index("ix_bim_models_project_id", "bim_models", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_bim_models_project_id", table_name="bim_models")
    op.drop_index("ix_bim_models_tenant_id", table_name="bim_models")
    op.drop_table("bim_models")
