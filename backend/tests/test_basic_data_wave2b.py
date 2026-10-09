"""Wave 2B governed Basic Data, exact denominator and source independence."""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, func, inspect, select
from tests.test_capital_allocation_wave2a import _context, _foundation, _token_headers, _user

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import (
    AdminConfiguration,
    EnterpriseWorkspace,
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRole,
    SecurityRolePermission,
)
from app.main import app
from app.modules.basic_data.models import BasicDataCommand, BasicDataReadinessAssessment, ProjectBasicDataItem
from app.modules.basic_data.schemas import (
    AssessmentActionIn,
    AssessmentCreateIn,
    ConfigurationCloneIn,
    ConfigurationPreviewIn,
    ConfigurationUpdateIn,
    ItemCreateIn,
    ItemUpdateIn,
    ItemValidateIn,
)
from app.modules.basic_data.service import DEFAULT_CONFIGURATION, BasicDataService, _hash
from app.modules.enterprise_structure.permissions import ensure_enterprise_permissions
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.investment_gate_preparation.models import InvestmentGatePreparation
from app.modules.project_definition.models import ProjectDefinitionAssessment, ProjectFELStatus
from app.modules.project_definition.schemas import AssessmentCreateIn as FELAssessmentCreateIn
from app.modules.project_definition.schemas import AssessmentUpdateIn as FELAssessmentUpdateIn
from app.modules.project_definition.schemas import ElementResultIn, StartFELIn
from app.modules.project_definition.service import CONFIGURATION_KIND as FEL_KIND
from app.modules.project_definition.service import DEFAULT_FRAMEWORK, ProjectDefinitionService
from app.modules.risk_readiness.models import ProjectRisk, RiskReadinessAssessment

MINING_CATEGORIES = (
    "geology",
    "geotechnical",
    "hydrogeology",
    "metallurgy",
    "survey",
    "environmental",
    "interfaces",
    "operations",
    "utilities",
    "design-criteria",
)


def _key(action):
    return f"wave2b-basic-{action}-{uuid4()}"


def _workspace(db, author, parent, kind="project", *, project_type="MINING", governance="CAPITAL_OWNER"):
    token = uuid4().hex[:10]
    row = EnterpriseWorkspace(
        tenant_id=author.tenant_id,
        parent_id=parent.id,
        workspace_type_code=kind,
        code=f"W2B-{kind}-{token}",
        record_code=f"W2B.{kind}.{token}",
        name=f"Wave 2B {kind} {token}",
        status="active",
        defaults_json={
            "_project": {
                "project_type": project_type,
                "governance_model": governance,
                "industry": "MINING",
                "gate_profile": "PYP-FFA",
                "fel_stage": "FEL-2",
                "location": "CO",
                "complexity": "HIGH",
                "risk": "HIGH",
                "uncertainty": "HIGH",
            }
        },
        version=1,
        created_by_user_id=author.id,
    )
    db.add(row)
    db.commit()
    return row


def _mining_configuration(scope_id, count=10):
    content = deepcopy(DEFAULT_CONFIGURATION)
    content["scope"] = {"type": "enterprise", "workspace_id": scope_id}
    content["applicability"] = {
        "governance_models": ["CAPITAL_OWNER"],
        "project_types": ["MINING"],
        "industries": ["MINING"],
    }
    content["categories"] = [{"code": name, "name": name.title()} for name in MINING_CATEGORIES[:count]]
    content["requirements"] = [
        {
            "requirement_code": name,
            "category": name,
            "name": f"{name.title()} technical input",
            "blocking": name == "geotechnical",
            "minimum_quality": "VALIDATED",
            "minimum_confidence": "HIGH",
            "minimum_validation_state": "VALIDATED",
            "minimum_availability": "AVAILABLE",
            "max_age_days": index + 30,
            "evidence_required": True,
            "applicability": {"gate_profiles": ["PYP-FFA"], "fel_stages": ["FEL-2", "FEL-3"]},
            "stage_rules": {
                "FEL-2": {"minimum_quality": "PRELIMINARY", "minimum_confidence": "PRELIMINARY"},
                "FEL-3": {"minimum_quality": "VALIDATED", "minimum_confidence": "HIGH"},
            },
        }
        for index, name in enumerate(MINING_CATEGORIES[:count])
    ]
    return content


def _fixture(db, *, count=10, fel=True):
    author, enterprise, _ = _foundation(db)
    reviewer = _user(db, author.tenant_id, "wave2b-basic-reviewer")
    ensure_enterprise_permissions(db, author.tenant_id, author.id)
    db.commit()
    project = _workspace(db, author, enterprise)
    preparer = BasicDataService(db, author.tenant_id, author.id, _context(author, "project_definition_manager"))
    final = BasicDataService(db, author.tenant_id, reviewer.id, _context(reviewer, "definition_reviewer"))
    seed = preparer.ensure_seed()
    draft = preparer.clone_configuration(
        seed.id,
        seed.version,
        ConfigurationCloneIn(code=f"wave2b-mining-{uuid4().hex[:10]}", target_workspace_id=enterprise.id),
        _key("clone"),
    )
    content = _mining_configuration(enterprise.id, count)
    draft = preparer.update_configuration(
        draft["id"],
        draft["version"],
        ConfigurationUpdateIn(name="Mining data requirements", content_json=content),
        _key("edit"),
    )
    published = final.publish_configuration(draft["id"], draft["version"], _key("publish"))
    result = {
        "author": author,
        "reviewer": reviewer,
        "enterprise": enterprise,
        "project": project,
        "preparer": preparer,
        "final": final,
        "configuration": published,
    }
    if fel:
        framework_content = deepcopy(DEFAULT_FRAMEWORK)
        framework_content["scope"] = {"type": "enterprise", "workspace_id": enterprise.id}
        framework = AdminConfiguration(
            tenant_id=author.tenant_id,
            kind=FEL_KIND,
            code=f"wave2b-definition-{uuid4().hex[:10]}",
            name="Wave 2B definition fixture",
            status="published",
            revision=1,
            version=1,
            content_json=framework_content,
            content_hash=_hash(framework_content),
            created_by_user_id=author.id,
            published_at=utc_now(),
        )
        db.add(framework)
        db.commit()
        definition = ProjectDefinitionService(db, author.tenant_id, author.id)
        definition.start_fel(
            project.id,
            StartFELIn(
                stage_code="FEL-2",
                framework_configuration_id=framework.id,
                entry_justification="Governed existing FEL-2 context",
                source_evidence=[{"reference": "scope-baseline"}],
                idempotency_key=_key("fel-start"),
            ),
        )
        assessment = definition.create_assessment(project.id, FELAssessmentCreateIn(idempotency_key=_key("definition")))
        assessment = definition.update_assessment(
            assessment.id,
            assessment.revision_version,
            FELAssessmentUpdateIn(
                element_results=[
                    ElementResultIn(
                        element_key=element["element_key"],
                        category_key=element["category_key"],
                        score=100,
                        evidence_refs=[{"reference": "verified-definition-input"}],
                    )
                    for element in framework_content["assessment_elements"]
                    if "FEL-2" in element["stages"]
                ],
                evidence_refs=[{"reference": "definition-package"}],
            ),
        )
        result["definition"] = definition.complete_assessment(
            assessment.id, assessment.revision_version, _key("definition-complete")
        )
    return result


def _item_payload(code, **updates):
    return ItemCreateIn(
        requirement_code=code,
        availability="AVAILABLE",
        quality="PRELIMINARY",
        confidence="PRELIMINARY",
        source_type="STUDY_REFERENCE",
        source_reference=f"study:{code}",
        source_version="1",
        source_hash=_hash({"study": code, "version": 1}),
        source_date=utc_now().date(),
        evidence_refs=[{"reference": f"evidence:{code}", "version": "1"}],
        **updates,
    )


def _items(fixture, *, omit=()):
    service, project = fixture["preparer"], fixture["project"]
    rows = []
    for r in service.requirements(project.id)["requirements"]:
        if r["requirement_code"] not in omit:
            row = service.create_item(project.id, _item_payload(r["requirement_code"]), _key("item"))
            rows.append(
                service.validate_item(
                    row["id"], row["revision_version"], ItemValidateIn(validation_state="VALIDATED"), _key("validate")
                )
            )
    return rows


def _complete(fixture):
    prep, final, project = fixture["preparer"], fixture["final"], fixture["project"]
    row = prep.create_assessment(project.id, AssessmentCreateIn(), _key("assessment"))
    row = prep.submit(row["id"], row["revision_version"], AssessmentActionIn(), _key("submit"))
    return final.complete(row["id"], row["revision_version"], AssessmentActionIn(), _key("complete"))


def _authority_snapshot(db, project_id):
    result = {}
    for model in (
        ProjectFELStatus,
        ProjectDefinitionAssessment,
        ProjectRisk,
        RiskReadinessAssessment,
        InvestmentGatePreparation,
        InvestmentDecision,
    ):
        table = model.__table__
        columns = {c.name for c in table.columns}
        scope = (
            table.c.project_workspace_id == project_id
            if "project_workspace_id" in columns
            else table.c.tenant_id == db.get(EnterpriseWorkspace, project_id).tenant_id
        )
        records = db.execute(select(table).where(scope).order_by(table.c.id)).mappings().all()
        result[model.__name__] = _hash([dict(r) for r in records])
    result["published_gate_policy"] = _hash(
        [
            {"id": r.id, "hash": r.content_hash, "content": r.content_json}
            for r in db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.kind == "investment_evidence_policy", AdminConfiguration.status == "published"
                )
            ).all()
        ]
    )
    return result


def test_basic_data_mining_happy_path_exact_denominator_provider_and_authority_independence():
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db)
        authority = _authority_snapshot(db, f["project"].id)
        _items(f)
        preview = f["preparer"].evaluate(f["project"].id)
        assert preview["coverage"] == {"required": 10, "satisfied": 10, "partial": 0, "missing": 0, "percentage": 100.0}
        assert preview["status"] == "READY"
        assert preview["context"]["fel_stage"] == "FEL-2"
        assert preview["context"]["fel_provider_key"] == "GATE07J_FEL_PROJECT_DEFINITION"
        assert preview["context"]["definition_assessment"]["hash"] == f["definition"].assessment_hash
        row = _complete(f)
        assert row["status"] == "COMPLETED" and row["assessment_number"].startswith("BDA-")
        assert len(row["assessment_hash"]) == 64
        source = f["preparer"].provider_evidence(f["project"].id)
        assert source["status"] == "AVAILABLE" and source["readiness_status"] == "READY" and source["source_current"]
        assert source["evidence_hash"] == row["assessment_hash"]
        assert _authority_snapshot(db, f["project"].id) == authority


def test_basic_data_90_percent_cannot_hide_critical_missing_geotechnical():
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db)
        _items(f, omit={"geotechnical"})
        row = _complete(f)
        snapshot = row["snapshot_json"]
        assert snapshot["coverage"] == {"required": 10, "satisfied": 9, "partial": 0, "missing": 1, "percentage": 90.0}
        assert snapshot["critical_gaps"] == ["geotechnical"] and snapshot["status"] == "BLOCKED"
        assert f["preparer"].provider_evidence(f["project"].id)["status"] == "UNAVAILABLE"


def test_basic_data_exact_partial_missing_counts_are_not_hidden_average():
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db)
        _items(f, omit={"geotechnical", "survey"})
        f["preparer"].create_item(f["project"].id, _item_payload("survey"), _key("partial"))
        result = f["preparer"].evaluate(f["project"].id)
        assert result["coverage"] == {"required": 10, "satisfied": 8, "partial": 1, "missing": 1, "percentage": 80.0}
        assert result["dimensions"]["VALIDATION_READINESS"]["satisfied"] == 8


def test_basic_data_expired_source_marks_current_stale_not_historical_snapshot(monkeypatch):
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db)
        _items(f)
        row = _complete(f)
        frozen = deepcopy(row["snapshot_json"])
        frozen_hash = row["assessment_hash"]
        instant = utc_now() + timedelta(days=31)
        monkeypatch.setattr("app.modules.basic_data.service.utc_now", lambda: instant)
        current = f["preparer"].current_readiness(f["project"].id)
        assert current["status"] == "STALE" and not current["source_current"]
        assert current["stale_reasons"]["stale_sources"] == ["geology", "geotechnical"][:1]
        assert f["preparer"].assessment(row["id"])["snapshot_json"] == frozen
        assert f["preparer"].assessment(row["id"])["assessment_hash"] == frozen_hash
        assert f["preparer"].provider_evidence(f["project"].id)["status"] == "UNAVAILABLE"


def test_basic_data_stage_preliminary_acceptable_fel2_blocked_fel3_pdri_unchanged():
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db)
        _items(f)
        before = deepcopy(f["preparer"].evaluate(f["project"].id))
        assert before["status"] == "READY"
        definition = db.get(ProjectDefinitionAssessment, f["definition"].id)
        score_hash = (definition.normalized_score, definition.assessment_hash, _hash(definition.source_snapshot_json))
        status = db.scalar(select(ProjectFELStatus).where(ProjectFELStatus.project_workspace_id == f["project"].id))
        # The source authority changes its own stage; Basic Data only consumes it.
        status.current_stage_code = "FEL-3"
        status.revision_version += 1
        db.commit()
        after = f["preparer"].evaluate(f["project"].id)
        assert after["status"] == "BLOCKED" and after["coverage"]["satisfied"] == 0
        assert after["dimensions"]["QUALITY_READINESS"]["satisfied"] == 0
        assert after["dimensions"]["VALIDATION_READINESS"]["satisfied"] == 10
        assert (
            definition.normalized_score,
            definition.assessment_hash,
            _hash(definition.source_snapshot_json),
        ) == score_hash
        assert status.current_stage_code == "FEL-3"


def test_basic_data_source_change_refresh_preview_apply_and_latest_governed_result():
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db)
        items = _items(f)
        prior = _complete(f)
        frozen = deepcopy(prior)
        item = items[0]
        changed = ItemUpdateIn(**{k: v for k, v in item.items() if k in ItemUpdateIn.model_fields}).model_copy(
            update={"source_version": "2", "source_hash": "b" * 64}
        )
        item = f["preparer"].update_item(item["id"], item["revision_version"], changed, _key("source-change"))
        assert item["validation_state"] == "NOT_VALIDATED" and item["validated_at"] is None
        preview = f["preparer"].refresh_preview(prior["id"])
        assert not preview["persisted"] and preview["deltas"]["changed_items"] == ["geology"]
        assert f["preparer"].current_readiness(f["project"].id)["status"] == "STALE"
        successor = f["preparer"].refresh_apply(
            prior["id"], prior["revision_version"], AssessmentActionIn(), _key("refresh")
        )
        assert successor["status"] == "DRAFT" and successor["predecessor_id"] == prior["id"]
        successor = f["preparer"].submit(
            successor["id"], successor["revision_version"], AssessmentActionIn(), _key("resubmit")
        )
        successor = f["final"].complete(
            successor["id"], successor["revision_version"], AssessmentActionIn(), _key("recomplete")
        )
        assert successor["snapshot_json"]["status"] == "BLOCKED"
        source = f["preparer"].provider_evidence(f["project"].id)
        assert source["assessment_id"] == successor["id"] and source["status"] == "UNAVAILABLE"
        historical = f["preparer"].assessment(prior["id"])
        assert {k: v for k, v in historical.items() if k != "allowed_actions"} == {
            k: v for k, v in frozen.items() if k != "allowed_actions"
        }
        assert f["preparer"].assessments(f["project"].id)["total"] == 2


def test_basic_data_sod_etag_payload_bound_retries_and_completed_orm_immutability():
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db, count=1)
        prep = f["preparer"]
        key = _key("item-retry")
        payload = _item_payload("geology")
        item = prep.create_item(f["project"].id, payload, key)
        assert prep.create_item(f["project"].id, payload, key) == item
        with pytest.raises(HTTPException) as reused:
            prep.create_item(f["project"].id, payload.model_copy(update={"source_version": "2"}), key)
        assert reused.value.detail["code"] == "IDEMPOTENCY_KEY_REUSED"
        with pytest.raises(HTTPException) as etag:
            prep.validate_item(item["id"], 99, ItemValidateIn(validation_state="VALIDATED"), _key("wrong-etag"))
        assert etag.value.status_code == 412
        row = prep.create_assessment(f["project"].id, AssessmentCreateIn(), _key("sod"))
        row = prep.submit(row["id"], row["revision_version"], AssessmentActionIn(), _key("sod-submit"))
        with pytest.raises(HTTPException) as sod:
            prep.complete(row["id"], row["revision_version"], AssessmentActionIn(), _key("sod-complete"))
        assert sod.value.status_code == 403
        complete_key = _key("complete-retry")
        result = f["final"].complete(row["id"], row["revision_version"], AssessmentActionIn(), complete_key)
        assert f["final"].complete(row["id"], row["revision_version"], AssessmentActionIn(), complete_key) == result
        entity = db.get(BasicDataReadinessAssessment, row["id"])
        entity.comments = "Unauthorized historical rewrite"
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()
        entity = db.get(BasicDataReadinessAssessment, row["id"])
        db.delete(entity)
        with pytest.raises(ValueError, match="cannot be deleted"):
            db.commit()
        db.rollback()


def test_basic_data_policy_configuration_change_stales_current_and_preview_is_readonly():
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db, count=1)
        _items(f)
        old = _complete(f)
        prep, final = f["preparer"], f["final"]
        configuration = f["configuration"]
        key = _key("policy-clone")
        clone_payload = ConfigurationCloneIn()
        draft = prep.clone_configuration(configuration["id"], configuration["version"], clone_payload, key)
        assert prep.clone_configuration(configuration["id"], configuration["version"], clone_payload, key) == draft
        content = deepcopy(draft["content_json"])
        content["requirements"][0]["stage_rules"]["FEL-2"]["minimum_quality"] = "VALIDATED"
        draft = prep.update_configuration(
            draft["id"],
            draft["version"],
            ConfigurationUpdateIn(name=draft["name"], content_json=content),
            _key("policy-change"),
        )
        counts = {
            model: db.scalar(select(func.count()).select_from(model))
            for model in (BasicDataReadinessAssessment, BasicDataCommand, ProjectBasicDataItem, SecurityEvent)
        }
        preview = prep.configuration_preview(
            ConfigurationPreviewIn(configuration_id=draft["id"], project_id=f["project"].id)
        )
        assert not preview["persisted"] and preview["readiness"]["status"] == "BLOCKED"
        assert all(db.scalar(select(func.count()).select_from(model)) == count for model, count in counts.items())
        with pytest.raises(HTTPException) as sod:
            prep.publish_configuration(draft["id"], draft["version"], _key("policy-sod"))
        assert sod.value.status_code == 403
        published_key = _key("policy-publish")
        published = final.publish_configuration(draft["id"], draft["version"], published_key)
        assert final.publish_configuration(draft["id"], draft["version"], published_key) == published
        assert prep.current_readiness(f["project"].id)["status"] == "STALE"
        assert prep.assessment(old["id"])["snapshot_json"] == old["snapshot_json"]
        with pytest.raises(HTTPException) as immutable:
            prep.update_configuration(
                published["id"],
                published["version"],
                ConfigurationUpdateIn(name="No rewrite", content_json=content),
                _key("published-edit"),
            )
        assert immutable.value.status_code == 409
        final.archive_configuration(published["id"], published["version"], _key("archive"))


def test_basic_data_project_type_governance_gate_tailoring_are_independent():
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db, fel=False)
        other_type = _workspace(db, f["author"], f["enterprise"], project_type="BUILDING")
        contractor = _workspace(db, f["author"], f["enterprise"], governance="CONTRACTOR_DELIVERY")
        internal = _workspace(db, f["author"], f["enterprise"], governance="DIRECT_INTERNAL")
        assert f["preparer"].requirements(f["project"].id)["applicable"]
        assert not f["preparer"].requirements(other_type.id)["applicable"]
        assert not f["preparer"].requirements(contractor.id)["applicable"]
        assert not f["preparer"].requirements(internal.id)["applicable"]
        changed = deepcopy(f["project"].defaults_json)
        changed["_project"]["gate_profile"] = "PYP-INV-SELECT"
        f["project"].defaults_json = changed
        db.commit()
        assert f["preparer"].requirements(f["project"].id)["requirements"] == []


def _grant(db, user, role_code, permissions=None, workspace_id=None):
    role = db.scalar(
        select(SecurityRole).where(SecurityRole.tenant_id == user.tenant_id, SecurityRole.code == role_code)
    )
    if role is None:
        role = SecurityRole(tenant_id=user.tenant_id, code=role_code, name=role_code, is_system=False, status="active")
        db.add(role)
        db.flush()
    if permissions:
        for permission in permissions:
            catalog = db.scalar(select(PermissionCatalog).where(PermissionCatalog.key == permission))
            db.add(
                SecurityRolePermission(
                    tenant_id=user.tenant_id, role_id=role.id, permission_id=catalog.id, granted_by_user_id=user.id
                )
            )
    db.add(
        SecurityAccessAssignment(
            tenant_id=user.tenant_id,
            subject_type="user",
            user_id=user.id,
            role_id=role.id,
            scope_type="workspace" if workspace_id else "organization",
            workspace_id=workspace_id,
            status="active",
            granted_by_user_id=user.id,
        )
    )
    db.commit()


def test_basic_data_direct_route_permissions_scope_validation_no_get_seeding_and_pagination():
    with TestClient(app) as client, SessionLocal() as db:
        f = _fixture(db, count=1)
        _items(f)
        row = f["preparer"].create_assessment(f["project"].id, AssessmentCreateIn(), _key("route-assessment"))
        row = f["preparer"].submit(row["id"], row["revision_version"], AssessmentActionIn(), _key("route-submit"))
        user = _user(db, f["author"].tenant_id, "basic-assessor")
        config_actor = _user(db, user.tenant_id, "basic-config-only")
        unauthorized = _user(db, user.tenant_id, "basic-sibling")
        validator = _user(db, user.tenant_id, "basic-validator-only")
        _grant(db, user, "definition_assessor", workspace_id=f["project"].id)
        _grant(db, config_actor, "project_definition_configuration_admin")
        other = _workspace(db, f["author"], f["enterprise"])
        _grant(db, unauthorized, "project_definition_viewer", workspace_id=other.id)
        _grant(
            db,
            validator,
            f"custom-validator-{uuid4().hex[:8]}",
            {"basic_data.item.validate", "basic_data.read"},
            f["project"].id,
        )
        headers = {**_token_headers(user), "If-Match": str(row["revision_version"]), "Idempotency-Key": _key("route")}
        assert (
            client.get(
                f"/api/v1/basic-data/projects/{f['project'].id}/items?page=1&page_size=1", headers=headers
            ).json()["total"]
            == 1
        )
        assert (
            client.post(f"/api/v1/basic-data/assessments/{row['id']}/complete", json={}, headers=headers).status_code
            == 403
        )
        assert client.post("/api/v1/basic-data/admin/configurations/1/publish", headers=headers).status_code == 403
        assert (
            client.post(
                f"/api/v1/basic-data/assessments/{row['id']}/complete",
                json={},
                headers={**headers, **_token_headers(config_actor)},
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/basic-data/assessments/{row['id']}/complete",
                json={},
                headers={**headers, **_token_headers(validator)},
            ).status_code
            == 403
        )
        assert (
            client.get(
                f"/api/v1/basic-data/projects/{f['project'].id}/requirements", headers=_token_headers(unauthorized)
            ).status_code
            == 403
        )
        assert client.get("/api/v1/basic-data/admin/configurations", headers=_token_headers(user)).status_code == 403
        before = db.scalar(select(func.count()).select_from(SecurityEvent))
        assert (
            client.get(f"/api/v1/basic-data/projects/{f['project'].id}/requirements", headers=headers).status_code
            == 200
        )
        assert (
            client.get(f"/api/v1/basic-data/projects/{f['project'].id}/current-readiness", headers=headers).status_code
            == 200
        )
        assert db.scalar(select(func.count()).select_from(SecurityEvent)) == before
        item = f["preparer"].items(f["project"].id)["items"][0]
        validate_headers = {
            **_token_headers(validator),
            "If-Match": str(item["revision_version"]),
            "Idempotency-Key": _key("direct-validate"),
        }
        assert (
            client.post(
                f"/api/v1/basic-data/items/{item['id']}/validate",
                json={"validation_state": "VALIDATED"},
                headers=validate_headers,
            ).status_code
            == 200
        )
        assert (
            "assessment_complete"
            not in client.get("/api/v1/basic-data/options", headers=_token_headers(validator)).json()["allowed_actions"]
        )
        validator_role_id = db.scalar(
            select(SecurityAccessAssignment.role_id).where(SecurityAccessAssignment.user_id == validator.id)
        )
        role = db.get(SecurityRole, validator_role_id)
        role.status = "inactive"
        db.commit()
        assert client.get("/api/v1/basic-data/options", headers=_token_headers(validator)).status_code == 403
        role.status = "active"
        db.commit()


def test_basic_data_workspace_scope_ancestor_allowed_sibling_denied_and_cross_tenant_hidden():
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db, count=1, fel=False)
        sibling = _workspace(db, f["author"], f["enterprise"])
        scoped = replace(
            _context(f["reviewer"], "definition_reviewer"),
            organization_wide=False,
            workspace_ids=frozenset({f["project"].id}),
        )
        service = BasicDataService(db, f["author"].tenant_id, f["reviewer"].id, scoped)
        assert service.requirements(f["project"].id)["configuration"]["id"] == f["configuration"]["id"]
        with pytest.raises(HTTPException) as denied:
            service.requirements(sibling.id)
        assert denied.value.status_code == 403
        outside = BasicDataService(db, 999999, f["reviewer"].id)
        with pytest.raises(HTTPException) as hidden:
            outside.requirements(f["project"].id)
        assert hidden.value.status_code == 404


def test_basic_data_register_batch_query_count_and_schema_contract():
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db)
        _items(f)
        statements = []

        def record(_conn, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement)

        event.listen(db.get_bind(), "before_cursor_execute", record)
        try:
            result = f["preparer"].items(f["project"].id, page_size=10)
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", record)
        assert len(result["items"]) == 10 and len(statements) < 12
        for table in (
            ProjectBasicDataItem.__table__,
            BasicDataReadinessAssessment.__table__,
            BasicDataCommand.__table__,
        ):
            actual = inspect(db.get_bind()).get_columns(table.name)
            assert {c["name"] for c in actual} == {c.name for c in table.columns}
        events = set(
            db.scalars(select(SecurityEvent.event_type).where(SecurityEvent.tenant_id == f["author"].tenant_id)).all()
        )
        assert {
            "basic_data.config.cloned",
            "basic_data.config.published",
            "basic_data.item.created",
            "basic_data.item.validated",
        } <= events


def test_basic_data_configuration_sod_cannot_be_disabled_by_author_or_any_draft_editor():
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db, count=1, fel=False)
        prep, editor = f["preparer"], f["final"]
        config = f["configuration"]
        draft = prep.clone_configuration(config["id"], config["version"], ConfigurationCloneIn(), _key("sod-clone"))
        content = deepcopy(draft["content_json"])
        content["separation_of_duties"]["author_cannot_publish"] = False
        draft = editor.update_configuration(
            draft["id"],
            draft["version"],
            ConfigurationUpdateIn(name="Review-required SoD downgrade", content_json=content),
            _key("sod-editor"),
        )
        for actor in (prep, editor):
            with pytest.raises(HTTPException) as denied:
                actor.publish_configuration(draft["id"], draft["version"], _key("sod-self-publish"))
            assert denied.value.status_code == 403
        independent = _user(db, f["author"].tenant_id, "independent-policy-authority")
        publisher = BasicDataService(db, independent.tenant_id, independent.id, _context(independent))
        published = publisher.publish_configuration(draft["id"], draft["version"], _key("sod-independent-publish"))
        assert published["status"] == "published"
        assert published["content_json"]["separation_of_duties"]["author_cannot_publish"] is False


@pytest.mark.parametrize(
    "replacement",
    [
        {"requirements": ["invalid"]},
        {"categories": [42]},
        {"coverage_rules": []},
        {"separation_of_duties": "false"},
        {"numbering": []},
    ],
)
def test_basic_data_invalid_declarative_configuration_returns_controlled_issues(replacement):
    with TestClient(app), SessionLocal() as db:
        f = _fixture(db, count=1, fel=False)
        content = deepcopy(f["configuration"]["content_json"])
        content.update(replacement)
        preview = f["preparer"].configuration_preview(ConfigurationPreviewIn(content_json=content))
        assert preview["persisted"] is False and preview["issues"]
