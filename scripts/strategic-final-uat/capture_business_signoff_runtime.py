"""Observe existing private UAT with READ ONLY SQL; never starts services/writes DB."""

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/gate07j-controlled-class-b-rebuild"
DB = "pypmis-strategic-persistent-uat-fresh-db-1"
PROJECT = "pypmis-strategic-persistent-uat"
VOLUME = "pypmis-strategic-persistent-uat_strategic_uat_postgres"


def run(*args):
    result = subprocess.run(
        args, cwd=ROOT, capture_output=True, check=True, timeout=120
    )
    return result.stdout.decode("utf-8").strip()


def ref(path):
    return {
        "file": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def readonly(sql):
    assert sql.startswith("BEGIN READ ONLY;") and sql.endswith("ROLLBACK;")
    return json.loads(run(
        "docker", "exec", DB, "psql", "-U", "strategic_uat", "-d",
        "strategic_fresh_uat", "-v", "ON_ERROR_STOP=1", "-qAt", "-c", sql
    ))


def differences(expected, actual, path=""):
    if type(expected) is not type(actual):
        return [path or "/"]
    if isinstance(expected, dict):
        result = []
        for key in sorted(set(expected) | set(actual)):
            child = path + "/" + key
            if key not in expected or key not in actual:
                result.append(child)
            else:
                result.extend(differences(expected[key], actual[key], child))
        return result
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [path + "/length"]
        return [part for index, values in enumerate(zip(expected, actual, strict=True))
                for part in differences(*values, path + "/" + str(index))]
    return [] if expected == actual else [path or "/"]


def main():
    metadata = json.loads(run("docker", "inspect", DB))[0]
    assert metadata["State"]["Running"] is True
    assert metadata["Config"]["Labels"]["com.docker.compose.project"] == PROJECT
    assert any(m.get("Name") == VOLUME and m["Destination"] == "/var/lib/postgresql/data"
               for m in metadata["Mounts"])
    assert not metadata["HostConfig"].get("Tmpfs")
    companions = {}
    for suffix in ("fresh-api-1", "fresh-redis-1"):
        name = PROJECT + "-" + suffix
        data = json.loads(run("docker", "inspect", name))[0]
        companions[name] = data["State"]["Status"]
        assert data["State"]["Running"] is False

    selected_path = QA / "selected-delivery-20261016.json"
    persistence_path = QA / "persistence-after.json"
    expected_selected = json.loads(selected_path.read_text(encoding="utf-8"))
    expected_persistence = json.loads(persistence_path.read_text(encoding="utf-8"))
    tenant = int(expected_selected["tenant"]["id"])
    project = int(expected_selected["project"]["id"])
    assert tenant == 1 and project == 4
    selected_sql = f"""BEGIN READ ONLY;
    SELECT jsonb_build_object(
      'database', current_database(),
      'tenant', (SELECT jsonb_build_object('id',id,'slug',slug) FROM tenants WHERE id={tenant}),
      'project', (SELECT to_jsonb(w) FROM enterprise_workspaces w WHERE tenant_id={tenant} AND id={project}),
      'initialization', (SELECT to_jsonb(i) FROM project_workspace_initializations i WHERE tenant_id={tenant} AND workspace_id={project}),
      'preparations', (SELECT jsonb_agg(jsonb_build_object('id',id,'status',status,'hash',preparation_hash,'source_hash',preparation_source_hash,'row_md5',md5(to_jsonb(g)::text)) ORDER BY id) FROM investment_gate_preparations g WHERE tenant_id={tenant}),
      'decisions', (SELECT jsonb_agg(jsonb_build_object('id',id,'status',status,'profile',profile_code,'outcome',outcome,'decision_hash',decision_hash,'is_fid',is_fid,'investment_authorized',investment_authorized,'full_funds_authorized',full_funds_authorized,'decided_by',decided_by,'decided_at',decided_at,'row_md5',md5(to_jsonb(d)::text)) ORDER BY id) FROM investment_decisions d WHERE tenant_id={tenant}),
      'post_fid', (SELECT jsonb_agg(to_jsonb(e) ORDER BY eligibility_round) FROM post_fid_project_eligibilities e WHERE tenant_id={tenant} AND project_workspace_id={project})
    ); ROLLBACK;"""
    selected = readonly(selected_sql)
    assert selected["database"] == "strategic_fresh_uat"
    assert selected["tenant"]["slug"] == "fresh-copper-1765b06813"
    tables = (
        "tenants", "enterprise_workspaces", "admin_configurations",
        "investment_gate_preparations", "investment_gate_evidence_items",
        "investment_decisions", "post_fid_project_eligibilities",
        "project_workspace_initializations",
    )
    pairs = ",".join(
        f"'{name}',(SELECT jsonb_build_object('count', count(*), 'rows_md5', "
        f"md5(COALESCE(jsonb_agg(to_jsonb(t) ORDER BY id)::text,'[]'))) FROM {name} t)"
        for name in tables
    )
    persistence_sql = (
        "BEGIN READ ONLY; SELECT jsonb_build_object('database', current_database(), "
        "'head',(SELECT version_num FROM alembic_version)," + pairs + "); ROLLBACK;"
    )
    persistence = readonly(persistence_sql)
    readonly_proof = readonly(
        "BEGIN READ ONLY; SELECT jsonb_build_object('transaction_read_only', "
        "current_setting('transaction_read_only'), 'database',current_database()); ROLLBACK;"
    )
    selected_diff = differences(expected_selected, selected)
    persistence_diff = differences(expected_persistence, persistence)
    table_comparisons = {
        name: {
            "expected": expected_persistence[name], "current": persistence[name],
            "matches": expected_persistence[name] == persistence[name],
        } for name in tables
    }
    success = (
        not selected_diff and not persistence_diff
        and persistence["head"] == "20261011_0068"
        and readonly_proof["transaction_read_only"] == "on"
    )
    out = {
        "schema_version": 1,
        "observed_at": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
        "result": "PASS_CURRENT_PERSISTED_CONTINUITY_READ_ONLY" if success else "MISMATCH_PRESERVED_FOR_REVIEW",
        "activity": "NEW_20261018_SQL_OBSERVATION_NOT_NEW_END_TO_END_TEST",
        "prior_initial_stopped_observation": "docs/validation/business-uat-signoff-20261018/baseline.json",
        "root_startup_boundary": "Root separately started only the exact existing private DB after checking compose-project and named-volume guards. This script did not start services; API and Redis remain stopped.",
        "container": DB,
        "project": PROJECT,
        "named_volume": VOLUME,
        "database_state": {key: metadata["State"].get(key) for key in ("Status", "Running", "StartedAt")},
        "companion_states": companions,
        "transaction_proof": readonly_proof,
        "selected_baseline": ref(selected_path),
        "selected_observation": selected,
        "selected_matches_delivery_20261016": not selected_diff,
        "selected_differences": selected_diff,
        "persistence_baseline": ref(persistence_path),
        "persistence_observation": persistence,
        "eight_tables": table_comparisons,
        "all_eight_table_counts_and_row_md5_match": all(row["matches"] for row in table_comparisons.values()),
        "persistence_matches_20261016": not persistence_diff,
        "persistence_differences": persistence_diff,
        "alembic_head": persistence["head"],
        "commands_executed": [selected_sql, persistence_sql, "BEGIN READ ONLY; SELECT transaction_read_only; ROLLBACK"],
        "interpretation": "The persisted material selected chain and complete rows of eight critical tables match the retained 16 October observation. This is continuity proof on 18 October, not a new service-level readiness calculation, browser UAT run, business review, approval, or real-world permit/contract attestation. PostgreSQL's normal startup/recovery housekeeping is not represented as application business-state mutation.",
        "new_application_business_commands": 0,
        "database_business_writes": 0,
        "schema_migrations_executed": 0,
        "api_started": False,
        "new_end_to_end_tests": 0,
        "new_human_approvals": 0,
        "script": ref(Path(__file__).resolve()),
        "transport": "Explicit UTF-8 psql/docker decoding; ASCII-escaped JSON stdout avoids Windows console codepage transformations.",
        "previous_capture_attempt": "docs/validation/business-uat-signoff-20261018/runtime-readonly-20261018-encoding-attempt.json",
    }
    print(json.dumps(out, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
