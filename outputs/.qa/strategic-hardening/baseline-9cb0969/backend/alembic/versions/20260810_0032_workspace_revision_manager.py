"""add governed workspace structure revisions

Revision ID: 20260810_0032
Revises: 20260810_0031
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0032"
down_revision: str | None = "20260810_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_protect_enterprise_core_release ON enterprise_core_releases")
        op.execute("DROP FUNCTION IF EXISTS protect_enterprise_core_release()")

    op.add_column(
        "enterprise_core_releases",
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "enterprise_core_releases",
        sa.Column("base_content_fingerprint", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "enterprise_core_releases",
        sa.Column("validation_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("enterprise_core_releases", sa.Column("validated_at", sa.DateTime(), nullable=True))
    op.add_column("enterprise_core_releases", sa.Column("validated_by_user_id", sa.Integer(), nullable=True))
    op.add_column("enterprise_core_releases", sa.Column("validated_draft_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "enterprise_core_releases",
        sa.Column("diff_hash", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column("enterprise_core_releases", sa.Column("approved_at", sa.DateTime(), nullable=True))
    op.add_column("enterprise_core_releases", sa.Column("approved_by_user_id", sa.Integer(), nullable=True))
    op.add_column("enterprise_core_releases", sa.Column("approved_draft_hash", sa.String(length=64), nullable=True))
    op.add_column("enterprise_core_releases", sa.Column("approved_diff_hash", sa.String(length=64), nullable=True))
    op.add_column("enterprise_core_releases", sa.Column("created_at", sa.DateTime(), nullable=True))
    op.add_column("enterprise_core_releases", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
    op.add_column("enterprise_core_releases", sa.Column("updated_at", sa.DateTime(), nullable=True))

    op.execute(
        """
        UPDATE enterprise_core_releases
        SET revision_number = id,
            base_content_fingerprint = content_fingerprint,
            validation_json = '{"valid": true, "errors": [], "conflicts": []}',
            diff_hash = '',
            created_at = published_at,
            created_by_user_id = published_by_user_id,
            updated_at = published_at
        """
    )
    op.alter_column("enterprise_core_releases", "created_at", nullable=False)
    op.alter_column("enterprise_core_releases", "created_by_user_id", nullable=False)
    op.alter_column("enterprise_core_releases", "updated_at", nullable=False)
    op.alter_column("enterprise_core_releases", "published_at", existing_type=sa.DateTime(), nullable=True)
    op.alter_column("enterprise_core_releases", "published_by_user_id", existing_type=sa.Integer(), nullable=True)

    op.create_foreign_key(
        "fk_enterprise_core_release_validated_by",
        "enterprise_core_releases",
        "user_accounts",
        ["validated_by_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_enterprise_core_release_approved_by",
        "enterprise_core_releases",
        "user_accounts",
        ["approved_by_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_enterprise_core_release_created_by",
        "enterprise_core_releases",
        "user_accounts",
        ["created_by_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_enterprise_core_releases_created_by_user_id",
        "enterprise_core_releases",
        ["created_by_user_id"],
    )

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION protect_enterprise_core_release() RETURNS trigger AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'CORE releases cannot be physically deleted';
              END IF;
              IF OLD.state <> 'draft' AND (
                NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                OR NEW.release_code IS DISTINCT FROM OLD.release_code
                OR NEW.release_name IS DISTINCT FROM OLD.release_name
                OR NEW.revision_number IS DISTINCT FROM OLD.revision_number
                OR NEW.source_hash IS DISTINCT FROM OLD.source_hash
                OR NEW.canonical_hash IS DISTINCT FROM OLD.canonical_hash
                OR NEW.content_fingerprint IS DISTINCT FROM OLD.content_fingerprint
                OR NEW.source_release_code IS DISTINCT FROM OLD.source_release_code
                OR NEW.previous_release_id IS DISTINCT FROM OLD.previous_release_id
                OR NEW.base_content_fingerprint IS DISTINCT FROM OLD.base_content_fingerprint
                OR NEW.snapshot_json IS DISTINCT FROM OLD.snapshot_json
                OR NEW.workspace_count IS DISTINCT FROM OLD.workspace_count
                OR NEW.objective_count IS DISTINCT FROM OLD.objective_count
                OR NEW.classification_count IS DISTINCT FROM OLD.classification_count
                OR NEW.link_count IS DISTINCT FROM OLD.link_count
                OR NEW.created_at IS DISTINCT FROM OLD.created_at
                OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
                OR NEW.published_at IS DISTINCT FROM OLD.published_at
                OR NEW.published_by_user_id IS DISTINCT FROM OLD.published_by_user_id
              ) THEN
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
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_protect_enterprise_core_release ON enterprise_core_releases")
        op.execute("DROP FUNCTION IF EXISTS protect_enterprise_core_release()")

    op.drop_index("ix_enterprise_core_releases_created_by_user_id", table_name="enterprise_core_releases")
    op.drop_constraint("fk_enterprise_core_release_created_by", "enterprise_core_releases", type_="foreignkey")
    op.drop_constraint("fk_enterprise_core_release_approved_by", "enterprise_core_releases", type_="foreignkey")
    op.drop_constraint("fk_enterprise_core_release_validated_by", "enterprise_core_releases", type_="foreignkey")
    op.alter_column("enterprise_core_releases", "published_by_user_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("enterprise_core_releases", "published_at", existing_type=sa.DateTime(), nullable=False)
    for column in (
        "updated_at",
        "created_by_user_id",
        "created_at",
        "approved_diff_hash",
        "approved_draft_hash",
        "approved_by_user_id",
        "approved_at",
        "diff_hash",
        "validated_draft_hash",
        "validated_by_user_id",
        "validated_at",
        "validation_json",
        "base_content_fingerprint",
        "revision_number",
    ):
        op.drop_column("enterprise_core_releases", column)
