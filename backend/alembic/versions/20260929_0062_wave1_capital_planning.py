"""add Wave 1 strategic capital planning and demand

Revision ID: 20260929_0062
Revises: 20260916_0061
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260929_0062"
down_revision: str | None = "20260916_0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _index(table: str, column: str) -> None:
    op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if "capital_planning_cycles" not in existing:
        op.create_table(
            "capital_planning_cycles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("cycle_number", sa.String(40), nullable=False),
            sa.Column("name", sa.String(220), nullable=False),
            sa.Column("planning_horizon_start", sa.Date(), nullable=False),
            sa.Column("planning_horizon_end", sa.Date(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("scope_workspace_id", sa.Integer(), nullable=True),
            sa.Column("responsible_organization_workspace_id", sa.Integer(), nullable=True),
            sa.Column("applicable_theme_codes_json", sa.JSON(), nullable=False),
            sa.Column("capital_basis_currency", sa.String(8), nullable=True),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("configuration_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("configuration_hash", sa.String(64), nullable=False),
            sa.Column("create_idempotency_key", sa.String(160), nullable=False),
            sa.Column("open_idempotency_key", sa.String(160), nullable=True),
            sa.Column("review_idempotency_key", sa.String(160), nullable=True),
            sa.Column("close_idempotency_key", sa.String(160), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=False),
            sa.Column("last_modified_by_user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("opened_at", sa.DateTime(), nullable=True),
            sa.Column("review_started_at", sa.DateTime(), nullable=True),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["scope_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["responsible_organization_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["last_modified_by_user_id"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "cycle_number", name="uq_capital_planning_cycle_number"),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_capital_planning_cycle_create_key"),
            sa.UniqueConstraint("tenant_id", "open_idempotency_key", name="uq_capital_planning_cycle_open_key"),
            sa.UniqueConstraint("tenant_id", "review_idempotency_key", name="uq_capital_planning_cycle_review_key"),
            sa.UniqueConstraint("tenant_id", "close_idempotency_key", name="uq_capital_planning_cycle_close_key"),
            sa.CheckConstraint(
                "status IN ('DRAFT','OPEN','IN_REVIEW','CLOSED')",
                name="ck_capital_planning_cycle_status",
            ),
            sa.CheckConstraint(
                "planning_horizon_end >= planning_horizon_start",
                name="ck_capital_planning_cycle_dates",
            ),
        )
        for column in (
            "tenant_id",
            "cycle_number",
            "status",
            "scope_workspace_id",
            "configuration_hash",
            "created_by_user_id",
            "last_modified_by_user_id",
            "updated_at",
        ):
            _index("capital_planning_cycles", column)
        op.create_index(
            "ix_cp_cycle_responsible_workspace",
            "capital_planning_cycles",
            ["responsible_organization_workspace_id"],
        )
        op.create_index(
            "ix_capital_planning_cycle_queue",
            "capital_planning_cycles",
            ["tenant_id", "status", "updated_at", "id"],
        )

    existing = set(sa.inspect(bind).get_table_names())
    if "capital_planning_cycle_themes" not in existing:
        op.create_table(
            "capital_planning_cycle_themes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("planning_cycle_id", sa.Integer(), nullable=False),
            sa.Column("theme_code", sa.String(120), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["planning_cycle_id"], ["capital_planning_cycles.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "planning_cycle_id", "theme_code", name="uq_capital_cycle_theme"),
        )
        for column in ("tenant_id", "planning_cycle_id", "theme_code"):
            _index("capital_planning_cycle_themes", column)
        op.create_index(
            "ix_capital_cycle_theme_lookup",
            "capital_planning_cycle_themes",
            ["tenant_id", "theme_code", "planning_cycle_id"],
        )

    existing = set(sa.inspect(bind).get_table_names())
    if "strategic_capital_demands" not in existing:
        op.create_table(
            "strategic_capital_demands",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("demand_number", sa.String(40), nullable=False),
            sa.Column("name", sa.String(220), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("planning_cycle_id", sa.Integer(), nullable=False),
            sa.Column("theme_codes_json", sa.JSON(), nullable=False),
            sa.Column("strategic_objective_codes_json", sa.JSON(), nullable=False),
            sa.Column("business_or_asset_need", sa.Text(), nullable=False),
            sa.Column("strategic_driver", sa.String(120), nullable=False),
            sa.Column("demand_category", sa.String(120), nullable=True),
            sa.Column("urgency", sa.String(40), nullable=True),
            sa.Column("target_horizon", sa.String(80), nullable=False),
            sa.Column("sponsor_user_id", sa.Integer(), nullable=False),
            sa.Column("owning_workspace_id", sa.Integer(), nullable=False),
            sa.Column("location_context", sa.String(300), nullable=True),
            sa.Column("indicative_capital_need", sa.Numeric(20, 2), nullable=True),
            sa.Column("currency_code", sa.String(8), nullable=True),
            sa.Column("indicative_capital_range_low", sa.Numeric(20, 2), nullable=True),
            sa.Column("indicative_capital_range_high", sa.Numeric(20, 2), nullable=True),
            sa.Column("uncertainty_level", sa.String(80), nullable=True),
            sa.Column("potential_portfolio_id", sa.Integer(), nullable=True),
            sa.Column("assumptions_json", sa.JSON(), nullable=False),
            sa.Column("constraints_json", sa.JSON(), nullable=False),
            sa.Column("dependencies_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("readiness_json", sa.JSON(), nullable=False),
            sa.Column("configuration_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("configuration_hash", sa.String(64), nullable=False),
            sa.Column("demand_hash", sa.String(64), nullable=False),
            sa.Column("endorsed_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("endorsed_snapshot_hash", sa.String(64), nullable=True),
            sa.Column("create_idempotency_key", sa.String(160), nullable=False),
            sa.Column("submit_idempotency_key", sa.String(160), nullable=True),
            sa.Column("review_idempotency_key", sa.String(160), nullable=True),
            sa.Column("return_idempotency_key", sa.String(160), nullable=True),
            sa.Column("endorse_idempotency_key", sa.String(160), nullable=True),
            sa.Column("defer_idempotency_key", sa.String(160), nullable=True),
            sa.Column("cancel_idempotency_key", sa.String(160), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=False),
            sa.Column("last_modified_by_user_id", sa.Integer(), nullable=False),
            sa.Column("reviewer_user_id", sa.Integer(), nullable=True),
            sa.Column("endorser_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
            sa.Column("review_started_at", sa.DateTime(), nullable=True),
            sa.Column("returned_at", sa.DateTime(), nullable=True),
            sa.Column("endorsed_at", sa.DateTime(), nullable=True),
            sa.Column("deferred_at", sa.DateTime(), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(), nullable=True),
            sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["planning_cycle_id"], ["capital_planning_cycles.id"]),
            sa.ForeignKeyConstraint(["sponsor_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["owning_workspace_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["potential_portfolio_id"], ["enterprise_workspaces.id"]),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["last_modified_by_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["reviewer_user_id"], ["user_accounts.id"]),
            sa.ForeignKeyConstraint(["endorser_user_id"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "demand_number", name="uq_strategic_capital_demand_number"),
            sa.UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_strategic_capital_demand_create_key"),
            sa.UniqueConstraint("tenant_id", "submit_idempotency_key", name="uq_strategic_capital_demand_submit_key"),
            sa.UniqueConstraint("tenant_id", "review_idempotency_key", name="uq_strategic_capital_demand_review_key"),
            sa.UniqueConstraint("tenant_id", "return_idempotency_key", name="uq_strategic_capital_demand_return_key"),
            sa.UniqueConstraint("tenant_id", "endorse_idempotency_key", name="uq_strategic_capital_demand_endorse_key"),
            sa.UniqueConstraint("tenant_id", "defer_idempotency_key", name="uq_strategic_capital_demand_defer_key"),
            sa.UniqueConstraint("tenant_id", "cancel_idempotency_key", name="uq_strategic_capital_demand_cancel_key"),
            sa.CheckConstraint(
                "status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED','ENDORSED','DEFERRED','CANCELLED','SUPERSEDED')",
                name="ck_strategic_capital_demand_status",
            ),
            sa.CheckConstraint(
                "indicative_capital_need IS NULL OR indicative_capital_need >= 0",
                name="ck_demand_need_nonnegative",
            ),
            sa.CheckConstraint(
                "indicative_capital_range_low IS NULL OR indicative_capital_range_low >= 0",
                name="ck_demand_range_low_nonnegative",
            ),
            sa.CheckConstraint(
                "indicative_capital_range_high IS NULL OR indicative_capital_range_high >= 0",
                name="ck_demand_range_high_nonnegative",
            ),
            sa.CheckConstraint(
                "indicative_capital_range_high IS NULL OR indicative_capital_range_low IS NULL "
                "OR indicative_capital_range_high >= indicative_capital_range_low",
                name="ck_demand_range_order",
            ),
        )
        for column in (
            "tenant_id",
            "demand_number",
            "planning_cycle_id",
            "strategic_driver",
            "demand_category",
            "urgency",
            "target_horizon",
            "sponsor_user_id",
            "owning_workspace_id",
            "currency_code",
            "uncertainty_level",
            "potential_portfolio_id",
            "status",
            "configuration_hash",
            "demand_hash",
            "endorsed_snapshot_hash",
            "created_by_user_id",
            "last_modified_by_user_id",
            "reviewer_user_id",
            "endorser_user_id",
            "updated_at",
        ):
            _index("strategic_capital_demands", column)
        op.create_index(
            "ix_strategic_capital_demand_queue",
            "strategic_capital_demands",
            ["tenant_id", "status", "updated_at", "id"],
        )
        op.create_index(
            "ix_strategic_capital_demand_cycle_status",
            "strategic_capital_demands",
            ["tenant_id", "planning_cycle_id", "status"],
        )

    for table_name, value_column, unique_name, lookup_name in (
        (
            "strategic_capital_demand_themes",
            "theme_code",
            "uq_capital_demand_theme",
            "ix_capital_demand_theme_lookup",
        ),
        (
            "strategic_capital_demand_objectives",
            "objective_code",
            "uq_capital_demand_objective",
            "ix_capital_demand_objective_lookup",
        ),
    ):
        existing = set(sa.inspect(bind).get_table_names())
        if table_name in existing:
            continue
        op.create_table(
            table_name,
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("capital_demand_id", sa.Integer(), nullable=False),
            sa.Column(value_column, sa.String(120), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["capital_demand_id"], ["strategic_capital_demands.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "capital_demand_id", value_column, name=unique_name),
        )
        for column in ("tenant_id", "capital_demand_id", value_column):
            _index(table_name, column)
        op.create_index(
            lookup_name,
            table_name,
            ["tenant_id", value_column, "capital_demand_id"],
        )

    idea_columns = {item["name"] for item in sa.inspect(bind).get_columns("ideas")}
    if "source_capital_demand_id" not in idea_columns or "source_capital_demand_snapshot_hash" not in idea_columns:
        with op.batch_alter_table("ideas") as batch_op:
            if "source_capital_demand_id" not in idea_columns:
                batch_op.add_column(sa.Column("source_capital_demand_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_ideas_source_capital_demand",
                    "strategic_capital_demands",
                    ["source_capital_demand_id"],
                    ["id"],
                )
                batch_op.create_index("ix_ideas_source_capital_demand_id", ["source_capital_demand_id"])
            if "source_capital_demand_snapshot_hash" not in idea_columns:
                batch_op.add_column(sa.Column("source_capital_demand_snapshot_hash", sa.String(64), nullable=True))
                batch_op.create_index(
                    "ix_ideas_source_capital_demand_snapshot_hash",
                    ["source_capital_demand_snapshot_hash"],
                )

    existing = set(sa.inspect(bind).get_table_names())
    if "capital_demand_idea_origins" not in existing:
        op.create_table(
            "capital_demand_idea_origins",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("capital_demand_id", sa.Integer(), nullable=False),
            sa.Column("idea_id", sa.Integer(), nullable=False),
            sa.Column("source_demand_version", sa.Integer(), nullable=False),
            sa.Column("source_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("source_snapshot_hash", sa.String(64), nullable=False),
            sa.Column("source_configuration_hash", sa.String(64), nullable=False),
            sa.Column("origin_request_hash", sa.String(64), nullable=False),
            sa.Column("origin_idempotency_key", sa.String(160), nullable=False),
            sa.Column("originated_by_user_id", sa.Integer(), nullable=False),
            sa.Column("originated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["capital_demand_id"], ["strategic_capital_demands.id"]),
            sa.ForeignKeyConstraint(["idea_id"], ["ideas.id"]),
            sa.ForeignKeyConstraint(["originated_by_user_id"], ["user_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "idea_id", name="uq_capital_demand_origin_idea"),
            sa.UniqueConstraint("tenant_id", "origin_idempotency_key", name="uq_capital_demand_origin_key"),
        )
        for column in (
            "tenant_id",
            "capital_demand_id",
            "idea_id",
            "source_snapshot_hash",
            "origin_request_hash",
            "originated_by_user_id",
            "originated_at",
        ):
            _index("capital_demand_idea_origins", column)
        op.create_index(
            "ix_capital_demand_origin_history",
            "capital_demand_idea_origins",
            ["tenant_id", "capital_demand_id", "originated_at", "id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if "capital_demand_idea_origins" in existing:
        op.drop_table("capital_demand_idea_origins")

    if "ideas" in existing:
        idea_columns = {item["name"] for item in sa.inspect(bind).get_columns("ideas")}
        if "source_capital_demand_id" in idea_columns or "source_capital_demand_snapshot_hash" in idea_columns:
            with op.batch_alter_table("ideas") as batch_op:
                if "source_capital_demand_id" in idea_columns:
                    batch_op.drop_index("ix_ideas_source_capital_demand_id")
                    batch_op.drop_constraint("fk_ideas_source_capital_demand", type_="foreignkey")
                    batch_op.drop_column("source_capital_demand_id")
                if "source_capital_demand_snapshot_hash" in idea_columns:
                    batch_op.drop_index("ix_ideas_source_capital_demand_snapshot_hash")
                    batch_op.drop_column("source_capital_demand_snapshot_hash")

    for table_name in (
        "strategic_capital_demand_objectives",
        "strategic_capital_demand_themes",
        "strategic_capital_demands",
        "capital_planning_cycle_themes",
        "capital_planning_cycles",
    ):
        if table_name in set(sa.inspect(bind).get_table_names()):
            op.drop_table(table_name)
