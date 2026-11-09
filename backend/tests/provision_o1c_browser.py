"""Persist disposable O1C real sources; never use the normal application database."""

import argparse
import json
import os
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from tests.forecast_release_fixture import REASON, assumption, body, component, create_forecast_fixture, request
from tests.progress_release_fixture import request as progress_request
from tests.test_schedule_foundation_release import accept, version
from tests.test_schedule_foundation_release import request as schedule_request
from tests.test_scope_foundation_release import success

from app.core.security import hash_password
from app.database.session import SessionLocal, engine
from app.domain.models import AuthCredential, ProjectMembership
from app.main import app
from app.modules.awp.policy import DIMENSIONS


def larger_current(f):
    """A real accepted successor with 36 activities, leaving the bundle baseline intact."""
    register = success(schedule_request(f, "GET", f"/registers/{f.schedule_register['id']}"))
    content = deepcopy(f.schedule_version["snapshot_json"])
    template = deepcopy(content["activities"][0])
    assignments = dict(f.activity_plans)
    for index in range(30):
        activity = deepcopy(template)
        identity = str(6000 + index)
        start = date(2026, 10, 23) + timedelta(days=index)
        activity.update(
            external_id=identity,
            code=f"O1C-{index + 1:02}",
            name=f"O1C larger imported work {index + 1}",
            planned_start=f"{start.isoformat()}T07:00:00",
            planned_finish=f"{(start + timedelta(days=2)).isoformat()}T17:00:00",
            total_float=0 if index % 7 == 0 else 24 if index % 3 == 0 else 80,
            critical=index % 7 == 0,
            source_fields={},
        )
        content["activities"].append(activity)
        assignments[identity] = f.plan_items[index % len(f.plan_items)]["id"]
    row = version(f, register, content=content, predecessor=f.schedule_version["id"], kind="UPDATE")
    for activity in row["snapshot_json"]["activities"]:
        row = success(
            schedule_request(
                f,
                "POST",
                f"/versions/{row['id']}/mappings",
                version=row["version"],
                payload={
                    **REASON,
                    "target_kind": "ACTIVITY",
                    "target_external_id": activity["external_id"],
                    "plan_item_ids": [assignments[activity["external_id"]]],
                },
            ),
            201,
        )["schedule_version"]
    f.schedule_version = accept(f, row)
    f.activity_plans = assignments
    assert f.schedule_version["id"] != f.bundle["source_snapshot_json"]["schedule_baseline"]["schedule_version_id"]


def current_readiness_sources(f):
    """Add actual constraints and assessments, retaining the baseline package mappings."""
    base = f"/api/v1/awp/projects/{f.project_workspace_id}"
    # Current Schedule's explicit activity-to-Plan/Scope mappings provide
    # read-side AWP context; they do not authorize new execution mappings.
    first_package = f.packages[0]
    constraint = success(
        request(
            f,
            "POST",
            base + "/constraints",
            actor="admin",
            payload={
                **REASON,
                "code": "O1C-OPEN-ACCESS",
                "constraint_type": "ACCESS",
                "title": "Controlled access condition remains explicitly open",
                "blocking": True,
                "owner_user_id": f.users["planner"].id,
                "due_date": "2026-10-24",
                "source_domain": "O1C_ISOLATED_UAT",
                "source_reference": "FIELD-ACCESS-SOURCE",
                "evidence_reference": "DISPOSABLE-ACCESS-INSPECTION",
            },
        ),
        201,
    )
    for mapping in (
        {"target_kind": "PACKAGE", "target_id": first_package["id"]},
        {"target_kind": "ACTIVITY", "schedule_version_id": f.schedule_version["id"], "activity_external_id": "5001"},
    ):
        constraint = success(
            request(
                f,
                "POST",
                base + f"/constraints/{constraint['id']}/mappings",
                actor="admin",
                version=constraint["version"],
                payload={**REASON, **mapping},
            ),
            201,
        )["constraint"]
    assessed_packages = []
    for package in f.packages:
        assessed = success(
            request(
                f,
                "POST",
                base + f"/packages/{package['id']}/assess",
                actor="admin",
                version=package["version"],
                payload={
                    **REASON,
                    "as_of": "2026-10-22",
                    "evidence_json": dict.fromkeys(DIMENSIONS, "O1C-SOURCE-REVIEW"),
                },
            ),
            201,
        )
        assessed_packages.append(assessed["package"])
    f.packages = assessed_packages
    f.open_constraint = constraint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--larger-current", action="store_true")
    args = parser.parse_args()
    assert os.getenv("PYPMIS_O1C_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database == "o1c_browser"
    target = Path(args.output).resolve()
    assert not target.exists(), "Reuse the already persisted isolated actors"
    with TestClient(app) as client, SessionLocal() as db:
        f = create_forecast_fixture(db, client, real_model=True, publish_forecast_policy=False)
        mapping_path = f"/api/v1/awp/projects/{f.project_workspace_id}/mappings"
        baseline_mappings = success(request(f, "GET", mapping_path, actor="admin"))
        if args.larger_current:
            larger_current(f)
        current_readiness_sources(f)
        assert success(request(f, "GET", mapping_path, actor="admin")) == baseline_mappings
        bundle_validation = success(progress_request(f, "GET", f"/baseline-bundles/{f.bundle['id']}/validate"))
        assert bundle_validation["effective_state"] == "APPROVED", bundle_validation["reason_codes"]
        assert bundle_validation["current_hash"] == bundle_validation["frozen_hash"] == f.bundle["content_hash"]
        password = "O1c-disposable-only!"
        for label, user in f.users.items():
            db.add(
                AuthCredential(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    provider="local",
                    password_hash=hash_password(password),
                    is_active=True,
                )
            )
            if label != "foreign":
                db.add(
                    ProjectMembership(
                        tenant_id=f.tenant_id,
                        project_id=f.legacy_project_id,
                        user_id=user.id,
                        role="Control Manager" if label in {"admin", "publisher"} else "Executive Viewer",
                        can_configure=label in {"admin", "publisher"},
                        can_capture_progress=False,
                        can_capture_cost=False,
                    )
                )
        db.commit()
        forecast_payload = body(f)
        unit = f.scope_items[0]["unit"]
        forecast_payload["assumptions"] = [
            assumption(f, "RATE", "100", f"USD/{unit}", kind="RATE"),
            assumption(f, "EXPECTED-FINISH", "2026-11-20", "date", kind="FORECAST_DATE", currency=None),
            assumption(f, "PRODUCTIVITY", "0.2", f"{unit}/day", kind="PRODUCTIVITY", currency=None),
            assumption(f, "CREW", "2", "person", kind="CREW", currency=None),
        ]
        forecast_payload["cost_items"] = [
            component(
                f,
                "QUANTITY-ETC",
                method="QUANTITY_RATE",
                assumption_codes=["RATE"],
                inputs={
                    "rate_assumption_code": "RATE",
                    "cost_bucket": "UNCOMMITTED",
                    "phasing": [{"date": "2026-11-01", "amount": "60"}],
                },
            )
        ]
        forecast_payload["time_items"] = [
            component(
                f,
                "P6-ACCEPTED-FINISH",
                method="ACTIVITY_REMAINING_DURATION",
                assumption_codes=[],
                activity_external_id="5001",
                inputs={},
            )
        ]
        forecast_payload["milestones"] = [
            component(
                f,
                "HANDOVER-FORECAST",
                method="MANUAL_GOVERNED",
                assumption_codes=["EXPECTED-FINISH"],
                inputs={"date_assumption_code": "EXPECTED-FINISH", "milestone_type": "HANDOVER"},
            )
        ]
        forecast_payload["resource_items"] = [
            component(
                f,
                "REMAINING-CREW",
                method="PRODUCTIVITY_BASED",
                assumption_codes=["PRODUCTIVITY", "CREW"],
                inputs={
                    "productivity_assumption_code": "PRODUCTIVITY",
                    "productivity_basis": "QUANTITY_PER_DAY",
                    "crew_assumption_code": "CREW",
                    "resource_type": "LABOR",
                },
            )
        ]
        result = {
            "tenant_id": f.tenant_id,
            "project_workspace_id": f.project_workspace_id,
            "legacy_project_id": f.legacy_project_id,
            "password": password,
            "users": {
                label: {"id": user.id, "email": user.email, "tenant_id": user.tenant_id}
                for label, user in f.users.items()
            },
            "bundle_id": f.bundle["id"],
            "forecast_payload": forecast_payload,
            "period_id": f.period["id"],
            "schedule_version_id": f.schedule_version["id"],
            "scope_item_id": f.scope_items[0]["id"],
            "as_of": "2026-10-22",
            "scope_items": f.scope_items,
            "plan_items": f.plan_items,
            "packages": f.packages,
            "open_constraint": f.open_constraint,
            "period": f.period,
            "bundle": f.bundle,
            "schedule_version": f.schedule_version,
            "cost_account": f.cost_account,
            "cost_baseline": f.cost_baseline,
            "cost_actual": f.cost_actual,
            "model": f.model,
            "fixture_scope": "Disposable isolated real IFC/P6 sources and approvals; no business acceptance.",
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "fixture_created": True,
                    "tenant_id": f.tenant_id,
                    "project_workspace_id": f.project_workspace_id,
                    "output": str(target),
                }
            )
        )


if __name__ == "__main__":
    main()
