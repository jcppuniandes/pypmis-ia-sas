"""Real isolated SQLite policy lifecycle, audit and contextual snapshots.

Provider output is a contract test double here. Full PostgreSQL QRA/BC/FID and
browser acceptance are separately exercised by the disposable integration stack.
"""

import os
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from tests.test_qra_engine import _engine_settings
from tests.test_qra_evidence_policy import _context, _qra_criterion, _qra_requirement, _value

from app.core.time import utc_now
from app.database.session import Base
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, Project, SecurityEvent, Tenant, UserAccount
from app.modules.investment_evidence_policy.service import (
    CONFIGURATION_KIND,
    DEFAULT_POLICY,
    InvestmentEvidencePolicyService,
    _hash,
)
from app.modules.portfolio_planning.models import PortfolioProjectMembership
from app.modules.project_definition.models import ProjectFELStatus
from app.modules.qra_engine.service import QraEngineService
from app.modules.qra_foundation.policy import DEFAULT_CONFIGURATION


@pytest.fixture
def fixture_db():
    engine = create_engine("sqlite://")
    tables = [
        model.__table__
        for model in (
            Tenant,
            UserAccount,
            AdminConfiguration,
            EnterpriseWorkspace,
            Project,
            SecurityEvent,
            ProjectFELStatus,
            PortfolioProjectMembership,
        )
    ]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as db:
        tenant = Tenant(name="Disposable QRA policy", slug="disposable-qra-policy")
        db.add(tenant)
        db.flush()
        author = UserAccount(tenant_id=tenant.id, email="author@policy.test", full_name="Author")
        publisher = UserAccount(tenant_id=tenant.id, email="publisher@policy.test", full_name="Publisher")
        db.add_all([author, publisher])
        db.flush()
        portfolio = EnterpriseWorkspace(
            tenant_id=tenant.id,
            code="PF",
            record_code="PF",
            name="Portfolio",
            workspace_type_code="portfolio",
            created_by_user_id=author.id,
        )
        db.add(portfolio)
        db.flush()
        project = EnterpriseWorkspace(
            id=14,
            tenant_id=tenant.id,
            code="PR",
            record_code="PF.PR",
            name="Project",
            parent_id=portfolio.id,
            workspace_type_code="project",
            created_by_user_id=author.id,
            defaults_json={"_project": {**_context(), "gate_profile": "PYP-FFA"}},
        )
        db.add(project)
        db.commit()
        yield db, tenant, author, publisher, portfolio, project
    engine.dispose()


@pytest.fixture(params=["sqlite", "postgresql"])
def clone_constraint_db(request):
    """Exercise native VARCHAR semantics only on explicitly disposable PostgreSQL."""
    if request.param == "postgresql":
        url = os.getenv("PYPMIS_TEST_DATABASE_URL", "").strip()
        parsed = make_url(url) if url else None
        if (
            not parsed
            or parsed.get_backend_name() != "postgresql"
            or not (parsed.database or "").startswith("qra_evidence")
        ):
            pytest.skip("Native clone VARCHAR check requires explicit disposable qra_evidence PostgreSQL")
    else:
        url = "sqlite://"
    engine = create_engine(url)
    tables = [model.__table__ for model in (Tenant, UserAccount, AdminConfiguration, SecurityEvent)]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as db:
        tag = uuid4().hex
        tenant = Tenant(name="Disposable clone constraint", slug=f"clone-{tag}")
        db.add(tenant)
        db.flush()
        author = UserAccount(tenant_id=tenant.id, email=f"author-{tag}@clone.test", full_name="Clone author")
        publisher = UserAccount(tenant_id=tenant.id, email=f"publisher-{tag}@clone.test", full_name="Publisher")
        db.add_all([author, publisher])
        db.flush()
        source = AdminConfiguration(
            tenant_id=tenant.id,
            kind=CONFIGURATION_KIND,
            code=f"clone-{tag}",
            name=("Organización 漢字 😀 " * 20)[:180],
            description="Isolated repeated revisions; no operational policy publication.",
            status="published",
            revision=1,
            version=1,
            content_json=deepcopy(DEFAULT_POLICY),
            content_hash=_hash(DEFAULT_POLICY),
            published_at=utc_now(),
            created_by_user_id=author.id,
        )
        db.add(source)
        db.commit()
        yield db, tenant, author, publisher, source
    engine.dispose()


@pytest.mark.parametrize("clone_kind", ["normal", "evid2"])
def test_repeated_unicode_max_length_clones_preserve_suffix_source_audit_and_replay(clone_constraint_db, clone_kind):
    db, tenant, author, publisher, source = clone_constraint_db
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    publishing = InvestmentEvidencePolicyService(db, tenant.id, publisher.id)
    assert len(source.name) == 180 and len(source.name.encode("utf-8")) > 180
    original_source = source
    original = (source.name, source.content_hash, deepcopy(source.content_json), source.revision)
    original_version = source.version
    for _round in range(20):
        before = (source.name, source.content_hash, deepcopy(source.content_json), source.version, source.revision)
        count_before = db.scalar(
            select(func.count()).select_from(AdminConfiguration).where(AdminConfiguration.tenant_id == tenant.id)
        )
        key = f"clone-{uuid4()}"
        if clone_kind == "normal":
            clone = service.clone_configuration(source.id, source.version, key)
            replay = service.clone_configuration(source.id, source.version, key)
            suffix = f" · revision {clone.revision}"
        else:
            clone = service.clone_gate07j_evid2_configuration(source.id, source.version)
            replay = service.clone_gate07j_evid2_configuration(source.id, source.version)
            suffix = f" · Gate 07J-EVID-2 revision {clone.revision}"
            assert clone.content_json["_gate07j_evid2"] == {
                "source_policy_id": source.id,
                "source_policy_revision": source.revision,
                "source_policy_hash": source.content_hash,
            }
        assert replay.id == clone.id and clone.name.endswith(suffix)
        assert len(clone.name) <= 180
        assert db.scalar(select(func.length(AdminConfiguration.name)).where(AdminConfiguration.id == clone.id)) <= 180
        assert (
            db.scalar(
                select(func.count()).select_from(AdminConfiguration).where(AdminConfiguration.tenant_id == tenant.id)
            )
            == count_before + 1
        )
        audit = db.scalar(
            select(SecurityEvent).where(
                SecurityEvent.tenant_id == tenant.id,
                SecurityEvent.target_id == clone.id,
                SecurityEvent.event_type == "investment_evidence_policy.cloned",
            )
        ).metadata_json
        assert audit["source_policy_id"] == source.id
        assert audit["source_policy_revision"] == source.revision
        assert audit["source_policy_hash"] == source.content_hash
        assert audit["source_policy_name"] == before[0] and audit["clone_name"] == clone.name
        assert (source.name, source.content_hash, source.content_json, source.version, source.revision) == before
        source = publishing.publish_configuration(clone.id, clone.version)
        assert source.status == "published"
    assert (
        original_source.name,
        original_source.content_hash,
        original_source.content_json,
        original_source.revision,
    ) == original
    # Publishing the successor legitimately supersedes the old active policy.
    # Cloning itself left even the source version unchanged above; do not
    # confuse the established lifecycle transition with rewriting content.
    assert original_source.status == "superseded"
    assert original_source.version == original_version + 1


def test_real_lifecycle_clone_etag_sod_publish_history_and_idempotency(fixture_db):
    db, tenant, author, publisher, portfolio, project = fixture_db
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    service.ensure_seed()
    seed = service.configurations()[0]
    old = service.publish_configuration(seed.id, seed.version)
    baseline = deepcopy(old.content_json), old.content_hash, old.revision, _hash(project.defaults_json)
    _method(db, tenant, author)
    clone = service.clone_configuration(old.id, old.version, "new-qra-policy-123")
    assert service.clone_configuration(old.id, old.version, "new-qra-policy-123").id == clone.id
    content = deepcopy(clone.content_json)
    content["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    content["effective_from"] = (utc_now() - timedelta(seconds=1)).isoformat()
    content["sod"] = {"author_must_differ_from_publisher": True}
    content["gate_profiles"]["PYP-FFA"]["requirements"].extend([_qra_requirement(), _qra_requirement("SCHEDULE_QRA")])
    clone = service.update_configuration(clone.id, clone.version, "QRA contextual draft", "", content)
    with pytest.raises(HTTPException) as error:
        service.publish_configuration(clone.id, clone.version)
    assert error.value.status_code == 403
    published = InvestmentEvidencePolicyService(db, tenant.id, publisher.id).publish_configuration(
        clone.id, clone.version
    )
    assert published.status == "published" and published.published_at and published.content_json["effective_from"]
    assert published.content_hash == _hash(published.content_json)
    with pytest.raises(HTTPException) as error:
        service.update_configuration(published.id, published.version, "Attempt rewrite", "", content)
    assert error.value.status_code == 409
    assert (old.content_json, old.content_hash, old.revision, _hash(project.defaults_json)) == baseline
    bundle = service.qra_requirements_for_project(project.id)
    assert bundle["policy_ref"]["policy_id"] == published.id
    assert {row["evidence_type"] for row in bundle["requirements"]} == {"COST_QRA_RESULT", "SCHEDULE_QRA_RESULT"}
    snapshot = service.published_snapshot(portfolio.id, "PYP-FFA", [project.id])
    assert snapshot["effective_from"] and snapshot["scope"] == content["scope"]
    assert snapshot["new_round_policy"] == "CURRENT_EFFECTIVE_POLICY_AT_NEW_OR_EXPLICIT_REFRESH_PREPARATION"
    events = db.scalars(select(SecurityEvent).where(SecurityEvent.tenant_id == tenant.id)).all()
    assert any(
        event.event_type == "investment_evidence_policy.cloned" and event.metadata_json.get("idempotency_key")
        for event in events
    )
    assert any(
        event.event_type == "investment_evidence_policy.published" and event.user_id == publisher.id for event in events
    )


def test_real_preview_readonly_context_rows_compact_and_separate_types(fixture_db, monkeypatch):
    db, tenant, author, _publisher, _portfolio, project = fixture_db
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    service.ensure_seed()
    record = service.configurations()[0]
    content = deepcopy(record.content_json)
    content["gate_profiles"]["PYP-FFA"]["requirements"].extend([_qra_requirement(), _qra_requirement("SCHEDULE_QRA")])

    def provider(_self, _project_id, analysis_type=None, **_qualifiers):
        return _value(
            analysis_type,
            result_semantics={"currency": "USD", "unit": "DAYS", "schedule_method": "NORMALIZED_ELAPSED_TIME_V1"},
        )

    monkeypatch.setattr(QraEngineService, "provider_evidence", provider)
    before = (
        _hash([dict(row) for row in db.execute(select(AdminConfiguration.__table__)).mappings()]),
        db.scalar(select(SecurityEvent.id)),
        _hash(project.defaults_json),
    )
    preview = service.preview(
        portfolio_id=None,
        gate_profile_code="PYP-FFA",
        project_ids=[project.id],
        configuration_id=record.id,
        content_override=content,
    )
    rows = [row for row in preview.current_evidence_status if row.get("qra_summary")]
    assert len(rows) == 2 and {row["qra_summary"]["analysis_type"] for row in rows} == {"COST_QRA", "SCHEDULE_QRA"}
    assert all(row["status"] == "VALID" and row["qra_summary"]["tail_convergence_certified"] is False for row in rows)
    assert preview.persisted is False and preview.can_enter_fid is False
    assert (
        _hash([dict(row) for row in db.execute(select(AdminConfiguration.__table__)).mappings()]),
        db.scalar(select(SecurityEvent.id)),
        _hash(project.defaults_json),
    ) == before


def test_real_low_value_selection_and_noncapital_defaults_not_forced(fixture_db):
    db, tenant, author, _publisher, _portfolio, project = fixture_db
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    service.ensure_seed()
    content = deepcopy(service.configurations()[0].content_json)
    content["gate_profiles"]["PYP-INV-SELECT"]["requirements"].append(
        _qra_requirement(
            applicability="CONDITIONAL",
            value_band={"source": "PROJECT_CREATION_ESTIMATED_BUDGET", "currency": "USD", "minimum": 2000000},
        )
    )
    row = [
        row
        for row in service._effective_matrix(content, "PYP-INV-SELECT", [project])
        if row["evidence_type"] == "COST_QRA_RESULT"
    ][0]
    assert row["classification"] == "C" and row["qra_applicability"]["outcome"] == "NOT_REQUIRED"
    for governance in ("CONTRACTOR_DELIVERY", "DIRECT_INTERNAL", "LEGACY_UNCLASSIFIED"):
        project.defaults_json = {"_project": _context(governance_model=governance)}
        row = [
            row
            for row in service._effective_matrix(content, "PYP-INV-SELECT", [project])
            if row["evidence_type"] == "COST_QRA_RESULT"
        ][0]
        assert row["classification"] == "C" and not row["blocking"]


@pytest.mark.parametrize("limit,minimum_value,expected", [(800, 0, False), (1000, 0, True), (800, 2000000, True)])
def test_readonly_preview_numeric_qra_hurdle_affects_readiness_without_forcing_optional_context(
    fixture_db, monkeypatch, limit, minimum_value, expected
):
    db, tenant, author, _publisher, _portfolio, project = fixture_db
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    record = service.configurations()[0]
    content = deepcopy(record.content_json)
    content["gate_profiles"]["PYP-FFA"]["requirements"].append(
        _qra_requirement(
            applicability="CONDITIONAL",
            value_band={
                "source": "PROJECT_CREATION_ESTIMATED_BUDGET",
                "currency": "USD",
                "minimum": minimum_value,
            },
        )
    )
    criterion = _qra_criterion()
    criterion["expected_value"] = limit
    criterion["qra_criterion"]["target"]["value"] = limit
    content.setdefault("decision_criterion_policy", {}).setdefault("criteria_by_profile", {})["PYP-FFA"] = [criterion]

    def evidence(matrix, *_args):
        # Contract input double isolates preview's deterministic criteria from
        # unrelated providers; the separate Pg stack computes/accepts real QRA.
        row = next(row for row in matrix if row["evidence_type"] == "COST_QRA_RESULT")
        return [
            {
                "evidence_type": "COST_QRA_RESULT",
                "project_workspace_id": project.id,
                "classification": row["classification"],
                "blocking": row["blocking"],
                "status": "NOT_REQUIRED" if row["classification"] == "C" else "VALID",
                "source_current": True,
                "source_hash": "accepted-current-reference",
                "qra_applicability": row["qra_applicability"],
                "qra_summary": _value(),
                "blockers": [],
                "warnings": [],
            }
        ]

    monkeypatch.setattr(service, "_current_evidence", evidence)
    monkeypatch.setattr(service, "_missing_provider_analysis", lambda *_a, **_k: [])
    before = (
        _hash(record.content_json),
        record.version,
        _hash(project.defaults_json),
        db.scalar(select(SecurityEvent.id)),
    )
    preview = service.preview(
        portfolio_id=None,
        gate_profile_code="PYP-FFA",
        project_ids=[project.id],
        configuration_id=record.id,
        content_override=content,
    )
    evaluation = preview.decision_criteria[0]["preview_evaluations"][0]
    assert preview.would_be_ready_for_investment_gate is expected
    assert evaluation["result"] == ("NOT_APPLICABLE" if minimum_value else "SATISFIED" if expected else "NOT_SATISFIED")
    assert preview.persisted is False and preview.can_enter_fid is False
    assert evaluation["qra_evidence"]["tail_convergence_certified"] is False
    assert before == (
        _hash(record.content_json),
        record.version,
        _hash(project.defaults_json),
        db.scalar(select(SecurityEvent.id)),
    )
    assert not db.new and not db.dirty


def test_governed_fel_stage_overrides_metadata_readonly_with_provenance(fixture_db):
    db, tenant, author, _publisher, _portfolio, project = fixture_db
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    service.ensure_seed()
    configuration = service.configurations()[0]
    project.defaults_json = {"_project": {**_context(fel_stage="FEL-1"), "gate_profile": "PYP-FFA"}}
    status = ProjectFELStatus(
        tenant_id=tenant.id,
        project_workspace_id=project.id,
        current_stage_code="FEL-3",
        effective_framework_id=configuration.id,
        effective_framework_revision=configuration.revision,
        effective_framework_hash=configuration.content_hash,
        definition_source_hash="definition-source-hash",
        created_by=author.id,
        updated_by=author.id,
    )
    db.add(status)
    db.commit()
    before = _hash(project.defaults_json), status.revision_version, status.definition_source_hash
    content = deepcopy(configuration.content_json)
    content["gate_profiles"]["PYP-FFA"]["requirements"].append(_qra_requirement(fel_stage_filter=["FEL-3"]))
    matrix = service._effective_matrix(content, "PYP-FFA", [project])
    row = next(row for row in matrix if row["evidence_type"] == "COST_QRA_RESULT")
    assert row["qra_applicability"]["outcome"] == "REQUIRED" and row["fel_stage"] == "FEL-3"
    assert row["fel_source"] == {
        "provider": "PROJECT_FEL_STATUS",
        "id": status.id,
        "revision": status.revision_version,
        "hash": status.definition_source_hash,
    }
    context = service._resolved_project_contexts([project], matrix)[0]
    assert context["fel_stage"] == "FEL-3" and context["fel_source"] == row["fel_source"]
    assert before == (_hash(project.defaults_json), status.revision_version, status.definition_source_hash)
    assert not db.dirty


def test_missing_governed_profile_never_defaults_to_ffa(fixture_db):
    db, tenant, author, _publisher, _portfolio, project = fixture_db
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    project.defaults_json = {"_project": _context()}
    assert service.qra_requirements_for_project(project.id) == {
        "policy_ref": {},
        "gate_profile_code": None,
        "requirements": [],
    }


def _sibling_portfolio_context(fixture_db):
    db, tenant, author, _publisher, portfolio, project = fixture_db
    enterprise = EnterpriseWorkspace(
        tenant_id=tenant.id,
        code="ENT",
        record_code="ENT",
        name="Enterprise",
        workspace_type_code="enterprise",
        created_by_user_id=author.id,
    )
    db.add(enterprise)
    db.flush()
    portfolio.parent_id = enterprise.id
    project.parent_id = enterprise.id
    membership = PortfolioProjectMembership(
        tenant_id=tenant.id,
        project_workspace_id=project.id,
        portfolio_workspace_id=portfolio.id,
        is_target_portfolio=True,
        status="ACTIVE",
        effective_from=utc_now() - timedelta(seconds=1),
        created_by=author.id,
        updated_by=author.id,
    )
    db.add(membership)
    db.commit()
    return membership


def test_project_policy_reuses_current_governed_portfolio_membership_without_reparenting(fixture_db):
    db, tenant, author, _publisher, portfolio, project = fixture_db
    membership = _sibling_portfolio_context(fixture_db)
    before = project.parent_id, _hash(project.defaults_json)
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    content = deepcopy(service.configurations()[0].content_json)
    content["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    content["gate_profiles"]["PYP-FFA"]["requirements"].append(_qra_requirement())
    _method(db, tenant, author)
    seed = service.configurations()[0]
    draft = service.update_configuration(seed.id, seed.version, "Portfolio QRA evidence policy", "", content)
    published = service.publish_configuration(draft.id, draft.version)
    for declared in (None, portfolio.id):
        bundle = service.qra_requirements_for_project(project.id, portfolio_id=declared)
        assert bundle["policy_ref"]["policy_id"] == published.id
        assert bundle["requirements"][0]["qra_applicability"]["outcome"] == "REQUIRED"
        assert bundle["portfolio_context"]["membership_id"] == membership.id
        assert bundle["portfolio_context"]["source"] == "PORTFOLIO_PROJECT_MEMBERSHIP"
        assert bundle["policy_ref"]["portfolio_context"] == bundle["portfolio_context"]
        assert bundle["portfolio_context"]["effective_from"] == membership.effective_from.isoformat()
        assert bundle["portfolio_context"]["selection"] == (
            "PROPOSAL_TARGET" if declared is not None else "UNIQUE_ACTIVE_MEMBERSHIP"
        )
    assert before == (project.parent_id, _hash(project.defaults_json))


def test_multiple_portfolios_require_declared_context_and_expired_membership_cannot_grant_it(fixture_db):
    db, tenant, author, _publisher, portfolio, project = fixture_db
    _sibling_portfolio_context(fixture_db)
    other = EnterpriseWorkspace(
        tenant_id=tenant.id,
        code="OTHER",
        record_code="OTHER",
        name="Other portfolio",
        workspace_type_code="portfolio",
        created_by_user_id=author.id,
    )
    db.add(other)
    db.flush()
    membership = PortfolioProjectMembership(
        tenant_id=tenant.id,
        project_workspace_id=project.id,
        portfolio_workspace_id=other.id,
        status="ACTIVE",
        effective_from=utc_now() - timedelta(days=1),
        created_by=author.id,
        updated_by=author.id,
    )
    db.add(membership)
    db.commit()
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    seed = service.configurations()[0]
    original = service.publish_configuration(seed.id, seed.version)
    baseline = original.content_hash
    optional = service.qra_requirements_for_project(project.id)
    assert optional["requirements"] == []
    assert optional["portfolio_context"]["selection"] == "NO_APPLICABLE_QRA_REQUIREMENT"
    assert original.content_hash == baseline
    content = deepcopy(original.content_json)
    content["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    content["gate_profiles"]["PYP-FFA"]["requirements"].append(_qra_requirement())
    _method(db, tenant, author)
    draft = service.clone_configuration(original.id, original.version)
    draft = service.update_configuration(draft.id, draft.version, "Governed multi-Portfolio QRA", "", content)
    service.publish_configuration(draft.id, draft.version)
    with pytest.raises(HTTPException) as error:
        service.qra_requirements_for_project(project.id)
    assert error.value.detail["code"] == "QRA_PORTFOLIO_CONTEXT_NOT_EVALUABLE"
    assert service._qra_policy_workspace(project, portfolio.id)[0].id == portfolio.id
    membership.effective_to = utc_now() - timedelta(seconds=1)
    db.commit()
    assert service._qra_policy_workspace(project, None)[0].id == portfolio.id
    with pytest.raises(HTTPException) as error:
        service.qra_requirements_for_project(project.id, portfolio_id=other.id)
    assert error.value.detail["code"] == "QRA_PROJECT_PORTFOLIO_CONTEXT_NOT_GOVERNED"


def test_multi_portfolio_low_value_context_is_not_blocked_by_conditional_qra(fixture_db):
    db, tenant, author, _publisher, portfolio, project = fixture_db
    _sibling_portfolio_context(fixture_db)
    other = EnterpriseWorkspace(
        tenant_id=tenant.id,
        code="OTHER",
        record_code="OTHER",
        name="Other portfolio",
        workspace_type_code="portfolio",
        created_by_user_id=author.id,
    )
    db.add(other)
    db.flush()
    db.add(
        PortfolioProjectMembership(
            tenant_id=tenant.id,
            project_workspace_id=project.id,
            portfolio_workspace_id=other.id,
            status="ACTIVE",
            effective_from=utc_now() - timedelta(seconds=1),
            created_by=author.id,
            updated_by=author.id,
        )
    )
    db.commit()
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    content = deepcopy(service.configurations()[0].content_json)
    content["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    content["gate_profiles"]["PYP-FFA"]["requirements"].append(
        _qra_requirement(
            applicability="CONDITIONAL",
            value_band={"source": "PROJECT_CREATION_ESTIMATED_BUDGET", "currency": "USD", "minimum": 2000000},
        )
    )
    _method(db, tenant, author)
    seed = service.configurations()[0]
    draft = service.update_configuration(seed.id, seed.version, "Conditional multi-Portfolio QRA", "", content)
    service.publish_configuration(draft.id, draft.version)
    result = service.qra_requirements_for_project(project.id)
    assert result["requirements"] == [] and result["portfolio_context"]["status"] == "NOT_REQUIRED"


def test_row_cannot_widen_parent_policy_governance_scope(fixture_db):
    db, tenant, author, _publisher, _portfolio, project = fixture_db
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    content = deepcopy(service.configurations()[0].content_json)
    content["gate_profiles"]["PYP-FFA"]["requirements"].append(
        _qra_requirement(governance_model_filter=["CONTRACTOR_DELIVERY"])
    )
    project.defaults_json = {"_project": _context(governance_model="CONTRACTOR_DELIVERY")}
    row = next(
        row
        for row in service._effective_matrix(content, "PYP-FFA", [project])
        if row["evidence_type"] == "COST_QRA_RESULT"
    )
    assert row["classification"] == "C" and not row["required"]
    assert row["qra_applicability"]["outcome"] == "NOT_APPLICABLE"
    assert row["qra_applicability"]["reasons"] == ["OUTSIDE_PUBLISHED_POLICY_GOVERNANCE_SCOPE"]


def _method(db, tenant, author, settings=None, scope=None):
    content = deepcopy(DEFAULT_CONFIGURATION)
    content["reserved_engine_settings"] = settings or _engine_settings()
    if scope:
        content["scope"] = scope
    method = AdminConfiguration(
        tenant_id=tenant.id,
        kind="qra_methodology_configuration",
        code="disposable-method",
        name="Method",
        description="Isolated output contract",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        created_by_user_id=author.id,
    )
    db.add(method)
    db.commit()
    return method


def _criterion_policy(service, portfolio, *, percentile=90):
    content = deepcopy(service.configurations()[0].content_json)
    content["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    content["gate_profiles"]["PYP-FFA"]["requirements"].append(
        _qra_requirement(selected_percentiles=[50, 80, percentile])
    )
    criterion = _qra_criterion()
    criterion["qra_criterion"]["percentile"] = percentile
    content.setdefault("decision_criterion_policy", {}).setdefault("criteria_by_profile", {})["PYP-FFA"] = [criterion]
    return content


@pytest.mark.parametrize("percentile,method_percentiles,valid", [(90, [50, 80], False), (95, [50, 80, 95], True)])
def test_publish_validates_actual_output_contract_without_universal_p95_ban(
    fixture_db, percentile, method_percentiles, valid
):
    db, tenant, author, _publisher, portfolio, _project = fixture_db
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    content = _criterion_policy(service, portfolio, percentile=percentile)
    _method(db, tenant, author, _engine_settings(percentiles=method_percentiles))
    if valid:
        service._validate_qra_output_contract(content)
    else:
        with pytest.raises(HTTPException) as error:
            service._validate_qra_output_contract(content)
        assert any(
            "QRA_CRITERION_PERCENTILE_NOT_IN_PUBLISHED_OUTPUT_CONTRACT" in item for item in error.value.detail["issues"]
        )


def test_publish_missing_or_out_of_scope_method_does_not_mutate_draft(fixture_db):
    db, tenant, author, _publisher, portfolio, _project = fixture_db
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    content = _criterion_policy(service, portfolio)
    seed = service.configurations()[0]
    draft = service.update_configuration(seed.id, seed.version, "QRA criterion draft", "", content)
    before = draft.status, draft.version, draft.content_hash
    with pytest.raises(HTTPException) as error:
        service.publish_configuration(draft.id, draft.version)
    assert error.value.status_code == 422
    assert all("QRA_PUBLISHED_OUTPUT_CONTRACT_NOT_EVALUABLE" in issue for issue in error.value.detail["issues"])
    assert before == (draft.status, draft.version, draft.content_hash)
    other = EnterpriseWorkspace(
        tenant_id=tenant.id,
        code="OTHER",
        record_code="OTHER",
        name="Other portfolio",
        workspace_type_code="portfolio",
        created_by_user_id=author.id,
    )
    db.add(other)
    db.commit()
    _method(db, tenant, author, scope={"type": "portfolio", "workspace_id": other.id})
    with pytest.raises(HTTPException) as error:
        service._validate_qra_output_contract(content)
    assert all("QRA_PUBLISHED_OUTPUT_CONTRACT_NOT_EVALUABLE" in issue for issue in error.value.detail["issues"])


@pytest.mark.parametrize("with_projects", [True, False])
@pytest.mark.parametrize("percentile,method_percentiles,valid", [(90, [50, 80], False), (95, [50, 80, 95], True)])
def test_selected_output_contract_is_validated_without_numeric_gate_criterion(
    fixture_db, with_projects, percentile, method_percentiles, valid
):
    db, tenant, author, _publisher, portfolio, project = fixture_db
    service = InvestmentEvidencePolicyService(db, tenant.id, author.id)
    content = deepcopy(service.configurations()[0].content_json)
    content["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    content["gate_profiles"]["PYP-FFA"]["requirements"].append(
        _qra_requirement(selected_percentiles=[50, 80, percentile])
    )
    assert not any(
        item.get("source_evidence_type") in {"COST_QRA_RESULT", "SCHEDULE_QRA_RESULT"}
        for item in content.get("decision_criterion_policy", {}).get("criteria_by_profile", {}).get("PYP-FFA", [])
    )
    if not with_projects:
        # Keep the Project immutable: move only the disposable policy scope to an
        # empty portfolio and check the future-context methodology contract.
        empty = EnterpriseWorkspace(
            tenant_id=tenant.id,
            code="EMPTY",
            record_code="EMPTY",
            name="Empty portfolio",
            workspace_type_code="portfolio",
            created_by_user_id=author.id,
        )
        db.add(empty)
        db.commit()
        content["scope"] = {"type": "portfolio", "workspace_id": empty.id}
    before = _hash(project.defaults_json)
    _method(db, tenant, author, _engine_settings(percentiles=method_percentiles))
    if valid:
        service._validate_qra_output_contract(content)
    else:
        with pytest.raises(HTTPException) as error:
            service._validate_qra_output_contract(content)
        assert error.value.status_code == 422
        assert any("OUTPUT_CONTRACT" in issue for issue in error.value.detail["issues"])
    assert _hash(project.defaults_json) == before
