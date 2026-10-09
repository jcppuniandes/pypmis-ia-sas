"""Gate 07J-FEL acceptance coverage for Project Definition / FEL Manager."""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests.test_portfolio_convergence_gate07i import _fixture

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, UserAccount
from app.main import app
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService
from app.modules.project_definition.schemas import (
    ActionCreateIn,
    ActionUpdateIn,
    AssessmentCreateIn,
    AssessmentUpdateIn,
    ElementResultIn,
    StartFELIn,
)
from app.modules.project_definition.service import (
    CONFIGURATION_KIND,
    DEFAULT_FRAMEWORK,
    ProjectDefinitionService,
    _hash,
)


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _framework(
    db,
    tenant_id: int,
    actor_id: int,
    *,
    framework_type: str = "CUSTOM",
    direction: str = "HIGHER_IS_BETTER",
    threshold: float = 65,
    governance_models: list[str] | None = None,
) -> AdminConfiguration:
    content = deepcopy(DEFAULT_FRAMEWORK)
    suffix = uuid4().hex[:10]
    content["framework_code"] = f"SYNTHETIC-{framework_type}-{suffix}"
    content["framework_type"] = framework_type
    content["framework_version"] = "1.0-test"
    content["score_direction"] = direction
    content["thresholds"] = {"FEL-1": threshold, "FEL-2": threshold, "FEL-3": threshold}
    content["applicable_governance_models"] = governance_models or ["CAPITAL_OWNER"]
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=CONFIGURATION_KIND,
        code=f"definition-{suffix}",
        name=f"Synthetic {framework_type}",
        description="Synthetic non-proprietary acceptance framework.",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        published_at=utc_now(),
        created_by_user_id=actor_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _reviewer(db, tenant_id: int) -> UserAccount:
    record = UserAccount(
        tenant_id=tenant_id,
        email=f"definition-reviewer-{uuid4().hex[:10]}@example.test",
        full_name="Independent Definition Reviewer",
        title="Definition Reviewer",
        status="active",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _complete_current(service: ProjectDefinitionService, project_id: int, *, score: float = 85, blocking=False):
    assessment = service.create_assessment(project_id, AssessmentCreateIn(idempotency_key=f"assessment-{uuid4()}"))
    elements = []
    for item in assessment.source_snapshot["applicable_elements"]:
        elements.append(
            ElementResultIn(
                element_key=item["element_key"],
                category_key=item["category_key"],
                applicable=True,
                score=score,
                maturity_status="READY" if score >= 65 else "DEVELOPING",
                comment="Synthetic governed definition result.",
                evidence_refs=[{"reference": f"evidence-{item['element_key']}", "origin": "GOVERNED_SOURCE"}],
                blocking=bool(blocking and not elements),
                action_required=bool(blocking and not elements),
            )
        )
    assessment = service.update_assessment(
        assessment.id,
        assessment.revision_version,
        AssessmentUpdateIn(status="IN_PROGRESS", element_results=elements),
    )
    return service.complete_assessment(assessment.id, assessment.revision_version, f"complete-{uuid4()}")


def test_custom_framework_happy_path_supplies_gate07j_evidence_without_fid() -> None:
    db, tenant_id, actor_id, _portfolio, projects, _budget, _resource = _fixture()
    try:
        framework = _framework(db, tenant_id, actor_id, threshold=65)
        service = ProjectDefinitionService(db, tenant_id, actor_id)
        project = projects[0]
        status = service.start_fel(
            project.id,
            StartFELIn(
                framework_configuration_id=framework.id,
                stage_code="FEL-1",
                idempotency_key=f"fel-start-{uuid4()}",
            ),
        )
        completed = _complete_current(service, project.id)
        readiness = service.readiness(project.id)
        contract = service.investment_gate_evidence(project.id)
        assert status.status == "IN_STAGE"
        assert completed.status == "COMPLETED"
        assert readiness.status == "READY"
        assert readiness.can_supply_investment_gate_evidence is True
        assert contract.source_module == "PROJECT_DEFINITION_FEL"
        assert contract.evidence_origin == "GOVERNED_SOURCE"
        assert contract.minimum_requirement_met is True

        payload = InvestmentGatePreparationService(db, tenant_id, actor_id)._governed_payload(
            {"evidence_type": "FEL_STAGE_READINESS"}, {}, project.id
        )
        assert payload is not None
        assert payload["source_module"] == "project_definition_fel"

        submitted = service.submit_stage_review(
            project.id, service.fel_status(project.id).revision_version, f"submit-{uuid4()}"
        )
        reviewer = _reviewer(db, tenant_id)
        reviewed = ProjectDefinitionService(db, tenant_id, reviewer.id).complete_stage(
            project.id, submitted.revision_version, f"stage-complete-{uuid4()}"
        )
        assert reviewed.current_stage_code == "FEL-2"
        assert reviewed.status == "IN_STAGE"
        assert project.status != "active-by-fel"
    finally:
        db.close()


def test_below_threshold_blocking_element_and_action_prevent_score_only_readiness() -> None:
    db, tenant_id, actor_id, _portfolio, projects, _budget, _resource = _fixture()
    try:
        framework = _framework(db, tenant_id, actor_id, threshold=65)
        service = ProjectDefinitionService(db, tenant_id, actor_id)
        project = projects[0]
        service.start_fel(
            project.id,
            StartFELIn(framework_configuration_id=framework.id, idempotency_key=f"fel-{uuid4()}"),
        )
        completed = _complete_current(service, project.id, score=95, blocking=True)
        readiness = service.readiness(project.id)
        assert readiness.status == "BLOCKED"
        assert "BLOCKING_DEFINITION_ELEMENTS" in readiness.blockers

        action = service.create_action(
            project.id,
            ActionCreateIn(
                assessment_id=completed.id,
                element_key="business-case-reference",
                title="Resolve definition blocker",
                blocking=True,
                idempotency_key=f"action-{uuid4()}",
            ),
        )
        assert "OPEN_BLOCKING_DEFINITION_ACTIONS" in service.readiness(project.id).blockers
        service.update_action(action.id, action.revision_version, ActionUpdateIn(status="RESOLVED"))
        assert service.readiness(project.id).open_blocking_action_count == 0
    finally:
        db.close()


@pytest.mark.parametrize(
    ("framework_type", "direction", "threshold", "score", "expected"),
    [
        ("PDRI_COMPATIBLE", "LOWER_IS_BETTER", 30, 20, "MEETS_REQUIRED"),
        ("FEL_INDEX_COMPATIBLE", "HIGHER_IS_BETTER", 70, 80, "MEETS_REQUIRED"),
    ],
)
def test_synthetic_framework_thresholds_are_isolated(
    framework_type: str, direction: str, threshold: float, score: float, expected: str
) -> None:
    db, tenant_id, actor_id, _portfolio, projects, _budget, _resource = _fixture()
    try:
        framework = _framework(
            db,
            tenant_id,
            actor_id,
            framework_type=framework_type,
            direction=direction,
            threshold=threshold,
        )
        service = ProjectDefinitionService(db, tenant_id, actor_id)
        service.start_fel(
            projects[0].id,
            StartFELIn(framework_configuration_id=framework.id, idempotency_key=f"fel-{uuid4()}"),
        )
        completed = _complete_current(service, projects[0].id, score=score)
        assert completed.framework_type == framework_type
        assert completed.threshold_status in {expected, "EXCEEDS_REQUIRED"}
    finally:
        db.close()


def test_governance_stage_skip_staleness_and_completed_immutability() -> None:
    db, tenant_id, actor_id, _portfolio, projects, _budget, _resource = _fixture()
    try:
        framework = _framework(db, tenant_id, actor_id)
        project = projects[0]
        context = deepcopy(project.defaults_json or {})
        context.setdefault("_project", {})["governance_model"] = "CONTRACTOR_DELIVERY"
        project.defaults_json = context
        db.commit()
        with pytest.raises(HTTPException) as optional:
            ProjectDefinitionService(db, tenant_id, actor_id).start_fel(
                project.id,
                StartFELIn(framework_configuration_id=framework.id, idempotency_key=f"contractor-{uuid4()}"),
            )
        assert optional.value.detail["code"] == "PROJECT_DEFINITION_CAPABILITY_NOT_APPLICABLE"
        assert optional.value.detail["contractor_delivery_required"] is False

        context["_project"]["governance_model"] = "CAPITAL_OWNER"
        project.defaults_json = context
        db.commit()
        service = ProjectDefinitionService(db, tenant_id, actor_id)
        with pytest.raises(HTTPException) as skipped:
            service.start_fel(
                project.id,
                StartFELIn(
                    framework_configuration_id=framework.id,
                    stage_code="FEL-3",
                    idempotency_key=f"skip-{uuid4()}",
                ),
            )
        assert skipped.value.detail["code"] == "FEL_STAGE_SKIP_REQUIRES_GOVERNED_BYPASS"

        service.start_fel(
            project.id,
            StartFELIn(framework_configuration_id=framework.id, idempotency_key=f"start-{uuid4()}"),
        )
        completed = _complete_current(service, project.id)
        with pytest.raises(HTTPException) as immutable:
            service.update_assessment(
                completed.id,
                completed.revision_version,
                AssessmentUpdateIn(status="IN_PROGRESS", element_results=[]),
            )
        assert immutable.value.detail["code"] == "COMPLETED_ASSESSMENT_IMMUTABLE"

        updated_content = deepcopy(framework.content_json)
        updated_content["framework_version"] = "1.1-test"
        framework.content_json = updated_content
        framework.content_hash = _hash(updated_content)
        db.commit()
        readiness = service.readiness(project.id)
        preview = service.refresh_preview(project.id)
        assert readiness.status == "STALE"
        assert preview["persisted"] is False
        assert preview["changes"]
    finally:
        db.close()


def test_configuration_preview_reports_invalid_evidence_metadata_without_server_error() -> None:
    db, tenant_id, actor_id, _portfolio, projects, _budget, _resource = _fixture()
    try:
        framework = _framework(db, tenant_id, actor_id)
        invalid = deepcopy(framework.content_json)
        invalid["required_evidence"] = ["scope-basis-reference"]
        preview = ProjectDefinitionService(db, tenant_id, actor_id).configuration_preview(
            projects[0].id,
            None,
            "CAPITAL_OWNER",
            "FEL-2",
            framework.id,
            invalid,
        )
        assert preview.persisted is False
        assert "INVALID_REQUIRED_EVIDENCE" in preview.blockers
        assert preview.required_evidence == []
    finally:
        db.close()
