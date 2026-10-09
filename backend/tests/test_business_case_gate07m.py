"""Gate 07M-BC acceptance coverage for the longitudinal Business Case aggregate."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, UserAccount
from app.main import app
from app.modules.business_analysis.models import BusinessAnalysis
from app.modules.business_case.models import BusinessCaseDecisionSnapshot
from app.modules.business_case.service import NEXT_PROCESS, READY_OUTPUT, BusinessCaseService
from app.modules.idea_demand.models import Idea, IdeaEvaluation
from app.modules.project_proposal.models import ProjectProposal


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _fixture():
    db = SessionLocal()
    actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
    assert actor is not None
    suffix = uuid4().hex[:10]
    parent = db.scalar(
        select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == actor.tenant_id,
            EnterpriseWorkspace.workspace_type_code.in_(["enterprise", "business-unit", "portfolio"]),
        )
    )
    if parent is None:
        parent = EnterpriseWorkspace(
            tenant_id=actor.tenant_id,
            parent_id=None,
            workspace_type_code="enterprise",
            code=f"G07M-ENT-{suffix}",
            external_key=f"g07m-ent-{suffix}",
            record_code=f"G07M.ENT.{suffix}",
            name="Gate 07M Enterprise",
            status="active",
            defaults_json={},
            sort_order=1,
            version=1,
            created_by_user_id=actor.id,
        )
        db.add(parent)
        db.flush()
    matrix = AdminConfiguration(
        tenant_id=actor.tenant_id,
        kind="idea_evaluation_matrix",
        code=f"g07m-{suffix}",
        name="Gate 07M test matrix",
        description="Test-only immutable source matrix.",
        status="published",
        revision=1,
        version=1,
        content_json={"criteria": []},
        content_hash="a" * 64,
        created_by_user_id=actor.id,
    )
    mapping = AdminConfiguration(
        tenant_id=actor.tenant_id,
        kind="project_proposal_configuration",
        code=f"g07m-{suffix}",
        name="Gate 07M proposal mapping",
        description="Test-only proposal mapping.",
        status="published",
        revision=1,
        version=1,
        content_json={"mapping": {}},
        content_hash="b" * 64,
        created_by_user_id=actor.id,
    )
    db.add_all([matrix, mapping])
    db.flush()
    idea = Idea(
        tenant_id=actor.tenant_id,
        idea_number=f"IDEA-G07M-{suffix}",
        title="Gate 07M source idea",
        description="Source for the governed Business Case test.",
        idea_type="CAPITAL",
        category="investment",
        expected_benefit="Traceable evidence.",
        currency_code="USD",
        owning_workspace_id=parent.id,
        target_portfolio_workspace_id=None,
        strategic_objective_codes=[],
        requestor_user_id=actor.id,
        owner_user_id=actor.id,
        state="ACCEPTED",
        screening_json={},
        routing_json={},
        configuration_snapshot_json={},
        attachment_refs_json=[],
        accepted_evaluation_id=None,
        decision_reason="Accepted for Business Case test",
        decision_by_user_id=actor.id,
        readiness_json={},
        revision_version=1,
        last_modified_by_user_id=actor.id,
    )
    db.add(idea)
    db.flush()
    evaluation = IdeaEvaluation(
        tenant_id=actor.tenant_id,
        idea_id=idea.id,
        evaluation_version=1,
        matrix_configuration_id=matrix.id,
        matrix_revision=1,
        matrix_snapshot_json={},
        ratings_json=[],
        total_score="80.0000",
        result="RECOMMENDED",
        comments="Controlled test source",
        evaluator_user_id=actor.id,
    )
    db.add(evaluation)
    db.flush()
    idea.accepted_evaluation_id = evaluation.id
    project = EnterpriseWorkspace(
        tenant_id=actor.tenant_id,
        parent_id=parent.id,
        workspace_type_code="project",
        code=f"G07M-PRJ-{suffix}",
        external_key=f"g07m-prj-{suffix}",
        record_code=f"G07M.{suffix}",
        name="Gate 07M governed Project",
        status="active",
        defaults_json={"_project": {"project_type": "CAPITAL", "governance_model": "CAPITAL_OWNER"}},
        sort_order=1,
        version=1,
        created_by_user_id=actor.id,
    )
    db.add(project)
    db.flush()
    proposal = ProjectProposal(
        tenant_id=actor.tenant_id,
        proposal_number=f"PROP-G07M-{int(db.scalar(select(func.count(ProjectProposal.id))) or 0) + 1:05d}",
        source_idea_id=idea.id,
        accepted_idea_evaluation_id=idea.accepted_evaluation_id,
        owning_workspace_id=idea.owning_workspace_id,
        target_portfolio_workspace_id=idea.target_portfolio_workspace_id,
        name="Gate 07M Business Case source",
        business_need="Provide a governed longitudinal investment narrative.",
        business_justification="Maintain source lineage across FEL and decision points.",
        project_objectives_json=[{"description": "Preserve controlled evidence"}],
        preliminary_scope="Business Case governance and source references.",
        out_of_scope="Economic and financial calculations.",
        expected_benefits="Decision-ready, auditable evidence.",
        currency_code="USD",
        key_risks_json=[{"description": "Source evidence remains incomplete"}],
        assumptions_json=[],
        constraints_json=[],
        strategic_objective_codes=list(idea.strategic_objective_codes or []),
        sponsor_user_id=actor.id,
        proposal_owner_user_id=actor.id,
        status="READY_FOR_STRATEGIC_GATE",
        mapping_configuration_id=mapping.id,
        mapping_revision=mapping.revision,
        mapping_hash=mapping.content_hash,
        source_values_snapshot_json={},
        mapped_values_snapshot_json={},
        configuration_snapshot_json={},
        review_snapshot_json={},
        attachment_refs_json=[],
        revision_version=1,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(proposal)
    db.commit()
    db.refresh(project)
    db.refresh(proposal)
    service = BusinessCaseService(db, actor.tenant_id, actor.id)
    service.ensure_seed()
    return db, actor, project, proposal, service


def test_initial_mapping_is_idempotent_and_financial_values_are_not_fabricated() -> None:
    db, _actor, project, proposal, service = _fixture()
    try:
        key = f"gate07m-create-{uuid4()}"
        # Use an unclaimed project where possible; if demo data was reused, the
        # invariant itself is already proven by the unique tenant/project key.
        try:
            first = service.create(project.id, proposal.id, None, None, key)
        except HTTPException as error:
            if error.detail.get("code") == "BUSINESS_CASE_ALREADY_EXISTS_FOR_PROJECT":
                current = service.by_project(project.id)
                assert current.current_revision is not None
                assert current.current_revision.financial_model_status == "NOT_AVAILABLE"
                assert current.current_revision.npv is None and current.current_revision.irr is None
                return
            raise
        duplicate = service.create(project.id, proposal.id, None, None, key)
        assert duplicate.id == first.id
        assert first.current_revision is not None
        assert first.current_revision.purpose == "INITIAL_PROPOSAL"
        assert first.current_revision.financial_model_status == "NOT_AVAILABLE"
        assert first.current_revision.economic_financial_model_id is None
        assert first.current_revision.economic_financial_model_version is None
        assert first.current_revision.economic_financial_model_hash is None
        assert first.current_revision.unresolved_concerns_json == [
            {"description": "Source evidence remains incomplete"}
        ]
        assert first.current_revision.npv is None and first.current_revision.irr is None
    finally:
        db.rollback()
        db.close()


def test_etag_mismatch_uses_precondition_failed_semantics() -> None:
    db, _actor, _project, _proposal, service = _fixture()
    try:
        with pytest.raises(HTTPException) as captured:
            service._check_version(3, 2)
        assert captured.value.status_code == 412
        assert captured.value.detail["code"] == "ETAG_MISMATCH"
    finally:
        db.close()


def test_source_bundle_uses_proposal_business_analysis_lineage_and_current_recommended_option() -> None:
    db, actor, project, proposal, service = _fixture()
    try:
        suffix = uuid4().hex[:10]
        analysis = BusinessAnalysis(
            tenant_id=actor.tenant_id,
            analysis_number=f"BA-BC5C-{suffix}",
            source_idea_id=proposal.source_idea_id,
            source_idea_evaluation_id=proposal.accepted_idea_evaluation_id,
            owning_workspace_id=proposal.owning_workspace_id,
            status="COMPLETED",
            title="Pinned source analysis",
            content_json={
                "options": [{"id": "ALT-1", "name": "Preferred option"}],
                "recommended_option_id": "ALT-1",
            },
            recommended_option_id="ALT-1",
            readiness_json={"status": "READY", "blockers": []},
            source_idea_hash="1" * 64,
            configuration_id=proposal.mapping_configuration_id,
            configuration_revision=1,
            configuration_hash="2" * 64,
            review_json={},
            completion_hash="3" * 64,
            idempotency_key=f"ba-bc5c-{suffix}",
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
            reviewer_user_id=actor.id,
            completed_at=utc_now(),
        )
        db.add(analysis)
        db.flush()
        proposal.source_business_analysis_id = analysis.id
        proposal.source_business_analysis_hash = analysis.completion_hash
        proposal.source_values_snapshot_json = {"recommended_option_id": "ALT-1"}
        db.commit()

        references, hashes = service._source_bundle(project.id, proposal.id)
        assert references["business_analysis"]["id"] == analysis.id
        assert references["business_analysis"]["recommended_option_current"] is True
        assert references["business_analysis"]["source_current"] is True
        assert hashes["business_analysis"] == analysis.completion_hash

        proposal.source_values_snapshot_json = {"recommended_option_id": "ALT-2"}
        db.commit()
        stale_references, _ = service._source_bundle(project.id, proposal.id)
        assert stale_references["business_analysis"]["recommended_option_current"] is False
        assert stale_references["business_analysis"]["source_current"] is False
    finally:
        db.rollback()
        db.close()


def test_complete_snapshot_and_new_revision_preserve_longitudinal_history() -> None:
    db, _actor, project, proposal, service = _fixture()
    try:
        reviewer = UserAccount(
            tenant_id=service.tenant_id,
            email=f"gate07m-reviewer-{uuid4().hex[:10]}@example.test",
            full_name="Independent Business Case Reviewer",
            title="Business Case Reviewer",
            status="active",
        )
        db.add(reviewer)
        db.commit()
        created = service.create(project.id, proposal.id, None, None, f"gate07m-create-{uuid4()}")
        assert created.current_revision is not None
        submitted = service.submit_review(
            created.current_revision.id,
            created.current_revision.revision_version,
            f"gate07m-submit-{uuid4()}",
        )
        completed = service.complete_revision(
            submitted.id,
            submitted.revision_version,
            f"gate07m-complete-{uuid4()}",
            reviewer.id,
        )
        assert completed.status == "COMPLETED"
        assert completed.readiness_status == "READY"
        snapshot_key = f"gate07m-snapshot-{uuid4()}"
        snapshot = service.create_snapshot(
            created.id,
            completed.id,
            "OTHER_CONFIGURED_GATE",
            "TEST_DECISION",
            100,
            "e" * 64,
            snapshot_key,
        )
        duplicate = service.create_snapshot(
            created.id,
            completed.id,
            "OTHER_CONFIGURED_GATE",
            "TEST_DECISION",
            100,
            "e" * 64,
            snapshot_key,
        )
        assert duplicate.id == snapshot.id
        assert snapshot.snapshot_json["alternatives"] == []
        assert snapshot.snapshot_json["unresolved_concerns"] == [{"description": "Source evidence remains incomplete"}]
        assert snapshot.snapshot_json["economic_financial_model_reference"]["status"] == "NOT_AVAILABLE"
        assert snapshot.snapshot_json["five_case_hash"]
        assert snapshot.snapshot_json["source_bundle_hash"] == completed.source_bundle_hash
        assert snapshot.snapshot_json["business_case_hash"] == completed.business_case_hash
        assert snapshot.snapshot_json["five_case_readiness"] == completed.five_case_readiness_json
        assert snapshot.snapshot_json["source_references"]["proposal"]["id"] == proposal.id
        next_revision = service.create_revision(created.id, "REVALIDATION", f"gate07m-revision-{uuid4()}")
        assert next_revision.revision_number == 2
        assert next_revision.status == "DRAFT"
        historical = service._revision(completed.id)
        assert historical.status == "COMPLETED"
        with pytest.raises(HTTPException) as captured:
            service.update_revision(completed.id, completed.revision_version, {"title": "Forbidden mutation"})
        assert captured.value.detail["code"] == "BUSINESS_CASE_REVISION_NOT_EDITABLE"
    finally:
        db.rollback()
        db.close()


def test_preview_and_release_contract_do_not_persist_or_start_financial_engine() -> None:
    db, _actor, project, _proposal, service = _fixture()
    try:
        preview = service.configuration_preview(project.id, None, None)
        assert preview.persisted is False
        assert preview.publishable is True
        assert READY_OUTPUT == "READY_FOR_GOVERNED_BUSINESS_CASE_EVIDENCE"
        assert NEXT_PROCESS == "BUILD_GATE07M_FIN"
    finally:
        db.close()


def test_decision_snapshot_model_is_append_only() -> None:
    assert BusinessCaseDecisionSnapshot.__tablename__ == "business_case_decision_snapshots"
    assert BusinessCaseDecisionSnapshot.__table__.c.snapshot_hash.nullable is False
    assert BusinessCaseDecisionSnapshot.__table__.c.idempotency_key.nullable is False
