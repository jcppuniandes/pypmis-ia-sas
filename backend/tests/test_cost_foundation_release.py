"""Real PostgreSQL/HTTP Cost foundation, immutability and authority contracts."""

import os
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from tests.cost_release_fixture import (
    REASON,
    account,
    approved_budget,
    apu,
    budget,
    cbs,
    cost_code,
    create_cost_fixture,
    line,
    rate,
    request,
)
from tests.test_scope_foundation_release import success

from app.database.session import SessionLocal, engine
from app.main import app


@pytest.fixture(scope="module")
def fixture():
    assert (
        engine.dialect.name == "postgresql"
        and engine.url.database == "o1bc"
        and os.getenv("PYPMIS_O1BC_FIXTURE") == "disposable-only"
    )
    with TestClient(app) as client, SessionLocal() as db:
        yield create_cost_fixture(db, client)
        db.rollback()


def _budget(f):
    rows = success(request(f, "GET", "/budgets"))["items"]
    approved = [r for r in rows if r["status"] == "APPROVED"]
    replaced = {r["predecessor_id"] for r in approved}
    current = next((r for r in approved if r["id"] not in replaced), None)
    return budget(f, **({"budget_type": "CURRENT", "predecessor_id": current["id"]} if current else {}))


def _approved(f):
    return approved_budget(f, row=_budget(f))


def test_cbs_hierarchy_cycle_and_etag(fixture):
    f = fixture
    parent = cbs(f)
    child = cbs(f, parent_id=parent["id"])
    assert child["level"] == 2 and child["path"] == parent["code"] + "/" + child["code"]
    body = {**REASON, "code": parent["code"], "name": parent["name"], "parent_id": child["id"]}
    assert request(f, "PUT", f"/cbs/{parent['id']}", version=parent["version"], payload=body).status_code == 422
    assert (
        request(
            f,
            "PUT",
            f"/cbs/{child['id']}",
            version=99,
            payload={**body, "code": child["code"], "parent_id": parent["id"]},
        ).status_code
        == 412
    )


def test_cbs_idempotency_conflict(fixture):
    body = {**REASON, "code": f"IDEM-{uuid4()}", "name": "Idempotent Cost tree"}
    key = str(uuid4())
    first = success(request(fixture, "POST", "/cbs", payload=body, key=key), 201)
    assert success(request(fixture, "POST", "/cbs", payload=body, key=key), 201) == first
    assert request(fixture, "POST", "/cbs", payload={**body, "name": "Different"}, key=key).status_code == 409


@pytest.mark.parametrize("actor", ["executive", "planner", "unassigned", "foreign"])
def test_cbs_denies_non_cost_duties(fixture, actor):
    response = request(
        fixture, "POST", "/cbs", actor=actor, payload={**REASON, "code": f"DENY-{uuid4()}", "name": "Must not write"}
    )
    assert response.status_code in {403, 404}


def test_cost_code_and_control_account_independent_from_wbs_funding(fixture):
    code, ca = cost_code(fixture), account(fixture)
    assert code["category"] == "LABOR" and "wbs_id" not in code and "fbs_id" not in code
    assert ca["owner_user_id"] == fixture.users["manager"].id and "wbs_id" not in ca
    assert (
        request(
            fixture,
            "POST",
            "/control-accounts",
            payload={
                **REASON,
                "code": f"BAD-{uuid4()}",
                "name": "Cross tenant",
                "owner_user_id": fixture.users["foreign"].id,
                "responsible_role": "Controls",
            },
        ).status_code
        == 422
    )


@pytest.mark.parametrize("kind", ["SCOPE", "PLAN", "PACKAGE", "WBS", "ACTIVITY"])
def test_explicit_m_to_n_sources_and_history(fixture, kind):
    f = fixture
    target = cbs(f)
    code = cost_code(f)
    source = {"source_kind": kind}
    if kind in {"SCOPE", "PLAN", "PACKAGE"}:
        source["source_id"] = {
            "SCOPE": f.scope_items[0]["id"],
            "PLAN": f.plan_items[0]["id"],
            "PACKAGE": f.awp_package["id"],
        }[kind]
    else:
        source.update(
            schedule_version_id=f.schedule_version["id"],
            source_external_id=f.schedule_version["snapshot_json"]["wbs" if kind == "WBS" else "activities"][0][
                "external_id"
            ],
        )
    body = {
        **REASON,
        **source,
        "cbs_id": target["id"],
        "allocation_basis": "PERCENTAGE",
        "quantity_basis": "EXPLICIT_COST_ALLOCATION_NOT_SCOPE_REDEFINITION",
        "percentage": "60",
        "effective_revision": "1",
        "source_reference": "CONTROLLED_MAPPING",
    }
    first = success(request(f, "POST", "/mappings", payload=body), 201)
    second = success(
        request(
            f, "POST", "/mappings", payload={**body, "cbs_id": None, "cost_code_id": code["id"], "percentage": "40"}
        ),
        201,
    )
    assert first["id"] != second["id"] and first["source_snapshot"]
    revised = success(
        request(
            f,
            "POST",
            f"/mappings/{first['id']}/successor",
            version=first["version"],
            payload={**body, "percentage": "55"},
        ),
        201,
    )
    assert revised["supersedes_id"] == first["id"]
    old = success(request(f, "GET", f"/mappings/{first['id']}"))
    assert Decimal(old["percentage"]) == Decimal(first["percentage"])
    assert success(request(f, "GET", f"/history/CostMapping/{revised['id']}"))["total"] == 1


def test_mapping_project_isolation(fixture):
    f = fixture
    target = cbs(f)
    body = {
        **REASON,
        "source_kind": "SCOPE",
        "source_id": f.scope_items[0]["id"],
        "cbs_id": target["id"],
        "allocation_basis": "QUANTITY",
        "quantity_basis": "APPROVED_SCOPE",
        "effective_revision": "1",
        "source_reference": "SCOPE",
    }
    response = request(
        f, "POST", f"/api/v1/cost/projects/{f.workspaces['other_project'].id}/mappings", actor="admin", payload=body
    )
    assert response.status_code in {404, 409}


@pytest.mark.parametrize("resource", ["LABOR", "MATERIAL", "EQUIPMENT", "SUBCONTRACT", "OTHER"])
def test_effective_rates_and_apu_component_categories(fixture, resource):
    f = fixture
    r = rate(f, resource_type=resource)
    result = apu(f, rates=[r])
    assert result["status"] == "PUBLISHED" and result["components_json"][0]["category"] == resource
    assert result["unit_amount"] == "20.50000000"


def test_rate_apu_publication_independent_actor_and_history(fixture):
    f = fixture
    draft = rate(f, publish=False)
    assert (
        request(
            f,
            "POST",
            f"/rates/{draft['id']}/publish",
            actor="cost_controller",
            version=draft["version"],
            payload=REASON,
        ).status_code
        == 403
    )
    published = success(
        request(f, "POST", f"/rates/{draft['id']}/publish", actor="manager", version=draft["version"], payload=REASON)
    )
    successor = rate(
        f,
        publish=False,
        code=published["code"],
        supersedes_id=published["id"],
        effective_from="2027-01-01",
        amount="15",
    )
    assert successor["revision"] == 2 and Decimal(successor["amount"]) == Decimal("15")
    assert success(request(f, "GET", f"/rates/{published['id']}"))["amount"] == published["amount"]
    candidate = apu(f, publish=False)
    assert (
        request(
            f, "POST", f"/apus/{candidate['id']}/publish", actor="admin", version=candidate["version"], payload=REASON
        ).status_code
        == 200
    )


def test_apu_rejects_unit_and_currency_incompatibility(fixture):
    f = fixture
    r = rate(f)
    body = {
        **REASON,
        "code": f"APU-{uuid4()}",
        "name": "Invalid unit",
        "unit": "m3",
        "currency": "USD",
        "effective_from": "2026-01-01",
        "source_reference": "COST",
        "components": [{"rate_id": r["id"], "category": "LABOR", "quantity_per_unit": 1, "unit": "kg"}],
    }
    assert request(f, "POST", "/apus", payload=body).status_code == 422
    body.update(currency="COP")
    body["components"][0]["unit"] = "h"
    assert request(f, "POST", "/apus", payload=body).status_code == 409


def test_scope_times_apu_candidate_only_preserves_quantity(fixture):
    f = fixture
    row, unit_price = _budget(f), apu(f)
    before = deepcopy(f.scope_items[0])
    candidate = success(
        request(
            f,
            "POST",
            f"/budgets/{row['id']}/candidate-from-scope",
            version=row["version"],
            payload={**REASON, "scope_item_id": before["id"], "apu_id": unit_price["id"], "line_code": "SCOPE-X-APU"},
        ),
        201,
    )
    assert candidate["candidate_only"] and candidate["budget_version"]["status"] == "DRAFT"
    assert candidate["amount"] == "205.00000000"
    assert candidate["source_json"]["scope"]["cost_source_lineage"]["scope_baseline_id"] == f.scope_baseline["id"]
    records = success(request(f, "GET", f"/api/v1/scope/projects/{f.project_workspace_id}/items", actor="admin"))[
        "items"
    ]
    actual = next(row for row in records if row["id"] == before["id"])
    assert Decimal(actual["quantity"]) == Decimal(before["quantity"])


def test_apu_effective_date_on_candidate(fixture):
    f = fixture
    row, unit_price = _budget(f), apu(f, effective_from="2027-01-01")
    result = request(
        f,
        "POST",
        f"/budgets/{row['id']}/candidate-from-scope",
        version=row["version"],
        payload={**REASON, "scope_item_id": f.scope_items[0]["id"], "apu_id": unit_price["id"], "line_code": "FUTURE"},
    )
    assert result.status_code == 422 and result.json()["detail"]["code"] == "COST_APU_NOT_EFFECTIVE_ON_PRICING_DATE"


def test_budget_lifecycle_sod_original_current_and_immutable(fixture):
    f = fixture
    row = _budget(f)
    row = line(f, row)["budget_version"]
    assert (
        request(
            f,
            "POST",
            f"/budgets/{row['id']}/transition",
            actor="manager",
            version=row["version"],
            payload={**REASON, "status": "APPROVED"},
        ).status_code
        == 409
    )
    for status in ("SUBMITTED", "UNDER_REVIEW"):
        row = success(
            request(
                f,
                "POST",
                f"/budgets/{row['id']}/transition",
                actor="cost_controller" if status == "SUBMITTED" else "manager",
                version=row["version"],
                payload={**REASON, "status": status},
            )
        )
    assert (
        request(
            f,
            "POST",
            f"/budgets/{row['id']}/transition",
            actor="cost_controller",
            version=row["version"],
            payload={**REASON, "status": "APPROVED"},
        ).status_code
        == 403
    )
    approved = success(
        request(
            f,
            "POST",
            f"/budgets/{row['id']}/transition",
            actor="manager",
            version=row["version"],
            payload={**REASON, "status": "APPROVED"},
        )
    )
    assert approved["status"] == "APPROVED" and approved["content_hash"]
    assert (
        request(
            f,
            "POST",
            f"/budgets/{row['id']}/lines",
            version=approved["version"],
            payload={
                **REASON,
                "line_code": "FORBIDDEN",
                "description": "No mutation",
                "quantity": 1,
                "unit": "ea",
                "rate": 1,
                "currency": "USD",
            },
        ).status_code
        == 409
    )
    successor = success(
        request(f, "POST", f"/budgets/{row['id']}/successor", version=approved["version"], payload=REASON), 201
    )
    assert successor["predecessor_id"] == row["id"] and successor["status"] == "DRAFT"
    successor = approved_budget(f, row=successor)
    model = success(request(f, "GET", "/overview"))
    assert model["budget_semantics"]["original_budget"]["id"] == approved["id"]
    assert model["budget_semantics"]["current_budget"]["id"] == successor["id"]
    assert success(request(f, "GET", f"/budgets/{approved['id']}"))["content_hash"] == approved["content_hash"]


def test_baseline_candidate_schedule_phasing_and_independent_approval(fixture):
    f = fixture
    approved = _approved(f)
    b = success(
        request(
            f, "POST", "/baselines", payload={**REASON, "code": f"BL-{uuid4()}", "budget_version_id": approved["id"]}
        ),
        201,
    )
    assert (
        request(
            f, "POST", f"/baselines/{b['id']}/approve", actor="manager", version=b["version"], payload=REASON
        ).status_code
        == 409
    )
    source = f.schedule_version["snapshot_json"]["activities"][0]
    line_id = approved["snapshot_json"]["lines"][0]["id"]
    phase = success(
        request(
            f,
            "POST",
            f"/baselines/{b['id']}/phase",
            version=b["version"],
            payload={
                **REASON,
                "budget_line_id": line_id,
                "method": "ACTIVITY_BASED",
                "schedule_version_id": f.schedule_version["id"],
                "source_external_id": source["external_id"],
                "period_id": f.period["id"],
            },
        ),
        201,
    )
    b = phase["baseline"]
    assert phase["basis_json"]["authority"] == "SCHEDULE_IMMUTABLE_SOURCE"
    assert sum(float(r["amount"]) for r in phase["spread_json"]) == pytest.approx(205)
    approved_b = success(
        request(f, "POST", f"/baselines/{b['id']}/approve", actor="manager", version=b["version"], payload=REASON)
    )
    assert approved_b["status"] == "APPROVED"
    assert (
        request(
            f,
            "POST",
            f"/baselines/{b['id']}/phase",
            version=approved_b["version"],
            payload={
                **REASON,
                "budget_line_id": line_id,
                "method": "LINEAR",
                "start_date": "2026-10-19",
                "finish_date": "2026-10-25",
            },
        ).status_code
        == 409
    )
    before = approved_b["content_hash"]
    _approved(f)
    assert success(request(f, "GET", f"/baselines/{b['id']}"))["content_hash"] == before


def test_contingency_inside_and_management_reserve_outside(fixture):
    f = fixture
    row = _budget(f)
    row = line(f, row, cost_class="CONTINGENCY", quantity="1", rate="10")["budget_version"]
    assert (
        request(
            f,
            "POST",
            f"/budgets/{row['id']}/lines",
            version=row["version"],
            payload={
                **REASON,
                "line_code": "MR-DENIED",
                "description": "Owner only",
                "quantity": 1,
                "unit": "ls",
                "rate": 20,
                "currency": "USD",
                "cost_class": "MANAGEMENT_RESERVE",
            },
        ).status_code
        == 403
    )
    reserve = success(
        request(
            f,
            "POST",
            f"/budgets/{row['id']}/lines",
            actor="admin",
            version=row["version"],
            payload={
                **REASON,
                "line_code": "MR",
                "description": "Owner management reserve",
                "quantity": 1,
                "unit": "ls",
                "rate": 20,
                "currency": "USD",
                "cost_class": "MANAGEMENT_RESERVE",
            },
        ),
        201,
    )
    for actor in ("manager", "second_manager"):
        denied = request(
            f,
            "POST",
            f"/budgets/{row['id']}/lines",
            actor=actor,
            version=reserve["budget_version"]["version"],
            payload={
                **REASON,
                "line_code": f"MR-DENIED-{actor}",
                "description": "Budget approval is not owner reserve delegation",
                "quantity": 1,
                "unit": "ls",
                "rate": 30,
                "currency": "USD",
                "cost_class": "MANAGEMENT_RESERVE",
            },
        )
        assert denied.status_code == 403
    denied = request(
        f,
        "PUT",
        f"/budgets/{row['id']}/lines/{reserve['id']}",
        actor="manager",
        version=reserve["budget_version"]["version"],
        payload={
            **REASON,
            "line_code": "MR",
            "description": "Cannot reclassify owner reserve to evade authorization",
            "quantity": 0,
            "unit": "ls",
            "rate": 0,
            "currency": "USD",
            "cost_class": "DIRECT",
        },
    )
    assert denied.status_code == 403
    calculation = success(request(f, "GET", f"/budgets/{row['id']}/calculation"))
    assert calculation["total"]["amount"] == "30.00000000"
    assert calculation["control_baseline_total"]["amount"] == "10.00000000"
    assert calculation["management_reserve"]["amount"] == "20.00000000"
    assert reserve["cost_class"] == "MANAGEMENT_RESERVE"


def test_budget_no_silent_mixed_currency(fixture):
    row = _budget(fixture)
    assert (
        request(
            fixture,
            "POST",
            f"/budgets/{row['id']}/lines",
            version=row["version"],
            payload={
                **REASON,
                "line_code": "COP",
                "description": "No implicit FX",
                "quantity": 1,
                "unit": "ea",
                "rate": 4000,
                "currency": "COP",
            },
        ).status_code
        == 422
    )


def test_gets_do_not_write_business_facts(fixture):
    statements = []

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        assert request(fixture, "GET", "/overview").status_code == 200
        assert request(fixture, "GET", "/cbs").status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert statements == []


def test_database_guards_no_approved_budget_rewrite(fixture):
    f = fixture
    approved = _approved(f)
    with engine.connect() as connection:
        transaction = connection.begin()
        with pytest.raises(DBAPIError):
            connection.execute(
                text("UPDATE cost_budget_versions SET name='forbidden' WHERE id=:id"), {"id": approved["id"]}
            )
        transaction.rollback()


def test_apu_revision_keeps_published_inputs_and_hash(fixture):
    f = fixture
    original = apu(f)
    successor = apu(
        f,
        code=original["code"],
        supersedes_id=original["id"],
        factors=[{"name": "Indirect", "percentage": "5", "basis": "DIRECT_COST"}],
    )
    assert successor["revision"] == 2 and successor["content_hash"] != original["content_hash"]
    assert success(request(f, "GET", f"/apus/{original['id']}"))["content_hash"] == original["content_hash"]


def test_draft_budget_line_edit_and_approved_line_rejection(fixture):
    f = fixture
    draft = _budget(f)
    candidate = line(f, draft)
    draft = candidate["budget_version"]
    body = {
        **REASON,
        "line_code": candidate["line_code"],
        "description": "Revised draft line",
        "quantity": "5",
        "unit": "m3",
        "rate": "20.50",
        "currency": "USD",
    }
    edited = success(
        request(f, "PUT", f"/budgets/{draft['id']}/lines/{candidate['id']}", version=draft["version"], payload=body)
    )
    assert edited["amount"] == "102.50000000" and edited["version"] == candidate["version"] + 1
    assert (
        request(
            f, "PUT", f"/budgets/{draft['id']}/lines/{candidate['id']}", version=draft["version"], payload=body
        ).status_code
        == 412
    )
    approved = approved_budget(f, row=edited["budget_version"])
    assert (
        request(
            f, "PUT", f"/budgets/{draft['id']}/lines/{candidate['id']}", version=approved["version"], payload=body
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "method", ["LINEAR", "FRONT_LOADED", "BACK_LOADED", "MILESTONE_BASED", "ACTIVITY_BASED", "MANUAL", "CURVE_BASED"]
)
def test_all_governed_phasing_methods_on_postgresql(fixture, method):
    f = fixture
    approved = _approved(f)
    b = success(
        request(
            f, "POST", "/baselines", payload={**REASON, "code": f"PHASE-{uuid4()}", "budget_version_id": approved["id"]}
        ),
        201,
    )
    body = {
        **REASON,
        "budget_line_id": approved["snapshot_json"]["lines"][0]["id"],
        "method": method,
        "start_date": "2026-10-19",
        "finish_date": "2026-10-25",
    }
    if method == "ACTIVITY_BASED":
        body.pop("start_date")
        body.pop("finish_date")
        body.update(
            schedule_version_id=f.schedule_version["id"],
            source_external_id=f.schedule_version["snapshot_json"]["activities"][0]["external_id"],
        )
    elif method == "MANUAL":
        body["manual_spread"] = [{"date": "2026-10-19", "amount": "100"}, {"date": "2026-10-25", "amount": "105"}]
    elif method == "CURVE_BASED":
        body["curve_weights"] = [1, 2, 3, 4, 3, 2, 1]
    result = success(request(f, "POST", f"/baselines/{b['id']}/phase", version=b["version"], payload=body), 201)
    assert result["method"] == method
    assert sum(float(r["amount"]) for r in result["spread_json"]) == pytest.approx(205)
    assert result["basis_json"]


def test_privileged_material_preparer_cannot_approve_budget_or_baseline(fixture):
    f = fixture
    draft = _budget(f)
    material = success(
        request(
            f,
            "POST",
            f"/budgets/{draft['id']}/lines",
            actor="admin",
            version=draft["version"],
            payload={
                **REASON,
                "line_code": "PRIVILEGED",
                "description": "Privileged editor is not approver",
                "quantity": 1,
                "unit": "ea",
                "rate": 50,
                "currency": "USD",
            },
        ),
        201,
    )
    row = material["budget_version"]
    for status, actor in (("SUBMITTED", "admin"), ("UNDER_REVIEW", "manager")):
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
    denied = request(
        f,
        "POST",
        f"/budgets/{row['id']}/transition",
        actor="admin",
        version=row["version"],
        payload={**REASON, "status": "APPROVED"},
    )
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "COST_BUDGET_APPROVAL_SOD"
    row = success(
        request(
            f,
            "POST",
            f"/budgets/{row['id']}/transition",
            actor="manager",
            version=row["version"],
            payload={**REASON, "status": "APPROVED"},
        )
    )
    baseline = success(
        request(
            f,
            "POST",
            "/baselines",
            actor="admin",
            payload={**REASON, "code": f"SOD-{uuid4()}", "budget_version_id": row["id"]},
        ),
        201,
    )
    phased = success(
        request(
            f,
            "POST",
            f"/baselines/{baseline['id']}/phase",
            actor="admin",
            version=baseline["version"],
            payload={
                **REASON,
                "budget_line_id": material["id"],
                "method": "LINEAR",
                "start_date": "2026-10-19",
                "finish_date": "2026-10-25",
            },
        ),
        201,
    )
    baseline = phased["baseline"]
    denied = request(
        f, "POST", f"/baselines/{baseline['id']}/approve", actor="admin", version=baseline["version"], payload=REASON
    )
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "COST_BASELINE_APPROVAL_SOD"
    assert (
        success(
            request(
                f,
                "POST",
                f"/baselines/{baseline['id']}/approve",
                actor="manager",
                version=baseline["version"],
                payload=REASON,
            )
        )["status"]
        == "APPROVED"
    )


def test_rates_and_apus_use_half_open_effective_windows(fixture):
    f = fixture
    denied = request(
        f,
        "POST",
        "/rates",
        payload={
            **REASON,
            "code": f"EMPTY-{uuid4()}",
            "name": "Empty effective interval",
            "resource_type": "LABOR",
            "unit": "h",
            "amount": "1",
            "currency": "USD",
            "effective_from": "2026-10-22",
            "effective_to": "2026-10-22",
            "source_reference": "EXPLICIT_RATE_WINDOW",
        },
    )
    assert denied.status_code == 422 and denied.json()["detail"]["code"] == "COST_RATE_EFFECTIVE_WINDOW_INVALID"
    source = rate(f)
    denied = request(
        f,
        "POST",
        "/apus",
        payload={
            **REASON,
            "code": f"EMPTY-{uuid4()}",
            "name": "Empty APU interval",
            "unit": "m3",
            "currency": "USD",
            "effective_from": "2026-10-22",
            "effective_to": "2026-10-22",
            "source_reference": "EXPLICIT_APU_WINDOW",
            "components": [{"rate_id": source["id"], "category": "LABOR", "quantity_per_unit": "1", "unit": "h"}],
        },
    )
    assert denied.status_code == 422 and denied.json()["detail"]["code"] == "COST_APU_EFFECTIVE_WINDOW_INVALID"
    unit_price, draft = apu(f, effective_to="2026-10-22"), _budget(f)
    denied = request(
        f,
        "POST",
        f"/budgets/{draft['id']}/candidate-from-scope",
        version=draft["version"],
        payload={
            **REASON,
            "scope_item_id": f.scope_items[0]["id"],
            "apu_id": unit_price["id"],
            "line_code": "EXPIRED-EXACT-END",
        },
    )
    assert denied.status_code == 422 and denied.json()["detail"]["code"] == "COST_APU_NOT_EFFECTIVE_ON_PRICING_DATE"


def test_scope_apu_candidate_idempotency_uses_original_command(fixture):
    f = fixture
    draft, unit_price = _budget(f), apu(f)
    body = {
        **REASON,
        "scope_item_id": f.scope_items[0]["id"],
        "apu_id": unit_price["id"],
        "line_code": "IDEMPOTENT-SCOPE-APU",
    }
    key = f"candidate-{uuid4()}"
    initial = success(
        request(
            f, "POST", f"/budgets/{draft['id']}/candidate-from-scope", version=draft["version"], payload=body, key=key
        ),
        201,
    )
    assert initial["budget_version"]["version"] > draft["version"]
    assert (
        success(
            request(
                f,
                "POST",
                f"/budgets/{draft['id']}/candidate-from-scope",
                version=draft["version"],
                payload=body,
                key=key,
            ),
            201,
        )
        == initial
    )
    assert (
        request(
            f,
            "POST",
            f"/budgets/{draft['id']}/candidate-from-scope",
            version=draft["version"],
            payload={**body, "line_code": "DIFFERENT"},
            key=key,
        ).status_code
        == 409
    )
