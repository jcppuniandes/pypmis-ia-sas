"""Add canonical Quality facts and explicit native evidence decisions, without data migration."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "20261120_0081"
down_revision = "20261118_0080"
branch_labels = None
depends_on = None

TABLES = [
    "quality_plans",
    "quality_itps",
    "quality_itp_items",
    "quality_inspection_requests",
    "quality_test_requests",
    "quality_inspection_records",
    "quality_test_records",
    "quality_control_point_decisions",
    "quality_history",
    "quality_ncrs",
    "quality_dispositions",
    "quality_corrective_actions",
    "quality_punch_items",
    "quality_acceptances",
    "quality_mappings",
    "quality_readiness_assessments",
    "quality_consumer_decisions",
]
APPEND_ONLY = {
    "quality_control_point_decisions",
    "quality_history",
    "quality_acceptances",
    "quality_mappings",
    "quality_readiness_assessments",
    "quality_consumer_decisions",
}
TERMINAL = {
    "quality_plans": "APPROVED",
    "quality_itps": "APPROVED",
    "quality_inspection_requests": "COMPLETED,CANCELLED",
    "quality_test_requests": "COMPLETED,CANCELLED",
    "quality_inspection_records": "CLOSED",
    "quality_test_records": "CLOSED",
    "quality_ncrs": "CLOSED,REJECTED,CANCELLED",
    "quality_dispositions": "APPROVED,REJECTED",
    "quality_corrective_actions": "CLOSED",
    "quality_punch_items": "CLOSED",
}


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Quality governed facts require PostgreSQL")
    for statement in Path(__file__).with_suffix(".sql").read_text("utf-8").strip().split(";\n\n"):
        op.execute(statement.rstrip(";"))
    op.execute("""
      CREATE FUNCTION o3b_record_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE ref record; parent jsonb; identity text; project jsonb;
      BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Quality governed records cannot be deleted'; END IF;
        IF TG_OP='UPDATE' THEN
          IF TG_ARGV[0]='*' OR (to_jsonb(OLD)->>'status')=ANY(string_to_array(TG_ARGV[0],',')) THEN
            RAISE EXCEPTION 'Quality terminal facts and decisions are immutable';
          END IF;
          IF NEW.tenant_id<>OLD.tenant_id OR NEW.project_workspace_id<>OLD.project_workspace_id
             OR NEW.created_by<>OLD.created_by OR NEW.created_at<>OLD.created_at THEN
            RAISE EXCEPTION 'Quality governed identity is immutable';
          END IF;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM enterprise_workspaces w WHERE w.id=NEW.project_workspace_id
                       AND w.tenant_id=NEW.tenant_id AND w.workspace_type_code='project')
           OR NOT EXISTS (SELECT 1 FROM user_accounts u WHERE u.id=NEW.created_by AND u.tenant_id=NEW.tenant_id)
        THEN RAISE EXCEPTION 'Quality project or actor scope mismatch'; END IF;
        -- Trusted catalog metadata is used to validate every simple FK parent scope.
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
            ) THEN RAISE EXCEPTION 'Quality parent reference scope mismatch'; END IF;
          END IF;
        END LOOP;
        RETURN NEW;
      END $$;
    """)
    for table in TABLES:
        guard = "*" if table in APPEND_ONLY else TERMINAL.get(table, "")
        op.execute(
            f"CREATE TRIGGER tr_o3b_record_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION o3b_record_guard('{guard}')"
        )
    op.execute("""
      CREATE FUNCTION o3b_itp_item_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF NOT EXISTS (SELECT 1 FROM quality_itps p WHERE p.id=NEW.itp_id AND p.tenant_id=NEW.tenant_id
          AND p.project_workspace_id=NEW.project_workspace_id AND p.status='DRAFT')
        THEN RAISE EXCEPTION 'Quality ITP items are editable only while parent is DRAFT'; END IF;
        IF TG_OP='UPDATE' AND NEW.itp_id<>OLD.itp_id THEN
          RAISE EXCEPTION 'Quality ITP item parent is immutable';
        END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER tr_o3b_itp_item_guard BEFORE INSERT OR UPDATE ON quality_itp_items
        FOR EACH ROW EXECUTE FUNCTION o3b_itp_item_guard();
      CREATE FUNCTION o3b_consumer_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE source_table text; source_row jsonb; root_row jsonb; linked_table text; linked_row jsonb; previous jsonb;
              root_id integer; seen integer[] := ARRAY[]::integer[];
      BEGIN
        source_table := CASE NEW.source_entity_type
          WHEN 'ACCEPTANCE' THEN 'quality_acceptances' WHEN 'READINESS' THEN 'quality_readiness_assessments'
          WHEN 'NCR' THEN 'quality_ncrs' WHEN 'INSPECTION' THEN 'quality_inspection_records'
          WHEN 'TEST' THEN 'quality_test_records' ELSE NULL END;
        IF source_table IS NULL THEN RAISE EXCEPTION 'Quality consumer source type invalid'; END IF;
        EXECUTE format('SELECT to_jsonb(s) FROM %I s WHERE id=$1',source_table)
          INTO source_row USING NEW.source_entity_id;
        IF source_row IS NULL OR (source_row->>'tenant_id')::integer<>NEW.tenant_id
          OR (source_row->>'project_workspace_id')::integer<>NEW.project_workspace_id
          OR (source_row->>'version')::integer<>NEW.source_version OR source_row->>'source_hash'<>NEW.source_hash
          OR NEW.source_hash !~ '^[a-f0-9]{64}$'
        THEN RAISE EXCEPTION 'Quality consumer source pin or scope mismatch'; END IF;
        IF NEW.subject_key<>source_row->>'subject_key' THEN
          RAISE EXCEPTION 'Quality consumer subject identity mismatch';
        END IF;
        root_id := NEW.source_entity_id;
        IF NEW.source_entity_type='READINESS' THEN
          SELECT min(r.id) INTO root_id FROM quality_readiness_assessments r
           WHERE r.tenant_id=NEW.tenant_id AND r.project_workspace_id=NEW.project_workspace_id
             AND r.itp_id=(source_row->>'itp_id')::integer AND r.subject_key=NEW.subject_key;
        ELSIF NEW.source_entity_type='ACCEPTANCE' THEN
          root_row := source_row;
          WHILE root_row->>'supersedes_id' IS NOT NULL LOOP
            IF root_id=ANY(seen) THEN RAISE EXCEPTION 'Quality acceptance lineage cycle'; END IF;
            seen := array_append(seen,root_id);
            root_id := (root_row->>'supersedes_id')::integer;
            SELECT to_jsonb(a) INTO root_row FROM quality_acceptances a WHERE a.id=root_id;
            IF root_row IS NULL OR (root_row->>'tenant_id')::integer<>NEW.tenant_id
              OR (root_row->>'project_workspace_id')::integer<>NEW.project_workspace_id
              OR root_row->>'subject_key'<>NEW.subject_key THEN
              RAISE EXCEPTION 'Quality acceptance lineage scope mismatch';
            END IF;
          END LOOP;
        END IF;
        IF NEW.source_root_id<>root_id THEN RAISE EXCEPTION 'Quality consumer root identity mismatch'; END IF;
        IF NEW.linked_entity_id IS NOT NULL THEN
          linked_table := CASE NEW.linked_entity_type WHEN 'ProgressMeasurement' THEN 'progress_measurements'
                        WHEN 'WorkPackage' THEN 'awp_work_packages' ELSE NULL END;
          IF linked_table IS NULL OR (NEW.consumer='PROGRESS' AND linked_table<>'progress_measurements')
             OR (NEW.consumer='AWP' AND linked_table<>'awp_work_packages') THEN
            RAISE EXCEPTION 'Quality consumer native link type invalid';
          END IF;
          EXECUTE format('SELECT to_jsonb(s) FROM %I s WHERE id=$1',linked_table)
            INTO linked_row USING NEW.linked_entity_id;
          IF linked_row IS NULL OR (linked_row->>'tenant_id')::integer<>NEW.tenant_id
             OR (linked_row->>'project_workspace_id')::integer<>NEW.project_workspace_id
          THEN RAISE EXCEPTION 'Quality consumer native object scope mismatch'; END IF;
        END IF;
        IF NEW.consumer NOT IN ('PROGRESS','AWP') AND NEW.linked_entity_id IS NOT NULL THEN
          RAISE EXCEPTION 'Quality informational evidence cannot create financial or commercial facts';
        END IF;
        IF NEW.previous_decision_id IS NOT NULL THEN
          SELECT to_jsonb(d) INTO previous FROM quality_consumer_decisions d WHERE d.id=NEW.previous_decision_id;
          IF previous IS NULL OR previous->>'consumer'<>NEW.consumer
            OR previous->>'subject_key'<>NEW.subject_key OR previous->>'source_entity_type'<>NEW.source_entity_type
            OR (previous->>'source_root_id')::integer<>NEW.source_root_id
            OR (previous->>'version')::integer+1<>NEW.version
          THEN RAISE EXCEPTION 'Quality consumer predecessor stream mismatch'; END IF;
        ELSIF NEW.version<>1 THEN RAISE EXCEPTION 'Quality consumer initial version must be one'; END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER tr_o3b_consumer_guard BEFORE INSERT ON quality_consumer_decisions
        FOR EACH ROW EXECUTE FUNCTION o3b_consumer_guard();
    """)


def downgrade():
    for table in TABLES:
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError(f"Refusing to discard governed Quality data from {table}")
    # Remove only FK constraints owned by the 17 reviewed empty Quality tables.
    # Cyclic NCR/disposition/reinspection links must not require a broad CASCADE.
    constraints = (
        op.get_bind()
        .execute(
            sa.text("""
      SELECT c.conrelid::regclass::text AS table_name, c.conname AS constraint_name
      FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
      WHERE c.contype='f' AND t.relname=ANY(:tables)
    """),
            {"tables": TABLES},
        )
        .all()
    )
    for table_name, constraint_name in constraints:
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION o3b_consumer_guard()")
    op.execute("DROP FUNCTION o3b_itp_item_guard()")
    op.execute("DROP FUNCTION o3b_record_guard()")
