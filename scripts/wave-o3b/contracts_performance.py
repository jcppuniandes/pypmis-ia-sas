"""Observe inherited O2C reads on a real synthetic contract without mutating it."""

import json
import os
import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o3b-20261119"


def main():
    expected = "postgresql+psycopg://o3b:o3b@127.0.0.1:5567/o3b"
    assert (
        os.environ.get("DATABASE_URL") == expected
        and os.environ.get("PYPMIS_O3B_FIXTURE") == "disposable-only"
    )
    os.environ["PYPMIS_O2C_FIXTURE"] = "disposable-only"
    sys.path.insert(0, str(ROOT / "backend"))
    from app.database.session import SessionLocal
    from app.main import app
    from fastapi.testclient import TestClient
    from tests.contracts_release_fixture import contract_root, setup
    from tests.test_contracts_foundation_release import create_chain
    from tests.test_procurement_consumer_release import signatures
    from tests.test_quality_consumer_release import measured_reads

    with SessionLocal() as db, TestClient(app) as client:
        f = setup(db, client)
        assert f.project_workspace_id != 14 and f.legacy_project_id != 14
        contract, version, commitment, _ = create_chain(f)
        tables = (
            "operational_contracts",
            "contract_versions",
            "commercial_commitments",
            "contract_history",
            "contract_changes",
            "operational_contract_notices",
            "operational_payment_certificates",
            "cost_actual_entries",
            "progress_measurements",
            "schedule_versions",
            "forecast_versions",
        )
        before = signatures(f, tables)
        queries = [
            (
                "contracts_" + name,
                f"{contract_root(f)}/{name}/{contract['id']}",
                {},
                "manager",
            )
            for name in ("readiness", "trace")
        ]
        records = measured_reads(f, queries)
        assert signatures(f, tables) == before
        proof = {
            "result": "PASS",
            "environment": "PostgreSQL16 isolated loopback5567 ASGI TestClient Windows",
            "fixture": {
                "tenant_id": f.tenant_id,
                "workspace_id": f.project_workspace_id,
                "contract_id": contract["id"],
                "version_id": version["id"],
                "commitment_id": commitment["id"],
            },
            "before_hashes": before,
            "after_hashes": signatures(f, tables),
            "read_mutations": [],
            "sla_claimed": False,
            "metrics": {
                record["query"]: {
                    **record,
                    "median_response_bytes": median(record["bytes"]),
                }
                for record in records
            },
            "technical_debt": {
                "O2C-S3-01": "MONITORED_NOT_CLOSED",
                "O2C-S3-02": "RETAINED",
            },
        }
        (QA / "contracts-performance.json").write_text(
            json.dumps(proof, indent=2), encoding="utf-8"
        )
        print(json.dumps({"result": "PASS", "queries": len(records)}))


if __name__ == "__main__":
    main()
