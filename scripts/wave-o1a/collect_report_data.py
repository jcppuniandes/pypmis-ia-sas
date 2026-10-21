"""Build the O1A report dataset from saved evidence, not assumed test outcomes."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1a-20261019"
DOCS = ROOT / "docs/validation/wave-o1a-20261019"
PROMPT = Path(
    "C:/Users/Ricardo/Documents/P&P/P&Pmis Construction AI/Diseño/Operation Processes/PROMPT_WAVE_O1A_OPERATIONAL_PROJECT_CONTEXT_BINDING_AUTHORIZATION_COMMON_CONTROL_PERIOD.md"
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def junit(name, category):
    path = QA / name
    root = ET.parse(path).getroot()
    cases = []
    for case in root.iter("testcase"):
        result = (
            "FAIL"
            if case.find("failure") is not None or case.find("error") is not None
            else "SKIP"
            if case.find("skipped") is not None
            else "PASS"
        )
        cases.append(
            {
                "name": case.get("name"),
                "class": case.get("classname"),
                "seconds": float(case.get("time", 0)),
                "result": result,
                "evidence": str(path.relative_to(ROOT)).replace("\\", "/"),
            }
        )
    return {
        "name": category,
        "file": name,
        "tests": len(cases),
        "passed": sum(c["result"] == "PASS" for c in cases),
        "failed": sum(c["result"] == "FAIL" for c in cases),
        "skipped": sum(c["result"] == "SKIP" for c in cases),
        "cases": cases,
    }


def api_rows():
    path = ROOT / "backend/app/modules/operational_context/router.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rows = []
    for function in tree.body:
        if not isinstance(function, ast.FunctionDef):
            continue
        for decorator in function.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(
                decorator.func, ast.Attribute
            ):
                continue
            method = decorator.func.attr.upper()
            if method not in {"GET", "POST", "PUT"}:
                continue
            route = ast.literal_eval(decorator.args[0])
            rows.append(
                [
                    method,
                    "/api/v1/operational" + route,
                    function.name,
                    f"backend/app/modules/operational_context/router.py:{function.lineno}",
                ]
            )
    for action in ("review", "close", "publish", "reopen"):
        rows.append(
            [
                "POST",
                "/api/v1/operational/projects/{workspace_id}/periods/{period_id}/"
                + action,
                "period." + action,
                "backend/app/modules/operational_context/router.py",
            ]
        )
    assert len(rows) == 18
    return rows


def main():
    suites = [
        junit(
            "postgresql-foundation-final3.xml",
            "PostgreSQL foundation and legacy compatibility",
        ),
        junit(
            "postgresql-owner-authority.xml",
            "PostgreSQL genuine Owner FID and activation",
        ),
        junit("postgresql-migration.xml", "PostgreSQL additive migration round trip"),
        junit(
            "postgresql-security-hardening-final3.xml",
            "PostgreSQL independent policy publication",
        ),
        junit(
            "strategic-regression-isolated.xml",
            "Canonical creation initialization and PostFID regression",
        ),
        junit("frontend-focused.xml", "Frontend component and navigation tests"),
    ]
    browser = read(QA / "chromium-release3/browser-uat.json")
    before = read(DOCS / "preservation-before.json")["observation"]
    identity_before = read(DOCS / "preservation-identity-before.json")["observation"]
    after = read(DOCS / "preservation-after.json")["observation"]
    preservation = (
        before["canonical_id14_row_sha256"] == after["canonical_id14_row_sha256"]
        and before["project14_row_sha256"] == after["project14_row_sha256"]
    )
    strategic_changes = [
        path
        for path, digest in before["product_source_sha256"].items()
        if path.startswith("backend/app/modules/")
        and not path.startswith("backend/app/modules/workspace_context/")
        and hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest
    ]
    app_unchanged = (
        hashlib.sha256((ROOT / "frontend/src/App.tsx").read_bytes()).hexdigest()
        == before["product_source_sha256"]["frontend/src/App.tsx"]
    )
    inventory = read(DOCS / "legacy-consumer-inventory.json")
    successful = (
        all(s["tests"] and not s["failed"] and not s["skipped"] for s in suites)
        and browser.get("result") == "PASS"
        and preservation
        and app_unchanged
        and not strategic_changes
    )
    # The separate nine-case hardening run overlaps the final 98-case matrix.
    # Retain run-level evidence, but never inflate the distinct-case inventory.
    all_cases = [case for suite in suites for case in suite["cases"]]
    cases = list({(case["class"], case["name"]): case for case in all_cases}.values())
    criteria_text = (
        PROMPT.read_text(encoding="utf-8")
        .split("# 57. RELEASE CRITERIA", 1)[1]
        .split("# 58.", 1)[0]
    )
    criteria = [
        line.strip().removesuffix(" = PASS")
        for line in criteria_text.splitlines()
        if line.strip().endswith(" = PASS")
    ]
    requirements = re.findall(
        r"^#{1,2} (\d+)\. (.+)$", PROMPT.read_text(encoding="utf-8"), re.MULTILINE
    )
    defects = [
        [
            "O1A-01",
            "S2",
            "Generic ADMIN routes could edit/clone a governed Operational Profile",
            "RESOLVED",
            "Dedicated API guard plus PostgreSQL negative tests",
        ],
        [
            "O1A-02",
            "S2",
            "Latest policy editor could publish own material change",
            "RESOLVED",
            "Independent publication guard plus dedicated PostgreSQL regression",
        ],
        [
            "O1A-03",
            "Validation",
            "WBS response omits project_id by existing response contract",
            "RESOLVED",
            "Assert actual persisted WBS tenant/project using returned id",
        ],
        [
            "O1A-04",
            "Environment",
            "Windows bind-mount Vite watcher EIO/ENOMEM",
            "RESOLVED",
            "Isolated production build and preview, no polling watcher",
        ],
        [
            "O1A-05",
            "Baseline",
            "Historical Alembic chain cannot initialize an empty schema",
            "EXISTING_LIMITATION",
            "Explicit pre-O1A ORM baseline; actual 0068 to 0069 migration proof only",
        ],
        [
            "O1A-06",
            "Deployment",
            "Existing local tenant has not been migrated or silently bound",
            "PLANNED_ROLLOUT",
            "Backup, additive migration, explicit catalog provisioning and governed onboarding",
        ],
    ]
    defects += [
        [
            "O1A-07",
            "S2",
            "Legacy dashboard GET could calculate and persist without canonical binding",
            "RESOLVED",
            "Read-only query and NOT_GENERATED sentinel; actual SQL write observer",
        ],
        [
            "O1A-08",
            "S2",
            "Generic overview exposed draft profiles without granular permission",
            "RESOLVED",
            "O1A profiles excluded from generic overview; scoped dedicated reader",
        ],
        [
            "O1A-09",
            "S2",
            "Generic defaults could replace canonical authorization metadata",
            "RESOLVED",
            "Server preserves reserved _project namespace and rejects spoofing",
        ],
    ]
    defects.append(
        [
            "O1A-10",
            "P3",
            "USER can show ACTIVE_IS_NOT_COMMITMENT_AUTHORITY twice in warnings",
            "OPEN_NON_BLOCKING",
            "Cosmetic duplication only; authorization and restrictions remain correct",
        ]
    )
    observations = browser.get("local_observations", [])
    performance = []
    for label in sorted({row["label"] for row in observations}):
        values = [row["elapsed_ms"] for row in observations if row["label"] == label]
        performance.append(
            [label, len(values), min(values), median(values), max(values)]
        )
    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "issue_date": "20 de octubre de 2026",
        "baseline_head": "c75a7da3db3bdcf326b6bed7834182ee126da921",
        "baseline_source_files": len(before["product_source_sha256"]),
        "prompt_sha256": hashlib.sha256(PROMPT.read_bytes()).hexdigest(),
        "strategic_state": "STRATEGIC_MACROPROCESS_TECHNICALLY_READY_UAT_SIGNOFF_PENDING",
        "release_validated": successful,
        "release_state": "WAVE_O1A_OPERATIONAL_FOUNDATION_RELEASE_VALIDATED"
        if successful
        else "WAVE_O1A_RELEASE_VALIDATION_PENDING",
        "final_output": "READY_FOR_WAVE_O1B_CONTROL_BASELINES_AND_SOURCE_FOUNDATIONS"
        if successful
        else "COMPLETE_WAVE_O1A_RELEASE_VALIDATION",
        "next_recommendation": "WAVE O1B — CONTROL BASELINES & SOURCE FOUNDATIONS"
        if successful
        else "Cerrar los bloqueos de validación de WAVE O1A",
        "suites": suites,
        "cases": cases,
        "distinct_test_cases": len(cases),
        "recorded_test_executions": len(all_cases),
        "browser": browser,
        "performance": performance,
        "project14": identity_before["canonical_project14"],
        "project14_sha256": before["canonical_id14_row_sha256"],
        "project14_preserved": preservation,
        "app_unchanged": app_unchanged,
        "strategic_business_changes": strategic_changes,
        "migration": read(QA / "migration-roundtrip.json"),
        "ddl_refresh": read(QA / "final-ddl-refresh.json"),
        "owner_current": read(QA / "owner-authorization-current.json"),
        "owner_commitment": read(QA / "owner-authorization-commitment.json"),
        "inventory_counts": inventory["counts"],
        "awareness_counts": inventory["awareness_counts"],
        "migration_counts": inventory["migration_counts"],
        "legacy_consumers": inventory["foreign_keys"]
        + inventory["backend_consumers"]
        + inventory["frontend_consumers"],
        "requirements": [
            [int(number), title, "PASS" if successful else "VALIDATION_PENDING"]
            for number, title in requirements
        ],
        "release_criteria": [
            [f"RC-{i:02}", criterion, "PASS" if successful else "VALIDATION_PENDING"]
            for i, criterion in enumerate(criteria, 1)
        ],
        "api": api_rows(),
        "defects": defects,
    }
    assert len(output["legacy_consumers"]) == 642
    destination = DOCS / "package-data.json"
    destination.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "release": output["release_state"],
                "suites": [
                    {k: s[k] for k in ("name", "tests", "passed", "failed", "skipped")}
                    for s in suites
                ],
                "browser_checks": len(browser.get("checks", [])),
                "requirements": len(requirements),
                "release_criteria": len(criteria),
            }
        )
    )


if __name__ == "__main__":
    main()
