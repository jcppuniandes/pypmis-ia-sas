"""Canonical downstream Schedule foundation, additive and source preserving.

Revision ID: 20261021_0071
Revises: 20261020_0070
"""

import sqlalchemy as sa
from alembic import op

revision = "20261021_0071"
down_revision = "20261020_0070"
branch_labels = None
depends_on = None

TABLES = (
    "schedule_registers",
    "schedule_versions",
    "schedule_scope_plan_mappings",
    "schedule_baselines",
    "schedule_export_manifests",
    "schedule_period_associations",
)


def _c(name, kind, target=None, nullable=False):
    return sa.Column(name, kind, *([sa.ForeignKey(target)] if target else []), nullable=nullable)


def _create(name, columns, constraints=()):
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), primary_key=True),
        _c("tenant_id", sa.Integer(), "tenants.id"),
        _c("project_workspace_id", sa.Integer(), "enterprise_workspaces.id"),
        _c("version", sa.Integer()),
        _c("created_by", sa.Integer(), "user_accounts.id"),
        _c("created_at", sa.DateTime()),
        *columns,
        *constraints,
    )
    op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
    op.create_index(f"ix_{name}_project_workspace_id", name, ["project_workspace_id"])


def upgrade():
    _create(
        "schedule_registers",
        [
            _c("schedule_code", sa.String(120)),
            _c("name", sa.String(300)),
            _c("schedule_type", sa.String(100)),
            _c("purpose", sa.Text()),
            _c("source_system", sa.String(80)),
            _c("status", sa.String(24)),
            _c("calendar_basis", sa.String(120)),
            _c("timezone", sa.String(80)),
            _c("current_version_id", sa.Integer(), nullable=True),
            _c("baseline_version_id", sa.Integer(), nullable=True),
        ],
        [sa.UniqueConstraint("tenant_id", "project_workspace_id", "schedule_code", name="uq_schedule_register_code")],
    )
    _create(
        "schedule_versions",
        [
            _c("register_id", sa.Integer(), "schedule_registers.id"),
            _c("revision", sa.Integer()),
            _c("predecessor_version_id", sa.Integer(), "schedule_versions.id", True),
            _c("scope_baseline_id", sa.Integer(), "scope_baselines.id"),
            _c("configuration_id", sa.Integer(), "admin_configurations.id"),
            _c("configuration_hash", sa.String(64)),
            _c("kind", sa.String(40)),
            _c("status", sa.String(32)),
            _c("data_date", sa.String(80)),
            _c("source_file_name", sa.String(260)),
            _c("source_format", sa.String(40)),
            _c("source_hash", sa.String(64)),
            _c("source_content", sa.LargeBinary()),
            _c("snapshot_json", sa.JSON()),
            _c("content_hash", sa.String(64)),
            _c("import_manifest_json", sa.JSON()),
            _c("validation_json", sa.JSON()),
            _c("diff_json", sa.JSON()),
            _c("health_json", sa.JSON()),
            _c("accepted_mapping_hash", sa.String(64), nullable=True),
            _c("reviewed_by", sa.Integer(), "user_accounts.id", True),
            _c("reviewed_at", sa.DateTime(), nullable=True),
            _c("accepted_by", sa.Integer(), "user_accounts.id", True),
            _c("accepted_at", sa.DateTime(), nullable=True),
            _c("last_material_editor", sa.Integer(), "user_accounts.id"),
            _c("reason", sa.Text()),
        ],
        [
            sa.UniqueConstraint("register_id", "revision", name="uq_schedule_version_revision"),
            sa.CheckConstraint(
                "status IN ('DRAFT','STAGED','VALIDATED','UNDER_REVIEW','ACCEPTED_CURRENT','SUPERSEDED','REJECTED')",
                name="ck_schedule_version_status",
            ),
        ],
    )
    with op.batch_alter_table("schedule_registers") as batch:
        batch.create_foreign_key("fk_schedule_register_current", "schedule_versions", ["current_version_id"], ["id"])
        batch.create_foreign_key("fk_schedule_register_baseline", "schedule_versions", ["baseline_version_id"], ["id"])
    _create(
        "schedule_scope_plan_mappings",
        [
            _c("schedule_version_id", sa.Integer(), "schedule_versions.id"),
            _c("target_kind", sa.String(20)),
            _c("target_external_id", sa.String(160)),
            _c("revision", sa.Integer()),
            _c("status", sa.String(30)),
            _c("plan_item_ids", sa.JSON()),
            _c("scope_item_ids", sa.JSON()),
            _c("lineage_json", sa.JSON()),
            _c("reason", sa.Text()),
        ],
        [
            sa.UniqueConstraint(
                "schedule_version_id",
                "target_kind",
                "target_external_id",
                "revision",
                name="uq_schedule_mapping_revision",
            ),
            sa.CheckConstraint("target_kind IN ('WBS','ACTIVITY')", name="ck_schedule_mapping_target"),
            sa.CheckConstraint(
                "status IN ('VALID','STALE','BROKEN','REQUIRES_REVIEW','REMOVED')", name="ck_schedule_mapping_status"
            ),
        ],
    )
    _create(
        "schedule_baselines",
        [
            _c("register_id", sa.Integer(), "schedule_registers.id"),
            _c("schedule_version_id", sa.Integer(), "schedule_versions.id"),
            _c("baseline_type", sa.String(80)),
            _c("revision", sa.Integer()),
            _c("previous_baseline_id", sa.Integer(), "schedule_baselines.id", True),
            _c("status", sa.String(32)),
            _c("snapshot_json", sa.JSON()),
            _c("content_hash", sa.String(64)),
            _c("configuration_id", sa.Integer(), "admin_configurations.id"),
            _c("reviewed_by", sa.Integer(), "user_accounts.id", True),
            _c("approved_by", sa.Integer(), "user_accounts.id", True),
            _c("approved_at", sa.DateTime(), nullable=True),
            _c("reason", sa.Text()),
        ],
        [
            sa.UniqueConstraint("register_id", "revision", name="uq_schedule_baseline_revision"),
            sa.CheckConstraint(
                "status IN ('BASELINE_CANDIDATE','SUBMITTED','UNDER_REVIEW','APPROVED_BASELINE','REJECTED')",
                name="ck_schedule_baseline_status",
            ),
        ],
    )
    _create(
        "schedule_export_manifests",
        [
            _c("schedule_version_id", sa.Integer(), "schedule_versions.id"),
            _c("baseline_id", sa.Integer(), "schedule_baselines.id", True),
            _c("purpose", sa.String(30)),
            _c("source_file_name", sa.String(260)),
            _c("source_hash", sa.String(64)),
            _c("source_content", sa.LargeBinary()),
            _c("manifest_json", sa.JSON()),
            _c("reason", sa.Text()),
        ],
    )
    _create(
        "schedule_period_associations",
        [
            _c("schedule_version_id", sa.Integer(), "schedule_versions.id"),
            _c("period_id", sa.Integer(), "project_controls_periods.id"),
            _c("snapshot_json", sa.JSON()),
            _c("reason", sa.Text()),
        ],
        [sa.UniqueConstraint("schedule_version_id", "period_id", name="uq_schedule_period_association")],
    )
    for name, columns in {
        "schedule_versions": ["register_id"],
        "schedule_scope_plan_mappings": ["schedule_version_id"],
        "schedule_baselines": ["register_id", "schedule_version_id"],
        "schedule_export_manifests": ["schedule_version_id"],
        "schedule_period_associations": ["schedule_version_id", "period_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{name}_{column}", name, [column])
    if op.get_bind().dialect.name == "postgresql":
        _postgres_guards()


def _postgres_guards():
    op.execute("""
    CREATE FUNCTION schedule_o1bb_reference(p_table text, p_id integer, p_tenant integer, p_project integer)
    RETURNS void LANGUAGE plpgsql AS $$
    DECLARE r jsonb;
    BEGIN
      IF p_id IS NULL THEN RETURN; END IF;
      EXECUTE format('SELECT to_jsonb(t) FROM %I t WHERE id=$1',p_table) INTO r USING p_id;
      IF r IS NULL OR (r->>'tenant_id')::integer IS DISTINCT FROM p_tenant
        OR (p_project IS NOT NULL AND (r->>'project_workspace_id')::integer IS DISTINCT FROM p_project)
      THEN RAISE EXCEPTION 'Schedule reference tenant/Project mismatch %',p_table USING ERRCODE='23514'; END IF;
    END $$;
    CREATE FUNCTION schedule_o1bb_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE n jsonb; o jsonb; r jsonb; identity integer; mutable text[];
    BEGIN
      IF TG_TABLE_NAME='admin_configurations' THEN
        IF TG_OP='DELETE' THEN
          IF OLD.kind='schedule_profile' THEN RAISE EXCEPTION 'Schedule Profile history is immutable' USING ERRCODE='23514'; END IF;
          RETURN OLD;
        END IF;
        IF OLD.kind='schedule_profile' AND (OLD.status='published' OR NEW.kind IS DISTINCT FROM OLD.kind)
        THEN RAISE EXCEPTION 'Published Schedule Profile is immutable' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END IF;
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Schedule history cannot be deleted' USING ERRCODE='23514'; END IF;
      n:=to_jsonb(NEW);
      SELECT to_jsonb(w) INTO r FROM enterprise_workspaces w WHERE w.id=NEW.project_workspace_id;
      IF r IS NULL OR (r->>'tenant_id')::integer IS DISTINCT FROM NEW.tenant_id OR lower(r->>'workspace_type_code')<>'project'
      THEN RAISE EXCEPTION 'Schedule requires canonical Project Workspace' USING ERRCODE='23514'; END IF;
      PERFORM schedule_o1bb_reference('user_accounts',NEW.created_by,NEW.tenant_id,NULL);
      IF TG_OP='UPDATE' THEN
        o:=to_jsonb(OLD);
        IF (o->>'tenant_id') IS DISTINCT FROM (n->>'tenant_id') OR (o->>'project_workspace_id') IS DISTINCT FROM (n->>'project_workspace_id') OR (o->>'created_by') IS DISTINCT FROM (n->>'created_by') OR (o->>'created_at') IS DISTINCT FROM (n->>'created_at')
        THEN RAISE EXCEPTION 'Schedule identity/author immutable' USING ERRCODE='23514'; END IF;
        IF TG_TABLE_NAME IN ('schedule_scope_plan_mappings','schedule_export_manifests','schedule_period_associations')
        THEN RAISE EXCEPTION 'Schedule mapping/export/period history immutable' USING ERRCODE='23514'; END IF;
        IF TG_TABLE_NAME='schedule_versions' THEN
          IF OLD.status IN ('SUPERSEDED','REJECTED') OR (OLD.status='ACCEPTED_CURRENT' AND NEW.status<>'SUPERSEDED')
          THEN RAISE EXCEPTION 'Accepted/rejected Schedule immutable' USING ERRCODE='23514'; END IF;
          mutable:=CASE WHEN OLD.status='ACCEPTED_CURRENT' THEN ARRAY['status','version'] ELSE ARRAY['status','version','validation_json','diff_json','health_json','accepted_mapping_hash','reviewed_by','reviewed_at','accepted_by','accepted_at','last_material_editor'] END;
          IF (o-mutable) IS DISTINCT FROM (n-mutable) THEN RAISE EXCEPTION 'Schedule source snapshot immutable' USING ERRCODE='23514'; END IF;
        ELSIF TG_TABLE_NAME='schedule_baselines' THEN
          IF OLD.status='APPROVED_BASELINE' OR (o-ARRAY['status','version','reviewed_by','approved_by','approved_at']) IS DISTINCT FROM (n-ARRAY['status','version','reviewed_by','approved_by','approved_at'])
          THEN RAISE EXCEPTION 'Schedule baseline snapshot immutable' USING ERRCODE='23514'; END IF;
        END IF;
      END IF;
      IF n ? 'register_id' THEN PERFORM schedule_o1bb_reference('schedule_registers',(n->>'register_id')::integer,NEW.tenant_id,NEW.project_workspace_id); END IF;
      IF n ? 'schedule_version_id' THEN
        PERFORM schedule_o1bb_reference('schedule_versions',(n->>'schedule_version_id')::integer,NEW.tenant_id,NEW.project_workspace_id);
        IF n ? 'register_id' THEN
          SELECT to_jsonb(v) INTO r FROM schedule_versions v WHERE v.id=(n->>'schedule_version_id')::integer;
          IF (r->>'register_id') IS DISTINCT FROM (n->>'register_id') THEN RAISE EXCEPTION 'Schedule stream mismatch' USING ERRCODE='23514'; END IF;
        END IF;
      END IF;
      IF TG_TABLE_NAME='schedule_registers' THEN
        FOREACH identity IN ARRAY ARRAY[NEW.current_version_id,NEW.baseline_version_id] LOOP
          PERFORM schedule_o1bb_reference('schedule_versions',identity,NEW.tenant_id,NEW.project_workspace_id);
          IF identity IS NOT NULL AND NOT EXISTS(SELECT 1 FROM schedule_versions v WHERE v.id=identity AND v.register_id=NEW.id)
          THEN RAISE EXCEPTION 'Schedule pointer stream mismatch' USING ERRCODE='23514'; END IF;
        END LOOP;
      ELSIF TG_TABLE_NAME='schedule_versions' THEN
        PERFORM schedule_o1bb_reference('scope_baselines',NEW.scope_baseline_id,NEW.tenant_id,NEW.project_workspace_id);
        PERFORM schedule_o1bb_reference('admin_configurations',NEW.configuration_id,NEW.tenant_id,NULL);
        IF NOT EXISTS(SELECT 1 FROM admin_configurations c WHERE c.id=NEW.configuration_id AND c.kind='schedule_profile' AND c.status='published' AND c.content_hash=NEW.configuration_hash)
        THEN RAISE EXCEPTION 'Published Schedule Profile required' USING ERRCODE='23514'; END IF;
        PERFORM schedule_o1bb_reference('schedule_versions',NEW.predecessor_version_id,NEW.tenant_id,NEW.project_workspace_id);
        IF NEW.predecessor_version_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM schedule_versions v WHERE v.id=NEW.predecessor_version_id AND v.register_id=NEW.register_id)
        THEN RAISE EXCEPTION 'Schedule predecessor stream mismatch' USING ERRCODE='23514'; END IF;
        FOREACH identity IN ARRAY ARRAY[NEW.last_material_editor,NEW.reviewed_by,NEW.accepted_by] LOOP PERFORM schedule_o1bb_reference('user_accounts',identity,NEW.tenant_id,NULL); END LOOP;
      ELSIF TG_TABLE_NAME='schedule_scope_plan_mappings' THEN
        IF NOT EXISTS(SELECT 1 FROM schedule_versions v WHERE v.id=NEW.schedule_version_id AND v.status IN ('DRAFT','STAGED','VALIDATED','UNDER_REVIEW'))
        THEN RAISE EXCEPTION 'Accepted Schedule mappings immutable' USING ERRCODE='23514'; END IF;
        FOR identity IN SELECT value::integer FROM json_array_elements_text(NEW.plan_item_ids) LOOP PERFORM schedule_o1bb_reference('scope_plan_items',identity,NEW.tenant_id,NEW.project_workspace_id); END LOOP;
        FOR identity IN SELECT value::integer FROM json_array_elements_text(NEW.scope_item_ids) LOOP PERFORM schedule_o1bb_reference('scope_items',identity,NEW.tenant_id,NEW.project_workspace_id); END LOOP;
        FOR identity IN SELECT value::integer FROM jsonb_array_elements_text(COALESCE(NEW.lineage_json::jsonb->'resolved_scope_item_ids','[]'::jsonb)) LOOP PERFORM schedule_o1bb_reference('scope_items',identity,NEW.tenant_id,NEW.project_workspace_id); END LOOP;
      ELSIF TG_TABLE_NAME='schedule_baselines' THEN
        PERFORM schedule_o1bb_reference('admin_configurations',NEW.configuration_id,NEW.tenant_id,NULL);
        PERFORM schedule_o1bb_reference('schedule_baselines',NEW.previous_baseline_id,NEW.tenant_id,NEW.project_workspace_id);
        IF NEW.previous_baseline_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM schedule_baselines b WHERE b.id=NEW.previous_baseline_id AND b.register_id=NEW.register_id)
        THEN RAISE EXCEPTION 'Schedule baseline stream mismatch' USING ERRCODE='23514'; END IF;
        FOREACH identity IN ARRAY ARRAY[NEW.reviewed_by,NEW.approved_by] LOOP PERFORM schedule_o1bb_reference('user_accounts',identity,NEW.tenant_id,NULL); END LOOP;
      ELSIF TG_TABLE_NAME='schedule_export_manifests' THEN
        PERFORM schedule_o1bb_reference('schedule_baselines',NEW.baseline_id,NEW.tenant_id,NEW.project_workspace_id);
        IF NEW.baseline_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM schedule_baselines b WHERE b.id=NEW.baseline_id AND b.schedule_version_id=NEW.schedule_version_id)
        THEN RAISE EXCEPTION 'Schedule export baseline mismatch' USING ERRCODE='23514'; END IF;
      ELSIF TG_TABLE_NAME='schedule_period_associations' THEN
        PERFORM schedule_o1bb_reference('project_controls_periods',NEW.period_id,NEW.tenant_id,NEW.project_workspace_id);
      END IF;
      RETURN NEW;
    END $$;
    """)
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER tr_{table}_o1bb BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION schedule_o1bb_guard()"
        )
    op.execute(
        "CREATE TRIGGER tr_schedule_profile_o1bb BEFORE UPDATE OR DELETE ON admin_configurations FOR EACH ROW EXECUTE FUNCTION schedule_o1bb_guard()"
    )


def downgrade():
    connection = op.get_bind()
    if any(connection.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar() for table in TABLES):
        raise RuntimeError("Refusing to destroy populated Schedule source/history; preserve and migrate explicitly")
    if connection.dialect.name == "postgresql":
        op.execute("DROP TRIGGER tr_schedule_profile_o1bb ON admin_configurations")
        for table in TABLES:
            op.execute(f"DROP TRIGGER tr_{table}_o1bb ON {table}")
        op.execute("DROP FUNCTION schedule_o1bb_guard()")
        op.execute("DROP FUNCTION schedule_o1bb_reference(text,integer,integer,integer)")
    with op.batch_alter_table("schedule_registers") as batch:
        batch.drop_constraint("fk_schedule_register_current", type_="foreignkey")
        batch.drop_constraint("fk_schedule_register_baseline", type_="foreignkey")
    for table in reversed(TABLES):
        op.drop_table(table)
