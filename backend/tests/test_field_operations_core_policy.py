"""Database-free field policy, identity and immutable-source hash boundaries."""

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.field_operations.execution_schemas import ProductionIn
from app.modules.field_operations.execution_service import ExecutionService
from app.modules.field_operations.models import FieldShift, LaborUsage
from app.modules.field_operations.policy import DEFAULT_PROFILE, FieldOperationsProfile
from app.modules.field_operations.schemas import ReferenceIn, ShiftIn, WorkfrontIn
from app.modules.field_operations.service import FieldOperationsService, record_hash


class DummyDatabase:
    def __init__(self):
        self.records = []

    def add(self, row):
        self.records.append(row)

    def flush(self):
        pass


def test_default_policy_preserves_explicit_duties_and_catalogs():
    profile = FieldOperationsProfile.model_validate(DEFAULT_PROFILE)
    assert profile.production_policy.require_released_iwp
    assert profile.production_policy.require_daily_report_approval_for_consumption
    assert profile.separation_of_duties["daily_author_cannot_approve"]
    assert profile.separation_of_duties["production_author_cannot_verify"]
    assert "EMERGENCY_WORK" in profile.production_policy.allowed_non_iwp_reasons


@pytest.mark.parametrize(
    "field,value",
    [
        ("production_types", ["INSTALLED", "INSTALLED"]),
        ("crew_trades", ["civil"]),
        ("separation_of_duties", {}),
        ("approval_profiles", {"daily_report": ["DRAFT", "APPROVED"], "shift": ["OPEN", "CLOSED"]}),
        ("max_shift_hours", 49),
    ],
)
def test_invalid_admin_policy_is_rejected(field, value):
    data = deepcopy(DEFAULT_PROFILE)
    data[field] = value
    with pytest.raises(ValidationError):
        FieldOperationsProfile.model_validate(data)


def test_reference_cannot_remap_schedule_by_name_or_use_ambiguous_identity():
    with pytest.raises(ValidationError):
        ReferenceIn(target_kind="ACTIVITY", target_id=12)
    with pytest.raises(ValidationError):
        ReferenceIn(target_kind="SCOPE", target_id=12, schedule_version_id=6, external_id="Activity A")
    pin = ReferenceIn(target_kind="ACTIVITY", schedule_version_id=6, external_id="A-100")
    assert pin.target_id is None and pin.external_id == "A-100"


def test_timezone_is_explicit_for_shift_inputs():
    with pytest.raises(ValidationError):
        ShiftIn(
            reason="Observe a governed shift",
            shift_code="DAY-1",
            shift_type="DAY",
            shift_date=date(2026, 11, 18),
            start_time=datetime(2026, 11, 18, 7),
            end_time=datetime(2026, 11, 18, 15),
            workfront_id=1,
        )


def test_append_only_initial_hash_has_materialized_defaults_and_normalized_decimals():
    db = DummyDatabase()
    service = FieldOperationsService(db, 2, 3)
    row = service._new(
        LaborUsage,
        5,
        record_code="H-1",
        shift_id=7,
        workfront_id=8,
        crew_id=9,
        trade="CIVIL",
        headcount=2,
        regular_hours=Decimal("8"),
        overtime_hours=Decimal("0"),
        configuration_id=6,
        configuration_hash="a" * 64,
    )
    assert row.created_at and row.updated_at and row.status == "RECORDED"
    assert row.source_hash == record_hash(row)
    digest = row.source_hash
    row.id, row.regular_hours, row.version = 10, Decimal("8.00000000"), 2
    assert record_hash(row) == digest
    row.regular_hours = Decimal("9")
    assert record_hash(row) != digest
    assert len(db.records) == 1


def test_source_hash_excludes_transition_provenance_but_not_the_shift_window():
    service = FieldOperationsService(DummyDatabase(), 2, 3)
    row = service._new(
        FieldShift,
        5,
        shift_code="SHIFT-1",
        shift_type="DAY",
        shift_date=date(2026, 11, 18),
        start_time=datetime(2026, 11, 18, 7),
        end_time=datetime(2026, 11, 18, 15),
        workfront_id=8,
        supervisor_user_id=3,
        configuration_id=6,
        configuration_hash="b" * 64,
    )
    digest = row.source_hash
    row.status, row.version, row.approved_by, row.approved_at = "APPROVED", 3, 15, datetime(2026, 11, 18, 19)
    assert record_hash(row) == digest
    row.end_time = datetime(2026, 11, 18, 16)
    assert record_hash(row) != digest


def test_workfront_cannot_combine_package_areas_when_explicit_cwa_is_omitted():
    class ReferenceService(FieldOperationsService):
        def _reference(self, workspace, pin):
            return pin.model_dump() if hasattr(pin, "model_dump") else pin

        def _get(self, model, workspace, identity, **kwargs):
            return SimpleNamespace(cwa_id={31: 4, 32: 5, 33: 4}[identity])

        def _person(self, identity=None):
            return identity or self.actor_id

    service = ReferenceService(DummyDatabase(), 2, 3)
    body = {
        "reason": "Validate canonical Workfront parent references",
        "workfront_code": "FRONT-1",
        "title": "Operational front",
        "location_reference": {"target_kind": "SCOPE", "target_id": 9},
        "planned_start": date(2026, 11, 18),
        "planned_finish": date(2026, 11, 19),
        "cwp_id": 31,
        "iwp_id": 32,
    }
    with pytest.raises(HTTPException) as error:
        service._workfront_values(7, WorkfrontIn(**body))
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "FIELD_OPERATIONS_PACKAGE_CWA_MISMATCH"
    values = service._workfront_values(7, WorkfrontIn(**(body | {"iwp_id": 33})))
    assert values["cwa_id"] == 4


def test_native_consumers_cannot_disable_daily_report_approval_in_admin_policy():
    body = deepcopy(DEFAULT_PROFILE)
    body["production_policy"]["require_daily_report_approval_for_consumption"] = False
    with pytest.raises(ValidationError):
        FieldOperationsProfile.model_validate(body)


def test_explicit_non_iwp_exception_preserves_ifc_execution_instant():
    observed = datetime(2026, 11, 18, 10)

    class SubjectService(ExecutionService):
        def _target_reference(self, workspace, kind, identity):
            return {"target_kind": kind, "target_id": identity}

        def _get(self, model, workspace, identity, **kwargs):
            return SimpleNamespace(id=identity, unit="m3")

        def _provider(self, workspace, pin, expected_kind=None, *, as_of=None):
            if pin is None:
                return None
            self.captured_as_of = as_of
            return {"observed_at": "2026-11-18T09:00:00+00:00", "source_entity_type": "IFC_RELEASE"}

    service = SubjectService(DummyDatabase(), 2, 3)
    payload = ProductionIn(
        reason="Controlled exception for survey work",
        production_code="SURVEY-1",
        workfront_id=6,
        shift_id=7,
        scope_item_id=9,
        quantity="1",
        uom="m3",
        observed_at="2026-11-18T10:00:00+00:00",
        source_reference="Governed source observation",
        document_reference={"document_id": 20, "attachment_id": 21},
        engineering_reference={
            "source_type": "IFC_RELEASE",
            "source_id": 22,
            "source_version": 1,
            "source_hash": "a" * 64,
        },
        execution_condition="SURVEY",
        exception_reason="Explicit approved policy exception",
    )
    result = service._production_subject(5, payload, DEFAULT_PROFILE, SimpleNamespace(iwp_id=None), observed)
    assert result[3] is None and service.captured_as_of == observed
    with pytest.raises(HTTPException) as error:
        service._production_subject(
            5,
            payload.model_copy(update={"execution_condition": "UNCONFIGURED"}),
            DEFAULT_PROFILE,
            SimpleNamespace(iwp_id=None),
            observed,
        )
    assert error.value.status_code == 422


def test_material_evidence_requires_allocation_not_an_unrelated_material_master():
    service = ExecutionService(DummyDatabase(), 2, 3)
    with pytest.raises(HTTPException) as error:
        service._provider(
            5,
            {"source_type": "MATERIAL_ITEM", "source_id": 7, "source_version": 1, "source_hash": "a" * 64},
            "MATERIAL_ALLOCATION",
        )
    assert error.value.status_code == 422
    assert error.value.detail["code"] == "FIELD_SOURCE_TYPE_MISMATCH"


def test_night_shift_consumption_uses_operational_date_not_utc_calendar_day():
    service = ExecutionService(DummyDatabase(), 2, 3)
    # 21:00 in Bogota on the shift day is 02:00 UTC on the following day.
    production = SimpleNamespace(iwp_id=8, observed_at=datetime(2026, 11, 19, 2))
    shift = SimpleNamespace(shift_date=date(2026, 11, 18))
    payload = SimpleNamespace(material_item_id=9, uom="EA", consumption_date=date(2026, 11, 18))
    facts = {"material_item_id": 9, "work_package_id": 8, "uom": "EA"}
    service._material_consumption_context(production, shift, payload, facts)
    payload.consumption_date = date(2026, 11, 17)
    with pytest.raises(HTTPException) as error:
        service._material_consumption_context(production, shift, payload, facts)
    assert error.value.status_code == 409
