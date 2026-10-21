"""Canonical Scope source, definition and execution decomposition (additive).

Revision ID: 20261020_0070
Revises: 20261019_0069
"""

import sqlalchemy as sa
from alembic import op

revision = "20261020_0070"
down_revision = "20261019_0069"
branch_labels = None
depends_on = None


def _c(name, kind, target=None, nullable=False):
    return sa.Column(name, kind, *([sa.ForeignKey(target)] if target else []), nullable=nullable)


def _create(name, columns, constraints=()):
    # Migration-owned constants, intentionally independent of live ORM metadata.
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


TABLES = (
    "scope_model_versions",
    "scope_bim_objects",
    "scope_excel_imports",
    "scope_items",
    "scope_model_mappings",
    "scope_revisions",
    "scope_baselines",
    "scope_execution_strategies",
    "scope_plan_items",
    "scope_plan_item_links",
    "scope_plan_model_links",
    "scope_derived_model_versions",
)


def upgrade():
    _create(
        "scope_model_versions",
        [
            _c("model_code", sa.String(120)),
            _c("revision", sa.Integer()),
            _c("source_file_name", sa.String(260)),
            _c("source_hash", sa.String(64)),
            _c("source_content", sa.LargeBinary()),
            _c("schema", sa.String(40)),
            _c("units", sa.JSON()),
            _c("status", sa.String(24)),
            _c("is_current", sa.Boolean()),
            _c("supersedes", sa.Integer(), "scope_model_versions.id", True),
            _c("validation_summary", sa.JSON()),
            _c("diff_json", sa.JSON()),
            _c("object_count", sa.Integer()),
            _c("reviewed_by", sa.Integer(), "user_accounts.id", True),
            _c("accepted_by", sa.Integer(), "user_accounts.id", True),
            _c("accepted_at", sa.DateTime(), nullable=True),
            _c("reason", sa.Text()),
        ],
        [
            sa.UniqueConstraint(
                "tenant_id", "project_workspace_id", "model_code", "revision", name="uq_scope_model_revision"
            ),
            sa.CheckConstraint("status IN ('STAGED','REVIEW','ACCEPTED','REJECTED')", name="ck_scope_model_status"),
        ],
    )
    op.create_index(
        "ix_scope_model_current",
        "scope_model_versions",
        ["tenant_id", "project_workspace_id", "model_code", "is_current"],
    )
    op.create_index(
        "uq_scope_model_effective",
        "scope_model_versions",
        ["tenant_id", "project_workspace_id", "model_code"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
        sqlite_where=sa.text("is_current = 1"),
    )
    _create(
        "scope_bim_objects",
        [
            _c("model_version_id", sa.Integer(), "scope_model_versions.id"),
            _c("source_identity", sa.String(160)),
            _c("guid", sa.String(80)),
            _c("express_id", sa.Integer()),
            _c("ifc_class", sa.String(120)),
            _c("name", sa.String(400)),
            _c("properties", sa.JSON()),
            _c("quantities", sa.JSON()),
            _c("classification", sa.JSON()),
            _c("discipline", sa.String(100)),
            _c("level", sa.String(150)),
            _c("area", sa.String(150)),
            _c("zone", sa.String(150)),
            _c("system", sa.String(150)),
            _c("materials", sa.JSON()),
            _c("geometry_reference", sa.JSON()),
        ],
        [sa.UniqueConstraint("model_version_id", "source_identity", name="uq_scope_bim_source_identity")],
    )
    op.create_index("ix_scope_bim_objects_model_version_id", "scope_bim_objects", ["model_version_id"])
    _create(
        "scope_excel_imports",
        [
            _c("source_file_name", sa.String(260)),
            _c("source_hash", sa.String(64)),
            _c("source_content", sa.LargeBinary()),
            _c("field_mapping", sa.JSON()),
            _c("headers", sa.JSON()),
            _c("rows_json", sa.JSON()),
            _c("validation_summary", sa.JSON()),
            _c("status", sa.String(24)),
            _c("candidate_item_ids", sa.JSON()),
            _c("reason", sa.Text()),
        ],
    )
    _create(
        "scope_items",
        [
            _c("scope_item_key", sa.String(80)),
            _c("scope_code", sa.String(120)),
            _c("name", sa.String(300)),
            _c("description", sa.Text()),
            _c("parent_scope_item_id", sa.Integer(), "scope_items.id", True),
            _c("predecessor_id", sa.Integer(), "scope_items.id", True),
            _c("revision", sa.Integer()),
            _c("scope_type", sa.String(100)),
            _c("scope_nature", sa.String(24)),
            _c("discipline", sa.String(100)),
            _c("area", sa.String(150)),
            _c("zone", sa.String(150)),
            _c("system", sa.String(150)),
            _c("location", sa.String(260)),
            _c("quantity", sa.Numeric(24, 8)),
            _c("source_quantity", sa.Numeric(24, 8)),
            _c("approved_quantity", sa.Numeric(24, 8), nullable=True),
            _c("current_quantity", sa.Numeric(24, 8)),
            _c("unit", sa.String(40)),
            _c("measurement_method", sa.String(260)),
            _c("source_type", sa.String(32)),
            _c("source_reference", sa.String(500)),
            _c("source_revision", sa.String(160)),
            _c("lineage_json", sa.JSON()),
            _c("status", sa.String(24)),
            _c("baseline_reference", sa.Integer(), nullable=True),
            _c("effective_from", sa.DateTime()),
            _c("effective_to", sa.DateTime(), nullable=True),
            _c("updated_by", sa.Integer(), "user_accounts.id"),
            _c("updated_at", sa.DateTime()),
        ],
        [
            sa.UniqueConstraint(
                "tenant_id", "project_workspace_id", "scope_code", "revision", name="uq_scope_item_revision"
            ),
            sa.CheckConstraint(
                "scope_nature IN ('INSTALL','REMOVE','TEMPORARY','MAINTENANCE')", name="ck_scope_nature"
            ),
            sa.CheckConstraint(
                "quantity >= 0 AND source_quantity >= 0 AND current_quantity >= 0", name="ck_scope_quantity"
            ),
            sa.CheckConstraint(
                "source_type IN ('IFC','EXCEL','MANUAL','APPROVED_CHANGE')", name="ck_scope_source_type"
            ),
        ],
    )
    op.create_index("ix_scope_items_scope_item_key", "scope_items", ["scope_item_key"])
    _create(
        "scope_model_mappings",
        [
            _c("scope_item_id", sa.Integer(), "scope_items.id"),
            _c("model_object_id", sa.Integer(), "scope_bim_objects.id"),
        ],
        [sa.UniqueConstraint("scope_item_id", "model_object_id", name="uq_scope_model_mapping")],
    )
    _create(
        "scope_revisions",
        [
            _c("revision_code", sa.String(120)),
            _c("revision", sa.Integer()),
            _c("status", sa.String(24)),
            _c("reason", sa.Text()),
            _c("snapshot_json", sa.JSON()),
            _c("content_hash", sa.String(64)),
            _c("configuration_id", sa.Integer(), "admin_configurations.id"),
            _c("reviewed_by", sa.Integer(), "user_accounts.id", True),
            _c("approved_by", sa.Integer(), "user_accounts.id", True),
        ],
        [sa.UniqueConstraint("tenant_id", "project_workspace_id", "revision_code", name="uq_scope_revision_code")],
    )
    _create(
        "scope_baselines",
        [
            _c("scope_revision_id", sa.Integer(), "scope_revisions.id"),
            _c("revision", sa.Integer()),
            _c("original_baseline_id", sa.Integer(), "scope_baselines.id", True),
            _c("previous_baseline_id", sa.Integer(), "scope_baselines.id", True),
            _c("snapshot_json", sa.JSON()),
            _c("content_hash", sa.String(64)),
            _c("approved_by", sa.Integer(), "user_accounts.id"),
            _c("approved_at", sa.DateTime()),
        ],
        [
            sa.UniqueConstraint("scope_revision_id", name="uq_scope_baseline_source_revision"),
            sa.UniqueConstraint("tenant_id", "project_workspace_id", "revision", name="uq_scope_baseline_revision"),
        ],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_scope_item_baseline", "scope_items", "scope_baselines", ["baseline_reference"], ["id"]
        )
    _create(
        "scope_execution_strategies",
        [
            _c("code", sa.String(120)),
            _c("name", sa.String(300)),
            _c("revision", sa.Integer()),
            _c("status", sa.String(24)),
            _c("reason", sa.Text()),
            _c("predecessor_id", sa.Integer(), "scope_execution_strategies.id", True),
            _c("paths_json", sa.JSON()),
            _c("segmentation_rules", sa.JSON()),
            _c("settings_json", sa.JSON()),
            _c("published_by", sa.Integer(), "user_accounts.id", True),
            _c("content_hash", sa.String(64)),
        ],
        [
            sa.UniqueConstraint(
                "tenant_id", "project_workspace_id", "code", "revision", name="uq_scope_strategy_revision"
            )
        ],
    )
    _create(
        "scope_plan_items",
        [
            _c("code", sa.String(120)),
            _c("name", sa.String(300)),
            _c("parent_plan_item_id", sa.Integer(), "scope_plan_items.id", True),
            _c("strategy_id", sa.Integer(), "scope_execution_strategies.id", True),
            _c("status", sa.String(24)),
            _c("operation", sa.String(30)),
            _c("reason", sa.Text()),
            _c("supersedes_ids", sa.JSON()),
            _c("future_mappings", sa.JSON()),
            _c("rule_json", sa.JSON()),
            _c("published_by", sa.Integer(), "user_accounts.id", True),
            _c("content_hash", sa.String(64)),
        ],
    )
    _create(
        "scope_plan_item_links",
        [
            _c("plan_item_id", sa.Integer(), "scope_plan_items.id"),
            _c("scope_item_id", sa.Integer(), "scope_items.id"),
            _c("quantity", sa.Numeric(24, 8)),
            _c("unit", sa.String(40)),
        ],
        [
            sa.UniqueConstraint("plan_item_id", "scope_item_id", name="uq_scope_plan_allocation"),
            sa.CheckConstraint("quantity > 0", name="ck_scope_plan_allocation_quantity"),
        ],
    )
    _create(
        "scope_plan_model_links",
        [
            _c("plan_item_id", sa.Integer(), "scope_plan_items.id"),
            _c("model_object_id", sa.Integer(), "scope_bim_objects.id"),
        ],
        [sa.UniqueConstraint("plan_item_id", "model_object_id", name="uq_scope_plan_model_link")],
    )
    _create(
        "scope_derived_model_versions",
        [
            _c("revision", sa.Integer()),
            _c("predecessor_id", sa.Integer(), "scope_derived_model_versions.id", True),
            _c("representation_type", sa.String(40)),
            _c("reason", sa.Text()),
            _c("snapshot_json", sa.JSON()),
            _c("content_hash", sa.String(64)),
        ],
    )
    for table, columns in {
        "scope_model_mappings": ["scope_item_id", "model_object_id"],
        "scope_plan_item_links": ["plan_item_id", "scope_item_id"],
        "scope_plan_model_links": ["plan_item_id", "model_object_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    if op.get_bind().dialect.name == "postgresql":
        _postgresql_guards()


def _postgresql_guards():
    op.execute("""CREATE FUNCTION scope_o1ba_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE project_tenant integer; parent_tenant integer; parent_project integer; ref jsonb; field text; target_table text;
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Scope history cannot be deleted'; END IF;
      SELECT tenant_id INTO project_tenant FROM enterprise_workspaces WHERE id=NEW.project_workspace_id AND lower(workspace_type_code)='project';
      IF project_tenant IS DISTINCT FROM NEW.tenant_id THEN RAISE EXCEPTION 'Canonical Scope tenant/project mismatch'; END IF;
      IF TG_OP = 'UPDATE' THEN
        IF TG_TABLE_NAME IN ('scope_bim_objects','scope_model_mappings','scope_baselines','scope_plan_item_links','scope_plan_model_links','scope_derived_model_versions') THEN
          RAISE EXCEPTION 'Scope immutable source/snapshot';
        ELSIF TG_TABLE_NAME IN ('scope_model_versions','scope_excel_imports') THEN
          IF (to_jsonb(OLD)-ARRAY['status','version','reason','reviewed_by','accepted_by','accepted_at','is_current','candidate_item_ids'])
             IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['status','version','reason','reviewed_by','accepted_by','accepted_at','is_current','candidate_item_ids']) THEN
             RAISE EXCEPTION 'Original Scope source is immutable'; END IF;
        ELSIF TG_TABLE_NAME = 'scope_items' AND OLD.status = 'APPROVED' THEN RAISE EXCEPTION 'Approved Scope Item is immutable';
        ELSIF TG_TABLE_NAME IN ('scope_revisions','scope_execution_strategies') AND OLD.status IN ('APPROVED','PUBLISHED') THEN RAISE EXCEPTION 'Published Scope state is immutable';
        ELSIF TG_TABLE_NAME = 'scope_plan_items' AND OLD.status IN ('PUBLISHED','SUPERSEDED') AND
          (to_jsonb(OLD)-ARRAY['status','version']) IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['status','version']) THEN RAISE EXCEPTION 'Published Plan Item content immutable';
        END IF;
      END IF;
      ref := to_jsonb(NEW);
      FOR field,target_table IN SELECT * FROM (VALUES
        ('model_version_id','scope_model_versions'),('model_object_id','scope_bim_objects'),
        ('scope_item_id','scope_items'),('parent_scope_item_id','scope_items'),
        ('scope_revision_id','scope_revisions'),('baseline_reference','scope_baselines'),
        ('plan_item_id','scope_plan_items'),('parent_plan_item_id','scope_plan_items'),
        ('strategy_id','scope_execution_strategies')) AS refs(field,target_table)
      LOOP
        IF ref ? field AND ref->>field IS NOT NULL THEN
          EXECUTE format('SELECT tenant_id,project_workspace_id FROM %I WHERE id=$1',target_table)
            INTO parent_tenant,parent_project USING (ref->>field)::integer;
          IF parent_tenant IS DISTINCT FROM NEW.tenant_id OR parent_project IS DISTINCT FROM NEW.project_workspace_id THEN RAISE EXCEPTION 'Scope cross-project reference denied'; END IF;
        END IF;
      END LOOP;
      IF ref ? 'predecessor_id' AND ref->>'predecessor_id' IS NOT NULL THEN
        EXECUTE format('SELECT tenant_id,project_workspace_id FROM %I WHERE id=$1',TG_TABLE_NAME)
          INTO parent_tenant,parent_project USING (ref->>'predecessor_id')::integer;
        IF parent_tenant IS DISTINCT FROM NEW.tenant_id OR parent_project IS DISTINCT FROM NEW.project_workspace_id THEN RAISE EXCEPTION 'Scope predecessor reference mismatch'; END IF;
      END IF;
      FOR field,target_table IN SELECT * FROM (VALUES
        ('supersedes','scope_model_versions'),('original_baseline_id','scope_baselines'),('previous_baseline_id','scope_baselines')) AS history(field,target_table)
      LOOP
        IF ref ? field AND ref->>field IS NOT NULL THEN
          EXECUTE format('SELECT tenant_id,project_workspace_id FROM %I WHERE id=$1',target_table)
            INTO parent_tenant,parent_project USING (ref->>field)::integer;
          IF parent_tenant IS DISTINCT FROM NEW.tenant_id OR parent_project IS DISTINCT FROM NEW.project_workspace_id THEN RAISE EXCEPTION 'Scope historical reference mismatch'; END IF;
        END IF;
      END LOOP;
      IF TG_TABLE_NAME='scope_revisions' THEN
        IF NOT EXISTS(SELECT 1 FROM admin_configurations WHERE id=NEW.configuration_id AND tenant_id=NEW.tenant_id AND kind='scope_profile' AND status='published')
          THEN RAISE EXCEPTION 'Published tenant Scope Profile required'; END IF;
      END IF;
      IF NEW.version < 1 THEN RAISE EXCEPTION 'Positive Scope version required'; END IF;
      RETURN NEW;
    END $$""")
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION scope_o1ba_guard()"
        )
    op.execute("""CREATE FUNCTION scope_o1ba_profile_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN IF OLD.kind='scope_profile' AND OLD.status='published' THEN RAISE EXCEPTION 'Published Scope Profile immutable'; END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER scope_o1ba_profile_immutable BEFORE UPDATE OR DELETE ON admin_configurations FOR EACH ROW EXECUTE FUNCTION scope_o1ba_profile_guard()"
    )


def downgrade():
    for table in TABLES:
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")):
            raise RuntimeError("Refusing to delete populated Scope history; restore/review a backup instead")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS scope_o1ba_profile_immutable ON admin_configurations")
        op.execute("DROP FUNCTION IF EXISTS scope_o1ba_profile_guard()")
        op.drop_constraint("fk_scope_item_baseline", "scope_items", type_="foreignkey")
    for table in reversed(TABLES):
        op.drop_table(table)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS scope_o1ba_guard()")
