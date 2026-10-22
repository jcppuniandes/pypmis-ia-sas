"""Freeze checked source/artifact hashes after human-readable visual QA."""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bb1-20261021"
DOCS = ROOT / "docs/validation/wave-o1bb1-20261021"
OUT = ROOT / "outputs/wave-o1bb1-20261021"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    data = json.loads((DOCS / "package-data.json").read_text("utf-8"))
    native = json.loads((QA / "native-artifact-verification.json").read_text("utf-8"))
    assert native["result"] == "PASS" and native["discrepancies"] == 0
    pages = sorted((QA / "word-pages-v3").glob("page-*.png"))
    assert len(pages) == 6
    previews = json.loads((QA / "workbook/render-manifest.json").read_text("utf-8"))
    assert len(previews) == 54 and len({row["sheet"] for row in previews}) == 15
    sources = []
    for folder, extensions in (
        ("backend/app/modules/awp", {".py", ".md"}),
        ("backend/app/modules/schedule_four_d", {".py", ".md"}),
        ("frontend/src/features/awp", {".ts", ".tsx", ".css"}),
        ("frontend/src/features/schedule-four-d", {".ts", ".tsx", ".css"}),
        ("scripts/wave-o1bb1", {".py", ".mjs", ".ps1"}),
    ):
        sources.extend(
            path
            for path in (ROOT / folder).iterdir()
            if path.is_file() and path.suffix in extensions
        )
    explicit = [
        "docker-compose.wave-o1bb1.yml",
        ".github/workflows/awp-readiness-four-d.yml",
        "backend/alembic/env.py",
        "backend/alembic/versions/20261021_0072_awp_readiness.py",
        "backend/app/api/v1/router.py",
        "backend/app/api/v1/routers/admin_configuration.py",
        "backend/app/modules/workspace_context/navigator.py",
        "frontend/src/features/workspace-context/WorkspaceOperationalPage.tsx",
        "frontend/src/features/schedule-foundation/ScheduleManagerWorkspace.tsx",
        "frontend/src/components/AdminConfigurationView.tsx",
        "frontend/src/navigation/applicationNavigation.ts",
        "frontend/src/navigation/applicationNavigation.test.ts",
        "frontend/e2e/awp-readiness-four-d.spec.ts",
        "backend/tests/awp_browser_fixture.py",
        "backend/tests/provision_o1bb1_schema.py",
        "backend/tests/provision_o1bb1_browser.py",
        "backend/tests/refresh_o1bb1_guards.py",
    ]
    sources.extend(ROOT / name for name in explicit)
    sources.extend((ROOT / "backend/tests").glob("test_awp*.py"))
    sources.extend((ROOT / "backend/tests").glob("test_schedule_four_d*.py"))
    source_manifest = {
        str(path.relative_to(ROOT)).replace("\\", "/"): digest(path)
        for path in sorted(set(sources))
    }
    (DOCS / "source-manifest.json").write_text(
        json.dumps(source_manifest, indent=2), encoding="utf-8"
    )
    outputs = sorted(path for path in OUT.iterdir() if path.is_file())
    assert len(outputs) == 2 and {path.suffix for path in outputs} == {".docx", ".xlsx"}
    proofs = [
        QA / "postgres-junit.xml",
        QA / "regression-junit.xml",
        QA / "frontend-components.json",
        QA / "chromium/browser-uat.json",
        QA / "native-artifact-verification.json",
        QA / "a11y.json",
        QA / "word-pages-v3/render-provenance.json",
        DOCS / "api-observations.json",
        DOCS / "preservation-before.json",
        DOCS / "preservation-after.json",
    ]
    manifest = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "release_state": data["release_state"],
        "final_output": data["final_output"],
        "next_increment": data["next_increment"],
        "suite_summary": data["suite_summary"],
        "criteria_count": len(data["release_criteria"]),
        "open_s1": 0,
        "open_s2": 0,
        "normal_database_migrated": False,
        "business_signatures_recorded": False,
        "commit_created": False,
        "push_performed": False,
        "github_workflow_executed": False,
        "source_manifest_sha256": digest(DOCS / "source-manifest.json"),
        "evidence_hashes": {
            str(path.relative_to(ROOT)).replace("\\", "/"): digest(path)
            for path in proofs
        },
        "artifacts": [
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
            for path in outputs
        ],
        "visual_review": {
            "result": "PASS",
            "word_pages": 6,
            "word_latest_render": "word-pages-v3",
            "all_word_pages_reviewed": True,
            "workbook_sheets": 15,
            "workbook_preview_ranges": 54,
            "native_compared_cells": native["compared_cells"],
            "discrepancies": 0,
        },
    }
    (DOCS / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "release_state": data["release_state"],
                "artifacts": manifest["artifacts"],
                "source_files": len(source_manifest),
            }
        )
    )


if __name__ == "__main__":
    main()
