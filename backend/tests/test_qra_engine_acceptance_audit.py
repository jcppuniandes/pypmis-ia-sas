"""Independent adversarial lifecycle and bounded-read audit.

Performance cases opt in and create their own SQLite in-memory database. They
never connect to the operational database, and never seed runtime tenants.
"""

import json
import os
import time
import tracemalloc
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.orm import Session
from tests.test_capital_allocation_wave2a import _context
from tests.test_qra_engine import _engine_fixture, _run_completed
from tests.test_qra_foundation import (
    _draft_model,
    _fixture,
    _key,
    _source_payload,
)

from app.core.time import utc_now
from app.database.seed import seed_demo
from app.database.session import Base, SessionLocal
from app.domain.models import (
    ActivityRelationship,
    RelationshipType,
    ScheduleActivityMap,
    ScheduleImport,
    SecurityAccessAssignment,
    SecurityRole,
)
from app.main import app
from app.modules.basic_data.service import _hash
from app.modules.qra_engine.calculation import calculate
from app.modules.qra_engine.schemas import RunActionIn, RunCreateIn
from app.modules.qra_foundation.models import QraModelDefinition
from app.modules.qra_foundation.schemas import ActionIn, ModelUpdateIn
from app.modules.qra_foundation.service import QraFoundationService


@pytest.fixture(scope="module")
def audit_client():
    with TestClient(app) as value:
        yield value


def _queue(f, seed=6001, iterations=1024):
    service = f["engine"]
    run = service.create_run(
        f["models"]["cost"]["id"], RunCreateIn(seed=seed, iterations=iterations), _key("audit-create")
    )
    service.execute(run["id"], run["revision_version"], RunActionIn(), _key("audit-execute"))
    return run, service._run(run["id"]).task_id


def test_worker_expired_after_last_checkpoint_cannot_resurrect_completed(audit_client):
    with SessionLocal() as db:
        f = _engine_fixture(db)
        service = f["engine"]
        run, task_id = _queue(f)

        def expire_after_numeric_result(snapshot, seed, iterations, progress_callback):
            result = calculate(snapshot, seed, iterations, progress_callback)
            current = service._run(run["id"], lock=True)
            current.heartbeat_at = utc_now() - timedelta(minutes=20)
            service._touch(current)
            db.commit()
            assert run["id"] in service.recover_expired_workers()["failed_run_ids"]
            return result

        outcome = service.worker_execute(run["id"], task_id, calculate_fn=expire_after_numeric_result)
        assert outcome["status"] == "FAILED"
        stored = service._run(run["id"])
        assert stored.failure_reason == "QRA_WORKER_LEASE_EXPIRED"
        assert stored.result_json == {} and stored.result_snapshot_hash is None and stored.completed_at is None
        assert service.evidence(run["id"])["status"] == "UNAVAILABLE"


def test_cancel_during_chunk_never_persists_partial_final_result(audit_client):
    with SessionLocal() as db:
        f = _engine_fixture(db)
        service = f["engine"]
        run, task_id = _queue(f, seed=6002)

        def cancel_inside_chunk(snapshot, seed, iterations, progress_callback):
            def checkpoint(completed):
                progress_callback(completed)
                if completed == 128:
                    current = service.status(run["id"])
                    service.cancel(run["id"], current["revision_version"], RunActionIn(), _key("audit-chunk-cancel"))
                return True

            return calculate(snapshot, seed, iterations, checkpoint)

        outcome = service.worker_execute(run["id"], task_id, calculate_fn=cancel_inside_chunk)
        assert outcome["status"] == "CANCELLED"
        stored = service._run(run["id"])
        assert stored.status == "CANCELLED" and stored.iterations_completed == 128
        assert stored.result_json == {} and stored.result_snapshot_hash is None and stored.trace_hash is None
        assert service.worker_execute(run["id"], task_id)["claimed"] is False


def test_execute_actor_revoked_after_final_checkpoint_fails_closed(audit_client):
    with SessionLocal() as db:
        f = _engine_fixture(db)
        service = f["engine"]
        run, task_id = _queue(f, seed=6003)
        actor = f["author"]
        original = actor.status

        def revoke_after_numeric_result(snapshot, seed, iterations, progress_callback):
            result = calculate(snapshot, seed, iterations, progress_callback)
            actor.status = "inactive"
            db.commit()
            return result

        try:
            outcome = service.worker_execute(run["id"], task_id, calculate_fn=revoke_after_numeric_result)
            assert outcome["status"] == "FAILED"
            stored = service._run(run["id"])
            assert stored.result_json == {} and stored.result_snapshot_hash is None
            assert stored.failure_reason
        finally:
            db.rollback()
            actor.status = original
            db.commit()


def test_accepted_provider_discloses_units_basis_scope_without_source_mutation(audit_client):
    with SessionLocal() as db:
        f = _engine_fixture(db)
        records = []
        for kind in ("cost", "schedule"):
            run = _run_completed(f, kind, seed=2**64 - 1)
            assert run["seed"] == str(2**64 - 1)
            assert run["results"]["seed"] == str(2**64 - 1)
            assert f["engine"].evidence(run["id"])["status"] == "UNAVAILABLE"
            reviewer = f["review_engine"]
            reviewed = reviewer.review_action(
                run["id"], run["revision_version"], RunActionIn(), _key("audit-review"), "review"
            )
            reviewer.review_action(
                run["id"], reviewed["revision_version"], RunActionIn(), _key("audit-accept"), "accept"
            )
            evidence = reviewer.evidence(run["id"])
            assert evidence["status"] == "AVAILABLE" and evidence["not_investment_approval"]
            assert evidence["analysis_scope"]["type"] == "ENTIRE_PROJECT"
            assert evidence["analysis_scope"]["scope_hash"] == _hash(run["results"]["provenance"]["analysis_scope"])
            if kind == "cost":
                assert evidence["result_semantics"]["currency"] == "USD"
                assert evidence["result_semantics"]["cost_basis"] == "BASE_COST"
                assert evidence["result_semantics"]["deterministic_reference"] > 0
            else:
                assert evidence["result_semantics"]["unit"] == "HOURS"
                assert evidence["result_semantics"]["schedule_method"] == "NORMALIZED_ELAPSED_TIME_V1"
                assert evidence["result_semantics"]["date_anchor"]
            assert "raw_iterations" not in json.dumps(evidence)
            records.append((run, deepcopy(f["engine"]._run(run["id"]).result_json)))
        for run, frozen in records:
            assert f["engine"]._run(run["id"]).result_json == frozen


def test_worker_writes_are_chunk_bounded_and_only_execution_audit_authorities(audit_client):
    with SessionLocal() as db:
        f = _engine_fixture(db)
        run, task_id = _queue(f, seed=6004)
        writes = []

        def capture(_conn, _cursor, statement, _params, _context, _executemany):
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                writes.append(statement.lower())

        bind = db.get_bind()
        event.listen(bind, "before_cursor_execute", capture)
        try:
            result = f["engine"].worker_execute(run["id"], task_id)
        finally:
            event.remove(bind, "before_cursor_execute", capture)
        assert result["status"] == "COMPLETED"
        assert writes and all("qra_runs" in statement or "security_events" in statement for statement in writes)
        checkpoints = f["engine"]._run(run["id"]).runtime_metadata["checkpoint_writes"]
        assert checkpoints == 9  # initial zero + eight chunks; never one write/input/iteration
        assert len([statement for statement in writes if statement.startswith("update qra_runs")]) <= checkpoints + 3


def test_summary_projection_preserves_editor_separation_of_duties(audit_client):
    with SessionLocal() as db:
        f = _engine_fixture(db)
        role = db.scalar(
            select(SecurityRole).where(
                SecurityRole.tenant_id == f["author"].tenant_id, SecurityRole.code == "project_definition_manager"
            )
        )
        assert role is not None
        db.add(
            SecurityAccessAssignment(
                tenant_id=f["author"].tenant_id,
                subject_type="user",
                user_id=f["reviewer"].id,
                role_id=role.id,
                scope_type="workspace",
                workspace_id=f["project"].id,
                granted_by_user_id=f["author"].id,
            )
        )
        db.commit()
        editor = QraFoundationService(
            db, f["author"].tenant_id, f["reviewer"].id, _context(f["reviewer"], "project_definition_manager")
        )
        draft = _draft_model(f, f["sources"])
        original = draft["aggregate_json"]
        payload = ModelUpdateIn.model_validate({key: value for key, value in original.items() if key != "preparers"})
        edited = editor.update("model", draft["id"], draft["revision_version"], payload, _key("audit-editor"))
        submitted = f["preparer"].action(
            "model", draft["id"], edited["revision_version"], ActionIn(), _key("audit-editor-submit"), "submit"
        )
        full = editor.record("model", draft["id"])
        summary = editor.record("model", draft["id"], summary=True)
        assert "review" not in full["allowed_actions"]
        assert summary["allowed_actions"] == full["allowed_actions"]
        assert "preparers" not in summary["aggregate_json"]
        with pytest.raises(HTTPException) as exc:
            editor.action(
                "model", draft["id"], submitted["revision_version"], ActionIn(), _key("audit-editor-denied"), "review"
            )
        assert exc.value.status_code == 403


def _measure(bind, callback):
    queries, writes = [], []

    def capture(_conn, _cursor, statement, _params, _context, _executemany):
        queries.append(statement)
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement)

    event.listen(bind, "before_cursor_execute", capture)
    tracemalloc.start()
    cpu_start, start = time.process_time(), time.perf_counter()
    try:
        value = callback()
        wall, cpu = time.perf_counter() - start, time.process_time() - cpu_start
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        event.remove(bind, "before_cursor_execute", capture)
    payload = len(json.dumps(value, default=str).encode())
    assert not writes, writes
    return value, {
        "queries": len(queries),
        "database_writes": len(writes),
        "wall_seconds": wall,
        "cpu_seconds": cpu,
        "peak_traced_bytes": peak,
        "payload_bytes": payload,
    }


@pytest.mark.skipif(os.getenv("PYPMIS_QRA_AUDIT_PERFORMANCE") != "1", reason="Opt-in isolated 5k/10k source profiler")
def test_foundation_5000_10000_bounded_reads_and_source_evaluation_profile():
    engine = create_engine("sqlite:///:memory:")
    assert engine.url.database == ":memory:"
    Base.metadata.create_all(engine)
    cases = []
    try:
        with Session(engine) as db:
            seed_demo(db)
            f = _fixture(db)
            service = f["preparer"]
            for count in (5000, 10000):
                # Only this fresh ephemeral import's logical source is replaced.
                project_id, import_id = f["operational_project"].id, f["schedule_import"].id
                db.execute(
                    delete(ActivityRelationship).where(
                        ActivityRelationship.project_id == project_id,
                        ActivityRelationship.schedule_import_id == import_id,
                    )
                )
                db.execute(
                    delete(ScheduleActivityMap).where(
                        ScheduleActivityMap.project_id == project_id,
                        ScheduleActivityMap.schedule_import_id == import_id,
                    )
                )
                refs = [f"L{index:06d}" for index in range(count)]
                db.add_all(
                    [
                        ScheduleActivityMap(
                            tenant_id=f["author"].tenant_id,
                            project_id=project_id,
                            schedule_import_id=import_id,
                            external_activity_id=ref,
                            activity_name=ref,
                            wbs_code="BENCH",
                        )
                        for ref in refs
                    ]
                )
                db.add_all(
                    [
                        ActivityRelationship(
                            tenant_id=f["author"].tenant_id,
                            project_id=project_id,
                            schedule_import_id=import_id,
                            predecessor_external_id=refs[index],
                            successor_external_id=refs[index + 1],
                            relationship_type=RelationshipType.fs,
                            lag_days=0,
                        )
                        for index in range(count - 1)
                    ]
                )
                metadata = deepcopy(f["schedule_import"].source_metadata)
                calendar_ref = metadata["calendars"][0]["source_id"]
                metadata["activities"] = [
                    {
                        "external_id": ref,
                        "original_duration": "10",
                        "remaining_duration": "10",
                        "duration_unit": "HOURS",
                        "status": "Not Started",
                        "calendar_ref": calendar_ref,
                        "milestone": False,
                    }
                    for ref in refs
                ]
                metadata["relationships"] = [
                    {
                        "predecessor": refs[index],
                        "successor": refs[index + 1],
                        "relationship_type": "FS",
                        "lag": "0",
                        "lag_unit": "HOURS",
                    }
                    for index in range(count - 1)
                ]
                f["schedule_import"].source_metadata = metadata
                db.commit()
                resolved = deepcopy(service.requirements(f["project"].id))
                resolved["policy"]["schedule_quality_rules"]["allowed_open_end_refs"] = [refs[0], refs[-1]]
                payload = _source_payload(f, "schedule").model_dump(mode="json")
                source, adapter = _measure(engine, lambda: service.adapters.schedule(f["project"], import_id))
                evaluation, evaluator = _measure(
                    engine, lambda: service.evaluate(f["project"].id, "schedule", payload, resolved=resolved)
                )
                assert evaluation["readiness_status"] == "READY", evaluation["blockers"]
                assert evaluation["coverage"]["population"] == count
                model = QraModelDefinition(
                    tenant_id=f["author"].tenant_id,
                    project_workspace_id=f["project"].id,
                    number=f"AUDIT-{count}",
                    model_number=f"AUDIT-M-{count}",
                    version=count // 5000,
                    title="Isolated large-model reader audit",
                    configuration_id=f["configuration"]["id"],
                    configuration_revision=f["configuration"]["revision"],
                    configuration_hash=f["configuration"]["hash"],
                    created_by=f["author"].id,
                    analysis_type="SCHEDULE_QRA",
                    aggregate_json={
                        "inputs": [
                            {
                                "source_kind": "SCHEDULE",
                                "source_item_ref": ref,
                                "mode": "DETERMINISTIC",
                                "rationale": "Explicit profiler input",
                                "evidence_refs": [{"reference": "isolated-qa"}],
                            }
                            for ref in refs
                        ],
                        "purpose": "Profile bounded read only",
                        "analysis_scope": {"type": "ENTIRE_PROJECT", "refs": []},
                    },
                    snapshot_json={
                        "population": source["items"],
                        "coverage": {
                            "required": count,
                            "covered": count,
                            "percentage": 100,
                            "missing_refs": [],
                            "unknown_refs": [],
                        },
                        "readiness_status": "READY_FOR_REVIEW",
                        "blockers": [],
                        "no_simulation": True,
                    },
                )
                db.add(model)
                db.commit()
                model_id = model.id
                db.expunge_all()
                service._action_cache.clear()
                page, item_profile = _measure(engine, lambda: service.record_items("model", model_id, page_size=25))
                summary, summary_profile = _measure(engine, lambda: service.record("model", model_id, summary=True))
                assert page["total"] == count and len(page["items"]) == 25
                assert "inputs" not in summary["aggregate_json"]
                assert summary_profile["payload_bytes"] < 10000
                cases.append(
                    {
                        "activities": count,
                        "adapter": adapter,
                        "source_evaluation": evaluator,
                        "items_page25": item_profile,
                        "summary": summary_profile,
                    }
                )
                # Return tracked fixture objects after expunge before next case.
                f["schedule_import"] = db.get(ScheduleImport, import_id)
            # Candidate picker does not decode contents of 1,000 extra imports.
            db.add_all(
                [
                    ScheduleImport(
                        tenant_id=f["author"].tenant_id,
                        project_id=f["operational_project"].id,
                        source=f["schedule_import"].source,
                        status=f["schedule_import"].status,
                        file_name=f"isolated-cost-candidate-{index}.xml",
                        source_metadata={"large_source": ["not_loaded_by_picker"] * 100},
                    )
                    for index in range(1000)
                ]
            )
            db.commit()
            picker, picker_profile = _measure(
                engine, lambda: service.source_options(f["project"].id, "cost", page_size=25)
            )
            assert picker["total"] >= 1000 and len(picker["items"]) == 25
            assert picker_profile["payload_bytes"] < 20000 and picker_profile["queries"] <= 5
            report = {
                "isolation": "SQLite in-memory disposal; no runtime database connections",
                "cases": cases,
                "cost_options_1000_candidates_page25": picker_profile,
                "production_sla": False,
                "profiling_notes": "Tracemalloc instrumentation; retained JSON still parsed inside SQL engine, not materialized in client",
            }
            output = (
                Path(__file__).resolve().parents[2]
                / "outputs"
                / ".qa"
                / "qra-engine"
                / "foundation-query-audit-20261011.json"
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2))
    finally:
        engine.dispose()
