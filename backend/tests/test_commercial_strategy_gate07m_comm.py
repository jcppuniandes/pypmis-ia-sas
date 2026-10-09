"""Gate 07M-COMM acceptance coverage for governed commercial strategy."""

from copy import deepcopy
from time import perf_counter
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.domain.models import (
    AuthCredential,
    EnterpriseWorkspace,
    SecurityAccessAssignment,
    SecurityRole,
    UserAccount,
)
from app.main import app
from app.modules.commercial_strategy.models import CommercialStrategyVersion
from app.modules.commercial_strategy.service import (
    DEFAULT_CONFIGURATION,
    EVIDENCE_TYPE,
    PROVIDER_KEY,
    SOURCE_MODULE,
    CommercialStrategyService,
)
from app.modules.investment_evidence_policy.service import (
    DEFAULT_POLICY,
    PROVIDER_REGISTRY,
    InvestmentEvidencePolicyService,
)


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _fixture() -> tuple[
    Session,
    UserAccount,
    EnterpriseWorkspace,
    CommercialStrategyService,
]:
    db = SessionLocal()
    actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
    assert actor is not None
    suffix = uuid4().hex[:10]
    parent = db.scalar(
        select(EnterpriseWorkspace)
        .where(
            EnterpriseWorkspace.tenant_id == actor.tenant_id,
            EnterpriseWorkspace.workspace_type_code.in_(["enterprise", "business-unit", "portfolio"]),
        )
        .order_by(EnterpriseWorkspace.id)
    )
    if parent is None:
        parent = EnterpriseWorkspace(
            tenant_id=actor.tenant_id,
            parent_id=None,
            workspace_type_code="enterprise",
            code=f"COMM-ENT-{suffix}",
            external_key=f"comm-ent-{suffix}",
            record_code=f"COMM.ENT.{suffix}",
            name="Commercial Strategy Enterprise",
            status="active",
            defaults_json={},
            sort_order=1,
            version=1,
            created_by_user_id=actor.id,
        )
        db.add(parent)
        db.flush()
    project = EnterpriseWorkspace(
        tenant_id=actor.tenant_id,
        parent_id=parent.id,
        workspace_type_code="project",
        code=f"COMM-PRJ-{suffix}",
        external_key=f"comm-prj-{suffix}",
        record_code=f"COMM.PRJ.{suffix}",
        name=f"Commercial Strategy Project {suffix}",
        status="active",
        defaults_json={
            "_project": {
                "project_type": "CAPITAL",
                "governance_model": "CAPITAL_OWNER",
                "fel_stage": "FEL-3",
            }
        },
        sort_order=1,
        version=1,
        created_by_user_id=actor.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    service = CommercialStrategyService(db, actor.tenant_id, actor.id)
    service.ensure_seed()
    return db, actor, project, service


def _ready_content() -> dict:
    return {
        "commercial_context": {
            "business_need": "Deliver the governed project through a viable market route.",
            "scope_summary": "Capital works and specialist equipment packages.",
        },
        "procurement_approach": "EPC",
        "packages": [
            {
                "package_code": "PKG-001",
                "package_name": "Main works",
                "package_type": "WORK",
                "scope_summary": "Engineering, procurement and construction.",
            }
        ],
        "contracting_model": "LUMP_SUM",
        "market_assessment": {
            "overall_score": 80,
            "summary": "Sufficient qualified market capacity was confirmed.",
        },
        "supply_chain_constraints": [{"description": "Long-lead equipment", "critical": True, "status": "MITIGATED"}],
        "risk_allocations": [
            {
                "commercial_risk_category": "CONSTRUCTION",
                "risk_description": "Construction productivity",
                "preferred_owner": "CONTRACTOR",
                "allocation_rationale": "The contractor controls execution means and methods.",
                "contractual_treatment": "Lump-sum performance obligation",
                "mandatory": True,
            }
        ],
        "payment_mechanism": "MILESTONE",
        "incentive_strategy": {"mechanism": "PERFORMANCE_INCENTIVE"},
        "guarantees_securities_strategy": {"performance_bond": True},
        "commercial_assumptions": [],
        "commercial_constraints": [],
        "dependencies": [],
        "legal_regulatory_considerations": [],
        "alternatives": [
            {
                "procurement_approach": "EPC",
                "contracting_model": "LUMP_SUM",
                "risk_allocation": "Single-point design and construction accountability.",
                "payment_mechanism": "MILESTONE",
                "market_fit": "Strong fit with the qualified supplier market.",
                "commercial_risk": "Concentrated counterparty and interface risk.",
                "pros": ["Single-point accountability", "Clear commercial baseline"],
                "cons": ["Reduced owner flexibility after award"],
                "rating": 4,
            },
            {
                "procurement_approach": "EPCM",
                "contracting_model": "COST_REIMBURSABLE",
                "risk_allocation": "Owner retains package and interface accountability.",
                "payment_mechanism": "COST_REIMBURSABLE",
                "market_fit": "Suitable where package-level competition is available.",
                "commercial_risk": "Higher owner exposure to cost and interfaces.",
                "pros": ["Greater owner control", "Flexible package sequencing"],
                "cons": ["More complex interface governance"],
                "rating": 3,
            },
        ],
        "recommendation": {
            "recommended_procurement_approach": "EPC",
            "recommended_packaging_strategy": "Single integrated main-works package",
            "recommended_contracting_model": "LUMP_SUM",
            "recommended_payment_mechanism": "MILESTONE",
            "recommended_incentive_strategy": "PERFORMANCE_INCENTIVE",
            "rationale": "Single-point accountability is appropriate for the defined scope.",
            "commercial_recommendation_status": "RECOMMENDED",
        },
        "conditions_open_issues": [],
    }


def _reviewer(db, actor: UserAccount) -> UserAccount:
    reviewer = UserAccount(
        tenant_id=actor.tenant_id,
        email=f"comm-reviewer-{uuid4().hex[:10]}@example.test",
        full_name="Independent Commercial Reviewer",
        title="Commercial Strategy Reviewer",
        status="active",
    )
    db.add(reviewer)
    db.commit()
    db.refresh(reviewer)
    return reviewer


def _role_headers(client: TestClient, db: Session, actor: UserAccount, role_code: str) -> dict[str, str]:
    role = db.scalar(
        select(SecurityRole).where(
            SecurityRole.tenant_id == actor.tenant_id,
            SecurityRole.code == role_code,
        )
    )
    assert role is not None
    email = f"{role_code}-{uuid4().hex[:10]}@example.test"
    user = UserAccount(
        tenant_id=actor.tenant_id,
        email=email,
        full_name=f"Gate 07M-COMM {role_code}",
        title=role_code,
        status="active",
    )
    db.add(user)
    db.flush()
    db.add(
        AuthCredential(
            tenant_id=actor.tenant_id,
            user_id=user.id,
            provider="local",
            password_hash=hash_password("1234"),
            is_active=True,
        )
    )
    db.add(
        SecurityAccessAssignment(
            tenant_id=actor.tenant_id,
            subject_type="user",
            user_id=user.id,
            role_id=role.id,
            scope_type="organization",
            status="active",
            granted_by_user_id=actor.id,
        )
    )
    db.commit()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _complete_strategy(db, actor, project, service):
    create_key = f"comm-create-{uuid4()}"
    created = service.create(project.id, "INITIAL_COMMERCIAL_ASSESSMENT", create_key)
    duplicate = service.create(project.id, "INITIAL_COMMERCIAL_ASSESSMENT", create_key)
    assert duplicate.id == created.id
    assert duplicate.current_version_id == created.current_version_id
    version = created.current_version
    assert version is not None
    assert version.readiness_status == "BLOCKED"

    with pytest.raises(HTTPException) as stale_etag:
        service.update_version(
            created.id,
            version.id,
            version.revision_version + 10,
            content_json=_ready_content(),
            fel_stage_code="FEL-3",
            reviewer_user_id=None,
        )
    assert stale_etag.value.status_code == 412
    assert stale_etag.value.detail["code"] == "ETAG_MISMATCH"

    updated = service.update_version(
        created.id,
        version.id,
        version.revision_version,
        content_json=_ready_content(),
        fel_stage_code="FEL-3",
        reviewer_user_id=None,
    )
    assert updated.readiness_status == "READY"
    submit_key = f"comm-submit-{uuid4()}"
    submitted = service.submit(created.id, updated.id, updated.revision_version, submit_key)
    submit_duplicate = service.submit(created.id, updated.id, updated.revision_version, submit_key)
    assert submit_duplicate.id == submitted.id
    assert submit_duplicate.revision_version == submitted.revision_version

    with pytest.raises(HTTPException) as same_actor_review:
        service.start_review(
            created.id,
            submitted.id,
            submitted.revision_version,
            f"comm-review-sod-{uuid4()}",
        )
    assert same_actor_review.value.status_code == 409
    assert same_actor_review.value.detail["code"] == "SEPARATION_OF_DUTIES_REQUIRED"

    reviewer = _reviewer(db, actor)
    review_service = CommercialStrategyService(db, actor.tenant_id, reviewer.id)
    review_key = f"comm-review-{uuid4()}"
    reviewing = review_service.start_review(
        created.id,
        submitted.id,
        submitted.revision_version,
        review_key,
    )
    review_duplicate = review_service.start_review(
        created.id,
        submitted.id,
        submitted.revision_version,
        review_key,
    )
    assert review_duplicate.id == reviewing.id
    assert review_duplicate.revision_version == reviewing.revision_version
    complete_key = f"comm-complete-{uuid4()}"
    completed = review_service.complete(
        created.id,
        reviewing.id,
        reviewing.revision_version,
        complete_key,
    )
    complete_duplicate = review_service.complete(
        created.id,
        reviewing.id,
        reviewing.revision_version,
        complete_key,
    )
    assert complete_duplicate.id == completed.id
    assert complete_duplicate.commercial_strategy_hash == completed.commercial_strategy_hash
    return created, completed, review_service


def test_lifecycle_etag_idempotency_sod_provider_and_terminal_immutability() -> None:
    db, actor, project, service = _fixture()
    try:
        created, completed, review_service = _complete_strategy(db, actor, project, service)
        assert completed.status == "COMPLETED"
        assert completed.readiness_status == "READY"
        assert completed.can_supply_investment_gate_evidence is True

        provider = review_service.provider_evidence(project.id)
        assert provider.provider_key == PROVIDER_KEY
        assert provider.source_module == SOURCE_MODULE
        assert provider.evidence_type == EVIDENCE_TYPE
        assert provider.status == "AVAILABLE"
        assert provider.can_supply_investment_gate_evidence is True
        assert provider.overall_commercial_readiness == "READY"
        assert provider.blockers == []

        with pytest.raises(HTTPException) as terminal_update:
            service.update_version(
                created.id,
                completed.id,
                completed.revision_version,
                content_json=_ready_content(),
                fel_stage_code="FEL-3",
                reviewer_user_id=None,
            )
        assert terminal_update.value.detail["code"] == "COMMERCIAL_STRATEGY_VERSION_NOT_EDITABLE"

        stored = db.get(CommercialStrategyVersion, completed.id)
        assert stored is not None
        frozen_content = deepcopy(stored.content_json)
        stored.content_json = {**stored.content_json, "commercial_context": {"tampered": True}}
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()
        db.expire_all()
        stored = db.get(CommercialStrategyVersion, completed.id)
        assert stored is not None
        assert stored.content_json == frozen_content
    finally:
        db.rollback()
        db.close()


def test_return_void_and_physical_delete_protection() -> None:
    db, actor, project, service = _fixture()
    try:
        created = service.create(
            project.id,
            "INITIAL_COMMERCIAL_ASSESSMENT",
            f"comm-return-create-{uuid4()}",
        )
        version = created.current_version
        assert version is not None
        updated = service.update_version(
            created.id,
            version.id,
            version.revision_version,
            content_json=_ready_content(),
            fel_stage_code="FEL-3",
            reviewer_user_id=None,
        )
        submitted = service.submit(
            created.id,
            updated.id,
            updated.revision_version,
            f"comm-return-submit-{uuid4()}",
        )
        reviewer = _reviewer(db, actor)
        review_service = CommercialStrategyService(db, actor.tenant_id, reviewer.id)
        reviewing = review_service.start_review(
            created.id,
            submitted.id,
            submitted.revision_version,
            f"comm-return-review-{uuid4()}",
        )
        return_key = f"comm-return-{uuid4()}"
        returned = review_service.return_version(
            created.id,
            reviewing.id,
            reviewing.revision_version,
            return_key,
            "Clarify the package allocation rationale.",
        )
        return_duplicate = review_service.return_version(
            created.id,
            reviewing.id,
            reviewing.revision_version,
            return_key,
            "Clarify the package allocation rationale.",
        )
        assert return_duplicate.id == returned.id
        assert return_duplicate.revision_version == returned.revision_version
        assert return_duplicate.return_reason == "Clarify the package allocation rationale."
        with pytest.raises(HTTPException) as return_key_reuse:
            review_service.return_version(
                created.id,
                reviewing.id,
                reviewing.revision_version,
                return_key,
                "A different payload must not reuse the same key.",
            )
        assert return_key_reuse.value.detail["code"] == "IDEMPOTENCY_KEY_REUSED"

        void_key = f"comm-void-{uuid4()}"
        voided = service.void(
            created.id,
            returned.id,
            returned.revision_version,
            void_key,
            "The investment concept was withdrawn.",
        )
        void_duplicate = service.void(
            created.id,
            returned.id,
            returned.revision_version,
            void_key,
            "The investment concept was withdrawn.",
        )
        assert void_duplicate.id == voided.id
        assert void_duplicate.status == "VOIDED"
        assert void_duplicate.void_reason == "The investment concept was withdrawn."
        with pytest.raises(HTTPException) as void_key_reuse:
            service.void(
                created.id,
                returned.id,
                returned.revision_version,
                void_key,
                "A different payload must not reuse the same key.",
            )
        assert void_key_reuse.value.detail["code"] == "IDEMPOTENCY_KEY_REUSED"

        stored = db.get(CommercialStrategyVersion, voided.id)
        assert stored is not None
        db.delete(stored)
        with pytest.raises(ValueError, match="cannot be physically deleted"):
            db.commit()
        db.rollback()
        assert db.get(CommercialStrategyVersion, voided.id) is not None
    finally:
        db.rollback()
        db.close()


def test_readiness_negative_staleness_refresh_and_history_are_non_destructive() -> None:
    db, actor, project, service = _fixture()
    try:
        created = service.create(
            project.id,
            "INITIAL_COMMERCIAL_ASSESSMENT",
            f"comm-negative-create-{uuid4()}",
        )
        version = created.current_version
        assert version is not None
        blocked_content = _ready_content()
        blocked_content["market_assessment"]["overall_score"] = 30
        blocked_content["packages"][0]["package_type"] = "UNPUBLISHED_PACKAGE_TYPE"
        blocked_content["risk_allocations"][0]["commercial_risk_category"] = "UNPUBLISHED_RISK"
        blocked_content["risk_allocations"][0]["preferred_owner"] = ""
        blocked_content["alternatives"][0].pop("rating")
        blocked_content["conditions_open_issues"] = [
            {"description": "Confirm market appetite", "blocking": True, "status": "OPEN"}
        ]
        blocked = service.update_version(
            created.id,
            version.id,
            version.revision_version,
            content_json=blocked_content,
            fel_stage_code="FEL-3",
            reviewer_user_id=None,
        )
        assert blocked.readiness_status == "BLOCKED"
        assert {
            "MARKET_CAPABILITY_BELOW_THRESHOLD",
            "RISK_ALLOCATION_INCOMPLETE",
            "MANDATORY_HIGH_RISK_ITEM_UNALLOCATED",
            "BLOCKING_COMMERCIAL_ISSUE_UNRESOLVED",
            "PACKAGE_TYPE_NOT_IN_PUBLISHED_CATALOG:PKG-001",
            "RISK_CATEGORY_NOT_IN_PUBLISHED_CATALOG:UNPUBLISHED_RISK",
            "REQUIRED_ALTERNATIVE_FIELDS_MISSING",
        }.issubset(blocked.readiness_blockers_json)
        with pytest.raises(HTTPException) as rejected_submit:
            service.submit(
                created.id,
                blocked.id,
                blocked.revision_version,
                f"comm-blocked-submit-{uuid4()}",
            )
        assert rejected_submit.value.detail["code"] == "COMMERCIAL_STRATEGY_BLOCKED"

        repaired = service.update_version(
            created.id,
            blocked.id,
            blocked.revision_version,
            content_json=_ready_content(),
            fel_stage_code="FEL-3",
            reviewer_user_id=None,
        )
        submitted = service.submit(
            created.id,
            repaired.id,
            repaired.revision_version,
            f"comm-ready-submit-{uuid4()}",
        )
        reviewer = _reviewer(db, actor)
        review_service = CommercialStrategyService(db, actor.tenant_id, reviewer.id)
        reviewing = review_service.start_review(
            created.id,
            submitted.id,
            submitted.revision_version,
            f"comm-ready-review-{uuid4()}",
        )
        completed = review_service.complete(
            created.id,
            reviewing.id,
            reviewing.revision_version,
            f"comm-ready-complete-{uuid4()}",
        )
        completed_hash = completed.commercial_strategy_hash

        project.version += 1
        db.commit()
        stale = service.readiness(created.id)
        assert stale.status == "STALE"
        assert stale.source_current is False
        assert stale.can_supply_investment_gate_evidence is False
        assert "COMMERCIAL_STRATEGY_SOURCE_STALE" in stale.blockers
        provider = service.provider_evidence(project.id)
        assert provider.can_supply_investment_gate_evidence is False
        assert provider.overall_commercial_readiness == "STALE"

        preview = service.refresh_preview(created.id)
        assert preview.persisted is False
        assert preview.source_delta
        assert preview.recommended_version_purpose == "MATERIAL_CHANGE_UPDATE"
        refresh_key = f"comm-refresh-{uuid4()}"
        refreshed = service.refresh_apply(
            created.id,
            service.get(created.id).revision_version,
            refresh_key,
        )
        assert refreshed.status == "DRAFT"
        assert refreshed.version_number == 2
        refresh_duplicate = service.refresh_apply(
            created.id,
            service.get(created.id).revision_version,
            refresh_key,
        )
        assert refresh_duplicate.id == refreshed.id

        history = service.history(created.id)
        assert [item.version.version_number for item in history] == [2, 1]
        historical = history[1].version
        assert historical.status == "SUPERSEDED"
        assert historical.commercial_strategy_hash == completed_hash
        assert historical.content_json == _ready_content()
        event_types = {event["event_type"] for entry in history for event in entry.lifecycle_events}
        assert {
            "commercial_strategy.completed",
            "commercial_strategy.refresh_applied",
        }.issubset(event_types)
    finally:
        db.rollback()
        db.close()


def test_api_exposes_strong_etag_and_rejects_invalid_preconditions() -> None:
    db, _actor, project, service = _fixture()
    try:
        created = service.create(
            project.id,
            "INITIAL_COMMERCIAL_ASSESSMENT",
            f"comm-api-create-{uuid4()}",
        )
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "admin", "password": "1234", "tenant_slug": "demo-energy"},
            )
            assert login.status_code == 200, login.text
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            detail = client.get(f"/api/v1/commercial-strategies/{created.id}", headers=headers)
            assert detail.status_code == 200, detail.text
            assert detail.headers["ETag"] == f'"{created.revision_version}"'
            assert detail.headers["Cache-Control"] == "private, no-store"

            version = created.current_version
            assert version is not None
            invalid = client.put(
                f"/api/v1/commercial-strategies/{created.id}/versions/{version.id}",
                headers={**headers, "If-Match": "not-an-etag"},
                json={"content_json": _ready_content(), "fel_stage_code": "FEL-3"},
            )
            assert invalid.status_code == 400
            assert invalid.json()["detail"]["code"] == "INVALID_IF_MATCH"
            stale = client.put(
                f"/api/v1/commercial-strategies/{created.id}/versions/{version.id}",
                headers={**headers, "If-Match": '"99999"'},
                json={"content_json": _ready_content(), "fel_stage_code": "FEL-3"},
            )
            assert stale.status_code == 412
            assert stale.json()["detail"]["code"] == "ETAG_MISMATCH"
    finally:
        db.rollback()
        db.close()


def test_effective_options_catalogs_and_user_admin_permission_separation() -> None:
    db, actor, project, service = _fixture()
    try:
        created = service.create(
            project.id,
            "INITIAL_COMMERCIAL_ASSESSMENT",
            f"comm-permissions-create-{uuid4()}",
        )
        effective = service.options(project.id)
        assert effective.configuration_id == created.configuration_id
        assert effective.configuration_revision == created.configuration_revision
        assert effective.configuration_hash == created.configuration_hash
        assert "EPC" in effective.procurement_approaches
        assert "LUMP_SUM" in effective.contracting_models
        assert "WORK" in effective.package_types
        assert "CONSTRUCTION" in effective.risk_allocation_categories
        assert "MILESTONE" in effective.payment_mechanisms
        assert effective.operational_procurement_excluded is True

        with TestClient(app) as client:
            config_headers = _role_headers(
                client,
                db,
                actor,
                "commercial_strategy_config_admin",
            )
            assert (
                client.get(
                    "/api/v1/commercial-strategies/admin/configurations",
                    headers=config_headers,
                ).status_code
                == 200
            )
            assert (
                client.get(
                    "/api/v1/commercial-strategies/options",
                    headers=config_headers,
                    params={"project_workspace_id": project.id},
                ).status_code
                == 403
            )
            assert (
                client.get(
                    f"/api/v1/commercial-strategies/{created.id}",
                    headers=config_headers,
                ).status_code
                == 403
            )

            author_headers = _role_headers(client, db, actor, "commercial_strategy_author")
            options = client.get(
                "/api/v1/commercial-strategies/options",
                headers=author_headers,
                params={"project_workspace_id": project.id},
            )
            assert options.status_code == 200, options.text
            assert options.json()["configuration_hash"] == created.configuration_hash
            assert "EPC" in options.json()["procurement_approaches"]
            assert (
                client.get(
                    "/api/v1/commercial-strategies/admin/configurations",
                    headers=author_headers,
                ).status_code
                == 403
            )

            reviewer_headers = _role_headers(client, db, actor, "commercial_strategy_reviewer")
            assert (
                client.get(
                    f"/api/v1/commercial-strategies/{created.id}",
                    headers=reviewer_headers,
                ).status_code
                == 200
            )
            assert (
                client.get(
                    "/api/v1/commercial-strategies/admin/configurations",
                    headers=reviewer_headers,
                ).status_code
                == 403
            )
    finally:
        db.rollback()
        db.close()


def test_provider_registry_does_not_reclassify_default_gate07j_policy() -> None:
    policy_snapshot = deepcopy(DEFAULT_POLICY)
    registry_snapshot = deepcopy(PROVIDER_REGISTRY)
    service = InvestmentEvidencePolicyService(None, tenant_id=1, actor_id=1)

    providers = {item.provider_key: item for item in service.providers()}
    commercial = providers["COMMERCIAL_READINESS_PROVIDER"]
    assert commercial.status == "AVAILABLE"
    assert commercial.evidence_type == "COMMERCIAL_READINESS"
    assert PROVIDER_REGISTRY[commercial.provider_key]["compatible_evidence_types"] == ["CONTRACTING_STRATEGY_READINESS"]

    rows = [item for profile in DEFAULT_POLICY["gate_profiles"].values() for item in profile["requirements"]]
    assert not [item for item in rows if item["evidence_type"] == "COMMERCIAL_READINESS"]
    legacy_rows = [item for item in rows if item["evidence_type"] == "CONTRACTING_STRATEGY_READINESS"]
    assert len(legacy_rows) == 2
    assert all(item["classification"] == "B" for item in legacy_rows)
    assert all(item["provider_key"] is None and item["provider_required"] is False for item in legacy_rows)
    assert DEFAULT_POLICY == policy_snapshot
    assert PROVIDER_REGISTRY == registry_snapshot


def test_tailoring_applies_only_to_matching_project_context_and_rejects_invalid_rules() -> None:
    db, _actor, project, service = _fixture()
    try:
        project.defaults_json = {
            **dict(project.defaults_json or {}),
            "_project": {
                **dict((project.defaults_json or {}).get("_project", {})),
                "project_size": "LARGE",
                "project_risk": "HIGH",
                "project_complexity": "COMPLEX",
                "gate_profile": "CAPITAL_MAJOR",
            },
        }
        db.commit()
        configuration = deepcopy(DEFAULT_CONFIGURATION)
        configuration["tailoring_rules"] = [
            {
                "match": {
                    "project_size": ["LARGE"],
                    "project_risk": "HIGH",
                    "project_complexity": ["COMPLEX"],
                    "project_type": ["CAPITAL"],
                    "governance_model": ["CAPITAL_OWNER"],
                    "gate_profile": ["CAPITAL_MAJOR"],
                    "fel_stage": ["FEL-3"],
                },
                "overrides": {
                    "minimum_alternatives": 3,
                    "market_blocking_threshold": 75,
                    "required_fields": {"package": ["package_code", "package_name", "package_type"]},
                },
            }
        ]

        effective = service._tailored_policy(project, configuration, "FEL-3")
        assert effective["minimum_alternatives"] == 3
        assert effective["market_blocking_threshold"] == 75
        assert effective["required_fields"]["package"] == ["package_code", "package_name", "package_type"]

        unmatched = service._tailored_policy(project, configuration, "FEL-2")
        assert unmatched["minimum_alternatives"] == DEFAULT_CONFIGURATION["minimum_alternatives"]
        assert service._configuration_issues(
            {**configuration, "tailoring_rules": [{"match": [], "overrides": {}}]}
        ) == ["INVALID_TAILORING_RULES"]
        assert service._configuration_issues(
            {
                **configuration,
                "tailoring_rules": [{"when": {"project_size": "LARGE"}, "overrides": {"minimum_alternatives": 3}}],
            }
        ) == ["INVALID_TAILORING_RULES"]
    finally:
        db.rollback()
        db.close()


def test_list_and_detail_performance_remains_bounded() -> None:
    db, _actor, project, service = _fixture()
    try:
        created = service.create(
            project.id,
            "INITIAL_COMMERCIAL_ASSESSMENT",
            f"comm-performance-create-{uuid4()}",
        )
        list_samples: list[float] = []
        detail_samples: list[float] = []
        for _ in range(5):
            started = perf_counter()
            items, _cursor = service.list_page(
                queue="all_authorized",
                project_workspace_id=project.id,
                search="",
                limit=50,
                cursor=None,
            )
            list_samples.append((perf_counter() - started) * 1000)
            assert [item.id for item in items] == [created.id]

            started = perf_counter()
            detail = service.get(created.id)
            detail_samples.append((perf_counter() - started) * 1000)
            assert detail.id == created.id

        list_average = sum(list_samples) / len(list_samples)
        detail_average = sum(detail_samples) / len(detail_samples)
        print(f"COMM_PERFORMANCE list_avg_ms={list_average:.2f} detail_avg_ms={detail_average:.2f}")
        assert max(list_samples) < 2_000
        assert max(detail_samples) < 1_000
    finally:
        db.rollback()
        db.close()
