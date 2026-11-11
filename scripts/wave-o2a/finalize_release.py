"""Seal only source-fresh O2A evidence and visually verified native deliverables."""

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2a-20261109"
OUT = ROOT / "outputs/wave-o2a-20261109"
DOCS = ROOT / "docs/validation/wave-o2a-20261109"


def read(path):
    return json.loads(path.read_text("utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    data = read(QA / "release-evidence.json")
    assert data["release_status"] == "VALIDATED"
    assert all(status == "PASS" for status in data["gate_status"].values())
    assert data["release_marker"] == "WAVE_O2A_ENGINEERING_FOUNDATION_RELEASE_VALIDATED"
    assert (
        data["next_increment"]
        == "READY_FOR_WAVE_O2B_PROCUREMENT_MATERIALS_LOGISTICS_FOUNDATION"
    )
    native = read(QA / "native-artifact-proof.json")
    report = OUT / "P&Pmis_Wave_O2A_Engineering_Foundation_Technical_Report.docx"
    workbook = OUT / "P&Pmis_Wave_O2A_Engineering_Foundation_Traceability.xlsx"
    assert native["report_sha256"] == digest(report) and native[
        "workbook_sha256"
    ] == digest(workbook)
    reviewed = read(QA / "visual-review.json")
    assert reviewed["result"] == "PASS" and reviewed["all_word_pages_reviewed"] is True
    assert (
        reviewed["all_workbook_ranges_reviewed"] is True
        and reviewed["all_chromium_screens_reviewed"] is True
    )
    assert reviewed["report_sha256"] == digest(report) and reviewed[
        "workbook_sha256"
    ] == digest(workbook)
    word_dir = QA / reviewed["word_pages_directory"]
    word = read(word_dir / "render-provenance.json")
    assert word["input_docx_sha256"] == digest(report)
    assert all(digest(word_dir / name) == sha for name, sha in word["pages"].items())
    sheet_dir = QA / "workbook"
    sheet = read(sheet_dir / "render-provenance.json")
    assert sheet["workbook_sha256"] == digest(workbook)
    assert sheet["traceability_data_sha256"] == digest(QA / "traceability-data.json")
    assert all(digest(sheet_dir / name) == sha for name, sha in sheet["images"].items())
    specs = read(QA / "traceability-data.json")
    assert len(specs) == 15 and len(specs[-1]["rows"]) == 41
    assert {row[-1] for row in specs[-1]["rows"]} == {"PASS"}
    summary = {
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "baseline_head": data["baseline_head"],
        "release_marker": data["release_marker"],
        "final_output": data["next_increment"],
        "next_increment": "WAVE O2B — PROCUREMENT, MATERIALS & LOGISTICS FOUNDATION",
        "scope": "Technical validation in isolated PostgreSQL/API/frontend; not production deployment or business acceptance",
        "postgresql": data["postgresql"]["counts"],
        "chromium_checks": len(data["browser"]["uat"]["checks"]),
        "chromium_project_workspace_id": data["browser"]["uat"]["project_workspace_id"],
        "performance": data["browser"]["performance"]["operations"],
        "register_size": data["browser"]["performance"]["register_size"],
        "project14_canonical_sha256": data["preservation"]["canonical_sha256"],
        "defects": data["open_defects"]["defects"],
        "artifacts": {path.name: digest(path) for path in (report, workbook)},
        "native_artifacts": native,
        "word_pages": len(word["pages"]),
        "workbook_sheets": 15,
        "release_criteria": 41,
        "git_commit_created": False,
        "git_push_performed": False,
        "normal_database_migrated": False,
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    browser_dir = ROOT / data["browser"]["run_directory"]
    readback = read(browser_dir / "awp-current-readback.json")
    assert readback["http_status"] == 200
    assert readback["project_workspace_id"] == data["browser"]["uat"]["project_workspace_id"]
    assert readback["current_readiness"]["readiness_state"] == "READY"
    assert readback["current_readiness"]["stale"] is False
    assert readback["package_release_state"] == "NOT_RELEASED"
    retained = {
        "final-postgres-junit.xml": QA / "final-postgres-junit.xml",
        "postgres-source-proof.json": QA / "postgres-source-proof.json",
        "frontend-validation.json": QA / "frontend-validation.json",
        "browser-uat.json": browser_dir / "browser-uat.json",
        "browser-source-proof.json": browser_dir / "browser-source-proof.json",
        "performance.json": browser_dir / "performance.json",
        "awp-current-readback.json": browser_dir / "awp-current-readback.json",
    }
    # Retain proofs, never the fixture manifest, JWTs, passwords, DB dump or trace.
    for name, source in retained.items():
        destination = DOCS / name
        if destination.exists():
            assert digest(destination) == digest(source), (
                "Do not replace a retained release proof"
            )
        else:
            shutil.copyfile(source, destination)
    summary["retained_evidence_sha256"] = {
        name: digest(source) for name, source in retained.items()
    }
    (DOCS / "release-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "release_marker",
                    "word_pages",
                    "workbook_sheets",
                    "postgresql",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
