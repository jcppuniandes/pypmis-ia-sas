"""Read-only sign-off baseline audit; JSON to stdout, no database/file writes."""

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from capture_remediation_preservation import SQL

ROOT = Path(__file__).resolve().parents[2]
FROZEN_COMMIT = "6672fd5da1f486e6bd571a74bb6d1e8b3337a405"
UAT_DB = "pypmis-strategic-persistent-uat-fresh-db-1"
UAT_API = "pypmis-strategic-persistent-uat-fresh-api-1"
VOLUME = "pypmis-strategic-persistent-uat_strategic_uat_postgres"
RESULTS = ROOT / "docs/validation/gate07j-controlled-class-b/rebuild-results.json"


def command(*args, cwd=ROOT):
    completed = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=120, check=False
    )
    return {
        "command": list(args),
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(path):
    path = ROOT / path
    return {
        "file": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def container(name):
    result = command("docker", "inspect", name)
    if result["exit_code"]:
        return {"name": name, "inspect_error": result["stderr"]}
    data = json.loads(result["stdout"])[0]
    return {
        "name": name,
        "state": {
            key: data["State"].get(key)
            for key in ("Status", "Running", "ExitCode", "FinishedAt", "OOMKilled")
        },
        "project": data["Config"].get("Labels", {}).get("com.docker.compose.project"),
        "mounts": [
            {key: mount.get(key) for key in ("Type", "Name", "Destination", "RW")}
            for mount in data.get("Mounts", [])
        ],
        "tmpfs": data.get("HostConfig", {}).get("Tmpfs"),
    }


def main():
    prior = json.loads(RESULTS.read_text(encoding="utf-8"))
    commands = {
        "status": command("git", "status", "--short", "--branch"),
        "diff": command("git", "diff"),
        "diff_stat": command("git", "diff", "--stat"),
        "log": command("git", "log", "-n", "10", "--format=%h %s"),
        "branch": command("git", "branch", "--show-current"),
        "head": command("git", "rev-parse", "HEAD"),
        "origin_main_local_tracking_ref": command("git", "rev-parse", "origin/main"),
        "product_diff_frozen": command(
            "git", "diff", "--name-only", FROZEN_COMMIT, "--", "backend", "frontend"
        ),
        "untracked_backend_frontend": command(
            "git", "ls-files", "--others", "--exclude-standard", "--", "backend", "frontend"
        ),
        "local_alembic_heads": command(
            str(ROOT / "backend/.venv/Scripts/python.exe"),
            "-m", "alembic", "heads", cwd=ROOT / "backend"
        ),
        "operational_api_alembic_heads": command(
            "docker", "exec", "pypmis-ia-sas-api-1", "alembic", "heads"
        ),
    }
    hashes = []
    for collection in ("product_hashes_at_collection", "fixture_hashes_at_collection"):
        for name, expected in prior["baseline"][collection].items():
            current = digest(ROOT / name)
            hashes.append({
                "file": name, "class": collection,
                "expected_sha256": expected, "current_sha256": current,
                "matches": current == expected,
            })
    uat_db = container(UAT_DB)
    uat_api = container(UAT_API)
    volume_result = command("docker", "volume", "inspect", VOLUME)
    volume = json.loads(volume_result["stdout"])[0] if volume_result["exit_code"] == 0 else None
    operational = command(
        "docker", "exec", "pypmis-ia-sas-db-1", "psql", "-U", "pypmis", "-d", "pypmis",
        "-qAt", "-c", SQL
    )
    operational_observation = json.loads(operational["stdout"]) if operational["exit_code"] == 0 else None
    operational_previous_path = ROOT / prior["preservation"]["after"]["file"]
    operational_previous = json.loads(operational_previous_path.read_text(encoding="utf-8"))
    out = {
        "schema_version": 1,
        "captured_at": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
        "scope": "READ_ONLY_AUDIT_FOR_AUTHORIZED_BUSINESS_UAT_SIGNOFF",
        "frozen_commit": FROZEN_COMMIT,
        "initial_pre_authoring_observation": {
            "branch": "main", "commit": FROZEN_COMMIT,
            "working_tree": "CLEAN_OBSERVED_BEFORE_SIGNOFF_ARTIFACT_AUTHORING",
            "tracked_diff": "EMPTY", "cached_diff": "EMPTY",
            "note": "Subsequent untracked sign-off documentation does not alter this initial observation. ACL warnings concerned inherited QA directories only.",
        },
        "commands": commands,
        "code_baseline_unchanged": (
            commands["head"]["stdout"] == FROZEN_COMMIT
            and commands["product_diff_frozen"]["exit_code"] == 0
            and not commands["product_diff_frozen"]["stdout"]
            and not commands["untracked_backend_frontend"]["stdout"]
            and all(row["matches"] for row in hashes)
        ),
        "captured_hashes": hashes,
        "captured_hash_counts": {"product": 5, "fixture": 9, "all_match": all(row["matches"] for row in hashes)},
        "technical_results_source": artifact(RESULTS.relative_to(ROOT)),
        "historical_technical_state": prior["release"],
        "historical_test_counts": {key: value["counts"] for key, value in prior["tests"].items()},
        "historical_test_evidence_integrity": {
            key: {"file": value["file"], "sha256": digest(ROOT / value["file"]),
                  "matches_captured_hash": digest(ROOT / value["file"]) == value["sha256"]}
            for key, value in prior["tests"].items()
        },
        "historical_identity": prior["identity"],
        "historical_gate": {
            "frozen": prior["gate"]["frozen"],
            "published_policy": prior["gate"]["policy"],
            "prefreeze_readiness": {key: prior["gate"]["readiness"].get(key) for key in (
                "readiness_status", "source_current", "required_requirement_count",
                "valid_requirement_count", "coverage_percent", "blockers"
            )},
        },
        "historical_fid": prior["fid"]["captured"],
        "historical_post_fid": {key: prior["postFid"]["current"].get(key) for key in (
            "id", "eligibility_status", "source_current", "eligibility_round",
            "investment_decision_id", "project_workspace_id", "fid_decision_hash",
            "decision_package_hash", "configuration_id", "configuration_hash",
            "blockers_json", "eligible_for_activation", "eligible_for_initialization"
        )},
        "prior_final_artifacts": [artifact(path) for path in (
            "outputs/gate07j-controlled-class-b-20261016/P&Pmis_Strategic_Macroprocess_Final_Release_Closeout.docx",
            "outputs/gate07j-controlled-class-b-20261016/P&Pmis_Strategic_Macroprocess_UAT_Plan_and_Results.docx",
            "outputs/gate07j-controlled-class-b-20261016/P&Pmis_Strategic_Macroprocess_UAT_Traceability.xlsx",
        )],
        "private_uat_runtime": {
            "db": uat_db, "api": uat_api,
            "volume": {key: volume.get(key) for key in ("Name", "CreatedAt", "Driver", "Labels")} if volume else None,
            "named_volume_exists": volume is not None,
            "selected_business_state_currently_verified": False,
            "classification": "RUNTIME_STOPPED_HISTORICAL_TECHNICAL_EVIDENCE_PRESERVED",
            "note": "No container started, volume mounted elsewhere, or database changed. Named-volume presence is not proof of current selected records; historical evidence is not represented as a new runtime revalidation.",
        },
        "operational": {
            "command": operational,
            "observation": operational_observation,
            "previous_observation": artifact(operational_previous_path.relative_to(ROOT)),
            "matches_previous_observation": operational_observation == operational_previous,
            "transaction": "BEGIN READ ONLY; SELECT; ROLLBACK",
        },
        "new_migrations": 0, "database_writes": 0, "containers_started": 0,
        "new_tests_executed": 0, "new_business_approvals": 0,
        "smallest_business_gap": "No actual authorized decisions, identities, dates or approval references for the 15 business acceptance areas have been supplied. Completion remains 0/15, UAT_SIGNOFF_PENDING.",
        "separate_runtime_gap": "Private persistent UAT is stopped; an attended live review would require controlled startup, which this read-only audit did not perform.",
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
