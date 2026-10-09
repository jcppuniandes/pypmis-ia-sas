"""add Gate 07K Investment Decision and FID governance

Revision ID: 20260831_0055
Revises: 20260831_0054
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0055"
down_revision: str | None = "20260831_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "investment_decisions" not in tables:
        op.create_table(
            "investment_decisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("decision_number", sa.String(40), nullable=False),
            sa.Column(
                "investment_gate_preparation_id",
                sa.Integer(),
                sa.ForeignKey("investment_gate_preparations.id"),
                nullable=False,
            ),
            sa.Column(
                "portfolio_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False
            ),
            sa.Column(
                "investment_gate_profile_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False
            ),
            sa.Column("profile_code", sa.String(80), nullable=False),
            sa.Column("decision_round", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("decision_scope_type", sa.String(32), nullable=False, server_default="EXACT_PROJECT_SET"),
            sa.Column("decision_scope_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
            sa.Column("outcome", sa.String(16)),
            sa.Column("title", sa.String(240), nullable=False),
            sa.Column("executive_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
            sa.Column("conditions_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("hold_reason", sa.Text()),
            sa.Column("recycle_target", sa.String(120)),
            sa.Column("source_preparation_hash", sa.String(64), nullable=False),
            sa.Column("source_package_hash", sa.String(64), nullable=False),
            sa.Column("source_profile_hash", sa.String(64), nullable=False),
            sa.Column("source_policy_hash", sa.String(64)),
            sa.Column("decision_package_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False),
            sa.Column("configuration_revision", sa.Integer(), nullable=False),
            sa.Column("configuration_hash", sa.String(64), nullable=False),
            sa.Column("configuration_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("authority_model", sa.String(32), nullable=False, server_default="SINGLE_DECISION_MAKER"),
            sa.Column("authority_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("committee_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("quorum_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("voting_rule_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("checklist_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("authorized_amount", sa.Numeric(18, 2)),
            sa.Column("authorized_currency", sa.String(3)),
            sa.Column("authorization_valid_until", sa.DateTime()),
            sa.Column("decision_maker_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id")),
            sa.Column("submitted_at", sa.DateTime()),
            sa.Column("review_started_at", sa.DateTime()),
            sa.Column("ready_at", sa.DateTime()),
            sa.Column("decided_at", sa.DateTime()),
            sa.Column("voided_at", sa.DateTime()),
            sa.Column("decided_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
            sa.Column("is_fid", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("full_funds_authorized", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("investment_authorized", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("decision_hash", sa.String(64)),
            sa.Column("create_idempotency_key", sa.String(160)),
            sa.Column("decide_idempotency_key", sa.String(160)),
            sa.Column("decide_payload_hash", sa.String(64)),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("tenant_id", "decision_number", name="uq_investment_decision_number"),
            sa.UniqueConstraint(
                "tenant_id",
                "investment_gate_preparation_id",
                "profile_code",
                "decision_round",
                name="uq_investment_decision_preparation_round",
            ),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_investment_decision_create_key"),
            sa.UniqueConstraint("tenant_id", "decide_idempotency_key", name="uq_investment_decision_decide_key"),
            sa.CheckConstraint(
                "status IN ('DRAFT','SUBMITTED','IN_REVIEW','READY_FOR_DECISION','DECIDED','VOIDED')",
                name="ck_investment_decision_status",
            ),
            sa.CheckConstraint(
                "outcome IS NULL OR outcome IN ('GO','HOLD','RECYCLE','KILL')",
                name="ck_investment_decision_outcome",
            ),
            sa.CheckConstraint(
                "(status = 'DECIDED' AND outcome IS NOT NULL AND decided_at IS NOT NULL AND decision_hash IS NOT NULL) "
                "OR (status != 'DECIDED' AND outcome IS NULL)",
                name="ck_investment_decision_closed_fields",
            ),
            sa.CheckConstraint(
                "is_fid = false OR (profile_code = 'PYP-FFA' AND outcome = 'GO' AND "
                "full_funds_authorized = true AND investment_authorized = true)",
                name="ck_investment_decision_fid_semantics",
            ),
            sa.CheckConstraint(
                "outcome != 'HOLD' OR hold_reason IS NOT NULL", name="ck_investment_decision_hold_reason"
            ),
            sa.CheckConstraint(
                "outcome != 'RECYCLE' OR recycle_target IS NOT NULL", name="ck_investment_decision_recycle_target"
            ),
            sa.CheckConstraint(
                "outcome != 'KILL' OR length(rationale) > 0", name="ck_investment_decision_kill_rationale"
            ),
        )
        indexes = (
            ("ix_investment_decisions_tenant_id", ["tenant_id"]),
            ("ix_investment_decisions_decision_number", ["decision_number"]),
            ("ix_investment_decisions_preparation_id", ["investment_gate_preparation_id"]),
            ("ix_investment_decisions_portfolio_id", ["portfolio_workspace_id"]),
            ("ix_investment_decisions_profile_id", ["investment_gate_profile_id"]),
            ("ix_investment_decisions_profile_code", ["profile_code"]),
            ("ix_investment_decisions_scope_hash", ["decision_scope_hash"]),
            ("ix_investment_decisions_status", ["status"]),
            ("ix_investment_decisions_outcome", ["outcome"]),
            ("ix_investment_decisions_source_preparation_hash", ["source_preparation_hash"]),
            ("ix_investment_decisions_source_package_hash", ["source_package_hash"]),
            ("ix_investment_decisions_source_profile_hash", ["source_profile_hash"]),
            ("ix_investment_decisions_source_policy_hash", ["source_policy_hash"]),
            ("ix_investment_decisions_configuration_id", ["configuration_id"]),
            ("ix_investment_decisions_configuration_hash", ["configuration_hash"]),
            ("ix_investment_decisions_maker_id", ["decision_maker_user_id"]),
            ("ix_investment_decisions_decided_by", ["decided_by"]),
            ("ix_investment_decisions_decision_hash", ["decision_hash"]),
            ("ix_investment_decisions_created_by", ["created_by"]),
            ("ix_investment_decisions_updated_by", ["updated_by"]),
            ("ix_investment_decision_queue", ["tenant_id", "status", "profile_code", "updated_at"]),
            ("ix_investment_decision_history", ["tenant_id", "portfolio_workspace_id", "decided_at"]),
        )
        for name, columns in indexes:
            op.create_index(name, "investment_decisions", columns)
        op.create_index(
            "uq_investment_decision_active_preparation_profile",
            "investment_decisions",
            ["tenant_id", "investment_gate_preparation_id", "profile_code"],
            unique=True,
            postgresql_where=sa.text("status IN ('DRAFT','SUBMITTED','IN_REVIEW','READY_FOR_DECISION')"),
        )

    if "investment_decision_votes" not in tables:
        op.create_table(
            "investment_decision_votes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("investment_decision_id", sa.Integer(), sa.ForeignKey("investment_decisions.id"), nullable=False),
            sa.Column("voter_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("vote", sa.String(16), nullable=False),
            sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
            sa.Column("cast_at", sa.DateTime(), nullable=False),
            sa.Column("idempotency_key", sa.String(160)),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint(
                "tenant_id", "investment_decision_id", "voter_user_id", name="uq_investment_vote_member"
            ),
            sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_investment_vote_key"),
            sa.CheckConstraint("vote IN ('GO','HOLD','RECYCLE','KILL','ABSTAIN')", name="ck_investment_vote_value"),
        )
        for name, columns in (
            ("ix_investment_decision_votes_tenant_id", ["tenant_id"]),
            ("ix_investment_decision_votes_decision_id", ["investment_decision_id"]),
            ("ix_investment_decision_votes_voter_id", ["voter_user_id"]),
            ("ix_investment_vote_decision_cast", ["tenant_id", "investment_decision_id", "cast_at"]),
        ):
            op.create_index(name, "investment_decision_votes", columns)


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "investment_decision_votes" in tables:
        op.drop_table("investment_decision_votes")
    if "investment_decisions" in tables:
        op.drop_table("investment_decisions")
