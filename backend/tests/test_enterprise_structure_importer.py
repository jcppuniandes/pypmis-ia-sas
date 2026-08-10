from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent
from app.main import app
from app.modules.enterprise_structure.importer.diff import build_diff
from app.modules.enterprise_structure.importer.models import (
    DiffAction,
    EnterpriseStructureImport,
    ExistingNode,
    TenantSnapshot,
)
from app.modules.enterprise_structure.importer.normalizer import normalize_configuration
from app.modules.enterprise_structure.importer.parser import (
    ConfigurationParseError,
    parse_configuration,
)
from app.modules.enterprise_structure.importer.report import render_human, render_json
from app.modules.enterprise_structure.importer.schema import canonical_json_schema
from app.modules.enterprise_structure.importer.snapshot import load_tenant_snapshot
from app.modules.enterprise_structure.importer.validator import (
    build_dry_run,
    topological_order,
)
from app.modules.enterprise_structure.models import (
    EnterpriseWorkspaceClassification,
    EnterpriseWorkspaceLink,
)


def _payload() -> dict:
    return {
        "metadata": {
            "tenant_code": "demo-energy",
            "release_code": "es-test-001",
            "release_name": "Approved test release",
            "source_date": "2026-08-06",
            "requested_by": "ADMIN@DEMO.LOCAL",
        },
        "strategic_objectives": [{"code": "obj-001", "name": "Growth", "active": True}],
        "nodes": [
            {
                "external_key": "ent-root",
                "code": "enterprise",
                "name": "Enterprise Workspace",
                "node_type": "ENTERPRISE",
                "description": "Enterprise root",
                "status": "ACTIVE",
                "sort_order": 0,
                "publish_candidate": True,
            },
            {
                "external_key": "bu-001",
                "code": "bu-001",
                "name": "Capital Projects",
                "node_type": "BUSINESS_UNIT",
                "parent_external_key": "ent-root",
                "status": "DRAFT",
                "sort_order": 10,
                "publish_candidate": True,
            },
            {
                "external_key": "prop-001",
                "code": "prop-001",
                "name": "Main Property",
                "node_type": "PROPERTY",
                "parent_external_key": "bu-001",
                "status": "DRAFT",
                "sort_order": 20,
                "publish_candidate": True,
            },
            {
                "external_key": "prj-001",
                "code": "prj-001",
                "name": "Pilot Project",
                "node_type": "PROJECT",
                "parent_external_key": "bu-001",
                "status": "DRAFT",
                "sort_order": 30,
                "publish_candidate": True,
            },
        ],
        "classifications": [
            {
                "workspace_external_key": "bu-001",
                "category_set_code": "RESPONSIBLE_AREA",
                "category_item_code": "corporate",
                "status": "ACTIVE",
            },
            {
                "workspace_external_key": "prop-001",
                "category_set_code": "PROPERTY_TYPE",
                "category_item_code": "owned",
                "status": "ACTIVE",
            },
            {
                "workspace_external_key": "prj-001",
                "category_set_code": "STRATEGIC_OBJECTIVE",
                "category_item_code": "obj-001",
                "status": "ACTIVE",
            },
        ],
        "links": [
            {
                "source_external_key": "prj-001",
                "target_external_key": "prop-001",
                "relationship_type": "LOCATED_AT",
                "status": "ACTIVE",
            }
        ],
    }


def _configuration(payload: dict | None = None) -> EnterpriseStructureImport:
    return normalize_configuration(EnterpriseStructureImport.model_validate(payload or _payload()))


def _snapshot() -> TenantSnapshot:
    root = ExistingNode(
        id=1,
        parent_id=None,
        external_key="ENT-ROOT",
        code="ENTERPRISE",
        name="Enterprise Workspace",
        node_type="enterprise",
        status="active",
        sort_order=0,
        metadata={"external_key": "ENT-ROOT", "description": "Enterprise root"},
        record_code="01",
    )
    return TenantSnapshot(
        tenant_id=1,
        tenant_code="DEMO-ENERGY",
        nodes=[root],
        published_type_codes={"enterprise", "business-unit", "portfolio", "program", "project", "property", "facility"},
        published_categories={
            "strategic-objective": {
                "applicable_types": ["portfolio", "program", "project"],
                "items": [],
            },
            "responsible-area": {
                "applicable_types": ["business-unit"],
                "items": [{"code": "corporate", "label": "Corporate"}],
            },
            "project-type": {"applicable_types": ["portfolio", "program", "project"], "items": []},
            "property-type": {
                "applicable_types": ["property"],
                "items": [{"code": "owned", "label": "Owned"}],
            },
            "facility-type": {"applicable_types": ["facility"], "items": []},
        },
        user_emails={"admin@demo.local"},
        requester_has_manage_permission=True,
    )


def test_yaml_parser_normalizes_declarative_identity(tmp_path: Path) -> None:
    source = tmp_path / "enterprise.yaml"
    source.write_text(
        """
metadata:
  tenant_code: demo-energy
  release_code: es-001
  release_name: First release
nodes:
  - external_key: ent-root
    code: ent-001
    name: Enterprise
    node_type: ENTERPRISE
    status: DRAFT
""".strip(),
        encoding="utf-8",
    )
    parsed = parse_configuration(source)

    assert parsed.metadata.tenant_code == "DEMO-ENERGY"
    assert parsed.metadata.release_code == "ES-001"
    assert parsed.nodes[0].external_key == "ENT-ROOT"
    assert parsed.nodes[0].code == "ENT-001"

    invalid = tmp_path / "enterprise.json"
    invalid.write_text("{}", encoding="utf-8")
    try:
        parse_configuration(invalid)
    except ConfigurationParseError as exc:
        assert "canonical .yaml/.yml" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected parser error")

    schema = canonical_json_schema()
    assert set(schema["properties"]) == {
        "metadata",
        "strategic_objectives",
        "nodes",
        "classifications",
        "links",
        "reconciliation",
    }


def test_dry_run_validates_topology_references_and_diff_without_mutation() -> None:
    configuration = _configuration()
    report = build_dry_run(configuration, _snapshot())

    assert report.valid is True
    assert report.summary["errors"] == 0
    assert report.topological_order.index("ENT-ROOT") < report.topological_order.index("BU-001")
    assert report.summary["create"] == 8
    assert report.summary["unchanged"] == 1
    assert report.summary["base_mutations"] == 0
    node_codes = {item.key: item.record_code for item in report.diff if item.entity == "node"}
    assert node_codes == {
        "ENT-ROOT": "01",
        "BU-001": "01.01",
        "PROP-001": "01.01.01",
        "PRJ-001": "01.01.02",
    }
    assert len(report.input_hash) == 64
    assert "Result: VALID" in render_human(report)
    assert '"release_code": "ES-TEST-001"' in render_json(report)


def test_dry_run_blocks_cycles_duplicates_invalid_links_and_dates() -> None:
    payload = _payload()
    payload["nodes"][0]["parent_external_key"] = "BU-001"
    payload["nodes"][1]["parent_external_key"] = "ENT-ROOT"
    payload["nodes"].append(dict(payload["nodes"][1]))
    payload["links"][0]["source_external_key"] = "BU-001"
    payload["classifications"][0]["category_item_code"] = "unknown-area"
    payload["nodes"][2]["valid_from"] = "2026-09-01"
    payload["nodes"][2]["valid_to"] = "2026-08-01"
    report = build_dry_run(_configuration(payload), _snapshot())
    codes = {item.code for item in report.findings}

    assert report.valid is False
    assert {
        "ROOT_COUNT",
        "DUPLICATE_EXTERNAL_KEY",
        "DUPLICATE_NODE_CODE",
        "HIERARCHY_CYCLE",
        "INVALID_DATE_RANGE",
        "UNSUPPORTED_RELATIONSHIP_PAIR",
        "CATEGORY_ITEM_NOT_PUBLISHED",
    }.issubset(codes)


def test_diff_is_idempotent_for_existing_nodes_classifications_and_links() -> None:
    configuration = _configuration()
    snapshot = _snapshot()
    existing_by_key = {item.external_key: item for item in snapshot.nodes}
    parent_ids = {"ENT-ROOT": None, "BU-001": 1, "PROP-001": 2, "PRJ-001": 2}
    for index, node in enumerate(configuration.nodes[1:], start=2):
        parent_id = parent_ids[node.external_key]
        existing = ExistingNode(
            id=index,
            parent_id=parent_id,
            external_key=node.external_key,
            code=node.code,
            name=node.name,
            node_type=node.node_type.value.lower().replace("_", "-"),
            status=node.status.value.lower(),
            sort_order=node.sort_order or 0,
            metadata={"external_key": node.external_key, "description": node.description or "", "region_code": ""},
            record_code={"BU-001": "01.01", "PROP-001": "01.01.01", "PRJ-001": "01.01.02"}[node.external_key],
        )
        snapshot.nodes.append(existing)
        existing_by_key[node.external_key] = existing
    snapshot.published_categories["strategic-objective"]["items"] = [{"code": "OBJ-001", "label": "Growth"}]
    snapshot.classifications.add((existing_by_key["BU-001"].id, "responsible-area", "corporate"))
    snapshot.classifications.add((existing_by_key["PROP-001"].id, "property-type", "owned"))
    snapshot.classifications.add((existing_by_key["PRJ-001"].id, "strategic-objective", "obj-001"))
    snapshot.links.add((existing_by_key["PRJ-001"].id, existing_by_key["PROP-001"].id, "LOCATED_AT"))

    diff = build_diff(configuration, snapshot)
    assert {item.action for item in diff} == {DiffAction.UNCHANGED}

    changed_parent = _payload()
    changed_parent["nodes"][2]["parent_external_key"] = "ENT-ROOT"
    parent_diff = build_diff(_configuration(changed_parent), snapshot)
    property_change = next(item for item in parent_diff if item.entity == "node" and item.key == "PROP-001")
    assert property_change.action == DiffAction.UPDATE


def test_required_categories_are_enforced() -> None:
    payload = _payload()
    payload["classifications"] = [
        item for item in payload["classifications"] if item["workspace_external_key"].lower() != "bu-001"
    ]
    report = build_dry_run(_configuration(payload), _snapshot())

    assert report.valid is False
    assert any(
        item.code == "REQUIRED_CLASSIFICATION_MISSING" and item.reference == "BU-001" for item in report.findings
    )


def test_validate_against_seeded_database_is_strictly_read_only() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin", "password": "1234", "tenant_slug": "demo-energy"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = client.get(
            "/api/v1/admin-configuration/enterprise-structure/configuration",
            headers=headers,
        )
        assert response.status_code == 200

    with SessionLocal() as db:
        counts_before = (
            db.scalar(select(func.count()).select_from(EnterpriseWorkspace)),
            db.scalar(select(func.count()).select_from(EnterpriseWorkspaceClassification)),
            db.scalar(select(func.count()).select_from(EnterpriseWorkspaceLink)),
            db.scalar(select(func.count()).select_from(SecurityEvent)),
            db.scalar(select(func.count()).select_from(AdminConfiguration)),
        )
        snapshot = load_tenant_snapshot(db, "demo-energy", "admin@demo.local")
        report = build_dry_run(_configuration(), snapshot)
        counts_after = (
            db.scalar(select(func.count()).select_from(EnterpriseWorkspace)),
            db.scalar(select(func.count()).select_from(EnterpriseWorkspaceClassification)),
            db.scalar(select(func.count()).select_from(EnterpriseWorkspaceLink)),
            db.scalar(select(func.count()).select_from(SecurityEvent)),
            db.scalar(select(func.count()).select_from(AdminConfiguration)),
        )

    assert report.summary["errors"] == 0
    assert counts_after == counts_before


def test_topological_order_reports_cycle_keys() -> None:
    payload = _payload()
    payload["nodes"][0]["parent_external_key"] = "BU-001"
    order, cycles = topological_order(_configuration(payload))
    assert len(order) == len(payload["nodes"])
    assert {"ENT-ROOT", "BU-001"}.issubset(cycles)


def _reconciled_payload() -> dict:
    payload = _payload()
    payload["reconciliation"] = [
        {"external_key": "ENT-ROOT", "existing_id": 1, "action": "ADOPT", "rationale": "Existing root"},
        {"external_key": "BU-001", "existing_id": 2, "action": "ADOPT", "rationale": "Existing BU"},
        {"external_key": "PROP-001", "existing_id": 3, "action": "ADOPT", "rationale": "Existing property"},
        {"external_key": "PRJ-001", "existing_id": 4, "action": "ADOPT", "rationale": "Existing project"},
    ]
    return payload


def _reconciliation_snapshot() -> TenantSnapshot:
    snapshot = _snapshot()
    snapshot.nodes = [
        ExistingNode(
            id=1,
            parent_id=None,
            external_key="",
            code="ENTERPRISE",
            name="Legacy Enterprise",
            node_type="enterprise",
            status="active",
            sort_order=0,
            metadata={},
            record_code="01",
            references={"children": 1, "classifications": 0, "links": 0, "module_settings": 0},
            child_ids=(2,),
        ),
        ExistingNode(
            id=2,
            parent_id=1,
            external_key="",
            code="001",
            name="Legacy Business Unit",
            node_type="business-unit",
            status="active",
            sort_order=0,
            metadata={},
            record_code="01.04",
            references={"children": 2, "classifications": 1, "links": 0, "module_settings": 0},
            child_ids=(3, 4),
        ),
        ExistingNode(
            id=3,
            parent_id=2,
            external_key="",
            code="LEG-PROP",
            name="Legacy Property",
            node_type="property",
            status="active",
            sort_order=0,
            metadata={},
            record_code="01.04.01",
            references={"children": 0, "classifications": 1, "links": 1, "module_settings": 0},
        ),
        ExistingNode(
            id=4,
            parent_id=2,
            external_key="",
            code="LEG-PRJ",
            name="Legacy Project",
            node_type="project",
            status="active",
            sort_order=0,
            metadata={},
            record_code="01.04.02",
            references={"children": 0, "classifications": 1, "links": 1, "module_settings": 0},
        ),
    ]
    snapshot.workspace_tenant_ids = {1: 1, 2: 1, 3: 1, 4: 1}
    snapshot.published_categories["strategic-objective"]["items"] = [{"code": "OBJ-001", "label": "Growth"}]
    snapshot.classifications = {
        (2, "responsible-area", "corporate"),
        (3, "property-type", "owned"),
        (4, "strategic-objective", "obj-001"),
    }
    snapshot.links = {(4, 3, "LOCATED_AT")}
    return snapshot


def test_explicit_adoption_preserves_ids_references_and_distinguishes_adopt_from_create() -> None:
    snapshot = _reconciliation_snapshot()
    classifications_before = set(snapshot.classifications)
    links_before = set(snapshot.links)
    report = build_dry_run(_configuration(_reconciled_payload()), snapshot)

    adopted = {item.key: item for item in report.diff if item.action == DiffAction.ADOPT}
    assert report.valid is True
    assert report.summary["adopt"] == 4
    assert report.summary["identity_conflicts"] == 0
    assert adopted["ENT-ROOT"].existing_id == 1
    assert adopted["BU-001"].existing_id == 2
    assert adopted["BU-001"].old_record_code == "01.04"
    assert adopted["BU-001"].record_code == "01.01"
    assert snapshot.classifications == classifications_before
    assert snapshot.links == links_before
    assert any(item.entity == "strategic_objective" and item.action == DiffAction.UNCHANGED for item in report.diff)
    assert not any(item.entity == "node" and item.action == DiffAction.CREATE for item in report.diff)


def test_reconciliation_rejects_duplicate_claims_and_unknown_external_keys() -> None:
    payload = _reconciled_payload()
    payload["reconciliation"].append(
        {"external_key": "BU-001", "existing_id": 1, "action": "ADOPT", "rationale": "Duplicate key"}
    )
    payload["reconciliation"].append(
        {"external_key": "UNKNOWN", "existing_id": 2, "action": "ADOPT", "rationale": "Unknown key"}
    )
    report = build_dry_run(_configuration(payload), _reconciliation_snapshot())
    codes = {item.code for item in report.findings}

    assert report.valid is False
    assert {"DUPLICATE_RECONCILIATION_KEY", "DUPLICATE_RECONCILIATION_ID", "RECONCILIATION_NODE_NOT_FOUND"}.issubset(
        codes
    )


def test_reconciliation_blocks_cross_tenant_adoption_and_workspace_type_mismatch() -> None:
    snapshot = _reconciliation_snapshot()
    payload = _payload()
    payload["reconciliation"] = [
        {"external_key": "ENT-ROOT", "existing_id": 99, "action": "ADOPT", "rationale": "Wrong tenant"},
        {"external_key": "PROP-001", "existing_id": 2, "action": "ADOPT", "rationale": "Wrong type"},
    ]
    snapshot.workspace_tenant_ids[99] = 2
    report = build_dry_run(_configuration(payload), snapshot)
    codes = {item.code for item in report.findings}

    assert report.valid is False
    assert {"CROSS_TENANT_ADOPTION", "ADOPTION_TYPE_MISMATCH"}.issubset(codes)


def test_reconciliation_blocks_unmapped_children_and_cycle_after_adoption() -> None:
    snapshot = _reconciliation_snapshot()
    payload = _reconciled_payload()
    payload["reconciliation"] = payload["reconciliation"][:2]
    payload["nodes"][0]["parent_external_key"] = "BU-001"
    report = build_dry_run(_configuration(payload), snapshot)
    codes = {item.code for item in report.findings}

    assert report.valid is False
    assert "ADOPTION_CHILD_REFERENCE_UNMAPPED" in codes
    assert "ADOPTION_HIERARCHY_CYCLE" in codes


def test_reconciled_dry_run_is_deterministic_and_does_not_mutate_snapshot() -> None:
    source = Path(__file__).parents[1] / "config" / "enterprise_structure.pyp_core_reconciled_review.yaml"
    configuration = parse_configuration(source)
    snapshot = _snapshot()
    snapshot.nodes = [
        ExistingNode(
            id=1,
            parent_id=None,
            external_key="",
            code="enterprise",
            name="P&P Ingenieria y Proyectos",
            node_type="enterprise",
            status="active",
            sort_order=0,
            metadata={},
            record_code="01",
            references={"children": 2, "classifications": 0, "links": 0, "module_settings": 0},
            child_ids=(2, 3),
        ),
        ExistingNode(
            id=2,
            parent_id=1,
            external_key="",
            code="001",
            name="Gerencia de Construcciones",
            node_type="business-unit",
            status="active",
            sort_order=0,
            metadata={},
            record_code="01.01",
        ),
        ExistingNode(
            id=3,
            parent_id=1,
            external_key="",
            code="002",
            name="Gerencia PMO aaS",
            node_type="business-unit",
            status="active",
            sort_order=0,
            metadata={},
            record_code="01.02",
        ),
    ]
    snapshot.workspace_tenant_ids = {1: 1, 2: 1, 3: 1}
    snapshot.published_categories["responsible-area"]["items"].extend(
        [
            {"code": "consulting", "label": "Consulting"},
            {"code": "pmo-aas", "label": "PMO aaS"},
            {"code": "technology", "label": "Technology"},
            {"code": "construction", "label": "Construction"},
        ]
    )
    before = deepcopy(snapshot)
    first = build_dry_run(configuration, snapshot)
    second = build_dry_run(configuration, snapshot)

    assert first.valid is True, render_json(first)
    assert first.input_hash == second.input_hash
    assert first.diff == second.diff
    assert first.summary["adopt"] == 3
    assert first.summary["create"] == 44
    assert first.summary["identity_conflicts"] == 0
    assert first.summary["base_mutations"] == 0
    assert snapshot == before
