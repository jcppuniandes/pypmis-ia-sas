"""Explicit Quality evidence decisions executed under each consumer's native authority."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import AwareDatetime, Field
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.core.time import utc_now
from app.database.session import get_db
from app.modules.awp.models import ReadinessAssessment, WorkPackage
from app.modules.awp.schemas import AssessmentIn
from app.modules.awp.service import AWPService
from app.modules.contracts_foundation.service import ContractsService
from app.modules.cost_foundation.models import ControlAccount, CostCBS, CostCode
from app.modules.cost_foundation.service import CostFoundationService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.field_operations.service import FieldOperationsService
from app.modules.portfolio_review.router import _etag, _idempotency_key
from app.modules.progress_foundation.models import ProgressMeasurement
from app.modules.progress_foundation.service import ProgressFoundationService
from app.modules.quality.consumer_models import QualityConsumerDecision
from app.modules.quality.consumer_sources import read_quality_source, validate_progress_binding
from app.modules.quality.schemas import ReasonIn
from app.modules.quality.support_router import expected_stream
from app.modules.schedule_foundation.service import ScheduleFoundationService


class NativeAWP(AWPService):
    def _write(self, command, workspace, payload, key, apply, identity=None, expected=None):
        # The outer native command owns the idempotency/transaction boundary.
        return apply()


OWNERS = {
    "PROGRESS": (ProgressFoundationService, "progress", "capture"),
    "AWP": (NativeAWP, "awp", "readiness.assess"),
    "COST": (CostFoundationService, "cost", "mapping.edit"),
    "CONTRACTS": (ContractsService, "contracts", None),
    "SCHEDULE": (ScheduleFoundationService, "schedule", None),
    "FIELD_OPERATIONS": (FieldOperationsService, "field-operations", None),
}
PERMISSION_PREFIX = {"SCHEDULE": "schedule_foundation", "FIELD_OPERATIONS": "field_operations"}
SUPPORTED = {
    "PROGRESS": {"ACCEPTANCE"},
    "AWP": {"READINESS", "ACCEPTANCE", "NCR"},
    "COST": {"NCR", "ACCEPTANCE", "INSPECTION", "TEST"},
    "CONTRACTS": {"NCR", "ACCEPTANCE", "INSPECTION", "TEST"},
    "SCHEDULE": {"NCR", "ACCEPTANCE", "READINESS"},
    "FIELD_OPERATIONS": {"ACCEPTANCE", "READINESS"},
}


class DecisionIn(ReasonIn):
    source_entity_type: Literal["ACCEPTANCE", "READINESS", "NCR", "INSPECTION", "TEST"]
    source_entity_id: int = Field(gt=0)
    source_version: int = Field(gt=0)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at: AwareDatetime
    decision: Literal["ADOPT", "REJECT", "RECONCILE"]
    measurement_id: int | None = Field(None, gt=0)
    work_package_id: int | None = Field(None, gt=0)
    cbs_id: int | None = Field(None, gt=0)
    cost_code_id: int | None = Field(None, gt=0)
    control_account_id: int | None = Field(None, gt=0)


class QualityConsumer:
    def __init__(self, consumer, owner):
        self.consumer, self.owner, self.db = consumer, owner, owner.db

    def check(self, workspace, write=False):
        project = self.owner._project(workspace)
        self.owner._permission("read", project)
        if not inspect(self.db.connection()).has_table(QualityConsumerDecision.__tablename__):
            self.owner._error(409, "QUALITY_CONSUMER_MIGRATION_REQUIRED")
        if write:
            duty = OWNERS[self.consumer][2]
            if duty is None:
                self.owner._error(403, "QUALITY_CONSUMER_INFORMATION_ONLY")
            self.owner._ready(workspace, duty)

    def query(self, workspace):
        return select(QualityConsumerDecision).where(
            QualityConsumerDecision.tenant_id == self.owner.tenant_id,
            QualityConsumerDecision.project_workspace_id == workspace,
            QualityConsumerDecision.consumer == self.consumer,
        )

    def source(self, workspace, kind, identity, **pins):
        if kind not in SUPPORTED[self.consumer]:
            self.owner._error(422, "QUALITY_CONSUMER_SOURCE_TYPE_DISABLED")
        return read_quality_source(
            self.db, self.owner.tenant_id, workspace, self.owner.actor_id, kind, identity, **pins
        )

    def latest(self, workspace, source):
        return self.db.scalar(
            self.query(workspace)
            .where(
                QualityConsumerDecision.subject_key == source["subject_key"],
                QualityConsumerDecision.source_entity_type == source["source_entity_type"],
                QualityConsumerDecision.source_root_id == source["source_root_id"],
            )
            .order_by(QualityConsumerDecision.version.desc())
            .limit(1)
        )

    def lookup(self, workspace, kind, identity):
        self.check(workspace)
        source = self.source(workspace, kind, identity)
        old = self.latest(workspace, source)
        duty = OWNERS[self.consumer][2]
        allowed = self.owner.allowed_actions(self.owner._project(workspace))
        prefix = PERMISSION_PREFIX.get(self.consumer, OWNERS[self.consumer][1])
        return {
            **source,
            "version": old.version if old else 0,
            "consumer_status": old.decision if old else None,
            "consumer_allowed_actions": [f"{prefix}.{duty}"] if duty and duty in allowed else [],
            "quantity_created": False,
            "package_released": False,
        }

    def progress(self, workspace, source, payload):
        if not payload.measurement_id:
            self.owner._error(422, "QUALITY_PROGRESS_EXISTING_DRAFT_MEASUREMENT_REQUIRED")
        row = self.owner._get(ProgressMeasurement, workspace, payload.measurement_id, lock=True)
        if (
            row.status not in {"DRAFT", "SUBMITTED", "UNDER_REVIEW"}
            or self.owner._source_state(row, check_quality=False) != "CURRENT"
        ):
            self.owner._error(409, "QUALITY_PROGRESS_CURRENT_DRAFT_REQUIRED")
        validate_progress_binding(self.owner, row, source)
        return "ProgressMeasurement", row.id, row.period_id, {}

    def awp(self, workspace, source, payload):
        if not payload.work_package_id:
            self.owner._error(422, "QUALITY_AWP_PACKAGE_REQUIRED")
        row = self.owner._get(WorkPackage, workspace, payload.work_package_id, lock=True)
        facts = source["facts"]
        subject = facts.get("subject_reference", {})
        if subject.get("facts", {}).get("iwp_id") != row.id:
            self.owner._error(422, "QUALITY_AWP_EXACT_IWP_REQUIRED")
        if payload.decision != "REJECT" and (
            source["source_entity_type"] not in {"READINESS", "ACCEPTANCE"}
            or source["source_entity_type"] == "READINESS"
            and facts["readiness_state"] != "READY"
        ):
            self.owner._error(409, "QUALITY_AWP_READY_EVIDENCE_REQUIRED")
        return "WorkPackage", row.id, None, {}

    def cost(self, workspace, source, payload):
        result = {}
        for field, model in (("cbs_id", CostCBS), ("cost_code_id", CostCode), ("control_account_id", ControlAccount)):
            identity = getattr(payload, field)
            if identity:
                target = self.owner._get(model, workspace, identity)
                result[field] = target.id
        if payload.decision != "REJECT" and not result:
            self.owner._error(422, "QUALITY_COST_CLASSIFICATION_REQUIRED")
        return None, None, None, result

    def decide(self, workspace, payload, expected, key):
        self.check(workspace, True)

        def apply():
            self.check(workspace, True)
            project = self.owner._project(workspace)
            # Serialize the source decision stream, including an empty first stream.
            self.db.refresh(project, with_for_update=True)
            source = self.source(
                workspace,
                payload.source_entity_type,
                payload.source_entity_id,
                expected_version=payload.source_version,
                expected_hash=payload.source_hash,
            )
            if source["observed_at"] != payload.observed_at.isoformat():
                from datetime import datetime

                if datetime.fromisoformat(source["observed_at"]) != payload.observed_at:
                    self.owner._error(409, "QUALITY_CONSUMER_OBSERVATION_PIN_CHANGED")
            old = self.latest(workspace, source)
            self.owner._version(old.version if old else 0, expected)
            if payload.decision != "REJECT" and source["source_state"] != "CURRENT":
                self.owner._error(409, "QUALITY_CONSUMER_CURRENT_EVIDENCE_REQUIRED")
            if payload.decision == "ADOPT" and old or payload.decision == "RECONCILE" and old is None:
                self.owner._error(409, "QUALITY_CONSUMER_EXPLICIT_RECONCILIATION_REQUIRED")
            if (
                self.consumer != "PROGRESS"
                and payload.measurement_id
                or self.consumer != "AWP"
                and payload.work_package_id
                or self.consumer != "COST"
                and any((payload.cbs_id, payload.cost_code_id, payload.control_account_id))
            ):
                self.owner._error(422, "QUALITY_CONSUMER_FOREIGN_AUTHORITY_FIELDS")
            linked_type, linked_id, period_id, mapping = getattr(self, self.consumer.lower())(
                workspace, source, payload
            )
            if old and old.linked_entity_id != linked_id:
                successor = (
                    self.owner._get(ProgressMeasurement, workspace, linked_id) if self.consumer == "PROGRESS" else None
                )
                if (
                    payload.decision != "RECONCILE"
                    or successor is None
                    or successor.supersedes_id != old.linked_entity_id
                ):
                    self.owner._error(409, "QUALITY_CONSUMER_RECONCILIATION_TARGET_CHANGED")
            row = QualityConsumerDecision(
                **(self.owner._base(workspace) | {"version": old.version + 1 if old else 1}),
                consumer=self.consumer,
                source_domain="QUALITY",
                source_entity_type=source["source_entity_type"],
                source_entity_id=source["source_entity_id"],
                source_root_id=source["source_root_id"],
                source_version=source["source_version"],
                source_hash=source["source_hash"],
                observed_at=payload.observed_at,
                subject_key=source["subject_key"],
                decision=payload.decision,
                linked_entity_type=linked_type,
                linked_entity_id=linked_id,
                effective_period_id=period_id,
                mapping_reference=mapping,
                source_snapshot=source,
                previous_decision_id=old.id if old else None,
                reason=payload.reason,
            )
            self.db.add(row)
            self.db.flush()
            if self.consumer == "AWP":
                package = self.owner._get(WorkPackage, workspace, linked_id)
                last = self.db.scalar(
                    select(ReadinessAssessment)
                    .where(
                        ReadinessAssessment.tenant_id == self.owner.tenant_id,
                        ReadinessAssessment.project_workspace_id == workspace,
                        ReadinessAssessment.work_package_id == linked_id,
                    )
                    .order_by(ReadinessAssessment.id.desc())
                    .limit(1)
                )
                evidence = dict(last.evidence_state.get("references", {}) if last else {})
                evidence["QUALITY"] = f"QUALITY_DECISION:{row.id}:{source['source_hash']}"
                self.owner.assess(
                    workspace,
                    linked_id,
                    AssessmentIn(reason=payload.reason, as_of=utc_now().isoformat(), evidence_json=evidence),
                    package.version,
                    key,
                )
            self.owner._event(
                "quality_evidence_decided",
                row.id,
                {
                    "workspace_id": workspace,
                    "source": source,
                    "decision": row.decision,
                    "linked_entity_type": linked_type,
                    "linked_entity_id": linked_id,
                    "reason": payload.reason,
                },
            )
            return self.owner._out(row)

        return self.owner._command(
            f"{self.consumer.lower()}.quality_evidence.decide",
            key,
            {"project": workspace, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )


def consumer_router(consumer):
    router = APIRouter()
    owner_type, _, duty = OWNERS[consumer]
    prefix = PERMISSION_PREFIX.get(consumer, OWNERS[consumer][1])

    def authorized(
        db: Session = Depends(get_db), tenant: int = Depends(get_tenant_id), actor: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(db, tenant, actor, f"{prefix}.read", bootstrap=False)
        return QualityConsumer(consumer, owner_type(db, tenant, actor, access))

    root = "/projects/{workspace_id}/quality-adoptions"

    @router.get(root + "/lookup", name=f"{consumer.lower()}_quality_lookup")
    def lookup(
        workspace_id: int,
        response: Response,
        source_entity_type: str = Query(min_length=2, max_length=40),
        source_entity_id: int = Query(gt=0),
        service=Depends(authorized),
    ):
        result = service.lookup(workspace_id, source_entity_type, source_entity_id)
        _etag(response, result["version"])
        return result

    @router.get(root, name=f"{consumer.lower()}_quality_history")
    def history(
        workspace_id: int,
        limit: int = Query(50, ge=1, le=200),
        before_id: int | None = Query(None, gt=0),
        service=Depends(authorized),
    ):
        service.check(workspace_id)
        query = service.query(workspace_id)
        if before_id:
            query = query.where(QualityConsumerDecision.id < before_id)
        rows = list(service.db.scalars(query.order_by(QualityConsumerDecision.id.desc()).limit(limit + 1)))
        return {
            "items": [service.owner._out(row) for row in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
        }

    if duty:

        @router.post(root, status_code=201, name=f"{consumer.lower()}_quality_decision")
        def decide(
            workspace_id: int,
            payload: DecisionIn,
            response: Response,
            expected=Depends(expected_stream),
            key=Depends(_idempotency_key),
            service=Depends(authorized),
        ):
            result = service.decide(workspace_id, payload, expected, key)
            _etag(response, result["version"])
            return result

    return router
