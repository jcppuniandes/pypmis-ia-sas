"""harden workspace revision concurrency and actor traceability

Revision ID: 20260810_0033
Revises: 20260810_0032
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0033"
down_revision: str | None = "20260810_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_protect_enterprise_core_release ON enterprise_core_releases")
        op.execute("DROP FUNCTION IF EXISTS protect_enterprise_core_release()")

    op.add_column(
        "enterprise_core_releases",
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "enterprise_core_releases",
        sa.Column("last_modified_by_user_id", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE enterprise_core_releases "
        "SET last_modified_by_user_id = created_by_user_id "
        "WHERE last_modified_by_user_id IS NULL"
    )
    op.create_foreign_key(
        "fk_enterprise_core_release_last_modified_by",
        "enterprise_core_releases",
        "user_accounts",
        ["last_modified_by_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_enterprise_core_releases_last_modified_by_user_id",
        "enterprise_core_releases",
        ["last_modified_by_user_id"],
    )
    if bind.dialect.name == "postgresql":
        _create_release_protection_trigger(include_last_modified=True)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_protect_enterprise_core_release ON enterprise_core_releases")
        op.execute("DROP FUNCTION IF EXISTS protect_enterprise_core_release()")
    op.drop_index(
        "ix_enterprise_core_releases_last_modified_by_user_id",
        table_name="enterprise_core_releases",
    )
    op.drop_constraint(
        "fk_enterprise_core_release_last_modified_by",
        "enterprise_core_releases",
        type_="foreignkey",
    )
    op.drop_column("enterprise_core_releases", "last_modified_by_user_id")
    op.drop_column("enterprise_core_releases", "revision_version")
    if bind.dialect.name == "postgresql":
        _create_release_protection_trigger(include_last_modified=False)


def _create_release_protection_trigger(*, include_last_modified: bool) -> None:
    actor_guard = (
        "OR NEW.last_modified_by_user_id IS DISTINCT FROM OLD.last_modified_by_user_id" if include_last_modified else ""
    )
    op.execute(
        f"""
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
            OR NEW.snapshot_json::text IS DISTINCT FROM OLD.snapshot_json::text
            OR NEW.workspace_count IS DISTINCT FROM OLD.workspace_count
            OR NEW.objective_count IS DISTINCT FROM OLD.objective_count
            OR NEW.classification_count IS DISTINCT FROM OLD.classification_count
            OR NEW.link_count IS DISTINCT FROM OLD.link_count
            OR NEW.created_at IS DISTINCT FROM OLD.created_at
            OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
            {actor_guard}
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
