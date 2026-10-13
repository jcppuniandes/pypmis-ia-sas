"""Real governed Wave 4 lifecycle on SQLite and isolated PostgreSQL.

Broker dispatch is injected in service tests; the calculation kernel, Foundation
sources, actual currentness, RBAC, database receipts and reviews are real.
"""

import re
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from tests.test_capital_allocation_wave2a import _context, _token_headers
from tests.test_qra_foundation import (
    _approve,
    _fixture,
    _inputs,
    _key,
    _ready_sources,
)

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import (
    ControlAccount,
    SecurityEvent,
)
from app.main import app
from app.modules.basic_data.service import _hash
from app.modules.investment_evidence_policy.service import PROVIDER_REGISTRY, InvestmentEvidencePolicyService
from app.modules.qra_engine.calculation import EngineCalculationError
from app.modules.qra_engine.models import QraRun
from app.modules.qra_engine.schemas import RunActionIn, RunCreateIn
from app.modules.qra_engine.service import QraEngineService
from app.modules.qra_foundation.schemas import ConfigurationCloneIn, ConfigurationUpdateIn, ModelCreateIn, ModelUpdateIn


def _engine_settings(**changes):
    """Explicit disposable method; never seeded/published in live tenants."""
    value = {
        "engine_version": "wave4-qra-v1",
        "supported_analysis_types": ["COST_QRA", "SCHEDULE_QRA"],
        "percentiles": [50, 80, 90],
        "histogram_bins": 12,
        "chunk_size": 128,
        "max_correlation_dimension": 100,
        "correlation_sampling": "GAUSSIAN_COPULA_V1",
        "probability_tolerance": 1e-9,
        "psd_tolerance": 1e-10,
        "normal_negative_policy": "TRUNCATE_AT_ZERO",
        "schedule_method": "NORMALIZED_ELAPSED_TIME_V1",
        "schedule_unit": "HOURS",
        "schedule_unit_seconds": 3600,
        "convergence": {"enabled": True, "min_iterations": 100, "relative_mean_standard_error_tolerance": 0.02},
        "iteration_policy": {"minimum": 100, "default": 1024, "maximum": 10000, "allow_override": True},
        "seed_policy": "USER_SPECIFIED",
        "result_review": {"require_review": True, "executor_cannot_accept": True},
        "run_numbering": {"prefix": "QRR", "padding": 6, "separator": "-"},
        "worker_lease_seconds": 600,
        "analytical_indicator_percentile": 80,
        "raw_samples": False,
        "sensitivity_method": "PEARSON_ONLINE_V1",
    }
    value.update(changes)
    return value


def _publish_engine_policy(f, settings=None):
    source = f["configuration"]
    draft = f["preparer"].clone_configuration(
        source["id"],
        source["version"],
        ConfigurationCloneIn(code=f"wave4-{uuid4().hex[:16]}", target_workspace_id=f["enterprise"].id),
        _key("engine-clone"),
    )
    content = deepcopy(draft["content_json"])
    content["reserved_engine_settings"] = settings if settings is not None else _engine_settings()
    draft = f["preparer"].update_configuration(
        draft["id"],
        draft["version"],
        ConfigurationUpdateIn(name="Wave 4 governed disposable method", content_json=content),
        _key("engine-policy-save"),
    )
    f["configuration"] = f["final"].publish_configuration(draft["id"], draft["version"], _key("engine-policy-publish"))
    return f["configuration"]


def _approved_model(f, sources, kind="cost", *, inputs=None, correlations=None):
    analysis = "COST_QRA" if kind == "cost" else "SCHEDULE_QRA"
    row = f["preparer"].create(
        f["project"].id,
        "model",
        ModelCreateIn(analysis_type=analysis, title=f"Approved Wave 4 {kind} model"),
        _key("engine-model-create"),
    )
    changes = {f"{kind}_source_assessment_id": sources[kind]["id"]}
    if correlations is not None:
        changes["correlations"] = correlations
    payload = ModelUpdateIn(
        analysis_type=analysis,
        title=f"Approved Wave 4 {kind} model",
        purpose="Reproducible read-only quantitative analysis",
        inputs=inputs if inputs is not None else _inputs({kind: sources[kind]}),
        **changes,
    )
    row = f["preparer"].update("model", row["id"], row["revision_version"], payload, _key("engine-model-save"))
    return _approve(f, row)


def _engine_fixture(db, *, contexts=False, settings=None, correlated_cost=True, extra_cost_inputs=1):
    f = _fixture(db, contexts=contexts)
    _publish_engine_policy(f, settings)
    # A reviewed disposable estimate is declared by its cost authority BEFORE
    # Foundation snapshots. The original import leaves budget at zero.
    accounts = db.scalars(select(ControlAccount).where(ControlAccount.project_id == f["operational_project"].id)).all()
    for account in accounts:
        account.budget = 1000.0
        account.version += 1
    for index in range(extra_cost_inputs):
        source = accounts[0]
        db.add(
            ControlAccount(
                tenant_id=source.tenant_id,
                project_id=source.project_id,
                wbs_id=source.wbs_id,
                code=f"QRA-WAVE4-COST-{index}-{uuid4().hex[:8]}",
                name=f"Reviewed uncertainty cost item {index + 2}",
                responsible="Disposable estimator",
                discipline=source.discipline,
                budget=500.0 + index * 100.0,
                cbs_code=source.cbs_code,
            )
        )
    # Fixture's manual XML lacks explicit zero-lag units. The source authority
    # declares them BEFORE assessments; no historical QRA/source record edited.
    metadata = deepcopy(f["schedule_import"].source_metadata)
    for relationship in metadata["relationships"]:
        relationship["lag_unit"] = "HOURS"
    f["schedule_import"].source_metadata = metadata
    db.commit()
    f["sources"] = _ready_sources(f)
    cost_inputs = _inputs({"cost": f["sources"]["cost"]})
    correlations = None
    if correlated_cost and len(cost_inputs) >= 2:
        refs = [f"COST:{i.source_item_ref}" for i in cost_inputs]
        correlations = {
            "method": "PAIRWISE_CORRELATION",
            "pairs": [
                {
                    "left": refs[0],
                    "right": refs[1],
                    "coefficient": 0.35,
                    "rationale": "Approved synthetic latent Gaussian dependency from reviewed cost workshop",
                }
            ],
            "groups": [],
            "matrix": [],
        }
    f["models"] = {
        "cost": _approved_model(f, f["sources"], "cost", correlations=correlations),
        "schedule": _approved_model(f, f["sources"], "schedule"),
    }
    f["engine"] = QraEngineService(db, f["author"].tenant_id, f["author"].id, dispatcher=lambda *_: None)
    f["review_engine"] = QraEngineService(db, f["author"].tenant_id, f["reviewer"].id)
    return f


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as value:
        yield value


@pytest.fixture(scope="module")
def governed(client):
    with SessionLocal() as db:
        yield _engine_fixture(db)


def _run_completed(f, kind="cost", *, seed=771, iterations=1024):
    service = f["engine"]
    row = service.create_run(f["models"][kind]["id"], RunCreateIn(seed=seed, iterations=iterations), _key("run-create"))
    service.execute(row["id"], row["revision_version"], RunActionIn(), _key("run-execute"))
    stored = service._run(row["id"])
    result = service.worker_execute(row["id"], stored.task_id)
    assert result["status"] == "COMPLETED", result
    return service.run(row["id"], summary=False)


@pytest.mark.parametrize("kind", ["cost", "schedule"])
def test_real_approved_model_run_reproduction_and_independence(governed, kind):
    f = governed
    db = f["engine"].db
    authorities = {
        "foundation": _hash([f["preparer"].record("model", v["id"]) for v in f["models"].values()]),
        "source": _hash([f["preparer"].record(k, v["id"]) for k, v in f["sources"].items()]),
        "operational": _hash(
            {
                "import": f["schedule_import"].source_metadata,
                "accounts": [
                    (a.id, a.budget, a.version)
                    for a in db.scalars(
                        select(ControlAccount).where(ControlAccount.project_id == f["operational_project"].id)
                    )
                ],
            }
        ),
    }
    writes = []

    def audit_writes(_connection, _cursor, statement, _parameters, _context, _many):
        match = re.match(r'\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([\w".]+)', statement, re.IGNORECASE)
        if match:
            writes.append(match.group(1).strip('"').lower())

    event.listen(db.get_bind(), "before_cursor_execute", audit_writes)
    try:
        left, right = _run_completed(f, kind), _run_completed(f, kind)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", audit_writes)
    assert writes and set(writes) <= {
        "qra_runs",
        "qra_run_reviews",
        "qra_commands",
        "security_events",
        "admin_number_sequences",
    }, writes
    assert left["id"] != right["id"]
    assert left["run_number"].startswith("QRR-")
    assert left["results"]["summary"] == right["results"]["summary"]
    assert left["results"]["percentiles"] == right["results"]["percentiles"]
    assert left["result_snapshot_hash"] == right["result_snapshot_hash"]
    assert left["trace_hash"] == right["trace_hash"]
    assert left["engine_version"] == "wave4-qra-v1"
    assert left["formula_version"] == left["results"]["engine_manifest"]["formula_version"]
    assert left["results"]["engine_manifest"]["prng_algorithm"] == "PCG64"
    assert left["results"]["convergence"]["status"] == "CONVERGED"
    assert left["results"]["sensitivity"][0]["coefficient"] is not None
    if kind == "schedule":
        assert left["results"]["summary"]["mean_completion_date"]
        assert len(left["results"]["milestones"]) == 2
        assert all("completion_date" in p for p in left["results"]["percentiles"])
    else:
        assert left["results"]["summary"]["cost_basis"] == "BASE_COST"
        assert left["results"]["summary"]["currency"] == "USD"
        assert left["results"]["analytical_contingency_indicator"]["interpretation"].startswith(
            "ANALYTICAL_INDICATOR_ONLY"
        )
    after = {
        "foundation": _hash([f["preparer"].record("model", v["id"]) for v in f["models"].values()]),
        "source": _hash([f["preparer"].record(k, v["id"]) for k, v in f["sources"].items()]),
        "operational": _hash(
            {
                "import": f["schedule_import"].source_metadata,
                "accounts": [
                    (a.id, a.budget, a.version)
                    for a in db.scalars(
                        select(ControlAccount).where(ControlAccount.project_id == f["operational_project"].id)
                    )
                ],
            }
        ),
    }
    assert after == authorities


def test_governed_cost_model_non_psd_matrix_blocks_before_run_insert(client):
    with SessionLocal() as db:
        f = _engine_fixture(db, extra_cost_inputs=2, correlated_cost=False)
        refs = [f"COST:{i.source_item_ref}" for i in _inputs({"cost": f["sources"]["cost"]})]
        assert len(refs) == 3
        model = _approved_model(
            f,
            f["sources"],
            correlations={
                "method": "MATRIX_CORRELATION",
                "refs": refs,
                "matrix": [[1, 0.9, 0.9], [0.9, 1, -0.9], [0.9, -0.9, 1]],
                "rationale": "Structurally valid approved matrix; PSD must be independently validated by engine",
            },
        )
        assert model["status"] == "APPROVED_FOR_ANALYSIS"
        preflight = f["engine"].preflight(model["id"])
        assert not preflight["eligible"] and "CORRELATION_MATRIX_NOT_PSD" in preflight["blockers"]
        count = db.scalar(select(func.count(QraRun.id)))
        with pytest.raises(HTTPException) as exc:
            f["engine"].create_run(model["id"], RunCreateIn(seed=123), _key("non-psd"))
        assert exc.value.status_code == 409 and "CORRELATION_MATRIX_NOT_PSD" in exc.value.detail["blockers"]
        assert db.scalar(select(func.count(QraRun.id))) == count


def test_independent_registry_provider_accepted_current_evidence_without_gate_mutation(governed):
    f = governed
    db = f["engine"].db
    gate = InvestmentEvidencePolicyService(db, f["author"].tenant_id, f["reviewer"].id)
    assert PROVIDER_REGISTRY["QRA_RESULT_PROVIDER"]["status"] == "AVAILABLE"
    assert gate._provider_payload("QRA_RESULT_PROVIDER", {}, "EACH_PROJECT", f["project"].id) is None
    run = _run_completed(f)
    reviewed = f["review_engine"].review_action(
        run["id"], run["revision_version"], RunActionIn(), _key("registry-review"), "review"
    )
    f["review_engine"].review_action(
        run["id"], reviewed["revision_version"], RunActionIn(), _key("registry-accept"), "accept"
    )
    writes = []

    def collect(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE ")):
            writes.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", collect)
    try:
        payload = gate._provider_payload("QRA_RESULT_PROVIDER", {}, "EACH_PROJECT", f["project"].id)
        assert payload and not gate.validate_provider_contract(payload)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", collect)
    assert payload["source_current"] and payload["source_record_id"] == str(run["id"])
    assert payload["readiness_status"] in {"READY", "READY_WITH_WARNINGS"}
    assert payload["evidence_refs"][0]["trace_hash"] == run["trace_hash"]
    assert payload["evidence_refs"][0]["not_investment_approval"] is True
    assert not writes, writes


def test_seed_change_compatible_comparison(governed):
    a, b = _run_completed(governed, seed=35), _run_completed(governed, seed=36)
    assert a["result_snapshot_hash"] != b["result_snapshot_hash"]
    compared = governed["engine"].compare(a["id"], b["id"])
    assert compared["compatible"] and compared["seed_changed"]
    assert compared["percentile_deltas"] and compared["driver_deltas"]
    schedule = _run_completed(governed, "schedule")
    with pytest.raises(HTTPException) as exc:
        governed["engine"].compare(a["id"], schedule["id"])
    assert exc.value.status_code == 422


def test_completed_run_immutable_separate_review_acceptance_provider(governed):
    f, service = governed, governed["engine"]
    complete = _run_completed(f)
    row = service._run(complete["id"])
    original = deepcopy(row.result_json)
    row.comments = "Forbidden completed mutation"
    with pytest.raises(ValueError, match="immutable"):
        service.db.flush()
    service.db.rollback()
    assert service.evidence(complete["id"])["status"] == "UNAVAILABLE"
    with pytest.raises(HTTPException) as exc:
        service.review_action(
            complete["id"], complete["revision_version"], RunActionIn(), _key("self-review"), "review"
        )
    assert exc.value.status_code == 403
    reviewed = f["review_engine"].review_action(
        complete["id"],
        complete["revision_version"],
        RunActionIn(comments="Independent analytical review"),
        _key("review"),
        "review",
    )
    accepted = f["review_engine"].review_action(
        complete["id"],
        reviewed["revision_version"],
        RunActionIn(comments="Accepted as analysis, not FID"),
        _key("accept"),
        "accept",
    )
    assert accepted["status"] == "COMPLETED" and accepted["review_status"] == "ACCEPTED"
    evidence = f["review_engine"].evidence(complete["id"])
    assert evidence["status"] == "AVAILABLE" and evidence["source_current"]
    assert evidence["not_investment_approval"] and evidence["raw_samples"] == "NOT_EXPOSED"
    assert service._run(complete["id"]).result_json == original
    review = service._review(complete["id"])
    review.acceptance_comments = "Forbidden acceptance rewrite"
    with pytest.raises(ValueError, match="immutable"):
        service.db.flush()
    service.db.rollback()


def test_queued_manifest_immutable_before_execution(governed):
    service = governed["engine"]
    run = service.create_run(governed["models"]["cost"]["id"], RunCreateIn(seed=1), _key("freeze"))
    stored = service._run(run["id"])
    stored.seed = "123"
    with pytest.raises(ValueError, match="Frozen"):
        service.db.flush()
    service.db.rollback()


def test_create_and_execute_receipts_idempotency_etag_and_dispatch_failures(governed):
    f, service = governed, governed["engine"]
    key = _key("idempotent")
    run = service.create_run(f["models"]["cost"]["id"], RunCreateIn(seed=993), key)
    assert service.create_run(f["models"]["cost"]["id"], RunCreateIn(seed=993), key) == run
    with pytest.raises(HTTPException) as exc:
        service.create_run(f["models"]["cost"]["id"], RunCreateIn(seed=994), key)
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        service.execute(run["id"], run["revision_version"] + 2, RunActionIn(), _key("etag"))
    assert exc.value.status_code == 412
    calls = []
    service.dispatcher = lambda *args: calls.append(args)
    command = _key("dispatch")
    first = service.execute(run["id"], run["revision_version"], RunActionIn(), command)
    assert service.execute(run["id"], run["revision_version"], RunActionIn(), command) == first
    assert len(calls) == 1
    assert service._run(run["id"]).dispatch_state == "PUBLISHED"
    result = service.worker_execute(run["id"], service._run(run["id"]).task_id)
    assert result["status"] == "COMPLETED"
    assert service.worker_execute(run["id"], service._run(run["id"]).task_id)["claimed"] is False
    service.dispatcher = lambda *_: None


def test_cancelled_run_atomicity_not_provider_eligible(governed):
    service = governed["engine"]
    row = service.create_run(governed["models"]["cost"]["id"], RunCreateIn(seed=444), _key("cancel-create"))
    service.execute(row["id"], row["revision_version"], RunActionIn(), _key("cancel-execute"))
    fresh = service.status(row["id"])
    cancelled = service.cancel(row["id"], fresh["revision_version"], RunActionIn(), _key("cancel"))
    assert cancelled["status"] == "CANCELLED"
    assert service.worker_execute(row["id"], service._run(row["id"]).task_id)["claimed"] is False
    assert service._run(row["id"]).result_json == {}
    assert service.evidence(row["id"])["status"] == "UNAVAILABLE"


def test_failure_after_progress_discards_partial_result(governed):
    service = governed["engine"]
    run = service.create_run(governed["models"]["cost"]["id"], RunCreateIn(seed=441), _key("failure-create"))
    service.execute(run["id"], run["revision_version"], RunActionIn(), _key("failure-execute"))

    def failed_calculation(manifest, seed, iterations, progress_callback):
        progress_callback(128)
        raise EngineCalculationError("SYNTHETIC_NUMERIC_FAILURE")

    failed = service.worker_execute(run["id"], service._run(run["id"]).task_id, calculate_fn=failed_calculation)
    assert failed["status"] == "FAILED" and failed["failure_reason"] == "SYNTHETIC_NUMERIC_FAILURE"
    stored = service._run(run["id"])
    assert stored.iterations_completed == 128 and stored.result_json == {}
    assert stored.result_snapshot_hash is None and stored.trace_hash is None
    assert service.evidence(run["id"])["status"] == "UNAVAILABLE"


def test_broker_failure_durable_queue_and_explicit_retry(governed):
    service = governed["engine"]
    run = service.create_run(governed["models"]["cost"]["id"], RunCreateIn(seed=443), _key("broker-create"))

    def unavailable(*_):
        raise ConnectionError("Disposable broker offline")

    service.dispatcher = unavailable
    key = _key("broker-execute")
    receipt = service.execute(run["id"], run["revision_version"], RunActionIn(), key)
    stored = service._run(run["id"])
    assert stored.status == "QUEUED" and stored.dispatch_state == "BROKER_UNAVAILABLE"
    calls = []
    service.dispatcher = lambda *args: calls.append(args)
    assert service.execute(run["id"], run["revision_version"], RunActionIn(), key) == receipt
    assert len(calls) == 1 and service._run(run["id"]).dispatch_state == "PUBLISHED"
    service.dispatcher = lambda *_: None


def test_worker_crash_lease_preserves_failed_attempt(governed):
    service = governed["engine"]
    run = service.create_run(governed["models"]["cost"]["id"], RunCreateIn(seed=433), _key("crash-create"))
    row = service._run(run["id"])
    row.status, row.started_at, row.heartbeat_at = (
        "RUNNING",
        utc_now() - timedelta(minutes=20),
        utc_now() - timedelta(minutes=20),
    )
    service._touch(row)
    service.db.commit()
    assert run["id"] in service.recover_expired_workers()["failed_run_ids"]
    assert service._run(run["id"]).failure_reason == "QRA_WORKER_LEASE_EXPIRED"


def test_approved_model_current_preflight_and_bounded_pagination(governed):
    service = governed["engine"]
    preflight = service.preflight(governed["models"]["cost"]["id"])
    assert preflight["eligible"] and preflight["persisted"] is False
    options = service.options(governed["project"].id)
    assert options["no_new_admin_module_required"] and len(options["approved_models"]) == 2
    assert "aggregate_json" not in options["approved_models"][0]
    run = _run_completed(governed)
    summary = service.run(run["id"])
    assert "results" not in summary and summary["result_summary"]["mean"]
    page = service.result_section(run["id"], "sensitivity", page_size=1)
    assert len(page["data"]) == 1
    statements = []

    def statement(_conn, _cursor, query, _parameters, _context, _executemany):
        statements.append(query)

    bind = service.db.get_bind()
    event.listen(bind, "before_cursor_execute", statement)
    try:
        service.runs(governed["project"].id, page_size=100)
        large_page_queries = list(statements)
        statements.clear()
        service.runs(governed["project"].id, page_size=1)
    finally:
        event.remove(bind, "before_cursor_execute", statement)
    assert len(statements) == len(large_page_queries), (statements, large_page_queries)
    assert len(statements) <= 20, statements
    assert not any(
        "qra_runs.input_snapshot_json" in q or "qra_runs.result_json" in q for q in statements + large_page_queries
    )


@pytest.mark.parametrize("case", ["source", "methodology", "missing_engine", "unapproved", "integrated"])
def test_pre_run_blocks_stale_unapproved_unsupported(client, case):
    with SessionLocal() as db:
        f = _engine_fixture(db)
        model_id = f["models"]["cost"]["id"]
        if case == "source":
            account = db.scalar(select(ControlAccount).where(ControlAccount.project_id == f["operational_project"].id))
            account.budget += 42
            account.version += 1
            db.commit()
        elif case == "methodology":
            _publish_engine_policy(f)
        elif case == "missing_engine":
            _publish_engine_policy(f, {})
            sources = _ready_sources(f)
            model_id = _approved_model(f, sources)["id"]
        elif case in {"unapproved", "integrated"}:
            draft = f["preparer"].create(
                f["project"].id,
                "model",
                ModelCreateIn(analysis_type="INTEGRATED_COST_SCHEDULE_QRA" if case == "integrated" else "COST_QRA"),
                _key("not-executable-model"),
            )
            model_id = draft["id"]
        count_before = db.scalar(select(func.count()).select_from(QraRun))
        with pytest.raises(HTTPException) as exc:
            f["engine"].create_run(model_id, RunCreateIn(seed=1), _key("blocked-create"))
        assert exc.value.status_code == 409
        assert db.scalar(select(func.count()).select_from(QraRun)) == count_before


def test_worker_revalidation_stale_between_queue_and_delivery(client):
    with SessionLocal() as db:
        f = _engine_fixture(db)
        service = f["engine"]
        run = service.create_run(f["models"]["cost"]["id"], RunCreateIn(seed=87), _key("stale-queue"))
        service.execute(run["id"], run["revision_version"], RunActionIn(), _key("stale-execute"))
        account = db.scalar(select(ControlAccount).where(ControlAccount.project_id == f["operational_project"].id))
        account.version += 1
        db.commit()
        failed = service.worker_execute(run["id"], service._run(run["id"]).task_id)
        assert failed["status"] == "FAILED"
        assert "REVALIDATION_BLOCKED" in failed["failure_reason"]
        assert service._run(run["id"]).iterations_completed == 0


def test_provider_becomes_unavailable_after_source_change_without_history_rewrite(client):
    with SessionLocal() as db:
        f = _engine_fixture(db)
        run = _run_completed(f)
        reviewed = f["review_engine"].review_action(
            run["id"], run["revision_version"], RunActionIn(), _key("provider-review"), "review"
        )
        accepted = f["review_engine"].review_action(
            run["id"], reviewed["revision_version"], RunActionIn(), _key("provider-accept"), "accept"
        )
        assert f["review_engine"].evidence(run["id"])["status"] == "AVAILABLE"
        frozen = deepcopy(f["engine"]._run(run["id"]).result_json)
        account = db.scalar(select(ControlAccount).where(ControlAccount.project_id == f["operational_project"].id))
        account.version += 1
        db.commit()
        assert f["review_engine"].evidence(run["id"])["status"] == "UNAVAILABLE"
        assert f["engine"]._run(run["id"]).result_json == frozen
        assert f["engine"].status(run["id"])["review_status"] == "ACCEPTED"
        assert accepted["result_snapshot_hash"] == run["result_snapshot_hash"]


def test_direct_http_scope_etag_and_permissions(client, governed):
    f = governed
    headers = _token_headers(f["author"])
    preflight = client.get(f"/api/v1/qra-engine/models/{f['models']['cost']['id']}/preflight", headers=headers)
    assert preflight.status_code == 200 and preflight.json()["eligible"], preflight.text
    created = client.post(
        f"/api/v1/qra-engine/models/{f['models']['cost']['id']}/runs",
        headers={**headers, "Idempotency-Key": _key("http-create")},
        json={"seed": 523, "iterations": 1024},
    )
    assert created.status_code == 201, created.text
    run = created.json()
    stale = client.post(
        f"/api/v1/qra-engine/runs/{run['id']}/cancel",
        headers={**headers, "Idempotency-Key": _key("http-etag"), "If-Match": '"999999"'},
        json={},
    )
    assert stale.status_code == 412
    reviewer_headers = _token_headers(f["reviewer"])
    forbidden = client.post(
        f"/api/v1/qra-engine/runs/{run['id']}/execute",
        headers={**reviewer_headers, "Idempotency-Key": _key("http-permission"), "If-Match": created.headers["etag"]},
        json={},
    )
    assert forbidden.status_code == 403
    db = f["engine"].db
    assert db.scalar(
        select(SecurityEvent.id).where(
            SecurityEvent.event_type == "qra.run.denied", SecurityEvent.user_id == f["reviewer"].id
        )
    )
    narrow = QraEngineService(
        db,
        f["author"].tenant_id,
        f["author"].id,
        replace(_context(f["author"]), organization_wide=False, workspace_ids=frozenset({999999})),
    )
    with pytest.raises(HTTPException) as exc:
        narrow.run(run["id"])
    assert exc.value.status_code == 403
    wrong_tenant = QraEngineService(db, 999999, f["author"].id)
    with pytest.raises(HTTPException) as exc:
        wrong_tenant.run(run["id"])
    assert exc.value.status_code == 404
