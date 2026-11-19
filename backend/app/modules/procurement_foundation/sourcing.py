"""Planning, sourcing and operational purchasing command handlers."""

from collections import defaultdict
from datetime import UTC
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace

from sqlalchemy import func, select

from app.core.time import utc_now
from app.domain.models import Contract, PurchaseOrder
from app.modules.basic_data.service import _hash, _json
from app.modules.cost_foundation.financial_models import CostCommitmentReference
from app.modules.engineering_foundation.integration import _cde_binding
from app.modules.procurement_foundation.policy import transition
from app.modules.procurement_foundation.sourcing_models import (
    ProcurementAward,
    ProcurementBid,
    ProcurementEvaluation,
    ProcurementHistory,
    ProcurementPackage,
    ProcurementPackageItem,
    ProcurementPurchaseOrder,
    ProcurementPurchaseOrderLine,
    ProcurementPurchaseOrderRevision,
    ProcurementRequirement,
    ProcurementRequisition,
    ProcurementRequisitionLine,
    ProcurementRFQ,
    ProcurementRFQVendor,
    ProcurementVendor,
)

SOURCING_COLLECTIONS = {
    "packages": ProcurementPackage,
    "requirements": ProcurementRequirement,
    "package-items": ProcurementPackageItem,
    "requisitions": ProcurementRequisition,
    "rfqs": ProcurementRFQ,
    "vendors": ProcurementVendor,
    "bids": ProcurementBid,
    "evaluations": ProcurementEvaluation,
    "awards": ProcurementAward,
    "purchase-orders": ProcurementPurchaseOrder,
}
ENTITY_MODELS = {
    "package": ProcurementPackage,
    "requirement": ProcurementRequirement,
    "requisition": ProcurementRequisition,
    "rfq": ProcurementRFQ,
    "po": ProcurementPurchaseOrder,
    "vendor": ProcurementVendor,
}


def po_revision_material(row):
    """Material hashed by both command and provider readers."""
    return _json(
        {
            key: getattr(row, key)
            for key in (
                "purchase_order_id",
                "previous_revision_id",
                "revision",
                "effective_date",
                "reason",
                "lines_snapshot",
                "schedule_impact_reference",
            )
        }
    )


class ProcurementSourcingMixin:
    def _source_query(self, model, workspace):
        if model is ProcurementVendor:
            return select(model).where(model.tenant_id == self.tenant_id)
        return self._scoped(model, workspace)

    def _vendor(self, identity, *, active=False, lock=False):
        query = self._source_query(ProcurementVendor, None).where(ProcurementVendor.id == identity)
        row = self.db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
        if row is None:
            self._error(404, "PROCUREMENT_VENDOR_NOT_FOUND")
        if active and row.status != "ACTIVE":
            self._error(409, "PROCUREMENT_ACTIVE_VENDOR_REQUIRED")
        return row

    def _source_rows(self, model, workspace, *criteria):
        return list(self.db.scalars(self._source_query(model, workspace).where(*criteria).order_by(model.id)))

    def _source_detail(self, workspace, row):
        out = self._out(row)
        if isinstance(row, ProcurementPackage):
            out["items"] = [
                self._out(item)
                for item in self._source_rows(
                    ProcurementPackageItem, workspace, ProcurementPackageItem.package_id == row.id
                )
            ]
        elif isinstance(row, ProcurementRequisition):
            out["lines"] = [
                self._out(line)
                for line in self._source_rows(
                    ProcurementRequisitionLine, workspace, ProcurementRequisitionLine.requisition_id == row.id
                )
            ]
        elif isinstance(row, ProcurementRFQ):
            out["invited_vendors"] = [
                self._out(vendor)
                for vendor in self._source_rows(ProcurementRFQVendor, workspace, ProcurementRFQVendor.rfq_id == row.id)
            ]
        elif isinstance(row, ProcurementBid):
            assessments = self._source_rows(ProcurementEvaluation, workspace, ProcurementEvaluation.bid_id == row.id)
            out["evaluations"] = [self._out(assessment) for assessment in assessments]
            evaluated = {assessment.evaluation_type: assessment.result for assessment in assessments}
            out["technical_status"] = evaluated.get("TECHNICAL", "PENDING")
            out["commercial_status"] = evaluated.get("COMMERCIAL", "PENDING")
        elif isinstance(row, ProcurementPurchaseOrder):
            out["lines"] = [
                self._out(line)
                for line in self._source_rows(
                    ProcurementPurchaseOrderLine, workspace, ProcurementPurchaseOrderLine.purchase_order_id == row.id
                )
            ]
            out["revisions"] = [
                self._out(revision)
                for revision in self._source_rows(
                    ProcurementPurchaseOrderRevision,
                    workspace,
                    ProcurementPurchaseOrderRevision.purchase_order_id == row.id,
                )
            ]
        return out

    def sourcing_list(self, workspace, collection, *, limit=50, after_id=0):
        self._read_project(workspace)
        model = SOURCING_COLLECTIONS[collection]
        query = self._source_query(model, workspace).where(model.id > after_id).order_by(model.id).limit(limit + 1)
        rows = list(self.db.scalars(query))
        return self._redact(
            workspace,
            {
                "items": [self._out(row) for row in rows[:limit]],
                "next_after_id": rows[limit - 1].id if len(rows) > limit else None,
            },
        )

    def sourcing_detail(self, workspace, collection, identity):
        self._read_project(workspace)
        model = SOURCING_COLLECTIONS[collection]
        row = self._vendor(identity) if model is ProcurementVendor else self._get(model, workspace, identity)
        return self._redact(workspace, self._source_detail(workspace, row))

    def _pin(self, workspace, ref):
        if ref is None:
            return {}
        return self.resolve_reference(workspace, ref.model_dump() | {"target_kind": ref.target_kind.upper()})

    def _check_pin(self, workspace, pin):
        if not pin:
            return
        query = {
            key: pin.get(key)
            for key in ("target_kind", "target_id", "schedule_version_id", "external_id", "source_hash")
        }
        self.resolve_reference(workspace, query)

    def _document_pin(self, workspace, ref):
        return {} if ref is None else self.resolve_document(workspace, ref.document_id, ref.attachment_id)

    def _catalog(self, profile, catalog, value):
        code = self._code(value)
        if code not in profile[catalog]:
            self._error(422, "PROCUREMENT_UNPUBLISHED_CATALOG_VALUE")
        return code

    @staticmethod
    def _profile_pin(profile):
        return {"configuration_id": profile.id, "configuration_hash": profile.content_hash}

    def _record_vendor(self, workspace, row, event, reason, *, changed=False):
        previous = row.version if changed else None
        if changed:
            row.version += 1
        self.db.flush()
        result = self._out(row)
        self.db.add(
            ProcurementHistory(
                **self._base(workspace),
                entity_type=type(row).__name__,
                entity_id=row.id,
                entity_version=row.version,
                previous_version=previous,
                event_type=event,
                snapshot_json=result,
                reason=reason,
            )
        )
        self._event(event, row.id, {"project_workspace_id": workspace, "version": row.version})
        return result

    def create_vendor(self, workspace, payload, key):
        self._ready(workspace, "vendor.create")

        def apply():
            values = payload.model_dump(exclude={"reason", "vendor_code", "country", "business_identifier"})
            row = ProcurementVendor(
                tenant_id=self.tenant_id,
                created_by=self.actor_id,
                vendor_code=self._code(payload.vendor_code),
                country=payload.country.upper(),
                business_identifier=payload.business_identifier.upper(),
                **values,
            )
            self.db.add(row)
            return self._record_vendor(workspace, row, "VENDOR_REGISTERED", payload.reason)

        return self._write("vendor.create", workspace, payload, key, apply)

    def save_package(self, workspace, payload, key, identity=None, expected=None):
        action = "package.create" if identity is None else "package.edit"
        _, profile = self._ready(workspace, action)

        def apply():
            values = payload.model_dump(
                exclude={
                    "reason",
                    "procurement_type",
                    "category",
                    "sourcing_method",
                    "package_code",
                    "responsible_user_id",
                    "procurement_manager_id",
                }
            ) | {
                "package_code": self._code(payload.package_code),
                "procurement_type": self._catalog(profile.content_json, "procurement_types", payload.procurement_type),
                "category": self._catalog(profile.content_json, "categories", payload.category),
                "sourcing_method": self._catalog(profile.content_json, "sourcing_methods", payload.sourcing_method),
                "responsible_user_id": self._actor(payload.responsible_user_id),
                "procurement_manager_id": self._actor(payload.procurement_manager_id),
            }
            milestones = [
                value
                for value in (payload.planned_rfq_date, payload.planned_award_date, payload.planned_po_date)
                if value
            ]
            if milestones != sorted(milestones):
                self._error(422, "PROCUREMENT_PACKAGE_MILESTONE_ORDER_INVALID")
            if identity is None:
                row = self._new(ProcurementPackage, workspace, **values, **self._profile_pin(profile))
            else:
                row = self._get(ProcurementPackage, workspace, identity, lock=True)
                self._version(row.version, expected)
                if row.status != "DRAFT":
                    self._error(409, "PROCUREMENT_PACKAGE_IMMUTABLE")
                if values["package_code"] != row.package_code:
                    self._error(409, "PROCUREMENT_PACKAGE_IDENTITY_IMMUTABLE")
                for name, value in values.items():
                    setattr(row, name, value)
            return self._record(
                row,
                "PACKAGE_CREATED" if identity is None else "PACKAGE_UPDATED",
                payload.reason,
                changed=identity is not None,
            )

        return self._write(action, workspace, payload, key, apply, identity, expected)

    def _active_package(self, workspace, identity, *, lock=False):
        package = self._get(ProcurementPackage, workspace, identity, lock=lock)
        if package.status not in {"DRAFT", "PLANNED"}:
            self._error(409, "PROCUREMENT_PACKAGE_NOT_OPEN")
        return package

    def create_requirement(self, workspace, payload, key):
        _, profile = self._ready(workspace, "requirement.create")

        def apply():
            self._active_package(workspace, payload.package_id, lock=True)
            pin = self._pin(workspace, payload.source_reference)
            target_kind = pin.get("target_kind", "")
            if profile.content_json["require_engineering_ifc"] and target_kind != "IFC_RELEASE":
                self._error(409, "PROCUREMENT_ENGINEERING_IFC_REQUIRED")
            authority = (
                "ENGINEERING"
                if target_kind.startswith("ENGINEERING") or target_kind == "IFC_RELEASE"
                else "AWP"
                if target_kind in {"PWP", "CWP", "IWP", "EWP", "CWA"}
                else "SCHEDULE"
                if target_kind in {"ACTIVITY", "WBS"}
                else target_kind
            )
            row = self._new(
                ProcurementRequirement,
                workspace,
                requirement_code=self._code(payload.requirement_code),
                package_id=payload.package_id,
                description=payload.description,
                item_type=self._catalog(profile.content_json, "procurement_types", payload.item_type),
                required_quantity=payload.required_quantity,
                uom=payload.uom.upper(),
                required_on_site_date=payload.required_on_site_date,
                priority=payload.priority,
                source_reference=pin,
                source_entity_type=target_kind,
                source_entity_id=pin.get("target_id"),
                source_authority=authority,
                source_hash=pin.get("source_hash", ""),
            )
            return self._record(row, "REQUIREMENT_CREATED", payload.reason)

        return self._write("requirement.create", workspace, payload, key, apply)

    def add_package_item(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "package.item.add")

        def apply():
            package = self._active_package(workspace, identity, lock=True)
            self._version(package.version, expected)
            requirement = self._get(ProcurementRequirement, workspace, payload.requirement_id)
            if requirement.package_id != package.id or requirement.status == "CANCELLED":
                self._error(409, "PROCUREMENT_PACKAGE_ITEM_REQUIREMENT_MISMATCH")
            if requirement.uom != payload.uom.upper() or requirement.required_quantity < payload.quantity:
                self._error(422, "PROCUREMENT_PACKAGE_ITEM_QUANTITY_MISMATCH")
            row = self._new(
                ProcurementPackageItem,
                workspace,
                package_id=identity,
                requirement_id=requirement.id,
                quantity=payload.quantity,
                uom=requirement.uom,
            )
            item = self._record(row, "PACKAGE_ITEM_LINKED", payload.reason)
            self._record(package, "PACKAGE_ITEM_LINKED", payload.reason, changed=True)
            return {"version": package.version, "package_item": item}

        return self._write("package.item.add", workspace, payload, key, apply, identity, expected)

    def _requirement_quantities(self, workspace, package_id, lines, *, require_active=True):
        totals = defaultdict(Decimal)
        numbers = set()
        requirements = {}
        for line in lines:
            if line.line_number in numbers:
                self._error(422, "PROCUREMENT_DUPLICATE_LINE_NUMBER")
            numbers.add(line.line_number)
            requirement = self._get(ProcurementRequirement, workspace, line.requirement_id)
            if (
                requirement.package_id != package_id
                or requirement.status == "CANCELLED"
                or require_active
                and requirement.status != "ACTIVE"
            ):
                self._error(409, "PROCUREMENT_ACTIVE_PACKAGE_REQUIREMENT_REQUIRED")
            if requirement.uom != line.uom.upper():
                self._error(422, "PROCUREMENT_REQUIREMENT_UOM_MISMATCH")
            self._check_pin(workspace, requirement.source_reference)
            totals[requirement.id] += line.quantity
            requirements[requirement.id] = requirement
        if any(quantity > requirements[identity].required_quantity for identity, quantity in totals.items()):
            self._error(422, "PROCUREMENT_REQUIREMENT_QUANTITY_EXCEEDED")
        return totals

    def create_requisition(self, workspace, payload, key):
        _, profile = self._ready(workspace, "requisition.create")

        def apply():
            self._active_package(workspace, payload.package_id, lock=True)
            self._requirement_quantities(workspace, payload.package_id, payload.lines)
            row = self._new(
                ProcurementRequisition,
                workspace,
                requisition_number=self._code(payload.requisition_number),
                package_id=payload.package_id,
                requested_by=self._actor(payload.requested_by),
                prepared_by=self.actor_id,
                issue_date=payload.issue_date,
                required_date=payload.required_date,
                currency=payload.currency.upper(),
                estimated_value=payload.estimated_value,
                notes=payload.notes,
                technical_reference=self._pin(workspace, payload.technical_reference),
                document_reference=self._document_pin(workspace, payload.document_reference),
                **self._profile_pin(profile),
            )
            for item in payload.lines:
                self._new(
                    ProcurementRequisitionLine,
                    workspace,
                    requisition_id=row.id,
                    **(
                        item.model_dump(exclude={"engineering_revision_reference", "uom"})
                        | {
                            "uom": item.uom.upper(),
                            "engineering_revision_reference": self._pin(workspace, item.engineering_revision_reference),
                        }
                    ),
                )
            self._record(row, "REQUISITION_CREATED", payload.reason)
            return self._source_detail(workspace, row)

        return self._write("requisition.create", workspace, payload, key, apply)

    def create_rfq(self, workspace, payload, key):
        _, profile = self._ready(workspace, "rfq.create")

        def apply():
            self._active_package(workspace, payload.package_id, lock=True)
            requisition = self._get(ProcurementRequisition, workspace, payload.requisition_id)
            if requisition.package_id != payload.package_id or requisition.status != "APPROVED":
                self._error(409, "PROCUREMENT_APPROVED_PACKAGE_REQUISITION_REQUIRED")
            if payload.issue_date < requisition.issue_date:
                self._error(422, "PROCUREMENT_RFQ_PRECEDES_REQUISITION")
            row = self._new(
                ProcurementRFQ,
                workspace,
                rfq_number=self._code(payload.rfq_number),
                package_id=payload.package_id,
                requisition_id=requisition.id,
                issue_date=payload.issue_date,
                closing_date=payload.closing_date,
                commercial_terms_reference=payload.commercial_terms_reference,
                technical_package_reference=self._pin(workspace, payload.technical_package_reference),
                document_reference=self._document_pin(workspace, payload.document_reference),
                **self._profile_pin(profile),
            )
            return self._record(row, "RFQ_CREATED", payload.reason)

        return self._write("rfq.create", workspace, payload, key, apply)

    def invite_vendor(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "rfq.invite")

        def apply():
            row = self._get(ProcurementRFQ, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "DRAFT":
                self._error(409, "PROCUREMENT_RFQ_INVITATIONS_FROZEN")
            vendor = self._vendor(payload.vendor_id, active=True)
            invite = self._new(
                ProcurementRFQVendor,
                workspace,
                rfq_id=row.id,
                vendor_id=vendor.id,
                vendor_snapshot={
                    key: getattr(vendor, key)
                    for key in ("vendor_code", "legal_name", "country", "business_identifier", "version")
                },
            )
            self._record(invite, "RFQ_VENDOR_INVITED", payload.reason)
            self._record(row, "RFQ_VENDOR_INVITED", payload.reason, changed=True)
            return self._source_detail(workspace, row)

        return self._write("rfq.invite", workspace, payload, key, apply, identity, expected)

    def _check_document_pin(self, workspace, pin):
        if pin and self._redact(workspace, pin).get("restricted_or_stale"):
            self._error(409, "PROCUREMENT_DOCUMENT_SOURCE_UNAVAILABLE")

    def _requisition_inputs(self, workspace, requisition):
        lines = self._source_rows(
            ProcurementRequisitionLine, workspace, ProcurementRequisitionLine.requisition_id == requisition.id
        )
        self._requirement_quantities(workspace, requisition.package_id, lines)
        self._check_pin(workspace, requisition.technical_reference)
        self._check_document_pin(workspace, requisition.document_reference)
        for line in lines:
            self._check_pin(workspace, line.engineering_revision_reference)
        return lines

    def transition_sourcing(self, workspace, entity, identity, payload, expected, key):
        model = ENTITY_MODELS[entity]
        action = f"{entity}.{payload.action}"
        if not any(
            transition(entity, state, payload.action)
            for state in ("DRAFT", "PLANNED", "ACTIVE", "SUSPENDED", "SUBMITTED", "ISSUED", "APPROVED")
        ):
            self._error(422, "PROCUREMENT_ACTION_INVALID")
        _, effective_profile = self._ready(workspace, action)

        def apply():
            row = (
                self._vendor(identity, lock=True)
                if model is ProcurementVendor
                else self._get(model, workspace, identity, lock=True)
            )
            self._version(row.version, expected)
            target = transition(entity, row.status, payload.action)
            if target is None:
                self._error(409, "PROCUREMENT_STATE_TRANSITION_CONFLICT")
            profile = self._pinned_profile(row) if hasattr(row, "configuration_id") else effective_profile.content_json
            sod = profile["separation_of_duties"]
            now = utc_now().date()
            if (
                entity == "package"
                and target == "CANCELLED"
                and self._source_rows(
                    ProcurementRequisition,
                    workspace,
                    ProcurementRequisition.package_id == row.id,
                    ProcurementRequisition.status == "APPROVED",
                )
            ):
                self._error(409, "PROCUREMENT_PACKAGE_HAS_APPROVED_FACTS")
            if entity == "requirement" and target == "ACTIVE":
                self._active_package(workspace, row.package_id)
                self._check_pin(workspace, row.source_reference)
                if profile["require_engineering_ifc"] and row.source_entity_type != "IFC_RELEASE":
                    self._error(409, "PROCUREMENT_ENGINEERING_IFC_REQUIRED")
            if entity == "requisition" and target in {"SUBMITTED", "APPROVED"}:
                self._active_package(workspace, row.package_id)
                self._requisition_inputs(workspace, row)
                if target == "APPROVED":
                    if sod["requisition_preparer_cannot_approve"] and self.actor_id == row.prepared_by:
                        self._error(403, "PROCUREMENT_REQUISITION_APPROVAL_SOD")
                    row.approved_by = self.actor_id
            if entity == "rfq" and target == "ISSUED":
                self._active_package(workspace, row.package_id)
                if sod["rfq_preparer_cannot_issue"] and self.actor_id == row.created_by:
                    self._error(403, "PROCUREMENT_RFQ_ISSUE_SOD")
                if not row.issue_date <= now <= row.closing_date:
                    self._error(409, "PROCUREMENT_RFQ_ISSUE_OUTSIDE_WINDOW")
                requisition = self._get(ProcurementRequisition, workspace, row.requisition_id)
                if requisition.status != "APPROVED":
                    self._error(409, "PROCUREMENT_APPROVED_PACKAGE_REQUISITION_REQUIRED")
                self._requisition_inputs(workspace, requisition)
                self._check_pin(workspace, row.technical_package_reference)
                self._check_document_pin(workspace, row.document_reference)
                invites = self._source_rows(ProcurementRFQVendor, workspace, ProcurementRFQVendor.rfq_id == row.id)
                if len(invites) < profile["minimum_rfq_vendors"]:
                    self._error(409, "PROCUREMENT_RFQ_MINIMUM_VENDORS_REQUIRED")
                for invitation in invites:
                    self._vendor(invitation.vendor_id, active=True)
                row.approved_by = self.actor_id
            if entity == "po" and target in {"APPROVED", "ISSUED"}:
                self._active_package(workspace, row.package_id)
                self._vendor(row.vendor_id, active=True)
                self._check_document_pin(workspace, row.document_reference)
                lines = self._source_rows(
                    ProcurementPurchaseOrderLine, workspace, ProcurementPurchaseOrderLine.purchase_order_id == row.id
                )
                self._requirement_quantities(workspace, row.package_id, lines)
                if target == "APPROVED":
                    if sod["po_preparer_cannot_approve"] and self.actor_id == row.created_by:
                        self._error(403, "PROCUREMENT_PO_APPROVAL_SOD")
                    revision = self._make_initial_po_revision(workspace, row, lines, payload.reason)
                    # The revision must exist before the single guarded DRAFT → APPROVED update.
                    row.approved_by = self.actor_id
                    row.current_revision_id = revision.id
                else:
                    if now < row.issue_date:
                        self._error(409, "PROCUREMENT_PO_ISSUE_IN_FUTURE")
                    if row.current_revision_id is None:
                        self._error(409, "PROCUREMENT_APPROVED_PO_REVISION_REQUIRED")
                    row.issued_by = self.actor_id
            row.status = target
            event = f"{entity.upper()}_{target}"
            if model is ProcurementVendor:
                return self._record_vendor(workspace, row, event, payload.reason, changed=True)
            self._record(row, event, payload.reason, changed=True)
            return self._source_detail(workspace, row)

        return self._write(action, workspace, payload, key, apply, identity, expected)

    @staticmethod
    def _decimal_string(value):
        return format(Decimal(value).normalize(), "f")

    def _bid_material(self, row):
        return _json(
            {
                key: getattr(row, key)
                for key in (
                    "rfq_id",
                    "vendor_id",
                    "bid_revision",
                    "supersedes_id",
                    "received_at",
                    "currency",
                    "validity_date",
                    "document_reference",
                )
            }
        ) | {
            "total_bid_value": self._decimal_string(row.total_bid_value),
        }

    def _current_bid(self, workspace, row):
        query = self._scoped(ProcurementBid, workspace).where(
            ProcurementBid.rfq_id == row.rfq_id,
            ProcurementBid.vendor_id == row.vendor_id,
            ProcurementBid.bid_revision > row.bid_revision,
        )
        if self.db.scalar(query.limit(1)) is not None:
            self._error(409, "PROCUREMENT_BID_SUPERSEDED")
        if _hash(self._bid_material(row)) != row.content_hash:
            self._error(409, "PROCUREMENT_BID_HASH_MISMATCH")
        return row

    def create_bid(self, workspace, payload, key):
        self._ready(workspace, "bid.create")

        def apply():
            rfq = self._get(ProcurementRFQ, workspace, payload.rfq_id, lock=True)
            if rfq.status != "ISSUED":
                self._error(409, "PROCUREMENT_ISSUED_RFQ_REQUIRED")
            self._vendor(payload.vendor_id, active=True)
            if (
                self.db.scalar(
                    self._scoped(ProcurementRFQVendor, workspace).where(
                        ProcurementRFQVendor.rfq_id == rfq.id,
                        ProcurementRFQVendor.vendor_id == payload.vendor_id,
                    )
                )
                is None
            ):
                self._error(409, "PROCUREMENT_RFQ_VENDOR_NOT_INVITED")
            now = utc_now()
            received = payload.received_at or now
            if received.tzinfo is not None:
                received = received.astimezone(UTC).replace(tzinfo=None)
            if (
                received > now
                or not rfq.issue_date <= received.date() <= rfq.closing_date
                or payload.validity_date < received.date()
            ):
                self._error(422, "PROCUREMENT_BID_DATE_INVALID")
            latest = self.db.scalar(
                self._scoped(ProcurementBid, workspace)
                .where(
                    ProcurementBid.rfq_id == rfq.id,
                    ProcurementBid.vendor_id == payload.vendor_id,
                )
                .order_by(ProcurementBid.bid_revision.desc())
                .limit(1)
            )
            if payload.supersedes_id != (latest.id if latest else None):
                self._error(409, "PROCUREMENT_EXPLICIT_BID_SUCCESSION_REQUIRED")
            if latest is not None and latest.received_at > received:
                self._error(422, "PROCUREMENT_BID_DATE_PRECEDES_ANTECESSOR")
            values = {
                "rfq_id": rfq.id,
                "vendor_id": payload.vendor_id,
                "bid_revision": latest.bid_revision + 1 if latest else 1,
                "supersedes_id": payload.supersedes_id,
                "received_at": received,
                "currency": payload.currency.upper(),
                "total_bid_value": payload.total_bid_value,
                "validity_date": payload.validity_date,
                "document_reference": self._document_pin(workspace, payload.document_reference),
            }
            digest = _hash(_json(values | {"total_bid_value": self._decimal_string(payload.total_bid_value)}))
            row = self._new(ProcurementBid, workspace, **values, content_hash=digest)
            return self._record(row, "BID_REVISION_RECEIVED", payload.reason)

        return self._write("bid.create", workspace, payload, key, apply)

    def _evaluation_material(self, row):
        return _json(
            {
                key: getattr(row, key)
                for key in (
                    "bid_id",
                    "evaluation_type",
                    "evaluated_on",
                    "result",
                    "comments",
                    "recommendation",
                    "engineering_reference",
                    "document_reference",
                    "created_by",
                )
            }
        ) | {
            "score": self._decimal_string(row.score) if row.score is not None else None,
        }

    def create_evaluation(self, workspace, payload, key):
        action = f"evaluation.{payload.evaluation_type.lower()}"
        self._ready(workspace, action)

        def apply():
            bid = self._current_bid(workspace, self._get(ProcurementBid, workspace, payload.bid_id))
            rfq = self._get(ProcurementRFQ, workspace, bid.rfq_id, lock=True)
            if rfq.status != "CLOSED":
                self._error(409, "PROCUREMENT_CLOSED_RFQ_REQUIRED")
            if payload.evaluation_type == "COMMERCIAL" and payload.engineering_reference is not None:
                self._error(422, "PROCUREMENT_COMMERCIAL_ENGINEERING_REFERENCE_NOT_ALLOWED")
            today = utc_now().date()
            evaluated = payload.evaluated_on or today
            if not bid.received_at.date() <= evaluated <= today:
                self._error(422, "PROCUREMENT_EVALUATION_DATE_INVALID")
            profile = self._pinned_profile(rfq)
            assessments = self._source_rows(ProcurementEvaluation, workspace, ProcurementEvaluation.bid_id == bid.id)
            if any(item.evaluation_type == payload.evaluation_type for item in assessments):
                self._error(409, "PROCUREMENT_EVALUATION_IMMUTABLE")
            if profile["separation_of_duties"]["technical_and_commercial_distinct"] and any(
                item.created_by == self.actor_id for item in assessments
            ):
                self._error(403, "PROCUREMENT_EVALUATION_SOD")
            self._check_document_pin(workspace, bid.document_reference)
            values = {
                "bid_id": bid.id,
                "evaluation_type": payload.evaluation_type,
                "evaluated_on": evaluated,
                "result": payload.result,
                "score": payload.score,
                "comments": payload.comments,
                "recommendation": payload.recommendation,
                "engineering_reference": self._pin(workspace, payload.engineering_reference),
                "document_reference": self._document_pin(workspace, payload.document_reference),
            }
            digest = _hash(
                _json(
                    values
                    | {
                        "created_by": self.actor_id,
                        "score": self._decimal_string(payload.score) if payload.score is not None else None,
                    }
                )
            )
            row = self._new(ProcurementEvaluation, workspace, **values, content_hash=digest)
            return self._record(row, "EVALUATION_RECORDED", payload.reason)

        return self._write(action, workspace, payload, key, apply)

    def create_award(self, workspace, payload, key):
        self._ready(workspace, "award.approve")

        def apply():
            rfq = self._get(ProcurementRFQ, workspace, payload.rfq_id, lock=True)
            if rfq.status != "CLOSED":
                self._error(409, "PROCUREMENT_CLOSED_RFQ_REQUIRED")
            self._active_package(workspace, rfq.package_id)
            bid = self._current_bid(workspace, self._get(ProcurementBid, workspace, payload.bid_id))
            if bid.rfq_id != rfq.id:
                self._error(404, "PROCUREMENT_RFQ_BID_NOT_FOUND")
            self._vendor(bid.vendor_id, active=True)
            today = utc_now().date()
            decided = payload.decision_date or today
            if not bid.received_at.date() <= decided <= today or bid.validity_date < today:
                self._error(409, "PROCUREMENT_AWARD_BID_DATE_INVALID")
            profile = self._pinned_profile(rfq)
            assessments = self._source_rows(ProcurementEvaluation, workspace, ProcurementEvaluation.bid_id == bid.id)
            by_kind = {item.evaluation_type: item for item in assessments}
            for kind in ("TECHNICAL", "COMMERCIAL"):
                item = by_kind.get(kind)
                if profile[f"require_{kind.lower()}_evaluation"] and (
                    item is None or item.result != "ACCEPTED" or item.recommendation != "RECOMMEND"
                ):
                    self._error(409, "PROCUREMENT_REQUIRED_EVALUATIONS_NOT_ACCEPTED")
            for item in assessments:
                if decided < item.evaluated_on or _hash(self._evaluation_material(item)) != item.content_hash:
                    self._error(409, "PROCUREMENT_EVALUATION_SOURCE_INVALID")
                self._check_pin(workspace, item.engineering_reference)
                self._check_document_pin(workspace, item.document_reference)
            if profile["separation_of_duties"]["evaluator_cannot_award"] and any(
                item.created_by == self.actor_id for item in assessments
            ):
                self._error(403, "PROCUREMENT_AWARD_SOD")
            requisition = self._get(ProcurementRequisition, workspace, rfq.requisition_id)
            self._requisition_inputs(workspace, requisition)
            self._check_document_pin(workspace, bid.document_reference)
            snapshot = {
                "rfq_id": rfq.id,
                "rfq_version": rfq.version,
                "requisition_id": requisition.id,
                "package_id": rfq.package_id,
                "bid_id": bid.id,
                "bid_hash": bid.content_hash,
                "vendor_id": bid.vendor_id,
                "currency": bid.currency,
                "award_value": self._decimal_string(bid.total_bid_value),
                "evaluations": [
                    {"id": item.id, "type": item.evaluation_type, "hash": item.content_hash} for item in assessments
                ],
                "decided_at": decided.isoformat(),
                "actor_id": self.actor_id,
                "approval_reference": payload.approval_reference,
            }
            row = self._new(
                ProcurementAward,
                workspace,
                rfq_id=rfq.id,
                bid_id=bid.id,
                vendor_id=bid.vendor_id,
                package_id=rfq.package_id,
                decision_date=decided,
                approval_reference=payload.approval_reference,
                snapshot_json=snapshot,
                content_hash=_hash(snapshot),
            )
            return self._record(row, "AWARD_RECORDED", payload.reason)

        return self._write("award.approve", workspace, payload, key, apply)

    def _purchase_order_legacy_references(self, workspace, payload):
        binding = _cde_binding(self.db, self.tenant_id, workspace)
        if payload.legacy_purchase_order_id is not None or payload.reference_contract_id is not None:
            if binding is None:
                self._error(409, "PROCUREMENT_LEGACY_BINDING_REQUIRED")
        if binding is not None:
            legacy = self.db.scalar(
                select(PurchaseOrder).where(
                    PurchaseOrder.tenant_id == self.tenant_id,
                    PurchaseOrder.project_id == binding.legacy_project_id,
                    PurchaseOrder.po_number == payload.po_number.upper(),
                )
            )
            if legacy and legacy.id != payload.legacy_purchase_order_id:
                self._error(409, "PROCUREMENT_LEGACY_PO_NUMBER_COLLISION")
            if payload.legacy_purchase_order_id is not None and (
                not legacy or legacy.id != payload.legacy_purchase_order_id
            ):
                self._error(404, "PROCUREMENT_LEGACY_PO_NOT_FOUND")
            if (
                payload.reference_contract_id is not None
                and self.db.scalar(
                    select(Contract.id).where(
                        Contract.tenant_id == self.tenant_id,
                        Contract.project_id == binding.legacy_project_id,
                        Contract.id == payload.reference_contract_id,
                    )
                )
                is None
            ):
                self._error(404, "PROCUREMENT_CONTRACT_REFERENCE_NOT_FOUND")
        if payload.reference_commitment_id is not None:
            self._get(CostCommitmentReference, workspace, payload.reference_commitment_id)

    def _po_total(self, lines):
        value = sum((Decimal(str(line["quantity"])) * Decimal(str(line["unit_price"])) for line in lines), Decimal(0))
        if value > Decimal("99999999999999.999999"):
            self._error(422, "PROCUREMENT_PO_VALUE_OUT_OF_RANGE")
        return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    def create_purchase_order(self, workspace, payload, key):
        _, profile = self._ready(workspace, "po.create")

        def apply():
            self._active_package(workspace, payload.package_id, lock=True)
            self._vendor(payload.vendor_id, active=True)
            requested = self._requirement_quantities(workspace, payload.package_id, payload.lines)
            if payload.award_id is None and profile.content_json["require_award_for_po"]:
                self._error(409, "PROCUREMENT_PO_AWARD_REQUIRED")
            total = self._po_total([line.model_dump() for line in payload.lines])
            currency = payload.currency.upper()
            if payload.award_id is not None:
                award = self._get(ProcurementAward, workspace, payload.award_id)
                if award.package_id != payload.package_id or award.vendor_id != payload.vendor_id:
                    self._error(409, "PROCUREMENT_AWARD_PACKAGE_VENDOR_MISMATCH")
                if _hash(award.snapshot_json) != award.content_hash:
                    self._error(409, "PROCUREMENT_AWARD_HASH_MISMATCH")
                if currency != award.snapshot_json["currency"] or total > Decimal(award.snapshot_json["award_value"]):
                    self._error(422, "PROCUREMENT_PO_AWARD_VALUE_OR_CURRENCY_MISMATCH")
                if payload.issue_date < award.decision_date:
                    self._error(422, "PROCUREMENT_PO_PRECEDES_AWARD")
                req = self._get(ProcurementRequisition, workspace, award.snapshot_json["requisition_id"])
                awarded = defaultdict(Decimal)
                for line in self._requisition_inputs(workspace, req):
                    awarded[line.requirement_id] += line.quantity
                if any(quantity > awarded[identity] for identity, quantity in requested.items()):
                    self._error(422, "PROCUREMENT_PO_AWARD_SCOPE_EXCEEDED")
            self._purchase_order_legacy_references(workspace, payload)
            values = payload.model_dump(exclude={"reason", "lines", "po_number", "currency", "document_reference"})
            row = self._new(
                ProcurementPurchaseOrder,
                workspace,
                **values,
                po_number=self._code(payload.po_number),
                currency=currency,
                original_value=total,
                current_value=total,
                document_reference=self._document_pin(workspace, payload.document_reference),
                **self._profile_pin(profile),
            )
            for item in payload.lines:
                self._new(
                    ProcurementPurchaseOrderLine,
                    workspace,
                    purchase_order_id=row.id,
                    **(item.model_dump() | {"uom": item.uom.upper()}),
                )
            self._record(row, "PO_CREATED", payload.reason)
            return self._source_detail(workspace, row)

        return self._write("po.create", workspace, payload, key, apply)

    def _po_line_snapshot(self, line):
        material = _json(
            {
                key: getattr(line, key)
                for key in (
                    "requirement_id",
                    "line_number",
                    "description",
                    "uom",
                    "requested_date",
                    "promised_date",
                    "forecast_date",
                )
            }
        )
        return material | {
            "line_id": line.id,
            "quantity": self._decimal_string(line.quantity),
            "unit_price": self._decimal_string(line.unit_price),
        }

    def _new_po_revision(self, workspace, order, previous, lines, date, reason, *, schedule=None, approved=False):
        total = self._po_total(lines)
        values = {
            "purchase_order_id": order.id,
            "previous_revision_id": previous.id if previous else None,
            "revision": previous.revision + 1 if previous else 1,
            "effective_date": date,
            "reason": reason,
            "lines_snapshot": lines,
            "schedule_impact_reference": schedule or {},
        }
        row = self._new(
            ProcurementPurchaseOrderRevision,
            workspace,
            **values,
            content_hash=_hash(_json(values)),
            status="APPROVED" if approved else "DRAFT",
            approved_by=self.actor_id if approved else None,
            approval_reference="PO_INITIAL_APPROVAL" if approved else "",
            total_value=total,
            value_delta=total - previous.total_value if previous else Decimal(0),
        )
        self._record(row, "PO_REVISION_APPROVED" if approved else "PO_REVISION_PREPARED", reason)
        return row

    def _make_initial_po_revision(self, workspace, order, lines, reason):
        return self._new_po_revision(
            workspace,
            order,
            None,
            [self._po_line_snapshot(line) for line in lines],
            order.effective_date,
            reason,
            approved=True,
        )

    def _po_revision(self, workspace, order, identity, *, lock=False):
        if identity is None:
            self._error(409, "PROCUREMENT_APPROVED_PO_REVISION_REQUIRED")
        row = self._get(ProcurementPurchaseOrderRevision, workspace, identity, lock=lock)
        if row.purchase_order_id != order.id:
            self._error(404, "PROCUREMENT_PO_REVISION_NOT_FOUND")
        if _hash(po_revision_material(row)) != row.content_hash:
            self._error(409, "PROCUREMENT_PO_REVISION_HASH_MISMATCH")
        return row

    def effective_po_line(self, workspace, line_id):
        line = self._get(ProcurementPurchaseOrderLine, workspace, line_id)
        order = self._get(ProcurementPurchaseOrder, workspace, line.purchase_order_id)
        revision = self._po_revision(workspace, order, order.current_revision_id)
        if revision.status != "APPROVED" or revision.effective_date > utc_now().date():
            self._error(409, "PROCUREMENT_EFFECTIVE_PO_REVISION_REQUIRED")
        matching = [entry for entry in revision.lines_snapshot if entry["line_id"] == line.id]
        if len(matching) != 1 or matching[0]["uom"] != line.uom:
            self._error(409, "PROCUREMENT_PO_LINE_REVISION_MISMATCH")
        return line, matching[0] | {"po_revision_id": revision.id, "po_revision_hash": revision.content_hash}

    def create_po_revision(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "po.revise")

        def apply():
            order = self._get(ProcurementPurchaseOrder, workspace, identity, lock=True)
            self._version(order.version, expected)
            if order.status != "ISSUED":
                self._error(409, "PROCUREMENT_ISSUED_PO_REQUIRED")
            previous = self._po_revision(workspace, order, order.current_revision_id)
            if payload.effective_date < previous.effective_date:
                self._error(422, "PROCUREMENT_PO_REVISION_DATE_INVALID")
            if (
                self.db.scalar(
                    self._scoped(ProcurementPurchaseOrderRevision, workspace).where(
                        ProcurementPurchaseOrderRevision.previous_revision_id == previous.id,
                    )
                )
                is not None
            ):
                self._error(409, "PROCUREMENT_PO_SUCCESSOR_EXISTS")
            lines = {item["line_id"]: item.copy() for item in previous.lines_snapshot}
            ids = {change.line_id for change in payload.changed_lines}
            if len(ids) != len(payload.changed_lines) or ids - lines.keys():
                self._error(422, "PROCUREMENT_PO_REVISION_LINE_INVALID")
            for change in payload.changed_lines:
                item = lines[change.line_id]
                item.update(
                    {
                        "quantity": self._decimal_string(change.quantity),
                        "unit_price": self._decimal_string(change.unit_price),
                    }
                )
                for field in ("promised_date", "forecast_date"):
                    if field in change.model_fields_set:
                        item[field] = _json(getattr(change, field))
            self._validate_po_revision_lines(workspace, order, list(lines.values()))
            revision = self._new_po_revision(
                workspace,
                order,
                previous,
                list(lines.values()),
                payload.effective_date,
                payload.reason,
                schedule=self._pin(workspace, payload.schedule_impact_reference),
            )
            return self._out(revision) | {"purchase_order_version": order.version}

        return self._write("po.revise", workspace, payload, key, apply, identity, expected)

    def _validate_po_revision_lines(self, workspace, order, lines):
        from app.modules.procurement_foundation.materials_models import (
            ProcurementMaterialReceiptLine,
            ProcurementShipment,
            ProcurementShipmentLine,
        )

        typed = [SimpleNamespace(**(line | {"quantity": Decimal(line["quantity"])})) for line in lines]
        self._requirement_quantities(workspace, order.package_id, typed)
        for line in typed:
            reserved = self.db.scalar(
                select(func.coalesce(func.sum(ProcurementShipmentLine.quantity), 0))
                .join(ProcurementShipment, ProcurementShipment.id == ProcurementShipmentLine.shipment_id)
                .where(
                    ProcurementShipmentLine.tenant_id == self.tenant_id,
                    ProcurementShipmentLine.project_workspace_id == workspace,
                    ProcurementShipmentLine.po_line_id == line.line_id,
                    ProcurementShipment.tenant_id == self.tenant_id,
                    ProcurementShipment.project_workspace_id == workspace,
                    ProcurementShipment.status != "CANCELLED",
                )
            )
            received = self.db.scalar(
                select(func.coalesce(func.sum(ProcurementMaterialReceiptLine.quantity), 0)).where(
                    ProcurementMaterialReceiptLine.tenant_id == self.tenant_id,
                    ProcurementMaterialReceiptLine.project_workspace_id == workspace,
                    ProcurementMaterialReceiptLine.po_line_id == line.line_id,
                )
            )
            if line.quantity < max(reserved, received):
                self._error(409, "PROCUREMENT_PO_REVISION_BELOW_PHYSICAL_QUANTITY")

    def approve_po_revision(self, workspace, identity, revision_id, payload, expected, key):
        self._ready(workspace, "po.revision.approve")

        def apply():
            order = self._get(ProcurementPurchaseOrder, workspace, identity, lock=True)
            row = self._po_revision(workspace, order, revision_id, lock=True)
            self._version(row.version, expected)
            if (
                order.status != "ISSUED"
                or row.status != "DRAFT"
                or row.previous_revision_id != order.current_revision_id
            ):
                self._error(409, "PROCUREMENT_PO_REVISION_STATE_CONFLICT")
            if row.effective_date > utc_now().date():
                self._error(409, "PROCUREMENT_PO_REVISION_EFFECTIVE_DATE_IN_FUTURE")
            if (
                self._pinned_profile(order)["separation_of_duties"]["po_revision_preparer_cannot_approve"]
                and row.created_by == self.actor_id
            ):
                self._error(403, "PROCUREMENT_PO_REVISION_APPROVAL_SOD")
            self._check_pin(workspace, row.schedule_impact_reference)
            self._validate_po_revision_lines(workspace, order, row.lines_snapshot)
            row.status, row.approved_by, row.approval_reference = "APPROVED", self.actor_id, payload.approval_reference
            revision = self._record(row, "PO_REVISION_APPROVED", payload.reason, changed=True)
            order.current_revision_id, order.current_value = row.id, row.total_value
            self._record(order, "PO_REVISION_EFFECTIVE", payload.reason, changed=True)
            return revision | {"purchase_order_version": order.version}

        return self._write("po.revision.approve", workspace, payload, key, apply, revision_id, expected)
