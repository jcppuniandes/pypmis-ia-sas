"""Disposable-only real upstream Scope/Schedule/AWP and Cost policy lifecycles."""

import os
from copy import deepcopy
from uuid import uuid4

from tests.schedule_release_fixture import create_schedule_fixture
from tests.test_schedule_foundation_release import accept, map_all, register, version
from tests.test_scope_foundation_release import profile, success

from app.modules.awp.permissions import ensure_awp_permissions
from app.modules.awp.policy import DEFAULT_PROFILE as AWP_PROFILE
from app.modules.cost_foundation.permissions import ensure_cost_permissions
from app.modules.cost_foundation.policy import DEFAULT_PROFILE
from app.modules.schedule_foundation.service import DEFAULT_PROFILE as SCHEDULE_PROFILE

REASON = {"reason": "Isolated governed O1B-C Cost validation"}


def request(f, method, path, *, payload=None, actor="cost_controller", version=None, key=None):
    headers = dict(f.headers[actor])
    if method != "GET":
        headers["Idempotency-Key"] = key or f"o1bc-{uuid4()}"
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    root = f"/api/v1/cost/projects/{f.project_workspace_id}"
    return f.client.request(method, path if path.startswith("/api") else root + path, headers=headers, json=payload)


def create_cost_fixture(db, client):
    assert (
        db.bind.dialect.name == "postgresql"
        and db.bind.url.database in {"o1bc", "o1bc_browser"}
        and os.getenv("PYPMIS_O1BC_FIXTURE") == "disposable-only"
    )
    f = create_schedule_fixture(db, client)
    f.db = db
    for tenant, actor in ((f.tenant_id, f.users["admin"].id), (f.foreign_tenant.id, f.users["foreign"].id)):
        ensure_cost_permissions(db, tenant, actor)
        ensure_awp_permissions(db, tenant, actor)
    workspace = f.workspaces["direct"]
    workspace.defaults_json = {
        **workspace.defaults_json,
        "enabled_modules": ["scope-manager", "schedule-manager", "awp", "cost-manager"],
    }
    db.commit()
    schedule_policy = deepcopy(SCHEDULE_PROFILE)
    schedule_policy["quality_thresholds"]["external_links"] = "WARN"
    f.schedule_profile = profile(f, "/api/v1/schedule", schedule_policy)
    f.cost_profile = profile(f, "/api/v1/cost", DEFAULT_PROFILE)
    f.awp_profile = profile(f, "/api/v1/awp", AWP_PROFILE)
    f.schedule_register = register(f)
    f.schedule_version = accept(f, map_all(f, version(f, f.schedule_register)))
    f.awp_package = success(
        request(
            f,
            "POST",
            f"/api/v1/awp/projects/{f.project_workspace_id}/packages",
            actor="admin",
            payload={
                **REASON,
                "package_code": "COST-IWP",
                "package_type": "IWP",
                "name": "Existing real AWP Cost package",
            },
        ),
        201,
    )
    f.period = success(
        request(
            f,
            "POST",
            f"/api/v1/operational/projects/{f.project_workspace_id}/periods",
            actor="manager",
            payload={
                **REASON,
                "period_code": "COST-OCT",
                "period_start": "2026-10-19",
                "period_end": "2026-10-25",
                "cutoff_at": "2026-10-25T17:00:00-05:00",
                "timezone": "America/Bogota",
            },
        ),
        201,
    )
    return f


def cbs(f, **changes):
    return success(
        request(
            f, "POST", "/cbs", payload={**REASON, "code": f"CBS-{uuid4().hex[:8]}", "name": "Governed CBS", **changes}
        ),
        201,
    )


def cost_code(f, **changes):
    return success(
        request(
            f,
            "POST",
            "/cost-codes",
            payload={
                **REASON,
                "code": f"CC-{uuid4().hex[:8]}",
                "name": "Labor cost code",
                "category": "LABOR",
                **changes,
            },
        ),
        201,
    )


def account(f, **changes):
    return success(
        request(
            f,
            "POST",
            "/control-accounts",
            payload={
                **REASON,
                "code": f"CA-{uuid4().hex[:8]}",
                "name": "Integrated responsibility",
                "owner_user_id": f.users["manager"].id,
                "responsible_role": "Project Controls",
                **changes,
            },
        ),
        201,
    )


def rate(f, *, publish=True, **changes):
    row = success(
        request(
            f,
            "POST",
            "/rates",
            payload={
                **REASON,
                "code": f"RATE-{uuid4().hex[:8]}",
                "name": "Labor rate",
                "resource_type": "LABOR",
                "unit": "h",
                "amount": "10.25",
                "currency": "USD",
                "effective_from": "2026-01-01",
                "source_reference": "AUTHORIZED_SUPPLIER_QUOTATION",
                **changes,
            },
        ),
        201,
    )
    return (
        success(
            request(f, "POST", f"/rates/{row['id']}/publish", actor="manager", version=row["version"], payload=REASON)
        )
        if publish
        else row
    )


def apu(f, *, publish=True, rates=None, **changes):
    rates = rates or [rate(f)]
    row = success(
        request(
            f,
            "POST",
            "/apus",
            payload={
                **REASON,
                "code": f"APU-{uuid4().hex[:8]}",
                "name": "Governed build-up",
                "unit": "m3",
                "currency": "USD",
                "effective_from": "2026-01-01",
                "source_reference": "APPROVED_COST_BUILD_UP",
                "components": [
                    {"rate_id": r["id"], "category": r["resource_type"], "quantity_per_unit": "2", "unit": r["unit"]}
                    for r in rates
                ],
                **changes,
            },
        ),
        201,
    )
    return (
        success(
            request(f, "POST", f"/apus/{row['id']}/publish", actor="manager", version=row["version"], payload=REASON)
        )
        if publish
        else row
    )


def budget(f, **changes):
    return success(
        request(
            f,
            "POST",
            "/budgets",
            payload={
                **REASON,
                "code": f"BUD-{uuid4().hex[:8]}",
                "name": "Controlled budget",
                "currency": "USD",
                "source_references": {"pricing_date": "2026-10-22"},
                **changes,
            },
        ),
        201,
    )


def line(f, row, **changes):
    return success(
        request(
            f,
            "POST",
            f"/budgets/{row['id']}/lines",
            version=row["version"],
            payload={
                **REASON,
                "line_code": f"L-{uuid4().hex[:8]}",
                "description": "Explicit Cost candidate",
                "quantity": "10",
                "unit": "m3",
                "rate": "20.50",
                "currency": "USD",
                **changes,
            },
        ),
        201,
    )


def approved_budget(f, *, row=None):
    row = row or budget(f)
    if not [r for r in success(request(f, "GET", "/budget-lines"))["items"] if r["budget_version_id"] == row["id"]]:
        row = line(f, row)["budget_version"]
    for status, actor in (("SUBMITTED", "cost_controller"), ("UNDER_REVIEW", "manager"), ("APPROVED", "manager")):
        row = success(
            request(
                f,
                "POST",
                f"/budgets/{row['id']}/transition",
                actor=actor,
                version=row["version"],
                payload={**REASON, "status": status},
            )
        )
    return row
