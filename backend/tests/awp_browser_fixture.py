"""Real source/Scope/Plan/Schedule prerequisites for the isolated O1B-B1 browser."""

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from tests.scope_foundation_fixture import scope_ifc
from tests.scope_release_fixture import create_scope_fixture
from tests.test_schedule_foundation_release import accept, baseline, register, version
from tests.test_schedule_foundation_release import request as schedule_request
from tests.test_scope_foundation_release import REASON, item, profile, request, revision, success

from app.modules.operational_context.service import DEFAULT_PROFILE as OPERATIONAL_PROFILE
from app.modules.schedule_foundation.exchange import parse_schedule_source
from app.modules.schedule_foundation.permissions import ensure_schedule_permissions
from app.modules.schedule_foundation.service import DEFAULT_PROFILE as SCHEDULE_PROFILE
from app.modules.scope_foundation.service import DEFAULT_PROFILE as SCOPE_PROFILE


def create_awp_browser_fixture(db, client):
    f = create_scope_fixture(db)
    f.client = client
    ensure_schedule_permissions(db, f.tenant_id, f.users["admin"].id)
    # Catalog grants only. Actor assignments remain those of the existing fixture.
    from app.modules.awp.permissions import ensure_awp_permissions
    from app.modules.schedule_four_d.permissions import ensure_four_d_permissions

    ensure_awp_permissions(db, f.tenant_id, f.users["admin"].id)
    ensure_four_d_permissions(db, f.tenant_id, f.users["admin"].id)
    workspace = f.workspaces["direct"]
    workspace.defaults_json = {
        **workspace.defaults_json,
        "enabled_modules": ["scope-manager", "schedule-manager", "awp"],
    }
    db.commit()
    f.operational_profile = profile(f, "/api/v1/operational", OPERATIONAL_PROFILE)
    f.scope_profile = profile(f, "/api/v1/scope", SCOPE_PROFILE)
    f.schedule_profile = profile(f, "/api/v1/schedule", SCHEDULE_PROFILE)
    source = scope_ifc(count=4)
    f.model = success(
        request(
            f,
            "POST",
            "/models",
            files={"file": ("four-natures.ifc", source, "application/octet-stream")},
            data={**REASON, "model_code": "B1-FOUR-NATURES"},
        ),
        201,
    )
    for action, actor in (("review", "admin"), ("accept", "publisher")):
        f.model = success(
            request(
                f, "POST", f"/models/{f.model['id']}/{action}", actor=actor, payload=REASON, version=f.model["version"]
            )
        )
    f.objects = [
        r
        for r in success(request(f, "GET", f"/models/{f.model['id']}/objects"))["items"]
        if r["ifc_class"] == "IfcWall"
    ]
    f.scope_items = [
        item(
            f,
            f"B1-{nature}",
            name=f"B1 {nature} real IFC",
            source_type="IFC",
            scope_nature=nature,
            quantity="1.2",
            unit="m3",
            source_quantity_name="NetVolume",
            model_object_ids=[obj["id"]],
            area="North",
            zone="A",
            system="Structural",
        )
        for nature, obj in zip(("INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"), f.objects, strict=True)
    ]
    f.scope_baseline = revision(f, f.scope_items)["baseline"]
    f.plan_items = []
    for scope in f.scope_items:
        plan = success(
            request(
                f,
                "POST",
                "/plan-items",
                payload={
                    **REASON,
                    "code": f"PLAN-{scope['scope_nature']}",
                    "name": f"Published {scope['scope_nature']} Plan",
                    "model_object_ids": scope["model_object_ids"],
                    "allocations": [
                        {"scope_item_id": scope["id"], "quantity": scope["quantity"], "unit": scope["unit"]}
                    ],
                },
            ),
            201,
        )
        f.plan_items.append(
            success(
                request(
                    f,
                    "POST",
                    f"/plan-items/{plan['id']}/publish",
                    actor="publisher",
                    version=plan["version"],
                    payload=REASON,
                )
            )
        )
    f.derived = success(
        request(
            f,
            "POST",
            "/derived-models",
            payload={**REASON, "plan_item_ids": [p["id"] for p in f.plan_items], "split_rule": "LOGICAL"},
        ),
        201,
    )
    content = deepcopy(
        parse_schedule_source(
            (Path(__file__).parent / "fixtures/schedule-foundation-p6.xml").read_bytes(), "source.xml"
        )["snapshot"]
    )
    content["relationships"] = []
    content["external_links"] = []
    content["constraints"] = []
    content["code_assignments"] = []
    template = deepcopy(content["activities"][0])
    content["activities"] = []
    specs = [
        ("INSTALL", 21, 22, 0, "EXECUTE"),
        ("REMOVE", 23, 24, 1, "EXECUTE"),
        ("TEMP-INSTALL", 21, 21, 2, "INSTALL"),
        ("TEMP-USE", 22, 24, 2, "USE"),
        ("TEMP-REMOVE", 25, 25, 2, "REMOVE"),
        ("MAINTENANCE", 23, 24, 3, "EXECUTE"),
    ]
    f.activity_plans = {}
    f.activity_phases = {}
    for index, (code, start, finish, plan_index, phase) in enumerate(specs, 1):
        activity = deepcopy(template)
        activity.update(
            external_id=str(5000 + index),
            code=code,
            name=f"B1 {code}",
            status="NOT_STARTED",
            source_fields={},
            total_float=-2 if index == 1 else 60,
            free_float=0,
            critical=index == 1,
            percent_complete=0,
        )
        for key in (
            "start",
            "finish",
            "actual_start",
            "actual_finish",
            "early_start",
            "early_finish",
            "late_start",
            "late_finish",
            "primary_constraint_type",
            "primary_constraint_date",
        ):
            activity[key] = None
        activity["planned_start"] = f"2026-10-{start:02d}T07:00:00"
        activity["planned_finish"] = f"2026-10-{finish:02d}T17:00:00"
        content["activities"].append(activity)
        f.activity_plans[activity["external_id"]] = f.plan_items[plan_index]["id"]
        f.activity_phases[activity["external_id"]] = phase
    f.schedule_register = register(f, schedule_code=f"B1-{uuid4().hex[:8]}")

    def mapped(row):
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
                        "plan_item_ids": [f.activity_plans[activity["external_id"]]],
                    },
                ),
                201,
            )["schedule_version"]
        return accept(f, row)

    f.baseline_schedule_version = mapped(version(f, f.schedule_register, content=content))
    f.schedule_baseline = baseline(f, f.baseline_schedule_version)
    f.schedule_register = success(schedule_request(f, "GET", f"/registers/{f.schedule_register['id']}"))
    changed = deepcopy(content)
    changed["project"]["data_date"] = "2026-10-22T08:00:00"
    changed["activities"][0]["planned_start"] = "2026-10-23T07:00:00"
    changed["activities"][0]["planned_finish"] = "2026-10-24T17:00:00"
    f.current_schedule_version = mapped(
        version(f, f.schedule_register, content=changed, predecessor=f.baseline_schedule_version["id"], kind="UPDATE")
    )
    return f
