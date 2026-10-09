"""Wave 3B acceptance: organizational capability, never staffing or QRA."""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from tests.test_basic_data_wave2b import _fixture as basic_fixture
from tests.test_basic_data_wave2b import _workspace
from tests.test_capital_allocation_wave2a import _context, _token_headers, _user

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, SecurityAccessAssignment, SecurityRole
from app.main import app
from app.modules.owner_capability.models import OwnerCapabilityAssessment
from app.modules.owner_capability.schemas import (
    AssessmentActionIn,
    AssessmentCreateIn,
    AssessmentUpdateIn,
    CapabilityItemIn,
    ConfigurationCloneIn,
    ConfigurationPreviewIn,
    ConfigurationUpdateIn,
    GapIn,
    MitigationIn,
)
from app.modules.owner_capability.service import (
    CONFIGURATION_KIND,
    DEFAULT_CONFIGURATION,
    OwnerCapabilityService,
    _hash,
)
from app.modules.project_definition.models import ProjectFELStatus


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as value:
        yield value


def _key(action):
    return f"wave3b-{action}-{uuid4()}"


def _policy(scope_id, count=10):
    content = deepcopy(DEFAULT_CONFIGURATION)
    content["scope"] = {"type": "enterprise", "workspace_id": scope_id}
    names = [
        "sponsor",
        "project-controls",
        "technical-assurance",
        "mine-process-integration",
        "commercial",
        "interfaces",
        "permitting-coordination",
        "risk-assurance",
        "owner-engineer",
        "transition",
    ]
    if count > len(names):
        names += [f"configured-capability-{i}" for i in range(len(names), count)]
    content["dimensions"] = [{"code": n, "name": n.title()} for n in names[:count]]
    content["requirements"] = [
        {
            "requirement_code": n,
            "dimension": n,
            "name": n.title(),
            "minimum_maturity": "IMPLEMENTED",
            "minimum_evidence_quality": "VERIFIED",
            "blocking": n in {"sponsor", "project-controls"},
            "evidence_required": True,
            "responsible_function_required": n == "sponsor",
            "stage_rules": {"FEL-2": {"minimum_maturity": "DEFINED"}, "FEL-3": {"minimum_maturity": "IMPLEMENTED"}},
        }
        for n in names[:count]
    ]
    return content


def _fixture(db, *, count=10, fel=True):
    source = basic_fixture(db, count=2, fel=fel)
    author, reviewer, project = source["author"], source["reviewer"], source["project"]
    if fel:
        status = db.scalar(
            select(ProjectFELStatus).where(
                ProjectFELStatus.tenant_id == author.tenant_id, ProjectFELStatus.project_workspace_id == project.id
            )
        )
        status.current_stage_code = "FEL-3"
        status.revision_version += 1
        db.commit()
    preparer = OwnerCapabilityService(db, author.tenant_id, author.id, _context(author, "project_definition_manager"))
    final = OwnerCapabilityService(db, author.tenant_id, reviewer.id, _context(reviewer, "definition_reviewer"))
    seed = preparer.ensure_seed()
    draft = preparer.clone_configuration(
        seed.id,
        seed.version,
        ConfigurationCloneIn(code=_key("policy")[:100], target_workspace_id=source["enterprise"].id),
        _key("clone"),
    )
    draft = preparer.update_configuration(
        draft["id"],
        draft["version"],
        ConfigurationUpdateIn(name="Mining Owner capability", content_json=_policy(source["enterprise"].id, count)),
        _key("edit-policy"),
    )
    source.update(
        preparer=preparer,
        final=final,
        configuration=final.publish_configuration(draft["id"], draft["version"], _key("publish")),
    )
    return source


def _items(policy, *, maturity="IMPLEMENTED"):
    return [
        CapabilityItemIn(
            requirement_code=r["requirement_code"],
            current_maturity=maturity,
            evidence_quality="VERIFIED",
            confidence="HIGH",
            evidence_refs=[
                {
                    "reference": f"governance:{r['requirement_code']}",
                    "hash": _hash(r["requirement_code"]),
                    "version": "1",
                }
            ],
            source_date=utc_now().date(),
            responsible_function="Sponsor function" if r["requirement_code"] == "sponsor" else "Owner function",
        )
        for r in policy["requirements"]
    ]


def _draft(fixture, **kwargs):
    s = fixture["preparer"]
    row = s.create_assessment(fixture["project"].id, AssessmentCreateIn(), _key("create"))
    return s.update_assessment(
        row["id"],
        row["revision_version"],
        AssessmentUpdateIn(items=kwargs.pop("items", _items(fixture["configuration"]["content_json"])), **kwargs),
        _key("update"),
    )


def _complete(fixture, row):
    prepared = fixture["preparer"].submit(row["id"], row["revision_version"], AssessmentActionIn(), _key("submit"))
    reviewed = fixture["final"].review(row["id"], prepared["revision_version"], AssessmentActionIn(), _key("review"))
    return fixture["final"].complete(row["id"], reviewed["revision_version"], AssessmentActionIn(), _key("complete"))


def _grant(db, user, role_code, *, scope_type="organization", workspace_id=None):
    role = db.scalar(
        select(SecurityRole).where(SecurityRole.tenant_id == user.tenant_id, SecurityRole.code == role_code)
    )
    assert role
    db.add(
        SecurityAccessAssignment(
            tenant_id=user.tenant_id,
            subject_type="user",
            role_id=role.id,
            user_id=user.id,
            scope_type=scope_type,
            workspace_id=workspace_id,
            status="active",
            granted_by_user_id=user.id,
        )
    )
    db.commit()


def test_happy_path_immutable_provider_and_history(client):
    with SessionLocal() as db:
        f = _fixture(db)
        row = _draft(f)
        assert row["assessment_number"].startswith("OCA-")
        assert row["snapshot_json"]["coverage"]["percentage"] == 100
        assert f["preparer"].provider_evidence(f["project"].id)["status"] == "NOT_AVAILABLE"
        completed = _complete(f, row)
        assert completed["status"] == "COMPLETED"
        provider = f["final"].provider_evidence(f["project"].id)
        assert provider["status"] == "AVAILABLE" and provider["source_current"]
        assert provider["evidence_hash"] == completed["assessment_hash"]
        assert provider["configuration"]["hash"] == f["configuration"]["content_hash"]
        assert provider["configuration"]["version"] == f["configuration"]["version"]
        assert completed["snapshot_json"]["configuration"]["version"] == f["configuration"]["version"]
        assert f["final"].assessments(f["project"].id)["total"] == 1
        record = db.get(OwnerCapabilityAssessment, row["id"])
        record.comments = "illegal history rewrite"
        with pytest.raises(ValueError, match="immutable"):
            db.flush()
        db.rollback()
        assert f["final"].assessment(row["id"])["assessment_hash"] == completed["assessment_hash"]


def test_ninety_percent_cannot_hide_blocking_controls(client):
    with SessionLocal() as db:
        f = _fixture(db)
        items = _items(f["configuration"]["content_json"])
        items[1] = items[1].model_copy(update={"current_maturity": "INITIAL"})
        row = _draft(f, items=items)
        preview = f["preparer"].preview(row["id"])
        assert preview["coverage"]["percentage"] == 90
        assert preview["coverage"]["required"] == 10
        assert preview["readiness_status"] == "BLOCKED"
        assert "CAPABILITY_BLOCKER:project-controls" in preview["blockers"]
        completed = _complete(f, row)
        assert completed["snapshot_json"]["readiness_status"] == "BLOCKED"
        assert f["final"].provider_evidence(f["project"].id)["status"] == "NOT_AVAILABLE"


def test_same_defined_maturity_stage_aware(client):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        fel = db.scalar(select(ProjectFELStatus).where(ProjectFELStatus.project_workspace_id == f["project"].id))
        fel.current_stage_code = "FEL-2"
        db.commit()
        row = _draft(f, items=_items(f["configuration"]["content_json"], maturity="DEFINED"))
        assert f["preparer"].preview(row["id"])["readiness_status"] == "READY"
        fel.current_stage_code = "FEL-3"
        fel.revision_version += 1
        db.commit()
        assert f["preparer"].preview(row["id"])["readiness_status"] == "BLOCKED"


def test_missing_sponsor_accountability_blocks(client):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        items = _items(f["configuration"]["content_json"])
        items[0] = items[0].model_copy(update={"responsible_function": ""})
        row = _draft(f, items=items)
        result = f["preparer"].preview(row["id"])
        assert "CAPABILITY_BLOCKER:sponsor" in result["blockers"]
        sponsor = next(r for r in result["requirements"] if r["requirement_code"] == "sponsor")
        assert sponsor["gaps"].count("ACCOUNTABILITY_MISSING") == 1


def test_external_support_requires_policy_and_independent_acceptance(client):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        s, final = f["preparer"], f["final"]
        source = f["configuration"]
        clone = s.clone_configuration(source["id"], source["version"], ConfigurationCloneIn(), _key("mit-policy"))
        content = deepcopy(clone["content_json"])
        content["mitigation_acceptance_rules"] = {
            "accepted_mitigation_sufficient": True,
            "allowed_approaches": ["EXTERNAL_SPECIALIST"],
            "required_statuses": ["IMPLEMENTED"],
            "require_closure_evidence": True,
        }
        clone = s.update_configuration(
            clone["id"],
            clone["version"],
            ConfigurationUpdateIn(name=clone["name"], content_json=content),
            _key("mit-edit"),
        )
        f["configuration"] = final.publish_configuration(clone["id"], clone["version"], _key("mit-publish"))
        items = _items(content)
        items[1] = items[1].model_copy(
            update={"current_maturity": "NOT_ESTABLISHED", "capability_source": "EXTERNAL_CONTRACTED"}
        )
        row = _draft(f, items=items)
        mitigation = MitigationIn(
            requirement_code="project-controls",
            approach="EXTERNAL_SPECIALIST",
            description="Contracted owner-controls strengthening",
            owner="Controls function",
            status="IMPLEMENTED",
            closure_evidence=[{"reference": "signed-owner-engineer-service"}],
        )
        row = s.save_mitigation(row["id"], row["revision_version"], mitigation, _key("mitigation"))
        assert s.preview(row["id"])["readiness_status"] == "BLOCKED"
        completed = _complete(f, row)
        assert completed["snapshot_json"]["readiness_status"] == "READY"
        assert "SATISFIED_BY_GOVERNED_MITIGATION:project-controls" in completed["snapshot_json"]["warnings"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("fel_stage", "FEL-2"),
        ("governance_model", "DIRECT_INTERNAL"),
        ("complexity", "LOW"),
        ("delivery_model", "EPCM"),
    ],
)
def test_material_context_stale_historical_unchanged(client, field, value):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        completed = _complete(f, _draft(f))
        snapshot = deepcopy(completed["snapshot_json"])
        if field == "fel_stage":
            status = db.scalar(select(ProjectFELStatus).where(ProjectFELStatus.project_workspace_id == f["project"].id))
            status.current_stage_code = value
            status.revision_version += 1
        else:
            metadata = deepcopy(f["project"].defaults_json)
            metadata["_project"][field] = value
            f["project"].defaults_json = metadata
        db.commit()
        assert f["final"].current_readiness(f["project"].id)["readiness_status"] == "STALE"
        assert f["final"].provider_evidence(f["project"].id)["status"] == "NOT_AVAILABLE"
        historical = f["final"].assessment(completed["id"])
        assert historical["snapshot_json"] == snapshot
        assert historical["assessment_hash"] == completed["assessment_hash"]


def test_policy_stale_refresh_successor_and_retry(client):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        completed = _complete(f, _draft(f))
        s, final = f["preparer"], f["final"]
        clone = s.clone_configuration(
            f["configuration"]["id"], f["configuration"]["version"], ConfigurationCloneIn(), _key("next")
        )
        final.publish_configuration(clone["id"], clone["version"], _key("publish-next"))
        assert final.current_readiness(f["project"].id)["readiness_status"] == "STALE"
        assert not s.refresh_preview(completed["id"])["persisted"]
        key = _key("refresh")
        successor = s.refresh_apply(completed["id"], completed["revision_version"], AssessmentActionIn(), key)
        assert successor["status"] == "DRAFT" and successor["predecessor_id"] == completed["id"]
        assert s.refresh_apply(completed["id"], completed["revision_version"], AssessmentActionIn(), key) == successor
        assert final.assessment(completed["id"])["assessment_hash"] == completed["assessment_hash"]
        assert final.provider_evidence(f["project"].id)["status"] == "NOT_AVAILABLE"


def test_etag_idempotency_and_all_edit_authors_sod(client):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        s = f["preparer"]
        key = _key("create")
        row = s.create_assessment(f["project"].id, AssessmentCreateIn(), key)
        assert s.create_assessment(f["project"].id, AssessmentCreateIn(), key) == row
        with pytest.raises(HTTPException) as caught:
            s.create_assessment(f["project"].id, AssessmentCreateIn(title="different"), key)
        assert caught.value.status_code == 409
        with pytest.raises(HTTPException) as caught:
            s.update_assessment(row["id"], 99, AssessmentUpdateIn(), _key("badetag"))
        assert caught.value.status_code == 412
        editor = f["final"]
        edited = editor.update_assessment(
            row["id"],
            row["revision_version"],
            AssessmentUpdateIn(items=_items(f["configuration"]["content_json"])),
            _key("editor"),
        )
        submitted = s.submit(row["id"], edited["revision_version"], AssessmentActionIn(), _key("submit"))
        for actor in [s, editor]:
            with pytest.raises(HTTPException) as caught:
                actor.review(row["id"], submitted["revision_version"], AssessmentActionIn(), _key("self-review"))
            assert caught.value.status_code == 403


@pytest.mark.parametrize("model", ["CONTRACTOR_DELIVERY", "DIRECT_INTERNAL"])
def test_governance_model_not_required_unless_opted_in(client, model):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        metadata = deepcopy(f["project"].defaults_json)
        metadata["_project"]["governance_model"] = model
        f["project"].defaults_json = metadata
        db.commit()
        assert f["preparer"].evaluate(f["project"].id)["readiness_status"] == "NOT_APPLICABLE"
        with pytest.raises(HTTPException) as caught:
            f["preparer"].create_assessment(f["project"].id, AssessmentCreateIn(), _key("inapplicable"))
        assert caught.value.status_code == 422
        clone = f["preparer"].clone_configuration(
            f["configuration"]["id"], f["configuration"]["version"], ConfigurationCloneIn(), _key("opt-in-clone")
        )
        content = deepcopy(clone["content_json"])
        content["applicability"]["governance_models"] = [model]
        clone = f["preparer"].update_configuration(
            clone["id"],
            clone["version"],
            ConfigurationUpdateIn(name="Explicit governance opt-in", content_json=content),
            _key("opt-in-edit"),
        )
        f["configuration"] = f["final"].publish_configuration(clone["id"], clone["version"], _key("opt-in-publish"))
        resolved = f["preparer"].requirements(f["project"].id)
        assert resolved["applicable"] and len(resolved["requirements"]) == 2
        completed = _complete(f, _draft(f))
        assert completed["snapshot_json"]["readiness_status"] == "READY"
        assert f["final"].provider_evidence(f["project"].id)["status"] == "AVAILABLE"


@pytest.mark.parametrize(
    "project_type,industry", [("MINING", "MINING"), ("INFRASTRUCTURE", "INFRASTRUCTURE"), ("INDUSTRIAL", "INDUSTRIAL")]
)
def test_tailoring_sector_is_configured_not_hardcoded(client, project_type, industry):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        clone = f["preparer"].clone_configuration(
            f["configuration"]["id"], f["configuration"]["version"], ConfigurationCloneIn(), _key("sector-clone")
        )
        content = deepcopy(clone["content_json"])
        configured_minimums = {"MINING": "EFFECTIVE", "INFRASTRUCTURE": "DEFINED", "INDUSTRIAL": "IMPLEMENTED"}
        content["requirements"][0]["project_type_rules"] = {
            code: {"minimum_maturity": minimum} for code, minimum in configured_minimums.items()
        }
        content["requirements"][1]["applicability"] = {"industries": ["MINING", "INDUSTRIAL"]}
        clone = f["preparer"].update_configuration(
            clone["id"],
            clone["version"],
            ConfigurationUpdateIn(name="Configured sector tailoring", content_json=content),
            _key("sector-edit"),
        )
        f["final"].publish_configuration(clone["id"], clone["version"], _key("sector-publish"))
        project = _workspace(db, f["author"], f["enterprise"], project_type=project_type)
        metadata = deepcopy(project.defaults_json)
        metadata["_project"]["industry"] = industry
        project.defaults_json = metadata
        db.commit()
        resolved = f["preparer"].requirements(project.id)
        assert len(resolved["requirements"]) == (1 if industry == "INFRASTRUCTURE" else 2)
        assert resolved["requirements"][0]["minimum_maturity"] == configured_minimums[project_type]
        assert resolved["context"]["project_type"] == project_type


def test_read_contexts_and_preview_never_write_source_authority(client):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        statements = []

        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE")):
                statements.append(statement)

        event.listen(db.bind, "before_cursor_execute", capture)
        try:
            f["preparer"].contexts(f["project"].id)
            f["preparer"].evaluate(f["project"].id)
            f["preparer"].configuration_preview(
                ConfigurationPreviewIn(configuration_id=f["configuration"]["id"], project_id=f["project"].id)
            )
        finally:
            event.remove(db.bind, "before_cursor_execute", capture)
        assert statements == []


def test_quality_confidence_semantics_are_distinct_and_scale_configurable(client):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        policy = deepcopy(f["configuration"]["content_json"])
        policy["evidence_quality_scale"][1]["code"] = "LOW_CONFIDENCE"
        issues = f["preparer"]._configuration_issues(policy)
        assert "QUALITY_CONFIDENCE_AMBIGUITY_NOT_ALLOWED" in issues
        policy = deepcopy(f["configuration"]["content_json"])
        policy["maturity_scale"][3]["name"] = "Owner mechanisms operating"
        assert f["preparer"]._configuration_issues(policy) == []
        assert "LOW_CONFIDENCE" not in f["preparer"].options()["quality_values"]


def test_critical_gap_remains_blocker_even_with_accepted_mitigation(client):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        clone = f["preparer"].clone_configuration(
            f["configuration"]["id"], f["configuration"]["version"], ConfigurationCloneIn(), _key("gap-clone")
        )
        content = deepcopy(clone["content_json"])
        content["mitigation_acceptance_rules"] = {
            "accepted_mitigation_sufficient": True,
            "allowed_approaches": ["EXTERNAL_SPECIALIST"],
            "required_statuses": ["IMPLEMENTED"],
            "require_closure_evidence": True,
        }
        clone = f["preparer"].update_configuration(
            clone["id"],
            clone["version"],
            ConfigurationUpdateIn(name="Governed mitigation never waives gap", content_json=content),
            _key("gap-edit"),
        )
        f["configuration"] = f["final"].publish_configuration(clone["id"], clone["version"], _key("gap-publish"))
        items = _items(content)
        items[1] = items[1].model_copy(update={"current_maturity": "NOT_ESTABLISHED"})
        row = _draft(
            f,
            items=items,
            gaps=[
                GapIn(
                    requirement_code="project-controls",
                    description="No accountable controls mechanism",
                    severity="CRITICAL",
                    blocking=True,
                )
            ],
        )
        readiness = f["preparer"].preview(row["id"])
        assert readiness["coverage"]["percentage"] == 50 and readiness["readiness_status"] == "BLOCKED"
        row = f["preparer"].save_mitigation(
            row["id"],
            row["revision_version"],
            MitigationIn(
                requirement_code="project-controls",
                approach="EXTERNAL_SPECIALIST",
                description="Implemented externally strengthened controls mechanism",
                status="IMPLEMENTED",
                closure_evidence=[{"source_reference": "SIGNED-CONTROLS-SERVICE"}],
            ),
            _key("gap-mitigation"),
        )
        completed = _complete(f, row)
        result = completed["snapshot_json"]
        control = next(r for r in result["requirements"] if r["requirement_code"] == "project-controls")
        assert control["accepted_mitigations"]
        assert "MATURITY_BELOW_REQUIRED" not in control["gaps"]
        assert "UNRESOLVED_CAPABILITY_GAP" in control["gaps"]
        assert result["readiness_status"] == "BLOCKED" and "CAPABILITY_BLOCKER:project-controls" in result["blockers"]
        assert f["final"].provider_evidence(f["project"].id)["status"] == "NOT_AVAILABLE"


def test_direct_routes_config_only_preparer_scope_and_tenant_denials(client):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        config_only = _user(db, f["author"].tenant_id, "owner-config-only")
        _grant(db, config_only, "configuration_admin")
        row = _draft(f)
        response = client.post(
            f"/api/v1/owner-capability/projects/{f['project'].id}/assessments",
            json={},
            headers=_token_headers(config_only) | {"Idempotency-Key": _key("config-live")},
        )
        assert response.status_code == 403
        preparer = _user(db, f["author"].tenant_id, "owner-preparer")
        _grant(db, preparer, "definition_assessor")
        response = client.get("/api/v1/owner-capability/admin/configurations", headers=_token_headers(preparer))
        assert response.status_code == 403
        context = replace(
            _context(preparer, "definition_assessor"),
            organization_wide=False,
            workspace_ids=frozenset({f["enterprise"].id + 1000000}),
        )
        service = OwnerCapabilityService(db, f["author"].tenant_id, preparer.id, context)
        with pytest.raises(HTTPException) as caught:
            service.assessment(row["id"])
        assert caught.value.status_code == 403
        alien = OwnerCapabilityService(db, f["author"].tenant_id + 1000000, preparer.id)
        with pytest.raises(HTTPException) as caught:
            alien.assessment(row["id"])
        assert caught.value.status_code == 404


def test_configuration_sod_cannot_be_disabled_by_current_editor(client):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        row = f["preparer"].clone_configuration(
            f["configuration"]["id"], f["configuration"]["version"], ConfigurationCloneIn(), _key("clone")
        )
        content = deepcopy(row["content_json"])
        content["separation_of_duties"]["author_cannot_publish"] = False
        row = f["preparer"].update_configuration(
            row["id"], row["version"], ConfigurationUpdateIn(name=row["name"], content_json=content), _key("disable")
        )
        with pytest.raises(HTTPException) as caught:
            f["preparer"].publish_configuration(row["id"], row["version"], _key("self-publish"))
        assert caught.value.status_code == 403
        assert db.get(AdminConfiguration, row["id"]).kind == CONFIGURATION_KIND


def test_expired_evidence_stale_and_provider_negative(client):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        items = _items(f["configuration"]["content_json"])
        items[1] = items[1].model_copy(update={"expires_on": utc_now().date() - timedelta(days=1)})
        row = _draft(f, items=items)
        assert f["preparer"].preview(row["id"])["readiness_status"] == "BLOCKED"
        completed = _complete(f, row)
        assert completed["snapshot_json"]["source_current"] is False
        assert f["final"].provider_evidence(f["project"].id)["status"] == "NOT_AVAILABLE"


@pytest.mark.parametrize(
    "path,value",
    [
        (("requirements", 0, "dimension"), {}),
        (("requirements", 0, "requirement_code"), 5),
        (("requirements", 0, "minimum_maturity"), {}),
        (("requirements", 0, "minimum_evidence_quality"), {}),
        (("requirements", 0, "allowed_capability_sources"), "INTERNAL"),
        (
            ("requirements", 0, "mitigation_acceptance_rules"),
            {"accepted_mitigation_sufficient": True, "allowed_approaches": [{}]},
        ),
        (("mitigation_acceptance_rules", "require_closure_evidence"), "false"),
        (("mitigation_acceptance_rules", "required_statuses"), [{}]),
        (("freshness", "material_context_sources"), "commercial"),
        (("freshness", "material_context_sources"), ["unknown-source"]),
        (("freshness", "max_age_days"), "thirty"),
        (("numbering", "separator"), None),
        (("scope", "type"), {}),
        (("scope", "workspace_id"), True),
        (("scope", "workspace_id"), None),
        (("dimensions", 0, "active"), "false"),
        (("stage_rules",), {"FEL-3": {"minimum_maturity": {}}}),
        (("effective_to",), 25),
        (("framework",), []),
        (("framework", "code"), {}),
        (("framework", "name"), None),
    ],
)
def test_malformed_configuration_returns_422_not_runtime_error(path, value):
    policy = _policy(1, count=2)
    target = policy
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    service = OwnerCapabilityService(None, 1, 1)
    with pytest.raises(HTTPException) as caught:
        service._validate_configuration(policy)
    assert caught.value.status_code == 422


def test_effective_date_range_and_executable_policy_rejected():
    service = OwnerCapabilityService(None, 1, 1)
    policy = _policy(1, count=2)
    policy.update(effective_from="2026-10-08", effective_to="2026-10-07")
    assert "INVALID_EFFECTIVE_DATE_RANGE" in service._configuration_issues(policy)
    policy["requirements"][0]["expression"] = "not executable"
    assert "EXECUTABLE_POLICY_NOT_ALLOWED" in service._configuration_issues(policy)


def test_empty_draft_framework_still_validates_global_tailoring_rule_types():
    service = OwnerCapabilityService(None, 1, 1)
    policy = deepcopy(DEFAULT_CONFIGURATION)
    policy["stage_rules"] = {"FEL-3": {"minimum_maturity": {}}}
    with pytest.raises(HTTPException) as caught:
        service._validate_configuration(policy)
    assert caught.value.status_code == 422
    assert "INVALID_MINIMUM_MATURITY" in caught.value.detail["issues"]


def test_null_effective_from_resolves_as_unbounded_not_runtime_error(client):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        row = f["preparer"].clone_configuration(
            f["configuration"]["id"], f["configuration"]["version"], ConfigurationCloneIn(), _key("nullable-clone")
        )
        content = deepcopy(row["content_json"])
        content.update(effective_from=None, effective_to=None)
        row = f["preparer"].update_configuration(
            row["id"],
            row["version"],
            ConfigurationUpdateIn(name=row["name"], content_json=content),
            _key("nullable-edit"),
        )
        published = f["final"].publish_configuration(row["id"], row["version"], _key("nullable-publish"))
        assert f["preparer"].requirements(f["project"].id)["configuration"]["id"] == published["id"]


def test_inapplicable_admin_preview_has_zero_exact_requirement_denominator(client):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        policy = deepcopy(f["configuration"]["content_json"])
        policy["applicability"] = {"governance_models": ["DIRECT_INTERNAL"]}
        preview = f["preparer"].configuration_preview(
            ConfigurationPreviewIn(
                configuration_id=f["configuration"]["id"],
                project_id=f["project"].id,
                content_json=policy,
            )
        )
        assert preview["persisted"] is False
        assert preview["readiness"]["readiness_status"] == "NOT_APPLICABLE"
        assert preview["readiness"]["coverage"]["required"] == 0
        assert preview["readiness"]["requirements"] == []


def test_clock_only_next_day_without_expiry_does_not_stale_completed_evidence(client, monkeypatch):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        completed = _complete(f, _draft(f))
        tomorrow = utc_now() + timedelta(days=1)
        monkeypatch.setattr("app.modules.owner_capability.service.utc_now", lambda: tomorrow)
        current = f["final"].current_readiness(f["project"].id)
        assert current["readiness_status"] == "READY" and current["source_current"]
        assert f["final"].provider_evidence(f["project"].id)["status"] == "AVAILABLE"
        historical = f["final"].assessment(completed["id"])
        assert historical["assessment_hash"] == completed["assessment_hash"]
        assert historical["snapshot_json"] == completed["snapshot_json"]


def test_current_risk_readiness_context_reuses_read_only_expiry_projection(client, monkeypatch):
    from tests.test_risk_readiness_gate07j_risk import _complete as complete_risk
    from tests.test_risk_readiness_gate07j_risk import _low_risk, _publish

    from app.modules.risk_readiness.models import RiskReadinessAssessment
    from app.modules.risk_readiness.service import RiskReadinessService

    with SessionLocal() as db:
        f = _fixture(db, count=2)
        risk_service = RiskReadinessService(db, f["author"].tenant_id, f["author"].id)
        _publish(risk_service)
        _low_risk(risk_service, f["project"].id)
        risk = complete_risk(risk_service, f["project"].id)
        baseline_hash = risk.risk_readiness_hash
        current = f["preparer"].contexts(f["project"].id)["risk_readiness"]
        assert current["status"] == "READY" and current["source_current"]
        tomorrow = risk.valid_until + timedelta(days=1)
        monkeypatch.setattr("app.modules.risk_readiness.service.utc_now", lambda: tomorrow)
        writes = []

        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE")):
                writes.append(statement)

        event.listen(db.bind, "before_cursor_execute", capture)
        try:
            expired = f["preparer"].contexts(f["project"].id)["risk_readiness"]
        finally:
            event.remove(db.bind, "before_cursor_execute", capture)
        assert expired["status"] == "EXPIRED" and not expired["source_current"]
        assert "RISK_READINESS_EXPIRED" in expired["blockers"]
        assert writes == []
        historical = db.get(RiskReadinessAssessment, risk.id)
        assert historical.readiness_status == "READY" and historical.risk_readiness_hash == baseline_hash


@pytest.mark.parametrize("area", ["assessment", "gap", "mitigation"])
@pytest.mark.parametrize("bad_ref", [{}, {"reference": "  "}, {"source_reference": 42}])
def test_empty_or_unidentifiable_evidence_refs_rejected_by_direct_api(client, area, bad_ref):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        row = _draft(f)
        baseline = deepcopy(row["aggregate_json"])
        items = _items(f["configuration"]["content_json"])
        gaps, mitigations = [], []
        if area == "assessment":
            items[0] = items[0].model_copy(update={"evidence_refs": [bad_ref]})
        elif area == "gap":
            gaps = [
                GapIn(
                    requirement_code="sponsor",
                    description="A closed gap requires identifiable proof",
                    status="CLOSED",
                    closure_evidence=[bad_ref],
                )
            ]
        else:
            mitigations = [
                MitigationIn(
                    requirement_code="sponsor",
                    approach="EXTERNAL_SPECIALIST",
                    description="An implemented mitigation requires identifiable proof",
                    status="IMPLEMENTED",
                    closure_evidence=[bad_ref],
                )
            ]
        payload = AssessmentUpdateIn(items=items, gaps=gaps, mitigations=mitigations)
        response = client.put(
            f"/api/v1/owner-capability/assessments/{row['id']}",
            json=payload.model_dump(mode="json"),
            headers=_token_headers(f["author"])
            | {"If-Match": str(row["revision_version"]), "Idempotency-Key": _key("invalid-ref")},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "OWNER_CAPABILITY_INVALID_EVIDENCE_REFERENCE"
        db.expire_all()
        stored = db.get(OwnerCapabilityAssessment, row["id"])
        assert stored.aggregate_json == baseline and stored.revision_version == row["revision_version"]


@pytest.mark.parametrize("area", ["assessment", "gap", "mitigation"])
def test_stored_empty_evidence_references_never_supply_ready_coverage_or_mitigation(area):
    policy = _policy(1, count=1)
    policy["mitigation_acceptance_rules"] = {
        "accepted_mitigation_sufficient": True,
        "allowed_approaches": ["EXTERNAL_SPECIALIST"],
        "required_statuses": ["IMPLEMENTED"],
        "require_closure_evidence": True,
    }
    aggregate = {"items": [i.model_dump(mode="json") for i in _items(policy)], "gaps": [], "mitigations": []}
    if area == "assessment":
        aggregate["items"][0]["evidence_refs"] = [{}]
    elif area == "gap":
        aggregate["gaps"] = [
            {
                "requirement_code": "sponsor",
                "status": "CLOSED",
                "blocking": True,
                "closure_evidence": [{}],
            }
        ]
    else:
        aggregate["items"][0]["current_maturity"] = "NOT_ESTABLISHED"
        aggregate["mitigations"] = [
            {
                "id": 1,
                "requirement_code": "sponsor",
                "approach": "EXTERNAL_SPECIALIST",
                "status": "IMPLEMENTED",
                "accepted_by": 2,
                "closure_evidence": [{}],
            }
        ]
    result = OwnerCapabilityService(None, 1, 1).evaluate(
        1,
        aggregate,
        resolved={
            "policy": policy,
            "configuration": {"id": 1, "revision": 1, "version": 1, "hash": _hash(policy)},
            "context": {"governance_model": "CAPITAL_OWNER"},
            "requirements": policy["requirements"],
            "dimensions": policy["dimensions"],
            "maturity_scale": policy["maturity_scale"],
            "quality_scale": policy["evidence_quality_scale"],
            "applicable": True,
        },
    )
    assert result["readiness_status"] == "BLOCKED" and result["coverage"]["percentage"] == 0
    assert result["requirements"][0]["accepted_mitigations"] == []
    assert {} not in result["evidence_refs"]


@pytest.mark.parametrize("reference_key", ["source_reference", "reference"])
def test_real_evidence_aliases_preserved_without_requiring_optional_metadata(reference_key):
    ref = {reference_key: "CHARTER-001"}
    assert OwnerCapabilityService._valid_references([ref])
    assert not OwnerCapabilityService._valid_references([ref, {}])
    assert not OwnerCapabilityService._valid_references([{"hash": "abc", "version": "1"}])


@pytest.mark.parametrize("exclusion", ["inheritance", "future", "expired"])
def test_admin_effective_preview_matches_user_inheritance_and_effective_date_exclusions(client, exclusion):
    with SessionLocal() as db:
        f = _fixture(db, count=2)
        clone = f["preparer"].clone_configuration(
            f["configuration"]["id"], f["configuration"]["version"], ConfigurationCloneIn(), _key("excluded-clone")
        )
        content = deepcopy(clone["content_json"])
        if exclusion == "inheritance":
            content["inherit_to_descendants"] = False
        elif exclusion == "future":
            content["effective_from"] = (utc_now().date() + timedelta(days=1)).isoformat()
        else:
            content["effective_to"] = (utc_now().date() - timedelta(days=1)).isoformat()
        clone = f["preparer"].update_configuration(
            clone["id"],
            clone["version"],
            ConfigurationUpdateIn(name="Policy excluded for current Project", content_json=content),
            _key("excluded-edit"),
        )
        candidate = f["final"].publish_configuration(clone["id"], clone["version"], _key("excluded-publish"))
        preview = f["preparer"].configuration_preview(
            ConfigurationPreviewIn(configuration_id=candidate["id"], project_id=f["project"].id)
        )
        assert not preview["persisted"] and not preview["readiness"]["applicable"]
        assert preview["readiness"]["requirements"] == [] and preview["readiness"]["coverage"]["required"] == 0
        current = f["preparer"].requirements(f["project"].id)
        assert current["configuration"]["id"] == f["configuration"]["id"]
        assert current["configuration"]["id"] != candidate["id"]
