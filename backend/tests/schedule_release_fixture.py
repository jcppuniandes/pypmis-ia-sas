"""Isolated real Scope lifecycles consumed read-only by Schedule validation."""

from tests.scope_release_fixture import create_scope_fixture
from tests.test_scope_foundation_release import REASON, item, profile, request, revision, success

from app.modules.operational_context.service import DEFAULT_PROFILE as OPERATIONAL_PROFILE
from app.modules.schedule_foundation.permissions import ensure_schedule_permissions
from app.modules.scope_foundation.service import DEFAULT_PROFILE as SCOPE_PROFILE


def create_schedule_fixture(db, client):
    fixture = create_scope_fixture(db)
    ensure_schedule_permissions(db, fixture.tenant_id, fixture.users["admin"].id)
    ensure_schedule_permissions(db, fixture.foreign_tenant.id, fixture.users["foreign"].id)
    db.commit()
    fixture.client = client
    fixture.operational_profile = profile(fixture, "/api/v1/operational", OPERATIONAL_PROFILE)
    fixture.scope_profile = profile(fixture, "/api/v1/scope", SCOPE_PROFILE)
    fixture.scope_items = [
        item(fixture, "SCH-SCOPE-A", quantity=10, unit="m3"),
        item(fixture, "SCH-SCOPE-B", quantity=20, unit="ea", scope_nature="TEMPORARY"),
    ]
    fixture.scope_baseline = revision(fixture, fixture.scope_items)["baseline"]
    strategy = success(
        request(
            fixture,
            "POST",
            "/strategies",
            payload={
                **REASON,
                "code": "SCH-EXECUTION",
                "name": "Existing Scope execution strategy",
                "paths": [{"code": "ORDERED", "name": "Controlled ordered path", "mode": "ORDERED", "sequence": 1}],
                "segmentation_rules": [],
            },
        ),
        201,
    )
    fixture.scope_strategy = success(
        request(
            fixture,
            "POST",
            f"/strategies/{strategy['id']}/publish",
            payload=REASON,
            actor="publisher",
            version=strategy["version"],
        )
    )
    plans = []
    for index, quantities in enumerate(((4, 5), (6, 15)), 1):
        payload = {
            **REASON,
            "code": f"SCH-PLAN-{index}",
            "name": f"Existing Scope package {index}",
            "strategy_id": strategy["id"],
            "allocations": [
                {"scope_item_id": scope["id"], "quantity": quantity, "unit": scope["unit"]}
                for scope, quantity in zip(fixture.scope_items, quantities, strict=True)
            ],
        }
        plans.append(success(request(fixture, "POST", "/plan-items", payload=payload), 201))
    fixture.plan_items = [
        success(
            request(
                fixture,
                "POST",
                f"/plan-items/{plan['id']}/publish",
                payload=REASON,
                actor="publisher",
                version=plan["version"],
            )
        )
        for plan in plans
    ]
    return fixture
