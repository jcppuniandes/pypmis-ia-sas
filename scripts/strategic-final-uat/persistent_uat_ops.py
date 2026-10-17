"""Guarded backups of the authorized UAT and READ ONLY operational observations."""

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from capture_remediation_preservation import SQL

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/gate07j-controlled-class-b-rebuild"
DB = "pypmis-strategic-persistent-uat-fresh-db-1"
VOLUME = "pypmis-strategic-persistent-uat_strategic_uat_postgres"


def run(command):
    result = subprocess.run(command, cwd=ROOT, capture_output=True, check=True)
    return result.stdout.decode("utf-8").strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup")
    parser.add_argument("--operational", choices=("before", "after"))
    parser.add_argument("--persistence", choices=("before", "after"))
    parser.add_argument("--state")
    args = parser.parse_args()
    QA.mkdir(parents=True, exist_ok=True)
    if args.state:
        assert re.fullmatch(r"[a-z0-9-]{1,70}", args.state)
        target = QA / (args.state + ".json")
        assert not target.exists()
        setup = json.loads((QA / "fresh-setup.json").read_text())
        tenant, project = int(setup["tenant_id"]), int(setup["project_id"])
        sql = f"""BEGIN READ ONLY;
        SELECT jsonb_build_object(
          'database', current_database(),
          'tenant', (SELECT jsonb_build_object('id',id,'slug',slug) FROM tenants WHERE id={tenant}),
          'project', (SELECT to_jsonb(w) FROM enterprise_workspaces w WHERE tenant_id={tenant} AND id={project}),
          'initialization', (SELECT to_jsonb(i) FROM project_workspace_initializations i WHERE tenant_id={tenant} AND workspace_id={project}),
          'preparations', (SELECT jsonb_agg(jsonb_build_object('id',id,'status',status,'hash',preparation_hash,'source_hash',preparation_source_hash,'row_md5',md5(to_jsonb(g)::text)) ORDER BY id) FROM investment_gate_preparations g WHERE tenant_id={tenant}),
          'decisions', (SELECT jsonb_agg(jsonb_build_object('id',id,'status',status,'profile',profile_code,'outcome',outcome,'decision_hash',decision_hash,'is_fid',is_fid,'investment_authorized',investment_authorized,'full_funds_authorized',full_funds_authorized,'decided_by',decided_by,'decided_at',decided_at,'row_md5',md5(to_jsonb(d)::text)) ORDER BY id) FROM investment_decisions d WHERE tenant_id={tenant}),
          'post_fid', (SELECT jsonb_agg(to_jsonb(e) ORDER BY eligibility_round) FROM post_fid_project_eligibilities e WHERE tenant_id={tenant} AND project_workspace_id={project})
        ); ROLLBACK;"""
        observation = json.loads(
            run(
                [
                    "docker",
                    "exec",
                    DB,
                    "psql",
                    "-U",
                    "strategic_uat",
                    "-d",
                    "strategic_fresh_uat",
                    "-qAt",
                    "-c",
                    sql,
                ]
            )
        )
        assert observation["database"] == "strategic_fresh_uat"
        assert observation["tenant"]["slug"] == setup["tenant_slug"]
        target.write_text(json.dumps(observation, indent=2), encoding="utf-8")
        print("Selected persistent UAT READ ONLY observation: " + str(target))
    if args.persistence:
        target = QA / ("persistence-" + args.persistence + ".json")
        assert not target.exists(), "Preserve each literal persistence observation"
        metadata = json.loads(run(["docker", "inspect", DB]))[0]
        assert (
            metadata["Config"]["Labels"]["com.docker.compose.project"]
            == "pypmis-strategic-persistent-uat"
        )
        assert any(m.get("Name") == VOLUME for m in metadata["Mounts"])
        tables = (
            "tenants",
            "enterprise_workspaces",
            "admin_configurations",
            "investment_gate_preparations",
            "investment_gate_evidence_items",
            "investment_decisions",
            "post_fid_project_eligibilities",
            "project_workspace_initializations",
        )
        pairs = ",".join(
            f"'{name}',(SELECT jsonb_build_object('count', count(*), 'rows_md5', "
            f"md5(COALESCE(jsonb_agg(to_jsonb(t) ORDER BY id)::text,'[]'))) FROM {name} t)"
            for name in tables
        )
        sql = (
            "BEGIN READ ONLY; SELECT jsonb_build_object('database', current_database(), "
            "'head',(SELECT version_num FROM alembic_version)," + pairs + "); ROLLBACK;"
        )
        observation = json.loads(
            run(
                [
                    "docker",
                    "exec",
                    DB,
                    "psql",
                    "-U",
                    "strategic_uat",
                    "-d",
                    "strategic_fresh_uat",
                    "-qAt",
                    "-c",
                    sql,
                ]
            )
        )
        assert observation["database"] == "strategic_fresh_uat"
        target.write_text(json.dumps(observation, indent=2), encoding="utf-8")
        if args.persistence == "after":
            assert observation == json.loads(
                (QA / "persistence-before.json").read_text()
            )
        print("Persistent UAT " + args.persistence + " observed; named volume verified")
    if args.backup:
        if not re.fullmatch(r"[a-z0-9-]{1,70}", args.backup):
            raise ValueError("Use an explicit bounded backup label")
        metadata = json.loads(run(["docker", "inspect", DB]))[0]
        assert (
            metadata["Config"]["Labels"]["com.docker.compose.project"]
            == "pypmis-strategic-persistent-uat"
        )
        assert any(
            m.get("Name") == VOLUME and m["Destination"] == "/var/lib/postgresql/data"
            for m in metadata["Mounts"]
        )
        assert not metadata["HostConfig"].get("Tmpfs")
        filename = args.backup + ".dump"
        target = QA / "backups" / filename
        assert not target.exists(), "Never overwrite a previous UAT backup"
        assert target.resolve().is_relative_to((QA / "backups").resolve())
        run(
            [
                "docker",
                "exec",
                DB,
                "pg_dump",
                "-U",
                "strategic_uat",
                "-d",
                "strategic_fresh_uat",
                "-Fc",
                "-f",
                "/backups/" + filename,
            ]
        )
        listing = run(
            ["docker", "exec", DB, "pg_restore", "--list", "/backups/" + filename]
        )
        assert target.is_file() and target.stat().st_size > 0
        assert "strategic_fresh_uat" in listing
        manifest = target.with_suffix(".json")
        manifest.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
                    "database": "strategic_fresh_uat",
                    "container": DB,
                    "volume": VOLUME,
                    "path": str(target),
                    "bytes": target.stat().st_size,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "archive_list_verified": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("Verified UAT backup: " + str(target))
    if args.operational:
        target = QA / ("operational-" + args.operational + ".json")
        assert not target.exists(), "Preserve the original observation"
        observation = json.loads(
            run(
                [
                    "docker",
                    "exec",
                    "pypmis-ia-sas-db-1",
                    "psql",
                    "-U",
                    "pypmis",
                    "-d",
                    "pypmis",
                    "-qAt",
                    "-c",
                    SQL,
                ]
            )
        )
        target.write_text(json.dumps(observation, indent=2), encoding="utf-8")
        baseline = (
            ROOT / "docs/validation/strategic-uat-remediation/operational-before.json"
            if args.operational == "before"
            else QA / "operational-before.json"
        )
        assert observation == json.loads(baseline.read_text())
        print(
            "Operational READ ONLY "
            + args.operational
            + " snapshot matches preserved baseline"
        )


if __name__ == "__main__":
    main()
