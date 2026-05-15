from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    AuditLog,
    BaselineVersion,
    BusinessProcessInstance,
    BusinessProcessTemplate,
    BusinessProcessTransitionTemplate,
    WorkflowStepInstance,
)


class WorkflowRoutingService:
    def __init__(self, db: Session):
        self.db = db

    def apply_action(
        self,
        tenant_id: int,
        project_id: int,
        process_id: int,
        action: str,
        actor: str = "Project Controls",
    ) -> BusinessProcessInstance:
        process = self.db.scalar(
            select(BusinessProcessInstance).where(
                BusinessProcessInstance.id == process_id,
                BusinessProcessInstance.tenant_id == tenant_id,
                BusinessProcessInstance.project_id == project_id,
            )
        )
        if not process:
            raise ValueError("Workflow process not found")

        normalized = action.strip().lower()
        if self._apply_configured_transition(process, normalized):
            if normalized == "approve_baseline":
                self._set_baseline_status(process, "approved")
            elif normalized == "reject_baseline":
                self._set_baseline_status(process, "rejected")
            elif normalized == "close_action":
                self._set_baseline_status(process, "active")
        elif normalized == "route_to_approval":
            self._route_to_approval(process)
        elif normalized == "approve_baseline":
            self._approve_baseline(process)
            self._set_baseline_status(process, "approved")
        elif normalized == "reject_baseline":
            self._reject_baseline(process)
            self._set_baseline_status(process, "rejected")
        elif normalized == "close_action":
            self._close_action(process)
            self._set_baseline_status(process, "active")
        else:
            raise ValueError("Unsupported workflow action")

        process.updated_at = utc_now()
        process.version = (process.version or 1) + 1
        self.db.add(
            AuditLog(
                tenant_id=tenant_id,
                project_id=project_id,
                actor=actor,
                action=f"workflow.{normalized}",
                entity_type="BusinessProcessInstance",
                entity_id=process.id,
                payload=f'{{"record_no":"{process.record_no}","current_step":"{process.current_step}"}}',
            )
        )
        self.db.commit()
        self.db.refresh(process)
        return process

    def _apply_configured_transition(self, process: BusinessProcessInstance, action: str) -> bool:
        transition = self._configured_transition(process, action, process.current_step)
        if not transition:
            transition = self._configured_transition(process, action, "")
        if not transition:
            return False

        if transition.from_step:
            self._set_step(process.id, transition.from_step, transition.from_status, transition.from_tone)
        if transition.to_step and transition.to_step.lower() != "closed":
            self._set_step(process.id, transition.to_step, transition.to_status, transition.to_tone)
        process.status = transition.process_status
        process.current_step = transition.to_step or process.current_step
        process.ball_in_court = transition.ball_in_court or process.ball_in_court
        return True

    def _configured_transition(
        self,
        process: BusinessProcessInstance,
        action: str,
        from_step: str,
    ) -> BusinessProcessTransitionTemplate | None:
        template = self.db.scalar(
            select(BusinessProcessTemplate).where(
                BusinessProcessTemplate.tenant_id == process.tenant_id,
                BusinessProcessTemplate.code == process.process_code,
            )
        )
        if not template:
            return None
        return self.db.scalar(
            select(BusinessProcessTransitionTemplate).where(
                BusinessProcessTransitionTemplate.tenant_id == process.tenant_id,
                BusinessProcessTransitionTemplate.template_id == template.id,
                BusinessProcessTransitionTemplate.action == action,
                BusinessProcessTransitionTemplate.from_step == from_step,
            )
        )

    def _route_to_approval(self, process: BusinessProcessInstance) -> None:
        self._set_step(process.id, "Impact Review", "Complete", "complete")
        self._set_step(process.id, "Approval", "Active", "active")
        process.status = "in_review"
        process.current_step = "Approval"
        process.ball_in_court = "Control Manager"

    def _approve_baseline(self, process: BusinessProcessInstance) -> None:
        self._set_step(process.id, "Approval", "Complete", "complete")
        self._set_step(process.id, "Action", "Active", "active")
        process.status = "approved"
        process.current_step = "Action"
        process.ball_in_court = "Execution Lead"

    def _reject_baseline(self, process: BusinessProcessInstance) -> None:
        self._set_step(process.id, "Approval", "Rejected", "critical")
        self._set_step(process.id, "Action", "Blocked", "queued")
        process.status = "rejected"
        process.current_step = "Data Quality Gate"
        process.ball_in_court = "Planning Lead"

    def _close_action(self, process: BusinessProcessInstance) -> None:
        self._set_step(process.id, "Action", "Complete", "complete")
        process.status = "closed"
        process.current_step = "Closed"
        process.ball_in_court = "Control Core"

    def _set_step(self, process_id: int, name: str, status: str, tone: str) -> None:
        step = self.db.scalar(
            select(WorkflowStepInstance).where(
                WorkflowStepInstance.process_instance_id == process_id,
                WorkflowStepInstance.name == name,
            )
        )
        if step:
            step.status = status
            step.tone = tone

    def _set_baseline_status(self, process: BusinessProcessInstance, status: str) -> None:
        if process.trigger_entity_type != "ScheduleImport":
            return
        baseline = self.db.scalar(
            select(BaselineVersion).where(
                BaselineVersion.tenant_id == process.tenant_id,
                BaselineVersion.project_id == process.project_id,
                BaselineVersion.schedule_import_id == process.trigger_entity_id,
            )
        )
        if baseline:
            baseline.status = status
