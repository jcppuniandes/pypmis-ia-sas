"""Opt-in real worker/service SQL profile, always on a disposable in-memory DB.

No app lifespan, TestClient, operational database, broker or mocked calculation.
The dispatcher alone is an injected no-op; worker claim, validation, calculation,
checkpoint commits, hashes and final result persistence use production services.
Enable explicitly with PYPMIS_QRA_WORKER_PROFILE=1; the default gate skips this
slow profiler. SQL writes count INSERT/UPDATE/DELETE cursor executions; schema
DDL is listed separately in sql_operations, and is not included in DML writes.
"""

import json
import math
import os
import platform
import re
import time
import tracemalloc
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from tests.test_qra_engine import _engine_fixture
from tests.test_qra_engine_acceptance_audit import _process_peak_rss
from tests.test_qra_foundation import _key

from app.database.session import Base
from app.domain.models import ControlAccount, ScheduleImport, Tenant, UserAccount
from app.modules.basic_data.service import _hash
from app.modules.qra_engine.calculation import engine_manifest
from app.modules.qra_engine.schemas import RunActionIn, RunCreateIn
from app.modules.qra_foundation.models import (
    CostSourceReadinessAssessment,
    QraModelDefinition,
    ScheduleSourceReadinessAssessment,
)

pytestmark = pytest.mark.skipif(
    os.getenv("PYPMIS_QRA_WORKER_PROFILE") != "1",
    reason="Opt-in isolated real-worker 1k inputs / 10k iterations profile",
)


def _profile(bind, name, callback):
    operations, write_tables = Counter(), Counter()
    commits, rollbacks = 0, 0

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        command = statement.lstrip().split(None, 1)[0].upper()
        operations[command] += 1
        match = re.match(r'\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([\w".]+)', statement, re.IGNORECASE)
        if match:
            write_tables[match.group(1).strip('"').lower()] += 1

    def committed(_conn):
        nonlocal commits
        commits += 1

    def rolled_back(_conn):
        nonlocal rollbacks
        rollbacks += 1

    event.listen(bind, "before_cursor_execute", capture)
    event.listen(bind, "commit", committed)
    event.listen(bind, "rollback", rolled_back)
    tracemalloc.start()
    cpu_start, start = time.process_time(), time.perf_counter()
    try:
        value = callback()
        wall, cpu = time.perf_counter() - start, time.process_time() - cpu_start
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        event.remove(bind, "before_cursor_execute", capture)
        event.remove(bind, "commit", committed)
        event.remove(bind, "rollback", rolled_back)
    profile = {
        "wall_seconds": wall,
        "cpu_seconds": cpu,
        "peak_traced_bytes": peak,
        "process_peak_rss_bytes": _process_peak_rss(),
        "sql_statement_executions": sum(operations.values()),
        "database_reads": operations["SELECT"] + operations["WITH"],
        "database_writes": sum(write_tables.values()),
        "sql_operations": dict(sorted(operations.items())),
        "write_tables": dict(sorted(write_tables.items())),
        "commits": commits,
        "rollbacks": rollbacks,
    }
    print(json.dumps({"completed_phase": name, "profile": profile}, sort_keys=True), flush=True)
    return value, profile


def _identity(db):
    tenant = Tenant(name="Isolated real QRA worker profiler", slug="qra-worker-profiler", base_currency="USD")
    db.add(tenant)
    db.flush()
    db.add(
        UserAccount(
            tenant_id=tenant.id,
            email="admin@demo.local",
            full_name="Isolated QRA worker profiler administrator",
            title="Tenant Administrator",
            status="active",
        )
    )
    db.commit()


def _authorities(db, identities):
    material = {
        "operational_accounts": [
            (a.id, a.budget, a.version)
            for a in db.scalars(
                select(ControlAccount)
                .where(ControlAccount.project_id == identities["operational_project_id"])
                .order_by(ControlAccount.id)
                .execution_options(populate_existing=True)
            )
        ],
        "schedule_metadata": db.get(
            ScheduleImport, identities["schedule_import_id"], populate_existing=True
        ).source_metadata,
        "models": [
            (row.id, row.hash, row.aggregate_json, row.snapshot_json)
            for row in db.scalars(
                select(QraModelDefinition)
                .where(QraModelDefinition.project_workspace_id == identities["workspace_id"])
                .order_by(QraModelDefinition.id)
                .execution_options(populate_existing=True)
            )
        ],
    }
    for kind, model in (
        ("cost", CostSourceReadinessAssessment),
        ("schedule", ScheduleSourceReadinessAssessment),
    ):
        material[kind] = [
            (row.id, row.hash, row.aggregate_json, row.snapshot_json)
            for row in db.scalars(
                select(model)
                .where(model.project_workspace_id == identities["workspace_id"])
                .order_by(model.id)
                .execution_options(populate_existing=True)
            )
        ]
    return _hash(material)


def test_real_cost_worker_1000_inputs_10000_iterations_sql_profile():
    engine = create_engine("sqlite:///:memory:")
    assert engine.url.database == ":memory:"
    try:
        _, schema_profile = _profile(engine, "schema", lambda: Base.metadata.create_all(engine))
        with Session(engine) as db:
            _, identity_profile = _profile(engine, "minimal_identity", lambda: _identity(db))
            f, fixture_profile = _profile(
                engine,
                "approved_fixture",
                lambda: _engine_fixture(db, extra_cost_inputs=999, correlated_cost=False),
            )
            service = f["engine"]

            def queue():
                run = service.create_run(
                    f["models"]["cost"]["id"],
                    RunCreateIn(seed=730145, iterations=10000),
                    _key("worker-profile-create"),
                )
                service.execute(run["id"], run["revision_version"], RunActionIn(), _key("worker-profile-execute"))
                return service._run(run["id"])

            queued, queue_profile = _profile(engine, "run_create_and_execution_request", queue)
            frozen = queued.input_snapshot_json
            run_id, task_id = queued.id, queued.task_id
            assert len(frozen["inputs"]) == 1000
            assert frozen["analysis_type"] == "COST_QRA"
            assert frozen["correlations"]["method"] == "NO_CORRELATION"
            assert all(item["distribution_family"] == "TRIANGULAR" for item in frozen["inputs"])
            identities = {
                "operational_project_id": f["operational_project"].id,
                "workspace_id": f["project"].id,
                "schedule_import_id": f["schedule_import"].id,
            }
            before = _authorities(db, identities)
            db.rollback()
            db.expunge_all()
            service._action_cache.clear()
            outcome, worker_profile = _profile(
                engine, "real_worker_execute", lambda: service.worker_execute(run_id, task_id)
            )
            assert outcome["claimed"] and outcome["status"] == "COMPLETED", outcome
            stored = service._run(run_id)
            result = stored.result_json
            checkpoints = stored.runtime_metadata["checkpoint_writes"]
            expected_checkpoints = math.ceil(10000 / frozen["policy"]["chunk_size"]) + 1
            assert checkpoints == expected_checkpoints
            assert worker_profile["database_writes"] > 0
            assert set(worker_profile["write_tables"]) <= {"qra_runs", "security_events"}
            assert worker_profile["write_tables"]["qra_runs"] <= checkpoints + 3
            assert stored.iterations_completed == 10000
            assert stored.result_snapshot_hash == _hash(result) and stored.trace_hash
            assert result["provenance"]["input_count"] == 1000
            assert result["raw_samples"]["persisted"] is False
            assert stored.runtime_metadata["raw_samples_stored"] is False
            assert _authorities(db, identities) == before
            bounds = [(i["values"]["min"], i["values"]["base"], i["values"]["max"]) for i in frozen["inputs"]]
            theoretical_mean = math.fsum((a + b + c) / 3 for a, b, c in bounds)
            theoretical_variance = math.fsum((a * a + b * b + c * c - a * b - a * c - b * c) / 18 for a, b, c in bounds)
            mean_standard_error = math.sqrt(theoretical_variance / 10000)
            assert abs(result["summary"]["mean"] - theoretical_mean) <= 6 * mean_standard_error
            assert result["summary"]["standard_deviation"] ** 2 == pytest.approx(theoretical_variance, rel=0.05)
            report = {
                "status": "PASS",
                "profiled_at_utc": datetime.now(UTC).isoformat(),
                "runtime": {"python_version": platform.python_version(), "platform": platform.platform()},
                "engine_manifest": engine_manifest(),
                "isolation": "SQLite in-memory engine disposed at test end; minimal synthetic tenant/admin; no runtime DB or app lifespan",
                "actual_scope": "Real QraEngineService.worker_execute including DB CAS claim, real RBAC/currentness revalidation before and after calculation, frozen input integrity, real calculate, checkpoint commits, result/provenance/trace hashes, final DB persistence. No calculate_fn substitution. Injected no-op dispatch only; no broker, Celery transport, HTTP/network or PostgreSQL timing.",
                "analysis_type": "COST_QRA",
                "input_count": 1000,
                "iterations": 10000,
                "seed": "730145",
                "chunk_size": frozen["policy"]["chunk_size"],
                "analysis_scope": frozen["analysis_scope"],
                "correlation_method": frozen["correlations"]["method"],
                "distribution_families": result["provenance"]["distribution_families"],
                "setup": {
                    "schema": schema_profile,
                    "minimal_identity": identity_profile,
                    "approved_foundation_fixture": fixture_profile,
                    "create_run_and_execution_request": queue_profile,
                },
                "worker_execution": worker_profile,
                "checkpoint_count": checkpoints,
                "expected_checkpoint_count": expected_checkpoints,
                "checkpoint_semantics": "Initial zero + one per chunk; SQL writes are cursor statement executions, not affected row count. Claim/RUNNING/COMPLETED writes and security events counted separately in write_tables.",
                "worker_runtime_metadata": stored.runtime_metadata,
                "result_payload_bytes": len(json.dumps(result, sort_keys=True, allow_nan=False).encode()),
                "result_snapshot_hash": stored.result_snapshot_hash,
                "trace_hash": stored.trace_hash,
                "source_authorities_unchanged": True,
                "numeric_sanity": {
                    "status": "PASS",
                    "theoretical_independent_triangular_mean": theoretical_mean,
                    "theoretical_independent_triangular_variance": theoretical_variance,
                    "expected_mean_standard_error": mean_standard_error,
                    "observed_mean": result["summary"]["mean"],
                    "observed_variance": result["summary"]["standard_deviation"] ** 2,
                    "convergence_status": result["convergence"]["status"],
                },
                "production_sla": False,
                "profiling_notes": "Tracemalloc instrumentation active. Worker timings include its own serialization/hashing/persistence but exclude fixture setup, separate verification queries and final report serialization. RSS is cumulative process high-water including imports/setup/prior phases; not worker-only allocation delta. File disk durability, broker delivery and production contention are not measured.",
            }
            output = (
                Path(__file__).resolve().parents[2]
                / "outputs"
                / ".qa"
                / "qra-engine"
                / "worker-profile-final-20261012.json"
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False), flush=True)
    finally:
        engine.dispose()
