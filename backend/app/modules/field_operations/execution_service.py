"""Governed field facts and read-only operational projections."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.core.time import utc_now, utc_today
from app.modules.awp.models import ConstraintMapping, ExecutionConstraint, PackageMapping, WorkPackage
from app.modules.basic_data.service import _hash
from app.modules.field_operations.execution_models import (
    FieldConstraintObservation,
    FieldEvent,
    FieldMapping,
    MaterialConsumption,
    ProductionRecord,
    SiteInstruction,
)
from app.modules.field_operations.models import (
    Crew,
    DailyConstructionReport,
    EquipmentUsage,
    FieldCondition,
    FieldEquipmentReference,
    FieldHistory,
    FieldShift,
    LaborUsage,
    Workfront,
)
from app.modules.field_operations.service import FieldOperationsService
from app.modules.procurement_foundation.availability import material_availability
from app.modules.scope_foundation.models import PlanItemScopeLink, ScopeItem

RESOURCES = {
    "production": ProductionRecord,
    "quantity-evidence": ProductionRecord,
    "rework": ProductionRecord,
    "events": FieldEvent,
    "instructions": SiteInstruction,
    "constraints": FieldConstraintObservation,
    "material-consumption": MaterialConsumption,
    "mappings": FieldMapping,
}
SOURCE_MODELS = {
    "WORKFRONT": Workfront,
    "PRODUCTION": ProductionRecord,
    "EVENT": FieldEvent,
    "INSTRUCTION": SiteInstruction,
    "CONSTRAINT": FieldConstraintObservation,
}


def _naive_utc(value):
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


class ExecutionService(FieldOperationsService):
    @staticmethod
    def _execution_catalog(content, category, value):
        if value not in content[category]:
            FieldOperationsService._error(422, "FIELD_CONFIGURED_CATALOG_VALUE_REQUIRED")

    def _execution_sod(self, content, key, *authors):
        if content["separation_of_duties"][key] and self.actor_id in authors:
            self._error(403, "FIELD_INDEPENDENT_DECISION_REQUIRED")

    def _pin_profile(self, profile):
        return {"configuration_id": profile.id, "configuration_hash": profile.content_hash}

    def _provider(self, workspace, pin, expected_kind=None, *, as_of=None):
        if pin is None:
            return None
        data = pin.model_dump() if hasattr(pin, "model_dump") else pin
        kind = data.get("source_type") or data.get("source_entity_type")
        if expected_kind and kind != expected_kind:
            self._error(422, "FIELD_SOURCE_TYPE_MISMATCH")
        return self.source_pin(
            workspace,
            kind,
            data.get("source_id", data.get("source_entity_id")),
            expected_version=data["source_version"],
            expected_hash=data["source_hash"],
            as_of=as_of,
        )

    def _target_reference(self, workspace, kind, identity):
        return self.resolve_reference(workspace, {"target_kind": kind, "target_id": identity})

    def _reference_current(self, workspace, pin):
        fields = {
            key: pin[key]
            for key in ("target_kind", "target_id", "schedule_version_id", "external_id", "source_hash")
            if pin.get(key) is not None
        }
        return self.resolve_reference(workspace, fields)

    def _front(self, workspace, identity, *, active=False):
        row = self._get(Workfront, workspace, identity)
        if active and row.status != "ACTIVE":
            self._error(409, "FIELD_ACTIVE_WORKFRONT_REQUIRED")
        self._reference_current(workspace, row.location_reference)
        return row

    def _date(self, value):
        if value > utc_today():
            self._error(422, "FIELD_FUTURE_OBSERVATION_FORBIDDEN")

    def _observation(self, value):
        instant = _naive_utc(value)
        if instant > utc_now():
            self._error(422, "FIELD_FUTURE_OBSERVATION_FORBIDDEN")
        return instant

    def _report(self, workspace, report_id, shift, front):
        if report_id is None:
            return
        row = self._get(DailyConstructionReport, workspace, report_id)
        if row.shift_id != shift.id or front.id not in row.workfront_ids or row.status != "DRAFT":
            self._error(409, "FIELD_DRAFT_REPORT_AND_SHIFT_REQUIRED")

    def _production_subject(self, workspace, payload, profile, front, observed):
        scope_ref = self._target_reference(workspace, "SCOPE", payload.scope_item_id)
        scope = self._get(ScopeItem, workspace, payload.scope_item_id)
        if scope.unit != payload.uom:
            self._error(422, "FIELD_SCOPE_UOM_MISMATCH")
        plan_ref = self._target_reference(workspace, "PLAN", payload.plan_item_id) if payload.plan_item_id else None
        if payload.plan_item_id:
            link = self.db.scalar(
                self._scoped(PlanItemScopeLink, workspace).where(
                    PlanItemScopeLink.plan_item_id == payload.plan_item_id,
                    PlanItemScopeLink.scope_item_id == scope.id,
                )
            )
            if link is None or link.unit != payload.uom:
                self._error(409, "FIELD_PLAN_SCOPE_RELATION_REQUIRED")
        iwp_id = payload.iwp_id or front.iwp_id
        if front.iwp_id and iwp_id != front.iwp_id:
            self._error(409, "FIELD_WORKFRONT_IWP_MISMATCH")
        iwp_ref = self._target_reference(workspace, "IWP", iwp_id) if iwp_id else None
        iwp = self._get(WorkPackage, workspace, iwp_id) if iwp_id else None
        rules = profile["production_policy"]
        if payload.execution_condition == "IWP_RELEASED":
            if iwp is None and rules["require_released_iwp"]:
                self._error(409, "FIELD_RELEASED_IWP_REQUIRED")
            if iwp and (
                iwp.package_type != "IWP"
                or iwp.release_state != "RELEASED"
                or not iwp.released_at
                or iwp.released_at > observed
            ):
                self._error(409, "FIELD_RELEASED_IWP_REQUIRED")
            if iwp is None:
                self._error(422, "FIELD_NON_IWP_CONDITION_REQUIRED")
        elif payload.execution_condition not in rules["allowed_non_iwp_reasons"] or not payload.exception_reason:
            self._error(422, "FIELD_CONFIGURED_NON_IWP_EXCEPTION_REQUIRED")
        if iwp:
            mappings = list(
                self.db.scalars(
                    self._scoped(PackageMapping, workspace).where(
                        PackageMapping.work_package_id == iwp.id,
                        PackageMapping.status == "ACTIVE",
                    )
                )
            )
            scopes = {item.target_id for item in mappings if item.target_kind == "SCOPE"}
            for item in mappings:
                if item.target_kind == "PLAN":
                    scopes.update(
                        self.db.scalars(
                            self._scoped(PlanItemScopeLink, workspace)
                            .where(
                                PlanItemScopeLink.plan_item_id == item.target_id,
                            )
                            .with_only_columns(PlanItemScopeLink.scope_item_id)
                        )
                    )
            if scope.id not in scopes:
                self._error(409, "FIELD_IWP_SCOPE_RELATION_REQUIRED")
            if front.cwa_id and iwp.cwa_id != front.cwa_id:
                self._error(409, "FIELD_IWP_CWA_MISMATCH")
        engineering = self._provider(workspace, payload.engineering_reference, "IFC_RELEASE", as_of=observed)
        if rules["require_engineering_ifc"] and engineering is None:
            self._error(409, "FIELD_VALID_IFC_REFERENCE_REQUIRED")
        if engineering:
            known = datetime.fromisoformat(engineering["observed_at"])
            if _naive_utc(known) > observed:
                self._error(409, "FIELD_IFC_RELEASE_AFTER_EXECUTION")
        material = self._provider(workspace, payload.material_reference, "MATERIAL_ALLOCATION", as_of=observed)
        if material and material["source_entity_type"] not in {"MATERIAL_ITEM", "MATERIAL_ALLOCATION"}:
            self._error(422, "FIELD_MATERIAL_SOURCE_REQUIRED")
        if material and material["source_entity_type"] == "MATERIAL_ALLOCATION":
            facts = material["facts"]
            if facts.get("work_package_id") != iwp_id:
                self._error(409, "FIELD_MATERIAL_ALLOCATION_IWP_MISMATCH")
        if rules["require_material_ready"]:
            if not iwp_id or material is None:
                self._error(409, "FIELD_MATERIAL_READY_REQUIRED")
            availability = material_availability(self.db, self.tenant_id, workspace, iwp_id, observed.date())
            if not availability or availability.get("status") != "READY":
                self._error(409, "FIELD_MATERIAL_READY_REQUIRED")
        return scope_ref, plan_ref, iwp_ref, iwp_id, engineering, material

    def create_production(self, workspace, payload, key):
        duty = "rework.record" if payload.production_type == "REWORKED" else "production.record"
        self._ready(workspace, duty)

        def apply():
            _, profile = self._ready(workspace, duty)
            content = profile.content_json
            self._execution_catalog(content, "production_types", payload.production_type)
            shift, front = self._shift_context(
                workspace, payload.shift_id, payload.workfront_id, correction=bool(payload.supersedes_id)
            )
            self._report(workspace, payload.report_id, shift, front)
            if payload.supersedes_id:
                correction_report = (
                    self._get(DailyConstructionReport, workspace, payload.report_id) if payload.report_id else None
                )
                if correction_report is None or not correction_report.supersedes_id:
                    self._error(409, "FIELD_PRODUCTION_CORRECTION_REPORT_REQUIRED")
            observed = self._observation(payload.observed_at)
            if not shift.start_time <= observed <= shift.end_time:
                self._error(422, "FIELD_OBSERVATION_OUTSIDE_SHIFT")
            refs = self._production_subject(workspace, payload, content, front, observed)
            scope_ref, plan_ref, iwp_ref, iwp_id, engineering, material = refs
            location = (
                self.resolve_reference(workspace, payload.location_reference)
                if payload.location_reference
                else front.location_reference
            )
            if any(
                location.get(field) != front.location_reference.get(field) for field in ("target_kind", "target_id")
            ):
                self._error(409, "FIELD_PRODUCTION_LOCATION_MISMATCH")
            document = self._document(workspace, payload.document_reference)
            revision = 1
            if payload.supersedes_id:
                old = self._get(ProductionRecord, workspace, payload.supersedes_id, lock=True)
                if (
                    old.status != "VERIFIED"
                    or old.shift_id != shift.id
                    or old.workfront_id != front.id
                    or old.production_code != payload.production_code.upper()
                    or (old.scope_item_id, old.plan_item_id, old.iwp_id, old.uom, old.production_type)
                    != (payload.scope_item_id, payload.plan_item_id, iwp_id, payload.uom, payload.production_type)
                ):
                    self._error(409, "FIELD_PRODUCTION_SUCCESSOR_MISMATCH")
                if self.db.scalar(
                    self._scoped(ProductionRecord, workspace)
                    .where(
                        ProductionRecord.supersedes_id == old.id,
                        ProductionRecord.status != "REJECTED",
                    )
                    .limit(1)
                ):
                    self._error(409, "FIELD_PRODUCTION_SUCCESSOR_EXISTS")
                revision = old.revision + 1
            if payload.original_production_id:
                old = self._get(ProductionRecord, workspace, payload.original_production_id)
                self._execution_catalog(content, "rework_reasons", payload.rework_reason)
                if old.status != "VERIFIED" or old.scope_item_id != payload.scope_item_id or old.uom != payload.uom:
                    self._error(409, "FIELD_REWORK_ORIGINAL_INVALID")
            evidence_key = _hash(
                {
                    "scope": payload.scope_item_id,
                    "plan": payload.plan_item_id,
                    "iwp": iwp_id,
                    "workfront": front.id,
                    "shift": shift.id,
                    "document": document,
                    "production_type": payload.production_type,
                    "original_production_id": payload.original_production_id,
                }
            )
            duplicate = self.db.scalar(
                self._scoped(ProductionRecord, workspace)
                .where(
                    ProductionRecord.evidence_key == evidence_key,
                    ProductionRecord.revision == revision,
                )
                .limit(1)
            )
            if duplicate:
                self._error(409, "FIELD_DUPLICATE_QUANTITY_EVIDENCE")
            values = payload.model_dump(
                exclude={
                    "reason",
                    "production_code",
                    "observed_at",
                    "location_reference",
                    "engineering_reference",
                    "material_reference",
                    "document_reference",
                    "iwp_id",
                }
            )
            row = self._new(
                ProductionRecord,
                workspace,
                **values,
                revision=revision,
                production_code=payload.production_code.upper(),
                observed_at=observed,
                location_reference=location,
                scope_reference=scope_ref,
                plan_reference=plan_ref,
                iwp_reference=iwp_ref,
                iwp_id=iwp_id,
                engineering_reference=engineering,
                material_reference=material,
                document_reference=document,
                evidence_key=evidence_key,
                **self._pin_profile(profile),
            )
            return self._record(row, "PRODUCTION_RECORDED", payload.reason)

        return self._write("production.record", workspace, payload, key, apply)

    def production_action(self, workspace, identity, payload, expected, key):
        self._read_project(workspace)
        source = self._get(ProductionRecord, workspace, identity)
        self._ready(workspace, "rework.approve" if source.production_type == "REWORKED" else "production.verify")

        def apply():
            row = self._get(ProductionRecord, workspace, identity, lock=True)
            duty = "rework.approve" if row.production_type == "REWORKED" else "production.verify"
            self._ready(workspace, duty)
            self._version(row.version, expected)
            if row.status != "RECORDED":
                self._error(409, "FIELD_PRODUCTION_TRANSITION_INVALID")
            shift, _ = self._shift_context(
                workspace, row.shift_id, row.workfront_id, correction=bool(row.supersedes_id)
            )
            if shift.status != "OPEN":
                self._error(409, "FIELD_OPEN_SHIFT_REQUIRED")
            profile = self._pinned_profile(row)
            self._execution_sod(
                profile,
                "rework_author_cannot_approve"
                if row.production_type == "REWORKED"
                else "production_author_cannot_verify",
                row.created_by,
            )
            if payload.action == "verify":
                self._reference_current(workspace, row.scope_reference)
                if row.plan_reference:
                    self._reference_current(workspace, row.plan_reference)
                if row.iwp_reference:
                    self._reference_current(workspace, row.iwp_reference)
                    iwp = self._get(WorkPackage, workspace, row.iwp_id)
                    if row.execution_condition == "IWP_RELEASED" and iwp.release_state != "RELEASED":
                        self._error(409, "FIELD_RELEASED_IWP_REQUIRED")
                self._check_document(workspace, row.document_reference)
                self._provider(workspace, row.engineering_reference, as_of=row.observed_at)
                self._provider(workspace, row.material_reference, "MATERIAL_ALLOCATION", as_of=row.observed_at)
            row.status = "VERIFIED" if payload.action == "verify" else "REJECTED"
            row.verified_by, row.verified_at = self.actor_id, utc_now()
            return self._record(row, f"PRODUCTION_{row.status}", payload.reason, changed=True)

        return self._write("production.verify", workspace, payload, key, apply, identity, expected)

    def create_event(self, workspace, payload, key):
        self._ready(workspace, "event.record")

        def apply():
            _, profile = self._ready(workspace, "event.record")
            self._execution_catalog(profile.content_json, "field_event_types", payload.event_type)
            front = self._front(workspace, payload.workfront_id, active=True)
            if payload.shift_id:
                self._shift_context(workspace, payload.shift_id, front.id)
            values = payload.model_dump(exclude={"reason", "observed_at", "document_reference", "event_code"})
            row = self._new(
                FieldEvent,
                workspace,
                **values,
                event_code=payload.event_code.upper(),
                observed_at=self._observation(payload.observed_at),
                document_reference=self._document(workspace, payload.document_reference),
                **self._pin_profile(profile),
            )
            return self._record(row, "FIELD_EVENT_RECORDED", payload.reason)

        return self._write("event.record", workspace, payload, key, apply)

    def event_action(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "event.classify")

        def apply():
            self._ready(workspace, "event.classify")
            row = self._get(FieldEvent, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.shift_id and self.db.scalar(
                self._scoped(DailyConstructionReport, workspace)
                .where(
                    DailyConstructionReport.shift_id == row.shift_id,
                    DailyConstructionReport.status.in_(("SUBMITTED", "REVIEWED")),
                )
                .limit(1)
            ):
                self._error(409, "FIELD_OPERATIONS_REPORT_FACTS_FROZEN")
            states = {"review": ("RECORDED", "REVIEWED"), "close": ("REVIEWED", "CLOSED")}
            old, new = states[payload.action]
            if row.status != old:
                self._error(409, "FIELD_EVENT_TRANSITION_INVALID")
            self._check_document(workspace, row.document_reference)
            row.status = new
            if new == "REVIEWED":
                row.reviewed_by, row.reviewed_at = self.actor_id, utc_now()
            return self._record(row, f"FIELD_EVENT_{new}", payload.reason, changed=True)

        return self._write("event.transition", workspace, payload, key, apply, identity, expected)

    def create_instruction(self, workspace, payload, key):
        self._ready(workspace, "instruction.record")

        def apply():
            _, profile = self._ready(workspace, "instruction.record")
            self._execution_catalog(profile.content_json, "instruction_types", payload.instruction_type)
            front = self._front(workspace, payload.workfront_id, active=True)
            self._date(payload.instruction_date)
            if payload.scope_item_id:
                self._target_reference(workspace, "SCOPE", payload.scope_item_id)
            if payload.iwp_id:
                self._target_reference(workspace, "IWP", payload.iwp_id)
                if front.iwp_id and front.iwp_id != payload.iwp_id:
                    self._error(409, "FIELD_WORKFRONT_IWP_MISMATCH")
            values = payload.model_dump(exclude={"reason", "document_reference", "instruction_number"})
            row = self._new(
                SiteInstruction,
                workspace,
                **values,
                instruction_number=payload.instruction_number.upper(),
                document_reference=self._document(workspace, payload.document_reference),
                **self._pin_profile(profile),
            )
            return self._record(row, "SITE_INSTRUCTION_PREPARED", payload.reason)

        return self._write("instruction.record", workspace, payload, key, apply)

    def instruction_action(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "instruction.issue")

        def apply():
            self._ready(workspace, "instruction.issue")
            row = self._get(SiteInstruction, workspace, identity, lock=True)
            self._version(row.version, expected)
            states = {
                "issue": ("DRAFT", "ISSUED"),
                "acknowledge": ("ISSUED", "ACKNOWLEDGED"),
                "close": ("ACKNOWLEDGED", "CLOSED"),
            }
            old, new = states[payload.action]
            if row.status != old:
                self._error(409, "FIELD_INSTRUCTION_TRANSITION_INVALID")
            self._check_document(workspace, row.document_reference)
            if new == "ISSUED":
                self._execution_sod(self._pinned_profile(row), "instruction_author_cannot_issue", row.created_by)
                row.issued_by, row.issued_at = self.actor_id, utc_now()
            if new == "ACKNOWLEDGED":
                row.acknowledged_by, row.acknowledged_at = self.actor_id, utc_now()
            row.status = new
            return self._record(row, f"SITE_INSTRUCTION_{new}", payload.reason, changed=True)

        return self._write("instruction.transition", workspace, payload, key, apply, identity, expected)

    def create_constraint(self, workspace, payload, key):
        self._ready(workspace, "constraint.record")

        def apply():
            _, profile = self._ready(workspace, "constraint.record")
            self._execution_catalog(profile.content_json, "constraint_observation_types", payload.constraint_type)
            front = self._front(workspace, payload.workfront_id, active=True)
            self._date(payload.observation_date)
            if payload.iwp_id:
                self._target_reference(workspace, "IWP", payload.iwp_id)
                if front.iwp_id and front.iwp_id != payload.iwp_id:
                    self._error(409, "FIELD_WORKFRONT_IWP_MISMATCH")
            values = payload.model_dump(exclude={"reason", "document_reference", "observation_code"})
            row = self._new(
                FieldConstraintObservation,
                workspace,
                **values,
                observation_code=payload.observation_code.upper(),
                document_reference=self._document(workspace, payload.document_reference),
                **self._pin_profile(profile),
            )
            return self._record(row, "CONSTRAINT_OBSERVATION_REPORTED", payload.reason)

        return self._write("constraint.record", workspace, payload, key, apply)

    def constraint_action(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "constraint.verify")

        def apply():
            self._ready(workspace, "constraint.verify")
            row = self._get(FieldConstraintObservation, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "REPORTED":
                self._error(409, "FIELD_OBSERVATION_TRANSITION_INVALID")
            self._check_document(workspace, row.document_reference)
            row.status = "VERIFIED" if payload.action == "verify" else "REJECTED"
            row.verified_by, row.verified_at = self.actor_id, utc_now()
            return self._record(row, f"CONSTRAINT_OBSERVATION_{row.status}", payload.reason, changed=True)

        return self._write("constraint.verify", workspace, payload, key, apply, identity, expected)

    def _material_consumption_context(self, production, shift, payload, facts):
        if (
            facts.get("material_item_id") != payload.material_item_id
            or facts.get("work_package_id") != production.iwp_id
            or facts.get("uom") != payload.uom
            or payload.consumption_date < shift.shift_date
        ):
            self._error(409, "FIELD_MATERIAL_CONSUMPTION_CONTEXT_INVALID")

    def create_material_consumption(self, workspace, payload, key):
        self._ready(workspace, "material.record")

        def apply():
            _, profile = self._ready(workspace, "material.record")
            production = self._get(ProductionRecord, workspace, payload.production_record_id)
            shift, _ = self._shift_context(workspace, production.shift_id, production.workfront_id)
            self._date(payload.consumption_date)
            allocation = self._provider(workspace, payload.allocation_reference, "MATERIAL_ALLOCATION")
            facts = allocation["facts"]
            self._material_consumption_context(production, shift, payload, facts)
            consumed = self.db.scalar(
                self._scoped(MaterialConsumption, workspace)
                .where(
                    MaterialConsumption.allocation_id == allocation["source_entity_id"],
                )
                .with_only_columns(func.coalesce(func.sum(MaterialConsumption.quantity), 0))
            )
            if consumed + payload.quantity > Decimal(str(facts["quantity"])):
                self._error(409, "FIELD_MATERIAL_CONSUMPTION_EXCEEDS_ALLOCATION")
            values = payload.model_dump(
                exclude={"reason", "allocation_reference", "document_reference", "consumption_code"}
            )
            row = self._new(
                MaterialConsumption,
                workspace,
                **values,
                consumption_code=payload.consumption_code.upper(),
                allocation_id=allocation["source_entity_id"],
                workfront_id=production.workfront_id,
                allocation_reference=allocation,
                document_reference=self._document(workspace, payload.document_reference),
                **self._pin_profile(profile),
            )
            return self._record(row, "MATERIAL_CONSUMPTION_RECORDED", payload.reason)

        return self._write("material.record", workspace, payload, key, apply)

    def record_mapping(self, workspace, payload, expected, key):
        self._ready(workspace, "mapping.edit")

        def apply():
            self._ready(workspace, "mapping.edit")
            self._get(SOURCE_MODELS[payload.source_kind], workspace, payload.source_id, lock=True)
            pin = self.resolve_reference(workspace, payload.target_reference)
            prior = self.db.scalar(
                self._scoped(FieldMapping, workspace)
                .where(
                    FieldMapping.source_kind == payload.source_kind,
                    FieldMapping.source_id == payload.source_id,
                )
                .order_by(FieldMapping.version.desc())
                .limit(1)
            )
            self._version(prior.version if prior else 0, expected)
            row = self._new(
                FieldMapping,
                workspace,
                source_kind=payload.source_kind,
                source_id=payload.source_id,
                target_kind=payload.target_reference.target_kind,
                target_reference=pin,
                action=payload.action,
                reason=payload.reason,
                version=(prior.version if prior else 0) + 1,
                source_hash=_hash(
                    {"source": payload.source_kind, "id": payload.source_id, "target": pin, "action": payload.action}
                ),
            )
            return self._record(row, "FIELD_MAPPING_RECORDED", payload.reason)

        return self._write("mapping.record", workspace, payload, key, apply, expected=expected)

    def execution_collection(
        self,
        workspace,
        resource,
        *,
        limit=50,
        after_id=0,
        workfront_id=None,
        status=None,
        source_kind=None,
        source_id=None,
    ):
        self._read_project(workspace)
        model = RESOURCES[resource]
        query = self._scoped(model, workspace).where(model.id > after_id)
        stream_version = None
        if resource == "mappings":
            if (source_kind is None) != (source_id is None):
                self._error(422, "FIELD_MAPPING_SOURCE_INCOMPLETE")
            if source_kind is not None:
                if source_kind not in SOURCE_MODELS:
                    self._error(422, "FIELD_MAPPING_SOURCE_UNSUPPORTED")
                self._get(SOURCE_MODELS[source_kind], workspace, source_id)
                query = query.where(FieldMapping.source_kind == source_kind, FieldMapping.source_id == source_id)
                stream_version = self.db.scalar(
                    self._scoped(FieldMapping, workspace)
                    .where(
                        FieldMapping.source_kind == source_kind,
                        FieldMapping.source_id == source_id,
                    )
                    .with_only_columns(func.coalesce(func.max(FieldMapping.version), 0))
                )
        if resource == "quantity-evidence":
            query = query.where(ProductionRecord.production_type == "INSTALLED")
        elif resource == "rework":
            query = query.where(ProductionRecord.production_type == "REWORKED")
        if workfront_id is not None and hasattr(model, "workfront_id"):
            self._get(Workfront, workspace, workfront_id)
            query = query.where(model.workfront_id == workfront_id)
        if status is not None and hasattr(model, "status"):
            query = query.where(model.status == status)
        items = list(self.db.scalars(query.order_by(model.id).limit(limit + 1)))
        result = {
            "items": [self._redact(workspace, self._out(row)) for row in items[:limit]],
            "next_cursor": items[limit - 1].id if len(items) > limit else None,
        }
        if stream_version is not None:
            result["version"] = stream_version
        return result

    def execution_detail(self, workspace, resource, identity):
        self._read_project(workspace)
        row = self._get(RESOURCES[resource], workspace, identity)
        if (
            resource == "quantity-evidence"
            and row.production_type != "INSTALLED"
            or resource == "rework"
            and row.production_type != "REWORKED"
        ):
            self._error(404, "FIELD_RECORD_NOT_FOUND")
        return self._redact(workspace, self._out(row))

    def dashboard(self, workspace):
        self._read_project(workspace)
        counts = {}
        for label, model in (
            ("workfronts", Workfront),
            ("shifts", FieldShift),
            ("daily_reports", DailyConstructionReport),
            ("production", ProductionRecord),
            ("events", FieldEvent),
            ("constraints", FieldConstraintObservation),
        ):
            query = self._scoped(model, workspace).with_only_columns(model.status, func.count()).group_by(model.status)
            counts[label] = dict(self.db.execute(query).all())
        successor = aliased(ProductionRecord)
        current = (
            ~select(successor.id)
            .where(
                successor.supersedes_id == ProductionRecord.id,
                successor.tenant_id == self.tenant_id,
                successor.project_workspace_id == workspace,
                successor.status == "VERIFIED",
            )
            .exists()
        )
        quantities = self.db.execute(
            self._scoped(ProductionRecord, workspace)
            .where(
                ProductionRecord.status == "VERIFIED",
                ProductionRecord.production_type != "REWORKED",
                current,
            )
            .with_only_columns(ProductionRecord.uom, func.sum(ProductionRecord.quantity))
            .group_by(ProductionRecord.uom)
        ).all()
        labor_successor = aliased(LaborUsage)
        equipment_successor = aliased(EquipmentUsage)
        labor_hours = self.db.scalar(
            self._scoped(LaborUsage, workspace)
            .where(
                ~select(labor_successor.id)
                .where(
                    labor_successor.supersedes_id == LaborUsage.id,
                    labor_successor.tenant_id == self.tenant_id,
                    labor_successor.project_workspace_id == workspace,
                )
                .exists()
            )
            .with_only_columns(func.coalesce(func.sum(LaborUsage.regular_hours + LaborUsage.overtime_hours), 0))
        )
        equipment_hours = self.db.scalar(
            self._scoped(EquipmentUsage, workspace)
            .where(
                ~select(equipment_successor.id)
                .where(
                    equipment_successor.supersedes_id == EquipmentUsage.id,
                    equipment_successor.tenant_id == self.tenant_id,
                    equipment_successor.project_workspace_id == workspace,
                )
                .exists()
            )
            .with_only_columns(func.coalesce(func.sum(EquipmentUsage.operating_hours), 0))
        )
        return {
            "counts": counts,
            "verified_production_by_uom": {uom: str(amount) for uom, amount in quantities},
            "labor_hours": str(labor_hours),
            "equipment_operating_hours": str(equipment_hours),
            "authority": "FIELD_FACTS_ONLY",
            "as_of": utc_now().isoformat(),
        }

    def readiness(self, workspace, workfront_id, as_of=None):
        project = self._read_project(workspace)
        profile = self._field_profile(project)
        if profile is None:
            self._error(409, "FIELD_PUBLISHED_PROFILE_REQUIRED")
        front = self._get(Workfront, workspace, workfront_id)
        checks, missing = [], []
        stale, broken = False, False
        requirements = profile.content_json["readiness_requirements"]
        day = as_of or utc_today()
        self._date(day)

        def add(name, ready, detail=None, required=True):
            checks.append({"check": name, "ready": bool(ready), "required": required, "detail": detail})
            if required and not ready:
                missing.append(name)

        add("workfront", front.status == "ACTIVE", front.status)
        link_rows = list(
            self.db.scalars(
                self._scoped(FieldMapping, workspace)
                .where(
                    FieldMapping.source_kind == "WORKFRONT",
                    FieldMapping.source_id == front.id,
                )
                .order_by(FieldMapping.version, FieldMapping.id)
            )
        )
        latest_links = {}
        for link in link_rows:
            pin = link.target_reference
            latest_links[
                (link.target_kind, pin.get("target_id"), pin.get("schedule_version_id"), pin.get("external_id"))
            ] = link
        references = [
            *front.source_references,
            *(item.target_reference for item in latest_links.values() if item.action == "SET"),
        ]
        latest_production = self.db.scalar(
            self._scoped(ProductionRecord, workspace)
            .where(
                ProductionRecord.workfront_id == front.id,
                ProductionRecord.status == "VERIFIED",
                ProductionRecord.observed_at < datetime.combine(day + timedelta(days=1), datetime.min.time()),
            )
            .order_by(ProductionRecord.observed_at.desc(), ProductionRecord.id.desc())
            .limit(1)
        )
        if latest_production:
            references.extend(
                pin for pin in (latest_production.engineering_reference, latest_production.material_reference) if pin
            )
        try:
            self._reference_current(workspace, front.location_reference)
            for pin in references:
                if pin.get("source_entity_type") in {"IFC_RELEASE", "MATERIAL_ITEM", "MATERIAL_ALLOCATION"}:
                    self._provider(workspace, pin)
                elif pin.get("target_kind"):
                    self._reference_current(workspace, pin)
        except HTTPException as error:
            broken = error.status_code == 404
            stale = not broken
            add("source_references", False, error.detail)
        iwp = self._get(WorkPackage, workspace, front.iwp_id) if front.iwp_id else None
        add(
            "iwp_release",
            bool(iwp and iwp.release_state == "RELEASED" and iwp.released_at and iwp.released_at.date() <= day),
            iwp.release_state if iwp else "NO_IWP",
            requirements["iwp_release"],
        )
        engineering = [
            pin for pin in references if pin.get("source_entity_type", pin.get("target_kind")) == "IFC_RELEASE"
        ]
        add(
            "engineering_ifc",
            bool(engineering),
            "PINNED" if engineering else "NOT_LINKED",
            requirements["engineering_ifc"],
        )
        availability = material_availability(self.db, self.tenant_id, workspace, iwp.id, day) if iwp else None
        material_ready = bool(availability and availability.get("status") == "READY")
        if availability and requirements["materials"]:
            stale = stale or availability.get("status") == "STALE"
            broken = broken or availability.get("status") == "BROKEN_REFERENCE"
        add("materials", material_ready, availability, requirements["materials"])
        crews = self.db.scalar(
            self._scoped(Crew, workspace).where(Crew.status == "ACTIVE").with_only_columns(func.count())
        )
        add("crew", crews > 0, crews, requirements["crew"])
        equipment = self.db.scalar(
            self._scoped(FieldEquipmentReference, workspace)
            .where(FieldEquipmentReference.status == "AVAILABLE")
            .with_only_columns(func.count())
        )
        add("equipment", equipment > 0, equipment, requirements["equipment"])
        conditions = list(
            self.db.scalars(
                self._scoped(FieldCondition, workspace)
                .where(
                    FieldCondition.workfront_id == front.id,
                    FieldCondition.condition_date <= day,
                )
                .order_by(FieldCondition.condition_date.desc(), FieldCondition.id.desc())
                .limit(1)
            )
        )
        add(
            "site_access",
            bool(conditions and conditions[0].access_condition == "AVAILABLE"),
            conditions[0].access_condition if conditions else "NOT_RECORDED",
            requirements["site_access"],
        )
        observations = list(
            self.db.scalars(
                self._scoped(FieldConstraintObservation, workspace).where(
                    FieldConstraintObservation.workfront_id == front.id,
                    FieldConstraintObservation.status.in_(["REPORTED", "VERIFIED"]),
                )
            )
        )
        add(
            "field_constraints",
            not any(row.severity in {"HIGH", "CRITICAL"} for row in observations),
            [{"id": row.id, "severity": row.severity, "status": row.status} for row in observations],
        )
        if iwp:
            links = (
                self._scoped(ConstraintMapping, workspace)
                .where(
                    ConstraintMapping.target_kind == "PACKAGE",
                    ConstraintMapping.target_id == iwp.id,
                    ConstraintMapping.status == "ACTIVE",
                )
                .with_only_columns(ConstraintMapping.constraint_id)
            )
            constraints = list(
                self.db.scalars(
                    self._scoped(ExecutionConstraint, workspace).where(
                        ExecutionConstraint.id.in_(links),
                        ExecutionConstraint.blocking.is_(True),
                        ExecutionConstraint.status.not_in(["CLEARED", "WAIVED"]),
                    )
                )
            )
        else:
            constraints = []
        add("awp_constraints", not constraints, [row.id for row in constraints])
        instructions = self.db.scalar(
            self._scoped(SiteInstruction, workspace)
            .where(
                SiteInstruction.workfront_id == front.id,
                SiteInstruction.status.in_(["ISSUED", "ACKNOWLEDGED", "CLOSED"]),
            )
            .with_only_columns(func.count())
        )
        add("instructions", instructions > 0, instructions, requirements["instructions"])
        required = [check for check in checks if check["required"]]
        state = (
            "BROKEN_REFERENCE"
            if broken
            else "STALE"
            if stale
            else "READY"
            if not missing
            else ("PARTIALLY_READY" if any(check["ready"] for check in required) else "NOT_READY")
        )
        return {
            "workfront_id": front.id,
            "assessment_date": day.isoformat(),
            "state": state,
            "checks": checks,
            "missing": missing,
            "profile_id": profile.id,
            "profile_hash": profile.content_hash,
            "awp_release_changed": False,
        }

    def lookahead(self, workspace, *, horizon_days=None, as_of=None):
        project = self._read_project(workspace)
        profile = self._field_profile(project)
        if profile is None:
            self._error(409, "FIELD_PUBLISHED_PROFILE_REQUIRED")
        start = as_of or utc_today()
        self._date(start)
        finish = start + timedelta(days=horizon_days or profile.content_json["lookahead_days"])
        fronts = list(
            self.db.scalars(
                self._scoped(Workfront, workspace)
                .where(
                    Workfront.planned_start <= finish,
                    Workfront.planned_finish >= start,
                    Workfront.status.in_(["PLANNED", "ACTIVE", "SUSPENDED"]),
                )
                .order_by(Workfront.planned_start, Workfront.id)
                .limit(200)
            )
        )
        shifts = list(
            self.db.scalars(
                self._scoped(FieldShift, workspace)
                .where(
                    FieldShift.shift_date.between(start, finish),
                )
                .order_by(FieldShift.shift_date, FieldShift.id)
                .limit(200)
            )
        )
        events = list(
            self.db.scalars(
                self._scoped(FieldEvent, workspace)
                .where(
                    FieldEvent.observed_at >= datetime.combine(start, datetime.min.time()),
                    FieldEvent.status != "CLOSED",
                )
                .order_by(FieldEvent.observed_at, FieldEvent.id)
                .limit(200)
            )
        )
        released_iwps = list(
            self.db.scalars(
                self._scoped(WorkPackage, workspace)
                .where(
                    WorkPackage.package_type == "IWP",
                    WorkPackage.release_state == "RELEASED",
                    WorkPackage.released_at.is_not(None),
                )
                .order_by(WorkPackage.id)
                .limit(200)
            )
        )
        crews = list(
            self.db.scalars(self._scoped(Crew, workspace).where(Crew.status == "ACTIVE").order_by(Crew.id).limit(200))
        )
        equipment = list(
            self.db.scalars(
                self._scoped(FieldEquipmentReference, workspace)
                .where(FieldEquipmentReference.status == "AVAILABLE")
                .order_by(FieldEquipmentReference.id)
                .limit(200)
            )
        )
        production = list(
            self.db.scalars(
                self._scoped(ProductionRecord, workspace)
                .where(
                    ProductionRecord.planned_quantity.is_not(None),
                    ProductionRecord.observed_at >= datetime.combine(start, datetime.min.time()),
                    ProductionRecord.observed_at < datetime.combine(finish + timedelta(days=1), datetime.min.time()),
                )
                .order_by(ProductionRecord.observed_at, ProductionRecord.id)
                .limit(200)
            )
        )
        return {
            "start": start.isoformat(),
            "end": finish.isoformat(),
            "workfronts": [
                {
                    "id": row.id,
                    "title": row.title,
                    "status": row.status,
                    "planned_start": row.planned_start.isoformat(),
                    "planned_finish": row.planned_finish.isoformat(),
                    "readiness": self.readiness(workspace, row.id, start),
                }
                for row in fronts
            ],
            "shifts": [self._out(row) for row in shifts],
            "events": [self._redact(workspace, self._out(row)) for row in events],
            "released_iwps": [
                {
                    "id": row.id,
                    "package_code": row.package_code,
                    "release_state": row.release_state,
                    "released_at": row.released_at.isoformat(),
                }
                for row in released_iwps
            ],
            "crew_availability": [self._out(row) for row in crews],
            "equipment_availability": [self._out(row) for row in equipment],
            "production_control": [
                {
                    "id": row.id,
                    "shift_id": row.shift_id,
                    "workfront_id": row.workfront_id,
                    "scope_item_id": row.scope_item_id,
                    "uom": row.uom,
                    "planned_quantity": str(row.planned_quantity),
                    "actual_quantity": str(row.quantity),
                    "variance": str(row.quantity - row.planned_quantity),
                    "reason": row.variance_reason,
                    "status": row.status,
                }
                for row in production
            ],
            "planning_scope": "SHORT_INTERVAL_OBSERVATIONS_NOT_RESOURCE_LOADED_SCHEDULE",
            "schedule_authority": "P6_UNCHANGED",
            "records_limited_to": 200,
        }

    def trace(self, workspace, entity_type, identity):
        self._read_project(workspace)
        if entity_type not in SOURCE_MODELS:
            self._error(422, "FIELD_TRACE_ENTITY_UNSUPPORTED")
        row = self._get(SOURCE_MODELS[entity_type], workspace, identity)
        history = list(
            self.db.scalars(
                self._scoped(FieldHistory, workspace)
                .where(
                    FieldHistory.entity_type == type(row).__name__,
                    FieldHistory.entity_id == row.id,
                )
                .order_by(FieldHistory.id)
                .limit(200)
            )
        )
        mappings = list(
            self.db.scalars(
                self._scoped(FieldMapping, workspace)
                .where(
                    FieldMapping.source_kind == entity_type,
                    FieldMapping.source_id == row.id,
                )
                .order_by(FieldMapping.id)
                .limit(200)
            )
        )
        return {
            "entity_type": entity_type,
            "entity": self._redact(workspace, self._out(row)),
            "history": [self._redact(workspace, self._out(item)) for item in history],
            "mappings": [self._out(item) for item in mappings],
            "downstream_write": False,
        }
