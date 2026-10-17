"""Real source-domain lifecycle adapters for fresh current-baseline strategic UAT.

No adapter inserts a business record, sets a terminal state, or modifies a
published configuration through the ORM. Callers own the disposable tenant,
canonical Project, real RBAC assignments and surrounding staged BC/FEL flow.
All source identifiers passed to Benefits refer to that same fresh chain.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

from tests.test_commercial_strategy_gate07m_comm import _ready_content

from app.core.time import utc_now
from app.modules.basic_data.schemas import (
    AssessmentActionIn as BasicAction,
)
from app.modules.basic_data.schemas import (
    AssessmentCreateIn as BasicAssessment,
)
from app.modules.basic_data.schemas import (
    ConfigurationCloneIn,
    ConfigurationUpdateIn,
    ItemCreateIn,
    ItemValidateIn,
)
from app.modules.basic_data.service import DEFAULT_CONFIGURATION as BASIC_DEFAULT
from app.modules.basic_data.service import BasicDataService, _hash
from app.modules.commercial_strategy.service import CommercialStrategyService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.owner_capability.schemas import (
    AssessmentActionIn as OwnerAction,
)
from app.modules.owner_capability.schemas import (
    AssessmentCreateIn as OwnerAssessment,
)
from app.modules.owner_capability.schemas import (
    AssessmentUpdateIn as OwnerUpdate,
)
from app.modules.owner_capability.schemas import (
    CapabilityItemIn,
)
from app.modules.owner_capability.service import DEFAULT_CONFIGURATION as OWNER_DEFAULT
from app.modules.owner_capability.service import OwnerCapabilityService
from app.modules.permit_readiness.schemas import (
    AssessmentActionIn as PermitAction,
)
from app.modules.permit_readiness.schemas import (
    AssessmentCreateIn as PermitAssessment,
)
from app.modules.permit_readiness.schemas import (
    ConditionCreateIn,
    ConditionUpdateIn,
    PermitCreateIn,
    PermitStatusIn,
)
from app.modules.permit_readiness.service import PermitReadinessService
from app.modules.strategic_benefits.schemas import BenefitCreateIn, BenefitMeasureCreateIn, BenefitOwnerIn
from app.modules.strategic_benefits.service import StrategicBenefitsService


def _key(action: str) -> str:
    return f"fresh-capital-{action}-{uuid4().hex}"


def _service(cls, db, tenant_id: int, actor_id: int, permission: str):
    """Resolve actual grants, rather than constructing an omnipotent context."""
    context = require_enterprise_permission(db, tenant_id, actor_id, permission, bootstrap=False)
    return cls(db, tenant_id, actor_id, context)


def _configuration_ref(record) -> dict:
    if isinstance(record, dict):
        return {key: record[key] for key in ("id", "revision", "status", "content_hash")}
    return {"id": record.id, "revision": record.revision, "status": record.status, "content_hash": record.content_hash}


def configure_current_sources(
    db,
    tenant_id: int,
    config_author_id: int,
    config_publisher_id: int,
    enterprise_workspace_id: int,
    *,
    project_type_code: str = "MINING",
) -> dict:
    """Publish isolated enterprise-scoped successors, preserving all default rules.

    Basic Data and Owner Capability ship deliberately empty DRAFT catalogues.
    The UAT configuration supplies explicit study/control requirements with 100%
    coverage and independent publication. It does not relax any existing policy.
    """
    assert config_author_id != config_publisher_id
    result = {}
    for name, cls, prefix in (
        ("benefits", StrategicBenefitsService, "benefits_plan"),
        ("commercial", CommercialStrategyService, "commercial_strategy"),
    ):
        author = _service(cls, db, tenant_id, config_author_id, f"{prefix}.admin.configure")
        publisher = _service(cls, db, tenant_id, config_publisher_id, f"{prefix}.admin.publish")
        author.ensure_seed()
        source = next(item for item in author.configurations() if item.status == "published")
        draft = author.clone_configuration(source.id, source.version)
        content = deepcopy(source.content_json)
        content["scope"] = {"workspace_id": enterprise_workspace_id, "inherit_to_descendants": True}
        draft = author.update_configuration(
            draft.id,
            draft.version,
            f"Fresh UAT {name}",
            "Isolated current-default successor, no relaxed rules",
            content,
        )
        result[name] = _configuration_ref(publisher.publish_configuration(draft.id, draft.version))

    permit_author = _service(
        PermitReadinessService, db, tenant_id, config_author_id, "permit_readiness.admin.configure"
    )
    permit_publisher = _service(
        PermitReadinessService, db, tenant_id, config_publisher_id, "permit_readiness.admin.publish"
    )
    source = permit_author.ensure_seed()
    draft = source if source.status == "draft" else permit_author.clone_configuration(source.id, source.version)
    content = deepcopy(draft.content_json)
    content["scope_workspace_id"] = enterprise_workspace_id
    # The current starter taxonomy may use the configured generic CAPITAL
    # equivalent rather than MINING. Add this UAT scope's actual type without
    # removing any existing Mining requirement or changing evidence/coverage.
    for requirement in content["requirements"]:
        requirement["applicable_project_types"] = sorted(
            set(requirement["applicable_project_types"]) | {project_type_code.upper()}
        )
    # Strengthen rather than weaken the default neutral Permit SoD.
    content["separation_of_duties"] = {
        **content["separation_of_duties"],
        "permit_preparer_cannot_complete": True,
        "assessment_author_cannot_complete": True,
    }
    draft = permit_author.update_configuration(
        draft.id, draft.version, "Fresh UAT Permit readiness", "Mining requirements unchanged", content
    )
    result["permit"] = _configuration_ref(permit_publisher.publish_configuration(draft.id, draft.version))

    basic_content = deepcopy(BASIC_DEFAULT)
    basic_content["scope"] = {"type": "enterprise", "workspace_id": enterprise_workspace_id}
    basic_codes = ("geotechnical", "process-design", "site-and-water", "environmental-baseline")
    basic_content["categories"] = [{"code": code, "name": code.replace("-", " ").title()} for code in basic_codes]
    basic_content["requirements"] = [
        {
            "requirement_code": code,
            "category": code,
            "name": f"Controlled {code} study",
            "blocking": True,
            "minimum_quality": "VALIDATED",
            "minimum_confidence": "HIGH",
            "minimum_validation_state": "VALIDATED",
            "minimum_availability": "AVAILABLE",
            "evidence_required": True,
            "max_age_days": 365,
        }
        for code in basic_codes
    ]
    owner_content = deepcopy(OWNER_DEFAULT)
    owner_content["scope"] = {"type": "enterprise", "workspace_id": enterprise_workspace_id}
    owner_codes = ("sponsor", "project-controls", "technical-assurance", "permitting-coordination")
    owner_content["dimensions"] = [{"code": code, "name": code.replace("-", " ").title()} for code in owner_codes]
    owner_content["requirements"] = [
        {
            "requirement_code": code,
            "dimension": code,
            "name": code.replace("-", " ").title(),
            "minimum_maturity": "IMPLEMENTED",
            "minimum_evidence_quality": "VERIFIED",
            "blocking": True,
            "evidence_required": True,
            "responsible_function_required": True,
        }
        for code in owner_codes
    ]
    for name, cls, prefix, content in (
        ("basic_data", BasicDataService, "basic_data", basic_content),
        ("owner_capability", OwnerCapabilityService, "owner_capability", owner_content),
    ):
        author = _service(cls, db, tenant_id, config_author_id, f"{prefix}.admin.configure")
        publisher = _service(cls, db, tenant_id, config_publisher_id, f"{prefix}.admin.publish")
        seed = author.ensure_seed()
        draft = author.clone_configuration(
            seed.id,
            seed.version,
            ConfigurationCloneIn(code=_key(name)[:120], target_workspace_id=enterprise_workspace_id),
            _key(f"{name}-clone"),
        )
        draft = author.update_configuration(
            draft["id"],
            draft["version"],
            ConfigurationUpdateIn(name=f"Fresh UAT {name}", content_json=content),
            _key(f"{name}-configure"),
        )
        result[name] = _configuration_ref(
            publisher.publish_configuration(draft["id"], draft["version"], _key(f"{name}-publish"))
        )
    return result


def complete_benefits(
    db,
    tenant_id: int,
    author_id: int,
    reviewer_id: int,
    project_id: int,
    *,
    idea_id: int,
    analysis_id: int,
    proposal_id: int,
    business_case_id: int,
    objective_code: str,
) -> dict:
    assert author_id != reviewer_id
    author = _service(StrategicBenefitsService, db, tenant_id, author_id, "benefits_plan.create")
    reviewer = _service(StrategicBenefitsService, db, tenant_id, reviewer_id, "benefits_plan.complete")
    plan = author.create(project_id, "INITIAL_BENEFITS_PLAN", _key("benefits-create"))
    version = plan.current_version
    assert version is not None
    version = author.update_version(
        plan.id,
        version.id,
        version.revision_version,
        overview_json={"purpose": "Governed copper processing expansion benefits", "value_thesis": "Improve recovery"},
        outputs_json=[{"id": "COPPER-OUT", "name": "Expanded processing capability", "type": "OUTPUT"}],
        outcomes_json=[
            {"id": "COPPER-OC", "name": "Improved copper recovery", "source_output_refs": [{"id": "COPPER-OUT"}]}
        ],
        assumptions_json=[{"statement": "Comparable feed and independently verified production data"}],
        constraints_json=[{"statement": "No operational benefits realization executed by this test"}],
        fel_stage_code="FEL-3",
        reviewer_user_id=reviewer_id,
    )
    benefit = author.add_benefit(
        plan.id,
        version.id,
        version.revision_version,
        _key("benefit-create"),
        BenefitCreateIn(
            benefit_name="Copper recovery improvement",
            benefit_description="Increase recoverable copper from comparable controlled feed",
            benefit_direction="BENEFIT",
            benefit_type="FINANCIAL",
            benefit_category="VALUE",
            strategic_objective_refs=[{"code": objective_code}],
            source_need_reference={"id": idea_id, "type": "IDEA"},
            source_business_analysis_reference={"id": analysis_id, "type": "BUSINESS_ANALYSIS"},
            source_project_proposal_reference={"id": proposal_id},
            source_business_case_reference={"id": business_case_id},
            expected_outputs=[{"id": "COPPER-OUT"}],
            expected_outcomes=[{"id": "COPPER-OC"}],
            benefit_statement="Increase governed copper recovery without automatic investment authorization",
            owner=BenefitOwnerIn(
                owner_type="USER",
                owner_user_id=author_id,
                accountability_statement="Own the controlled baseline, target and measurement plan",
                acceptance_status="ACCEPTED",
            ),
            expected_value={"amount": 30_000_000, "currency": "USD", "basis": "annual additional revenue"},
            monetizable_flag=True,
        ),
    )
    version = author.get(plan.id).current_version
    author.add_measure(
        plan.id,
        version.id,
        benefit.id,
        version.revision_version,
        _key("benefit-measure"),
        BenefitMeasureCreateIn(
            measure_code="COPPER-RECOVERY",
            measure_name="Controlled copper recovery percentage",
            definition="Comparable-feed recovery independently checked against the production balance",
            unit_of_measure="PERCENT",
            direction="INCREASE",
            is_primary=True,
            baseline_status="KNOWN",
            baseline_value=82,
            baseline_as_of_date=utc_now().date(),
            baseline_source="Isolated UAT copper balance study",
            baseline_evidence_reference=f"UAT-STUDY-{project_id}-RECOVERY",
            baseline_confidence="HIGH",
            target_value=90,
            target_date=utc_now().date() + timedelta(days=730),
            target_basis="Independent option assessment target",
            measurement_method="Governed mass balance on comparable feed",
            measurement_frequency="ANNUAL",
            data_source_description="Controlled copper study",
            measurement_owner_reference={"user_id": author_id},
        ),
    )
    version = author.get(plan.id).current_version
    submitted = author.submit(plan.id, version.id, version.revision_version, _key("benefits-submit"))
    reviewing = reviewer.start_review(plan.id, submitted.id, submitted.revision_version, _key("benefits-review"))
    completed = reviewer.complete(plan.id, reviewing.id, reviewing.revision_version, _key("benefits-complete"))
    assert completed.status == "COMPLETED"
    return {
        "id": plan.id,
        "version_id": completed.id,
        "hash": completed.benefits_plan_hash,
        "provider": reviewer.provider_evidence(project_id).model_dump(mode="json"),
    }


def complete_commercial(db, tenant_id: int, author_id: int, reviewer_id: int, project_id: int) -> dict:
    assert author_id != reviewer_id
    author = _service(CommercialStrategyService, db, tenant_id, author_id, "commercial_strategy.create")
    reviewer = _service(CommercialStrategyService, db, tenant_id, reviewer_id, "commercial_strategy.complete")
    strategy = author.create(project_id, "INITIAL_COMMERCIAL_ASSESSMENT", _key("commercial-create"))
    version = strategy.current_version
    assert version is not None
    content = _ready_content()  # Payload only: no fixture, identity, configuration or final-state seed.
    content["commercial_context"]["business_need"] = "Governed copper processing expansion investment"
    version = author.update_version(
        strategy.id,
        version.id,
        version.revision_version,
        content_json=content,
        fel_stage_code="FEL-3",
        reviewer_user_id=reviewer_id,
    )
    submitted = author.submit(strategy.id, version.id, version.revision_version, _key("commercial-submit"))
    reviewing = reviewer.start_review(strategy.id, submitted.id, submitted.revision_version, _key("commercial-review"))
    completed = reviewer.complete(strategy.id, reviewing.id, reviewing.revision_version, _key("commercial-complete"))
    assert completed.status == "COMPLETED"
    return {
        "id": strategy.id,
        "version_id": completed.id,
        "hash": completed.commercial_strategy_hash,
        "provider": reviewer.provider_evidence(project_id).model_dump(mode="json"),
    }


def complete_permits(db, tenant_id: int, author_id: int, reviewer_id: int, project_id: int) -> dict:
    assert author_id != reviewer_id
    author = _service(PermitReadinessService, db, tenant_id, author_id, "permit_readiness.create")
    reviewer = _service(PermitReadinessService, db, tenant_id, reviewer_id, "permit_readiness.complete")
    # Real normal readiness context resolves the effective catalogue; no taxonomy invention.
    context = author.project_readiness(project_id)
    configuration = author._published_configuration(author._project(project_id))
    assert configuration is not None
    requirements = [
        r
        for r in configuration.content_json["requirements"]
        if author._project_type(author._project(project_id)) in r["applicable_project_types"]
        or "*" in r["applicable_project_types"]
    ]
    assert requirements, context.model_dump(mode="json")
    ids = []
    for requirement in requirements:
        permit = author.create_permit(
            project_id,
            PermitCreateIn(
                permit_type_code=requirement["permit_type_code"],
                requirement_key=requirement["requirement_key"],
                title=requirement["description"],
                issuing_authority="Isolated UAT competent authority",
                application_reference=_key("permit-application"),
                application_date=utc_now().date() - timedelta(days=90),
                approval_date=utc_now().date() - timedelta(days=30),
                effective_from=utc_now().date() - timedelta(days=30),
                valid_until=utc_now().date() + timedelta(days=365),
                permit_identifier=_key("permit-authorization"),
                evidence_refs=[{"reference": _key("permit-decision-document")}],
                idempotency_key=_key("permit-create"),
            ),
        )
        for state in ("IN_PREPARATION", "SUBMITTED", "UNDER_REVIEW", "APPROVED_WITH_CONDITIONS"):
            permit = author.change_permit_status(
                permit.id, permit.revision_version, PermitStatusIn(status=state, idempotency_key=_key("permit-state"))
            )
        condition = author.create_condition(
            permit.id,
            ConditionCreateIn(
                condition_key=_key("condition"),
                description="Record controlled pre-investment monitoring protocol",
                blocking=True,
                owner_id=author_id,
                status="OPEN",
                idempotency_key=_key("condition-create"),
            ),
        )
        for state in ("EVIDENCE_PROVIDED", "SATISFIED"):
            condition = reviewer.update_condition(
                condition.id,
                condition.revision_version,
                ConditionUpdateIn(
                    description=condition.description,
                    blocking=True,
                    owner_id=author_id,
                    status=state,
                    evidence_refs=[{"reference": _key("monitoring-protocol")}],
                ),
            )
        permit = author.change_permit_status(
            permit.id,
            permit.revision_version,
            PermitStatusIn(status="APPROVED", idempotency_key=_key("permit-approved")),
        )
        ids.append(permit.id)
    assessment = author.create_assessment(
        project_id,
        PermitAssessment(
            gate_profile_code="PYP-FFA",
            idempotency_key=_key("permit-assessment"),
        ),
    )
    completed = reviewer.complete_assessment(
        assessment.id, assessment.revision_version, PermitAction(idempotency_key=_key("permit-complete"))
    )
    assert completed.status == "COMPLETED" and completed.readiness_status == "READY"
    return {
        "id": completed.id,
        "permit_ids": ids,
        "hash": completed.permit_readiness_hash,
        "provider": reviewer.project_readiness(project_id).model_dump(mode="json"),
    }


def complete_basic_data(db, tenant_id: int, author_id: int, reviewer_id: int, project_id: int) -> dict:
    assert author_id != reviewer_id
    author = _service(BasicDataService, db, tenant_id, author_id, "basic_data.item.create")
    reviewer = _service(BasicDataService, db, tenant_id, reviewer_id, "basic_data.assessment.complete")
    requirements = author.requirements(project_id)["requirements"]
    assert requirements
    ids = []
    for requirement in requirements:
        code = requirement["requirement_code"]
        item = author.create_item(
            project_id,
            ItemCreateIn(
                requirement_code=code,
                availability="AVAILABLE",
                quality="VALIDATED",
                confidence="HIGH",
                source_type="STUDY_REFERENCE",
                source_reference=f"UAT:{project_id}:study:{code}",
                source_version="1",
                source_hash=_hash({"project": project_id, "study": code, "version": 1}),
                source_date=utc_now().date(),
                evidence_refs=[{"reference": f"UAT:{project_id}:study:{code}", "version": "1"}],
            ),
            _key("basic-item"),
        )
        item = reviewer.validate_item(
            item["id"], item["revision_version"], ItemValidateIn(validation_state="VALIDATED"), _key("basic-validate")
        )
        ids.append(item["id"])
    assessment = author.create_assessment(project_id, BasicAssessment(), _key("basic-assessment"))
    submitted = author.submit(assessment["id"], assessment["revision_version"], BasicAction(), _key("basic-submit"))
    completed = reviewer.complete(submitted["id"], submitted["revision_version"], BasicAction(), _key("basic-complete"))
    assert completed["status"] == "COMPLETED"
    return {
        "id": completed["id"],
        "item_ids": ids,
        "hash": completed["assessment_hash"],
        "provider": reviewer.provider_evidence(project_id),
    }


def complete_owner_capability(db, tenant_id: int, author_id: int, reviewer_id: int, project_id: int) -> dict:
    assert author_id != reviewer_id
    author = _service(OwnerCapabilityService, db, tenant_id, author_id, "owner_capability.assessment.create")
    reviewer = _service(OwnerCapabilityService, db, tenant_id, reviewer_id, "owner_capability.assessment.complete")
    requirements = author.requirements(project_id)["requirements"]
    assert requirements
    assessment = author.create_assessment(project_id, OwnerAssessment(), _key("owner-assessment"))
    items = [
        CapabilityItemIn(
            requirement_code=r["requirement_code"],
            current_maturity="IMPLEMENTED",
            evidence_quality="VERIFIED",
            confidence="HIGH",
            responsible_function=f"UAT owner {r['dimension']} function",
            source_date=utc_now().date(),
            evidence_refs=[{"reference": f"UAT:{project_id}:governance:{r['requirement_code']}", "version": "1"}],
        )
        for r in requirements
    ]
    assessment = author.update_assessment(
        assessment["id"], assessment["revision_version"], OwnerUpdate(items=items), _key("owner-update")
    )
    submitted = author.submit(assessment["id"], assessment["revision_version"], OwnerAction(), _key("owner-submit"))
    reviewing = reviewer.review(submitted["id"], submitted["revision_version"], OwnerAction(), _key("owner-review"))
    completed = reviewer.complete(reviewing["id"], reviewing["revision_version"], OwnerAction(), _key("owner-complete"))
    assert completed["status"] == "COMPLETED"
    return {
        "id": completed["id"],
        "hash": completed["assessment_hash"],
        "provider": reviewer.provider_evidence(project_id),
    }
