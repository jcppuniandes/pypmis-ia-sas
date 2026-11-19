"""Canonical field facts and explicit native consumer decisions, additive only."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "20261118_0080"
down_revision = "20261113_0079"
branch_labels = None
depends_on = None

TABLES = ["field_workfronts","field_crews","field_equipment_references","field_record_closures","field_history","field_mappings","field_consumer_decisions","field_shifts","field_site_instructions","field_constraint_observations","field_daily_reports","field_labor_usage","field_equipment_usage","field_conditions","field_events","field_production_records","field_material_consumption"]
APPEND_ONLY = {
    "field_labor_usage", "field_equipment_usage", "field_conditions", "field_history", "field_record_closures",
    "field_material_consumption", "field_mappings", "field_consumer_decisions",
}
TERMINAL = {
    "field_workfronts": "COMPLETE", "field_shifts": "CLOSED", "field_daily_reports": "APPROVED",
    "field_production_records": "VERIFIED,REJECTED", "field_events": "CLOSED",
    "field_site_instructions": "CLOSED", "field_constraint_observations": "VERIFIED,REJECTED",
}


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Field operational governance requires PostgreSQL")
    for statement in Path(__file__).with_suffix(".sql").read_text("utf-8").strip().split(";\n\n"):
        op.execute(statement.rstrip(";"))
    op.execute("""
      CREATE FUNCTION o3a_record_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE ref record; parent jsonb; identity text; value jsonb;
      BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Field governed records cannot be deleted'; END IF;
        IF TG_OP='UPDATE' THEN
          IF TG_ARGV[0]='*' OR (to_jsonb(OLD)->>'status')=ANY(string_to_array(TG_ARGV[0],',')) THEN
            RAISE EXCEPTION 'Field approved facts and decisions are immutable';
          END IF;
          IF NEW.tenant_id<>OLD.tenant_id OR NEW.project_workspace_id<>OLD.project_workspace_id
             OR NEW.created_by<>OLD.created_by OR NEW.created_at<>OLD.created_at THEN
            RAISE EXCEPTION 'Field governed identity is immutable';
          END IF;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM enterprise_workspaces w WHERE w.id=NEW.project_workspace_id
                       AND w.tenant_id=NEW.tenant_id AND w.workspace_type_code='project')
           OR NOT EXISTS (SELECT 1 FROM user_accounts u WHERE u.id=NEW.created_by AND u.tenant_id=NEW.tenant_id)
        THEN RAISE EXCEPTION 'Field project or actor scope mismatch'; END IF;
        -- The catalog is trusted metadata, never supplied SQL. Validate every simple FK parent scope.
        FOR ref IN
          SELECT c.confrelid::regclass AS target, a.attname AS local_column, p.attname AS parent_column
          FROM pg_constraint c
          JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=c.conkey[1]
          JOIN pg_attribute p ON p.attrelid=c.confrelid AND p.attnum=c.confkey[1]
          WHERE c.conrelid=TG_RELID AND c.contype='f' AND cardinality(c.conkey)=1
        LOOP
          identity := to_jsonb(NEW)->>ref.local_column;
          IF identity IS NOT NULL THEN
            EXECUTE format('SELECT to_jsonb(p) FROM %s p WHERE %I=$1::integer', ref.target, ref.parent_column)
              INTO parent USING identity;
            IF parent IS NOT NULL AND (
              (parent ? 'tenant_id' AND (parent->>'tenant_id')::integer<>NEW.tenant_id)
              OR (parent ? 'project_workspace_id' AND (parent->>'project_workspace_id')::integer<>NEW.project_workspace_id)
            ) THEN RAISE EXCEPTION 'Field parent reference scope mismatch'; END IF;
          END IF;
        END LOOP;
        RETURN NEW;
      END $$;
    """)
    for table in TABLES:
        guard = "*" if table in APPEND_ONLY else TERMINAL.get(table, "")
        op.execute(f"CREATE TRIGGER tr_o3a_record_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION o3a_record_guard('{guard}')")
    op.execute("""
      CREATE FUNCTION o3a_consumer_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE source_table text; source_row jsonb; linked_table text; linked_row jsonb;
      BEGIN
        source_table := CASE NEW.source_entity_type
          WHEN 'PRODUCTION' THEN 'field_production_records' WHEN 'CONSTRAINT' THEN 'field_constraint_observations'
          WHEN 'LABOR' THEN 'field_labor_usage' WHEN 'EQUIPMENT' THEN 'field_equipment_usage'
          WHEN 'EVENT' THEN 'field_events' WHEN 'INSTRUCTION' THEN 'field_site_instructions'
          WHEN 'DAILY_REPORT' THEN 'field_daily_reports' WHEN 'WORKFRONT' THEN 'field_workfronts' ELSE NULL END;
        IF source_table IS NULL THEN RAISE EXCEPTION 'Field consumer source type invalid'; END IF;
        EXECUTE format('SELECT to_jsonb(s) FROM %I s WHERE id=$1',source_table)
          INTO source_row USING NEW.source_entity_id;
        IF source_row IS NULL OR (source_row->>'tenant_id')::integer<>NEW.tenant_id
          OR (source_row->>'project_workspace_id')::integer<>NEW.project_workspace_id
          OR (source_row->>'version')::integer<>NEW.source_version OR source_row->>'source_hash'<>NEW.source_hash
          OR NEW.source_hash !~ '^[a-f0-9]{64}$'
        THEN RAISE EXCEPTION 'Field consumer source pin or scope mismatch'; END IF;
        IF NEW.linked_entity_id IS NOT NULL THEN
          linked_table := CASE NEW.linked_entity_type WHEN 'ProgressMeasurement' THEN 'progress_measurements'
                        WHEN 'AWPExecutionConstraint' THEN 'awp_execution_constraints' ELSE NULL END;
          IF linked_table IS NULL THEN RAISE EXCEPTION 'Field consumer native link type invalid'; END IF;
          EXECUTE format('SELECT to_jsonb(s) FROM %I s WHERE id=$1',linked_table)
            INTO linked_row USING NEW.linked_entity_id;
          IF linked_row IS NULL OR (linked_row->>'tenant_id')::integer<>NEW.tenant_id
             OR (linked_row->>'project_workspace_id')::integer<>NEW.project_workspace_id
          THEN RAISE EXCEPTION 'Field consumer native object scope mismatch'; END IF;
        END IF;
        IF NEW.consumer='COST' AND NEW.linked_entity_id IS NOT NULL THEN
          RAISE EXCEPTION 'Field Cost evidence cannot recognize actual cost';
        END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER tr_o3a_consumer_guard BEFORE INSERT ON field_consumer_decisions
        FOR EACH ROW EXECUTE FUNCTION o3a_consumer_guard();
    """)


def downgrade():
    for table in TABLES:
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError(f"Refusing to discard governed Field data from {table}")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION o3a_consumer_guard()")
    op.execute("DROP FUNCTION o3a_record_guard()")
