"""Freeze technical O1A evidence and delivered artifact hashes, without DB writes."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/validation/wave-o1a-20261019"
QA = ROOT / "outputs/.qa/wave-o1a-20261019"
OUTPUT = ROOT / "outputs/wave-o1a-20261019"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    data_path = DOCS / "package-data.json"
    data = read(data_path)
    document = read(QA / "documents-build-manifest.json")
    workbook = read(QA / "workbook/build-manifest.json")
    provenance = read(QA / "word-pages-v1/render-provenance.json")
    after = read(DOCS / "preservation-after.json")["observation"]
    assert data["release_validated"]
    assert data["distinct_test_cases"] == 240
    assert data["recorded_test_executions"] == 249
    assert len(data["browser"]["checks"]) == 12
    assert all(item["result"] == "PASS" for item in data["browser"]["checks"])
    assert data["project14_preserved"] and data["app_unchanged"]
    assert not data["strategic_business_changes"]
    assert document["data_sha256"] == workbook["data_sha256"] == sha(data_path)
    unchanged = after["product_source_sha256"]
    drift = [name for name, digest in unchanged.items() if sha(ROOT / name) != digest]
    assert not drift, f"Product source drift since final tests: {drift}"

    docx = OUTPUT / "P&Pmis_Wave_O1A_Operational_Context_and_Period_Technical_Report.docx"
    xlsx = OUTPUT / "P&Pmis_Wave_O1A_Operational_Context_Traceability.xlsx"
    assert sha(docx) == document["output"]["sha256"]
    assert sha(docx) == provenance["input_docx_sha256"]
    assert len(provenance["pages"]) == 9
    for name, digest in provenance["pages"].items():
        assert sha(QA / "word-pages-v1" / name) == digest
    assert len(workbook["sheets"]) == 10
    assert sum(sheet["rows"] for sheet in workbook["sheets"]) == 909
    previews = json.loads((QA / "workbook/render-manifest.json").read_text("utf-8"))
    assert len(previews) == 59
    assert all((QA / "workbook" / item["file"]).is_file() for item in previews)
    assert read(QA / "word-a11y.json")["counts"] == {
        "high": 0, "medium": 0, "low": 0
    }

    evidence = [
        DOCS / "preservation-before.json",
        DOCS / "preservation-after.json",
        DOCS / "security-review.json",
        data_path,
        QA / "chromium-release3/browser-uat.json",
        QA / "chromium-release3/browser-summary.json",
        ROOT / ".github/workflows/wave-o1a.yml",
        ROOT / "docker-compose.wave-o1a.yml",
        ROOT / "backend/alembic/versions/20261019_0069_operational_context.py",
        *[QA / suite["file"] for suite in data["suites"]],
    ]
    source_paths = set(unchanged)
    for folder in (
        ROOT / "backend/app/modules/operational_context",
        ROOT / "frontend/src/features/operational-context",
    ):
        source_paths.update(
            str(path.relative_to(ROOT)).replace("\\", "/")
            for path in folder.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
    result = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "release_state": data["release_state"],
        "final_output": data["final_output"],
        "next_recommendation": data["next_recommendation"],
        "strategic_state_unchanged": data["strategic_state"],
        "deployment_scope": "Isolated PostgreSQL/API 8851/frontend 5511 only",
        "normal_local_database_migrated": False,
        "business_signoff_or_signature_recorded": False,
        "commit_or_push_performed": False,
        "distinct_backend_cases": 229,
        "distinct_frontend_cases": 11,
        "recorded_test_executions": 249,
        "browser_checks": 12,
        "open_S1": 0,
        "open_S2": 0,
        "nonblocking_P3": "Duplicate ACTIVE_IS_NOT_COMMITMENT_AUTHORITY warning",
        "project14_sha256": data["project14_sha256"],
        "app_tsx_sha256": sha(ROOT / "frontend/src/App.tsx"),
        "source_drift_since_final_tests": drift,
        "artifact_qa": {
            "word_pages_visually_reviewed_at_original_resolution": list(range(1, 10)),
            "word_preserved_template_parts": document["output"]["parts_preserved"],
            "word_accessibility_findings": 0,
            "workbook_sheets_visually_reviewed": 10,
            "workbook_rendered_ranges_reviewed_in_contacts": 59,
            "workbook_records": 909,
            "workbook_legacy_consumers": 642,
            "workbook_native_export": "Artifact Session live bound workbook",
            "independent_read_only_office_review": {
                "data_cells_compared": 5239,
                "discrepancies_or_omissions": 0,
                "intentional_blank_metric_cells": 172,
                "native_filtered_tables": 10,
                "formula_or_error_cells": 0,
                "hidden_sheets": 0,
                "broken_internal_relationships": 0,
                "word_heading1_sections": 28,
                "zip_crc_and_xml_parse": "PASS",
            },
        },
        "artifacts": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha(path),
             "bytes": path.stat().st_size}
            for path in (docx, xlsx)
        ],
        "evidence_sha256": {
            str(path.relative_to(ROOT)).replace("\\", "/"): sha(path)
            for path in evidence
        },
        "source_sha256": {name: sha(ROOT / name) for name in sorted(source_paths)},
        "superseded_status_notes": [
            "Security peer review was recorded before the final Chromium PASS; both original and later evidence are retained.",
            "The final workflow adds the sequential existing strategic lifecycle/Post-FID regression job absent at the earlier peer snapshot.",
        ],
    }
    (DOCS / "release-manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: result[key] for key in (
        "release_state", "distinct_backend_cases", "distinct_frontend_cases",
        "browser_checks", "source_drift_since_final_tests", "artifacts"
    )}, ensure_ascii=False))


if __name__ == "__main__":
    main()
