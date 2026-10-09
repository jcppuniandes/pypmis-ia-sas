"""Wave 2B Risk policy acceptance, independent of Project risk/Gate authority."""

from copy import deepcopy
from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, select, text
from tests.test_capital_allocation_wave2a import _context, _token_headers, _user
from tests.test_risk_readiness_gate07j_risk import _complete as _complete_risk
from tests.test_risk_readiness_gate07j_risk import _low_risk
from tests.test_risk_readiness_gate07j_risk import _publish as _publish_risk

from app.database.session import SessionLocal
from app.domain.models import (
    AdminConfiguration,
    EnterpriseWorkspace,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRole,
    UserAccount,
)
from app.main import app
from app.modules.enterprise_structure.permissions import ensure_enterprise_permissions
from app.modules.risk_governance.schemas import ConfigurationPreviewIn, EffectiveContextIn, ThresholdEvaluationIn
from app.modules.risk_governance.service import CONFIGURATION_KIND, DEFAULT_CONFIGURATION, RiskGovernanceService
from app.modules.risk_readiness.models import RiskReadinessAssessment
from app.modules.risk_readiness.service import RiskReadinessService


def _key(operation):
    return f"wave2b-risk-{operation}-{uuid4()}"


def _workspace(db, actor, workspace_type, parent=None, **defaults):
    token = uuid4().hex[:10]
    record = EnterpriseWorkspace(
        tenant_id=actor.tenant_id,
        parent_id=parent.id if parent else None,
        workspace_type_code=workspace_type,
        code=f"W2B-{workspace_type}-{token}",
        record_code=f"W2B.{token}",
        name=f"Risk context {workspace_type}",
        status="active",
        defaults_json=defaults,
        created_by_user_id=actor.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _fixture(db):
    author = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
    reviewer = _user(db, author.tenant_id, "risk-governance-reviewer")
    service = RiskGovernanceService(db, author.tenant_id, author.id, _context(author, "configuration_admin"))
    service.ensure_seed()
    authority = RiskGovernanceService(db, author.tenant_id, reviewer.id, _context(reviewer, "configuration_admin"))
    enterprise = _workspace(db, author, "enterprise", governance_model="CAPITAL_OWNER")
    unit = _workspace(db, author, "business-unit", enterprise)
    portfolio = _workspace(db, author, "portfolio", unit)
    project = _workspace(
        db,
        author,
        "project",
        portfolio,
        project_type="MINING",
        strategic_theme="RESILIENCE",
        investment_category="GROWTH",
    )
    sibling = _workspace(db, author, "portfolio", enterprise)
    template = db.scalar(
        select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == author.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
            AdminConfiguration.code == "default",
            AdminConfiguration.revision == 1,
        )
    )
    return {
        "author": author,
        "reviewer": reviewer,
        "service": service,
        "authority": authority,
        "enterprise": enterprise,
        "unit": unit,
        "portfolio": portfolio,
        "project": project,
        "sibling": sibling,
        "template": template,
    }


def _policy(scope_id=None, *, effective_from="2026-01-01", limit="15", **applicability):
    content = deepcopy(DEFAULT_CONFIGURATION)
    content["scope"] = {"type": "workspace" if scope_id else "tenant", "workspace_id": scope_id}
    content["effective_from"] = effective_from
    content["applicability"].update(applicability)
    content["dimensions"] = [
        {"code": "FINANCIAL_EXPOSURE", "label": "Financial exposure", "active": True},
        {"code": "SAFETY", "label": "Safety", "active": True},
    ]
    content["capacity_statements"] = [
        {
            "code": "FIN-CAPACITY",
            "dimension_code": "FINANCIAL_EXPOSURE",
            "statement": "Maintain solvency within approved exposure envelope",
            "rationale": "Governed enterprise boundary",
        }
    ]
    content["appetite_statements"] = [
        {
            "code": "FIN-APPETITE",
            "dimension_code": "FINANCIAL_EXPOSURE",
            "statement": "Accept measured exposure for strategic growth",
            "rationale": "Not a Project approval",
        }
    ]
    content["thresholds"] = [
        {
            "code": "FIN-LIMIT",
            "label": "Financial threshold",
            "dimension_code": "FINANCIAL_EXPOSURE",
            "type": "PERCENTAGE",
            "operator": "LESS_THAN_OR_EQUAL",
            "value": limit,
            "unit": "%",
        },
        {
            "code": "SAFE",
            "label": "Safety criteria met",
            "dimension_code": "SAFETY",
            "type": "BOOLEAN",
            "operator": "IS_TRUE",
            "value": True,
        },
    ]
    return content


def _publish(fixture, scope, content):
    service, authority, template = fixture["service"], fixture["authority"], fixture["template"]
    draft = service.clone_configuration(template.id, template.version, _key("clone"), target_workspace_id=scope.id)
    updated = service.update_configuration(
        draft.id,
        draft.version,
        name="Governed risk boundaries",
        description="Configurable risk policy",
        content=content,
    )
    return authority.publish_configuration(updated.id, updated.version, _key("publish"))


def _authorities(db):
    names = set(inspect(db.bind).get_table_names())
    preserved = (
        "project_risks",
        "risk_register_entries",
        "risk_readiness_assessments",
        "investment_gate_preparations",
        "investment_gate_evidence_items",
        "investment_decisions",
        "investment_decision_votes",
        "project_definition_assessments",
        "definition_maturity_assessments",
    )
    return {
        name: list(db.execute(text(f'SELECT * FROM "{name}" ORDER BY id')).mappings())
        for name in preserved
        if name in names
    } | {
        "other_admin_configurations": [
            AdminConfiguration.__table__.c.keys(),
            [
                tuple(row)
                for row in db.execute(
                    select(AdminConfiguration.__table__).where(AdminConfiguration.kind != CONFIGURATION_KIND)
                ).all()
            ],
        ]
    }


def test_wave2b_risk_inheritance_effective_dates_context_overrides_and_history():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            service = fixture["service"]
            before = _authorities(db)
            enterprise = _publish(fixture, fixture["enterprise"], _policy(fixture["enterprise"].id, limit="25"))
            unit = _publish(fixture, fixture["unit"], _policy(fixture["unit"].id, limit="20"))
            portfolio = _publish(
                fixture,
                fixture["portfolio"],
                _policy(fixture["portfolio"].id, effective_from="2026-06-01", limit="10", project_types=["MINING"]),
            )
            context = EffectiveContextIn(workspace_id=fixture["project"].id, effective_date=date(2026, 7, 1))
            resolved = service.effective(context)
            assert resolved.source["configuration_id"] == portfolio.id
            assert resolved.thresholds[0]["value"] == "10"
            assert resolved.capacity_statements and resolved.appetite_statements
            assert len(resolved.resolution_path) == 4 and resolved.persisted is False
            early = service.effective(context.model_copy(update={"effective_date": date(2026, 3, 1)}))
            assert early.source["configuration_id"] == unit.id
            building = service.effective(context.model_copy(update={"project_type": "BUILDING"}))
            assert building.source["configuration_id"] == unit.id
            assert (
                service.effective(EffectiveContextIn(workspace_id=fixture["sibling"].id)).source["configuration_id"]
                == enterprise.id
            )
            contractor = service.effective(context.model_copy(update={"governance_model": "CONTRACTOR_DELIVERY"}))
            assert contractor.status == "NOT_APPLICABLE" and contractor.source is None
            assert (
                service.effective(context.model_copy(update={"governance_model": "DIRECT_INTERNAL"})).status
                == "NOT_APPLICABLE"
            )
            assert _authorities(db) == before
            assert [row.id for row in service.configurations(code=portfolio.code)] == [portfolio.id]


def test_wave2b_risk_version_successor_future_policy_and_no_implicit_default_merge():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            original = _publish(fixture, fixture["enterprise"], _policy(fixture["enterprise"].id))
            draft = fixture["service"].clone_configuration(original.id, original.version, _key("successor"))
            content = deepcopy(draft.content_json)
            content["effective_from"], content["effective_to"] = "2027-01-01", "2027-12-31"
            content["thresholds"] = []
            draft = fixture["service"].update_configuration(
                draft.id, draft.version, name=draft.name, description="Future policy", content=content
            )
            successor = fixture["authority"].publish_configuration(draft.id, draft.version, _key("future-publish"))
            assert (
                fixture["service"]
                .effective(EffectiveContextIn(workspace_id=fixture["project"].id, effective_date=date(2026, 10, 7)))
                .source["configuration_id"]
                == original.id
            )

            future = fixture["service"].effective(
                EffectiveContextIn(workspace_id=fixture["project"].id, effective_date=date(2027, 1, 1))
            )
            assert future.source["configuration_id"] == successor.id and future.thresholds == []
            assert fixture["service"].configuration(original.id).content_hash == original.content_hash
            assert fixture["service"].configuration(original.id).status == "published"
            assert (
                fixture["service"]
                .effective(EffectiveContextIn(workspace_id=fixture["project"].id, effective_date=date(2028, 1, 1)))
                .source["configuration_id"]
                == original.id
            )


def test_wave2b_risk_canonical_project_classifiers_do_not_equate_mining_with_capital_owner():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            _publish(fixture, fixture["enterprise"], _policy(fixture["enterprise"].id, project_types=["MINING"]))
            project = fixture["project"]
            project.defaults_json = {"_project": {"project_type": "MINING", "governance_model": "CONTRACTOR_DELIVERY"}}
            db.commit()
            actual = fixture["service"].effective(EffectiveContextIn(workspace_id=project.id))
            assert actual.context["project_type"] == "MINING"
            assert actual.context["governance_model"] == "CONTRACTOR_DELIVERY" and actual.status == "NOT_APPLICABLE"
            project.defaults_json = {"_project": {"project_type": "MINING", "governance_model": "CAPITAL_OWNER"}}
            db.commit()
            assert fixture["service"].effective(EffectiveContextIn(workspace_id=project.id)).status == "AVAILABLE"


def test_wave2b_risk_published_immutable_sod_etag_and_idempotency_exact_receipts():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            source = fixture["template"]
            service, authority = fixture["service"], fixture["authority"]
            key = _key("clone")
            draft = service.clone_configuration(
                source.id, source.version, key, target_workspace_id=fixture["enterprise"].id
            )
            assert (
                service.clone_configuration(
                    source.id, source.version, key, target_workspace_id=fixture["enterprise"].id
                )
                == draft
            )
            with pytest.raises(HTTPException) as collision:
                service.clone_configuration(source.id, source.version, key, target_workspace_id=fixture["unit"].id)
            assert collision.value.status_code == 409
            with pytest.raises(HTTPException) as stale:
                service.update_configuration(draft.id, 99, name="wrong", description="", content=draft.content_json)
            assert stale.value.status_code == 412
            content = _policy(fixture["enterprise"].id)
            content["separation_of_duties"]["preparer_cannot_publish"] = False
            draft = service.update_configuration(
                draft.id, draft.version, name="Try disabling SoD", description="", content=content
            )
            with pytest.raises(HTTPException) as sod:
                service.publish_configuration(draft.id, draft.version, _key("same-actor"))
            assert sod.value.detail["code"] == "RISK_GOVERNANCE_SOD_PUBLISH_DENIED"
            publish_key = _key("publish")
            published = authority.publish_configuration(draft.id, draft.version, publish_key)
            assert authority.publish_configuration(draft.id, draft.version, publish_key) == published
            with pytest.raises(HTTPException) as immutable:
                service.update_configuration(
                    published.id, published.version, name="illegal", description="", content=published.content_json
                )
            assert immutable.value.detail["code"] == "DRAFT_CONFIGURATION_REQUIRED"
            archive_key = _key("archive")
            archived = authority.archive_configuration(published.id, published.version, archive_key)
            assert archived.status == "archived"
            assert authority.archive_configuration(published.id, published.version, archive_key) == archived
            assert authority.publish_configuration(draft.id, draft.version, publish_key) == published
            assert authority.configuration(published.id).content_hash == published.content_hash
            events = db.scalars(
                select(SecurityEvent).where(
                    SecurityEvent.target_id == published.id, SecurityEvent.event_type.like("risk_governance.config.%")
                )
            ).all()
            assert {row.event_type for row in events} >= {
                "risk_governance.config.cloned",
                "risk_governance.config.updated",
                "risk_governance.config.published",
                "risk_governance.config.archived",
            }


@pytest.mark.parametrize(
    "operator,value,actual,expected",
    [
        ("EQUALS", "5", "5", "AT_THRESHOLD"),
        ("NOT_EQUALS", "5", "4", "WITHIN_APPETITE"),
        ("GREATER_THAN", "5", "6", "WITHIN_APPETITE"),
        ("GREATER_THAN_OR_EQUAL", "5", "4", "OUTSIDE_APPETITE"),
        ("LESS_THAN", "5", "4", "WITHIN_APPETITE"),
        ("LESS_THAN_OR_EQUAL", "5", "5", "AT_THRESHOLD"),
        ("WITHIN_RANGE", {"minimum": "2", "maximum": "8"}, "7", "WITHIN_APPETITE"),
        ("OUTSIDE_RANGE", {"minimum": "2", "maximum": "8"}, "9", "WITHIN_APPETITE"),
    ],
)
def test_wave2b_risk_numeric_controlled_operators_return_context_never_decisions(operator, value, actual, expected):
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            content = _policy(fixture["enterprise"].id)
            content["thresholds"][0].update(operator=operator, value=value)
            _publish(fixture, fixture["enterprise"], content)
            outcome = fixture["service"].evaluate_threshold(
                ThresholdEvaluationIn(
                    workspace_id=fixture["project"].id, threshold_code="FIN-LIMIT", source_value=actual, unit="%"
                )
            )
            assert outcome.status == expected and outcome.persisted is False and outcome.decision_generated is False
            assert (
                fixture["service"]
                .evaluate_threshold(
                    ThresholdEvaluationIn(workspace_id=fixture["project"].id, threshold_code="FIN-LIMIT", unit="%")
                )
                .status
                == "NOT_EVALUABLE"
            )
            assert (
                fixture["service"]
                .evaluate_threshold(
                    ThresholdEvaluationIn(
                        workspace_id=fixture["project"].id, threshold_code="FIN-LIMIT", source_value="NaN", unit="%"
                    )
                )
                .status
                == "NOT_EVALUABLE"
            )


def test_wave2b_risk_category_boolean_currency_units_and_invalid_operator_no_code():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            content = _policy(fixture["enterprise"].id)
            threshold = content["thresholds"][0]
            threshold.update(type="CATEGORY", operator="IN", value=["LOW", "MEDIUM"], unit="")
            _publish(fixture, fixture["enterprise"], content)
            assert (
                fixture["service"]
                .evaluate_threshold(
                    ThresholdEvaluationIn(
                        workspace_id=fixture["project"].id, threshold_code="FIN-LIMIT", source_value="LOW"
                    )
                )
                .status
                == "WITHIN_APPETITE"
            )
            assert (
                fixture["service"]
                .evaluate_threshold(
                    ThresholdEvaluationIn(workspace_id=fixture["project"].id, threshold_code="SAFE", source_value=True)
                )
                .status
                == "WITHIN_APPETITE"
            )
            assert (
                fixture["service"]
                .evaluate_threshold(
                    ThresholdEvaluationIn(
                        workspace_id=fixture["project"].id, threshold_code="SAFE", source_value="true"
                    )
                )
                .status
                == "NOT_EVALUABLE"
            )
            threshold.update(type="CURRENCY", operator="LESS_THAN", value="1000000", currency_code="USD")
            currency = _publish(
                fixture,
                fixture["portfolio"],
                {**content, "scope": {"type": "workspace", "workspace_id": fixture["portfolio"].id}},
            )
            outcome = fixture["service"].evaluate_threshold(
                ThresholdEvaluationIn(
                    workspace_id=fixture["project"].id,
                    threshold_code="FIN-LIMIT",
                    source_value="500000",
                    currency_code="COP",
                )
            )
            assert outcome.status == "NOT_EVALUABLE" and "CURRENCY_MISMATCH_NO_FX" in outcome.warnings
            assert outcome.source["configuration_id"] == currency.id
            threshold["operator"] = "eval(source)"
            with pytest.raises(HTTPException) as invalid:
                fixture["service"].validate_configuration(content)
            assert invalid.value.detail["code"] == "RISK_GOVERNANCE_OPERATOR_INVALID"
            threshold.update(type="RANGE", operator="WITHIN_RANGE", value={"minimum": "NaN", "maximum": "2"})
            with pytest.raises(HTTPException) as invalid_range:
                fixture["service"].validate_configuration(content)
            assert invalid_range.value.detail["code"] == "RISK_GOVERNANCE_RANGE_INVALID"


def test_wave2b_risk_scoped_read_inherited_policy_cannot_escape_mutate_or_retarget():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            published = _publish(fixture, fixture["enterprise"], _policy(fixture["enterprise"].id))
            scoped = replace(
                _context(fixture["author"]), organization_wide=False, workspace_ids=frozenset({fixture["portfolio"].id})
            )
            service = RiskGovernanceService(db, fixture["author"].tenant_id, fixture["author"].id, scoped)
            assert (
                service.effective(EffectiveContextIn(workspace_id=fixture["project"].id)).source["configuration_id"]
                == published.id
            )
            with pytest.raises(HTTPException) as sibling:
                service.effective(EffectiveContextIn(workspace_id=fixture["sibling"].id))
            assert sibling.value.status_code == 403
            with pytest.raises(HTTPException) as parent_write:
                service.clone_configuration(published.id, published.version, _key("illegal-parent"))
            assert parent_write.value.status_code == 403
            draft = service.clone_configuration(
                published.id, published.version, _key("portfolio"), target_workspace_id=fixture["portfolio"].id
            )
            content = deepcopy(draft.content_json)
            content["scope"] = {"type": "tenant", "workspace_id": None}
            with pytest.raises(HTTPException) as escape:
                service.update_configuration(draft.id, draft.version, name=draft.name, description="", content=content)
            assert escape.value.detail["code"] == "CONFIGURATION_SCOPE_IMMUTABLE_USE_CLONE"
            count_before = len(db.scalars(select(SecurityEvent)).all())
            preview = service.preview(
                ConfigurationPreviewIn(workspace_id=fixture["project"].id, configuration_id=draft.id)
            )
            assert preview.persisted is False and preview.source["status"] == "draft"
            assert len(db.scalars(select(SecurityEvent)).all()) == count_before


def test_wave2b_risk_http_read_only_direct_route_security_etag_idempotency_and_no_seed_on_get():
    with TestClient(app) as client:
        with SessionLocal() as db:
            fixture = _fixture(db)
            viewer = _user(db, fixture["author"].tenant_id, "risk-context-viewer")
            ensure_enterprise_permissions(db, viewer.tenant_id, fixture["author"].id)
            role = db.scalar(
                select(SecurityRole).where(
                    SecurityRole.tenant_id == viewer.tenant_id, SecurityRole.code == "project_definition_viewer"
                )
            )
            db.add(
                SecurityAccessAssignment(
                    tenant_id=viewer.tenant_id,
                    subject_type="user",
                    user_id=viewer.id,
                    role_id=role.id,
                    scope_type="workspace",
                    workspace_id=fixture["portfolio"].id,
                    status="active",
                    granted_by_user_id=fixture["author"].id,
                )
            )
            db.commit()
            headers = _token_headers(viewer)
            statements = []

            def track(_conn, _cursor, statement, _parameters, _context, _many):
                if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                    statements.append(statement)

            event.listen(db.bind, "before_cursor_execute", track)
            try:
                response = client.get(
                    f"/api/v1/risk-governance/effective?workspace_id={fixture['project'].id}", headers=headers
                )
                assert response.status_code == 200, response.text
                assert response.json()["persisted"] is False
                assert statements == []
            finally:
                event.remove(db.bind, "before_cursor_execute", track)
            assert client.get("/api/v1/risk-governance/admin/configurations", headers=headers).status_code == 403
            assert (
                client.post(
                    f"/api/v1/risk-governance/admin/configurations/{fixture['template'].id}/clone",
                    headers={**headers, "If-Match": '"1"', "Idempotency-Key": _key("denied")},
                    json={},
                ).status_code
                == 403
            )
            assert (
                client.get(
                    f"/api/v1/risk-governance/effective?workspace_id={fixture['sibling'].id}", headers=headers
                ).status_code
                == 403
            )
            admin_headers = _token_headers(fixture["author"])
            template = fixture["template"]
            request_headers = {
                **admin_headers,
                "If-Match": f'"{template.version}"',
                "Idempotency-Key": _key("http-clone"),
            }
            clone_url = f"/api/v1/risk-governance/admin/configurations/{template.id}/clone"
            cloned = client.post(
                clone_url, headers=request_headers, json={"target_workspace_id": fixture["enterprise"].id}
            )
            assert cloned.status_code == 200, cloned.text
            assert cloned.headers["ETag"] == '"1"'
            assert "edit" in cloned.json()["allowed_actions"]
            assert "publish" not in cloned.json()["allowed_actions"]
            assert (
                client.post(
                    clone_url, headers=request_headers, json={"target_workspace_id": fixture["enterprise"].id}
                ).json()
                == cloned.json()
            )
            row = cloned.json()
            reviewer_role = db.scalar(
                select(SecurityRole).where(
                    SecurityRole.tenant_id == viewer.tenant_id, SecurityRole.code == "configuration_admin"
                )
            )
            db.add(
                SecurityAccessAssignment(
                    tenant_id=viewer.tenant_id,
                    subject_type="user",
                    user_id=fixture["reviewer"].id,
                    role_id=reviewer_role.id,
                    scope_type="workspace",
                    workspace_id=fixture["enterprise"].id,
                    status="active",
                    granted_by_user_id=fixture["author"].id,
                )
            )
            db.commit()
            reviewer_detail = client.get(
                f"/api/v1/risk-governance/admin/configurations/{row['id']}", headers=_token_headers(fixture["reviewer"])
            )
            assert reviewer_detail.status_code == 200, reviewer_detail.text
            assert "publish" in reviewer_detail.json()["allowed_actions"]
            update = client.put(
                f"/api/v1/risk-governance/admin/configurations/{row['id']}",
                headers={**admin_headers, "If-Match": '"99"'},
                json={"name": "Risk", "description": "", "content_json": row["content_json"]},
            )
            assert update.status_code == 412


def test_wave2b_risk_context_specificity_themes_categories_and_statement_filters_are_backend_owned():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            generic = _publish(fixture, fixture["portfolio"], _policy(fixture["portfolio"].id, limit="30"))
            specific_content = _policy(
                fixture["portfolio"].id, limit="12", strategic_themes=["RESILIENCE"], investment_categories=["GROWTH"]
            )
            specific_content["appetite_statements"][0]["applicability"] = {"project_types": ["BUILDING"]}
            specific = _publish(fixture, fixture["portfolio"], specific_content)
            actual = fixture["service"].effective(EffectiveContextIn(workspace_id=fixture["project"].id))
            assert actual.source["configuration_id"] == specific.id
            assert actual.thresholds[0]["value"] == "12" and actual.appetite_statements == []
            assert (
                fixture["service"]
                .effective(EffectiveContextIn(workspace_id=fixture["project"].id, strategic_theme="OTHER"))
                .source["configuration_id"]
                == generic.id
            )
            assert (
                fixture["service"]
                .effective(EffectiveContextIn(workspace_id=fixture["project"].id, investment_category="SUSTAIN"))
                .source["configuration_id"]
                == generic.id
            )


def test_wave2b_risk_remaining_category_boolean_operators_and_invalid_duration():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            for operator, value, actual, expected in [
                ("NOT_IN", ["HIGH"], "LOW", "WITHIN_APPETITE"),
                ("EQUALS", "LOW", "LOW", "WITHIN_APPETITE"),
                ("NOT_EQUALS", "HIGH", "HIGH", "OUTSIDE_APPETITE"),
            ]:
                content = _policy(fixture["enterprise"].id)
                content["thresholds"][0].update(type="QUALITATIVE", operator=operator, value=value, unit="")
                _publish(fixture, fixture["enterprise"], content)
                assert (
                    fixture["service"]
                    .evaluate_threshold(
                        ThresholdEvaluationIn(
                            workspace_id=fixture["project"].id, threshold_code="FIN-LIMIT", source_value=actual
                        )
                    )
                    .status
                    == expected
                )
            content = _policy(fixture["enterprise"].id)
            content["thresholds"][1]["operator"] = "IS_FALSE"
            _publish(fixture, fixture["enterprise"], content)
            assert (
                fixture["service"]
                .evaluate_threshold(
                    ThresholdEvaluationIn(workspace_id=fixture["project"].id, threshold_code="SAFE", source_value=False)
                )
                .status
                == "WITHIN_APPETITE"
            )
            content["thresholds"][0].update(type="DURATION", unit="", operator="LESS_THAN", value="30")
            with pytest.raises(HTTPException) as missing_unit:
                fixture["service"].validate_configuration(content)
            assert missing_unit.value.detail["code"] == "RISK_GOVERNANCE_DURATION_UNIT_REQUIRED"


def test_wave2b_risk_policy_publication_preserves_real_completed_risk_readiness_evidence():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            project = fixture["project"]
            project.defaults_json = {"_project": {"project_type": "MINING", "governance_model": "CAPITAL_OWNER"}}
            db.commit()
            risk_service = RiskReadinessService(db, fixture["author"].tenant_id, fixture["author"].id)
            _publish_risk(risk_service)
            _low_risk(risk_service, project.id)
            completed = _complete_risk(risk_service, project.id)
            assert completed.status == "COMPLETED" and completed.risk_readiness_hash
            history = db.scalar(select(RiskReadinessAssessment).where(RiskReadinessAssessment.id == completed.id))
            before = _authorities(db)
            before_hash = history.risk_readiness_hash
            before_snapshot = {
                column.key: deepcopy(getattr(history, column.key))
                for column in RiskReadinessAssessment.__table__.columns
            }
            published = _publish(fixture, fixture["enterprise"], _policy(fixture["enterprise"].id, limit="0"))
            assert (
                fixture["service"].effective(EffectiveContextIn(workspace_id=project.id)).source["configuration_id"]
                == published.id
            )
            db.expire(history)
            assert history.risk_readiness_hash == before_hash
            assert {
                column.key: getattr(history, column.key) for column in RiskReadinessAssessment.__table__.columns
            } == before_snapshot
            assert _authorities(db) == before
