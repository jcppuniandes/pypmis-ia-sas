"""add aconex style document control

Revision ID: 20260506_0005
Revises: 20260506_0004
Create Date: 2026-05-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260506_0005"
down_revision: str | None = "20260506_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DOCUMENT_COLUMNS = (
    ("document_number", sa.Column("document_number", sa.String(length=120), nullable=False, server_default="")),
    ("revision", sa.Column("revision", sa.String(length=40), nullable=False, server_default="A")),
    ("revision_date", sa.Column("revision_date", sa.Date(), nullable=True)),
    ("discipline", sa.Column("discipline", sa.String(length=80), nullable=False, server_default="")),
    ("organization", sa.Column("organization", sa.String(length=120), nullable=False, server_default="")),
    ("status", sa.Column("status", sa.String(length=40), nullable=False, server_default="current")),
    ("review_status", sa.Column("review_status", sa.String(length=40), nullable=False, server_default="not_started")),
    ("confidentiality", sa.Column("confidentiality", sa.String(length=40), nullable=False, server_default="project")),
    ("file_name", sa.Column("file_name", sa.String(length=260), nullable=False, server_default="")),
    ("version", sa.Column("version", sa.Integer(), nullable=False, server_default="1")),
    ("created_at", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))),
    ("updated_at", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "documents" in table_names:
        existing_columns = {column["name"] for column in inspector.get_columns("documents")}
        for column_name, column in DOCUMENT_COLUMNS:
            if column_name not in existing_columns:
                op.add_column("documents", column)
        op.execute("UPDATE documents SET document_number = 'DOC-' || LPAD(id::text, 5, '0') WHERE document_number = ''")
        if not _has_index(inspector, "documents", "ix_documents_document_number"):
            op.create_index(op.f("ix_documents_document_number"), "documents", ["document_number"], unique=False)

    if "document_transmittals" not in table_names:
        op.create_table(
            "document_transmittals",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("transmittal_no", sa.String(length=120), nullable=False),
            sa.Column("subject", sa.String(length=260), nullable=False),
            sa.Column("purpose", sa.String(length=80), nullable=False, server_default="for_review"),
            sa.Column("recipient_org", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("recipient_contact", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="sent"),
            sa.Column("sent_on", sa.Date(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("created_by", sa.String(length=160), nullable=False, server_default="system"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "project_id", "transmittal_no"),
        )
        op.create_index(op.f("ix_document_transmittals_project_id"), "document_transmittals", ["project_id"], unique=False)
        op.create_index(op.f("ix_document_transmittals_tenant_id"), "document_transmittals", ["tenant_id"], unique=False)
        op.create_index(op.f("ix_document_transmittals_transmittal_no"), "document_transmittals", ["transmittal_no"], unique=False)

    if "document_transmittal_items" not in table_names:
        op.create_table(
            "document_transmittal_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("transmittal_id", sa.Integer(), nullable=False),
            sa.Column("document_id", sa.Integer(), nullable=False),
            sa.Column("document_number", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("revision", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("action_required", sa.String(length=80), nullable=False, server_default="review"),
            sa.Column("response_status", sa.String(length=40), nullable=False, server_default="outstanding"),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.ForeignKeyConstraint(["transmittal_id"], ["document_transmittals.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "project_id", "transmittal_id", "document_id"),
        )
        op.create_index(op.f("ix_document_transmittal_items_document_id"), "document_transmittal_items", ["document_id"], unique=False)
        op.create_index(op.f("ix_document_transmittal_items_project_id"), "document_transmittal_items", ["project_id"], unique=False)
        op.create_index(op.f("ix_document_transmittal_items_tenant_id"), "document_transmittal_items", ["tenant_id"], unique=False)
        op.create_index(op.f("ix_document_transmittal_items_transmittal_id"), "document_transmittal_items", ["transmittal_id"], unique=False)

    if "document_reviews" not in table_names:
        op.create_table(
            "document_reviews",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("document_id", sa.Integer(), nullable=False),
            sa.Column("reviewer_role", sa.String(length=120), nullable=False, server_default="Document Control"),
            sa.Column("review_status", sa.String(length=40), nullable=False, server_default="outstanding"),
            sa.Column("comments", sa.Text(), nullable=False, server_default=""),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("closed_on", sa.Date(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_document_reviews_document_id"), "document_reviews", ["document_id"], unique=False)
        op.create_index(op.f("ix_document_reviews_project_id"), "document_reviews", ["project_id"], unique=False)
        op.create_index(op.f("ix_document_reviews_tenant_id"), "document_reviews", ["tenant_id"], unique=False)

    if "project_mail" not in table_names:
        op.create_table(
            "project_mail",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("mail_no", sa.String(length=120), nullable=False),
            sa.Column("mail_type", sa.String(length=80), nullable=False, server_default="letter"),
            sa.Column("subject", sa.String(length=260), nullable=False),
            sa.Column("from_role", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("to_role", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="outstanding"),
            sa.Column("response_required", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sent_on", sa.Date(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("closed_on", sa.Date(), nullable=True),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("linked_entity_type", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("linked_entity_id", sa.Integer(), nullable=True),
            sa.Column("document_id", sa.Integer(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "project_id", "mail_no"),
        )
        op.create_index(op.f("ix_project_mail_document_id"), "project_mail", ["document_id"], unique=False)
        op.create_index(op.f("ix_project_mail_mail_no"), "project_mail", ["mail_no"], unique=False)
        op.create_index(op.f("ix_project_mail_project_id"), "project_mail", ["project_id"], unique=False)
        op.create_index(op.f("ix_project_mail_tenant_id"), "project_mail", ["tenant_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "project_mail" in table_names:
        op.drop_index(op.f("ix_project_mail_tenant_id"), table_name="project_mail")
        op.drop_index(op.f("ix_project_mail_project_id"), table_name="project_mail")
        op.drop_index(op.f("ix_project_mail_mail_no"), table_name="project_mail")
        op.drop_index(op.f("ix_project_mail_document_id"), table_name="project_mail")
        op.drop_table("project_mail")
    if "document_reviews" in table_names:
        op.drop_index(op.f("ix_document_reviews_tenant_id"), table_name="document_reviews")
        op.drop_index(op.f("ix_document_reviews_project_id"), table_name="document_reviews")
        op.drop_index(op.f("ix_document_reviews_document_id"), table_name="document_reviews")
        op.drop_table("document_reviews")
    if "document_transmittal_items" in table_names:
        op.drop_index(op.f("ix_document_transmittal_items_transmittal_id"), table_name="document_transmittal_items")
        op.drop_index(op.f("ix_document_transmittal_items_tenant_id"), table_name="document_transmittal_items")
        op.drop_index(op.f("ix_document_transmittal_items_project_id"), table_name="document_transmittal_items")
        op.drop_index(op.f("ix_document_transmittal_items_document_id"), table_name="document_transmittal_items")
        op.drop_table("document_transmittal_items")
    if "document_transmittals" in table_names:
        op.drop_index(op.f("ix_document_transmittals_transmittal_no"), table_name="document_transmittals")
        op.drop_index(op.f("ix_document_transmittals_tenant_id"), table_name="document_transmittals")
        op.drop_index(op.f("ix_document_transmittals_project_id"), table_name="document_transmittals")
        op.drop_table("document_transmittals")

    if "documents" in table_names:
        if _has_index(inspector, "documents", "ix_documents_document_number"):
            op.drop_index(op.f("ix_documents_document_number"), table_name="documents")
        existing_columns = {column["name"] for column in inspector.get_columns("documents")}
        for column_name, _column in reversed(DOCUMENT_COLUMNS):
            if column_name in existing_columns:
                op.drop_column("documents", column_name)


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))
