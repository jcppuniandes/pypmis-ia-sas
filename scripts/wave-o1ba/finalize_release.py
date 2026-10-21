"""Freeze verified Scope evidence and final artifact hashes without DB mutations."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/validation/wave-o1ba-20261020"
QA = ROOT / "outputs/.qa/wave-o1ba-20261020"
OUT = ROOT / "outputs/wave-o1ba-20261020"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text("utf-8"))


def main():
    data_path = DOCS / "package-data.json"
    data = read(data_path)
    document = read(QA / "documents-build-manifest.json")
    workbook = read(QA / "workbook/build-manifest.json")
    native = read(QA / "native-artifact-verification.json")
    provenance = read(QA / "word-pages-v1/render-provenance.json")
    source = read(QA / "test-source-snapshot.json")["source_sha256"]
    drift = [name for name, digest in source.items() if sha(ROOT / name) != digest]
    assert not drift
    assert (
        data["release_validated"]
        and data["app_unchanged"]
        and data["project14_preserved"]
    )
    assert data["distinct_test_cases"] == 321
    assert all(row["result"] == "PASS" for row in data["browser"]["checks"])
    assert document["data_sha256"] == workbook["data_sha256"] == sha(data_path)
    assert native["result"] == "PASS" and len(workbook["sheets"]) == 14
    assert read(QA / "word-a11y.json")["counts"] == {"high": 0, "medium": 0, "low": 0}
    review = read(QA / "visual-review.json")
    assert (
        review["word_pages"] == len(provenance["pages"])
        and review["workbook_sheets"] == 14
    )
    assert review["result"] == "PASS"
    paths = [
        OUT / "P&Pmis_Wave_O1B_A_Scope_Foundation_Technical_Report.docx",
        OUT / "P&Pmis_Wave_O1B_A_Scope_Foundation_Traceability.xlsx",
    ]
    assert sha(paths[0]) == document["output_sha256"] == provenance["input_docx_sha256"]
    for name, digest in provenance["pages"].items():
        assert sha(QA / "word-pages-v1" / name) == digest
    evidence = [
        data_path,
        DOCS / "preservation-before.json",
        DOCS / "preservation-after.json",
        DOCS / "security-review.md",
        QA / "chromium-release4/browser-uat.json",
        QA / "frontend-eslint-final.json",
        QA / "migration-roundtrip.json",
        *[QA / row["file"] for row in data["suites"]],
    ]
    result = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "release_state": data["release_state"],
        "final_output": data["final_output"],
        "strategic_state_unchanged": data["strategic_state"],
        "next_recommendation": data["next_recommendation"],
        "distinct_backend_cases": 307,
        "distinct_frontend_cases": 14,
        "browser_checks": len(data["browser"]["checks"]),
        "open_S1": 0,
        "open_S2": 0,
        "deployment_scope": "Isolated API8852 frontend5512 PostgreSQL only",
        "normal_database_migrated": False,
        "business_signoff_recorded": False,
        "commit_or_push_performed": False,
        "project14_sha256": data["project14_sha256"],
        "source_drift_since_snapshot": drift,
        "artifact_visual_review": review,
        "native_artifact_verification": native,
        "artifacts": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha(path),
                "bytes": path.stat().st_size,
            }
            for path in paths
        ],
        "evidence_sha256": {
            path.relative_to(ROOT).as_posix(): sha(path) for path in evidence
        },
        "source_sha256": source,
    }
    (DOCS / "release-manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "release_state",
                    "distinct_backend_cases",
                    "distinct_frontend_cases",
                    "browser_checks",
                    "artifacts",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
