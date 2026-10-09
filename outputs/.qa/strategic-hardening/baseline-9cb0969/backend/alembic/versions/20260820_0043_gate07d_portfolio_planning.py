"""add Gate 07D portfolio planning stage entry

Revision ID: 20260820_0043
Revises: 20260813_0042
Create Date: 2026-08-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260820_0043"
down_revision: str | None = "20260813_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    request_columns = {item["name"] for item in inspector.get_columns("project_creation_requests")}
    columns = (
        ("source_context_type", sa.String(48)),
        ("strategic_gate_decision_id", sa.Integer()),
        ("source_project_proposal_id", sa.Integer()),
        ("source_idea_id", sa.Integer()),
        ("source_decision_hash", sa.String(64)),
        ("source_readiness_hash", sa.String(64)),
        ("strategic_target_portfolio_workspace_id", sa.Integer()),
        ("strategic_mapping_configuration_id", sa.Integer()),
        ("strategic_mapping_revision", sa.Integer()),
        ("strategic_mapping_hash", sa.String(64)),
        ("strategic_source_snapshot_json", sa.JSON()),
    )
    for name, column_type in columns:
        if name not in request_columns:
            op.add_column("project_creation_requests", sa.Column(name, column_type, nullable=True))
    foreign_keys = {item.get("name") for item in sa.inspect(connection).get_foreign_keys("project_creation_requests")}
    fk_specs = (
        ("fk_pcr_strategic_decision", "strategic_gate_decision_id", "strategic_gate_decisions"),
        ("fk_pcr_source_proposal", "source_project_proposal_id", "project_proposals"),
        ("fk_pcr_source_idea", "source_idea_id", "ideas"),
        ("fk_pcr_target_portfolio", "strategic_target_portfolio_workspace_id", "enterprise_workspaces"),
        ("fk_pcr_strategic_mapping", "strategic_mapping_configuration_id", "admin_configurations"),
    )
    if connection.dialect.name != "sqlite":
        for name, column, target in fk_specs:
            if name not in foreign_keys:
                op.create_foreign_key(name, "project_creation_requests", target, [column], ["id"])
    indexes = {item["name"] for item in sa.inspect(connection).get_indexes("project_creation_requests")}
    request_index_names = {
        "source_context_type": "ix_project_creation_requests_source_context_type",
        "strategic_gate_decision_id": "ix_project_creation_requests_strategic_gate_decision_id",
        "source_project_proposal_id": "ix_project_creation_requests_source_project_proposal_id",
        "source_idea_id": "ix_project_creation_requests_source_idea_id",
        "strategic_target_portfolio_workspace_id": "ix_pcr_strategic_target_portfolio",
        "strategic_mapping_configuration_id": "ix_pcr_strategic_mapping_config",
    }
    for column, name in request_index_names.items():
        if name not in indexes:
            op.create_index(name, "project_creation_requests", [column])
    if "uq_project_creation_strategic_decision" not in indexes:
        op.create_index(
            "uq_project_creation_strategic_decision",
            "project_creation_requests",
            ["tenant_id", "strategic_gate_decision_id"],
            unique=True,
        )
    connection.execute(
        sa.text(
            "UPDATE project_creation_requests SET strategic_source_snapshot_json = '{}' "
            "WHERE strategic_source_snapshot_json IS NULL"
        )
    )

    if "portfolio_project_memberships" not in tables:
        op.create_table(
            "portfolio_project_memberships",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("portfolio_workspace_id", sa.Integer(), nullable=False),
            sa.Column("project_workspace_id", sa.Integer(), nullable=False),
            sa.Column("membership_source", sa.String(40), nullable=False),
            sa.Column("source_strategic_gate_decision_id", sa.Integer(), nullable=True),
            sa.Column("source_project_proposal_id", sa.Integer(), nullable=True),
            sa.Column("is_target_portfolio", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("effective_from", sa.DateTime(), nullable=False),
            sa.Column("effective_to", sa.DateTime(), nullable=True),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["portfolio_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["project_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["source_strategic_gate_decision_id"], ["strategic_gate_decisions.id"]),
            sa.ForeignKeyConstraint(["source_project_proposal_id"], ["project_proposals.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["updated_by"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in (
            "tenant_id",
            "portfolio_workspace_id",
            "project_workspace_id",
            "membership_source",
            "source_strategic_gate_decision_id",
            "source_project_proposal_id",
            "is_target_portfolio",
            "status",
            "created_by",
            "updated_by",
        ):
            op.create_index(
                op.f(f"ix_portfolio_project_memberships_{column}"),
                "portfolio_project_memberships",
                [column],
            )
        op.create_index(
            "uq_portfolio_project_membership_active",
            "portfolio_project_memberships",
            ["tenant_id", "portfolio_workspace_id", "project_workspace_id"],
            unique=True,
            postgresql_where=sa.text("status = 'ACTIVE'"),
            sqlite_where=sa.text("status = 'ACTIVE'"),
        )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "portfolio_project_memberships" in set(inspector.get_table_names()):
        op.drop_table("portfolio_project_memberships")
    request_indexes = {item["name"] for item in sa.inspect(connection).get_indexes("project_creation_requests")}
    for index_name in (
        "uq_project_creation_strategic_decision",
        "ix_project_creation_requests_source_context_type",
        "ix_project_creation_requests_strategic_gate_decision_id",
        "ix_project_creation_requests_source_project_proposal_id",
        "ix_project_creation_requests_source_idea_id",
        "ix_pcr_strategic_target_portfolio",
        "ix_pcr_strategic_mapping_config",
    ):
        if index_name in request_indexes:
            op.drop_index(index_name, table_name="project_creation_requests")
    if connection.dialect.name != "sqlite":
        request_foreign_keys = {
            item.get("name") for item in sa.inspect(connection).get_foreign_keys("project_creation_requests")
        }
        for constraint_name in (
            "fk_pcr_strategic_decision",
            "fk_pcr_source_proposal",
            "fk_pcr_source_idea",
            "fk_pcr_target_portfolio",
            "fk_pcr_strategic_mapping",
        ):
            if constraint_name in request_foreign_keys:
                op.drop_constraint(
                    constraint_name,
                    "project_creation_requests",
                    type_="foreignkey",
                )
    columns = {item["name"] for item in sa.inspect(connection).get_columns("project_creation_requests")}
    for name in (
        "strategic_source_snapshot_json",
        "strategic_mapping_hash",
        "strategic_mapping_revision",
        "strategic_mapping_configuration_id",
        "strategic_target_portfolio_workspace_id",
        "source_readiness_hash",
        "source_decision_hash",
        "source_idea_id",
        "source_project_proposal_id",
        "strategic_gate_decision_id",
        "source_context_type",
    ):
        if name in columns:
            op.drop_column("project_creation_requests", name)
