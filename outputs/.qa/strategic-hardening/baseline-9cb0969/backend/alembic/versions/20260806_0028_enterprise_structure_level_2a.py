"""add enterprise classifications and cross-relations

Revision ID: 20260806_0028
Revises: 20260806_0027
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_0028"
down_revision: str | None = "20260806_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "enterprise_workspace_classifications" not in existing:
        op.create_table(
            "enterprise_workspace_classifications",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("workspace_id", sa.Integer(), nullable=False),
            sa.Column("category_set_code", sa.String(length=120), nullable=False),
            sa.Column("category_item_code", sa.String(length=120), nullable=False),
            sa.Column("created_by_user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["workspace_id"], ["enterprise_workspaces.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "workspace_id",
                "category_set_code",
                "category_item_code",
                name="uq_enterprise_workspace_classification",
            ),
        )
        for column in ("tenant_id", "workspace_id", "category_set_code", "category_item_code", "created_by_user_id"):
            op.create_index(
                op.f(f"ix_enterprise_workspace_classifications_{column}"),
                "enterprise_workspace_classifications",
                [column],
                unique=False,
            )
    if "enterprise_workspace_links" not in existing:
        op.create_table(
            "enterprise_workspace_links",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("source_workspace_id", sa.Integer(), nullable=False),
            sa.Column("target_workspace_id", sa.Integer(), nullable=False),
            sa.Column("relationship_type", sa.String(length=60), nullable=False),
            sa.Column("valid_from", sa.DateTime(), nullable=True),
            sa.Column("valid_to", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("created_by_user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["source_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["target_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "source_workspace_id",
                "target_workspace_id",
                "relationship_type",
                name="uq_enterprise_workspace_link",
            ),
        )
        for column in (
            "tenant_id",
            "source_workspace_id",
            "target_workspace_id",
            "relationship_type",
            "status",
            "created_by_user_id",
        ):
            op.create_index(
                op.f(f"ix_enterprise_workspace_links_{column}"),
                "enterprise_workspace_links",
                [column],
                unique=False,
            )


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "enterprise_workspace_links" in existing:
        op.drop_table("enterprise_workspace_links")
    if "enterprise_workspace_classifications" in existing:
        op.drop_table("enterprise_workspace_classifications")
