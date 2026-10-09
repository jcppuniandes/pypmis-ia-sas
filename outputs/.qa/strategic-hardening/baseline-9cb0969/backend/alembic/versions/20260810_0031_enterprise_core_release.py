"""add immutable enterprise CORE release publication

Revision ID: 20260810_0031
Revises: 20260809_0030
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0031"
down_revision: str | None = "20260809_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enterprise_core_releases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("release_code", sa.String(length=160), nullable=False),
        sa.Column("release_name", sa.String(length=220), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("canonical_hash", sa.String(length=64), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("source_release_code", sa.String(length=160), nullable=True),
        sa.Column("previous_release_id", sa.Integer(), nullable=True),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("workspace_count", sa.Integer(), nullable=False),
        sa.Column("objective_count", sa.Integer(), nullable=False),
        sa.Column("classification_count", sa.Integer(), nullable=False),
        sa.Column("link_count", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("published_by_user_id", sa.Integer(), nullable=False),
        sa.Column("unpublished_at", sa.DateTime(), nullable=True),
        sa.Column("unpublished_by_user_id", sa.Integer(), nullable=True),
        sa.Column("rollback_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["previous_release_id"], ["enterprise_core_releases.id"]),
        sa.ForeignKeyConstraint(["published_by_user_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["unpublished_by_user_id"], ["user_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "release_code", name="uq_enterprise_core_release_code"),
    )
    op.create_index("ix_enterprise_core_releases_tenant_id", "enterprise_core_releases", ["tenant_id"])
    op.create_index("ix_enterprise_core_releases_release_code", "enterprise_core_releases", ["release_code"])
    op.create_index("ix_enterprise_core_releases_state", "enterprise_core_releases", ["state"])
    op.create_index(
        "ix_enterprise_core_releases_content_fingerprint",
        "enterprise_core_releases",
        ["content_fingerprint"],
    )
    op.create_index(
        "ix_enterprise_core_releases_published_by_user_id",
        "enterprise_core_releases",
        ["published_by_user_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION protect_enterprise_core_release() RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Published CORE releases cannot be physically deleted';
              END IF;
              IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                OR NEW.release_code IS DISTINCT FROM OLD.release_code
                OR NEW.release_name IS DISTINCT FROM OLD.release_name
                OR NEW.source_hash IS DISTINCT FROM OLD.source_hash
                OR NEW.canonical_hash IS DISTINCT FROM OLD.canonical_hash
                OR NEW.content_fingerprint IS DISTINCT FROM OLD.content_fingerprint
                OR NEW.source_release_code IS DISTINCT FROM OLD.source_release_code
                OR NEW.previous_release_id IS DISTINCT FROM OLD.previous_release_id
                OR NEW.snapshot_json IS DISTINCT FROM OLD.snapshot_json
                OR NEW.workspace_count IS DISTINCT FROM OLD.workspace_count
                OR NEW.objective_count IS DISTINCT FROM OLD.objective_count
                OR NEW.classification_count IS DISTINCT FROM OLD.classification_count
                OR NEW.link_count IS DISTINCT FROM OLD.link_count
                OR NEW.published_at IS DISTINCT FROM OLD.published_at
                OR NEW.published_by_user_id IS DISTINCT FROM OLD.published_by_user_id
              THEN
                RAISE EXCEPTION 'Published CORE release immutable fields cannot change';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_protect_enterprise_core_release
            BEFORE UPDATE OR DELETE ON enterprise_core_releases
            FOR EACH ROW EXECUTE FUNCTION protect_enterprise_core_release();
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_protect_enterprise_core_release ON enterprise_core_releases")
        op.execute("DROP FUNCTION IF EXISTS protect_enterprise_core_release()")
    op.drop_table("enterprise_core_releases")
