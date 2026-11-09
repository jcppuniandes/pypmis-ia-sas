"""Read actual isolated O1C API inventory and immutable browser release results."""

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1c-20261106"
OUT = ROOT / "docs/validation/wave-o1c-20261106"
API = "http://127.0.0.1:8858"


def main():
    fixture = json.loads((QA / "browser-fixture.json").read_text("utf-8"))
    browser = json.loads((QA / "chromium/browser-uat.json").read_text("utf-8"))
    assert browser["result"] == "PASS" and not browser["browser_errors"]
    project = fixture["project_workspace_id"]
    assert project != 14 and API.endswith(":8858")
    client = httpx.Client(base_url=API, timeout=120, trust_env=False)
    user = fixture["users"]["manager"]
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": user["email"],
            "tenant_id": user["tenant_id"],
            "password": fixture["password"],
        },
    )
    login.raise_for_status()
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}

    def get(path):
        response = client.get(path, headers=headers)
        response.raise_for_status()
        return response.json()

    overview = get(f"/api/v1/forecast/projects/{project}/overview")
    versions = overview["versions"]
    approved = [r for r in versions if r["status"] == "APPROVED"]
    reports = get(f"/api/v1/reporting/projects/{project}/reports")["items"]
    assert approved and reports
    immutable = [r for r in reports if r["status"] == "PUBLISHED"]
    assert immutable and all(
        r["source_refs_json"] and r["content_hash"] for r in immutable
    )
    timing = json.loads((QA / "chromium/performance.json").read_text("utf-8"))
    assert timing["result"] == "PASS" and timing["observational_only"] is True
    performance = [
        [
            row["operation"],
            len(row["samples_ms"]),
            row["min_ms"],
            row["median_ms"],
            row["max_ms"],
        ]
        for row in timing["operations"]
    ]
    assert all(
        all(status == 200 for status in row["statuses"]) for row in timing["operations"]
    )
    assert len(performance) == 11 and all(row[1] == 3 for row in performance)
    openapi = client.get("/openapi.json")
    openapi.raise_for_status()
    routes = [
        [method.upper(), path, operation.get("operationId", ""), path.split("/")[3]]
        for path, methods in openapi.json()["paths"].items()
        if path.startswith(
            ("/api/v1/forecast/", "/api/v1/performance/", "/api/v1/reporting/")
        )
        for method, operation in methods.items()
        if method in {"get", "post", "put", "delete", "patch"}
    ]
    volume = {
        key: len(overview[key])
        for key in (
            "scope_items",
            "plan_items",
            "packages",
            "schedule_versions",
            "periods",
            "control_accounts",
            "versions",
        )
    }
    volume.update(
        {
            "current_schedule_activities": len(
                fixture["schedule_version"]["snapshot_json"]["activities"]
            ),
            "report_snapshots": len(reports),
            "forecast_assumptions": sum(len(r["assumptions"]) for r in versions),
            "forecast_components": sum(
                sum(
                    len(r[family])
                    for family in (
                        "cost_items",
                        "time_items",
                        "milestones",
                        "resource_items",
                    )
                )
                for r in versions
            ),
        }
    )
    result = {
        "scope": "ISOLATED_LOCAL_OBSERVATION_NOT_PRODUCTION_SLA",
        "project_workspace_id": project,
        "performance": performance,
        "data_volume": volume,
        "api": routes,
        "approved_forecasts": approved,
        "published_reports": reports,
        "timing_context": {
            key: value for key, value in timing.items() if key != "operations"
        },
        "observation_after_browser_uat": True,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "api-observations.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "api_routes": len(routes),
                "operations_measured": len(performance),
                "data_volume": volume,
            }
        )
    )


if __name__ == "__main__":
    main()
