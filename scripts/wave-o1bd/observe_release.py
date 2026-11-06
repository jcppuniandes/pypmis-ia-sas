"""Read actual isolated Progress API inventory and frozen reporting evidence."""

import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bd-20261104"
OUT = ROOT / "docs/validation/wave-o1bd-20261104"
API = "http://127.0.0.1:8857"


def main():
    fixture = json.loads((QA / "browser-fixture.json").read_text("utf-8"))
    browser = json.loads((QA / "chromium/browser-uat.json").read_text("utf-8"))
    assert browser["result"] == "PASS" and not browser["browser_errors"]
    project = fixture["project_workspace_id"]
    assert project != 14 and API.endswith(":8857")
    client = httpx.Client(base_url=API, timeout=120, trust_env=False)
    user = fixture["users"]["manager"]
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": user["email"],
            "tenant_id": user["tenant_id"],
            "password": "O1bd-disposable-only!",
        },
    )
    login.raise_for_status()
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    root = f"/api/v1/progress/projects/{project}"

    def get(path):
        response = client.get(path, headers=headers)
        response.raise_for_status()
        return response.json()

    overview = get(root + "/overview")
    snapshots = get(root + "/evm/snapshots")["items"]
    computable = [r for r in snapshots if r["status"] == "COMPUTABLE"]
    assert computable, "Real Chromium must save the approved EVM basis"
    bundles = get(root + "/baseline-bundles")["items"]
    assert any(r["status"] == "APPROVED" for r in bundles)
    performance_proof = json.loads(
        (QA / "chromium/performance.json").read_text("utf-8")
    )
    assert performance_proof["stage"] == "AFTER_PERIOD_PUBLICATION_BEFORE_PROFILE_DRIFT"
    performance = performance_proof["rows"]
    assert len(performance) == 9 and all(r[1] == 3 for r in performance)
    openapi = client.get("/openapi.json")
    openapi.raise_for_status()
    routes = [
        [method.upper(), path, operation.get("operationId", ""), "Progress"]
        for path, methods in openapi.json()["paths"].items()
        if path.startswith("/api/v1/progress/")
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
            "scope_baselines",
            "schedule_baselines",
            "cost_baselines",
            "periods",
            "control_accounts",
            "rules",
            "measurements",
        )
    }
    observation = {
        "scope": "ISOLATED_LOCAL_OBSERVATION_NOT_PRODUCTION_SLA",
        "project_workspace_id": project,
        "performance": performance,
        "data_volume": volume,
        "api": routes,
        "evm_snapshots": computable,
        "baseline_bundles": bundles,
        "measurement_progress_values": [
            {
                key: row.get(key)
                for key in (
                    "id",
                    "progress_type",
                    "method",
                    "status",
                    "denominator",
                    "progress_value",
                    "period_progress",
                    "period_quantity",
                    "content_hash",
                )
            }
            for row in overview["measurements"]
        ],
        "observation_after_explicit_profile_successor": True,
        "timings_measured_before_profile_drift_by_real_chromium": True,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "api-observations.json").write_text(
        json.dumps(observation, indent=2, ensure_ascii=False), encoding="utf-8"
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
