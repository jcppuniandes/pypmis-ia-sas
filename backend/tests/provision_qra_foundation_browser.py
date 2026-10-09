"""Real QRA browser actors/sources, exclusively in a disposable database.

Source setup deliberately uses the existing P6 XML ingestion authority. QRA
reads never fabricate calendar/duration metadata and never operate a CPM engine.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select

from app.core.security import hash_password
from app.core.time import utc_now
from app.database.session import Base, SessionLocal, engine
from app.domain.models import AuthCredential, Project, UserAccount
from app.services.schedule_ingestion import ScheduleIngestionService


def schedule_xml(*, data_date: str | None = None, disconnected: bool = False) -> bytes:
    """Manual-P6-export-shaped test source; values are imported, never computed."""
    current = data_date or utc_now().date().isoformat()
    relationships = (
        ""
        if disconnected
        else """
      <Relationship><PredecessorActivityObjectId>11</PredecessorActivityObjectId>
        <SuccessorActivityObjectId>12</SuccessorActivityObjectId><Type>FS</Type><Lag>0</Lag></Relationship>
      <Relationship><PredecessorActivityObjectId>12</PredecessorActivityObjectId>
        <SuccessorActivityObjectId>13</SuccessorActivityObjectId><Type>FS</Type><Lag>0</Lag></Relationship>
    """
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V19/API/BusinessObjects">
      <Project><ObjectId>100</ObjectId><Id>QRA-IMPORTED</Id><Name>QRA manual XML source</Name>
        <DataDate>{current}T00:00:00</DataDate><CurrencyId>USD</CurrencyId></Project>
      <Calendar><ObjectId>CAL-QRA</ObjectId><Name>Imported 8-hour working calendar</Name>
        <HoursPerDay>8</HoursPerDay><HoursPerWeek>40</HoursPerWeek><Type>Project</Type></Calendar>
      <WBS><ObjectId>WBS-1</ObjectId><Code>MINE</Code><Name>Mine development path</Name></WBS>
      <Activity><ObjectId>11</ObjectId><Id>A-START</Id><Name>Start milestone</Name>
        <WBSObjectId>WBS-1</WBSObjectId><CalendarObjectId>CAL-QRA</CalendarObjectId>
        <Type>Start Milestone</Type><Status>Not Started</Status><DurationUnit>HOURS</DurationUnit>
        <PlannedDuration>0</PlannedDuration><RemainingDuration>0</RemainingDuration>
        <PlannedStartDate>2027-01-04</PlannedStartDate><PlannedFinishDate>2027-01-04</PlannedFinishDate>
        <TotalFloat>0</TotalFloat><IsCritical>true</IsCritical></Activity>
      <Activity><ObjectId>12</ObjectId><Id>A-MINE</Id><Name>Mine development</Name>
        <WBSObjectId>WBS-1</WBSObjectId><CalendarObjectId>CAL-QRA</CalendarObjectId>
        <Type>Task Dependent</Type><Status>Not Started</Status><DurationUnit>HOURS</DurationUnit>
        <PlannedDuration>80</PlannedDuration><RemainingDuration>80</RemainingDuration>
        <PrimaryConstraintType>None</PrimaryConstraintType>
        <PlannedStartDate>2027-01-04</PlannedStartDate><PlannedFinishDate>2027-01-15</PlannedFinishDate>
        <PlannedTotalCost>1000</PlannedTotalCost><TotalFloat>0</TotalFloat><IsCritical>true</IsCritical></Activity>
      <Activity><ObjectId>13</ObjectId><Id>A-FINISH</Id><Name>Finish milestone</Name>
        <WBSObjectId>WBS-1</WBSObjectId><CalendarObjectId>CAL-QRA</CalendarObjectId>
        <Type>Finish Milestone</Type><Status>Not Started</Status><DurationUnit>HOURS</DurationUnit>
        <PlannedDuration>0</PlannedDuration><RemainingDuration>0</RemainingDuration>
        <PlannedStartDate>2027-01-15</PlannedStartDate><PlannedFinishDate>2027-01-15</PlannedFinishDate>
        <TotalFloat>0</TotalFloat><IsCritical>true</IsCritical></Activity>
      {relationships}
    </APIBusinessObjects>""".encode()


def prepare_imported_schedule(db, fixture, *, suffix: str = ""):
    """Establish a tenant-checked explicit canonical-to-operational link."""
    author, workspace = fixture["author"], fixture["project"]
    marker = suffix or uuid4().hex[:10]
    operational = Project(
        tenant_id=author.tenant_id,
        code=f"QRA-{marker}",
        name="QRA Foundation disposable imported schedule authority",
        currency="USD",
        phase="Planning",
        status="active",
        configuration={"enterprise_workspace_id": workspace.id},
    )
    db.add(operational)
    db.flush()
    values = deepcopy(workspace.defaults_json or {})
    values.setdefault("_project", {})["operational_project_id"] = operational.id
    workspace.defaults_json = values
    db.commit()
    source = ScheduleIngestionService(db).ingest(
        author.tenant_id, operational.id, f"qra-manual-p6-{marker}.xml", schedule_xml()
    )
    assert source.source.value == "p6_xml"
    assert source.source_metadata["calendars"], "Calendar must come from the imported XML authority"
    assert len(source.source_metadata["activities"]) == 3
    return {"operational_project": operational, "schedule_import": source}


def credential(db, actor, email, name):
    actor.email, actor.full_name = email, name
    existing = db.scalar(select(AuthCredential).where(AuthCredential.user_id == actor.id))
    if existing is None:
        db.add(
            AuthCredential(
                tenant_id=actor.tenant_id,
                user_id=actor.id,
                provider="local",
                password_hash=hash_password("1234"),
                is_active=True,
            )
        )
    db.commit()


def prepare_governed_contexts(db, fixture):
    """Complete actual prerequisite workflows before Owner captures its context.

    This helper is invoked by isolated acceptance fixtures, not application
    startup or reads. Evidence references are explicit disposable examples;
    their external document authenticity is not asserted.
    """
    from tests.test_capital_allocation_wave2a import _context
    from tests.test_owner_capability_wave3b import _complete as complete_owner
    from tests.test_owner_capability_wave3b import _draft as draft_owner
    from tests.test_owner_capability_wave3b import _grant, _key, _policy
    from tests.test_risk_governance_wave2b import _policy as risk_policy
    from tests.test_risk_readiness_gate07j_risk import _complete as complete_risk
    from tests.test_risk_readiness_gate07j_risk import _low_risk
    from tests.test_risk_readiness_gate07j_risk import _publish as publish_risk

    from app.domain.models import AdminConfiguration
    from app.modules.basic_data.schemas import AssessmentActionIn, AssessmentCreateIn, ItemCreateIn, ItemValidateIn
    from app.modules.basic_data.service import BasicDataService, _hash
    from app.modules.owner_capability.schemas import ConfigurationCloneIn, ConfigurationUpdateIn
    from app.modules.owner_capability.service import OwnerCapabilityService
    from app.modules.project_definition.schemas import AssessmentCreateIn as DefinitionCreateIn
    from app.modules.project_definition.schemas import AssessmentUpdateIn as DefinitionUpdateIn
    from app.modules.project_definition.schemas import ElementResultIn, StartFELIn
    from app.modules.project_definition.service import CONFIGURATION_KIND as FEL_KIND
    from app.modules.project_definition.service import DEFAULT_FRAMEWORK, ProjectDefinitionService
    from app.modules.risk_governance.schemas import EffectiveContextIn
    from app.modules.risk_governance.service import CONFIGURATION_KIND as RISK_KIND
    from app.modules.risk_governance.service import RiskGovernanceService
    from app.modules.risk_readiness.service import RiskReadinessService

    author, reviewer, project = fixture["author"], fixture["reviewer"], fixture["project"]
    for role in ("configuration_admin", "definition_assessor", "definition_reviewer"):
        _grant(db, reviewer, role)
    values = deepcopy(project.defaults_json or {})
    values.setdefault("_project", {})["fel_stage"] = "FEL-3"
    project.defaults_json = values
    db.commit()

    definition = ProjectDefinitionService(
        db, author.tenant_id, author.id, _context(author, "project_definition_manager")
    )
    final_definition = ProjectDefinitionService(
        db, reviewer.tenant_id, reviewer.id, _context(reviewer, "definition_reviewer")
    )
    definition.ensure_seed()
    template = db.scalar(
        select(AdminConfiguration)
        .where(
            AdminConfiguration.tenant_id == author.tenant_id,
            AdminConfiguration.kind == FEL_KIND,
            AdminConfiguration.code == "pyp-custom-definition",
        )
        .order_by(AdminConfiguration.revision.desc())
    )
    clone = definition.clone_configuration(template.id, template.version)
    framework = deepcopy(DEFAULT_FRAMEWORK)
    framework["scope"] = {"type": "enterprise", "workspace_id": fixture["enterprise"].id}
    clone = definition.update_configuration(
        clone.id,
        clone.version,
        "QRA governed FEL-3 framework",
        "Disposable prerequisite, not proprietary PDRI scoring.",
        framework,
    )
    framework_record = final_definition.publish_configuration(clone.id, clone.version)
    definition.start_fel(
        project.id,
        StartFELIn(
            stage_code="FEL-3",
            framework_configuration_id=framework_record.id,
            entry_justification="Existing governed FEL-3 Project, independently evidenced import boundary.",
            source_evidence=[{"reference": "DISPOSABLE-FEL3-ENTRY"}],
            idempotency_key=_key("qra-fel3-start"),
        ),
    )
    assessment = definition.create_assessment(
        project.id, DefinitionCreateIn(idempotency_key=_key("qra-definition-create"))
    )
    assessment = definition.update_assessment(
        assessment.id,
        assessment.revision_version,
        DefinitionUpdateIn(
            element_results=[
                ElementResultIn(
                    element_key=element["element_key"],
                    category_key=element["category_key"],
                    score=100,
                    evidence_refs=[{"reference": f"DISPOSABLE-FEL3:{element['element_key']}"}],
                )
                for element in framework["assessment_elements"]
                if "FEL-3" in element["stages"]
            ],
            evidence_refs=[{"reference": "DISPOSABLE-FEL3-DEFINITION-PACKAGE"}],
        ),
    )
    completed_definition = final_definition.complete_assessment(
        assessment.id, assessment.revision_version, _key("qra-definition-complete")
    )
    assert completed_definition.status == "COMPLETED"
    assert final_definition.readiness(project.id).source_current

    basic = BasicDataService(db, author.tenant_id, author.id, _context(author, "project_definition_manager"))
    basic_final = BasicDataService(db, reviewer.tenant_id, reviewer.id, _context(reviewer, "definition_reviewer"))
    for requirement in basic.requirements(project.id)["requirements"]:
        code = requirement["requirement_code"]
        item = basic.create_item(
            project.id,
            ItemCreateIn(
                requirement_code=code,
                availability="AVAILABLE",
                quality="VALIDATED",
                confidence="HIGH",
                source_type="STUDY_REFERENCE",
                source_reference=f"DISPOSABLE-QRA-STUDY:{code}",
                source_version="1",
                source_hash=_hash({"qra_study": code}),
                source_date=utc_now().date(),
                evidence_refs=[{"reference": f"DISPOSABLE-QRA-STUDY:{code}"}],
            ),
            _key("qra-basic-item"),
        )
        basic_final.validate_item(
            item["id"],
            item["revision_version"],
            ItemValidateIn(validation_state="VALIDATED"),
            _key("qra-basic-validate"),
        )
    row = basic.create_assessment(project.id, AssessmentCreateIn(), _key("qra-basic-create"))
    row = basic.submit(row["id"], row["revision_version"], AssessmentActionIn(), _key("qra-basic-submit"))
    basic_final.complete(row["id"], row["revision_version"], AssessmentActionIn(), _key("qra-basic-complete"))
    assert basic_final.provider_evidence(project.id)["status"] == "AVAILABLE"

    governance = RiskGovernanceService(db, author.tenant_id, author.id, _context(author, "configuration_admin"))
    governance_final = RiskGovernanceService(
        db, reviewer.tenant_id, reviewer.id, _context(reviewer, "configuration_admin")
    )
    governance.ensure_seed()
    template = db.scalar(
        select(AdminConfiguration)
        .where(
            AdminConfiguration.tenant_id == author.tenant_id,
            AdminConfiguration.kind == RISK_KIND,
            AdminConfiguration.code == "default",
        )
        .order_by(AdminConfiguration.revision.desc())
    )
    clone = governance.clone_configuration(
        template.id, template.version, _key("qra-risk-governance-clone"), target_workspace_id=fixture["enterprise"].id
    )
    policy = risk_policy(
        fixture["enterprise"].id,
        effective_from=utc_now().date().isoformat(),
        governance_models=["CAPITAL_OWNER"],
        project_types=["MINING"],
    )
    clone = governance.update_configuration(
        clone.id,
        clone.version,
        name="QRA governed Risk appetite/capacity",
        description="Independent source context, not QRA outputs.",
        content=policy,
    )
    governance_final.publish_configuration(clone.id, clone.version, _key("qra-risk-governance-publish"))
    assert governance_final.effective(EffectiveContextIn(workspace_id=project.id)).status == "AVAILABLE"
    risk = RiskReadinessService(db, author.tenant_id, author.id)
    risk_final = RiskReadinessService(db, reviewer.tenant_id, reviewer.id)
    publish_risk(risk)
    _low_risk(risk, project.id, title="Disposable governed discrete risk, never quantified")
    completed_risk = complete_risk(risk_final, project.id)
    assert completed_risk.status == "COMPLETED" and completed_risk.readiness_status == "READY"
    assert risk_final.project_readiness(project.id).source_current

    owner = OwnerCapabilityService(db, author.tenant_id, author.id, _context(author, "project_definition_manager"))
    owner_final = OwnerCapabilityService(db, reviewer.tenant_id, reviewer.id, _context(reviewer, "definition_reviewer"))
    seed = owner.ensure_seed()
    clone = owner.clone_configuration(
        seed.id,
        seed.version,
        ConfigurationCloneIn(code=_key("qra-owner-policy")[:100], target_workspace_id=fixture["enterprise"].id),
        _key("qra-owner-clone"),
    )
    owner_policy = _policy(fixture["enterprise"].id, count=2)
    clone = owner.update_configuration(
        clone["id"],
        clone["version"],
        ConfigurationUpdateIn(name="QRA governed Owner prerequisite", content_json=owner_policy),
        _key("qra-owner-update"),
    )
    published = owner_final.publish_configuration(clone["id"], clone["version"], _key("qra-owner-publish"))
    owner_fixture = {**fixture, "preparer": owner, "final": owner_final, "configuration": published}
    completed_owner = complete_owner(owner_fixture, draft_owner(owner_fixture))
    assert completed_owner["status"] == "COMPLETED"
    assert owner_final.provider_evidence(project.id)["status"] == "AVAILABLE"
    return {
        "fel_pdri": "CURRENT_FEL3_COMPLETED",
        "basic_data": "AVAILABLE",
        "risk_governance": "AVAILABLE",
        "risk_readiness": "READY",
        "owner_capability": "AVAILABLE",
    }


def main() -> None:
    if os.getenv("PYPMIS_QRA_BROWSER_FIXTURE") != "disposable-only" or (
        engine.dialect.name != "postgresql" or engine.url.database != "qra_foundation_browser"
    ):
        raise RuntimeError("QRA browser provisioning is restricted to disposable qra_foundation_browser PostgreSQL")
    # Imported only after the explicit database/environment guard.
    from tests.test_capital_allocation_wave2a import _user
    from tests.test_owner_capability_wave3b import _grant
    from tests.test_qra_foundation import _fixture

    from app.database.seed import ensure_membership, seed_demo

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_demo(db)
        if db.scalar(select(UserAccount).where(UserAccount.email == "qra.authority@demo.local")):
            print(json.dumps({"database": engine.url.database, "fixture": "reused"}), flush=True)
            return
        fixture = _fixture(db, contexts=True)
        author, authority, workspace = fixture["author"], fixture["reviewer"], fixture["project"]
        sources = fixture if "schedule_import" in fixture else prepare_imported_schedule(db, fixture)
        credential(db, authority, "qra.authority@demo.local", "QRA Independent Project Authority")
        for role in ("configuration_admin", "definition_assessor", "definition_reviewer"):
            _grant(db, authority, role)
        user = _user(db, author.tenant_id, "qra-user")
        credential(db, user, "qra.user@demo.local", "QRA Project-scoped preparer")
        _grant(db, user, "definition_assessor", scope_type="workspace", workspace_id=workspace.id)
        config = _user(db, author.tenant_id, "qra-config")
        credential(db, config, "qra.config@demo.local", "QRA Configuration-only actor")
        _grant(db, config, "configuration_admin")
        shell_project = db.scalar(select(Project).where(Project.tenant_id == author.tenant_id).order_by(Project.id))
        if shell_project is None:
            raise RuntimeError("Application shell requires an existing disposable operational Project")
        for actor, role in ((authority, "Control Manager"), (user, "Executive"), (config, "Executive")):
            ensure_membership(db, author.tenant_id, shell_project.id, actor.id, role)
        db.commit()
        print(
            json.dumps(
                {
                    "database": engine.url.database,
                    "project_workspace_id": workspace.id,
                    "schedule_import_id": sources["schedule_import"].id,
                    "authority_email": authority.email,
                    "user_email": user.email,
                    "config_email": config.email,
                    "schedule_authority": "MANUAL_P6_XML_IMPORT_NO_CPM",
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
