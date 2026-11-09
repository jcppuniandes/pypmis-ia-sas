"""Disposable Forecast prerequisites through real upstream APIs and approvals."""

import os
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

from tests.progress_release_fixture import create_progress_fixture
from tests.progress_release_fixture import request as progress_request
from tests.test_progress_foundation_release import approve, measurement_body
from tests.test_progress_integration_release import _approved_bundle
from tests.test_scope_foundation_release import success

from app.modules.forecast_foundation.permissions import ensure_forecast_permissions
from app.modules.forecast_foundation.policy import DEFAULT_PROFILE

REASON = {"reason": "Isolated governed O1C Forecast and reporting validation"}


def publish_profile(f):
    row = success(
        request(
            f,
            "POST",
            "/api/v1/forecast/admin/profiles",
            actor="admin",
            payload={
                **REASON,
                "code": f"O1C-{uuid4().hex[:10]}",
                "name": "Governed isolated Forecast policy",
                "content_json": deepcopy(DEFAULT_PROFILE),
            },
        ),
        201,
    )
    return success(
        request(
            f,
            "POST",
            f"/api/v1/forecast/admin/profiles/{row['id']}/publish",
            actor="publisher",
            version=row["version"],
            payload=REASON,
        )
    )


def request(f, method, path, *, payload=None, actor="cost_controller", version=None, key=None, params=None):
    headers = dict(f.headers[actor])
    if method != "GET":
        headers["Idempotency-Key"] = key or f"o1c-{uuid4()}"
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    base = f"/api/v1/forecast/projects/{f.project_workspace_id}"
    return f.client.request(
        method, path if path.startswith("/api") else base + path, headers=headers, json=payload, params=params
    )


def create_forecast_fixture(db, client, *, real_model=False, publish_forecast_policy=True):
    assert db.bind.dialect.name == "postgresql" and db.bind.url.database in {"o1c", "o1c_browser"}
    assert os.getenv("PYPMIS_O1C_FIXTURE") == "disposable-only"
    f = create_progress_fixture(db, client, real_model=real_model)
    f.db = db
    for tenant, actor in ((f.tenant_id, f.users["admin"].id), (f.foreign_tenant.id, f.users["foreign"].id)):
        ensure_forecast_permissions(db, tenant, actor)
    workspace = f.workspaces["direct"]
    workspace.defaults_json = {
        **workspace.defaults_json,
        "enabled_modules": ["scope-manager", "schedule-manager", "awp", "cost", "progress", "forecast"],
    }
    db.commit()
    f.forecast_profile = publish_profile(f) if publish_forecast_policy else None
    scope = f.scope_items[0]
    f.approved_quantity_progress = approve(
        f,
        success(
            progress_request(
                f, "POST", "/measurements", payload=measurement_body(f, numerator=str(Decimal(scope["quantity"]) / 2))
            ),
            201,
        ),
    )
    physical = measurement_body(
        f,
        code=f"FORECAST-PHYS-{uuid4().hex[:8]}",
        progress_type="PHYSICAL",
        numerator=str(Decimal(scope["quantity"]) / 2),
    )
    f.approved_physical_progress = approve(
        f, success(progress_request(f, "POST", "/measurements", payload=physical), 201)
    )
    f.bundle = _approved_bundle(f)
    f.evm_snapshot = success(
        progress_request(
            f,
            "POST",
            "/evm/snapshots",
            actor="manager",
            payload={**REASON, "bundle_id": f.bundle["id"], "period_id": f.period["id"], "as_of": "2026-10-22"},
        ),
        201,
    )
    return f


def assumption(f, code, value, unit, *, kind="AMOUNT", currency="USD", **changes):
    return {
        "code": code,
        "name": f"Governed {code}",
        "kind": kind,
        "value": str(value),
        "unit": unit,
        "currency": currency,
        "source_reference": f"FIELD-REVIEW-{code}",
        "owner_id": f.users["cost_controller"].id,
        "effective_date": "2026-10-22",
        "confidence": "MEDIUM",
        "status": "CONFIRMED",
        "evidence_ref": f"SOURCE-DOCUMENT-{code}",
        "rationale": "Independent source basis reviewed by the named owner",
        **changes,
    }


def component(f, code, method="MANUAL_GOVERNED", **changes):
    return {
        "code": code,
        "name": f"Projected {code}",
        "method": method,
        "scope_item_id": f.scope_items[0]["id"],
        "control_account_id": f.cost_account["id"],
        "cbs_id": f.cost_cbs["id"],
        "cost_code_id": f.cost_code["id"],
        "currency": "USD",
        "unit": f.scope_items[0]["unit"],
        "assumption_codes": ["REMAINING-COST"],
        "inputs": {
            "amount_assumption_code": "REMAINING-COST",
            "cost_bucket": "UNCOMMITTED",
            "phasing": [{"date": "2026-11-01", "amount": "75", "currency": "USD"}],
        },
        **changes,
    }


def body(f, **changes):
    return {
        **REASON,
        "code": f"FC-{uuid4().hex[:10]}",
        "name": "Governed projection distinct from Current and Baseline",
        "bundle_id": f.bundle["id"],
        "period_id": f.period["id"],
        "as_of": "2026-10-22",
        "schedule_version_id": f.schedule_version["id"],
        "currency": "USD",
        "method": "BOTTOM_UP",
        "confidence": "MEDIUM",
        "confidence_rationale": "Owner corroboration with independent projection review",
        "data_completeness": "OWNER_REVIEWED_DECLARED_BASIS",
        "assumption_maturity": "OWNER_CONFIRMED_SOURCE_REFERENCES",
        "evidence_ref": "GOVERNED-FORECAST-REVIEW-DOCUMENT",
        "assumptions": [
            assumption(f, "REMAINING-COST", "75", "USD"),
            assumption(f, "EXPECTED-FINISH", "2026-11-20", "date", kind="FORECAST_DATE", currency=None),
        ],
        "cost_items": [component(f, "REMAINING-WORK")],
        "time_items": [
            component(
                f,
                "PROJECT-FINISH",
                method="MANUAL_GOVERNED",
                activity_external_id=f.schedule_version["snapshot_json"]["activities"][0]["external_id"],
                assumption_codes=["EXPECTED-FINISH"],
                inputs={"date_assumption_code": "EXPECTED-FINISH"},
            )
        ],
        "milestones": [],
        "resource_items": [],
        **changes,
    }


def draft(f, **changes):
    return success(request(f, "POST", "/versions", payload=body(f, **changes)), 201)


def calculate(f, row, *, actor="cost_controller"):
    return success(
        request(f, "POST", f"/versions/{row['id']}/calculate", actor=actor, version=row["version"], payload=REASON)
    )


def approved(f, row=None):
    row = calculate(f, row or draft(f))
    for action, actor in (("review", "cost_controller"), ("approve", "manager")):
        row = success(
            request(
                f,
                "POST",
                f"/versions/{row['id']}/transition",
                actor=actor,
                version=row["version"],
                payload={**REASON, "action": action},
            )
        )
    return row
