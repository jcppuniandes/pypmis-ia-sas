"""Read-only Quality adapters to actual Field, Engineering and Procurement facts.

Eligibility here belongs to inspection, not Progress: a verified Field fact may
be inspected before daily-report approval, and verified rework stays distinct.
"""

from datetime import UTC, datetime
from hmac import compare_digest

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.core.time import utc_now
from app.modules.basic_data.service import _hash, _json
from app.modules.engineering_foundation.models import EngineeringRelease, EngineeringRevision
from app.modules.field_operations.execution_models import FieldEvent, ProductionRecord, SiteInstruction
from app.modules.field_operations.models import DailyConstructionReport, FieldEquipmentReference, Workfront
from app.modules.field_operations.service import record_hash as field_hash
from app.modules.field_operations.sources import FieldSourceMixin
from app.modules.procurement_foundation.availability import material_acceptance_hash
from app.modules.procurement_foundation.materials_models import (
    ProcurementMaterialAcceptance,
    ProcurementMaterialAllocation,
    ProcurementMaterialItem,
    ProcurementMaterialReceipt,
    ProcurementMaterialReceiptLine,
    ProcurementMaterialRequirement,
)

FIELD_MODELS = {
    "FIELD_PRODUCTION": ProductionRecord,
    "FIELD_REWORK": ProductionRecord,
    "FIELD_WORKFRONT": Workfront,
    "FIELD_DAILY_REPORT": DailyConstructionReport,
    "FIELD_EVENT": FieldEvent,
    "FIELD_INSTRUCTION": SiteInstruction,
    "FIELD_EQUIPMENT_REFERENCE": FieldEquipmentReference,
}
SOURCE_MODELS = FIELD_MODELS | {
    "MATERIAL_RECEIPT_LINE": ProcurementMaterialReceiptLine,
    "MATERIAL_ACCEPTANCE": ProcurementMaterialAcceptance,
    "MATERIAL_ALLOCATION": ProcurementMaterialAllocation,
    "IFC_RELEASE": EngineeringRelease,
    "ENGINEERING_REVISION": EngineeringRevision,
}


def instant(value=None):
    value = value or utc_now()
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def iso(value):
    return instant(value).replace(tzinfo=UTC).isoformat()


class QualitySourceMixin(FieldSourceMixin):
    def resolve_reference(self, workspace, reference):
        """AWP assessment provenance is not a change of Quality's technical scope."""
        ref = reference.model_dump() if isinstance(reference, BaseModel) else reference
        kind = ref.get("target_kind")
        if kind not in {"CWP", "IWP"}:
            return super().resolve_reference(workspace, reference)
        from app.modules.awp.models import AWPHistory, WorkPackage

        row = self._get(WorkPackage, workspace, ref.get("target_id"))
        if row.package_type != kind or row.status == "SUPERSEDED":
            self._error(409, "QUALITY_PACKAGE_CONTEXT_NOT_APPLICABLE")
        fields = ("package_code", "package_type", "name", "description", "cwa_id", "owner_user_id", "responsible_role")
        context = {field: getattr(row, field) for field in fields}
        digest = _hash({"target_kind": kind, "target_id": row.id, "context": context})
        expected = ref.get("source_hash")
        if expected and ref.get("governance_projection") == "QUALITY_PACKAGE_CONTEXT_V1":
            if not compare_digest(expected, digest) or ref.get("package_context") != context:
                self._error(409, "QUALITY_PACKAGE_CONTEXT_CHANGED")
            return dict(ref)
        # The public ReferenceIn DTO intentionally carries just identity and hash.
        # Canonicalize a current semantic hash even without the saved projection.
        if expected and not compare_digest(expected, digest):
            # Preserve already captured pre-release references without rewriting
            # any governed row. The authoritative historical AWP snapshot proves
            # whether only status/readiness/version provenance changed.
            old = {key: ref.get(key) for key in ("target_kind", "target_id", "target_version", "code", "title")}
            historical = self.db.scalar(
                select(AWPHistory)
                .where(
                    AWPHistory.tenant_id == self.tenant_id,
                    AWPHistory.project_workspace_id == workspace,
                    AWPHistory.entity_type == "WorkPackage",
                    AWPHistory.entity_id == row.id,
                    AWPHistory.snapshot_json["version"].as_integer() == ref.get("target_version"),
                )
                .order_by(AWPHistory.id.desc())
                .limit(1)
            )
            if (
                not compare_digest(expected, _hash(old))
                or historical is None
                or {field: historical.snapshot_json.get(field) for field in fields} != context
            ):
                self._error(409, "QUALITY_PACKAGE_CONTEXT_HISTORY_CHANGED_OR_MISSING")
            return dict(ref)
        return {
            "target_kind": kind,
            "target_id": row.id,
            "target_version": row.version,
            "code": row.package_code,
            "title": row.name,
            "governance_projection": "QUALITY_PACKAGE_CONTEXT_V1",
            "package_context": context,
            "source_hash": digest,
        }

    def _source_root(self, workspace, row):
        root, seen = row, set()
        while getattr(root, "supersedes_id", None):
            if root.id in seen:
                self._error(409, "QUALITY_SOURCE_LINEAGE_CYCLE")
            seen.add(root.id)
            root = self._get(type(row), workspace, root.supersedes_id)
        return root

    def _field_source(self, workspace, kind, identity, at):
        row = self._get(FIELD_MODELS[kind], workspace, identity)
        if row.source_hash != field_hash(row):
            self._error(409, "QUALITY_FIELD_SOURCE_INTEGRITY")
        if row.created_at > at:
            self._error(409, "QUALITY_SOURCE_NOT_YET_RECORDED")
        if isinstance(row, ProductionRecord):
            if row.status != "VERIFIED":
                self._error(409, "QUALITY_VERIFIED_PRODUCTION_REQUIRED")
            if (kind == "FIELD_REWORK") != (row.production_type == "REWORKED"):
                self._error(422, "QUALITY_PRODUCTION_REWORK_TYPE_MISMATCH")
            if row.observed_at > at:
                self._error(409, "QUALITY_PRODUCTION_OBSERVED_AFTER_INSPECTION")
            if row.verified_at is None or row.verified_at > at:
                self._error(409, "QUALITY_PRODUCTION_NOT_VERIFIED_AT_INSPECTION")
        elif isinstance(row, DailyConstructionReport) and row.status != "APPROVED":
            self._error(409, "QUALITY_APPROVED_DAILY_REPORT_REQUIRED")
        elif isinstance(row, DailyConstructionReport) and (row.approved_at is None or row.approved_at > at):
            self._error(409, "QUALITY_DAILY_REPORT_NOT_APPROVED_AT_INSPECTION")
        elif isinstance(row, Workfront) and row.status not in {"ACTIVE", "SUSPENDED", "COMPLETE"}:
            self._error(409, "QUALITY_WORKFRONT_NOT_EXECUTION_CONTEXT")
        elif isinstance(row, SiteInstruction) and row.status not in {"ISSUED", "ACKNOWLEDGED", "CLOSED"}:
            self._error(409, "QUALITY_ISSUED_INSTRUCTION_REQUIRED")
        elif isinstance(row, FieldEquipmentReference) and row.status != "AVAILABLE":
            self._error(409, "QUALITY_EQUIPMENT_REFERENCE_INACTIVE")
        if hasattr(type(row), "supersedes_id"):
            terminal = "VERIFIED" if isinstance(row, ProductionRecord) else "APPROVED"
            newer = self.db.scalar(
                select(type(row).id)
                .where(
                    type(row).tenant_id == self.tenant_id,
                    type(row).project_workspace_id == workspace,
                    type(row).supersedes_id == row.id,
                    type(row).status == terminal,
                )
                .limit(1)
            )
            if newer:
                self._error(409, "QUALITY_FIELD_SOURCE_SUPERSEDED")
        for key in ("document_reference", "document_references"):
            refs = getattr(row, key, None)
            for ref in refs if isinstance(refs, list) else [refs] if refs else []:
                self._check_document(workspace, ref)
        root = self._source_root(workspace, row)
        facts = {"status": row.status, "source_root_id": root.id}
        for field in (
            "scope_item_id",
            "plan_item_id",
            "iwp_id",
            "workfront_id",
            "shift_id",
            "report_id",
            "quantity",
            "uom",
            "production_type",
            "original_production_id",
            "location_reference",
            "description",
            "title",
            "event_type",
            "instruction_type",
            "external_id",
            "source_system",
            "equipment_type",
        ):
            if hasattr(row, field):
                facts[field] = getattr(row, field)
        if isinstance(row, Workfront):
            facts["workfront_id"] = row.id
        if getattr(row, "original_production_id", None):
            original = self._get(ProductionRecord, workspace, row.original_production_id)
            if original.source_hash != field_hash(original):
                self._error(409, "QUALITY_REWORK_ORIGIN_INTEGRITY")
            facts["original_production_root_id"] = self._source_root(workspace, original).id
        observed = getattr(row, "observed_at", None) or row.created_at
        return row, root.id, row.source_hash, observed, facts

    def _material_source(self, workspace, kind, identity, at):
        allocation = acceptance = None
        if kind == "MATERIAL_ALLOCATION":
            pin = self.source_pin(workspace, kind, identity, as_of=at)
            allocation = self._get(ProcurementMaterialAllocation, workspace, identity)
            row = allocation
            line = self._get(ProcurementMaterialReceiptLine, workspace, allocation.receipt_line_id)
            acceptance = self._get(ProcurementMaterialAcceptance, workspace, allocation.acceptance_id)
            digest = pin["source_hash"]
            amount = allocation.quantity
        elif kind == "MATERIAL_ACCEPTANCE":
            acceptance = row = self._get(ProcurementMaterialAcceptance, workspace, identity)
            if acceptance.content_hash != material_acceptance_hash(acceptance) or acceptance.accepted_quantity <= 0:
                self._error(409, "QUALITY_PROCUREMENT_ACCEPTANCE_INVALID")
            line = self._get(ProcurementMaterialReceiptLine, workspace, acceptance.receipt_line_id)
            digest, amount = acceptance.content_hash, acceptance.accepted_quantity
        else:
            row = line = self._get(ProcurementMaterialReceiptLine, workspace, identity)
            digest, amount = None, line.quantity
        receipt = self._get(ProcurementMaterialReceipt, workspace, line.receipt_id)
        material = self._get(ProcurementMaterialItem, workspace, line.material_item_id)
        requirement = self._get(ProcurementMaterialRequirement, workspace, line.material_requirement_id)
        if max(row.created_at, line.created_at, receipt.created_at) > at or receipt.received_at > at:
            self._error(409, "QUALITY_MATERIAL_NOT_RECEIVED_AT_INSPECTION")
        if requirement.material_item_id != material.id or material.uom != line.uom or amount <= 0:
            self._error(409, "QUALITY_MATERIAL_IDENTITY_OR_UOM_INVALID")
        if receipt.document_reference_json:
            self._check_document(workspace, receipt.document_reference_json)
        facts = {
            "material_receipt_line_id": line.id,
            "receipt_id": receipt.id,
            "material_item_id": material.id,
            "material_code": material.material_code,
            "material_requirement_id": requirement.id,
            "quantity": amount,
            "uom": line.uom,
            "receipt_document": receipt.document_reference_json,
            "location": receipt.location,
            "acceptance_id": acceptance.id if acceptance else None,
            "iwp_id": allocation.work_package_id if allocation else None,
        }
        # Receipt lines have no independent content hash; retain all owning identities.
        digest = digest or _hash({"receipt_line": self._out(line), "receipt": self._out(receipt)})
        return row, line.id, digest, receipt.received_at, facts

    def source_lookup(self, workspace, kind, identity, as_of=None):
        if kind not in SOURCE_MODELS:
            self._error(422, "QUALITY_SOURCE_TYPE_NOT_SUPPORTED")
        at = instant(as_of)
        if at > utc_now():
            self._error(422, "QUALITY_FUTURE_SOURCE_OBSERVATION_FORBIDDEN")
        if kind in FIELD_MODELS:
            row, root, digest, observed, facts = self._field_source(workspace, kind, identity, at)
            domain, entity = "FIELD_OPERATIONS", kind.removeprefix("FIELD_")
        elif kind.startswith("MATERIAL_"):
            row, root, digest, observed, facts = self._material_source(workspace, kind, identity, at)
            domain, entity = "PROCUREMENT", kind
        elif kind == "IFC_RELEASE":
            value = self.source_pin(workspace, kind, identity, as_of=at)
            row = self._get(EngineeringRelease, workspace, identity)
            root, digest, observed, facts = row.id, value["source_hash"], row.released_at, value["facts"]
            domain, entity = "ENGINEERING", kind
        else:
            from app.modules.engineering_foundation.service import EngineeringFoundationService

            row = self._get(EngineeringRevision, workspace, identity)
            if row.status != "APPROVED" or row.approved_at is None or row.approved_at > at:
                self._error(409, "QUALITY_APPROVED_ENGINEERING_REVISION_AT_INSPECTION_REQUIRED")
            if row.content_hash != _hash(EngineeringFoundationService._material(row)):
                self._error(409, "QUALITY_ENGINEERING_REVISION_INTEGRITY")
            # A direct revision is metadata evidence, not a substitute for an IFC release.
            root, digest, observed = row.id, row.content_hash, row.approved_at
            facts = {
                "revision_id": row.id,
                "deliverable_id": row.deliverable_id,
                "revision_code": row.revision_code,
                "status": row.status,
            }
            domain, entity = "ENGINEERING", kind
        subject_kind = "MATERIAL_RECEIPT_LINE" if domain == "PROCUREMENT" else entity
        return _json(
            {
                "source_type": kind,
                "source_id": row.id,
                "source_version": row.version,
                "source_hash": digest,
                "source_domain": domain,
                "source_entity_type": entity,
                "source_entity_id": row.id,
                "source_root_id": root,
                "subject_key": f"{domain}:{subject_kind}:{root}",
                "observed_at": iso(observed),
                "facts": facts,
            }
        )

    def _subject(self, workspace, pin, as_of=None):
        data = pin.model_dump() if isinstance(pin, BaseModel) else pin
        if not isinstance(data, dict):
            self._error(422, "QUALITY_TYPED_SOURCE_REFERENCE_REQUIRED")
        value = self.source_lookup(workspace, data.get("source_type"), data.get("source_id"), as_of)
        if value["source_version"] != data.get("source_version"):
            self._error(409, "QUALITY_SOURCE_VERSION_MISMATCH")
        expected = data.get("source_hash")
        if not isinstance(expected, str) or not compare_digest(value["source_hash"], expected):
            self._error(409, "QUALITY_SOURCE_HASH_MISMATCH")
        return value

    def _source_current(self, workspace, pin, as_of=None):
        current = self._subject(workspace, pin, as_of)
        data = pin.model_dump() if isinstance(pin, BaseModel) else pin
        if "facts" in data and current != data:
            self._error(409, "QUALITY_SOURCE_PROJECTION_CHANGED")
        return current

    def source_targets(self, workspace, kind, limit=100, after_id=0):
        self._read_project(workspace)
        if kind not in SOURCE_MODELS:
            self._error(422, "QUALITY_SOURCE_TYPE_NOT_SUPPORTED")
        model = SOURCE_MODELS[kind]
        rows = list(
            self.db.scalars(
                select(model)
                .where(
                    model.tenant_id == self.tenant_id,
                    model.project_workspace_id == workspace,
                    model.id > after_id,
                )
                .order_by(model.id)
                .limit(limit + 1)
            )
        )
        items = []
        for row in rows[:limit]:
            try:
                items.append(self.source_lookup(workspace, kind, row.id))
            except HTTPException as error:
                if error.status_code not in {403, 404, 409, 422}:
                    raise
        return {"items": items, "next_cursor": rows[limit - 1].id if len(rows) > limit else None}
