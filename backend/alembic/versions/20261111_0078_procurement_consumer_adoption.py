"""Add the consumer-owned O2B reference decision ledger."""

import sqlalchemy as sa
from alembic import op

revision = "20261111_0078"
down_revision = "20261111_0077"
branch_labels = None
depends_on = None

TABLE = "operational_procurement_adoptions"


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Procurement adoption requires PostgreSQL guards")
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("project_workspace_id", sa.Integer(), sa.ForeignKey("enterprise_workspaces.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("consumer", sa.String(12), nullable=False),
        sa.Column("source_domain", sa.String(20), nullable=False),
        sa.Column("source_entity_type", sa.String(40), nullable=False),
        sa.Column("source_entity_id", sa.Integer(), nullable=False),
        sa.Column("source_package_id", sa.Integer(), sa.ForeignKey("procurement_packages.id"), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.Date(), nullable=False),
        sa.Column("consumer_status", sa.String(16), nullable=False),
        sa.Column("period_id", sa.Integer(), sa.ForeignKey("project_controls_periods.id")),
        sa.Column("consumer_version_id", sa.Integer(), sa.ForeignKey("forecast_versions.id")),
        sa.Column("consumer_version", sa.Integer()),
        sa.Column("signal_key", sa.String(80)),
        sa.Column("source_forecast_date", sa.Date()),
        sa.Column("context_key", sa.String(180), nullable=False),
        sa.Column("mapping_reference", sa.JSON(), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.CheckConstraint("consumer IN ('COST','PROGRESS','FORECAST')", name="ck_op_proc_adoption_consumer"),
        sa.CheckConstraint(
            "source_domain = 'PROCUREMENT' AND source_version > 0 AND version > 0 AND source_entity_id > 0",
            name="ck_op_proc_adoption_source",
        ),
        sa.CheckConstraint("consumer_status IN ('ADOPTED','NOT_ADOPTED')", name="ck_op_proc_adoption_status"),
        sa.CheckConstraint(
            "(consumer='COST' AND period_id IS NULL AND consumer_version_id IS NULL "
            "AND consumer_version IS NULL AND signal_key IS NULL AND source_forecast_date IS NULL) OR "
            "(consumer='PROGRESS' AND period_id IS NOT NULL AND consumer_version_id IS NULL "
            "AND consumer_version IS NULL AND signal_key IS NULL AND source_forecast_date IS NULL) OR "
            "(consumer='FORECAST' AND period_id IS NOT NULL AND consumer_version_id IS NOT NULL "
            "AND consumer_version IS NOT NULL AND consumer_version > 0 AND signal_key IS NOT NULL "
            "AND source_forecast_date IS NOT NULL)",
            name="ck_op_proc_adoption_context",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "project_workspace_id",
            "consumer",
            "source_entity_type",
            "source_entity_id",
            "context_key",
            "version",
            name="uq_op_proc_adoption_stream",
        ),
    )
    op.create_index("ix_op_proc_adoption_history", TABLE, ["tenant_id", "project_workspace_id", "consumer", "id"])
    for field in ("tenant_id", "project_workspace_id"):
        op.create_index(f"ix_{TABLE}_{field}", TABLE, [field])
    op.execute("""
    CREATE FUNCTION o2b_consumer_adoption_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'Procurement consumer decisions are append-only';
      END IF;
      IF NEW.source_hash !~ '^[0-9a-f]{64}$' OR length(btrim(NEW.reason)) < 3 THEN
        RAISE EXCEPTION 'Procurement consumer decision requires source hash and reason';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM user_accounts u WHERE u.id=NEW.created_by AND u.tenant_id=NEW.tenant_id)
         OR NOT EXISTS (SELECT 1 FROM procurement_packages p WHERE p.id=NEW.source_package_id
            AND p.tenant_id=NEW.tenant_id AND p.project_workspace_id=NEW.project_workspace_id)
         OR NOT EXISTS (SELECT 1 FROM enterprise_workspaces w WHERE w.id=NEW.project_workspace_id
            AND w.tenant_id=NEW.tenant_id AND w.workspace_type_code='project') THEN
        RAISE EXCEPTION 'Procurement consumer tenant and Project mismatch';
      END IF;
      IF NEW.period_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM project_controls_periods p WHERE p.id=NEW.period_id AND p.tenant_id=NEW.tenant_id
        AND p.project_workspace_id=NEW.project_workspace_id
        AND NEW.effective_at BETWEEN p.period_start AND p.period_end
      ) THEN RAISE EXCEPTION 'Procurement consumer period mismatch'; END IF;
      IF NEW.consumer_version_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM forecast_versions f WHERE f.id=NEW.consumer_version_id AND f.tenant_id=NEW.tenant_id
        AND f.project_workspace_id=NEW.project_workspace_id AND f.version=NEW.consumer_version
        AND f.period_id=NEW.period_id AND f.status='DRAFT'
      ) THEN RAISE EXCEPTION 'Procurement consumer forecast draft version mismatch'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER tr_operational_procurement_adoptions_o2b_close
      BEFORE INSERT OR UPDATE OR DELETE ON operational_procurement_adoptions
      FOR EACH ROW EXECUTE FUNCTION o2b_consumer_adoption_guard();
    """)


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM operational_procurement_adoptions)")):
        raise RuntimeError("Refusing to discard governed Procurement adoption decisions")
    op.drop_table(TABLE)
    op.execute("DROP FUNCTION o2b_consumer_adoption_guard()")
