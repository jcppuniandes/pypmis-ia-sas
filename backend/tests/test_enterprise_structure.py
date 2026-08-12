from fastapi.testclient import TestClient

from app.database.session import SessionLocal
from app.domain.models import EnterpriseWorkspace
from app.main import app
from app.modules.enterprise_structure.record_codes import next_record_code


def _headers(client: TestClient, email: str = "admin") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _configuration(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.get(
        "/api/v1/admin-configuration/enterprise-structure/configuration",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_node(
    client: TestClient,
    headers: dict[str, str],
    *,
    code: str,
    name: str,
    workspace_type: str,
    parent_id: int,
) -> dict:
    response = client.post(
        "/api/v1/admin-configuration/enterprise-structure/nodes",
        headers=headers,
        json={
            "code": code,
            "name": name,
            "workspace_type_code": workspace_type,
            "parent_id": parent_id,
            "region_code": "CO-DC",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_enterprise_configuration_seeds_seven_types_categories_and_one_root() -> None:
    with TestClient(app) as client:
        payload = _configuration(client, _headers(client))

    assert {item["code"] for item in payload["workspace_types"]} >= {
        "enterprise",
        "business-unit",
        "portfolio",
        "program",
        "project",
        "property",
        "facility",
    }
    assert {item["code"] for item in payload["categories"]} >= {
        "strategic-objective",
        "responsible-area",
        "project-type",
        "property-type",
        "facility-type",
    }
    assert len(payload["tree"]) == 1
    assert payload["tree"][0]["workspace_type_code"] == "enterprise"
    assert payload["tree"][0]["record_code"] == "01"
    assert payload["tree"][0]["depth"] == 0


def test_enterprise_hierarchy_applies_composition_cycle_and_archive_rules() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        root = _configuration(client, headers)["tree"][0]
        business_unit = _create_node(
            client,
            headers,
            code="BU-LEVEL2A",
            name="Capital Projects",
            workspace_type="business-unit",
            parent_id=root["id"],
        )
        portfolio = _create_node(
            client,
            headers,
            code="PF-LEVEL2A",
            name="Strategic Portfolio",
            workspace_type="portfolio",
            parent_id=business_unit["id"],
        )
        program = _create_node(
            client,
            headers,
            code="PG-LEVEL2A",
            name="Infrastructure Program",
            workspace_type="program",
            parent_id=portfolio["id"],
        )
        project = _create_node(
            client,
            headers,
            code="PR-LEVEL2A",
            name="Expansion Project",
            workspace_type="project",
            parent_id=program["id"],
        )
        property_node = _create_node(
            client,
            headers,
            code="PROP-LEVEL2A",
            name="North Property",
            workspace_type="property",
            parent_id=business_unit["id"],
        )
        facility = _create_node(
            client,
            headers,
            code="FAC-LEVEL2A",
            name="Main Plant",
            workspace_type="facility",
            parent_id=property_node["id"],
        )
        invalid_facility = client.post(
            "/api/v1/admin-configuration/enterprise-structure/nodes",
            headers=headers,
            json={
                "code": "FAC-INVALID",
                "name": "Invalid Facility",
                "workspace_type_code": "facility",
                "parent_id": portfolio["id"],
            },
        )
        cycle = client.patch(
            f"/api/v1/admin-configuration/enterprise-structure/nodes/{business_unit['id']}",
            headers=headers,
            json={"parent_id": project["id"], "expected_version": business_unit["version"]},
        )
        blocked_archive = client.delete(
            f"/api/v1/admin-configuration/enterprise-structure/nodes/{property_node['id']}",
            headers=headers,
        )

    assert facility["parent_id"] == property_node["id"]
    assert business_unit["record_code"].startswith("01.")
    assert portfolio["record_code"] == f"{business_unit['record_code']}.01"
    assert property_node["record_code"] == f"{business_unit['record_code']}.02"
    assert facility["record_code"] == f"{property_node['record_code']}.01"
    assert len({business_unit["record_code"], portfolio["record_code"], property_node["record_code"]}) == 3
    assert invalid_facility.status_code == 409
    assert cycle.status_code == 409
    assert blocked_archive.status_code == 409


def test_classifications_cross_relations_and_enterprise_explorer_are_persistent() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        configuration = _configuration(client, headers)
        flat_nodes: list[dict] = []

        def flatten(nodes: list[dict]) -> None:
            for node in nodes:
                flat_nodes.append(node)
                flatten(node["children"])

        flatten(configuration["tree"])
        portfolio = next(item for item in flat_nodes if item["code"] == "PF-LEVEL2A")
        project = next(item for item in flat_nodes if item["code"] == "PR-LEVEL2A")
        property_node = next(item for item in flat_nodes if item["code"] == "PROP-LEVEL2A")
        facility = next(item for item in flat_nodes if item["code"] == "FAC-LEVEL2A")

        classification = client.post(
            f"/api/v1/admin-configuration/enterprise-structure/nodes/{portfolio['id']}/classifications",
            headers=headers,
            json={"category_set_code": "strategic-objective", "category_item_code": "growth"},
        )
        duplicate = client.post(
            f"/api/v1/admin-configuration/enterprise-structure/nodes/{portfolio['id']}/classifications",
            headers=headers,
            json={"category_set_code": "strategic-objective", "category_item_code": "growth"},
        )
        property_link = client.post(
            "/api/v1/admin-configuration/enterprise-structure/links",
            headers=headers,
            json={
                "source_workspace_id": project["id"],
                "target_workspace_id": property_node["id"],
                "relationship_type": "LOCATED_AT",
            },
        )
        facility_link = client.post(
            "/api/v1/admin-configuration/enterprise-structure/links",
            headers=headers,
            json={
                "source_workspace_id": project["id"],
                "target_workspace_id": facility["id"],
                "relationship_type": "AFFECTS",
            },
        )
        explorer = client.get(
            "/api/v1/enterprise-structure/overview?strategic_objective=growth",
            headers=headers,
        )
        detail = client.get(f"/api/v1/enterprise-structure/nodes/{project['id']}", headers=headers)

    assert classification.status_code == 201, classification.text
    assert duplicate.status_code == 409
    assert property_link.status_code == 201, property_link.text
    assert facility_link.status_code == 201, facility_link.text
    assert explorer.status_code == 200, explorer.text
    assert [item["code"] for item in explorer.json()["nodes"]] == ["PF-LEVEL2A"]
    assert len(detail.json()["links"]) == 2
    assert [item["code"] for item in detail.json()["path"]][-1] == "PR-LEVEL2A"


def test_configuration_drafts_validate_publish_and_remain_immutable() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        clone = client.post(
            "/api/v1/admin-configuration/enterprise-structure/types/portfolio/clone",
            headers=headers,
        )
        assert clone.status_code == 201, clone.text
        rule = client.put(
            "/api/v1/admin-configuration/enterprise-structure/composition-rules/portfolio",
            headers=headers,
            json={
                "allowed_children": ["program", "project"],
                "can_be_root": False,
                "required_categories": ["strategic-objective"],
                "required_fields": ["code", "name"],
            },
        )
        validation = client.post(
            "/api/v1/admin-configuration/enterprise-structure/validate",
            headers=headers,
            json={"configuration_ids": [clone.json()["id"]]},
        )
        candidate_hash = clone.json()["content_hash"]
        stale_publish = client.post(
            "/api/v1/admin-configuration/enterprise-structure/publish",
            headers=headers,
            json={"configuration_ids": [clone.json()["id"]]},
        )
        published = client.post(
            "/api/v1/admin-configuration/enterprise-structure/publish",
            headers=headers,
            json={
                "configuration_ids": [clone.json()["id"]],
                "expected_hashes": {str(clone.json()["id"]): candidate_hash},
            },
        )
        generic_update = client.patch(
            f"/api/v1/admin-configuration/configurations/{clone.json()['id']}",
            headers=headers,
            json={"name": "Changed after publish"},
        )

    assert rule.status_code == 200, rule.text
    assert validation.json()["valid"] is True
    assert stale_publish.status_code == 409
    assert published.status_code == 200, published.text
    assert len(published.json()["published"][0]["content_hash"]) == 64
    assert generic_update.status_code == 409


def test_enterprise_endpoints_require_specific_permissions_and_tenant_scoping() -> None:
    with TestClient(app) as client:
        admin_headers = _headers(client)
        _configuration(client, admin_headers)
        reader_headers = _headers(client, "pablo.planner@demo.local")
        forbidden = client.get("/api/v1/enterprise-structure/tree", headers=reader_headers)
        unknown_target = client.post(
            "/api/v1/admin-configuration/enterprise-structure/links",
            headers=admin_headers,
            json={
                "source_workspace_id": 999998,
                "target_workspace_id": 999999,
                "relationship_type": "LOCATED_AT",
            },
        )

    assert forbidden.status_code == 403
    assert "enterprise_structure.read" in forbidden.text
    assert unknown_target.status_code == 404


def test_moving_node_recalculates_descendants_without_changing_stable_identity() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        configuration = _configuration(client, headers)
        root = configuration["tree"][0]
        first_business_unit = next(item for item in root["children"] if item["code"] == "BU-LEVEL2A")
        portfolio = first_business_unit["children"][0]
        program = portfolio["children"][0]
        second_business_unit = _create_node(
            client,
            headers,
            code="BU-MOVE-TARGET",
            name="Move Target",
            workspace_type="business-unit",
            parent_id=root["id"],
        )

        with SessionLocal() as db:
            persisted = db.get(EnterpriseWorkspace, portfolio["id"])
            defaults = dict(persisted.defaults_json or {})
            metadata = dict(defaults.get("_enterprise", {}))
            metadata["external_key"] = "PF-STABLE-IDENTITY"
            defaults["_enterprise"] = metadata
            persisted.defaults_json = defaults
            db.commit()

        moved = client.patch(
            f"/api/v1/admin-configuration/enterprise-structure/nodes/{portfolio['id']}",
            headers=headers,
            json={"parent_id": second_business_unit["id"], "expected_version": portfolio["version"]},
        )
        program_after = client.get(
            f"/api/v1/enterprise-structure/nodes/{program['id']}",
            headers=headers,
        )

    assert moved.status_code == 200, moved.text
    moved_payload = moved.json()
    assert moved_payload["id"] == portfolio["id"]
    assert moved_payload["record_code"].startswith(f"{second_business_unit['record_code']}.")
    assert program_after.json()["node"]["record_code"].startswith(f"{moved_payload['record_code']}.")
    with SessionLocal() as db:
        persisted = db.get(EnterpriseWorkspace, portfolio["id"])
        assert persisted.defaults_json["_enterprise"]["external_key"] == "PF-STABLE-IDENTITY"


def test_record_code_uniqueness_is_tenant_scoped_for_concurrent_writes() -> None:
    constraint = next(
        item
        for item in EnterpriseWorkspace.__table__.constraints
        if getattr(item, "name", None) == "uq_enterprise_workspace_record_code"
    )
    assert [column.name for column in constraint.columns] == ["tenant_id", "record_code"]


def test_record_code_extends_after_99_without_rewriting_existing_segments() -> None:
    existing = [f"01.{sequence:02d}" for sequence in range(1, 100)]

    assert next_record_code("01", existing) == "01.100"
    assert existing[0] == "01.01"
    assert existing[-1] == "01.99"
