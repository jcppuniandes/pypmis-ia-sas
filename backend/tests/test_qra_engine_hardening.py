"""Wave4 policy, Foundation projection and incremental-edit release probes."""

from copy import deepcopy

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect
from sqlalchemy.orm import defer
from tests.test_qra_engine import _engine_settings
from tests.test_qra_foundation import _fixture, _inputs, _key, _ready_sources

from app.database.session import SessionLocal
from app.main import app
from app.modules.qra_engine.policy import engine_configuration_issues
from app.modules.qra_foundation.models import QraModelDefinition
from app.modules.qra_foundation.policy import DEFAULT_CONFIGURATION, configuration_issues
from app.modules.qra_foundation.schemas import ModelCreateIn, ModelInputsPatchIn, ModelMetadataPatchIn, ModelUpdateIn
from app.modules.qra_foundation.service import QraFoundationService


def test_historical_empty_engine_configuration_stays_valid_without_enabling_execution():
    assert engine_configuration_issues({}) == []
    assert configuration_issues(deepcopy(DEFAULT_CONFIGURATION)) == []
    assert engine_configuration_issues(_engine_settings()) == []


@pytest.mark.parametrize(
    "key,value,issue",
    [
        ("engine_version", "invented", "ENGINE_VERSION_NOT_SUPPORTED"),
        ("supported_analysis_types", ["INTEGRATED_COST_SCHEDULE_QRA"], "ENGINE_ANALYSIS_TYPES_INVALID"),
        ("chunk_size", True, "ENGINE_INTEGER_POLICY_INVALID:chunk_size"),
        ("percentiles", [50, 50], "ENGINE_PERCENTILES_DUPLICATED"),
        ("psd_tolerance", 0.2, "ENGINE_NUMERIC_TOLERANCE_INVALID:psd_tolerance"),
        ("correlation_sampling", "NEAREST_PSD", "ENGINE_CORRELATION_METHOD_NOT_SUPPORTED"),
        ("schedule_unit_seconds", None, "ENGINE_SCHEDULE_UNIT_SECONDS_REQUIRED"),
        ("raw_samples", True, "ENGINE_RAW_SAMPLE_STORAGE_NOT_SUPPORTED"),
        ("result_review", {"require_review": False}, "ENGINE_INDEPENDENT_RESULT_REVIEW_REQUIRED"),
        ("run_numbering", None, "ENGINE_RUN_NUMBERING_REQUIRED"),
    ],
)
def test_invalid_engine_configuration_blocks_publication(key, value, issue):
    assert issue in engine_configuration_issues(_engine_settings(**{key: value}))


@pytest.mark.parametrize("bad", [None, [], "enabled", 42])
def test_malformed_engine_settings_are_controlled_errors(bad):
    assert engine_configuration_issues(bad) == ["ENGINE_CONFIGURATION_OBJECT_REQUIRED"]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as value:
        yield value


@pytest.fixture(scope="module")
def editing(client):
    with SessionLocal() as db:
        fixture = _fixture(db)
        fixture["sources"] = _ready_sources(fixture)
        yield fixture


def test_incremental_model_inputs_preserve_other_rows_metadata_and_etag(editing):
    f = editing
    model = f["preparer"].create(f["project"].id, "model", ModelCreateIn(), _key("incremental"))
    inputs = _inputs({"cost": f["sources"]["cost"]})
    model = f["preparer"].update(
        "model",
        model["id"],
        model["revision_version"],
        ModelUpdateIn(
            title="Incremental editor",
            purpose="Traceable input editing",
            cost_source_assessment_id=f["sources"]["cost"]["id"],
            inputs=inputs,
        ),
        _key("editor-save"),
    )
    original = f["preparer"].record("model", model["id"])
    update = inputs[0].model_copy(update={"rationale": "Updated independent workshop evidence"})
    patch = ModelInputsPatchIn(inputs=[update])
    key = _key("input-patch")
    updated = f["preparer"].patch_model(model["id"], model["revision_version"], patch, key, inputs=True)
    assert "inputs" not in updated["aggregate_json"]
    assert updated["revision_version"] == model["revision_version"] + 1
    after = f["preparer"].record("model", model["id"])
    assert after["aggregate_json"]["inputs"][1:] == original["aggregate_json"]["inputs"][1:]
    assert after["aggregate_json"]["purpose"] == original["aggregate_json"]["purpose"]
    assert f["preparer"].patch_model(model["id"], model["revision_version"], patch, key, inputs=True) == updated
    with pytest.raises(HTTPException) as stale:
        f["preparer"].patch_model(model["id"], model["revision_version"], patch, _key("stale"), inputs=True)
    assert stale.value.status_code == 412
    metadata = f["preparer"].patch_model(
        model["id"], updated["revision_version"], ModelMetadataPatchIn(title="Updated metadata"), _key("metadata")
    )
    assert metadata["title"] == "Updated metadata"
    assert f["preparer"].record("model", model["id"])["aggregate_json"]["inputs"] == after["aggregate_json"]["inputs"]


def test_source_picker_queries_only_metadata_and_keeps_candidates_paginated(editing):
    f = editing
    service = f["preparer"]
    page = service.source_options(f["project"].id, "cost", page_size=1)
    assert len(page["items"]) == 1 and page["total"] >= 1
    assert page["items"][0]["read_model"] == "CANDIDATE_METADATA_ONLY"
    assert "items" not in page["items"][0]
    assert page["items"][0]["hash"] is None  # A picker is not an assessment.
    assert service.source_options(f["project"].id, "cost", page=99999, page_size=1)["items"] == []


def test_ten_thousand_input_page_and_summary_do_not_decode_full_snapshots(editing):
    f = editing
    service = f["preparer"]
    model = service.create(f["project"].id, "model", ModelCreateIn(), _key("projection"))
    row = service.db.get(QraModelDefinition, model["id"])
    row.aggregate_json = {
        **row.aggregate_json,
        "inputs": [
            {"source_kind": "COST", "source_item_ref": f"BENCH-{i}", "rationale": "Projection-only fixture"}
            for i in range(10000)
        ],
    }
    row.snapshot_json = {**row.snapshot_json, "population": [{"ref": f"BENCH-{i}"} for i in range(10000)]}
    service.db.commit()
    with SessionLocal() as db:
        reader = QraFoundationService(db, service.tenant_id, service.actor_id)
        loaded = db.get(
            QraModelDefinition,
            model["id"],
            options=[defer(QraModelDefinition.aggregate_json), defer(QraModelDefinition.snapshot_json)],
        )
        statements = []

        def capture(_connection, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        event.listen(db.get_bind(), "before_cursor_execute", capture)
        try:
            result = reader.record_items("model", model["id"], page=201, page_size=25)
            summary = reader.record("model", model["id"], summary=True)
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", capture)
        assert result["total"] == 10000 and len(result["items"]) == 25
        assert result["items"][0]["source_item_ref"] == "BENCH-5000"
        assert "inputs" not in summary["aggregate_json"] and "population" not in summary["snapshot_json"]
        # The metadata row is still in the identity map, with both large columns deferred.
        assert {"aggregate_json", "snapshot_json"}.issubset(inspect(loaded).unloaded)
        assert any("json_each" in sql or "jsonb_array_elements" in sql for sql in statements)
