"""Independent provider contract and batched scale checks for Wave 2B."""

from copy import deepcopy
from dataclasses import replace
from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import event
from tests.test_basic_data_wave2b import _authority_snapshot, _complete, _fixture, _items, _key

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import EnterpriseWorkspace
from app.main import app
from app.modules.basic_data.models import ProjectBasicDataItem
from app.modules.basic_data.schemas import ConfigurationCloneIn, ConfigurationUpdateIn
from app.modules.basic_data.service import BasicDataService
from app.modules.investment_evidence_policy.service import InvestmentEvidencePolicyService


def test_wave2b_available_provider_normalizes_completed_evidence_without_gate_policy_writes():
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db, count=2)
        before = _authority_snapshot(db, f["project"].id)
        gate = InvestmentEvidencePolicyService(db, f["author"].tenant_id, f["author"].id, f["preparer"].context)
        provider = gate.provider("BASIC_DATA_READINESS_PROVIDER")
        assert provider.status == "AVAILABLE" and provider.contract_valid
        requirement = {
            "provider_key": "BASIC_DATA_READINESS_PROVIDER",
            "evidence_type": "BASIC_DATA_READINESS",
            "scope": "EACH_PROJECT",
            "minimum_readiness_status": "READY",
        }
        payload, gap = gate.resolve_governed_payload(requirement, {}, f["project"].id)
        assert payload is None and gap == "SOURCE_EVIDENCE_UNAVAILABLE"
        _items(f)
        completed = _complete(f)
        payload, gap = gate.resolve_governed_payload(requirement, {}, f["project"].id)
        assert gap is None and payload["readiness_status"] == "READY" and payload["source_current"]
        assert payload["source_record_id"] == str(completed["id"])
        assert payload["evidence_hash"] == completed["assessment_hash"]
        assert gate.validate_provider_contract(payload) == []
        assert _authority_snapshot(db, f["project"].id) == before


def test_wave2b_hundreds_requirements_thousand_project_selector_use_batched_queries():
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db, count=1, fel=False)
        prep, final, actor, project = f["preparer"], f["final"], f["author"], f["project"]
        config = f["configuration"]
        draft = prep.clone_configuration(config["id"], config["version"], ConfigurationCloneIn(), _key("scale-clone"))
        content = deepcopy(draft["content_json"])
        requirement = content["requirements"][0]
        content["requirements"] = [
            dict(requirement, requirement_code=f"scale-{i}", name=f"Technical data {i}") for i in range(400)
        ]
        draft = prep.update_configuration(
            draft["id"],
            draft["version"],
            ConfigurationUpdateIn(name="Scale policy", content_json=content),
            _key("scale-edit"),
        )
        final.publish_configuration(draft["id"], draft["version"], _key("scale-publish"))
        db.add_all(
            [
                ProjectBasicDataItem(
                    tenant_id=actor.tenant_id,
                    project_workspace_id=project.id,
                    requirement_code=f"scale-{i}",
                    category=requirement["category"],
                    availability="AVAILABLE",
                    validation_state="VALIDATED",
                    quality="VALIDATED",
                    confidence="HIGH",
                    source_type="STUDY_REFERENCE",
                    source_reference=f"scale:{i}",
                    source_version="1",
                    source_hash="a" * 64,
                    source_date=utc_now().date(),
                    evidence_refs_json=[{"reference": f"scale-evidence:{i}"}],
                    created_by=actor.id,
                    updated_by=actor.id,
                )
                for i in range(400)
            ]
        )
        db.add_all(
            [
                EnterpriseWorkspace(
                    tenant_id=actor.tenant_id,
                    parent_id=f["enterprise"].id,
                    workspace_type_code="project",
                    code=f"scale-{project.id}-{i}",
                    record_code=f"SCALE.{project.id}.{i}",
                    name=f"Scale Project {i:04d}",
                    status="active",
                    defaults_json={},
                    created_by_user_id=actor.id,
                )
                for i in range(1000)
            ]
        )
        db.commit()
        statements = []

        def record(_conn, _cursor, sql, _parameters, _context, _many):
            statements.append(sql)

        started = perf_counter()
        event.listen(db.get_bind(), "before_cursor_execute", record)
        try:
            evaluated = prep.evaluate(project.id)
            page = prep.items(project.id, page=2, page_size=100)
            scoped = BasicDataService(
                db,
                actor.tenant_id,
                actor.id,
                replace(prep.context, organization_wide=False, workspace_ids=frozenset({f["enterprise"].id})),
            )
            options = scoped.options(page=3, page_size=100, search="Scale Project")
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", record)
        assert evaluated["coverage"]["required"] == 400 and evaluated["coverage"]["satisfied"] == 400
        assert page["total"] == 400 and len(page["items"]) == 100
        assert options["project_total"] == 1000 and len(options["projects"]) == 100
        assert len(statements) < 40, f"Unexpected row-per-query pattern: {len(statements)}"
        print(
            f"WAVE2B_BATCH_SCALE requirements=400 projects=1000 queries={len(statements)} elapsed={perf_counter() - started:.3f}s"
        )
