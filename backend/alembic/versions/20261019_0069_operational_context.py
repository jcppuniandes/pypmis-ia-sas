"""O1A canonical binding and common period headers (additive only).

Revision ID: 20261019_0069
Revises: 20261011_0068
"""

import sqlalchemy as sa
from alembic import op

revision = "20261019_0069"
down_revision = "20261011_0068"
branch_labels = None
depends_on = None


def upgrade():
    # Frozen migration-owned schema, not live model metadata.
    op.create_table(
        "operational_project_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("legacy_project_id", sa.Integer(), sa.ForeignKey("projects.id")),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("validated_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("effective_from", sa.DateTime(), nullable=False),
        sa.Column("effective_to", sa.DateTime()),
        sa.UniqueConstraint("tenant_id", "project_workspace_id", "revision", name="uq_operational_binding_revision"),
        sa.CheckConstraint(
            "status IN ('ACTIVE','NO_LEGACY_BINDING_REQUIRED','SUPERSEDED','REVOKED')",
            name="ck_operational_binding_status",
        ),
        sa.CheckConstraint(
            "(status != 'ACTIVE' OR legacy_project_id IS NOT NULL) AND (status != 'NO_LEGACY_BINDING_REQUIRED' OR legacy_project_id IS NULL)",
            name="ck_operational_binding_reference",
        ),
        sa.CheckConstraint("version > 0 AND revision > 0", name="ck_operational_binding_versions"),
        sa.CheckConstraint(
            "(status IN ('ACTIVE','NO_LEGACY_BINDING_REQUIRED') AND effective_to IS NULL) OR (status IN ('SUPERSEDED','REVOKED') AND effective_to IS NOT NULL)",
            name="ck_operational_binding_effective_status",
        ),
    )
    op.create_index(
        "uq_operational_binding_active_workspace",
        "operational_project_bindings",
        ["tenant_id", "project_workspace_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('ACTIVE','NO_LEGACY_BINDING_REQUIRED')"),
        sqlite_where=sa.text("status IN ('ACTIVE','NO_LEGACY_BINDING_REQUIRED')"),
    )
    op.create_index(
        "uq_operational_binding_active_legacy",
        "operational_project_bindings",
        ["tenant_id", "legacy_project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "ix_operational_binding_lookup",
        "operational_project_bindings",
        ["tenant_id", "project_workspace_id", "revision"],
    )
    columns = [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("period_code", sa.String(80), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("profile_code", sa.String(120), nullable=False),
        sa.Column("active_slot", sa.String(100)),
        sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("admin_configurations.id"), nullable=False),
        sa.Column("source_configuration_revision", sa.Integer(), nullable=False),
        sa.Column("source_configuration_hash", sa.String(64), nullable=False),
        sa.Column("schedule_data_date", sa.Date()),
        sa.Column("reopen_parent_id", sa.Integer(), sa.ForeignKey("project_controls_periods.id")),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
    ]
    for stamp in ("opened", "review_started", "closed", "published"):
        columns += [
            sa.Column(f"{stamp}_at", sa.DateTime(), nullable=stamp != "opened"),
            sa.Column(f"{stamp}_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=stamp != "opened"),
        ]
    columns += [
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "project_workspace_id", "period_code", "revision", name="uq_project_controls_period_revision"
        ),
        sa.UniqueConstraint(
            "tenant_id", "project_workspace_id", "profile_code", "active_slot", name="uq_project_controls_active_period"
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','REVIEW','CLOSED','PUBLISHED')", name="ck_project_controls_period_status"
        ),
        sa.CheckConstraint(
            "period_end >= period_start AND version > 0 AND revision > 0", name="ck_project_controls_period_dates"
        ),
        sa.CheckConstraint(
            "(status IN ('OPEN','REVIEW') AND active_slot IS NOT NULL) OR (status IN ('CLOSED','PUBLISHED') AND active_slot IS NULL)",
            name="ck_project_controls_period_active_slot",
        ),
        sa.CheckConstraint(
            "status != 'PUBLISHED' OR (published_at IS NOT NULL AND published_by IS NOT NULL)",
            name="ck_project_controls_period_publication",
        ),
    ]
    op.create_table("project_controls_periods", *columns)
    op.create_index(
        "ix_project_controls_period_lookup",
        "project_controls_periods",
        ["tenant_id", "project_workspace_id", "status", "period_end"],
    )
    op.create_table(
        "operational_context_commands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("command_type", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_operational_context_command_key"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION o1a_guard_history() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE previous jsonb := to_jsonb(OLD); BEGIN
          IF TG_TABLE_NAME = 'project_controls_periods' AND previous->>'status' = 'PUBLISHED' THEN RAISE EXCEPTION 'Published period header is immutable'; END IF;
          IF TG_TABLE_NAME = 'project_controls_periods' AND TG_OP = 'UPDATE' THEN
            IF (to_jsonb(NEW) - ARRAY['status','version','review_started_at','review_started_by','closed_at','closed_by','published_at','published_by','reason','notes','active_slot','snapshot_json']) IS DISTINCT FROM (previous - ARRAY['status','version','review_started_at','review_started_by','closed_at','closed_by','published_at','published_by','reason','notes','active_slot','snapshot_json']) THEN RAISE EXCEPTION 'Period identity/cutoff/policy is immutable'; END IF;
          END IF;
          IF TG_TABLE_NAME = 'operational_context_commands' THEN RAISE EXCEPTION 'Operational command receipt is immutable'; END IF;
          IF TG_TABLE_NAME = 'admin_configurations' AND previous->>'kind' = 'operational_profile' AND previous->>'status' = 'published' THEN RAISE EXCEPTION 'Published Operational Profile is immutable'; END IF;
          IF TG_TABLE_NAME = 'operational_project_bindings' THEN
            IF TG_OP = 'DELETE' OR previous->>'status' IN ('REVOKED','SUPERSEDED') THEN RAISE EXCEPTION 'Operational binding history is immutable'; END IF;
            IF (to_jsonb(NEW) - ARRAY['status','effective_to','version']) IS DISTINCT FROM (previous - ARRAY['status','effective_to','version']) THEN RAISE EXCEPTION 'Operational binding identity is immutable'; END IF;
          END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$""")
        for table in (
            "project_controls_periods",
            "operational_context_commands",
            "admin_configurations",
            "operational_project_bindings",
        ):
            op.execute(
                f"CREATE TRIGGER o1a_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION o1a_guard_history()"
            )
        op.execute("""CREATE FUNCTION o1a_guard_scope() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM enterprise_workspaces w WHERE w.id=NEW.project_workspace_id AND w.tenant_id=NEW.tenant_id AND lower(w.workspace_type_code)='project') THEN RAISE EXCEPTION 'Canonical Project tenant/type mismatch'; END IF;
          IF TG_TABLE_NAME='operational_project_bindings' THEN
            IF NEW.legacy_project_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM projects p WHERE p.id=NEW.legacy_project_id AND p.tenant_id=NEW.tenant_id) THEN RAISE EXCEPTION 'Legacy Project tenant mismatch'; END IF;
          ELSE
            IF NOT EXISTS (SELECT 1 FROM admin_configurations c WHERE c.id=NEW.configuration_id AND c.tenant_id=NEW.tenant_id AND c.kind='operational_profile' AND c.status='published' AND c.revision=NEW.source_configuration_revision AND c.content_hash=NEW.source_configuration_hash) THEN RAISE EXCEPTION 'Published period policy tenant/revision mismatch'; END IF;
          END IF;
          RETURN NEW; END $$""")
        for table in ("operational_project_bindings", "project_controls_periods"):
            op.execute(
                f"CREATE TRIGGER o1a_scope BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION o1a_guard_scope()"
            )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "project_controls_periods",
            "operational_context_commands",
            "admin_configurations",
            "operational_project_bindings",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS o1a_immutable ON {table}")
        for table in ("operational_project_bindings", "project_controls_periods"):
            op.execute(f"DROP TRIGGER IF EXISTS o1a_scope ON {table}")
        op.execute("DROP FUNCTION IF EXISTS o1a_guard_history()")
        op.execute("DROP FUNCTION IF EXISTS o1a_guard_scope()")
    op.drop_table("operational_context_commands")
    op.drop_table("project_controls_periods")
    op.drop_table("operational_project_bindings")
