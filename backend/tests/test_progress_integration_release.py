"""Real PostgreSQL/API baseline, reporting and EVM boundaries over reused sources."""

import os
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError
from tests.progress_release_fixture import REASON, create_progress_fixture, request
from tests.test_scope_foundation_release import success

from app.database.session import SessionLocal
from app.main import app
from app.modules.basic_data.service import _hash
from app.modules.operational_context.service import DEFAULT_PROFILE as OPERATIONAL_PROFILE
from app.modules.schedule_foundation.models import ScheduleVersion
from app.modules.scope_foundation.models import ScopeModelVersion

pytestmark = pytest.mark.skipif(
    os.getenv("PYPMIS_O1BD_FIXTURE") != "disposable-only",
    reason="Dedicated O1B-D disposable PostgreSQL scenario required",
)


@pytest.fixture(scope="module")
def fixture():
    with TestClient(app) as client, SessionLocal() as db:
        f = create_progress_fixture(db, client)
        f.db = db
        yield f
        db.rollback()


@pytest.fixture(scope="module")
def model_fixture():
    with TestClient(app) as client, SessionLocal() as db:
        f = create_progress_fixture(db, client, real_model=True)
        f.db = db
        yield f
        db.rollback()


def _body(f, **changes):
    scope = f.scope_items[0]
    return {
        **REASON,
        "code": f"EV-PHYSICAL-{uuid4().hex[:8]}",
        "name": "Independently approved earned basis",
        "progress_type": "PHYSICAL",
        "method": "QUANTITY_BASED",
        "source_reference": "FIELD_CERTIFIED_QUANTITY_SHEET",
        "scope_item_id": scope["id"],
        "scope_nature": scope["scope_nature"],
        "phase": "INSTALL",
        "period_id": f.period["id"],
        "measurement_date": "2026-10-21",
        "as_of": "2026-10-22",
        "numerator": str(Decimal(scope["quantity"]) / 2),
        "unit": scope["unit"],
        "weighting_basis": "QUANTITY",
        "weight": scope["quantity"],
        "evidence_refs": [{"kind": "QUANTITY_SHEET", "reference": "CERTIFIED_FIELD_REPORT"}],
        **changes,
    }


def _approve(f, row):
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
            payload={**REASON, "evidence_reference": "INDEPENDENT_QUANTITY_CERTIFICATION"},
        )
    )
    for state in ("UNDER_REVIEW", "APPROVED"):
        row = success(
            request(
                f,
                "POST",
                f"/measurements/{row['id']}/transition",
                actor="manager",
                version=row["version"],
                payload={**REASON, "status": state},
            )
        )
    return row


def _bundle_body(f, **changes):
    return {
        **REASON,
        "code": f"CONTROL-{uuid4().hex[:8]}",
        "name": "Integrated approved source references",
        "scope_baseline_id": f.scope_baseline["id"],
        "schedule_baseline_id": f.schedule_baseline["id"],
        "cost_baseline_id": f.cost_baseline["id"],
        "effective_date": "2026-10-19",
        **changes,
    }


def _approved_bundle(f):
    row = success(request(f, "POST", "/baseline-bundles", payload=_bundle_body(f)), 201)
    for action in ("review", "approve"):
        row = success(
            request(
                f,
                "POST",
                f"/baseline-bundles/{row['id']}/transition",
                actor="manager",
                version=row["version"],
                payload={**REASON, "action": action},
            )
        )
    return row


def _evm(f, bundle, **changes):
    return success(
        request(
            f,
            "GET",
            "/evm",
            params={"bundle_id": bundle["id"], "period_id": f.period["id"], "as_of": "2026-10-22", **changes},
        )
    )


def test_bundle_explicit_approved_sources_independent_approval_and_immutability(fixture):
    f = fixture
    body = _bundle_body(f)
    key = f"bundle-idempotent-{uuid4()}"
    row = success(request(f, "POST", "/baseline-bundles", payload=body, key=key), 201)
    assert success(request(f, "POST", "/baseline-bundles", payload=body, key=key), 201) == row
    assert (
        request(
            f, "POST", f"/baseline-bundles/{row['id']}/transition", version=999, payload={**REASON, "action": "review"}
        ).status_code
        == 412
    )
    row = success(
        request(
            f,
            "POST",
            f"/baseline-bundles/{row['id']}/transition",
            version=row["version"],
            payload={**REASON, "action": "review"},
        )
    )
    assert (
        request(
            f,
            "POST",
            f"/baseline-bundles/{row['id']}/transition",
            version=row["version"],
            payload={**REASON, "action": "approve"},
        ).status_code
        == 403
    )
    row = success(
        request(
            f,
            "POST",
            f"/baseline-bundles/{row['id']}/transition",
            actor="manager",
            version=row["version"],
            payload={**REASON, "action": "approve"},
        )
    )
    assert row["status"] == "APPROVED"
    assert row["source_snapshot_json"]["scope_baseline"]["hash"] == f.scope_baseline["content_hash"]
    assert row["source_snapshot_json"]["schedule_baseline"]["hash"] == f.schedule_baseline["content_hash"]
    assert row["source_snapshot_json"]["cost_baseline"]["hash"] == f.cost_baseline["content_hash"]
    with f.db.begin_nested():
        with pytest.raises(DBAPIError):
            with f.db.begin_nested():
                f.db.execute(
                    text("UPDATE progress_control_baseline_bundles SET name='forbidden' WHERE id=:id"),
                    {"id": row["id"]},
                )
    f.bundle = row


@pytest.mark.parametrize("field", ["scope_baseline_id", "schedule_baseline_id", "cost_baseline_id"])
def test_bundle_foreign_or_missing_source_rejected(fixture, field):
    response = request(fixture, "POST", "/baseline-bundles", payload=_bundle_body(fixture, **{field: 2147483000}))
    assert response.status_code == 409
    assert "NOT_FOUND_IN_PROJECT" in str(response.json())


@pytest.mark.parametrize("actor", ["foreign", "unassigned", "executive"])
def test_bundle_write_authorization_and_scoping(fixture, actor):
    assert request(fixture, "POST", "/baseline-bundles", actor=actor, payload=_bundle_body(fixture)).status_code in {
        403,
        404,
    }


@pytest.mark.parametrize("domain", ["schedule", "cost"])
def test_bundle_rejects_unapproved_upstream_candidate(fixture, domain):
    f = fixture
    if domain == "schedule":
        candidate = success(
            request(
                f,
                "POST",
                f"/api/v1/schedule/projects/{f.project_workspace_id}/versions/{f.schedule_version['id']}/baselines",
                actor="admin",
                version=f.schedule_version["version"],
                payload={
                    **REASON,
                    "baseline_type": "CONTROL",
                    "previous_baseline_id": f.schedule_baseline["id"],
                },
            ),
            201,
        )
        field, reason = "schedule_baseline_id", "APPROVED_SCHEDULE_BASELINE_REQUIRED"
    else:
        candidate = success(
            request(
                f,
                "POST",
                f"/api/v1/cost/projects/{f.project_workspace_id}/baselines",
                payload={
                    **REASON,
                    "code": f"UNAPPROVED-{uuid4().hex[:8]}",
                    "budget_version_id": f.cost_budget["id"],
                    "previous_baseline_id": f.cost_baseline["id"],
                },
            ),
            201,
        )
        field, reason = "cost_baseline_id", "APPROVED_COST_BASELINE_REQUIRED"
    response = request(f, "POST", "/baseline-bundles", payload=_bundle_body(f, **{field: candidate["id"]}))
    assert response.status_code == 409 and reason in response.json()["detail"]["reason_codes"]


def test_evm_missing_ev_not_computable_and_no_schedule_invoice_default(fixture):
    f = fixture
    result = _evm(f, f.bundle)
    assert result["status"] == "NOT_COMPUTABLE"
    assert "MISSING_EV" in result["reason_codes"] and result["ev"] is None
    assert result["earned_lines"] == []
    assert result["authority"]["ev"] == "APPROVED_PHYSICAL_QUANTITY_MILESTONE_ONLY"


def test_partial_plan_completion_does_not_earn_entire_scope_budget(fixture):
    f = fixture
    allocation = next(row for row in f.plan_items[0]["allocations"] if row["scope_item_id"] == f.scope_items[0]["id"])
    assert Decimal(allocation["quantity"]) < Decimal(f.scope_items[0]["quantity"])
    f.partial_plan_physical = _approve(
        f,
        success(
            request(
                f,
                "POST",
                "/measurements",
                payload=_body(
                    f,
                    plan_item_id=f.plan_items[0]["id"],
                    denominator_basis="PLAN",
                    numerator=str(Decimal(allocation["quantity"]) / 2),
                    weight=allocation["quantity"],
                ),
            ),
            201,
        ),
    )
    result = _evm(f, f.bundle)
    assert result["status"] == "NOT_COMPUTABLE" and result["ev"] is None
    assert "INCOMPATIBLE_BUDGETED_PROGRESS_COVERAGE" in result["reason_codes"]


def test_manual_partial_plan_percentage_is_not_full_scope_budget_coverage(fixture):
    f = fixture
    allocation = next(row for row in f.plan_items[1]["allocations"] if row["scope_item_id"] == f.scope_items[0]["id"])
    assert Decimal(allocation["quantity"]) < Decimal(f.scope_items[0]["quantity"])
    f.partial_plan_manual = _approve(
        f,
        success(
            request(
                f,
                "POST",
                "/measurements",
                payload=_body(
                    f,
                    plan_item_id=f.plan_items[1]["id"],
                    denominator_basis="PLAN",
                    method="MANUAL_EXPERT_ASSESSMENT",
                    numerator="50",
                    unit="%",
                    weight=allocation["quantity"],
                ),
            ),
            201,
        ),
    )
    result = _evm(f, f.bundle)
    assert result["status"] == "NOT_COMPUTABLE" and result["ev"] is None
    assert "INCOMPATIBLE_BUDGETED_PROGRESS_COVERAGE" in result["reason_codes"]


def test_approved_physical_earns_budget_and_uses_recognized_actual(fixture):
    f = fixture
    f.physical = _approve(f, success(request(f, "POST", "/measurements", payload=_body(f)), 201))
    result = _evm(f, f.bundle)
    assert result["status"] == "COMPUTABLE", result
    assert Decimal(result["ac"]) == Decimal("25")
    budgeted = sum(Decimal(row["amount"]) for row in f.cost_baseline["snapshot_json"]["lines"])
    assert Decimal(result["ev"]) == budgeted / 2
    assert Decimal(result["cpi"]) == (budgeted / 2 / 25).quantize(Decimal("0.00000001"))
    assert Decimal(result["spi"]) == (Decimal(result["ev"]) / Decimal(result["pv"])).quantize(Decimal("0.00000001"))
    assert result["basis"]["actual_recognition_dates"] == ["2026-10-22"]
    assert result["basis"]["progress_measurement_dates"] == ["2026-10-21"]


def test_parallel_quantity_and_physical_are_not_earned_twice(fixture):
    f = fixture
    before = _evm(f, f.bundle)
    f.quantity = _approve(
        f, success(request(f, "POST", "/measurements", payload=_body(f, progress_type="QUANTITY")), 201)
    )
    after = _evm(f, f.bundle)
    assert after["ev"] == before["ev"]
    assert {row["progress_type"] for row in after["earned_lines"]} == {"PHYSICAL"}


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"currency": "COP"}, "CURRENCY_MISMATCH"),
        ({"as_of": "2026-10-26"}, "PERIOD_AS_OF_MISMATCH"),
        ({"as_of": "2026-10-18"}, "BUNDLE_EFFECTIVE_DATE_MISMATCH"),
    ],
)
def test_evm_incompatible_basis_explicitly_not_computable(fixture, changes, reason):
    result = _evm(fixture, fixture.bundle, **changes)
    assert result["status"] == "NOT_COMPUTABLE" and reason in result["reason_codes"]
    assert result["pv"] is result["ev"] is result["ac"] is None


def test_recognized_zero_actual_denominator_is_not_computable_in_postgresql(fixture):
    f = fixture
    root = f"/api/v1/cost/projects/{f.project_workspace_id}/actuals"
    # Use Cost's real signed-adjustment/independent recognition lifecycle;
    # never edit an approved cost record just to manufacture a denominator.
    for amount in ("-25", "25"):
        adjustment = success(
            request(
                f,
                "POST",
                f"{root}/{f.cost_actual['id']}/adjustments",
                actor="admin",
                payload={
                    **REASON,
                    "source_system": "CONTROLLED_MANUAL",
                    "source_reference": f"ZERO-AC-PROOF-{uuid4().hex[:8]}",
                    "posting_date": "2026-10-22",
                    "recognition_date": "2026-10-22",
                    "period_id": f.period["id"],
                    "amount": amount,
                    "currency": "USD",
                    "cbs_id": f.cost_cbs["id"],
                    "cost_code_id": f.cost_code["id"],
                    "control_account_id": f.cost_account["id"],
                    "evidence_ref": "INDEPENDENT_SIGNED_ACTUAL_ADJUSTMENT_DOCUMENT",
                },
            ),
            201,
        )
        success(
            request(
                f,
                "POST",
                f"{root}/{adjustment['id']}/decision",
                actor="manager",
                version=adjustment["version"],
                payload=REASON,
            )
        )
        result = _evm(f, f.bundle)
        if amount == "-25":
            assert result["status"] == "NOT_COMPUTABLE" and result["cpi"] is None
            assert "ZERO_AC_DENOMINATOR" in result["reason_codes"]
            assert Decimal(result["source_values"]["ac"]) == 0
        else:
            assert result["status"] == "COMPUTABLE" and Decimal(result["ac"]) == 25


def test_evm_snapshot_is_explicit_immutable_command_not_get_side_effect(fixture):
    f = fixture
    writes = []

    def capture(_connection, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE ")):
            writes.append(statement)

    event.listen(f.db.bind, "before_cursor_execute", capture)
    try:
        _evm(f, f.bundle)
        success(request(f, "GET", f"/baseline-bundles/{f.bundle['id']}/validate"))
        success(request(f, "GET", f"/periods/{f.period['id']}/review"))
        success(
            request(
                f,
                "GET",
                "/curves",
                params={"bundle_id": f.bundle["id"], "period_id": f.period["id"], "as_of": "2026-10-22"},
            )
        )
    finally:
        event.remove(f.db.bind, "before_cursor_execute", capture)
    assert writes == []
    body = {**REASON, "bundle_id": f.bundle["id"], "period_id": f.period["id"], "as_of": "2026-10-22"}
    assert request(f, "POST", "/evm/snapshots", actor="executive", payload=body).status_code == 403
    row = success(request(f, "POST", "/evm/snapshots", actor="manager", payload=body), 201)
    assert row["status"] == "COMPUTABLE" and row["content_hash"] == _hash(row["snapshot_json"])
    with pytest.raises(DBAPIError):
        with f.db.begin_nested():
            f.db.execute(text("UPDATE progress_earned_value_snapshots SET ev=999 WHERE id=:id"), {"id": row["id"]})


def test_bundle_successor_preserves_original_and_computed_supersession(fixture):
    f = fixture
    original = deepcopy(success(request(f, "GET", f"/baseline-bundles/{f.bundle['id']}")))
    successor = success(
        request(
            f,
            "POST",
            f"/baseline-bundles/{f.bundle['id']}/successor",
            version=f.bundle["version"],
            payload=_bundle_body(f, code=f.bundle["code"]),
        ),
        201,
    )
    for action in ("review", "approve"):
        successor = success(
            request(
                f,
                "POST",
                f"/baseline-bundles/{successor['id']}/transition",
                actor="manager",
                version=successor["version"],
                payload={**REASON, "action": action},
            )
        )
    after = success(request(f, "GET", f"/baseline-bundles/{f.bundle['id']}"))
    assert (
        after["source_snapshot_json"] == original["source_snapshot_json"]
        and after["content_hash"] == original["content_hash"]
    )
    assert after["status"] == "APPROVED" and after["validation"]["effective_state"] == "SUPERSEDED"
    f.bundle = successor


def test_open_review_frozen_set_closed_published_and_governed_reopen(fixture):
    f = fixture
    successor = success(
        request(
            f,
            "POST",
            f"/measurements/{f.physical['id']}/successor",
            version=f.physical["version"],
            payload=_body(
                f,
                code=f.physical["code"],
                numerator=str(Decimal(f.scope_items[0]["quantity"]) * Decimal("0.6")),
                correction_kind="QUANTITY_CORRECTION",
            ),
        ),
        201,
    )
    scope = f.scope_items[1]
    pending = success(
        request(
            f,
            "POST",
            "/measurements",
            payload=_body(
                f,
                scope_item_id=scope["id"],
                scope_nature=scope["scope_nature"],
                unit=scope["unit"],
                numerator=str(Decimal(scope["quantity"]) / 2),
                weight=scope["quantity"],
            ),
        ),
        201,
    )
    period = success(
        request(
            f,
            "POST",
            f"/periods/{f.period['id']}/transition",
            actor="manager",
            version=f.period["version"],
            payload={**REASON, "action": "review"},
        )
    )["period"]
    review = success(request(f, "GET", f"/periods/{period['id']}/review"))
    assert review["candidate_set_frozen"] and review["snapshot"]["status"] == "FROZEN"
    assert {row["id"] for row in review["snapshot"]["candidate_snapshot_json"]} == {
        f.physical["id"],
        f.quantity["id"],
        f.partial_plan_physical["id"],
        f.partial_plan_manual["id"],
        pending["id"],
        successor["id"],
    }
    assert request(f, "POST", "/measurements", payload=_body(f)).status_code == 409
    assert (
        request(
            f,
            "POST",
            f"/periods/{period['id']}/transition",
            actor="manager",
            version=period["version"],
            payload={**REASON, "action": "close"},
        ).status_code
        == 409
    )
    approved = _approve(f, pending)
    assert approved["content_hash"] == pending["content_hash"] and approved["status"] == "APPROVED"
    successor = success(
        request(
            f,
            "POST",
            f"/measurements/{successor['id']}/transition",
            version=successor["version"],
            payload={**REASON, "status": "SUBMITTED"},
        )
    )
    successor = success(
        request(
            f,
            "POST",
            f"/measurements/{successor['id']}/transition",
            actor="manager",
            version=successor["version"],
            payload={**REASON, "status": "REJECTED"},
        )
    )
    period = success(
        request(
            f,
            "POST",
            f"/periods/{period['id']}/transition",
            actor="manager",
            version=period["version"],
            payload={**REASON, "action": "close"},
        )
    )["period"]
    assert period["status"] == "CLOSED"
    assert (
        request(
            f,
            "POST",
            f"/periods/{period['id']}/transition",
            actor="manager",
            version=period["version"],
            payload={**REASON, "action": "publish"},
        ).status_code
        == 403
    )
    period = success(
        request(
            f,
            "POST",
            f"/periods/{period['id']}/transition",
            actor="second_manager",
            version=period["version"],
            payload={**REASON, "action": "publish"},
        )
    )["period"]
    published = success(request(f, "GET", f"/periods/{period['id']}/review"))["snapshot"]
    assert published["status"] == "PUBLISHED"
    assert f.physical["id"] in {row["id"] for row in published["report_snapshot_json"]["approved_measurements"]}
    assert published["report_snapshot_json"]["rejected_measurement_ids"] == [successor["id"]]
    assert published["content_hash"] == _hash(published["report_snapshot_json"])
    assert period["snapshot_json"]["publication_boundary"] == "PERIOD_HEADER_ONLY"
    with pytest.raises(DBAPIError):
        with f.db.begin_nested():
            f.db.execute(
                text("UPDATE progress_period_snapshots SET reason='tamper' WHERE id=:id"), {"id": published["id"]}
            )
    reopened = success(
        request(
            f,
            "POST",
            f"/periods/{period['id']}/transition",
            actor="manager",
            version=period["version"],
            payload={**REASON, "action": "reopen"},
        )
    )["period"]
    assert reopened["id"] != period["id"] and reopened["reopen_parent_id"] == period["id"]
    assert success(request(f, "GET", f"/periods/{period['id']}/review"))["snapshot"] == published


def test_later_published_profile_causes_bundle_drift_without_mutation(fixture):
    f = fixture
    old = deepcopy(success(request(f, "GET", f"/baseline-bundles/{f.bundle['id']}")))
    current = f.progress_profile
    successor = success(
        request(
            f,
            "POST",
            f"/api/v1/progress/admin/profiles/{current['id']}/successor",
            actor="admin",
            version=current["version"],
            payload=REASON,
        ),
        201,
    )
    success(
        request(
            f,
            "POST",
            f"/api/v1/progress/admin/profiles/{successor['id']}/publish",
            actor="publisher",
            version=successor["version"],
            payload=REASON,
        )
    )
    current = success(request(f, "GET", f"/baseline-bundles/{f.bundle['id']}"))
    assert current["validation"]["status"] == "BLOCK" and "BUNDLE_SOURCE_DRIFT" in current["validation"]["reason_codes"]
    assert (
        current["content_hash"] == old["content_hash"]
        and current["source_snapshot_json"] == old["source_snapshot_json"]
    )
    result = _evm(f, f.bundle)
    assert result["status"] == "NOT_COMPUTABLE" and "BASELINE_BUNDLE_REQUIRES_REVIEW" in result["reason_codes"]


def test_later_mapping_change_requires_rebase_without_editing_approved_bundle(fixture):
    f = fixture
    original = deepcopy(success(request(f, "GET", f"/baseline-bundles/{f.bundle['id']}")))
    scope = f.scope_items[1]
    success(
        request(
            f,
            "POST",
            f"/api/v1/cost/projects/{f.project_workspace_id}/mappings",
            payload={
                **REASON,
                "source_kind": "SCOPE",
                "source_id": scope["id"],
                "quantity": scope["quantity"],
                "unit": scope["unit"],
                "cbs_id": f.cost_cbs["id"],
                "cost_code_id": f.cost_code["id"],
                "control_account_id": f.cost_account["id"],
                "allocation_basis": "QUANTITY",
                "quantity_basis": "APPROVED_SCOPE_OR_ALLOCATED_PLAN",
                "effective_revision": str(f.scope_baseline["id"]),
                "source_reference": "NEW_APPROVED_SCOPE_MAPPING_AFTER_BUNDLE_APPROVAL",
            },
        ),
        201,
    )
    current = success(request(f, "GET", f"/baseline-bundles/{f.bundle['id']}"))
    assert "COST_MAPPING_REBASE_REQUIRED" in current["validation"]["reason_codes"]
    assert current["source_snapshot_json"] == original["source_snapshot_json"]
    assert current["content_hash"] == original["content_hash"]


def test_real_four_d_planned_and_approved_overlay_four_natures_no_source_mutation(model_fixture):
    f = model_fixture
    bundle = _approved_bundle(f)
    source_models = f.db.scalars(
        select(ScopeModelVersion).where(ScopeModelVersion.project_workspace_id == f.project_workspace_id)
    ).all()
    schedules = f.db.scalars(
        select(ScheduleVersion).where(ScheduleVersion.project_workspace_id == f.project_workspace_id)
    ).all()
    before_ifc = {row.id: sha256(row.source_content).hexdigest() for row in source_models}
    before_schedule = {row.id: _hash(row.snapshot_json) for row in schedules}
    params = {"bundle_id": bundle["id"], "period_id": f.period["id"], "as_of": "2026-10-22"}
    original = success(request(f, "GET", "/four-d-overlay", params=params))
    assert {row["scope_nature"] for row in original["items"]} == {"INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"}
    assert all(row["approved_physical_state"]["state"] == "NOT_MEASURED" for row in original["items"])
    assert any(row["objects"] for row in original["items"])
    for scope in f.scope_items:
        nature = scope["scope_nature"]
        body = _body(
            f,
            scope_item_id=scope["id"],
            scope_nature=nature,
            phase={"INSTALL": "INSTALL", "REMOVE": "REMOVE", "TEMPORARY": "INSTALL", "MAINTENANCE": "RESTORATION"}[
                nature
            ],
            unit=scope["unit"],
            numerator=str(Decimal(scope["quantity"]) / 2),
            weight=scope["quantity"],
        )
        if nature == "MAINTENANCE":
            body.update(method="MANUAL_EXPERT_ASSESSMENT", unit="%", numerator="50")
        _approve(f, success(request(f, "POST", "/measurements", payload=body), 201))
    overlay = success(request(f, "GET", "/four-d-overlay", params=params))
    expected = {
        "INSTALL": "INSTALLATION",
        "REMOVE": "REMOVAL",
        "TEMPORARY": "TEMPORARY_INSTALLATION",
        "MAINTENANCE": "MAINTENANCE_INTERVENTION",
    }
    assert all(row["approved_physical_state"]["state"] == expected[row["scope_nature"]] for row in overlay["items"])
    assert [(row["id"], row["schedule_state"]) for row in original["items"]] == [
        (row["id"], row["schedule_state"]) for row in overlay["items"]
    ]
    assert overlay["source_hashes"] == original["source_hashes"]
    f.db.expire_all()
    assert {row.id: sha256(row.source_content).hexdigest() for row in source_models} == before_ifc
    assert {row.id: _hash(row.snapshot_json) for row in schedules} == before_schedule
    assert overlay["authority"]["schedule_mutated"] is False and overlay["authority"]["ifc_mutated"] is False


def test_project_pv_accumulates_approved_phases_from_each_own_control_period(fixture):
    """A future valid phase is not an error and prior-period PV carries forward."""
    f = create_progress_fixture(fixture.db, fixture.client, multi_period_phasing=True)
    assert OPERATIONAL_PROFILE["calendar"]["allow_parallel_active_periods"] is False
    assert f.operational_profile["status"] == "published"
    assert f.operational_profile["content_json"]["calendar"]["allow_parallel_active_periods"] is True
    assert f.period["configuration_id"] == f.next_period["configuration_id"] == f.operational_profile["id"]
    bundle = _approved_bundle(f)
    _approve(f, success(request(f, "POST", "/measurements", payload=_body(f)), 201))
    first = _evm(f, bundle, as_of="2026-10-25")
    assert first["status"] == "COMPUTABLE", first
    assert Decimal(first["pv"]) == Decimal("1000")
    assert set(first["basis"]["phasing_period_ids"]) == {f.period["id"], f.next_period["id"]}
    original_period = f.period
    f.period = f.next_period
    _approve(
        f,
        success(
            request(
                f,
                "POST",
                "/measurements",
                payload=_body(f, numerator="7.5", measurement_date="2026-10-28", as_of="2026-10-29"),
            ),
            201,
        ),
    )
    second = _evm(f, bundle, as_of="2026-10-29")
    assert second["status"] == "COMPUTABLE", second
    expected = sum(
        (
            Decimal(point["amount"])
            for phase in f.cost_baseline["snapshot_json"]["phasing"]
            for point in phase["spread_json"]
            if point["date"][:10] <= "2026-10-29"
        ),
        Decimal("0"),
    )
    assert Decimal(second["pv"]) == expected > Decimal(first["pv"])
    assert original_period["id"] in second["basis"]["phasing_period_ids"]
    assert Decimal(second["ev"]) == Decimal("1500")
    assert Decimal(second["ac"]) == Decimal("25")
    cost_root = f"/api/v1/cost/projects/{f.project_workspace_id}"
    candidate = success(
        request(
            f,
            "POST",
            cost_root + "/baselines",
            payload={
                **REASON,
                "code": f.cost_baseline["code"],
                "budget_version_id": f.cost_budget["id"],
                "previous_baseline_id": f.cost_baseline["id"],
            },
        ),
        201,
    )
    # An approved Cost source is still not automatically a compatible
    # integrated basis: every phase date must belong to its declared period.
    for budget_line in f.cost_budget["snapshot_json"]["lines"]:
        candidate = success(
            request(
                f,
                "POST",
                cost_root + f"/baselines/{candidate['id']}/phase",
                version=candidate["version"],
                payload={
                    **REASON,
                    "budget_line_id": budget_line["id"],
                    "method": "LINEAR",
                    "start_date": "2026-10-19",
                    "finish_date": "2026-10-25",
                    "period_id": f.next_period["id"],
                },
            ),
            201,
        )["baseline"]
    incompatible_cost = success(
        request(
            f,
            "POST",
            cost_root + f"/baselines/{candidate['id']}/approve",
            actor="manager",
            version=candidate["version"],
            payload=REASON,
        )
    )
    denied = request(
        f,
        "POST",
        "/baseline-bundles",
        payload=_bundle_body(f, cost_baseline_id=incompatible_cost["id"]),
    )
    assert denied.status_code == 409, denied.text
    assert "COST_BASELINE_PHASE_DATE_PERIOD_MISMATCH" in str(denied.json())
