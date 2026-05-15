import json
from datetime import date
from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.domain.models import (
    KPI,
    WBS,
    Activity,
    ActivityRelationship,
    AuthCredential,
    BaselineVersion,
    Budget,
    BusinessProcessInstance,
    BusinessProcessStepTemplate,
    BusinessProcessTemplate,
    BusinessProcessTransitionTemplate,
    CashFlowPeriod,
    ChangeRequest,
    Claim,
    ClaimEntitlementItem,
    ClaimImpactAnalysis,
    Contract,
    ContractCommunication,
    ContractNotice,
    ControlAccount,
    ControlAccountFundingAllocation,
    ControlAccountMapping,
    ControlPeriod,
    ControlSnapshot,
    CostBreakdownStructure,
    CostCode,
    CostRecord,
    CostSource,
    Document,
    DocumentReview,
    DocumentTransmittal,
    DocumentTransmittalItem,
    Event,
    ForecastScenario,
    FundingSource,
    ImportStatus,
    PaymentCertificate,
    ProgressRecord,
    Project,
    ProjectControlPlan,
    ProjectMail,
    ProjectMembership,
    ProjectOperationalSetup,
    PurchaseOrder,
    RelationshipType,
    Resource,
    RFQBid,
    RFQPackage,
    ScheduleActivityMap,
    ScheduleImport,
    ScheduleSource,
    ScheduleValidationFinding,
    Tenant,
    UserAccount,
    WarehouseReceipt,
    WorkflowStepInstance,
    WorkPackage,
    WorkPackageConstraint,
)
from app.domain.process_catalog import DEFAULT_PROCESS_TEMPLATES
from app.services.control_core import ControlCoreService
from app.services.integrated_control import IntegratedControlService
from app.services.schedule_ingestion import ScheduleIngestionService

SEED_DEMO_ADVISORY_LOCK_ID = 572401


def seed_demo(db: Session) -> None:
    lock_acquired = acquire_seed_demo_lock(db)
    if not lock_acquired:
        return

    try:
        seed_demo_records(db)
    except Exception:
        db.rollback()
        raise
    finally:
        release_seed_demo_lock(db)


def acquire_seed_demo_lock(db: Session) -> bool:
    if db.get_bind().dialect.name != "postgresql":
        return True
    return bool(
        db.scalar(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": SEED_DEMO_ADVISORY_LOCK_ID},
        )
    )


def release_seed_demo_lock(db: Session) -> None:
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_unlock(:lock_id)"),
        {"lock_id": SEED_DEMO_ADVISORY_LOCK_ID},
    )
    db.commit()


def seed_demo_records(db: Session) -> None:
    existing = db.scalar(select(Tenant).where(Tenant.slug == "demo-energy"))
    if existing:
        ensure_default_bp_templates(db, existing.id)
        project = ensure_primary_project(db, existing.id)
        if project:
            ensure_project_control_plan(db, existing.id, project.id)
            ensure_project_operational_setup(db, existing.id, project.id)
            neutralize_schedule_labels(db, existing.id, project.id)
            ensure_demo_schedule(db, existing.id, project.id)
            ensure_control_account_mapping_records(db, existing.id, project.id)
            ensure_contract_records(db, existing.id, project.id)
            ensure_purchase_order_records(db, existing.id, project.id)
            ensure_payment_certificate_records(db, existing.id, project.id)
            ensure_warehouse_receipt_records(db, existing.id, project.id)
            ensure_rfq_records(db, existing.id, project.id)
            ensure_awp_records(db, existing.id, project.id)
            ensure_claim_entitlement_records(db, existing.id, project.id)
            ensure_claim_notice_and_impact_records(db, existing.id, project.id)
            ensure_document_control_records(db, existing.id, project.id)
            ControlCoreService(db).run_project_cycle(existing.id, project.id)
            ensure_control_history_records(db, existing.id, project.id)
            ensure_cost_manager_records(db, existing.id, project.id)
        secondary = ensure_secondary_project(db, existing.id)
        if secondary:
            ensure_project_control_plan(db, existing.id, secondary.id)
            ensure_project_operational_setup(db, existing.id, secondary.id)
            neutralize_schedule_labels(db, existing.id, secondary.id)
            ensure_control_account_mapping_records(db, existing.id, secondary.id)
            ensure_contract_records(db, existing.id, secondary.id)
            ensure_purchase_order_records(db, existing.id, secondary.id)
            ensure_payment_certificate_records(db, existing.id, secondary.id)
            ensure_warehouse_receipt_records(db, existing.id, secondary.id)
            ensure_rfq_records(db, existing.id, secondary.id)
            ensure_awp_records(db, existing.id, secondary.id)
            ensure_claim_entitlement_records(db, existing.id, secondary.id)
            ensure_claim_notice_and_impact_records(db, existing.id, secondary.id)
            ensure_document_control_records(db, existing.id, secondary.id)
            ControlCoreService(db).run_project_cycle(existing.id, secondary.id)
            ensure_control_history_records(db, existing.id, secondary.id)
            ensure_cost_manager_records(db, existing.id, secondary.id)
        ensure_integrated_control_examples(db, existing.id)
        ensure_demo_users(db, existing.id)
        return

    tenant = Tenant(name="Demo Energy Infrastructure", slug="demo-energy")
    db.add(tenant)
    db.flush()
    ensure_default_bp_templates(db, tenant.id)

    project = Project(
        tenant_id=tenant.id,
        code="CTRL-DEMO-001",
        name="Proyecto Demo - Control Integrado TCM",
        phase="Execution",
        currency="USD",
        start_date=date(2026, 1, 5),
        finish_date=date(2026, 12, 18),
    )
    db.add(project)
    db.flush()
    ensure_project_control_plan(db, tenant.id, project.id)
    ensure_project_operational_setup(db, tenant.id, project.id)

    wbs = WBS(tenant_id=tenant.id, project_id=project.id, code="1.2", name="Mechanical and Piping", parent_id=None)
    db.add(wbs)
    db.flush()

    accounts = [
        ControlAccount(
            tenant_id=tenant.id,
            project_id=project.id,
            wbs_id=wbs.id,
            code="CA-MECH-100",
            name="Compressor Mechanical Installation",
            responsible="Construction Manager",
            discipline="Mechanical",
        ),
        ControlAccount(
            tenant_id=tenant.id,
            project_id=project.id,
            wbs_id=wbs.id,
            code="CA-PIPE-210",
            name="Process Piping Fabrication and Erection",
            responsible="Piping Lead",
            discipline="Piping",
        ),
        ControlAccount(
            tenant_id=tenant.id,
            project_id=project.id,
            wbs_id=wbs.id,
            code="CA-ELEC-310",
            name="Electrical Hook-up and Precommissioning",
            responsible="E&I Lead",
            discipline="Electrical",
        ),
    ]
    db.add_all(accounts)
    db.flush()
    ensure_demo_schedule(db, tenant.id, project.id)
    ensure_control_account_mapping_records(db, tenant.id, project.id)

    budget_rows = [
        ("CBS-3210", 2_400_000, 1_600_000, 62, 1_820_000, 7800, 92000),
        ("CBS-4210", 3_100_000, 2_280_000, 58, 2_620_000, 11200, 96000),
        ("CBS-5110", 1_250_000, 750_000, 66, 730_000, 5100, 72000),
    ]
    for account, (cbs, bac, pv, percent, ac, hours, qty) in zip(accounts, budget_rows, strict=True):
        db.add(
            Budget(
                tenant_id=tenant.id,
                project_id=project.id,
                control_account_id=account.id,
                cbs_code=cbs,
                bac=bac,
                cost_loaded_pv=pv,
            )
        )
        db.add(
            CostRecord(
                tenant_id=tenant.id,
                project_id=project.id,
                control_account_id=account.id,
                source=CostSource.invoice,
                amount=ac,
                incurred_on=date(2026, 5, 1),
                description="Actual cost imported from ERP cut-off.",
            )
        )
        db.add(
            ProgressRecord(
                tenant_id=tenant.id,
                project_id=project.id,
                control_account_id=account.id,
                physical_percent=percent,
                quantity_installed=qty,
                labor_hours=hours,
                reported_on=date(2026, 5, 1),
                evidence_ref="FIELD-REPORT-2026-05-01",
            )
        )

    db.add(
        Event(
            tenant_id=tenant.id,
            project_id=project.id,
            control_account_id=accounts[1].id,
            event_type="Material delay",
            title="Late delivery of 24-inch valves",
            occurred_on=date(2026, 4, 22),
            contractual_notice_required=True,
        )
    )
    db.add(
        ChangeRequest(
            tenant_id=tenant.id,
            project_id=project.id,
            control_account_id=accounts[1].id,
            title="Additional pipe supports due to IFC revision",
            deviation="Design revision increased support density in compressor discharge line.",
            cost_impact=185_000,
            schedule_impact_days=9,
        )
    )
    db.add(
        Claim(
            tenant_id=tenant.id,
            project_id=project.id,
            control_account_id=accounts[1].id,
            title="Productivity loss from late owner-furnished valves",
            causality="Owner-furnished equipment delay restricted workface availability.",
            impact="Crew stacking, resequencing and idle equipment during piping erection.",
            evidence_summary="Linked field reports, procurement correspondence and daily equipment logs.",
        )
    )
    db.add_all(
        [
            Document(
                tenant_id=tenant.id,
                project_id=project.id,
                linked_entity_type="ControlAccount",
                linked_entity_id=accounts[1].id,
                title="Daily field report package",
                doc_type="Field Report",
                uri="edms://field/DFR-2026-05-01",
            ),
            Document(
                tenant_id=tenant.id,
                project_id=project.id,
                linked_entity_type="Claim",
                linked_entity_id=1,
                title="Valve delay correspondence",
                doc_type="Contract Communication",
                uri="edms://contracts/COM-VALVE-DELAY",
            ),
        ]
    )
    db.commit()

    ControlCoreService(db).run_project_cycle(tenant.id, project.id)
    ensure_control_history_records(db, tenant.id, project.id)
    ensure_cost_manager_records(db, tenant.id, project.id)
    ensure_contract_records(db, tenant.id, project.id)
    ensure_purchase_order_records(db, tenant.id, project.id)
    ensure_payment_certificate_records(db, tenant.id, project.id)
    ensure_warehouse_receipt_records(db, tenant.id, project.id)
    ensure_rfq_records(db, tenant.id, project.id)
    ControlCoreService(db).run_project_cycle(tenant.id, project.id)
    ensure_control_history_records(db, tenant.id, project.id)
    ensure_awp_records(db, tenant.id, project.id)
    ensure_claim_entitlement_records(db, tenant.id, project.id)
    ensure_claim_notice_and_impact_records(db, tenant.id, project.id)
    ensure_document_control_records(db, tenant.id, project.id)
    secondary = ensure_secondary_project(db, tenant.id)
    if secondary:
        ensure_project_control_plan(db, tenant.id, secondary.id)
        ensure_project_operational_setup(db, tenant.id, secondary.id)
        ensure_contract_records(db, tenant.id, secondary.id)
        ensure_purchase_order_records(db, tenant.id, secondary.id)
        ensure_payment_certificate_records(db, tenant.id, secondary.id)
        ensure_warehouse_receipt_records(db, tenant.id, secondary.id)
        ensure_rfq_records(db, tenant.id, secondary.id)
        ensure_control_account_mapping_records(db, tenant.id, secondary.id)
        ensure_awp_records(db, tenant.id, secondary.id)
        ensure_claim_entitlement_records(db, tenant.id, secondary.id)
        ensure_claim_notice_and_impact_records(db, tenant.id, secondary.id)
        ensure_document_control_records(db, tenant.id, secondary.id)
        ControlCoreService(db).run_project_cycle(tenant.id, secondary.id)
        ensure_control_history_records(db, tenant.id, secondary.id)
        ensure_cost_manager_records(db, tenant.id, secondary.id)
    ensure_integrated_control_examples(db, tenant.id)
    ensure_demo_users(db, tenant.id)


def ensure_default_bp_templates(db: Session, tenant_id: int) -> None:
    legacy_project_template = db.scalar(
        select(BusinessProcessTemplate).where(
            BusinessProcessTemplate.tenant_id == tenant_id,
            BusinessProcessTemplate.code == "PJ-SHELL",
        )
    )
    if legacy_project_template:
        current_project_template = db.scalar(
            select(BusinessProcessTemplate).where(
                BusinessProcessTemplate.tenant_id == tenant_id,
                BusinessProcessTemplate.code == "PJ-CREATE",
            )
        )
        if current_project_template and current_project_template.id != legacy_project_template.id:
            legacy_project_template.code = "PJ-CREATE-LEGACY"
            legacy_project_template.name = "Project Creation Legacy"
            legacy_project_template.description = "Legacy project creation process retained for audit history."
            legacy_project_template.status = "Archived"
        else:
            legacy_project_template.code = "PJ-CREATE"
        db.flush()

    for template_seed in DEFAULT_PROCESS_TEMPLATES:
        template = db.scalar(
            select(BusinessProcessTemplate).where(
                BusinessProcessTemplate.tenant_id == tenant_id,
                BusinessProcessTemplate.code == template_seed["code"],
            )
        )
        if not template:
            template = BusinessProcessTemplate(
                tenant_id=tenant_id,
                code=template_seed["code"],
                name=template_seed["name"],
                category=template_seed.get("category", "Custom"),
                description=template_seed.get("description", ""),
                form_schema=json.dumps(template_seed.get("form_schema", [])),
                status=template_seed.get("status", "Draft"),
                version_no=template_seed.get("version_no", 1),
            )
            db.add(template)
            db.flush()
        else:
            template.name = template_seed["name"]
            template.category = template_seed.get("category", template.category)
            template.description = template_seed.get("description", template.description)
            template.form_schema = json.dumps(template_seed.get("form_schema", []))
            template.status = template_seed.get("status", template.status)
            template.version_no = max(template.version_no or 1, template_seed.get("version_no", 1))

        existing_steps = list(
            db.scalars(
                select(BusinessProcessStepTemplate).where(
                    BusinessProcessStepTemplate.tenant_id == tenant_id,
                    BusinessProcessStepTemplate.template_id == template.id,
                )
            ).all()
        )
        if not existing_steps:
            for index, step in enumerate(template_seed.get("steps", []), start=1):
                db.add(
                    BusinessProcessStepTemplate(
                        tenant_id=tenant_id,
                        template_id=template.id,
                        step_order=index,
                        name=step["name"],
                        detail=step.get("detail", ""),
                        owner_role=step.get("owner_role", ""),
                        status=step.get("status", "Queued"),
                        tone=step.get("tone", "queued"),
                    )
                )
        else:
            by_name = {step.name: step for step in existing_steps}
            for index, step_seed in enumerate(template_seed.get("steps", []), start=1):
                step = by_name.get(step_seed["name"])
                if not step:
                    db.add(
                        BusinessProcessStepTemplate(
                            tenant_id=tenant_id,
                            template_id=template.id,
                            step_order=index,
                            name=step_seed["name"],
                            detail=step_seed.get("detail", ""),
                            owner_role=step_seed.get("owner_role", ""),
                            status=step_seed.get("status", "Queued"),
                            tone=step_seed.get("tone", "queued"),
                        )
                    )
                    continue
                step.step_order = index
                step.detail = step_seed.get("detail", step.detail)
                step.owner_role = step_seed.get("owner_role", step.owner_role)

        existing_transitions = list(
            db.scalars(
                select(BusinessProcessTransitionTemplate).where(
                    BusinessProcessTransitionTemplate.tenant_id == tenant_id,
                    BusinessProcessTransitionTemplate.template_id == template.id,
                )
            ).all()
        )
        transition_keys = {(transition.action, transition.from_step) for transition in existing_transitions}
        for transition_seed in template_seed.get("transitions", []):
            action = transition_seed["action"].strip().lower()
            key = (action, transition_seed.get("from_step", ""))
            if key in transition_keys:
                continue
            db.add(
                BusinessProcessTransitionTemplate(
                    tenant_id=tenant_id,
                    template_id=template.id,
                    action=action,
                    label=transition_seed.get("label", action.replace("_", " ").title()),
                    from_step=transition_seed.get("from_step", ""),
                    to_step=transition_seed.get("to_step", ""),
                    process_status=transition_seed.get("process_status", "in_review"),
                    ball_in_court=transition_seed.get("ball_in_court", ""),
                    from_status=transition_seed.get("from_status", "Complete"),
                    from_tone=transition_seed.get("from_tone", "complete"),
                    to_status=transition_seed.get("to_status", "Active"),
                    to_tone=transition_seed.get("to_tone", "active"),
                    requires_approval=transition_seed.get("requires_approval", False),
                    permission_key=transition_seed.get("permission_key", ""),
                )
            )
    db.flush()


def ensure_primary_project(db: Session, tenant_id: int) -> Project | None:
    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.code == "CTRL-DEMO-001"))
    if not project:
        project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.code == "EPC-PIPE-001"))
    if not project:
        return None
    project.code = "CTRL-DEMO-001"
    project.name = "Proyecto Demo - Control Integrado TCM"
    project.phase = "Execution"
    project.currency = project.currency or "USD"
    project.start_date = project.start_date or date(2026, 1, 5)
    project.finish_date = project.finish_date or date(2026, 12, 18)
    db.flush()
    return project


def ensure_project_control_plan(db: Session, tenant_id: int, project_id: int) -> None:
    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    if not project:
        return
    plan = db.scalar(
        select(ProjectControlPlan).where(
            ProjectControlPlan.tenant_id == tenant_id,
            ProjectControlPlan.project_id == project_id,
        )
    )
    is_turnaround = project.code == "REF-TURN-002"
    defaults = {
        "execution_strategy": (
            "Execute turnaround windows through approved shutdown logic, discipline work packs and daily constraint review."
            if is_turnaround
            else "Execute the project through the approved control baseline, control accounts, AWP packages and weekly decision cycle."
        ),
        "control_strategy": "Use schedule intake, data quality gates, WBS/CBS/activity mapping, EVM, AWP readiness, claims exposure and workflow approvals.",
        "progress_measurement_rule": "Capture physical percent, quantities, labor hours and field evidence by control account each control period.",
        "cost_measurement_rule": "Committed cost comes from contracts and purchase orders; incurred cost comes from payment certificates and warehouse receipts by control account before BAC, PV, EV, AC, CPI, EAC and VAC reporting.",
        "change_management_rule": "Identify deviations, quantify cost/schedule impact, route approvals, update forecasts and preserve audit trail.",
        "risk_management_rule": "Review schedule quality, productivity, cost variance, open constraints, procurement slippage, notices and claim exposure.",
        "procurement_strategy": "Track RFQ packages, bid evaluation, purchase orders, warehouse receipts and contracting constraints that can affect workface readiness, critical path or contractual notices.",
        "document_control_rule": "Link field reports, correspondence, notices, evidence, decisions and baseline artifacts to the controlled entity.",
        "reporting_cadence": "Weekly",
        "status": "active",
    }
    if not plan:
        db.add(ProjectControlPlan(tenant_id=tenant_id, project_id=project_id, **defaults))
        db.flush()
        return
    for field, value in defaults.items():
        if not getattr(plan, field):
            setattr(plan, field, value)
    if plan.status == "draft":
        plan.status = "active"
    db.flush()


def ensure_project_operational_setup(db: Session, tenant_id: int, project_id: int) -> None:
    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    if not project:
        return
    setup = db.scalar(
        select(ProjectOperationalSetup).where(
            ProjectOperationalSetup.tenant_id == tenant_id,
            ProjectOperationalSetup.project_id == project_id,
        )
    )
    defaults = {
        "project_number": project.code,
        "setup_template": "Capital Project Controls Template",
        "attribute_form": "Project Attribute Form",
        "permissions_configured": True,
        "modules_configured": True,
        "cost_sheet_ready": True,
        "funding_sheet_ready": True,
        "p6_mapping_ready": True,
        "status": "ready",
        "readiness_status": "ready",
        "readiness_notes": "Ready for controlled data loading.",
    }
    if not setup:
        db.add(ProjectOperationalSetup(tenant_id=tenant_id, project_id=project_id, **defaults))
        db.flush()
        return
    for field, value in defaults.items():
        if getattr(setup, field) in ("", False, None, "not_ready", "draft"):
            setattr(setup, field, value)
    db.flush()


def ensure_cost_manager_records(db: Session, tenant_id: int, project_id: int) -> None:
    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    if not project:
        return

    existing_funding_codes = set(
        db.scalars(
            select(FundingSource.code).where(
                FundingSource.tenant_id == tenant_id,
                FundingSource.project_id == project_id,
            )
        ).all()
    )
    funding_rows = (
        [
            ("CAPEX-2026", "Approved 2026 capital allocation", 5_500_000, "approved"),
            ("CONT-RESERVE", "Management reserve for pilot controls", 1_250_000, "approved"),
            ("CHANGE-FUND", "Owner change contingency", 950_000, "planned"),
        ]
        if project.code == "CTRL-DEMO-001"
        else [
            ("TURN-CAPEX", "Turnaround approved budget envelope", 2_100_000, "approved"),
            ("OPS-RESERVE", "Operations contingency reserve", 450_000, "planned"),
        ]
    )
    for code, name, amount, status in funding_rows:
        if code not in existing_funding_codes:
            db.add(
                FundingSource(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    code=code,
                    name=name,
                    amount=amount,
                    currency=project.currency,
                    status=status,
                )
            )

    existing_periods = set(
        db.scalars(
            select(CashFlowPeriod.period_label).where(
                CashFlowPeriod.tenant_id == tenant_id,
                CashFlowPeriod.project_id == project_id,
            )
        ).all()
    )
    cash_flow_rows = (
        [
            ("2026-01", 1_400_000, 880_000, 1_400_000, 860_000, 920_000),
            ("2026-02", 1_200_000, 1_120_000, 1_200_000, 1_180_000, 1_250_000),
            ("2026-03", 1_450_000, 1_420_000, 1_410_000, 1_520_000, 1_630_000),
            ("2026-04", 1_100_000, 1_560_000, 1_050_000, 1_610_000, 1_720_000),
            ("2026-05", 1_250_000, 1_770_000, 1_190_000, 1_720_000, 1_840_000),
        ]
        if project.code == "CTRL-DEMO-001"
        else [
            ("2026-03", 750_000, 420_000, 740_000, 390_000, 470_000),
            ("2026-04", 680_000, 580_000, 650_000, 610_000, 690_000),
            ("2026-05", 650_000, 760_000, 610_000, 720_000, 820_000),
        ]
    )
    for (
        period_label,
        planned_inflow,
        planned_outflow,
        actual_inflow,
        actual_outflow,
        forecast_outflow,
    ) in cash_flow_rows:
        if period_label not in existing_periods:
            db.add(
                CashFlowPeriod(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    period_label=period_label,
                    planned_inflow=planned_inflow,
                    planned_outflow=planned_outflow,
                    actual_inflow=actual_inflow,
                    actual_outflow=actual_outflow,
                    forecast_outflow=forecast_outflow,
                )
            )
    db.commit()


def neutralize_schedule_labels(db: Session, tenant_id: int, project_id: int) -> None:
    schedule_imports = list(
        db.scalars(
            select(ScheduleImport).where(
                ScheduleImport.tenant_id == tenant_id,
                ScheduleImport.project_id == project_id,
            )
        ).all()
    )
    for schedule_import in schedule_imports:
        schedule_import.file_name = neutral_schedule_file_name(schedule_import)
        schedule_import.baseline_name = neutral_schedule_text(
            schedule_import.baseline_name or f"Schedule Baseline {schedule_import.id:02d}"
        )
        schedule_import.validation_summary = neutral_schedule_text(schedule_import.validation_summary)

        baseline = db.scalar(
            select(BaselineVersion).where(
                BaselineVersion.tenant_id == tenant_id,
                BaselineVersion.project_id == project_id,
                BaselineVersion.schedule_import_id == schedule_import.id,
            )
        )
        if baseline:
            baseline.name = schedule_import.baseline_name

        processes = list(
            db.scalars(
                select(BusinessProcessInstance).where(
                    BusinessProcessInstance.tenant_id == tenant_id,
                    BusinessProcessInstance.project_id == project_id,
                    BusinessProcessInstance.trigger_entity_type == "ScheduleImport",
                    BusinessProcessInstance.trigger_entity_id == schedule_import.id,
                )
            ).all()
        )
        for process in processes:
            process.title = f"Schedule Intake - {schedule_import.file_name}"
            steps = list(
                db.scalars(
                    select(WorkflowStepInstance).where(
                        WorkflowStepInstance.process_instance_id == process.id,
                    )
                ).all()
            )
            for step in steps:
                step.detail = neutral_schedule_text(step.detail)

    findings = list(
        db.scalars(
            select(ScheduleValidationFinding).where(
                ScheduleValidationFinding.tenant_id == tenant_id,
                ScheduleValidationFinding.project_id == project_id,
            )
        ).all()
    )
    for finding in findings:
        finding.message = neutral_schedule_text(finding.message)

    db.flush()


def neutral_schedule_file_name(schedule_import: ScheduleImport) -> str:
    current = schedule_import.file_name or f"SCHEDULE_IMPORT_{schedule_import.id:05d}"
    upper = current.upper()
    suffix = (
        ".xml"
        if current.lower().endswith(".xml")
        else ".xer"
        if current.lower().endswith(".xer")
        else Path(current).suffix or ".xml"
    )
    if "MSPROJECT" in upper or "MS PROJECT" in upper or "MSP" in upper:
        return f"Imported_Schedule_{schedule_import.id:05d}{suffix}"
    if "P6_EPC_PIPELINE" in upper or "EPC_PIPELINE" in upper:
        return f"Control_Baseline_{schedule_import.id:05d}{suffix}"
    return neutral_schedule_text(current)


def neutral_schedule_text(value: str) -> str:
    return (
        value.replace("Schedule file received from Primavera P6 or MS Project.", "Source schedule file received.")
        .replace("Primavera P6 or MS Project", "source schedule")
        .replace("MSPROJECT_WORKFLOW_TRIGGER", "Schedule Baseline Intake")
        .replace("SCHEDULE_WORKFLOW_TRIGGER", "Schedule Baseline Intake")
        .replace("MSPROJECT", "SCHEDULE")
        .replace("MS Project", "schedule")
        .replace("P6/MSP", "source schedule")
        .replace("MSP", "schedule")
        .replace("P6_EPC_PIPELINE", "Control Baseline")
        .replace("EPC_PIPELINE", "Control Baseline")
    )


def ensure_integrated_control_examples(db: Session, tenant_id: int) -> None:
    examples = [
        {
            "project_code": "MIN-ABC",
            "project_name": "MIN-ABC Planta Minera",
            "fbs_code": "FBS-OWN-AFE002-PLT",
            "source_of_funds": "Owner equity AFE002",
            "funding_type": "AFE",
            "authorization_ref": "AFE002",
            "wbs_code": "1.5.3",
            "wbs_name": "Obras civiles planta",
            "package_type": "CWP",
            "package_code": "CWP-PLT-CIV-001",
            "control_account": "CA-PLT-CIV-001",
            "cbs_code": "4000 MO",
            "cost_category": "Mano de obra",
            "cost_code": "MIN-1.5.3-CA-PLT-CIV-001-4000",
            "contract": "CTR-CIV-001",
            "budget": 5_000_000,
            "funds": 4_800_000,
            "currency": "USD",
        },
        {
            "project_code": "VIA-001",
            "project_name": "VIA-001 Infraestructura Vial",
            "fbs_code": "FBS-PUB-VIG2027-T01",
            "source_of_funds": "Vigencia publica 2027 Tramo 1",
            "funding_type": "Public funding",
            "authorization_ref": "VIG2027-T01",
            "wbs_code": "1.5.1",
            "wbs_name": "Tramo 1",
            "package_type": "CWP",
            "package_code": "CWP-T01-MT-001",
            "control_account": "CA-VIA-T01-MT-001",
            "cbs_code": "6000 Equipos",
            "cost_category": "Equipos",
            "cost_code": "VIA-1.5.1-CA-VIA-T01-MT-001-6000",
            "contract": "CTR-MT-001",
            "budget": 3_200_000,
            "funds": 3_000_000,
            "currency": "USD",
        },
    ]
    for spec in examples:
        project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.code == spec["project_code"]))
        if not project:
            project = Project(
                tenant_id=tenant_id,
                code=spec["project_code"],
                name=spec["project_name"],
                phase="Execution",
                currency=spec["currency"],
                calendar_base="5x8",
                owner="Owner / Direccion",
                status="authorized",
                authorization_date=date(2026, 5, 12),
                authorization_ref=spec["authorization_ref"],
                configuration={"control_model": "FBS-WBS-CA-AWP-CBS-CostCode"},
                start_date=date(2026, 5, 12),
                finish_date=date(2027, 12, 31),
            )
            db.add(project)
            db.flush()
        ensure_project_control_plan(db, tenant_id, project.id)
        ensure_project_operational_setup(db, tenant_id, project.id)

        wbs = db.scalar(
            select(WBS).where(WBS.tenant_id == tenant_id, WBS.project_id == project.id, WBS.code == spec["wbs_code"])
        )
        if not wbs:
            wbs = WBS(
                tenant_id=tenant_id,
                project_id=project.id,
                parent_id=None,
                code=spec["wbs_code"],
                name=spec["wbs_name"],
                level=3,
                description=spec["wbs_name"],
                dictionary=f"Diccionario WBS para {spec['wbs_name']}.",
                responsible="Project Controls",
                status="active",
            )
            db.add(wbs)
            db.flush()

        fbs = db.scalar(
            select(FundingSource).where(
                FundingSource.tenant_id == tenant_id,
                FundingSource.project_id == project.id,
                FundingSource.code == spec["fbs_code"],
            )
        )
        if not fbs:
            fbs = FundingSource(
                tenant_id=tenant_id,
                project_id=project.id,
                code=spec["fbs_code"],
                name=spec["source_of_funds"],
                source_of_funds=spec["source_of_funds"],
                funding_type=spec["funding_type"],
                authorization_ref=spec["authorization_ref"],
                usage_restrictions=f"Uso restringido a {spec['wbs_name']}.",
                usage_rules="Validar disponibilidad antes de emitir compromisos.",
                amount=spec["funds"],
                funds_available=spec["funds"],
                currency=spec["currency"],
                status="approved",
            )
            db.add(fbs)
            db.flush()

        cbs = db.scalar(
            select(CostBreakdownStructure).where(
                CostBreakdownStructure.tenant_id == tenant_id,
                CostBreakdownStructure.project_id == project.id,
                CostBreakdownStructure.code == spec["cbs_code"],
            )
        )
        if not cbs:
            cbs = CostBreakdownStructure(
                tenant_id=tenant_id,
                project_id=project.id,
                parent_id=None,
                code=spec["cbs_code"],
                level=2,
                cost_category=spec["cost_category"],
                description=f"CBS {spec['cost_category']} para {spec['project_code']}.",
                status="active",
            )
            db.add(cbs)
            db.flush()

        account = db.scalar(
            select(ControlAccount).where(
                ControlAccount.tenant_id == tenant_id,
                ControlAccount.project_id == project.id,
                ControlAccount.code == spec["control_account"],
            )
        )
        if not account:
            account = ControlAccount(
                tenant_id=tenant_id,
                project_id=project.id,
                wbs_id=wbs.id,
                code=spec["control_account"],
                name=spec["wbs_name"],
                responsible="Project Controls Manager",
                discipline="Civil" if spec["project_code"] == "MIN-ABC" else "Roadworks",
                scope=spec["wbs_name"],
                budget=spec["budget"],
                cbs_code=spec["cbs_code"],
                contract_ref=spec["contract"],
                measurement_rule="Avance fisico por cantidades instaladas.",
                forecast=spec["budget"],
                lifecycle_status="active",
            )
            db.add(account)
            db.flush()

        package = db.scalar(
            select(WorkPackage).where(
                WorkPackage.tenant_id == tenant_id,
                WorkPackage.project_id == project.id,
                WorkPackage.code == spec["package_code"],
            )
        )
        if not package:
            package = WorkPackage(
                tenant_id=tenant_id,
                project_id=project.id,
                wbs_id=wbs.id,
                control_account_id=account.id,
                parent_id=None,
                package_type=spec["package_type"],
                code=spec["package_code"],
                title=spec["wbs_name"],
                description=f"Paquete AWP para {spec['wbs_name']}.",
                discipline=account.discipline,
                path_of_construction=spec["wbs_name"],
                owner_role="Workface Planner",
                readiness_status="ready_to_release",
                planned_release_date=date(2026, 6, 1),
                release_required_on=date(2026, 6, 15),
                main_constraints="Permisos, ingenieria IFC, materiales y acceso.",
                progress_percent=0,
            )
            db.add(package)
            db.flush()
            account.awp_package_id = package.id

        allocation = db.scalar(
            select(ControlAccountFundingAllocation).where(
                ControlAccountFundingAllocation.tenant_id == tenant_id,
                ControlAccountFundingAllocation.project_id == project.id,
                ControlAccountFundingAllocation.control_account_id == account.id,
                ControlAccountFundingAllocation.funding_source_id == fbs.id,
            )
        )
        if not allocation:
            db.add(
                ControlAccountFundingAllocation(
                    tenant_id=tenant_id,
                    project_id=project.id,
                    control_account_id=account.id,
                    funding_source_id=fbs.id,
                    allocated_amount=spec["funds"],
                    forecast_amount=spec["budget"],
                    distribution_note="Seed de matriz integrada FBS-WBS-CA-CBS.",
                    status="active",
                )
            )

        budget = db.scalar(
            select(Budget).where(
                Budget.tenant_id == tenant_id,
                Budget.project_id == project.id,
                Budget.control_account_id == account.id,
                Budget.cbs_code == spec["cbs_code"],
            )
        )
        if not budget:
            db.add(
                Budget(
                    tenant_id=tenant_id,
                    project_id=project.id,
                    control_account_id=account.id,
                    cbs_code=spec["cbs_code"],
                    bac=spec["budget"],
                    cost_loaded_pv=spec["budget"] * 0.4,
                )
            )

        contract = db.scalar(
            select(Contract).where(
                Contract.tenant_id == tenant_id,
                Contract.project_id == project.id,
                Contract.code == spec["contract"],
            )
        )
        if not contract:
            contract = Contract(
                tenant_id=tenant_id,
                project_id=project.id,
                funding_source_id=fbs.id,
                control_account_id=account.id,
                code=spec["contract"],
                title=f"Contrato {spec['wbs_name']}",
                counterparty="Contratista demo",
                contract_type="Construction",
                value=spec["budget"] * 0.8,
                status="active",
            )
            db.add(contract)
            db.flush()
        else:
            contract.funding_source_id = contract.funding_source_id or fbs.id

        cost_code = db.scalar(
            select(CostCode).where(
                CostCode.tenant_id == tenant_id,
                CostCode.project_id == project.id,
                CostCode.code == spec["cost_code"],
            )
        )
        if not cost_code:
            db.add(
                CostCode(
                    tenant_id=tenant_id,
                    project_id=project.id,
                    wbs_id=wbs.id,
                    control_account_id=account.id,
                    cbs_id=cbs.id,
                    fbs_id=fbs.id,
                    contract_ref=spec["contract"],
                    code=spec["cost_code"],
                    budget=spec["budget"],
                    funds_available=spec["funds"],
                    commitments=contract.value,
                    actual_costs=0,
                    forecast=spec["budget"],
                    status="active",
                )
            )
        IntegratedControlService(db).refresh_funding_balance(tenant_id, project.id, fbs)
        ControlCoreService(db).run_project_cycle(tenant_id, project.id)
    db.commit()


def ensure_demo_users(db: Session, tenant_id: int) -> None:
    demo_password = get_settings().demo_user_password
    users_seed = [
        ("ana.control@demo.local", "Ana Martinez", "Project Controls Manager"),
        ("pablo.planner@demo.local", "Pablo Rojas", "Lead Planner"),
        ("camila.cost@demo.local", "Camila Torres", "Cost Controller"),
        ("laura.contracts@demo.local", "Laura Gomez", "Contract Manager"),
        ("mateo.field@demo.local", "Mateo Ruiz", "Field Engineer"),
        ("sofia.awp@demo.local", "Sofia Navarro", "Workface Planner"),
        ("diana.docs@demo.local", "Diana Vega", "Document Controller"),
        ("direccion@demo.local", "Direccion Proyecto", "Executive Sponsor"),
    ]
    users: dict[str, UserAccount] = {}
    for email, full_name, title in users_seed:
        user = db.scalar(select(UserAccount).where(UserAccount.tenant_id == tenant_id, UserAccount.email == email))
        if not user:
            user = UserAccount(tenant_id=tenant_id, email=email, full_name=full_name, title=title)
            db.add(user)
            db.flush()
        ensure_local_credential(db, tenant_id, user.id, demo_password)
        users[email] = user

    projects = list(db.scalars(select(Project).where(Project.tenant_id == tenant_id)).all())
    for project in projects:
        project_roles = [
            ("ana.control@demo.local", "Control Manager"),
            ("direccion@demo.local", "Executive"),
            ("camila.cost@demo.local", "Cost Controller"),
            ("diana.docs@demo.local", "Document Controller"),
        ]
        if project.code in {"CTRL-DEMO-001", "EPC-PIPE-001"}:
            project_roles += [
                ("pablo.planner@demo.local", "Planner"),
                ("laura.contracts@demo.local", "Contract Manager"),
                ("sofia.awp@demo.local", "Workface Planner"),
            ]
        else:
            project_roles += [
                ("mateo.field@demo.local", "Field Engineer"),
                ("pablo.planner@demo.local", "Planner"),
                ("sofia.awp@demo.local", "Workface Planner"),
            ]
        for email, role in project_roles:
            ensure_membership(db, tenant_id, project.id, users[email].id, role)
    db.commit()


def ensure_local_credential(db: Session, tenant_id: int, user_id: int, password: str) -> None:
    credential = db.scalar(
        select(AuthCredential).where(
            AuthCredential.tenant_id == tenant_id,
            AuthCredential.user_id == user_id,
            AuthCredential.provider == "local",
        )
    )
    if credential:
        credential.is_active = True
        credential.password_hash = hash_password(password)
        return
    db.add(
        AuthCredential(
            tenant_id=tenant_id,
            user_id=user_id,
            provider="local",
            password_hash=hash_password(password),
            is_active=True,
        )
    )


def ensure_membership(db: Session, tenant_id: int, project_id: int, user_id: int, role: str) -> None:
    membership = db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.tenant_id == tenant_id,
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user_id,
        )
    )
    permissions = role_permissions(role)
    if membership:
        membership.role = role
        for key, value in permissions.items():
            setattr(membership, key, value)
        return
    db.add(
        ProjectMembership(
            tenant_id=tenant_id,
            project_id=project_id,
            user_id=user_id,
            role=role,
            **permissions,
        )
    )


def role_permissions(role: str) -> dict[str, bool]:
    return {
        "can_capture_progress": role in {"Control Manager", "Planner", "Field Engineer", "Workface Planner"},
        "can_capture_cost": role in {"Control Manager", "Cost Controller"},
        "can_approve_workflow": role in {"Control Manager"},
        "can_manage_contract": role in {"Control Manager", "Contract Manager"},
        "can_configure": role in {"Control Manager"},
    }


def ensure_secondary_project(db: Session, tenant_id: int) -> Project | None:
    existing = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.code == "REF-TURN-002"))
    if existing:
        ensure_demo_schedule(db, tenant_id, existing.id)
        return existing

    project = Project(
        tenant_id=tenant_id,
        code="REF-TURN-002",
        name="Refinery Turnaround Utilities Upgrade",
        phase="Planning",
        currency="USD",
        start_date=date(2026, 2, 2),
        finish_date=date(2026, 9, 30),
    )
    db.add(project)
    db.flush()

    wbs = WBS(tenant_id=tenant_id, project_id=project.id, code="2.1", name="Utilities and Turnaround", parent_id=None)
    db.add(wbs)
    db.flush()

    accounts = [
        ControlAccount(
            tenant_id=tenant_id,
            project_id=project.id,
            wbs_id=wbs.id,
            code="CA-UTIL-120",
            name="Steam and condensate tie-ins",
            responsible="Utilities Lead",
            discipline="Mechanical",
        ),
        ControlAccount(
            tenant_id=tenant_id,
            project_id=project.id,
            wbs_id=wbs.id,
            code="CA-INST-220",
            name="Instrumentation loop checks",
            responsible="I&C Lead",
            discipline="Instrumentation",
        ),
    ]
    db.add_all(accounts)
    db.flush()

    for account, cbs, bac, pv, percent, ac, hours, qty in [
        (accounts[0], "CBS-UTIL-120", 1_750_000, 840_000, 41, 910_000, 4200, 38000),
        (accounts[1], "CBS-INST-220", 980_000, 360_000, 34, 310_000, 2900, 25000),
    ]:
        db.add(
            Budget(
                tenant_id=tenant_id,
                project_id=project.id,
                control_account_id=account.id,
                cbs_code=cbs,
                bac=bac,
                cost_loaded_pv=pv,
            )
        )
        db.add(
            CostRecord(
                tenant_id=tenant_id,
                project_id=project.id,
                control_account_id=account.id,
                source=CostSource.invoice,
                amount=ac,
                incurred_on=date(2026, 5, 1),
                description="Actual cost imported from turnaround cost ledger.",
            )
        )
        db.add(
            ProgressRecord(
                tenant_id=tenant_id,
                project_id=project.id,
                control_account_id=account.id,
                physical_percent=percent,
                quantity_installed=qty,
                labor_hours=hours,
                reported_on=date(2026, 5, 1),
                evidence_ref="TA-FIELD-2026-05-01",
            )
        )

    db.add(
        ChangeRequest(
            tenant_id=tenant_id,
            project_id=project.id,
            control_account_id=accounts[0].id,
            title="Additional steam tracing after HAZOP action",
            deviation="HAZOP action added steam tracing for winterization readiness.",
            cost_impact=92_000,
            schedule_impact_days=4,
        )
    )
    db.add(
        Document(
            tenant_id=tenant_id,
            project_id=project.id,
            linked_entity_type="ControlAccount",
            linked_entity_id=accounts[0].id,
            title="Turnaround readiness package",
            doc_type="Readiness Review",
            uri="edms://turnaround/readiness/REF-TURN-002",
        )
    )
    db.flush()
    ensure_demo_schedule(db, tenant_id, project.id)
    db.commit()
    return project


def ensure_contract_records(db: Session, tenant_id: int, project_id: int) -> None:
    inspector = inspect(db.get_bind())
    table_names = set(inspector.get_table_names())
    if "contracts" in table_names:
        contract_columns = {column["name"] for column in inspector.get_columns("contracts")}
        if "control_account_id" not in contract_columns:
            return

    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    if not project:
        return
    account = db.scalar(
        select(ControlAccount)
        .where(ControlAccount.tenant_id == tenant_id, ControlAccount.project_id == project_id)
        .order_by(ControlAccount.code)
    )
    existing = db.scalars(
        select(Contract).where(Contract.tenant_id == tenant_id, Contract.project_id == project_id)
    ).first()
    if existing:
        if account and not existing.control_account_id:
            existing.control_account_id = account.id
            db.flush()
        return

    is_turnaround = project.code == "REF-TURN-002"
    contract = Contract(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=account.id if account else None,
        code="CON-TA-001" if is_turnaround else "CON-CTRL-001",
        title="Turnaround mechanical and instrumentation services"
        if is_turnaround
        else "Integrated project controls and construction support",
        counterparty="Industrial Services Contractor" if is_turnaround else "Owner / EPC Contractor",
        contract_type="Services" if is_turnaround else "EPC / Controls",
        value=1_850_000 if is_turnaround else 4_250_000,
        status="active",
    )
    db.add(contract)
    db.flush()
    db.add(
        ContractCommunication(
            tenant_id=tenant_id,
            project_id=project_id,
            contract_id=contract.id,
            communication_type="notice",
            subject="Notice of control baseline and reporting requirements",
            reference=f"{contract.code}-COMM-001",
            sent_on=date(2026, 5, 2),
            status="issued",
        )
    )
    db.add(
        Document(
            tenant_id=tenant_id,
            project_id=project_id,
            linked_entity_type="Contract",
            linked_entity_id=contract.id,
            title="Contract administration register",
            doc_type="Contract Register",
            uri=f"edms://contracts/{contract.code}/register",
        )
    )


def ensure_purchase_order_records(db: Session, tenant_id: int, project_id: int) -> None:
    inspector = inspect(db.get_bind())
    if "purchase_orders" not in set(inspector.get_table_names()):
        return

    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    if not project:
        return
    accounts = list(
        db.scalars(
            select(ControlAccount)
            .where(ControlAccount.tenant_id == tenant_id, ControlAccount.project_id == project_id)
            .order_by(ControlAccount.code)
        ).all()
    )
    if not accounts:
        return
    contracts = list(
        db.scalars(
            select(Contract)
            .where(Contract.tenant_id == tenant_id, Contract.project_id == project_id)
            .order_by(Contract.code)
        ).all()
    )
    contract_by_account = {
        contract.control_account_id: contract for contract in contracts if contract.control_account_id
    }
    is_turnaround = project.code == "REF-TURN-002"
    rows = (
        [
            (
                "PO-CTRL-1001",
                accounts[0],
                "Mechanical installation purchase order",
                "Industrial Services Contractor",
                1_250_000,
            ),
            (
                "PO-CTRL-2101",
                accounts[1] if len(accounts) > 1 else accounts[0],
                "Valve and piping material purchase order",
                "Valve Supplier",
                980_000,
            ),
            (
                "PO-CTRL-3101",
                accounts[2] if len(accounts) > 2 else accounts[-1],
                "Electrical hook-up supply order",
                "Electrical Vendor",
                420_000,
            ),
        ]
        if not is_turnaround
        else [
            (
                "PO-TA-1201",
                accounts[0],
                "Steam and condensate tie-in purchase order",
                "Industrial Services Contractor",
                760_000,
            ),
            (
                "PO-TA-2201",
                accounts[1] if len(accounts) > 1 else accounts[0],
                "Instrumentation loop check order",
                "I&C Services Vendor",
                290_000,
            ),
        ]
    )
    existing_numbers = set(
        db.scalars(
            select(PurchaseOrder.po_number).where(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.project_id == project_id,
            )
        ).all()
    )
    for po_number, account, description, vendor, amount in rows:
        if po_number in existing_numbers:
            continue
        db.add(
            PurchaseOrder(
                tenant_id=tenant_id,
                project_id=project_id,
                control_account_id=account.id,
                contract_id=contract_by_account.get(account.id).id if account.id in contract_by_account else None,
                po_number=po_number,
                description=description,
                vendor=vendor,
                committed_amount=amount,
                status="issued",
                issued_on=date(2026, 5, 2),
            )
        )
    db.commit()


def ensure_payment_certificate_records(db: Session, tenant_id: int, project_id: int) -> None:
    inspector = inspect(db.get_bind())
    if "payment_certificates" not in set(inspector.get_table_names()):
        return

    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    if not project:
        return
    accounts = list(
        db.scalars(
            select(ControlAccount)
            .where(ControlAccount.tenant_id == tenant_id, ControlAccount.project_id == project_id)
            .order_by(ControlAccount.code)
        ).all()
    )
    if not accounts:
        return
    purchase_orders = list(
        db.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.project_id == project_id)
            .order_by(PurchaseOrder.po_number)
        ).all()
    )
    contracts = list(
        db.scalars(
            select(Contract)
            .where(Contract.tenant_id == tenant_id, Contract.project_id == project_id)
            .order_by(Contract.code)
        ).all()
    )
    po_by_account = {order.control_account_id: order for order in purchase_orders if order.control_account_id}
    contract_by_account = {
        contract.control_account_id: contract for contract in contracts if contract.control_account_id
    }
    is_turnaround = project.code == "REF-TURN-002"
    rows = (
        [
            ("AP-CTRL-100-001", accounts[0], "2026-05", 1_820_000, 91_000),
            ("AP-CTRL-210-001", accounts[1] if len(accounts) > 1 else accounts[0], "2026-05", 2_620_000, 131_000),
            ("AP-CTRL-310-001", accounts[2] if len(accounts) > 2 else accounts[-1], "2026-05", 730_000, 36_500),
        ]
        if not is_turnaround
        else [
            ("AP-TA-120-001", accounts[0], "2026-05", 910_000, 45_500),
            ("AP-TA-220-001", accounts[1] if len(accounts) > 1 else accounts[0], "2026-05", 310_000, 15_500),
        ]
    )
    existing_numbers = set(
        db.scalars(
            select(PaymentCertificate.certificate_no).where(
                PaymentCertificate.tenant_id == tenant_id,
                PaymentCertificate.project_id == project_id,
            )
        ).all()
    )
    for certificate_no, account, period_label, certified_amount, retained_amount in rows:
        if certificate_no in existing_numbers:
            continue
        db.add(
            PaymentCertificate(
                tenant_id=tenant_id,
                project_id=project_id,
                control_account_id=account.id,
                contract_id=contract_by_account.get(account.id).id if account.id in contract_by_account else None,
                purchase_order_id=po_by_account.get(account.id).id if account.id in po_by_account else None,
                certificate_no=certificate_no,
                period_label=period_label,
                certified_amount=certified_amount,
                retained_amount=retained_amount,
                status="certified",
                certified_on=date(2026, 5, 5),
            )
        )
    db.commit()


def ensure_warehouse_receipt_records(db: Session, tenant_id: int, project_id: int) -> None:
    inspector = inspect(db.get_bind())
    if "warehouse_receipts" not in set(inspector.get_table_names()):
        return

    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    if not project:
        return
    accounts = list(
        db.scalars(
            select(ControlAccount)
            .where(ControlAccount.tenant_id == tenant_id, ControlAccount.project_id == project_id)
            .order_by(ControlAccount.code)
        ).all()
    )
    if not accounts:
        return
    purchase_orders = list(
        db.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.project_id == project_id)
            .order_by(PurchaseOrder.po_number)
        ).all()
    )
    contracts = list(
        db.scalars(
            select(Contract)
            .where(Contract.tenant_id == tenant_id, Contract.project_id == project_id)
            .order_by(Contract.code)
        ).all()
    )
    po_by_account = {order.control_account_id: order for order in purchase_orders if order.control_account_id}
    contract_by_account = {
        contract.control_account_id: contract for contract in contracts if contract.control_account_id
    }
    is_turnaround = project.code == "REF-TURN-002"
    rows = (
        [
            (
                "GRN-CTRL-100-001",
                accounts[0],
                "Mechanical material receipt and warehouse acceptance",
                12,
                18_500,
                222_000,
            ),
            (
                "GRN-CTRL-210-001",
                accounts[1] if len(accounts) > 1 else accounts[0],
                "Valve and piping materials received in warehouse",
                8,
                42_500,
                340_000,
            ),
            (
                "GRN-CTRL-310-001",
                accounts[2] if len(accounts) > 2 else accounts[-1],
                "Electrical bulk materials warehouse receipt",
                15,
                9_200,
                138_000,
            ),
        ]
        if not is_turnaround
        else [
            ("GRN-TA-120-001", accounts[0], "Shutdown mechanical spares received", 9, 22_000, 198_000),
            (
                "GRN-TA-220-001",
                accounts[1] if len(accounts) > 1 else accounts[0],
                "Instrumentation materials received",
                6,
                15_500,
                93_000,
            ),
        ]
    )
    existing_numbers = set(
        db.scalars(
            select(WarehouseReceipt.receipt_no).where(
                WarehouseReceipt.tenant_id == tenant_id,
                WarehouseReceipt.project_id == project_id,
            )
        ).all()
    )
    for receipt_no, account, description, quantity, unit_cost, received_value in rows:
        if receipt_no in existing_numbers:
            continue
        db.add(
            WarehouseReceipt(
                tenant_id=tenant_id,
                project_id=project_id,
                control_account_id=account.id,
                contract_id=contract_by_account.get(account.id).id if account.id in contract_by_account else None,
                purchase_order_id=po_by_account.get(account.id).id if account.id in po_by_account else None,
                receipt_no=receipt_no,
                description=description,
                received_quantity=quantity,
                unit_cost=unit_cost,
                received_value=received_value,
                status="accepted",
                received_on=date(2026, 5, 6),
            )
        )
    db.commit()


def ensure_rfq_records(db: Session, tenant_id: int, project_id: int) -> None:
    inspector = inspect(db.get_bind())
    table_names = set(inspector.get_table_names())
    if "rfq_packages" not in table_names or "rfq_bids" not in table_names:
        return

    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    if not project:
        return
    accounts = list(
        db.scalars(
            select(ControlAccount)
            .where(ControlAccount.tenant_id == tenant_id, ControlAccount.project_id == project_id)
            .order_by(ControlAccount.code)
        ).all()
    )
    if not accounts:
        return
    is_turnaround = project.code == "REF-TURN-002"
    package_rows = (
        [
            (
                "RFQ-CTRL-2101",
                accounts[1] if len(accounts) > 1 else accounts[0],
                "Valve supply and expediting RFQ",
                "Supply valves, expediting support, QA dossier and warehouse delivery requirements.",
                1_050_000,
                "under_evaluation",
            ),
            (
                "RFQ-CTRL-3101",
                accounts[2] if len(accounts) > 2 else accounts[-1],
                "Electrical installation services RFQ",
                "Field electrical hook-up support, supervision, test packs and precommissioning labor.",
                620_000,
                "issued",
            ),
        ]
        if not is_turnaround
        else [
            (
                "RFQ-TA-2201",
                accounts[1] if len(accounts) > 1 else accounts[0],
                "Instrumentation loop-check RFQ",
                "Loop checks, test packs, calibration records and turnaround shift support.",
                330_000,
                "under_evaluation",
            ),
        ]
    )
    existing_packages = {
        package.package_no: package
        for package in db.scalars(
            select(RFQPackage).where(RFQPackage.tenant_id == tenant_id, RFQPackage.project_id == project_id)
        ).all()
    }
    for package_no, account, title, scope, budget, status in package_rows:
        package = existing_packages.get(package_no)
        if not package:
            package = RFQPackage(
                tenant_id=tenant_id,
                project_id=project_id,
                control_account_id=account.id,
                package_no=package_no,
                title=title,
                scope_summary=scope,
                procurement_method="RFQ",
                status=status,
                budget_amount=budget,
                issue_date=date(2026, 5, 1),
                due_date=date(2026, 5, 18),
            )
            db.add(package)
            db.flush()
            existing_packages[package_no] = package

    primary_package = existing_packages.get("RFQ-TA-2201" if is_turnaround else "RFQ-CTRL-2101")
    if not primary_package:
        db.commit()
        return

    existing_bidder_names = set(
        db.scalars(
            select(RFQBid.bidder_name).where(
                RFQBid.tenant_id == tenant_id,
                RFQBid.project_id == project_id,
                RFQBid.rfq_package_id == primary_package.id,
            )
        ).all()
    )
    bid_rows = (
        [
            (
                "Andes Industrial Supply",
                970_000,
                84,
                88,
                78,
                80,
                "Shortlisted; best commercial position with acceptable schedule.",
            ),
            ("Global Valve Partners", 1_020_000, 91, 76, 86, 84, "Technically strong and lower execution risk."),
            ("Rapid Pipe Logistics", 945_000, 74, 90, 72, 66, "Lowest price but higher delivery risk."),
        ]
        if not is_turnaround
        else [
            ("LoopCheck Services", 305_000, 86, 84, 82, 78, "Balanced technical and commercial offer."),
            ("I&C Rapid Response", 322_000, 90, 78, 88, 84, "Higher score for schedule recovery capacity."),
        ]
    )
    for bidder_name, amount, technical, commercial, schedule, risk, notes in bid_rows:
        if bidder_name in existing_bidder_names:
            continue
        weighted_score = round(technical * 0.35 + commercial * 0.35 + schedule * 0.15 + risk * 0.15, 1)
        db.add(
            RFQBid(
                tenant_id=tenant_id,
                project_id=project_id,
                rfq_package_id=primary_package.id,
                bidder_name=bidder_name,
                bid_amount=amount,
                technical_score=technical,
                commercial_score=commercial,
                schedule_score=schedule,
                risk_score=risk,
                weighted_score=weighted_score,
                status="received",
                submitted_on=date(2026, 5, 12),
                notes=notes,
            )
        )
    db.commit()


def ensure_awp_records(db: Session, tenant_id: int, project_id: int) -> None:
    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    if not project:
        return
    accounts = list(
        db.scalars(
            select(ControlAccount)
            .where(ControlAccount.tenant_id == tenant_id, ControlAccount.project_id == project_id)
            .order_by(ControlAccount.code)
        ).all()
    )
    if not accounts:
        return

    by_code = {account.code: account for account in accounts}
    first_account = accounts[0]
    second_account = accounts[1] if len(accounts) > 1 else accounts[0]
    third_account = accounts[2] if len(accounts) > 2 else accounts[-1]
    is_turnaround = project.code == "REF-TURN-002"
    package_seed = (
        [
            (
                None,
                None,
                "CWA",
                "CWA-TA-01",
                "Turnaround utilities work area",
                "Construction",
                10,
                "Utilities tie-in sequence",
                "Workface Planner",
                "ready_to_release",
                date(2026, 2, 2),
                date(2026, 9, 30),
                35,
            ),
            (
                "CWA-TA-01",
                by_code.get("CA-UTIL-120", first_account),
                "CWP",
                "CWP-UTIL-120",
                "Steam and condensate tie-ins construction package",
                "Mechanical",
                20,
                "Outage window critical path",
                "Workface Planner",
                "constraint_review",
                date(2026, 3, 9),
                date(2026, 6, 26),
                41,
            ),
            (
                "CWP-UTIL-120",
                by_code.get("CA-UTIL-120", first_account),
                "IWP",
                "IWP-UTIL-120A",
                "Execute first tie-in workface package",
                "Mechanical",
                30,
                "Tie-in train A before loop checks",
                "Field Engineer",
                "blocked",
                date(2026, 5, 6),
                date(2026, 5, 24),
                28,
            ),
            (
                "CWA-TA-01",
                by_code.get("CA-INST-220", second_account),
                "IWP",
                "IWP-INST-220A",
                "Instrumentation loop check package",
                "Instrumentation",
                40,
                "Release after mechanical turnover",
                "Field Engineer",
                "ready_to_release",
                date(2026, 5, 27),
                date(2026, 6, 18),
                15,
            ),
        ]
        if is_turnaround
        else [
            (
                None,
                None,
                "CWA",
                "CWA-COMP-01",
                "Compressor station construction area",
                "Construction",
                10,
                "Mechanical completion before piping pressure test",
                "Workface Planner",
                "ready_to_release",
                date(2026, 2, 9),
                date(2026, 10, 9),
                52,
            ),
            (
                "CWA-COMP-01",
                by_code.get("CA-MECH-100", first_account),
                "EWP",
                "EWP-MECH-100",
                "Compressor mechanical engineering work package",
                "Mechanical",
                20,
                "Engineering deliverables aligned to CWP-MECH-100",
                "Planner",
                "released",
                date(2026, 1, 15),
                date(2026, 3, 1),
                100,
            ),
            (
                "CWA-COMP-01",
                by_code.get("CA-MECH-100", first_account),
                "CWP",
                "CWP-MECH-100",
                "Compressor mechanical construction work package",
                "Mechanical",
                30,
                "Set equipment before piping tie-ins",
                "Workface Planner",
                "ready_to_release",
                date(2026, 3, 2),
                date(2026, 7, 17),
                62,
            ),
            (
                "CWP-MECH-100",
                by_code.get("CA-PIPE-210", second_account),
                "PWP",
                "PWP-VALVE-210",
                "Owner-furnished valve procurement package",
                "Piping",
                40,
                "Valve delivery gates piping IWP release",
                "Contract Manager",
                "blocked",
                date(2026, 2, 9),
                date(2026, 5, 28),
                70,
            ),
            (
                "CWP-MECH-100",
                by_code.get("CA-PIPE-210", second_account),
                "IWP",
                "IWP-PIPE-210A",
                "Pipe rack erection workface package A",
                "Piping",
                50,
                "Piping train A after equipment set",
                "Field Engineer",
                "blocked",
                date(2026, 5, 6),
                date(2026, 6, 14),
                48,
            ),
            (
                "CWA-COMP-01",
                by_code.get("CA-ELEC-310", third_account),
                "IWP",
                "IWP-ELEC-310A",
                "Electrical hook-up workface package A",
                "Electrical",
                60,
                "Hook-up after mechanical completion",
                "Field Engineer",
                "ready_to_release",
                date(2026, 6, 8),
                date(2026, 7, 10),
                22,
            ),
        ]
    )

    packages: dict[str, WorkPackage] = {}
    for (
        parent_code,
        account,
        package_type,
        code,
        title,
        discipline,
        sequence_no,
        path,
        owner_role,
        readiness,
        start,
        finish,
        progress,
    ) in package_seed:
        existing = db.scalar(
            select(WorkPackage).where(
                WorkPackage.tenant_id == tenant_id,
                WorkPackage.project_id == project_id,
                WorkPackage.code == code,
            )
        )
        parent_id = packages[parent_code].id if parent_code and parent_code in packages else None
        if existing:
            existing.control_account_id = account.id if account else None
            existing.parent_id = parent_id
            existing.package_type = package_type
            existing.title = title
            existing.discipline = discipline
            existing.sequence_no = sequence_no
            existing.path_of_construction = path
            existing.owner_role = owner_role
            existing.readiness_status = (
                readiness
                if existing.readiness_status not in {"blocked", "released", "complete"}
                else existing.readiness_status
            )
            existing.planned_start = start
            existing.planned_finish = finish
            existing.progress_percent = progress
            package = existing
        else:
            package = WorkPackage(
                tenant_id=tenant_id,
                project_id=project_id,
                control_account_id=account.id if account else None,
                parent_id=parent_id,
                package_type=package_type,
                code=code,
                title=title,
                discipline=discipline,
                sequence_no=sequence_no,
                path_of_construction=path,
                owner_role=owner_role,
                readiness_status=readiness,
                planned_start=start,
                planned_finish=finish,
                progress_percent=progress,
            )
            db.add(package)
            db.flush()
        packages[code] = package
        ensure_awp_business_process(db, tenant_id, project_id, package)

    constraints_seed = (
        [
            (
                "IWP-UTIL-120A",
                "Permit",
                "Hot work permit approval required before outage execution.",
                "Construction Manager",
                date(2026, 5, 6),
                "open",
                True,
            ),
            (
                "CWP-UTIL-120",
                "Engineering",
                "Tie-in isometric revision must be issued for construction.",
                "Planner",
                date(2026, 5, 3),
                "open",
                True,
            ),
        ]
        if is_turnaround
        else [
            (
                "PWP-VALVE-210",
                "Material",
                "Owner-furnished 24-inch valves are not available at workface.",
                "Contract Manager",
                date(2026, 5, 10),
                "open",
                True,
            ),
            (
                "IWP-PIPE-210A",
                "Access",
                "Scaffold handover and access tag required for pipe rack elevation 2.",
                "Construction Manager",
                date(2026, 5, 8),
                "open",
                True,
            ),
            (
                "IWP-PIPE-210A",
                "Document",
                "Latest hydrotest limits and marked-up isometrics must be linked.",
                "Document Control",
                date(2026, 5, 7),
                "closed",
                False,
            ),
            (
                "IWP-ELEC-310A",
                "Safety",
                "JSA reviewed with field crew before release.",
                "Field Engineer",
                date(2026, 6, 6),
                "closed",
                False,
            ),
        ]
    )
    for package_code, constraint_type, description, owner_role, required_by, status, blocking in constraints_seed:
        package = packages.get(package_code)
        if not package:
            continue
        existing_constraint = db.scalar(
            select(WorkPackageConstraint).where(
                WorkPackageConstraint.tenant_id == tenant_id,
                WorkPackageConstraint.project_id == project_id,
                WorkPackageConstraint.work_package_id == package.id,
                WorkPackageConstraint.constraint_type == constraint_type,
                WorkPackageConstraint.description == description,
            )
        )
        if existing_constraint:
            existing_constraint.owner_role = owner_role
            existing_constraint.required_by = required_by
            existing_constraint.status = status
            existing_constraint.blocking = blocking
            continue
        db.add(
            WorkPackageConstraint(
                tenant_id=tenant_id,
                project_id=project_id,
                work_package_id=package.id,
                constraint_type=constraint_type,
                description=description,
                owner_role=owner_role,
                required_by=required_by,
                status=status,
                blocking=blocking,
            )
        )
    db.commit()


def ensure_awp_business_process(db: Session, tenant_id: int, project_id: int, package: WorkPackage) -> None:
    existing = db.scalar(
        select(BusinessProcessInstance).where(
            BusinessProcessInstance.tenant_id == tenant_id,
            BusinessProcessInstance.project_id == project_id,
            BusinessProcessInstance.trigger_entity_type == "WorkPackage",
            BusinessProcessInstance.trigger_entity_id == package.id,
        )
    )
    if existing:
        existing.title = f"AWP Readiness - {package.code}"
        existing.ball_in_court = (
            package.owner_role if existing.current_step == "Constraint Review" else existing.ball_in_court
        )
        return
    process = BusinessProcessInstance(
        tenant_id=tenant_id,
        project_id=project_id,
        trigger_entity_type="WorkPackage",
        trigger_entity_id=package.id,
        process_code="AWP-READY",
        process_name="AWP Readiness",
        record_no=f"AWP-{package.id:05d}",
        title=f"AWP Readiness - {package.code}",
        status="in_review",
        current_step="Constraint Review",
        ball_in_court=package.owner_role,
    )
    db.add(process)
    db.flush()
    for order, (name, detail, owner_role, status, tone) in enumerate(
        [
            (
                "Path Definition",
                "Path of construction and sequence are aligned with the approved schedule.",
                "Planner",
                "Complete",
                "complete",
            ),
            (
                "Package Scope",
                "CWA/CWP/EWP/PWP/IWP scope is tied to control accounts and deliverables.",
                "Workface Planner",
                "Complete",
                "complete",
            ),
            (
                "Constraint Review",
                "Open constraints determine workface readiness.",
                package.owner_role,
                "Active",
                "active",
            ),
            (
                "Release",
                "Ready package can be released to field execution.",
                "Construction Manager",
                "Queued",
                "queued",
            ),
            ("Execute", "Field progress feeds Control Core and AWP status.", "Field Engineer", "Queued", "queued"),
        ],
        start=1,
    ):
        db.add(
            WorkflowStepInstance(
                tenant_id=tenant_id,
                project_id=project_id,
                process_instance_id=process.id,
                step_order=order,
                name=name,
                detail=detail,
                owner_role=owner_role,
                status=status,
                tone=tone,
            )
        )


def ensure_claim_entitlement_records(db: Session, tenant_id: int, project_id: int) -> None:
    claims = list(
        db.scalars(
            select(Claim).where(Claim.tenant_id == tenant_id, Claim.project_id == project_id).order_by(Claim.id)
        ).all()
    )
    for claim in claims:
        ensure_claim_business_process(db, tenant_id, project_id, claim)
        existing = db.scalar(
            select(ClaimEntitlementItem).where(
                ClaimEntitlementItem.tenant_id == tenant_id,
                ClaimEntitlementItem.project_id == project_id,
                ClaimEntitlementItem.claim_id == claim.id,
            )
        )
        if existing:
            continue
        entitlement_seed = [
            (
                "RP120R-21",
                "Contract Basis",
                "Contractual entitlement",
                "Identify the contract clause, change mechanism or legal basis that allows recovery.",
                "Potential basis is tied to owner-furnished equipment and contract administration records.",
                "CON-CTRL-001 / COM-VALVE-DELAY",
                "partial",
                1.2,
                0.65,
            ),
            (
                "RP120R-21",
                "Change / Event",
                "Compensable event definition",
                "Define the changed condition, direction, delay, disruption or other event with dates and affected scope.",
                claim.causality,
                "Event: Late delivery of 24-inch valves",
                "satisfied",
                1.1,
                0.9,
            ),
            (
                "RP120R-21",
                "Notice",
                "Notice and procedural compliance",
                "Demonstrate that contractual notice, timing and required content were preserved.",
                "Notice evidence exists but requires formal linkage to contractual time bars.",
                "CON-CTRL-001-COMM-001",
                "partial",
                1.0,
                0.6,
            ),
            (
                "RP120R-21",
                "Causation",
                "Cause and effect linkage",
                "Connect the event to schedule, productivity, cost or resource impact using contemporaneous records.",
                claim.causality,
                "Field reports / procurement correspondence",
                "partial",
                1.4,
                0.7,
            ),
            (
                "RP120R-21",
                "Impact",
                "Schedule and cost impact",
                "Quantify time and cost effect and connect it to impacted activities or control accounts.",
                claim.impact,
                "CA-PIPE-210 / schedule activity P6-PIPE-2100",
                "partial",
                1.3,
                0.55,
            ),
            (
                "RP120R-21",
                "Quantum",
                "Damages calculation",
                "Calculate recoverable cost with traceable labor, equipment, material, subcontract and overhead records.",
                "Cost exposure exists; full damages calculation and exclusions are pending.",
                "ERP cut-off / equipment logs",
                "gap",
                1.2,
                0.35,
            ),
            (
                "RP120R-21",
                "Mitigation",
                "Mitigation and avoidance",
                "Show reasonable mitigation, resequencing attempts, notices and decisions taken to reduce impact.",
                "Resequencing noted, but mitigation record is incomplete.",
                "Lookahead / daily reports",
                "gap",
                0.8,
                0.3,
            ),
            (
                "RP120R-21",
                "Evidence",
                "Contemporaneous evidence package",
                "Link contract, correspondence, field reports, photos, schedule updates, costs and decisions.",
                claim.evidence_summary,
                "Claim evidence package",
                "partial",
                1.0,
                0.7,
            ),
            (
                "RP130R-23",
                "Cumulative Impact",
                "Change population and saturation",
                "Identify the population of changes and explain how cumulative change volume disrupted planned productivity.",
                "Multiple changes and material constraints are visible, but saturation analysis is not complete.",
                "Change log / AWP constraints",
                "gap",
                1.2,
                0.35,
            ),
            (
                "RP130R-23",
                "Productivity",
                "Productivity baseline / measured mile",
                "Establish a reliable unimpacted or least impacted productivity baseline for comparison.",
                "Progress and labor hours exist by control account; measured mile selection is pending.",
                "ProgressRecord labor hours",
                "partial",
                1.4,
                0.5,
            ),
            (
                "RP130R-23",
                "Causation",
                "Cumulative causal link",
                "Separate cumulative impact from discrete changes, contractor-caused issues and normal inefficiency.",
                "Need cause segregation between owner-furnished valve delay, access constraints and execution factors.",
                "Forensic cause matrix",
                "gap",
                1.3,
                0.25,
            ),
            (
                "RP130R-23",
                "Damages",
                "Cumulative impact damages",
                "Translate productivity loss into recoverable labor, equipment and related cost impact.",
                "Cumulative damages model is not yet calculated.",
                "Pending productivity analysis",
                "gap",
                1.1,
                0.2,
            ),
        ]
        for sequence_no, (
            source,
            category,
            element,
            requirement,
            assessment,
            evidence_ref,
            status,
            weight,
            score,
        ) in enumerate(entitlement_seed, start=10):
            db.add(
                ClaimEntitlementItem(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    claim_id=claim.id,
                    practice_source=source,
                    category=category,
                    element=element,
                    requirement=requirement,
                    assessment=assessment,
                    evidence_ref=evidence_ref,
                    status=status,
                    weight=weight,
                    score=score,
                    sequence_no=sequence_no,
                )
            )
    db.commit()


def ensure_claim_notice_and_impact_records(db: Session, tenant_id: int, project_id: int) -> None:
    claims = list(
        db.scalars(
            select(Claim).where(Claim.tenant_id == tenant_id, Claim.project_id == project_id).order_by(Claim.id)
        ).all()
    )
    if not claims:
        return

    contract = db.scalar(
        select(Contract)
        .where(Contract.tenant_id == tenant_id, Contract.project_id == project_id)
        .order_by(Contract.code)
    )

    for claim in claims:
        existing_notice = db.scalar(
            select(ContractNotice).where(
                ContractNotice.tenant_id == tenant_id,
                ContractNotice.project_id == project_id,
                ContractNotice.claim_id == claim.id,
            )
        )
        if not existing_notice:
            db.add(
                ContractNotice(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    contract_id=contract.id if contract else None,
                    claim_id=claim.id,
                    change_request_id=None,
                    notice_type="contractual_notice",
                    subject=f"Notice of potential claim - {claim.title}",
                    reference=f"{contract.code if contract else 'CON'}-NOTICE-CL-{claim.id:03d}",
                    event_date=date(2026, 4, 22),
                    due_date=date(2026, 4, 29),
                    notice_date=date(2026, 4, 28),
                    status="issued",
                    days_late=0,
                    compliance_status="compliant",
                )
            )

        existing_analysis = db.scalar(
            select(ClaimImpactAnalysis).where(
                ClaimImpactAnalysis.tenant_id == tenant_id,
                ClaimImpactAnalysis.project_id == project_id,
                ClaimImpactAnalysis.claim_id == claim.id,
            )
        )
        if existing_analysis:
            continue

        db.add_all(
            [
                ClaimImpactAnalysis(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    claim_id=claim.id,
                    method="Time Impact Analysis",
                    impacted_activity="P6-PIPE-2100 / Pipe rack erection workface",
                    cause=claim.causality,
                    effect="Late owner-furnished valves delayed workface release and drove resequencing on the piping path.",
                    schedule_impact_days=9,
                    cost_impact=185_000,
                    productivity_loss_percent=0,
                    evidence_ref="Schedule update / valve procurement correspondence / lookahead",
                    confidence_score=0.72,
                    status="reviewed",
                ),
                ClaimImpactAnalysis(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    claim_id=claim.id,
                    method="Measured Mile / Productivity",
                    impacted_activity="CA-PIPE-210 / Piping fabrication and erection",
                    cause="Restricted workface availability created crew stacking and non-productive movement.",
                    effect="Measured productivity loss is calculated from installed quantities and labor hours against the least impacted period.",
                    schedule_impact_days=0,
                    cost_impact=92_000,
                    productivity_loss_percent=14.5,
                    evidence_ref="Progress records / labor reports / daily field reports",
                    confidence_score=0.62,
                    status="draft",
                ),
            ]
        )
    db.commit()


def ensure_document_control_records(db: Session, tenant_id: int, project_id: int) -> None:
    inspector = inspect(db.get_bind())
    table_names = set(inspector.get_table_names())
    if "documents" not in table_names:
        return
    document_columns = {column["name"] for column in inspector.get_columns("documents")}
    if "document_number" not in document_columns:
        return

    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    if not project:
        return

    documents = list(
        db.scalars(
            select(Document)
            .where(Document.tenant_id == tenant_id, Document.project_id == project_id)
            .order_by(Document.id)
        ).all()
    )
    if not documents:
        control_account = db.scalar(
            select(ControlAccount)
            .where(ControlAccount.tenant_id == tenant_id, ControlAccount.project_id == project_id)
            .order_by(ControlAccount.code)
        )
        db.add(
            Document(
                tenant_id=tenant_id,
                project_id=project_id,
                linked_entity_type="ControlAccount",
                linked_entity_id=control_account.id if control_account else project_id,
                title="Controlled document register seed",
                doc_type="Document Register",
                uri=f"edms://documents/{project.code}/register",
            )
        )
        db.flush()
        documents = list(
            db.scalars(
                select(Document)
                .where(Document.tenant_id == tenant_id, Document.project_id == project_id)
                .order_by(Document.id)
            ).all()
        )

    for index, document in enumerate(documents, start=1):
        if not document.document_number:
            document.document_number = f"{project.code}-DOC-{index:04d}"
        document.revision = document.revision or "A"
        document.revision_date = document.revision_date or date(2026, 5, min(index + 1, 28))
        document.discipline = document.discipline or (
            "Contracts" if document.linked_entity_type in {"Claim", "Contract"} else "Project Controls"
        )
        document.organization = document.organization or (
            "EPC Contractor" if project.code == "CTRL-DEMO-001" else "Turnaround Team"
        )
        document.status = document.status or "current"
        document.review_status = document.review_status or ("approved" if index == 1 else "in_review")
        document.confidentiality = document.confidentiality or "project"
        document.file_name = document.file_name or f"{document.document_number}_REV_{document.revision}.pdf"

    db.flush()
    documents = list(
        db.scalars(
            select(Document)
            .where(Document.tenant_id == tenant_id, Document.project_id == project_id)
            .order_by(Document.id)
        ).all()
    )
    if not documents:
        db.commit()
        return

    transmittal = db.scalar(
        select(DocumentTransmittal).where(
            DocumentTransmittal.tenant_id == tenant_id,
            DocumentTransmittal.project_id == project_id,
            DocumentTransmittal.transmittal_no == f"{project.code}-TR-0001",
        )
    )
    if not transmittal:
        transmittal = DocumentTransmittal(
            tenant_id=tenant_id,
            project_id=project_id,
            transmittal_no=f"{project.code}-TR-0001",
            subject="Issue controlled pilot document package for review",
            purpose="for_review",
            recipient_org="Owner Project Controls" if project.code == "CTRL-DEMO-001" else "Operations Readiness",
            recipient_contact="Document Control",
            status="sent",
            sent_on=date(2026, 5, 3),
            due_date=date(2026, 5, 10),
            created_by="System seed",
        )
        db.add(transmittal)
        db.flush()
    existing_item_ids = set(
        db.scalars(
            select(DocumentTransmittalItem.document_id).where(
                DocumentTransmittalItem.tenant_id == tenant_id,
                DocumentTransmittalItem.project_id == project_id,
                DocumentTransmittalItem.transmittal_id == transmittal.id,
            )
        ).all()
    )
    for document in documents[:3]:
        if document.id not in existing_item_ids:
            db.add(
                DocumentTransmittalItem(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    transmittal_id=transmittal.id,
                    document_id=document.id,
                    document_number=document.document_number,
                    revision=document.revision,
                    action_required="review",
                    response_status="outstanding"
                    if document.review_status not in {"approved", "reviewed"}
                    else "closed",
                )
            )

    existing_review_ids = set(
        db.scalars(
            select(DocumentReview.document_id).where(
                DocumentReview.tenant_id == tenant_id,
                DocumentReview.project_id == project_id,
            )
        ).all()
    )
    for document in documents[:3]:
        if document.id not in existing_review_ids:
            status = "approved" if document.review_status in {"approved", "reviewed"} else "outstanding"
            db.add(
                DocumentReview(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    document_id=document.id,
                    reviewer_role="Project Controls"
                    if document.discipline == "Project Controls"
                    else "Contract Manager",
                    review_status=status,
                    comments="Pilot document control review seeded for Aconex-style workflow.",
                    due_date=date(2026, 5, 10),
                    closed_on=date(2026, 5, 6) if status == "approved" else None,
                )
            )

    existing_mail = db.scalar(
        select(ProjectMail).where(
            ProjectMail.tenant_id == tenant_id,
            ProjectMail.project_id == project_id,
            ProjectMail.mail_no == f"{project.code}-MAIL-0001",
        )
    )
    if not existing_mail:
        db.add(
            ProjectMail(
                tenant_id=tenant_id,
                project_id=project_id,
                mail_no=f"{project.code}-MAIL-0001",
                mail_type="document_review",
                subject="Please review controlled pilot document package",
                from_role="Document Controller",
                to_role="Project Controls",
                status="outstanding",
                response_required=True,
                sent_on=date(2026, 5, 3),
                due_date=date(2026, 5, 10),
                body="Review the issued document package and return comments through the controlled review workflow.",
                linked_entity_type="DocumentTransmittal",
                linked_entity_id=transmittal.id,
                document_id=documents[0].id,
            )
        )
    db.commit()


def ensure_claim_business_process(db: Session, tenant_id: int, project_id: int, claim: Claim) -> None:
    existing = db.scalar(
        select(BusinessProcessInstance).where(
            BusinessProcessInstance.tenant_id == tenant_id,
            BusinessProcessInstance.project_id == project_id,
            BusinessProcessInstance.trigger_entity_type == "Claim",
            BusinessProcessInstance.trigger_entity_id == claim.id,
        )
    )
    if existing:
        existing.title = f"Claim Event - {claim.title}"
        return
    process = BusinessProcessInstance(
        tenant_id=tenant_id,
        project_id=project_id,
        trigger_entity_type="Claim",
        trigger_entity_id=claim.id,
        process_code="CL-FORENSIC",
        process_name="Claim Event",
        record_no=f"CL-{claim.id:05d}",
        title=f"Claim Event - {claim.title}",
        status="in_review",
        current_step="Causation Review",
        ball_in_court="Claims Analyst",
    )
    db.add(process)
    db.flush()
    for order, (name, detail, owner_role, status, tone) in enumerate(
        [
            (
                "Event Capture",
                "Claim event, affected control account and evidence package are captured.",
                "Field Lead",
                "Complete",
                "complete",
            ),
            (
                "Notice Review",
                "Contract notice, timing and procedural compliance are checked.",
                "Contract Manager",
                "Active",
                "active",
            ),
            (
                "Causation Review",
                "Cause-and-effect analysis links event, schedule, productivity and cost impact.",
                "Claims Analyst",
                "Active",
                "active",
            ),
            (
                "Impact / Quantum Analysis",
                "Schedule impact, productivity loss and damages are quantified.",
                "Project Controls",
                "Pending",
                "pending",
            ),
            (
                "Entitlement Position",
                "Contract position and recovery strategy are approved.",
                "Control Manager",
                "Queued",
                "queued",
            ),
        ],
        start=1,
    ):
        db.add(
            WorkflowStepInstance(
                tenant_id=tenant_id,
                project_id=project_id,
                process_instance_id=process.id,
                step_order=order,
                name=name,
                detail=detail,
                owner_role=owner_role,
                status=status,
                tone=tone,
            )
        )


def ensure_control_history_records(db: Session, tenant_id: int, project_id: int) -> None:
    current = db.scalars(
        select(ControlSnapshot)
        .where(
            ControlSnapshot.tenant_id == tenant_id,
            ControlSnapshot.project_id == project_id,
            ControlSnapshot.control_account_id.is_(None),
        )
        .order_by(ControlSnapshot.period_label.desc())
    ).first()
    if not current:
        project_kpi = db.scalars(
            select(KPI)
            .where(KPI.tenant_id == tenant_id, KPI.project_id == project_id, KPI.control_account_id.is_(None))
            .order_by(KPI.created_at.desc())
        ).first()
        if not project_kpi:
            return
        current = ControlSnapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            control_account_id=None,
            period_label=project_kpi.period,
            data_date=None,
            pv=project_kpi.pv,
            ev=project_kpi.ev,
            ac=project_kpi.ac,
            spi=project_kpi.spi,
            cpi=project_kpi.cpi,
            sv=project_kpi.sv,
            cv=project_kpi.cv,
            bac=project_kpi.bac,
            eac=project_kpi.eac,
            etc=project_kpi.etc,
            vac=project_kpi.vac,
            productivity_index=None,
        )
        db.add(current)
        db.flush()

    existing_periods = set(
        db.scalars(
            select(ControlSnapshot.period_label).where(
                ControlSnapshot.tenant_id == tenant_id,
                ControlSnapshot.project_id == project_id,
                ControlSnapshot.control_account_id.is_(None),
            )
        ).all()
    )
    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    year = project.start_date.year if project and project.start_date else 2026
    curve_seed = [
        ("01", 0.16, 0.13, 0.14, 0.95),
        ("02", 0.30, 0.26, 0.29, 0.92),
        ("03", 0.49, 0.43, 0.51, 0.86),
        ("04", 0.72, 0.65, 0.77, 0.82),
    ]
    for month, pv_factor, ev_factor, ac_factor, productivity_index in curve_seed:
        period_label = f"{year}-{month}"
        if period_label in existing_periods:
            continue
        pv = current.bac * pv_factor
        ev = current.bac * ev_factor
        ac = current.bac * ac_factor
        spi = ev / pv if pv else 0
        cpi = ev / ac if ac else 0
        eac = current.bac / cpi if cpi else current.bac
        etc = max(eac - ac, 0)
        db.add(
            ControlSnapshot(
                tenant_id=tenant_id,
                project_id=project_id,
                control_account_id=None,
                period_label=period_label,
                data_date=date(year, int(month), 1),
                pv=round(pv, 2),
                ev=round(ev, 2),
                ac=round(ac, 2),
                spi=round(spi, 3),
                cpi=round(cpi, 3),
                sv=round(ev - pv, 2),
                cv=round(ev - ac, 2),
                bac=current.bac,
                eac=round(eac, 2),
                etc=round(etc, 2),
                vac=round(current.bac - eac, 2),
                productivity_index=productivity_index,
            )
        )

    forecast_exists = db.scalar(
        select(ForecastScenario).where(
            ForecastScenario.tenant_id == tenant_id,
            ForecastScenario.project_id == project_id,
            ForecastScenario.period_label == current.period_label,
        )
    )
    if forecast_exists:
        db.flush()
        return
    cpi = current.cpi if current.cpi > 0 else 1
    for name, method, cpi_factor, spi_factor in [
        ("Current Performance", "EAC = BAC / current CPI", cpi, current.spi if current.spi > 0 else 1),
        (
            "Recovery Plan",
            "Corrective action improves CPI and SPI",
            min(cpi + 0.10, 1.10),
            min((current.spi if current.spi > 0 else 1) + 0.08, 1.05),
        ),
        (
            "Pessimistic Drift",
            "Unresolved productivity and cost drift",
            max(cpi * 0.90, 0.10),
            max((current.spi if current.spi > 0 else 1) * 0.92, 0.10),
        ),
    ]:
        eac = current.bac / cpi_factor if cpi_factor else current.bac
        etc = max(eac - current.ac, 0)
        vac = current.bac - eac
        risk = (
            "high" if cpi_factor < 0.9 or spi_factor < 0.9 else "medium" if cpi_factor < 1 or spi_factor < 1 else "low"
        )
        db.add(
            ForecastScenario(
                tenant_id=tenant_id,
                project_id=project_id,
                period_label=current.period_label,
                name=name,
                method=method,
                cpi_factor=round(cpi_factor, 3),
                spi_factor=round(spi_factor, 3),
                eac=round(eac, 2),
                etc=round(etc, 2),
                vac=round(vac, 2),
                completion_risk=risk,
                summary=f"{name}: EAC {round(eac, 2)}, VAC {round(vac, 2)}, risk {risk}.",
            )
        )
    db.flush()


def ensure_control_account_mapping_records(db: Session, tenant_id: int, project_id: int) -> None:
    schedule_import = db.scalars(
        select(ScheduleImport)
        .where(ScheduleImport.tenant_id == tenant_id, ScheduleImport.project_id == project_id)
        .order_by(ScheduleImport.imported_at.desc(), ScheduleImport.id.desc())
    ).first()
    if not schedule_import:
        return
    schedule_rows = list(
        db.scalars(
            select(ScheduleActivityMap)
            .where(
                ScheduleActivityMap.tenant_id == tenant_id,
                ScheduleActivityMap.project_id == project_id,
                ScheduleActivityMap.schedule_import_id == schedule_import.id,
            )
            .order_by(ScheduleActivityMap.external_activity_id)
        ).all()
    )
    if not schedule_rows:
        return

    activity_ids = [row.activity_id for row in schedule_rows if row.activity_id]
    activities = {
        activity.id: activity
        for activity in db.scalars(
            select(Activity).where(
                Activity.tenant_id == tenant_id,
                Activity.project_id == project_id,
                Activity.id.in_(activity_ids) if activity_ids else False,
            )
        ).all()
    }
    activities_by_code = {
        activity.code: activity
        for activity in db.scalars(
            select(Activity).where(Activity.tenant_id == tenant_id, Activity.project_id == project_id)
        ).all()
    }
    wbs_cache: dict[str, WBS] = {
        wbs.code: wbs
        for wbs in db.scalars(select(WBS).where(WBS.tenant_id == tenant_id, WBS.project_id == project_id)).all()
    }
    account_cache: dict[str, ControlAccount] = {
        account.code: account
        for account in db.scalars(
            select(ControlAccount).where(ControlAccount.tenant_id == tenant_id, ControlAccount.project_id == project_id)
        ).all()
    }
    for row in schedule_rows:
        if row.activity_id and row.activity_id in activities:
            continue
        activity = activities_by_code.get(row.external_activity_id)
        if not activity:
            wbs_code = row.wbs_code or "UNMAPPED"
            wbs = wbs_cache.get(wbs_code)
            if not wbs:
                wbs = WBS(
                    tenant_id=tenant_id, project_id=project_id, parent_id=None, code=wbs_code, name=f"WBS {wbs_code}"
                )
                db.add(wbs)
                db.flush()
                wbs_cache[wbs_code] = wbs
            account_code = f"CA-{wbs_code}"[:80]
            account = account_cache.get(account_code)
            if not account:
                account = ControlAccount(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    wbs_id=wbs.id,
                    code=account_code,
                    name=f"Control Account {wbs_code}",
                    responsible="Project Controls",
                    discipline="Imported Schedule",
                )
                db.add(account)
                db.flush()
                account_cache[account_code] = account
            activity = Activity(
                tenant_id=tenant_id,
                project_id=project_id,
                control_account_id=account.id,
                code=row.external_activity_id,
                name=row.activity_name,
                logic_type="FS",
                baseline_start=row.planned_start,
                baseline_finish=row.planned_finish,
                planned_percent=0,
                critical_path=row.critical_path,
                lookahead_window="6W",
            )
            db.add(activity)
            db.flush()
            activities_by_code[activity.code] = activity
        row.activity_id = activity.id
        activities[activity.id] = activity

    account_ids = {activity.control_account_id for activity in activities.values()}
    budgets_by_account: dict[int, Budget] = {
        budget.control_account_id: budget
        for budget in db.scalars(
            select(Budget).where(
                Budget.tenant_id == tenant_id,
                Budget.project_id == project_id,
                Budget.control_account_id.in_(account_ids) if account_ids else False,
            )
        ).all()
    }
    activity_count_by_account: dict[int, int] = {}
    for activity in activities.values():
        activity_count_by_account[activity.control_account_id] = (
            activity_count_by_account.get(activity.control_account_id, 0) + 1
        )

    for row in schedule_rows:
        existing = db.scalar(
            select(ControlAccountMapping).where(
                ControlAccountMapping.tenant_id == tenant_id,
                ControlAccountMapping.project_id == project_id,
                ControlAccountMapping.schedule_activity_map_id == row.id,
            )
        )
        activity = activities.get(row.activity_id or 0)
        if not activity:
            continue
        budget = budgets_by_account.get(activity.control_account_id)
        allocated_cost = (
            (budget.bac / max(activity_count_by_account.get(activity.control_account_id, 1), 1)) if budget else 0
        )
        planned_value = allocated_cost * activity.planned_percent / 100
        mapping = existing or ControlAccountMapping(
            tenant_id=tenant_id,
            project_id=project_id,
            schedule_import_id=schedule_import.id,
            schedule_activity_map_id=row.id,
        )
        mapping.activity_id = activity.id
        mapping.control_account_id = activity.control_account_id
        mapping.wbs_code = row.wbs_code or "UNMAPPED"
        mapping.wbs_name = f"WBS {row.wbs_code or 'UNMAPPED'}"
        mapping.cbs_code = budget.cbs_code if budget else f"CBS-{row.wbs_code or activity.code}"
        mapping.mapping_rule = "Existing Activity -> Control Account -> CBS"
        mapping.planned_cost = allocated_cost
        mapping.planned_value = planned_value
        mapping.planned_percent = activity.planned_percent
        mapping.status = "mapped" if allocated_cost > 0 else "needs_cost_loading"
        mapping.review_note = (
            "" if allocated_cost > 0 else "Activity mapped, but no loaded budget was found for the control account."
        )
        if not existing:
            db.add(mapping)
    db.flush()


def ensure_schedule_quality_artifacts(
    db: Session,
    tenant_id: int,
    project_id: int,
    schedule_import: ScheduleImport,
) -> None:
    existing_baseline = db.scalar(
        select(BaselineVersion).where(
            BaselineVersion.tenant_id == tenant_id,
            BaselineVersion.project_id == project_id,
            BaselineVersion.schedule_import_id == schedule_import.id,
        )
    )
    if not existing_baseline:
        version_no = (
            db.scalar(
                select(BaselineVersion.version_no)
                .where(BaselineVersion.tenant_id == tenant_id, BaselineVersion.project_id == project_id)
                .order_by(BaselineVersion.version_no.desc())
            )
            or 0
        ) + 1
        db.add(
            BaselineVersion(
                tenant_id=tenant_id,
                project_id=project_id,
                schedule_import_id=schedule_import.id,
                version_no=version_no,
                name=schedule_import.baseline_name,
                status="in_review" if schedule_import.status == ImportStatus.validated else "rejected",
                data_date=schedule_import.data_date,
                quality_score=schedule_import.quality_score,
            )
        )
        db.flush()

    if schedule_import.data_date:
        period_label = schedule_import.data_date.strftime("%Y-%m")
        existing_period = db.scalar(
            select(ControlPeriod).where(
                ControlPeriod.tenant_id == tenant_id,
                ControlPeriod.project_id == project_id,
                ControlPeriod.period_label == period_label,
            )
        )
        if not existing_period:
            db.add(
                ControlPeriod(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    period_label=period_label,
                    data_date=schedule_import.data_date,
                    status="open",
                )
            )
            db.flush()

    existing_finding = db.scalar(
        select(ScheduleValidationFinding).where(
            ScheduleValidationFinding.tenant_id == tenant_id,
            ScheduleValidationFinding.project_id == project_id,
            ScheduleValidationFinding.schedule_import_id == schedule_import.id,
        )
    )
    if not existing_finding:
        db.add(
            ScheduleValidationFinding(
                tenant_id=tenant_id,
                project_id=project_id,
                schedule_import_id=schedule_import.id,
                check_code="SEEDED_BASELINE",
                severity="info",
                message=schedule_import.validation_summary,
                item_count=0,
                weight=0,
            )
        )
        db.flush()


def ensure_demo_schedule(db: Session, tenant_id: int, project_id: int) -> None:
    existing_imports = list(
        db.scalars(
            select(ScheduleImport).where(ScheduleImport.tenant_id == tenant_id, ScheduleImport.project_id == project_id)
        ).all()
    )
    if existing_imports:
        created_process = False
        for existing_import in existing_imports:
            ensure_schedule_quality_artifacts(db, tenant_id, project_id, existing_import)
            existing_process = db.scalar(
                select(BusinessProcessInstance).where(
                    BusinessProcessInstance.tenant_id == tenant_id,
                    BusinessProcessInstance.project_id == project_id,
                    BusinessProcessInstance.trigger_entity_type == "ScheduleImport",
                    BusinessProcessInstance.trigger_entity_id == existing_import.id,
                )
            )
            if not existing_process:
                ScheduleIngestionService(db).start_schedule_workflow(tenant_id, project_id, existing_import)
                created_process = True
        if created_process:
            db.commit()
        return

    accounts = list(
        db.scalars(
            select(ControlAccount)
            .where(ControlAccount.tenant_id == tenant_id, ControlAccount.project_id == project_id)
            .order_by(ControlAccount.id)
        ).all()
    )
    if not accounts:
        return
    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    is_turnaround = project.code == "REF-TURN-002" if project else False

    schedule_import = ScheduleImport(
        tenant_id=tenant_id,
        project_id=project_id,
        source=ScheduleSource.p6_xer,
        file_name="REF_TURNAROUND_BASELINE.xer" if is_turnaround else "CONTROL_BASELINE_DEMO.xer",
        status=ImportStatus.validated,
        data_date=date(2026, 5, 1),
        baseline_name="TA-01 Approved Turnaround Baseline" if is_turnaround else "BL-01 Approved Control Baseline",
        quality_score=94,
        validation_summary=f"{len(accounts)} control activities, {max(len(accounts) - 1, 0)} FS relationships, data date verified, all activities mapped to control accounts.",
    )
    db.add(schedule_import)
    db.flush()
    ensure_schedule_quality_artifacts(db, tenant_id, project_id, schedule_import)
    ScheduleIngestionService(db).start_schedule_workflow(tenant_id, project_id, schedule_import)

    activity_rows = (
        [
            (
                accounts[0],
                "P6-UTIL-1200",
                "Execute steam and condensate tie-ins",
                date(2026, 3, 9),
                date(2026, 6, 26),
                2,
                False,
            ),
            (
                accounts[1],
                "P6-INST-2200",
                "Complete instrumentation loop checks",
                date(2026, 5, 11),
                date(2026, 8, 21),
                0,
                True,
            ),
        ]
        if is_turnaround and len(accounts) >= 2
        else [
            (
                accounts[0],
                "P6-MECH-1000",
                "Install compressor mechanical package",
                date(2026, 3, 2),
                date(2026, 7, 17),
                0,
                True,
            ),
            (
                accounts[1],
                "P6-PIPE-2100",
                "Fabricate and erect process piping",
                date(2026, 2, 9),
                date(2026, 8, 28),
                4,
                False,
            ),
            (
                accounts[2],
                "P6-ELEC-3100",
                "Electrical hook-up and precommissioning",
                date(2026, 6, 8),
                date(2026, 10, 9),
                0,
                True,
            ),
        ]
        if len(accounts) >= 3
        else [
            (accounts[0], "P6-CTRL-1000", accounts[0].name, date(2026, 3, 2), date(2026, 7, 17), 0, True),
        ]
    )

    for account, code, name, start, finish, total_float, critical in activity_rows:
        activity = Activity(
            tenant_id=tenant_id,
            project_id=project_id,
            control_account_id=account.id,
            code=code,
            name=name,
            logic_type="FS",
            baseline_start=start,
            baseline_finish=finish,
            planned_percent=70 if critical else 64,
            critical_path=critical,
            lookahead_window="6W",
        )
        db.add(activity)
        db.flush()
        db.add(
            ScheduleActivityMap(
                tenant_id=tenant_id,
                project_id=project_id,
                schedule_import_id=schedule_import.id,
                activity_id=activity.id,
                external_activity_id=code,
                wbs_code="1.2",
                activity_name=name,
                planned_start=start,
                planned_finish=finish,
                total_float_days=total_float,
                critical_path=critical,
            )
        )

    db.add_all(
        [
            ActivityRelationship(
                tenant_id=tenant_id,
                project_id=project_id,
                schedule_import_id=schedule_import.id,
                predecessor_external_id=activity_rows[index][1],
                successor_external_id=activity_rows[index + 1][1],
                relationship_type=RelationshipType.fs,
                lag_days=0 if index == 0 else 2,
            )
            for index in range(len(activity_rows) - 1)
        ]
        + [
            Resource(
                tenant_id=tenant_id,
                project_id=project_id,
                code="CREW-TURNAROUND-A" if is_turnaround else "CREW-PIPING-A",
                name="Turnaround execution crew A" if is_turnaround else "Piping erection crew A",
                resource_type="labor",
                unit_of_measure="hr",
            ),
        ]
    )
    db.commit()
