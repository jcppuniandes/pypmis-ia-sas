"""add Gate 07J-RISK Project Risk and Risk Readiness

Revision ID: 20260830_0053
Revises: 20260830_0052
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0053"
down_revision: str | None = "20260830_0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "project_risks" not in tables:
        op.create_table(
            "project_risks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
            sa.Column("risk_number", sa.String(40), nullable=False),
            sa.Column("title", sa.String(240), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("risk_category", sa.String(60), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
            sa.Column("identified_date", sa.Date(), nullable=False),
            sa.Column("risk_owner_id", sa.Integer(), sa.ForeignKey("user_accounts.id")),
            sa.Column("cause", sa.Text(), nullable=False, server_default=""),
            sa.Column("event", sa.Text(), nullable=False, server_default=""),
            sa.Column("impact_description", sa.Text(), nullable=False, server_default=""),
            sa.Column("likelihood_before", sa.Integer()),
            sa.Column("impact_before", sa.Integer()),
            sa.Column("inherent_rating", sa.String(20)),
            sa.Column("treatment_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("treatment_strategy", sa.String(24)),
            sa.Column("treatment_description", sa.Text()),
            sa.Column("treatment_owner_id", sa.Integer(), sa.ForeignKey("user_accounts.id")),
            sa.Column("target_treatment_date", sa.Date()),
            sa.Column("treatment_status", sa.String(24)),
            sa.Column("likelihood_after", sa.Integer()),
            sa.Column("impact_after", sa.Integer()),
            sa.Column("residual_rating", sa.String(20)),
            sa.Column("residual_acceptance_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("accepted_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
            sa.Column("accepted_at", sa.DateTime()),
            sa.Column("acceptance_comment", sa.Text()),
            sa.Column("acceptance_authority_level", sa.String(80)),
            sa.Column("due_date", sa.Date()),
            sa.Column("source_reference", sa.String(300)),
            sa.Column("evidence_refs_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("create_idempotency_key", sa.String(160)),
            sa.Column("acceptance_idempotency_key", sa.String(160)),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint("tenant_id", "project_workspace_id", "risk_number", name="uq_project_risk_number"),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_project_risk_create_key"),
            sa.UniqueConstraint("tenant_id", "acceptance_idempotency_key", name="uq_project_risk_accept_key"),
            sa.CheckConstraint(
                "status IN ('DRAFT','OPEN','UNDER_TREATMENT','MONITORING','CLOSED','VOIDED')",
                name="ck_project_risk_status",
            ),
            sa.CheckConstraint(
                "treatment_strategy IS NULL OR treatment_strategy IN ('AVOID','REDUCE','TRANSFER','ACCEPT')",
                name="ck_project_risk_treatment_strategy",
            ),
            sa.CheckConstraint(
                "treatment_status IS NULL OR treatment_status IN ('OPEN','IN_PROGRESS','COMPLETED','CANCELLED')",
                name="ck_project_risk_treatment_status",
            ),
            sa.CheckConstraint(
                "likelihood_before IS NULL OR likelihood_before BETWEEN 1 AND 5",
                name="ck_project_risk_likelihood_before",
            ),
            sa.CheckConstraint(
                "impact_before IS NULL OR impact_before BETWEEN 1 AND 5", name="ck_project_risk_impact_before"
            ),
            sa.CheckConstraint(
                "likelihood_after IS NULL OR likelihood_after BETWEEN 1 AND 5", name="ck_project_risk_likelihood_after"
            ),
            sa.CheckConstraint(
                "impact_after IS NULL OR impact_after BETWEEN 1 AND 5", name="ck_project_risk_impact_after"
            ),
            sa.CheckConstraint(
                "(accepted_by IS NULL AND accepted_at IS NULL) OR (accepted_by IS NOT NULL AND accepted_at IS NOT NULL)",
                name="ck_project_risk_acceptance_pair",
            ),
        )
        for name, columns in (
            ("ix_project_risks_tenant_id", ["tenant_id"]),
            ("ix_project_risks_project_workspace_id", ["project_workspace_id"]),
            ("ix_project_risks_risk_category", ["risk_category"]),
            ("ix_project_risks_status", ["status"]),
            ("ix_project_risks_risk_owner_id", ["risk_owner_id"]),
            ("ix_project_risks_inherent_rating", ["inherent_rating"]),
            ("ix_project_risks_treatment_owner_id", ["treatment_owner_id"]),
            ("ix_project_risks_target_treatment_date", ["target_treatment_date"]),
            ("ix_project_risks_residual_rating", ["residual_rating"]),
            ("ix_project_risks_accepted_by", ["accepted_by"]),
            ("ix_project_risks_due_date", ["due_date"]),
            ("ix_project_risks_created_by", ["created_by"]),
            ("ix_project_risks_updated_by", ["updated_by"]),
            ("ix_project_risk_tenant_project_status", ["tenant_id", "project_workspace_id", "status"]),
            ("ix_project_risk_readiness_scan", ["tenant_id", "project_workspace_id", "inherent_rating"]),
        ):
            op.create_index(name, "project_risks", columns)

    if "risk_readiness_assessments" not in tables:
        op.create_table(
            "risk_readiness_assessments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
            sa.Column("assessment_number", sa.String(40), nullable=False),
            sa.Column("assessment_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("as_of_date", sa.DateTime(), nullable=False),
            sa.Column("valid_until", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="IN_PROGRESS"),
            sa.Column("risk_register_hash", sa.String(64), nullable=False),
            sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False),
            sa.Column("configuration_revision", sa.Integer(), nullable=False),
            sa.Column("configuration_hash", sa.String(64), nullable=False),
            sa.Column("total_active_risks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("high_risk_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("critical_risk_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("risks_without_owner", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("risks_without_treatment", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("overdue_treatments", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("residual_high_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("residual_critical_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("risks_requiring_acceptance", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("risks_without_acceptance", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("evidence_coverage_percent", sa.Float(), nullable=False, server_default="0"),
            sa.Column("warnings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("blockers_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("readiness_status", sa.String(16), nullable=False, server_default="BLOCKED"),
            sa.Column("risk_readiness_hash", sa.String(64)),
            sa.Column("assessed_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("completed_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
            sa.Column("completed_at", sa.DateTime()),
            sa.Column("create_idempotency_key", sa.String(160)),
            sa.Column("complete_idempotency_key", sa.String(160)),
            sa.Column("reassessment_idempotency_key", sa.String(160)),
            sa.Column("refresh_idempotency_key", sa.String(160)),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint("tenant_id", "assessment_number", name="uq_risk_readiness_assessment_number"),
            sa.UniqueConstraint(
                "tenant_id", "project_workspace_id", "assessment_version", name="uq_risk_readiness_project_version"
            ),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_risk_readiness_create_key"),
            sa.UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_risk_readiness_complete_key"),
            sa.UniqueConstraint("tenant_id", "reassessment_idempotency_key", name="uq_risk_readiness_reassess_key"),
            sa.UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_risk_readiness_refresh_key"),
            sa.CheckConstraint(
                "status IN ('DRAFT','IN_PROGRESS','COMPLETED','SUPERSEDED','VOIDED')",
                name="ck_risk_readiness_assessment_status",
            ),
            sa.CheckConstraint(
                "readiness_status IN ('NOT_STARTED','READY','BLOCKED','STALE','EXPIRED')",
                name="ck_risk_readiness_status",
            ),
            sa.CheckConstraint(
                "status != 'COMPLETED' OR (completed_by IS NOT NULL AND completed_at IS NOT NULL AND risk_readiness_hash IS NOT NULL)",
                name="ck_risk_readiness_completed",
            ),
            sa.CheckConstraint(
                "evidence_coverage_percent >= 0 AND evidence_coverage_percent <= 100", name="ck_risk_readiness_coverage"
            ),
        )
        for name, columns in (
            ("ix_risk_readiness_assessments_tenant_id", ["tenant_id"]),
            ("ix_risk_readiness_assessments_project_workspace_id", ["project_workspace_id"]),
            ("ix_risk_readiness_assessments_valid_until", ["valid_until"]),
            ("ix_risk_readiness_assessments_status", ["status"]),
            ("ix_risk_readiness_assessments_risk_register_hash", ["risk_register_hash"]),
            ("ix_risk_readiness_assessments_configuration_id", ["configuration_id"]),
            ("ix_risk_readiness_assessments_configuration_hash", ["configuration_hash"]),
            ("ix_risk_readiness_assessments_readiness_status", ["readiness_status"]),
            ("ix_risk_readiness_assessments_risk_readiness_hash", ["risk_readiness_hash"]),
            ("ix_risk_readiness_assessments_assessed_by", ["assessed_by"]),
            ("ix_risk_readiness_assessments_completed_by", ["completed_by"]),
            ("ix_risk_readiness_tenant_project_status", ["tenant_id", "project_workspace_id", "status"]),
        ):
            op.create_index(name, "risk_readiness_assessments", columns)
        op.create_index(
            "uq_risk_readiness_active_project",
            "risk_readiness_assessments",
            ["tenant_id", "project_workspace_id"],
            unique=True,
            postgresql_where=sa.text("status IN ('DRAFT','IN_PROGRESS')"),
        )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "risk_readiness_assessments" in tables:
        op.drop_table("risk_readiness_assessments")
    if "project_risks" in tables:
        op.drop_table("project_risks")
