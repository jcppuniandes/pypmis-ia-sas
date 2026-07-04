from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import (
    BaselineVersion,
    BusinessProcessInstance,
    ControlAccount,
    ControlAccountMapping,
    CostRecord,
    Document,
    FundingSource,
    ProgressRecord,
    Project,
    ProjectOperationalSetup,
    ScheduleActivityMap,
    ScheduleImport,
    Tenant,
    WBS,
    WorkPackage,
    WorkPackageConstraint,
)
from app.domain.schemas import (
    CostCurrencyGateOut,
    GuidedFlowOut,
    GuidedFlowStepOut,
    GuidedNextActionOut,
    GuidedProjectContextOut,
    TenantContextOut,
)


class GuidedFlowService:
    def __init__(self, db: Session):
        self.db = db

    def build(self, tenant_id: int, project_id: int) -> GuidedFlowOut:
        tenant = self.db.scalar(select(Tenant).where(Tenant.id == tenant_id))
        project = self.db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
        if not tenant or not project:
            raise ValueError("Project not found")

        latest_import = self._latest_import(tenant_id, project_id)
        activity_count = self._schedule_import_activity_count(tenant_id, project_id, latest_import)
        baseline_count = self._count(BaselineVersion, tenant_id, project_id)
        mapping_count = self._count(ControlAccountMapping, tenant_id, project_id)
        account_count = self._count(ControlAccount, tenant_id, project_id)
        wbs_count = self._count(WBS, tenant_id, project_id)
        funding_count = self._count(FundingSource, tenant_id, project_id)
        progress_count = self._count(ProgressRecord, tenant_id, project_id)
        cost_count = self._count(CostRecord, tenant_id, project_id)
        process_count = self._count(BusinessProcessInstance, tenant_id, project_id)
        package_count = self._count(WorkPackage, tenant_id, project_id)
        document_count = self._count(Document, tenant_id, project_id)
        blocking_constraints = self._blocking_constraints(tenant_id, project_id)
        setup = self.db.scalar(
            select(ProjectOperationalSetup).where(
                ProjectOperationalSetup.tenant_id == tenant_id,
                ProjectOperationalSetup.project_id == project_id,
            )
        )
        setup_ready = bool(setup and setup.readiness_status == "ready")
        cost_gate = self._cost_gate(project_id, latest_import, activity_count)
        cost_ready = cost_gate.state == "ready"

        steps = [
            self._step(
                "project_setup",
                "Project setup",
                "complete" if setup_ready else "blocked",
                "Operational setup ready" if setup_ready else "Complete permissions, modules, cost sheet, funding sheet and P6 mapping",
                "Complete setup" if not setup_ready else "Load XER/XML schedule",
                "Control Manager",
                "setup",
                0 if setup_ready else 1,
            ),
            self._step(
                "schedule",
                "Schedule intake",
                "complete" if latest_import else "blocked",
                f"{activity_count} activities imported" if latest_import else "No XER/XML schedule loaded",
                "Review cost and currency gate" if latest_import else "Load XER/XML schedule",
                "Planner",
                "schedule-intake",
                0 if latest_import else 1,
            ),
            self._step(
                "cost_currency",
                "Cost and currency gate",
                "complete" if cost_ready else "blocked",
                cost_gate.message,
                "Approve baseline" if cost_ready else "Confirm currency and cost loading",
                "Project Controls",
                "baseline",
                0 if cost_ready else 1,
            ),
            self._step(
                "mapping",
                "WBS/CBS/FBS mapping",
                "complete" if mapping_count and account_count and wbs_count and funding_count else "review_required",
                f"{mapping_count} mappings / {account_count} control accounts / {funding_count} funding sources",
                "Complete WBS-CBS-FBS mapping",
                "Project Controls",
                "integrated-control",
                0 if mapping_count and account_count and wbs_count and funding_count else 1,
            ),
            self._step(
                "baseline",
                "Baseline approval",
                "ready" if baseline_count and cost_ready else "blocked",
                f"{baseline_count} baseline version(s)",
                "Approve baseline" if baseline_count and cost_ready else "Resolve baseline blockers",
                "Control Manager",
                "baseline",
                0 if baseline_count and cost_ready else 1,
            ),
            self._step(
                "progress",
                "Progress and cost capture",
                "complete" if progress_count and cost_count else "review_required",
                f"{progress_count} progress records / {cost_count} cost records",
                "Capture progress and actual costs",
                "Field Engineer",
                "progress",
                0 if progress_count and cost_count else 1,
            ),
            self._step(
                "control_core",
                "Integrated Control",
                "complete" if process_count else "review_required",
                f"{process_count} business process records",
                "Review Control Core exceptions",
                "Project Controls",
                "integrated-control",
            ),
            self._step(
                "awp",
                "Work Packages",
                "complete" if package_count and not blocking_constraints else "review_required",
                f"{package_count} packages / {blocking_constraints} blocking constraints",
                "Create draft AWP packages" if not package_count else "Resolve AWP constraints",
                "Workface Planner",
                "work-packages",
                blocking_constraints if package_count else 1,
            ),
            self._step(
                "evidence",
                "Evidence and closeout",
                "complete" if document_count else "review_required",
                f"{document_count} controlled documents",
                "Attach evidence",
                "Document Controller",
                "evidence",
                0 if document_count else 1,
            ),
        ]

        return GuidedFlowOut(
            tenant=TenantContextOut.model_validate(tenant),
            project=GuidedProjectContextOut(
                id=project.id,
                code=project.code,
                name=project.name,
                status=project.status,
                currency=project.currency,
            ),
            steps=steps,
            next_action=self._next_action(steps),
            cost_currency_gate=cost_gate,
        )

    def _latest_import(self, tenant_id: int, project_id: int) -> ScheduleImport | None:
        return self.db.scalar(
            select(ScheduleImport)
            .where(ScheduleImport.tenant_id == tenant_id, ScheduleImport.project_id == project_id)
            .order_by(ScheduleImport.imported_at.desc())
        )

    def _count(self, model: type, tenant_id: int, project_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count()).select_from(model).where(model.tenant_id == tenant_id, model.project_id == project_id)
            )
            or 0
        )

    def _schedule_import_activity_count(
        self,
        tenant_id: int,
        project_id: int,
        schedule_import: ScheduleImport | None,
    ) -> int:
        if not schedule_import:
            return 0
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(ScheduleActivityMap)
                .where(
                    ScheduleActivityMap.tenant_id == tenant_id,
                    ScheduleActivityMap.project_id == project_id,
                    ScheduleActivityMap.schedule_import_id == schedule_import.id,
                )
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

    def _cost_gate(
        self,
        project_id: int,
        schedule_import: ScheduleImport | None,
        activity_count: int,
    ) -> CostCurrencyGateOut:
        if not schedule_import:
            return CostCurrencyGateOut(project_id=project_id)
        missing_cost_activity_count = max(activity_count - schedule_import.cost_loaded_activity_count, 0)
        has_costs = schedule_import.cost_loaded_activity_count > 0 and schedule_import.total_imported_cost > 0
        has_currency = bool(schedule_import.detected_currency)
        ready = has_costs and has_currency and schedule_import.currency_confirmed
        if ready:
            state = "ready"
            message = "Cost loading and currency are confirmed for baseline approval."
        elif not has_costs:
            state = "blocked"
            message = "Baseline is blocked until the schedule has cost-loaded activities."
        elif not has_currency:
            state = "blocked"
            message = "Baseline is blocked until schedule currency is selected."
        else:
            state = "review_required"
            message = "Confirm detected currency before baseline approval."
        return CostCurrencyGateOut(
            project_id=project_id,
            schedule_import_id=schedule_import.id,
            detected_currency=schedule_import.detected_currency,
            currency_confidence=schedule_import.currency_confidence,
            currency_source=schedule_import.currency_source,
            currency_confirmed=schedule_import.currency_confirmed,
            total_imported_cost=schedule_import.total_imported_cost,
            cost_loaded_activity_count=schedule_import.cost_loaded_activity_count,
            cost_loaded_activity_percent=schedule_import.cost_loaded_activity_percent,
            missing_cost_activity_count=missing_cost_activity_count,
            cost_source_summary=schedule_import.cost_source_summary or {},
            state=state,
            message=message,
        )

    def _step(
        self,
        key: str,
        label: str,
        state: str,
        summary: str,
        next_action: str,
        owner_role: str,
        target_view: str,
        blocking_count: int = 0,
    ) -> GuidedFlowStepOut:
        return GuidedFlowStepOut(
            key=key,
            label=label,
            state=state,
            summary=summary,
            next_action=next_action,
            owner_role=owner_role,
            target_view=target_view,
            blocking_count=blocking_count,
        )

    def _next_action(self, steps: list[GuidedFlowStepOut]) -> GuidedNextActionOut:
        for step in steps:
            if step.state in {"blocked", "review_required"}:
                return GuidedNextActionOut(
                    key=step.key,
                    label=step.next_action,
                    target_view=step.target_view,
                    disabled=False,
                    reason=step.summary,
                )
        baseline_step = next((step for step in steps if step.key == "baseline"), steps[0])
        return GuidedNextActionOut(
            key=baseline_step.key,
            label=baseline_step.next_action,
            target_view=baseline_step.target_view,
            disabled=False,
            reason=baseline_step.summary,
        )
