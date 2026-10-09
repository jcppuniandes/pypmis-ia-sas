"""add governed Business Analysis and Project Proposal lineage

Revision ID: 20260910_0059
Revises: 20260902_0058
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260910_0059"
down_revision: str | None = "20260902_0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "business_analyses" not in tables:
        op.create_table(
            "business_analyses",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("analysis_number", sa.String(40), nullable=False),
            sa.Column("source_idea_id", sa.Integer(), nullable=False),
            sa.Column("source_idea_evaluation_id", sa.Integer(), nullable=False),
            sa.Column("owning_workspace_id", sa.Integer(), nullable=False),
            sa.Column("supersedes_analysis_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(40), nullable=False),
            sa.Column("title", sa.String(220), nullable=False),
            sa.Column("content_json", sa.JSON(), nullable=False),
            sa.Column("recommended_option_id", sa.String(80), nullable=True),
            sa.Column("readiness_json", sa.JSON(), nullable=False),
            sa.Column("source_idea_hash", sa.String(64), nullable=False),
            sa.Column("configuration_id", sa.Integer(), nullable=False),
            sa.Column("configuration_revision", sa.Integer(), nullable=False),
            sa.Column("configuration_hash", sa.String(64), nullable=False),
            sa.Column("review_json", sa.JSON(), nullable=False),
            sa.Column("completion_hash", sa.String(64), nullable=False),
            sa.Column("idempotency_key", sa.String(120), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_by_user_id", sa.Integer(), nullable=False),
            sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
            sa.Column("reviewer_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
            sa.Column("review_started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("returned_at", sa.DateTime(), nullable=True),
            sa.Column("voided_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["source_idea_id"], ["ideas.id"]),
            sa.ForeignKeyConstraint(["source_idea_evaluation_id"], ["idea_evaluations.id"]),
            sa.ForeignKeyConstraint(["owning_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["supersedes_analysis_id"], ["business_analyses.id"]),
            sa.ForeignKeyConstraint(["configuration_id"], ["admin_configurations.id"]),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["reviewer_user_id"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint(
                "status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED','COMPLETED','SUPERSEDED','VOIDED')",
                name="ck_business_analysis_status",
            ),
            sa.UniqueConstraint("tenant_id", "analysis_number", name="uq_business_analysis_tenant_number"),
            sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_business_analysis_idempotency"),
        )
        for column in (
            "tenant_id",
            "analysis_number",
            "source_idea_id",
            "source_idea_evaluation_id",
            "owning_workspace_id",
            "supersedes_analysis_id",
            "status",
            "configuration_id",
            "created_by_user_id",
            "updated_by_user_id",
            "reviewer_user_id",
        ):
            op.create_index(op.f(f"ix_business_analyses_{column}"), "business_analyses", [column])
        op.create_index(
            "uq_business_analysis_active_idea",
            "business_analyses",
            ["tenant_id", "source_idea_id"],
            unique=True,
            postgresql_where=sa.text("status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED')"),
            sqlite_where=sa.text("status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED')"),
        )

    tables = set(sa.inspect(bind).get_table_names())
    if "business_analysis_revisions" not in tables:
        op.create_table(
            "business_analysis_revisions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("business_analysis_id", sa.Integer(), nullable=False),
            sa.Column("revision_number", sa.Integer(), nullable=False),
            sa.Column("lifecycle_status", sa.String(40), nullable=False),
            sa.Column("source_idea_hash", sa.String(64), nullable=False),
            sa.Column("configuration_hash", sa.String(64), nullable=False),
            sa.Column("content_json", sa.JSON(), nullable=False),
            sa.Column("readiness_json", sa.JSON(), nullable=False),
            sa.Column("snapshot_hash", sa.String(64), nullable=False),
            sa.Column("actor_user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["business_analysis_id"], ["business_analyses.id"]),
            sa.ForeignKeyConstraint(["actor_user_id"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id",
                "business_analysis_id",
                "revision_number",
                name="uq_business_analysis_revision_number",
            ),
        )
        for column in ("tenant_id", "business_analysis_id", "actor_user_id"):
            op.create_index(
                op.f(f"ix_business_analysis_revisions_{column}"),
                "business_analysis_revisions",
                [column],
            )

    proposal_columns = {item["name"] for item in sa.inspect(bind).get_columns("project_proposals")}
    additions = {
        "source_business_analysis_id": sa.Column("source_business_analysis_id", sa.Integer(), nullable=True),
        "source_business_analysis_hash": sa.Column("source_business_analysis_hash", sa.String(64), nullable=True),
        "business_analysis_configuration_id": sa.Column(
            "business_analysis_configuration_id", sa.Integer(), nullable=True
        ),
        "business_analysis_configuration_revision": sa.Column(
            "business_analysis_configuration_revision", sa.Integer(), nullable=True
        ),
        "business_analysis_configuration_hash": sa.Column(
            "business_analysis_configuration_hash", sa.String(64), nullable=True
        ),
    }
    for name, column in additions.items():
        if name not in proposal_columns:
            op.add_column("project_proposals", column)
    if bind.dialect.name != "sqlite":
        foreign_keys = {item.get("name") for item in sa.inspect(bind).get_foreign_keys("project_proposals")}
        if "fk_project_proposals_business_analysis" not in foreign_keys:
            op.create_foreign_key(
                "fk_project_proposals_business_analysis",
                "project_proposals",
                "business_analyses",
                ["source_business_analysis_id"],
                ["id"],
            )
        if "fk_project_proposals_business_analysis_configuration" not in foreign_keys:
            op.create_foreign_key(
                "fk_project_proposals_business_analysis_configuration",
                "project_proposals",
                "admin_configurations",
                ["business_analysis_configuration_id"],
                ["id"],
            )
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("project_proposals")}
    if "ix_project_proposals_source_business_analysis_id" not in indexes:
        op.create_index(
            "ix_project_proposals_source_business_analysis_id",
            "project_proposals",
            ["source_business_analysis_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "project_proposals" in tables:
        columns = {item["name"] for item in sa.inspect(bind).get_columns("project_proposals")}
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("project_proposals")}
        if "ix_project_proposals_source_business_analysis_id" in indexes:
            op.drop_index("ix_project_proposals_source_business_analysis_id", table_name="project_proposals")
        if bind.dialect.name != "sqlite":
            foreign_keys = {item.get("name") for item in sa.inspect(bind).get_foreign_keys("project_proposals")}
            for constraint in (
                "fk_project_proposals_business_analysis_configuration",
                "fk_project_proposals_business_analysis",
            ):
                if constraint in foreign_keys:
                    op.drop_constraint(constraint, "project_proposals", type_="foreignkey")
        for name in (
            "business_analysis_configuration_hash",
            "business_analysis_configuration_revision",
            "business_analysis_configuration_id",
            "source_business_analysis_hash",
            "source_business_analysis_id",
        ):
            if name in columns:
                op.drop_column("project_proposals", name)
    tables = set(sa.inspect(bind).get_table_names())
    if "business_analysis_revisions" in tables:
        op.drop_table("business_analysis_revisions")
    if "business_analyses" in tables:
        op.drop_table("business_analyses")
