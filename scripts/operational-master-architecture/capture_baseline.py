"""Read-only product fingerprint for architecture-only deliverables."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
VALIDATION = ROOT / "docs/validation/operational-master-architecture-20261019"
PRODUCT_PATHS = [
    "backend/app",
    "backend/alembic",
    "backend/tests",
    "frontend/src",
    "frontend/tests",
    ".github/workflows",
]
PROMPT = Path(
    "C:/Users/Ricardo/Documents/P&P/P&Pmis Construction AI/Diseño/Operation Processes/PROMPT_OPERATIONAL_MACROPROCESS_MASTER_ARCHITECTURE_DOMAIN_MAP_IMPLEMENTATION_ROADMAP.md"
)


def command(args):
    result = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "argv": args,
        "exit_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    VALIDATION.mkdir(parents=True, exist_ok=True)
    listed = command(["git", "ls-files", *PRODUCT_PATHS])
    assert listed["exit_code"] == 0
    files = {name: digest(ROOT / name) for name in listed["stdout"].splitlines()}
    commands = {
        "head": command(["git", "rev-parse", "HEAD"]),
        "status": command(["git", "status", "--short", "--branch"]),
        "diff_stat": command(["git", "diff", "--stat"]),
        "product_diff": command(["git", "diff", "HEAD", "--", *PRODUCT_PATHS]),
        "cached": command(["git", "diff", "--cached", "--stat"]),
        "log": command(["git", "log", "-n", "10", "--oneline"]),
    }
    data = {
        "schema_version": 1,
        "observed_at": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
        "scope": "READ_ONLY_REPOSITORY_FINGERPRINT_NO_APPLICATION_OR_DATABASE_COMMANDS",
        "commands": commands,
        "product_file_count": len(files),
        "product_hashes": files,
        "prompt": {"path": str(PROMPT), "sha256": digest(PROMPT)},
        "strategic_state": "STRATEGIC_MACROPROCESS_TECHNICALLY_READY_UAT_SIGNOFF_PENDING",
        "application_tests_executed": 0,
        "database_commands": 0,
        "schema_migrations": 0,
        "product_edits": 0,
        "business_signoffs": 0,
        "commits_or_pushes": 0,
    }
    if args.final:
        baseline = json.loads(
            (VALIDATION / "baseline.json").read_text(encoding="utf-8")
        )
        changed = [
            name
            for name in set(files) | set(baseline["product_hashes"])
            if files.get(name) != baseline["product_hashes"].get(name)
        ]
        data["comparison"] = {
            "changed_product_files": changed,
            "head_unchanged": commands["head"]["stdout"]
            == baseline["commands"]["head"]["stdout"],
            "prompt_unchanged": data["prompt"] == baseline["prompt"],
        }
        data["result"] = (
            "PASS"
            if not changed
            and data["comparison"]["head_unchanged"]
            and data["comparison"]["prompt_unchanged"]
            and not commands["product_diff"]["stdout"]
            else "FAIL"
        )
        name = "final-scope-audit.json"
    else:
        data["result"] = "CAPTURED"
        name = "baseline.json"
        assert not (VALIDATION / name).exists(), "Do not overwrite initial baseline"
    (VALIDATION / name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "file": name,
                "result": data["result"],
                "head": commands["head"]["stdout"],
                "product_files": len(files),
            }
        )
    )
    if data["result"] == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
