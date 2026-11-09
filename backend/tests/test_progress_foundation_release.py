"""Real PostgreSQL/HTTP Progress authority, lineage and independent approvals."""

import os
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from tests.progress_release_fixture import REASON, create_progress_fixture, request
from tests.test_scope_foundation_release import success

from app.database.session import SessionLocal, engine
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("PYPMIS_O1BD_FIXTURE") != "disposable-only" and os.getenv("PYPMIS_O1C_FIXTURE") != "disposable-only",
    reason="Dedicated O1B-D disposable PostgreSQL scenario required",
)


@pytest.fixture(scope="module")
def fixture():
    assert engine.dialect.name == "postgresql" and (
        (engine.url.database == "o1bd" and os.getenv("PYPMIS_O1BD_FIXTURE") == "disposable-only")
        or (engine.url.database == "o1c" and os.getenv("PYPMIS_O1C_FIXTURE") == "disposable-only")
    )
    with TestClient(app) as client, SessionLocal() as db:
        value = create_progress_fixture(db, client)
        value.db = db
        yield value
        db.rollback()


def measurement_body(f, **changes):
    scope = f.scope_items[0]
    return {
        **REASON,
        "code": f"P-{uuid4().hex[:10]}",
        "name": "Governed quantity measurement",
        "progress_type": "QUANTITY",
        "method": "QUANTITY_BASED",
        "source_reference": "CERTIFIABLE_FIELD_QUANTITY_SHEET",
        "scope_item_id": scope["id"],
        "scope_nature": scope["scope_nature"],
        "phase": "INSTALL",
        "period_id": f.period["id"],
        "measurement_date": "2026-10-21",
        "as_of": "2026-10-22",
        "numerator": "5",
        "unit": scope["unit"],
        "evidence_refs": [{"kind": "QUANTITY_SHEET", "reference": "FIELD-QS-001"}],
        **changes,
    }


def create(f, **changes):
    return success(request(f, "POST", "/measurements", payload=measurement_body(f, **changes)), 201)


def approve(f, row):
    row = success(
        request(
            f,
            "POST",
            f"/measurements/{row['id']}/transition",
            version=row["version"],
            payload={**REASON, "status": "SUBMITTED"},
        )
    )
    row = success(
        request(
            f,
            "POST",
            f"/measurements/{row['id']}/certify",
            actor="manager",
            version=row["version"],
            payload={**REASON, "evidence_reference": "INDEPENDENT_INSPECTION_CERTIFICATE"},
        )
    )
    row = success(
        request(
            f,
            "POST",
            f"/measurements/{row['id']}/transition",
            actor="manager",
            version=row["version"],
            payload={**REASON, "status": "UNDER_REVIEW"},
        )
    )
    return success(
        request(
            f,
            "POST",
            f"/measurements/{row['id']}/transition",
            actor="manager",
            version=row["version"],
            payload={**REASON, "status": "APPROVED"},
        )
    )


def quantity(f):
    if not hasattr(f, "approved_quantity_progress"):
        f.approved_quantity_progress = approve(f, create(f))
    return f.approved_quantity_progress


def rule(f, method="RULE_OF_CREDIT", weights=("30", "20", "30", "20"), **changes):
    payload = {
        **REASON,
        "code": f"ROC-{uuid4().hex[:10]}",
        "name": "Independent governed credit",
        "method": method,
        "steps": [
            {"code": str(index), "name": f"Step {index}", "weight": weight} for index, weight in enumerate(weights)
        ],
        **changes,
    }
    candidate = success(request(f, "POST", "/rules", payload=payload), 201)
    return success(
        request(
            f,
            "POST",
            f"/rules/{candidate['id']}/publish",
            actor="manager",
            version=candidate["version"],
            payload=REASON,
        )
    )


@pytest.mark.parametrize("basis", ["SCOPE", "PLAN", "PACKAGE"])
def test_quantity_denominator_from_approved_scope_plan_and_package(fixture, basis):
    f = fixture
    fields = {
        "SCOPE": {},
        "PLAN": {"plan_item_id": f.plan_items[0]["id"]},
        "PACKAGE": {"work_package_id": f.awp_package["id"]},
    }[basis]
    expected = Decimal("4") if basis == "PLAN" else Decimal("10")
    row = create(f, numerator="2", denominator_basis=basis, **fields)
    assert Decimal(row["denominator"]) == expected
    assert row["source_snapshot"]["scope_baseline_id"] == f.scope_baseline["id"]
    assert row["source_snapshot"]["scope_baseline_hash"] == f.scope_baseline["content_hash"]


@pytest.mark.parametrize("numerator,expected,overrun", [("0", "0", False), ("10", "100", False), ("12", "120", True)])
def test_quantity_zero_full_overrun_uncapped(fixture, numerator, expected, overrun):
    row = create(fixture, numerator=numerator)
    assert Decimal(row["progress_value"]) == Decimal(expected)
    assert row["overrun"] is overrun


def test_unit_and_mixed_plan_denominator_require_explicit_compatible_allocation(fixture):
    f = fixture
    assert request(f, "POST", "/measurements", payload=measurement_body(f, unit="kg")).status_code == 422
    response = request(
        f,
        "POST",
        "/measurements",
        payload=measurement_body(f, scope_item_id=None, plan_item_id=f.plan_items[0]["id"], denominator_basis="PLAN"),
    )
    assert response.status_code == 422


def test_approved_lifecycle_independent_certifier_and_stable_content_hash(fixture):
    row = quantity(fixture)
    assert row["status"] == "APPROVED"
    assert row["certified_by"] == fixture.users["manager"].id
    assert row["prepared_by"] != row["approved_by"]
    before = success(request(fixture, "GET", f"/measurements/{row['id']}"))
    assert before["source_state"] == "CURRENT" and before["content_hash"] == row["content_hash"]


@pytest.mark.parametrize("actor", ["executive", "planner", "unassigned", "foreign"])
def test_progress_capture_rejects_non_progress_duties(fixture, actor):
    assert request(fixture, "POST", "/measurements", actor=actor, payload=measurement_body(fixture)).status_code in {
        403,
        404,
    }


def test_existing_progress_engineer_role_can_capture_without_source_write_duty(fixture):
    f = fixture
    row = success(request(f, "POST", "/measurements", actor="progress_engineer", payload=measurement_body(f)), 201)
    assert row["prepared_by"] == f.users["progress_engineer"].id
    assert (
        request(
            f,
            "POST",
            f"/measurements/{row['id']}/certify",
            actor="progress_engineer",
            version=row["version"],
            payload={**REASON, "evidence_reference": "NOT_AUTHORIZED"},
        ).status_code
        == 403
    )


def test_recorder_cannot_certify_or_review_own_measurement(fixture):
    f = fixture
    row = create(f)
    row = success(
        request(
            f,
            "POST",
            f"/measurements/{row['id']}/transition",
            version=row["version"],
            payload={**REASON, "status": "SUBMITTED"},
        )
    )
    for path, payload in (
        ("certify", {**REASON, "evidence_reference": "OWN_CERT"}),
        ("transition", {**REASON, "status": "UNDER_REVIEW"}),
    ):
        denied = request(f, "POST", f"/measurements/{row['id']}/{path}", version=row["version"], payload=payload)
        assert denied.status_code == 403


def test_actor_with_certifier_permission_still_cannot_certify_own_work(fixture):
    f = fixture
    row = success(request(f, "POST", "/measurements", actor="manager", payload=measurement_body(f)), 201)
    row = success(
        request(
            f,
            "POST",
            f"/measurements/{row['id']}/transition",
            actor="manager",
            version=row["version"],
            payload={**REASON, "status": "SUBMITTED"},
        )
    )
    denied = request(
        f,
        "POST",
        f"/measurements/{row['id']}/certify",
        actor="manager",
        version=row["version"],
        payload={**REASON, "evidence_reference": "OWN_INSPECTION"},
    )
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "PROGRESS_RECORDER_CERTIFIER_SOD"


def test_progress_idempotency_actor_binding_and_etag(fixture):
    f = fixture
    payload, key = measurement_body(f), str(uuid4())
    created = success(request(f, "POST", "/measurements", payload=payload, key=key), 201)
    assert success(request(f, "POST", "/measurements", payload=payload, key=key), 201) == created
    assert request(f, "POST", "/measurements", actor="manager", payload=payload, key=key).status_code == 409
    assert request(f, "PUT", f"/measurements/{created['id']}", version=999, payload=payload).status_code == 412


@pytest.mark.parametrize("field", ["progress_value", "denominator", "approved_by", "percent_complete", "budget_amount"])
def test_api_rejects_unrecognized_progress_and_upstream_authority_fields(fixture, field):
    assert (
        request(fixture, "POST", "/measurements", payload=measurement_body(fixture, **{field: "10"})).status_code == 422
    )


@pytest.mark.parametrize(
    "method",
    [
        "QUANTITY_BASED",
        "WEIGHTED_COMPONENTS",
        "MILESTONE_BASED",
        "STEP_METHOD",
        "RULE_OF_CREDIT",
        "MANUAL_EXPERT_ASSESSMENT",
    ],
)
def test_all_six_physical_methods_are_backend_governed(fixture, method):
    f = fixture
    fields = {"progress_type": "PHYSICAL", "method": method}
    if method in {"RULE_OF_CREDIT", "STEP_METHOD", "MILESTONE_BASED"}:
        published = rule(f, method, ("50", "50"))
        fields.update(rule_id=published["id"], completed_steps=["0"], numerator="0", unit="%")
    elif method == "MANUAL_EXPERT_ASSESSMENT":
        fields.update(numerator="35", unit="%")
    elif method == "WEIGHTED_COMPONENTS":
        first = quantity(f)
        if not hasattr(f, "approved_temporary_progress"):
            other = f.scope_items[1]
            f.approved_temporary_progress = approve(
                f,
                create(
                    f,
                    scope_item_id=other["id"],
                    scope_nature="TEMPORARY",
                    phase="INSTALL",
                    numerator="10",
                    unit=other["unit"],
                ),
            )
        fields.update(
            scope_item_id=None,
            numerator="0",
            unit="%",
            components=[
                {"measurement_id": first["id"], "weight": "1"},
                {"measurement_id": f.approved_temporary_progress["id"], "weight": "1"},
            ],
        )
    row = create(f, **fields)
    assert row["method"] == method
    assert Decimal(row["progress_value"]) == (Decimal("35") if method == "MANUAL_EXPERT_ASSESSMENT" else Decimal("50"))


@pytest.mark.parametrize(
    "weights,completed,expected",
    [
        (("100",), [], "0"),
        (("100",), ["0"], "100"),
        (("50", "50"), ["0"], "50"),
        (("10", "20", "30", "40"), ["0", "1", "2"], "60"),
    ],
)
def test_discrete_and_weighted_milestone_rules(fixture, weights, completed, expected):
    published = rule(fixture, "MILESTONE_BASED", weights)
    row = create(
        fixture,
        progress_type="MILESTONE",
        method="MILESTONE_BASED",
        rule_id=published["id"],
        completed_steps=completed,
        numerator="0",
        unit="%",
    )
    assert Decimal(row["progress_value"]) == Decimal(expected)


def test_published_rule_immutable_and_successor_preserves_original(fixture):
    f = fixture
    old = rule(f)
    payload = {**REASON, "code": old["code"], "name": old["name"], "method": old["method"], "steps": old["steps_json"]}
    assert request(f, "PUT", f"/rules/{old['id']}", version=old["version"], payload=payload).status_code == 409
    successor = success(
        request(f, "POST", f"/rules/{old['id']}/successor", version=old["version"], payload=payload), 201
    )
    assert successor["revision"] == old["revision"] + 1 and successor["supersedes_id"] == old["id"]
    assert success(request(f, "GET", f"/rules/{old['id']}"))["content_hash"] == old["content_hash"]


def test_quantity_correction_does_not_overwrite_approved_content(fixture):
    f = fixture
    old = quantity(f)
    payload = measurement_body(f, code=old["code"], numerator="4", correction_kind="REWORK")
    row = success(
        request(f, "POST", f"/measurements/{old['id']}/successor", version=old["version"], payload=payload), 201
    )
    assert Decimal(row["numerator"]) == 4 and row["supersedes_id"] == old["id"]
    assert row["correction_kind"] == "REWORK"
    assert success(request(f, "GET", f"/measurements/{old['id']}"))["content_hash"] == old["content_hash"]


def test_negative_correction_requires_policy_kind_and_evidence(fixture):
    f, old = fixture, quantity(fixture)
    payload = measurement_body(f, code=old["code"], numerator="4")
    assert (
        request(f, "POST", f"/measurements/{old['id']}/successor", version=old["version"], payload=payload).status_code
        == 422
    )
    payload.update(correction_kind="REWORK", evidence_refs=[])
    assert (
        request(f, "POST", f"/measurements/{old['id']}/successor", version=old["version"], payload=payload).status_code
        == 422
    )


def test_existing_approved_quantity_cannot_edit_denominator_or_source_basis(fixture):
    f, old = fixture, quantity(fixture)
    assert (
        request(
            f,
            "PUT",
            f"/measurements/{old['id']}",
            version=old["version"],
            payload=measurement_body(f, code=old["code"]),
        ).status_code
        == 409
    )
    changed = measurement_body(f, code=old["code"], plan_item_id=f.plan_items[0]["id"], denominator_basis="PLAN")
    assert request(
        f, "POST", f"/measurements/{old['id']}/successor", version=old["version"], payload=changed
    ).status_code in {422, 409}


@pytest.mark.parametrize("basis", ["QUANTITY", "BUDGET", "LABOR_HOURS", "ENGINEERING_HOURS", "CONTRACT_VALUE"])
def test_weight_cannot_be_arbitrary_value_relabelled_governed_basis(fixture, basis):
    assert (
        request(
            fixture, "POST", "/measurements", payload=measurement_body(fixture, weighting_basis=basis, weight="999")
        ).status_code
        == 422
    )


def test_schedule_cost_and_invoice_never_create_physical_progress(fixture):
    f = fixture
    before = success(request(f, "GET", "/physical-progress"))["items"]
    schedule = success(
        request(f, "GET", "/schedule-progress", params={"as_of": "2026-10-24", "period_id": f.period["id"]})
    )
    cost = success(request(f, "GET", "/cost-progress", params={"as_of": "2026-10-24", "period_id": f.period["id"]}))
    assert schedule["physical_progress_automatic"] is False and cost["physical_progress_automatic"] is False
    assert all(row["progress_type"] == "SCHEDULE" for row in schedule["items"])
    assert all(row["progress_type"] == "COST" for row in cost["items"])
    assert success(request(f, "GET", "/physical-progress"))["items"] == before


def test_schedule_source_after_asof_is_not_silently_used(fixture):
    result = success(request(fixture, "GET", "/schedule-progress", params={"as_of": "2026-10-01"}))
    assert result["items"]
    assert all(
        item["result"] == "NOT_COMPUTABLE" and "SCHEDULE_DATA_DATE_AFTER_AS_OF" in item["reason_codes"]
        for item in result["items"]
    )


def test_quantity_weight_is_governed_by_actual_source_denominator(fixture):
    row = create(fixture, weighting_basis="QUANTITY", weight="10")
    assert Decimal(row["weight"]) == 10
    assert row["source_snapshot"]["weight_source"]["authority"] == "APPROVED_DENOMINATOR"
    assert row["source_snapshot"]["weight_source"]["unit"] == fixture.scope_items[0]["unit"]


def test_budget_weight_and_control_account_pin_exact_approved_allocation(fixture):
    f = fixture
    amount = sum(
        Decimal(line["amount"])
        for line in f.cost_baseline["snapshot_json"]["lines"]
        if line["cost_class"] != "MANAGEMENT_RESERVE"
    )
    row = create(
        f,
        numerator="2",
        work_package_id=f.awp_package["id"],
        control_account_id=f.cost_account["id"],
        weighting_basis="BUDGET",
        weight=str(amount),
    )
    assert Decimal(row["weight"]) == amount
    assert row["source_snapshot"]["weight_source"]["cost_baseline_id"] == f.cost_baseline["id"]
    assert row["source_snapshot"]["control_account_basis"]["mappings"]
    unmapped_budget = request(
        f,
        "POST",
        "/measurements",
        payload=measurement_body(
            f,
            plan_item_id=f.plan_items[0]["id"],
            work_package_id=f.awp_package["id"],
            control_account_id=f.cost_account["id"],
            weighting_basis="BUDGET",
            weight=str(amount),
        ),
    )
    assert unmapped_budget.status_code == 422
    assert unmapped_budget.json()["detail"]["code"] == "PROGRESS_UNAMBIGUOUS_BUDGET_WEIGHT_REQUIRED"
    denied = request(
        f,
        "POST",
        "/measurements",
        payload=measurement_body(
            f,
            scope_item_id=f.scope_items[1]["id"],
            scope_nature="TEMPORARY",
            unit=f.scope_items[1]["unit"],
            control_account_id=f.cost_account["id"],
        ),
    )
    assert denied.status_code == 422
    assert denied.json()["detail"]["code"] == "PROGRESS_EXPLICIT_CONTROL_ACCOUNT_MAPPING_REQUIRED"


def test_cost_over_budget_preserves_raw_ratio_and_does_not_claim_normal_or_physical_progress(fixture):
    f = fixture
    before = success(request(f, "GET", "/physical-progress"))["items"]
    root = f"/api/v1/cost/projects/{f.project_workspace_id}"
    actual = success(
        request(
            f,
            "POST",
            root + "/actuals",
            payload={
                **REASON,
                "source_system": "CONTROLLED_MANUAL",
                "source_reference": f"OVER-BUDGET-{uuid4()}",
                "posting_date": "2026-10-21",
                "recognition_date": "2026-10-22",
                "period_id": f.period["id"],
                "amount": "2000",
                "currency": "USD",
                "cbs_id": f.cost_cbs["id"],
                "cost_code_id": f.cost_code["id"],
                "control_account_id": f.cost_account["id"],
                "evidence_ref": "CERTIFIED_OVER_BUDGET_ACTUAL",
            },
        ),
        201,
    )
    success(
        request(
            f,
            "POST",
            root + f"/actuals/{actual['id']}/decision",
            actor="manager",
            version=actual["version"],
            payload=REASON,
        )
    )
    result = success(request(f, "GET", "/cost-progress", params={"as_of": "2026-10-24", "period_id": f.period["id"]}))[
        "items"
    ][0]
    assert result["result"] == "NOT_COMPUTABLE" and result["progress_value"] is None
    assert Decimal(result["raw_ratio"]) > 100 and result["overrun"] is True
    assert "COST_PROGRESS_BOUNDS_EXCEEDED" in result["reason_codes"]
    assert success(request(f, "GET", "/physical-progress"))["items"] == before


def test_activity_identity_is_version_qualified_and_broken_is_not_remapped(fixture):
    f = fixture
    activity = f.schedule_version["snapshot_json"]["activities"][0]["external_id"]
    row = create(
        f,
        activity_external_id=activity,
        schedule_version_id=f.schedule_version["id"],
        plan_item_id=f.plan_items[0]["id"],
        numerator="2",
    )
    assert row["source_snapshot"]["schedule_version_id"] == f.schedule_version["id"]
    assert row["source_snapshot"]["schedule_data_date"] == f.schedule_version["data_date"]
    response = request(
        f,
        "POST",
        "/measurements",
        payload=measurement_body(
            f, activity_external_id="NO-SUCH-ACTIVITY", schedule_version_id=f.schedule_version["id"]
        ),
    )
    assert response.status_code == 422


def test_measurement_asof_cutoff_and_schedule_dates_not_forced_equal(fixture):
    row = create(fixture, measurement_date="2026-10-20", as_of="2026-10-24")
    assert row["measurement_date"] != row["as_of"]
    assert row["as_of"] not in fixture.period["cutoff_at"]


def test_get_overview_aggregation_and_history_have_no_business_writes(fixture):
    writes = []

    def observe(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        for path in ("/overview", "/aggregation", "/history", "/quantity-progress", "/physical-progress"):
            assert request(fixture, "GET", path).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert writes == []


def test_postgresql_approved_progress_and_history_are_immutable(fixture):
    row = quantity(fixture)
    for statement in (
        "UPDATE progress_measurements SET numerator=99 WHERE id=:id",
        "DELETE FROM progress_measurements WHERE id=:id",
        "UPDATE progress_history SET reason='rewrite' WHERE entity_type='ProgressMeasurement' AND entity_id=:id",
    ):
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(text(statement), {"id": row["id"]})


def test_scope_plan_overlap_is_not_double_counted(fixture):
    f, original = fixture, quantity(fixture)
    plan = approve(f, create(f, plan_item_id=f.plan_items[0]["id"], denominator_basis="PLAN", numerator="2"))
    response = request(
        f,
        "POST",
        "/measurements",
        payload=measurement_body(
            f,
            progress_type="WEIGHTED",
            method="WEIGHTED_COMPONENTS",
            scope_item_id=None,
            unit="%",
            numerator="0",
            components=[
                {"measurement_id": original["id"], "weight": "1"},
                {"measurement_id": plan["id"], "weight": "1"},
            ],
        ),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PROGRESS_OVERLAPPING_COMPONENT_WORK"
    project = success(request(f, "GET", "/aggregation", params={"progress_type": "QUANTITY"}))["items"]
    assert project and project[0]["status"] == "NOT_COMPUTABLE"
    assert "OVERLAPPING_WORK_MEASUREMENTS" in project[0]["reason_codes"]


def test_period_delta_cumulative_negative_successor_and_closed_boundary(fixture):
    # A separate tenant avoids borrowing or rewriting any other test's period.
    f = create_progress_fixture(fixture.db, fixture.client, prepare_integrated=False)
    first = approve(f, create(f))
    original_period = f.period
    for action, actor in (("review", "manager"), ("close", "admin"), ("publish", "publisher")):
        original_period = success(
            request(
                f,
                "POST",
                f"/periods/{original_period['id']}/transition",
                actor=actor,
                version=original_period["version"],
                payload={**REASON, "action": action},
            )
        )["period"]
    assert original_period["status"] == "PUBLISHED"
    denied = request(f, "POST", "/measurements", payload=measurement_body(f))
    assert denied.status_code == 409
    f.period = success(
        request(
            f,
            "POST",
            f"/api/v1/operational/projects/{f.project_workspace_id}/periods",
            actor="manager",
            payload={
                **REASON,
                "period_code": "PROGRESS-NEXT",
                "period_start": "2026-10-26",
                "period_end": "2026-11-01",
                "cutoff_at": "2026-11-01T17:00:00-05:00",
                "timezone": "America/Bogota",
                "schedule_data_date": "2026-10-22",
            },
        ),
        201,
    )
    second = approve(
        f, create(f, numerator="2", input_mode="PERIOD_DELTA", measurement_date="2026-10-28", as_of="2026-10-29")
    )
    assert Decimal(second["cumulative_quantity"]) == 7 and Decimal(second["period_quantity"]) == 2
    assert Decimal(second["progress_value"]) == 70 and Decimal(second["period_progress"]) == 20
    correction = measurement_body(
        f,
        code=second["code"],
        numerator="-1",
        input_mode="PERIOD_DELTA",
        correction_kind="REWORK",
        measurement_date="2026-10-28",
        as_of="2026-10-30",
    )
    successor = success(
        request(f, "POST", f"/measurements/{second['id']}/successor", version=second["version"], payload=correction),
        201,
    )
    successor = approve(f, successor)
    assert Decimal(successor["cumulative_quantity"]) == 4 and Decimal(successor["period_quantity"]) == -1
    assert Decimal(successor["progress_value"]) == 40 and Decimal(successor["period_progress"]) == -10
    old = success(request(f, "GET", f"/measurements/{second['id']}"))
    assert old["content_hash"] == second["content_hash"] and old["effective_status"] == "SUPERSEDED"
    assert success(request(f, "GET", f"/measurements/{first['id']}"))["content_hash"] == first["content_hash"]


def test_weighted_components_cannot_hide_extra_scope_behind_parent_label(fixture):
    f = create_progress_fixture(fixture.db, fixture.client, prepare_integrated=False)
    first = approve(f, create(f))
    scope = f.scope_items[1]
    second = approve(
        f,
        create(
            f, scope_item_id=scope["id"], scope_nature="TEMPORARY", phase="INSTALL", unit=scope["unit"], numerator="10"
        ),
    )
    payload = measurement_body(
        f,
        progress_type="PHYSICAL",
        method="WEIGHTED_COMPONENTS",
        numerator="0",
        unit="%",
        components=[{"measurement_id": first["id"], "weight": "1"}, {"measurement_id": second["id"], "weight": "1"}],
    )
    denied = request(f, "POST", "/measurements", payload=payload)
    assert denied.status_code == 422
    assert denied.json()["detail"]["code"] == "PROGRESS_COMPONENT_OUTSIDE_SUBJECT_COVERAGE"
    payload.update(scope_item_id=None)
    aggregate = approve(f, success(request(f, "POST", "/measurements", payload=payload), 201))
    assert {tuple(value) for value in aggregate["source_snapshot"]["component_coverage"]} == {
        (first["scope_item_id"], "INSTALL"),
        (second["scope_item_id"], "INSTALL"),
    }
    nested = request(
        f,
        "POST",
        "/measurements",
        payload=measurement_body(
            f,
            progress_type="WEIGHTED",
            method="WEIGHTED_COMPONENTS",
            scope_item_id=None,
            numerator="0",
            unit="%",
            components=[
                {"measurement_id": aggregate["id"], "weight": "1"},
                {"measurement_id": second["id"], "weight": "1"},
            ],
        ),
    )
    assert nested.status_code == 422
    assert nested.json()["detail"]["code"] == "PROGRESS_OVERLAPPING_COMPONENT_WORK"


def test_install_execute_aliases_cannot_be_counted_as_different_component_work(fixture):
    f = create_progress_fixture(fixture.db, fixture.client, prepare_integrated=False)
    install = approve(f, create(f, phase="INSTALL"))
    execute = create(f, phase="EXECUTE")
    assert execute["subject_key"] == install["subject_key"]
    for operation in ("SUBMITTED", "CERTIFY", "UNDER_REVIEW"):
        path = "certify" if operation == "CERTIFY" else "transition"
        data = (
            {**REASON, "evidence_reference": "INDEPENDENT_ALIAS_REVIEW"}
            if operation == "CERTIFY"
            else {**REASON, "status": operation}
        )
        execute = success(
            request(
                f,
                "POST",
                f"/measurements/{execute['id']}/{path}",
                actor="cost_controller" if operation == "SUBMITTED" else "manager",
                version=execute["version"],
                payload=data,
            )
        )
    denied = request(
        f,
        "POST",
        f"/measurements/{execute['id']}/transition",
        actor="manager",
        version=execute["version"],
        payload={**REASON, "status": "APPROVED"},
    )
    assert (
        denied.status_code == 409 and denied.json()["detail"]["code"] == "PROGRESS_APPROVED_BRANCH_OR_DUPLICATE_SUBJECT"
    )
    aggregate = success(request(f, "GET", "/aggregation", params={"progress_type": "QUANTITY"}))["items"][0]
    assert aggregate["status"] == "COMPUTABLE" and aggregate["input_ids"] == [install["id"]]


def test_weighted_plan_requires_allocated_components_not_whole_scope_percentage(fixture):
    f = create_progress_fixture(fixture.db, fixture.client, prepare_integrated=False)
    whole = approve(f, create(f))
    fields = {
        "progress_type": "PHYSICAL",
        "method": "WEIGHTED_COMPONENTS",
        "numerator": "0",
        "unit": "%",
        "plan_item_id": f.plan_items[0]["id"],
        "components": [{"measurement_id": whole["id"], "weight": "1"}],
    }
    denied = request(f, "POST", "/measurements", payload=measurement_body(f, **fields))
    assert denied.status_code == 422
    assert denied.json()["detail"]["code"] == "PROGRESS_COMPONENT_OUTSIDE_SUBJECT_COVERAGE"
    allocated = approve(f, create(f, plan_item_id=f.plan_items[0]["id"], denominator_basis="PLAN", numerator="2"))
    fields["components"] = [{"measurement_id": allocated["id"], "weight": "1"}]
    accepted = approve(f, create(f, **fields))
    assert Decimal(accepted["progress_value"]) == 50
    assert {tuple(value) for value in accepted["source_snapshot"]["component_coverage"]} == {
        (whole["scope_item_id"], "INSTALL")
    }


def test_temporary_activity_uses_explicit_awp_phase_not_caller_relabelling(fixture):
    f = create_progress_fixture(fixture.db, fixture.client, real_model=True)
    scope, plan, package = f.scope_items[2], f.plan_items[2], f.packages[2]
    activity = next(
        identity
        for identity, phase in f.activity_phases.items()
        if phase == "INSTALL" and f.activity_plans[identity] == plan["id"]
    )
    payload = measurement_body(
        f,
        progress_type="PHYSICAL",
        scope_item_id=scope["id"],
        scope_nature="TEMPORARY",
        phase="REMOVE",
        plan_item_id=plan["id"],
        work_package_id=package["id"],
        schedule_version_id=f.schedule_version["id"],
        activity_external_id=activity,
        denominator_basis="SCOPE",
        numerator="0.6",
        unit=scope["unit"],
    )
    denied = request(f, "POST", "/measurements", payload=payload)
    assert denied.status_code == 422
    assert denied.json()["detail"]["code"] == "PROGRESS_PACKAGE_ACTIVITY_PHASE_MISMATCH"
    payload.update(phase="INSTALL")
    accepted = approve(f, success(request(f, "POST", "/measurements", payload=payload), 201))
    assert Decimal(accepted["progress_value"]) == 50
    assert accepted["source_snapshot"]["scope_item_ids"] == [scope["id"]]
    assert success(request(f, "GET", f"/measurements/{accepted['id']}"))["source_state"] == "CURRENT"


def test_reopen_cross_period_successor_preserves_published_snapshot_and_lineage(fixture):
    f = create_progress_fixture(fixture.db, fixture.client, prepare_integrated=False)
    first = approve(f, create(f, as_of="2026-10-24"))
    original = approve(
        f,
        success(
            request(
                f,
                "POST",
                f"/measurements/{first['id']}/successor",
                version=first["version"],
                payload=measurement_body(f, code=first["code"], numerator="6", as_of="2026-10-24"),
            ),
            201,
        ),
    )
    period = f.period
    for action, actor in (("review", "manager"), ("close", "admin"), ("publish", "publisher")):
        period = success(
            request(
                f,
                "POST",
                f"/periods/{period['id']}/transition",
                actor=actor,
                version=period["version"],
                payload={**REASON, "action": action},
            )
        )["period"]
    frozen = deepcopy(success(request(f, "GET", f"/periods/{period['id']}/review"))["snapshot"])
    f.period = success(
        request(
            f,
            "POST",
            f"/periods/{period['id']}/transition",
            actor="manager",
            version=period["version"],
            payload={**REASON, "action": "reopen"},
        )
    )["period"]
    assert f.period["reopen_parent_id"] == period["id"]
    # A closed period stays closed; the successor must explicitly name the new
    # O1A revision and cannot invent lineage from matching dates.
    assert request(f, "POST", "/measurements", payload=measurement_body(f, period_id=period["id"])).status_code == 409
    payload = measurement_body(f, code=original["code"], numerator="4")
    denied = request(
        f, "POST", f"/measurements/{original['id']}/successor", version=original["version"], payload=payload
    )
    assert (
        denied.status_code == 422
        and denied.json()["detail"]["code"] == "PROGRESS_NEGATIVE_CORRECTION_REQUIRES_POLICY_AND_REASON"
    )
    payload.update(correction_kind="REWORK")
    revised = approve(
        f,
        success(
            request(
                f, "POST", f"/measurements/{original['id']}/successor", version=original["version"], payload=payload
            ),
            201,
        ),
    )
    lineage = revised["source_snapshot"]["period_reopen_predecessor"]
    assert revised["supersedes_id"] == original["id"] and revised["revision"] > original["revision"]
    assert original["as_of"] == "2026-10-24" and revised["as_of"] == "2026-10-22"
    assert lineage["period_id"] == period["id"] and lineage["reopen_period_id"] == f.period["id"]
    assert lineage["configuration_hash"] == period["source_configuration_hash"]
    current = success(request(f, "GET", "/aggregation", params={"progress_type": "QUANTITY"}))["items"][0]
    assert current["input_ids"] == [revised["id"]] and Decimal(current["progress_value"]) == 40
    historical = success(
        request(f, "GET", "/aggregation", params={"progress_type": "QUANTITY", "period_id": period["id"]})
    )["items"][0]
    assert historical["input_ids"] == [original["id"]] and Decimal(historical["progress_value"]) == 60
    assert success(request(f, "GET", f"/periods/{period['id']}/review"))["snapshot"] == frozen
    assert success(request(f, "GET", f"/measurements/{original['id']}"))["content_hash"] == original["content_hash"]
    assert success(request(f, "GET", f"/measurements/{revised['id']}"))["source_state"] == "CURRENT"


def test_unrelated_period_and_foreign_period_cannot_claim_reopen_lineage(fixture):
    f = create_progress_fixture(fixture.db, fixture.client, prepare_integrated=False)
    original = approve(f, create(f))
    period = f.period
    for action, actor in (("review", "manager"), ("close", "admin"), ("publish", "publisher")):
        period = success(
            request(
                f,
                "POST",
                f"/periods/{period['id']}/transition",
                actor=actor,
                version=period["version"],
                payload={**REASON, "action": action},
            )
        )["period"]
    f.period = success(
        request(
            f,
            "POST",
            f"/api/v1/operational/projects/{f.project_workspace_id}/periods",
            actor="manager",
            payload={
                **REASON,
                "period_code": "UNRELATED-SAME-DATES",
                "period_start": "2026-10-19",
                "period_end": "2026-10-25",
                "cutoff_at": "2026-10-25T17:00:00-05:00",
                "timezone": "America/Bogota",
                "schedule_data_date": "2026-10-22",
            },
        ),
        201,
    )
    payload = measurement_body(f, code=original["code"], numerator="6")
    denied = request(
        f, "POST", f"/measurements/{original['id']}/successor", version=original["version"], payload=payload
    )
    assert denied.status_code == 422 and denied.json()["detail"]["code"] == "PROGRESS_REOPEN_PERIOD_BASIS_MISMATCH"
    unlinked = create(f, numerator="6")
    for operation in ("SUBMITTED", "CERTIFY", "UNDER_REVIEW"):
        path = "certify" if operation == "CERTIFY" else "transition"
        data = (
            {**REASON, "evidence_reference": "INDEPENDENT_OVERLAP_REVIEW"}
            if operation == "CERTIFY"
            else {**REASON, "status": operation}
        )
        unlinked = success(
            request(
                f,
                "POST",
                f"/measurements/{unlinked['id']}/{path}",
                actor="cost_controller" if operation == "SUBMITTED" else "manager",
                version=unlinked["version"],
                payload=data,
            )
        )
    rejected = request(
        f,
        "POST",
        f"/measurements/{unlinked['id']}/transition",
        actor="manager",
        version=unlinked["version"],
        payload={**REASON, "status": "APPROVED"},
    )
    assert (
        rejected.status_code == 409 and rejected.json()["detail"]["code"] == "PROGRESS_OVERLAPPING_PERIOD_CONTROL_BASIS"
    )
    foreign = create_progress_fixture(fixture.db, fixture.client, prepare_integrated=False)
    payload.update(period_id=foreign.period["id"])
    assert request(
        f, "POST", f"/measurements/{original['id']}/successor", version=original["version"], payload=payload
    ).status_code in {403, 404}
