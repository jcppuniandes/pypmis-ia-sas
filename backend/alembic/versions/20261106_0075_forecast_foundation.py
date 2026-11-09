"""Governed Forecast projection and immutable reporting, additive only.

Revision ID: 20261106_0075
Revises: 20261104_0074
"""

import sqlalchemy as sa
from alembic import op

revision = "20261106_0075"
down_revision = "20261104_0074"
branch_labels = None
depends_on = None

FROZEN_TABLES = [
    {
        "name": "forecast_versions",
        "columns": [
            ("code", "String", [120], False, False, [], False),
            ("name", "String", [300], False, False, [], False),
            ("revision", "Integer", [], False, False, [], False),
            ("supersedes_id", "Integer", [], True, False, ["forecast_versions.id"], False),
            ("status", "String", [24], False, False, [], False),
            ("bundle_id", "Integer", [], False, False, ["progress_control_baseline_bundles.id"], False),
            ("period_id", "Integer", [], False, False, ["project_controls_periods.id"], False),
            ("as_of", "Date", [], False, False, [], False),
            ("schedule_version_id", "Integer", [], False, False, ["schedule_versions.id"], False),
            ("data_date_reference", "String", [80], False, False, [], False),
            ("currency", "String", [8], False, False, [], False),
            ("method", "String", [60], False, False, [], False),
            ("configuration_id", "Integer", [], False, False, ["admin_configurations.id"], False),
            ("configuration_hash", "String", [64], False, False, [], False),
            ("confidence", "String", [24], False, False, [], False),
            ("confidence_rationale", "Text", [], False, False, [], False),
            ("data_completeness", "String", [200], False, False, [], False),
            ("assumption_maturity", "String", [200], False, False, [], False),
            ("source_snapshot_json", "JSON", [], False, False, [], False),
            ("source_hashes_json", "JSON", [], False, False, [], False),
            ("result_json", "JSON", [], False, False, [], False),
            ("content_hash", "String", [64], False, False, [], False),
            ("prepared_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("updated_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("reviewed_by", "Integer", [], True, False, ["user_accounts.id"], False),
            ("approved_by", "Integer", [], True, False, ["user_accounts.id"], False),
            ("reviewed_at", "DateTime", [False], True, False, [], False),
            ("approved_at", "DateTime", [False], True, False, [], False),
            ("evidence_ref", "String", [1000], False, False, [], False),
            ("reason", "Text", [], False, False, [], False),
            ("id", "Integer", [], False, True, [], False),
            ("tenant_id", "Integer", [], False, False, ["tenants.id"], True),
            ("project_workspace_id", "Integer", [], False, False, ["enterprise_workspaces.id"], True),
            ("version", "Integer", [], False, False, [], False),
            ("created_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("created_at", "DateTime", [False], False, False, [], False),
        ],
        "unique": [("uq_forecast_version_revision", ["tenant_id", "project_workspace_id", "code", "revision"])],
        "checks": [
            ("ck_forecast_confidence", "confidence IN ('LOW','MEDIUM','HIGH')"),
            ("ck_forecast_version_status", "status IN ('DRAFT','UNDER_REVIEW','APPROVED','REJECTED')"),
        ],
    },
    {
        "name": "forecast_assumptions",
        "columns": [
            ("forecast_version_id", "Integer", [], False, False, ["forecast_versions.id"], True),
            ("code", "String", [120], False, False, [], False),
            ("name", "String", [300], False, False, [], False),
            ("kind", "String", [60], False, False, [], False),
            ("value", "String", [1000], False, False, [], False),
            ("unit", "String", [80], False, False, [], False),
            ("currency", "String", [8], True, False, [], False),
            ("source_reference", "String", [1000], False, False, [], False),
            ("owner_id", "Integer", [], False, False, ["user_accounts.id"], False),
            ("effective_date", "Date", [], False, False, [], False),
            ("confidence", "String", [24], False, False, [], False),
            ("status", "String", [24], False, False, [], False),
            ("evidence_ref", "String", [1000], False, False, [], False),
            ("rationale", "Text", [], False, False, [], False),
            ("content_hash", "String", [64], False, False, [], False),
            ("id", "Integer", [], False, True, [], False),
            ("tenant_id", "Integer", [], False, False, ["tenants.id"], True),
            ("project_workspace_id", "Integer", [], False, False, ["enterprise_workspaces.id"], True),
            ("version", "Integer", [], False, False, [], False),
            ("created_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("created_at", "DateTime", [False], False, False, [], False),
        ],
        "unique": [("uq_forecast_assumption_code", ["forecast_version_id", "code"])],
        "checks": [("ck_forecast_assumption_status", "status IN ('DRAFT','CONFIRMED')")],
    },
    {
        "name": "forecast_components",
        "columns": [
            ("forecast_version_id", "Integer", [], False, False, ["forecast_versions.id"], True),
            ("component_kind", "String", [24], False, False, [], False),
            ("code", "String", [120], False, False, [], False),
            ("name", "String", [300], False, False, [], False),
            ("method", "String", [60], False, False, [], False),
            ("assumption_codes", "JSON", [], False, False, [], False),
            ("scope_item_id", "Integer", [], True, False, ["scope_items.id"], False),
            ("plan_item_id", "Integer", [], True, False, ["scope_plan_items.id"], False),
            ("work_package_id", "Integer", [], True, False, ["awp_work_packages.id"], False),
            ("control_account_id", "Integer", [], True, False, ["cost_control_accounts.id"], False),
            ("cbs_id", "Integer", [], True, False, ["cost_cbs.id"], False),
            ("cost_code_id", "Integer", [], True, False, ["cost_code_dictionary.id"], False),
            ("schedule_version_id", "Integer", [], True, False, ["schedule_versions.id"], False),
            ("activity_external_id", "String", [160], False, False, [], False),
            ("wbs_external_id", "String", [160], False, False, [], False),
            ("area", "String", [150], False, False, [], False),
            ("zone", "String", [150], False, False, [], False),
            ("system", "String", [150], False, False, [], False),
            ("discipline", "String", [150], False, False, [], False),
            ("currency", "String", [8], True, False, [], False),
            ("unit", "String", [80], False, False, [], False),
            ("inputs", "JSON", [], False, False, [], False),
            ("result_json", "JSON", [], False, False, [], False),
            ("amount", "Numeric", [24, 8], True, False, [], False),
            ("quantity", "Numeric", [24, 8], True, False, [], False),
            ("forecast_finish", "Date", [], True, False, [], False),
            ("content_hash", "String", [64], False, False, [], False),
            ("id", "Integer", [], False, True, [], False),
            ("tenant_id", "Integer", [], False, False, ["tenants.id"], True),
            ("project_workspace_id", "Integer", [], False, False, ["enterprise_workspaces.id"], True),
            ("version", "Integer", [], False, False, [], False),
            ("created_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("created_at", "DateTime", [False], False, False, [], False),
        ],
        "unique": [("uq_forecast_component_code", ["forecast_version_id", "component_kind", "code"])],
        "checks": [("ck_forecast_component_kind", "component_kind IN ('COST','TIME','MILESTONE','RESOURCE')")],
    },
    {
        "name": "forecast_history",
        "columns": [
            ("entity_type", "String", [80], False, False, [], False),
            ("entity_id", "Integer", [], False, False, [], False),
            ("revision", "Integer", [], False, False, [], False),
            ("event_type", "String", [100], False, False, [], False),
            ("snapshot_json", "JSON", [], False, False, [], False),
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
        "name": "forecast_report_snapshots",
        "columns": [
            ("forecast_version_id", "Integer", [], False, False, ["forecast_versions.id"], True),
            ("bundle_id", "Integer", [], False, False, ["progress_control_baseline_bundles.id"], False),
            ("period_id", "Integer", [], False, False, ["project_controls_periods.id"], True),
            ("as_of", "Date", [], False, False, [], False),
            ("schedule_version_id", "Integer", [], False, False, ["schedule_versions.id"], False),
            ("cost_baseline_id", "Integer", [], False, False, ["cost_baselines.id"], False),
            ("progress_snapshot_id", "Integer", [], False, False, ["progress_period_snapshots.id"], False),
            ("evm_snapshot_id", "Integer", [], False, False, ["progress_earned_value_snapshots.id"], False),
            ("configuration_id", "Integer", [], False, False, ["admin_configurations.id"], False),
            ("configuration_hash", "String", [64], False, False, [], False),
            ("revision", "Integer", [], False, False, [], False),
            ("supersedes_id", "Integer", [], True, False, ["forecast_report_snapshots.id"], False),
            ("status", "String", [24], False, False, [], False),
            ("source_refs_json", "JSON", [], False, False, [], False),
            ("source_snapshot_json", "JSON", [], False, False, [], False),
            ("metrics_json", "JSON", [], False, False, [], False),
            ("narratives_json", "JSON", [], False, False, [], False),
            ("content_hash", "String", [64], False, False, [], False),
            ("published_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("published_at", "DateTime", [False], False, False, [], False),
            ("reason", "Text", [], False, False, [], False),
            ("evidence_reference", "String", [1000], False, False, [], False),
            ("id", "Integer", [], False, True, [], False),
            ("tenant_id", "Integer", [], False, False, ["tenants.id"], True),
            ("project_workspace_id", "Integer", [], False, False, ["enterprise_workspaces.id"], True),
            ("version", "Integer", [], False, False, [], False),
            ("created_by", "Integer", [], False, False, ["user_accounts.id"], False),
            ("created_at", "DateTime", [False], False, False, [], False),
        ],
        "unique": [("uq_forecast_report_revision", ["tenant_id", "project_workspace_id", "period_id", "revision"])],
        "checks": [
            ("ck_forecast_report_revision", "revision > 0"),
            ("ck_forecast_report_published", "status = 'PUBLISHED'"),
        ],
    },
    {
        "name": "forecast_lookahead_snapshots",
        "columns": [
            ("forecast_version_id", "Integer", [], False, False, ["forecast_versions.id"], True),
            ("period_id", "Integer", [], False, False, ["project_controls_periods.id"], False),
            ("as_of", "Date", [], False, False, [], False),
            ("schedule_version_id", "Integer", [], False, False, ["schedule_versions.id"], False),
            ("configuration_id", "Integer", [], False, False, ["admin_configurations.id"], False),
            ("configuration_hash", "String", [64], False, False, [], False),
            ("query_json", "JSON", [], False, False, [], False),
            ("result_snapshot_json", "JSON", [], False, False, [], False),
            ("source_refs_json", "JSON", [], False, False, [], False),
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
        "checks": [],
    },
]

GUARD_SQL = r"""
CREATE FUNCTION o1c_forecast_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  d jsonb; prior jsonb; ref record; ref_row jsonb; project_row jsonb;
  field_name text; actor bigint; reference_id bigint; parent forecast_versions%ROWTYPE;
  profile admin_configurations%ROWTYPE; period_row project_controls_periods%ROWTYPE;
  predecessor jsonb; parent_status text; source_forecast forecast_versions%ROWTYPE;
BEGIN
  IF TG_OP='DELETE' THEN
    IF TG_TABLE_NAME NOT IN ('forecast_assumptions','forecast_components') THEN
      RAISE EXCEPTION 'Forecast authority and reporting history cannot be deleted';
    END IF;
    d := to_jsonb(OLD);
  ELSE
    d := to_jsonb(NEW);
  END IF;
  IF TG_OP='UPDATE' THEN
    prior := to_jsonb(OLD);
    IF TG_TABLE_NAME IN ('forecast_assumptions','forecast_components') AND
       d->>'forecast_version_id' IS DISTINCT FROM prior->>'forecast_version_id' THEN
      RAISE EXCEPTION 'Forecast input parent is immutable';
    END IF;
    IF TG_TABLE_NAME IN ('forecast_history','forecast_report_snapshots','forecast_lookahead_snapshots') OR
       (TG_TABLE_NAME='forecast_versions' AND prior->>'status' IN ('APPROVED','REJECTED')) THEN
      RAISE EXCEPTION 'Forecast terminal projection is immutable; create a successor';
    END IF;
    IF d->>'tenant_id' IS DISTINCT FROM prior->>'tenant_id' OR
       d->>'project_workspace_id' IS DISTINCT FROM prior->>'project_workspace_id' OR
       d->>'created_by' IS DISTINCT FROM prior->>'created_by' OR
       d->>'created_at' IS DISTINCT FROM prior->>'created_at' THEN
      RAISE EXCEPTION 'Forecast scope and creator are immutable';
    END IF;
  END IF;
  SELECT to_jsonb(w) INTO project_row FROM enterprise_workspaces w
    WHERE w.id=(d->>'project_workspace_id')::bigint AND w.tenant_id=(d->>'tenant_id')::bigint;
  IF project_row IS NULL OR project_row->>'workspace_type_code'<>'project' OR
     lower(project_row->>'status')<>'active' THEN
    RAISE EXCEPTION 'Forecast requires same-tenant active Project';
  END IF;
  FOREACH field_name IN ARRAY ARRAY['created_by','updated_by','prepared_by','reviewed_by','approved_by','published_by','owner_id'] LOOP
    IF d ? field_name AND d->>field_name IS NOT NULL THEN
      actor := (d->>field_name)::bigint;
      IF NOT EXISTS(SELECT 1 FROM user_accounts u WHERE u.id=actor AND u.tenant_id=(d->>'tenant_id')::bigint) THEN
        RAISE EXCEPTION 'Forecast cross-tenant actor';
      END IF;
    END IF;
  END LOOP;
  FOR ref IN SELECT * FROM (VALUES
    ('scope_item_id','scope_items'),('plan_item_id','scope_plan_items'),('work_package_id','awp_work_packages'),
    ('control_account_id','cost_control_accounts'),('cbs_id','cost_cbs'),('cost_code_id','cost_code_dictionary'),
    ('schedule_version_id','schedule_versions'),('period_id','project_controls_periods'),
    ('bundle_id','progress_control_baseline_bundles'),('cost_baseline_id','cost_baselines'),
    ('progress_snapshot_id','progress_period_snapshots'),('evm_snapshot_id','progress_earned_value_snapshots'),
    ('forecast_version_id','forecast_versions')
  ) AS references_catalog(field_name,table_name) LOOP
    IF d ? ref.field_name AND d->>ref.field_name IS NOT NULL THEN
      reference_id := (d->>ref.field_name)::bigint;
      EXECUTE format('SELECT to_jsonb(r) FROM %I r WHERE r.id=$1',ref.table_name) INTO ref_row USING reference_id;
      IF ref_row IS NULL OR ref_row->>'tenant_id' IS DISTINCT FROM d->>'tenant_id' OR
         ref_row->>'project_workspace_id' IS DISTINCT FROM d->>'project_workspace_id' THEN
        RAISE EXCEPTION 'Forecast cross-project or cross-tenant reference: %',ref.field_name;
      END IF;
    END IF;
  END LOOP;
  IF d ? 'configuration_id' THEN
    SELECT * INTO profile FROM admin_configurations WHERE id=(d->>'configuration_id')::bigint;
    IF profile.id IS NULL OR profile.tenant_id<>(d->>'tenant_id')::bigint OR
       profile.kind<>'forecast_profile' OR profile.status<>'published' OR
       profile.content_hash IS DISTINCT FROM d->>'configuration_hash' THEN
      RAISE EXCEPTION 'Published pinned Forecast profile required';
    END IF;
    IF profile.content_json->'scope'->>'type'='workspace' AND
       (profile.content_json->'scope'->>'workspace_id')::bigint<>(d->>'project_workspace_id')::bigint AND
       (NOT coalesce((profile.content_json->>'inherit_to_descendants')::boolean,false) OR
        NOT EXISTS(WITH RECURSIVE ancestors AS (
          SELECT id,parent_id,1 AS depth FROM enterprise_workspaces WHERE id=(d->>'project_workspace_id')::bigint
          UNION ALL SELECT w.id,w.parent_id,a.depth+1 FROM enterprise_workspaces w JOIN ancestors a ON w.id=a.parent_id
          WHERE w.tenant_id=(d->>'tenant_id')::bigint AND a.depth<100
        ) SELECT 1 FROM ancestors WHERE id=(profile.content_json->'scope'->>'workspace_id')::bigint)) THEN
      RAISE EXCEPTION 'Forecast profile outside Project ancestry';
    END IF;
  END IF;
  IF d ? 'supersedes_id' AND d->>'supersedes_id' IS NOT NULL THEN
    EXECUTE format('SELECT to_jsonb(r) FROM %I r WHERE r.id=$1',TG_TABLE_NAME) INTO predecessor USING (d->>'supersedes_id')::bigint;
    IF predecessor IS NULL OR predecessor->>'tenant_id' IS DISTINCT FROM d->>'tenant_id' OR
       predecessor->>'project_workspace_id' IS DISTINCT FROM d->>'project_workspace_id' OR
       predecessor->>'status' NOT IN ('APPROVED','REJECTED','PUBLISHED') OR
       (d->>'revision')::integer<>(predecessor->>'revision')::integer+1 THEN
      RAISE EXCEPTION 'Forecast successor requires a prior immutable revision in the same Project';
    END IF;
  END IF;
  IF TG_TABLE_NAME IN ('forecast_assumptions','forecast_components') THEN
    SELECT * INTO parent FROM forecast_versions WHERE id=(d->>'forecast_version_id')::bigint FOR UPDATE;
    IF parent.id IS NULL OR parent.status<>'DRAFT' THEN
      RAISE EXCEPTION 'Forecast inputs can change only in DRAFT';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  ELSIF TG_TABLE_NAME='forecast_versions' THEN
    SELECT * INTO period_row FROM project_controls_periods WHERE id=NEW.period_id;
    IF NEW.as_of<period_row.period_start OR NEW.as_of>period_row.period_end OR
       NEW.data_date_reference='' OR NEW.data_date_reference IS NULL THEN
      RAISE EXCEPTION 'Forecast requires compatible period and explicit Schedule Data Date';
    END IF;
    IF NOT EXISTS(SELECT 1 FROM progress_control_baseline_bundles WHERE id=NEW.bundle_id AND status='APPROVED') THEN
      RAISE EXCEPTION 'Approved integrated baseline required';
    END IF;
    IF TG_OP='INSERT' THEN
      IF NEW.status<>'DRAFT' OR NEW.revision<1 OR NEW.prepared_by<>NEW.created_by THEN
        RAISE EXCEPTION 'Forecast must start as attributed DRAFT';
      END IF;
      IF period_row.status='PUBLISHED' AND (NEW.supersedes_id IS NULL OR
         NOT coalesce((profile.content_json->>'allow_published_period_successor')::boolean,false)) THEN
        RAISE EXCEPTION 'Published period requires an explicitly allowed Forecast successor';
      END IF;
    ELSE
      IF NEW.code<>OLD.code OR NEW.revision<>OLD.revision OR NEW.supersedes_id IS DISTINCT FROM OLD.supersedes_id OR
         NEW.prepared_by<>OLD.prepared_by THEN
        RAISE EXCEPTION 'Forecast identity is immutable';
      END IF;
      IF NEW.status<>OLD.status AND NOT ((OLD.status='DRAFT' AND NEW.status='UNDER_REVIEW') OR
         (OLD.status='UNDER_REVIEW' AND NEW.status IN ('APPROVED','REJECTED'))) THEN
        RAISE EXCEPTION 'Invalid Forecast lifecycle transition';
      END IF;
      IF OLD.status='UNDER_REVIEW' AND
         (d - ARRAY['status','version','reviewed_by','reviewed_at','approved_by','approved_at','reason']) IS DISTINCT FROM
         (prior - ARRAY['status','version','reviewed_by','reviewed_at','approved_by','approved_at','reason']) THEN
        RAISE EXCEPTION 'Submitted Forecast inputs and results are frozen';
      END IF;
    END IF;
    IF NEW.status='APPROVED' THEN
      IF NEW.approved_by IS NULL OR NEW.approved_at IS NULL OR NEW.reviewed_by IS NULL OR
         (coalesce((profile.content_json->'separation_of_duties'->>'preparer_cannot_approve')::boolean,true) AND NEW.approved_by=NEW.prepared_by) OR
         (coalesce((profile.content_json->'separation_of_duties'->>'last_material_editor_cannot_approve')::boolean,true) AND NEW.approved_by=NEW.updated_by) THEN
        RAISE EXCEPTION 'Forecast independent attributed approval required';
      END IF;
      IF NOT EXISTS(SELECT 1 FROM schedule_versions WHERE id=NEW.schedule_version_id AND status='ACCEPTED_CURRENT') THEN
        RAISE EXCEPTION 'Forecast approval requires accepted Current Schedule';
      END IF;
      IF NEW.source_hashes_json::jsonb='{}'::jsonb OR NEW.result_json::jsonb='{}'::jsonb THEN
        RAISE EXCEPTION 'Forecast approval requires frozen sources and calculation';
      END IF;
    END IF;
  ELSIF TG_TABLE_NAME IN ('forecast_report_snapshots','forecast_lookahead_snapshots') THEN
    SELECT * INTO source_forecast FROM forecast_versions WHERE id=NEW.forecast_version_id;
    IF source_forecast.status<>'APPROVED' OR source_forecast.period_id<>NEW.period_id OR
       source_forecast.as_of<>NEW.as_of OR source_forecast.schedule_version_id<>NEW.schedule_version_id THEN
      RAISE EXCEPTION 'Reporting requires the same approved Forecast period and source basis';
    END IF;
    IF TG_TABLE_NAME='forecast_report_snapshots' THEN
      IF NEW.bundle_id<>source_forecast.bundle_id OR
         NOT EXISTS(SELECT 1 FROM project_controls_periods WHERE id=NEW.period_id AND status='PUBLISHED') OR
         NOT EXISTS(SELECT 1 FROM progress_period_snapshots WHERE id=NEW.progress_snapshot_id AND period_id=NEW.period_id AND status='PUBLISHED') OR
         NOT EXISTS(SELECT 1 FROM progress_earned_value_snapshots WHERE id=NEW.evm_snapshot_id AND period_id=NEW.period_id AND bundle_id=NEW.bundle_id AND as_of=NEW.as_of) OR
         NOT EXISTS(SELECT 1 FROM progress_control_baseline_bundles WHERE id=NEW.bundle_id AND cost_baseline_id=NEW.cost_baseline_id) THEN
        RAISE EXCEPTION 'Published report references must share the approved period and baseline basis';
      END IF;
      IF (NEW.supersedes_id IS NULL AND NEW.revision<>1) OR
         (NEW.supersedes_id IS NOT NULL AND predecessor->>'period_id' IS DISTINCT FROM d->>'period_id') THEN
        RAISE EXCEPTION 'Report republication requires an explicit predecessor in the same period';
      END IF;
      IF (coalesce((profile.content_json->'reporting'->>'publisher_not_forecast_preparer')::boolean,true) AND NEW.published_by=source_forecast.prepared_by) OR
         (coalesce((profile.content_json->'reporting'->>'publisher_not_forecast_approver')::boolean,true) AND NEW.published_by=source_forecast.approved_by) THEN
        RAISE EXCEPTION 'Independent report publisher required';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION o1c_forecast_profile_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.kind='forecast_profile' AND OLD.status='published' THEN
    RAISE EXCEPTION 'Published Forecast profile is immutable; create a successor';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tr_forecast_profile_o1c BEFORE UPDATE OR DELETE ON admin_configurations
FOR EACH ROW EXECUTE FUNCTION o1c_forecast_profile_guard();
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
                f"CREATE TRIGGER tr_{spec['name']}_o1c BEFORE INSERT OR UPDATE OR DELETE ON {spec['name']} FOR EACH ROW EXECUTE FUNCTION o1c_forecast_guard()"
            )


def downgrade():
    connection = op.get_bind()
    for spec in FROZEN_TABLES:
        if connection.scalar(sa.text(f"SELECT count(*) FROM {spec['name']}")):
            raise RuntimeError("Forecast or reporting contains business records; downgrade refused")
    if connection.dialect.name == "postgresql":
        op.execute("DROP TRIGGER tr_forecast_profile_o1c ON admin_configurations")
    for spec in reversed(FROZEN_TABLES):
        op.drop_table(spec["name"])
    if connection.dialect.name == "postgresql":
        op.execute("DROP FUNCTION o1c_forecast_profile_guard()")
        op.execute("DROP FUNCTION o1c_forecast_guard()")
