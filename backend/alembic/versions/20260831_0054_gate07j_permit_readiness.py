"""add Gate 07J-PERMIT Permit Register and Permit Readiness

Revision ID: 20260831_0054
Revises: 20260830_0053
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0054"
down_revision: str | None = "20260830_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "project_permits" not in tables:
        op.create_table(
            "project_permits",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column(
                "project_workspace_id",
                sa.Integer(),
                sa.ForeignKey("enterprise_workspaces.id"),
                nullable=False,
            ),
            sa.Column("permit_number", sa.String(40), nullable=False),
            sa.Column("permit_type_code", sa.String(80), nullable=False),
            sa.Column("requirement_key", sa.String(120)),
            sa.Column("title", sa.String(240), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("issuing_authority", sa.String(240), nullable=False, server_default=""),
            sa.Column("jurisdiction", sa.String(240)),
            sa.Column("status", sa.String(32), nullable=False, server_default="NOT_STARTED"),
            sa.Column("application_reference", sa.String(240)),
            sa.Column("application_date", sa.Date()),
            sa.Column("approval_date", sa.Date()),
            sa.Column("effective_from", sa.Date()),
            sa.Column("valid_until", sa.Date()),
            sa.Column("permit_identifier", sa.String(240)),
            sa.Column("evidence_refs_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("source_reference", sa.String(300)),
            sa.Column("responsible_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id")),
            sa.Column("next_action", sa.Text()),
            sa.Column("target_date", sa.Date()),
            sa.Column("renewal_of_permit_id", sa.Integer(), sa.ForeignKey("project_permits.id")),
            sa.Column("create_idempotency_key", sa.String(160)),
            sa.Column("status_idempotency_key", sa.String(160)),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint(
                "tenant_id",
                "project_workspace_id",
                "permit_number",
                name="uq_project_permit_number",
            ),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_project_permit_create_key"),
            sa.UniqueConstraint("tenant_id", "status_idempotency_key", name="uq_project_permit_status_key"),
            sa.CheckConstraint(
                "status IN ('NOT_STARTED','IN_PREPARATION','SUBMITTED','UNDER_REVIEW','APPROVED',"
                "'APPROVED_WITH_CONDITIONS','REJECTED','SUSPENDED','EXPIRED','CANCELLED','NOT_REQUIRED')",
                name="ck_project_permit_status",
            ),
            sa.CheckConstraint(
                "valid_until IS NULL OR effective_from IS NULL OR valid_until >= effective_from",
                name="ck_project_permit_validity",
            ),
            sa.CheckConstraint(
                "approval_date IS NULL OR application_date IS NULL OR approval_date >= application_date",
                name="ck_project_permit_approval_date",
            ),
            sa.CheckConstraint(
                "renewal_of_permit_id IS NULL OR renewal_of_permit_id != id",
                name="ck_permit_not_self_renewal",
            ),
        )
        for name, columns in (
            ("ix_project_permits_tenant_id", ["tenant_id"]),
            ("ix_project_permits_project_workspace_id", ["project_workspace_id"]),
            ("ix_project_permits_permit_type_code", ["permit_type_code"]),
            ("ix_project_permits_requirement_key", ["requirement_key"]),
            ("ix_project_permits_status", ["status"]),
            ("ix_project_permits_valid_until", ["valid_until"]),
            ("ix_project_permits_responsible_user_id", ["responsible_user_id"]),
            ("ix_project_permits_target_date", ["target_date"]),
            ("ix_project_permits_renewal_of_permit_id", ["renewal_of_permit_id"]),
            ("ix_project_permits_created_by", ["created_by"]),
            ("ix_project_permits_updated_by", ["updated_by"]),
            (
                "ix_project_permit_tenant_project_status",
                ["tenant_id", "project_workspace_id", "status"],
            ),
            (
                "ix_project_permit_readiness_scan",
                ["tenant_id", "project_workspace_id", "requirement_key", "valid_until"],
            ),
        ):
            op.create_index(name, "project_permits", columns)

    if "permit_conditions" not in tables:
        op.create_table(
            "permit_conditions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("permit_id", sa.Integer(), sa.ForeignKey("project_permits.id"), nullable=False),
            sa.Column("condition_key", sa.String(120), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("condition_type", sa.String(80), nullable=False, server_default="OTHER"),
            sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("user_accounts.id")),
            sa.Column("target_date", sa.Date()),
            sa.Column("status", sa.String(32), nullable=False, server_default="OPEN"),
            sa.Column("evidence_refs_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("source_reference", sa.String(300)),
            sa.Column("create_idempotency_key", sa.String(160)),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint("tenant_id", "permit_id", "condition_key", name="uq_permit_condition_key"),
            sa.UniqueConstraint(
                "tenant_id",
                "create_idempotency_key",
                name="uq_permit_condition_create_key",
            ),
            sa.CheckConstraint(
                "status IN ('OPEN','EVIDENCE_PROVIDED','SATISFIED','WAIVED','EXPIRED')",
                name="ck_permit_condition_status",
            ),
        )
        for name, columns in (
            ("ix_permit_conditions_tenant_id", ["tenant_id"]),
            ("ix_permit_conditions_permit_id", ["permit_id"]),
            ("ix_permit_conditions_blocking", ["blocking"]),
            ("ix_permit_conditions_owner_id", ["owner_id"]),
            ("ix_permit_conditions_target_date", ["target_date"]),
            ("ix_permit_conditions_status", ["status"]),
            ("ix_permit_conditions_created_by", ["created_by"]),
            ("ix_permit_conditions_updated_by", ["updated_by"]),
            ("ix_permit_condition_scan", ["tenant_id", "permit_id", "blocking", "status"]),
        ):
            op.create_index(name, "permit_conditions", columns)

    if "permit_readiness_assessments" not in tables:
        op.create_table(
            "permit_readiness_assessments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column(
                "project_workspace_id",
                sa.Integer(),
                sa.ForeignKey("enterprise_workspaces.id"),
                nullable=False,
            ),
            sa.Column("assessment_number", sa.String(40), nullable=False),
            sa.Column("assessment_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("as_of_date", sa.DateTime(), nullable=False),
            sa.Column("valid_until", sa.DateTime(), nullable=False),
            sa.Column("gate_profile_code", sa.String(80), nullable=False),
            sa.Column("project_type_code", sa.String(80), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="IN_PROGRESS"),
            sa.Column("requirement_set_hash", sa.String(64), nullable=False),
            sa.Column("permit_register_hash", sa.String(64), nullable=False),
            sa.Column("permit_source_hash", sa.String(64), nullable=False),
            sa.Column(
                "configuration_id",
                sa.Integer(),
                sa.ForeignKey("admin_configurations.id"),
                nullable=False,
            ),
            sa.Column("configuration_revision", sa.Integer(), nullable=False),
            sa.Column("configuration_hash", sa.String(64), nullable=False),
            sa.Column("required_permit_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("approved_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("approved_with_conditions_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("submitted_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("under_review_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("missing_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("suspended_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("expired_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("open_blocking_conditions_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("evidence_coverage_percent", sa.Float(), nullable=False, server_default="0"),
            sa.Column("warnings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("blockers_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("readiness_status", sa.String(16), nullable=False, server_default="BLOCKED"),
            sa.Column("permit_readiness_hash", sa.String(64)),
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
            sa.UniqueConstraint(
                "tenant_id",
                "assessment_number",
                name="uq_permit_readiness_assessment_number",
            ),
            sa.UniqueConstraint(
                "tenant_id",
                "project_workspace_id",
                "gate_profile_code",
                "assessment_version",
                name="uq_permit_readiness_project_profile_version",
            ),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_permit_readiness_create_key"),
            sa.UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_permit_readiness_complete_key"),
            sa.UniqueConstraint(
                "tenant_id",
                "reassessment_idempotency_key",
                name="uq_permit_readiness_reassess_key",
            ),
            sa.UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_permit_readiness_refresh_key"),
            sa.CheckConstraint(
                "status IN ('DRAFT','IN_PROGRESS','COMPLETED','SUPERSEDED','VOIDED')",
                name="ck_permit_readiness_assessment_status",
            ),
            sa.CheckConstraint(
                "readiness_status IN ('NOT_STARTED','READY','BLOCKED','STALE','EXPIRED')",
                name="ck_permit_readiness_status",
            ),
            sa.CheckConstraint(
                "status != 'COMPLETED' OR (completed_by IS NOT NULL AND completed_at IS NOT NULL "
                "AND permit_readiness_hash IS NOT NULL)",
                name="ck_permit_readiness_completed",
            ),
            sa.CheckConstraint(
                "evidence_coverage_percent >= 0 AND evidence_coverage_percent <= 100",
                name="ck_permit_readiness_coverage",
            ),
        )
        for name, columns in (
            ("ix_permit_readiness_assessments_tenant_id", ["tenant_id"]),
            ("ix_permit_readiness_assessments_project_workspace_id", ["project_workspace_id"]),
            ("ix_permit_readiness_assessments_valid_until", ["valid_until"]),
            ("ix_permit_readiness_assessments_gate_profile_code", ["gate_profile_code"]),
            ("ix_permit_readiness_assessments_project_type_code", ["project_type_code"]),
            ("ix_permit_readiness_assessments_status", ["status"]),
            ("ix_permit_readiness_assessments_requirement_set_hash", ["requirement_set_hash"]),
            ("ix_permit_readiness_assessments_permit_register_hash", ["permit_register_hash"]),
            ("ix_permit_readiness_assessments_permit_source_hash", ["permit_source_hash"]),
            ("ix_permit_readiness_assessments_configuration_id", ["configuration_id"]),
            ("ix_permit_readiness_assessments_configuration_hash", ["configuration_hash"]),
            ("ix_permit_readiness_assessments_readiness_status", ["readiness_status"]),
            ("ix_permit_readiness_assessments_permit_readiness_hash", ["permit_readiness_hash"]),
            ("ix_permit_readiness_assessments_assessed_by", ["assessed_by"]),
            ("ix_permit_readiness_assessments_completed_by", ["completed_by"]),
            (
                "ix_permit_readiness_tenant_project_status",
                ["tenant_id", "project_workspace_id", "status"],
            ),
        ):
            op.create_index(name, "permit_readiness_assessments", columns)
        op.create_index(
            "uq_permit_readiness_active_project_profile",
            "permit_readiness_assessments",
            ["tenant_id", "project_workspace_id", "gate_profile_code"],
            unique=True,
            postgresql_where=sa.text("status IN ('DRAFT','IN_PROGRESS')"),
        )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "permit_readiness_assessments" in tables:
        op.drop_table("permit_readiness_assessments")
    if "permit_conditions" in tables:
        op.drop_table("permit_conditions")
    if "project_permits" in tables:
        op.drop_table("project_permits")
