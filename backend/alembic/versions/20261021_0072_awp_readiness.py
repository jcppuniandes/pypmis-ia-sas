"""Canonical AWP execution packages, constraints and readiness. No source backfill.

Revision ID: 20261021_0072
Revises: 20261021_0071
"""

import sqlalchemy as sa
from alembic import op

revision = "20261021_0072"
down_revision = "20261021_0071"
branch_labels = None
depends_on = None

TABLES = (
    "awp_cwas",
    "awp_work_packages",
    "awp_package_mappings",
    "awp_package_dependencies",
    "awp_execution_constraints",
    "awp_constraint_mappings",
    "awp_readiness_assessments",
    "awp_history",
)


def _c(name, kind, target=None, nullable=False):
    return sa.Column(name, kind, *([sa.ForeignKey(target)] if target else []), nullable=nullable)


def _create(name, columns, *, mutable=False, constraints=()):
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), primary_key=True),
        _c("tenant_id", sa.Integer(), "tenants.id"),
        _c("project_workspace_id", sa.Integer(), "enterprise_workspaces.id"),
        _c("version", sa.Integer()),
        _c("created_by", sa.Integer(), "user_accounts.id"),
        _c("created_at", sa.DateTime()),
        *(
            [
                _c("revision", sa.Integer()),
                _c("updated_by", sa.Integer(), "user_accounts.id"),
                _c("updated_at", sa.DateTime()),
            ]
            if mutable
            else []
        ),
        *columns,
        *constraints,
    )
    op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])
    op.create_index(f"ix_{name}_project_workspace_id", name, ["project_workspace_id"])


def _mapping_columns(owner, target):
    return [
        _c(owner, sa.Integer(), target),
        _c("target_kind", sa.String(20)),
        _c("target_id", sa.Integer(), nullable=True),
        _c("schedule_version_id", sa.Integer(), "schedule_versions.id", True),
        _c("activity_external_id", sa.String(160), nullable=True),
        _c("status", sa.String(20)),
        _c("revision", sa.Integer()),
        _c("reason", sa.Text()),
    ]


def upgrade():
    _create(
        "awp_cwas",
        [
            _c("code", sa.String(120)),
            _c("name", sa.String(300)),
            _c("description", sa.Text()),
            _c("area", sa.String(150)),
            _c("zone", sa.String(150)),
            _c("location", sa.String(260)),
            _c("parent_cwa_id", sa.Integer(), "awp_cwas.id", True),
            _c("status", sa.String(24)),
        ],
        mutable=True,
        constraints=[
            sa.UniqueConstraint("tenant_id", "project_workspace_id", "code", name="uq_awp_cwa_code"),
            sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_awp_cwa_status"),
        ],
    )
    _create(
        "awp_work_packages",
        [
            _c("package_code", sa.String(120)),
            _c("package_type", sa.String(80)),
            _c("name", sa.String(300)),
            _c("description", sa.Text()),
            _c("cwa_id", sa.Integer(), "awp_cwas.id", True),
            _c("status", sa.String(30)),
            _c("owner_user_id", sa.Integer(), "user_accounts.id", True),
            _c("responsible_role", sa.String(120)),
            _c("readiness_state", sa.String(30)),
            _c("release_state", sa.String(30)),
            _c("released_by", sa.Integer(), "user_accounts.id", True),
            _c("released_at", sa.DateTime(), nullable=True),
        ],
        mutable=True,
        constraints=[
            sa.UniqueConstraint("tenant_id", "project_workspace_id", "package_code", name="uq_awp_package_code"),
            sa.CheckConstraint(
                "status IN ('DRAFT','PLANNED','UNDER_REVIEW','READY','RELEASED','IN_PROGRESS','COMPLETED','CLOSED','SUPERSEDED')",
                name="ck_awp_package_status",
            ),
            sa.CheckConstraint(
                "readiness_state IN ('NOT_ASSESSED','NOT_READY','PARTIALLY_READY','READY','RELEASED')",
                name="ck_awp_package_readiness",
            ),
            sa.CheckConstraint("release_state IN ('NOT_RELEASED','RELEASED')", name="ck_awp_package_release"),
        ],
    )
    _create(
        "awp_package_mappings",
        [
            *_mapping_columns("work_package_id", "awp_work_packages.id"),
            _c("phase", sa.String(20)),
            _c("lineage_json", sa.JSON()),
        ],
        constraints=[
            sa.CheckConstraint(
                "target_kind IN ('SCOPE','PLAN','ACTIVITY') AND status IN ('ACTIVE','REMOVED') AND phase IN ('EXECUTE','INSTALL','USE','REMOVE')",
                name="ck_awp_package_mapping",
            )
        ],
    )
    _create(
        "awp_package_dependencies",
        [
            _c("predecessor_package_id", sa.Integer(), "awp_work_packages.id"),
            _c("successor_package_id", sa.Integer(), "awp_work_packages.id"),
            _c("dependency_type", sa.String(80)),
            _c("blocking", sa.Boolean()),
            _c("evidence_reference", sa.String(1000)),
            _c("status", sa.String(20)),
            _c("reason", sa.Text()),
        ],
        mutable=True,
        constraints=[
            sa.CheckConstraint(
                "predecessor_package_id<>successor_package_id AND status IN ('ACTIVE','CLEARED','CANCELLED')",
                name="ck_awp_dependency",
            )
        ],
    )
    _create(
        "awp_execution_constraints",
        [
            _c("constraint_type", sa.String(80)),
            _c("code", sa.String(120)),
            _c("title", sa.String(300)),
            _c("description", sa.Text()),
            _c("status", sa.String(24)),
            _c("blocking", sa.Boolean()),
            _c("owner_user_id", sa.Integer(), "user_accounts.id", True),
            _c("due_date", sa.String(80), nullable=True),
            _c("source_domain", sa.String(120)),
            _c("source_reference", sa.String(1000)),
            _c("evidence_reference", sa.String(1000)),
            _c("waiver_reference", sa.String(1000)),
            _c("cleared_by", sa.Integer(), "user_accounts.id", True),
            _c("cleared_at", sa.DateTime(), nullable=True),
        ],
        mutable=True,
        constraints=[
            sa.UniqueConstraint("tenant_id", "project_workspace_id", "code", name="uq_awp_constraint_code"),
            sa.CheckConstraint(
                "status IN ('OPEN','IN_PROGRESS','CLEARED','WAIVED','CANCELLED')", name="ck_awp_constraint_status"
            ),
        ],
    )
    _create(
        "awp_constraint_mappings",
        _mapping_columns("constraint_id", "awp_execution_constraints.id"),
        constraints=[
            sa.CheckConstraint(
                "target_kind IN ('SCOPE','PLAN','ACTIVITY','PACKAGE','CWA') AND status IN ('ACTIVE','REMOVED')",
                name="ck_awp_constraint_mapping",
            )
        ],
    )
    _create(
        "awp_readiness_assessments",
        [
            _c("work_package_id", sa.Integer(), "awp_work_packages.id"),
            _c("as_of", sa.String(80)),
            _c("readiness_state", sa.String(30)),
            _c("blocking_constraints", sa.JSON()),
            _c("open_nonblocking_constraints", sa.JSON()),
            _c("dependency_state", sa.JSON()),
            _c("evidence_state", sa.JSON()),
            _c("dimensions", sa.JSON()),
            _c("source_hashes", sa.JSON()),
            _c("policy_revision", sa.Integer()),
            _c("configuration_id", sa.Integer(), "admin_configurations.id"),
            _c("reason", sa.Text()),
        ],
        constraints=[
            sa.CheckConstraint(
                "readiness_state IN ('NOT_ASSESSED','NOT_READY','PARTIALLY_READY','READY','RELEASED')",
                name="ck_awp_assessment_status",
            )
        ],
    )
    _create(
        "awp_history",
        [
            _c("entity_type", sa.String(80)),
            _c("entity_id", sa.Integer()),
            _c("revision", sa.Integer()),
            _c("snapshot_json", sa.JSON()),
            _c("event_type", sa.String(100)),
            _c("reason", sa.Text()),
        ],
    )
    for table, fields in {
        "awp_package_mappings": ["work_package_id"],
        "awp_package_dependencies": ["predecessor_package_id", "successor_package_id"],
        "awp_constraint_mappings": ["constraint_id"],
        "awp_readiness_assessments": ["work_package_id"],
        "awp_history": ["entity_id"],
    }.items():
        for field in fields:
            op.create_index(f"ix_{table}_{field}", table, [field])
    if op.get_bind().dialect.name == "postgresql":
        _postgres_guards()


def _postgres_guards():
    op.execute("""
    CREATE FUNCTION awp_b1_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE n jsonb; o jsonb; r jsonb; target_table text; target_identity integer; f text;
    BEGIN
      IF TG_TABLE_NAME='admin_configurations' THEN
        IF TG_OP='DELETE' THEN
          IF OLD.kind IN ('awp_profile','four_d_profile') THEN RAISE EXCEPTION 'AWP/4D profile history immutable' USING ERRCODE='23514'; END IF;
          RETURN OLD;
        END IF;
        IF OLD.kind IN ('awp_profile','four_d_profile') AND (OLD.status='published' OR OLD.kind IS DISTINCT FROM NEW.kind)
        THEN RAISE EXCEPTION 'Published AWP/4D profile immutable' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END IF;
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'AWP history cannot be deleted' USING ERRCODE='23514'; END IF;
      n:=to_jsonb(NEW);
      SELECT to_jsonb(w) INTO r FROM enterprise_workspaces w WHERE w.id=NEW.project_workspace_id;
      IF r IS NULL OR (r->>'tenant_id')::integer IS DISTINCT FROM NEW.tenant_id OR lower(r->>'workspace_type_code')<>'project'
      THEN RAISE EXCEPTION 'AWP canonical Project Workspace required' USING ERRCODE='23514'; END IF;
      PERFORM schedule_o1bb_reference('user_accounts',NEW.created_by,NEW.tenant_id,NULL);
      IF TG_OP='UPDATE' THEN
        o:=to_jsonb(OLD);
        IF TG_TABLE_NAME IN ('awp_package_mappings','awp_constraint_mappings','awp_readiness_assessments','awp_history')
        THEN RAISE EXCEPTION 'AWP mappings/assessment/history append only' USING ERRCODE='23514'; END IF;
        IF (o-ARRAY['version','revision','updated_by','updated_at','code','name','description','area','zone','location','parent_cwa_id','status','package_code','package_type','cwa_id','owner_user_id','responsible_role','readiness_state','release_state','released_by','released_at','predecessor_package_id','successor_package_id','dependency_type','blocking','evidence_reference','reason','constraint_type','title','due_date','source_domain','source_reference','waiver_reference','cleared_by','cleared_at']) IS DISTINCT FROM (n-ARRAY['version','revision','updated_by','updated_at','code','name','description','area','zone','location','parent_cwa_id','status','package_code','package_type','cwa_id','owner_user_id','responsible_role','readiness_state','release_state','released_by','released_at','predecessor_package_id','successor_package_id','dependency_type','blocking','evidence_reference','reason','constraint_type','title','due_date','source_domain','source_reference','waiver_reference','cleared_by','cleared_at'])
          OR NEW.version<>OLD.version+1 OR NEW.revision<>OLD.revision+1
        THEN RAISE EXCEPTION 'AWP identity/author immutable; successor version required' USING ERRCODE='23514'; END IF;
      END IF;
      FOREACH f IN ARRAY ARRAY['updated_by','owner_user_id','released_by','cleared_by'] LOOP
        IF n ? f THEN PERFORM schedule_o1bb_reference('user_accounts',(n->>f)::integer,NEW.tenant_id,NULL); END IF;
      END LOOP;
      FOREACH f IN ARRAY ARRAY['cwa_id','parent_cwa_id','work_package_id','predecessor_package_id','successor_package_id','constraint_id','schedule_version_id'] LOOP
        IF n ? f THEN
          target_table:=CASE WHEN f IN ('cwa_id','parent_cwa_id') THEN 'awp_cwas' WHEN f IN ('work_package_id','predecessor_package_id','successor_package_id') THEN 'awp_work_packages' WHEN f='constraint_id' THEN 'awp_execution_constraints' ELSE 'schedule_versions' END;
          PERFORM schedule_o1bb_reference(target_table,(n->>f)::integer,NEW.tenant_id,NEW.project_workspace_id);
        END IF;
      END LOOP;
      IF TG_TABLE_NAME='awp_cwas' THEN
        IF NEW.parent_cwa_id IS NOT NULL THEN
          IF EXISTS(WITH RECURSIVE ancestors(id,parent_cwa_id) AS (SELECT id,parent_cwa_id FROM awp_cwas WHERE id=NEW.parent_cwa_id UNION SELECT c.id,c.parent_cwa_id FROM awp_cwas c JOIN ancestors a ON c.id=a.parent_cwa_id) SELECT 1 FROM ancestors WHERE id=NEW.id)
          THEN RAISE EXCEPTION 'CWA cycle' USING ERRCODE='23514'; END IF;
        END IF;
      END IF;
      IF TG_TABLE_NAME IN ('awp_package_mappings','awp_constraint_mappings') THEN
        IF NEW.target_kind='ACTIVITY' THEN
          IF NEW.target_id IS NOT NULL OR NEW.schedule_version_id IS NULL OR NEW.activity_external_id IS NULL
            OR NOT EXISTS(SELECT 1 FROM schedule_versions s, json_array_elements(s.snapshot_json->'activities') a WHERE s.id=NEW.schedule_version_id AND s.accepted_at IS NOT NULL AND a->>'external_id'=NEW.activity_external_id)
          THEN RAISE EXCEPTION 'AWP accepted existing Activity mapping required' USING ERRCODE='23514'; END IF;
        ELSE
          IF NEW.target_id IS NULL OR NEW.schedule_version_id IS NOT NULL OR NEW.activity_external_id IS NOT NULL
          THEN RAISE EXCEPTION 'AWP canonical target shape invalid' USING ERRCODE='23514'; END IF;
          target_table:=CASE NEW.target_kind WHEN 'SCOPE' THEN 'scope_items' WHEN 'PLAN' THEN 'scope_plan_items' WHEN 'PACKAGE' THEN 'awp_work_packages' WHEN 'CWA' THEN 'awp_cwas' ELSE NULL END;
          IF target_table IS NULL THEN RAISE EXCEPTION 'AWP mapping target invalid' USING ERRCODE='23514'; END IF;
          PERFORM schedule_o1bb_reference(target_table,NEW.target_id,NEW.tenant_id,NEW.project_workspace_id);
        END IF;
      END IF;
      IF TG_TABLE_NAME='awp_readiness_assessments' THEN
        PERFORM schedule_o1bb_reference('admin_configurations',NEW.configuration_id,NEW.tenant_id,NULL);
        IF NOT EXISTS(SELECT 1 FROM admin_configurations p WHERE p.id=NEW.configuration_id AND p.kind='awp_profile' AND p.status='published' AND p.revision=NEW.policy_revision AND p.content_hash=NEW.source_hashes->>'policy')
        THEN RAISE EXCEPTION 'Readiness published policy provenance required' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    """)
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER tr_{table}_b1 BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION awp_b1_guard()"
        )
    op.execute(
        "CREATE TRIGGER tr_awp_four_d_profile_b1 BEFORE UPDATE OR DELETE ON admin_configurations FOR EACH ROW EXECUTE FUNCTION awp_b1_guard()"
    )


def downgrade():
    connection = op.get_bind()
    if any(connection.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar() for table in TABLES):
        raise RuntimeError("Refusing to destroy populated AWP execution/history; preserve and migrate explicitly")
    if connection.dialect.name == "postgresql":
        op.execute("DROP TRIGGER tr_awp_four_d_profile_b1 ON admin_configurations")
        for table in TABLES:
            op.execute(f"DROP TRIGGER tr_{table}_b1 ON {table}")
        op.execute("DROP FUNCTION awp_b1_guard()")
    for table in reversed(TABLES):
        op.drop_table(table)
