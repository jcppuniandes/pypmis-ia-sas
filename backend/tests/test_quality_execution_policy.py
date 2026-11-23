"""Database-free Quality remediation policies; PostgreSQL/UAT are separate gates."""

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.time import utc_now
from app.modules.quality.execution_models import (
    QualityAcceptance,
    QualityCorrectiveAction,
    QualityDisposition,
    QualityNCR,
)
from app.modules.quality.execution_schemas import (
    AcceptanceIn,
    CorrectiveActionIn,
    DispositionActionIn,
    NCRActionIn,
    NCRIn,
)
from app.modules.quality.execution_service import QualityExecutionService
from app.modules.quality.models import InspectionRecord, InspectionRequest, InspectionTestPlan, ITPItem
from app.modules.quality.models import TestRecord as QualityTestRecord
from app.modules.quality.policy import DEFAULT_PROFILE
from app.modules.quality.service import quality_hash

REASON = "Controlled Quality boundary policy verification"
PIN = {"source_type": "FIELD_PRODUCTION", "source_id": 10, "source_version": 2, "source_hash": "a" * 64}
DOC = {"document_id": 8, "attachment_id": 9}


class DummyDatabase:
    def __init__(self):
        self.rows = []

    def add(self, row):
        if row.id is None:
            row.id = len(self.rows) + 100
        self.rows.append(row)

    @staticmethod
    def flush():
        pass

    @staticmethod
    def scalars(_statement):
        return []

    @staticmethod
    def scalar(_statement):
        return None


class Harness(QualityExecutionService):
    def __init__(self, *, actor=30):
        super().__init__(DummyDatabase(), 2, actor)
        self.records = {}
        self.profile = SimpleNamespace(id=3, content_hash="b" * 64, content_json=deepcopy(DEFAULT_PROFILE))
        self.subject = {
            **PIN,
            "source_domain": "FIELD_OPERATIONS",
            "source_entity_type": "FIELD_PRODUCTION",
            "source_entity_id": 10,
            "source_root_id": 10,
            "subject_key": "FIELD:PRODUCTION:10",
            "facts": {"quantity": "10", "uom": "EA", "workfront_id": 5, "iwp_id": 7},
        }
        self.inspection = self._new(
            InspectionRecord,
            5,
            record_number="PURE-CLOSED-PASS",
            request_id=1,
            itp_item_id=6,
            subject_key=self.subject["subject_key"],
            subject_reference=deepcopy(self.subject),
            quantity=Decimal("5"),
            uom="EA",
            engineering_reference=PIN,
            requirement_reference={"description": "Governed conformity requirement"},
            inspector_user_id=20,
            inspected_at=utc_now(),
            document_references=[DOC],
            result="PASS",
            status="CLOSED",
            closed_by=22,
            closed_at=utc_now(),
            checklist_template={},
            checklist_responses=[],
            configuration_id=3,
            configuration_hash="b" * 64,
        )
        self.records[InspectionRecord, self.inspection.id] = self.inspection
        # This is pre-existing governed evidence, not a write caused by acceptance.
        self.db.rows.clear()

    def _ready(self, _workspace, _action):
        return None, self.profile

    @staticmethod
    def _read_project(_workspace):
        return None

    def _get(self, model, workspace, identity, **_kwargs):
        if workspace != 5 or (model, identity) not in self.records:
            self._error(404, "QUALITY_RECORD_NOT_FOUND")
        return self.records[model, identity]

    @staticmethod
    def _write(_command, _workspace, _payload, _key, apply, *_args):
        return apply()

    def _record(self, row, _event, _reason, *, changed=False):
        if changed:
            row.version += 1
            row.source_hash = quality_hash(row)
        self.records[type(row), row.id] = row
        return {"id": row.id, "version": row.version, "status": row.status, "source_hash": row.source_hash}

    def _pinned_profile(self, _row):
        return self.profile.content_json

    @staticmethod
    def _execution_person(identity):
        return identity

    def _subject(self, _workspace, _pin, **_kwargs):
        return deepcopy(self.subject)

    @staticmethod
    def _source_current(_workspace, pin, **_kwargs):
        return pin

    @staticmethod
    def _result_current(_workspace, row, **_kwargs):
        # Core source/IFC/checklist policies have their own release tests. This
        # focused execution harness supplies an already-current closed result.
        return row

    @staticmethod
    def _document(_workspace, pin):
        value = pin.model_dump() if hasattr(pin, "model_dump") else pin
        return {**value, "sha256": "c" * 64}

    @staticmethod
    def _check_document(_workspace, pin):
        if not pin:
            raise HTTPException(409, detail={"code": "QUALITY_CDE_REQUIRED"})
        return pin

    def evaluate_required_controls(self, _workspace, _itp, _subject, **_kwargs):
        return {
            "state": "READY",
            "itp": {"id": 4, "version": 2, "source_hash": "d" * 64},
            "subject_reference": self.subject,
            "items": [
                {
                    "itp_item_id": 6,
                    "required": True,
                    "inspection_required": True,
                    "test_required": False,
                    "inspection_record": self._execution_pin(self.inspection, "INSPECTION"),
                    "issues": [],
                }
            ],
            "missing": [],
            "source_references": [],
            "inspector_user_ids": [20],
            "itp_prepared_by": 21,
        }


def acceptance(**changes):
    return AcceptanceIn(
        reason=REASON,
        acceptance_code="ACCEPT-1",
        subject_reference=PIN,
        itp_id=4,
        quantity=changes.pop("quantity", "5"),
        uom=changes.pop("uom", "EA"),
        effective_at=datetime.now(UTC),
        document_reference=DOC,
        **changes,
    )


def ncr(service, *, status="VERIFIED", disposition_id=None):
    row = service._new(
        QualityNCR,
        5,
        ncr_number="NCR-1",
        title="Observed mismatch",
        description="Tolerance outside requirement",
        category="WORKMANSHIP",
        severity="HIGH",
        responsible_user_id=45,
        subject_key=service.subject["subject_key"],
        subject_reference=service.subject,
        requirement_reference="Approved IFC tolerance",
        detected_at=utc_now(),
        document_reference=DOC,
        status=status,
        disposition_id=disposition_id,
        configuration_id=3,
        configuration_hash="b" * 64,
    )
    service.records[QualityNCR, row.id] = row
    return row


def test_corrective_action_requires_its_ncr_but_prevention_is_not_an_ncr_duplicate():
    body = {
        "reason": REASON,
        "action_code": "ACTION-1",
        "description": "Improve the inspection method",
        "owner_user_id": 2,
        "due_date": "2026-11-19",
        "subject_reference": PIN,
        "document_reference": DOC,
    }
    with pytest.raises(ValidationError):
        CorrectiveActionIn(**body)
    assert CorrectiveActionIn(**body, action_kind="PREVENTIVE").ncr_id is None


def test_ncr_does_not_accept_ambiguous_dual_original_results():
    with pytest.raises(ValidationError):
        NCRIn(
            reason=REASON,
            ncr_number="NCR-1",
            title="Mismatch",
            description="Observed deviation",
            category="WORKMANSHIP",
            severity="HIGH",
            responsible_user_id=1,
            subject_reference=PIN,
            inspection_record_id=1,
            test_record_id=2,
            requirement_reference="Approved tolerance",
            detected_at=datetime.now(UTC),
            document_reference=DOC,
        )


@pytest.mark.parametrize("quantity,uom", [("11", "EA"), ("5", "m3")])
def test_quality_acceptance_cannot_extend_the_source_quantity_or_change_unit(quantity, uom):
    service = Harness()
    with pytest.raises(HTTPException) as error:
        service.create_acceptance(5, acceptance(quantity=quantity, uom=uom), "bad-quantity")
    assert error.value.status_code == 422 and not service.db.rows


def test_quality_acceptance_is_only_a_granular_quality_fact():
    service = Harness()
    result = service.create_acceptance(5, acceptance(), "quality-only")
    assert result["status"] == "APPROVED"
    assert [type(row) for row in service.db.rows] == [QualityAcceptance]
    assert service.db.rows[0].quantity == 5 and service.db.rows[0].subject_reference == service.subject


def test_current_execution_result_reuses_all_core_result_freshness_controls():
    service = Harness()
    checked = []

    def stale_core_result(workspace, row):
        checked.append((workspace, row.id))
        raise HTTPException(409, detail={"code": "QUALITY_CHECKLIST_OR_ENGINEERING_EVIDENCE_STALE"})

    service._result_current = stale_core_result
    with pytest.raises(HTTPException) as error:
        service._execution_result(5, "INSPECTION", service.inspection.id, passed=True)
    assert error.value.detail["code"] == "QUALITY_CHECKLIST_OR_ENGINEERING_EVIDENCE_STALE"
    assert checked == [(5, service.inspection.id)]
    # Historical evidence remains inspectable, not eligible for a new decision.
    assert service._execution_result(5, "INSPECTION", service.inspection.id, current=False) is service.inspection


@pytest.mark.parametrize(
    "inspected_quantity,unit,accepted_quantity", [("1", "EA", "2"), (None, "EA", "1"), ("5", "m3", "1")]
)
def test_acceptance_never_expands_from_partial_or_unspecified_inspection_coverage(
    inspected_quantity, unit, accepted_quantity
):
    service = Harness()
    service.inspection.quantity = Decimal(inspected_quantity) if inspected_quantity is not None else None
    service.inspection.uom = unit
    service.inspection.source_hash = quality_hash(service.inspection)
    with pytest.raises(HTTPException) as error:
        service.create_acceptance(5, acceptance(quantity=accepted_quantity), "over-inspection-coverage")
    assert error.value.status_code == 409 and not service.db.rows


def test_previously_stored_acceptance_becomes_stale_when_it_exceeds_its_actual_inspection_coverage():
    service = Harness()
    service.create_acceptance(5, acceptance(), "original-acceptance")
    row = service.db.rows[0]
    # Represent a legacy, correctly hashed fact captured by the pre-hardening
    # application; revalidation must not bless it merely because its hash matches.
    row.quantity = Decimal("6")
    row.source_hash = quality_hash(row)
    assert service.acceptance_state(5, row) == "STALE"


@pytest.mark.parametrize("tested_quantity,succeeds", [("1", False), (None, False), ("2", True)])
def test_every_required_test_has_its_own_explicit_quantity_coverage(tested_quantity, succeeds):
    service = Harness()
    record = service._new(
        QualityTestRecord,
        5,
        record_number="PURE-TEST-CLOSED-PASS",
        request_id=2,
        itp_item_id=6,
        subject_key=service.subject["subject_key"],
        subject_reference=deepcopy(service.subject),
        quantity=Decimal(tested_quantity) if tested_quantity is not None else None,
        uom="EA",
        engineering_reference=PIN,
        requirement_reference={"description": "Governed test requirement"},
        inspector_user_id=20,
        tested_at=utc_now(),
        document_references=[DOC],
        result="PASS",
        status="CLOSED",
        closed_by=22,
        closed_at=utc_now(),
        method="Controlled laboratory method",
        standard="Approved project test specification",
        measurements=[],
        configuration_id=3,
        configuration_hash="b" * 64,
    )
    service.records[QualityTestRecord, record.id] = record
    service.db.rows.clear()
    original_controls = service.evaluate_required_controls

    def controls(*args, **kwargs):
        result = original_controls(*args, **kwargs)
        result["items"][0]["test_required"] = True
        result["items"][0]["test_record"] = service._execution_pin(record, "TEST")
        return result

    service.evaluate_required_controls = controls
    if succeeds:
        assert service.create_acceptance(5, acceptance(quantity="2"), "test-coverage")["status"] == "APPROVED"
    else:
        with pytest.raises(HTTPException) as error:
            service.create_acceptance(5, acceptance(quantity="2"), "test-coverage")
        assert error.value.status_code == 409 and not service.db.rows


@pytest.mark.parametrize("actor", [20, 21])
def test_acceptance_inspector_and_itp_preparer_cannot_self_accept(actor):
    service = Harness(actor=actor)
    with pytest.raises(HTTPException) as error:
        service.create_acceptance(5, acceptance(), "self-accept")
    assert error.value.status_code == 403 and not service.db.rows


def test_backdated_quality_acceptance_cannot_ignore_a_current_blocker():
    service = Harness()
    base = service.evaluate_required_controls(5, 4, service.subject)
    service.readiness = lambda *_args, **kwargs: base if kwargs.get("as_of") else {**base, "state": "NOT_READY"}
    with pytest.raises(HTTPException) as error:
        service.create_acceptance(5, acceptance(), "backdated")
    assert error.value.detail["code"] == "QUALITY_CURRENT_CONTROLS_ACCEPTANCE_NOT_READY"


def test_ncr_cannot_close_without_an_approved_disposition():
    service = Harness()
    row = ncr(service)
    with pytest.raises(HTTPException) as error:
        service.ncr_action(5, row.id, NCRActionIn(reason=REASON, action="close"), row.version, "bad-close")
    assert error.value.detail["code"] == "QUALITY_APPROVED_DISPOSITION_REQUIRED"
    assert row.status == "VERIFIED"


def test_generic_engineering_approval_is_not_an_ncr_bound_use_as_is_decision():
    service = Harness(actor=30)
    observed = ncr(service, status="UNDER_REVIEW")
    observed.created_by = 40
    row = service._new(
        QualityDisposition,
        5,
        ncr_id=observed.id,
        disposition_code="USE-1",
        disposition_type="USE_AS_IS",
        description="Proposed acceptance without repair",
        document_reference=DOC,
        engineering_decision_reference={"facts": {"status": "APPROVED", "revision_id": 5}},
        configuration_id=3,
        configuration_hash="b" * 64,
        created_by=41,
    )
    service.records[QualityDisposition, row.id] = row
    with pytest.raises(HTTPException) as error:
        service.disposition_action(
            5, row.id, DispositionActionIn(reason=REASON, action="approve"), row.version, "unsafe-use"
        )
    assert error.value.detail["code"] == "QUALITY_NCR_BOUND_ENGINEERING_DISPOSITION_REQUIRED"
    assert row.status == "PROPOSED"


def test_rework_correction_must_link_the_original_field_fact():
    service = Harness()
    action = SimpleNamespace(
        action_kind="CORRECTIVE", subject_key=service.subject["subject_key"], subject_reference=service.subject
    )
    service.subject = {
        **service.subject,
        "source_type": "FIELD_REWORK",
        "source_entity_id": 11,
        "facts": {"original_production_id": 999},
    }
    with pytest.raises(HTTPException) as error:
        service._correction_reference(5, action, PIN)
    assert error.value.detail["code"] == "QUALITY_LINKED_VERIFIED_FIELD_CORRECTION_REQUIRED"
    service.subject["facts"]["original_production_id"] = 10
    assert service._correction_reference(5, action, PIN)["source_entity_id"] == 11


def test_same_iwp_does_not_make_other_production_the_same_accepted_subject():
    first = {"subject_key": "FIELD:PRODUCTION:10", "facts": {"iwp_id": 7}}
    second = {"subject_key": "FIELD:PRODUCTION:11", "facts": {"iwp_id": 7}}
    assert not QualityExecutionService._related_subject(first, second)


def test_material_ncr_cannot_use_an_unrelated_field_rework_with_the_same_integer_id():
    service = Harness()
    material = {**service.subject, "source_domain": "PROCUREMENT", "source_type": "MATERIAL_RECEIPT_LINE"}
    action = SimpleNamespace(action_kind="CORRECTIVE", subject_key=material["subject_key"], subject_reference=material)
    service.subject = {**service.subject, "source_type": "FIELD_REWORK", "facts": {"original_production_id": 10}}
    with pytest.raises(HTTPException) as error:
        service._correction_reference(5, action, PIN)
    assert error.value.detail["code"] == "QUALITY_TYPED_CORRECTION_PROVIDER_REQUIRED"


def test_quality_schema_cannot_smuggle_native_release_or_financial_authority():
    with pytest.raises(ValidationError):
        AcceptanceIn(**acceptance().model_dump(), awp_release_state="RELEASED", actual_cost="100")


@pytest.mark.parametrize("status,state", [(409, "STALE"), (404, "BROKEN_REFERENCE")])
def test_readiness_reports_known_captured_source_failures_without_granting_release(status, state):
    service = Harness()
    service.records[InspectionTestPlan, 4] = SimpleNamespace(id=4, version=3, source_hash="d" * 64, created_by=21)
    service._captured_subject = lambda *_args: service.subject

    def unavailable(*_args, **_kwargs):
        raise HTTPException(status, detail={"code": "QUALITY_KNOWN_SOURCE_UNAVAILABLE"})

    service.evaluate_required_controls = unavailable
    result = service.readiness(5, 4, PIN)
    assert result["state"] == state and result["awp_release_changed"] is False
    assert result["subject_reference"] == service.subject


def test_readiness_does_not_turn_a_never_captured_foreign_identity_into_visible_broken_state():
    service = Harness()
    service.records[InspectionTestPlan, 4] = SimpleNamespace(id=4, version=3, source_hash="d" * 64, created_by=21)
    service._captured_subject = lambda *_args: None

    def hidden(*_args, **_kwargs):
        raise HTTPException(404, detail={"code": "QUALITY_RECORD_NOT_FOUND"})

    service.evaluate_required_controls = hidden
    with pytest.raises(HTTPException) as error:
        service.readiness(5, 4, PIN)
    assert error.value.status_code == 404


def test_reinspection_cannot_verify_a_different_itp_control_than_the_original_failure():
    service = Harness()
    service._execution_integrity = lambda _row: None
    service.records[QualityCorrectiveAction, 11] = SimpleNamespace(
        id=11,
        status="COMPLETED",
        subject_key=service.subject["subject_key"],
        completion_reference=None,
        completion_document_reference=DOC,
        ncr_id=12,
    )
    service.records[QualityNCR, 12] = SimpleNamespace(status="CORRECTED", inspection_record_id=20)
    service.records[InspectionRecord, 20] = SimpleNamespace(itp_item_id=7, subject_key=service.subject["subject_key"])
    payload = SimpleNamespace(corrective_action_id=11, reinspection_of_id=20, itp_item_id=99)
    with pytest.raises(HTTPException) as error:
        service._validate_reinspection(5, payload, service.subject)
    assert error.value.detail["code"] == "QUALITY_REINSPECTION_ORIGINAL_CONTROL_SUBJECT_MISMATCH"


def pending_context(service, *, control_type="HOLD", released=False, issues=None):
    """Captured requests/results, without any new operational decision."""
    instant = utc_now()
    item = SimpleNamespace(id=6, itp_id=4, itp_item_code="QC-6", control_type=control_type)
    service.records[ITPItem, item.id] = item
    request = InspectionRequest(
        id=200,
        itp_item_id=item.id,
        subject_key=service.subject["subject_key"],
        subject_reference=deepcopy(service.subject),
        requested_for=instant,
        created_at=instant,
        uom="EA",
        status="COMPLETED",
    )
    original = service.readiness

    def captured_readiness(*args, **kwargs):
        result = original(*args, **kwargs)
        result["items"][0] |= {
            "control_decision": {"source_entity_id": 300} if released else None,
            "issues": issues or [],
        }
        if not released or issues:
            result["state"] = "NOT_READY"
            result["missing"] = [item.itp_item_code]
        return result

    service.readiness = captured_readiness
    return instant, request


@pytest.mark.parametrize("control_type", ["HOLD", "WITNESS"])
def test_lookahead_derives_pending_control_and_granular_acceptance_without_writing(control_type):
    service = Harness()
    instant, request = pending_context(service, control_type=control_type)
    before = deepcopy(service.subject)
    result = service._lookahead_pending(5, [request], lambda *_args: True, instant)
    assert len(result["hold_witness_pending"]) == 1
    assert result["hold_witness_pending"][0]["control_type"] == control_type
    assert result["hold_witness_pending"][0]["authority"] == "QUALITY_CONTROL_ONLY_NOT_AWP_RELEASE"
    pending = result["acceptance_pending"][0]
    assert pending["status"] == "AWAITING_CONTROLS"
    assert pending["controlled_quantity"] == Decimal("5")
    assert pending["accepted_quantity"] == 0 and pending["pending_quantity"] == 5
    assert service.subject == before and not service.db.rows


def test_lookahead_hides_released_control_but_retains_stale_or_missing_decision():
    service = Harness()
    instant, request = pending_context(service, released=True)
    assert service._lookahead_pending(5, [request], lambda *_args: True, instant)["hold_witness_pending"] == []
    service = Harness()
    instant, request = pending_context(service, released=True, issues=["explicit_control_release_missing_or_stale"])
    result = service._lookahead_pending(5, [request], lambda *_args: True, instant)
    assert result["hold_witness_pending"][0]["missing"] == ["explicit_control_release_missing_or_stale"]


@pytest.mark.parametrize("accepted,state,pending", [("2", "PARTIALLY_ACCEPTED", "3"), ("5", None, "0")])
def test_lookahead_acceptance_pending_respects_current_granular_quantity(accepted, state, pending):
    service = Harness()
    instant, request = pending_context(service, released=True)
    service.db.scalar = lambda _statement: SimpleNamespace(
        id=301, subject_reference=service.subject, quantity=Decimal(accepted)
    )
    service.acceptance_state = lambda *_args: "CURRENT"
    result = service._lookahead_pending(5, [request], lambda *_args: True, instant)
    if state is None:
        assert result["acceptance_pending"] == []
    else:
        assert result["acceptance_pending"][0]["status"] == state
        assert result["acceptance_pending"][0]["pending_quantity"] == Decimal(pending)
    assert not service.db.rows


def test_lookahead_does_not_subtract_a_stale_acceptance_or_assume_null_result_quantity():
    service = Harness()
    instant, request = pending_context(service, released=True)
    service.db.scalar = lambda _statement: SimpleNamespace(id=301, subject_reference=service.subject, quantity=5)
    service.acceptance_state = lambda *_args: "STALE"
    result = service._lookahead_pending(5, [request], lambda *_args: True, instant)
    assert result["acceptance_pending"][0]["accepted_quantity"] == 0
    service.inspection.quantity = None
    service.inspection.source_hash = quality_hash(service.inspection)
    result = service._lookahead_pending(5, [request], lambda *_args: True, instant)
    assert result["acceptance_pending"][0]["status"] == "QUANTITY_SCOPE_REQUIRED"
    assert result["acceptance_pending"][0]["controlled_quantity"] is None
    assert "EXPLICIT_CONTROL_QUANTITY_REQUIRED" in result["acceptance_pending"][0]["missing"]


def test_lookahead_derived_rows_use_the_same_status_filter_and_one_subject_stream():
    service = Harness()
    instant, request = pending_context(service)
    selected_statuses = []

    def selected(_row, status):
        selected_statuses.append(status)
        return False

    result = service._lookahead_pending(5, [request, request], selected, instant)
    assert result == {"hold_witness_pending": [], "acceptance_pending": []}
    assert selected_statuses == ["PENDING_RELEASE", "AWAITING_CONTROLS"]
    assert not service.db.rows
