"""source commitments from contracts and purchase orders

Revision ID: 20260506_0006
Revises: 20260506_0005
Create Date: 2026-05-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260506_0006"
down_revision: str | None = "20260506_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "contracts" in table_names:
        contract_columns = {column["name"] for column in inspector.get_columns("contracts")}
        if "control_account_id" not in contract_columns:
            op.add_column("contracts", sa.Column("control_account_id", sa.Integer(), nullable=True))
            op.create_index(op.f("ix_contracts_control_account_id"), "contracts", ["control_account_id"], unique=False)
            op.create_foreign_key(
                "fk_contracts_control_account_id_control_accounts",
                "contracts",
                "control_accounts",
                ["control_account_id"],
                ["id"],
            )

    if "purchase_orders" not in table_names:
        op.create_table(
            "purchase_orders",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("control_account_id", sa.Integer(), nullable=True),
            sa.Column("contract_id", sa.Integer(), nullable=True),
            sa.Column("po_number", sa.String(length=120), nullable=False),
            sa.Column("description", sa.String(length=260), nullable=False, server_default=""),
            sa.Column("vendor", sa.String(length=180), nullable=False, server_default=""),
            sa.Column("committed_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="issued"),
            sa.Column("issued_on", sa.Date(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
            sa.ForeignKeyConstraint(["control_account_id"], ["control_accounts.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "project_id", "po_number"),
        )
        op.create_index(op.f("ix_purchase_orders_contract_id"), "purchase_orders", ["contract_id"], unique=False)
        op.create_index(op.f("ix_purchase_orders_control_account_id"), "purchase_orders", ["control_account_id"], unique=False)
        op.create_index(op.f("ix_purchase_orders_po_number"), "purchase_orders", ["po_number"], unique=False)
        op.create_index(op.f("ix_purchase_orders_project_id"), "purchase_orders", ["project_id"], unique=False)
        op.create_index(op.f("ix_purchase_orders_tenant_id"), "purchase_orders", ["tenant_id"], unique=False)

    if "cost_records" in table_names:
        op.execute("UPDATE cost_records SET source = 'invoice' WHERE source = 'commitment'")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "purchase_orders" in table_names:
        op.drop_index(op.f("ix_purchase_orders_tenant_id"), table_name="purchase_orders")
        op.drop_index(op.f("ix_purchase_orders_project_id"), table_name="purchase_orders")
        op.drop_index(op.f("ix_purchase_orders_po_number"), table_name="purchase_orders")
        op.drop_index(op.f("ix_purchase_orders_control_account_id"), table_name="purchase_orders")
        op.drop_index(op.f("ix_purchase_orders_contract_id"), table_name="purchase_orders")
        op.drop_table("purchase_orders")

    if "contracts" in table_names:
        contract_columns = {column["name"] for column in inspector.get_columns("contracts")}
        if "control_account_id" in contract_columns:
            op.drop_constraint("fk_contracts_control_account_id_control_accounts", "contracts", type_="foreignkey")
            op.drop_index(op.f("ix_contracts_control_account_id"), table_name="contracts")
            op.drop_column("contracts", "control_account_id")
