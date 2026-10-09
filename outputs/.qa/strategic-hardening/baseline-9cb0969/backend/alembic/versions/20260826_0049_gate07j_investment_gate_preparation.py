"""add Gate 07J Investment Gate Preparation

Revision ID: 20260826_0049
Revises: 20260826_0048
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_0049"
down_revision: str | None = "20260826_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "investment_gate_preparations" in inspector.get_table_names():
        return
    op.create_table(
        "investment_gate_preparations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("portfolio_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("preparation_number", sa.String(120), nullable=False),
        sa.Column("logical_code", sa.String(120), nullable=False, server_default="INVESTMENT-GATE-PREPARATION"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("investment_gate_profile_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False),
        sa.Column("profile_code", sa.String(120), nullable=False),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("profile_hash", sa.String(64), nullable=False),
        sa.Column(
            "source_convergence_id", sa.Integer(), sa.ForeignKey("portfolio_scenario_convergences.id"), nullable=False
        ),
        sa.Column("source_convergence_revision", sa.Integer(), nullable=False),
        sa.Column("source_recommendation_hash", sa.String(64), nullable=False),
        sa.Column(
            "recommended_alternative_id",
            sa.Integer(),
            sa.ForeignKey("portfolio_converged_alternatives.id"),
            nullable=False,
        ),
        sa.Column("recommended_project_set_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("readiness_status", sa.String(16), nullable=False, server_default="BLOCKED"),
        sa.Column("source_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("evidence_summary_json", sa.JSON(), nullable=False),
        sa.Column("conditions_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("blockers_json", sa.JSON(), nullable=False),
        sa.Column("preparation_source_hash", sa.String(64), nullable=False),
        sa.Column("preparation_hash", sa.String(64)),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(160)),
        sa.Column("refresh_idempotency_key", sa.String(160)),
        sa.Column("ready_idempotency_key", sa.String(160)),
        sa.Column("freeze_idempotency_key", sa.String(160)),
        sa.Column("clone_idempotency_key", sa.String(160)),
        sa.Column("void_idempotency_key", sa.String(160)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("frozen_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("frozen_at", sa.DateTime()),
        sa.Column("voided_at", sa.DateTime()),
        sa.UniqueConstraint("tenant_id", "preparation_number", name="uq_investment_gate_preparation_number"),
        sa.UniqueConstraint(
            "tenant_id",
            "portfolio_workspace_id",
            "logical_code",
            "revision",
            name="uq_investment_gate_preparation_revision",
        ),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_investment_gate_create_key"),
        sa.UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_investment_gate_refresh_key"),
        sa.UniqueConstraint("tenant_id", "ready_idempotency_key", name="uq_investment_gate_ready_key"),
        sa.UniqueConstraint("tenant_id", "freeze_idempotency_key", name="uq_investment_gate_freeze_key"),
        sa.UniqueConstraint("tenant_id", "clone_idempotency_key", name="uq_investment_gate_clone_key"),
        sa.UniqueConstraint("tenant_id", "void_idempotency_key", name="uq_investment_gate_void_key"),
        sa.CheckConstraint(
            "status IN ('DRAFT','IN_PREPARATION','READY_FOR_REVIEW','FROZEN','SUPERSEDED','VOIDED')",
            name="ck_investment_gate_preparation_status",
        ),
        sa.CheckConstraint(
            "readiness_status IN ('READY','BLOCKED','STALE')",
            name="ck_investment_gate_preparation_readiness",
        ),
        sa.CheckConstraint(
            "status != 'FROZEN' OR (readiness_status = 'READY' AND preparation_hash IS NOT NULL)",
            name="ck_investment_gate_frozen_package",
        ),
    )
    for name, columns in (
        ("ix_investment_gate_preparations_tenant_id", ["tenant_id"]),
        ("ix_investment_gate_preparations_portfolio_workspace_id", ["portfolio_workspace_id"]),
        ("ix_investment_gate_preparations_investment_gate_profile_id", ["investment_gate_profile_id"]),
        ("ix_investment_gate_preparations_profile_code", ["profile_code"]),
        ("ix_investment_gate_preparations_source_convergence_id", ["source_convergence_id"]),
        ("ix_investment_gate_preparations_source_recommendation_hash", ["source_recommendation_hash"]),
        ("ix_investment_gate_preparations_recommended_alternative_id", ["recommended_alternative_id"]),
        ("ix_investment_gate_preparations_recommended_project_set_hash", ["recommended_project_set_hash"]),
        ("ix_investment_gate_preparations_status", ["status"]),
        ("ix_investment_gate_preparations_readiness_status", ["readiness_status"]),
        ("ix_investment_gate_preparations_preparation_source_hash", ["preparation_source_hash"]),
        ("ix_investment_gate_preparations_preparation_hash", ["preparation_hash"]),
        ("ix_investment_gate_preparations_created_by", ["created_by"]),
        ("ix_investment_gate_preparations_updated_by", ["updated_by"]),
        ("ix_investment_gate_preparations_frozen_by", ["frozen_by"]),
        ("ix_investment_gate_tenant_portfolio", ["tenant_id", "portfolio_workspace_id"]),
        ("ix_investment_gate_tenant_status", ["tenant_id", "status", "readiness_status"]),
        ("ix_investment_gate_source_profile", ["tenant_id", "source_convergence_id", "investment_gate_profile_id"]),
    ):
        op.create_index(name, "investment_gate_preparations", columns)

    op.create_table(
        "investment_gate_evidence_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("preparation_id", sa.Integer(), sa.ForeignKey("investment_gate_preparations.id"), nullable=False),
        sa.Column("requirement_key", sa.String(160), nullable=False),
        sa.Column("evidence_type", sa.String(80), nullable=False),
        sa.Column("scope_type", sa.String(40), nullable=False),
        sa.Column("scope_id", sa.Integer()),
        sa.Column("scope_key", sa.String(120), nullable=False),
        sa.Column("evidence_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("evidence_origin", sa.String(32), nullable=False),
        sa.Column("source_module", sa.String(120)),
        sa.Column("source_record_id", sa.String(180)),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("scope_reference_hash", sa.String(64)),
        sa.Column("status", sa.String(24), nullable=False, server_default="MISSING"),
        sa.Column("evidence_date", sa.DateTime()),
        sa.Column("valid_until", sa.DateTime()),
        sa.Column("issuer", sa.String(180)),
        sa.Column("owner", sa.String(180)),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("validated_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("validated_at", sa.DateTime()),
        sa.Column("validation_note", sa.Text()),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("blockers_json", sa.JSON(), nullable=False),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("add_idempotency_key", sa.String(160)),
        sa.Column("validate_idempotency_key", sa.String(160)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "preparation_id",
            "requirement_key",
            "scope_key",
            "evidence_revision",
            name="uq_investment_gate_evidence_revision",
        ),
        sa.UniqueConstraint("tenant_id", "add_idempotency_key", name="uq_investment_gate_evidence_add_key"),
        sa.UniqueConstraint("tenant_id", "validate_idempotency_key", name="uq_investment_gate_evidence_validate_key"),
        sa.CheckConstraint(
            "evidence_origin IN ('GOVERNED_SOURCE','MANUAL_REFERENCE')",
            name="ck_investment_gate_evidence_origin",
        ),
        sa.CheckConstraint(
            "scope_type IN ('PORTFOLIO','PROJECT_SET','EACH_PROJECT','SELECTED_PROJECTS_ONLY')",
            name="ck_investment_gate_evidence_scope",
        ),
        sa.CheckConstraint(
            "status IN ('NOT_AVAILABLE','MISSING','DRAFT','SUBMITTED','VALID','INVALID','EXPIRED','STALE','NOT_REQUIRED')",
            name="ck_investment_gate_evidence_status",
        ),
    )
    for name, columns in (
        ("ix_investment_gate_evidence_items_tenant_id", ["tenant_id"]),
        ("ix_investment_gate_evidence_items_preparation_id", ["preparation_id"]),
        ("ix_investment_gate_evidence_items_requirement_key", ["requirement_key"]),
        ("ix_investment_gate_evidence_items_evidence_type", ["evidence_type"]),
        ("ix_investment_gate_evidence_items_scope_id", ["scope_id"]),
        ("ix_investment_gate_evidence_items_source_hash", ["source_hash"]),
        ("ix_investment_gate_evidence_items_scope_reference_hash", ["scope_reference_hash"]),
        ("ix_investment_gate_evidence_items_status", ["status"]),
        ("ix_investment_gate_evidence_items_valid_until", ["valid_until"]),
        ("ix_investment_gate_evidence_items_submitted_by", ["submitted_by"]),
        ("ix_investment_gate_evidence_items_validated_by", ["validated_by"]),
        ("ix_investment_gate_evidence_lookup", ["tenant_id", "preparation_id", "requirement_key"]),
        ("ix_investment_gate_evidence_status", ["tenant_id", "preparation_id", "status"]),
    ):
        op.create_index(name, "investment_gate_evidence_items", columns)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "investment_gate_preparations" not in inspector.get_table_names():
        return
    if "investment_gate_evidence_items" in inspector.get_table_names():
        op.drop_table("investment_gate_evidence_items")
    op.drop_table("investment_gate_preparations")
