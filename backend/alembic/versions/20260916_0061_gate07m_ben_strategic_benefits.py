"""add Gate 07M-BEN strategic benefits plans and stable benefits

Revision ID: 20260916_0061
Revises: 20260915_0060
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_0061"
down_revision: str | None = "20260915_0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if "strategic_benefits_plans" not in existing:
        op.create_table(
            "strategic_benefits_plans",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("project_workspace_id", sa.Integer(), nullable=False),
            sa.Column("plan_number", sa.String(40), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("current_version_id", sa.Integer(), nullable=True),
            sa.Column("configuration_id", sa.Integer(), nullable=False),
            sa.Column("configuration_revision", sa.Integer(), nullable=False),
            sa.Column("configuration_hash", sa.String(64), nullable=False),
            sa.Column("configuration_source_workspace_id", sa.Integer(), nullable=True),
            sa.Column("configuration_resolution_chain_json", sa.JSON(), nullable=False),
            sa.Column("create_idempotency_key", sa.String(160), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["project_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["configuration_id"], ["admin_configurations.id"]),
            sa.ForeignKeyConstraint(["configuration_source_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["updated_by"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "project_workspace_id", name="uq_benefits_plan_project"),
            sa.UniqueConstraint("tenant_id", "plan_number", name="uq_benefits_plan_number"),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_benefits_plan_create_key"),
            sa.CheckConstraint(
                "status IN ('DRAFT','IN_REVIEW','COMPLETED','SUPERSEDED','VOIDED')",
                name="ck_benefits_plan_status",
            ),
        )
        for column in (
            "tenant_id",
            "project_workspace_id",
            "plan_number",
            "status",
            "current_version_id",
            "configuration_id",
            "configuration_hash",
            "configuration_source_workspace_id",
            "created_by",
            "updated_by",
            "updated_at",
        ):
            op.create_index(op.f(f"ix_strategic_benefits_plans_{column}"), "strategic_benefits_plans", [column])
        op.create_index(
            "ix_benefits_plan_queue",
            "strategic_benefits_plans",
            ["tenant_id", "status", "updated_at", "id"],
        )

    existing = set(sa.inspect(bind).get_table_names())
    if "strategic_benefits_plan_versions" not in existing:
        op.create_table(
            "strategic_benefits_plan_versions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("benefits_plan_id", sa.Integer(), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("version_purpose", sa.String(48), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("fel_stage_code", sa.String(32), nullable=True),
            sa.Column("overview_json", sa.JSON(), nullable=False),
            sa.Column("outputs_json", sa.JSON(), nullable=False),
            sa.Column("outcomes_json", sa.JSON(), nullable=False),
            sa.Column("assumptions_json", sa.JSON(), nullable=False),
            sa.Column("constraints_json", sa.JSON(), nullable=False),
            sa.Column("readiness_json", sa.JSON(), nullable=False),
            sa.Column("readiness_status", sa.String(24), nullable=False),
            sa.Column("readiness_warnings_json", sa.JSON(), nullable=False),
            sa.Column("readiness_blockers_json", sa.JSON(), nullable=False),
            sa.Column("source_references_json", sa.JSON(), nullable=False),
            sa.Column("source_hashes_json", sa.JSON(), nullable=False),
            sa.Column("source_bundle_hash", sa.String(64), nullable=False),
            sa.Column("source_current", sa.Boolean(), nullable=False),
            sa.Column("configuration_id", sa.Integer(), nullable=False),
            sa.Column("configuration_revision", sa.Integer(), nullable=False),
            sa.Column("configuration_hash", sa.String(64), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("benefit_set_hash", sa.String(64), nullable=False),
            sa.Column("traceability_hash", sa.String(64), nullable=False),
            sa.Column("benefits_plan_hash", sa.String(64), nullable=False),
            sa.Column("preparer_user_id", sa.Integer(), nullable=False),
            sa.Column("reviewer_user_id", sa.Integer(), nullable=True),
            sa.Column("return_reason", sa.Text(), nullable=True),
            sa.Column("void_reason", sa.Text(), nullable=True),
            sa.Column("create_idempotency_key", sa.String(160), nullable=True),
            sa.Column("submit_idempotency_key", sa.String(160), nullable=True),
            sa.Column("review_idempotency_key", sa.String(160), nullable=True),
            sa.Column("return_idempotency_key", sa.String(160), nullable=True),
            sa.Column("complete_idempotency_key", sa.String(160), nullable=True),
            sa.Column("void_idempotency_key", sa.String(160), nullable=True),
            sa.Column("refresh_idempotency_key", sa.String(160), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
            sa.Column("review_started_at", sa.DateTime(), nullable=True),
            sa.Column("returned_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("completed_by", sa.Integer(), nullable=True),
            sa.Column("voided_at", sa.DateTime(), nullable=True),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["benefits_plan_id"], ["strategic_benefits_plans.id"]),
            sa.ForeignKeyConstraint(["configuration_id"], ["admin_configurations.id"]),
            sa.ForeignKeyConstraint(["preparer_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["reviewer_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["updated_by"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["completed_by"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "benefits_plan_id", "version_number", name="uq_benefits_plan_version"),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_benefits_version_create_key"),
            sa.UniqueConstraint("tenant_id", "submit_idempotency_key", name="uq_benefits_version_submit_key"),
            sa.UniqueConstraint("tenant_id", "review_idempotency_key", name="uq_benefits_version_review_key"),
            sa.UniqueConstraint("tenant_id", "return_idempotency_key", name="uq_benefits_version_return_key"),
            sa.UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_benefits_version_complete_key"),
            sa.UniqueConstraint("tenant_id", "void_idempotency_key", name="uq_benefits_version_void_key"),
            sa.UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_benefits_version_refresh_key"),
            sa.CheckConstraint("version_number > 0", name="ck_benefits_version_number"),
            sa.CheckConstraint(
                "status IN ('DRAFT','IN_REVIEW','COMPLETED','SUPERSEDED','VOIDED')",
                name="ck_benefits_version_status",
            ),
            sa.CheckConstraint(
                "readiness_status IN ('NOT_STARTED','IN_PROGRESS','READY','BLOCKED','STALE','NOT_APPLICABLE')",
                name="ck_benefits_version_readiness",
            ),
        )
        for column in (
            "tenant_id",
            "benefits_plan_id",
            "version_purpose",
            "status",
            "fel_stage_code",
            "readiness_status",
            "source_bundle_hash",
            "source_current",
            "configuration_id",
            "configuration_hash",
            "content_hash",
            "benefit_set_hash",
            "traceability_hash",
            "benefits_plan_hash",
            "preparer_user_id",
            "reviewer_user_id",
            "created_by",
            "updated_by",
            "updated_at",
            "completed_by",
        ):
            op.create_index(
                op.f(f"ix_strategic_benefits_plan_versions_{column}"),
                "strategic_benefits_plan_versions",
                [column],
            )
        op.create_index(
            "ix_benefits_version_history",
            "strategic_benefits_plan_versions",
            ["tenant_id", "benefits_plan_id", "version_number"],
        )

    existing = set(sa.inspect(bind).get_table_names())
    if "strategic_benefits" not in existing:
        op.create_table(
            "strategic_benefits",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("benefits_plan_id", sa.Integer(), nullable=False),
            sa.Column("benefit_number", sa.String(40), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("create_idempotency_key", sa.String(160), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["benefits_plan_id"], ["strategic_benefits_plans.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["updated_by"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "benefit_number", name="uq_strategic_benefit_number"),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_strategic_benefit_create_key"),
            sa.CheckConstraint("status IN ('ACTIVE','RETIRED')", name="ck_strategic_benefit_status"),
        )
        for column in ("tenant_id", "benefits_plan_id", "benefit_number", "status", "created_by", "updated_by"):
            op.create_index(op.f(f"ix_strategic_benefits_{column}"), "strategic_benefits", [column])
        op.create_index(
            "ix_strategic_benefit_plan", "strategic_benefits", ["tenant_id", "benefits_plan_id", "id"]
        )

    existing = set(sa.inspect(bind).get_table_names())
    if "strategic_benefit_version_snapshots" not in existing:
        op.create_table(
            "strategic_benefit_version_snapshots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("plan_version_id", sa.Integer(), nullable=False),
            sa.Column("strategic_benefit_id", sa.Integer(), nullable=False),
            sa.Column("benefit_name", sa.String(240), nullable=False),
            sa.Column("benefit_description", sa.Text(), nullable=False),
            sa.Column("benefit_direction", sa.String(24), nullable=False),
            sa.Column("benefit_type", sa.String(80), nullable=False),
            sa.Column("benefit_category", sa.String(120), nullable=True),
            sa.Column("strategic_objective_refs_json", sa.JSON(), nullable=False),
            sa.Column("source_need_reference_json", sa.JSON(), nullable=False),
            sa.Column("source_business_analysis_reference_json", sa.JSON(), nullable=False),
            sa.Column("source_project_proposal_reference_json", sa.JSON(), nullable=False),
            sa.Column("source_business_case_reference_json", sa.JSON(), nullable=False),
            sa.Column("expected_outputs_json", sa.JSON(), nullable=False),
            sa.Column("expected_outcomes_json", sa.JSON(), nullable=False),
            sa.Column("benefit_statement", sa.Text(), nullable=False),
            sa.Column("owner_type", sa.String(32), nullable=True),
            sa.Column("owner_user_id", sa.Integer(), nullable=True),
            sa.Column("owner_organization_unit_id", sa.Integer(), nullable=True),
            sa.Column("owner_security_role_id", sa.Integer(), nullable=True),
            sa.Column("owner_reference", sa.String(180), nullable=True),
            sa.Column("owner_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("owner_effective_from", sa.Date(), nullable=True),
            sa.Column("owner_effective_to", sa.Date(), nullable=True),
            sa.Column("accountability_statement", sa.Text(), nullable=False),
            sa.Column("owner_acceptance_status", sa.String(32), nullable=True),
            sa.Column("expected_value_json", sa.JSON(), nullable=False),
            sa.Column("monetizable_flag", sa.Boolean(), nullable=False),
            sa.Column("dependencies_json", sa.JSON(), nullable=False),
            sa.Column("assumptions_json", sa.JSON(), nullable=False),
            sa.Column("constraints_json", sa.JSON(), nullable=False),
            sa.Column("risk_references_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("snapshot_hash", sa.String(64), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["plan_version_id"], ["strategic_benefits_plan_versions.id"]),
            sa.ForeignKeyConstraint(["strategic_benefit_id"], ["strategic_benefits.id"]),
            sa.ForeignKeyConstraint(["owner_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["owner_organization_unit_id"], ["organization_units.id"]),
            sa.ForeignKeyConstraint(["owner_security_role_id"], ["security_roles.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["updated_by"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id", "plan_version_id", "strategic_benefit_id", name="uq_benefit_snapshot"
            ),
            sa.CheckConstraint("benefit_direction IN ('BENEFIT','DISBENEFIT')", name="ck_benefit_direction"),
            sa.CheckConstraint("status IN ('ACTIVE','REMOVED')", name="ck_benefit_snapshot_status"),
            sa.CheckConstraint(
                "owner_type IS NULL OR owner_type IN "
                "('USER','ORGANIZATION_UNIT','SECURITY_ROLE','EXTERNAL_REFERENCE')",
                name="ck_benefit_owner_type",
            ),
        )
        for column in (
            "tenant_id",
            "plan_version_id",
            "strategic_benefit_id",
            "benefit_type",
            "benefit_category",
            "owner_type",
            "owner_user_id",
            "owner_organization_unit_id",
            "owner_security_role_id",
            "status",
            "snapshot_hash",
            "created_by",
            "updated_by",
        ):
            op.create_index(
                op.f(f"ix_strategic_benefit_version_snapshots_{column}"),
                "strategic_benefit_version_snapshots",
                [column],
            )
        op.create_index(
            "ix_benefit_snapshot_matrix",
            "strategic_benefit_version_snapshots",
            ["tenant_id", "plan_version_id", "status", "id"],
        )

    existing = set(sa.inspect(bind).get_table_names())
    if "strategic_benefit_measures" not in existing:
        op.create_table(
            "strategic_benefit_measures",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("benefit_snapshot_id", sa.Integer(), nullable=False),
            sa.Column("measure_code", sa.String(80), nullable=False),
            sa.Column("measure_name", sa.String(180), nullable=False),
            sa.Column("definition", sa.Text(), nullable=False),
            sa.Column("unit_of_measure", sa.String(80), nullable=False),
            sa.Column("direction", sa.String(32), nullable=False),
            sa.Column("is_primary", sa.Boolean(), nullable=False),
            sa.Column("baseline_status", sa.String(16), nullable=False),
            sa.Column("baseline_value_json", sa.JSON(), nullable=True),
            sa.Column("baseline_as_of_date", sa.Date(), nullable=True),
            sa.Column("baseline_source", sa.String(240), nullable=True),
            sa.Column("baseline_evidence_reference", sa.String(500), nullable=True),
            sa.Column("baseline_confidence", sa.String(40), nullable=True),
            sa.Column("target_value_json", sa.JSON(), nullable=True),
            sa.Column("target_date", sa.Date(), nullable=True),
            sa.Column("target_basis", sa.Text(), nullable=True),
            sa.Column("tolerance_json", sa.JSON(), nullable=False),
            sa.Column("measurement_method", sa.Text(), nullable=False),
            sa.Column("measurement_frequency", sa.String(80), nullable=True),
            sa.Column("data_source_description", sa.Text(), nullable=True),
            sa.Column("measurement_owner_reference_json", sa.JSON(), nullable=False),
            sa.Column("measure_hash", sa.String(64), nullable=False),
            sa.Column("create_idempotency_key", sa.String(160), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["benefit_snapshot_id"], ["strategic_benefit_version_snapshots.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["updated_by"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id", "benefit_snapshot_id", "measure_code", name="uq_benefit_measure_code"
            ),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_benefit_measure_create_key"),
            sa.CheckConstraint(
                "direction IN ('INCREASE','DECREASE','MAINTAIN_ABOVE','MAINTAIN_BELOW','BINARY_ACHIEVEMENT')",
                name="ck_benefit_measure_direction",
            ),
            sa.CheckConstraint("baseline_status IN ('KNOWN','UNKNOWN')", name="ck_benefit_baseline_status"),
        )
        for column in (
            "tenant_id",
            "benefit_snapshot_id",
            "is_primary",
            "measure_hash",
            "created_by",
            "updated_by",
        ):
            op.create_index(
                op.f(f"ix_strategic_benefit_measures_{column}"), "strategic_benefit_measures", [column]
            )
        op.create_index(
            "ix_benefit_measure_snapshot",
            "strategic_benefit_measures",
            ["tenant_id", "benefit_snapshot_id", "is_primary", "id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for table_name in (
        "strategic_benefit_measures",
        "strategic_benefit_version_snapshots",
        "strategic_benefits",
        "strategic_benefits_plan_versions",
        "strategic_benefits_plans",
    ):
        if table_name in existing:
            op.drop_table(table_name)
