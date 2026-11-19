"""Add governed Procurement, Materials and Logistics without changing legacy records."""

import sqlalchemy as sa
from alembic import op

from app.modules.procurement_foundation.migration_0077_ddl import DEFERRED, TABLES

revision = "20261111_0077"
down_revision = "20261109_0076"
branch_labels = None
depends_on = None

GUARD = r"""
CREATE FUNCTION o2b_procurement_record_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    d jsonb; o jsonb; p jsonb; v jsonb; fk record;
    t bigint; w bigint; target bigint; relation_name text; source_name text;
    used_quantity numeric;
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Procurement history cannot be deleted'; END IF;
    d := to_jsonb(NEW); t := (d->>'tenant_id')::bigint; w := (d->>'project_workspace_id')::bigint;
    IF w IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM enterprise_workspaces x WHERE x.id=w AND x.tenant_id=t AND x.workspace_type_code='project'
    ) THEN RAISE EXCEPTION 'Procurement requires a Project in the same tenant'; END IF;

    IF TG_OP='UPDATE' THEN
        o := to_jsonb(OLD);
        IF d->'tenant_id' IS DISTINCT FROM o->'tenant_id' OR d->'project_workspace_id' IS DISTINCT FROM o->'project_workspace_id'
           OR d->'id' IS DISTINCT FROM o->'id' OR d->'created_by' IS DISTINCT FROM o->'created_by'
           OR d->'created_at' IS DISTINCT FROM o->'created_at' THEN
            RAISE EXCEPTION 'Procurement identity is immutable';
        END IF;
        IF TG_TABLE_NAME IN ('procurement_package_items','procurement_requisition_lines','procurement_rfq_vendors',
           'procurement_bids','procurement_evaluations','procurement_awards','procurement_po_lines','procurement_history',
           'procurement_mappings','procurement_material_items','procurement_vendor_milestones','procurement_expediting_events',
           'procurement_shipment_lines','procurement_material_receipt_lines','procurement_material_acceptances',
           'procurement_material_allocations') THEN RAISE EXCEPTION 'Procurement fact is immutable'; END IF;
        IF (TG_TABLE_NAME='procurement_requisitions' AND o->>'status' IN ('APPROVED','REJECTED','CANCELLED'))
           OR (TG_TABLE_NAME='procurement_rfqs' AND o->>'status' IN ('CLOSED','CANCELLED'))
           OR (TG_TABLE_NAME='procurement_po_revisions' AND o->>'status'='APPROVED')
           OR (TG_TABLE_NAME='procurement_inspections' AND o->>'status' IN ('ACCEPTED','REJECTED','CONDITIONAL'))
           OR (TG_TABLE_NAME='procurement_shipments' AND o->>'status' IN ('RECEIVED','CANCELLED'))
           OR (TG_TABLE_NAME='procurement_packages' AND o->>'status' IN ('CLOSED','CANCELLED')) THEN
            RAISE EXCEPTION 'Terminal Procurement record is immutable';
        END IF;
        IF TG_TABLE_NAME='procurement_material_receipts' AND d-'version' IS DISTINCT FROM o-'version' THEN
            RAISE EXCEPTION 'Physical receipt is immutable';
        END IF;
        IF TG_TABLE_NAME='procurement_material_requirements' AND (
            (d-ARRAY['version','procurement_requirement_id']) IS DISTINCT FROM (o-ARRAY['version','procurement_requirement_id'])
            OR (o->>'procurement_requirement_id' IS NOT NULL AND d->'procurement_requirement_id' IS DISTINCT FROM o->'procurement_requirement_id')
        ) THEN RAISE EXCEPTION 'Physical requirement is immutable except first linkage'; END IF;
        IF TG_TABLE_NAME='procurement_purchase_orders' AND o->>'status' IN ('APPROVED','ISSUED','CANCELLED') THEN
            IF (d-ARRAY['version','updated_by','updated_at','status','current_revision_id','current_value','issued_by'])
               IS DISTINCT FROM (o-ARRAY['version','updated_by','updated_at','status','current_revision_id','current_value','issued_by']) THEN
                RAISE EXCEPTION 'Approved PO is immutable; use approved successor';
            END IF;
            IF d->>'status' IS DISTINCT FROM o->>'status' THEN
                IF o->>'status' IS DISTINCT FROM 'APPROVED' OR d->>'status' IS DISTINCT FROM 'ISSUED'
                   OR d->>'issued_by' IS NULL OR d->>'current_revision_id' IS NULL THEN
                    RAISE EXCEPTION 'Approved PO status can only advance to issued with issuer and approved revision';
                END IF;
            ELSIF d->'issued_by' IS DISTINCT FROM o->'issued_by' THEN
                RAISE EXCEPTION 'PO issuer is immutable after issue';
            END IF;
            IF d->'current_revision_id' IS DISTINCT FROM o->'current_revision_id' THEN
                IF o->>'status' IS DISTINCT FROM 'ISSUED' OR NOT EXISTS (
                    SELECT 1 FROM procurement_po_revisions r WHERE r.id=(d->>'current_revision_id')::bigint
                    AND r.purchase_order_id=NEW.id AND r.previous_revision_id=(o->>'current_revision_id')::bigint
                    AND r.tenant_id=t AND r.project_workspace_id=w AND r.status='APPROVED'
                    AND r.approved_by IS NOT NULL
                    AND r.total_value=(d->>'current_value')::numeric) THEN
                    RAISE EXCEPTION 'PO pointer requires approved successor with matching value';
                END IF;
            ELSIF d->'current_value' IS DISTINCT FROM o->'current_value' THEN
                RAISE EXCEPTION 'PO value requires approved successor';
            END IF;
        END IF;
    END IF;

    IF TG_TABLE_NAME='procurement_purchase_orders' THEN
        IF TG_OP='INSERT' AND d->>'status' IS DISTINCT FROM 'DRAFT' THEN
            RAISE EXCEPTION 'PO must start in draft';
        END IF;
        IF d->>'status' IN ('DRAFT','CANCELLED') AND (
            d->>'current_revision_id' IS NOT NULL OR d->>'approved_by' IS NOT NULL OR d->>'issued_by' IS NOT NULL
            OR d->'current_value' IS DISTINCT FROM d->'original_value'
        ) THEN RAISE EXCEPTION 'Unapproved PO cannot record approval, issue, or revised value'; END IF;
        IF TG_OP='UPDATE' AND o->>'status'='DRAFT' THEN
            IF d->>'status' NOT IN ('DRAFT','APPROVED','CANCELLED') THEN
                RAISE EXCEPTION 'Draft PO must be approved before issue';
            END IF;
            IF d->>'status'='APPROVED' AND (
                d->>'issued_by' IS NOT NULL OR d->>'approved_by' IS NULL
                OR d->'current_value' IS DISTINCT FROM d->'original_value'
                OR NOT EXISTS (SELECT 1 FROM procurement_po_revisions r WHERE r.id=(d->>'current_revision_id')::bigint
                    AND r.purchase_order_id=NEW.id AND r.revision=1 AND r.previous_revision_id IS NULL
                    AND r.tenant_id=t AND r.project_workspace_id=w AND r.status='APPROVED'
                    AND r.approved_by=(d->>'approved_by')::bigint AND r.total_value=(d->>'current_value')::numeric)
            ) THEN RAISE EXCEPTION 'PO approval requires approved initial revision with matching approver and value'; END IF;
        END IF;
    END IF;

    -- Relational FKs check identity; this adds tenant and Project equality.
    FOR fk IN
        SELECT a.attname AS field, r.relname AS target_name, n.nspname AS target_schema
        FROM pg_constraint c JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=c.conkey[1]
        JOIN pg_class r ON r.oid=c.confrelid JOIN pg_namespace n ON n.oid=r.relnamespace
        WHERE c.conrelid=TG_RELID AND c.contype='f' AND cardinality(c.conkey)=1 AND n.nspname='public'
    LOOP
        target := (d->>fk.field)::bigint;
        IF target IS NULL THEN CONTINUE; END IF;
        EXECUTE format('SELECT to_jsonb(x) FROM %I.%I x WHERE x.id=$1', fk.target_schema, fk.target_name) INTO p USING target;
        IF p IS NULL OR (p ? 'tenant_id' AND (p->>'tenant_id')::bigint IS DISTINCT FROM t)
           OR (w IS NOT NULL AND p ? 'project_workspace_id' AND (p->>'project_workspace_id')::bigint IS DISTINCT FROM w) THEN
            RAISE EXCEPTION 'Procurement reference outside tenant or Project: %', fk.field;
        END IF;
        IF fk.target_name IN ('contracts','purchase_orders') AND NOT EXISTS (
            SELECT 1 FROM operational_project_bindings b WHERE b.tenant_id=t AND b.project_workspace_id=w
            AND b.legacy_project_id=(p->>'project_id')::bigint AND b.status='ACTIVE' AND b.effective_to IS NULL
        ) THEN RAISE EXCEPTION 'Procurement legacy reference requires Project binding'; END IF;
        IF fk.target_name='admin_configurations' AND
           (p->>'kind' IS DISTINCT FROM 'procurement_profile' OR p->>'status' IS DISTINCT FROM 'published'
            OR (d ? 'configuration_hash' AND d->>'configuration_hash' IS DISTINCT FROM p->>'content_hash')) THEN
            RAISE EXCEPTION 'Procurement requires its published profile revision';
        END IF;
    END LOOP;

    IF TG_TABLE_NAME='procurement_mappings' THEN
        source_name := CASE d->>'source_kind' WHEN 'PACKAGE' THEN 'procurement_packages'
            WHEN 'REQUIREMENT' THEN 'procurement_requirements' WHEN 'MATERIAL_REQUIREMENT' THEN 'procurement_material_requirements'
            WHEN 'MATERIAL_ITEM' THEN 'procurement_material_items' WHEN 'RECEIPT' THEN 'procurement_material_receipts'
            WHEN 'ALLOCATION' THEN 'procurement_material_allocations' END;
        relation_name := CASE d->>'target_kind'
            WHEN 'PWP' THEN 'awp_work_packages' WHEN 'CWP' THEN 'awp_work_packages' WHEN 'IWP' THEN 'awp_work_packages'
            WHEN 'EWP' THEN 'awp_work_packages' WHEN 'CWA' THEN 'awp_cwas' WHEN 'SCOPE' THEN 'scope_items'
            WHEN 'PLAN' THEN 'scope_plan_items' WHEN 'WBS' THEN 'schedule_versions' WHEN 'ACTIVITY' THEN 'schedule_versions'
            WHEN 'MILESTONE' THEN 'schedule_versions' WHEN 'CBS' THEN 'cost_cbs' WHEN 'COST_CODE' THEN 'cost_code_dictionary'
            WHEN 'CONTROL_ACCOUNT' THEN 'cost_control_accounts' WHEN 'ENGINEERING_DELIVERABLE' THEN 'engineering_deliverables'
            WHEN 'ENGINEERING_REVISION' THEN 'engineering_revisions' WHEN 'IFC_RELEASE' THEN 'engineering_releases'
            WHEN 'DESIGN_PACKAGE' THEN 'engineering_design_packages' END;
        IF source_name IS NULL OR relation_name IS NULL THEN RAISE EXCEPTION 'Invalid Procurement mapping kind'; END IF;
        EXECUTE format('SELECT to_jsonb(x) FROM %I x WHERE x.id=$1 AND x.tenant_id=$2 AND x.project_workspace_id=$3', source_name)
            INTO p USING (d->>'source_id')::bigint,t,w;
        EXECUTE format('SELECT to_jsonb(x) FROM %I x WHERE x.id=$1 AND x.tenant_id=$2 AND x.project_workspace_id=$3', relation_name)
            INTO v USING COALESCE(d->>'target_id',d->>'schedule_version_id')::bigint,t,w;
        IF p IS NULL OR v IS NULL OR (relation_name='awp_work_packages' AND v->>'package_type' IS DISTINCT FROM d->>'target_kind') THEN
            RAISE EXCEPTION 'Procurement mapping source or target outside Project or type';
        END IF;
    ELSIF TG_TABLE_NAME='procurement_material_acceptances' THEN
        SELECT to_jsonb(x) INTO p FROM procurement_material_receipt_lines x WHERE x.id=(d->>'receipt_line_id')::bigint FOR UPDATE;
        IF (d->>'accepted_quantity')::numeric+(d->>'rejected_quantity')::numeric+(d->>'quarantine_quantity')::numeric
           IS DISTINCT FROM (p->>'quantity')::numeric THEN RAISE EXCEPTION 'Material disposition must equal physical receipt'; END IF;
    ELSIF TG_TABLE_NAME='procurement_material_allocations' THEN
        SELECT to_jsonb(x) INTO p FROM procurement_material_acceptances x WHERE x.id=(d->>'acceptance_id')::bigint FOR UPDATE;
        SELECT to_jsonb(x) INTO v FROM procurement_material_receipt_lines x WHERE x.id=(d->>'receipt_line_id')::bigint;
        IF p->>'receipt_line_id' IS DISTINCT FROM d->>'receipt_line_id'
           OR v->>'material_requirement_id' IS DISTINCT FROM d->>'material_requirement_id'
           OR v->>'uom' IS DISTINCT FROM d->>'uom' THEN RAISE EXCEPTION 'Material allocation lineage mismatch'; END IF;
        IF d->>'state'='ACTIVE' THEN
            SELECT COALESCE(sum(a.quantity),0) INTO used_quantity FROM procurement_material_allocations a
            WHERE a.acceptance_id=(d->>'acceptance_id')::bigint AND a.state='ACTIVE'
                AND NOT EXISTS (SELECT 1 FROM procurement_material_allocations b WHERE b.supersedes_id=a.id);
            IF used_quantity+(d->>'quantity')::numeric > (p->>'accepted_quantity')::numeric THEN
                RAISE EXCEPTION 'Material allocation exceeds accepted stock';
            END IF;
        ELSE
            SELECT to_jsonb(x) INTO v FROM procurement_material_allocations x WHERE x.id=(d->>'supersedes_id')::bigint;
            IF v->>'state' IS DISTINCT FROM 'ACTIVE' OR
               v->>'acceptance_id' IS DISTINCT FROM d->>'acceptance_id' OR v->>'receipt_line_id' IS DISTINCT FROM d->>'receipt_line_id'
               OR v->>'work_package_id' IS DISTINCT FROM d->>'work_package_id' OR v->>'quantity' IS DISTINCT FROM d->>'quantity' THEN
                RAISE EXCEPTION 'Material allocation release must match previous allocation';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION o2b_procurement_profile_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.kind='procurement_profile' AND OLD.status='published' THEN
        RAISE EXCEPTION 'Published Procurement profile is immutable';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER tr_procurement_profile_o2b BEFORE UPDATE OR DELETE ON admin_configurations
FOR EACH ROW EXECUTE FUNCTION o2b_procurement_profile_guard();
"""


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Wave O2B requires guarded PostgreSQL migration")
    for _, statement, indexes in TABLES:
        op.execute(statement)
        for index in indexes:
            op.execute(index)
    for statement in DEFERRED:
        op.execute(statement)
    op.execute(GUARD)
    for table, *_ in TABLES:
        op.execute(f"CREATE TRIGGER tr_{table}_o2b BEFORE INSERT OR UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION o2b_procurement_record_guard()")


def downgrade():
    bind = op.get_bind()
    for table, *_ in TABLES:
        if bind.scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("Procurement records exist; downgrade refused")
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM admin_configurations WHERE kind='procurement_profile')")):
        raise RuntimeError("Procurement profiles exist; downgrade refused")
    op.execute("DROP TRIGGER tr_procurement_profile_o2b ON admin_configurations")
    op.execute("ALTER TABLE procurement_purchase_orders DROP CONSTRAINT fk_proc_po_current_revision")
    for table, *_ in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION o2b_procurement_profile_guard()")
    op.execute("DROP FUNCTION o2b_procurement_record_guard()")
