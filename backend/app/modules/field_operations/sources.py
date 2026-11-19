"""Read-only adapters to existing master identities and governed upstream evidence."""

from datetime import UTC
from hmac import compare_digest

from pydantic import BaseModel
from sqlalchemy import select

from app.core.time import utc_now
from app.domain.models import EnterpriseWorkspace
from app.modules.basic_data.service import _hash, _json
from app.modules.engineering_foundation.integration import EngineeringIntegrationMixin
from app.modules.procurement_foundation.availability import (
    active_allocations,
    material_acceptance_hash,
    material_allocation_hash,
)
from app.modules.procurement_foundation.integration import TARGET_MODELS, ProcurementIntegrationMixin
from app.modules.procurement_foundation.materials_models import (
    ProcurementMaterialAcceptance,
    ProcurementMaterialAllocation,
    ProcurementMaterialItem,
    ProcurementMaterialReceiptLine,
    ProcurementMaterialRequirement,
)

GEOGRAPHIC_TYPES = {"region", "district", "site", "linear-asset"}


def _iso(value):
    return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.astimezone(UTC).isoformat()


class FieldSourceMixin(ProcurementIntegrationMixin):
    def _verify_ifc(self, workspace, release):
        from app.modules.engineering_foundation.integration import (
            EngineeringReadinessReader,
            _effective_release,
        )
        from app.modules.engineering_foundation.models import EngineeringRelease, EngineeringRevision

        instant = getattr(self, "_field_ifc_as_of", None) or utc_now()
        if instant.tzinfo is not None:
            instant = instant.astimezone(UTC).replace(tzinfo=None)
        reader = EngineeringReadinessReader(self.db, self.tenant_id, workspace, [])
        reader.revision_by_id = {
            row.id: row
            for row in self.db.scalars(
                select(EngineeringRevision).where(
                    EngineeringRevision.tenant_id == self.tenant_id,
                    EngineeringRevision.project_workspace_id == workspace,
                    EngineeringRevision.deliverable_id == release.deliverable_id,
                )
            )
        }
        releases = list(
            self.db.scalars(
                select(EngineeringRelease).where(
                    EngineeringRelease.tenant_id == self.tenant_id,
                    EngineeringRelease.project_workspace_id == workspace,
                    EngineeringRelease.deliverable_id == release.deliverable_id,
                )
            )
        )
        current = _effective_release(releases, reader.revision_by_id, instant.date(), instant)
        if current is None or current.id != release.id:
            self._error(409, "FIELD_IFC_NOT_EFFECTIVE_AT_EXECUTION")
        if reader._source_reason(
            {"required_revision_ids": [release.revision_id]}, release, releases, instant.date(), instant
        ):
            self._error(409, "FIELD_IFC_SOURCE_INVALID_AT_EXECUTION")

    def resolve_document(self, workspace, document_id, attachment_id, expected_hash=None):
        value = EngineeringIntegrationMixin._resolve_document(self, workspace, document_id, attachment_id)
        if expected_hash and not compare_digest(expected_hash, value["sha256"]):
            self._error(409, "FIELD_CDE_HASH_MISMATCH")
        return value

    def _document(self, workspace, pin):
        values = pin.model_dump() if isinstance(pin, BaseModel) else pin
        return self.resolve_document(
            workspace, values["document_id"], values["attachment_id"], values.get("source_hash") or values.get("sha256")
        )

    def _check_document(self, workspace, snapshot):
        value = self._document(workspace, snapshot)
        if any(
            snapshot.get(key) != value.get(key)
            for key in (
                "document_version",
                "attachment_version",
                "binding_id",
                "revision",
            )
            if key in snapshot
        ):
            self._error(409, "FIELD_CDE_REVISION_CHANGED")
        return value

    def resolve_reference(self, workspace, reference):
        value = reference.model_dump() if isinstance(reference, BaseModel) else reference
        if value.get("target_kind") != "GEOGRAPHIC_WORKSPACE":
            return ProcurementIntegrationMixin.resolve_reference(self, workspace, value)
        row = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == value.get("target_id"),
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.status == "active",
                EnterpriseWorkspace.workspace_type_code.in_(GEOGRAPHIC_TYPES),
            )
        )
        if row is None:
            self._error(404, "FIELD_GEOGRAPHIC_MASTER_NOT_FOUND")
        snapshot = {
            "target_kind": "GEOGRAPHIC_WORKSPACE",
            "target_id": row.id,
            "target_version": row.version,
            "code": row.code,
            "title": row.name,
            "workspace_type": row.workspace_type_code,
        }
        digest = _hash(snapshot)
        if value.get("source_hash") and not compare_digest(value["source_hash"], digest):
            self._error(409, "FIELD_GEOGRAPHIC_MASTER_STALE")
        return snapshot | {"source_hash": digest}

    def reference_targets(self, workspace, target_kind, limit=100, after_id=0):
        self._read_project(workspace)
        if target_kind in {"MATERIAL_ITEM", "MATERIAL_ALLOCATION"}:
            model = ProcurementMaterialItem if target_kind == "MATERIAL_ITEM" else ProcurementMaterialAllocation
        elif target_kind == "GEOGRAPHIC_WORKSPACE":
            model = EnterpriseWorkspace
        else:
            model = TARGET_MODELS.get(target_kind)
        if model is None:
            self._error(422, "FIELD_REFERENCE_KIND_NOT_SUPPORTED")
        statement = select(model).where(model.tenant_id == self.tenant_id, model.id > after_id)
        if model is EnterpriseWorkspace:
            statement = statement.where(model.workspace_type_code.in_(GEOGRAPHIC_TYPES), model.status == "active")
        else:
            statement = statement.where(model.project_workspace_id == workspace)
        if target_kind in {"CWP", "PWP", "EWP", "IWP"}:
            statement = statement.where(model.package_type == target_kind)
        candidates = list(self.db.scalars(statement.order_by(model.id).limit(limit + 1)))
        items = []
        for row in candidates[:limit]:
            try:
                if target_kind in {"IFC_RELEASE", "MATERIAL_ITEM", "MATERIAL_ALLOCATION"}:
                    item = self.source_pin(workspace, target_kind, row.id)
                else:
                    item = self.resolve_reference(workspace, {"target_kind": target_kind, "target_id": row.id})
                items.append(item)
            except Exception as error:
                from fastapi import HTTPException

                if not isinstance(error, HTTPException) or error.status_code not in {403, 404, 409, 422}:
                    raise
        return {"items": items, "next_cursor": candidates[limit - 1].id if len(candidates) > limit else None}

    def source_pin(self, workspace, kind, identity, expected_version=None, expected_hash=None, as_of=None):
        if kind == "IFC_RELEASE":
            from app.modules.engineering_foundation.models import EngineeringRelease

            row = self._get(EngineeringRelease, workspace, identity)
            previous = getattr(self, "_field_ifc_as_of", None)
            self._field_ifc_as_of = as_of
            try:
                reference = self.resolve_reference(workspace, {"target_kind": kind, "target_id": identity})
            finally:
                self._field_ifc_as_of = previous
            digest = reference["source_hash"]
            facts = reference
            domain = "ENGINEERING"
        elif kind == "MATERIAL_ITEM":
            row = self._get(ProcurementMaterialItem, workspace, identity)
            facts = self._out(row)
            digest = _hash(facts)
            domain = "PROCUREMENT"
        elif kind == "MATERIAL_ALLOCATION":
            row = self._get(ProcurementMaterialAllocation, workspace, identity)
            observed = as_of or utc_now()
            if observed.tzinfo is not None:
                observed = observed.astimezone(UTC).replace(tzinfo=None)
            if row.created_at > observed or row.allocation_date > observed.date():
                self._error(409, "FIELD_MATERIAL_ALLOCATION_NOT_EFFECTIVE_AT_EXECUTION")
            if row.id not in {
                item.id for item in active_allocations(self.db, self.tenant_id, workspace, as_of=observed)
            }:
                self._error(409, "FIELD_MATERIAL_ALLOCATION_NOT_CURRENT")
            if row.expires_on and row.expires_on < observed.date():
                self._error(409, "FIELD_MATERIAL_ALLOCATION_EXPIRED")
            if row.content_hash != material_allocation_hash(row):
                self._error(409, "FIELD_MATERIAL_ALLOCATION_INTEGRITY")
            acceptance = self._get(ProcurementMaterialAcceptance, workspace, row.acceptance_id)
            receipt = self._get(ProcurementMaterialReceiptLine, workspace, row.receipt_line_id)
            requirement = self._get(ProcurementMaterialRequirement, workspace, row.material_requirement_id)
            if (
                acceptance.content_hash != material_acceptance_hash(acceptance)
                or acceptance.receipt_line_id != receipt.id
                or acceptance.accepted_quantity < row.quantity
                or requirement.material_item_id != receipt.material_item_id
                or row.uom != receipt.uom
            ):
                self._error(409, "FIELD_MATERIAL_ACCEPTANCE_INVALID")
            facts = self._out(row) | {
                "material_item_id": receipt.material_item_id,
                "accepted_quantity": str(acceptance.accepted_quantity),
            }
            digest = row.content_hash
            domain = "PROCUREMENT"
        else:
            self._error(422, "FIELD_SOURCE_TYPE_NOT_SUPPORTED")
        if expected_version is not None and expected_version != row.version:
            self._error(409, "FIELD_SOURCE_VERSION_MISMATCH")
        if expected_hash and not compare_digest(expected_hash, digest):
            self._error(409, "FIELD_SOURCE_HASH_MISMATCH")
        return _json(
            {
                "source_domain": domain,
                "source_entity_type": kind,
                "source_entity_id": identity,
                "source_type": kind,
                "source_id": identity,
                "source_version": row.version,
                "source_hash": digest,
                "observed_at": _iso(row.created_at),
                "facts": facts,
            }
        )
