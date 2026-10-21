"""Collect actual Scope release evidence; never infer PASS from implementation."""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from urllib.request import urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1ba-20261020"
DOCS = ROOT / "docs/validation/wave-o1ba-20261020"
PROMPT = Path(
    "C:/Users/Ricardo/Documents/P&P/P&Pmis Construction AI/Diseño/Operation Processes/PROMPT_WAVE_O1B_A_SCOPE_FOUNDATION_3D_SCOPE_ITEMS_EXECUTION_STRATEGY_PLAN_ITEMS.md"
)


def read(path):
    return json.loads(path.read_text("utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def junit(filename, name):
    cases = []
    for row in ET.parse(QA / filename).getroot().iter("testcase"):
        result = (
            "FAIL"
            if row.find("failure") is not None or row.find("error") is not None
            else "SKIP"
            if row.find("skipped") is not None
            else "PASS"
        )
        cases.append(
            {
                "name": row.get("name"),
                "class": row.get("classname"),
                "seconds": float(row.get("time", 0)),
                "result": result,
                "evidence": f"outputs/.qa/wave-o1ba-20261020/{filename}",
            }
        )
    return {
        "name": name,
        "file": filename,
        "tests": len(cases),
        "passed": sum(row["result"] == "PASS" for row in cases),
        "failed": sum(row["result"] == "FAIL" for row in cases),
        "skipped": sum(row["result"] == "SKIP" for row in cases),
        "cases": cases,
    }


def main():
    suites = [
        junit(
            "postgresql-release-final.xml",
            "Scope sources lifecycle security and additive migration PostgreSQL",
        ),
        junit(
            "regression-initial.xml",
            "Existing O1A and canonical strategic regression PostgreSQL",
        ),
        junit(
            "legacy-compatibility.xml",
            "Existing O1A legacy query and configuration protection",
        ),
        junit("frontend-release-final.xml", "Scope frontend component contracts"),
    ]
    browser = read(QA / "chromium-release4/browser-uat.json")
    before = read(DOCS / "preservation-before.json")["observation"]
    after = read(DOCS / "preservation-after.json")["observation"]
    preservation = all(
        before[key] == after[key]
        for key in (
            "canonical_id14_row_sha256",
            "project14_row_sha256",
            "project14_references",
        )
    )
    cases = {
        (case["class"], case["name"]): case
        for suite in suites
        for case in suite["cases"]
    }
    migration = read(QA / "migration-roundtrip.json")
    app_unchanged = before["product_source_sha256"]["frontend/src/App.tsx"] == digest(
        ROOT / "frontend/src/App.tsx"
    )
    lint = read(QA / "frontend-eslint-final.json")
    engineering = {
        "app_unchanged": app_unchanged,
        "migration_additive_roundtrip": migration["o1a_preserved"]
        and len(migration["new_tables"]) == 12
        and all(step.endswith("PASS") for step in migration["steps"]),
        "scoped_lint_no_errors": all(row["errorCount"] == 0 for row in lint),
        "scoped_security_review_recorded": (DOCS / "security-review.md").is_file(),
    }
    successful = (
        all(
            suite["tests"] > 0 and not suite["failed"] and not suite["skipped"]
            for suite in suites
        )
        and browser.get("result") == "PASS"
        and preservation
        and all(engineering.values())
    )
    text = PROMPT.read_text("utf-8")
    criteria = re.findall(
        r"^(.+) = PASS$",
        text.split("# 32. RELEASE CRITERIA", 1)[1].split("# 33.", 1)[0],
        re.MULTILINE,
    )
    requirements = re.findall(r"^# (\d+)\. (.+)$", text, re.MULTILINE)
    source_performance = read(QA / "import-performance.json")["observations"]
    timing = [
        [row["label"], row["n"], row["min_ms"], row["median_ms"], row["max_ms"]]
        for row in source_performance
    ]
    observations = browser.get("observations", [])
    for label in sorted({row["label"] for row in observations}):
        values = [row["elapsed_ms"] for row in observations if row["label"] == label]
        timing.append(
            [label, len(values), min(values), round(median(values), 2), max(values)]
        )
    with urlopen("http://127.0.0.1:8852/openapi.json", timeout=30) as response:
        openapi = json.load(response)
    api = [
        [
            method.upper(),
            route,
            operation.get("operationId", ""),
            "Canonical tenant/Workspace Scope RBAC",
            "backend/app/modules/scope_foundation/router.py",
        ]
        for route, methods in openapi["paths"].items()
        if route.startswith("/api/v1/scope/")
        for method, operation in methods.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    defects = [
        [
            "O1BA-01",
            "Validation",
            "Generic-route negative tests lacked the existing legacy configurator membership",
            "RESOLVED",
            "Explicit isolated legacy membership exercises the dedicated API guard",
        ],
        [
            "O1BA-02",
            "Validation",
            "Excel edit test omitted immutable source reference and revision",
            "RESOLVED",
            "Preserve actual lineage in the edit payload; original source quantity stays fixed",
        ],
        [
            "O1BA-03",
            "Environment",
            "Initial Chromium bundle did not contain the latest quantity selector",
            "RESOLVED",
            "Rebuilt production bundle and restarted isolated preview",
        ],
        [
            "O1BA-04",
            "Validation",
            "Exact select label included option text in Chromium",
            "RESOLVED",
            "Use accessible combobox role and anchored name",
        ],
        [
            "O1BA-05",
            "Build",
            "Final quantity array callback types and testing-library options",
            "RESOLVED",
            "Typed source records and valid query options; tsc and component tests repeated",
        ],
        [
            "O1BA-06",
            "Baseline",
            "Historical Alembic chain assumes an initial ORM schema",
            "EXISTING_LIMITATION",
            "Proved real additive0069-to0070 roundtrip after explicit isolated baseline bootstrap",
        ],
        [
            "O1BA-07",
            "Deployment",
            "Normal local database has not received Scope migration or provisioning",
            "PLANNED_ROLLOUT",
            "Backup, additive upgrade and explicit scoped onboarding required",
        ],
        [
            "O1BA-08",
            "Scale",
            "Development fixture observations do not demonstrate production load capacity",
            "DOCUMENTED_LIMIT",
            "No production SLA or full-model scalability claim",
        ],
        [
            "O1BA-09",
            "P1",
            "Direct Excel source creation could relabel the staged unit",
            "RESOLVED",
            "Reject source unit mismatch; direct API negative and same-unit positive regression",
        ],
        [
            "O1BA-10",
            "P2",
            "Pending Plan could publish after its approved Scope was replaced",
            "RESOLVED",
            "Recheck current baseline membership at Plan publication; stale Scope regression",
        ],
        [
            "O1BA-11",
            "Build",
            "React compiler rejected memoization derived from an unstable array selection",
            "RESOLVED",
            "Memoize candidate model selection; repeated ESLint without errors and rebuilt preview",
        ],
        [
            "O1BA-12",
            "Warning",
            "Scoped ESLint reports existing viewer effects and one model dependency warning",
            "DOCUMENTED_LIMIT",
            "Zero lint errors; warning-only optimization suggestions do not block the real geometry journey",
        ],
    ]
    data = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "issue_date": "20 de octubre de 2026",
        "prompt_sha256": digest(PROMPT),
        "baseline_head": "c75a7da3db3bdcf326b6bed7834182ee126da921",
        "release_validated": successful,
        "release_state": "WAVE_O1B_A_SCOPE_FOUNDATION_RELEASE_VALIDATED"
        if successful
        else "WAVE_O1B_A_SCOPE_FOUNDATION_VALIDATION_PENDING",
        "final_output": "READY_FOR_WAVE_O1B_B_SCHEDULE_FOUNDATION"
        if successful
        else "VALIDATION_PENDING",
        "strategic_state": "STRATEGIC_MACROPROCESS_TECHNICALLY_READY_UAT_SIGNOFF_PENDING",
        "next_recommendation": "WAVE O1B-B — SCHEDULE FOUNDATION",
        "suites": suites,
        "cases": list(cases.values()),
        "distinct_test_cases": len(cases),
        "recorded_test_executions": sum(suite["tests"] for suite in suites),
        "browser": browser,
        "performance": timing,
        "api": api,
        "defects": defects,
        "engineering_checks": engineering,
        "requirements": [
            [
                int(number),
                name,
                "CLOSEOUT_MANIFEST"
                if int(number) in {30, 31, 35}
                else "PASS"
                if successful
                else "VALIDATION_PENDING",
            ]
            for number, name in requirements
        ],
        "release_criteria": [
            [
                f"RC-{index:02}",
                criterion,
                "PASS" if successful else "VALIDATION_PENDING",
                "migration-roundtrip.json"
                if "PostgreSQL" in criterion
                else "chromium-release4/browser-uat.json"
                if "Chromium" in criterion
                else "preservation-before.json and preservation-after.json"
                if "Project 14" in criterion
                else "security-review.md and final PostgreSQL security cases"
                if any(
                    term in criterion
                    for term in (
                        "SoD",
                        "RBAC",
                        "ADMIN",
                        "ETag",
                        "Idempotency",
                        "Audit",
                        "open S",
                    )
                )
                else "Source and integration review; module README and frozen source snapshot"
                if criterion.startswith("No ")
                else "postgresql-release-final.xml and thematic cases in sheets02 to11",
            ]
            for index, criterion in enumerate(criteria, 1)
        ],
        "project14": after["canonical_project14"],
        "project14_sha256": after["canonical_id14_row_sha256"],
        "project14_preserved": preservation,
        "app_unchanged": app_unchanged,
        "migration": migration,
    }
    (DOCS / "package-data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "release": data["release_state"],
                "distinct_cases": len(cases),
                "browser_checks": len(browser.get("checks", [])),
                "api_routes": len(api),
                "criteria": len(criteria),
            }
        )
    )


if __name__ == "__main__":
    main()
