"""Read actual isolated Cost endpoints and bounded local timings, never an SLA."""

import json
import statistics
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bc-20261022"
OUT = ROOT / "docs/validation/wave-o1bc-20261022"
API = "http://127.0.0.1:8856"


def main():
    fixture = json.loads((QA / "browser-fixture.json").read_text("utf-8"))
    project = fixture["project_workspace_id"]
    assert project != 14 and API.endswith(":8856")
    client = httpx.Client(base_url=API, timeout=120, trust_env=False)
    user = fixture["users"]["cost_controller"]
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": user["email"],
            "tenant_id": user["tenant_id"],
            "password": "O1bc-disposable-only!",
        },
    )
    login.raise_for_status()
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    root = f"/api/v1/cost/projects/{project}"

    def get(path):
        response = client.get(path, headers=headers)
        response.raise_for_status()
        return response.json()

    overview = get(root + "/overview")
    budgets = [r for r in overview["budgets"] if r["status"] == "APPROVED"]
    apus = [r for r in overview["apus"] if r["status"] == "PUBLISHED"]
    baselines = [r for r in overview["baselines"] if r["status"] == "APPROVED"]
    assert budgets and apus and baselines, (
        "Real Chromium must finish approval before observations"
    )
    endpoints = [
        ("Árbol CBS", "/cbs"),
        ("Mapeos Cost", "/mappings"),
        ("Lista Budget", "/budgets"),
        ("Cálculo Budget", f"/budgets/{budgets[-1]['id']}/calculation"),
        ("Cálculo APU", f"/apus/{apus[-1]['id']}/calculation"),
        ("Carga Cost Baseline", f"/baselines/{baselines[-1]['id']}"),
        ("Consulta phasing", "/phasing"),
        ("Conciliación compromisos", "/commitments/reconciliation"),
        ("Lista Actuals", "/actuals"),
        ("Cost overview", "/financial-overview"),
    ]
    performance = []
    for label, suffix in endpoints:
        samples = []
        for _ in range(3):
            start = time.perf_counter()
            get(root + suffix)
            samples.append((time.perf_counter() - start) * 1000)
        performance.append(
            [
                label,
                len(samples),
                min(samples),
                statistics.median(samples),
                max(samples),
            ]
        )
    openapi = client.get("/openapi.json")
    openapi.raise_for_status()
    routes = [
        [method.upper(), path, operation.get("operationId", ""), "Cost"]
        for path, methods in openapi.json()["paths"].items()
        if path.startswith("/api/v1/cost/")
        for method, operation in methods.items()
        if method in {"get", "post", "put", "delete", "patch"}
    ]
    volume = {
        key: len(overview[key])
        for key in (
            "cbs",
            "cost_codes",
            "control_accounts",
            "mappings",
            "rates",
            "apus",
            "budgets",
            "budget_lines",
            "baselines",
            "phasing",
            "scope_items",
            "plan_items",
            "packages",
            "schedule_versions",
            "periods",
        )
    }
    OUT.mkdir(parents=True, exist_ok=True)
    observation = {
        "scope": "ISOLATED_LOCAL_OBSERVATION_NOT_PRODUCTION_SLA",
        "project_workspace_id": project,
        "performance": performance,
        "data_volume": volume,
        "api": routes,
        "financial_overview": get(root + "/financial-overview"),
        "cash_flow": get(root + "/cash-flow"),
        "legacy_candidate_boundary": get(root + "/legacy-candidates")["authority"],
    }
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
