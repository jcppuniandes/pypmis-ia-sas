"""Capture the continuation prerequisite without starting or changing any database."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from capture_remediation_preservation import SQL

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "docs/validation/gate07j-controlled-class-b"
QA = ROOT / "outputs/.qa/gate07j-controlled-class-b"
PREVIOUS = ROOT / "docs/validation/strategic-uat-remediation"
CONTAINER = "pypmis-strategic-fresh-uat-fresh-db-1"


def run(command, cwd=ROOT):
    result = subprocess.run(command, cwd=cwd, capture_output=True, check=False)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.decode("utf-8", errors="replace").strip(),
        "stderr": result.stderr.decode("utf-8", errors="replace").strip(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--after", action="store_true")
    args = parser.parse_args()
    if args.after:
        observed = run(
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
        if observed["returncode"]:
            raise RuntimeError(observed["stderr"])
        snapshot = json.loads(observed["stdout"])
        (DATA / "operational-after.json").write_text(
            json.dumps(snapshot, indent=2), encoding="utf-8"
        )
        assert snapshot == json.loads((DATA / "operational-before.json").read_text())
        print("Operational read-only before/after snapshots are identical")
        return
    DATA.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    commands = {
        "git_status": run(["git", "status", "--short"]),
        "git_diff_stat": run(["git", "diff", "--stat"]),
        "git_log": run(["git", "log", "-n", "20", "--oneline"]),
        "git_head": run(["git", "rev-parse", "HEAD"]),
        "git_branch": run(["git", "branch", "--show-current"]),
        "alembic_heads": run(
            [str(ROOT / "backend/.venv/Scripts/python.exe"), "-m", "alembic", "heads"],
            ROOT / "backend",
        ),
        "uat_container": run(
            [
                "docker",
                "inspect",
                CONTAINER,
                "--format",
                "{{json .State}}|{{json .HostConfig.Tmpfs}}|{{json .Mounts}}",
            ]
        ),
        "pg_version": run(
            ["docker", "cp", f"{CONTAINER}:/var/lib/postgresql/data/PG_VERSION", "-"]
        ),
        "uat_api_state": run(
            [
                "docker",
                "inspect",
                "pypmis-strategic-fresh-uat-fresh-api-1",
                "--format",
                "{{json .State}}",
            ]
        ),
        "containers": run(["docker", "ps", "-a", "--format", "{{.Names}} {{.Status}}"]),
        "backup_search": run(
            [
                "rg",
                "--files",
                "--hidden",
                "outputs/.qa/strategic-uat-remediation",
                "docs/validation/strategic-uat-remediation",
                "-g",
                "*.dump",
                "-g",
                "*.backup",
                "-g",
                "*.sql",
                "-g",
                "*pgdump*",
            ]
        ),
    }
    diff = run(["git", "diff", "--no-ext-diff"])
    diff_path = QA / "baseline-working-tree.diff"
    diff_path.write_text(diff["stdout"], encoding="utf-8")
    commands["git_diff"] = {
        "returncode": diff["returncode"],
        "file": str(diff_path.relative_to(ROOT)),
        "sha256": hashlib.sha256(diff_path.read_bytes()).hexdigest(),
        "stderr": diff["stderr"],
    }
    operational_command = [
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
    observed = run(operational_command)
    if observed["returncode"]:
        raise RuntimeError(observed["stderr"])
    operational = json.loads(observed["stdout"])
    old_operational = json.loads((PREVIOUS / "operational-before.json").read_text())
    (DATA / "operational-before.json").write_text(
        json.dumps(operational, indent=2), encoding="utf-8"
    )
    assert operational == old_operational, (
        "Operational data changed; report the actual mismatch"
    )
    assert commands["uat_container"]["returncode"] == 0
    state, tmpfs, mounts = (
        json.loads(value) for value in commands["uat_container"]["stdout"].split("|")
    )
    assert state["Running"] is False
    assert "/var/lib/postgresql/data" in tmpfs and mounts == []
    assert commands["pg_version"]["returncode"] != 0
    assert "Could not find the file" in commands["pg_version"]["stderr"]
    assert commands["backup_search"]["returncode"] == 1
    result = {
        "captured_at": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
        "status": "BLOCKED_UAT_DATABASE_NOT_AVAILABLE",
        "release_status": "STRATEGIC_MACROPROCESS_NOT_VALIDATED",
        "release_decision": "NO_GO",
        "selected_chain_verification": "NOT_VERIFIABLE",
        "expected_identity": {
            "tenant_id": 4,
            "tenant_slug": "fresh-copper-debf223b50",
            "enterprise_id": 13,
            "portfolio_id": 15,
            "project_id": 16,
            "capital_cycle_id": 4,
            "capital_demand_id": 4,
            "allocation_plan_id": 4,
            "idea_id": 4,
            "analysis_id": 4,
            "proposal_id": 4,
            "strategic_gate_id": 4,
            "project_creation_request_id": 4,
        },
        "finding": {
            "container_state": state["Status"],
            "exit_code": state["ExitCode"],
            "finished_at": state["FinishedAt"],
            "postgres_storage": "TMPFS",
            "persistent_mounts": mounts,
            "pg_version_available": False,
            "scope_of_backup_search": [
                "outputs/.qa/strategic-uat-remediation",
                "docs/validation/strategic-uat-remediation",
            ],
            "matching_backup_found": False,
            "other_backup": "Only an older operational Wave3A dump dated 2026-10-07 was found by the broader repository search; it is not a selected-UAT backup and was not restored.",
        },
        "commands": commands,
        "commands_against_selected_chain": 0,
        "business_state_direct_writes": 0,
        "upstream_rebuild_performed": False,
        "new_migrations": 0,
        "new_product_changes": 0,
        "current_tests": {"status": "NOT_RUN", "counts": None},
        "current_browser": {"status": "NOT_RUN", "counts": None},
        "historical_results_only": json.loads(
            (PREVIOUS / "release-results.json").read_text(encoding="utf-8")
        )["suites"],
        "operational_preservation": "MATCHES_PREVIOUS_READ_ONLY_BASELINE",
        "human_signoff": "PENDING_NOT_ASSUMED",
        "required_input": "Selected-chain PostgreSQL backup or explicit human authorization to rebuild through actual governed lifecycles in persistent isolated storage. JSON/checkpoints cannot replace the lost database or authorize terminal-state replay.",
        "next": "REMEDIATE THE SMALLEST REMAINING STRATEGIC UAT BLOCKER",
    }
    path = DATA / "preflight.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "operational_preservation": result["operational_preservation"],
            }
        )
    )


if __name__ == "__main__":
    main()
