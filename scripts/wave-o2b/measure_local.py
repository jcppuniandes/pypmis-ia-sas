"""Observe eight actual API reads after the isolated Chromium workflow."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import httpx
from evidence import QA


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    manifest, target = args.fixture.resolve(), args.target.resolve()
    assert (
        manifest.is_relative_to(QA)
        and target.is_relative_to(QA)
        and not target.exists()
    )
    fixture = json.loads(manifest.read_text("utf-8"))
    workspace = fixture["project_workspace_id"]
    assert isinstance(workspace, int) and workspace > 0 and workspace != 14
    buyer = fixture["users"]["buyer"]
    assert buyer["tenant_id"] == fixture["tenant_id"]
    api = "http://127.0.0.1:8860"
    project = f"/api/v1/procurement/projects/{workspace}"
    day = datetime.now(UTC).date().isoformat()
    with httpx.Client(base_url=api, timeout=20) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": buyer["email"],
                "password": buyer.get("password", fixture["password"]),
                "tenant_id": buyer["tenant_id"],
            },
        )
        login.raise_for_status()
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        rows = client.get(project + "/packages")
        rows.raise_for_status()
        register = rows.json()
        assert len(register["items"]) == 1
        package = register["items"][0]["id"]
        routes = (
            ("Procurement Register", "/packages"),
            ("Procurement Package detail", f"/packages/{package}"),
            ("RFQ queue", "/rfqs"),
            ("PO register", "/purchase-orders"),
            ("Expediting queue", "/expediting-events"),
            ("Shipment register", "/shipments"),
            (
                "Material Availability",
                f"/material-availability?work_package_id={fixture['iwp_id']}&as_of={day}",
            ),
            ("Procurement Look-Ahead", "/lookahead"),
        )
        operations = []
        for name, route in routes:
            samples, sizes, counts = [], [], []
            for _ in range(3):
                start = perf_counter_ns()
                response = client.get(project + route)
                samples.append((perf_counter_ns() - start) / 1_000_000)
                response.raise_for_status()
                data = response.json()
                sizes.append(len(response.content))
                counts.append(len(data.get("items", data.get("requirements", [data]))))
                if name == "Material Availability":
                    assert data["status"] == "READY"
            operations.append(
                {
                    "operation": name,
                    "route": route,
                    "samples_ms": samples,
                    "median_ms": median(samples),
                    "response_json_bytes": sizes[-1],
                    "record_count": counts[-1],
                }
            )
    with target.open("x", encoding="utf-8") as file:
        json.dump(
            {
                "result": "MEASURED",
                "scope": "local real HTTP and isolated PostgreSQL; not production SLA",
                "project_workspace_id": workspace,
                "register_size": register.get("total", len(register["items"])),
                "observed_at_utc": datetime.now(UTC).isoformat(),
                "operations": operations,
            },
            file,
            indent=2,
        )
    print("8 endpoints, 3 real HTTP samples per endpoint")


if __name__ == "__main__":
    main()
