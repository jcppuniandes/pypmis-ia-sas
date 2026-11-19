"""Add canonical Contracts authority and explicit Cost adoption, without backfill."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "20261113_0079"
down_revision = "20261111_0078"
branch_labels = None
depends_on = None

# Parent-first order follows the frozen DDL. No names come from runtime input.
TABLES = (
    "contract_packages",
    "contract_history",
    "contract_mappings",
    "operational_contracts",
    "contract_versions",
    "operational_contract_notices",
    "commercial_commitments",
    "contract_sovs",
    "contract_changes",
    "contract_claims",
    "payment_applications",
    "contract_sov_lines",
    "cost_commercial_commitment_adoptions",
    "operational_payment_certificates",
    "payment_application_lines",
    "payment_certificate_lines",
    "contract_finance_references",
)
GUARDS = {
    "contract_packages": "",
    "operational_contracts": "",
    "contract_history": "*",
    "contract_mappings": "*",
    "contract_versions": "APPROVED",
    "commercial_commitments": "APPROVED",
    "contract_sovs": "PUBLISHED",
    "contract_sov_lines": "*",
    "contract_changes": "ORDER_APPROVED,REJECTED",
    "payment_applications": "REVIEWED,REJECTED",
    "payment_application_lines": "*",
    "operational_payment_certificates": "APPROVED,REJECTED",
    "payment_certificate_lines": "*",
    "operational_contract_notices": "CLOSED",
    "contract_claims": "ACCEPTED,REJECTED",
    "contract_finance_references": "*",
    "cost_commercial_commitment_adoptions": "*",
}


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("Contracts governance requires PostgreSQL")
    schema = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    for statement in schema.strip().split(";\n\n"):
        op.execute(statement.rstrip(";"))
    op.execute("""
        CREATE FUNCTION o2c_governed_record_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'Governed commercial records cannot be deleted';
          END IF;
          IF TG_OP = 'UPDATE' THEN
            IF TG_ARGV[0] = '*' OR (to_jsonb(OLD)->>'status') = ANY(string_to_array(TG_ARGV[0], ',')) THEN
              RAISE EXCEPTION 'Approved commercial evidence is immutable';
            END IF;
            IF NEW.tenant_id <> OLD.tenant_id OR NEW.project_workspace_id <> OLD.project_workspace_id
               OR NEW.created_by <> OLD.created_by OR NEW.created_at <> OLD.created_at THEN
              RAISE EXCEPTION 'Governed commercial identity is immutable';
            END IF;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM enterprise_workspaces w
                          WHERE w.id=NEW.project_workspace_id AND w.tenant_id=NEW.tenant_id
                            AND w.workspace_type_code='project')
             OR NOT EXISTS (SELECT 1 FROM user_accounts u WHERE u.id=NEW.created_by AND u.tenant_id=NEW.tenant_id) THEN
            RAISE EXCEPTION 'Governed commercial project or actor mismatch';
          END IF;
          RETURN NEW;
        END $$;
    """)
    for table, terminal in GUARDS.items():
        op.execute(
            f"CREATE TRIGGER tr_o2c_record_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION o2c_governed_record_guard('{terminal}')"
        )
    op.execute("""
        CREATE FUNCTION o2c_cost_adoption_source_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.source_hash !~ '^[0-9a-f]{64}$' OR length(btrim(NEW.reason)) < 3 OR NOT EXISTS (
            SELECT 1 FROM commercial_commitments c WHERE c.id=NEW.source_entity_id
              AND c.tenant_id=NEW.tenant_id AND c.project_workspace_id=NEW.project_workspace_id
              AND c.status='APPROVED' AND c.version=NEW.source_version AND c.source_hash=NEW.source_hash
              AND c.effective_date <= NEW.effective_at
          ) THEN RAISE EXCEPTION 'Cost adoption requires approved commercial source pins'; END IF;
          IF NOT EXISTS (SELECT 1 FROM cost_cbs r WHERE r.id=NEW.cbs_id AND r.status='ACTIVE'
                        AND r.tenant_id=NEW.tenant_id AND r.project_workspace_id=NEW.project_workspace_id)
             OR NOT EXISTS (SELECT 1 FROM cost_code_dictionary r WHERE r.id=NEW.cost_code_id AND r.status='ACTIVE'
                        AND r.tenant_id=NEW.tenant_id AND r.project_workspace_id=NEW.project_workspace_id)
             OR NOT EXISTS (SELECT 1 FROM cost_control_accounts r WHERE r.id=NEW.control_account_id AND r.status='ACTIVE'
                        AND r.tenant_id=NEW.tenant_id AND r.project_workspace_id=NEW.project_workspace_id)
          THEN RAISE EXCEPTION 'Cost adoption dimensions must be active in the same project'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER tr_o2c_cost_source_guard BEFORE INSERT ON cost_commercial_commitment_adoptions
          FOR EACH ROW EXECUTE FUNCTION o2c_cost_adoption_source_guard();
    """)


def downgrade():
    for table in TABLES:
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError(f"Refusing to discard governed data from {table}")
    op.drop_constraint("fk_o2c_contract_current_version", "operational_contracts", type_="foreignkey")
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION o2c_cost_adoption_source_guard()")
    op.execute("DROP FUNCTION o2c_governed_record_guard()")
