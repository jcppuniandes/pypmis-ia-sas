"""Real PostgreSQL structural evidence for Gate 07M-BC."""

from copy import deepcopy
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.database.session import engine
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, Tenant, UserAccount
from app.modules.business_case.models import BusinessCase, BusinessCaseRevision
from app.modules.business_case.service import DEFAULT_CONFIGURATION, BusinessCaseService

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL Gate 07M-BC evidence required")


def test_gate07m_bc_core_tables_constraints_and_indexes_exist() -> None:
    inspector = inspect(engine)
    assert {
        "business_cases",
        "business_case_revisions",
        "business_case_decision_snapshots",
    }.issubset(inspector.get_table_names())
    revision_checks = {item["name"] for item in inspector.get_check_constraints("business_case_revisions")}
    assert {
        "ck_business_case_revision_status",
        "ck_business_case_revision_purpose",
        "ck_business_case_revision_readiness",
        "ck_business_case_material_change",
        "ck_business_case_financial_status",
    }.issubset(revision_checks)
    snapshot_uniques = {item["name"] for item in inspector.get_unique_constraints("business_case_decision_snapshots")}
    assert {"uq_business_case_snapshot_key", "uq_business_case_revision_snapshot_type"}.issubset(snapshot_uniques)
    case_indexes = {item["name"] for item in inspector.get_indexes("business_cases")}
    assert "ix_business_case_queue" in case_indexes
    # ``Base.metadata.create_all`` and Alembic use different index names for
    # these single-column indexes.  Validate the indexed columns so both
    # supported bootstrap paths prove the same PostgreSQL capability.
    revision_indexes = {tuple(item["column_names"]) for item in inspector.get_indexes("business_case_revisions")}
    assert {
        ("as_of_date",),
        ("fel_stage_code",),
        ("economic_financial_model_id",),
        ("economic_financial_model_hash",),
    }.issubset(revision_indexes)


def test_gate07m_bc_five_case_ready_revision_round_trips_on_postgresql() -> None:
    """Persist and read a complete Five Case contract, then roll it all back."""

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    suffix = uuid4().hex[:10]
    try:
        tenant = Tenant(name="Gate 07M BC-5C PostgreSQL", slug=f"gate07m-bc5c-{suffix}")
        session.add(tenant)
        session.flush()
        user = UserAccount(
            tenant_id=tenant.id,
            email=f"gate07m-bc5c-{suffix}@example.test",
            full_name="Gate 07M BC-5C Reviewer",
            title="Investment Reviewer",
        )
        session.add(user)
        session.flush()
        project = EnterpriseWorkspace(
            tenant_id=tenant.id,
            parent_id=None,
            workspace_type_code="project",
            code=f"BC5C-{suffix}",
            external_key=f"bc5c-{suffix}",
            record_code=f"BC5C.{suffix}",
            name="Five Case PostgreSQL Project",
            status="active",
            defaults_json={
                "_project": {
                    "project_type": "CAPITAL",
                    "governance_model": "CAPITAL_OWNER",
                    "gate_profile": "PYP-FFA",
                }
            },
            created_by_user_id=user.id,
        )
        session.add(project)
        session.flush()
        configuration = AdminConfiguration(
            tenant_id=tenant.id,
            kind="business_case_governance_configuration",
            code=f"bc5c-{suffix}",
            name="Five Case PostgreSQL policy",
            status="published",
            revision=1,
            version=1,
            content_json=deepcopy(DEFAULT_CONFIGURATION),
            content_hash="c" * 64,
            created_by_user_id=user.id,
        )
        session.add(configuration)
        session.flush()
        case = BusinessCase(
            tenant_id=tenant.id,
            business_case_number=f"BC-5C-{suffix}",
            project_workspace_id=project.id,
            source_project_proposal_id=None,
            owning_workspace_id=project.id,
            owner_user_id=user.id,
            sponsor_user_id=user.id,
            status="ACTIVE",
            current_revision_id=None,
            material_change_review_json={},
            configuration_id=configuration.id,
            configuration_revision=1,
            configuration_hash=configuration.content_hash,
            configuration_source_workspace_id=None,
            configuration_resolution_chain_json=[],
            create_idempotency_key=f"create-{suffix}",
            created_by=user.id,
            updated_by=user.id,
        )
        session.add(case)
        session.flush()

        as_of = datetime(2026, 9, 18, 12, 0, 0)
        refs = {
            "_five_case": {
                "schema_version": "1.0",
                "integration_layer": True,
                "source_authority_preserved": True,
                "configuration_id": configuration.id,
                "configuration_hash": configuration.content_hash,
                "policy": deepcopy(DEFAULT_CONFIGURATION["five_case"]),
                "gate_context": {
                    "project_workspace_id": project.id,
                    "project_type": "CAPITAL",
                    "governance_model": "CAPITAL_OWNER",
                    "gate_profile": "PYP-FFA",
                    "fel_stage": "FFA",
                    "policy_stage": "FFA",
                    "decision_gate": None,
                    "revision_purpose": "FFA_UPDATE",
                    "as_of_date": as_of.isoformat(),
                },
            },
            "proposal": {"id": 1, "status": "READY", "readiness": "READY", "source_current": True},
            "business_analysis": {
                "id": 2,
                "status": "COMPLETED",
                "readiness": "READY",
                "recommended_option_id": "ALT-1",
                "recommended_option_current": True,
                "source_current": True,
            },
            "benefits": {"id": 3, "status": "COMPLETED", "readiness": "READY", "source_current": True},
            "commercial_strategy": {
                "id": 4,
                "status": "COMPLETED",
                "readiness": "READY",
                "source_current": True,
                "procurement_approach": "COMPETITIVE",
                "contracting_model": "EPC",
            },
            "fel": {"id": 5, "stage": "FFA", "readiness": "READY", "source_current": True},
            "budget": {"id": 6, "status": "FROZEN", "readiness": "READY", "source_current": True},
            "resource": {"id": 7, "status": "FROZEN", "readiness": "READY", "source_current": True},
            "funding": {"id": 8, "status": "READY", "readiness": "READY", "source_current": True},
            "economic_financial_model": {
                "id": 9,
                "status": "COMPLETED",
                "readiness": "READY",
                "source_current": True,
            },
            "risk": {"id": 10, "status": "READY", "readiness": "READY", "source_current": True},
            "permit": {"id": 11, "status": "READY", "readiness": "READY", "source_current": True},
        }
        hashes = {key: f"{index:x}" * 64 for index, key in enumerate(refs, start=1) if key != "_five_case"}
        revision = BusinessCaseRevision(
            tenant_id=tenant.id,
            business_case_id=case.id,
            revision_number=1,
            revision_label="R1",
            purpose="FFA_UPDATE",
            status="COMPLETED",
            as_of_date=as_of,
            fel_stage_code="FFA",
            title="Five Case PostgreSQL happy path",
            executive_summary="Governed Five Case synthesis",
            business_need="Validate all five Cases on PostgreSQL",
            strategic_alignment_json=[{"code": "STR-1"}],
            objectives_json=[{"description": "Validate readiness"}],
            scope_json={"in_scope": "Five Case"},
            alternatives_json=[{"id": "ALT-1"}],
            benefits_json=[{"description": "Decision readiness"}],
            assumptions_json=[],
            constraints_json=[],
            delivery_json={"approach": "stage gated"},
            unresolved_concerns_json=[],
            recommendation_json={"selected_alternative": "ALT-1"},
            source_references_json=refs,
            source_hashes_json=hashes,
            source_snapshot_hash="a" * 64,
            economic_financial_model_id=9,
            economic_financial_model_version=1,
            economic_financial_model_hash=hashes["economic_financial_model"],
            financial_model_status="AVAILABLE",
            economic_financial_readiness="READY",
            economic_financial_as_of_date=as_of,
            readiness_status="READY",
            readiness_warnings_json=[],
            readiness_blockers_json=[],
            readiness_hash="b" * 64,
            material_change_status="NO_MATERIAL_CHANGE",
            content_hash="d" * 64,
            preparer_user_id=user.id,
            reviewer_user_id=user.id,
            completed_at=as_of,
            completed_by=user.id,
            created_by=user.id,
            updated_by=user.id,
        )
        session.add(revision)
        session.flush()
        case.current_revision_id = revision.id
        session.flush()

        result = BusinessCaseService(session, tenant.id, user.id).revision_out(revision.id)

        assert result.legacy_layout is False
        assert result.source_current is True
        assert result.five_case_hash and result.source_bundle_hash and result.business_case_hash
        assert result.five_case_readiness_json == {
            "strategic_case": "READY",
            "economic_case": "READY",
            "commercial_case": "READY",
            "financial_case": "READY",
            "management_case": "READY",
            "overall_business_case_readiness": "READY",
        }
        assert len(result.source_evidence_matrix_json) == 20
    finally:
        session.close()
        transaction.rollback()
        connection.close()
