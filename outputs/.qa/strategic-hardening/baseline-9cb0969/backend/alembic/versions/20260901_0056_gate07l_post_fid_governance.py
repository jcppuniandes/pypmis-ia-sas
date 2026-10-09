"""add Gate 07L Post-FID Project Governance snapshots

Revision ID: 20260901_0056
Revises: 20260831_0055
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0056"
down_revision: str | None = "20260831_0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "post_fid_project_eligibilities" in tables:
        return
    op.create_table(
        "post_fid_project_eligibilities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "investment_decision_id", sa.Integer(), sa.ForeignKey("investment_decisions.id"), nullable=False
        ),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("eligibility_round", sa.Integer(), nullable=False),
        sa.Column("fid_decision_hash", sa.String(64), nullable=False),
        sa.Column("decision_package_hash", sa.String(64), nullable=False),
        sa.Column("project_state_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("condition_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("eligibility_status", sa.String(64), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("blockers_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("eligible_for_initialization", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("eligible_for_activation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.Column("evaluated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("source_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("eligibility_hash", sa.String(64), nullable=False),
        sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False),
        sa.Column("configuration_hash", sa.String(64), nullable=False),
        sa.Column("operation_type", sa.String(32), nullable=False, server_default="EVALUATE"),
        sa.Column("operation_key", sa.String(160), nullable=False),
        sa.Column("operation_payload_hash", sa.String(64), nullable=False),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "tenant_id",
            "investment_decision_id",
            "project_workspace_id",
            "eligibility_round",
            name="uq_post_fid_eligibility_round",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "investment_decision_id",
            "project_workspace_id",
            "operation_key",
            name="uq_post_fid_eligibility_operation",
        ),
        sa.CheckConstraint(
            "eligibility_status IN ("
            "'READY_FOR_PROJECT_WORKSPACE_INITIALIZATION',"
            "'READY_FOR_PROJECT_WORKSPACE_ACTIVATION',"
            "'POST_FID_PROJECT_GOVERNANCE_BLOCKED',"
            "'NO_REACTIVATION_REQUIRED','NOT_APPLICABLE','STALE')",
            name="ck_post_fid_eligibility_status",
        ),
        sa.CheckConstraint(
            "NOT (eligible_for_initialization AND eligible_for_activation)",
            name="ck_post_fid_single_handoff",
        ),
    )
    for name, columns in (
        ("ix_post_fid_project_eligibilities_tenant_id", ["tenant_id"]),
        ("ix_post_fid_project_eligibilities_decision_id", ["investment_decision_id"]),
        ("ix_post_fid_project_eligibilities_project_id", ["project_workspace_id"]),
        ("ix_post_fid_project_eligibilities_fid_hash", ["fid_decision_hash"]),
        ("ix_post_fid_project_eligibilities_package_hash", ["decision_package_hash"]),
        ("ix_post_fid_project_eligibilities_condition_hash", ["condition_snapshot_hash"]),
        ("ix_post_fid_project_eligibilities_status", ["eligibility_status"]),
        ("ix_post_fid_project_eligibilities_evaluated_by", ["evaluated_by"]),
        ("ix_post_fid_project_eligibilities_hash", ["eligibility_hash"]),
        ("ix_post_fid_project_eligibilities_configuration_id", ["configuration_id"]),
        ("ix_post_fid_project_eligibilities_configuration_hash", ["configuration_hash"]),
        (
            "ix_post_fid_eligibility_latest",
            ["tenant_id", "investment_decision_id", "project_workspace_id", "eligibility_round"],
        ),
        ("ix_post_fid_eligibility_queue", ["tenant_id", "eligibility_status", "evaluated_at"]),
    ):
        op.create_index(name, "post_fid_project_eligibilities", columns)


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "post_fid_project_eligibilities" in tables:
        op.drop_table("post_fid_project_eligibilities")
