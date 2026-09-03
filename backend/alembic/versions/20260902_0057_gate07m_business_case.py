"""add Gate 07M-BC governed Business Case lifecycle

Revision ID: 20260902_0057
Revises: 20260901_0056
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0057"
down_revision: str | None = "20260901_0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "business_cases" not in tables:
        op.create_table(
            "business_cases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("business_case_number", sa.String(40), nullable=False),
            sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
            sa.Column("source_project_proposal_id", sa.Integer(), sa.ForeignKey("project_proposals.id")),
            sa.Column("owning_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
            sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("sponsor_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id")),
            sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
            sa.Column("current_revision_id", sa.Integer()),
            sa.Column("material_change_review_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False),
            sa.Column("configuration_revision", sa.Integer(), nullable=False),
            sa.Column("configuration_hash", sa.String(64), nullable=False),
            sa.Column("configuration_source_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id")),
            sa.Column("configuration_resolution_chain_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("create_idempotency_key", sa.String(160)),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint("tenant_id", "business_case_number", name="uq_business_case_number"),
            sa.UniqueConstraint("tenant_id", "project_workspace_id", name="uq_business_case_project"),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_business_case_create_key"),
            sa.CheckConstraint(
                "status IN ('DRAFT','ACTIVE','ON_HOLD','CLOSED','ARCHIVED')", name="ck_business_case_status"
            ),
        )
        for name, columns in (
            ("ix_business_cases_tenant_id", ["tenant_id"]),
            ("ix_business_cases_number", ["business_case_number"]),
            ("ix_business_cases_project", ["project_workspace_id"]),
            ("ix_business_cases_proposal", ["source_project_proposal_id"]),
            ("ix_business_cases_current_revision", ["current_revision_id"]),
            ("ix_business_case_queue", ["tenant_id", "status", "updated_at"]),
        ):
            op.create_index(name, "business_cases", columns)

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "business_case_revisions" not in tables:
        op.create_table(
            "business_case_revisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("business_case_id", sa.Integer(), sa.ForeignKey("business_cases.id"), nullable=False),
            sa.Column("revision_number", sa.Integer(), nullable=False),
            sa.Column("revision_label", sa.String(20), nullable=False),
            sa.Column("purpose", sa.String(48), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
            sa.Column("as_of_date", sa.DateTime(), nullable=False),
            sa.Column("fel_stage_code", sa.String(32)),
            sa.Column("title", sa.String(240), nullable=False),
            sa.Column("executive_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("business_need", sa.Text(), nullable=False, server_default=""),
            sa.Column("strategic_alignment_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("objectives_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("scope_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("alternatives_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("benefits_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("assumptions_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("constraints_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("delivery_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("unresolved_concerns_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("recommendation_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("source_references_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("source_hashes_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("source_snapshot_hash", sa.String(64), nullable=False),
            sa.Column("economic_financial_model_id", sa.Integer()),
            sa.Column("economic_financial_model_version", sa.Integer()),
            sa.Column("economic_financial_model_hash", sa.String(64)),
            sa.Column("financial_model_status", sa.String(24), nullable=False, server_default="NOT_AVAILABLE"),
            sa.Column("economic_financial_readiness", sa.String(32)),
            sa.Column("economic_financial_as_of_date", sa.DateTime()),
            sa.Column("npv", sa.Numeric(20, 4)),
            sa.Column("irr", sa.Numeric(12, 6)),
            sa.Column("payback_period", sa.Numeric(12, 4)),
            sa.Column("benefit_cost_ratio", sa.Numeric(12, 6)),
            sa.Column("readiness_status", sa.String(20), nullable=False, server_default="NOT_STARTED"),
            sa.Column("readiness_warnings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("readiness_blockers_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("readiness_hash", sa.String(64), nullable=False),
            sa.Column("material_change_status", sa.String(40), nullable=False, server_default="NO_MATERIAL_CHANGE"),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("preparer_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("reviewer_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id")),
            sa.Column("submitted_at", sa.DateTime()),
            sa.Column("completed_at", sa.DateTime()),
            sa.Column("completed_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
            sa.Column("create_idempotency_key", sa.String(160)),
            sa.Column("complete_idempotency_key", sa.String(160)),
            sa.Column("refresh_idempotency_key", sa.String(160)),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint("tenant_id", "business_case_id", "revision_number", name="uq_business_case_revision"),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_business_case_revision_create_key"),
            sa.UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_business_case_revision_complete_key"),
            sa.UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_business_case_revision_refresh_key"),
            sa.CheckConstraint("revision_number > 0", name="ck_business_case_revision_number"),
            sa.CheckConstraint(
                "status IN ('DRAFT','IN_REVIEW','COMPLETED','SUPERSEDED','VOIDED')",
                name="ck_business_case_revision_status",
            ),
            sa.CheckConstraint(
                "purpose IN ('INITIAL_PROPOSAL','FEL_1_UPDATE','FEL_2_UPDATE','INVESTMENT_SELECTION_UPDATE',"
                "'FEL_3_UPDATE','FFA_UPDATE','MATERIAL_CHANGE_UPDATE','REVALIDATION','OTHER')",
                name="ck_business_case_revision_purpose",
            ),
            sa.CheckConstraint(
                "readiness_status IN ('NOT_STARTED','READY','BLOCKED','STALE','EXPIRED')",
                name="ck_business_case_revision_readiness",
            ),
            sa.CheckConstraint(
                "material_change_status IN ('NO_MATERIAL_CHANGE','MATERIAL_CHANGE_REVIEW_REQUIRED')",
                name="ck_business_case_material_change",
            ),
            sa.CheckConstraint(
                "financial_model_status IN ('NOT_AVAILABLE','AVAILABLE','STALE')",
                name="ck_business_case_financial_status",
            ),
        )
        for name, columns in (
            ("ix_business_case_revisions_tenant", ["tenant_id"]),
            ("ix_business_case_revisions_case", ["business_case_id"]),
            ("ix_business_case_revisions_purpose", ["purpose"]),
            ("ix_business_case_revisions_status", ["status"]),
            ("ix_business_case_revisions_as_of", ["as_of_date"]),
            ("ix_business_case_revisions_fel_stage", ["fel_stage_code"]),
            ("ix_business_case_revisions_source_hash", ["source_snapshot_hash"]),
            ("ix_business_case_revisions_financial_model", ["economic_financial_model_id"]),
            ("ix_business_case_revisions_financial_hash", ["economic_financial_model_hash"]),
            ("ix_business_case_revisions_readiness", ["readiness_status"]),
            ("ix_business_case_revision_latest", ["tenant_id", "business_case_id", "revision_number"]),
        ):
            op.create_index(name, "business_case_revisions", columns)
        op.create_foreign_key(
            "fk_business_cases_current_revision",
            "business_cases",
            "business_case_revisions",
            ["current_revision_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "business_case_decision_snapshots" not in tables:
        op.create_table(
            "business_case_decision_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("business_case_id", sa.Integer(), sa.ForeignKey("business_cases.id"), nullable=False),
            sa.Column(
                "business_case_revision_id", sa.Integer(), sa.ForeignKey("business_case_revisions.id"), nullable=False
            ),
            sa.Column("snapshot_type", sa.String(48), nullable=False),
            sa.Column("decision_reference_type", sa.String(80)),
            sa.Column("decision_reference_id", sa.Integer()),
            sa.Column("decision_reference_hash", sa.String(64)),
            sa.Column("revision_content_hash", sa.String(64), nullable=False),
            sa.Column("source_snapshot_hash", sa.String(64), nullable=False),
            sa.Column("snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("snapshot_hash", sa.String(64), nullable=False),
            sa.Column("idempotency_key", sa.String(160), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_business_case_snapshot_key"),
            sa.UniqueConstraint(
                "tenant_id",
                "business_case_revision_id",
                "snapshot_type",
                name="uq_business_case_revision_snapshot_type",
            ),
            sa.CheckConstraint(
                "snapshot_type IN ('INVESTMENT_SELECTION','FULL_FUNDS_AUTHORIZATION','OTHER_CONFIGURED_GATE')",
                name="ck_business_case_snapshot_type",
            ),
        )
        for name, columns in (
            ("ix_business_case_snapshots_tenant", ["tenant_id"]),
            ("ix_business_case_snapshots_case", ["business_case_id"]),
            ("ix_business_case_snapshots_revision", ["business_case_revision_id"]),
            ("ix_business_case_snapshots_type", ["snapshot_type"]),
            ("ix_business_case_snapshots_hash", ["snapshot_hash"]),
            ("ix_business_case_snapshot_history", ["tenant_id", "business_case_id", "created_at"]),
        ):
            op.create_index(name, "business_case_decision_snapshots", columns)


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "business_case_decision_snapshots" in tables:
        op.drop_table("business_case_decision_snapshots")
    if "business_cases" in tables and "business_case_revisions" in tables:
        op.drop_constraint("fk_business_cases_current_revision", "business_cases", type_="foreignkey")
    if "business_case_revisions" in tables:
        op.drop_table("business_case_revisions")
    if "business_cases" in tables:
        op.drop_table("business_cases")
