"""Real PostgreSQL read models and immutable publication across reused authorities."""

import os
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from tests.forecast_release_fixture import REASON, approved, body, calculate, create_forecast_fixture, draft, request
from tests.progress_release_fixture import request as progress_request
from tests.test_progress_foundation_release import approve as approve_progress
from tests.test_progress_foundation_release import measurement_body
from tests.test_scope_foundation_release import success

from app.database.session import SessionLocal
from app.domain.models import SecurityEvent
from app.main import app
from app.modules.basic_data.service import _hash
from app.modules.forecast_foundation.models import ForecastHistory
from app.modules.forecast_foundation.reporting_models import ForecastLookAheadSnapshot, ForecastReportSnapshot
from app.modules.schedule_foundation.models import ScheduleVersion
from app.modules.scope_foundation.models import ScopeBaseline

pytestmark = pytest.mark.skipif(
    os.getenv("PYPMIS_O1C_FIXTURE") != "disposable-only", reason="Dedicated O1C disposable PostgreSQL required"
)


def assess_packages(f, *, as_of="2026-10-22"):
    path = f"/api/v1/awp/projects/{f.project_workspace_id}"
    packages = success(request(f, "GET", path + "/overview", actor="admin"))["packages"]
    for package in packages:
        success(
            request(
                f,
                "POST",
                path + f"/packages/{package['id']}/assess",
                actor="admin",
                version=package["version"],
                payload={**REASON, "as_of": as_of, "evidence_json": {}},
            ),
            201,
        )


def publish_period(f):
    row = success(progress_request(f, "GET", f"/periods/{f.period['id']}/review"))["period"]
    for action, actor in (("review", "manager"), ("close", "manager"), ("publish", "second_manager")):
        row = success(
            progress_request(
                f,
                "POST",
                f"/periods/{row['id']}/transition",
                actor=actor,
                version=row["version"],
                payload={**REASON, "action": action},
            )
        )["period"]
    f.period = row
    return row


def report_body(forecast):
    return {**REASON, "forecast_version_id": forecast["id"], "evidence_reference": "AUTHORIZED-TECHNICAL-REPORT-SOURCE"}


def report_request(f, method, suffix="", **kwargs):
    return request(f, method, f"/api/v1/reporting/projects/{f.project_workspace_id}/reports" + suffix, **kwargs)


def performance(f, page, forecast=None, **params):
    return request(
        f,
        "GET",
        f"/api/v1/performance/projects/{f.project_workspace_id}/{page}",
        params={"forecast_version_id": (forecast or f.forecast)["id"], **params},
    )


@pytest.fixture(scope="module")
def fixture():
    with TestClient(app) as client, SessionLocal() as db:
        f = create_forecast_fixture(db, client)
        assess_packages(f)
        f.forecast = approved(f)
        yield f
        db.rollback()


@pytest.fixture(scope="module")
def published_fixture():
    with TestClient(app) as client, SessionLocal() as db:
        f = create_forecast_fixture(db, client)
        assess_packages(f)
        f.forecast = approved(f)
        publish_period(f)
        f.report_payload, f.report_key = report_body(f.forecast), f"report-{uuid4()}"
        f.report = success(
            report_request(f, "POST", payload=f.report_payload, actor="second_manager", key=f.report_key), 201
        )
        yield f
        db.rollback()


def test_performance_reuses_frozen_evm_and_distinct_forecast_current_baseline(fixture):
    f = fixture
    result = success(performance(f, "overview"))
    assert Decimal(result["metrics"]["pv"]) == Decimal(f.evm_snapshot["pv"])
    assert Decimal(result["metrics"]["ev"]) == Decimal(f.evm_snapshot["ev"])
    assert Decimal(result["metrics"]["ac"]) == Decimal(f.evm_snapshot["ac"])
    assert Decimal(result["metrics"]["cpi"]) == Decimal(f.evm_snapshot["cpi"])
    assert Decimal(result["metrics"]["spi"]) == Decimal(f.evm_snapshot["spi"])
    assert result["metrics"]["forecast_finish"] == "2026-11-20"
    assert result["metrics"]["forecast_finish"] != result["metrics"]["current_finish"]
    assert Decimal(result["metrics"]["eac"]) == 100
    assert result["authority"]["source_writes_performed"] is False


def test_variance_cost_vac_and_time_delta_keep_explicit_control_basis(fixture):
    result = success(performance(fixture, "variance"))
    cost, finish = result["items"]
    assert Decimal(cost["variance"]) == Decimal(cost["baseline"]) - Decimal(cost["forecast"])
    assert finish["unit"] == "CALENDAR_DAY_DELTA_NOT_CPM"
    assert result["progress_variances"]["approved_physical_progress"] is not None
    assert result["progress_variances"]["status"] == "NOT_COMPUTABLE"
    assert result["progress_variances"]["physical_variance"] is None


def test_reporting_source_context_rejects_mismatched_period_and_as_of(fixture):
    f = fixture
    assert performance(f, "overview", period_id=f.period["id"] + 999999).status_code == 422
    assert performance(f, "overview", as_of="2026-10-23").status_code == 422


def test_all_six_s_curves_keep_units_and_explicit_forecast_phasing(fixture):
    result = success(performance(fixture, "curves"))
    series = {row["code"]: row for row in result["series"]}
    assert set(series) == {
        "PLANNED_PROGRESS",
        "APPROVED_ACTUAL_PROGRESS",
        "EARNED_VALUE",
        "PLANNED_VALUE",
        "ACTUAL_COST",
        "FORECAST_COST",
    }
    assert series["PLANNED_PROGRESS"]["unit"] == "%" and series["PLANNED_PROGRESS"]["currency"] is None
    assert "NOT_PHYSICAL" in series["PLANNED_PROGRESS"]["basis"]
    assert series["ACTUAL_COST"]["currency"] == "USD"
    assert Decimal(series["ACTUAL_COST"]["points"][-1]["cumulative_value"]) == 25
    assert Decimal(series["FORECAST_COST"]["points"][-1]["cumulative_value"]) == 100
    assert series["FORECAST_COST"]["status"] == "COMPUTABLE"
    assert all(row["source_refs"] for row in series.values())


def test_dashboard_and_executive_are_read_models_without_business_writes(fixture):
    f = fixture

    def counts():
        return [
            f.db.scalar(select(func.count()).select_from(model))
            for model in (ForecastHistory, ForecastReportSnapshot, ForecastLookAheadSnapshot, SecurityEvent)
        ]

    before = counts()
    schedule_before = f.db.scalar(
        select(ScheduleVersion.content_hash).where(ScheduleVersion.id == f.schedule_version["id"])
    )
    scope_before = f.db.scalar(select(ScopeBaseline.content_hash).where(ScopeBaseline.id == f.scope_baseline["id"]))
    dashboard = success(performance(f, "dashboard"))
    executive = success(
        request(
            f,
            "GET",
            f"/api/v1/performance/projects/{f.project_workspace_id}/executive",
            actor="manager",
            params={"forecast_version_id": f.forecast["id"]},
        )
    )
    assert dashboard["view"] == "PROJECT_CONTROLS" and executive["view"] == "EXECUTIVE"
    assert set(dashboard["domains"]) == {"schedule", "cost", "progress", "forecast", "awp"}
    assert counts() == before
    assert dashboard["metrics"]["schedule_progress"]
    assert dashboard["metrics"]["cost_progress"]
    assert (
        f.db.scalar(select(ScheduleVersion.content_hash).where(ScheduleVersion.id == f.schedule_version["id"]))
        == schedule_before
    )
    assert (
        f.db.scalar(select(ScopeBaseline.content_hash).where(ScopeBaseline.id == f.scope_baseline["id"]))
        == scope_before
    )


def test_lookahead_four_week_default_and_custom_horizon_do_not_calculate_cpm(fixture):
    f = fixture
    default = success(performance(f, "lookahead"))
    assert default["horizon_days"] == 28
    assert default["authority"]["cpm_calculation_performed"] is False
    assert default["source_refs"]["schedule_version_id"] == f.schedule_version["id"]
    for days in (7, 42):
        result = success(performance(f, "lookahead", horizon_days=days))
        assert result["horizon_days"] == days
    assert performance(f, "lookahead", group_by="INVALID").status_code == 422


@pytest.mark.parametrize("params", [{"forecast_version_id": 0}, {"wbs_external_id": "x" * 161}])
def test_lookahead_invalid_query_contract_returns_422_not_server_error(fixture, params):
    assert performance(fixture, "lookahead", **params).status_code == 422


@pytest.mark.parametrize("group", ["PARENT_WBS", "CWA", "PACKAGE", "AREA", "ZONE", "SYSTEM", "DISCIPLINE"])
def test_lookahead_all_groupings_join_plan_package_scope_readiness_constraints(fixture, group):
    result = success(performance(fixture, "lookahead", group_by=group))
    assert result["group_by"] == group
    assert result["items"], result
    row = result["items"][0]
    assert "scope_item_ids" in row and "plan_item_ids" in row and "work_package_ids" in row
    assert "readiness" in row and "constraints" in row
    assert row["driving_predecessor"]["state"] in {"UNKNOWN", "IMPORTED"}


def test_lookahead_generated_snapshot_audited_but_get_is_not(fixture):
    f = fixture
    payload = {"forecast_version_id": f.forecast["id"], **REASON}
    before = f.db.scalar(select(func.count()).select_from(ForecastLookAheadSnapshot))
    success(performance(f, "lookahead"))
    assert f.db.scalar(select(func.count()).select_from(ForecastLookAheadSnapshot)) == before
    row = success(
        request(
            f, "POST", f"/api/v1/performance/projects/{f.project_workspace_id}/lookahead/snapshots", payload=payload
        ),
        201,
    )
    assert row["result_snapshot_json"]["horizon_days"] == 28
    assert row["content_hash"] == _hash(row["result_snapshot_json"])
    with pytest.raises(DBAPIError):
        with f.db.begin_nested():
            f.db.execute(
                text("UPDATE forecast_lookahead_snapshots SET reason='tamper' WHERE id=:id"), {"id": row["id"]}
            )


def test_draft_lookahead_preview_is_read_only_and_cannot_create_snapshot(fixture):
    f = fixture
    row = draft(f)

    def counts():
        return [
            f.db.scalar(select(func.count()).select_from(model))
            for model in (ForecastLookAheadSnapshot, ForecastHistory, SecurityEvent)
        ]

    before = counts()
    preview = success(performance(f, "lookahead", row))
    assert preview["forecast_version_id"] == row["id"]
    assert counts() == before
    response = request(
        f,
        "POST",
        f"/api/v1/performance/projects/{f.project_workspace_id}/lookahead/snapshots",
        payload={"forecast_version_id": row["id"], **REASON},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "LOOKAHEAD_APPROVED_FORECAST_REQUIRED"
    after = counts()
    assert after[:2] == before[:2]
    assert after[2] == before[2] + 1  # A rejected command remains auditable; GET above was write-free.


@pytest.mark.parametrize("amount", ["NOT-A-NUMBER", "1e30"])
def test_malformed_draft_forecast_phasing_returns_read_only_not_computable_http(fixture, amount):
    f = fixture
    payload = body(f)
    payload["cost_items"][0]["inputs"]["phasing"] = [{"date": "2026-11-01", "amount": amount}]
    row = success(request(f, "POST", "/versions", payload=payload), 201)
    before = [
        f.db.scalar(select(func.count()).select_from(model))
        for model in (ForecastHistory, ForecastLookAheadSnapshot, ForecastReportSnapshot, SecurityEvent)
    ]
    result = success(performance(f, "curves", row))
    forecast = next(item for item in result["series"] if item["code"] == "FORECAST_COST")
    assert forecast["status"] == "NOT_COMPUTABLE"
    assert "FORECAST_COST_PHASING_NUMERIC_OR_DATE_INVALID" in forecast["reason_codes"]
    assert forecast["points"] == []
    after = [
        f.db.scalar(select(func.count()).select_from(model))
        for model in (ForecastHistory, ForecastLookAheadSnapshot, ForecastReportSnapshot, SecurityEvent)
    ]
    assert after == before


def test_report_publication_requires_published_common_control_period(fixture):
    response = report_request(fixture, "POST", payload=report_body(fixture.forecast), actor="second_manager")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REPORT_PUBLISHED_PERIOD_REQUIRED"


def test_published_report_pins_all_domains_and_independent_publisher(published_fixture):
    f = published_fixture
    report = f.report
    assert report["status"] == "PUBLISHED"
    assert report["published_by"] not in {f.forecast["prepared_by"], f.forecast["approved_by"]}
    assert report["bundle_id"] == f.bundle["id"]
    assert report["schedule_version_id"] == f.schedule_version["id"]
    assert report["cost_baseline_id"] == f.cost_baseline["id"]
    assert report["progress_snapshot_id"] and report["evm_snapshot_id"]
    assert report["source_refs_json"]["readiness"]["assessment_ids"]
    assert (
        report["source_snapshot_json"]["cost_period_snapshot"]["authority"]
        == "DERIVED_COST_PERIOD_READ_MODEL_NOT_COST_TRANSACTION"
    )
    assert all(row["fact_references"] for row in report["narratives_json"])


def test_report_publication_idempotency_is_not_duplicate_history(published_fixture):
    f = published_fixture
    old = success(report_request(f, "POST", payload=f.report_payload, actor="second_manager", key=f.report_key), 201)
    assert old == f.report
    assert (
        report_request(
            f,
            "POST",
            payload={**f.report_payload, "reason": "Changed governed publication reason"},
            actor="second_manager",
            key=f.report_key,
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE forecast_report_snapshots SET reason='tamper' WHERE id=:id",
        "DELETE FROM forecast_report_snapshots WHERE id=:id",
    ],
)
def test_published_report_sql_immutability(published_fixture, statement):
    f = published_fixture
    with pytest.raises(DBAPIError):
        with f.db.begin_nested():
            f.db.execute(text(statement), {"id": f.report["id"]})
    assert success(report_request(f, "GET", f"/{f.report['id']}"))["content_hash"] == f.report["content_hash"]


def test_report_orm_immutability(published_fixture):
    f = published_fixture
    with pytest.raises(ValueError, match="immutable"):
        with f.db.begin_nested():
            row = f.db.get(ForecastReportSnapshot, f.report["id"])
            row.reason = "Attempt to overwrite published report"
            f.db.flush()


def test_report_permission_and_sod_are_independent_of_forecast_approval(published_fixture):
    f = published_fixture
    assert report_request(f, "POST", payload=f.report_payload, actor="cost_controller").status_code == 403
    assert report_request(f, "POST", payload=f.report_payload, actor="manager").status_code == 403
    assert report_request(f, "GET", f"/{f.report['id']}", actor="foreign").status_code in {403, 404}


def test_report_successor_requires_new_approved_forecast_and_keeps_old_result(published_fixture):
    f = published_fixture
    payload = deepcopy(f.forecast["input_json"])
    payload["reason"] = "Governed corrected Forecast successor for report republish"
    successor = success(
        request(f, "POST", f"/versions/{f.forecast['id']}/successor", version=f.forecast["version"], payload=payload),
        201,
    )
    successor = approved(f, successor)
    bad_narrative = report_body(successor) | {
        "narratives": [{"section": "COST", "text": "Unsupported claim", "fact_references": ["NO_SOURCE"]}]
    }
    assert (
        report_request(
            f,
            "POST",
            f"/{f.report['id']}/successor",
            actor="second_manager",
            version=f.report["version"],
            payload=bad_narrative,
        ).status_code
        == 422
    )
    assert (
        report_request(
            f,
            "POST",
            f"/{f.report['id']}/successor",
            actor="second_manager",
            version=999,
            payload=report_body(successor),
        ).status_code
        == 412
    )
    corrected = success(
        report_request(
            f,
            "POST",
            f"/{f.report['id']}/successor",
            actor="second_manager",
            version=f.report["version"],
            payload=report_body(successor),
        ),
        201,
    )
    assert corrected["revision"] == 2 and corrected["supersedes_id"] == f.report["id"]
    assert success(report_request(f, "GET", f"/{f.report['id']}")) == f.report
    trends = success(performance(f, "trends"))
    assert len(trends["items"]) == 1 and trends["items"][0]["id"] == corrected["id"]
    assert len(success(report_request(f, "GET", "/history"))["items"]) == 2


def test_power_bi_read_model_contract_has_explicit_refresh_and_no_writeback(published_fixture):
    f = published_fixture
    result = success(request(f, "GET", f"/api/v1/reporting/projects/{f.project_workspace_id}/analytics-contract"))
    assert result["write_back_supported"] is False
    assert "EXPLICIT_REFRESH" in result["refresh_semantics"]
    assert result["reports"] and result["reports"][0]["content_hash"]
    assert result["schema_version"] == 1
    linkage = result["trend_event_linkage"]
    assert linkage["schema_version"] == 1
    assert set(linkage["allowed_target_kinds"]) == {"TREND", "POTENTIAL_CHANGE", "RISK", "ISSUE", "CLAIM"}
    assert {"report_id", "report_content_hash", "metric"} <= set(linkage["source_anchor_fields"])
    assert linkage["creates_target_records"] is False and linkage["write_back_supported"] is False


def test_reporting_draft_preview_uses_paired_live_sources_without_rewriting_approved_result():
    with TestClient(app) as client, SessionLocal() as db:
        f = create_forecast_fixture(db, client)
        frozen = approved(f)
        candidate = calculate(f, draft(f))
        cost_path = f"/api/v1/cost/projects/{f.project_workspace_id}"
        actual = success(
            request(
                f,
                "POST",
                cost_path + "/actuals",
                payload={
                    **REASON,
                    "source_system": "CONTROLLED_MANUAL",
                    "source_reference": f"PREVIEW-{uuid4()}",
                    "posting_date": "2026-10-22",
                    "recognition_date": "2026-10-22",
                    "period_id": f.period["id"],
                    "amount": "7",
                    "currency": "USD",
                    "cbs_id": f.cost_cbs["id"],
                    "cost_code_id": f.cost_code["id"],
                    "control_account_id": f.cost_account["id"],
                    "evidence_ref": "CONTROLLED-ACTUAL-DOCUMENT",
                },
            ),
            201,
        )
        success(
            request(
                f,
                "POST",
                cost_path + f"/actuals/{actual['id']}/decision",
                actor="manager",
                version=actual["version"],
                payload=REASON,
            )
        )
        preview = success(performance(f, "overview", candidate))
        assert Decimal(preview["metrics"]["actual"]) == 32
        assert actual["id"] in {
            r["id"] for r in preview["source_refs"]["cost_period_snapshot"]["recognized_actual_refs"]
        }
        historical = success(performance(f, "overview", frozen))
        assert Decimal(historical["metrics"]["actual"]) == 25
        assert actual["id"] not in {
            r["id"] for r in historical["source_refs"]["cost_period_snapshot"]["recognized_actual_refs"]
        }


def test_successive_published_periods_preserve_evolving_forecast_evm_and_nonduplicated_actuals(published_fixture):
    f = published_fixture
    original_report = success(report_request(f, "GET", f"/{f.report['id']}"))
    history_count = len(success(report_request(f, "GET", "/history"))["items"])
    first_period = f.period
    f.period = success(
        request(
            f,
            "POST",
            f"/api/v1/operational/projects/{f.project_workspace_id}/periods",
            actor="manager",
            payload={
                **REASON,
                "period_code": "REPORT-NEXT-PERIOD",
                "period_start": "2026-10-26",
                "period_end": "2026-11-01",
                "cutoff_at": "2026-11-01T17:00:00-05:00",
                "timezone": "America/Bogota",
                "schedule_data_date": "2026-10-22",
            },
        ),
        201,
    )
    assert f.period["configuration_id"] == first_period["configuration_id"]
    for kind in ("QUANTITY", "PHYSICAL"):
        approve_progress(
            f,
            success(
                progress_request(
                    f,
                    "POST",
                    "/measurements",
                    payload=measurement_body(
                        f,
                        progress_type=kind,
                        numerator=str(Decimal(f.scope_items[0]["quantity"]) * Decimal("0.75")),
                        measurement_date="2026-10-28",
                        as_of="2026-10-29",
                    ),
                ),
                201,
            ),
        )
    assess_packages(f, as_of="2026-10-29")
    next_evm = success(
        progress_request(
            f,
            "POST",
            "/evm/snapshots",
            actor="manager",
            payload={**REASON, "bundle_id": f.bundle["id"], "period_id": f.period["id"], "as_of": "2026-10-29"},
        ),
        201,
    )
    payload = body(f, as_of="2026-10-29")
    payload["assumptions"][0]["value"] = "85"
    payload["assumptions"][1]["value"] = "2026-12-05"
    payload["cost_items"][0]["inputs"]["phasing"][0]["amount"] = "85"
    candidate = success(request(f, "POST", "/versions", payload=payload), 201)
    next_forecast = approved(f, candidate)
    publish_period(f)
    next_report = success(report_request(f, "POST", actor="second_manager", payload=report_body(next_forecast)), 201)
    assert next_report["bundle_id"] == original_report["bundle_id"]
    assert next_report["period_id"] != original_report["period_id"]
    assert next_report["evm_snapshot_id"] == next_evm["id"]
    assert success(report_request(f, "GET", f"/{original_report['id']}")) == original_report
    trends = success(performance(f, "trends", next_forecast))
    assert len(trends["items"]) == 2
    assert {row["period_id"] for row in trends["items"]} == {first_period["id"], f.period["id"]}
    series = {row["metric"]: row["points"] for row in trends["series"]}
    for name in ("eac", "etc", "vac", "physical_progress", "spi", "cpi", "forecast_finish"):
        assert len(series[name]) == 2
        assert series[name][0]["value"] != series[name][1]["value"], (name, series[name])
        assert all(point["source_hash"] and point["report_id"] for point in series[name])
    assert Decimal(series["eac"][1]["value"]) == 110
    history = success(report_request(f, "GET", "/history"))
    assert len(history["items"]) == history_count + 1
    curves = {row["code"]: row for row in success(performance(f, "curves", next_forecast))["series"]}
    assert Decimal(curves["ACTUAL_COST"]["points"][-1]["cumulative_value"]) == 25
    assert len(curves["APPROVED_ACTUAL_PROGRESS"]["points"]) == 2
    assert Decimal(curves["APPROVED_ACTUAL_PROGRESS"]["points"][-1]["cumulative_value"]) == 75
    assert len(curves["EARNED_VALUE"]["points"]) == 2


def test_reporting_uses_pinned_admin_thresholds_and_selected_series(fixture):
    f = fixture
    original = f.forecast_profile
    profiles = "/api/v1/forecast/admin/profiles"
    successor = success(
        request(
            f,
            "POST",
            f"{profiles}/{original['id']}/successor",
            actor="admin",
            version=original["version"],
            payload=REASON,
        ),
        201,
    )
    content = deepcopy(original["content_json"])
    content["s_curve_series"] = ["FORECAST_COST", "ACTUAL_COST"]
    content["trend_metrics"] = ["eac", "forecast_finish"]
    content["dashboard_thresholds"]["cpi_warning"] = "999999"
    successor = success(
        request(
            f,
            "PUT",
            f"{profiles}/{successor['id']}",
            actor="admin",
            version=successor["version"],
            payload={**REASON, "name": successor["name"], "content_json": content},
        )
    )
    successor = success(
        request(
            f,
            "POST",
            f"{profiles}/{successor['id']}/publish",
            actor="publisher",
            version=successor["version"],
            payload=REASON,
        )
    )
    new = draft(f)
    assert new["configuration_id"] == successor["id"]
    current = success(performance(f, "dashboard", new))
    cpi = next(item for item in current["dashboard_indicators"] if item["metric"] == "cpi")
    assert cpi["status"] == "WARNING" and cpi["threshold"] == "999999"
    assert [item["code"] for item in success(performance(f, "curves", new))["series"]] == content["s_curve_series"]
    assert [item["metric"] for item in success(performance(f, "trends", new))["series"]] == content["trend_metrics"]
    frozen = success(performance(f, "dashboard"))
    assert next(item for item in frozen["dashboard_indicators"] if item["metric"] == "cpi")["threshold"] == "1"
    assert len(success(performance(f, "curves"))["series"]) == 6
