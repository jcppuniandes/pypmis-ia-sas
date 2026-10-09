"""Real PostgreSQL happy/negative release evidence for Gate 07A-BA."""

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.database.session import SessionLocal, engine
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, UserAccount
from app.main import app
from app.modules.business_analysis.models import BusinessAnalysis, BusinessAnalysisRevision
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.enterprise_structure.service import EnterpriseStructureService
from app.modules.idea_demand.models import Idea, IdeaEvaluation
from app.modules.idea_demand.service import IdeaDemandService

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="PostgreSQL Gate 07A-BA evidence requires PYPMIS_TEST_DATABASE_URL",
)


def _bootstrap_gate() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin", "password": "1234", "tenant_slug": "demo-energy"},
        )
        assert login.status_code == 200, login.text
        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            assert admin is not None
            EnterpriseStructureService(db, admin.tenant_id, admin.id).ensure_seed()
            context = require_enterprise_permission(db, admin.tenant_id, admin.id, "idea.read")
            IdeaDemandService(db, admin.tenant_id, admin.id, context).ensure_seed()
        response = client.get(
            "/api/v1/business-analyses/options",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert response.status_code == 200, response.text


def test_gate07a_ba_postgres_schema_lineage_and_constraints() -> None:
    _bootstrap_gate()
    inspector = inspect(engine)
    assert {"business_analyses", "business_analysis_revisions"}.issubset(inspector.get_table_names())
    analysis_checks = {item["name"] for item in inspector.get_check_constraints("business_analyses")}
    assert "ck_business_analysis_status" in analysis_checks
    analysis_indexes = {item["name"]: item for item in inspector.get_indexes("business_analyses")}
    assert analysis_indexes["uq_business_analysis_active_idea"]["unique"] is True
    assert analysis_indexes["uq_business_analysis_active_idea"].get("dialect_options", {}).get("postgresql_where")
    proposal_columns = {item["name"] for item in inspector.get_columns("project_proposals")}
    assert {
        "source_business_analysis_id",
        "source_business_analysis_hash",
        "business_analysis_configuration_id",
        "business_analysis_configuration_revision",
        "business_analysis_configuration_hash",
    }.issubset(proposal_columns)


def test_gate07a_ba_postgres_happy_snapshot_and_negative_active_duplicate() -> None:
    _bootstrap_gate()
    token = uuid4().hex
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        workspace = db.scalar(
            select(EnterpriseWorkspace)
            .where(EnterpriseWorkspace.tenant_id == admin.tenant_id)
            .order_by(EnterpriseWorkspace.id)
        )
        idea_matrix = db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == admin.tenant_id,
                AdminConfiguration.kind == "idea_evaluation_matrix",
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
        )
        ba_configuration = db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == admin.tenant_id,
                AdminConfiguration.kind == "business_analysis_configuration",
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
        )
        assert admin is not None and workspace is not None
        assert idea_matrix is not None and ba_configuration is not None

        idea = Idea(
            tenant_id=admin.tenant_id,
            idea_number=f"IDEA-BA-PG-{token[:10]}",
            title="PostgreSQL BA constraint evidence",
            description="Disposable Gate 07A-BA database evidence.",
            idea_type="need",
            category="capital",
            expected_benefit="Traceable option decision",
            estimated_value=Decimal("100000.00"),
            currency_code="COP",
            owning_workspace_id=workspace.id,
            target_portfolio_workspace_id=None,
            strategic_objective_codes=["postgres-evidence"],
            requestor_user_id=admin.id,
            owner_user_id=admin.id,
            state="ACCEPTED",
            screening_json={},
            routing_json={},
            configuration_snapshot_json={"effective": {}},
            attachment_refs_json=[],
            decision_reason="PostgreSQL evidence",
            decision_by_user_id=admin.id,
            readiness_json={},
            revision_version=1,
            last_modified_by_user_id=admin.id,
        )
        db.add(idea)
        db.flush()
        evaluation = IdeaEvaluation(
            tenant_id=admin.tenant_id,
            idea_id=idea.id,
            evaluation_version=1,
            matrix_configuration_id=idea_matrix.id,
            matrix_revision=idea_matrix.revision,
            matrix_snapshot_json=idea_matrix.content_json,
            ratings_json=[],
            total_score=Decimal("80.0000"),
            result="RECOMMENDED",
            comments="PostgreSQL evidence",
            evaluator_user_id=admin.id,
        )
        db.add(evaluation)
        db.flush()
        idea.accepted_evaluation_id = evaluation.id
        db.flush()

        completed = BusinessAnalysis(
            tenant_id=admin.tenant_id,
            analysis_number=f"BA-PG-C-{token[:10]}",
            source_idea_id=idea.id,
            source_idea_evaluation_id=evaluation.id,
            owning_workspace_id=workspace.id,
            status="COMPLETED",
            title="Completed PostgreSQL evidence",
            content_json={"statement": "Evidence"},
            readiness_json={"blockers": []},
            source_idea_hash="a" * 64,
            configuration_id=ba_configuration.id,
            configuration_revision=ba_configuration.revision,
            configuration_hash=ba_configuration.content_hash,
            review_json={"completed_by": admin.id},
            completion_hash="b" * 64,
            idempotency_key=f"ba-pg-completed-{token}",
            revision_version=1,
            created_by_user_id=admin.id,
            updated_by_user_id=admin.id,
            reviewer_user_id=admin.id,
        )
        db.add(completed)
        db.flush()
        db.add(
            BusinessAnalysisRevision(
                tenant_id=admin.tenant_id,
                business_analysis_id=completed.id,
                revision_number=1,
                lifecycle_status="COMPLETED",
                source_idea_hash=completed.source_idea_hash,
                configuration_hash=completed.configuration_hash,
                content_json=completed.content_json,
                readiness_json=completed.readiness_json,
                snapshot_hash="c" * 64,
                actor_user_id=admin.id,
            )
        )
        active = BusinessAnalysis(
            tenant_id=admin.tenant_id,
            analysis_number=f"BA-PG-A-{token[:10]}",
            source_idea_id=idea.id,
            source_idea_evaluation_id=evaluation.id,
            owning_workspace_id=workspace.id,
            supersedes_analysis_id=completed.id,
            status="DRAFT",
            title="Active PostgreSQL evidence",
            content_json={},
            readiness_json={},
            source_idea_hash="d" * 64,
            configuration_id=ba_configuration.id,
            configuration_revision=ba_configuration.revision,
            configuration_hash=ba_configuration.content_hash,
            review_json={},
            completion_hash="",
            idempotency_key=f"ba-pg-active-{token}",
            revision_version=1,
            created_by_user_id=admin.id,
            updated_by_user_id=admin.id,
        )
        db.add(active)
        db.flush()
        assert completed.id and active.id
        assert db.scalar(
            select(BusinessAnalysisRevision).where(BusinessAnalysisRevision.business_analysis_id == completed.id)
        )

        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(
                    BusinessAnalysis(
                        tenant_id=admin.tenant_id,
                        analysis_number=f"BA-PG-D-{token[:10]}",
                        source_idea_id=idea.id,
                        source_idea_evaluation_id=evaluation.id,
                        owning_workspace_id=workspace.id,
                        status="SUBMITTED",
                        title="Forbidden duplicate active BA",
                        content_json={},
                        readiness_json={},
                        source_idea_hash="e" * 64,
                        configuration_id=ba_configuration.id,
                        configuration_revision=ba_configuration.revision,
                        configuration_hash=ba_configuration.content_hash,
                        review_json={},
                        completion_hash="",
                        idempotency_key=f"ba-pg-duplicate-{token}",
                        revision_version=1,
                        created_by_user_id=admin.id,
                        updated_by_user_id=admin.id,
                    )
                )
                db.flush()
        db.rollback()
