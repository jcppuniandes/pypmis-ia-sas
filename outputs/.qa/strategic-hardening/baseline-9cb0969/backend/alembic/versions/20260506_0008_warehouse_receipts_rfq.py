"""add warehouse receipts and rfq bid evaluation

Revision ID: 20260506_0008
Revises: 20260506_0007
Create Date: 2026-05-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260506_0008"
down_revision: str | None = "20260506_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "warehouse_receipts" not in table_names:
        op.create_table(
            "warehouse_receipts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("control_account_id", sa.Integer(), nullable=True),
            sa.Column("contract_id", sa.Integer(), nullable=True),
            sa.Column("purchase_order_id", sa.Integer(), nullable=True),
            sa.Column("receipt_no", sa.String(length=120), nullable=False),
            sa.Column("description", sa.String(length=260), nullable=False, server_default=""),
            sa.Column("received_quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("unit_cost", sa.Float(), nullable=False, server_default="0"),
            sa.Column("received_value", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="accepted"),
            sa.Column("received_on", sa.Date(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
            sa.ForeignKeyConstraint(["control_account_id"], ["control_accounts.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "project_id", "receipt_no"),
        )
        op.create_index(op.f("ix_warehouse_receipts_control_account_id"), "warehouse_receipts", ["control_account_id"], unique=False)
        op.create_index(op.f("ix_warehouse_receipts_contract_id"), "warehouse_receipts", ["contract_id"], unique=False)
        op.create_index(op.f("ix_warehouse_receipts_project_id"), "warehouse_receipts", ["project_id"], unique=False)
        op.create_index(op.f("ix_warehouse_receipts_purchase_order_id"), "warehouse_receipts", ["purchase_order_id"], unique=False)
        op.create_index(op.f("ix_warehouse_receipts_receipt_no"), "warehouse_receipts", ["receipt_no"], unique=False)
        op.create_index(op.f("ix_warehouse_receipts_tenant_id"), "warehouse_receipts", ["tenant_id"], unique=False)

    if "rfq_packages" not in table_names:
        op.create_table(
            "rfq_packages",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("control_account_id", sa.Integer(), nullable=True),
            sa.Column("package_no", sa.String(length=120), nullable=False),
            sa.Column("title", sa.String(length=220), nullable=False),
            sa.Column("scope_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("procurement_method", sa.String(length=80), nullable=False, server_default="RFQ"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
            sa.Column("budget_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("issue_date", sa.Date(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["control_account_id"], ["control_accounts.id"]),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "project_id", "package_no"),
        )
        op.create_index(op.f("ix_rfq_packages_control_account_id"), "rfq_packages", ["control_account_id"], unique=False)
        op.create_index(op.f("ix_rfq_packages_package_no"), "rfq_packages", ["package_no"], unique=False)
        op.create_index(op.f("ix_rfq_packages_project_id"), "rfq_packages", ["project_id"], unique=False)
        op.create_index(op.f("ix_rfq_packages_tenant_id"), "rfq_packages", ["tenant_id"], unique=False)

    if "rfq_bids" not in table_names:
        op.create_table(
            "rfq_bids",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("rfq_package_id", sa.Integer(), nullable=False),
            sa.Column("bidder_name", sa.String(length=180), nullable=False),
            sa.Column("bid_amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("technical_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("commercial_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("schedule_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("risk_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("weighted_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="received"),
            sa.Column("submitted_on", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.ForeignKeyConstraint(["rfq_package_id"], ["rfq_packages.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "project_id", "rfq_package_id", "bidder_name"),
        )
        op.create_index(op.f("ix_rfq_bids_project_id"), "rfq_bids", ["project_id"], unique=False)
        op.create_index(op.f("ix_rfq_bids_rfq_package_id"), "rfq_bids", ["rfq_package_id"], unique=False)
        op.create_index(op.f("ix_rfq_bids_tenant_id"), "rfq_bids", ["tenant_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "rfq_bids" in table_names:
        op.drop_index(op.f("ix_rfq_bids_tenant_id"), table_name="rfq_bids")
        op.drop_index(op.f("ix_rfq_bids_rfq_package_id"), table_name="rfq_bids")
        op.drop_index(op.f("ix_rfq_bids_project_id"), table_name="rfq_bids")
        op.drop_table("rfq_bids")

    if "rfq_packages" in table_names:
        op.drop_index(op.f("ix_rfq_packages_tenant_id"), table_name="rfq_packages")
        op.drop_index(op.f("ix_rfq_packages_project_id"), table_name="rfq_packages")
        op.drop_index(op.f("ix_rfq_packages_package_no"), table_name="rfq_packages")
        op.drop_index(op.f("ix_rfq_packages_control_account_id"), table_name="rfq_packages")
        op.drop_table("rfq_packages")

    if "warehouse_receipts" in table_names:
        op.drop_index(op.f("ix_warehouse_receipts_tenant_id"), table_name="warehouse_receipts")
        op.drop_index(op.f("ix_warehouse_receipts_receipt_no"), table_name="warehouse_receipts")
        op.drop_index(op.f("ix_warehouse_receipts_purchase_order_id"), table_name="warehouse_receipts")
        op.drop_index(op.f("ix_warehouse_receipts_project_id"), table_name="warehouse_receipts")
        op.drop_index(op.f("ix_warehouse_receipts_contract_id"), table_name="warehouse_receipts")
        op.drop_index(op.f("ix_warehouse_receipts_control_account_id"), table_name="warehouse_receipts")
        op.drop_table("warehouse_receipts")
