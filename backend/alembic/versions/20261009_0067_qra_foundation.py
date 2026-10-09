"""QRA source evidence / model definitions, and additive imported-source metadata.

Revision ID: 20261009_0067
Revises: 20261008_0066
No historical source or assessment rewrite. Metadata absent on existing imports.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261009_0067"
down_revision: str | None = "20261008_0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _aggregate(name, kind, final_status):
    columns = [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("number", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("predecessor_id", sa.Integer(), sa.ForeignKey(f"{name}.id")),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("comments", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False),
        sa.Column("configuration_revision", sa.Integer(), nullable=False),
        sa.Column("configuration_hash", sa.String(64), nullable=False),
        sa.Column("aggregate_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("snapshot_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("hash", sa.String(64)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
    ]
    if kind == "model":
        columns += [
            sa.Column("analysis_type", sa.String(40), nullable=False, server_default="COST_QRA"),
            sa.Column("model_number", sa.String(40), nullable=False),
            sa.Column("cost_source_assessment_id", sa.Integer(), sa.ForeignKey("qra_cost_source_assessments.id")),
            sa.Column(
                "schedule_source_assessment_id", sa.Integer(), sa.ForeignKey("qra_schedule_source_assessments.id")
            ),
            sa.CheckConstraint(
                "analysis_type IN ('COST_QRA','SCHEDULE_QRA','INTEGRATED_COST_SCHEDULE_QRA')",
                name="ck_qra_model_analysis_type",
            ),
            sa.UniqueConstraint("tenant_id", "model_number", "version", name="uq_qra_model_identity_version"),
        ]
    op.create_table(
        name,
        *columns,
        sa.UniqueConstraint("tenant_id", "number", name=f"uq_qra_{kind}_number"),
        sa.UniqueConstraint("tenant_id", "project_workspace_id", "version", name=f"uq_qra_{kind}_version"),
        sa.CheckConstraint(f"status IN ('DRAFT','IN_REVIEW','{final_status}')", name=f"ck_qra_{kind}_status"),
        sa.CheckConstraint("version > 0 AND revision_version > 0", name=f"ck_qra_{kind}_versions"),
        sa.CheckConstraint(
            f"status != '{final_status}' OR (hash IS NOT NULL AND completed_at IS NOT NULL AND approved_by IS NOT NULL AND reviewed_by IS NOT NULL)",
            name=f"ck_qra_{kind}_{'approved' if kind == 'model' else 'completed'}",
        ),
    )
    for column in ("tenant_id", "project_workspace_id"):
        op.create_index(f"ix_{name}_{column}", name, [column])
    op.create_index(f"ix_qra_{kind}_history", name, ["tenant_id", "project_workspace_id", "status", "version"])
    if kind == "model":
        op.create_index("ix_qra_model_definitions_model_number", name, ["model_number"])
        for column in ("cost_source_assessment_id", "schedule_source_assessment_id"):
            op.create_index(f"ix_{name}_{column}", name, [column])


def upgrade():
    op.add_column("schedule_imports", sa.Column("source_metadata", sa.JSON(), nullable=False, server_default="{}"))
    _aggregate("qra_cost_source_assessments", "cost", "COMPLETED")
    _aggregate("qra_schedule_source_assessments", "schedule", "COMPLETED")
    _aggregate("qra_model_definitions", "model", "APPROVED_FOR_ANALYSIS")
    op.create_table(
        "qra_commands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("command_type", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_qra_command_key"),
    )


def downgrade():
    op.drop_table("qra_commands")
    op.drop_table("qra_model_definitions")
    op.drop_table("qra_schedule_source_assessments")
    op.drop_table("qra_cost_source_assessments")
    op.drop_column("schedule_imports", "source_metadata")
