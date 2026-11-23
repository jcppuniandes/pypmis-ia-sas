"""Quality-owned remediation and granular acceptance with explicit decisions."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.core.time import utc_now
from app.domain.models import UserAccount
from app.modules.basic_data.service import _hash, _json
from app.modules.quality.execution_models import (
    QualityAcceptance,
    QualityCorrectiveAction,
    QualityDisposition,
    QualityNCR,
    QualityPunchItem,
)
from app.modules.quality.models import (
    InspectionRecord,
    InspectionRequest,
    InspectionTestPlan,
    ITPItem,
    QualityHistory,
    QualityPlan,
    TestRecord,
    TestRequest,
)
from app.modules.quality.service import QualityService, quality_hash

RESOURCES = {
    "ncrs": QualityNCR,
    "dispositions": QualityDisposition,
    "corrective-actions": QualityCorrectiveAction,
    "punch-items": QualityPunchItem,
    "acceptances": QualityAcceptance,
}
RESULTS = {"INSPECTION": InspectionRecord, "TEST": TestRecord}
TERMINAL_NCR = {"CLOSED", "CANCELLED", "REJECTED"}


def _instant(value):
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


class QualityExecutionService(QualityService):
    def _execution_catalog(self, profile, key, value):
        if value not in profile[key]:
            self._error(422, "QUALITY_CONFIGURED_CATALOG_VALUE_REQUIRED")

    def _execution_sod(self, profile, key, *authors):
        if profile["separation_of_duties"].get(key, True) and self.actor_id in authors:
            self._error(403, "QUALITY_INDEPENDENT_DECISION_REQUIRED")

    def _execution_person(self, identity):
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

    def _execution_observed(self, value):
        instant = _instant(value)
        if instant > utc_now():
            self._error(422, "QUALITY_FUTURE_OBSERVATION_FORBIDDEN")
        return instant

    @staticmethod
    def _execution_profile(profile):
        return {"configuration_id": profile.id, "configuration_hash": profile.content_hash}

    def _execution_integrity(self, row):
        if not row.source_hash or row.source_hash != quality_hash(row):
            self._error(409, "QUALITY_RECORD_INTEGRITY_INVALID")

    def _execution_pin(self, row, kind):
        self._execution_integrity(row)
        return _json(
            {
                "source_domain": "QUALITY",
                "source_entity_type": kind,
                "source_entity_id": row.id,
                "source_version": row.version,
                "source_hash": row.source_hash,
                "facts": {
                    key: getattr(row, key)
                    for key in (
                        "status",
                        "result",
                        "subject_key",
                        "itp_item_id",
                        "ncr_id",
                        "disposition_type",
                        "closed_by",
                        "closed_at",
                        "inspector_user_id",
                        "inspected_at",
                        "tested_at",
                    )
                    if hasattr(row, key)
                },
            }
        )

    def _execution_result(self, workspace, kind, identity, *, expected=None, current=True, passed=False):
        if kind not in RESULTS:
            self._error(422, "QUALITY_RESULT_TYPE_UNSUPPORTED")
        row = self._get(RESULTS[kind], workspace, identity)
        self._execution_integrity(row)
        if row.status != "CLOSED" or passed and row.result != "PASS":
            self._error(409, "QUALITY_CLOSED_PASS_RESULT_REQUIRED" if passed else "QUALITY_CLOSED_RESULT_REQUIRED")
        if expected and (row.version != expected.source_version or row.source_hash != expected.source_hash):
            self._error(409, "QUALITY_RESULT_PIN_MISMATCH")
        if current:
            # Reuse the core result boundary: a current subject alone does not
            # prove the captured IFC/ITP applicability, checklist attachments or
            # test equipment/calibration evidence are still valid.
            self._result_current(workspace, row)
        for document in row.document_references:
            self._check_document(workspace, document)
        return row

    def quality_source(self, workspace, kind, identity):
        self._read_project(workspace)
        row = self._execution_result(workspace, kind, identity, current=False)
        return self._execution_pin(row, kind)

    @staticmethod
    def _subject_key(subject):
        return subject["subject_key"]

    @staticmethod
    def _related_subject(left, right):
        if left.get("subject_key") == right.get("subject_key"):
            return True
        a, b = left.get("facts", {}), right.get("facts", {})
        left_kind = left.get("source_type", left.get("source_entity_type"))
        if left_kind in {"FIELD_WORKFRONT", "WORKFRONT"}:
            front = a.get("workfront_id", left.get("source_entity_id"))
            return front is not None and front == b.get("workfront_id")
        a_receipt = a.get("receipt_line_id", a.get("material_receipt_line_id"))
        b_receipt = b.get("receipt_line_id", b.get("material_receipt_line_id"))
        if left_kind in {"MATERIAL_RECEIPT_LINE", "RECEIPT_LINE"}:
            a_receipt = left.get("source_entity_id", left.get("source_id"))
        return bool(a_receipt and a_receipt == b_receipt)

    def create_ncr(self, workspace, payload, key):
        self._ready(workspace, "ncr.record")

        def apply():
            _, profile = self._ready(workspace, "ncr.record")
            self._execution_catalog(profile.content_json, "ncr_categories", payload.category)
            self._execution_catalog(profile.content_json, "severities", payload.severity)
            observed = self._execution_observed(payload.detected_at)
            subject = self._subject(workspace, payload.subject_reference, as_of=observed)
            for kind, identity in (("INSPECTION", payload.inspection_record_id), ("TEST", payload.test_record_id)):
                if identity:
                    result = self._execution_result(workspace, kind, identity)
                    if result.result not in {"FAIL", "CONDITIONAL"} or result.subject_key != self._subject_key(subject):
                        self._error(409, "QUALITY_NCR_FAILED_SUBJECT_RESULT_REQUIRED")
            values = payload.model_dump(
                exclude={"reason", "subject_reference", "document_reference", "detected_at", "ncr_number"}
            )
            row = self._new(
                QualityNCR,
                workspace,
                **values,
                ncr_number=payload.ncr_number.upper(),
                detected_at=observed,
                subject_key=self._subject_key(subject),
                subject_reference=subject,
                document_reference=self._document(workspace, payload.document_reference),
                **self._execution_profile(profile),
            )
            self._execution_person(payload.responsible_user_id)
            return self._record(row, "NCR_RECORDED", payload.reason)

        return self._write("ncr.record", workspace, payload, key, apply)

    def create_disposition(self, workspace, payload, key):
        self._ready(workspace, "ncr.disposition")

        def apply():
            _, profile = self._ready(workspace, "ncr.disposition")
            ncr = self._get(QualityNCR, workspace, payload.ncr_id, lock=True)
            if ncr.status != "UNDER_REVIEW":
                self._error(409, "QUALITY_NCR_UNDER_REVIEW_REQUIRED")
            self._execution_catalog(profile.content_json, "dispositions", payload.disposition_type)
            if self.db.scalar(
                self._scoped(QualityDisposition, workspace)
                .where(
                    QualityDisposition.ncr_id == ncr.id,
                    QualityDisposition.status == "APPROVED",
                )
                .limit(1)
            ):
                self._error(409, "QUALITY_APPROVED_DISPOSITION_EXISTS")
            engineering = (
                self._subject(workspace, payload.engineering_decision_reference)
                if payload.engineering_decision_reference
                else None
            )
            row = self._new(
                QualityDisposition,
                workspace,
                ncr_id=ncr.id,
                disposition_code=payload.disposition_code.upper(),
                disposition_type=payload.disposition_type,
                description=payload.description,
                engineering_decision_reference=engineering,
                document_reference=self._document(workspace, payload.document_reference),
                **self._execution_profile(profile),
            )
            return self._record(row, "DISPOSITION_PROPOSED", payload.reason)

        return self._write("ncr.disposition.propose", workspace, payload, key, apply)

    def disposition_action(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "ncr.disposition")

        def apply():
            self._ready(workspace, "ncr.disposition")
            row = self._get(QualityDisposition, workspace, identity, lock=True)
            self._version(row.version, expected)
            ncr = self._get(QualityNCR, workspace, row.ncr_id, lock=True)
            if row.status != "PROPOSED" or ncr.status != "UNDER_REVIEW":
                self._error(409, "QUALITY_DISPOSITION_TRANSITION_INVALID")
            policy = self._pinned_profile(row)
            self._execution_sod(policy, "disposition_author_cannot_approve", row.created_by)
            self._execution_sod(policy, "ncr_author_cannot_dispose", ncr.created_by)
            self._check_document(workspace, row.document_reference)
            if payload.action == "approve":
                if self.db.scalar(
                    self._scoped(QualityDisposition, workspace)
                    .where(
                        QualityDisposition.ncr_id == ncr.id,
                        QualityDisposition.status == "APPROVED",
                    )
                    .limit(1)
                ):
                    self._error(409, "QUALITY_APPROVED_DISPOSITION_EXISTS")
                required = policy.get("disposition_policy", {}).get("require_engineering_approval", ["USE_AS_IS"])
                if row.disposition_type in required:
                    pin = row.engineering_decision_reference
                    if pin:
                        self._source_current(workspace, pin)
                    facts = (pin or {}).get("facts", {})
                    if (
                        facts.get("decision_ncr_id") != ncr.id
                        or facts.get("disposition_decision") != row.disposition_type
                    ):
                        self._error(409, "QUALITY_NCR_BOUND_ENGINEERING_DISPOSITION_REQUIRED")
                row.approved_by, row.approved_at = self.actor_id, utc_now()
            row.status = "APPROVED" if payload.action == "approve" else "REJECTED"
            return self._record(row, f"DISPOSITION_{row.status}", payload.reason, changed=True)

        return self._write("ncr.disposition.decide", workspace, payload, key, apply, identity, expected)

    def _ncr_actions(self, workspace, ncr):
        return list(
            self.db.scalars(
                self._scoped(QualityCorrectiveAction, workspace)
                .where(
                    QualityCorrectiveAction.ncr_id == ncr.id,
                    QualityCorrectiveAction.action_kind == "CORRECTIVE",
                )
                .order_by(QualityCorrectiveAction.id)
            )
        )

    def _validate_actions_complete(self, workspace, ncr, *, verified):
        actions = self._ncr_actions(workspace, ncr)
        states = {"VERIFIED", "CLOSED"} if verified else {"COMPLETED", "VERIFIED", "CLOSED"}
        if not actions or any(row.status not in states for row in actions):
            self._error(
                409,
                "QUALITY_ALL_CORRECTIVE_ACTIONS_VERIFIED_REQUIRED"
                if verified
                else "QUALITY_CORRECTIVE_COMPLETION_REQUIRED",
            )
        for row in actions:
            self._execution_integrity(row)
            if row.completion_reference:
                self._source_current(workspace, row.completion_reference)
            if not row.completion_document_reference:
                self._error(409, "QUALITY_CORRECTIVE_EVIDENCE_REQUIRED")
            self._check_document(workspace, row.completion_document_reference)
            if verified:
                pin = row.verification_reference or {}
                self._execution_result(
                    workspace, pin.get("source_entity_type"), pin.get("source_entity_id"), passed=True
                )
        return actions

    def ncr_action(self, workspace, identity, payload, expected, key):
        duty = {
            "issue": "ncr.issue",
            "review": "ncr.review",
            "disposition": "ncr.disposition",
            "correct": "ncr.correct",
            "verify": "ncr.verify",
            "close": "ncr.close",
            "cancel": "ncr.review",
            "reject": "ncr.review",
        }[payload.action]
        self._ready(workspace, duty)

        def apply():
            self._ready(workspace, duty)
            row = self._get(QualityNCR, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status in TERMINAL_NCR:
                self._error(409, "QUALITY_TERMINAL_NCR_IMMUTABLE")
            policy = self._pinned_profile(row)
            transitions = {
                "issue": ("DRAFT", "ISSUED"),
                "review": ("ISSUED", "UNDER_REVIEW"),
                "disposition": ("UNDER_REVIEW", "DISPOSITIONED"),
                "correct": ("DISPOSITIONED", "CORRECTED"),
                "verify": ("CORRECTED", "VERIFIED"),
                "close": ("VERIFIED", "CLOSED"),
            }
            if payload.action in {"cancel", "reject"}:
                if row.status not in {"DRAFT", "ISSUED", "UNDER_REVIEW"}:
                    self._error(409, "QUALITY_NCR_CANCELLATION_TOO_LATE")
                new = "CANCELLED" if payload.action == "cancel" else "REJECTED"
            else:
                previous, new = transitions[payload.action]
                if row.status != previous:
                    self._error(409, "QUALITY_NCR_TRANSITION_INVALID")
            self._check_document(workspace, row.document_reference)
            if payload.action == "issue":
                row.issued_by, row.issued_at = self.actor_id, utc_now()
            elif payload.action == "disposition":
                if not payload.disposition_id:
                    self._error(422, "QUALITY_APPROVED_DISPOSITION_REQUIRED")
                disposition = self._get(QualityDisposition, workspace, payload.disposition_id)
                if disposition.ncr_id != row.id or disposition.status != "APPROVED":
                    self._error(409, "QUALITY_APPROVED_DISPOSITION_REQUIRED")
                row.disposition_id = disposition.id
                row.disposition_reference = self._execution_pin(disposition, "DISPOSITION")
            elif payload.action in {"correct", "verify", "close"}:
                if not row.disposition_id:
                    self._error(409, "QUALITY_APPROVED_DISPOSITION_REQUIRED")
                disposition = self._get(QualityDisposition, workspace, row.disposition_id)
                if disposition.status != "APPROVED" or disposition.ncr_id != row.id:
                    self._error(409, "QUALITY_APPROVED_DISPOSITION_REQUIRED")
                self._validate_actions_complete(workspace, row, verified=payload.action != "correct")
                if payload.action == "verify":
                    self._execution_sod(policy, "ncr_author_cannot_verify", row.created_by, row.issued_by)
                    self._execution_sod(policy, "ncr_disposer_cannot_verify", disposition.approved_by)
                    row.verified_by, row.verified_at = self.actor_id, utc_now()
                if payload.action == "close":
                    if not row.verified_by:
                        self._error(409, "QUALITY_NCR_VERIFICATION_REQUIRED")
                    row.closed_by, row.closed_at = self.actor_id, utc_now()
            row.status = new
            return self._record(row, f"NCR_{new}", payload.reason, changed=True)

        return self._write("ncr.transition", workspace, payload, key, apply, identity, expected)

    def create_corrective_action(self, workspace, payload, key):
        self._ready(workspace, "action.record")

        def apply():
            _, profile = self._ready(workspace, "action.record")
            self._execution_catalog(profile.content_json, "corrective_action_types", payload.action_kind)
            subject = self._subject(workspace, payload.subject_reference)
            if payload.ncr_id:
                ncr = self._get(QualityNCR, workspace, payload.ncr_id)
                if ncr.status != "DISPOSITIONED" or ncr.subject_key != self._subject_key(subject):
                    self._error(409, "QUALITY_DISPOSITIONED_NCR_SUBJECT_REQUIRED")
            self._execution_person(payload.owner_user_id)
            row = self._new(
                QualityCorrectiveAction,
                workspace,
                action_code=payload.action_code.upper(),
                action_kind=payload.action_kind,
                ncr_id=payload.ncr_id,
                description=payload.description,
                owner_user_id=payload.owner_user_id,
                due_date=payload.due_date,
                subject_key=self._subject_key(subject),
                subject_reference=subject,
                document_reference=self._document(workspace, payload.document_reference),
                **self._execution_profile(profile),
            )
            return self._record(row, "QUALITY_ACTION_RECORDED", payload.reason)

        return self._write("action.record", workspace, payload, key, apply)

    def _correction_reference(self, workspace, action, reference):
        if reference is None:
            self._error(422, "QUALITY_EXPLICIT_FIELD_CORRECTION_REQUIRED")
        pin = self._subject(workspace, reference)
        kind, facts = pin.get("source_type"), pin.get("facts", {})
        original = action.subject_reference
        if (
            original.get("source_type") not in {"FIELD_PRODUCTION", "FIELD_REWORK"}
            or original.get("source_domain") != "FIELD_OPERATIONS"
        ):
            # Integer IDs from Procurement and Field are not interchangeable. A
            # material return/repair needs its native governed correction provider,
            # not an unrelated Field rework that happens to have the same number.
            self._error(409, "QUALITY_TYPED_CORRECTION_PROVIDER_REQUIRED")
        original_id = original.get("source_entity_id", original.get("source_id"))
        same = pin.get("subject_key") == action.subject_key
        linked = facts.get("original_production_id") == original_id or (
            facts.get("original_production_root_id") == original.get("source_root_id")
            and facts.get("original_production_root_id") is not None
        )
        correction = (
            kind == "FIELD_REWORK"
            and linked
            or (kind == "FIELD_PRODUCTION" and same and pin.get("source_entity_id") != original_id)
        )
        if action.action_kind == "CORRECTIVE" and not correction:
            self._error(409, "QUALITY_LINKED_VERIFIED_FIELD_CORRECTION_REQUIRED")
        return pin

    def _validate_reinspection(self, workspace, payload, subject):
        if not payload.corrective_action_id:
            self._error(422, "QUALITY_REINSPECTION_CORRECTIVE_ACTION_REQUIRED")
        action = self._get(QualityCorrectiveAction, workspace, payload.corrective_action_id)
        if action.status not in {"COMPLETED", "VERIFIED", "CLOSED"} or action.subject_key != self._subject_key(subject):
            self._error(409, "QUALITY_REINSPECTION_CORRECTION_NOT_COMPLETED")
        self._execution_integrity(action)
        if action.completion_reference:
            self._source_current(workspace, action.completion_reference)
        self._check_document(workspace, action.completion_document_reference)
        ncr = self._get(QualityNCR, workspace, action.ncr_id) if action.ncr_id else None
        if ncr is None or ncr.status not in {"DISPOSITIONED", "CORRECTED", "VERIFIED"}:
            self._error(409, "QUALITY_REINSPECTION_ACTIVE_NCR_REQUIRED")
        if ncr.inspection_record_id and ncr.inspection_record_id != payload.reinspection_of_id:
            self._error(409, "QUALITY_REINSPECTION_ORIGINAL_FAIL_MISMATCH")
        original = self._get(InspectionRecord, workspace, payload.reinspection_of_id)
        if original.itp_item_id != payload.itp_item_id or original.subject_key != self._subject_key(subject):
            self._error(409, "QUALITY_REINSPECTION_ORIGINAL_CONTROL_SUBJECT_MISMATCH")

    def corrective_action_action(self, workspace, identity, payload, expected, key):
        duty = {
            "start": "action.record",
            "complete": "action.complete",
            "verify": "action.verify",
            "close": "action.verify",
        }[payload.action]
        self._ready(workspace, duty)

        def apply():
            self._ready(workspace, duty)
            row = self._get(QualityCorrectiveAction, workspace, identity, lock=True)
            self._version(row.version, expected)
            old, new = {
                "start": ("OPEN", "IN_PROGRESS"),
                "complete": ("IN_PROGRESS", "COMPLETED"),
                "verify": ("COMPLETED", "VERIFIED"),
                "close": ("VERIFIED", "CLOSED"),
            }[payload.action]
            if row.status != old:
                self._error(409, "QUALITY_ACTION_TRANSITION_INVALID")
            policy = self._pinned_profile(row)
            self._check_document(workspace, row.document_reference)
            if payload.action == "complete":
                if not payload.document_reference:
                    self._error(422, "QUALITY_COMPLETION_CDE_REQUIRED")
                if row.action_kind == "CORRECTIVE":
                    row.completion_reference = self._correction_reference(
                        workspace, row, payload.completion_field_reference
                    )
                elif payload.completion_field_reference:
                    row.completion_reference = self._subject(workspace, payload.completion_field_reference)
                row.completion_document_reference = self._document(workspace, payload.document_reference)
                row.completed_by, row.completed_at = self.actor_id, utc_now()
            elif payload.action == "verify":
                self._execution_sod(policy, "action_completer_cannot_verify", row.completed_by)
                if not payload.verification_reference or not payload.document_reference:
                    self._error(422, "QUALITY_ACTION_VERIFICATION_RESULT_AND_CDE_REQUIRED")
                pin = payload.verification_reference
                result = self._execution_result(
                    workspace, pin.source_entity_type, pin.source_entity_id, expected=pin, passed=True
                )
                if result.subject_key != row.subject_key:
                    self._error(409, "QUALITY_ACTION_VERIFICATION_SUBJECT_MISMATCH")
                if row.ncr_id:
                    ncr = self._get(QualityNCR, workspace, row.ncr_id)
                    if ncr.inspection_record_id:
                        if pin.source_entity_type != "INSPECTION":
                            self._error(409, "QUALITY_NCR_REINSPECTION_REQUIRED")
                        request = self._get(InspectionRequest, workspace, result.request_id)
                        if (
                            request.reinspection_of_id != ncr.inspection_record_id
                            or request.corrective_action_id != row.id
                        ):
                            self._error(409, "QUALITY_NCR_LINKED_REINSPECTION_REQUIRED")
                row.verification_reference = self._execution_pin(result, pin.source_entity_type)
                row.verification_document_reference = self._document(workspace, payload.document_reference)
                row.verified_by, row.verified_at = self.actor_id, utc_now()
            elif payload.action == "close":
                if not row.verification_reference or not row.verified_by:
                    self._error(409, "QUALITY_ACTION_VERIFICATION_REQUIRED")
                pin = row.verification_reference
                self._execution_result(workspace, pin["source_entity_type"], pin["source_entity_id"], passed=True)
            row.status = new
            return self._record(row, f"QUALITY_ACTION_{new}", payload.reason, changed=True)

        return self._write("action.transition", workspace, payload, key, apply, identity, expected)

    def create_punch(self, workspace, payload, key):
        self._ready(workspace, "punch.record")

        def apply():
            _, profile = self._ready(workspace, "punch.record")
            self._execution_catalog(profile.content_json, "punch_categories", payload.category)
            subject = self._subject(workspace, payload.subject_reference)
            self._execution_person(payload.responsible_user_id)
            row = self._new(
                QualityPunchItem,
                workspace,
                item_number=payload.item_number.upper(),
                subject_key=self._subject_key(subject),
                subject_reference=subject,
                location_reference=subject.get("facts", {}).get("location_reference")
                or {"subject_key": self._subject_key(subject)},
                description=payload.description,
                category=payload.category,
                responsible_user_id=payload.responsible_user_id,
                due_date=payload.due_date,
                document_reference=self._document(workspace, payload.document_reference),
                **self._execution_profile(profile),
            )
            return self._record(row, "QUALITY_PUNCH_RECORDED", payload.reason)

        return self._write("punch.record", workspace, payload, key, apply)

    def punch_action(self, workspace, identity, payload, expected, key):
        duty = "punch.verify" if payload.action == "close" else "punch.record"
        self._ready(workspace, duty)

        def apply():
            self._ready(workspace, duty)
            row = self._get(QualityPunchItem, workspace, identity, lock=True)
            self._version(row.version, expected)
            previous, new = {
                "start": ("OPEN", "IN_PROGRESS"),
                "ready": ("IN_PROGRESS", "READY_FOR_VERIFICATION"),
                "close": ("READY_FOR_VERIFICATION", "CLOSED"),
            }[payload.action]
            if row.status != previous:
                self._error(409, "QUALITY_PUNCH_TRANSITION_INVALID")
            self._check_document(workspace, row.document_reference)
            if payload.action in {"ready", "close"}:
                if payload.document_reference is None:
                    self._error(422, "QUALITY_PUNCH_CDE_REQUIRED")
                reference = self._document(workspace, payload.document_reference)
                if payload.action == "ready":
                    row.completion_document_reference = reference
                else:
                    policy = self._pinned_profile(row)
                    self._execution_sod(policy, "punch_author_cannot_verify", row.created_by)
                    self._execution_sod(policy, "punch_owner_cannot_verify", row.responsible_user_id)
                    if payload.verification_result != "PASS" or row.completion_document_reference is None:
                        self._error(409, "QUALITY_PUNCH_EXPLICIT_VERIFICATION_REQUIRED")
                    self._check_document(workspace, row.completion_document_reference)
                    row.verification_document_reference = reference
                    row.verified_by, row.verified_at = self.actor_id, utc_now()
            row.status = new
            return self._record(row, f"QUALITY_PUNCH_{new}", payload.reason, changed=True)

        return self._write("punch.transition", workspace, payload, key, apply, identity, expected)

    def _related_quality(self, workspace, subject, model):
        # Root identity is used for remediation association, never as a substitute
        # for the exact revision/hash required by each inspection control.
        return [
            row
            for row in self.db.scalars(self._scoped(model, workspace).order_by(model.id))
            if self._related_subject(row.subject_reference, subject)
        ]

    @staticmethod
    def _assessment_time(as_of):
        if as_of is None:
            return utc_now()
        if not isinstance(as_of, datetime):
            return min(datetime.combine(as_of, datetime.max.time()), utc_now())
        return _instant(as_of)

    def _captured_subject(self, workspace, itp_id, source_type, source_id, as_of=None):
        instant = self._assessment_time(as_of)
        item_ids = self._scoped(ITPItem, workspace).where(ITPItem.itp_id == itp_id).with_only_columns(ITPItem.id)
        candidates = []
        for model in (InspectionRequest, TestRequest, InspectionRecord, TestRecord, QualityAcceptance):
            query = self._scoped(model, workspace).where(
                model.subject_reference["source_type"].as_string() == source_type,
                model.subject_reference["source_id"].as_integer() == source_id,
                model.created_at <= instant,
            )
            query = (
                query.where(model.itp_id == itp_id)
                if model is QualityAcceptance
                else query.where(model.itp_item_id.in_(item_ids))
            )
            row = self.db.scalar(query.order_by(model.created_at.desc(), model.id.desc()).limit(1))
            if row:
                candidates.append(row)
        return max(candidates, key=lambda row: row.created_at).subject_reference if candidates else None

    def readiness_query(self, workspace, itp_id, source_type, source_id, as_of=None):
        self._read_project(workspace)
        self._get(InspectionTestPlan, workspace, itp_id)
        try:
            subject = self.source_lookup(workspace, source_type, source_id, as_of=as_of)
        except HTTPException as error:
            if error.status_code not in {404, 409, 422}:
                raise
            subject = self._captured_subject(workspace, itp_id, source_type, source_id, as_of)
            if subject is None:
                # A foreign or never-captured identity is still hidden/not eligible.
                raise
        return self.readiness(workspace, itp_id, subject, as_of=as_of)

    def _broken_readiness_basis(self, workspace, itp_id, subject_reference, instant, error):
        if error.status_code not in {404, 409, 422}:
            raise error
        itp = self._get(InspectionTestPlan, workspace, itp_id)
        data = subject_reference.model_dump() if hasattr(subject_reference, "model_dump") else subject_reference
        # Only an actual historic pin captured in this project's exact ITP may be
        # diagnosed as broken. Cross-workspace/tenant identifiers remain 404.
        captured = self._captured_subject(workspace, itp_id, data.get("source_type"), data.get("source_id"), instant)
        if captured is None:
            raise error
        state = "BROKEN_REFERENCE" if error.status_code == 404 else "STALE"
        code = (
            error.detail.get("code", "QUALITY_SOURCE_REQUIRES_REVIEW")
            if isinstance(error.detail, dict)
            else "QUALITY_SOURCE_REQUIRES_REVIEW"
        )
        return {
            "state": state,
            "itp": self._pin(itp),
            "subject_reference": captured,
            "items": [],
            "missing": [code],
            "source_references": [self._pin(itp)],
            "inspector_user_ids": [],
            "itp_prepared_by": itp.created_by,
        }

    def readiness(self, workspace, itp_id, subject_reference, as_of=None):
        self._read_project(workspace)
        instant = self._assessment_time(as_of)
        if instant > utc_now():
            self._error(422, "QUALITY_FUTURE_ASSESSMENT_FORBIDDEN")
        try:
            base = self.evaluate_required_controls(workspace, itp_id, subject_reference, as_of=instant)
        except HTTPException as error:
            base = self._broken_readiness_basis(workspace, itp_id, subject_reference, instant, error)
        subject = base["subject_reference"]
        ncrs = self._related_quality(workspace, subject, QualityNCR)
        punches = self._related_quality(workspace, subject, QualityPunchItem)
        # Historical assessments cannot learn later quality observations.
        ncrs = [row for row in ncrs if row.created_at <= instant]
        punches = [row for row in punches if row.created_at <= instant]
        open_ncrs = [row for row in ncrs if row.status not in TERMINAL_NCR]
        open_punches = [row for row in punches if row.status != "CLOSED"]
        later_decisions = [row for row in (*ncrs, *punches) if row.updated_at > instant]
        missing = list(base.get("missing", []))
        if open_ncrs:
            missing.append("OPEN_NCR")
        if open_punches:
            missing.append("OPEN_PUNCH")
        state = base["state"]
        if later_decisions and state != "BROKEN_REFERENCE":
            # An operational status observed today cannot be projected backwards
            # as if a later closure had already been known at that instant.
            state = "STALE"
            missing.append("QUALITY_DECISION_AFTER_ASSESSMENT")
        if state not in {"STALE", "BROKEN_REFERENCE"} and (open_ncrs or open_punches):
            any_control_ready = base["state"] == "READY" or any(
                not item.get("issues") for item in base.get("items", [])
            )
            state = "PARTIALLY_READY" if any_control_ready else "NOT_READY"
        references = list(base.get("source_references", []))
        references.extend(self._execution_pin(row, "NCR") for row in ncrs if row.status == "CLOSED")
        references.extend(self._execution_pin(row, "PUNCH") for row in punches if row.status == "CLOSED")
        basis = {
            "itp": base["itp"],
            "subject_reference": subject,
            "source_references": references,
            "ncr_states": [
                {"id": row.id, "version": row.version, "status": row.status, "source_hash": row.source_hash}
                for row in ncrs
            ],
            "punch_states": [
                {"id": row.id, "version": row.version, "status": row.status, "source_hash": row.source_hash}
                for row in punches
            ],
        }
        return _json(
            {
                **base,
                "state": state,
                "missing": missing,
                "open_ncr_ids": [row.id for row in open_ncrs],
                "open_punch_ids": [row.id for row in open_punches],
                "source_references": references,
                "basis": basis,
                "basis_hash": _hash(basis),
                "assessed_at": instant.isoformat(),
                "authority": "QUALITY_ONLY",
                "awp_release_changed": False,
            }
        )

    def _acceptance_quantity_coverage(self, workspace, assessment, quantity, uom):
        """A partial inspected/tested quantity never implies acceptance of its whole subject."""
        required = [item for item in assessment.get("items", []) if item.get("required")]
        if not required:
            self._error(409, "QUALITY_ACCEPTANCE_REQUIRED_QUANTITY_CONTROLS_MISSING")
        for item in required:
            for label, kind, needed in (
                ("inspection_record", "INSPECTION", item.get("inspection_required")),
                ("test_record", "TEST", item.get("test_required")),
            ):
                if not needed:
                    continue
                pin = item.get(label) or {}
                if not pin.get("source_entity_id"):
                    self._error(409, "QUALITY_ACCEPTANCE_EXPLICIT_INSPECTED_QUANTITY_REQUIRED")
                result = self._execution_result(workspace, kind, pin["source_entity_id"], passed=True)
                if result.version != pin.get("source_version") or result.source_hash != pin.get("source_hash"):
                    self._error(409, "QUALITY_ACCEPTANCE_QUANTITY_RESULT_PIN_CHANGED")
                if result.quantity is None or not result.uom:
                    self._error(409, "QUALITY_ACCEPTANCE_EXPLICIT_INSPECTED_QUANTITY_REQUIRED")
                if result.uom != uom or quantity > result.quantity:
                    self._error(409, "QUALITY_ACCEPTANCE_QUANTITY_EXCEEDS_INSPECTED_OR_TESTED_COVERAGE")

    def create_acceptance(self, workspace, payload, key):
        self._ready(workspace, "acceptance.approve")

        def apply():
            _, profile = self._ready(workspace, "acceptance.approve")
            self._execution_catalog(profile.content_json, "acceptance_profiles", payload.acceptance_profile_code)
            effective = self._execution_observed(payload.effective_at)
            assessment = self.readiness(workspace, payload.itp_id, payload.subject_reference, as_of=effective)
            if assessment["state"] != "READY":
                self._error(409, "QUALITY_ALL_REQUIRED_CONTROLS_ACCEPTANCE_NOT_READY")
            current_assessment = self.readiness(workspace, payload.itp_id, payload.subject_reference)
            if current_assessment["state"] != "READY":
                self._error(409, "QUALITY_CURRENT_CONTROLS_ACCEPTANCE_NOT_READY")
            subject = assessment["subject_reference"]
            facts = subject.get("facts", {})
            amount = facts.get("quantity", facts.get("accepted_quantity"))
            unit = facts.get("uom", facts.get("unit"))
            if amount is None or unit != payload.uom or payload.quantity > Decimal(str(amount)):
                self._error(422, "QUALITY_ACCEPTANCE_GRANULAR_QUANTITY_OR_UOM_INVALID")
            self._acceptance_quantity_coverage(workspace, assessment, payload.quantity, payload.uom)
            self._acceptance_quantity_coverage(workspace, current_assessment, payload.quantity, payload.uom)
            policy = profile.content_json
            self._execution_sod(
                policy, "acceptance_inspector_cannot_approve", *assessment.get("inspector_user_ids", [])
            )
            self._execution_sod(policy, "acceptance_itp_author_cannot_approve", assessment.get("itp_prepared_by"))
            result_approvers = []
            for item in assessment.get("items", []):
                for label in ("inspection_record", "test_record"):
                    pin = item.get(label) or {}
                    result_approvers.append(pin.get("closed_by", pin.get("facts", {}).get("closed_by")))
            self._execution_sod(policy, "acceptance_result_approver_cannot_approve", *result_approvers)
            revision = 1
            key_subject = self._subject_key(subject)
            existing = list(
                self.db.scalars(
                    self._scoped(QualityAcceptance, workspace)
                    .where(
                        QualityAcceptance.subject_key == key_subject,
                    )
                    .order_by(QualityAcceptance.id)
                )
            )
            if payload.supersedes_id:
                old = self._get(QualityAcceptance, workspace, payload.supersedes_id, lock=True)
                if (
                    old.subject_key != key_subject
                    or old.acceptance_code != payload.acceptance_code.upper()
                    or any(candidate.supersedes_id == old.id for candidate in existing)
                ):
                    self._error(409, "QUALITY_ACCEPTANCE_SUCCESSOR_IDENTITY_INVALID")
                self._execution_integrity(old)
                revision = old.revision + 1
            elif existing:
                self._error(409, "QUALITY_ACCEPTANCE_EXPLICIT_SUCCESSOR_REQUIRED")
            row = self._new(
                QualityAcceptance,
                workspace,
                acceptance_code=payload.acceptance_code.upper(),
                revision=revision,
                supersedes_id=payload.supersedes_id,
                subject_key=key_subject,
                subject_reference=subject,
                itp_id=payload.itp_id,
                acceptance_profile_code=payload.acceptance_profile_code,
                quantity=payload.quantity,
                uom=payload.uom,
                effective_at=effective,
                document_reference=self._document(workspace, payload.document_reference),
                source_references=assessment["source_references"],
                readiness_snapshot=assessment["basis"],
                **self._execution_profile(profile),
            )
            return self._record(row, "QUALITY_ACCEPTANCE_APPROVED", payload.reason)

        return self._write("acceptance.approve", workspace, payload, key, apply)

    def acceptance_state(self, workspace, row):
        self._execution_integrity(row)
        if self.db.scalar(
            self._scoped(QualityAcceptance, workspace)
            .where(
                QualityAcceptance.supersedes_id == row.id,
            )
            .limit(1)
        ):
            return "SUPERSEDED"
        try:
            self._source_current(workspace, row.subject_reference)
            self._check_document(workspace, row.document_reference)
            current = self.readiness(workspace, row.itp_id, row.subject_reference)
            if current["state"] == "BROKEN_REFERENCE":
                return "BROKEN_REFERENCE"
            if current["state"] != "READY" or _hash(row.readiness_snapshot) != current["basis_hash"]:
                return "STALE"
            self._acceptance_quantity_coverage(workspace, current, row.quantity, row.uom)
        except HTTPException as error:
            if error.status_code not in {403, 404, 409, 422}:
                raise
            return "BROKEN_REFERENCE" if error.status_code == 404 else "STALE"
        return "CURRENT"

    def execution_collection(self, workspace, resource, *, limit=50, after_id=0, status=None, ncr_id=None):
        self._read_project(workspace)
        model = RESOURCES[resource]
        query = self._scoped(model, workspace).where(model.id > after_id)
        if status:
            query = query.where(model.status == status)
        if ncr_id:
            self._get(QualityNCR, workspace, ncr_id)
            if not hasattr(model, "ncr_id"):
                self._error(422, "QUALITY_NCR_FILTER_NOT_APPLICABLE")
            query = query.where(model.ncr_id == ncr_id)
        rows = list(self.db.scalars(query.order_by(model.id).limit(limit + 1)))
        return {
            "items": [self._redact(workspace, self._out(row)) for row in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
        }

    def execution_detail(self, workspace, resource, identity):
        self._read_project(workspace)
        row = self._get(RESOURCES[resource], workspace, identity)
        value = self._out(row)
        if isinstance(row, QualityAcceptance):
            value["source_state"] = self.acceptance_state(workspace, row)
        return self._redact(workspace, value)

    def dashboard(self, workspace):
        self._read_project(workspace)
        counts = {}
        for resource, model in RESOURCES.items():
            values = list(self.db.scalars(self._scoped(model, workspace)))
            counts[resource] = {
                status: sum(row.status == status for row in values) for status in sorted({row.status for row in values})
            }
        return {"counts": counts, "authority": "QUALITY_ONLY", "as_of": utc_now().isoformat()}

    def _lookahead_pending(self, workspace, candidates, selected, instant):
        """Derive pending controls/acceptance from bounded captured requests, never new facts."""
        controls, groups, items, assessments = {}, {}, {}, {}

        def item_for(row):
            if row.itp_item_id not in items:
                items[row.itp_item_id] = self._get(ITPItem, workspace, row.itp_item_id)
            return items[row.itp_item_id]

        def assessment_for(row):
            item = item_for(row)
            key = (item.itp_id, row.subject_key)
            if key not in assessments:
                assessments[key] = self.readiness(workspace, item.itp_id, row.subject_reference, as_of=instant)
            return assessments[key]

        def newest(row, old):
            return old is None or (row.requested_for, row.created_at, row.id) > (
                old.requested_for,
                old.created_at,
                old.id,
            )

        for row in candidates:
            item = item_for(row)
            control_key = (item.id, row.subject_key)
            group_key = (item.itp_id, row.subject_key)
            if item.control_type in {"HOLD", "WITNESS"} and newest(row, controls.get(control_key)):
                controls[control_key] = row
            if newest(row, groups.get(group_key)):
                groups[group_key] = row

        pending_points, pending_acceptance = [], []
        for row in controls.values():
            if not selected(row, "PENDING_RELEASE"):
                continue
            item = item_for(row)
            assessment = assessment_for(row)
            point = next((value for value in assessment.get("items", []) if value["itp_item_id"] == item.id), None)
            if point and point.get("control_decision") and not point.get("issues"):
                continue
            pending_points.append(
                {
                    "itp_id": item.itp_id,
                    "itp_item_id": item.id,
                    "itp_item_code": item.itp_item_code,
                    "control_type": item.control_type,
                    "subject_key": row.subject_key,
                    "subject_reference": row.subject_reference,
                    "request_id": row.id,
                    "request_entity_type": type(row).__name__,
                    "requested_for": row.requested_for,
                    "status": "PENDING_RELEASE",
                    "readiness_state": assessment["state"],
                    "missing": point.get("issues", []) if point else assessment.get("missing", []),
                    "authority": "QUALITY_CONTROL_ONLY_NOT_AWP_RELEASE",
                }
            )

        for row in groups.values():
            item = item_for(row)
            assessment = assessment_for(row)
            quantities, units, complete = [], set(), True
            for point in assessment.get("items", []):
                if not point.get("required"):
                    continue
                for label, model, needed in (
                    ("inspection_record", InspectionRecord, point.get("inspection_required")),
                    ("test_record", TestRecord, point.get("test_required")),
                ):
                    if not needed:
                        continue
                    pin = point.get(label) or {}
                    result = (
                        self._get(model, workspace, pin["source_entity_id"]) if pin.get("source_entity_id") else None
                    )
                    if result is None or result.quantity is None or not result.uom:
                        complete = False
                    else:
                        quantities.append(result.quantity)
                        units.add(result.uom)
            quantity = min(quantities) if complete and quantities and len(units) == 1 else None
            uom = next(iter(units)) if quantity is not None else row.uom
            current = self.db.scalar(
                self._scoped(QualityAcceptance, workspace)
                .where(
                    QualityAcceptance.itp_id == item.itp_id,
                    QualityAcceptance.subject_key == row.subject_key,
                )
                .order_by(QualityAcceptance.id.desc())
                .limit(1)
            )
            accepted_quantity = Decimal(0)
            if (
                current
                and current.subject_reference == row.subject_reference
                and self.acceptance_state(workspace, current) == "CURRENT"
            ):
                accepted_quantity = current.quantity
            if quantity is not None and accepted_quantity >= quantity:
                continue
            state = (
                "AWAITING_CONTROLS"
                if assessment["state"] != "READY"
                else "QUANTITY_SCOPE_REQUIRED"
                if quantity is None
                else "PARTIALLY_ACCEPTED"
                if accepted_quantity > 0
                else "READY_FOR_ACCEPTANCE"
            )
            if not selected(row, state):
                continue
            pending_acceptance.append(
                {
                    "itp_id": item.itp_id,
                    "subject_key": row.subject_key,
                    "subject_reference": row.subject_reference,
                    "requested_for": row.requested_for,
                    "status": state,
                    "readiness_state": assessment["state"],
                    "controlled_quantity": quantity,
                    "accepted_quantity": accepted_quantity,
                    "pending_quantity": max(Decimal(0), quantity - accepted_quantity) if quantity is not None else None,
                    "uom": uom,
                    "latest_acceptance_id": current.id if current else None,
                    "missing": assessment.get("missing", [])
                    + (["EXPLICIT_CONTROL_QUANTITY_REQUIRED"] if quantity is None else []),
                    "next_action": "EXPLICIT_QUALITY_ACCEPTANCE_OR_SUCCESSOR",
                    "authority": "QUALITY_ONLY_NOT_PROGRESS_APPROVAL",
                }
            )
        return {"hold_witness_pending": pending_points, "acceptance_pending": pending_acceptance}

    def lookahead(
        self,
        workspace,
        *,
        horizon_days=14,
        as_of=None,
        status=None,
        iwp_id=None,
        workfront_id=None,
        cwp_id=None,
        discipline=None,
        vendor_id=None,
        inspector_user_id=None,
        date_from=None,
        date_to=None,
        location=None,
    ):
        self._read_project(workspace)
        instant = self._assessment_time(as_of)
        if instant > utc_now():
            self._error(422, "QUALITY_FUTURE_ASSESSMENT_FORBIDDEN")
        until = instant + timedelta(days=horizon_days)
        lower = date_from
        upper = date_to or until.date()
        if lower and upper < lower:
            self._error(422, "QUALITY_LOOKAHEAD_DATE_RANGE_INVALID")
        if iwp_id:
            self.resolve_reference(workspace, {"target_kind": "IWP", "target_id": iwp_id})
        if cwp_id:
            self.resolve_reference(workspace, {"target_kind": "CWP", "target_id": cwp_id})
        if workfront_id:
            self.source_lookup(workspace, "FIELD_WORKFRONT", workfront_id)
        if vendor_id:
            from app.modules.procurement_foundation.sourcing_models import ProcurementVendor

            if (
                self.db.scalar(
                    select(ProcurementVendor.id).where(
                        ProcurementVendor.tenant_id == self.tenant_id, ProcurementVendor.id == vendor_id
                    )
                )
                is None
            ):
                self._error(404, "QUALITY_VENDOR_NOT_FOUND")
        if inspector_user_id:
            if (
                self.db.scalar(
                    select(UserAccount.id).where(
                        UserAccount.tenant_id == self.tenant_id, UserAccount.id == inspector_user_id
                    )
                )
                is None
            ):
                self._error(404, "QUALITY_PERSON_NOT_FOUND")
        actions = list(
            self.db.scalars(
                self._scoped(QualityCorrectiveAction, workspace)
                .where(
                    QualityCorrectiveAction.due_date <= upper,
                    QualityCorrectiveAction.status != "CLOSED",
                    QualityCorrectiveAction.created_at <= instant,
                )
                .order_by(QualityCorrectiveAction.due_date, QualityCorrectiveAction.id)
                .limit(200)
            )
        )
        punches = list(
            self.db.scalars(
                self._scoped(QualityPunchItem, workspace)
                .where(
                    QualityPunchItem.due_date <= upper,
                    QualityPunchItem.status != "CLOSED",
                    QualityPunchItem.created_at <= instant,
                )
                .order_by(QualityPunchItem.due_date, QualityPunchItem.id)
                .limit(200)
            )
        )
        request_candidates = list(
            self.db.scalars(
                self._scoped(InspectionRequest, workspace)
                .where(
                    InspectionRequest.status != "CANCELLED",
                    InspectionRequest.created_at <= instant,
                    InspectionRequest.requested_for < datetime.combine(upper + timedelta(days=1), datetime.min.time()),
                )
                .order_by(InspectionRequest.id)
                .limit(200)
            )
        )
        test_candidates = list(
            self.db.scalars(
                self._scoped(TestRequest, workspace)
                .where(
                    TestRequest.status != "CANCELLED",
                    TestRequest.created_at <= instant,
                    TestRequest.requested_for < datetime.combine(upper + timedelta(days=1), datetime.min.time()),
                )
                .order_by(TestRequest.id)
                .limit(200)
            )
        )
        ncrs = list(
            self.db.scalars(
                self._scoped(QualityNCR, workspace)
                .where(
                    QualityNCR.status.not_in(TERMINAL_NCR),
                    QualityNCR.due_date <= upper,
                    QualityNCR.created_at <= instant,
                )
                .order_by(QualityNCR.due_date, QualityNCR.id)
                .limit(200)
            )
        )

        canonical_context = {}

        def related(model, identity):
            if not identity:
                return None
            key = (model, identity)
            if key not in canonical_context:
                canonical_context[key] = self._get(model, workspace, identity)
            return canonical_context[key]

        def context(row, facts, itp):
            # Filters follow existing scoped owners instead of inventing denormalized
            # cwp/vendor fields or altering the historical subject hash.
            from app.modules.field_operations.execution_models import ProductionRecord
            from app.modules.field_operations.models import Workfront
            from app.modules.procurement_foundation.materials_models import (
                ProcurementMaterialReceipt,
                ProcurementMaterialReceiptLine,
                ProcurementShipment,
            )

            cwp_ids = {facts.get("cwp_id")}
            vendors = {facts.get("vendor_id"), getattr(row, "laboratory_vendor_id", None)}
            if cwp_id and facts.get("workfront_id"):
                front = related(Workfront, facts["workfront_id"])
                cwp_ids.add(front.cwp_id)
            if cwp_id and itp:
                cwp_ids.update(
                    reference.get("target_id")
                    for reference in itp.source_references
                    if reference.get("target_kind") == "CWP"
                )
            receipt_line_id = facts.get("material_receipt_line_id", facts.get("receipt_line_id"))
            reference = row.subject_reference
            if (
                vendor_id
                and not receipt_line_id
                and reference.get("source_type") in {"FIELD_PRODUCTION", "FIELD_REWORK"}
            ):
                production = related(ProductionRecord, reference.get("source_entity_id", reference.get("source_id")))
                material = production.material_reference or {}
                receipt_line_id = material.get("facts", {}).get("material_receipt_line_id") or material.get(
                    "facts", {}
                ).get("receipt_line_id")
            if vendor_id and receipt_line_id:
                line = related(ProcurementMaterialReceiptLine, receipt_line_id)
                receipt = related(ProcurementMaterialReceipt, line.receipt_id)
                vendors.add(related(ProcurementShipment, receipt.shipment_id).vendor_id)
            return cwp_ids, vendors

        def selected(row, derived_status=None):
            facts = row.subject_reference.get("facts", {})
            scheduled = getattr(row, "requested_for", None)
            day = scheduled.date() if scheduled else getattr(row, "due_date", None)
            location_value = str(facts.get("location_reference", facts.get("location", ""))).casefold()
            if (
                (iwp_id and facts.get("iwp_id") != iwp_id)
                or (workfront_id and facts.get("workfront_id") != workfront_id)
                or (inspector_user_id and getattr(row, "inspector_user_id", None) != inspector_user_id)
                or (lower and (day is None or day < lower))
                or (location and location.casefold() not in location_value)
            ):
                return False
            item = self._get(ITPItem, workspace, row.itp_item_id) if hasattr(row, "itp_item_id") else None
            if item is None and discipline:
                ncr = row if isinstance(row, QualityNCR) else related(QualityNCR, getattr(row, "ncr_id", None))
                if ncr:
                    result = related(InspectionRecord, ncr.inspection_record_id) or related(
                        TestRecord, ncr.test_record_id
                    )
                    item = related(ITPItem, result.itp_item_id) if result else None
            itp = self._get(InspectionTestPlan, workspace, item.itp_id) if item else None
            applicable_discipline = itp.discipline if itp else facts.get("discipline")
            if discipline and not applicable_discipline and facts.get("scope_item_id"):
                from app.modules.scope_foundation.models import ScopeItem

                applicable_discipline = related(ScopeItem, facts["scope_item_id"]).discipline
            cwp_ids, vendor_ids = context(row, facts, itp) if cwp_id or vendor_id else (set(), set())
            return (
                (not status or row.status == status or derived_status == status)
                and (not cwp_id or cwp_id in cwp_ids)
                and (not discipline or applicable_discipline == discipline)
                and (not vendor_id or vendor_id in vendor_ids)
            )

        requests = [row for row in request_candidates if row.status != "COMPLETED"]
        tests = [row for row in test_candidates if row.status != "COMPLETED"]
        # Apply the same canonical dimensional/date filters before resolving
        # readiness. A request outside the requested context must not cause an
        # unrelated stale/broken reference to abort this read-only projection.
        # Passing the requested status only bypasses that one dimension here;
        # the helper applies the actual derived status after it is known.
        pending_candidates = [row for row in [*request_candidates, *test_candidates] if selected(row, status)]
        pending = self._lookahead_pending(workspace, pending_candidates, selected, instant)
        return {
            "as_of": instant.isoformat(),
            "horizon_days": horizon_days,
            "corrective_actions": [self._redact(workspace, self._out(row)) for row in actions if selected(row)],
            "punch_items": [self._redact(workspace, self._out(row)) for row in punches if selected(row)],
            "inspection_requests": [self._redact(workspace, self._out(row)) for row in requests if selected(row)],
            "test_requests": [self._redact(workspace, self._out(row)) for row in tests if selected(row)],
            "ncrs_due": [self._redact(workspace, self._out(row)) for row in ncrs if selected(row)],
            **self._redact(workspace, _json(pending)),
            "reinspections": [
                self._redact(workspace, self._out(row)) for row in requests if row.reinspection_of_id and selected(row)
            ],
            "filters": {
                "iwp_id": iwp_id,
                "cwp_id": cwp_id,
                "workfront_id": workfront_id,
                "discipline": discipline,
                "vendor_id": vendor_id,
                "inspector_user_id": inspector_user_id,
                "date_from": lower.isoformat() if lower else None,
                "date_to": upper.isoformat(),
                "location": location,
            },
            "schedule_authority": "P6_UNCHANGED",
            "records_limited_to": 200,
        }

    def trace(self, workspace, entity_type, identity):
        self._read_project(workspace)
        types = {
            "NCR": QualityNCR,
            "CORRECTIVE_ACTION": QualityCorrectiveAction,
            "PUNCH": QualityPunchItem,
            "ACCEPTANCE": QualityAcceptance,
            "INSPECTION": InspectionRecord,
            "TEST": TestRecord,
            "PLAN": QualityPlan,
            "ITP": InspectionTestPlan,
            "ITP_ITEM": ITPItem,
            "INSPECTION_REQUEST": InspectionRequest,
            "TEST_REQUEST": TestRequest,
        }
        if entity_type not in types:
            self._error(422, "QUALITY_TRACE_TYPE_UNSUPPORTED")
        row = self._get(types[entity_type], workspace, identity)
        subject = getattr(row, "subject_reference", None)
        ncrs = self._related_quality(workspace, subject, QualityNCR) if subject else []
        ncr_ids = [item.id for item in ncrs]
        actions = (
            list(
                self.db.scalars(
                    self._scoped(QualityCorrectiveAction, workspace)
                    .where(
                        QualityCorrectiveAction.ncr_id.in_(ncr_ids),
                    )
                    .order_by(QualityCorrectiveAction.id)
                    .limit(200)
                )
            )
            if ncr_ids
            else []
        )
        history = list(
            self.db.scalars(
                self._scoped(QualityHistory, workspace)
                .where(
                    QualityHistory.entity_type == type(row).__name__,
                    QualityHistory.entity_id == row.id,
                )
                .order_by(QualityHistory.id)
                .limit(200)
            )
        )
        item_ids = {row.itp_item_id} if hasattr(row, "itp_item_id") else set()
        itp_ids = {row.itp_id} if hasattr(row, "itp_id") else set()
        plan_ids = {row.id} if isinstance(row, QualityPlan) else set()
        if isinstance(row, InspectionTestPlan):
            itp_ids.add(row.id)
        if isinstance(row, ITPItem):
            item_ids.add(row.id)
        for ncr in ncrs:
            if ncr.inspection_record_id:
                item_ids.add(self._get(InspectionRecord, workspace, ncr.inspection_record_id).itp_item_id)
            if ncr.test_record_id:
                item_ids.add(self._get(TestRecord, workspace, ncr.test_record_id).itp_item_id)
        if plan_ids:
            itp_ids.update(
                self.db.scalars(
                    self._scoped(InspectionTestPlan, workspace)
                    .where(
                        InspectionTestPlan.quality_plan_id.in_(plan_ids),
                    )
                    .with_only_columns(InspectionTestPlan.id)
                    .limit(200)
                )
            )
        for item_id in item_ids:
            itp_ids.add(self._get(ITPItem, workspace, item_id).itp_id)
        itps = [self._get(InspectionTestPlan, workspace, itp_id) for itp_id in sorted(itp_ids)]
        plan_ids.update(value.quality_plan_id for value in itps)
        plans = [self._get(QualityPlan, workspace, plan_id) for plan_id in sorted(plan_ids)]
        items = (
            list(
                self.db.scalars(
                    self._scoped(ITPItem, workspace)
                    .where(
                        ITPItem.itp_id.in_(itp_ids),
                    )
                    .order_by(ITPItem.itp_id, ITPItem.sequence)
                    .limit(200)
                )
            )
            if itp_ids
            else []
        )
        all_item_ids = [item.id for item in items]
        chain = {}
        for label, model in (
            ("inspection_requests", InspectionRequest),
            ("test_requests", TestRequest),
            ("inspections", InspectionRecord),
            ("tests", TestRecord),
        ):
            values = (
                list(
                    self.db.scalars(
                        self._scoped(model, workspace)
                        .where(
                            model.itp_item_id.in_(all_item_ids),
                        )
                        .order_by(model.id)
                        .limit(200)
                    )
                )
                if all_item_ids
                else []
            )
            if subject:
                values = [value for value in values if value.subject_key == self._subject_key(subject)]
            chain[label] = [self._redact(workspace, self._out(value)) for value in values]
        return {
            "entity_type": entity_type,
            "entity": self._redact(workspace, self._out(row)),
            "subject_reference": subject,
            "plans": [self._redact(workspace, self._out(value)) for value in plans],
            "itps": [self._redact(workspace, self._out(value)) for value in itps],
            "itp_items": [self._redact(workspace, self._out(value)) for value in items],
            **chain,
            "ncrs": [self._redact(workspace, self._out(value)) for value in ncrs],
            "corrective_actions": [self._redact(workspace, self._out(value)) for value in actions],
            "acceptances": [
                self._redact(workspace, self._out(value))
                for value in (self._related_quality(workspace, subject, QualityAcceptance) if subject else [])
            ],
            "history": [self._redact(workspace, self._out(value)) for value in history],
            "downstream_write": False,
        }
