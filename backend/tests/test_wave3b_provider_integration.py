"""Independent normalized provider, source-boundary and batched-scale checks."""

from copy import deepcopy
from dataclasses import replace
from time import perf_counter
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event, select
from tests.provision_wave3b_browser import prepare_source_contexts
from tests.test_capital_allocation_wave2a import _context, _foundation
from tests.test_owner_capability_wave3b import _complete, _draft, _fixture, _items, _key

from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, EnterpriseWorkspace
from app.main import app
from app.modules.investment_evidence_policy.service import InvestmentEvidencePolicyService
from app.modules.owner_capability.schemas import ConfigurationCloneIn, ConfigurationUpdateIn
from app.modules.owner_capability.service import OwnerCapabilityService, _hash


def _published_gate_snapshot(db):
    return [
        (row.id, row.version, row.revision, row.content_hash, deepcopy(row.content_json))
        for row in db.scalars(
            select(AdminConfiguration)
            .where(AdminConfiguration.kind == "investment_evidence_policy", AdminConfiguration.status == "published")
            .order_by(AdminConfiguration.id)
        )
    ]


def test_wave3b_provider_catalog_available_does_not_publish_gate_requirements_or_fake_evidence():
    with TestClient(app), SessionLocal() as db:
        actor, enterprise, _ = _foundation(db)
        project = EnterpriseWorkspace(
            tenant_id=actor.tenant_id,
            parent_id=enterprise.id,
            workspace_type_code="project",
            code=f"W3B-provider-empty-{uuid4().hex[:8]}",
            record_code=f"W3B.provider.{uuid4().hex[:8]}",
            name="Owner provider with no assessment",
            status="active",
            defaults_json={"_project": {"governance_model": "CAPITAL_OWNER", "project_type": "MINING"}},
            created_by_user_id=actor.id,
        )
        db.add(project)
        db.commit()
        before = _published_gate_snapshot(db)
        gate = InvestmentEvidencePolicyService(
            db, actor.tenant_id, actor.id, _context(actor, "project_definition_manager")
        )
        provider = gate.provider("OWNER_CAPABILITY_READINESS_PROVIDER")
        assert provider.status == "AVAILABLE" and provider.contract_valid
        requirement = {
            "provider_key": "OWNER_CAPABILITY_READINESS_PROVIDER",
            "evidence_type": "OWNER_CAPABILITY_READINESS",
            "scope": "EACH_PROJECT",
            "minimum_readiness_status": "READY",
        }
        payload, gap = gate.resolve_governed_payload(requirement, {}, project.id)
        assert payload is None and gap == "SOURCE_EVIDENCE_UNAVAILABLE"
        assert _published_gate_snapshot(db) == before


def _authority_snapshot(db, tenant_id):
    names = (
        "portfolio_resource_scenarios",
        "portfolio_resource_scenario_projects",
        "commercial_contracting_strategies",
        "commercial_strategy_versions",
        "project_fel_statuses",
        "project_definition_assessments",
        "project_risks",
        "risk_readiness_assessments",
        "project_basic_data_items",
        "basic_data_readiness_assessments",
        "investment_gate_preparations",
        "investment_decisions",
    )
    from app.database.session import Base

    result = {}
    for name in names:
        table = Base.metadata.tables[name]
        rows = db.execute(select(table).where(table.c.tenant_id == tenant_id).order_by(table.c.id)).mappings()
        result[name] = _hash([dict(row) for row in rows])
    result["non_owner_policies"] = _hash(
        [
            {column.key: getattr(row, column.key) for column in AdminConfiguration.__table__.columns}
            for row in db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == tenant_id,
                    AdminConfiguration.kind != "owner_capability_readiness_configuration",
                )
                .order_by(AdminConfiguration.id)
            )
        ]
    )
    return result


def test_wave3b_real_fel3_commercial_basic_resource_context_and_normalized_provider_never_mutate_sources():
    with TestClient(app), SessionLocal() as db:
        fixture = _fixture(db, count=2)
        sources = prepare_source_contexts(db, fixture)
        assert sources["fel_pdri"]["fel_stage"] == "FEL-3"
        assert sources["commercial"]["status"] == "COMPLETED" and sources["commercial"]["hash"]
        assert sources["resources"]["status"] == "AVAILABLE"
        assert sources["resources"]["scenarios"][0]["status"] == "DRAFT"
        assert sources["basic_data"]["status"] == "READY"
        before = _authority_snapshot(db, fixture["author"].tenant_id)
        gate = InvestmentEvidencePolicyService(
            db, fixture["author"].tenant_id, fixture["author"].id, fixture["preparer"].context
        )
        requirement = {
            "provider_key": "OWNER_CAPABILITY_READINESS_PROVIDER",
            "evidence_type": "OWNER_CAPABILITY_READINESS",
            "scope": "EACH_PROJECT",
            "minimum_readiness_status": "READY",
        }
        row = _draft(fixture)
        payload, gap = gate.resolve_governed_payload(requirement, {}, fixture["project"].id)
        assert payload is None and gap == "SOURCE_EVIDENCE_UNAVAILABLE"
        completed = _complete(fixture, row)
        payload, gap = gate.resolve_governed_payload(requirement, {}, fixture["project"].id)
        assert gap is None and payload["readiness_status"] == "READY" and payload["source_current"]
        assert payload["source_record_id"] == str(completed["id"])
        assert payload["evidence_hash"] == completed["assessment_hash"]
        assert gate.validate_provider_contract(payload) == []
        assert _authority_snapshot(db, fixture["author"].tenant_id) == before


def test_wave3b_hundreds_requirements_thousand_project_selector_no_row_per_query_pattern():
    with TestClient(app), SessionLocal() as db:
        fixture = _fixture(db, count=1, fel=False)
        preparer, final = fixture["preparer"], fixture["final"]
        configuration = fixture["configuration"]
        draft = preparer.clone_configuration(
            configuration["id"], configuration["version"], ConfigurationCloneIn(), _key("scale-clone")
        )
        content = deepcopy(draft["content_json"])
        requirement = content["requirements"][0]
        content["requirements"] = [
            dict(requirement, requirement_code=f"scale-{i}", name=f"Owner requirement {i}") for i in range(400)
        ]
        draft = preparer.update_configuration(
            draft["id"],
            draft["version"],
            ConfigurationUpdateIn(name="Scale Owner policy", content_json=content),
            _key("scale-update"),
        )
        published = final.publish_configuration(draft["id"], draft["version"], _key("scale-publish"))
        actor, project = fixture["author"], fixture["project"]
        db.add_all(
            [
                EnterpriseWorkspace(
                    tenant_id=actor.tenant_id,
                    parent_id=fixture["enterprise"].id,
                    workspace_type_code="project",
                    code=f"owner-scale-{project.id}-{i}",
                    record_code=f"OWNER.SCALE.{project.id}.{i}",
                    name=f"Scale Owner Project {i:04d}",
                    status="active",
                    defaults_json={},
                    created_by_user_id=actor.id,
                )
                for i in range(1000)
            ]
        )
        db.commit()
        scoped = OwnerCapabilityService(
            db,
            actor.tenant_id,
            actor.id,
            replace(
                preparer.context,
                organization_wide=False,
                workspace_ids=frozenset({fixture["enterprise"].id}),
            ),
        )
        statements = []

        def record(_conn, _cursor, sql, _parameters, _context, _many):
            statements.append(sql)

        started = perf_counter()
        event.listen(db.get_bind(), "before_cursor_execute", record)
        try:
            evaluated = preparer.evaluate(
                project.id,
                {
                    "items": [item.model_dump(mode="json") for item in _items(published["content_json"])],
                    "gaps": [],
                    "mitigations": [],
                },
            )
            options = scoped.options(page=3, page_size=100, search="Scale Owner Project")
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", record)
        assert evaluated["coverage"]["required"] == 400 and evaluated["coverage"]["satisfied"] == 400
        assert options["project_total"] == 1000 and len(options["projects"]) == 100
        assert len(statements) < 80, f"Unexpected per-requirement/per-Project query pattern: {len(statements)}"
        print(
            f"WAVE3B_BATCH_SCALE requirements=400 projects=1000 queries={len(statements)} elapsed={perf_counter() - started:.3f}s"
        )
