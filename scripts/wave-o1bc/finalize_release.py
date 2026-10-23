"""Freeze actual release proof only after native and visual artifact QA passes."""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bc-20261022"
DOCS = ROOT / "docs/validation/wave-o1bc-20261022"
OUT = ROOT / "outputs/wave-o1bc-20261022"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    data = json.loads((DOCS / "package-data.json").read_text("utf-8"))
    native = json.loads((QA / "native-artifact-verification.json").read_text("utf-8"))
    visual = json.loads((QA / "visual-review.json").read_text("utf-8"))
    a11y = json.loads((QA / "a11y.json").read_text("utf-8"))
    assert native["result"] == "PASS" and native["discrepancies"] == 0
    assert visual["result"] == "PASS" and visual["all_word_pages_reviewed"]
    render = QA / visual["word_latest_render"]
    provenance = json.loads((render / "render-provenance.json").read_text("utf-8"))
    pages = sorted(render.glob("page-*.png"))
    assert len(pages) == visual["word_pages"] == len(provenance["pages"])
    for page in pages:
        assert digest(page) == provenance["pages"][page.name]
    previews = json.loads((QA / "workbook/render-manifest.json").read_text("utf-8"))
    assert len(previews) == visual["workbook_preview_ranges"]
    assert len({row["sheet"] for row in previews}) == visual["workbook_sheets"] == 18
    assert a11y["findings"] == [] and all(
        count == 0 for count in a11y["counts"].values()
    ), a11y
    names = (
        subprocess.check_output(
            ["git", "ls-files", "-m", "-o", "--exclude-standard", "-z"], cwd=ROOT
        )
        .decode("utf-8")
        .split("\0")
    )
    sources = {}
    for name in sorted(set(names)):
        path = ROOT / name
        if (
            not name
            or name.startswith(("outputs/", "docs/validation/"))
            or not path.is_file()
            or path.is_symlink()
        ):
            continue
        sources[name.replace("\\", "/")] = digest(path)
    assert len(sources) > 40
    source_path = DOCS / "source-manifest.json"
    source_path.write_text(json.dumps(sources, indent=2), encoding="utf-8")
    artifacts = sorted(path for path in OUT.iterdir() if path.is_file())
    assert len(artifacts) == 2 and {path.suffix for path in artifacts} == {
        ".docx",
        ".xlsx",
    }
    proofs = [
        QA / "cost-junit.xml",
        QA / "regression-junit.xml",
        QA / "frontend-components.json",
        QA / "chromium/browser-uat.json",
        QA / "chromium/visual-check.json",
        QA / "native-artifact-verification.json",
        QA / "a11y.json",
        QA / "visual-review.json",
        render / "render-provenance.json",
        DOCS / "api-observations.json",
        DOCS / "preservation-before.json",
        DOCS / "preservation-after.json",
    ]
    result = {
        "closed_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "release_state": data["release_state"],
        "final_output": data["final_output"],
        "next_increment": data["next_increment"],
        "suite_summary": data["suite_summary"],
        "postgres_count": data["postgres_count"],
        "policy_bootstrap_count": data["pure_count"],
        "criteria_count": len(data["release_criteria"]),
        "open_s1": 0,
        "open_s2": 0,
        "normal_database_migrated": False,
        "business_signatures_recorded": False,
        "commit_created": False,
        "push_performed": False,
        "github_workflow_executed": False,
        "source_manifest_sha256": digest(source_path),
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
            for path in artifacts
        ],
        "visual_review": {**visual, "native_compared_cells": native["compared_cells"]},
    }
    (DOCS / "release-manifest.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "release_state": data["release_state"],
                "artifacts": result["artifacts"],
                "sources": len(sources),
            }
        )
    )


if __name__ == "__main__":
    main()
