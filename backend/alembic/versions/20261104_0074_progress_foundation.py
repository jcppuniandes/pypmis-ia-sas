"""Progress authority and integrated baseline references, additive only.

Revision ID: 20261104_0074
Revises: 20261022_0073
"""

import sqlalchemy as sa
from alembic import op

revision = "20261104_0074"
down_revision = "20261022_0073"
branch_labels = None
depends_on = None

FROZEN_TABLES = [
    {
        "name": "progress_rules",
        "columns": [
            ("code", "String", [120], False, False, [], False),
            ("name", "String", [300], False, False, [], False),
            ("method", "String", [60], False, False, [], False),
            ("steps_json", "JSON", [], False, False, [], False),
            ("ordered", "Boolean", [], False, False, [], False),
            ("scope_natures", "JSON", [], False, False, [], False),
            ("package_types", "JSON", [], False, False, [], False),
            ("measurement_basis", "JSON", [], False, False, [], False),
            ("revision", "Integer", [], False, False, [], False),
            ("supersedes_id", "Integer", [], True, False, ["progress_rules.id"], False),
            ("configuration_id", "Integer", [], False, False, ["admin_configurations.id"], False),
            ("configuration_hash", "String", [64], False, False, [], False),
            ("content_hash", "String", [64], False, False, [], False),
            ("status", "String", [24], False, False, [], False),
            ("updated_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("published_by", "Integer", [], True, False, ["user_accounts.id"], False),
            ("published_at", "DateTime", [False], True, False, [], False),
            ("id", "Integer", [], False, True, [], False),
            ("tenant_id", "Integer", [], False, False, ["tenants.id"], True),
            ("project_workspace_id", "Integer", [], False, False, ["enterprise_workspaces.id"], True),
            ("version", "Integer", [], False, False, [], False),
            ("created_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("created_at", "DateTime", [False], False, False, [], False),
        ],
        "unique": [("uq_progress_rule_revision", ["tenant_id", "project_workspace_id", "code", "revision"])],
        "checks": [],
    },
    {
        "name": "progress_measurements",
        "columns": [
            ("code", "String", [120], False, False, [], False),
            ("name", "String", [300], False, False, [], False),
            ("subject_key", "String", [300], False, False, [], True),
            ("progress_type", "String", [24], False, False, [], False),
            ("method", "String", [60], False, False, [], False),
            ("source_domain", "String", [80], False, False, [], False),
            ("source_reference", "String", [1000], False, False, [], False),
            ("scope_item_id", "Integer", [], True, False, ["scope_items.id"], False),
            ("plan_item_id", "Integer", [], True, False, ["scope_plan_items.id"], False),
            ("work_package_id", "Integer", [], True, False, ["awp_work_packages.id"], False),
            ("activity_external_id", "String", [160], False, False, [], False),
            ("schedule_version_id", "Integer", [], True, False, ["schedule_versions.id"], False),
            ("control_account_id", "Integer", [], True, False, ["cost_control_accounts.id"], False),
            ("wbs_external_id", "String", [160], False, False, [], False),
            ("area", "String", [150], False, False, [], False),
            ("system", "String", [150], False, False, [], False),
            ("discipline", "String", [150], False, False, [], False),
            ("scope_nature", "String", [24], False, False, [], False),
            ("phase", "String", [24], False, False, [], False),
            ("period_id", "Integer", [], False, False, ["project_controls_periods.id"], True),
            ("measurement_date", "Date", [], False, False, [], False),
            ("as_of", "Date", [], False, False, [], False),
            ("numerator", "Numeric", [24, 8], False, False, [], False),
            ("denominator", "Numeric", [24, 8], False, False, [], False),
            ("unit", "String", [40], False, False, [], False),
            ("weight", "Numeric", [24, 8], False, False, [], False),
            ("weighting_basis", "String", [60], False, False, [], False),
            ("progress_value", "Numeric", [24, 8], False, False, [], False),
            ("period_quantity", "Numeric", [24, 8], False, False, [], False),
            ("cumulative_quantity", "Numeric", [24, 8], False, False, [], False),
            ("period_progress", "Numeric", [24, 8], False, False, [], False),
            ("overrun", "Boolean", [], False, False, [], False),
            ("status", "String", [24], False, False, [], False),
            ("revision", "Integer", [], False, False, [], False),
            ("supersedes_id", "Integer", [], True, False, ["progress_measurements.id"], False),
            ("rule_id", "Integer", [], True, False, ["progress_rules.id"], False),
            ("configuration_id", "Integer", [], False, False, ["admin_configurations.id"], False),
            ("configuration_hash", "String", [64], False, False, [], False),
            ("input_json", "JSON", [], False, False, [], False),
            ("source_snapshot", "JSON", [], False, False, [], False),
            ("source_hash", "String", [64], False, False, [], False),
            ("content_hash", "String", [64], False, False, [], False),
            ("evidence_json", "JSON", [], False, False, [], False),
            ("correction_kind", "String", [40], False, False, [], False),
            ("prepared_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("updated_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("reviewed_by", "Integer", [], True, False, ["user_accounts.id"], False),
            ("certified_by", "Integer", [], True, False, ["user_accounts.id"], False),
            ("approved_by", "Integer", [], True, False, ["user_accounts.id"], False),
            ("approved_at", "DateTime", [False], True, False, [], False),
            ("certified_at", "DateTime", [False], True, False, [], False),
            ("reason", "Text", [], False, False, [], False),
            ("id", "Integer", [], False, True, [], False),
            ("tenant_id", "Integer", [], False, False, ["tenants.id"], True),
            ("project_workspace_id", "Integer", [], False, False, ["enterprise_workspaces.id"], True),
            ("version", "Integer", [], False, False, [], False),
            ("created_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("created_at", "DateTime", [False], False, False, [], False),
        ],
        "unique": [("uq_progress_measurement_revision", ["tenant_id", "project_workspace_id", "code", "revision"])],
        "checks": [],
    },
    {
        "name": "progress_history",
        "columns": [
            ("entity_type", "String", [100], False, False, [], False),
            ("entity_id", "Integer", [], False, False, [], True),
            ("revision", "Integer", [], False, False, [], False),
            ("snapshot_json", "JSON", [], False, False, [], False),
            ("event_type", "String", [120], False, False, [], False),
            ("reason", "Text", [], False, False, [], False),
            ("id", "Integer", [], False, True, [], False),
            ("tenant_id", "Integer", [], False, False, ["tenants.id"], True),
            ("project_workspace_id", "Integer", [], False, False, ["enterprise_workspaces.id"], True),
            ("version", "Integer", [], False, False, [], False),
            ("created_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("created_at", "DateTime", [False], False, False, [], False),
        ],
        "unique": [],
        "checks": [],
    },
    {
        "name": "progress_control_baseline_bundles",
        "columns": [
            ("code", "String", [120], False, False, [], False),
            ("name", "String", [300], False, False, [], False),
            ("revision", "Integer", [], False, False, [], False),
            ("supersedes_id", "Integer", [], True, False, ["progress_control_baseline_bundles.id"], False),
            ("status", "String", [30], False, False, [], False),
            ("scope_baseline_id", "Integer", [], False, False, ["scope_baselines.id"], False),
            ("schedule_baseline_id", "Integer", [], False, False, ["schedule_baselines.id"], False),
            ("cost_baseline_id", "Integer", [], False, False, ["cost_baselines.id"], False),
            ("progress_profile_id", "Integer", [], False, False, ["admin_configurations.id"], False),
            ("configuration_hash", "String", [64], False, False, [], False),
            ("effective_date", "Date", [], False, False, [], False),
            ("currency", "String", [8], False, False, [], False),
            ("source_snapshot_json", "JSON", [], False, False, [], False),
            ("content_hash", "String", [64], False, False, [], False),
            ("reviewed_by", "Integer", [], True, False, ["user_accounts.id"], False),
            ("approved_by", "Integer", [], True, False, ["user_accounts.id"], False),
            ("approved_at", "DateTime", [False], True, False, [], False),
            ("updated_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("reason", "Text", [], False, False, [], False),
            ("id", "Integer", [], False, True, [], False),
            ("tenant_id", "Integer", [], False, False, ["tenants.id"], True),
            ("project_workspace_id", "Integer", [], False, False, ["enterprise_workspaces.id"], True),
            ("version", "Integer", [], False, False, [], False),
            ("created_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("created_at", "DateTime", [False], False, False, [], False),
        ],
        "unique": [("uq_progress_control_bundle_revision", ["tenant_id", "project_workspace_id", "code", "revision"])],
        "checks": [("ck_progress_control_bundle_status", "status IN ('DRAFT','UNDER_REVIEW','APPROVED')")],
    },
    {
        "name": "progress_period_snapshots",
        "columns": [
            ("period_id", "Integer", [], False, False, ["project_controls_periods.id"], False),
            ("revision", "Integer", [], False, False, [], False),
            ("status", "String", [24], False, False, [], False),
            ("candidate_snapshot_json", "JSON", [], False, False, [], False),
            ("report_snapshot_json", "JSON", [], False, False, [], False),
            ("content_hash", "String", [64], False, False, [], False),
            ("period_source_hash", "String", [64], False, False, [], False),
            ("frozen_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("frozen_at", "DateTime", [False], False, False, [], False),
            ("closed_by", "Integer", [], True, False, ["user_accounts.id"], False),
            ("closed_at", "DateTime", [False], True, False, [], False),
            ("published_by", "Integer", [], True, False, ["user_accounts.id"], False),
            ("published_at", "DateTime", [False], True, False, [], False),
            ("reason", "Text", [], False, False, [], False),
            ("id", "Integer", [], False, True, [], False),
            ("tenant_id", "Integer", [], False, False, ["tenants.id"], True),
            ("project_workspace_id", "Integer", [], False, False, ["enterprise_workspaces.id"], True),
            ("version", "Integer", [], False, False, [], False),
            ("created_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("created_at", "DateTime", [False], False, False, [], False),
        ],
        "unique": [(None, ["period_id"])],
        "checks": [("ck_progress_period_snapshot_status", "status IN ('FROZEN','CLOSED','PUBLISHED')")],
    },
    {
        "name": "progress_earned_value_snapshots",
        "columns": [
            ("bundle_id", "Integer", [], False, False, ["progress_control_baseline_bundles.id"], False),
            ("period_id", "Integer", [], False, False, ["project_controls_periods.id"], False),
            ("as_of", "Date", [], False, False, [], False),
            ("revision", "Integer", [], False, False, [], False),
            ("status", "String", [30], False, False, [], False),
            ("currency", "String", [8], False, False, [], False),
            ("pv", "Numeric", [24, 8], True, False, [], False),
            ("ev", "Numeric", [24, 8], True, False, [], False),
            ("ac", "Numeric", [24, 8], True, False, [], False),
            ("cpi", "Numeric", [24, 8], True, False, [], False),
            ("spi", "Numeric", [24, 8], True, False, [], False),
            ("snapshot_json", "JSON", [], False, False, [], False),
            ("content_hash", "String", [64], False, False, [], False),
            ("reason", "Text", [], False, False, [], False),
            ("id", "Integer", [], False, True, [], False),
            ("tenant_id", "Integer", [], False, False, ["tenants.id"], True),
            ("project_workspace_id", "Integer", [], False, False, ["enterprise_workspaces.id"], True),
            ("version", "Integer", [], False, False, [], False),
            ("created_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("created_at", "DateTime", [False], False, False, [], False),
        ],
        "unique": [],
        "checks": [("ck_progress_evm_snapshot_status", "status IN ('COMPUTABLE','NOT_COMPUTABLE')")],
    },
]

GUARD_SQL = r"""
CREATE FUNCTION o1bd_progress_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  d jsonb; prior jsonb; ref record; actor bigint; role_field text;
  reference_id bigint; ref_row jsonb; project_row jsonb; period_state text; frozen jsonb;
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Progress authority history cannot be deleted'; END IF;
  d := to_jsonb(NEW);
  IF TG_OP = 'UPDATE' THEN
    prior := to_jsonb(OLD);
    IF TG_TABLE_NAME IN ('progress_history','progress_earned_value_snapshots') OR
       (TG_TABLE_NAME IN ('progress_measurements','progress_control_baseline_bundles') AND prior->>'status' IN ('APPROVED','REJECTED','SUPERSEDED')) OR
       (TG_TABLE_NAME='progress_rules' AND prior->>'status'='PUBLISHED') OR
       (TG_TABLE_NAME='progress_period_snapshots' AND prior->>'status'='PUBLISHED') THEN
      RAISE EXCEPTION 'Progress terminal authority is immutable; create a successor';
    END IF;
    IF d->>'tenant_id' IS DISTINCT FROM prior->>'tenant_id' OR
       d->>'project_workspace_id' IS DISTINCT FROM prior->>'project_workspace_id' OR
       d->>'created_by' IS DISTINCT FROM prior->>'created_by' OR
       d->>'created_at' IS DISTINCT FROM prior->>'created_at' THEN
      RAISE EXCEPTION 'Progress immutable scope and creator';
    END IF;
  END IF;
  SELECT to_jsonb(w) INTO project_row FROM enterprise_workspaces w
    WHERE w.id=(d->>'project_workspace_id')::bigint AND w.tenant_id=(d->>'tenant_id')::bigint;
  IF project_row IS NULL OR project_row->>'workspace_type_code'<>'project' OR
     lower(project_row->>'status')<>'active' THEN RAISE EXCEPTION 'Progress requires same-tenant active Project'; END IF;
  FOREACH role_field IN ARRAY ARRAY['created_by','updated_by','prepared_by','reviewed_by','certified_by','approved_by','published_by','frozen_by','closed_by'] LOOP
    IF d ? role_field AND d->>role_field IS NOT NULL THEN
      actor := (d->>role_field)::bigint;
      IF NOT EXISTS(SELECT 1 FROM user_accounts u WHERE u.id=actor AND u.tenant_id=(d->>'tenant_id')::bigint) THEN
        RAISE EXCEPTION 'Progress cross-tenant actor';
      END IF;
    END IF;
  END LOOP;
  FOR ref IN SELECT * FROM (VALUES
    ('scope_item_id','scope_items'),('plan_item_id','scope_plan_items'),('work_package_id','awp_work_packages'),
    ('control_account_id','cost_control_accounts'),('schedule_version_id','schedule_versions'),
    ('rule_id','progress_rules'),('scope_baseline_id','scope_baselines'),('schedule_baseline_id','schedule_baselines'),
    ('cost_baseline_id','cost_baselines'),('period_id','project_controls_periods'),('bundle_id','progress_control_baseline_bundles')
  ) AS references_catalog(field_name,table_name) LOOP
    IF d ? ref.field_name AND d->>ref.field_name IS NOT NULL THEN
      reference_id := (d->>ref.field_name)::bigint;
      EXECUTE format('SELECT to_jsonb(r) FROM %I r WHERE r.id=$1',ref.table_name) INTO ref_row USING reference_id;
      IF ref_row IS NULL OR ref_row->>'tenant_id' IS DISTINCT FROM d->>'tenant_id' OR
         ref_row->>'project_workspace_id' IS DISTINCT FROM d->>'project_workspace_id' THEN
        RAISE EXCEPTION 'Progress cross-project or cross-tenant reference: %',ref.field_name;
      END IF;
    END IF;
  END LOOP;
  FOREACH role_field IN ARRAY ARRAY['configuration_id','progress_profile_id'] LOOP
    IF d ? role_field AND d->>role_field IS NOT NULL THEN
      SELECT to_jsonb(a) INTO ref_row FROM admin_configurations a WHERE a.id=(d->>role_field)::bigint;
      IF ref_row IS NULL OR ref_row->>'tenant_id' IS DISTINCT FROM d->>'tenant_id' OR
         ref_row->>'kind'<>'progress_profile' OR ref_row->>'status'<>'published' OR
         ref_row->>'content_hash' IS DISTINCT FROM d->>'configuration_hash' THEN
        RAISE EXCEPTION 'Published pinned Progress profile required';
      END IF;
    END IF;
  END LOOP;
  IF d ? 'supersedes_id' AND d->>'supersedes_id' IS NOT NULL THEN
    EXECUTE format('SELECT to_jsonb(r) FROM %I r WHERE r.id=$1',TG_TABLE_NAME) INTO ref_row USING (d->>'supersedes_id')::bigint;
    IF ref_row IS NULL OR ref_row->>'tenant_id' IS DISTINCT FROM d->>'tenant_id' OR
       ref_row->>'project_workspace_id' IS DISTINCT FROM d->>'project_workspace_id' OR
       ref_row->>'status' NOT IN ('APPROVED','PUBLISHED','REJECTED') OR
       (ref_row->>'revision')::integer >= (d->>'revision')::integer THEN
      RAISE EXCEPTION 'Progress predecessor is not a prior immutable revision in the same Project';
    END IF;
  END IF;
  IF TG_TABLE_NAME='progress_rules' THEN
    IF TG_OP='INSERT' AND NEW.status<>'DRAFT' THEN RAISE EXCEPTION 'Progress rule must start in DRAFT'; END IF;
    IF NEW.status NOT IN ('DRAFT','PUBLISHED') THEN RAISE EXCEPTION 'Invalid Progress rule state'; END IF;
    IF jsonb_typeof(NEW.steps_json::jsonb)<>'array' OR jsonb_array_length(NEW.steps_json::jsonb)=0 OR
       (SELECT sum((step->>'weight')::numeric) FROM jsonb_array_elements(NEW.steps_json::jsonb) step)<>100 OR
       EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.steps_json::jsonb) step WHERE (step->>'weight')::numeric<=0) THEN
      RAISE EXCEPTION 'Progress rule weights must be positive and reconcile to100';
    END IF;
    IF NEW.status='PUBLISHED' AND (NEW.published_by IS NULL OR NEW.published_at IS NULL OR
       NEW.published_by=NEW.created_by OR NEW.published_by=(prior->>'updated_by')::bigint) THEN
      RAISE EXCEPTION 'Progress rule independent publication required';
    END IF;
  ELSIF TG_TABLE_NAME='progress_measurements' THEN
    IF NEW.progress_type NOT IN ('QUANTITY','PHYSICAL','WEIGHTED','MILESTONE') OR
       NEW.status NOT IN ('DRAFT','SUBMITTED','UNDER_REVIEW','APPROVED','REJECTED') OR
       NEW.denominator<=0 OR NEW.weight<=0 OR NEW.cumulative_quantity<0 OR NEW.progress_value<0 OR
       (NEW.progress_value>100 AND NOT(NEW.progress_type='QUANTITY' AND NEW.overrun)) THEN
      RAISE EXCEPTION 'Invalid Progress type, value, weighting or denominator';
    END IF;
    SELECT status INTO period_state FROM project_controls_periods WHERE id=NEW.period_id FOR UPDATE;
    IF period_state NOT IN ('OPEN','REVIEW') THEN RAISE EXCEPTION 'Closed or published Progress period'; END IF;
    IF TG_OP='INSERT' AND (period_state<>'OPEN' OR NEW.status<>'DRAFT') THEN
      RAISE EXCEPTION 'Progress capture requires OPEN period and DRAFT';
    END IF;
    IF NEW.measurement_date>NEW.as_of THEN RAISE EXCEPTION 'Progress measurement cannot follow as-of'; END IF;
    IF TG_OP='UPDATE' THEN
      IF NEW.status<>OLD.status AND NOT (
         (OLD.status='DRAFT' AND NEW.status='SUBMITTED') OR
         (OLD.status='SUBMITTED' AND NEW.status IN ('UNDER_REVIEW','REJECTED')) OR
         (OLD.status='UNDER_REVIEW' AND NEW.status IN ('APPROVED','REJECTED'))) THEN
        RAISE EXCEPTION 'Invalid Progress lifecycle transition';
      END IF;
      IF OLD.period_id<>NEW.period_id OR OLD.subject_key<>NEW.subject_key OR OLD.progress_type<>NEW.progress_type THEN
        RAISE EXCEPTION 'Progress identity cannot be edited';
      END IF;
      IF OLD.status<>'DRAFT' AND
         (d - ARRAY['status','version','reviewed_by','certified_by','certified_at','approved_by','approved_at','updated_by','reason']) IS DISTINCT FROM
         (prior - ARRAY['status','version','reviewed_by','certified_by','certified_at','approved_by','approved_at','updated_by','reason']) THEN
        RAISE EXCEPTION 'Submitted Progress inputs are frozen';
      END IF;
      IF period_state='REVIEW' THEN
        SELECT candidate_snapshot_json::jsonb INTO frozen FROM progress_period_snapshots WHERE period_id=NEW.period_id;
        IF frozen IS NULL OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(frozen) c
            WHERE (c->>'id')::bigint=NEW.id AND c->>'content_hash'=NEW.content_hash) THEN
          RAISE EXCEPTION 'Measurement is not part of frozen Progress candidates';
        END IF;
      END IF;
    END IF;
    IF NEW.status='APPROVED' AND (NEW.approved_by IS NULL OR NEW.approved_at IS NULL OR
       NEW.approved_by=NEW.prepared_by OR NEW.approved_by=NEW.updated_by) THEN
      RAISE EXCEPTION 'Independent Progress approval required';
    END IF;
  ELSIF TG_TABLE_NAME='progress_control_baseline_bundles' THEN
    IF TG_OP='INSERT' AND NEW.status<>'DRAFT' THEN
      RAISE EXCEPTION 'Integrated baseline must start in DRAFT';
    END IF;
    IF TG_OP='UPDATE' AND NEW.status<>OLD.status AND NOT (
       (OLD.status='DRAFT' AND NEW.status='UNDER_REVIEW') OR
       (OLD.status='UNDER_REVIEW' AND NEW.status='APPROVED')) THEN
      RAISE EXCEPTION 'Invalid integrated baseline transition';
    END IF;
    IF NEW.status='APPROVED' AND (NEW.approved_by IS NULL OR NEW.approved_at IS NULL OR
       NEW.approved_by=NEW.created_by OR NEW.approved_by=NEW.updated_by) THEN
      RAISE EXCEPTION 'Independent integrated baseline approval required';
    END IF;
    IF NEW.status='APPROVED' AND (
       NOT EXISTS(SELECT 1 FROM scope_baselines b JOIN scope_revisions r ON r.id=b.scope_revision_id
         AND r.tenant_id=b.tenant_id AND r.project_workspace_id=b.project_workspace_id
         WHERE b.id=NEW.scope_baseline_id AND r.status='APPROVED'
         AND b.approved_by IS NOT NULL AND b.approved_at IS NOT NULL) OR
       NOT EXISTS(SELECT 1 FROM schedule_baselines WHERE id=NEW.schedule_baseline_id AND status='APPROVED_BASELINE') OR
       NOT EXISTS(SELECT 1 FROM cost_baselines WHERE id=NEW.cost_baseline_id AND status='APPROVED')) THEN
      RAISE EXCEPTION 'Approved upstream baselines required';
    END IF;
  ELSIF TG_TABLE_NAME='progress_period_snapshots' AND TG_OP='INSERT' THEN
    IF NEW.status<>'FROZEN' THEN RAISE EXCEPTION 'Progress reporting must start in FROZEN review'; END IF;
  ELSIF TG_TABLE_NAME='progress_period_snapshots' AND TG_OP='UPDATE' THEN
    IF NEW.status<>OLD.status AND NOT ((OLD.status='FROZEN' AND NEW.status='CLOSED') OR
       (OLD.status='CLOSED' AND NEW.status='PUBLISHED')) THEN
      RAISE EXCEPTION 'Invalid Progress reporting transition';
    END IF;
    IF (d - ARRAY['status','version','report_snapshot_json','content_hash','closed_by','closed_at','published_by','published_at','reason']) IS DISTINCT FROM
       (prior - ARRAY['status','version','report_snapshot_json','content_hash','closed_by','closed_at','published_by','published_at','reason']) THEN
      RAISE EXCEPTION 'Progress frozen candidate identity is immutable';
    END IF;
    IF OLD.status='CLOSED' AND (NEW.status<>'PUBLISHED' OR NEW.report_snapshot_json::jsonb IS DISTINCT FROM OLD.report_snapshot_json::jsonb OR
       NEW.content_hash<>OLD.content_hash OR NEW.closed_by IS DISTINCT FROM OLD.closed_by OR NEW.closed_at IS DISTINCT FROM OLD.closed_at OR
       NEW.published_by IS NULL OR NEW.published_by=OLD.closed_by) THEN
      RAISE EXCEPTION 'Closed Progress reporting is immutable and needs independent publication';
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION o1bd_progress_profile_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.kind='progress_profile' AND OLD.status='published' THEN
    RAISE EXCEPTION 'Published Progress profile is immutable; use successor';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tr_progress_profile_o1bd BEFORE UPDATE OR DELETE ON admin_configurations
FOR EACH ROW EXECUTE FUNCTION o1bd_progress_profile_guard();

CREATE FUNCTION o1bd_period_consistency() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE p project_controls_periods%ROWTYPE; s progress_period_snapshots%ROWTYPE; period_key bigint;
BEGIN
  IF TG_TABLE_NAME='project_controls_periods' THEN
    period_key := NEW.id;
  ELSE
    period_key := NEW.period_id;
  END IF;
  SELECT * INTO p FROM project_controls_periods WHERE id=period_key;
  IF NOT EXISTS(SELECT 1 FROM progress_history h WHERE h.tenant_id=p.tenant_id AND h.project_workspace_id=p.project_workspace_id) THEN RETURN NEW; END IF;
  SELECT * INTO s FROM progress_period_snapshots WHERE period_id=p.id;
  IF p.status IN ('REVIEW','CLOSED','PUBLISHED') AND (s.id IS NULL OR
     (p.status='REVIEW' AND s.status<>'FROZEN') OR (p.status='CLOSED' AND s.status<>'CLOSED') OR
     (p.status='PUBLISHED' AND s.status<>'PUBLISHED')) THEN
    RAISE EXCEPTION 'O1A period and frozen Progress reporting state must agree';
  END IF;
  RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER tr_progress_period_state_o1bd AFTER INSERT OR UPDATE ON project_controls_periods
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION o1bd_period_consistency();
CREATE CONSTRAINT TRIGGER tr_progress_snapshot_state_o1bd AFTER INSERT OR UPDATE ON progress_period_snapshots
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION o1bd_period_consistency();
"""


def upgrade():
    for spec in FROZEN_TABLES:
        columns = []
        for name, kind, args, nullable, primary, references, _index in spec["columns"]:
            typ = sa.DateTime(timezone=args[0]) if kind == "DateTime" else getattr(sa, kind)(*args)
            columns.append(
                sa.Column(
                    name, typ, *(sa.ForeignKey(ref) for ref in references), nullable=nullable, primary_key=primary
                )
            )
        constraints = [sa.UniqueConstraint(*fields, name=name) for name, fields in spec["unique"]]
        constraints += [sa.CheckConstraint(sql, name=name) for name, sql in spec["checks"]]
        op.create_table(spec["name"], *columns, *constraints)
        for name, _kind, _args, _nullable, _primary, _refs, index in spec["columns"]:
            if index:
                op.create_index(f"ix_{spec['name']}_{name}", spec["name"], [name])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(GUARD_SQL)
        for spec in FROZEN_TABLES:
            op.execute(
                f"CREATE TRIGGER tr_{spec['name']}_o1bd BEFORE INSERT OR UPDATE OR DELETE ON {spec['name']} "
                "FOR EACH ROW EXECUTE FUNCTION o1bd_progress_guard()"
            )


def downgrade():
    connection = op.get_bind()
    for spec in FROZEN_TABLES:
        if connection.scalar(sa.text(f"SELECT count(*) FROM {spec['name']}")):
            raise RuntimeError("Progress authority contains business records; downgrade refused")
    if connection.dialect.name == "postgresql":
        op.execute("DROP TRIGGER tr_progress_profile_o1bd ON admin_configurations")
        op.execute("DROP TRIGGER tr_progress_period_state_o1bd ON project_controls_periods")
    for spec in reversed(FROZEN_TABLES):
        op.drop_table(spec["name"])
    if connection.dialect.name == "postgresql":
        op.execute("DROP FUNCTION o1bd_period_consistency()")
        op.execute("DROP FUNCTION o1bd_progress_profile_guard()")
        op.execute("DROP FUNCTION o1bd_progress_guard()")
