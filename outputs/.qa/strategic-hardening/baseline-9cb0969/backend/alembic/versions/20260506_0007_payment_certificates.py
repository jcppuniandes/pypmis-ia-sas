"""add payment certificates as incurred cost source

Revision ID: 20260506_0007
Revises: 20260506_0006
Create Date: 2026-05-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260506_0007"
down_revision: str | None = "20260506_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "payment_certificates" not in table_names:
        op.create_table(
            "payment_certificates",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("control_account_id", sa.Integer(), nullable=True),
            sa.Column("contract_id", sa.Integer(), nullable=True),
            sa.Column("purchase_order_id", sa.Integer(), nullable=True),
            sa.Column("certificate_no", sa.String(length=120), nullable=False),
            sa.Column("period_label", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("certified_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("retained_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="certified"),
            sa.Column("certified_on", sa.Date(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
            sa.ForeignKeyConstraint(["control_account_id"], ["control_accounts.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "project_id", "certificate_no"),
        )
        op.create_index(op.f("ix_payment_certificates_certificate_no"), "payment_certificates", ["certificate_no"], unique=False)
        op.create_index(op.f("ix_payment_certificates_contract_id"), "payment_certificates", ["contract_id"], unique=False)
        op.create_index(op.f("ix_payment_certificates_control_account_id"), "payment_certificates", ["control_account_id"], unique=False)
        op.create_index(op.f("ix_payment_certificates_project_id"), "payment_certificates", ["project_id"], unique=False)
        op.create_index(op.f("ix_payment_certificates_purchase_order_id"), "payment_certificates", ["purchase_order_id"], unique=False)
        op.create_index(op.f("ix_payment_certificates_tenant_id"), "payment_certificates", ["tenant_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "payment_certificates" in set(inspector.get_table_names()):
        op.drop_index(op.f("ix_payment_certificates_tenant_id"), table_name="payment_certificates")
        op.drop_index(op.f("ix_payment_certificates_purchase_order_id"), table_name="payment_certificates")
        op.drop_index(op.f("ix_payment_certificates_project_id"), table_name="payment_certificates")
        op.drop_index(op.f("ix_payment_certificates_control_account_id"), table_name="payment_certificates")
        op.drop_index(op.f("ix_payment_certificates_contract_id"), table_name="payment_certificates")
        op.drop_index(op.f("ix_payment_certificates_certificate_no"), table_name="payment_certificates")
        op.drop_table("payment_certificates")
