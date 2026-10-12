"""Separate governed QRA runs and reviews with database history protection.

Revision ID: 20261011_0068
Revises: 20261009_0067
Additive only. No Foundation or source-domain row is rewritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261011_0068"
down_revision: str | None = "20261009_0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FROZEN = (
    "tenant_id",
    "project_workspace_id",
    "run_number",
    "model_definition_id",
    "model_number",
    "model_version",
    "model_hash",
    "analysis_type",
    "engine_name",
    "engine_version",
    "formula_version",
    "configuration_id",
    "configuration_revision",
    "configuration_hash",
    "seed",
    "iterations_requested",
    "input_snapshot_hash",
    "input_snapshot_json",
    "title",
    "comments",
    "created_by",
    "created_at",
)


def upgrade():
    op.create_table(
        "qra_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("run_number", sa.String(40), nullable=False),
        sa.Column("model_definition_id", sa.Integer(), sa.ForeignKey("qra_model_definitions.id"), nullable=False),
        sa.Column("model_number", sa.String(40), nullable=False),
        sa.Column("model_version", sa.Integer(), nullable=False),
        sa.Column("model_hash", sa.String(64), nullable=False),
        sa.Column("analysis_type", sa.String(40), nullable=False),
        sa.Column("engine_name", sa.String(80), nullable=False),
        sa.Column("engine_version", sa.String(80), nullable=False),
        sa.Column("formula_version", sa.String(80), nullable=False),
        sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False),
        sa.Column("configuration_revision", sa.Integer(), nullable=False),
        sa.Column("configuration_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUEUED"),
        sa.Column("seed", sa.String(30), nullable=False),
        sa.Column("iterations_requested", sa.Integer(), nullable=False),
        sa.Column("iterations_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("result_snapshot_hash", sa.String(64)),
        sa.Column("trace_hash", sa.String(64)),
        sa.Column("input_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("runtime_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("warnings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("failure_reason", sa.String(240)),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("comments", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("execution_actor", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("heartbeat_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("failed_at", sa.DateTime()),
        sa.Column("cancelled_at", sa.DateTime()),
        sa.Column("dispatch_state", sa.String(24), nullable=False, server_default="NOT_REQUESTED"),
        sa.Column("task_id", sa.String(100)),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("tenant_id", "run_number", name="uq_qra_run_number"),
        sa.UniqueConstraint("task_id", name="uq_qra_run_task"),
        sa.CheckConstraint(
            "status IN ('QUEUED','VALIDATING','RUNNING','COMPLETED','FAILED','CANCELLED')", name="ck_qra_run_status"
        ),
        sa.CheckConstraint("analysis_type IN ('COST_QRA','SCHEDULE_QRA')", name="ck_qra_run_analysis"),
        sa.CheckConstraint(
            "iterations_requested > 0 AND iterations_completed >= 0 AND iterations_completed <= iterations_requested AND revision_version > 0",
            name="ck_qra_run_progress",
        ),
        sa.CheckConstraint(
            "status != 'COMPLETED' OR (result_snapshot_hash IS NOT NULL AND trace_hash IS NOT NULL AND completed_at IS NOT NULL AND iterations_completed = iterations_requested)",
            name="ck_qra_run_completed",
        ),
    )
    for column in ("tenant_id", "project_workspace_id", "model_definition_id", "status"):
        op.create_index(f"ix_qra_runs_{column}", "qra_runs", [column])
    op.create_index("ix_qra_run_history", "qra_runs", ["tenant_id", "project_workspace_id", "analysis_type", "id"])
    op.create_table(
        "qra_run_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("qra_runs.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="IN_REVIEW"),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("accepted_by", sa.Integer(), sa.ForeignKey("user_accounts.id")),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime()),
        sa.Column("review_comments", sa.Text(), nullable=False, server_default=""),
        sa.Column("acceptance_comments", sa.Text(), nullable=False, server_default=""),
        sa.Column("acceptance_hash", sa.String(64)),
        sa.Column("revision_version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("tenant_id", "run_id", name="uq_qra_run_review"),
        sa.CheckConstraint("status IN ('IN_REVIEW','ACCEPTED')", name="ck_qra_run_review_status"),
        sa.CheckConstraint(
            "status != 'ACCEPTED' OR (accepted_by IS NOT NULL AND accepted_at IS NOT NULL AND acceptance_hash IS NOT NULL)",
            name="ck_qra_run_review_accepted",
        ),
    )
    for column in ("tenant_id", "run_id"):
        op.create_index(f"ix_qra_run_reviews_{column}", "qra_run_reviews", [column])
    _protection()


def _protection():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        comparison = " OR ".join(f"NEW.{column}::text IS DISTINCT FROM OLD.{column}::text" for column in FROZEN)
        comparison += " OR NEW.runtime_metadata->>'worker_lease_seconds' IS DISTINCT FROM OLD.runtime_metadata->>'worker_lease_seconds'"
        op.execute(f"""CREATE FUNCTION qra_run_history_guard() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'QRA run history cannot be deleted'; END IF;
          IF OLD.status = 'COMPLETED' OR {comparison} THEN
            RAISE EXCEPTION 'QRA completed result or frozen manifest is immutable';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
        op.execute(
            "CREATE TRIGGER qra_run_history_guard BEFORE UPDATE OR DELETE ON qra_runs FOR EACH ROW EXECUTE FUNCTION qra_run_history_guard()"
        )
        op.execute("""CREATE FUNCTION qra_review_history_guard() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' OR OLD.status = 'ACCEPTED' THEN
            RAISE EXCEPTION 'QRA accepted review or review history is immutable';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
        op.execute(
            "CREATE TRIGGER qra_review_history_guard BEFORE UPDATE OR DELETE ON qra_run_reviews FOR EACH ROW EXECUTE FUNCTION qra_review_history_guard()"
        )
    elif dialect == "sqlite":
        comparison = " OR ".join(f"NEW.{column} IS NOT OLD.{column}" for column in FROZEN)
        comparison += " OR json_extract(NEW.runtime_metadata, '$.worker_lease_seconds') IS NOT json_extract(OLD.runtime_metadata, '$.worker_lease_seconds')"
        op.execute(
            f"CREATE TRIGGER qra_run_update_guard BEFORE UPDATE ON qra_runs WHEN OLD.status = 'COMPLETED' OR {comparison} BEGIN SELECT RAISE(ABORT, 'QRA result or manifest is immutable'); END"
        )
        op.execute(
            "CREATE TRIGGER qra_run_delete_guard BEFORE DELETE ON qra_runs BEGIN SELECT RAISE(ABORT, 'QRA history cannot be deleted'); END"
        )
        op.execute(
            "CREATE TRIGGER qra_review_update_guard BEFORE UPDATE ON qra_run_reviews WHEN OLD.status = 'ACCEPTED' BEGIN SELECT RAISE(ABORT, 'QRA accepted review is immutable'); END"
        )
        op.execute(
            "CREATE TRIGGER qra_review_delete_guard BEFORE DELETE ON qra_run_reviews BEGIN SELECT RAISE(ABORT, 'QRA review history cannot be deleted'); END"
        )


def downgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER qra_review_history_guard ON qra_run_reviews")
        op.execute("DROP TRIGGER qra_run_history_guard ON qra_runs")
        op.execute("DROP FUNCTION qra_review_history_guard()")
        op.execute("DROP FUNCTION qra_run_history_guard()")
    elif dialect == "sqlite":
        for name in (
            "qra_review_delete_guard",
            "qra_review_update_guard",
            "qra_run_delete_guard",
            "qra_run_update_guard",
        ):
            op.execute(f"DROP TRIGGER {name}")
    op.drop_table("qra_run_reviews")
    op.drop_table("qra_runs")
