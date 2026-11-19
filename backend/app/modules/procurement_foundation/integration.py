"""Scoped cross-authority references, append-only links, and read projections."""

from collections import Counter
from datetime import date, timedelta
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func

from app.core.time import utc_now
from app.modules.awp.models import CWA, WorkPackage
from app.modules.basic_data.service import _hash
from app.modules.cost_foundation.models import ControlAccount, CostCBS, CostCode
from app.modules.engineering_foundation.integration import (
    EngineeringIntegrationMixin,
    EngineeringReadinessReader,
    _effective_release,
    _observed_at,
    _schedule_item,
    _schedule_summary,
    _scoped,
)
from app.modules.engineering_foundation.models import (
    EngineeringDeliverable,
    EngineeringDesignPackage,
    EngineeringRelease,
    EngineeringRevision,
)
from app.modules.procurement_foundation.integration_models import ProcurementMapping
from app.modules.schedule_foundation.models import ScheduleVersion
from app.modules.scope_foundation.models import PlanItem, ScopeItem

AWP_KINDS = frozenset({"PWP", "CWP", "IWP", "EWP"})
SCHEDULE_KINDS = frozenset({"WBS", "ACTIVITY", "MILESTONE"})
TARGET_MODELS = {
    **dict.fromkeys(AWP_KINDS, WorkPackage),
    "CWA": CWA,
    "SCOPE": ScopeItem,
    "PLAN": PlanItem,
    "CBS": CostCBS,
    "COST_CODE": CostCode,
    "CONTROL_ACCOUNT": ControlAccount,
    "ENGINEERING_DELIVERABLE": EngineeringDeliverable,
    "ENGINEERING_REVISION": EngineeringRevision,
    "IFC_RELEASE": EngineeringRelease,
    "DESIGN_PACKAGE": EngineeringDesignPackage,
}
SOURCE_KINDS = {"PACKAGE", "REQUIREMENT", "MATERIAL_REQUIREMENT", "MATERIAL_ITEM", "RECEIPT", "ALLOCATION"}
SOURCE_LINKS = {
    "PACKAGE": AWP_KINDS | SCHEDULE_KINDS | {"CWA", "SCOPE", "PLAN", "CBS", "COST_CODE", "CONTROL_ACCOUNT"},
    "REQUIREMENT": set(TARGET_MODELS) | SCHEDULE_KINDS,
    "MATERIAL_REQUIREMENT": set(TARGET_MODELS) | SCHEDULE_KINDS,
    "MATERIAL_ITEM": {"CWP", "IWP"},
    "RECEIPT": {"IWP"},
    "ALLOCATION": {"IWP"},
}


class ProcurementMappingIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_kind: Literal["PACKAGE", "REQUIREMENT", "MATERIAL_REQUIREMENT", "MATERIAL_ITEM", "RECEIPT", "ALLOCATION"]
    source_id: int = Field(gt=0)
    target_kind: str = Field(min_length=2, max_length=32)
    target_id: int | None = Field(default=None, gt=0)
    schedule_version_id: int | None = Field(default=None, gt=0)
    external_id: str | None = Field(default=None, min_length=1, max_length=160)
    source_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    action: Literal["SET", "REMOVE"] = "SET"
    effective_date: date | None = None
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def validate_pair(self):
        if self.target_kind not in SOURCE_LINKS[self.source_kind]:
            raise ValueError("PROCUREMENT_MAPPING_PAIR_INVALID")
        if self.target_kind in SCHEDULE_KINDS:
            if self.target_id is not None or self.schedule_version_id is None or self.external_id is None:
                raise ValueError("PROCUREMENT_SCHEDULE_IDENTITY_REQUIRED")
        elif self.target_id is None or self.schedule_version_id is not None or self.external_id is not None:
            raise ValueError("PROCUREMENT_CANONICAL_IDENTITY_REQUIRED")
        return self


def mapping_key(row):
    return row.source_kind, row.source_id, row.target_kind, row.target_id, row.schedule_version_id, row.external_id


def mapping_content(row):
    return {
        **{
            name: getattr(row, name)
            for name in (
                "tenant_id",
                "project_workspace_id",
                "source_kind",
                "source_id",
                "target_kind",
                "target_id",
                "schedule_version_id",
                "external_id",
                "version",
                "action",
                "target_snapshot_json",
                "reason",
                "created_by",
            )
        },
        "effective_date": row.effective_date.isoformat(),
    }


def effective_mappings(db, tenant, workspace, *, source_kind=None, target_kind=None, target_id=None, as_of=None):
    instant = _observed_at(as_of)
    q = _scoped(ProcurementMapping, tenant, workspace).where(
        ProcurementMapping.created_at <= instant, ProcurementMapping.effective_date <= instant.date()
    )
    for column, value in (
        (ProcurementMapping.source_kind, source_kind),
        (ProcurementMapping.target_kind, target_kind),
        (ProcurementMapping.target_id, target_id),
    ):
        if value is not None:
            q = q.where(column == value)
    latest = {
        mapping_key(row): row for row in db.scalars(q.order_by(ProcurementMapping.version, ProcurementMapping.id))
    }
    return [row for row in latest.values() if row.action == "SET"]


def _source_models():
    from app.modules.procurement_foundation.materials_models import (
        ProcurementMaterialAllocation,
        ProcurementMaterialItem,
        ProcurementMaterialReceipt,
        ProcurementMaterialRequirement,
    )
    from app.modules.procurement_foundation.sourcing_models import ProcurementPackage, ProcurementRequirement

    return {
        "PACKAGE": ProcurementPackage,
        "REQUIREMENT": ProcurementRequirement,
        "MATERIAL_REQUIREMENT": ProcurementMaterialRequirement,
        "MATERIAL_ITEM": ProcurementMaterialItem,
        "RECEIPT": ProcurementMaterialReceipt,
        "ALLOCATION": ProcurementMaterialAllocation,
    }


class ProcurementIntegrationMixin:
    """Composition with the procurement authorization and command service."""

    def resolve_document(self, workspace, document_id, attachment_id):
        return EngineeringIntegrationMixin._resolve_document(self, workspace, document_id, attachment_id)

    def document_targets(self, workspace, limit=100, after=0):
        self._read_project(workspace)
        return EngineeringIntegrationMixin.document_targets(self, workspace, limit, after)

    def _redact(self, workspace, value):
        if isinstance(value, list):
            return [self._redact(workspace, item) for item in value]
        if not isinstance(value, dict):
            return value
        if value.get("source_system") == "PYPMIS_CDE" and "attachment_id" in value:
            key = (workspace, value.get("document_id"), value.get("attachment_id"))
            cache = self.__dict__.setdefault("_o2b_document_access", {})
            if key not in cache:
                try:
                    cache[key] = self.resolve_document(*key)
                except HTTPException as error:
                    if error.status_code not in {403, 404, 409, 422}:
                        raise
                    cache[key] = None
            if not cache[key] or any(
                cache[key].get(k) != value.get(k)
                for k in ("sha256", "binding_id", "document_version", "attachment_version")
            ):
                return {"source_system": "PYPMIS_CDE", "restricted_or_stale": True}
        return {key: self._redact(workspace, item) for key, item in value.items()}

    def resolve_reference(self, workspace, reference):
        ref = reference.model_dump() if isinstance(reference, BaseModel) else reference
        kind, identity = ref.get("target_kind"), ref.get("target_id")
        expected = ref.get("source_hash")
        if kind in SCHEDULE_KINDS:
            version_id, external = ref.get("schedule_version_id"), ref.get("external_id")
            if identity is not None or not version_id or not external:
                self._error(422, "PROCUREMENT_SCHEDULE_IDENTITY_REQUIRED")
            version = self._get(ScheduleVersion, workspace, version_id)
            if version.status != "ACCEPTED_CURRENT" or not version.accepted_at:
                self._error(409, "PROCUREMENT_SCHEDULE_VERSION_NOT_CURRENT")
            item = _schedule_item(version, kind, external)
            if item is None:
                self._error(422, "PROCUREMENT_SCHEDULE_TARGET_NOT_FOUND")
            snapshot = _schedule_summary(version, item, kind) | {
                "wbs_external_id": item.get("wbs_external_id"),
                "item_hash": _hash(item),
            }
            if expected and expected != version.content_hash:
                self._error(409, "PROCUREMENT_SOURCE_HASH_MISMATCH")
            return snapshot | {"source_hash": version.content_hash}
        if kind not in TARGET_MODELS or not identity or ref.get("schedule_version_id") or ref.get("external_id"):
            self._error(422, "PROCUREMENT_CANONICAL_IDENTITY_REQUIRED")
        row = self._get(TARGET_MODELS[kind], workspace, identity)
        if kind in AWP_KINDS and row.package_type != kind:
            self._error(422, "PROCUREMENT_PACKAGE_TYPE_MISMATCH")
        if kind == "PLAN" and row.status != "PUBLISHED":
            self._error(409, "PROCUREMENT_PUBLISHED_PLAN_REQUIRED")
        if kind == "SCOPE":
            baseline = self._current_baseline(workspace)
            if baseline is None or not any(item["id"] == row.id for item in baseline.snapshot_json.get("items", [])):
                self._error(409, "PROCUREMENT_APPROVED_SCOPE_REQUIRED")
        if kind == "ENGINEERING_REVISION":
            parent = self._get(EngineeringDeliverable, workspace, row.deliverable_id)
            if parent.current_revision_id != row.id or row.status != "APPROVED":
                self._error(409, "PROCUREMENT_ENGINEERING_REVISION_STALE_OR_UNAPPROVED")
        if kind == "IFC_RELEASE":
            self._verify_ifc(workspace, row)
        snapshot = {
            "target_kind": kind,
            "target_id": row.id,
            "target_version": row.version,
            "code": next(
                (
                    getattr(row, name)
                    for name in ("code", "package_code", "scope_code", "revision_code")
                    if getattr(row, name, None)
                ),
                "",
            ),
            "title": getattr(row, "title", getattr(row, "name", "")),
        }
        if kind == "IFC_RELEASE":
            snapshot |= {
                "revision_id": row.revision_id,
                "deliverable_id": row.deliverable_id,
                "effective_date": row.effective_date.isoformat(),
            }
        digest = getattr(row, "release_hash", None) or getattr(row, "content_hash", None) or _hash(snapshot)
        if expected and expected != digest:
            self._error(409, "PROCUREMENT_SOURCE_HASH_MISMATCH")
        return snapshot | {"source_hash": digest}

    def _verify_ifc(self, workspace, release):
        observed = utc_now()
        reader = EngineeringReadinessReader(self.db, self.tenant_id, workspace, [])
        reader.revision_by_id = {
            row.id: row
            for row in self.db.scalars(
                _scoped(EngineeringRevision, self.tenant_id, workspace).where(
                    EngineeringRevision.deliverable_id == release.deliverable_id
                )
            )
        }
        releases = list(
            self.db.scalars(
                _scoped(EngineeringRelease, self.tenant_id, workspace).where(
                    EngineeringRelease.deliverable_id == release.deliverable_id
                )
            )
        )
        current = _effective_release(releases, reader.revision_by_id, observed.date(), observed)
        if current is None or current.id != release.id:
            self._error(409, "PROCUREMENT_IFC_RELEASE_NOT_CURRENT")
        if reader._source_reason(
            {"required_revision_ids": [release.revision_id]}, release, releases, observed.date(), observed
        ):
            self._error(409, "PROCUREMENT_IFC_SOURCE_INVALID")

    def _mapping_query(self, workspace, source_kind=None, source_id=None):
        q = _scoped(ProcurementMapping, self.tenant_id, workspace)
        if source_kind is not None:
            q = q.where(ProcurementMapping.source_kind == source_kind)
        if source_id is not None:
            q = q.where(ProcurementMapping.source_id == source_id)
        return q

    def _mapping_version(self, workspace, source_kind, source_id):
        return (
            self.db.scalar(
                self._mapping_query(workspace, source_kind, source_id).with_only_columns(
                    func.max(ProcurementMapping.version)
                )
            )
            or 1
        )

    def _mapping_state(self, workspace, row):
        if row.content_hash != _hash(mapping_content(row)):
            return "BROKEN_REFERENCE"
        if row.action == "REMOVE":
            return "RETIRED"
        if row.effective_date > utc_now().date():
            return "FUTURE"
        if row.target_kind in SCHEDULE_KINDS:
            current = self.db.scalar(
                _scoped(ScheduleVersion, self.tenant_id, workspace).where(
                    ScheduleVersion.register_id == row.target_snapshot_json["schedule_register_id"],
                    ScheduleVersion.status == "ACCEPTED_CURRENT",
                )
            )
            item = _schedule_item(current, row.target_kind, row.external_id) if current else None
            if item is None:
                return "BROKEN"
            if current.id != row.schedule_version_id:
                return "NEEDS_REVIEW"
            return "CURRENT" if _hash(item) == row.target_snapshot_json["item_hash"] else "BROKEN_REFERENCE"
        try:
            current = self.resolve_reference(workspace, {"target_kind": row.target_kind, "target_id": row.target_id})
        except HTTPException as error:
            if error.status_code == 404:
                return "BROKEN_REFERENCE"
            if error.status_code in {409, 422}:
                return "NEEDS_REVIEW"
            raise
        return "CURRENT" if current["source_hash"] == row.target_snapshot_json["source_hash"] else "NEEDS_REVIEW"

    def procurement_mappings(self, workspace, source_kind=None, source_id=None, limit=50, after=0):
        self._read_project(workspace)
        if (source_kind is None) != (source_id is None) or source_kind is not None and source_kind not in SOURCE_KINDS:
            self._error(422, "PROCUREMENT_MAPPING_SOURCE_INVALID")
        if source_kind is not None:
            self._get(_source_models()[source_kind], workspace, source_id)
        q = self._mapping_query(workspace, source_kind, source_id)
        rows = list(
            self.db.scalars(q.where(ProcurementMapping.id > after).order_by(ProcurementMapping.id).limit(limit + 1))
        )
        active = {row.id for row in effective_mappings(self.db, self.tenant_id, workspace, source_kind=source_kind)}
        return {
            "version": self._mapping_version(workspace, source_kind, source_id),
            "items": [
                self._out(row) | {"mapping_health": self._mapping_state(workspace, row), "active": row.id in active}
                for row in rows[:limit]
            ],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
        }

    def write_procurement_mapping(self, workspace, payload, expected, key):
        self._ready(workspace, "mapping.edit")

        def apply():
            self._ready(workspace, "mapping.edit")
            self._get(_source_models()[payload.source_kind], workspace, payload.source_id, lock=True)
            version = self._mapping_version(workspace, payload.source_kind, payload.source_id)
            self._version(version, expected)
            prior = self.db.scalar(
                self._mapping_query(workspace, payload.source_kind, payload.source_id)
                .where(
                    ProcurementMapping.target_kind == payload.target_kind,
                    ProcurementMapping.target_id == payload.target_id,
                    ProcurementMapping.schedule_version_id == payload.schedule_version_id,
                    ProcurementMapping.external_id == payload.external_id,
                )
                .order_by(ProcurementMapping.version.desc())
                .limit(1)
            )
            day = payload.effective_date or utc_now().date()
            if day < utc_now().date() or prior and day < prior.effective_date:
                self._error(422, "PROCUREMENT_MAPPING_EFFECTIVE_DATE_INVALID")
            if payload.action == "REMOVE":
                if prior is None or prior.action != "SET":
                    self._error(409, "PROCUREMENT_MAPPING_NOT_ACTIVE")
                snapshot = prior.target_snapshot_json
            else:
                snapshot = self.resolve_reference(workspace, payload)
                if prior and prior.action == "SET" and snapshot == prior.target_snapshot_json:
                    self._error(409, "PROCUREMENT_MAPPING_ALREADY_ACTIVE")
            row = ProcurementMapping(
                **(self._base(workspace) | {"version": version + 1}),
                **payload.model_dump(exclude={"source_hash", "effective_date"}),
                effective_date=day,
                target_snapshot_json=snapshot,
                content_hash="",
            )
            row.content_hash = _hash(mapping_content(row))
            self.db.add(row)
            return self._record(row, "PROCUREMENT_MAPPING_" + payload.action, payload.reason)

        return self._write("mapping.edit", workspace, payload, key, apply, payload.source_id, expected)

    def procurement_status(self, workspace):
        self._read_project(workspace)
        model = _source_models()["PACKAGE"]
        rows = self.db.execute(
            _scoped(model, self.tenant_id, workspace)
            .with_only_columns(model.status, func.count())
            .group_by(model.status)
        )
        counts = dict(rows.all())
        return {"counts": counts, "total": sum(counts.values())}

    def procurement_lookahead(
        self,
        workspace,
        horizon_days=28,
        package_id=None,
        status=None,
        category=None,
        discipline=None,
        responsible_id=None,
        vendor_id=None,
        target_kind=None,
        target_id=None,
        start=None,
        end=None,
    ):
        self._read_project(workspace)
        start = start or utc_now().date()
        end = end or start + timedelta(days=horizon_days)
        if end < start or (end - start).days > 366:
            self._error(422, "PROCUREMENT_LOOKAHEAD_RANGE_INVALID")
        from app.modules.procurement_foundation import materials_models
        from app.modules.procurement_foundation import sourcing_models as models

        package_model = _source_models()["PACKAGE"]
        package_query = _scoped(package_model, self.tenant_id, workspace)
        for column, value in (
            (package_model.id, package_id),
            (package_model.status, status),
            (package_model.category, category),
            (package_model.discipline, discipline),
            (package_model.responsible_user_id, responsible_id),
        ):
            if value is not None:
                package_query = package_query.where(column == value)
        packages = {row.id: row for row in self.db.scalars(package_query.order_by(package_model.id))}
        if target_kind is not None or target_id is not None:
            if target_kind not in {"PWP", "CWP", "IWP"} or target_id is None:
                self._error(422, "PROCUREMENT_LOOKAHEAD_PACKAGE_FILTER_INVALID")
            links = effective_mappings(self.db, self.tenant_id, workspace, target_kind=target_kind, target_id=target_id)
            eligible = {row.source_id for row in links if row.source_kind == "PACKAGE"}
            demand_ids = {row.source_id for row in links if row.source_kind == "REQUIREMENT"}
            material_ids = {row.source_id for row in links if row.source_kind == "MATERIAL_REQUIREMENT"}
            if material_ids:
                material = materials_models.ProcurementMaterialRequirement
                demand_ids.update(
                    row.procurement_requirement_id
                    for row in self.db.scalars(
                        _scoped(material, self.tenant_id, workspace).where(material.id.in_(material_ids))
                    )
                )
            if demand_ids:
                demand = models.ProcurementRequirement
                eligible.update(
                    row.package_id
                    for row in self.db.scalars(
                        _scoped(demand, self.tenant_id, workspace).where(demand.id.in_(demand_ids))
                    )
                )
            packages = {identity: row for identity, row in packages.items() if identity in eligible}
        if vendor_id is not None:
            po = models.ProcurementPurchaseOrder
            matched = {
                getattr(row, "package_id", getattr(row, "procurement_package_id", None))
                for row in self.db.scalars(_scoped(po, self.tenant_id, workspace).where(po.vendor_id == vendor_id))
            }
            packages = {identity: row for identity, row in packages.items() if identity in matched}
        entries = []

        def collect(row, identity, dates):
            if identity not in packages:
                return
            for field, event_type in dates:
                day = getattr(row, field, None)
                if day is not None and start.isoformat() <= str(day)[:10] <= end.isoformat():
                    entries.append(
                        {
                            "entity_id": row.id,
                            "package_id": identity,
                            "kind": event_type,
                            "due_date": str(day)[:10],
                            "status": getattr(row, "status", None),
                        }
                    )

        for identity, row in packages.items():
            collect(
                row,
                identity,
                (
                    ("planned_rfq_date", "RFQ_DUE"),
                    ("planned_award_date", "AWARD_DUE"),
                    ("planned_po_date", "PO_ISSUE_DUE"),
                    ("required_on_site_date", "REQUIRED_ON_SITE"),
                    ("forecast_delivery_date", "DELIVERY_FORECAST"),
                ),
            )
        pos = {
            row.id: row.package_id
            for row in self.db.scalars(_scoped(models.ProcurementPurchaseOrder, self.tenant_id, workspace))
        }
        po_lines = {
            row.id: pos.get(row.purchase_order_id)
            for row in self.db.scalars(_scoped(models.ProcurementPurchaseOrderLine, self.tenant_id, workspace))
        }
        shipment_packages = {}
        for line in self.db.scalars(_scoped(materials_models.ProcurementShipmentLine, self.tenant_id, workspace)):
            shipment_packages.setdefault(line.shipment_id, set()).add(po_lines.get(line.po_line_id))
        for module, name, dates in (
            (models, "ProcurementRequisition", (("required_date", "REQUISITION_DUE"),)),
            (models, "ProcurementRFQ", (("closing_date", "RFQ_CLOSE_OR_EVALUATION"),)),
            (models, "ProcurementPurchaseOrder", (("expected_delivery_date", "PO_DELIVERY_DUE"),)),
            (
                materials_models,
                "ProcurementVendorMilestone",
                (("forecast_date", "MANUFACTURING_FORECAST"), ("planned_date", "MANUFACTURING_DUE")),
            ),
            (materials_models, "ProcurementInspection", (("inspection_date", "INSPECTION_DUE"),)),
            (
                materials_models,
                "ProcurementShipment",
                (
                    ("dispatch_date", "DISPATCH_DUE"),
                    ("planned_arrival", "ARRIVAL_DUE"),
                    ("forecast_arrival", "ARRIVAL_FORECAST"),
                ),
            ),
        ):
            model = getattr(module, name, None)
            if model is None:
                continue
            for row in self.db.scalars(_scoped(model, self.tenant_id, workspace)):
                owner = getattr(row, "package_id", None) or po_lines.get(getattr(row, "po_line_id", None))
                for identity in shipment_packages.get(row.id, set()) if name == "ProcurementShipment" else (owner,):
                    collect(row, identity, dates)
        entries.sort(key=lambda row: (row["due_date"], row["kind"], row["entity_id"]))
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "items": entries[:500],
            "total": len(entries),
            "counts": dict(Counter(row["kind"] for row in entries)),
        }

    def procurement_mapping_targets(self, workspace, target_kind, schedule_version_id=None, limit=50, after=0):
        self._read_project(workspace)
        if target_kind in SCHEDULE_KINDS:
            from app.modules.engineering_foundation.integration import _schedule_rows

            if not schedule_version_id:
                versions = list(
                    self.db.scalars(
                        _scoped(ScheduleVersion, self.tenant_id, workspace)
                        .where(
                            ScheduleVersion.status == "ACCEPTED_CURRENT",
                            ScheduleVersion.id > after,
                        )
                        .order_by(ScheduleVersion.id)
                        .limit(limit + 1)
                    )
                )
                return {
                    "items": [self._out(row, ("snapshot_json",)) for row in versions[:limit]],
                    "next_cursor": versions[limit - 1].id if len(versions) > limit else None,
                }
            version = self._get(ScheduleVersion, workspace, schedule_version_id)
            if version.status != "ACCEPTED_CURRENT":
                self._error(409, "PROCUREMENT_SCHEDULE_VERSION_NOT_CURRENT")
            rows = _schedule_rows(version, target_kind)
            return {
                "items": [_schedule_summary(version, row, target_kind) for row in rows[after : after + limit]],
                "next_cursor": after + limit if len(rows) > after + limit else None,
            }
        model = TARGET_MODELS.get(target_kind)
        if model is None:
            self._error(422, "PROCUREMENT_TARGET_KIND_INVALID")
        query = _scoped(model, self.tenant_id, workspace).where(model.id > after)
        if target_kind in AWP_KINDS:
            query = query.where(model.package_type == target_kind)
        result = []
        batch = list(self.db.scalars(query.order_by(model.id).limit(limit + 1)))
        for row in batch[:limit]:
            try:
                result.append(self.resolve_reference(workspace, {"target_kind": target_kind, "target_id": row.id}))
            except HTTPException as error:
                if error.status_code not in {404, 409}:
                    raise
        return {"items": result, "next_cursor": batch[limit - 1].id if len(batch) > limit else None}

    def procurement_trace(self, workspace, package_id):
        self._read_project(workspace)
        from app.modules.procurement_foundation import materials_models as m
        from app.modules.procurement_foundation import sourcing_models as s

        package = self._get(s.ProcurementPackage, workspace, package_id)
        records = {"PACKAGE": [self._out(package)]}

        def branch(kind, model, field, identities):
            rows = list(
                self.db.scalars(
                    _scoped(model, self.tenant_id, workspace)
                    .where(getattr(model, field).in_(identities))
                    .order_by(model.id)
                    .limit(501)
                )
            )
            if len(rows) > 500:
                self._error(409, "PROCUREMENT_TRACE_TOO_BROAD")
            records[kind] = [self._out(row) for row in rows]
            return [row.id for row in rows]

        req = branch("REQUIREMENT", s.ProcurementRequirement, "package_id", [package_id])
        requisitions = branch("REQUISITION", s.ProcurementRequisition, "package_id", [package_id])
        branch("REQUISITION_LINE", s.ProcurementRequisitionLine, "requisition_id", requisitions)
        rfqs = branch("RFQ", s.ProcurementRFQ, "package_id", [package_id])
        bids = branch("BID", s.ProcurementBid, "rfq_id", rfqs)
        branch("EVALUATION", s.ProcurementEvaluation, "bid_id", bids)
        branch("AWARD", s.ProcurementAward, "rfq_id", rfqs)
        orders = branch("PO", s.ProcurementPurchaseOrder, "package_id", [package_id])
        lines = branch("PO_LINE", s.ProcurementPurchaseOrderLine, "purchase_order_id", orders)
        branch("PO_REVISION", s.ProcurementPurchaseOrderRevision, "purchase_order_id", orders)
        needs = branch("MATERIAL_REQUIREMENT", m.ProcurementMaterialRequirement, "procurement_requirement_id", req)
        branch("VENDOR_MILESTONE", m.ProcurementVendorMilestone, "po_line_id", lines)
        branch("EXPEDITING", m.ProcurementExpeditingEvent, "po_line_id", lines)
        branch("INSPECTION", m.ProcurementInspection, "po_line_id", lines)
        branch("SHIPMENT_LINE", m.ProcurementShipmentLine, "po_line_id", lines)
        branch("SHIPMENT", m.ProcurementShipment, "id", {row["shipment_id"] for row in records["SHIPMENT_LINE"]})
        receipts = branch("RECEIPT_LINE", m.ProcurementMaterialReceiptLine, "po_line_id", lines)
        branch("RECEIPT", m.ProcurementMaterialReceipt, "id", {row["receipt_id"] for row in records["RECEIPT_LINE"]})
        branch("ACCEPTANCE", m.ProcurementMaterialAcceptance, "receipt_line_id", receipts)
        allocations = branch("ALLOCATION", m.ProcurementMaterialAllocation, "material_requirement_id", needs)
        branch(
            "MATERIAL_ITEM",
            m.ProcurementMaterialItem,
            "id",
            {row["material_item_id"] for row in records["MATERIAL_REQUIREMENT"]},
        )
        link_sources = {
            "PACKAGE": [package_id],
            "REQUIREMENT": req,
            "MATERIAL_REQUIREMENT": needs,
            "ALLOCATION": allocations,
            "RECEIPT": [row["id"] for row in records["RECEIPT"]],
            "MATERIAL_ITEM": [row["id"] for row in records["MATERIAL_ITEM"]],
        }
        mappings = [
            self._out(row) | {"mapping_health": self._mapping_state(workspace, row)}
            for row in effective_mappings(self.db, self.tenant_id, workspace)
            if row.source_id in link_sources.get(row.source_kind, ())
        ]
        return self._redact(workspace, {"package_id": package_id, "records": records, "mappings": mappings})

    def procurement_readiness(self, workspace, package_id):
        trace = self.procurement_trace(workspace, package_id)
        records, mappings = trace["records"], trace["mappings"]
        requirements = [row for row in records["REQUIREMENT"] if row["status"] == "ACTIVE"]
        verified = 0
        for row in requirements:
            if not row["source_reference"]:
                continue
            try:
                self.resolve_reference(workspace, row["source_reference"])
                verified += 1
            except HTTPException as error:
                if error.status_code not in {404, 409, 422}:
                    raise
        targets = {
            row["target_id"]
            for row in mappings
            if row["target_kind"] in {"CWP", "IWP"} and row["source_kind"] == "MATERIAL_REQUIREMENT"
        }
        from app.modules.procurement_foundation.availability import material_availability

        material = [material_availability(self.db, self.tenant_id, workspace, identity) for identity in sorted(targets)]
        values = {
            "requirements": len(requirements),
            "technical_sources": verified if verified == len(requirements) else 0,
            "requisitions": sum(row["status"] == "APPROVED" for row in records["REQUISITION"]),
            "sourcing": len(records["BID"]),
            "awards": len(records["AWARD"]),
            "issued_orders": sum(row["status"] == "ISSUED" for row in records["PO"]),
            "delivery_forecast": sum(bool(row["expected_delivery_date"]) for row in records["PO"]),
            "material": len(material) if all(row and row["status"] == "READY" for row in material) else 0,
        }
        checks = [
            {"key": key, "status": "READY" if value else "NOT_READY", "count": value} for key, value in values.items()
        ]
        result = {
            "package_id": package_id,
            "status": "READY" if all(values.values()) else "NOT_READY",
            "checks": checks,
        }
        return result | {"source_hash": _hash({"result": result, "trace": trace, "material": material})}

    def procurement_source_facts(self, workspace, package_id):
        trace = self.procurement_trace(workspace, package_id)
        rows = trace["records"]
        projections = {
            "cost": [("AWARD", row, ("vendor_id", "bid_id")) for row in rows["AWARD"]]
            + [
                ("PO", row, ("po_number", "currency", "original_value", "current_value", "current_revision_id"))
                for row in rows["PO"]
                if row["status"] == "ISSUED"
            ],
            "progress": [
                ("MANUFACTURING", row, ("code", "actual_date"))
                for row in rows["VENDOR_MILESTONE"]
                if row["actual_date"]
            ]
            + [("DISPATCH", row, ("dispatch_date",)) for row in rows["SHIPMENT"] if row["dispatch_date"]]
            + [("RECEIPT", row, ("received_at",)) for row in rows["RECEIPT"]]
            + [("ACCEPTANCE", row, ("accepted_quantity", "receipt_line_id")) for row in rows["ACCEPTANCE"]],
            "forecast": [
                ("PACKAGE", row, ("planned_award_date", "planned_po_date", "forecast_delivery_date"))
                for row in rows["PACKAGE"]
            ]
            + [("MANUFACTURING", row, ("forecast_date",)) for row in rows["VENDOR_MILESTONE"] if row["forecast_date"]]
            + [("SHIPMENT", row, ("forecast_arrival",)) for row in rows["SHIPMENT"] if row["forecast_arrival"]],
        }
        return {
            "package_id": package_id,
            "observed_at": utc_now().isoformat(),
            **{
                domain: [
                    {
                        "kind": kind,
                        "id": row["id"],
                        "version": row["version"],
                        "source_hash": row.get("content_hash") or _hash(row),
                        "observed_on": row.get("updated_at") or row["created_at"],
                        "facts": {field: row.get(field) for field in fields},
                    }
                    for kind, row, fields in facts
                ]
                for domain, facts in projections.items()
            },
        }
