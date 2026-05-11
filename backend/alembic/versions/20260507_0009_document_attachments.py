"""add document attachment storage metadata

Revision ID: 20260507_0009
Revises: 20260506_0008
Create Date: 2026-05-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260507_0009"
down_revision: str | None = "20260506_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "document_attachments" not in table_names:
        op.create_table(
            "document_attachments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("document_id", sa.Integer(), nullable=False),
            sa.Column("original_file_name", sa.String(length=260), nullable=False),
            sa.Column("stored_file_name", sa.String(length=260), nullable=False),
            sa.Column("storage_path", sa.String(length=500), nullable=False),
            sa.Column("content_type", sa.String(length=160), nullable=False, server_default="application/octet-stream"),
            sa.Column("extension", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("source", sa.String(length=40), nullable=False, server_default="upload"),
            sa.Column("uploaded_by", sa.String(length=160), nullable=False, server_default="system"),
            sa.Column("scan_status", sa.String(length=40), nullable=False, server_default="not_scanned"),
            sa.Column("validation_message", sa.String(length=360), nullable=False, server_default=""),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_document_attachments_document_id"), "document_attachments", ["document_id"], unique=False)
        op.create_index(op.f("ix_document_attachments_project_id"), "document_attachments", ["project_id"], unique=False)
        op.create_index(op.f("ix_document_attachments_sha256"), "document_attachments", ["sha256"], unique=False)
        op.create_index(op.f("ix_document_attachments_tenant_id"), "document_attachments", ["tenant_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "document_attachments" in table_names:
        op.drop_index(op.f("ix_document_attachments_tenant_id"), table_name="document_attachments")
        op.drop_index(op.f("ix_document_attachments_sha256"), table_name="document_attachments")
        op.drop_index(op.f("ix_document_attachments_project_id"), table_name="document_attachments")
        op.drop_index(op.f("ix_document_attachments_document_id"), table_name="document_attachments")
        op.drop_table("document_attachments")
