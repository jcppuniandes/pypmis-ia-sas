"""Observe inherited O2C read latency on an actual isolated contract chain.

Only the literal O3A disposable PostgreSQL identity is accepted. Existing O2C
fixture/configuration/contract commands are reused in a new synthetic tenant.
The six measured GET requests run against the real app and database, not mocks.
No SLA or O2C debt closure is inferred from these local ASGI timings.
"""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o3a-20261118"
DATABASE = "postgresql+psycopg://o3a:o3a@127.0.0.1:5564/o3a"


def main():
    assert os.environ.get("PYPMIS_O3A_FIXTURE") == "disposable-only"
    assert os.environ.get("DATABASE_URL") == DATABASE
    assert os.environ.get("PYPMIS_TEST_DATABASE_URL") == DATABASE
    runtime = QA / "contracts-performance-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        AUTO_CREATE_SCHEMA="false",
        SEED_DEMO_DATA="false",
        RATE_LIMIT_ENABLED="false",
        PYPMIS_O2C_FIXTURE="disposable-only",
        LOG_LEVEL="WARNING",
        DOCUMENT_STORAGE_PATH=str(runtime / "document-storage"),
    )
    sys.path.insert(0, str(ROOT / "backend"))
    from app.database.session import SessionLocal, engine
    from app.main import app
    from fastapi.testclient import TestClient
    from sqlalchemy import event
    from tests.contracts_release_fixture import contract_root, setup
    from tests.engineering_release_fixture import request
    from tests.o2b_close_isolation import is_close_consumer_database
    from tests.test_contracts_foundation_release import create_chain
    from tests.test_procurement_consumer_release import signatures
    from tests.test_procurement_o2b_release import expect

    assert (
        engine.url.host,
        engine.url.port,
        engine.url.database,
        engine.url.username,
    ) == ("127.0.0.1", 5564, "o3a", "o3a")
    observed = datetime.now(UTC).isoformat()
    with SessionLocal() as db, TestClient(app) as client:
        assert is_close_consumer_database(db)
        fixture = setup(db, client)
        assert fixture.project_workspace_id != 14 and fixture.legacy_project_id != 14
        contract, version, commitment, _doc = create_chain(fixture)
        assert contract["status"] == "EFFECTIVE" and commitment["status"] == "APPROVED"
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
        before = signatures(fixture, tables)
        mutations = []

        def observe_mutation(
            _connection, _cursor, statement, _parameters, _context, _executemany
        ):
            if (
                statement.lstrip()
                .upper()
                .startswith(("INSERT ", "UPDATE ", "DELETE ", "MERGE "))
            ):
                mutations.append(statement.splitlines()[0][:160])

        results = {}
        event.listen(engine, "before_cursor_execute", observe_mutation)
        try:
            for name, suffix in (
                ("contracts_readiness", "readiness"),
                ("contracts_trace", "trace"),
            ):
                path = f"{contract_root(fixture)}/{suffix}/{contract['id']}"
                samples = []
                for number in range(1, 4):
                    started = perf_counter()
                    response = request(fixture, "GET", path, actor="manager")
                    elapsed = round((perf_counter() - started) * 1000, 2)
                    payload = expect(response, 200)
                    assert isinstance(payload, dict) and payload
                    samples.append(
                        {
                            "sample": number,
                            "ms": elapsed,
                            "response_bytes": len(response.content),
                            "status": 200,
                        }
                    )
                results[name] = {
                    "path": path,
                    "samples": samples,
                    "median_ms": median(sample["ms"] for sample in samples),
                    "median_response_bytes": median(
                        sample["response_bytes"] for sample in samples
                    ),
                    "response_bytes": samples[-1]["response_bytes"],
                }
        finally:
            event.remove(engine, "before_cursor_execute", observe_mutation)
        after = signatures(fixture, tables)
        assert before == after and not mutations, {
            "mutations": mutations,
            "hashes_unchanged": before == after,
        }
        proof = {
            "result": "PASS",
            "observed_at_utc": observed,
            "fixture": {
                "tenant_id": fixture.tenant_id,
                "project_workspace_id": fixture.project_workspace_id,
                "legacy_project_id": fixture.legacy_project_id,
                "contract_id": contract["id"],
                "contract_version_id": version["id"],
                "commitment_id": commitment["id"],
                "contract_state": contract["status"],
                "commitment_state": commitment["status"],
            },
            "environment": "isolated PostgreSQL16 at loopback5564 new synthetic tenant",
            "transport": "real FastAPI ASGI TestClient with PostgreSQL no HTTP or database mocks",
            "method": "three consecutive GET requests per endpoint with no warmup exclusion",
            "metrics": results,
            "read_mutations": mutations,
            "before_hashes": before,
            "after_hashes": after,
            "project14_written": False,
            "sla_claimed": False,
            "technical_debt": {
                "O2C-S3-01": "MONITORED_NOT_CLOSED",
                "O2C-S3-02": "RETAINED_NO_O2C_SCHEMA_CHANGE",
            },
        }
    target = QA / "contracts-performance.json"
    target.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"result": "PASS", "file": str(target), "metrics": results}, indent=2
        )
    )


if __name__ == "__main__":
    main()
