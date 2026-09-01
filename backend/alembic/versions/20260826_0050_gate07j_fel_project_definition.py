"""add Gate 07J-FEL Project Definition and maturity

Revision ID: 20260826_0050
Revises: 20260826_0049
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_0050"
down_revision: str | None = "20260826_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "project_definition_assessments" in inspector.get_table_names():
        return
    op.create_table(
        "project_definition_assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("assessment_number", sa.String(120), nullable=False),
        sa.Column("assessment_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("framework_config_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False),
        sa.Column("framework_code", sa.String(120), nullable=False),
        sa.Column("framework_type", sa.String(40), nullable=False),
        sa.Column("framework_version", sa.String(80), nullable=False),
        sa.Column("framework_hash", sa.String(64), nullable=False),
        sa.Column("fel_stage_code", sa.String(40), nullable=False),
        sa.Column("assessment_date", sa.DateTime(), nullable=False),
        sa.Column("as_of_date", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("raw_score", sa.Float()),
        sa.Column("normalized_score", sa.Float()),
        sa.Column("maturity_level", sa.String(80)),
        sa.Column("threshold_status", sa.String(32), nullable=False, server_default="NOT_EVALUATED"),
        sa.Column("category_results_json", sa.JSON(), nullable=False),
        sa.Column("element_results_json", sa.JSON(), nullable=False),
        sa.Column("blocking_items_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("actions_summary_json", sa.JSON(), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("source_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("definition_source_hash", sa.String(64), nullable=False),
        sa.Column("assessed_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("completed_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("assessment_hash", sa.String(64)),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(160)),
        sa.Column("complete_idempotency_key", sa.String(160)),
        sa.Column("reevaluate_idempotency_key", sa.String(160)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "assessment_number", name="uq_project_definition_assessment_number"),
        sa.UniqueConstraint(
            "tenant_id", "project_workspace_id", "assessment_version", name="uq_project_definition_assessment_version"
        ),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_project_definition_assessment_create_key"),
        sa.UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_project_definition_assessment_complete_key"),
        sa.UniqueConstraint("tenant_id", "reevaluate_idempotency_key", name="uq_project_definition_assessment_reevaluate_key"),
        sa.CheckConstraint(
            "status IN ('DRAFT','IN_PROGRESS','COMPLETED','SUPERSEDED','VOIDED')",
            name="ck_project_definition_assessment_status",
        ),
        sa.CheckConstraint(
            "framework_type IN ('CUSTOM','PDRI_COMPATIBLE','FEL_INDEX_COMPATIBLE')",
            name="ck_project_definition_framework_type",
        ),
        sa.CheckConstraint(
            "threshold_status IN ('NOT_EVALUATED','BELOW_REQUIRED','MEETS_REQUIRED','EXCEEDS_REQUIRED')",
            name="ck_project_definition_threshold_status",
        ),
    )
    _indexes(
        "project_definition_assessments",
        (
            ("ix_project_definition_assessments_tenant_id", ["tenant_id"]),
            ("ix_project_definition_assessments_project_workspace_id", ["project_workspace_id"]),
            ("ix_project_definition_assessments_assessment_number", ["assessment_number"]),
            ("ix_project_definition_assessments_framework_config_id", ["framework_config_id"]),
            ("ix_project_definition_assessments_framework_code", ["framework_code"]),
            ("ix_project_definition_assessments_framework_hash", ["framework_hash"]),
            ("ix_project_definition_assessments_fel_stage_code", ["fel_stage_code"]),
            ("ix_project_definition_assessments_status", ["status"]),
            ("ix_project_definition_assessments_definition_source_hash", ["definition_source_hash"]),
            ("ix_project_definition_assessments_assessed_by", ["assessed_by"]),
            ("ix_project_definition_assessments_completed_by", ["completed_by"]),
            ("ix_project_definition_assessments_assessment_hash", ["assessment_hash"]),
            ("ix_project_definition_assessment_lookup", ["tenant_id", "project_workspace_id", "fel_stage_code"]),
            ("ix_project_definition_assessment_history", ["tenant_id", "project_workspace_id", "assessment_date"]),
        ),
    )

    op.create_table(
        "project_fel_statuses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("current_stage_code", sa.String(40), nullable=False, server_default="FEL-1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="NOT_STARTED"),
        sa.Column("stage_started_at", sa.DateTime()),
        sa.Column("target_stage_exit_date", sa.DateTime()),
        sa.Column("effective_framework_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False),
        sa.Column("effective_framework_revision", sa.Integer(), nullable=False),
        sa.Column("effective_framework_hash", sa.String(64), nullable=False),
        sa.Column("current_assessment_id", sa.Integer(), sa.ForeignKey("project_definition_assessments.id")),
        sa.Column("latest_completed_assessment_id", sa.Integer(), sa.ForeignKey("project_definition_assessments.id")),
        sa.Column("readiness_status", sa.String(24), nullable=False, server_default="NOT_STARTED"),
        sa.Column("definition_source_hash", sa.String(64), nullable=False),
        sa.Column("review_submitted_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("review_submitted_at", sa.DateTime()),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("start_idempotency_key", sa.String(160)),
        sa.Column("submit_idempotency_key", sa.String(160)),
        sa.Column("complete_stage_idempotency_key", sa.String(160)),
        sa.Column("return_stage_idempotency_key", sa.String(160)),
        sa.Column("refresh_idempotency_key", sa.String(160)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "project_workspace_id", name="uq_project_fel_status_project"),
        sa.UniqueConstraint("tenant_id", "start_idempotency_key", name="uq_project_fel_start_key"),
        sa.UniqueConstraint("tenant_id", "submit_idempotency_key", name="uq_project_fel_submit_key"),
        sa.UniqueConstraint("tenant_id", "complete_stage_idempotency_key", name="uq_project_fel_complete_stage_key"),
        sa.UniqueConstraint("tenant_id", "return_stage_idempotency_key", name="uq_project_fel_return_stage_key"),
        sa.UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_project_fel_refresh_key"),
        sa.CheckConstraint(
            "status IN ('NOT_STARTED','IN_STAGE','READY_FOR_STAGE_REVIEW','STAGE_COMPLETED','BLOCKED')",
            name="ck_project_fel_status_lifecycle",
        ),
        sa.CheckConstraint(
            "readiness_status IN ('READY','BLOCKED','STALE','NOT_STARTED')",
            name="ck_project_fel_readiness_status",
        ),
    )
    _indexes(
        "project_fel_statuses",
        (
            ("ix_project_fel_statuses_tenant_id", ["tenant_id"]),
            ("ix_project_fel_statuses_project_workspace_id", ["project_workspace_id"]),
            ("ix_project_fel_statuses_current_stage_code", ["current_stage_code"]),
            ("ix_project_fel_statuses_status", ["status"]),
            ("ix_project_fel_statuses_effective_framework_id", ["effective_framework_id"]),
            ("ix_project_fel_statuses_effective_framework_hash", ["effective_framework_hash"]),
            ("ix_project_fel_statuses_current_assessment_id", ["current_assessment_id"]),
            ("ix_project_fel_statuses_latest_completed_assessment_id", ["latest_completed_assessment_id"]),
            ("ix_project_fel_statuses_readiness_status", ["readiness_status"]),
            ("ix_project_fel_statuses_definition_source_hash", ["definition_source_hash"]),
            ("ix_project_fel_statuses_created_by", ["created_by"]),
            ("ix_project_fel_statuses_updated_by", ["updated_by"]),
            ("ix_project_fel_tenant_stage", ["tenant_id", "current_stage_code", "status"]),
        ),
    )

    op.create_table(
        "project_definition_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("project_definition_assessments.id"), nullable=False),
        sa.Column("element_key", sa.String(160), nullable=False),
        sa.Column("title", sa.String(220), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("target_date", sa.DateTime()),
        sa.Column("status", sa.String(24), nullable=False, server_default="OPEN"),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("audit_json", sa.JSON(), nullable=False),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(160)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_project_definition_action_create_key"),
        sa.CheckConstraint(
            "status IN ('OPEN','IN_PROGRESS','RESOLVED','ACCEPTED_RISK','CANCELLED')",
            name="ck_project_definition_action_status",
        ),
    )
    _indexes(
        "project_definition_actions",
        (
            ("ix_project_definition_actions_tenant_id", ["tenant_id"]),
            ("ix_project_definition_actions_project_workspace_id", ["project_workspace_id"]),
            ("ix_project_definition_actions_assessment_id", ["assessment_id"]),
            ("ix_project_definition_actions_element_key", ["element_key"]),
            ("ix_project_definition_actions_owner_id", ["owner_id"]),
            ("ix_project_definition_actions_status", ["status"]),
            ("ix_project_definition_action_lookup", ["tenant_id", "project_workspace_id", "status"]),
        ),
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "project_definition_actions" in tables:
        op.drop_table("project_definition_actions")
    if "project_fel_statuses" in tables:
        op.drop_table("project_fel_statuses")
    if "project_definition_assessments" in tables:
        op.drop_table("project_definition_assessments")


def _indexes(table: str, definitions: tuple[tuple[str, list[str]], ...]) -> None:
    for name, columns in definitions:
        op.create_index(name, table, columns)
