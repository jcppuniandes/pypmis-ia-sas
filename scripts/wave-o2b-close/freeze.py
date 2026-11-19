"""Fingerprint the dirty source tree and check the exact same source after validation."""

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2b-close-20261111"
HEAD = "20261111_0078"
SCOPE = (
    "backend/app",
    "backend/tests",
    "backend/alembic",
    "backend/alembic.ini",
    "backend/pyproject.toml",
    "frontend/src",
    "frontend/e2e",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/playwright.config.ts",
    "scripts/wave-o2b-close/freeze.py",
    "scripts/wave-o2b-close/postgres_regression.py",
    "scripts/wave-o2b-close/chromium_gate.py",
    "scripts/wave-o2b-close/preservation.py",
    "scripts/wave-o2b-close/generate_historical_bootstrap.py",
    "docker-compose.wave-o2a.yml",
    "docker-compose.wave-o2b.yml",
    ".gitignore",
)
EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".css",
    ".sql",
    ".json",
    ".ini",
    ".toml",
    ".yml",
    ".xml",
    ".xer",
    ".ifc",
}


def snapshot():
    files = subprocess.check_output(
        ["git", "ls-files", "-c", "-o", "--exclude-standard", "--", *SCOPE],
        cwd=ROOT,
        text=True,
    ).splitlines()
    return {
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "alembic_head": HEAD,
        "sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in sorted(set(files))
            if (ROOT / path).is_file()
            and (Path(path).suffix in EXTENSIONS or path == ".gitignore")
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "verify"))
    parser.add_argument("name")
    args = parser.parse_args()
    assert args.name.isalnum() or all(c.isalnum() or c == "-" for c in args.name)
    target = QA / "release" / f"freeze-{args.name}.json"
    current = snapshot()
    if args.mode == "capture":
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as handle:
            json.dump(
                {"frozen_at_utc": datetime.now(UTC).isoformat(), "source": current},
                handle,
                indent=2,
            )
    else:
        assert current == json.loads(target.read_text("utf-8"))["source"], (
            "Source changed after freeze"
        )
    print(
        f"{args.mode}: {current['git_commit'][:7]}, {HEAD}, {len(current['sha256'])} files"
    )


if __name__ == "__main__":
    main()
