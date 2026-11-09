"""Pair real browser outcomes with unchanged checked frontend sources."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1c-20261106"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    chromium = QA / "chromium"
    frontend_path = QA / "frontend-validation.json"
    browser_path = chromium / "browser-uat.json"
    business_path = QA / "frontend-business-uat-source-proof.json"
    frontend = json.loads(frontend_path.read_text("utf-8"))
    browser = json.loads(browser_path.read_text("utf-8"))
    business = json.loads(business_path.read_text("utf-8"))
    layout = json.loads((chromium / "layout.json").read_text("utf-8"))
    assert all(
        proof["result"] == "PASS" for proof in (frontend, browser, business, layout)
    )
    assert (
        frontend["source_unchanged_during_validation"]
        and business["source_unchanged_during_validation"]
    )
    assert frontend["source_sha256"] and not browser["browser_errors"]
    assert browser["checks"] and all(
        check["result"] == "PASS" for check in browser["checks"]
    )
    for name, expected in frontend["source_sha256"].items():
        assert digest(ROOT / name) == expected, name
    assert business["source_sha256"].keys() == frontend["source_sha256"].keys()
    changed = {
        name
        for name, sha in business["source_sha256"].items()
        if frontend["source_sha256"][name] != sha
    }
    presentation_path = chromium / "presentation-recheck.json"
    presentation = None
    if changed:
        assert presentation_path.is_file(), (
            "Frontend changed after business UAT: real presentation recheck required"
        )
        presentation = json.loads(presentation_path.read_text("utf-8"))
        assert presentation["result"] == "PASS"
        assert presentation["source_sha256"] == frontend["source_sha256"]
        assert changed == {
            "frontend/src/features/forecast-foundation/ReadPanels.tsx",
            "frontend/src/features/forecast-foundation/ReportingPanels.tsx",
            "frontend/src/features/forecast-foundation/forecastFoundation.css",
            "frontend/src/features/forecast-foundation/forecastFoundation.test.tsx",
        }
        assert set(presentation["presentation_changes_from_business_uat"]) == changed
        assert presentation["business_uat_sha256"] == digest(browser_path)
        assert presentation["business_source_proof_sha256"] == digest(business_path)
        assert presentation["final_frontend_validation_sha256"] == digest(frontend_path)
        assert presentation["business_responses_mocked"] is False
        assert (
            not presentation["business_write_attempts"]
            and not presentation["browser_errors"]
        )
        for proof_key, business_key in (
            ("project_workspace_id", "project_workspace_id"),
            ("forecast_id", "forecast"),
            ("report_id", "report"),
        ):
            assert presentation[proof_key] == browser["created"][business_key], (
                proof_key
            )
        hashes = presentation["frozen_content_hashes"]
        for key in ("forecast", "report"):
            assert (
                hashes[key]["before"]
                == hashes[key]["after"]
                == browser["source_hashes"][key]
            ), key
        assert hashes["audit_history"]["before"] == hashes["audit_history"]["after"]
        screenshots = presentation["screenshot_sha256"]
        assert set(screenshots) == {
            f"presentation-{panel}-{viewport}.png"
            for panel in ("audit", "single-point-curve", "dashboard-actions")
            for viewport in ("desktop", "mobile")
        }
        for name, expected in screenshots.items():
            assert digest(chromium / name) == expected, name
        layout = {name: presentation[name] for name in ("desktop", "mobile")}
    for name, width in (("desktop", 1440), ("mobile", 390)):
        assert layout[name]["width"] == width, name
        assert layout[name]["documentWidth"] <= layout[name]["width"] + 2, name
    result = {
        **layout,
        "result": "PASS",
        "source_sha256": frontend["source_sha256"],
        "business_responses_mocked": False,
        "presentation_revalidated": presentation is not None,
        "business_uat_sha256": digest(browser_path),
        "presentation_recheck_sha256": digest(presentation_path)
        if presentation
        else None,
    }
    (chromium / "layout-final.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "result": "PASS",
                "checked_sources": len(frontend["source_sha256"]),
                "viewport_layouts": 2,
            }
        )
    )


if __name__ == "__main__":
    main()
