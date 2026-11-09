"""Real PostgreSQL/API Forecast lifecycle, source isolation and immutable projections."""

import os
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from tests.forecast_release_fixture import (
    REASON,
    approved,
    assumption,
    body,
    calculate,
    component,
    create_forecast_fixture,
    draft,
    request,
)
from tests.progress_release_fixture import request as progress_request
from tests.test_cost_financial_release import commitment
from tests.test_scope_foundation_release import success

from app.database.session import SessionLocal
from app.main import app
from app.modules.basic_data.service import _hash
from app.modules.forecast_foundation.models import (
    ForecastAssumption,
    ForecastComponent,
    ForecastHistory,
    ForecastVersion,
)

pytestmark = pytest.mark.skipif(
    os.getenv("PYPMIS_O1C_FIXTURE") != "disposable-only", reason="Dedicated O1C disposable PostgreSQL scenario required"
)


@pytest.fixture(scope="module")
def fixture():
    with TestClient(app) as client, SessionLocal() as db:
        f = create_forecast_fixture(db, client)
        yield f
        db.rollback()


def test_draft_lifecycle_calculation_approved_sources_and_independent_approval(fixture):
    f = fixture
    row = draft(f)
    assert row["status"] == "DRAFT"
    assert row["assumptions"] and row["cost_items"] and row["time_items"]
    row = calculate(f, row)
    assert row["result_json"]["cost"]["status"] == "COMPUTABLE", row["result_json"]
    assert Decimal(row["result_json"]["cost"]["etc"]) == 75
    assert Decimal(row["result_json"]["cost"]["eac"]) == 100
    assert row["result_json"]["time"]["forecast_finish"] == "2026-11-20"
    assert row["result_json"]["time"]["cpm_calculated"] is False
    row = success(
        request(
            f,
            "POST",
            f"/versions/{row['id']}/transition",
            version=row["version"],
            payload={**REASON, "action": "review"},
        )
    )
    assert row["status"] == "UNDER_REVIEW"
    row = success(
        request(
            f,
            "POST",
            f"/versions/{row['id']}/transition",
            actor="manager",
            version=row["version"],
            payload={**REASON, "action": "approve"},
        )
    )
    assert row["status"] == "APPROVED" and row["approved_by"] != row["prepared_by"]
    assert row["source_snapshot_json"]["bundle"]["hash"] == f.bundle["content_hash"]
    assert row["source_hashes_json"] and row["result_json"]["assumption_hashes"]
    f.forecast = row


def test_idempotency_and_etag_conflicts(fixture):
    f, payload, key = fixture, body(fixture), f"forecast-idempotent-{uuid4()}"
    created = request(f, "POST", "/versions", payload=payload, key=key)
    row = success(created, 201)
    etag = f'"{row["version"]}"'
    assert created.headers["ETag"] == etag
    replay = request(f, "POST", "/versions", payload=payload, key=key)
    assert success(replay, 201) == row and replay.headers["ETag"] == etag
    assert request(f, "POST", "/versions", payload={**payload, "name": "Different content"}, key=key).status_code == 409
    path = f"/versions/{row['id']}"
    change = {**payload, "name": "A rejected concurrent edit"}
    assert request(f, "PUT", path, payload=change, version=999).status_code == 412
    missing = request(f, "PUT", path, payload=change)
    # The shared mutation dependency declares a required header in FastAPI.
    assert missing.status_code == 422
    assert any(item["loc"] == ["header", "If-Match"] for item in missing.json()["detail"])
    unchanged = request(f, "GET", path)
    assert success(unchanged) == row and unchanged.headers["ETag"] == etag


def test_preparer_and_last_material_editor_cannot_approve(fixture):
    f = fixture
    row = success(request(f, "POST", "/versions", actor="manager", payload=body(f)), 201)
    row = calculate(f, row, actor="manager")
    row = success(
        request(
            f,
            "POST",
            f"/versions/{row['id']}/transition",
            actor="manager",
            version=row["version"],
            payload={**REASON, "action": "review"},
        )
    )
    denied = request(
        f,
        "POST",
        f"/versions/{row['id']}/transition",
        actor="manager",
        version=row["version"],
        payload={**REASON, "action": "approve"},
    )
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "FORECAST_APPROVAL_SOD"
    row = success(
        request(
            f,
            "POST",
            f"/versions/{row['id']}/transition",
            actor="second_manager",
            version=row["version"],
            payload={**REASON, "action": "approve"},
        )
    )
    assert row["updated_by"] == f.users["manager"].id and row["approved_by"] == f.users["second_manager"].id


def test_approved_version_and_children_immutable_http_orm_and_sql(fixture):
    f, row = fixture, approved(fixture)
    payload = deepcopy(row["input_json"])
    payload["name"] = "Forbidden replacement"
    assert request(f, "PUT", f"/versions/{row['id']}", payload=payload, version=row["version"]).status_code == 409
    assert (
        request(f, "POST", f"/versions/{row['id']}/calculate", payload=REASON, version=row["version"]).status_code
        == 409
    )
    f.db.expire_all()
    record = f.db.get(ForecastVersion, row["id"])
    with pytest.raises(ValueError, match="IMMUTABLE"):
        with f.db.begin_nested():
            record.name = "Forbidden ORM edit"
            f.db.flush()
    for table, identity, field, value in (
        ("forecast_versions", row["id"], "name", "tamper"),
        ("forecast_assumptions", row["assumptions"][0]["id"], "value", "999"),
        ("forecast_components", row["cost_items"][0]["id"], "name", "tamper"),
    ):
        with pytest.raises(DBAPIError):
            with f.db.begin_nested():
                f.db.execute(
                    text(f"UPDATE {table} SET {field}=:value WHERE id=:identity"),
                    {"value": value, "identity": identity},
                )
    assert success(request(f, "GET", f"/versions/{row['id']}"))["content_hash"] == row["content_hash"]


def test_approved_children_cannot_be_reparented_to_same_project_draft_via_orm_or_sql(fixture):
    f = fixture
    original = approved(f)
    # Empty same-Project DRAFT: neither scope checks nor uniqueness collisions
    # should obscure the check that an existing child's parent cannot change.
    destination = draft(f, assumptions=[], cost_items=[], time_items=[])
    assert destination["status"] == "DRAFT"
    assert destination["project_workspace_id"] == original["project_workspace_id"]
    for model, child in (
        (ForecastAssumption, original["assumptions"][0]),
        (ForecastComponent, original["cost_items"][0]),
    ):
        record = f.db.get(model, child["id"])
        assert record.forecast_version_id == original["id"]
        f.db.expire(record, ["forecast_version_id"])
        with pytest.raises(ValueError, match="FORECAST_CHILD_PARENT_IMMUTABLE"):
            with f.db.begin_nested():
                record.forecast_version_id = destination["id"]
                f.db.flush()
        with pytest.raises(DBAPIError, match="Forecast input parent is immutable"):
            with f.db.begin_nested():
                f.db.execute(
                    text(f"UPDATE {model.__tablename__} SET forecast_version_id=:parent_id WHERE id=:child_id"),
                    {"parent_id": destination["id"], "child_id": child["id"]},
                )
        assert record.forecast_version_id == original["id"]
    assert success(request(f, "GET", f"/versions/{original['id']}")) == original
    assert success(request(f, "GET", f"/versions/{destination['id']}")) == destination


def test_successor_preserves_original_and_freezes_new_assumption_revision(fixture):
    f, old = fixture, approved(fixture)
    payload = deepcopy(old["input_json"])
    payload["assumptions"][0]["value"] = "95"
    payload["cost_items"][0]["inputs"]["phasing"][0]["amount"] = "95"
    payload["reason"] = "Approved source correction requires governed successor"
    row = success(request(f, "POST", f"/versions/{old['id']}/successor", payload=payload, version=old["version"]), 201)
    assert row["revision"] == old["revision"] + 1 and row["supersedes_id"] == old["id"]
    duplicate = request(f, "POST", f"/versions/{old['id']}/successor", payload=payload, version=old["version"])
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "FORECAST_LATEST_VERSION_WITHOUT_SUCCESSOR_REQUIRED"
    row = approved(f, row)
    assert Decimal(row["result_json"]["cost"]["eac"]) == 120
    preserved = success(request(f, "GET", f"/versions/{old['id']}"))
    assert preserved["status"] == "APPROVED" and preserved["effective_status"] == "SUPERSEDED"
    assert preserved["result_json"] == old["result_json"] and preserved["content_hash"] == old["content_hash"]


def test_tenant_and_project_isolation(fixture):
    f, row = fixture, draft(fixture)
    assert request(f, "GET", f"/versions/{row['id']}", actor="foreign").status_code in {403, 404}
    assert request(f, "POST", "/versions", payload=body(f, bundle_id=2147483647)).status_code == 404
    payload = body(f)
    payload["assumptions"][0]["owner_id"] = f.users["foreign"].id
    assert request(f, "POST", "/versions", payload=payload).status_code == 422


def test_currency_mismatch_returns_not_computable_with_null_financial_metrics(fixture):
    f, payload = fixture, body(fixture, currency="EUR")
    payload["assumptions"][0].update(value="75", unit="EUR", currency="EUR")
    payload["cost_items"][0].update(currency="EUR")
    payload["cost_items"][0]["inputs"]["phasing"][0]["currency"] = "EUR"
    payload["time_items"][0]["currency"] = "EUR"
    row = calculate(f, success(request(f, "POST", "/versions", payload=payload), 201))
    result = row["result_json"]["cost"]
    assert result["status"] == "NOT_COMPUTABLE" and "FORECAST_CURRENCY_MISMATCH" in result["reason_codes"]
    assert all(result[key] is None for key in ("actual", "etc", "eac", "vac"))
    assert (
        request(
            f,
            "POST",
            f"/versions/{row['id']}/transition",
            version=row["version"],
            payload={**REASON, "action": "review"},
        ).status_code
        == 409
    )


def test_quantity_rate_uses_approved_remaining_quantity_and_declared_rate(fixture):
    f, payload = fixture, body(fixture)
    unit = f.scope_items[0]["unit"]
    payload["assumptions"].append(assumption(f, "UNIT-RATE", "15", f"USD/{unit}", kind="RATE"))
    payload["cost_items"] = [
        component(
            f,
            "Q-RATE",
            method="QUANTITY_RATE",
            assumption_codes=["UNIT-RATE"],
            inputs={"rate_assumption_code": "UNIT-RATE"},
        )
    ]
    row = calculate(f, success(request(f, "POST", "/versions", payload=payload), 201))
    cost = row["result_json"]["cost"]
    assert cost["status"] == "COMPUTABLE", cost
    remaining = Decimal(f.scope_items[0]["quantity"]) / 2
    assert Decimal(cost["etc"]) == remaining * 15
    assert cost["items"][0]["quantity_basis"]["source"] == "APPROVED_QUANTITY_PROGRESS"


@pytest.mark.parametrize(
    "kind,expected_unit",
    [
        ("LABOR", "h"),
        ("EQUIPMENT", "equipment-hour"),
        ("CREW", "h"),
        ("ENGINEERING_HOURS", "h"),
        ("CONSTRUCTION_HOURS", "h"),
        ("PROJECT_CONTROLS_HOURS", "h"),
    ],
)
def test_resource_foundation_units_and_remaining_quantity(fixture, kind, expected_unit):
    f, payload = fixture, body(fixture)
    unit = f.scope_items[0]["unit"]
    payload["assumptions"].append(assumption(f, "PRODUCTIVITY", "2", f"h/{unit}", kind="PRODUCTIVITY", currency=None))
    payload["resource_items"] = [
        component(
            f,
            "RESOURCE",
            method="PRODUCTIVITY_BASED",
            assumption_codes=["PRODUCTIVITY"],
            inputs={
                "productivity_assumption_code": "PRODUCTIVITY",
                "productivity_basis": "HOURS_PER_UNIT",
                "resource_type": kind,
            },
        )
    ]
    row = calculate(f, success(request(f, "POST", "/versions", payload=payload), 201))
    resource = row["result_json"]["resources"]["items"][0]
    assert resource["status"] == "COMPUTABLE", resource
    assert resource["unit"] == expected_unit
    assert Decimal(resource["quantity"]) == Decimal(f.scope_items[0]["quantity"])


def test_draft_assumption_not_confirmed_blocks_approval(fixture):
    f, payload = fixture, body(fixture)
    payload["assumptions"][0]["status"] = "DRAFT"
    row = calculate(f, success(request(f, "POST", "/versions", payload=payload), 201))
    assert row["result_json"]["status"] == "NOT_COMPUTABLE"
    assert (
        request(
            f,
            "POST",
            f"/versions/{row['id']}/transition",
            payload={**REASON, "action": "review"},
            version=row["version"],
        ).status_code
        == 409
    )


def test_get_reads_do_not_create_forecast_rows_or_history(fixture):
    f, row = fixture, approved(fixture)
    f.db.expire_all()
    models = (ForecastVersion, ForecastAssumption, ForecastComponent, ForecastHistory)
    before = _hash(
        [[r.id for r in f.db.scalars(select(model).where(model.tenant_id == f.tenant_id))] for model in models]
    )
    for path in ("/overview", "/history", "/versions", f"/versions/{row['id']}", f"/versions/{row['id']}/calculation"):
        assert request(f, "GET", path).status_code == 200
    f.db.expire_all()
    after = _hash(
        [[r.id for r in f.db.scalars(select(model).where(model.tenant_id == f.tenant_id))] for model in models]
    )
    assert before == after


@pytest.mark.parametrize("method", ["BOTTOM_UP", "CONTROL_ACCOUNT", "MANUAL_GOVERNED"])
def test_governed_amount_methods_use_persisted_assumption_not_a_placeholder(fixture, method):
    f, payload = fixture, body(fixture)
    payload["cost_items"][0]["method"] = method
    row = calculate(f, success(request(f, "POST", "/versions", payload=payload), 201))
    assert row["result_json"]["cost"]["status"] == "COMPUTABLE", row["result_json"]
    assert Decimal(row["result_json"]["cost"]["etc"]) == 75
    assert row["result_json"]["assumption_hashes"]["REMAINING-COST"]


def test_explicit_duration_rate_cost_does_not_add_working_duration_to_calendar_dates(fixture):
    f, payload = fixture, body(fixture)
    payload["assumptions"] += [
        assumption(f, "REMAINING-DURATION", "5", "h", kind="DURATION", currency=None),
        assumption(f, "HOUR-RATE", "12", "USD/h", kind="RATE"),
    ]
    payload["cost_items"] = [
        component(
            f,
            "DURATION-COST",
            method="ACTIVITY_REMAINING_DURATION",
            activity_external_id=f.schedule_version["snapshot_json"]["activities"][0]["external_id"],
            assumption_codes=["REMAINING-DURATION", "HOUR-RATE"],
            inputs={"duration_assumption_code": "REMAINING-DURATION", "rate_assumption_code": "HOUR-RATE"},
        )
    ]
    row = calculate(f, success(request(f, "POST", "/versions", payload=payload), 201))
    assert row["result_json"]["cost"]["status"] == "COMPUTABLE", row["result_json"]
    assert Decimal(row["result_json"]["cost"]["etc"]) == 60
    assert row["result_json"]["time"]["forecast_finish"] == "2026-11-20"
    assert row["result_json"]["time"]["cpm_calculated"] is False


def test_productivity_cost_uses_declared_unit_per_day_and_daily_rate(fixture):
    f, payload = fixture, body(fixture)
    unit = f.scope_items[0]["unit"]
    payload["assumptions"] += [
        assumption(f, "PRODUCTIVITY-COST", "2", f"{unit}/day", kind="PRODUCTIVITY", currency=None),
        assumption(f, "DAILY-RATE", "30", "USD/day", kind="RATE"),
    ]
    payload["cost_items"] = [
        component(
            f,
            "PRODUCTIVITY-COST",
            method="PRODUCTIVITY_BASED",
            assumption_codes=["PRODUCTIVITY-COST", "DAILY-RATE"],
            inputs={"productivity_assumption_code": "PRODUCTIVITY-COST", "rate_assumption_code": "DAILY-RATE"},
        )
    ]
    row = calculate(f, success(request(f, "POST", "/versions", payload=payload), 201))
    assert row["result_json"]["cost"]["status"] == "COMPUTABLE", row["result_json"]
    assert Decimal(row["result_json"]["cost"]["etc"]) == Decimal(f.scope_items[0]["quantity"]) / 2 / 2 * 30


def test_commitment_remaining_deducts_recognized_incurred_and_is_not_added_twice(fixture):
    f = fixture
    obligation = commitment(
        f,
        amount="100",
        control_account_id=f.cost_account["id"],
        cbs_id=f.cost_cbs["id"],
        cost_code_id=f.cost_code["id"],
    )
    payload = body(f)
    payload["cost_items"] = [
        component(
            f,
            "COMMITTED",
            method="COMMITMENT_BASED",
            assumption_codes=[],
            inputs={"commitment_ids": [obligation["id"]], "incurred_actual_ids": [f.cost_actual["id"]]},
        )
    ]
    row = calculate(f, success(request(f, "POST", "/versions", payload=payload), 201))
    cost = row["result_json"]["cost"]
    assert cost["status"] == "COMPUTABLE", cost
    assert Decimal(cost["committed_etc"]) == 75
    assert Decimal(cost["actual"]) == 25 and Decimal(cost["eac"]) == 100
    assert cost["commitment_added_to_eac"] is False
    assert Decimal(cost["items"][0]["quantity_basis"][0]["recognized_incurred"]) == 25
    missing = deepcopy(payload)
    missing["code"] = f"FC-{uuid4().hex[:10]}"
    missing["cost_items"][0]["inputs"].pop("incurred_actual_ids")
    result = calculate(f, success(request(f, "POST", "/versions", payload=missing), 201))["result_json"]["cost"]
    assert result["status"] == "NOT_COMPUTABLE" and result["eac"] is None
    assert "FORECAST_COMMITMENT_INCURRED_MAPPING_REQUIRED" in result["reason_codes"]
    duplicate = deepcopy(payload)
    duplicate["code"] = f"FC-{uuid4().hex[:10]}"
    duplicate["cost_items"].append({**deepcopy(duplicate["cost_items"][0]), "code": "DUPLICATE-OBLIGATION"})
    result = calculate(f, success(request(f, "POST", "/versions", payload=duplicate), 201))["result_json"]["cost"]
    assert result["status"] == "NOT_COMPUTABLE" and result["eac"] is None
    assert any("OVERLAP" in reason or "DOUBLE" in reason for reason in result["reason_codes"])


def test_trend_method_requires_approved_prior_asof_and_explicit_factor(fixture):
    f, prior = fixture, approved(fixture)
    payload = body(f, as_of="2026-10-23")
    payload["assumptions"].append(assumption(f, "TREND", "1.1", "ratio", kind="FACTOR", currency=None))
    payload["cost_items"] = [
        component(
            f,
            "TREND-ETC",
            method="TREND_BASED",
            assumption_codes=["TREND"],
            inputs={"prior_forecast_id": prior["id"], "trend_factor_assumption_code": "TREND"},
        )
    ]
    row = calculate(f, success(request(f, "POST", "/versions", payload=payload), 201))
    assert row["result_json"]["cost"]["status"] == "COMPUTABLE", row["result_json"]
    assert Decimal(row["result_json"]["cost"]["etc"]) == Decimal("82.5")
    assert row["result_json"]["cost"]["items"][0]["quantity_basis"]["hash"] == prior["content_hash"]


def test_recognition_after_asof_is_not_invented_as_zero_and_period_mismatch_is_controlled(fixture):
    f, payload = fixture, body(fixture, as_of="2026-10-21")
    for item in payload["assumptions"]:
        item["effective_date"] = "2026-10-21"
    row = calculate(f, success(request(f, "POST", "/versions", payload=payload), 201))
    cost = row["result_json"]["cost"]
    assert cost["status"] == "NOT_COMPUTABLE" and cost["eac"] is None and cost["actual"] is None
    assert "RECOGNIZED_ACTUAL_REQUIRED" in cost["reason_codes"]
    bad = request(f, "POST", "/versions", payload=body(f, as_of="2026-10-26"))
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "FORECAST_PERIOD_AS_OF_MISMATCH"


def test_rejected_is_frozen_and_has_auditable_reason(fixture):
    f, row = fixture, calculate(fixture, draft(fixture))
    row = success(
        request(
            f,
            "POST",
            f"/versions/{row['id']}/transition",
            version=row["version"],
            payload={**REASON, "action": "review"},
        )
    )
    row = success(
        request(
            f,
            "POST",
            f"/versions/{row['id']}/transition",
            actor="manager",
            version=row["version"],
            payload={"reason": "Independent review rejects unsupported delivery narrative", "action": "reject"},
        )
    )
    assert row["status"] == "REJECTED" and row["approved_by"] is None
    assert (
        request(f, "PUT", f"/versions/{row['id']}", version=row["version"], payload=row["input_json"]).status_code
        == 409
    )
    history = success(request(f, "GET", "/history"))["items"]
    assert any(r["entity_id"] == row["id"] and r["event_type"] == "FORECAST_REJECTED" for r in history)


def test_readiness_at_forecast_cutoff_uses_persisted_evidence_not_future_assessments(fixture):
    f = fixture
    base = f"/api/v1/awp/projects/{f.project_workspace_id}"
    package = success(request(f, "GET", base + "/packages", actor="admin"))["items"][0]

    def assess(row, as_of):
        return success(
            request(
                f,
                "POST",
                base + f"/packages/{row['id']}/assess",
                actor="admin",
                version=row["version"],
                payload={**REASON, "as_of": as_of, "evidence_json": {}},
            ),
            201,
        )

    future = assess(package, "2026-10-23")
    snapshot = draft(f)["source_snapshot_json"]
    key = str(package["id"])
    assert snapshot["readiness"] == []
    assert snapshot["current_readiness"][key]["readiness_state"] == "UNKNOWN"
    assert snapshot["current_readiness"][key]["assessment_id"] is None

    recorded = assess(future["package"], "2026-10-22")
    frozen = approved(f)
    assess(recorded["package"], "2026-10-24")
    current = draft(f)["source_snapshot_json"]
    assert [row["id"] for row in current["readiness"]] == [recorded["id"]]
    assert current["current_readiness"][key]["assessment_id"] == recorded["id"]
    assert current["current_readiness"][key]["readiness_state"] == recorded["readiness_state"]
    assert current["current_readiness"][key]["source_hashes"] == recorded["source_hashes"]
    assert success(request(f, "GET", f"/versions/{frozen['id']}")) == frozen


def test_accepted_current_may_differ_from_pinned_baseline_without_upstream_mutation(fixture):
    from tests.test_schedule_foundation_release import accept, map_all, version
    from tests.test_schedule_foundation_release import request as schedule_request

    f = fixture
    prior = approved(f)
    before_baseline = deepcopy(f.schedule_baseline)
    before_snapshot = deepcopy(f.schedule_version["snapshot_json"])
    register = success(schedule_request(f, "GET", f"/registers/{f.schedule_register['id']}"))
    changed = deepcopy(before_snapshot)
    changed["activities"][0]["name"] += " imported external successor"
    imported = version(f, register, content=changed, predecessor=f.schedule_version["id"], kind="UPDATE")
    f.schedule_version = accept(f, map_all(f, imported))
    baseline_source = f.bundle["source_snapshot_json"]["schedule_baseline"]
    assert baseline_source["schedule_version_id"] == before_baseline["schedule_version_id"]
    assert f.schedule_version["id"] != baseline_source["schedule_version_id"]
    validation = success(progress_request(f, "GET", f"/baseline-bundles/{f.bundle['id']}/validate"))
    assert validation["effective_state"] == "APPROVED", validation["reason_codes"]
    assert validation["current_hash"] == validation["frozen_hash"] == f.bundle["content_hash"]
    row = calculate(f, draft(f))
    assert row["result_json"]["cost"]["status"] == "COMPUTABLE", row["result_json"]
    assert row["source_snapshot_json"]["baseline_schedule"]["id"] == before_baseline["id"]
    assert row["source_snapshot_json"]["current_schedule"]["id"] == f.schedule_version["id"]
    assert row["result_json"]["time"]["cpm_calculated"] is False
    accepted = success(schedule_request(f, "GET", f"/versions/{f.schedule_version['id']}"))
    assert (
        accepted["content_hash"] == f.schedule_version["content_hash"]
        and accepted["version"] == f.schedule_version["version"]
    )
    frozen = success(request(f, "GET", f"/versions/{prior['id']}/calculation"))
    assert frozen["frozen"] is True and frozen["source_refs"]["schedule_version_id"] != f.schedule_version["id"]


def test_pure_forecast_role_reads_required_sources_without_upstream_write_grants(fixture):
    from tests.operational_context_fixture import fixture_headers

    from app.domain.models import (
        PermissionCatalog,
        SecurityAccessAssignment,
        SecurityRole,
        SecurityRolePermission,
        UserAccount,
    )

    f = fixture
    actor = UserAccount(
        tenant_id=f.tenant_id,
        email=f"forecast-only-{uuid4().hex}@o1c.test",
        full_name="Isolated scoped Forecast controller",
        status="active",
    )
    f.db.add(actor)
    f.db.flush()
    role = f.db.scalar(
        select(SecurityRole).where(SecurityRole.tenant_id == f.tenant_id, SecurityRole.code == "forecast_controller")
    )
    f.db.add(
        SecurityAccessAssignment(
            tenant_id=f.tenant_id,
            subject_type="user",
            user_id=actor.id,
            role_id=role.id,
            scope_type="workspace",
            workspace_id=f.project_workspace_id,
            granted_by_user_id=f.users["admin"].id,
            status="active",
        )
    )
    f.db.commit()
    f.headers["forecast_only"] = fixture_headers(actor)
    overview = success(request(f, "GET", "/overview", actor="forecast_only"))
    assert "etc.calculate" in overview["allowed_actions"] and "approve" not in overview["allowed_actions"]
    row = success(request(f, "POST", "/versions", payload=body(f), actor="forecast_only"), 201)
    row = calculate(f, row, actor="forecast_only")
    assert row["result_json"]["cost"]["status"] == "COMPUTABLE", row["result_json"]
    assert request(
        f, "GET", f"/api/v1/forecast/projects/{f.workspaces['other_project'].id}/overview", actor="forecast_only"
    ).status_code in {403, 404}
    permissions = set(
        f.db.scalars(
            select(PermissionCatalog.key)
            .join(SecurityRolePermission, SecurityRolePermission.permission_id == PermissionCatalog.id)
            .where(SecurityRolePermission.tenant_id == f.tenant_id, SecurityRolePermission.role_id == role.id)
        )
    )
    source_writes = {
        "progress.create",
        "progress.approve",
        "progress.period.publish",
        "cost.actual.recognize",
        "cost.commitment.verify",
        "schedule_foundation.import",
        "schedule_foundation.accept",
        "scope_foundation.publish",
        "awp.package.create",
    }
    assert not permissions & source_writes


def test_resource_quantity_per_day_with_crew_keeps_person_days_separate_from_hours(fixture):
    f, payload = fixture, body(fixture)
    unit = f.scope_items[0]["unit"]
    payload["assumptions"] += [
        assumption(f, "OUTPUT", "2", f"{unit}/day", kind="PRODUCTIVITY", currency=None),
        assumption(f, "CREW", "3", "person", kind="CREW", currency=None),
    ]
    payload["resource_items"] = [
        component(
            f,
            "CREW-REMAINING",
            method="PRODUCTIVITY_BASED",
            assumption_codes=["OUTPUT", "CREW"],
            inputs={
                "resource_type": "LABOR",
                "productivity_basis": "QUANTITY_PER_DAY",
                "productivity_assumption_code": "OUTPUT",
                "crew_assumption_code": "CREW",
            },
        )
    ]
    row = calculate(f, success(request(f, "POST", "/versions", payload=payload), 201))
    resource = row["result_json"]["resources"]["items"][0]
    assert resource["status"] == "COMPUTABLE" and resource["unit"] == "person-day"
    assert Decimal(resource["quantity"]) == Decimal(f.scope_items[0]["quantity"]) / 2 / 2 * 3
    assert row["result_json"]["resources"]["cross_unit_aggregation"] is False
    payload["code"] = f"FC-{uuid4().hex[:10]}"
    payload["assumptions"][-2]["unit"] = f"h/{unit}"
    row = calculate(f, success(request(f, "POST", "/versions", payload=payload), 201))
    assert row["result_json"]["resources"]["status"] == "NOT_COMPUTABLE"
    assert row["result_json"]["resources"]["items"][0]["quantity"] is None


def test_forecast_approval_has_no_upstream_domain_write_path(fixture):
    from sqlalchemy import event

    from app.database.session import engine

    writes = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        normalized = " ".join(statement.lower().split())
        if normalized.startswith(("insert into ", "update ", "delete from ")):
            writes.append(normalized)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        assert approved(fixture)["status"] == "APPROVED"
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert writes
    allowed = ("forecast_", "operational_context_commands", "security_events")
    for statement in writes:
        target = (
            statement.split()[2] if statement.startswith(("insert into ", "delete from ")) else statement.split()[1]
        )
        assert target.startswith(allowed), statement


def test_populated_downgrade_is_refused_before_any_schema_or_business_change(fixture):
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect

    from app.modules.forecast_foundation.migration_schema import FORECAST_MIGRATION_TABLE_NAMES

    f = fixture
    draft(f)
    f.db.expire_all()
    connection = f.db.connection()

    def state():
        return {
            "head": connection.scalar(text("SELECT version_num FROM alembic_version")),
            "tables": set(inspect(connection).get_table_names()),
            "counts": {
                name: connection.scalar(text(f"SELECT count(*) FROM {name}"))
                for name in sorted(FORECAST_MIGRATION_TABLE_NAMES)
            },
        }

    before = state()
    migration = ScriptDirectory.from_config(Config("alembic.ini")).get_revision("20261106_0075").module
    with Operations.context(MigrationContext.configure(connection)):
        with pytest.raises(RuntimeError, match="business records"):
            migration.downgrade()
    assert state() == before


def test_future_effective_commitment_successor_does_not_hide_asof_obligation(fixture):
    f = fixture
    old = commitment(
        f,
        amount="100",
        control_account_id=f.cost_account["id"],
        cbs_id=f.cost_cbs["id"],
        cost_code_id=f.cost_code["id"],
    )
    future = commitment(
        f,
        amount="150",
        control_account_id=f.cost_account["id"],
        cbs_id=f.cost_cbs["id"],
        cost_code_id=f.cost_code["id"],
        supersedes_id=old["id"],
        source_system=old["source_system"],
        source_type=old["source_type"],
        source_reference=old["source_reference"],
        source_revision="2",
        source_hash="b" * 64,
        economic_origin=old["economic_origin"],
        effective_date="2026-10-24",
    )
    payload = body(f)
    payload["cost_items"] = [
        component(
            f,
            "ASOF-COMMITMENT",
            method="COMMITMENT_BASED",
            assumption_codes=[],
            inputs={"commitment_ids": [old["id"]], "incurred_actual_ids": [f.cost_actual["id"]]},
        )
    ]
    row = calculate(f, success(request(f, "POST", "/versions", payload=payload), 201))
    cost = row["result_json"]["cost"]
    assert cost["status"] == "COMPUTABLE", cost
    assert Decimal(cost["etc"]) == 75 and Decimal(cost["eac"]) == 100
    sources = row["source_snapshot_json"]["commitments"]["items"]
    assert old["id"] in {item["id"] for item in sources}
    assert future["id"] not in {item["id"] for item in sources}
