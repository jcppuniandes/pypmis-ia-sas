"""Final read-only code/document/operational preservation audit for sign-off pack."""

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from capture_remediation_preservation import SQL

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs/validation/business-uat-signoff-20261018"
COMMIT = "6672fd5da1f486e6bd571a74bb6d1e8b3337a405"


def command(*args, cwd=ROOT):
    completed = subprocess.run(args, cwd=cwd, capture_output=True, timeout=120, check=False)
    return {
        "command": list(args), "exit_code": completed.returncode,
        "stdout": completed.stdout.decode("utf-8").strip(),
        "stderr": completed.stderr.decode("utf-8").strip(),
    }


def ref(path):
    return {
        "file": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def main():
    baseline = json.loads((AUDIT / "baseline.json").read_text(encoding="utf-8"))
    pack = json.loads((AUDIT / "review-pack-data.json").read_text(encoding="utf-8"))
    evidence = {row["id"]: row for row in pack["evidence_register"]}
    docs = []
    for row in pack["required_documents"]:
        current = ref(ROOT / evidence[row["evidence_id"]]["path"])
        docs.append({
            "id": row["id"], "name": row["name"], "expected_sha256": row["sha256"],
            "current": current, "matches": current["sha256"] == row["sha256"],
        })
    assert len(docs) == 6
    commands = {
        "head": command("git", "rev-parse", "HEAD"),
        "branch": command("git", "branch", "--show-current"),
        "status": command("git", "status", "--short", "--branch"),
        "tracked_changed_paths": command("git", "diff", "--name-only", COMMIT),
        "tracked_stat": command("git", "diff", "--stat", COMMIT),
        "packaging_diff": command("git", "diff", COMMIT, "--", ".gitignore"),
        "product_diff": command(
            "git", "diff", "--name-only", COMMIT, "--", "backend/app", "frontend/src", "backend/alembic"
        ),
        "untracked_product_paths": command(
            "git", "ls-files", "--others", "--exclude-standard", "--",
            "backend/app", "frontend/src", "backend/alembic"
        ),
        "cached_stat": command("git", "diff", "--cached", "--stat"),
        "local_alembic_heads": command(
            str(ROOT / "backend/.venv/Scripts/python.exe"), "-m", "alembic", "heads", cwd=ROOT / "backend"
        ),
    }
    source_hashes = []
    for captured in baseline["captured_hashes"]:
        current = ref(ROOT / captured["file"])
        source_hashes.append({
            "file": captured["file"], "expected_sha256": captured["expected_sha256"],
            "current_sha256": current["sha256"], "matches": current["sha256"] == captured["expected_sha256"],
        })
    operational_command = command(
        "docker", "exec", "pypmis-ia-sas-db-1", "psql", "-U", "pypmis", "-d", "pypmis",
        "-v", "ON_ERROR_STOP=1", "-qAt", "-c", SQL
    )
    assert operational_command["exit_code"] == 0
    operational = json.loads(operational_command["stdout"])
    companions = {}
    for service in ("fresh-api-1", "fresh-redis-1"):
        name = "pypmis-strategic-persistent-uat-" + service
        result = command("docker", "inspect", name)
        assert result["exit_code"] == 0
        data = json.loads(result["stdout"])[0]
        companions[name] = {
            "status": data["State"]["Status"], "running": data["State"]["Running"]
        }
    product_unchanged = (
        commands["head"]["stdout"] == COMMIT
        and commands["product_diff"]["exit_code"] == 0
        and not commands["product_diff"]["stdout"]
        and not commands["untracked_product_paths"]["stdout"]
        and all(row["matches"] for row in source_hashes)
    )
    docs_unchanged = all(row["matches"] for row in docs)
    operational_unchanged = operational == baseline["operational"]["observation"]
    single_packaging_change = commands["tracked_changed_paths"]["stdout"].splitlines() == [".gitignore"]
    source_head_ok = commands["local_alembic_heads"]["stdout"] == "20261011_0068 (head)"
    success = (
        product_unchanged and docs_unchanged and operational_unchanged
        and single_packaging_change and source_head_ok
        and operational["head"] == "20261011_0068"
        and not any(row["running"] for row in companions.values())
    )
    out = {
        "schema_version": 1,
        "observed_at": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
        "result": "PASS_FINAL_SCOPE_AND_PRESERVATION_READ_ONLY" if success else "MISMATCH_PRESERVED_FOR_REVIEW",
        "scope": "CODE_DOCUMENT_HASH_AND_OPERATIONAL_READ_ONLY_FINAL_AUDIT_NOT_BUSINESS_ACCEPTANCE",
        "frozen_commit": COMMIT,
        "commands": commands,
        "product_unchanged": product_unchanged,
        "fourteen_source_hashes": source_hashes,
        "six_source_documents": docs,
        "six_source_documents_unchanged": docs_unchanged,
        "preserved_prior_observations": [ref(AUDIT / path) for path in (
            "baseline.json", "runtime-readonly-20261018.json", "runtime-readonly-20261018-encoding-attempt.json"
        )],
        "operational_readonly_command": operational_command,
        "operational_final_observation": operational,
        "operational_matches_initial_20261018": operational_unchanged,
        "operational_transaction": "BEGIN READ ONLY; SELECT; ROLLBACK",
        "alembic_head": operational["head"],
        "private_api_redis_states": companions,
        "packaging_only_tracked_change": {
            "confirmed": single_packaging_change,
            "path": ".gitignore",
            "addition": "outputs/.qa/business-uat-signoff-20261018/",
            "classification": "QA_ARTIFACT_PACKAGING_EXCLUSION_NOT_FUNCTIONAL_PRODUCT_CHANGE",
            "effect": "Excludes temporary sign-off QA render/test artifacts only; no code, workflow, policy, authority, database state, or source-document change.",
        },
        "no_business_acceptance_inferred": True,
        "signoff_counts": pack["counts"],
        "new_database_business_writes": 0,
        "new_schema_migrations": 0,
        "new_tests_executed": 0,
        "services_started_by_this_audit": 0,
        "commits_or_pushes": 0,
        "script": ref(Path(__file__).resolve()),
    }
    print(json.dumps(out, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
