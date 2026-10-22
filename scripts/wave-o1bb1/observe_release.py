"""Observe actual isolated API data and bounded local timings, not a production SLA."""

import json
import statistics
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bb1-20261021"
OUT = ROOT / "docs/validation/wave-o1bb1-20261021"
API = "http://127.0.0.1:8854"
REASON = "Isolated B1 API observation and controlled performance fixture"


def main():
    fixture = json.loads((QA / "browser-fixture.json").read_text("utf-8"))
    project = fixture["project_workspace_id"]
    assert project != 14 and API.endswith(":8854")
    client = httpx.Client(base_url=API, timeout=120)

    def login(role):
        user = fixture["users"][role]
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": user["email"],
                "tenant_id": user["tenant_id"],
                "password": "O1bb1-disposable-only!",
            },
        )
        response.raise_for_status()
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    planner, manager = login("planner"), login("manager")
    awp = f"/api/v1/awp/projects/{project}"
    schedule = f"/api/v1/schedule/projects/{project}"
    measured = []

    def get(path, headers=planner, params=None):
        response = client.get(path, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    def post(path, payload, version=None, headers=planner):
        command_headers = headers | {"Idempotency-Key": f"observe-{uuid4()}"}
        if version is not None:
            command_headers["If-Match"] = f'"{version}"'
        response = client.post(
            path, headers=command_headers, json={"reason": REASON, **payload}
        )
        response.raise_for_status()
        return response.json()

    # Real operational header and explicit version associations. No cutoff inference.
    period_root = f"/api/v1/operational/projects/{project}/periods"
    periods = get(period_root)
    if isinstance(periods, dict):
        periods = periods.get("items", periods.get("periods", []))
    period = next(
        (row for row in periods if row["period_code"] == "B1-COMMON-PERIOD"), None
    )
    if period is None:
        period = post(
            period_root,
            {
                "period_code": "B1-COMMON-PERIOD",
                "period_start": "2026-10-19",
                "period_end": "2026-10-25",
                "cutoff_at": "2026-10-25T18:00:00-05:00",
                "timezone": "America/Bogota",
                "schedule_data_date": "2026-10-22",
            },
            headers=manager,
        )
    preserved_sources = []
    for source in (fixture["baseline_version"], fixture["current_version"]):
        before = get(f"{schedule}/versions/{source['id']}")
        associations = get(f"{schedule}/period-associations")["items"]
        if not any(
            row["schedule_version_id"] == source["id"]
            and row["period_id"] == period["id"]
            for row in associations
        ):
            post(
                f"{schedule}/versions/{source['id']}/period-associations",
                {"period_id": period["id"]},
                before["version"],
            )
        after = get(f"{schedule}/versions/{source['id']}")
        assert (
            before["snapshot_json"] == after["snapshot_json"]
            and before["content_hash"] == after["content_hash"]
        )
        preserved_sources.append(
            {
                "schedule_version_id": source["id"],
                "content_hash": after["content_hash"],
                "data_date": after["data_date"],
                "unchanged": True,
            }
        )

    packages = get(awp + "/packages")["items"]
    for index in range(32):
        code = f"B1-PERF-{index:03}"
        if not any(row["package_code"] == code for row in packages):
            packages.append(
                post(
                    awp + "/packages",
                    {
                        "package_code": code,
                        "package_type": "SUPPORT",
                        "name": f"Bounded performance observation {index}",
                    },
                )
            )
    candidate = next(row for row in packages if row["package_code"] == "B1-PERF-000")
    for name, path in (
        ("CWA list", "/cwas"),
        ("Package list", "/packages"),
        ("Dependency list", "/dependencies"),
        ("Execution Constraint list", "/constraints"),
    ):
        samples = []
        for _ in range(3):
            start = time.perf_counter()
            get(awp + path)
            samples.append((time.perf_counter() - start) * 1000)
        measured.append(
            [name, len(samples), min(samples), statistics.median(samples), max(samples)]
        )
    for name, path, body in (
        (
            "Readiness assessment",
            f"/packages/{candidate['id']}/assess",
            {
                "as_of": "2026-10-22",
                "evidence_json": {"RESOURCE": "PERF-RESOURCE-EVIDENCE"},
            },
        ),
        (
            "Package Scope mapping",
            f"/packages/{candidate['id']}/mappings",
            {"target_kind": "SCOPE", "target_id": fixture["scope_items"][0]["id"]},
        ),
    ):
        current = get(f"{awp}/packages/{candidate['id']}")
        start = time.perf_counter()
        post(awp + path, body, current["version"])
        elapsed = (time.perf_counter() - start) * 1000
        measured.append([name, 1, elapsed, elapsed, elapsed])
    for name, path, params in (
        (
            "4D initial API view",
            "/4d",
            {"version_id": fixture["current_version"]["id"]},
        ),
        (
            "4D date step API",
            "/4d",
            {
                "version_id": fixture["current_version"]["id"],
                "at": "2026-10-23T12:00:00",
            },
        ),
        (
            "4D traceability",
            f"/4d/traceability/{fixture['scope_items'][0]['id']}",
            {"version_id": fixture["current_version"]["id"]},
        ),
        (
            "4D Baseline Current comparison",
            "/4d/compare",
            {
                "version_id": fixture["current_version"]["id"],
                "baseline_id": fixture["schedule_baseline"]["id"],
                "at": "2026-10-23T12:00:00",
            },
        ),
    ):
        samples = []
        for _ in range(3):
            start = time.perf_counter()
            get(schedule + path, params=params)
            samples.append((time.perf_counter() - start) * 1000)
        measured.append(
            [name, len(samples), min(samples), statistics.median(samples), max(samples)]
        )
    view = get(
        schedule + "/4d", params={"version_id": fixture["current_version"]["id"]}
    )
    assert (
        view["source"]["data_date"].startswith("2026-10-22")
        and view["period_associations"]
    )
    openapi = get("/openapi.json")
    inventory = [
        [
            method.upper(),
            path,
            operation.get("operationId", ""),
            "AWP"
            if "/awp/" in path
            else "Readiness"
            if "/readiness/" in path
            else "4D",
        ]
        for path, methods in openapi["paths"].items()
        if path.startswith(("/api/v1/awp/", "/api/v1/readiness/"))
        or path.startswith("/api/v1/schedule/")
        and "/4d" in path
        for method, operation in methods.items()
        if method in {"get", "post", "put", "delete", "patch"}
    ]
    result = {
        "result": "PASS",
        "api": inventory,
        "performance": measured,
        "data_volume": {
            "packages": len(packages),
            "scope_items": len(fixture["scope_items"]),
            "activities_per_version": len(
                fixture["current_version"]["snapshot_json"]["activities"]
            ),
            "ifc_objects": len(fixture["objects"]),
        },
        "source_preservation": preserved_sources,
        "period_id": period["id"],
        "period_cutoff_at": period["cutoff_at"],
        "four_d_data_date": view["source"]["data_date"],
        "measurement_scope": "Local isolated API latency. No production SLA or browser rendering FPS claim.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "api-observations.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "result": "PASS",
                "routes": len(inventory),
                "operations_measured": len(measured),
                "packages": len(packages),
            }
        )
    )


if __name__ == "__main__":
    main()
