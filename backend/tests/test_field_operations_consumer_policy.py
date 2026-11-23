"""Behavioral unit regressions for explicit Field consumer boundaries.

These database-free tests complement, and do not replace, PostgreSQL consumer
and Chromium acceptance evidence. Native persistence is stubbed only where the
boundary under test precedes persistence.
"""

from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.basic_data.service import _hash
from app.modules.engineering_foundation.integration import EngineeringReadinessReader
from app.modules.field_operations.consumer_router import DecisionIn, FieldConsumer
from app.modules.field_operations.consumer_sources import _report
from app.modules.field_operations.execution_models import ProductionRecord
from app.modules.field_operations.models import DailyConstructionReport
from app.modules.field_operations.service import record_hash
from app.modules.field_operations.sources import FieldSourceMixin
from app.modules.operational_context.models import ProjectControlsPeriod
from app.modules.progress_foundation.service import ProgressFoundationService

DAY = date(2026, 11, 18)
REASON = "Explicit consumer adoption for isolated boundary verification"


class QueueDatabase:
    def __init__(self, *, scalar_values=(), scalar_lists=()):
        self.scalar_values = iter(scalar_values)
        self.scalar_lists = iter(scalar_lists)
        self.statements = []

    def scalar(self, statement):
        self.statements.append(statement)
        return next(self.scalar_values)

    def scalars(self, statement):
        self.statements.append(statement)
        return next(self.scalar_lists)


class NativeOwner:
    """A native owner spy: the tests must not approve or post financial facts."""

    tenant_id = 2

    def __init__(self, db, *, approved=()):
        self.db, self.approved = db, list(approved)
        self.commands = []

    @staticmethod
    def _error(status, code):
        raise HTTPException(status, detail={"code": code})

    def _get(self, model, workspace, identity, **_kwargs):
        assert workspace == 5
        if model is ProjectControlsPeriod:
            return SimpleNamespace(id=identity, period_start=DAY, period_end=DAY)
        return SimpleNamespace(id=identity, scope_nature="INSTALL")

    @staticmethod
    def _subject(_payload):
        return "PACKAGE:3:INSTALL:INSTALL"

    def effective_approved(self, _workspace, **_kwargs):
        return self.approved

    def save_measurement(self, workspace, payload, key, *identity, **kwargs):
        self.commands.append((workspace, payload, key, identity, kwargs))
        return {"id": 88, "status": "DRAFT"}

    def save_constraint(self, *_args, **_kwargs):
        self.commands.append("constraint_created")
        return {"id": 89, "version": 1}

    def map_constraint(self, *_args, **_kwargs):
        self.commands.append("constraint_mapped")


def source(identity=10, *, root=None):
    return {
        "source_domain": "FIELD_OPERATIONS",
        "source_entity_type": "PRODUCTION",
        "source_entity_id": identity,
        "source_root_id": root or identity,
        "source_version": 2,
        "source_hash": "a" * 64,
        "observed_at": datetime.combine(DAY, datetime.min.time(), UTC).isoformat(),
        "observation_date": DAY.isoformat(),
        "facts": {
            "quantity": "10.00000000",
            "uom": "m3",
            "scope_item_id": 1,
            "plan_item_id": 2,
            "iwp_id": 3,
        },
    }


def decision(pin, *, quantity="10", decision_type="ADOPT"):
    return DecisionIn(
        **{
            key: pin[key]
            for key in ("source_entity_type", "source_entity_id", "source_version", "source_hash", "observed_at")
        },
        decision=decision_type,
        quantity=quantity,
        period_id=4,
        measurement_code="FIELD-NATIVE-1",
        reason=REASON,
    )


def consumer(owner, *, consumed="0"):
    value = FieldConsumer("PROGRESS", owner)
    value.consumed = lambda *_args: Decimal(consumed)
    return value


def test_pending_native_draft_blocks_a_second_field_adoption_before_any_write():
    owner = NativeOwner(QueueDatabase(scalar_values=[99]))
    pin = source()
    with pytest.raises(HTTPException) as error:
        consumer(owner).progress(5, pin, decision(pin), "one-command")
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "FIELD_PROGRESS_PENDING_NATIVE_MEASUREMENT"
    assert owner.commands == []


@pytest.mark.parametrize("prior_shape", ["single", "collection"])
def test_successor_keeps_each_previous_field_source_without_approving_it(prior_shape):
    prior, pin = source(9), source(10)
    old = SimpleNamespace(
        id=70,
        version=5,
        numerator=Decimal("4"),
        code="ORIGINAL-NATIVE",
        subject_key="PACKAGE:3:INSTALL:INSTALL",
        source_snapshot={"field_operations": prior if prior_shape == "single" else [prior]},
    )
    owner = NativeOwner(QueueDatabase(scalar_values=[None]), approved=[old])
    result = consumer(owner).progress(5, pin, decision(pin), "successor-command")
    assert owner.field_pin == [prior, pin]
    assert result[:3] == ("ProgressMeasurement", 88, Decimal("10"))
    _, payload, _, identities, options = owner.commands[0]
    assert identities == (70, 5) and options == {"successor": True}
    assert payload.numerator == Decimal("14") and payload.input_mode == "CUMULATIVE"
    assert payload.code == "ORIGINAL-NATIVE"
    # The existing native evidence vocabulary must be used, not an unsupported
    # Literal that raises before the consumer can create a DRAFT measurement.
    assert payload.evidence_refs[0].kind == "FIELD_REPORT"
    assert len(owner.commands) == 1


@pytest.mark.parametrize(
    "already,quantity,kind,expected",
    [("8", "3", "PARTIAL_ADOPT", 409), ("0", "3", "ADOPT", 409), ("0", "10", "PARTIAL_ADOPT", 422)],
)
def test_previously_adopted_or_ambiguous_quantities_fail_before_native_write(already, quantity, kind, expected):
    owner = NativeOwner(QueueDatabase())
    pin = source()
    with pytest.raises(HTTPException) as error:
        consumer(owner, consumed=already).progress(
            5, pin, decision(pin, quantity=quantity, decision_type=kind), "bad-qty"
        )
    assert error.value.status_code == expected
    assert owner.commands == []


def test_any_prior_awp_adoption_prevents_a_duplicate_even_after_a_later_rejection():
    owner = NativeOwner(QueueDatabase(scalar_values=[SimpleNamespace(decision="ADOPT")]))
    value = FieldConsumer("AWP", owner)
    value.latest = lambda *_args: SimpleNamespace(decision="REJECT")
    pin = source()
    pin.update(source_entity_type="CONSTRAINT")
    pin["facts"].update(description="Verified material restriction")
    payload = DecisionIn(
        **{
            key: pin[key]
            for key in ("source_entity_type", "source_entity_id", "source_version", "source_hash", "observed_at")
        },
        decision="ADOPT",
        constraint_type="MATERIAL",
        constraint_code="OBS-1",
        blocking=True,
        reason=REASON,
    )
    with pytest.raises(HTTPException) as error:
        value.awp(5, pin, payload, "repeat-adoption")
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "FIELD_AWP_ALREADY_ADOPTED"
    assert owner.commands == []


def test_native_progress_freshness_checks_every_retained_field_source(monkeypatch):
    from app.modules.field_operations import consumer_sources
    from app.modules.quality import consumer_sources as quality_sources

    # This focused unit double exercises Field freshness; Quality's real gate is
    # exercised by the isolated PostgreSQL consumer lifecycle suite.
    monkeypatch.setattr(quality_sources, "progress_quality_gate", lambda *_args, **_kwargs: [])

    pins = [source(9), source(10)]
    owner = NativeOwner(QueueDatabase(scalar_values=[None]))
    consumer(owner).progress(5, pins[1], decision(pins[1]), "new-draft")
    payload = owner.commands[0][1]
    native_basis = {"scope_baseline_hash": "b" * 64}
    weight = {"authority": "INDEPENDENT_MEASUREMENT_APPROVAL", "weight": "1"}
    row = SimpleNamespace(
        project_workspace_id=5,
        configuration_id=7,
        configuration_hash="c" * 64,
        input_json=payload.model_dump(mode="json"),
        rule_id=None,
        source_snapshot={**native_basis, "weight_source": weight, "field_operations": pins},
    )
    owner._project = lambda *_args: SimpleNamespace(id=5)
    owner._progress_profile = lambda *_args: SimpleNamespace(id=7, content_hash="c" * 64)
    owner._source_basis = lambda *_args: (native_basis, Decimal("20"), None, None)
    owner._governed_weight = lambda *_args: (Decimal("1"), weight)
    seen = []

    def read_source(_db, _tenant, _workspace, _kind, identity, **_pins):
        seen.append(identity)
        return deepcopy(next(pin for pin in pins if pin["source_entity_id"] == identity))

    monkeypatch.setattr(consumer_sources, "read_field_source", read_source)
    assert ProgressFoundationService._source_state(owner, row) == "CURRENT"
    assert seen == [9, 10]

    def changed_first(*args, **kwargs):
        current = read_source(*args, **kwargs)
        if current["source_entity_id"] == 9:
            current["source_hash"] = "d" * 64
        return current

    monkeypatch.setattr(consumer_sources, "read_field_source", changed_first)
    assert ProgressFoundationService._source_state(owner, row) == "REQUIRES_REVIEW"


def engineering_sources():
    revisions, releases = [], []
    for identity, effective, sequence in ((11, date(2026, 1, 1), 1), (12, date(2026, 1, 10), 2)):
        revision = SimpleNamespace(
            id=identity,
            deliverable_id=7,
            revision_sequence=sequence,
            status="APPROVED",
            approved_at=datetime(2026, 1, 1),
            document_hash="d" * 64,
            document_ref_json={"document_id": 15, "attachment_id": 16},
            content_hash=str(sequence) * 64,
        )
        snapshot = {
            "tenant_id": 2,
            "project_workspace_id": 5,
            "revision_id": identity,
            "deliverable_id": 7,
            "effective_date": effective.isoformat(),
            "revision_content_hash": revision.content_hash,
            "document_hash": revision.document_hash,
            "document_reference": revision.document_ref_json,
        }
        release = SimpleNamespace(
            id=identity + 10,
            revision_id=identity,
            deliverable_id=7,
            tenant_id=2,
            project_workspace_id=5,
            effective_date=effective,
            released_at=datetime(2026, 1, 1),
            snapshot_json=snapshot,
            release_hash=_hash(snapshot),
        )
        revisions.append(revision)
        releases.append(release)
    return revisions, releases


@pytest.mark.parametrize("candidate,passes", [(0, True), (1, False)])
def test_ifc_is_selected_at_execution_not_at_later_data_entry(monkeypatch, candidate, passes):
    revisions, releases = engineering_sources()
    owner = NativeOwner(QueueDatabase(scalar_lists=[revisions, releases]))
    # CDE access itself is covered by PostgreSQL integration tests. Here the
    # native release selector and all other release-integrity checks are real.
    monkeypatch.setattr(EngineeringReadinessReader, "_reference_valid", lambda *_args: True)
    owner._field_ifc_as_of = datetime(2026, 1, 5, 12, tzinfo=UTC)
    if passes:
        assert FieldSourceMixin._verify_ifc(owner, 5, releases[candidate]) is None
    else:
        with pytest.raises(HTTPException) as error:
            FieldSourceMixin._verify_ifc(owner, 5, releases[candidate])
        assert error.value.status_code == 409
        assert error.value.detail["code"] == "FIELD_IFC_NOT_EFFECTIVE_AT_EXECUTION"


def test_ifc_release_hash_tampering_is_rejected_at_execution(monkeypatch):
    revisions, releases = engineering_sources()
    releases[0].release_hash = "0" * 64
    owner = NativeOwner(QueueDatabase(scalar_lists=[revisions, releases]))
    owner._field_ifc_as_of = datetime(2026, 1, 5, 12, tzinfo=UTC)
    monkeypatch.setattr(EngineeringReadinessReader, "_reference_valid", lambda *_args: True)
    with pytest.raises(HTTPException) as error:
        FieldSourceMixin._verify_ifc(owner, 5, releases[0])
    assert error.value.detail["code"] == "FIELD_IFC_SOURCE_INVALID_AT_EXECUTION"


def report_sources():
    fact = ProductionRecord(id=10, shift_id=8, report_id=51, version=2, source_hash="a" * 64)
    pin = {"source_entity_type": "PRODUCTION", "source_entity_id": 10, "source_version": 2, "source_hash": "a" * 64}
    first = DailyConstructionReport(
        id=51, version=4, shift_id=8, status="APPROVED", report_date=DAY, source_references=[pin], comments="Original"
    )
    corrected = DailyConstructionReport(
        id=52,
        version=4,
        shift_id=8,
        status="APPROVED",
        report_date=DAY,
        supersedes_id=51,
        source_references=[pin],
        comments="Corrected report commentary, same verified facts",
    )
    first.source_hash, corrected.source_hash = record_hash(first), record_hash(corrected)
    return fact, first, corrected


def test_current_approved_report_successor_may_reaffirm_unchanged_verified_evidence():
    fact, first, corrected = report_sources()
    db = QueueDatabase(scalar_values=[first, corrected, None])
    assert _report(db, 2, 5, fact) is corrected


@pytest.mark.parametrize("tamper", ["bytes", "fact_pin"])
def test_report_successor_must_have_valid_hash_and_capture_the_exact_fact(tamper):
    fact, first, corrected = report_sources()
    if tamper == "bytes":
        corrected.comments = "Unapproved byte change after its recorded hash"
        expected = "FIELD_CONSUMER_DAILY_REPORT_INTEGRITY_INVALID"
    else:
        corrected.source_references[0] = {**corrected.source_references[0], "source_version": 1}
        corrected.source_hash = record_hash(corrected)
        expected = "FIELD_CONSUMER_SOURCE_NOT_INCLUDED_IN_APPROVED_DAILY_REPORT"
    with pytest.raises(HTTPException) as error:
        _report(QueueDatabase(scalar_values=[first, corrected, None]), 2, 5, fact)
    assert error.value.status_code == 409 and error.value.detail["code"] == expected


def test_a_superseded_report_itself_is_not_accepted_as_a_current_source():
    _, first, corrected = report_sources()
    with pytest.raises(HTTPException) as error:
        _report(QueueDatabase(scalar_values=[corrected]), 2, 5, first)
    assert error.value.detail["code"] == "FIELD_CONSUMER_DAILY_REPORT_SUPERSEDED"
