from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import (
    WBS,
    ActivitySheet,
    BaselineVersion,
    BusinessProcessInstance,
    BusinessProcessPolicy,
    ControlAccount,
    ControlAccountMapping,
    CostBreakdownStructure,
    CostCode,
    Document,
    FundingSource,
    Project,
    ProjectMembership,
    ProjectOperationalSetup,
    QuantityTakeoffLine,
    QuantityTakeoffRun,
    ScheduleImport,
    WorkPackage,
    WorkPackageConstraint,
)
from app.domain.schemas import ProcessFlowBoardOut, ProcessFlowItemOut, ProcessFlowLaneOut

STATUS_SCORE = {
    "complete": 1.0,
    "ready": 0.75,
    "review_required": 0.45,
    "blocked": 0.0,
}


class ProcessFlowBoardService:
    """Builds a production BPM board from the current project control evidence."""

    def __init__(self, db: Session):
        self.db = db

    def build(self, tenant_id: int, project_id: int) -> ProcessFlowBoardOut:
        project = self.db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
        if not project:
            raise ValueError("Project not found")

        setup = self.db.scalar(
            select(ProjectOperationalSetup).where(
                ProjectOperationalSetup.tenant_id == tenant_id,
                ProjectOperationalSetup.project_id == project_id,
            )
        )
        latest_import = self.db.scalar(
            select(ScheduleImport)
            .where(ScheduleImport.tenant_id == tenant_id, ScheduleImport.project_id == project_id)
            .order_by(ScheduleImport.imported_at.desc())
        )
        counts = {
            "activity_sheets": self._count(ActivitySheet, tenant_id, project_id),
            "baselines": self._count(BaselineVersion, tenant_id, project_id),
            "business_processes": self._count(BusinessProcessInstance, tenant_id, project_id),
            "control_accounts": self._count(ControlAccount, tenant_id, project_id),
            "cost_codes": self._count(CostCode, tenant_id, project_id),
            "cbs": self._count(CostBreakdownStructure, tenant_id, project_id),
            "documents": self._count(Document, tenant_id, project_id),
            "funding": self._count(FundingSource, tenant_id, project_id),
            "mappings": self._count(ControlAccountMapping, tenant_id, project_id),
            "memberships": self._count(ProjectMembership, tenant_id, project_id),
            "policies": self._count(BusinessProcessPolicy, tenant_id, project_id),
            "packages": self._count(WorkPackage, tenant_id, project_id),
            "quantity_lines": self._count(QuantityTakeoffLine, tenant_id, project_id),
            "quantity_runs": self._count(QuantityTakeoffRun, tenant_id, project_id),
            "wbs": self._count(WBS, tenant_id, project_id),
        }
        quantity_mapped = self._quantity_line_count(tenant_id, project_id, "mapped")
        quantity_review = counts["quantity_lines"] - quantity_mapped
        blocking_constraints = self._blocking_constraints(tenant_id, project_id)

        lanes = [
            ProcessFlowLaneOut(
                key="owner",
                label="Owner / Direction",
                owner_role="Owner / Control Manager",
                items=[
                    self._project_authorization(project),
                    self._funding_authority(counts["funding"]),
                ],
            ),
            ProcessFlowLaneOut(
                key="project_controls",
                label="Project Controls",
                owner_role="Control Manager",
                items=[
                    self._operational_setup(setup),
                    self._role_matrix(counts["memberships"], counts["policies"]),
                    self._baseline_approval(counts["baselines"], latest_import, counts["mappings"]),
                ],
            ),
            ProcessFlowLaneOut(
                key="planning",
                label="Planning / P6",
                owner_role="Planner",
                items=[
                    self._activity_sheet(counts["activity_sheets"], latest_import),
                    self._wbs_sheet(counts["wbs"], counts["activity_sheets"]),
                    self._schedule_quality(latest_import),
                ],
            ),
            ProcessFlowLaneOut(
                key="cost_funding",
                label="Cost / Funding",
                owner_role="Cost Controller",
                items=[
                    self._fbs_funding(counts["funding"]),
                    self._cbs_cost_codes(counts["cbs"], counts["cost_codes"], counts["mappings"]),
                    self._business_process_governance(counts["business_processes"], counts["policies"]),
                ],
            ),
            ProcessFlowLaneOut(
                key="awp_construction",
                label="AWP / Construction",
                owner_role="Workface Planner",
                items=[
                    self._bim_quantity_takeoff(
                        counts["quantity_runs"],
                        counts["quantity_lines"],
                        quantity_mapped,
                        quantity_review,
                    ),
                    self._awp_packages(counts["packages"], blocking_constraints),
                    self._constraints(counts["packages"], blocking_constraints),
                    self._field_evidence(counts["documents"]),
                ],
            ),
        ]
        items = [item for lane in lanes for item in lane.items]
        completion_percent = round(sum(STATUS_SCORE[item.status] for item in items) / len(items) * 100, 1)
        if any(item.status == "blocked" for item in items):
            overall_status = "blocked"
        elif all(item.status == "complete" for item in items):
            overall_status = "complete"
        elif any(item.status == "review_required" for item in items):
            overall_status = "review_required"
        else:
            overall_status = "ready"
        return ProcessFlowBoardOut(
            project_id=project_id,
            overall_status=overall_status,
            completion_percent=completion_percent,
            lanes=lanes,
        )

    def _project_authorization(self, project: Project) -> ProcessFlowItemOut:
        authorized = project.status in {"authorized", "baseline_approved", "active"} and bool(project.authorization_ref)
        return self._item(
            key="project_authorization",
            label="Project authorization",
            status="complete" if authorized else "blocked",
            owner_role="Owner / Direction",
            evidence=f"{project.status}; authorization reference {project.authorization_ref or 'missing'}.",
            next_action="Capture project authorization reference" if not authorized else "Maintain approval evidence",
            acceptance_criteria=[
                "Project code, sponsor, phase, currency and authorization reference are approved.",
                "The project exists before Activity Sheet, WBS Sheet, Cost Sheet or Funding Sheet operations.",
            ],
            target_view="setup",
        )

    def _funding_authority(self, funding_count: int) -> ProcessFlowItemOut:
        return self._item(
            key="funding_authority",
            label="Funding authority",
            status="complete" if funding_count else "blocked",
            owner_role="Owner / Funding",
            evidence=f"{funding_count} approved or planned funding source(s).",
            next_action="Create FBS / funding codes" if not funding_count else "Monitor funding availability",
            acceptance_criteria=[
                "Funding source, authorization, restrictions, currency and availability are recorded.",
                "Funding is traceable to WBS, control account, CBS, commitment and forecast.",
            ],
            target_view="costs",
        )

    def _operational_setup(self, setup: ProjectOperationalSetup | None) -> ProcessFlowItemOut:
        ready = bool(setup and setup.readiness_status == "ready")
        notes = setup.readiness_notes if setup else "Operational setup is missing."
        return self._item(
            key="operational_setup",
            label="Operational setup",
            status="complete" if ready else "blocked",
            owner_role="Control Manager",
            evidence=notes or "Ready for controlled data loading.",
            next_action="Complete permissions, modules, Cost Sheet, Funding Sheet and P6 mapping"
            if not ready
            else "Keep setup under governance",
            acceptance_criteria=[
                "Project number, template, attribute form, permissions and modules are configured.",
                "Cost Sheet, Funding Sheet and P6 mapping are ready before Get Data.",
            ],
            target_view="setup",
        )

    def _role_matrix(self, membership_count: int, policy_count: int) -> ProcessFlowItemOut:
        status = "complete" if membership_count > 1 and policy_count else "review_required"
        return self._item(
            key="role_matrix",
            label="Role matrix and approvals",
            status=status,
            owner_role="Control Manager",
            evidence=f"{membership_count} project member(s); {policy_count} BP approval policie(s).",
            next_action="Load client role matrix and BP approval policies"
            if status != "complete"
            else "Review role matrix periodically",
            acceptance_criteria=[
                "Client role matrix is configured for Planning, Controls, Cost/Funding, AWP, Contracts and Document Control.",
                "BP actions have required role and permission policies before production approval.",
            ],
            target_view="admin",
        )

    def _baseline_approval(
        self,
        baseline_count: int,
        latest_import: ScheduleImport | None,
        mapping_count: int,
    ) -> ProcessFlowItemOut:
        cost_ready = bool(
            latest_import
            and latest_import.currency_confirmed
            and latest_import.cost_loaded_activity_count > 0
            and latest_import.total_imported_cost > 0
        )
        if baseline_count and mapping_count and cost_ready:
            status = "complete"
        elif latest_import and mapping_count:
            status = "review_required"
        else:
            status = "blocked"
        return self._item(
            key="baseline_approval",
            label="Integrated baseline approval",
            status=status,
            owner_role="Control Manager",
            evidence=f"{baseline_count} baseline version(s); {mapping_count} WBS/CBS/control account mapping(s).",
            next_action="Confirm cost loading, currency and mappings before approval"
            if status != "complete"
            else "Control approved baseline changes",
            acceptance_criteria=[
                "All schedule activities are mapped before baseline approval.",
                "Cost loading and currency confirmation are complete before approving the baseline.",
            ],
            target_view="baseline",
        )

    def _activity_sheet(self, sheet_count: int, latest_import: ScheduleImport | None) -> ProcessFlowItemOut:
        return self._item(
            key="activity_sheet",
            label="System Activity Sheet",
            status="complete" if sheet_count and latest_import else "blocked",
            owner_role="Planner",
            evidence=f"{sheet_count} activity sheet(s); latest import {latest_import.file_name if latest_import else 'missing'}.",
            next_action="Run Get Data with XML/XER schedule" if not sheet_count else "Review Activity Sheet rows",
            acceptance_criteria=[
                "Activity Sheet is created from the controlled P6 XML/XER source.",
                "Activities include WBS, dates, data date, costs, resource assignments and stable activity IDs.",
            ],
            target_view="setup",
        )

    def _wbs_sheet(self, wbs_count: int, sheet_count: int) -> ProcessFlowItemOut:
        has_imported_wbs = wbs_count > 1 and sheet_count > 0
        return self._item(
            key="wbs_sheet",
            label="WBS Sheet roll-up",
            status="complete" if has_imported_wbs else "blocked",
            owner_role="Planner",
            evidence=f"{wbs_count} WBS node(s) available.",
            next_action="Load Activity Sheet to generate WBS roll-up"
            if not has_imported_wbs
            else "Validate WBS values and review counts",
            acceptance_criteria=[
                "WBS Sheet reflects hierarchy, activity count, planned cost and planned value.",
                "WBS does not replace CBS; it remains the approved scope structure.",
            ],
            target_view="setup",
        )

    def _schedule_quality(self, latest_import: ScheduleImport | None) -> ProcessFlowItemOut:
        if not latest_import:
            status = "blocked"
            evidence = "No schedule import found."
        elif latest_import.quality_score >= 70:
            status = "complete"
            evidence = f"Quality score {latest_import.quality_score:.1f}; {latest_import.validation_summary}"
        else:
            status = "review_required"
            evidence = f"Quality score {latest_import.quality_score:.1f}; schedule requires correction."
        return self._item(
            key="schedule_quality",
            label="Schedule quality gate",
            status=status,
            owner_role="Project Controls",
            evidence=evidence,
            next_action="Resolve schedule quality findings" if status != "complete" else "Route baseline for approval",
            acceptance_criteria=[
                "Schedule quality gate checks open starts/finishes, leads/lags, missing dates and cost loading.",
                "Rejected or low-quality schedules do not become the control baseline.",
            ],
            target_view="baseline",
        )

    def _fbs_funding(self, funding_count: int) -> ProcessFlowItemOut:
        return self._item(
            key="fbs_funding",
            label="FBS / Funding codes",
            status="complete" if funding_count else "blocked",
            owner_role="Cost / Funding",
            evidence=f"{funding_count} funding code(s) configured.",
            next_action="Create funding codes with authorization and restrictions"
            if not funding_count
            else "Monitor available funds",
            acceptance_criteria=[
                "Each fund has source, type, authorization, restrictions, approved amount, currency and status.",
                "Funds can be assigned to control accounts, commitments, costs and forecast.",
            ],
            target_view="costs",
        )

    def _cbs_cost_codes(self, cbs_count: int, cost_code_count: int, mapping_count: int) -> ProcessFlowItemOut:
        if cbs_count and cost_code_count:
            status = "complete"
        elif cbs_count or mapping_count:
            status = "review_required"
        else:
            status = "blocked"
        return self._item(
            key="cbs_cost_codes",
            label="CBS and cost codes",
            status=status,
            owner_role="Cost Controller",
            evidence=f"{cbs_count} CBS code(s); {cost_code_count} integrated cost code(s); {mapping_count} mapping(s).",
            next_action="Create CBS and approved cost codes"
            if status == "blocked"
            else "Complete cost-code approval and reconciliation",
            acceptance_criteria=[
                "CBS classifies cost nature and does not replace WBS or FBS.",
                "Cost codes connect WBS, control account, CBS, FBS, contract and package evidence.",
            ],
            target_view="integrated-control",
        )

    def _business_process_governance(self, process_count: int, policy_count: int) -> ProcessFlowItemOut:
        if process_count and policy_count:
            status = "complete"
        elif process_count or policy_count:
            status = "review_required"
        else:
            status = "blocked"
        return self._item(
            key="bp_governance",
            label="BP governance",
            status=status,
            owner_role="Project Controls",
            evidence=f"{process_count} BP record(s); {policy_count} approval policie(s).",
            next_action="Configure BP policies and create CBS/FBS/WBS transactions"
            if status != "complete"
            else "Control line-item versions and approvals",
            acceptance_criteria=[
                "BP CBS+Fund and BP CBS+WBS enforce funding availability and approval policies.",
                "Line items maintain version history for edits, approvals and audit.",
            ],
            target_view="integrated-control",
        )

    def _awp_packages(self, package_count: int, blocking_constraints: int) -> ProcessFlowItemOut:
        if package_count and blocking_constraints == 0:
            status = "complete"
        elif package_count:
            status = "review_required"
        else:
            status = "blocked"
        return self._item(
            key="awp_packages",
            label="AWP package chain",
            status=status,
            owner_role="Workface Planner",
            evidence=f"{package_count} package(s); {blocking_constraints} blocking constraint(s).",
            next_action="Create CWA/CWP/EWP/PWP/IWP/TWP/TOP package drafts"
            if not package_count
            else "Resolve blocking package constraints",
            acceptance_criteria=[
                "Packages are tied to WBS, control account, path of construction and responsible owner.",
                "IWP release depends on critical constraints and funding readiness when applicable.",
            ],
            target_view="work-packages",
        )

    def _bim_quantity_takeoff(
        self,
        run_count: int,
        line_count: int,
        mapped_count: int,
        review_count: int,
    ) -> ProcessFlowItemOut:
        if run_count and line_count and review_count == 0:
            status = "complete"
        elif run_count and line_count:
            status = "review_required"
        else:
            status = "blocked"
        return self._item(
            key="bim_quantity_takeoff",
            label="BIM quantity takeoff",
            status=status,
            owner_role="BIM / Workface Planner",
            evidence=(f"{run_count} run(s); {line_count} line(s); {mapped_count} mapped; {review_count} need mapping."),
            next_action=(
                "Load BIM/IFC or Excel quantities"
                if not run_count
                else "Review unmapped BIM/IFC or Excel quantity lines before package release"
            ),
            acceptance_criteria=[
                "Controlled physical quantity items are consolidated from BIM/IFC or Excel before package release.",
                "Each quantity line keeps element GUID, IFC class, spatial/system context, unit, quantity and WBS/CBS/FBS/package mapping.",
                "Unmapped quantity lines stay in review before CWP/IWP release.",
            ],
            target_view="quantity-takeoff",
        )

    def _constraints(self, package_count: int, blocking_constraints: int) -> ProcessFlowItemOut:
        if package_count and blocking_constraints == 0:
            status = "complete"
        elif package_count:
            status = "review_required"
        else:
            status = "blocked"
        return self._item(
            key="constraints",
            label="Constraint management",
            status=status,
            owner_role="Workface Planner",
            evidence=f"{blocking_constraints} open blocking constraint(s).",
            next_action="Capture, assign and close package constraints"
            if status != "complete"
            else "Maintain constraint closure evidence",
            acceptance_criteria=[
                "Restrictions have owner, required date, priority, evidence and closure note.",
                "Blocked packages cannot be treated as ready for release.",
            ],
            target_view="work-packages",
        )

    def _field_evidence(self, document_count: int) -> ProcessFlowItemOut:
        return self._item(
            key="field_evidence",
            label="Evidence and closeout",
            status="complete" if document_count else "review_required",
            owner_role="Document Controller",
            evidence=f"{document_count} controlled document(s).",
            next_action="Attach evidence to schedule, cost, package and BP records"
            if not document_count
            else "Review evidence traceability",
            acceptance_criteria=[
                "Evidence supports approvals, changes, constraints, claims, payment and closeout.",
                "Closeout retains audit trail by project, WBS, control account, package and funding source.",
            ],
            target_view="evidence",
        )

    def _item(
        self,
        *,
        key: str,
        label: str,
        status: str,
        owner_role: str,
        evidence: str,
        next_action: str,
        acceptance_criteria: list[str],
        target_view: str,
    ) -> ProcessFlowItemOut:
        return ProcessFlowItemOut(
            key=key,
            label=label,
            status=status,
            owner_role=owner_role,
            evidence=evidence,
            next_action=next_action,
            acceptance_criteria=acceptance_criteria,
            target_view=target_view,
        )

    def _count(self, model: type, tenant_id: int, project_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(model)
                .where(model.tenant_id == tenant_id, model.project_id == project_id)
            )
            or 0
        )

    def _blocking_constraints(self, tenant_id: int, project_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(WorkPackageConstraint)
                .where(
                    WorkPackageConstraint.tenant_id == tenant_id,
                    WorkPackageConstraint.project_id == project_id,
                    WorkPackageConstraint.status == "open",
                    WorkPackageConstraint.blocking.is_(True),
                )
            )
            or 0
        )

    def _quantity_line_count(self, tenant_id: int, project_id: int, mapping_status: str) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(QuantityTakeoffLine)
                .where(
                    QuantityTakeoffLine.tenant_id == tenant_id,
                    QuantityTakeoffLine.project_id == project_id,
                    QuantityTakeoffLine.mapping_status == mapping_status,
                )
            )
            or 0
        )
