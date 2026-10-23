"""Canonical operational Cost authority without source backfill.

Revision ID: 20261022_0073
Revises: 20261021_0072
"""

import sqlalchemy as sa
from alembic import op

revision = "20261022_0073"
down_revision = "20261021_0072"
branch_labels = None
depends_on = None

# Frozen schema specifications, not imported runtime ORM metadata.
# name:type[:foreign key]; ? marks a nullable field.
SCHEMA = {
    "cost_cbs": "code:s120 name:s300 parent_id:i?:cost_cbs.id path:x level:i sort_order:i status:s24",
    "cost_code_dictionary": "code:s120 name:s300 category:s80 status:s24",
    "cost_control_accounts": "code:s120 name:s300 owner_user_id:i:user_accounts.id responsible_role:s120 status:s24",
    "cost_mappings": "source_kind:s24 source_id:i? schedule_version_id:i?:schedule_versions.id source_external_id:s160 cbs_id:i?:cost_cbs.id cost_code_id:i?:cost_code_dictionary.id control_account_id:i?:cost_control_accounts.id allocation_basis:s100 quantity_basis:s100 quantity:n? unit:s40 percentage:n? amount:n? currency:s8? effective_revision:s120 source_reference:s1000 source_snapshot:j status:s24 supersedes_id:i?:cost_mappings.id reason:x",
    "cost_rates": "code:s120 name:s300 resource_type:s40 unit:s40 amount:n currency:s8 effective_from:d effective_to:d? source_reference:s1000 source_snapshot:j status:s24 supersedes_id:i?:cost_rates.id published_by:i?:user_accounts.id published_at:t?",
    "cost_apus": "code:s120 name:s300 unit:s40 currency:s8 effective_from:d effective_to:d? components_json:j factors_json:j unit_amount:n source_reference:s1000 content_hash:s64 status:s24 supersedes_id:i?:cost_apus.id published_by:i?:user_accounts.id published_at:t?",
    "cost_budget_versions": "code:s120 name:s300 budget_type:s80 currency:s8 status:s24 predecessor_id:i?:cost_budget_versions.id configuration_id:i:admin_configurations.id configuration_hash:s64 source_references:j snapshot_json:j content_hash:s64 reviewed_by:i?:user_accounts.id approved_by:i?:user_accounts.id approved_at:t?",
    "cost_budget_lines": "budget_version_id:i:cost_budget_versions.id line_code:s120 description:s1000 cbs_id:i?:cost_cbs.id cost_code_id:i?:cost_code_dictionary.id control_account_id:i?:cost_control_accounts.id scope_item_id:i?:scope_items.id plan_item_id:i?:scope_plan_items.id work_package_id:i?:awp_work_packages.id apu_id:i?:cost_apus.id quantity:n unit:s40 rate:n amount:n currency:s8 cost_class:s40 time_phasing_basis:s100 source_json:j",
    "cost_baselines": "code:s120 budget_version_id:i:cost_budget_versions.id previous_baseline_id:i?:cost_baselines.id status:s24 configuration_id:i:admin_configurations.id snapshot_json:j content_hash:s64 approved_by:i?:user_accounts.id approved_at:t?",
    "cost_phasing": "baseline_id:i:cost_baselines.id budget_line_id:i:cost_budget_lines.id method:s40 revision:i period_id:i?:project_controls_periods.id start_date:d finish_date:d schedule_version_id:i?:schedule_versions.id source_external_id:s160 basis_json:j spread_json:j amount:n currency:s8 content_hash:s64 supersedes_id:i?:cost_phasing.id reason:x",
    "cost_history": "entity_type:s80 entity_id:i revision:i snapshot_json:j event_type:s100 reason:x",
    "cost_fx_rates": "code:s120 from_currency:s8 to_currency:s8 rate:n effective_from:d effective_to:d? conversion_basis:s1000 source_reference:s1000 status:s24 content_hash:s64 supersedes_id:i?:cost_fx_rates.id published_by:i?:user_accounts.id published_at:t?",
    "cost_actual_entries": "entry_kind:s24 adjusts_entry_id:i?:cost_actual_entries.id source_system:s120 source_reference:s260 source_type:s80 posting_date:d recognition_date:d period_id:i:project_controls_periods.id amount:n currency:s8 cbs_id:i?:cost_cbs.id cost_code_id:i?:cost_code_dictionary.id control_account_id:i?:cost_control_accounts.id evidence_ref:s1000 description:x fx_rate_id:i?:cost_fx_rates.id status:s24 approved_by:i?:user_accounts.id approved_at:t?",
    "cost_commitment_references": "source_system:s120 source_type:s40 source_reference:s260 source_revision:s120 supersedes_id:i?:cost_commitment_references.id source_hash:s64 source_record_id:i? source_document:s1000 source_approval_status:s40 economic_origin:s260 parent_economic_origin:s260? inclusion_mode:s24 amount:n currency:s8 effective_date:d cbs_id:i?:cost_cbs.id cost_code_id:i?:cost_code_dictionary.id control_account_id:i?:cost_control_accounts.id fx_rate_id:i?:cost_fx_rates.id status:s24 verified_by:i?:user_accounts.id verified_at:t?",
}
TABLES = tuple(SCHEMA)
APPEND_ONLY = {"cost_mappings", "cost_phasing", "cost_history", "cost_budget_lines"}
UNIQUES = {
    "cost_cbs": (("tenant_id", "project_workspace_id", "code"), "uq_cost_cbs_code"),
    "cost_code_dictionary": (("tenant_id", "project_workspace_id", "code"), "uq_cost_code_dictionary"),
    "cost_control_accounts": (("tenant_id", "project_workspace_id", "code"), "uq_cost_account_code"),
    "cost_rates": (("tenant_id", "project_workspace_id", "code", "revision"), "uq_cost_rate_revision"),
    "cost_apus": (("tenant_id", "project_workspace_id", "code", "revision"), "uq_cost_apu_revision"),
    "cost_budget_versions": (("tenant_id", "project_workspace_id", "code", "revision"), "uq_cost_budget_revision"),
    "cost_budget_lines": (("budget_version_id", "line_code"), "uq_cost_budget_line"),
    "cost_baselines": (("tenant_id", "project_workspace_id", "code", "revision"), "uq_cost_baseline_revision"),
    "cost_fx_rates": (("tenant_id", "project_workspace_id", "code", "revision"), "uq_cost_fx_revision"),
    "cost_actual_entries": (
        ("tenant_id", "project_workspace_id", "source_system", "source_reference"),
        "uq_cost_actual_source",
    ),
    "cost_commitment_references": (
        ("tenant_id", "project_workspace_id", "source_system", "source_type", "source_reference", "source_revision"),
        "uq_cost_commitment_source",
    ),
}
CHECKS = {
    "cost_cbs": ["level > 0 AND status IN ('ACTIVE','INACTIVE')"],
    "cost_code_dictionary": ["status IN ('ACTIVE','INACTIVE')"],
    "cost_control_accounts": ["status IN ('ACTIVE','INACTIVE')"],
    "cost_mappings": [
        "source_kind IN ('SCOPE','PLAN','PACKAGE','WBS','ACTIVITY')",
        "status IN ('ACTIVE','REMOVED')",
        "percentage IS NULL OR (percentage>=0 AND percentage<=100)",
        "amount IS NULL OR currency IS NOT NULL",
        "cbs_id IS NOT NULL OR cost_code_id IS NOT NULL OR control_account_id IS NOT NULL",
    ],
    "cost_rates": [
        "status IN ('DRAFT','PUBLISHED') AND amount >= 0",
        "effective_to IS NULL OR effective_to>effective_from",
    ],
    "cost_apus": [
        "status IN ('DRAFT','PUBLISHED') AND unit_amount >= 0",
        "effective_to IS NULL OR effective_to>effective_from",
    ],
    "cost_budget_versions": ["status IN ('DRAFT','SUBMITTED','UNDER_REVIEW','APPROVED','SUPERSEDED','REJECTED')"],
    "cost_budget_lines": ["quantity>=0 AND rate>=0 AND amount>=0"],
    "cost_baselines": ["status IN ('CANDIDATE','APPROVED')"],
    "cost_phasing": [
        "finish_date>=start_date AND amount>=0",
        "method IN ('LINEAR','FRONT_LOADED','BACK_LOADED','MILESTONE_BASED','ACTIVITY_BASED','MANUAL','CURVE_BASED')",
    ],
    "cost_fx_rates": [
        "rate > 0 AND from_currency<>to_currency",
        "status IN ('DRAFT','PUBLISHED')",
        "effective_to IS NULL OR effective_to>effective_from",
    ],
    "cost_actual_entries": [
        "status IN ('IMPORTED','RECOGNIZED','REJECTED')",
        "(entry_kind='ORIGINAL' AND adjusts_entry_id IS NULL AND amount>0) OR (entry_kind='ADJUSTMENT' AND adjusts_entry_id IS NOT NULL AND amount<>0)",
    ],
    "cost_commitment_references": [
        "status IN ('PROPOSED','VERIFIED','REJECTED')",
        "inclusion_mode IN ('INCLUDED','CALL_OFF','ADDITIVE','REFERENCE_ONLY')",
        "amount>=0",
    ],
}


def _columns(spec):
    result = []
    for field in spec.split():
        name, descriptor, *foreign = field.split(":")
        nullable = descriptor.endswith("?")
        descriptor = descriptor.rstrip("?")
        kind = (
            sa.String(int(descriptor[1:]))
            if descriptor.startswith("s")
            else {
                "i": sa.Integer,
                "n": lambda: sa.Numeric(24, 8),
                "d": sa.Date,
                "t": sa.DateTime,
                "x": sa.Text,
                "j": sa.JSON,
            }[descriptor]()
        )
        result.append(sa.Column(name, kind, *([sa.ForeignKey(foreign[0])] if foreign else []), nullable=nullable))
    return result


def upgrade():
    base = "tenant_id:i:tenants.id project_workspace_id:i:enterprise_workspaces.id version:i created_by:i:user_accounts.id created_at:t"
    mutable = "revision:i updated_by:i:user_accounts.id updated_at:t"
    for table, spec in SCHEMA.items():
        constraints = [sa.CheckConstraint("version>0", name=f"ck_{table}_version")]
        if table in UNIQUES:
            fields, name = UNIQUES[table]
            constraints.append(sa.UniqueConstraint(*fields, name=name))
        for index, expression in enumerate(CHECKS.get(table, [])):
            constraints.append(sa.CheckConstraint(expression, name=f"ck_{table}_{index}"))
        op.create_table(
            table,
            sa.Column("id", sa.Integer, primary_key=True),
            *_columns(base),
            *(_columns(mutable) if table not in APPEND_ONLY else []),
            *_columns(spec),
            *constraints,
        )
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        op.create_index(f"ix_{table}_project_workspace_id", table, ["project_workspace_id"])
    for table, field in (
        ("cost_budget_lines", "budget_version_id"),
        ("cost_phasing", "baseline_id"),
        ("cost_history", "entity_id"),
    ):
        op.create_index(f"ix_{table}_{field}", table, [field])
    if op.get_bind().dialect.name == "postgresql":
        _postgres_guards()


def _postgres_guards():
    op.execute("""
    CREATE FUNCTION cost_o1bc_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE n jsonb; o jsonb; r jsonb; f text; target_table text; source_table text; source_identity integer;
    BEGIN
      IF TG_TABLE_NAME='admin_configurations' THEN
        IF TG_OP='DELETE' THEN
          IF OLD.kind='cost_profile' THEN RAISE EXCEPTION 'Cost policy history immutable' USING ERRCODE='23514'; END IF;
          RETURN OLD;
        END IF;
        IF OLD.kind='cost_profile' AND (OLD.status='published' OR OLD.kind IS DISTINCT FROM NEW.kind)
          THEN RAISE EXCEPTION 'Published Cost policy immutable' USING ERRCODE='23514'; END IF;
        RETURN NEW;
      END IF;
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Cost history cannot be deleted' USING ERRCODE='23514'; END IF;
      n:=to_jsonb(NEW);
      SELECT to_jsonb(w) INTO r FROM enterprise_workspaces w WHERE w.id=NEW.project_workspace_id;
      IF r IS NULL OR (r->>'tenant_id')::integer IS DISTINCT FROM NEW.tenant_id OR lower(r->>'workspace_type_code')<>'project'
        THEN RAISE EXCEPTION 'Cost canonical Project Workspace required' USING ERRCODE='23514'; END IF;
      PERFORM schedule_o1bb_reference('user_accounts',NEW.created_by,NEW.tenant_id,NULL);
      IF TG_OP='UPDATE' THEN
        o:=to_jsonb(OLD);
        IF TG_TABLE_NAME IN ('cost_mappings','cost_phasing','cost_history')
          THEN RAISE EXCEPTION 'Cost mapping/phasing/history append only' USING ERRCODE='23514'; END IF;
        IF o->>'status' IN ('APPROVED','PUBLISHED','SUPERSEDED','REJECTED','RECOGNIZED','VERIFIED')
          THEN RAISE EXCEPTION 'Approved Cost or published source immutable' USING ERRCODE='23514'; END IF;
        IF (n->>'tenant_id') IS DISTINCT FROM (o->>'tenant_id') OR (n->>'project_workspace_id') IS DISTINCT FROM (o->>'project_workspace_id')
          OR (n->>'created_by') IS DISTINCT FROM (o->>'created_by') OR (n->>'created_at') IS DISTINCT FROM (o->>'created_at')
          OR NEW.version<>OLD.version+1
          THEN RAISE EXCEPTION 'Cost identity immutable and successor version required' USING ERRCODE='23514'; END IF;
        IF TG_TABLE_NAME IN ('cost_fx_rates','cost_actual_entries','cost_commitment_references') THEN
          IF (n-ARRAY['status','version','revision','updated_by','updated_at','published_by','published_at','approved_by','approved_at','verified_by','verified_at'])
             IS DISTINCT FROM (o-ARRAY['status','version','revision','updated_by','updated_at','published_by','published_at','approved_by','approved_at','verified_by','verified_at'])
          THEN RAISE EXCEPTION 'Financial economic inputs immutable; successor or adjustment required' USING ERRCODE='23514'; END IF;
        END IF;
      END IF;
      FOREACH f IN ARRAY ARRAY['updated_by','owner_user_id','reviewed_by','approved_by','published_by','verified_by'] LOOP
        IF n ? f THEN PERFORM schedule_o1bb_reference('user_accounts',(n->>f)::integer,NEW.tenant_id,NULL); END IF;
      END LOOP;
      FOREACH f IN ARRAY ARRAY['parent_id','cbs_id','cost_code_id','control_account_id','schedule_version_id','scope_item_id','plan_item_id','work_package_id','apu_id','budget_version_id','baseline_id','budget_line_id','previous_baseline_id','predecessor_id','period_id','fx_rate_id','adjusts_entry_id','supersedes_id'] LOOP
        IF n ? f AND n->>f IS NOT NULL THEN
          target_table:=CASE f
            WHEN 'parent_id' THEN 'cost_cbs' WHEN 'cbs_id' THEN 'cost_cbs' WHEN 'cost_code_id' THEN 'cost_code_dictionary'
            WHEN 'control_account_id' THEN 'cost_control_accounts' WHEN 'schedule_version_id' THEN 'schedule_versions'
            WHEN 'scope_item_id' THEN 'scope_items' WHEN 'plan_item_id' THEN 'scope_plan_items' WHEN 'work_package_id' THEN 'awp_work_packages'
            WHEN 'apu_id' THEN 'cost_apus' WHEN 'budget_version_id' THEN 'cost_budget_versions' WHEN 'baseline_id' THEN 'cost_baselines'
            WHEN 'budget_line_id' THEN 'cost_budget_lines' WHEN 'previous_baseline_id' THEN 'cost_baselines' WHEN 'predecessor_id' THEN 'cost_budget_versions'
            WHEN 'period_id' THEN 'project_controls_periods' WHEN 'fx_rate_id' THEN 'cost_fx_rates' WHEN 'adjusts_entry_id' THEN 'cost_actual_entries'
            WHEN 'supersedes_id' THEN TG_TABLE_NAME ELSE NULL END;
          PERFORM schedule_o1bb_reference(target_table,(n->>f)::integer,NEW.tenant_id,NEW.project_workspace_id);
        END IF;
      END LOOP;
      IF n ? 'configuration_id' THEN
        IF NOT EXISTS(SELECT 1 FROM admin_configurations c WHERE c.id=(n->>'configuration_id')::integer AND c.tenant_id=NEW.tenant_id AND c.kind='cost_profile' AND c.status='published')
          THEN RAISE EXCEPTION 'Published tenant Cost policy required' USING ERRCODE='23514'; END IF;
      END IF;
      IF TG_TABLE_NAME='cost_cbs' THEN
        IF NEW.parent_id IS NOT NULL THEN
          IF EXISTS(WITH RECURSIVE a(id,parent_id) AS (SELECT id,parent_id FROM cost_cbs WHERE id=NEW.parent_id UNION SELECT c.id,c.parent_id FROM cost_cbs c JOIN a ON c.id=a.parent_id) SELECT 1 FROM a WHERE id=NEW.id)
            THEN RAISE EXCEPTION 'CBS cycle' USING ERRCODE='23514'; END IF;
        END IF;
      END IF;
      IF TG_TABLE_NAME='cost_mappings' THEN
        IF NEW.source_kind IN ('SCOPE','PLAN','PACKAGE') THEN
          source_table:=CASE NEW.source_kind WHEN 'SCOPE' THEN 'scope_items' WHEN 'PLAN' THEN 'scope_plan_items' ELSE 'awp_work_packages' END;
          IF NEW.source_id IS NULL OR NEW.schedule_version_id IS NOT NULL OR NEW.source_external_id<>'' THEN RAISE EXCEPTION 'Canonical cost source shape invalid' USING ERRCODE='23514'; END IF;
          PERFORM schedule_o1bb_reference(source_table,NEW.source_id,NEW.tenant_id,NEW.project_workspace_id);
        ELSE
          IF NEW.source_id IS NOT NULL OR NEW.schedule_version_id IS NULL OR NEW.source_external_id='' THEN RAISE EXCEPTION 'Schedule cost source shape invalid' USING ERRCODE='23514'; END IF;
          IF NOT EXISTS(SELECT 1 FROM schedule_versions s WHERE s.id=NEW.schedule_version_id AND s.accepted_at IS NOT NULL)
            THEN RAISE EXCEPTION 'Accepted Schedule required' USING ERRCODE='23514'; END IF;
        END IF;
      END IF;
      IF TG_TABLE_NAME='cost_budget_lines' THEN
        IF NOT EXISTS(SELECT 1 FROM cost_budget_versions b WHERE b.id=NEW.budget_version_id AND b.status='DRAFT')
          THEN RAISE EXCEPTION 'Budget line requires draft parent' USING ERRCODE='23514'; END IF;
      END IF;
      IF TG_TABLE_NAME='cost_phasing' THEN
        IF NOT EXISTS(SELECT 1 FROM cost_baselines b WHERE b.id=NEW.baseline_id AND b.status='CANDIDATE')
          THEN RAISE EXCEPTION 'Phasing requires candidate baseline' USING ERRCODE='23514'; END IF;
      END IF;
      IF TG_TABLE_NAME='cost_actual_entries' THEN
        IF NOT EXISTS(SELECT 1 FROM project_controls_periods p WHERE p.id=NEW.period_id AND p.status='OPEN' AND NEW.recognition_date BETWEEN p.period_start AND p.period_end)
          THEN RAISE EXCEPTION 'Actual requires open valid recognition period' USING ERRCODE='23514'; END IF;
      END IF;
      IF n->>'status' IN ('APPROVED','PUBLISHED','RECOGNIZED','VERIFIED') THEN
        IF COALESCE(n->>'approved_by',n->>'published_by',n->>'verified_by')=n->>'created_by'
          THEN RAISE EXCEPTION 'Independent Cost approval required' USING ERRCODE='23514'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    """)
    for table in TABLES:
        op.execute(
            f"CREATE TRIGGER tr_{table}_o1bc BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION cost_o1bc_guard()"
        )
    op.execute(
        "CREATE TRIGGER tr_cost_profile_o1bc BEFORE UPDATE OR DELETE ON admin_configurations FOR EACH ROW EXECUTE FUNCTION cost_o1bc_guard()"
    )


def downgrade():
    connection = op.get_bind()
    if any(connection.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar() for table in TABLES):
        raise RuntimeError("Refusing to destroy populated Cost history; preserve and migrate explicitly")
    if connection.dialect.name == "postgresql":
        op.execute("DROP TRIGGER tr_cost_profile_o1bc ON admin_configurations")
        for table in TABLES:
            op.execute(f"DROP TRIGGER tr_{table}_o1bc ON {table}")
        op.execute("DROP FUNCTION cost_o1bc_guard()")
    for table in reversed(TABLES):
        op.drop_table(table)
