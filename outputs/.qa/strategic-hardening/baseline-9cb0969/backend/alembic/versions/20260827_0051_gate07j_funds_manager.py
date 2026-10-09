"""add Gate 07J-FUND strategic Funds and Funding Readiness

Revision ID: 20260827_0051
Revises: 20260826_0050
Create Date: 2026-08-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0051"
down_revision: str | None = "20260826_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "strategic_funding_sources" in inspector.get_table_names():
        return
    op.create_table(
        "strategic_funding_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("source_code", sa.String(80), nullable=False),
        sa.Column("source_name", sa.String(180), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("legal_entity_provider_reference", sa.String(300)),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("effective_from", sa.Date()),
        sa.Column("effective_to", sa.Date()),
        sa.Column("restrictions_json", sa.JSON(), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("source_reference", sa.String(300)),
        sa.Column("source_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(160)),
        sa.Column("activate_idempotency_key", sa.String(160)),
        sa.Column("suspend_idempotency_key", sa.String(160)),
        sa.Column("close_idempotency_key", sa.String(160)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "source_code", name="uq_strategic_funding_source_code"),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_strategic_funding_source_create_key"),
        sa.UniqueConstraint("tenant_id", "activate_idempotency_key", name="uq_strategic_funding_source_activate_key"),
        sa.UniqueConstraint("tenant_id", "suspend_idempotency_key", name="uq_strategic_funding_source_suspend_key"),
        sa.UniqueConstraint("tenant_id", "close_idempotency_key", name="uq_strategic_funding_source_close_key"),
        sa.CheckConstraint(
            "status IN ('DRAFT','ACTIVE','SUSPENDED','CLOSED','ARCHIVED')",
            name="ck_strategic_funding_source_status",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_strategic_funding_source_dates",
        ),
    )
    _indexes(
        "strategic_funding_sources",
        (
            ("ix_strategic_funding_sources_tenant_id", ["tenant_id"]),
            ("ix_strategic_funding_sources_source_code", ["source_code"]),
            ("ix_strategic_funding_sources_source_type", ["source_type"]),
            ("ix_strategic_funding_sources_currency", ["currency"]),
            ("ix_strategic_funding_sources_status", ["status"]),
            ("ix_strategic_funding_sources_source_hash", ["source_hash"]),
            ("ix_strategic_funding_source_tenant_status", ["tenant_id", "status"]),
        ),
    )

    op.create_table(
        "funds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("fund_code", sa.String(80), nullable=False),
        sa.Column("fund_name", sa.String(180), nullable=False),
        sa.Column("funding_source_id", sa.Integer(), sa.ForeignKey("strategic_funding_sources.id")),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("authorized_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("available_from", sa.Date()),
        sa.Column("available_to", sa.Date()),
        sa.Column("period_granularity", sa.String(16), nullable=False, server_default="TOTAL"),
        sa.Column("authorized_amount_by_period_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("restrictions_json", sa.JSON(), nullable=False),
        sa.Column("applicable_workspace_scope_json", sa.JSON(), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("source_reference", sa.String(300)),
        sa.Column("fund_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(160)),
        sa.Column("authorize_idempotency_key", sa.String(160)),
        sa.Column("activate_idempotency_key", sa.String(160)),
        sa.Column("suspend_idempotency_key", sa.String(160)),
        sa.Column("close_idempotency_key", sa.String(160)),
        sa.Column("authorized_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("authorized_at", sa.DateTime()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "fund_code", name="uq_fund_code"),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_fund_create_key"),
        sa.UniqueConstraint("tenant_id", "authorize_idempotency_key", name="uq_fund_authorize_key"),
        sa.UniqueConstraint("tenant_id", "activate_idempotency_key", name="uq_fund_activate_key"),
        sa.UniqueConstraint("tenant_id", "suspend_idempotency_key", name="uq_fund_suspend_key"),
        sa.UniqueConstraint("tenant_id", "close_idempotency_key", name="uq_fund_close_key"),
        sa.CheckConstraint("authorized_amount >= 0", name="ck_fund_authorized_non_negative"),
        sa.CheckConstraint(
            "status IN ('DRAFT','AUTHORIZED','ACTIVE','SUSPENDED','EXHAUSTED','CLOSED','SUPERSEDED')",
            name="ck_fund_status",
        ),
        sa.CheckConstraint(
            "period_granularity IN ('TOTAL','YEAR','QUARTER','MONTH')", name="ck_fund_period_granularity"
        ),
        sa.CheckConstraint(
            "available_to IS NULL OR available_from IS NULL OR available_to >= available_from",
            name="ck_fund_dates",
        ),
    )
    _indexes(
        "funds",
        (
            ("ix_funds_tenant_id", ["tenant_id"]),
            ("ix_funds_fund_code", ["fund_code"]),
            ("ix_funds_funding_source_id", ["funding_source_id"]),
            ("ix_funds_currency", ["currency"]),
            ("ix_funds_status", ["status"]),
            ("ix_funds_fund_hash", ["fund_hash"]),
            ("ix_funds_authorized_by", ["authorized_by"]),
            ("ix_funds_created_by", ["created_by"]),
            ("ix_funds_updated_by", ["updated_by"]),
            ("ix_fund_tenant_status_currency", ["tenant_id", "status", "currency"]),
        ),
    )

    op.create_table(
        "funding_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("fund_id", sa.Integer(), sa.ForeignKey("funds.id"), nullable=False),
        sa.Column("parent_assignment_id", sa.Integer(), sa.ForeignKey("funding_assignments.id")),
        sa.Column("assignment_number", sa.String(80), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("portfolio_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id")),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id")),
        sa.Column("recommended_project_set_hash", sa.String(64)),
        sa.Column("source_convergence_id", sa.Integer(), sa.ForeignKey("portfolio_scenario_convergences.id")),
        sa.Column("source_recommendation_hash", sa.String(64)),
        sa.Column("amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("normalized_amount", sa.Numeric(20, 2)),
        sa.Column("normalized_currency", sa.String(8)),
        sa.Column("fx_source_reference", sa.String(300)),
        sa.Column("fx_as_of_date", sa.Date()),
        sa.Column("fx_hash", sa.String(64)),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("period_profile_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("assignment_purpose", sa.Text(), nullable=False, server_default=""),
        sa.Column("eligibility_status", sa.String(32), nullable=False, server_default="ELIGIBLE"),
        sa.Column("conditions_json", sa.JSON(), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("assignment_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_idempotency_key", sa.String(160)),
        sa.Column("reserve_idempotency_key", sa.String(160)),
        sa.Column("confirm_idempotency_key", sa.String(160)),
        sa.Column("release_idempotency_key", sa.String(160)),
        sa.Column("cancel_idempotency_key", sa.String(160)),
        sa.Column("prepared_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("confirmed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "assignment_number", name="uq_funding_assignment_number"),
        sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_funding_assignment_create_key"),
        sa.UniqueConstraint("tenant_id", "reserve_idempotency_key", name="uq_funding_assignment_reserve_key"),
        sa.UniqueConstraint("tenant_id", "confirm_idempotency_key", name="uq_funding_assignment_confirm_key"),
        sa.UniqueConstraint("tenant_id", "release_idempotency_key", name="uq_funding_assignment_release_key"),
        sa.UniqueConstraint("tenant_id", "cancel_idempotency_key", name="uq_funding_assignment_cancel_key"),
        sa.CheckConstraint("amount > 0", name="ck_funding_assignment_positive_amount"),
        sa.CheckConstraint(
            "status IN ('DRAFT','RESERVED','CONFIRMED','RELEASED','CANCELLED','EXPIRED')",
            name="ck_funding_assignment_status",
        ),
        sa.CheckConstraint(
            "scope_type IN ('PORTFOLIO','PROJECT','RECOMMENDED_PROJECT_SET')",
            name="ck_funding_assignment_scope",
        ),
        sa.CheckConstraint(
            "eligibility_status IN ('ELIGIBLE','CONDITIONALLY_ELIGIBLE','INELIGIBLE')",
            name="ck_funding_assignment_eligibility",
        ),
        sa.CheckConstraint(
            "period_end IS NULL OR period_start IS NULL OR period_end >= period_start",
            name="ck_funding_assignment_dates",
        ),
    )
    _indexes(
        "funding_assignments",
        (
            ("ix_funding_assignments_tenant_id", ["tenant_id"]),
            ("ix_funding_assignments_fund_id", ["fund_id"]),
            ("ix_funding_assignments_parent_assignment_id", ["parent_assignment_id"]),
            ("ix_funding_assignments_assignment_number", ["assignment_number"]),
            ("ix_funding_assignments_scope_type", ["scope_type"]),
            ("ix_funding_assignments_portfolio_workspace_id", ["portfolio_workspace_id"]),
            ("ix_funding_assignments_project_workspace_id", ["project_workspace_id"]),
            ("ix_funding_assignments_recommended_project_set_hash", ["recommended_project_set_hash"]),
            ("ix_funding_assignments_source_convergence_id", ["source_convergence_id"]),
            ("ix_funding_assignments_source_recommendation_hash", ["source_recommendation_hash"]),
            ("ix_funding_assignments_currency", ["currency"]),
            ("ix_funding_assignments_status", ["status"]),
            ("ix_funding_assignments_eligibility_status", ["eligibility_status"]),
            ("ix_funding_assignments_assignment_hash", ["assignment_hash"]),
            ("ix_funding_assignments_prepared_by", ["prepared_by"]),
            ("ix_funding_assignments_confirmed_by", ["confirmed_by"]),
            ("ix_funding_assignment_scope_lookup", ["tenant_id", "scope_type", "portfolio_workspace_id"]),
            ("ix_funding_assignment_fund_status", ["tenant_id", "fund_id", "status"]),
        ),
    )

    op.create_table(
        "funding_readiness_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("portfolio_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id")),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id")),
        sa.Column("source_convergence_id", sa.Integer(), sa.ForeignKey("portfolio_scenario_convergences.id")),
        sa.Column("source_recommendation_hash", sa.String(64)),
        sa.Column("recommended_project_set_hash", sa.String(64)),
        sa.Column("budget_scenario_id", sa.Integer(), sa.ForeignKey("portfolio_budget_scenarios.id")),
        sa.Column("budget_scenario_hash", sa.String(64)),
        sa.Column("funding_requirement_source", sa.JSON(), nullable=False),
        sa.Column("funding_requirement_hash", sa.String(64), nullable=False),
        sa.Column("required_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("required_currency", sa.String(8), nullable=False),
        sa.Column("confirmed_funding_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("reserved_funding_amount", sa.Numeric(20, 2), nullable=False),
        sa.Column("funding_gap", sa.Numeric(20, 2), nullable=False),
        sa.Column("confirmed_coverage_percent", sa.Numeric(9, 4), nullable=False),
        sa.Column("potential_coverage_percent", sa.Numeric(9, 4), nullable=False),
        sa.Column("project_coverage_summary_json", sa.JSON(), nullable=False),
        sa.Column("period_coverage_summary_json", sa.JSON(), nullable=False),
        sa.Column("restriction_summary_json", sa.JSON(), nullable=False),
        sa.Column("conditions_summary_json", sa.JSON(), nullable=False),
        sa.Column("source_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("configuration_hash", sa.String(64), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("blockers_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("funding_readiness_hash", sa.String(64), nullable=False),
        sa.Column("source_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_supply_investment_gate_evidence", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("refresh_idempotency_key", sa.String(160)),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("generated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_funding_readiness_refresh_key"),
        sa.CheckConstraint("scope_type IN ('PORTFOLIO','PROJECT')", name="ck_funding_readiness_scope"),
        sa.CheckConstraint(
            "status IN ('NOT_STARTED','READY','BLOCKED','STALE','EXPIRED')",
            name="ck_funding_readiness_status",
        ),
        sa.CheckConstraint("required_amount >= 0", name="ck_funding_readiness_required_non_negative"),
    )
    _indexes(
        "funding_readiness_snapshots",
        (
            ("ix_funding_readiness_snapshots_tenant_id", ["tenant_id"]),
            ("ix_funding_readiness_snapshots_scope_type", ["scope_type"]),
            ("ix_funding_readiness_snapshots_portfolio_workspace_id", ["portfolio_workspace_id"]),
            ("ix_funding_readiness_snapshots_project_workspace_id", ["project_workspace_id"]),
            ("ix_funding_readiness_snapshots_source_convergence_id", ["source_convergence_id"]),
            ("ix_funding_readiness_snapshots_source_recommendation_hash", ["source_recommendation_hash"]),
            ("ix_funding_readiness_snapshots_recommended_project_set_hash", ["recommended_project_set_hash"]),
            ("ix_funding_readiness_snapshots_budget_scenario_id", ["budget_scenario_id"]),
            ("ix_funding_readiness_snapshots_funding_requirement_hash", ["funding_requirement_hash"]),
            ("ix_funding_readiness_snapshots_source_hash", ["source_hash"]),
            ("ix_funding_readiness_snapshots_configuration_hash", ["configuration_hash"]),
            ("ix_funding_readiness_snapshots_status", ["status"]),
            ("ix_funding_readiness_snapshots_funding_readiness_hash", ["funding_readiness_hash"]),
            ("ix_funding_readiness_snapshots_generated_by", ["generated_by"]),
            ("ix_funding_readiness_snapshots_generated_at", ["generated_at"]),
            (
                "ix_funding_readiness_latest",
                ["tenant_id", "portfolio_workspace_id", "project_workspace_id", "generated_at"],
            ),
        ),
    )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in ("funding_readiness_snapshots", "funding_assignments", "funds", "strategic_funding_sources"):
        if table in tables:
            op.drop_table(table)


def _indexes(table: str, definitions: tuple[tuple[str, list[str]], ...]) -> None:
    for name, columns in definitions:
        op.create_index(name, table, columns)
