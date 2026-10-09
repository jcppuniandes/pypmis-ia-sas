"""add multi-source Project governance fields

Revision ID: 20260820_0044
Revises: 20260820_0043
Create Date: 2026-08-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0044"
down_revision: str | None = "20260820_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = {item["name"] for item in inspector.get_columns("project_creation_requests")}
    additions = (
        ("governance_model", sa.String(40)),
        ("source_context_id", sa.Integer()),
        ("source_external_key", sa.String(160)),
        ("idempotency_key", sa.String(160)),
        ("source_snapshot_json", sa.JSON()),
        ("source_hash", sa.String(64)),
        ("creation_policy_id", sa.Integer()),
        ("creation_policy_revision", sa.Integer()),
        ("creation_policy_hash", sa.String(64)),
    )
    for name, column_type in additions:
        if name not in columns:
            op.add_column("project_creation_requests", sa.Column(name, column_type, nullable=True))

    connection.execute(
        sa.text(
            "UPDATE project_creation_requests "
            "SET governance_model = 'CAPITAL_OWNER', "
            "source_context_id = strategic_gate_decision_id "
            "WHERE source_context_type = 'STRATEGIC_GATE_DECISION' "
            "AND strategic_gate_decision_id IS NOT NULL"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE project_creation_requests "
            "SET source_snapshot_json = COALESCE(strategic_source_snapshot_json, '{}') "
            "WHERE source_snapshot_json IS NULL"
        )
    )
    if connection.dialect.name != "sqlite":
        op.alter_column("project_creation_requests", "source_snapshot_json", nullable=False)

    if connection.dialect.name != "sqlite":
        foreign_keys = {
            item.get("name") for item in sa.inspect(connection).get_foreign_keys("project_creation_requests")
        }
        if "fk_pcr_creation_policy" not in foreign_keys:
            op.create_foreign_key(
                "fk_pcr_creation_policy",
                "project_creation_requests",
                "admin_configurations",
                ["creation_policy_id"],
                ["id"],
            )

    indexes = {item["name"] for item in sa.inspect(connection).get_indexes("project_creation_requests")}
    for name, columns_ in (
        ("ix_pcr_governance_model", ["governance_model"]),
        ("ix_pcr_source_context_id", ["source_context_id"]),
        ("ix_pcr_source_external_key", ["source_external_key"]),
        ("ix_pcr_idempotency_key", ["idempotency_key"]),
        ("ix_pcr_creation_policy_id", ["creation_policy_id"]),
    ):
        if name not in indexes:
            op.create_index(name, "project_creation_requests", columns_)

    if "uq_pcr_source_context_identity" not in indexes:
        op.create_index(
            "uq_pcr_source_context_identity",
            "project_creation_requests",
            ["tenant_id", "source_context_type", "source_context_id"],
            unique=True,
            postgresql_where=sa.text("source_context_id IS NOT NULL AND state NOT IN ('cancelled', 'rejected')"),
            sqlite_where=sa.text("source_context_id IS NOT NULL AND state NOT IN ('cancelled', 'rejected')"),
        )
    if "uq_pcr_source_external_identity" not in indexes:
        op.create_index(
            "uq_pcr_source_external_identity",
            "project_creation_requests",
            ["tenant_id", "source_context_type", "source_external_key"],
            unique=True,
            postgresql_where=sa.text("source_external_key IS NOT NULL AND state NOT IN ('cancelled', 'rejected')"),
            sqlite_where=sa.text("source_external_key IS NOT NULL AND state NOT IN ('cancelled', 'rejected')"),
        )
    if "uq_pcr_direct_idempotency" not in indexes:
        op.create_index(
            "uq_pcr_direct_idempotency",
            "project_creation_requests",
            ["tenant_id", "idempotency_key"],
            unique=True,
            postgresql_where=sa.text("idempotency_key IS NOT NULL AND state NOT IN ('cancelled', 'rejected')"),
            sqlite_where=sa.text("idempotency_key IS NOT NULL AND state NOT IN ('cancelled', 'rejected')"),
        )


def downgrade() -> None:
    connection = op.get_bind()
    indexes = {item["name"] for item in sa.inspect(connection).get_indexes("project_creation_requests")}
    for name in (
        "uq_pcr_direct_idempotency",
        "uq_pcr_source_external_identity",
        "uq_pcr_source_context_identity",
        "ix_pcr_creation_policy_id",
        "ix_pcr_idempotency_key",
        "ix_pcr_source_external_key",
        "ix_pcr_source_context_id",
        "ix_pcr_governance_model",
    ):
        if name in indexes:
            op.drop_index(name, table_name="project_creation_requests")
    if connection.dialect.name != "sqlite":
        foreign_keys = {
            item.get("name") for item in sa.inspect(connection).get_foreign_keys("project_creation_requests")
        }
        if "fk_pcr_creation_policy" in foreign_keys:
            op.drop_constraint("fk_pcr_creation_policy", "project_creation_requests", type_="foreignkey")
    columns = {item["name"] for item in sa.inspect(connection).get_columns("project_creation_requests")}
    for name in (
        "creation_policy_hash",
        "creation_policy_revision",
        "creation_policy_id",
        "source_hash",
        "source_snapshot_json",
        "idempotency_key",
        "source_external_key",
        "source_context_id",
        "governance_model",
    ):
        if name in columns:
            op.drop_column("project_creation_requests", name)
