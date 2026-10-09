"""QRA Foundation acceptance. Evidence definitions only; no probabilistic engine."""

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.provision_qra_foundation_browser import prepare_imported_schedule, schedule_xml
from tests.test_basic_data_wave2b import _fixture as basic_fixture
from tests.test_basic_data_wave2b import _workspace
from tests.test_capital_allocation_wave2a import _context

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, SecurityEvent
from app.main import app
from app.modules.project_definition.schemas import AssessmentCreateIn as FELCreateIn
from app.modules.project_definition.schemas import AssessmentUpdateIn as FELUpdateIn
from app.modules.project_definition.schemas import ElementResultIn, StartFELIn
from app.modules.project_definition.service import CONFIGURATION_KIND as FEL_KIND
from app.modules.project_definition.service import DEFAULT_FRAMEWORK, ProjectDefinitionService
from app.modules.qra_foundation.models import (
    CostSourceReadinessAssessment,
    QraCommand,
    QraModelDefinition,
    ScheduleSourceReadinessAssessment,
)
from app.modules.qra_foundation.schemas import (
    ActionIn,
    ConfigurationCloneIn,
    ConfigurationPreviewIn,
    ConfigurationUpdateIn,
    InputIn,
    ModelCreateIn,
    ModelUpdateIn,
    SourceCreateIn,
    SourceUpdateIn,
)
from app.modules.qra_foundation.service import DEFAULT_CONFIGURATION, QraFoundationService, _hash


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as value:
        yield value


def _key(action):
    return f"qra-{action}-{uuid4()}"


def _policy(scope_id):
    policy = deepcopy(DEFAULT_CONFIGURATION)
    policy["scope"] = {"type": "enterprise", "workspace_id": scope_id}
    policy["methodology"] = {
        "code": "MINING_QRA_FOUNDATION",
        "name": "Mining QRA source and methodology example",
        "description": "Configured example, not production universal rule",
    }
    policy["cost_requirements"] = [
        {
            "code": field,
            "dimension": f"COST_{field.upper()}",
            "field": field,
            "blocking": True,
            "required": True,
            "evidence_required": True,
            "minimum_quality": "VERIFIED",
        }
        for field in (
            "source_identity",
            "scope_coverage",
            "currency",
            "basis_date",
            "estimate_basis",
            "contingency_basis",
            "quantity_basis",
            "rate_basis",
            "assumptions",
            "exclusions",
        )
    ]
    policy["schedule_requirements"] = [
        {
            "code": field,
            "dimension": f"SCHEDULE_{field.upper()}",
            "field": field,
            "blocking": True,
            "required": True,
            "minimum_quality": "VERIFIED",
        }
        for field in ("source_identity", "scope_coverage", "data_date", "calendars", "schedule_type")
    ]
    policy["schedule_quality_rules"] = {
        "require_data_date": True,
        "require_calendars": True,
        "require_durations": True,
        "require_metadata": True,
        "maximum_open_ends": 0,
        "allowed_open_end_refs": ["A-START", "A-FINISH"],
        "maximum_constraints": 0,
        "maximum_negative_lags": 0,
        "maximum_lag_value": 40,
        "lag_unit": "HOURS",
        "maximum_status_findings": 0,
    }
    policy["range_policies"] = [
        {
            "code": "MIN_MOST_LIKELY_MAX",
            "allow_negative": False,
            "zero_floor": True,
            "require_evidence": True,
            "require_rationale": True,
            "minimum_quality": "VERIFIED",
        },
        {
            "code": "PERCENT_MINUS_PLUS",
            "allow_negative": False,
            "maximum_percent": 100,
            "require_evidence": True,
            "require_rationale": True,
        },
        {"code": "ABSOLUTE_RANGE", "allow_negative": False, "require_evidence": True, "require_rationale": True},
        {"code": "DISCRETE_SCENARIO", "allow_negative": False, "require_evidence": True, "require_rationale": True},
    ]
    policy["distribution_families"] = [
        {"code": "TRIANGULAR", "allowed_range_types": ["MIN_MOST_LIKELY_MAX"]},
        {
            "code": "PERT",
            "allowed_range_types": ["MIN_MOST_LIKELY_MAX"],
            "parameters": ["lambda"],
            "parameter_bounds": {"lambda": {"min": 0.1, "max": 10}},
        },
        {"code": "UNIFORM", "allowed_range_types": ["ABSOLUTE_RANGE"]},
        {"code": "DISCRETE", "allowed_range_types": ["DISCRETE_SCENARIO"]},
    ]
    policy["correlation_methods"] = [
        "NO_CORRELATION",
        "PAIRWISE_CORRELATION",
        "GROUP_CORRELATION",
        "MATRIX_CORRELATION",
    ]
    policy["correlation_rules"] = {"minimum_coefficient": -1, "maximum_coefficient": 1, "require_rationale": True}
    policy["model_governance"].update(
        allow_deterministic=True,
        deterministic_evidence_required=True,
        allowed_contingency_bases=["BASE_COST", "COST_WITH_ESTIMATE_ALLOWANCE", "COST_WITH_CONTINGENCY"],
        require_review=True,
    )
    return policy


def _prepare_fel3(db, f):
    author, project = f["author"], f["project"]
    content = deepcopy(DEFAULT_FRAMEWORK)
    content["scope"] = {"type": "enterprise", "workspace_id": f["enterprise"].id}
    framework = AdminConfiguration(
        tenant_id=author.tenant_id,
        kind=FEL_KIND,
        code=_key("fel")[:100],
        name="QRA existing definition authority",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        created_by_user_id=author.id,
        published_at=utc_now(),
    )
    db.add(framework)
    db.commit()
    service = ProjectDefinitionService(db, author.tenant_id, author.id)
    service.start_fel(
        project.id,
        StartFELIn(
            stage_code="FEL-3",
            framework_configuration_id=framework.id,
            entry_justification="Governed FEL-3 QRA source context",
            source_evidence=[{"reference": "scope-current-FEL3"}],
            idempotency_key=_key("fel-start"),
        ),
    )
    assessment = service.create_assessment(project.id, FELCreateIn(idempotency_key=_key("pdri")))
    assessment = service.update_assessment(
        assessment.id,
        assessment.revision_version,
        FELUpdateIn(
            element_results=[
                ElementResultIn(
                    element_key=e["element_key"],
                    category_key=e["category_key"],
                    score=100,
                    evidence_refs=[{"reference": "FEL-3-current-definition"}],
                )
                for e in content["assessment_elements"]
                if "FEL-3" in e["stages"]
            ],
            evidence_refs=[{"reference": "FEL3-package"}],
        ),
    )
    f["definition"] = service.complete_assessment(assessment.id, assessment.revision_version, _key("pdri-complete"))


def _fixture(db, *, contexts=False):
    f = basic_fixture(db, count=2, fel=False)
    f["project"].code, f["project"].name = (
        f"QRA-PROJECT-{f['project'].id}",
        "QRA Foundation CAPITAL_OWNER FEL-3 Project",
    )
    db.commit()
    f.update(prepare_imported_schedule(db, f))
    if contexts:
        from tests.provision_qra_foundation_browser import prepare_governed_contexts

        f["context_proofs"] = prepare_governed_contexts(db, f)
    else:
        _prepare_fel3(db, f)
    author, reviewer = f["author"], f["reviewer"]
    preparer = QraFoundationService(db, author.tenant_id, author.id, _context(author, "project_definition_manager"))
    final = QraFoundationService(db, author.tenant_id, reviewer.id, _context(reviewer, "definition_reviewer"))
    seed = preparer.ensure_seed()
    draft = preparer.clone_configuration(
        seed.id,
        seed.version,
        ConfigurationCloneIn(code=_key("policy")[:100], target_workspace_id=f["enterprise"].id),
        _key("clone"),
    )
    policy = _policy(f["enterprise"].id)
    if contexts:
        policy["model_governance"]["required_contexts"] = [
            "fel_pdri",
            "risk_readiness",
            "risk_governance",
            "basic_data",
            "owner_capability",
        ]
    draft = preparer.update_configuration(
        draft["id"],
        draft["version"],
        ConfigurationUpdateIn(name="QRA Foundation mining example", content_json=policy),
        _key("policy-save"),
    )
    f.update(
        preparer=preparer,
        final=final,
        configuration=final.publish_configuration(draft["id"], draft["version"], _key("publish")),
    )
    return f


def _source_payload(f, kind, **changes):
    if kind == "cost":
        ref = {"kind": "CONTROL_ACCOUNTS", "id": f["operational_project"].id}
        basis = {
            "currency": "USD",
            "basis_date": utc_now().date().isoformat(),
            "estimate_basis": "BoE-QRA-001",
            "contingency_basis": "BASE_COST",
            "structure": "CONTROL_ACCOUNT",
            "quantity_basis": "Imported manual P6 cost context + reviewed quantities",
            "rate_basis": "Verified supplier/rate evidence",
            "assumptions": "Reviewed source assumptions",
            "exclusions": "Excluded ownerreserve explicitly documented",
        }
    else:
        ref = {"kind": "SCHEDULE_IMPORT", "id": f["schedule_import"].id}
        basis = {"schedule_type": "CURRENT", "imported_from_p6_reference": "manual-export-P6-001"}
    return SourceUpdateIn(
        title=f"QRA {kind.title()} source",
        source_refs=[ref],
        basis=basis,
        quality="VERIFIED",
        confidence="HIGH",
        evidence_refs=[{"reference": f"independent-{kind}-source-validation"}],
        **changes,
    )


def _draft_source(f, kind, payload=None):
    row = f["preparer"].create(f["project"].id, kind, SourceCreateIn(title=f"{kind} source"), _key("create"))
    return f["preparer"].update(
        kind, row["id"], row["revision_version"], payload or _source_payload(f, kind), _key("save")
    )


def _complete_source(f, kind, row):
    row = f["preparer"].action(kind, row["id"], row["revision_version"], ActionIn(), _key("submit"), "submit")
    row = f["final"].action(kind, row["id"], row["revision_version"], ActionIn(), _key("review"), "review")
    return f["final"].action(kind, row["id"], row["revision_version"], ActionIn(), _key("complete"), "complete")


def _ready_sources(f):
    return {kind: _complete_source(f, kind, _draft_source(f, kind)) for kind in ("cost", "schedule")}


def _inputs(sources):
    entries = []
    for kind, source in sources.items():
        for item in source["snapshot_json"]["population"]:
            if item.get("milestone"):
                entries.append(
                    InputIn(
                        source_kind=kind.upper(),
                        source_item_ref=item["ref"],
                        mode="DETERMINISTIC",
                        rationale="Imported milestone remains explicitly deterministic",
                        evidence_refs=[{"reference": "milestone-scope-approval"}],
                        unit=item.get("duration_unit", "HOURS"),
                    )
                )
            else:
                base = float(item.get("amount", item.get("original_duration", 0)))
                entries.append(
                    InputIn(
                        source_kind=kind.upper(),
                        source_item_ref=item["ref"],
                        range_type="MIN_MOST_LIKELY_MAX",
                        values={"min": base * 0.9, "base": base, "max": base * 1.2},
                        distribution_family="TRIANGULAR",
                        rationale="Reviewed three-point source definition, not sampled",
                        evidence_refs=[{"reference": "uncertainty-workshop-source"}],
                        range_source="expert judgment",
                        unit=item.get("unit", item.get("duration_unit", "")),
                    )
                )
    return entries


def _draft_model(f, sources, *, inputs=None, **changes):
    row = f["preparer"].create(
        f["project"].id, "model", ModelCreateIn(analysis_type="INTEGRATED_COST_SCHEDULE_QRA"), _key("model-create")
    )
    payload = ModelUpdateIn(
        analysis_type="INTEGRATED_COST_SCHEDULE_QRA",
        purpose="Governed cost/schedule source definition for a future QRA engine",
        cost_source_assessment_id=sources["cost"]["id"],
        schedule_source_assessment_id=sources["schedule"]["id"],
        inputs=inputs if inputs is not None else _inputs(sources),
        **changes,
    )
    return f["preparer"].update("model", row["id"], row["revision_version"], payload, _key("model-save"))


def _approve(f, row):
    row = f["preparer"].action("model", row["id"], row["revision_version"], ActionIn(), _key("model-submit"), "submit")
    row = f["final"].action("model", row["id"], row["revision_version"], ActionIn(), _key("model-review"), "review")
    return f["final"].action("model", row["id"], row["revision_version"], ActionIn(), _key("model-approve"), "approve")


def test_cost_schedule_model_happy_path_hash_and_zero_simulation(client):
    with SessionLocal() as db:
        f = _fixture(db)
        sources = _ready_sources(f)
        for kind, row in sources.items():
            assert row["status"] == "COMPLETED"
            assert row["snapshot_json"]["readiness_status"] == "READY", row["snapshot_json"]["blockers"]
            assert f["final"].provider_evidence(f["project"].id, kind)["status"] == "AVAILABLE"
        row = _draft_model(f, sources)
        assert row["snapshot_json"]["readiness_status"] == "READY_FOR_REVIEW", row["snapshot_json"]["blockers"]
        approved = _approve(f, row)
        assert approved["number"].startswith("QRM-") and len(approved["hash"]) == 64
        assert approved["snapshot_json"]["derived_output"] == "READY_FOR_QRA_ANALYSIS"
        assert approved["snapshot_json"]["coverage"]["required"] == 4
        assert approved["snapshot_json"]["coverage"]["deterministic"] == 2
        assert approved["snapshot_json"]["simulation_results"] is None
        current = f["final"].current_readiness(f["project"].id, "model")
        assert current["status"] == "APPROVED_FOR_ANALYSIS", current
        for kind, model in (
            ("cost", CostSourceReadinessAssessment),
            ("schedule", ScheduleSourceReadinessAssessment),
            ("model", QraModelDefinition),
        ):
            record = db.get(model, sources[kind]["id"] if kind != "model" else approved["id"])
            record.comments = "Forbidden historical rewrite"
            with pytest.raises(ValueError, match="immutable"):
                db.flush()
            db.rollback()
        assert f["final"].record("model", approved["id"])["hash"] == approved["hash"]


@pytest.mark.parametrize(
    "case", ["open_ends", "data_date", "calendar", "duration", "raw_relationship", "scope", "constraint", "lag"]
)
def test_schedule_negatives_are_backend_owned(client, case):
    with SessionLocal() as db:
        f = _fixture(db)
        source = f["schedule_import"]
        if case == "data_date":
            source.data_date = None
        elif case == "calendar":
            meta = deepcopy(source.source_metadata)
            meta["calendars"] = []
            source.source_metadata = meta
        elif case == "duration":
            meta = deepcopy(source.source_metadata)
            meta["activities"][1]["duration_unit"] = None
            source.source_metadata = meta
        elif case == "raw_relationship":
            meta = deepcopy(source.source_metadata)
            meta["relationships"][0]["relationship_type"] = "UNKNOWN"
            source.source_metadata = meta
        elif case == "constraint":
            meta = deepcopy(source.source_metadata)
            meta["activities"][1]["primary_constraint_type"] = "Must Finish On"
            source.source_metadata = meta
        elif case == "lag":
            meta = deepcopy(source.source_metadata)
            meta["relationships"][0]["lag"] = "80"
            meta["relationships"][0]["lag_unit"] = "HOURS"
            source.source_metadata = meta
        elif case == "open_ends":
            from app.domain.models import ActivityRelationship

            for relation in db.scalars(
                select(ActivityRelationship).where(ActivityRelationship.schedule_import_id == source.id)
            ):
                db.delete(relation)
        db.commit()
        payload = _source_payload(f, "schedule")
        if case == "scope":
            payload = payload.model_copy(update={"analysis_scope": {"type": "SELECTED_WBS", "refs": ["UNKNOWN"]}})
            payload = SourceUpdateIn.model_validate(payload.model_dump())
        row = _draft_source(f, "schedule", payload)
        assert row["snapshot_json"]["readiness_status"] == "BLOCKED", row["snapshot_json"]
        completed = _complete_source(f, "schedule", row)
        assert f["final"].provider_evidence(f["project"].id, "schedule")["status"] == "UNAVAILABLE"
        assert completed["snapshot_json"]["no_cpm"]


def test_new_import_stales_sources_and_model_history_unchanged(client):
    with SessionLocal() as db:
        f = _fixture(db)
        sources = _ready_sources(f)
        approved = _approve(f, _draft_model(f, sources))
        before = deepcopy(approved)
        from app.services.schedule_ingestion import ScheduleIngestionService

        ScheduleIngestionService(db).ingest(
            f["author"].tenant_id, f["operational_project"].id, "newer-manual.xml", schedule_xml()
        )
        assert f["final"].current_readiness(f["project"].id, "schedule")["status"] == "STALE"
        assert f["final"].current_readiness(f["project"].id, "model")["status"] == "STALE"
        assert f["final"].record("model", approved["id"])["hash"] == before["hash"]
        preview = f["final"].refresh_preview("model", approved["id"])
        assert preview["persisted"] is False and preview["stale"]
        successor = f["preparer"].refresh_apply(
            "model", approved["id"], approved["revision_version"], ActionIn(), _key("refresh")
        )
        assert successor["status"] == "DRAFT" and successor["predecessor_id"] == approved["id"]
        assert f["final"].record("model", approved["id"])["aggregate_json"] == before["aggregate_json"]


def test_cost_unknown_contingency_and_reconciliation_negative(client):
    with SessionLocal() as db:
        f = _fixture(db)
        payload = _source_payload(f, "cost")
        payload.basis["contingency_basis"] = "UNKNOWN"
        row = _draft_source(f, "cost", payload)
        assert "CONTINGENCY_BASIS_REQUIRED" in row["snapshot_json"]["blockers"]
        comparator = {"kind": "CONTROL_ACCOUNTS", "id": f["operational_project"].id}
        external = SourceUpdateIn(
            source_refs=[
                {
                    "kind": "EXTERNAL_REFERENCE",
                    "reference": "estimate-authority:external-v1",
                    "version": 1,
                    "hash": _hash("source-v1"),
                }
            ],
            basis={
                **_source_payload(f, "cost").basis,
                "items": [{"ref": "E-1", "amount": 2000, "currency": "USD", "unit": "USD"}],
                "reconciliation_ref": comparator,
            },
            quality="VERIFIED",
            evidence_refs=[{"reference": "estimate-basis-approved"}],
        )
        row = _draft_source(f, "cost", external)
        assert row["snapshot_json"]["reconciliation"]["status"] == "OUT_OF_TOLERANCE"
        assert "COST_RECONCILIATION_BLOCKED" in row["snapshot_json"]["blockers"]


@pytest.mark.parametrize(
    "mutation",
    [
        "range_order",
        "distribution",
        "pert_lambda",
        "unknown_parameter",
        "correlation_bounds",
        "correlation_self",
        "correlation_unknown",
        "correlation_asymmetry",
    ],
)
def test_invalid_model_input_rejected_not_normalized(client, mutation):
    with SessionLocal() as db:
        f = _fixture(db)
        sources = _ready_sources(f)
        row = f["preparer"].create(f["project"].id, "model", ModelCreateIn(), _key("create-model"))
        inputs = [i.model_dump() for i in _inputs(sources)]
        correlations = {"method": "NO_CORRELATION"}
        if mutation == "range_order":
            inputs[0]["values"] = {"min": 100, "base": 10, "max": 20}
        elif mutation == "distribution":
            inputs[0]["distribution_family"] = "NORMAL"
        elif mutation == "pert_lambda":
            inputs[0]["distribution_family"] = "PERT"
            inputs[0]["parameters"] = {"lambda": -1}
        elif mutation == "unknown_parameter":
            inputs[0]["parameters"] = {"stdev_unrecognized": 1}
        else:
            refs = [f"{i['source_kind']}:{i['source_item_ref']}" for i in inputs if i["mode"] == "UNCERTAIN"]
            correlations = {
                "method": "PAIRWISE_CORRELATION",
                "pairs": [
                    {
                        "left": refs[0],
                        "right": refs[1],
                        "coefficient": 2 if mutation == "correlation_bounds" else 0.2,
                        "rationale": "Explicit reviewed association",
                    }
                ],
            }
            if mutation == "correlation_self":
                correlations["pairs"][0]["right"] = refs[0]
            if mutation == "correlation_unknown":
                correlations["pairs"][0]["right"] = "COST:UNKNOWN"
            if mutation == "correlation_asymmetry":
                correlations = {
                    "method": "MATRIX_CORRELATION",
                    "refs": refs,
                    "matrix": [[1, 0.2], [0.3, 1]],
                    "rationale": "Reviewed matrix",
                }
        with pytest.raises(HTTPException) as error:
            f["preparer"].update(
                "model",
                row["id"],
                row["revision_version"],
                ModelUpdateIn(
                    analysis_type="INTEGRATED_COST_SCHEDULE_QRA",
                    purpose="Input definition",
                    cost_source_assessment_id=sources["cost"]["id"],
                    schedule_source_assessment_id=sources["schedule"]["id"],
                    inputs=inputs,
                    correlations=correlations,
                ),
                _key("invalid"),
            )
        assert error.value.status_code == 422


def test_exact_denominator_missing_input_blocks_approval(client):
    with SessionLocal() as db:
        f = _fixture(db)
        sources = _ready_sources(f)
        row = _draft_model(f, sources, inputs=_inputs(sources)[:-1])
        assert row["snapshot_json"]["coverage"]["required"] == 4
        assert row["snapshot_json"]["coverage"]["covered"] == 3
        assert "INPUT_POPULATION_INCOMPLETE" in row["snapshot_json"]["blockers"]
        with pytest.raises(HTTPException) as error:
            _approve(f, row)
        assert error.value.status_code == 409


def test_model_preparer_and_methodology_author_sod(client):
    with SessionLocal() as db:
        f = _fixture(db)
        sources = _ready_sources(f)
        row = _draft_model(f, sources)
        row = f["preparer"].action("model", row["id"], row["revision_version"], ActionIn(), _key("submit"), "submit")
        with pytest.raises(HTTPException) as error:
            f["preparer"].action("model", row["id"], row["revision_version"], ActionIn(), _key("self-review"), "review")
        assert error.value.status_code == 403
        configuration = f["preparer"].clone_configuration(
            f["configuration"]["id"], f["configuration"]["version"], ConfigurationCloneIn(), _key("clone")
        )
        with pytest.raises(HTTPException) as error:
            f["preparer"].publish_configuration(configuration["id"], configuration["version"], _key("self-publish"))
        assert error.value.status_code == 403


def test_etag_idempotency_actor_payload_and_audit(client):
    with SessionLocal() as db:
        f = _fixture(db)
        key, payload = _key("receipt"), SourceCreateIn()
        row = f["preparer"].create(f["project"].id, "cost", payload, key)
        assert f["preparer"].create(f["project"].id, "cost", payload, key) == row
        with pytest.raises(HTTPException) as error:
            f["final"].create(f["project"].id, "cost", payload, key)
        assert error.value.status_code == 409
        with pytest.raises(HTTPException) as error:
            f["preparer"].update("cost", row["id"], 999, _source_payload(f, "cost"), _key("old-etag"))
        assert error.value.status_code == 412
        assert db.scalar(select(QraCommand.id).where(QraCommand.idempotency_key == key))
        assert db.scalar(
            select(SecurityEvent.id).where(
                SecurityEvent.event_type == "qra.cost.created", SecurityEvent.target_id == row["id"]
            )
        )


def test_methodology_new_revision_stales_completed_history(client):
    with SessionLocal() as db:
        f = _fixture(db)
        sources = _ready_sources(f)
        approved = _approve(f, _draft_model(f, sources))
        config = f["preparer"].clone_configuration(
            f["configuration"]["id"], f["configuration"]["version"], ConfigurationCloneIn(), _key("clone-method")
        )
        changed = deepcopy(config["content_json"])
        changed["range_policies"][0]["max"] = 1000000
        config = f["preparer"].update_configuration(
            config["id"],
            config["version"],
            ConfigurationUpdateIn(name="Next governed methodology", content_json=changed),
            _key("edit-method"),
        )
        f["final"].publish_configuration(config["id"], config["version"], _key("publish-method"))
        assert f["final"].current_readiness(f["project"].id, "model")["status"] == "STALE"
        assert f["final"].record("model", approved["id"])["hash"] == approved["hash"]
        assert f["final"].record("cost", sources["cost"]["id"])["hash"] == sources["cost"]["hash"]


def test_effective_scope_dates_governance_and_preview_readonly(client):
    with SessionLocal() as db:
        f = _fixture(db)
        project = _workspace(db, f["author"], f["enterprise"], governance="CONTRACTOR")
        assert f["preparer"].requirements(project.id)["applicable"] is False
        content = deepcopy(f["configuration"]["content_json"])
        content["inherit_to_descendants"] = False
        preview = f["preparer"].configuration_preview(
            ConfigurationPreviewIn(project_id=f["project"].id, content_json=content)
        )
        assert not preview["applicable"] and preview["persisted"] is False
        content["inherit_to_descendants"] = True
        content["effective_from"] = (utc_now().date() + timedelta(days=1)).isoformat()
        preview = f["preparer"].configuration_preview(
            ConfigurationPreviewIn(project_id=f["project"].id, content_json=content)
        )
        assert not preview["applicable"]


def test_wrong_tenant_and_project_source_denied(client):
    with SessionLocal() as db:
        f, other = _fixture(db), _fixture(db)
        sources = _ready_sources(f)
        row = other["preparer"].create(other["project"].id, "model", ModelCreateIn(), _key("model"))
        with pytest.raises(HTTPException) as error:
            other["preparer"].update(
                "model",
                row["id"],
                row["revision_version"],
                ModelUpdateIn(cost_source_assessment_id=sources["cost"]["id"]),
                _key("foreign"),
            )
        assert error.value.status_code in {404, 422}


def test_source_population_and_schedule_hash_paginated(client):
    with SessionLocal() as db:
        f = _fixture(db)
        source = _complete_source(f, "schedule", _draft_source(f, "schedule"))
        snapshot = source["snapshot_json"]
        assert snapshot["coverage"]["population"] == 3
        assert len(snapshot["schedule_summary"]["eligible_activity_refs"]) == 3
        assert f["final"].records(f["project"].id, "schedule", page_size=1)["total"] == 1
        assert f["final"].source_options(f["project"].id, "schedule")["items"][0]["id"] == f["schedule_import"].id


def test_no_execution_routes_or_sampling_domain(client):
    paths = [r.path for r in app.routes if "qra-foundation" in r.path]
    assert paths and not any("/run" in p or "/simulate" in p for p in paths)
    assert all("results" not in p for p in paths)
