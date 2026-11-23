"""Quality governance reusing the operational command ledger and scoped source adapters."""

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import func, inspect, select

from app.core.time import utc_now, utc_today
from app.domain.models import SecurityEvent, UserAccount, WorkspaceModuleSetting
from app.modules.basic_data.service import _hash
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.field_operations.service import field_hash as quality_hash
from app.modules.quality.models import (
    ControlPointDecision,
    InspectionRecord,
    InspectionRequest,
    InspectionTestPlan,
    ITPItem,
    QualityHistory,
    QualityPlan,
    TestRecord,
    TestRequest,
)
from app.modules.quality.permissions import ACTIONS, require_quality_schema
from app.modules.quality.profiles import QualityProfilesMixin
from app.modules.quality.sources import QualitySourceMixin
from app.modules.scope_foundation.service import ScopeFoundationService

COLLECTIONS = {
    "plans": QualityPlan,
    "itps": InspectionTestPlan,
    "itp-items": ITPItem,
    "inspection-requests": InspectionRequest,
    "inspections": InspectionRecord,
    "test-requests": TestRequest,
    "tests": TestRecord,
    "control-point-decisions": ControlPointDecision,
    "history": QualityHistory,
}


def naive(value):
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


class QualityService(QualitySourceMixin, QualityProfilesMixin, ScopeFoundationService):
    def _require_schema(self):
        if not getattr(self, "_field_schema_confirmed", False):
            require_quality_schema(self.db)
            self._field_schema_confirmed = True

    def _project(self, workspace):
        self._require_schema()
        project = super()._project(workspace)
        if project.status.lower() != "active":
            self._error(409, "QUALITY_ACTIVE_PROJECT_REQUIRED")
        keys = {"quality-management", "quality-manager", "quality"}
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
            self._error(409, "QUALITY_MODULE_NOT_ENABLED")
        return project

    def _permission(self, action, workspace=None):
        if self.access_context is None:
            return
        if action not in self._permission_contexts:
            self._permission_contexts[action] = require_enterprise_permission(
                self.db,
                self.tenant_id,
                self.actor_id,
                f"quality.{action}",
                bootstrap=False,
            )
        access = self._permission_contexts[action]
        if action.startswith("admin.") and not access.organization_wide:
            self._error(403, "QUALITY_ORGANIZATION_SCOPE_REQUIRED")
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
        profile = self._quality_profile(project)
        if profile is None:
            self._error(409, "QUALITY_PUBLISHED_PROFILE_REQUIRED")
        return project, profile

    def _scoped(self, model, workspace):
        return select(model).where(model.tenant_id == self.tenant_id, model.project_workspace_id == workspace)

    def _get(self, model, workspace, identity, *, lock=False):
        query = self._scoped(model, workspace).where(model.id == identity)
        row = self.db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
        if row is None:
            self._error(404, "QUALITY_RECORD_NOT_FOUND")
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
            row.source_hash = quality_hash(row)
        self.db.add(row)
        self.db.flush()
        return row

    def _event(self, action, identity, metadata, *, outcome="success"):
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=f"quality.{action}",
                outcome=outcome,
                target_type="Quality",
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
                row.source_hash = quality_hash(row)
        self.db.flush()
        payload = super()._out(row)
        self.db.add(
            QualityHistory(
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

    def _write(self, command, workspace, payload, key, apply, identity=None, expected=None):
        self._project(workspace)
        result = self._command(
            f"quality.{command}",
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
        profile = self._quality_profile(project)
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
            self._error(404, "QUALITY_PERSON_NOT_FOUND")
        return identity

    def _catalog(self, profile, category, value):
        body = profile.content_json if hasattr(profile, "content_json") else profile
        if value not in body[category]:
            self._error(422, f"QUALITY_{category.upper()}_DISABLED")
        return value

    def _sod(self, body, key, *identities):
        content = body.content_json if hasattr(body, "content_json") else body
        if content["separation_of_duties"][key] and self.actor_id in identities:
            self._error(403, "QUALITY_INDEPENDENT_ACTOR_REQUIRED")

    def _documents(self, workspace, pins):
        result = [self._document(workspace, pin) for pin in pins]
        if len({(item["document_id"], item["attachment_id"]) for item in result}) != len(result):
            self._error(422, "QUALITY_DUPLICATE_DOCUMENT")
        return result

    def _reference(self, workspace, pin):
        return self.resolve_reference(workspace, pin.model_dump() if isinstance(pin, BaseModel) else pin)

    @staticmethod
    def _at(value=None):
        from datetime import date

        if value is None:
            return utc_now()
        if isinstance(value, date) and not isinstance(value, datetime):
            return datetime.combine(value, datetime.max.time())
        return naive(value)

    def _observed(self, value):
        instant = self._at(value)
        if instant > utc_now():
            self._error(422, "QUALITY_FUTURE_OBSERVATION_FORBIDDEN")
        return instant

    @staticmethod
    def _pin(row):
        kinds = {
            QualityPlan: "QUALITY_PLAN",
            InspectionTestPlan: "ITP",
            ITPItem: "ITP_ITEM",
            InspectionRecord: "INSPECTION",
            TestRecord: "TEST",
            ControlPointDecision: "CONTROL_POINT_DECISION",
        }
        pin = {
            "source_domain": "QUALITY",
            "source_entity_type": kinds.get(type(row), type(row).__name__),
            "source_entity_id": row.id,
            "source_version": row.version,
            "source_hash": row.source_hash,
            "created_by": row.created_by,
        }
        for name in ("inspector_user_id", "closed_by"):
            if hasattr(row, name):
                pin[name] = getattr(row, name)
        return pin

    def _out(self, row, exclude=()):
        value = super()._out(row, exclude)
        if isinstance(row, (QualityPlan, InspectionTestPlan)) and row.status == "APPROVED":
            successor = self.db.scalar(
                self._scoped(type(row), row.project_workspace_id)
                .where(
                    type(row).code == row.code,
                    type(row).revision > row.revision,
                    type(row).status == "APPROVED",
                    type(row).effective_date <= utc_today(),
                )
                .limit(1)
            )
            if successor:
                value["source_status"], value["status"] = "APPROVED", "SUPERSEDED"
        if isinstance(row, InspectionRequest):
            value["checklist_template"] = self._get(
                ITPItem, row.project_workspace_id, row.itp_item_id
            ).checklist_template
        return value

    def _current_version(self, model, workspace, identity, at=None):
        row = self._get(model, workspace, identity)
        instant = self._at(at)
        if (
            row.status != "APPROVED"
            or not row.approved_at
            or row.approved_at > instant
            or row.effective_date > instant.date()
        ):
            self._error(409, "QUALITY_APPLICABLE_APPROVED_VERSION_REQUIRED")
        if self.db.scalar(
            self._scoped(model, workspace)
            .where(
                model.code == row.code,
                model.revision > row.revision,
                model.status == "APPROVED",
                model.approved_at <= instant,
                model.effective_date <= instant.date(),
            )
            .limit(1)
        ):
            self._error(409, "QUALITY_VERSION_SUPERSEDED")
        if row.source_hash != quality_hash(row):
            self._error(409, "QUALITY_VERSION_INTEGRITY_INVALID")
        self._pinned_profile(row)
        for pin in row.document_references:
            self._check_document(workspace, pin)
        for pin in row.source_references:
            self.resolve_reference(workspace, pin)
        return row

    def _current_itp(self, workspace, identity, at=None):
        row = self._current_version(InspectionTestPlan, workspace, identity, at)
        self._current_version(QualityPlan, workspace, row.quality_plan_id, at)
        # A future requested slot is a plan, not a claim of future knowledge.
        # Technical evidence must already exist; actual result capture below
        # validates again at the real inspection/test observation instant.
        self._source_current(workspace, row.engineering_reference, as_of=min(self._at(at), utc_now()))
        items = list(
            self.db.scalars(self._scoped(ITPItem, workspace).where(ITPItem.itp_id == row.id).order_by(ITPItem.sequence))
        )
        if row.items_snapshot != [self._pin(item) for item in items] or any(
            item.source_hash != quality_hash(item) for item in items
        ):
            self._error(409, "QUALITY_ITP_ITEMS_INTEGRITY_INVALID")
        return row

    def _version_values(self, workspace, payload, profile, model):
        values = payload.model_dump(
            exclude={"reason", "source_references", "document_references", "engineering_reference"}
        )
        values["code"] = payload.code.upper()
        values["source_references"] = [self._reference(workspace, ref) for ref in payload.source_references]
        values["document_references"] = self._documents(workspace, payload.document_references)
        if model is QualityPlan:
            values["responsible_user_id"] = self._person(payload.responsible_user_id)
        else:
            plan = self._current_version(QualityPlan, workspace, payload.quality_plan_id)
            if payload.effective_date < plan.effective_date:
                self._error(422, "QUALITY_ITP_PRECEDES_QUALITY_PLAN")
            if payload.engineering_reference.source_type not in {"IFC_RELEASE", "ENGINEERING_REVISION"}:
                self._error(422, "QUALITY_TECHNICAL_REQUIREMENT_REQUIRED")
            values["engineering_reference"] = self._subject(workspace, payload.engineering_reference, as_of=utc_now())
        return values

    def save_version(self, workspace, resource, payload, key, identity=None, expected=None):
        model, duty = (QualityPlan, "plan") if resource == "plans" else (InspectionTestPlan, "itp")
        self._ready(workspace, f"{duty}.edit")

        def apply():
            _, profile = self._ready(workspace, f"{duty}.edit")
            values = self._version_values(workspace, payload, profile, model)
            if identity:
                row = self._get(model, workspace, identity, lock=True)
                self._version(row.version, expected)
                if row.status != "DRAFT" or row.code != values["code"]:
                    self._error(409, "QUALITY_VERSION_NOT_EDITABLE")
                for name, value in values.items():
                    setattr(row, name, value)
            else:
                row = self._new(model, workspace, **values, **self._profile_pin(profile))
            return self._record(row, f"{duty}.saved", payload.reason, changed=bool(identity))

        return self._write(f"{duty}.save", workspace, payload, key, apply, identity, expected)

    def version_action(self, workspace, resource, identity, payload, expected, key):
        model, duty = (QualityPlan, "plan") if resource == "plans" else (InspectionTestPlan, "itp")
        permission = "submit" if payload.action == "submit" else "approve"
        self._ready(workspace, f"{duty}.{permission}")

        def apply():
            self._ready(workspace, f"{duty}.{permission}")
            row = self._get(model, workspace, identity, lock=True)
            self._version(row.version, expected)
            old, new = {
                "submit": ("DRAFT", "SUBMITTED"),
                "return_to_draft": ("SUBMITTED", "DRAFT"),
                "approve": ("SUBMITTED", "APPROVED"),
            }[payload.action]
            if row.status != old:
                self._error(409, "QUALITY_VERSION_TRANSITION_INVALID")
            profile = self._pinned_profile(row)
            if payload.action == "submit":
                for pin in row.document_references:
                    self._check_document(workspace, pin)
                if model is InspectionTestPlan:
                    items = list(
                        self.db.scalars(
                            self._scoped(ITPItem, workspace).where(ITPItem.itp_id == row.id).order_by(ITPItem.sequence)
                        )
                    )
                    if not items or not any(item.required for item in items):
                        self._error(409, "QUALITY_REQUIRED_ITP_CONTROLS_REQUIRED")
                    row.items_snapshot = [self._pin(item) for item in items]
                row.submitted_by, row.submitted_at = self.actor_id, utc_now()
            if payload.action == "approve":
                self._sod(profile, f"{duty}_author_cannot_approve", row.created_by, row.submitted_by)
                if model is InspectionTestPlan:
                    self._current_version(QualityPlan, workspace, row.quality_plan_id)
                    self._source_current(workspace, row.engineering_reference, as_of=utc_now())
                    items = list(
                        self.db.scalars(
                            self._scoped(ITPItem, workspace).where(ITPItem.itp_id == row.id).order_by(ITPItem.sequence)
                        )
                    )
                    if row.items_snapshot != [self._pin(item) for item in items]:
                        self._error(409, "QUALITY_ITP_ITEMS_CHANGED")
                for pin in row.document_references:
                    self._check_document(workspace, pin)
                row.approved_by, row.approved_at = self.actor_id, utc_now()
            row.status = new
            return self._record(row, f"{duty}.{payload.action}", payload.reason, changed=True)

        return self._write(f"{duty}.transition", workspace, payload, key, apply, identity, expected)

    def version_successor(self, workspace, resource, identity, payload, expected, key):
        model, duty = (QualityPlan, "plan") if resource == "plans" else (InspectionTestPlan, "itp")
        self._ready(workspace, f"{duty}.edit")

        def apply():
            row = self._get(model, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "APPROVED" or self.db.scalar(
                self._scoped(model, workspace).where(model.supersedes_id == row.id).limit(1)
            ):
                self._error(409, "QUALITY_SUCCESSOR_NOT_ALLOWED")
            excluded = {
                "id",
                "version",
                "revision",
                "supersedes_id",
                "status",
                "source_hash",
                "created_by",
                "created_at",
                "updated_by",
                "updated_at",
                "submitted_by",
                "submitted_at",
                "approved_by",
                "approved_at",
                "items_snapshot",
            }
            values = {
                column.key: deepcopy(getattr(row, column.key))
                for column in row.__table__.columns
                if column.key not in excluded
            }
            successor = self._new(model, workspace, **values, revision=row.revision + 1, supersedes_id=row.id)
            if model is InspectionTestPlan:
                for item in self.db.scalars(
                    self._scoped(ITPItem, workspace).where(ITPItem.itp_id == row.id).order_by(ITPItem.sequence)
                ):
                    copied = {
                        column.key: deepcopy(getattr(item, column.key))
                        for column in item.__table__.columns
                        if column.key
                        not in {
                            "id",
                            "version",
                            "source_hash",
                            "created_by",
                            "created_at",
                            "updated_by",
                            "updated_at",
                            "itp_id",
                        }
                    }
                    self._record(
                        self._new(ITPItem, workspace, **copied, itp_id=successor.id), "itp.item.copied", payload.reason
                    )
            return self._record(successor, f"{duty}.successor", payload.reason)

        return self._write(f"{duty}.successor", workspace, payload, key, apply, identity, expected)

    def save_item(self, workspace, payload, key, identity=None, expected=None):
        self._ready(workspace, "itp.edit")

        def apply():
            parent = self._get(InspectionTestPlan, workspace, payload.itp_id, lock=True)
            if parent.status != "DRAFT":
                self._error(409, "QUALITY_ITP_NOT_DRAFT")
            profile = self._pinned_profile(parent)
            if payload.control_type not in {point["code"] for point in profile["control_point_types"]}:
                self._error(422, "QUALITY_CONFIGURED_CONTROL_TYPE_REQUIRED")
            if payload.test_type and payload.test_type not in profile["test_types"]:
                self._error(422, "QUALITY_CONFIGURED_TEST_TYPE_REQUIRED")
            template = next(
                (item for item in profile["checklist_templates"] if item["code"] == payload.checklist_template_code),
                None,
            )
            if template is None:
                self._error(422, "QUALITY_CONFIGURED_CHECKLIST_TEMPLATE_REQUIRED")
            snapshot = deepcopy(template) | {
                "configuration_id": parent.configuration_id,
                "configuration_hash": parent.configuration_hash,
                "template_hash": _hash(template),
            }
            values = payload.model_dump(exclude={"reason"}) | {
                "itp_item_code": payload.itp_item_code.upper(),
                "checklist_template": snapshot,
            }
            if identity:
                row = self._get(ITPItem, workspace, identity, lock=True)
                self._version(row.version, expected)
                if row.itp_id != parent.id:
                    self._error(409, "QUALITY_ITEM_PARENT_IMMUTABLE")
                for name, value in values.items():
                    setattr(row, name, value)
            else:
                row = self._new(
                    ITPItem,
                    workspace,
                    **values,
                    configuration_id=parent.configuration_id,
                    configuration_hash=parent.configuration_hash,
                )
            return self._record(row, "itp.item.saved", payload.reason, changed=bool(identity))

        return self._write("itp.item.save", workspace, payload, key, apply, identity, expected)

    def _quantity(self, subject, quantity, uom):
        facts = subject["facts"]
        if quantity is not None and (
            uom != facts.get("uom") or facts.get("quantity") is None or quantity > Decimal(str(facts["quantity"]))
        ):
            self._error(422, "QUALITY_SUBJECT_QUANTITY_OR_UOM_INVALID")
        return quantity, uom

    def _itp_applicability(self, workspace, itp, subject):
        """Canonical scope references constrain the ITP, never a name/text match."""
        from app.modules.field_operations.models import Workfront

        facts = subject.get("facts", {})
        keys = {"SCOPE": facts.get("scope_item_id"), "PLAN": facts.get("plan_item_id"), "IWP": facts.get("iwp_id")}
        location = facts.get("location_reference") or {}
        if location.get("target_kind") in keys and keys[location["target_kind"]] is None:
            keys[location["target_kind"]] = location.get("target_id")
        if facts.get("workfront_id"):
            front = self._get(Workfront, workspace, facts["workfront_id"])
            keys |= {"CWP": front.cwp_id, "CWA": front.cwa_id}
        restrictions = {}
        for reference in itp.source_references:
            kind = reference.get("target_kind")
            if kind in {"SCOPE", "PLAN", "IWP", "CWP", "CWA"}:
                restrictions.setdefault(kind, set()).add(reference["target_id"])
        if any(keys.get(kind) not in identities for kind, identities in restrictions.items()):
            self._error(409, "QUALITY_SUBJECT_OUTSIDE_ITP_APPLICABILITY")

    def create_request(self, workspace, resource, payload, key):
        model, duty = (InspectionRequest, "inspection") if resource == "inspection-requests" else (TestRequest, "test")
        self._ready(workspace, f"{duty}.request")

        def apply():
            _, profile = self._ready(workspace, f"{duty}.request")
            item = self._get(ITPItem, workspace, payload.itp_item_id)
            itp = self._current_itp(workspace, item.itp_id, max(naive(payload.requested_for), utc_now()))
            self._observed(payload.requested_at)
            subject = self._subject(workspace, payload.subject_reference)
            self._itp_applicability(workspace, itp, subject)
            quantity, uom = self._quantity(subject, payload.quantity, payload.uom)
            if duty == "inspection":
                self._catalog(profile, "inspection_types", payload.inspection_type)
                if payload.reinspection_of_id:
                    original = self._get(InspectionRecord, workspace, payload.reinspection_of_id)
                    if original.status != "CLOSED" or original.result != "FAIL":
                        self._error(409, "QUALITY_CLOSED_FAILED_INSPECTION_REQUIRED")
                    from app.modules.quality.execution_service import QualityExecutionService

                    QualityExecutionService(
                        self.db, self.tenant_id, self.actor_id, self.access_context
                    )._validate_reinspection(workspace, payload, subject)
                elif payload.corrective_action_id:
                    self._error(422, "QUALITY_REINSPECTION_ORIGINAL_REQUIRED")
            else:
                self._catalog(profile, "test_types", payload.test_type)
                if not item.test_required or item.test_type != payload.test_type:
                    self._error(409, "QUALITY_ITP_TEST_TYPE_MISMATCH")
                self._vendor(workspace, payload.laboratory_vendor_id)
            values = payload.model_dump(
                exclude={
                    "reason",
                    "subject_reference",
                    "document_references",
                    "requested_at",
                    "requested_for",
                    "quantity",
                    "uom",
                }
            )
            row = self._new(
                model,
                workspace,
                **values,
                subject_key=subject["subject_key"],
                subject_reference=subject,
                requester_user_id=self.actor_id,
                quantity=quantity,
                uom=uom,
                requested_at=naive(payload.requested_at),
                requested_for=naive(payload.requested_for),
                document_references=self._documents(workspace, payload.document_references),
                **self._profile_pin(profile),
            )
            self._person(row.inspector_user_id)
            return self._record(row, f"{duty}.requested", payload.reason)

        return self._write(f"{duty}.request", workspace, payload, key, apply)

    def _vendor(self, workspace, identity):
        if identity is None:
            return
        from app.modules.procurement_foundation.sourcing_models import ProcurementVendor

        row = self.db.scalar(
            select(ProcurementVendor).where(
                ProcurementVendor.tenant_id == self.tenant_id,
                ProcurementVendor.id == identity,
                ProcurementVendor.status == "ACTIVE",
            )
        )
        if row is None:
            self._error(404, "QUALITY_VENDOR_NOT_FOUND")

    def request_action(self, workspace, resource, identity, payload, expected, key):
        model, record_model, duty, started = (
            (InspectionRequest, InspectionRecord, "inspection", "IN_INSPECTION")
            if resource == "inspection-requests"
            else (TestRequest, TestRecord, "test", "IN_TEST")
        )
        permission = (
            "request"
            if payload.action in {"submit", "cancel"}
            else ("schedule" if payload.action == "schedule" else "perform")
        )
        self._ready(workspace, f"{duty}.{permission}")

        def apply():
            row = self._get(model, workspace, identity, lock=True)
            self._version(row.version, expected)
            if payload.action == "cancel":
                if row.status in {"CANCELLED", "COMPLETED"} or self.db.scalar(
                    self._scoped(record_model, workspace).where(record_model.request_id == row.id).limit(1)
                ):
                    self._error(409, "QUALITY_REQUEST_CANNOT_CANCEL")
                row.status = "CANCELLED"
            else:
                old, new = {
                    "submit": ("DRAFT", "SUBMITTED"),
                    "schedule": ("SUBMITTED", "SCHEDULED"),
                    "start": ("SCHEDULED", started),
                }[payload.action]
                if row.status != old:
                    self._error(409, "QUALITY_REQUEST_TRANSITION_INVALID")
                item = self._get(ITPItem, workspace, row.itp_item_id)
                self._current_itp(
                    workspace,
                    item.itp_id,
                    max(row.requested_for, utc_now()) if payload.action != "start" else utc_now(),
                )
                self._source_current(workspace, row.subject_reference)
                if payload.action == "start":
                    if self.actor_id != row.inspector_user_id:
                        self._error(403, "QUALITY_ASSIGNED_INSPECTOR_REQUIRED")
                    self._sod(self._pinned_profile(row), "requester_cannot_inspect", row.requester_user_id)
                row.status = new
            return self._record(row, f"{duty}.request.{payload.action}", payload.reason, changed=True)

        return self._write(f"{duty}.request.transition", workspace, payload, key, apply, identity, expected)

    def _checklist(self, workspace, template, responses, result):
        indexed = {item.item_code: item for item in responses}
        if len(indexed) != len(responses) or set(indexed) - {item["code"] for item in template["items"]}:
            self._error(422, "QUALITY_CHECKLIST_RESPONSE_IDENTITY_INVALID")
        failed, normalized = False, []
        for item in template["items"]:
            response = indexed.get(item["code"])
            if response is None:
                if item["required"]:
                    self._error(422, "QUALITY_REQUIRED_CHECKLIST_RESPONSE_MISSING")
                continue
            if item["evidence_required"] and not response.evidence_references:
                self._error(422, "QUALITY_CHECKLIST_EVIDENCE_REQUIRED")
            mode = item["response_type"]
            selected = {
                "PASS_FAIL_NA": response.response_code,
                "NUMBER": response.numeric_value,
                "TEXT": response.text_value,
                "BOOLEAN": response.boolean_value,
            }
            if selected[mode] is None or any(value is not None for name, value in selected.items() if name != mode):
                self._error(422, "QUALITY_CHECKLIST_RESPONSE_TYPE_INVALID")
            if mode == "PASS_FAIL_NA":
                if response.response_code == "CONDITIONAL" or (
                    response.response_code == "NOT_APPLICABLE" and (not item["allow_na"] or not response.comment)
                ):
                    self._error(422, "QUALITY_CHECKLIST_NOT_APPLICABLE_FORBIDDEN")
                failed = failed or response.response_code == "FAIL"
            if mode == "NUMBER":
                if response.uom != item["uom"]:
                    self._error(422, "QUALITY_CHECKLIST_UOM_MISMATCH")
                failed = (
                    failed
                    or (
                        item.get("lower_limit") is not None
                        and response.numeric_value < Decimal(str(item["lower_limit"]))
                    )
                    or (
                        item.get("upper_limit") is not None
                        and response.numeric_value > Decimal(str(item["upper_limit"]))
                    )
                )
            if mode == "BOOLEAN":
                failed = failed or not response.boolean_value
            normalized.append(
                response.model_dump(mode="json", exclude={"evidence_references"})
                | {"evidence_references": self._documents(workspace, response.evidence_references)}
            )
        if failed and result != "FAIL":
            self._error(422, "QUALITY_FAILED_CHECKLIST_CANNOT_PASS")
        return normalized

    def _measurements(self, item, values, result):
        if len({value.code for value in values}) != len(values):
            self._error(422, "QUALITY_DISTINCT_MEASUREMENTS_REQUIRED")
        if (item.test_lower_limit is not None or item.test_upper_limit is not None) and not any(
            value.numeric_value is not None for value in values
        ):
            self._error(422, "QUALITY_REQUIRED_NUMERIC_TEST_RESULT_MISSING")
        failed = False
        for value in values:
            if value.numeric_value is not None:
                if item.test_uom and value.uom != item.test_uom:
                    self._error(422, "QUALITY_TEST_UOM_MISMATCH")
                for key in ("lower_limit", "upper_limit"):
                    expected = getattr(item, "test_" + key)
                    if expected is not None and getattr(value, key) != expected:
                        self._error(422, "QUALITY_TEST_LIMIT_OVERRIDE_FORBIDDEN")
                outside = (value.lower_limit is not None and value.numeric_value < value.lower_limit) or (
                    value.upper_limit is not None and value.numeric_value > value.upper_limit
                )
                if outside and value.result != "FAIL":
                    self._error(422, "QUALITY_OUT_OF_LIMIT_MEASUREMENT_CANNOT_PASS")
            failed = failed or value.result == "FAIL"
        if failed and result != "FAIL":
            self._error(422, "QUALITY_FAILED_TEST_CANNOT_PASS")
        return [value.model_dump(mode="json") for value in values]

    def _result_values(self, workspace, resource, payload, request, profile):
        inspection = resource == "inspections"
        observed = self._observed(payload.inspected_at if inspection else payload.tested_at)
        if observed < request.requested_at or self.actor_id != request.inspector_user_id:
            self._error(403, "QUALITY_ASSIGNED_INSPECTOR_AND_REQUEST_TIME_REQUIRED")
        item = self._get(ITPItem, workspace, request.itp_item_id)
        itp = self._current_itp(workspace, item.itp_id, observed)
        subject = self._source_current(workspace, request.subject_reference, as_of=observed)
        self._itp_applicability(workspace, itp, subject)
        requirement = self._subject(workspace, payload.engineering_reference, as_of=observed)
        for field in ("source_domain", "source_entity_type", "source_entity_id", "source_version", "source_hash"):
            if requirement[field] != itp.engineering_reference[field]:
                self._error(409, "QUALITY_ITP_TECHNICAL_REQUIREMENT_MISMATCH")
        self._sod(self._pinned_profile(request), "requester_cannot_inspect", request.requester_user_id)
        self._catalog(profile, "result_codes", payload.result)
        values = payload.model_dump(
            exclude={
                "reason",
                "engineering_reference",
                "document_references",
                "inspected_at",
                "tested_at",
                "checklist_responses",
                "measurements",
                "equipment_reference",
            }
        )
        values |= {
            "itp_item_id": item.id,
            "subject_key": subject["subject_key"],
            "subject_reference": subject,
            "quantity": request.quantity,
            "uom": request.uom,
            "inspector_user_id": self.actor_id,
            "engineering_reference": requirement,
            "requirement_reference": self._pin(item)
            | {"description": item.requirement_reference, "acceptance_criteria": item.acceptance_criteria},
            "document_references": self._documents(workspace, payload.document_references),
        }
        if inspection:
            values |= {
                "inspected_at": observed,
                "checklist_template": deepcopy(item.checklist_template),
                "checklist_responses": self._checklist(
                    workspace, item.checklist_template, payload.checklist_responses, payload.result
                ),
            }
        else:
            self._vendor(workspace, payload.laboratory_vendor_id)
            equipment = None
            if payload.equipment_reference:
                equipment = payload.equipment_reference
                if equipment.source_reference.source_type != "FIELD_EQUIPMENT_REFERENCE" or not naive(
                    equipment.valid_from
                ) <= observed <= naive(equipment.valid_to):
                    self._error(409, "QUALITY_EQUIPMENT_CALIBRATION_NOT_VALID_AT_TEST")
                equipment = {
                    "source_reference": self._subject(workspace, equipment.source_reference, as_of=observed),
                    "calibration_status": equipment.calibration_status,
                    "valid_from": equipment.valid_from.isoformat(),
                    "valid_to": equipment.valid_to.isoformat(),
                    "document_reference": self._document(workspace, equipment.document_reference),
                }
            values |= {
                "tested_at": observed,
                "equipment_reference": equipment,
                "measurements": self._measurements(item, payload.measurements, payload.result),
            }
        return values

    def save_result(self, workspace, resource, payload, key, identity=None, expected=None):
        model, request_model, duty, state = (
            (InspectionRecord, InspectionRequest, "inspection", "IN_INSPECTION")
            if resource == "inspections"
            else (TestRecord, TestRequest, "test", "IN_TEST")
        )
        self._ready(workspace, f"{duty}.perform")

        def apply():
            _, profile = self._ready(workspace, f"{duty}.perform")
            request = self._get(request_model, workspace, payload.request_id, lock=True)
            if request.status != state:
                self._error(409, "QUALITY_REQUEST_MUST_BE_IN_EXECUTION")
            values = self._result_values(workspace, resource, payload, request, profile)
            if identity:
                row = self._get(model, workspace, identity, lock=True)
                self._version(row.version, expected)
                if row.status != "DRAFT" or row.request_id != request.id:
                    self._error(409, "QUALITY_RESULT_NOT_EDITABLE")
                for name, value in values.items():
                    setattr(row, name, value)
            else:
                row = self._new(model, workspace, **values, **self._profile_pin(profile))
            return self._record(row, f"{duty}.recorded", payload.reason, changed=bool(identity))

        return self._write(f"{duty}.record", workspace, payload, key, apply, identity, expected)

    def result_action(self, workspace, resource, identity, payload, expected, key):
        model, request_model, duty = (
            (InspectionRecord, InspectionRequest, "inspection")
            if resource == "inspections"
            else (TestRecord, TestRequest, "test")
        )
        permission = "perform" if payload.action == "submit" else "close"
        self._ready(workspace, f"{duty}.{permission}")

        def apply():
            row = self._get(model, workspace, identity, lock=True)
            self._version(row.version, expected)
            old, new = {
                "submit": ("DRAFT", "SUBMITTED"),
                "return_to_draft": ("SUBMITTED", "DRAFT"),
                "close": ("SUBMITTED", "CLOSED"),
            }[payload.action]
            if row.status != old:
                self._error(409, "QUALITY_RESULT_TRANSITION_INVALID")
            if payload.action == "submit":
                if self.actor_id != row.inspector_user_id:
                    self._error(403, "QUALITY_ASSIGNED_INSPECTOR_REQUIRED")
                row.submitted_by, row.submitted_at = self.actor_id, utc_now()
            if payload.action == "close":
                self._sod(
                    self._pinned_profile(row),
                    "inspector_cannot_close",
                    row.inspector_user_id,
                    row.created_by,
                    row.submitted_by,
                )
                self._result_current(workspace, row, terminal=False)
                request = self._get(request_model, workspace, row.request_id, lock=True)
                if request.status != ("IN_INSPECTION" if duty == "inspection" else "IN_TEST"):
                    self._error(409, "QUALITY_REQUEST_MUST_BE_IN_EXECUTION")
                request.status = "COMPLETED"
                self._record(request, f"{duty}.request.completed", payload.reason, changed=True)
                # The request history flush must precede terminal result fields.
                # Otherwise SQL sees SUBMITTED with closed_by set, or the ORM
                # sees an already-CLOSED fact during its later version update.
                row.closed_by, row.closed_at = self.actor_id, utc_now()
            row.status = new
            return self._record(row, f"{duty}.{payload.action}", payload.reason, changed=True)

        return self._write(f"{duty}.transition", workspace, payload, key, apply, identity, expected)

    def _result_current(self, workspace, row, *, terminal=True, as_of=None):
        if terminal and row.status != "CLOSED":
            self._error(409, "QUALITY_CLOSED_RESULT_REQUIRED")
        if row.source_hash != quality_hash(row):
            self._error(409, "QUALITY_RESULT_INTEGRITY_INVALID")
        subject = self._source_current(workspace, row.subject_reference, as_of=as_of)
        self._source_current(
            workspace, row.engineering_reference, as_of=getattr(row, "inspected_at", None) or row.tested_at
        )
        item = self._get(ITPItem, workspace, row.itp_item_id)
        itp = self._current_itp(workspace, item.itp_id, getattr(row, "inspected_at", None) or row.tested_at)
        self._itp_applicability(workspace, itp, subject)
        for pin in row.document_references:
            self._check_document(workspace, pin)
        for response in getattr(row, "checklist_responses", []):
            for pin in response["evidence_references"]:
                self._check_document(workspace, pin)
        if isinstance(row, TestRecord) and row.equipment_reference:
            self._source_current(workspace, row.equipment_reference["source_reference"])
            self._check_document(workspace, row.equipment_reference["document_reference"])
        return row

    def _control_evidence(self, workspace, item, subject, as_of=None):
        instant = self._at(as_of)
        selected, issues = {}, []
        for name, model, required in (
            ("inspection_record", InspectionRecord, item.inspection_required),
            ("test_record", TestRecord, item.test_required),
        ):
            row = self.db.scalar(
                self._scoped(model, workspace)
                .where(
                    model.itp_item_id == item.id,
                    model.subject_key == subject["subject_key"],
                    model.created_at <= instant,
                )
                .order_by(model.id.desc())
                .limit(1)
            )
            selected[name] = row
            if required:
                if row is None:
                    issues.append(name + "_missing")
                else:
                    self._result_current(workspace, row, terminal=False, as_of=instant)
                    if row.subject_reference != subject:
                        issues.append(name + "_subject_changed")
                    if row.status != "CLOSED" or row.closed_at is None or row.closed_at > instant:
                        issues.append(name + "_independent_review_pending")
                    if row.result != "PASS":
                        issues.append(name + "_not_passed")
        return selected, issues

    def control_decision(self, workspace, payload, expected, key):
        self._ready(workspace, "control.release")

        def apply():
            _, profile = self._ready(workspace, "control.release")
            item = self._get(ITPItem, workspace, payload.itp_item_id)
            itp = self._current_itp(workspace, item.itp_id)
            subject = self._subject(workspace, payload.subject_reference)
            self._itp_applicability(workspace, itp, subject)
            previous = self.db.scalar(
                self._scoped(ControlPointDecision, workspace)
                .where(
                    ControlPointDecision.itp_item_id == item.id,
                    ControlPointDecision.subject_key == subject["subject_key"],
                )
                .order_by(ControlPointDecision.version.desc())
                .limit(1)
            )
            self._version(previous.version if previous else 0, expected)
            point = next(
                point
                for point in self._pinned_profile(item)["control_point_types"]
                if point["code"] == item.control_type
            )
            if payload.decision == "WAIVED" and not point["allow_waiver"]:
                self._error(409, "QUALITY_CONTROL_WAIVER_FORBIDDEN")
            selected, issues = self._control_evidence(workspace, item, subject)
            if issues:
                self._error(409, "QUALITY_CONTROL_RESULTS_NOT_PASSED")
            pins = []
            for name in ("inspection_record", "test_record"):
                row = selected[name]
                supplied = getattr(payload, name + "_id")
                if supplied != (row.id if row else None):
                    self._error(409, "QUALITY_LATEST_CONTROL_RESULT_PIN_REQUIRED")
                if row:
                    self._sod(self._pinned_profile(item), "control_releaser_cannot_be_inspector", row.inspector_user_id)
                    pins.append(self._pin(row))
            if (
                previous
                and previous.subject_reference == subject
                and previous.source_references == pins
                and previous.decision == payload.decision
            ):
                self._error(409, "QUALITY_DUPLICATE_CONTROL_DECISION")
            row = self._new(
                ControlPointDecision,
                workspace,
                itp_item_id=item.id,
                subject_key=subject["subject_key"],
                subject_reference=subject,
                inspection_record_id=payload.inspection_record_id,
                test_record_id=payload.test_record_id,
                source_references=pins,
                decision=payload.decision,
                reason=payload.reason,
                document_references=self._documents(workspace, payload.document_references),
                version=(previous.version + 1 if previous else 1),
                **self._profile_pin(profile),
            )
            return self._record(row, "control.decided", payload.reason)

        return self._write("control.decide", workspace, payload, key, apply, payload.itp_item_id, expected)

    def evaluate_required_controls(self, workspace, itp_id, subject_reference, as_of=None):
        instant = self._at(as_of)
        itp = self._current_itp(workspace, itp_id, as_of)
        subject = self._source_current(workspace, subject_reference, as_of=instant)
        self._itp_applicability(workspace, itp, subject)
        items, missing, pins, inspectors = [], [], [self._pin(itp)], set()
        for item in self.db.scalars(
            self._scoped(ITPItem, workspace).where(ITPItem.itp_id == itp.id).order_by(ITPItem.sequence)
        ):
            selected, issues = self._control_evidence(workspace, item, subject, as_of=instant)
            point = next(
                point
                for point in self._pinned_profile(item)["control_point_types"]
                if point["code"] == item.control_type
            )
            decision = self.db.scalar(
                self._scoped(ControlPointDecision, workspace)
                .where(
                    ControlPointDecision.itp_item_id == item.id,
                    ControlPointDecision.subject_key == subject["subject_key"],
                    ControlPointDecision.created_at <= instant,
                )
                .order_by(ControlPointDecision.version.desc())
                .limit(1)
            )
            result_pins = [self._pin(row) for row in selected.values() if row]
            if point["require_release"] and (
                not decision
                or decision.subject_reference != subject
                or decision.source_references != result_pins
                or decision.source_hash != quality_hash(decision)
            ):
                issues.append("explicit_control_release_missing_or_stale")
            for row in selected.values():
                if row:
                    inspectors.add(row.inspector_user_id)
            if item.required:
                if issues:
                    missing.append(item.itp_item_code)
                pins.extend([self._pin(item), *result_pins])
                if decision:
                    for document in decision.document_references:
                        self._check_document(workspace, document)
                    pins.append(self._pin(decision))
            items.append(
                {
                    "itp_item_id": item.id,
                    "itp_item_code": item.itp_item_code,
                    "required": item.required,
                    "control_type": item.control_type,
                    "inspection_required": item.inspection_required,
                    "test_required": item.test_required,
                    **{name: self._pin(row) if row else None for name, row in selected.items()},
                    "control_decision": self._pin(decision) if decision else None,
                    "issues": issues,
                }
            )
        return {
            "state": "READY"
            if not missing
            else ("PARTIALLY_READY" if any(not item["issues"] for item in items) else "NOT_READY"),
            "itp": self._pin(itp) | {"prepared_by": itp.created_by},
            "subject_reference": subject,
            "items": items,
            "missing": missing,
            "source_references": pins,
            "inspector_user_ids": sorted(inspectors),
            "itp_prepared_by": itp.created_by,
        }

    def collection(
        self,
        workspace,
        resource,
        *,
        limit=50,
        after_id=0,
        itp_id=None,
        itp_item_id=None,
        subject_key=None,
        status=None,
        **filters,
    ):
        self._read_project(workspace)
        model = COLLECTIONS[resource]
        query = self._scoped(model, workspace).where(model.id > after_id)
        for field, value in (
            ("itp_id", itp_id),
            ("itp_item_id", itp_item_id),
            ("subject_key", subject_key),
            ("status", status),
        ):
            if value is not None and hasattr(model, field):
                query = query.where(getattr(model, field) == value)
        rows = list(self.db.scalars(query.order_by(model.id).limit(limit + 1)))
        result = {
            "items": [self._redact(workspace, self._out(row)) for row in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
        }
        if model is ControlPointDecision and itp_item_id is not None and subject_key:
            result["version"] = self.db.scalar(
                self._scoped(model, workspace)
                .where(model.itp_item_id == itp_item_id, model.subject_key == subject_key)
                .with_only_columns(func.coalesce(func.max(model.version), 0))
            )
        return result

    def detail(self, workspace, resource, identity):
        self._read_project(workspace)
        row = self._get(COLLECTIONS[resource], workspace, identity)
        value = self._out(row)
        if isinstance(row, InspectionTestPlan):
            value["items"] = [
                self._out(item)
                for item in self.db.scalars(
                    self._scoped(ITPItem, workspace).where(ITPItem.itp_id == row.id).order_by(ITPItem.sequence)
                )
            ]
        return self._redact(workspace, value)
