"""Verify and aggregate the preserved, segmented Chromium O3B lifecycle evidence."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o3b-20261119"
SEGMENTS = (
    (
        "chromium-attempt4",
        "Async form reason was not filled before submit; 58 successful commands retained.",
    ),
    (
        "chromium-closeout",
        "Harness expected zero prior Progress measurements; two fixture measurements existed.",
    ),
    ("chromium-closeout-v2", None),
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    rows = []
    previous = None
    for name, interruption in SEGMENTS:
        path = QA / name / "summary.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["fixture"] == "browser-fixture-v4.json"
        assert data["errors"] == [], f"JavaScript errors in {name}"
        assert all(200 <= step["status"] < 300 for step in data["steps"])
        if previous:
            link = data["previous_segment"]
            assert Path(link["path"]).resolve() == previous["path"].resolve()
            assert link["sha256"] == previous["sha256"]
            assert link["accepted_successful_steps"] == len(previous["data"]["steps"])
            assert (
                data["steps"][: len(previous["data"]["steps"])]
                == previous["data"]["steps"]
            )
        rows.append(
            {
                "path": str(path.relative_to(QA)),
                "sha256": digest(path),
                "original_run_passed": data["passed"],
                "successful_commands": len(data["steps"]),
                "stage": data["stage"],
                "interruption": interruption,
                "finished_at": data["finished_at"],
            }
        )
        previous = {"path": path, "sha256": digest(path), "data": data}

    final = previous["data"]
    assert final["passed"] is True and final["stage"] == "NATIVE_CONTRACTS"
    assert len(final["steps"]) == 62
    runner = json.loads(
        (QA / "playwright-closeout-v2/.last-run.json").read_text(encoding="utf-8")
    )
    assert runner == {"status": "passed", "failedTests": []}
    facts = final["diagnostics"]
    assert facts["persisted_chain"] == {
        "acceptance_id": 6,
        "acceptance_state": "CURRENT",
        "supersedes_id": 4,
        "ncr_status": "CLOSED",
        "failed_id": 17,
        "failed_result": "FAIL",
        "reinspection_id": 19,
        "reinspection_result": "PASS",
    }
    assert facts["mobile"] == {"viewport": 390, "scroll": 390}
    assert facts["progress_before"]["count"] == 2
    assert facts["progress_after"] == {
        "count": 3,
        "id": 34,
        "status": "DRAFT",
        "numerator": "1.60000000",
        "quality_created_quantity": False,
    }
    assert (
        facts["awp"]["release_state_before"]
        == facts["awp"]["release_state_after"]
        == "RELEASED"
    )
    assert facts["awp"]["constraints_unchanged"] is True
    assert facts["contracts"]["information_only"] is True
    screenshots = [
        QA / name / filename
        for name, filenames in (
            (
                "chromium-attempt4",
                (
                    "01-admin-published.png",
                    "02-acceptance.png",
                    "03-ncr-closed-successor.png",
                ),
            ),
            (
                "chromium-closeout-v2",
                (
                    "04-readiness-assessment.png",
                    "05-trace.png",
                    "06-mobile-ready.png",
                    "07-progress-native-quality.png",
                    "08-awp-native-quality.png",
                    "09-contracts-readonly.png",
                ),
            ),
        )
        for filename in filenames
    ]
    result = {
        "status": "PASS_SEGMENTED",
        "passed": True,
        "single_uninterrupted_full_run": False,
        "method": "Three hash-linked real Chromium segments on the same persisted tenant/workspace; no recreated Quality facts or mocked writes.",
        "fixture": final["fixture"],
        "tenant_id": 29,
        "project_workspace_id": 169729974,
        "segments": rows,
        "steps": final["steps"],
        "observed": final["observed"],
        "diagnostics": facts,
        "errors": final["errors"],
        "screenshots": [
            {"path": str(path.relative_to(QA)), "sha256": digest(path)}
            for path in screenshots
        ],
        "scope_limitation": "Browser execution predates the subsequent backend quantity-coverage hardening. Final API/PG validation must independently cover that hardening.",
        "browser_finished_at": final["finished_at"],
        "aggregated_at": datetime.now(UTC).isoformat(),
    }
    target = QA / "browser-summary.json"
    with target.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(
        json.dumps(
            {
                "status": result["status"],
                "commands": len(result["steps"]),
                "segments": len(rows),
            }
        )
    )


if __name__ == "__main__":
    main()
