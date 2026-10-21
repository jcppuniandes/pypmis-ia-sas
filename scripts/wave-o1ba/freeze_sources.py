"""Record the final validation source snapshot without modifying product files."""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "outputs/.qa/wave-o1ba-20261020/test-source-snapshot.json"


def main():
    assert not TARGET.exists(), "Never overwrite a source snapshot"
    tracked = subprocess.check_output(
        ["git", "ls-files", "backend/app", "frontend/src", "backend/alembic"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    paths = {ROOT / name for name in tracked}
    for folder in (
        "backend/app/modules/operational_context",
        "backend/app/modules/scope_foundation",
        "frontend/src/features/operational-context",
        "frontend/src/features/scope-foundation",
    ):
        paths.update(
            path
            for path in (ROOT / folder).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
    paths.update(
        ROOT / name
        for name in (
            "backend/alembic/versions/20261020_0070_scope_foundation.py",
            "frontend/src/lib/bimViewerSource.ts",
            "frontend/e2e/scope-foundation.spec.ts",
            "backend/tests/test_scope_foundation_release.py",
            ".github/workflows/wave-o1ba.yml",
        )
    )
    values = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }
    TARGET.write_text(
        json.dumps(
            {
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_sha256": values,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"frozen_sources": len(values)}))


if __name__ == "__main__":
    main()
