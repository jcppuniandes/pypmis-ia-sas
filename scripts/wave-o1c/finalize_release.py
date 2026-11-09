"""Close O1C only after source-fresh functional and native/visual artifact gates."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1c-20261106"
DOCS = ROOT / "docs/validation/wave-o1c-20261106"
OUT = ROOT / "outputs/wave-o1c-20261106"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text("utf-8"))


def main():
    for filename in (
        "forecast-source-proof.json",
        "regression-source-proof.json",
        "frontend-validation.json",
    ):
        proof = read(QA / filename)
        if filename == "frontend-validation.json":
            assert proof["result"] == "PASS" and all(
                row["exit_code"] == 0 for row in proof["checks"]
            )
        else:
            assert (
                proof["pytest_exit_code"] == 0
                and proof["source_unchanged_during_validation"]
            )
        assert proof["source_sha256"]
        for name, expected in proof["source_sha256"].items():
            assert digest(ROOT / name) == expected, name
    data = read(DOCS / "package-data.json")
    native, visual, a11y, browser_visual = (
        read(QA / name)
        for name in (
            "native-artifact-verification.json",
            "visual-review.json",
            "a11y.json",
            "chromium/visual-check.json",
        )
    )
    assert native["result"] == "PASS" and native["discrepancies"] == 0
    assert (
        visual["result"] == "PASS"
        and visual["all_word_pages_reviewed"]
        and visual["all_workbook_sheets_reviewed"]
        and visual["all_workbook_preview_ranges_reviewed"]
    )
    assert browser_visual["result"] == "PASS"
    for proof in (
        browser_visual["original_business_uat_screenshots"],
        browser_visual["final_presentation_screenshots"],
        visual["word_png_sha256"],
        visual["workbook_png_sha256"],
    ):
        assert proof
        for name, expected in proof.items():
            assert digest(QA / name) == expected, name
    render = QA / visual["word_latest_render"]
    provenance = read(render / "render-provenance.json")
    pages = sorted(render.glob("page-*.png"))
    assert len(pages) == visual["word_pages"] == len(provenance["pages"])
    assert all(digest(page) == provenance["pages"][page.name] for page in pages)
    previews = read(QA / "workbook/render-manifest.json")
    assert len(previews) == visual["workbook_preview_ranges"]
    assert len({row["sheet"] for row in previews}) == visual["workbook_sheets"] == 19
    assert a11y["findings"] == [] and all(
        value == 0 for value in a11y["counts"].values()
    )
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
    assert sources
    source_path = DOCS / "source-manifest.json"
    source_path.write_text(json.dumps(sources, indent=2), encoding="utf-8")
    artifacts = sorted(path for path in OUT.iterdir() if path.is_file())
    assert len(artifacts) == 2 and {path.suffix for path in artifacts} == {
        ".docx",
        ".xlsx",
    }
    assert {path.name: digest(path) for path in artifacts} == native["artifact_sha256"]
    assert (
        digest(next(path for path in artifacts if path.suffix == ".docx"))
        == provenance["input_docx_sha256"]
    )
    proofs = [
        QA / name
        for name in (
            "forecast-final-junit.xml",
            "regression-junit.xml",
            "forecast-source-proof.json",
            "regression-source-proof.json",
            "frontend-components.json",
            "frontend-validation.json",
            "frontend-business-uat-source-proof.json",
            "chromium/browser-uat.json",
            "chromium/performance.json",
            "chromium/presentation-recheck.json",
            "chromium/layout-final.json",
            "chromium/visual-check.json",
            "native-artifact-verification.json",
            "a11y.json",
            "visual-review.json",
        )
    ]
    proofs += [
        render / "render-provenance.json",
        *(
            DOCS / name
            for name in (
                "api-observations.json",
                "preservation-before.json",
                "preservation-after.json",
            )
        ),
    ]
    result = {
        "closed_at_utc": datetime.now(UTC).isoformat(),
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "release_state": data["release_state"],
        "final_output": data["final_output"],
        "next_increment": "WAVE O2 — PROCUREMENT, CONTRACTS & ENGINEERING",
        "suite_summary": data["suite_summary"],
        "criteria_count": len(data["release_criteria"]),
        "open_s1": 0,
        "open_s2": 0,
        "known_non_blocking_s3": sum(
            row[1] == "S3" and row[3] == "KNOWN_NON_BLOCKING" for row in data["defects"]
        ),
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
                "release_state": result["release_state"],
                "artifacts": result["artifacts"],
                "sources": len(sources),
            }
        )
    )


if __name__ == "__main__":
    main()
