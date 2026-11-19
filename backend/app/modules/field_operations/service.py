"""Core field facts with independent duties and immutable approved observations."""

from copy import deepcopy
from datetime import UTC
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import inspect, select

from app.core.time import utc_now, utc_today
from app.domain.models import SecurityEvent, UserAccount, WorkspaceModuleSetting
from app.modules.awp.models import WorkPackage
from app.modules.basic_data.service import _hash, _json
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.field_operations.models import (
    Crew,
    DailyConstructionReport,
    EquipmentUsage,
    FieldClosure,
    FieldCondition,
    FieldEquipmentReference,
    FieldHistory,
    FieldShift,
    LaborUsage,
    Workfront,
)
from app.modules.field_operations.permissions import ACTIONS, require_field_schema
from app.modules.field_operations.profiles import FieldProfilesMixin
from app.modules.field_operations.sources import FieldSourceMixin
from app.modules.procurement_foundation.sourcing_models import ProcurementVendor
from app.modules.scope_foundation.service import ScopeFoundationService

COLLECTIONS = {
    "workfronts": Workfront,
    "shifts": FieldShift,
    "daily-reports": DailyConstructionReport,
    "crews": Crew,
    "equipment-references": FieldEquipmentReference,
    "labor": LaborUsage,
    "equipment": EquipmentUsage,
    "conditions": FieldCondition,
    "history": FieldHistory,
}


def field_content(row):
    """Stable decimal normalization; source identity is carried separately in pins."""
    result = {}
    for column in row.__table__.columns:
        if column.key not in {
            "id",
            "source_hash",
            "version",
            "status",
            "created_at",
            "updated_at",
            "updated_by",
            "approved_by",
            "approved_at",
            "submitted_by",
            "submitted_at",
            "reviewed_by",
            "reviewed_at",
            "verified_by",
            "verified_at",
            "issued_by",
            "issued_at",
            "closed_by",
            "closed_at",
        }:
            value = getattr(row, column.key)
            result[column.key] = format(value, ".8f") if isinstance(value, Decimal) else value
    return _json(result)


def field_hash(row):
    return _hash(field_content(row))


record_hash = field_hash


class FieldOperationsService(FieldSourceMixin, FieldProfilesMixin, ScopeFoundationService):
    def _require_schema(self):
        if not getattr(self, "_field_schema_confirmed", False):
            require_field_schema(self.db)
            self._field_schema_confirmed = True

    def _project(self, workspace):
        self._require_schema()
        project = super()._project(workspace)
        if project.status.lower() != "active":
            self._error(409, "FIELD_OPERATIONS_ACTIVE_PROJECT_REQUIRED")
        keys = {"field-operations", "field-operations-manager", "field_operations"}
        data = project.defaults_json or {}
        metadata = {**data, **(data.get("_enterprise") or {})}
        settings = dict(
            self.db.execute(
                select(WorkspaceModuleSetting.module_key, WorkspaceModuleSetting.enabled).where(
                    WorkspaceModuleSetting.tenant_id == self.tenant_id,
                    WorkspaceModuleSetting.workspace_id == workspace,
                    WorkspaceModuleSetting.module_key.in_(keys),
                )
            ).all()
        )
        if False in settings.values() or not (
            keys.intersection(metadata.get("enabled_modules") or []) or any(settings.values())
        ):
            self._error(409, "FIELD_OPERATIONS_MODULE_NOT_ENABLED")
        return project

    def _permission(self, action, workspace=None):
        if self.access_context is None:
            return
        if action not in self._permission_contexts:
            self._permission_contexts[action] = require_enterprise_permission(
                self.db,
                self.tenant_id,
                self.actor_id,
                f"field_operations.{action}",
                bootstrap=False,
            )
        access = self._permission_contexts[action]
        if action.startswith("admin.") and not access.organization_wide:
            self._error(403, "FIELD_OPERATIONS_ORGANIZATION_SCOPE_REQUIRED")
        if workspace is not None:
            self._scope(workspace, access)

    def allowed_actions(self, workspace=None):
        result = []
        for action in ACTIONS:
            try:
                self._permission(action, workspace)
                result.append(action)
            except HTTPException as error:
                if error.status_code != 403:
                    raise
        return result

    def _read_project(self, workspace):
        project = self._project(workspace)
        self._permission("read", project)
        return project

    def _ready(self, workspace, action):
        project = self._project(workspace)
        self._permission(action, project)
        operational = self._operational()
        operational._operable(workspace)
        operational._policy_ready(project, operational._effective_profile(project))
        profile = self._field_profile(project)
        if profile is None:
            self._error(409, "FIELD_OPERATIONS_PUBLISHED_PROFILE_REQUIRED")
        return project, profile

    def _scoped(self, model, workspace):
        return select(model).where(model.tenant_id == self.tenant_id, model.project_workspace_id == workspace)

    def _get(self, model, workspace, identity, *, lock=False):
        query = self._scoped(model, workspace).where(model.id == identity)
        row = self.db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
        if row is None:
            self._error(404, "FIELD_OPERATIONS_RECORD_NOT_FOUND")
        return row

    @staticmethod
    def _profile_pin(profile):
        return {"configuration_id": profile.id, "configuration_hash": profile.content_hash}

    def _new(self, model, workspace, **values):
        data = self._base(workspace) | values
        if hasattr(model, "updated_by"):
            data.setdefault("updated_by", self.actor_id)
        # Defaults are materialized before hashing, so append-only facts need no post-insert UPDATE.
        for column in model.__table__.columns:
            if column.key not in data and column.default is not None:
                default = column.default
                if default.is_scalar:
                    data[column.key] = deepcopy(default.arg)
                elif default.is_callable:
                    data[column.key] = default.arg(None)
        row = model(**data)
        if hasattr(row, "source_hash"):
            row.source_hash = field_hash(row)
        self.db.add(row)
        self.db.flush()
        return row

    def _event(self, action, identity, metadata, *, outcome="success"):
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=f"field_operations.{action}",
                outcome=outcome,
                target_type="FieldOperations",
                target_id=identity,
                metadata_json=deepcopy(metadata),
            )
        )

    def _record(self, row, event, reason, *, changed=False):
        old_version = row.version if changed else None
        old_states = inspect(row).attrs.status.history.deleted if hasattr(row, "status") else []
        old_status = old_states[0] if old_states else None
        if changed:
            row.version += 1
            if hasattr(row, "updated_by"):
                row.updated_by, row.updated_at = self.actor_id, utc_now()
            if hasattr(row, "source_hash"):
                row.source_hash = field_hash(row)
        self.db.flush()
        payload = super()._out(row)
        self.db.add(
            FieldHistory(
                **self._base(row.project_workspace_id),
                entity_type=type(row).__name__,
                entity_id=row.id,
                entity_version=row.version,
                previous_version=old_version,
                previous_state=old_status,
                new_state=getattr(row, "status", None),
                event_type=event,
                reason=reason,
                snapshot_json=payload,
            )
        )
        self._event(
            event,
            row.id,
            {
                "project_workspace_id": row.project_workspace_id,
                "entity_type": type(row).__name__,
                "previous_version": old_version,
                "version": row.version,
                "previous_state": old_status,
                "new_state": getattr(row, "status", None),
                "reason": reason,
            },
        )
        return self._out(row)

    def _out(self, row, exclude=()):
        payload = super()._out(row, exclude)
        if isinstance(row, DailyConstructionReport) and self.db.scalar(
            self._scoped(FieldClosure, row.project_workspace_id)
            .where(
                FieldClosure.entity_type == "DailyConstructionReport",
                FieldClosure.entity_id == row.id,
            )
            .limit(1)
        ):
            payload["source_status"], payload["status"] = payload["status"], "CLOSED"
        return payload

    def _write(self, command, workspace, payload, key, apply, identity=None, expected=None):
        self._project(workspace)
        result = self._command(
            f"field_operations.{command}",
            key,
            {
                "project": workspace,
                "id": identity,
                "expected": expected,
                **payload.model_dump(mode="json"),
            },
            apply,
        )
        return self._redact(workspace, result)

    def configuration(self, workspace):
        project = self._read_project(workspace)
        profile = self._field_profile(project)
        return {
            "profile": self._profile_out(profile) if profile else None,
            "allowed_actions": self.allowed_actions(project),
        }

    def _person(self, identity=None):
        identity = identity or self.actor_id
        row = self.db.scalar(
            select(UserAccount).where(
                UserAccount.tenant_id == self.tenant_id,
                UserAccount.id == identity,
                UserAccount.status == "active",
            )
        )
        if row is None:
            self._error(404, "FIELD_OPERATIONS_PERSON_NOT_FOUND")
        return identity

    def _catalog(self, profile, category, value):
        body = profile.content_json if hasattr(profile, "content_json") else profile
        if value not in body[category]:
            self._error(422, f"FIELD_OPERATIONS_{category.upper()}_DISABLED")
        return value

    def _sod(self, body, key, *identities):
        content = body.content_json if hasattr(body, "content_json") else body
        if content["separation_of_duties"][key] and self.actor_id in identities:
            self._error(403, "FIELD_OPERATIONS_INDEPENDENT_ACTOR_REQUIRED")

    def _documents(self, workspace, pins):
        result = [self._document(workspace, pin) for pin in pins]
        if len({(item["document_id"], item["attachment_id"]) for item in result}) != len(result):
            self._error(422, "FIELD_OPERATIONS_DUPLICATE_DOCUMENT")
        return result

    def _reference(self, workspace, pin):
        return self.resolve_reference(workspace, pin.model_dump() if isinstance(pin, BaseModel) else pin)

    def _workfront_values(self, workspace, payload):
        if payload.planned_finish < payload.planned_start:
            self._error(422, "FIELD_OPERATIONS_WORKFRONT_DATES_INVALID")
        if payload.location_reference.target_kind not in {"SCOPE", "CWA", "GEOGRAPHIC_WORKSPACE"}:
            self._error(422, "FIELD_OPERATIONS_LOCATION_REFERENCE_REQUIRED")
        references = []
        cwa = None
        for field, kind in (("cwa_id", "CWA"), ("cwp_id", "CWP"), ("iwp_id", "IWP")):
            identity = getattr(payload, field)
            if identity:
                references.append(self._reference(workspace, {"target_kind": kind, "target_id": identity}))
                if kind == "CWA":
                    cwa = identity
                else:
                    package = self._get(WorkPackage, workspace, identity)
                    if cwa is not None and package.cwa_id != cwa:
                        self._error(409, "FIELD_OPERATIONS_PACKAGE_CWA_MISMATCH")
                    cwa = package.cwa_id
        values = payload.model_dump(exclude={"reason", "location_reference", "responsible_user_id"})
        return values | {
            "workfront_code": payload.workfront_code.upper(),
            "cwa_id": cwa,
            "source_references": references,
            "location_reference": self._reference(workspace, payload.location_reference),
            "responsible_user_id": self._person(payload.responsible_user_id),
        }

    def save_workfront(self, workspace, payload, key, identity=None, expected=None):
        self._ready(workspace, "workfront.edit")

        def apply():
            _, profile = self._ready(workspace, "workfront.edit")
            values = self._workfront_values(workspace, payload)
            if identity:
                row = self._get(Workfront, workspace, identity, lock=True)
                self._version(row.version, expected)
                if row.status != "PLANNED":
                    self._error(409, "FIELD_OPERATIONS_WORKFRONT_NOT_PLANNED")
                for name, value in values.items():
                    setattr(row, name, value)
            else:
                row = self._new(Workfront, workspace, **values, **self._profile_pin(profile))
            return self._record(row, "workfront.saved", payload.reason, changed=bool(identity))

        return self._write("workfront.save", workspace, payload, key, apply, identity, expected)

    def workfront_action(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "workfront.activate")

        def apply():
            self._ready(workspace, "workfront.activate")
            row = self._get(Workfront, workspace, identity, lock=True)
            self._version(row.version, expected)
            states = {
                "activate": ("PLANNED", "ACTIVE"),
                "suspend": ("ACTIVE", "SUSPENDED"),
                "resume": ("SUSPENDED", "ACTIVE"),
                "complete": ("ACTIVE", "COMPLETE"),
            }
            old, new = states[payload.action]
            if row.status != old:
                self._error(409, "FIELD_OPERATIONS_WORKFRONT_TRANSITION_INVALID")
            actual = payload.actual_date or utc_today()
            if actual > utc_today() or row.actual_start and actual < row.actual_start:
                self._error(422, "FIELD_OPERATIONS_ACTUAL_DATE_INVALID")
            if payload.action == "activate":
                row.actual_start = actual
            elif payload.action == "complete":
                pending = self.db.scalar(
                    self._scoped(FieldShift, workspace)
                    .where(
                        FieldShift.workfront_id == identity,
                        FieldShift.status != "CLOSED",
                    )
                    .limit(1)
                )
                if pending:
                    self._error(409, "FIELD_OPERATIONS_OPEN_SHIFT_EXISTS")
                row.actual_finish = actual
            row.status = new
            return self._record(row, f"workfront.{payload.action}", payload.reason, changed=True)

        return self._write("workfront.action", workspace, payload, key, apply, identity, expected)

    def _shift_context(self, workspace, shift_id, workfront_id=None, *, write=True, correction=False):
        shift = self._get(FieldShift, workspace, shift_id, lock=write)
        front = self._get(Workfront, workspace, shift.workfront_id, lock=write)
        if workfront_id is not None and front.id != workfront_id:
            self._error(409, "FIELD_OPERATIONS_SHIFT_WORKFRONT_MISMATCH")
        if write and (shift.status != "OPEN" or front.status != "ACTIVE"):
            self._error(409, "FIELD_OPERATIONS_OPEN_SHIFT_ACTIVE_WORKFRONT_REQUIRED")
        frozen_report = (
            self.db.scalar(
                self._scoped(DailyConstructionReport, workspace)
                .where(
                    DailyConstructionReport.shift_id == shift_id,
                    DailyConstructionReport.status.in_(("SUBMITTED", "REVIEWED", "APPROVED")),
                )
                .order_by(DailyConstructionReport.id.desc())
                .limit(1)
            )
            if write
            else None
        )
        if frozen_report is not None:
            successor = (
                self.db.scalar(
                    self._scoped(DailyConstructionReport, workspace)
                    .where(
                        DailyConstructionReport.supersedes_id == frozen_report.id,
                        DailyConstructionReport.shift_id == shift_id,
                        DailyConstructionReport.status == "DRAFT",
                    )
                    .limit(1)
                )
                if correction and frozen_report.status == "APPROVED"
                else None
            )
            if successor is None:
                self._error(409, "FIELD_OPERATIONS_REPORT_FACTS_FROZEN")
        return shift, front

    def save_shift(self, workspace, payload, key, identity=None, expected=None):
        self._ready(workspace, "shift.edit")

        def apply():
            _, profile = self._ready(workspace, "shift.edit")
            front = self._get(Workfront, workspace, payload.workfront_id, lock=True)
            start, end = (
                payload.start_time.astimezone(UTC).replace(tzinfo=None),
                payload.end_time.astimezone(UTC).replace(tzinfo=None),
            )
            hours = Decimal(str((end - start).total_seconds())) / Decimal(3600)
            if front.status != "ACTIVE" or not 0 < hours <= profile.content_json["max_shift_hours"]:
                self._error(422, "FIELD_OPERATIONS_SHIFT_WINDOW_INVALID")
            if payload.start_time.date() != payload.shift_date:
                self._error(422, "FIELD_OPERATIONS_SHIFT_DATE_MISMATCH")
            self._catalog(profile, "shift_types", payload.shift_type)
            values = payload.model_dump(exclude={"reason", "supervisor_user_id", "start_time", "end_time"}) | {
                "shift_code": payload.shift_code.upper(),
                "start_time": start,
                "end_time": end,
                "supervisor_user_id": self._person(payload.supervisor_user_id),
            }
            if identity:
                row = self._get(FieldShift, workspace, identity, lock=True)
                self._version(row.version, expected)
                if row.status != "OPEN" or self.db.scalar(
                    self._scoped(DailyConstructionReport, workspace)
                    .where(
                        DailyConstructionReport.shift_id == identity,
                    )
                    .limit(1)
                ):
                    self._error(409, "FIELD_OPERATIONS_SHIFT_CONTEXT_FROZEN")
                for name, value in values.items():
                    setattr(row, name, value)
            else:
                row = self._new(FieldShift, workspace, **values, **self._profile_pin(profile))
            return self._record(row, "shift.saved", payload.reason, changed=bool(identity))

        return self._write("shift.save", workspace, payload, key, apply, identity, expected)

    def shift_action(self, workspace, identity, payload, expected, key):
        duty = {"submit": "shift.submit", "approve": "shift.approve", "close": "shift.close"}[payload.action]
        self._ready(workspace, duty)

        def apply():
            self._ready(workspace, duty)
            row = self._get(FieldShift, workspace, identity, lock=True)
            self._version(row.version, expected)
            old, new = {
                "submit": ("OPEN", "SUBMITTED"),
                "approve": ("SUBMITTED", "APPROVED"),
                "close": ("APPROVED", "CLOSED"),
            }[payload.action]
            if row.status != old:
                self._error(409, "FIELD_OPERATIONS_SHIFT_TRANSITION_INVALID")
            if payload.action == "approve":
                self._sod(self._pinned_profile(row), "shift_author_cannot_approve", row.created_by)
                row.approved_by, row.approved_at = self.actor_id, utc_now()
            row.status = new
            return self._record(row, f"shift.{payload.action}", payload.reason, changed=True)

        return self._write("shift.action", workspace, payload, key, apply, identity, expected)

    def _summary(self, workspace, shift_id):
        result = {}
        for name, model in (("labor", LaborUsage), ("equipment", EquipmentUsage), ("conditions", FieldCondition)):
            records = list(
                self.db.scalars(self._scoped(model, workspace).where(model.shift_id == shift_id).order_by(model.id))
            )
            superseded = {getattr(row, "supersedes_id", None) for row in records}
            result[name] = [ScopeFoundationService._out(row) for row in records if row.id not in superseded]
        # Execution aggregates remain in their own tables. Freeze links in the report, not copied binary data.
        from app.modules.field_operations import execution_models

        for name, class_name in (
            ("production", "ProductionRecord"),
            ("events", "FieldEvent"),
            ("instructions", "SiteInstruction"),
            ("constraints", "FieldConstraintObservation"),
            ("rework", "ReworkRecord"),
            ("material_consumption", "MaterialConsumption"),
        ):
            model = getattr(execution_models, class_name, None)
            if model is not None and class_name == "MaterialConsumption":
                productions = (
                    self._scoped(execution_models.ProductionRecord, workspace)
                    .where(
                        execution_models.ProductionRecord.shift_id == shift_id,
                    )
                    .with_only_columns(execution_models.ProductionRecord.id)
                )
                records = list(
                    self.db.scalars(
                        self._scoped(model, workspace)
                        .where(model.production_record_id.in_(productions))
                        .order_by(model.id)
                    )
                )
                result[name] = [ScopeFoundationService._out(row) for row in records]
                continue
            if model is not None and hasattr(model, "shift_id"):
                records = list(
                    self.db.scalars(self._scoped(model, workspace).where(model.shift_id == shift_id).order_by(model.id))
                )
                superseded = {
                    row.supersedes_id for row in records if hasattr(row, "supersedes_id") and row.status == "VERIFIED"
                }
                result[name] = [ScopeFoundationService._out(row) for row in records if row.id not in superseded]
        return result

    def _report_values(self, workspace, payload, *, correction=False):
        shift, front = self._shift_context(workspace, payload.shift_id, write=not correction)
        if payload.report_date != shift.shift_date:
            self._error(422, "FIELD_OPERATIONS_REPORT_DATE_MISMATCH")
        fronts = payload.workfront_ids or [front.id]
        if len(fronts) != len(set(fronts)) or front.id not in fronts:
            self._error(422, "FIELD_OPERATIONS_REPORT_WORKFRONTS_INVALID")
        for identity in fronts:
            self._get(Workfront, workspace, identity)
        return payload.model_dump(exclude={"reason", "document_references", "workfront_ids"}) | {
            "report_number": payload.report_number.upper(),
            "workfront_ids": fronts,
            "document_references": self._documents(workspace, payload.document_references),
        }

    def save_report(self, workspace, payload, key, identity=None, expected=None):
        self._ready(workspace, "daily.prepare")

        def apply():
            _, profile = self._ready(workspace, "daily.prepare")
            row = self._get(DailyConstructionReport, workspace, identity, lock=True) if identity else None
            if row:
                self._version(row.version, expected)
                if row.status != "DRAFT":
                    self._error(409, "FIELD_OPERATIONS_DAILY_REPORT_NOT_DRAFT")
            values = self._report_values(workspace, payload, correction=bool(row and row.supersedes_id))
            if row:
                for name, value in values.items():
                    setattr(row, name, value)
            else:
                row = self._new(DailyConstructionReport, workspace, **values, **self._profile_pin(profile))
            return self._record(row, "daily.saved", payload.reason, changed=bool(identity))

        return self._write("daily.save", workspace, payload, key, apply, identity, expected)

    def report_action(self, workspace, identity, payload, expected, key):
        duty = f"daily.{payload.action}"
        self._ready(workspace, duty)

        def apply():
            self._ready(workspace, duty)
            row = self._get(DailyConstructionReport, workspace, identity, lock=True)
            self._version(row.version, expected)
            body = self._pinned_profile(row)
            closed = self.db.scalar(
                self._scoped(FieldClosure, workspace)
                .where(
                    FieldClosure.entity_type == "DailyConstructionReport",
                    FieldClosure.entity_id == identity,
                )
                .limit(1)
            )
            if closed:
                self._error(409, "FIELD_OPERATIONS_DAILY_REPORT_CLOSED")
            if payload.action == "close":
                if row.status != "APPROVED":
                    self._error(409, "FIELD_OPERATIONS_APPROVED_DAILY_REPORT_REQUIRED")
                self._new(
                    FieldClosure,
                    workspace,
                    entity_type="DailyConstructionReport",
                    entity_id=row.id,
                    entity_version=row.version,
                    reason=payload.reason,
                )
                self.db.add(
                    FieldHistory(
                        **self._base(workspace),
                        entity_type="DailyConstructionReport",
                        entity_id=row.id,
                        entity_version=row.version,
                        previous_version=row.version,
                        previous_state="APPROVED",
                        new_state="CLOSED",
                        event_type="daily.closed",
                        reason=payload.reason,
                        snapshot_json=super(FieldOperationsService, self)._out(row) | {"effective_status": "CLOSED"},
                    )
                )
                self._event("daily.closed", row.id, {"reason": payload.reason, "source_hash": row.source_hash})
                return self._out(row)
            old, new = {
                "submit": ("DRAFT", "SUBMITTED"),
                "review": ("SUBMITTED", "REVIEWED"),
                "approve": ("REVIEWED", "APPROVED"),
            }[payload.action]
            if row.status != old:
                self._error(409, "FIELD_OPERATIONS_DAILY_REPORT_TRANSITION_INVALID")
            if payload.action == "submit":
                row.summaries = self._summary(workspace, row.shift_id)
                types = {
                    "production": "PRODUCTION",
                    "labor": "LABOR",
                    "equipment": "EQUIPMENT",
                    "events": "EVENT",
                    "instructions": "INSTRUCTION",
                    "constraints": "CONSTRAINT",
                    "rework": "REWORK",
                    "conditions": "CONDITION",
                    "material_consumption": "MATERIAL_CONSUMPTION",
                }
                row.source_references = [
                    {
                        "source_domain": "FIELD_OPERATIONS",
                        "source_entity_type": types.get(category, category.upper()),
                        "source_entity_id": item["id"],
                        "source_version": item["version"],
                        "source_hash": item["source_hash"],
                    }
                    for category, items in row.summaries.items()
                    for item in items
                ]
                row.submitted_by, row.submitted_at = self.actor_id, utc_now()
            elif payload.action == "review":
                row.reviewed_by, row.reviewed_at = self.actor_id, utc_now()
            elif payload.action == "approve":
                self._sod(body, "daily_author_cannot_approve", row.created_by)
                self._sod(body, "daily_submitter_cannot_approve", row.submitted_by)
                for pin in row.document_references:
                    self._check_document(workspace, pin)
                current = self._summary(workspace, row.shift_id)
                if current != row.summaries:
                    self._error(409, "FIELD_OPERATIONS_REPORT_FACTS_CHANGED_RESUBMISSION_REQUIRED")
                row.approved_by, row.approved_at = self.actor_id, utc_now()
            row.status = new
            return self._record(row, f"daily.{payload.action}", payload.reason, changed=True)

        return self._write("daily.action", workspace, payload, key, apply, identity, expected)

    def report_successor(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "daily.prepare")

        def apply():
            self._ready(workspace, "daily.prepare")
            old = self._get(DailyConstructionReport, workspace, identity, lock=True)
            self._version(old.version, expected)
            if old.status != "APPROVED" or self.db.scalar(
                self._scoped(DailyConstructionReport, workspace)
                .where(
                    DailyConstructionReport.supersedes_id == identity,
                )
                .limit(1)
            ):
                self._error(409, "FIELD_OPERATIONS_DAILY_REPORT_SUCCESSOR_INVALID")
            excluded = {
                "id",
                "version",
                "created_at",
                "created_by",
                "updated_by",
                "updated_at",
                "source_hash",
                "supersedes_id",
                "revision",
                "status",
                "submitted_by",
                "submitted_at",
                "reviewed_by",
                "reviewed_at",
                "approved_by",
                "approved_at",
                "summaries",
            }
            values = {
                column.key: deepcopy(getattr(old, column.key))
                for column in old.__table__.columns
                if column.key not in excluded
            }
            row = self._new(
                DailyConstructionReport, workspace, **values, revision=old.revision + 1, supersedes_id=old.id
            )
            return self._record(row, "daily.successor", payload.reason)

        return self._write("daily.successor", workspace, payload, key, apply, identity, expected)

    def save_crew(self, workspace, payload, key, identity=None, expected=None):
        self._ready(workspace, "crew.edit")

        def apply():
            _, profile = self._ready(workspace, "crew.edit")
            self._catalog(profile, "crew_trades", payload.trade)
            if payload.vendor_id:
                vendor = self.db.scalar(
                    select(ProcurementVendor).where(
                        ProcurementVendor.tenant_id == self.tenant_id,
                        ProcurementVendor.id == payload.vendor_id,
                        ProcurementVendor.status == "ACTIVE",
                    )
                )
                if vendor is None:
                    self._error(404, "FIELD_OPERATIONS_VENDOR_NOT_FOUND")
            values = payload.model_dump(exclude={"reason", "supervisor_user_id"}) | {
                "crew_code": payload.crew_code.upper(),
                "supervisor_user_id": self._person(payload.supervisor_user_id),
            }
            if identity:
                row = self._get(Crew, workspace, identity, lock=True)
                self._version(row.version, expected)
                for name, value in values.items():
                    setattr(row, name, value)
            else:
                row = self._new(Crew, workspace, **values, **self._profile_pin(profile))
            return self._record(row, "crew.saved", payload.reason, changed=bool(identity))

        return self._write("crew.save", workspace, payload, key, apply, identity, expected)

    def crew_action(self, workspace, identity, payload, expected, key):
        return self._availability_action(
            workspace,
            Crew,
            identity,
            payload,
            expected,
            key,
            "crew.edit",
            {"activate": "ACTIVE", "inactivate": "INACTIVE"},
        )

    def create_equipment_reference(self, workspace, payload, key):
        self._ready(workspace, "equipment.edit")

        def apply():
            _, profile = self._ready(workspace, "equipment.edit")
            self._catalog(profile, "equipment_types", payload.equipment_type)
            row = self._new(
                FieldEquipmentReference,
                workspace,
                **payload.model_dump(exclude={"reason"}),
                **self._profile_pin(profile),
            )
            return self._record(row, "equipment_reference.created", payload.reason)

        return self._write("equipment_reference.create", workspace, payload, key, apply)

    def equipment_reference_action(self, workspace, identity, payload, expected, key):
        return self._availability_action(
            workspace,
            FieldEquipmentReference,
            identity,
            payload,
            expected,
            key,
            "equipment.edit",
            {"available": "AVAILABLE", "unavailable": "UNAVAILABLE"},
        )

    def _availability_action(self, workspace, model, identity, payload, expected, key, duty, states):
        self._ready(workspace, duty)

        def apply():
            self._ready(workspace, duty)
            row = self._get(model, workspace, identity, lock=True)
            self._version(row.version, expected)
            state = states[payload.action]
            if row.status == state:
                self._error(409, "FIELD_OPERATIONS_STATE_UNCHANGED")
            row.status = state
            return self._record(row, f"{model.__name__}.{payload.action}", payload.reason, changed=True)

        return self._write(f"{model.__name__}.availability", workspace, payload, key, apply, identity, expected)

    def _usage_values(self, workspace, payload, model):
        shift, front = self._shift_context(
            workspace, payload.shift_id, payload.workfront_id, correction=bool(payload.supersedes_id)
        )
        values = payload.model_dump(exclude={"reason", "activity_reference", "document_references"})
        values["activity_reference"] = (
            self._reference(workspace, payload.activity_reference) if payload.activity_reference else {}
        )
        values["document_references"] = self._documents(workspace, payload.document_references)
        values["record_code"] = payload.record_code.upper()
        if payload.supersedes_id:
            old = self._get(model, workspace, payload.supersedes_id, lock=True)
            if (
                old.shift_id != shift.id
                or old.workfront_id != front.id
                or self.db.scalar(self._scoped(model, workspace).where(model.supersedes_id == old.id).limit(1))
            ):
                self._error(409, "FIELD_OPERATIONS_USAGE_SUCCESSOR_INVALID")
        return shift, values

    def create_labor(self, workspace, payload, key):
        self._ready(workspace, "labor.record")

        def apply():
            _, profile = self._ready(workspace, "labor.record")
            shift, values = self._usage_values(workspace, payload, LaborUsage)
            crew = self._get(Crew, workspace, payload.crew_id)
            self._catalog(profile, "crew_trades", payload.trade)
            hours = payload.regular_hours + payload.overtime_hours
            length = Decimal(str((shift.end_time - shift.start_time).total_seconds())) / Decimal(3600)
            if crew.status != "ACTIVE" or crew.trade != payload.trade or not 0 < hours <= length * payload.headcount:
                self._error(422, "FIELD_OPERATIONS_LABOR_HOURS_INVALID")
            if sum((payload.productive_hours or Decimal(0), payload.nonproductive_hours or Decimal(0))) > hours:
                self._error(422, "FIELD_OPERATIONS_LABOR_BREAKDOWN_INVALID")
            records = list(
                self.db.scalars(
                    self._scoped(LaborUsage, workspace).where(
                        LaborUsage.shift_id == shift.id,
                        LaborUsage.crew_id == crew.id,
                    )
                )
            )
            superseded = {item.supersedes_id for item in records} | {payload.supersedes_id}
            used = sum(
                (item.regular_hours + item.overtime_hours for item in records if item.id not in superseded), Decimal(0)
            )
            if used + hours > length * payload.headcount:
                self._error(409, "FIELD_OPERATIONS_LABOR_SHIFT_CAP_EXCEEDED")
            row = self._new(LaborUsage, workspace, **values, **self._profile_pin(profile))
            return self._record(row, "labor.recorded", payload.reason)

        return self._write("labor.create", workspace, payload, key, apply)

    def create_equipment_usage(self, workspace, payload, key):
        self._ready(workspace, "equipment.record")

        def apply():
            _, profile = self._ready(workspace, "equipment.record")
            shift, values = self._usage_values(workspace, payload, EquipmentUsage)
            equipment = self._get(FieldEquipmentReference, workspace, payload.equipment_id)
            self._catalog(profile, "equipment_usage_types", payload.usage_type)
            length = Decimal(str((shift.end_time - shift.start_time).total_seconds())) / Decimal(3600)
            hours = sum((payload.operating_hours, payload.idle_hours, payload.standby_hours, payload.downtime_hours))
            if equipment.status != "AVAILABLE" or not 0 < hours <= length:
                self._error(422, "FIELD_OPERATIONS_EQUIPMENT_HOURS_INVALID")
            records = list(
                self.db.scalars(
                    self._scoped(EquipmentUsage, workspace).where(
                        EquipmentUsage.shift_id == shift.id,
                        EquipmentUsage.equipment_id == equipment.id,
                    )
                )
            )
            superseded = {item.supersedes_id for item in records} | {payload.supersedes_id}
            used = sum(
                (
                    item.operating_hours + item.idle_hours + item.standby_hours + item.downtime_hours
                    for item in records
                    if item.id not in superseded
                ),
                Decimal(0),
            )
            if used + hours > length:
                self._error(409, "FIELD_OPERATIONS_EQUIPMENT_SHIFT_CAP_EXCEEDED")
            row = self._new(EquipmentUsage, workspace, **values, **self._profile_pin(profile))
            return self._record(row, "equipment_usage.recorded", payload.reason)

        return self._write("equipment_usage.create", workspace, payload, key, apply)

    def create_condition(self, workspace, payload, key):
        self._ready(workspace, "condition.record")

        def apply():
            _, profile = self._ready(workspace, "condition.record")
            shift, front = self._shift_context(workspace, payload.shift_id, payload.workfront_id)
            if payload.condition_date != shift.shift_date:
                self._error(422, "FIELD_OPERATIONS_CONDITION_DATE_MISMATCH")
            self._catalog(profile, "weather_conditions", payload.weather_condition)
            self._catalog(profile, "site_condition_types", payload.access_condition)
            location = self._reference(workspace, payload.location_reference)
            if location != front.location_reference:
                self._error(409, "FIELD_OPERATIONS_CONDITION_LOCATION_MISMATCH")
            values = payload.model_dump(exclude={"reason", "location_reference", "document_references"}) | {
                "condition_code": payload.condition_code.upper(),
                "location_reference": location,
                "document_references": self._documents(workspace, payload.document_references),
            }
            row = self._new(FieldCondition, workspace, **values, **self._profile_pin(profile))
            return self._record(row, "condition.recorded", payload.reason)

        return self._write("condition.create", workspace, payload, key, apply)

    def collection(self, workspace, collection, *, limit=50, after_id=0, shift_id=None, workfront_id=None):
        self._read_project(workspace)
        model = COLLECTIONS[collection]
        query = self._scoped(model, workspace).where(model.id > after_id)
        if shift_id is not None and hasattr(model, "shift_id"):
            query = query.where(model.shift_id == shift_id)
        if workfront_id is not None and hasattr(model, "workfront_id"):
            query = query.where(model.workfront_id == workfront_id)
        records = list(self.db.scalars(query.order_by(model.id).limit(limit + 1)))
        return self._redact(
            workspace,
            {
                "items": [self._out(row) for row in records[:limit]],
                "next_cursor": records[limit - 1].id if len(records) > limit else None,
            },
        )

    def detail(self, workspace, collection, identity):
        self._read_project(workspace)
        return self._redact(workspace, self._out(self._get(COLLECTIONS[collection], workspace, identity)))
