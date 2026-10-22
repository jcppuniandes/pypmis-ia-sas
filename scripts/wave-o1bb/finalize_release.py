"""Close only a technically validated release with verified native deliverables."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/validation/wave-o1bb-20261020"
QA = ROOT / "outputs/.qa/wave-o1bb-20261020"
OUT = ROOT / "outputs/wave-o1bb-20261020"


def read(path):
    return json.loads(path.read_text("utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    data = read(DOCS / "package-data.json")
    assert data["release_validated"] and all(row[2] == "PASS" for row in data["release_criteria"])
    assert data["backend_result"] == data["regression_result"] == data["preservation_result"] == "PASS"
    assert data["browser"]["result"] == "PASS" and all(row["result"] == "PASS" for row in data["browser"]["checks"])
    assert read(QA / "native-artifact-verification.json")["result"] == "PASS"
    assert read(QA / "visual-review.json")["result"] == "PASS"
    source = read(DOCS / "source-manifest.json")
    assert all((ROOT / name).is_file() and digest(ROOT / name) == value for name, value in source.items())
    deliverables = [OUT / "P&Pmis_Wave_O1B_B_Schedule_Foundation_Technical_Report.docx", OUT / "P&Pmis_Wave_O1B_B_Schedule_Foundation_Traceability.xlsx"]
    result = {
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "issue_date": "2026-10-21",
        "baseline_head": data["baseline_head"],
        "release_state": data["release_state"],
        "final_output": data["final_output"],
        "next_increment": "WAVE O1B-C — COST FOUNDATION",
        "next_increment_started": False,
        "backend_cases": data["backend_count"],
        "regression_cases": data["regression_count"],
        "frontend_cases": len(data["frontend"]),
        "browser_checks": len(data["browser"]["checks"]),
        "project14_preserved": True,
        "normal_database_migrated": False,
        "business_signoff": "PENDING_NO_SIGNATURES",
        "commit_or_push_performed": False,
        "open_S1": 0,
        "open_S2": 0,
        "limitations": ["No XER export", "No native BaselineProject transport", "No P6 application or installed XSD certification", "No production scale SLA", "Remote GitHub CI not run by this task"],
        "artifacts": {str(path.relative_to(ROOT)).replace("\\", "/"): {"bytes": path.stat().st_size, "sha256": digest(path)} for path in deliverables},
        "source_manifest_sha256": digest(DOCS / "source-manifest.json"),
        "native_verification_sha256": digest(QA / "native-artifact-verification.json"),
    }
    (DOCS / "release-manifest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
