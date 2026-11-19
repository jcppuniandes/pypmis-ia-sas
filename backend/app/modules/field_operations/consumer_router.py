"""Native consumer decisions. Field fact creation never invokes these commands."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.awp.schemas import ConstraintIn, ConstraintMappingIn
from app.modules.awp.service import AWPService
from app.modules.basic_data.service import _hash
from app.modules.contracts_foundation.service import ContractsService
from app.modules.cost_foundation.models import ControlAccount, CostCBS, CostCode
from app.modules.cost_foundation.service import CostFoundationService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.field_operations.consumer_models import FieldConsumerDecision
from app.modules.field_operations.consumer_sources import SOURCES, read_field_source
from app.modules.operational_context.models import ProjectControlsPeriod
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.progress_foundation.models import ProgressMeasurement
from app.modules.progress_foundation.schemas import MeasurementIn
from app.modules.progress_foundation.service import ProgressFoundationService
from app.modules.schedule_foundation.service import ScheduleFoundationService
from app.modules.scope_foundation.models import ScopeItem

ROOT = "/projects/{workspace_id}/field-adoptions"


class DecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_entity_type: str = Field(pattern=r"^[A-Z_]{2,40}$")
    source_entity_id: int = Field(gt=0)
    source_version: int = Field(gt=0)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at: AwareDatetime
    decision: Literal["ADOPT", "PARTIAL_ADOPT", "REJECT"]
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=24, decimal_places=8)
    period_id: int | None = Field(default=None, gt=0)
    measurement_code: str | None = Field(default=None, min_length=1, max_length=120)
    constraint_type: str | None = Field(default=None, min_length=1, max_length=80)
    constraint_code: str | None = Field(default=None, min_length=1, max_length=120)
    blocking: bool | None = None
    cbs_id: int | None = Field(default=None, gt=0)
    cost_code_id: int | None = Field(default=None, gt=0)
    control_account_id: int | None = Field(default=None, gt=0)
    reason: str = Field(min_length=8, max_length=3000)


class AtomicNativeCommands:
    """Keep native validations and audit inside one outer consumer receipt transaction."""

    field_pin = None

    def _write(self, command, workspace, payload, key, apply, identity=None, expected=None):
        return apply()

    def _record(self, row, event, reason, **kwargs):
        if isinstance(row, ProgressMeasurement) and self.field_pin:
            row.source_snapshot = row.source_snapshot | {"field_operations": self.field_pin}
            row.source_hash = _hash(row.source_snapshot)
            row.source_domain = "FIELD_OPERATIONS"
            row.content_hash = _hash(self._content(row))
        return super()._record(row, event, reason, **kwargs)


class NativeProgress(AtomicNativeCommands, ProgressFoundationService):
    pass


class NativeAWP(AtomicNativeCommands, AWPService):
    pass


OWNERS = {
    "PROGRESS": (NativeProgress, "progress", "capture"),
    "AWP": (NativeAWP, "awp", "constraint.raise"),
    "COST": (CostFoundationService, "cost", "mapping.edit"),
    "CONTRACTS": (ContractsService, "contracts", None),
    "SCHEDULE": (ScheduleFoundationService, "schedule_foundation", None),
}
SUPPORTED = {
    "PROGRESS": {"PRODUCTION"},
    "AWP": {"CONSTRAINT"},
    "COST": {"LABOR", "EQUIPMENT", "PRODUCTION"},
    "CONTRACTS": {"EVENT", "INSTRUCTION", "PRODUCTION", "DAILY_REPORT"},
    "SCHEDULE": {"WORKFRONT", "PRODUCTION", "EVENT"},
}


def _expected(value: str = Header(..., alias="If-Match")):
    return 0 if value.strip() in {"0", '"0"'} else _if_match(value)


class FieldConsumer:
    def __init__(self, consumer, owner):
        self.consumer, self.owner, self.db = consumer, owner, owner.db

    def check(self, workspace, write=False):
        project = self.owner._project(workspace)
        self.owner._permission("read", project)
        if not inspect(self.db.connection()).has_table(FieldConsumerDecision.__tablename__):
            self.owner._error(409, "FIELD_CONSUMER_MIGRATION_REQUIRED")
        if write:
            duty = OWNERS[self.consumer][2]
            if not duty:
                self.owner._error(403, "FIELD_CONSUMER_INFORMATION_ONLY")
            self.owner._ready(workspace, duty)

    def query(self, workspace):
        return select(FieldConsumerDecision).where(
            FieldConsumerDecision.tenant_id == self.owner.tenant_id,
            FieldConsumerDecision.project_workspace_id == workspace,
            FieldConsumerDecision.consumer == self.consumer,
        )

    def source(self, workspace, kind, identity, **pins):
        if kind not in SUPPORTED[self.consumer]:
            self.owner._error(422, "FIELD_CONSUMER_SOURCE_TYPE_DISABLED")
        return read_field_source(self.db, self.owner.tenant_id, workspace, kind, identity, **pins)

    def latest(self, workspace, source):
        return self.db.scalar(
            self.query(workspace)
            .where(
                FieldConsumerDecision.source_entity_type == source["source_entity_type"],
                FieldConsumerDecision.source_root_id == source["source_root_id"],
            )
            .order_by(FieldConsumerDecision.version.desc())
            .limit(1)
        )

    def lookup(self, workspace, kind, identity):
        self.check(workspace)
        source = self.source(workspace, kind, identity)
        old = self.latest(workspace, source)
        duty = OWNERS[self.consumer][2]
        actions = self.owner.allowed_actions(self.owner._project(workspace))
        permission_prefix = OWNERS[self.consumer][1]
        quantity = self.consumed(workspace, source)
        return source | {
            "version": old.version if old else 0,
            "consumer_decision": old.decision if old else None,
            "previously_adopted_quantity": str(quantity),
            "remaining_quantity": str(Decimal(source["facts"].get("quantity", "0")) - quantity),
            "consumer_allowed_actions": [f"{permission_prefix}.{duty}"] if duty and duty in actions else [],
        }

    def consumed(self, workspace, source):
        return self.db.scalar(
            select(func.coalesce(func.sum(FieldConsumerDecision.quantity), 0)).where(
                FieldConsumerDecision.tenant_id == self.owner.tenant_id,
                FieldConsumerDecision.project_workspace_id == workspace,
                FieldConsumerDecision.consumer == self.consumer,
                FieldConsumerDecision.source_entity_type == source["source_entity_type"],
                FieldConsumerDecision.source_root_id == source["source_root_id"],
                FieldConsumerDecision.decision.in_(("ADOPT", "PARTIAL_ADOPT")),
            )
        ) or Decimal(0)

    def progress(self, workspace, source, payload, key):
        if not payload.period_id or not payload.measurement_code:
            self.owner._error(422, "FIELD_PROGRESS_PERIOD_AND_CODE_REQUIRED")
        facts = source["facts"]
        available = Decimal(facts["quantity"]) - self.consumed(workspace, source)
        quantity = payload.quantity
        if quantity is None or quantity > available or payload.decision == "ADOPT" and quantity != available:
            self.owner._error(409, "FIELD_PROGRESS_QUANTITY_EXCEEDS_AVAILABLE_OR_PARTIAL_REQUIRED")
        if payload.decision == "PARTIAL_ADOPT" and quantity >= available:
            self.owner._error(422, "FIELD_PROGRESS_PARTIAL_QUANTITY_REQUIRED")
        period = self.owner._get(ProjectControlsPeriod, workspace, payload.period_id, lock=True)
        observed = date.fromisoformat(source["observation_date"])
        if not period.period_start <= observed <= period.period_end:
            self.owner._error(422, "FIELD_PROGRESS_OBSERVATION_OUTSIDE_PERIOD")
        scope = self.owner._get(ScopeItem, workspace, facts["scope_item_id"])
        data = MeasurementIn(
            reason=payload.reason,
            code=payload.measurement_code,
            name="Explicit Field evidence adoption",
            progress_type="QUANTITY",
            method="QUANTITY_BASED",
            source_reference=f"FIELD_OPERATIONS:PRODUCTION:{source['source_entity_id']}:{source['source_hash']}",
            # Measure the approved Scope denominator, not a potentially mixed-UOM IWP.
            # Plan and IWP identities remain frozen in the complete Field source pin.
            scope_item_id=scope.id,
            denominator_basis="SCOPE",
            scope_nature=scope.scope_nature,
            phase="INSTALL",
            period_id=payload.period_id,
            measurement_date=observed,
            as_of=observed,
            numerator=quantity,
            unit=facts["uom"],
            input_mode="PERIOD_DELTA",
            evidence_refs=[
                {
                    "kind": "FIELD_REPORT",
                    "reference": f"PRODUCTION:{source['source_entity_id']}",
                    "content_hash": source["source_hash"],
                }
            ],
        )
        subject = self.owner._subject(data)
        pending = self.db.scalar(
            select(ProgressMeasurement.id)
            .where(
                ProgressMeasurement.tenant_id == self.owner.tenant_id,
                ProgressMeasurement.project_workspace_id == workspace,
                ProgressMeasurement.period_id == period.id,
                ProgressMeasurement.subject_key == subject,
                ProgressMeasurement.status.in_(("DRAFT", "SUBMITTED", "UNDER_REVIEW")),
            )
            .limit(1)
        )
        if pending:
            self.owner._error(409, "FIELD_PROGRESS_PENDING_NATIVE_MEASUREMENT")
        approved = [
            row
            for row in self.owner.effective_approved(workspace, period_id=period.id, progress_type="QUANTITY")
            if row.subject_key == subject
        ]
        if len(approved) > 1:
            self.owner._error(409, "FIELD_PROGRESS_APPROVED_SUBJECT_AMBIGUOUS")
        prior_pins = approved[0].source_snapshot.get("field_operations", []) if approved else []
        if isinstance(prior_pins, dict):
            prior_pins = [prior_pins]
        self.owner.field_pin = [*prior_pins, source]
        if approved:
            old = approved[0]
            data = data.model_copy(
                update={"code": old.code, "input_mode": "CUMULATIVE", "numerator": old.numerator + quantity}
            )
            result = self.owner.save_measurement(workspace, data, key, old.id, old.version, successor=True)
        else:
            result = self.owner.save_measurement(workspace, data, key)
        return "ProgressMeasurement", result["id"], quantity, {"period_id": period.id}

    def awp(self, workspace, source, payload, key):
        if not payload.constraint_type or not payload.constraint_code or payload.blocking is None:
            self.owner._error(422, "FIELD_AWP_CONSTRAINT_DETAILS_REQUIRED")
        if self.db.scalar(
            self.query(workspace)
            .where(
                FieldConsumerDecision.source_entity_type == source["source_entity_type"],
                FieldConsumerDecision.source_root_id == source["source_root_id"],
                FieldConsumerDecision.decision == "ADOPT",
            )
            .limit(1)
        ):
            self.owner._error(409, "FIELD_AWP_ALREADY_ADOPTED")
        result = self.owner.save_constraint(
            workspace,
            ConstraintIn(
                reason=payload.reason,
                code=payload.constraint_code,
                title="Adopted Field constraint observation",
                description=source["facts"]["description"],
                constraint_type=payload.constraint_type,
                blocking=payload.blocking,
                source_domain="FIELD_OPERATIONS",
                source_reference=f"CONSTRAINT:{source['source_entity_id']}:{source['source_hash']}",
                evidence_reference=f"FIELD_OPERATIONS:{source['source_entity_id']}",
            ),
            key,
        )
        iwp = source["facts"].get("iwp_id")
        if not iwp:
            self.owner._error(422, "FIELD_AWP_OBSERVATION_IWP_REQUIRED")
        self.owner.map_constraint(
            workspace,
            result["id"],
            ConstraintMappingIn(
                reason=payload.reason,
                target_kind="PACKAGE",
                target_id=iwp,
            ),
            result["version"],
            key,
        )
        return "AWPExecutionConstraint", result["id"], None, {"iwp_id": iwp}

    def decide(self, workspace, payload, expected, key):
        self.check(workspace, write=True)
        fields = {
            "PROGRESS": {"quantity", "period_id", "measurement_code"},
            "AWP": {"constraint_type", "constraint_code", "blocking"},
            "COST": {"cbs_id", "cost_code_id", "control_account_id"},
        }
        consumer_fields = set().union(*fields.values())
        if any(getattr(payload, name) is not None for name in consumer_fields - fields[self.consumer]):
            self.owner._error(422, "FIELD_CONSUMER_UNRELATED_AUTHORITY_FIELDS")

        def apply():
            self.check(workspace, write=True)
            if payload.source_entity_type not in SUPPORTED[self.consumer]:
                self.owner._error(422, "FIELD_CONSUMER_SOURCE_TYPE_DISABLED")
            self.owner._get(SOURCES[payload.source_entity_type], workspace, payload.source_entity_id, lock=True)
            source = self.source(
                workspace,
                payload.source_entity_type,
                payload.source_entity_id,
                expected_version=payload.source_version,
                expected_hash=payload.source_hash,
            )
            if datetime.fromisoformat(source["observed_at"]) != payload.observed_at:
                self.owner._error(409, "FIELD_CONSUMER_OBSERVATION_MISMATCH")
            old = self.latest(workspace, source)
            version = old.version if old else 0
            self.owner._version(version, expected)
            linked_type = linked_id = quantity = None
            mapping = {}
            if payload.decision != "REJECT":
                if self.consumer == "PROGRESS":
                    linked_type, linked_id, quantity, mapping = self.progress(workspace, source, payload, key)
                elif self.consumer == "AWP":
                    if payload.decision != "ADOPT":
                        self.owner._error(422, "FIELD_AWP_PARTIAL_NOT_SUPPORTED")
                    linked_type, linked_id, quantity, mapping = self.awp(workspace, source, payload, key)
                else:
                    if payload.decision != "ADOPT":
                        self.owner._error(422, "FIELD_COST_PARTIAL_NOT_SUPPORTED")
                    if self.db.scalar(
                        self.query(workspace)
                        .where(
                            FieldConsumerDecision.source_entity_type == source["source_entity_type"],
                            FieldConsumerDecision.source_root_id == source["source_root_id"],
                            FieldConsumerDecision.decision == "ADOPT",
                        )
                        .limit(1)
                    ):
                        self.owner._error(409, "FIELD_COST_ALREADY_ADOPTED")
                    for model, field in (
                        (CostCBS, "cbs_id"),
                        (CostCode, "cost_code_id"),
                        (ControlAccount, "control_account_id"),
                    ):
                        if not getattr(payload, field):
                            self.owner._error(422, "FIELD_COST_DIMENSIONS_REQUIRED")
                        row = self.owner._get(model, workspace, getattr(payload, field))
                        if row.status != "ACTIVE":
                            self.owner._error(409, "FIELD_COST_DIMENSION_INACTIVE")
                        mapping[field] = {"id": row.id, "version": row.version, "code": row.code}
            row = FieldConsumerDecision(
                **(self.owner._base(workspace) | {"version": version + 1}),
                consumer=self.consumer,
                source_domain="FIELD_OPERATIONS",
                source_entity_type=payload.source_entity_type,
                source_entity_id=payload.source_entity_id,
                source_root_id=source["source_root_id"],
                source_version=payload.source_version,
                source_hash=payload.source_hash,
                observed_at=payload.observed_at,
                observation_date=date.fromisoformat(source["observation_date"]),
                effective_period_id=payload.period_id,
                quantity=quantity,
                uom=source["facts"].get("uom"),
                decision=payload.decision,
                linked_entity_type=linked_type,
                linked_entity_id=linked_id,
                mapping_reference=mapping,
                source_snapshot=source,
                reason=payload.reason,
            )
            self.db.add(row)
            self.db.flush()
            self.owner._event(
                "field_evidence_adopted",
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
            f"{self.consumer.lower()}.field_evidence.decide",
            key,
            {"project": workspace, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )


def consumer_router(domain):
    router = APIRouter()
    owner_type, prefix, duty = OWNERS[domain]

    def dependency(
        db: Session = Depends(get_db), tenant: int = Depends(get_tenant_id), actor: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(db, tenant, actor, f"{prefix}.read", bootstrap=False)
        return FieldConsumer(domain, owner_type(db, tenant, actor, access))

    @router.get(ROOT + "/lookup", name=f"{domain.lower()}_field_lookup")
    def lookup(
        workspace_id: int,
        response: Response,
        source_entity_type: str = Query(pattern=r"^[A-Z_]{2,40}$"),
        source_entity_id: int = Query(gt=0),
        service=Depends(dependency),
    ):
        result = service.lookup(workspace_id, source_entity_type, source_entity_id)
        _etag(response, result["version"])
        return result

    @router.get(ROOT, name=f"{domain.lower()}_field_history")
    def history(
        workspace_id: int,
        limit: int = Query(50, ge=1, le=200),
        before_id: int | None = Query(None, gt=0),
        service=Depends(dependency),
    ):
        service.check(workspace_id)
        query = service.query(workspace_id)
        if before_id:
            query = query.where(FieldConsumerDecision.id < before_id)
        values = list(service.db.scalars(query.order_by(FieldConsumerDecision.id.desc()).limit(limit + 1)))
        return {
            "items": [service.owner._out(row) for row in values[:limit]],
            "next_cursor": values[limit - 1].id if len(values) > limit else None,
        }

    if duty:

        @router.post(ROOT, status_code=201, name=f"{domain.lower()}_field_decision")
        def decide(
            workspace_id: int,
            payload: DecisionIn,
            response: Response,
            expected=Depends(_expected),
            key=Depends(_idempotency_key),
            service=Depends(dependency),
        ):
            result = service.decide(workspace_id, payload, expected, key)
            _etag(response, result["version"])
            return result

    return router
