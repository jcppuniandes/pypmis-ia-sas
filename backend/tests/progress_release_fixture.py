"""Explicit disposable Progress prerequisites through real upstream lifecycles."""

import os
from copy import deepcopy
from uuid import uuid4

from tests.cost_release_fixture import account, approved_budget, budget, cbs, cost_code, create_cost_fixture, line
from tests.cost_release_fixture import request as cost_request
from tests.test_schedule_foundation_release import baseline as schedule_baseline
from tests.test_scope_foundation_release import profile, success

from app.modules.awp.permissions import ensure_awp_permissions
from app.modules.awp.policy import DEFAULT_PROFILE as AWP_PROFILE
from app.modules.cost_foundation.permissions import ensure_cost_permissions
from app.modules.cost_foundation.policy import DEFAULT_PROFILE as COST_PROFILE
from app.modules.operational_context.service import DEFAULT_PROFILE as OPERATIONAL_PROFILE
from app.modules.progress_foundation.permissions import ensure_progress_permissions
from app.modules.progress_foundation.policy import DEFAULT_PROFILE
from app.modules.schedule_four_d.permissions import ensure_four_d_permissions
from app.modules.schedule_four_d.service import DEFAULT_PROFILE as FOUR_D_PROFILE

REASON = {"reason": "Isolated governed O1B-D Progress validation"}


def request(f, method, path, *, payload=None, actor="cost_controller", version=None, key=None, params=None):
    headers = dict(f.headers[actor])
    if method != "GET":
        headers["Idempotency-Key"] = key or f"o1bd-{uuid4()}"
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    root = f"/api/v1/progress/projects/{f.project_workspace_id}"
    return f.client.request(
        method, path if path.startswith("/api") else root + path, headers=headers, json=payload, params=params
    )


def create_progress_fixture(
    db, client, *, prepare_integrated=True, publish_profile=True, real_model=False, multi_period_phasing=False
):
    assert db.bind.dialect.name == "postgresql" and (
        (db.bind.url.database in {"o1bd", "o1bd_browser"} and os.getenv("PYPMIS_O1BD_FIXTURE") == "disposable-only")
        or (db.bind.url.database in {"o1c", "o1c_browser"} and os.getenv("PYPMIS_O1C_FIXTURE") == "disposable-only")
    )
    if real_model:
        from tests.awp_browser_fixture import create_awp_browser_fixture

        f = create_awp_browser_fixture(db, client)
        f.db = db
        f.schedule_version = f.current_schedule_version
        for tenant, actor in ((f.tenant_id, f.users["admin"].id), (f.foreign_tenant.id, f.users["foreign"].id)):
            ensure_cost_permissions(db, tenant, actor)
            ensure_awp_permissions(db, tenant, actor)
        db.commit()
        f.cost_profile = profile(f, "/api/v1/cost", COST_PROFILE)
        f.awp_profile = profile(f, "/api/v1/awp", AWP_PROFILE)
        f.period = success(
            request(
                f,
                "POST",
                f"/api/v1/operational/projects/{f.project_workspace_id}/periods",
                actor="manager",
                payload={
                    **REASON,
                    "period_code": "PROGRESS-OCT",
                    "period_start": "2026-10-19",
                    "period_end": "2026-10-25",
                    "cutoff_at": "2026-10-25T17:00:00-05:00",
                    "timezone": "America/Bogota",
                    "schedule_data_date": "2026-10-22",
                },
            ),
            201,
        )
        f.awp_package = success(
            request(
                f,
                "POST",
                f"/api/v1/awp/projects/{f.project_workspace_id}/packages",
                actor="admin",
                payload={
                    **REASON,
                    "package_code": "PROGRESS-IWP",
                    "package_type": "IWP",
                    "name": "Existing installation package",
                },
            ),
            201,
        )
    else:
        operational_policy = None
        if multi_period_phasing:
            operational_policy = deepcopy(OPERATIONAL_PROFILE)
            operational_policy["calendar"]["allow_parallel_active_periods"] = True
        f = create_cost_fixture(db, client, operational_policy=operational_policy)
    for tenant, actor in ((f.tenant_id, f.users["admin"].id), (f.foreign_tenant.id, f.users["foreign"].id)):
        ensure_progress_permissions(db, tenant, actor)
        ensure_four_d_permissions(db, tenant, actor)
    workspace = f.workspaces["direct"]
    workspace.defaults_json = {
        **workspace.defaults_json,
        "enabled_modules": ["scope-manager", "schedule-manager", "awp", "cost", "progress"],
    }
    db.commit()
    f.progress_profile = profile(f, "/api/v1/progress", deepcopy(DEFAULT_PROFILE)) if publish_profile else None
    f.four_d_profile = profile(f, "/api/v1/schedule/4d", FOUR_D_PROFILE)
    if not prepare_integrated:
        return f
    f.schedule_baseline = schedule_baseline(
        f,
        f.schedule_version,
        **({"previous_baseline_id": f.schedule_baseline["id"]} if real_model else {}),
    )
    # Explicit AWP Scope/Plan/Activity links; readiness is not progress.
    f.packages = []
    for index, scope in enumerate(f.scope_items if real_model else f.scope_items[:1]):
        plan = f.plan_items[min(index, len(f.plan_items) - 1)]
        package = (
            f.awp_package
            if index == 0
            else success(
                request(
                    f,
                    "POST",
                    f"/api/v1/awp/projects/{f.project_workspace_id}/packages",
                    actor="admin",
                    payload={
                        **REASON,
                        "package_code": f"PROGRESS-{scope['scope_nature']}",
                        "package_type": ["IWP", "CWP", "SUPPORT", "EWP"][index],
                        "name": scope["name"],
                    },
                ),
                201,
            )
        )
        activities = [
            a
            for a in f.schedule_version["snapshot_json"]["activities"]
            if not real_model or f.activity_plans.get(a["external_id"]) == plan["id"]
        ]
        links = [{"target_kind": "SCOPE", "target_id": scope["id"]}, {"target_kind": "PLAN", "target_id": plan["id"]}]
        links.extend(
            {
                "target_kind": "ACTIVITY",
                "schedule_version_id": f.schedule_version["id"],
                "activity_external_id": a["external_id"],
                "phase": f.activity_phases[a["external_id"]] if real_model else "EXECUTE",
            }
            for a in activities
        )
        for link in links:
            package = success(
                request(
                    f,
                    "POST",
                    f"/api/v1/awp/projects/{f.project_workspace_id}/packages/{package['id']}/mappings",
                    actor="admin",
                    version=package["version"],
                    payload={**REASON, **link},
                ),
                201,
            )["package"]
        f.packages.append(package)
    f.awp_package = f.packages[0]
    f.cost_cbs, f.cost_code, f.cost_account = cbs(f), cost_code(f), account(f)
    f.cost_mappings = []
    scope, plan = f.scope_items[0], f.plan_items[0]
    allocation = next(a for a in plan["allocations"] if a["scope_item_id"] == scope["id"])
    for source in (
        {"source_kind": "SCOPE", "source_id": scope["id"], "quantity": scope["quantity"]},
        {"source_kind": "PLAN", "source_id": plan["id"], "quantity": allocation["quantity"]},
        {"source_kind": "PACKAGE", "source_id": f.awp_package["id"], "quantity": scope["quantity"]},
        {
            "source_kind": "ACTIVITY",
            "schedule_version_id": f.schedule_version["id"],
            "source_external_id": f.schedule_version["snapshot_json"]["activities"][0]["external_id"],
            "quantity": scope["quantity"],
        },
    ):
        f.cost_mappings.append(
            success(
                cost_request(
                    f,
                    "POST",
                    "/mappings",
                    payload={
                        **REASON,
                        "cbs_id": f.cost_cbs["id"],
                        "cost_code_id": f.cost_code["id"],
                        "control_account_id": f.cost_account["id"],
                        "allocation_basis": "QUANTITY",
                        "quantity_basis": "APPROVED_SCOPE_OR_ALLOCATED_PLAN",
                        "unit": scope["unit"],
                        "effective_revision": str(f.scope_baseline["id"]),
                        "source_reference": "GOVERNED_UPSTREAM_PROGRESS_BASIS",
                        **source,
                    },
                ),
                201,
            )
        )
    candidate = budget(f)
    candidate = line(
        f,
        candidate,
        line_code="PROGRESS-CONTROL",
        quantity=scope["quantity"],
        unit=scope["unit"],
        rate="100",
        cbs_id=f.cost_cbs["id"],
        cost_code_id=f.cost_code["id"],
        control_account_id=f.cost_account["id"],
        scope_item_id=scope["id"],
        work_package_id=f.awp_package["id"],
        **({"plan_item_id": plan["id"]} if real_model else {}),
    )["budget_version"]
    if multi_period_phasing:
        f.next_period = success(
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
        candidate = line(
            f,
            candidate,
            line_code="PROGRESS-CONTROL-NEXT",
            quantity=scope["quantity"],
            unit=scope["unit"],
            rate="100",
            cbs_id=f.cost_cbs["id"],
            cost_code_id=f.cost_code["id"],
            control_account_id=f.cost_account["id"],
            scope_item_id=scope["id"],
            work_package_id=f.awp_package["id"],
        )["budget_version"]
    f.cost_budget = approved_budget(f, row=candidate)
    candidate = success(
        cost_request(
            f,
            "POST",
            "/baselines",
            payload={**REASON, "code": "PROGRESS-COST-BL", "budget_version_id": f.cost_budget["id"]},
        ),
        201,
    )
    for index, budget_line in enumerate(f.cost_budget["snapshot_json"]["lines"]):
        phase_period = f.next_period if multi_period_phasing and index == 1 else f.period
        phased = success(
            cost_request(
                f,
                "POST",
                f"/baselines/{candidate['id']}/phase",
                version=candidate["version"],
                payload={
                    **REASON,
                    "budget_line_id": budget_line["id"],
                    "method": "LINEAR",
                    "start_date": phase_period["period_start"],
                    "finish_date": phase_period["period_end"],
                    "period_id": phase_period["id"],
                },
            ),
            201,
        )
        candidate = phased["baseline"]
    f.cost_baseline = success(
        cost_request(
            f,
            "POST",
            f"/baselines/{candidate['id']}/approve",
            actor="manager",
            version=candidate["version"],
            payload=REASON,
        )
    )
    actual = success(
        cost_request(
            f,
            "POST",
            "/actuals",
            payload={
                **REASON,
                "source_system": "CONTROLLED_MANUAL",
                "source_reference": f"PROGRESS-AC-{uuid4()}",
                "posting_date": "2026-10-21",
                "recognition_date": "2026-10-22",
                "period_id": f.period["id"],
                "amount": "25",
                "currency": "USD",
                "cbs_id": f.cost_cbs["id"],
                "cost_code_id": f.cost_code["id"],
                "control_account_id": f.cost_account["id"],
                "evidence_ref": "RECOGNIZED_ACTUAL_SOURCE_DOCUMENT",
            },
        ),
        201,
    )
    f.cost_actual = success(
        cost_request(
            f, "POST", f"/actuals/{actual['id']}/decision", actor="manager", version=actual["version"], payload=REASON
        )
    )
    return f
