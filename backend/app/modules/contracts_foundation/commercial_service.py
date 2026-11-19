"""Commercial lifecycle commands; upstream authorities are read-only."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.time import utc_now, utc_today
from app.modules.awp.models import CWA, WorkPackage
from app.modules.basic_data.service import _hash, _json
from app.modules.contracts_foundation.commercial_models import (
    ContractChange,
    ContractClaim,
    ContractFinanceReference,
    ContractMapping,
    ContractSOV,
    ContractSOVLine,
    OperationalContractNotice,
    OperationalPaymentCertificate,
    PaymentApplication,
    PaymentApplicationLine,
    PaymentCertificateLine,
)
from app.modules.contracts_foundation.models import ContractPackage, ContractVersion, OperationalContract
from app.modules.contracts_foundation.service import ContractsService, _version_hash
from app.modules.cost_foundation.models import ControlAccount, CostCBS, CostCode
from app.modules.operational_context.models import ProjectControlsPeriod
from app.modules.procurement_foundation.sourcing_models import ProcurementPackage
from app.modules.progress_foundation.models import ProgressMeasurement
from app.modules.progress_foundation.service import ProgressFoundationService

MONEY = Decimal("0.00000001")
MAX_AMOUNT = Decimal("9999999999999999.99999999")
ACTIVE_CONTRACT = {"EXECUTED", "EFFECTIVE"}
RESOURCES = {
    "sovs": (ContractSOV, ContractSOVLine, "sov_id"),
    "changes": (ContractChange, None, None),
    "payment-applications": (PaymentApplication, PaymentApplicationLine, "application_id"),
    "payment-certificates": (OperationalPaymentCertificate, PaymentCertificateLine, "certificate_id"),
    "notices": (OperationalContractNotice, None, None),
    "claims": (ContractClaim, None, None),
    "finance-references": (ContractFinanceReference, None, None),
    "mappings": (ContractMapping, None, None),
}
TARGETS = {
    "CWA": CWA,
    "CWP": WorkPackage,
    "PWP": WorkPackage,
    "IWP": WorkPackage,
    "CBS": CostCBS,
    "COST_CODE": CostCode,
    "CONTROL_ACCOUNT": ControlAccount,
}
SOV_KINDS = {"SCOPE", "PLAN", *TARGETS}
CHANGE_TRANSITIONS = {
    "request": ("POTENTIAL", "REQUESTED", "change.prepare"),
    "review": ("REQUESTED", "UNDER_REVIEW", "change.review"),
    "approve": ("UNDER_REVIEW", "ORDER_APPROVED", "change.approve"),
    "reject": ("UNDER_REVIEW", "REJECTED", "change.approve"),
}


class CommercialWorkflows(ContractsService):
    @staticmethod
    def _code(value):
        return value.upper()

    def _profile_pin(self, profile):
        return {"configuration_id": profile.id, "configuration_hash": profile.content_hash}

    def _money(self, value, *, positive=False):
        try:
            value = value.quantize(MONEY, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            self._error(422, "CONTRACTS_VALUE_OUT_OF_RANGE")
        if not value.is_finite() or abs(value) > MAX_AMOUNT or (positive and value <= 0):
            self._error(422, "CONTRACTS_VALUE_OUT_OF_RANGE")
        return value

    def _catalog(self, content, category, value):
        if value not in content[category]:
            self._error(422, "CONTRACTS_CATALOG_VALUE_INVALID")
        return value

    def _sod(self, content, key, *actors):
        if content["separation_of_duties"].get(key, True) and self.actor_id in actors:
            self._error(403, "CONTRACTS_SEPARATION_OF_DUTIES")

    def _optional_document(self, workspace, payload):
        return self._document(workspace, payload) if payload is not None else None

    def _document_current(self, workspace, snapshot):
        if not snapshot:
            self._error(422, "CONTRACTS_CDE_DOCUMENT_REQUIRED")
        return self._check_document(workspace, snapshot)

    def _children(self, model, workspace, column, value):
        return list(
            self.db.scalars(self._scoped(model, workspace).where(getattr(model, column) == value).order_by(model.id))
        )

    def commercial_list(self, workspace, resource, *, limit=50, after_id=0, contract_id=None, status=None):
        self._read_project(workspace)
        model, _, _ = RESOURCES[resource]
        query = self._scoped(model, workspace).where(model.id > after_id)
        if contract_id:
            self._get(OperationalContract, workspace, contract_id)
            if hasattr(model, "contract_id"):
                query = query.where(model.contract_id == contract_id)
            elif model is ContractFinanceReference:
                certs = (
                    self._scoped(OperationalPaymentCertificate, workspace)
                    .where(
                        OperationalPaymentCertificate.contract_id == contract_id,
                    )
                    .with_only_columns(OperationalPaymentCertificate.id)
                )
                query = query.where(model.certificate_id.in_(certs))
            elif model is ContractMapping:
                query = query.where(model.source_kind == "CONTRACT", model.source_id == contract_id)
        if status:
            if not hasattr(model, "status"):
                self._error(422, "CONTRACTS_STATUS_FILTER_UNSUPPORTED")
            query = query.where(model.status == status)
        rows = list(self.db.scalars(query.order_by(model.id).limit(limit + 1)))
        return {
            "items": [self._redact(workspace, self._out(row)) for row in rows[:limit]],
            "next_after_id": rows[limit - 1].id if len(rows) > limit else None,
        }

    def commercial_detail(self, workspace, resource, identity):
        self._read_project(workspace)
        model, children, parent = RESOURCES[resource]
        row = self._get(model, workspace, identity)
        output = self._out(row)
        if children:
            output["lines"] = [self._out(item) for item in self._children(children, workspace, parent, row.id)]
        if model is OperationalPaymentCertificate:
            output["finance_references"] = [
                self._out(item)
                for item in self._children(ContractFinanceReference, workspace, "certificate_id", row.id)
            ]
        return self._redact(workspace, output)

    def _contract_version(self, workspace, contract_id, version_id=None, *, lock=False):
        contract = self._get(OperationalContract, workspace, contract_id, lock=lock)
        if contract.status not in ACTIVE_CONTRACT or not contract.current_version_id:
            self._error(409, "CONTRACTS_EXECUTED_CONTRACT_REQUIRED")
        version = self._get(ContractVersion, workspace, version_id or contract.current_version_id)
        if version.id != contract.current_version_id or version.contract_id != contract.id:
            self._error(409, "CONTRACTS_CURRENT_CONTRACT_VERSION_REQUIRED")
        if version.status != "APPROVED" or version.source_hash != _version_hash(version):
            self._error(409, "CONTRACTS_VERSION_INTEGRITY_INVALID")
        return contract, version

    def _assert_distinct(self, values, code):
        if len(set(values)) != len(values):
            self._error(422, code)

    def _target(self, workspace, request):
        ref = request.model_dump() if hasattr(request, "model_dump") else request
        pin = self.resolve_reference(workspace, ref)
        if ref["target_kind"] in TARGETS:
            target = self._get(TARGETS[ref["target_kind"]], workspace, ref["target_id"])
            if target.status in {"INACTIVE", "CANCELLED", "SUPERSEDED", "RETIRED", "ARCHIVED"}:
                self._error(409, "CONTRACTS_TARGET_INACTIVE")
        return pin

    @staticmethod
    def _target_input(pin):
        return {
            key: pin.get(key)
            for key in ("target_kind", "target_id", "schedule_version_id", "external_id", "source_hash")
        }

    def create_sov(self, workspace, payload, key):
        self._ready(workspace, "sov.edit")

        def apply():
            _, profile = self._ready(workspace, "sov.edit")
            contract, version = self._contract_version(workspace, payload.contract_id, payload.contract_version_id)
            self._assert_distinct([item.line_number for item in payload.lines], "CONTRACTS_DUPLICATE_SOV_LINE")
            prior = self.db.scalar(
                self._scoped(ContractSOV, workspace)
                .where(
                    ContractSOV.contract_id == contract.id,
                    ContractSOV.status == "PUBLISHED",
                )
                .order_by(ContractSOV.id.desc())
                .limit(1)
            )
            old_lines = (
                {line.line_number: line for line in self._children(ContractSOVLine, workspace, "sov_id", prior.id)}
                if prior
                else {}
            )
            previous_usage = {
                number: self._applied_quantity(workspace, contract_id=contract.id, line_number=number)
                for number in old_lines
            }
            proposed_numbers = {item.line_number for item in payload.lines}
            if any(quantity and number not in proposed_numbers for number, quantity in previous_usage.items()):
                self._error(409, "CONTRACTS_APPLIED_SOV_LINE_CANNOT_BE_REMOVED")
            data = []
            for item in payload.lines:
                old_line = old_lines.get(item.line_number)
                if (
                    old_line
                    and previous_usage[item.line_number]
                    and (item.uom != old_line.uom or item.quantity < previous_usage[item.line_number])
                ):
                    self._error(409, "CONTRACTS_SOV_LINE_BELOW_PRIOR_APPLICATIONS")
                if any(ref.target_kind not in SOV_KINDS for ref in item.mappings):
                    self._error(422, "CONTRACTS_SOV_MAPPING_KIND_INVALID")
                self._assert_distinct(
                    [(ref.target_kind, ref.target_id) for ref in item.mappings],
                    "CONTRACTS_DUPLICATE_SOV_MAPPING",
                )
                mappings = [self._target(workspace, ref) for ref in item.mappings]
                rules = profile.content_json["retention_rules"]
                if item.retention_rule is not None and item.retention_rule not in rules:
                    self._error(422, "CONTRACTS_RETENTION_RULE_INVALID")
                rate = Decimal(str(rules[item.retention_rule])) if item.retention_rule else Decimal(0)
                value = self._money(item.quantity * item.unit_rate, positive=True)
                values = {
                    "line_number": item.line_number,
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_rate": item.unit_rate,
                    "uom": item.uom,
                    "mappings": mappings,
                    "retention_rule": item.retention_rule,
                    "retention_rate": rate,
                    "original_value": old_line.original_value if old_line is not None else value,
                    "current_value": value,
                }
                data.append(values | {"source_hash": _hash(_json(values))})
            total = self._money(sum(line["current_value"] for line in data), positive=True)
            if total > version.value:
                self._error(422, "CONTRACTS_SOV_EXCEEDS_CONTRACT_VERSION")
            row = self._new(
                ContractSOV,
                workspace,
                contract_id=contract.id,
                contract_version_id=version.id,
                code=self._code(payload.code),
                currency=contract.currency,
                total_value=total,
                source_hash=_hash(_json({"contract_version_id": version.id, "lines": data})),
                **self._profile_pin(profile),
            )
            lines = [self._new(ContractSOVLine, workspace, sov_id=row.id, **values) for values in data]
            return self._record(row, "SOV_DRAFTED", payload.reason) | {"lines": [self._out(line) for line in lines]}

        return self._write("sov.create", workspace, payload, key, apply)

    def publish_sov(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "sov.publish")

        def apply():
            self._ready(workspace, "sov.publish")
            row = self._get(ContractSOV, workspace, identity, lock=True)
            self._version(row.version, expected)
            profile = self._pinned_profile(row)
            self._sod(profile, "sov_author_cannot_publish", row.created_by)
            self._contract_version(workspace, row.contract_id, row.contract_version_id)
            if row.status != "DRAFT" or self.db.scalar(
                self._scoped(ContractSOV, workspace)
                .where(
                    ContractSOV.contract_id == row.contract_id,
                    ContractSOV.contract_version_id == row.contract_version_id,
                    ContractSOV.status == "PUBLISHED",
                )
                .limit(1)
            ):
                self._error(409, "CONTRACTS_SOV_PUBLICATION_CONFLICT")
            for line in self._children(ContractSOVLine, workspace, "sov_id", row.id):
                for pin in line.mappings:
                    if self._target(workspace, self._target_input(pin)) != pin:
                        self._error(409, "CONTRACTS_SOV_MAPPING_STALE")
            row.status, row.published_by, row.published_at = "PUBLISHED", self.actor_id, utc_now()
            return self._record(row, "SOV_PUBLISHED", payload.reason, changed=True)

        return self._write("sov.publish", workspace, payload, key, apply, identity, expected)

    def create_change(self, workspace, payload, key):
        self._ready(workspace, "change.prepare")

        def apply():
            _, profile = self._ready(workspace, "change.prepare")
            contract, version = self._contract_version(workspace, payload.contract_id, payload.base_version_id)
            self._catalog(profile.content_json, "change_types", payload.change_type)
            self._notice_for_contract(workspace, payload.notice_id, contract.id)
            if payload.effective_date < version.effective_date:
                self._error(422, "CONTRACTS_CHANGE_EFFECTIVE_DATE_INVALID")
            schedule = [self._target(workspace, reference) for reference in payload.schedule_references]
            self._assert_distinct(
                [(ref["target_kind"], ref["schedule_version_id"], ref["external_id"]) for ref in schedule],
                "CONTRACTS_DUPLICATE_SCHEDULE_REFERENCE",
            )
            values = payload.model_dump(exclude={"reason", "schedule_references", "document_reference"})
            values |= {
                "change_number": self._code(payload.change_number),
                "schedule_references": schedule,
                "document_reference": self._optional_document(workspace, payload.document_reference),
            }
            row = self._new(
                ContractChange, workspace, **values, source_hash=_hash(_json(values)), **self._profile_pin(profile)
            )
            return self._record(row, "POTENTIAL_CHANGE_REGISTERED", payload.reason)

        return self._write("change.create", workspace, payload, key, apply)

    def change_action(self, workspace, identity, payload, expected, key):
        old, new, duty = CHANGE_TRANSITIONS[payload.action]
        self._ready(workspace, duty)

        def apply():
            self._ready(workspace, duty)
            row = self._get(ContractChange, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != old:
                self._error(409, "CONTRACTS_CHANGE_TRANSITION_INVALID")
            profile = self._pinned_profile(row)
            if payload.action != "reject":
                contract, version = self._contract_version(workspace, row.contract_id, row.base_version_id, lock=True)
            if payload.document_reference:
                row.document_reference = self._document(workspace, payload.document_reference)
            if payload.action == "request":
                row.requested_by = self.actor_id
            elif payload.action == "review":
                row.reviewed_by = self.actor_id
            else:
                self._sod(profile, "change_author_cannot_approve", row.created_by, row.requested_by)
            if payload.action == "approve":
                self._threshold(profile, "change_approval_limit", row.value_delta)
                self._money(version.value + row.value_delta)
                document = self._document_current(workspace, row.document_reference)
                for pin in row.schedule_references:
                    if self._target(workspace, self._target_input(pin)) != pin:
                        self._error(409, "CONTRACTS_CHANGE_SCHEDULE_PIN_STALE")
                row.resulting_version_id = self.apply_change_version(
                    workspace,
                    contract,
                    version,
                    value_delta=row.value_delta,
                    time_delta=row.time_delta,
                    effective_date=row.effective_date,
                    document=document,
                    reason=payload.reason,
                    change_id=row.id,
                ).id
                row.approved_by, row.approved_at = self.actor_id, utc_now()
            row.status = new
            row.source_hash = _hash(self._out(row, exclude=("source_hash", "version")))
            return self._record(row, f"CHANGE_{new}", payload.reason, changed=True)

        return self._write(f"change.{payload.action}", workspace, payload, key, apply, identity, expected)

    def _progress(self, workspace, line, period_id, measurement_id, *, version=None, digest=None):
        row = self._get(ProgressMeasurement, workspace, measurement_id)
        allowed = {
            ref["target_kind"]: {
                item["target_id"] for item in line.mappings if item["target_kind"] == ref["target_kind"]
            }
            for ref in line.mappings
            if ref["target_kind"] in {"SCOPE", "PLAN", "IWP"}
        }
        source_keys = {"SCOPE": row.scope_item_id, "PLAN": row.plan_item_id, "IWP": row.work_package_id}
        if (
            row.status != "APPROVED"
            or not row.approved_at
            or row.period_id != period_id
            or row.progress_type not in {"QUANTITY", "PHYSICAL"}
            or row.phase != "INSTALL"
            or row.period_quantity <= 0
            or row.unit != line.uom
            or not allowed
            or any(source_keys[kind] not in targets for kind, targets in allowed.items())
        ):
            self._error(409, "CONTRACTS_APPROVED_PROGRESS_EVIDENCE_REQUIRED")
        reader = ProgressFoundationService(self.db, self.tenant_id, self.actor_id)
        approved_ids = {candidate.id for candidate in reader.effective_approved(workspace)}
        if row.id not in approved_ids or reader._source_state(row) != "CURRENT":
            self._error(409, "CONTRACTS_PROGRESS_EVIDENCE_STALE")
        for pin in line.mappings:
            if self._target(workspace, self._target_input(pin)) != pin:
                self._error(409, "CONTRACTS_SOV_MAPPING_STALE")
        if (version is not None and version != row.version) or (digest is not None and digest != row.content_hash):
            self._error(409, "CONTRACTS_PROGRESS_PIN_MISMATCH")
        return {
            "source_domain": "PROGRESS",
            "measurement_id": row.id,
            "version": row.version,
            "source_hash": row.content_hash,
            "source_basis_hash": row.source_hash,
            "period_id": row.period_id,
            "scope_item_id": row.scope_item_id,
            "plan_item_id": row.plan_item_id,
            "work_package_id": row.work_package_id,
            "subject_key": row.subject_key,
            "unit": row.unit,
            "quantity": str(row.period_quantity),
            "as_of": row.as_of.isoformat(),
        }

    def progress_sources(self, workspace, period_id, sov_line_id, *, limit=50, after_id=0):
        self._read_project(workspace)
        self._get(ProjectControlsPeriod, workspace, period_id)
        line = self._get(ContractSOVLine, workspace, sov_line_id)
        query = (
            self._scoped(ProgressMeasurement, workspace)
            .where(
                ProgressMeasurement.id > after_id,
                ProgressMeasurement.period_id == period_id,
                ProgressMeasurement.status == "APPROVED",
            )
            .order_by(ProgressMeasurement.id)
            .limit(limit + 1)
        )
        rows = list(self.db.scalars(query))
        items = []
        for row in rows[:limit]:
            try:
                items.append(self._progress(workspace, line, period_id, row.id))
            except HTTPException as error:
                if error.status_code not in {403, 404, 409, 422}:
                    raise
        return {"items": items, "next_after_id": rows[limit - 1].id if len(rows) > limit else None}

    def _applied_quantity(self, workspace, *, contract_id=None, line_number=None, progress=None):
        query = (
            select(func.coalesce(func.sum(PaymentApplicationLine.quantity), 0))
            .join(
                PaymentApplication,
                PaymentApplication.id == PaymentApplicationLine.application_id,
            )
            .where(
                PaymentApplicationLine.tenant_id == self.tenant_id,
                PaymentApplicationLine.project_workspace_id == workspace,
                PaymentApplication.tenant_id == self.tenant_id,
                PaymentApplication.project_workspace_id == workspace,
                PaymentApplication.status != "REJECTED",
            )
        )
        if line_number is not None:
            query = query.join(ContractSOVLine, ContractSOVLine.id == PaymentApplicationLine.sov_line_id).where(
                ContractSOVLine.tenant_id == self.tenant_id,
                ContractSOVLine.project_workspace_id == workspace,
                ContractSOVLine.line_number == line_number,
                PaymentApplication.contract_id == contract_id,
            )
        if progress:
            # A quantity and a physical observation of the same subject and period are not separate
            # billable quantities; nor is a corrected or reopened-period successor.
            row = self._get(ProgressMeasurement, workspace, progress["measurement_id"])
            period_ids = {row.period_id}
            visited = {row.id}
            while row.supersedes_id and row.supersedes_id not in visited:
                row = self._get(ProgressMeasurement, workspace, row.supersedes_id)
                visited.add(row.id)
                period_ids.add(row.period_id)
            query = query.join(
                ProgressMeasurement,
                ProgressMeasurement.id == PaymentApplicationLine.progress_measurement_id,
            ).where(
                ProgressMeasurement.tenant_id == self.tenant_id,
                ProgressMeasurement.project_workspace_id == workspace,
                ProgressMeasurement.subject_key == progress["subject_key"],
                ProgressMeasurement.period_id.in_(period_ids),
            )
        return self.db.scalar(query)

    def create_application(self, workspace, payload, key):
        self._ready(workspace, "application.prepare")

        def apply():
            _, profile = self._ready(workspace, "application.prepare")
            contract, version = self._contract_version(workspace, payload.contract_id)
            if contract.status != "EFFECTIVE":
                self._error(409, "CONTRACTS_EFFECTIVE_CONTRACT_REQUIRED")
            sov = self._get(ContractSOV, workspace, payload.sov_id)
            period = self._get(ProjectControlsPeriod, workspace, payload.period_id)
            if sov.contract_id != contract.id or sov.status != "PUBLISHED" or sov.contract_version_id != version.id:
                self._error(409, "CONTRACTS_PUBLISHED_CURRENT_SOV_REQUIRED")
            if (
                period.status not in {"OPEN", "REVIEW", "CLOSED", "PUBLISHED"}
                or not period.period_start <= payload.effective_date <= period.period_end
                or payload.effective_date < version.effective_date
            ):
                self._error(422, "CONTRACTS_PAYMENT_PERIOD_INVALID")
            self._catalog(profile.content_json, "application_statuses", "SUBMITTED")
            self._assert_distinct([item.sov_line_id for item in payload.lines], "CONTRACTS_DUPLICATE_APPLICATION_LINE")
            data = []
            progress_subjects = set()
            for item in payload.lines:
                line = self._get(ContractSOVLine, workspace, item.sov_line_id)
                if line.sov_id != sov.id:
                    self._error(404, "CONTRACTS_SOV_LINE_NOT_FOUND")
                evidence = self._progress(
                    workspace,
                    line,
                    period.id,
                    item.progress.measurement_id,
                    version=item.progress.version,
                    digest=item.progress.source_hash,
                )
                if payload.effective_date < date.fromisoformat(evidence["as_of"]):
                    self._error(422, "CONTRACTS_APPLICATION_DATE_PRECEDES_PROGRESS")
                progress_subject = (evidence["subject_key"], evidence["period_id"])
                if progress_subject in progress_subjects:
                    self._error(422, "CONTRACTS_DUPLICATE_PROGRESS_REFERENCE")
                progress_subjects.add(progress_subject)
                if self._applied_quantity(
                    workspace, contract_id=contract.id, line_number=line.line_number
                ) + item.quantity > line.quantity or self._applied_quantity(
                    workspace, progress=evidence
                ) + item.quantity > Decimal(evidence["quantity"]):
                    self._error(409, "CONTRACTS_PAYMENT_APPLICATION_EXCEEDS_EVIDENCE")
                data.append(
                    {
                        "sov_line_id": line.id,
                        "progress_measurement_id": evidence["measurement_id"],
                        "progress_reference": evidence,
                        "quantity": item.quantity,
                        "applied_amount": self._money(item.quantity * line.unit_rate, positive=True),
                    }
                )
            total = self._money(sum(item["applied_amount"] for item in data), positive=True)
            values = {
                "contract_id": contract.id,
                "contract_version_id": version.id,
                "sov_id": sov.id,
                "application_number": self._code(payload.application_number),
                "period_id": period.id,
                "effective_date": payload.effective_date,
                "document_reference": self._optional_document(workspace, payload.document_reference),
                "currency": contract.currency,
                "applied_amount": total,
            }
            row = self._new(
                PaymentApplication,
                workspace,
                **values,
                source_hash=_hash(_json(values | {"lines": data})),
                **self._profile_pin(profile),
            )
            lines = [self._new(PaymentApplicationLine, workspace, application_id=row.id, **item) for item in data]
            return self._record(row, "PAYMENT_APPLICATION_SUBMITTED", payload.reason) | {
                "lines": [self._out(line) for line in lines],
            }

        return self._write("application.create", workspace, payload, key, apply)

    def application_action(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "application.review")

        def apply():
            self._ready(workspace, "application.review")
            row = self._get(PaymentApplication, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "SUBMITTED":
                self._error(409, "CONTRACTS_APPLICATION_TRANSITION_INVALID")
            profile = self._pinned_profile(row)
            self._sod(profile, "application_author_cannot_review", row.created_by)
            new = "REVIEWED" if payload.action == "review" else "REJECTED"
            self._catalog(profile, "application_statuses", new)
            if new == "REVIEWED":
                self._contract_version(workspace, row.contract_id, row.contract_version_id)
                self._document_current(workspace, row.document_reference)
                for line in self._children(PaymentApplicationLine, workspace, "application_id", row.id):
                    sov_line = self._get(ContractSOVLine, workspace, line.sov_line_id)
                    self._progress(
                        workspace,
                        sov_line,
                        row.period_id,
                        line.progress_measurement_id,
                        version=line.progress_reference["version"],
                        digest=line.progress_reference["source_hash"],
                    )
            row.status, row.reviewed_by, row.reviewed_at = new, self.actor_id, utc_now()
            return self._record(row, f"PAYMENT_APPLICATION_{new}", payload.reason, changed=True)

        return self._write(f"application.{payload.action}", workspace, payload, key, apply, identity, expected)

    def _certified_quantity(self, workspace, application_line_id):
        return self.db.scalar(
            select(func.coalesce(func.sum(PaymentCertificateLine.quantity), 0))
            .join(
                OperationalPaymentCertificate,
                OperationalPaymentCertificate.id == PaymentCertificateLine.certificate_id,
            )
            .where(
                PaymentCertificateLine.tenant_id == self.tenant_id,
                PaymentCertificateLine.project_workspace_id == workspace,
                PaymentCertificateLine.application_line_id == application_line_id,
                OperationalPaymentCertificate.tenant_id == self.tenant_id,
                OperationalPaymentCertificate.project_workspace_id == workspace,
                OperationalPaymentCertificate.status == "APPROVED",
            )
        )

    def create_certificate(self, workspace, payload, key):
        self._ready(workspace, "certificate.prepare")

        def apply():
            _, profile = self._ready(workspace, "certificate.prepare")
            app = self._get(PaymentApplication, workspace, payload.application_id)
            contract, version = self._contract_version(workspace, app.contract_id, app.contract_version_id)
            if app.status != "REVIEWED":
                self._error(409, "CONTRACTS_REVIEWED_APPLICATION_REQUIRED")
            if payload.effective_date < app.effective_date:
                self._error(422, "CONTRACTS_CERTIFICATE_DATE_INVALID")
            self._catalog(profile.content_json, "certificate_statuses", "DRAFT")
            self._assert_distinct(
                [item.application_line_id for item in payload.lines],
                "CONTRACTS_DUPLICATE_CERTIFICATE_LINE",
            )
            values = []
            for item in payload.lines:
                applied = self._get(PaymentApplicationLine, workspace, item.application_line_id)
                if applied.application_id != app.id:
                    self._error(404, "CONTRACTS_APPLICATION_LINE_NOT_FOUND")
                if self._certified_quantity(workspace, applied.id) + item.quantity > applied.quantity:
                    self._error(409, "CONTRACTS_CERTIFICATE_EXCEEDS_APPLICATION")
                sov = self._get(ContractSOVLine, workspace, applied.sov_line_id)
                gross = self._money(sov.unit_rate * item.quantity, positive=True)
                retention = self._money(gross * sov.retention_rate)
                if item.retention is not None and item.retention != retention:
                    self._error(422, "CONTRACTS_CERTIFICATE_RETENTION_RULE_MISMATCH")
                deductions = item.advance_recovery + item.deductions + item.withholdings + item.other_adjustments
                if deductions + retention > gross:
                    self._error(422, "CONTRACTS_CERTIFICATE_DEDUCTIONS_EXCEED_GROSS")
                values.append(
                    item.model_dump(exclude={"retention"})
                    | {
                        "gross_amount": gross,
                        "retention": retention,
                        "net_amount": self._money(gross - deductions - retention),
                    }
                )
            header = {
                "application_id": app.id,
                "contract_id": contract.id,
                "contract_version_id": version.id,
                "certificate_number": self._code(payload.certificate_number),
                "effective_date": payload.effective_date,
                "document_reference": self._optional_document(workspace, payload.document_reference),
                "currency": contract.currency,
                "gross_amount": self._money(sum(item["gross_amount"] for item in values), positive=True),
                "net_amount": self._money(sum(item["net_amount"] for item in values)),
            }
            row = self._new(
                OperationalPaymentCertificate,
                workspace,
                **header,
                **self._profile_pin(profile),
                source_hash=_hash(_json(header | {"lines": values})),
            )
            lines = [self._new(PaymentCertificateLine, workspace, certificate_id=row.id, **item) for item in values]
            return self._record(row, "PAYMENT_CERTIFICATE_DRAFTED", payload.reason) | {
                "lines": [self._out(line) for line in lines],
            }

        return self._write("certificate.create", workspace, payload, key, apply)

    def certificate_action(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "certificate.approve")

        def apply():
            self._ready(workspace, "certificate.approve")
            row = self._get(OperationalPaymentCertificate, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "DRAFT":
                self._error(409, "CONTRACTS_CERTIFICATE_TRANSITION_INVALID")
            profile = self._pinned_profile(row)
            self._sod(profile, "certificate_author_cannot_approve", row.created_by)
            state = "APPROVED" if payload.action == "approve" else "REJECTED"
            self._catalog(profile, "certificate_statuses", state)
            if state == "APPROVED":
                self._threshold(profile, "certificate_approval_limit", row.gross_amount)
                self._contract_version(workspace, row.contract_id, row.contract_version_id, lock=True)
                self._document_current(workspace, row.document_reference)
                app = self._get(PaymentApplication, workspace, row.application_id)
                for line in self._children(PaymentCertificateLine, workspace, "certificate_id", row.id):
                    applied = self._get(PaymentApplicationLine, workspace, line.application_line_id)
                    sov = self._get(ContractSOVLine, workspace, applied.sov_line_id)
                    self._progress(
                        workspace,
                        sov,
                        app.period_id,
                        applied.progress_measurement_id,
                        version=applied.progress_reference["version"],
                        digest=applied.progress_reference["source_hash"],
                    )
                    if self._certified_quantity(workspace, applied.id) + line.quantity > applied.quantity:
                        self._error(409, "CONTRACTS_CERTIFICATE_EXCEEDS_APPLICATION")
                row.approved_by, row.approved_at = self.actor_id, utc_now()
            row.status = state
            return self._record(row, f"PAYMENT_CERTIFICATE_{state}", payload.reason, changed=True)

        return self._write(f"certificate.{payload.action}", workspace, payload, key, apply, identity, expected)

    def add_finance_reference(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "invoice.reference")

        def apply():
            self._ready(workspace, "invoice.reference")
            row = self._get(OperationalPaymentCertificate, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "APPROVED" or not row.approved_at:
                self._error(409, "CONTRACTS_APPROVED_CERTIFICATE_REQUIRED")
            self._document_current(workspace, row.document_reference)
            refs = self._scoped(ContractFinanceReference, workspace)
            previous = self.db.scalar(
                refs.where(
                    ContractFinanceReference.source_system == payload.source_system,
                    ContractFinanceReference.invoice_reference == payload.invoice_reference,
                )
                .order_by(ContractFinanceReference.source_version.desc())
                .limit(1)
            )
            if previous and (
                previous.certificate_id != row.id
                or payload.source_version <= previous.source_version
                or previous.source_hash == payload.source_hash
            ):
                self._error(409, "CONTRACTS_FINANCE_REFERENCE_CONFLICT")
            live = {
                (ref.source_system, ref.invoice_reference): ref
                for ref in self.db.scalars(
                    refs.where(ContractFinanceReference.certificate_id == row.id).order_by(
                        ContractFinanceReference.source_version,
                        ContractFinanceReference.id,
                    )
                )
            }
            live.pop((payload.source_system, payload.invoice_reference), None)
            if sum(item.amount for item in live.values()) + payload.amount > row.net_amount:
                self._error(422, "CONTRACTS_INVOICE_REFERENCES_EXCEED_CERTIFIED_NET")
            values = payload.model_dump(exclude={"reason"})
            reference = self._new(
                ContractFinanceReference,
                workspace,
                certificate_id=row.id,
                certificate_hash=row.source_hash,
                currency=row.currency,
                supersedes_id=previous.id if previous else None,
                **values,
            )
            return self._record(reference, "FINANCE_REFERENCE_RECORDED", payload.reason)

        return self._write("certificate.finance_reference", workspace, payload, key, apply, identity, expected)

    def _notice_for_contract(self, workspace, notice_id, contract_id):
        if notice_id is not None:
            notice = self._get(OperationalContractNotice, workspace, notice_id)
            if notice.contract_id != contract_id:
                self._error(404, "CONTRACTS_NOTICE_NOT_FOUND")
            return notice
        return None

    def create_notice(self, workspace, payload, key):
        self._ready(workspace, "notice.record")

        def apply():
            _, profile = self._ready(workspace, "notice.record")
            self._contract_version(workspace, payload.contract_id)
            self._catalog(profile.content_json, "notice_types", payload.notice_type)
            today = utc_today()
            if (
                payload.issue_date > today
                or payload.received_date
                and not payload.issue_date <= payload.received_date <= today
                or payload.response_due_date
                and payload.response_due_date < payload.issue_date
            ):
                self._error(422, "CONTRACTS_NOTICE_DATE_INVALID")
            values = payload.model_dump(exclude={"document_reference", "reason"}) | {
                "notice_number": self._code(payload.notice_number),
                "document_reference": self._document(workspace, payload.document_reference),
                "status": "RECEIVED" if payload.received_date else "ISSUED",
            }
            row = self._new(
                OperationalContractNotice,
                workspace,
                **values,
                source_hash=_hash(_json(values)),
                **self._profile_pin(profile),
            )
            return self._record(row, "CONTRACT_NOTICE_REGISTERED", payload.reason)

        return self._write("notice.create", workspace, payload, key, apply)

    def notice_action(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "notice.record")

        def apply():
            self._ready(workspace, "notice.record")
            row = self._get(OperationalContractNotice, workspace, identity, lock=True)
            self._version(row.version, expected)
            self._pinned_profile(row)
            self._document_current(workspace, row.document_reference)
            if payload.action == "receive" and row.status == "ISSUED":
                day = payload.received_date or utc_today()
                if not row.issue_date <= day <= utc_today():
                    self._error(422, "CONTRACTS_NOTICE_DATE_INVALID")
                row.received_date, row.status = day, "RECEIVED"
            elif payload.action == "close" and row.status == "RECEIVED" and payload.received_date is None:
                row.status = "CLOSED"
            else:
                self._error(409, "CONTRACTS_NOTICE_TRANSITION_INVALID")
            row.source_hash = _hash(self._out(row, exclude=("source_hash", "version")))
            return self._record(row, f"CONTRACT_NOTICE_{row.status}", payload.reason, changed=True)

        return self._write(f"notice.{payload.action}", workspace, payload, key, apply, identity, expected)

    def create_claim(self, workspace, payload, key):
        self._ready(workspace, "claim.prepare")

        def apply():
            _, profile = self._ready(workspace, "claim.prepare")
            contract, _ = self._contract_version(workspace, payload.contract_id)
            self._catalog(profile.content_json, "claim_types", payload.claim_type)
            self._notice_for_contract(workspace, payload.notice_id, contract.id)
            self._assert_distinct(
                [(ref.document_id, ref.attachment_id) for ref in payload.documents],
                "CONTRACTS_DUPLICATE_CLAIM_DOCUMENT",
            )
            values = payload.model_dump(exclude={"documents", "reason"}) | {
                "claim_number": self._code(payload.claim_number),
                "currency": contract.currency,
                "vendor_id": contract.vendor_id,
                "documents": [self._document(workspace, doc) for doc in payload.documents],
            }
            row = self._new(
                ContractClaim,
                workspace,
                **values,
                source_hash=_hash(_json(values)),
                **self._profile_pin(profile),
            )
            return self._record(row, "CONTRACT_CLAIM_REGISTERED", payload.reason)

        return self._write("claim.create", workspace, payload, key, apply)

    def claim_action(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "claim.decide")

        def apply():
            self._ready(workspace, "claim.decide")
            row = self._get(ContractClaim, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "REGISTERED":
                self._error(409, "CONTRACTS_CLAIM_TRANSITION_INVALID")
            profile = self._pinned_profile(row)
            self._sod(profile, "claim_author_cannot_decide", row.created_by)
            if payload.action == "accept":
                for pin in row.documents:
                    self._document_current(workspace, pin)
            row.status = "ACCEPTED" if payload.action == "accept" else "REJECTED"
            row.decided_by, row.decided_at = self.actor_id, utc_now()
            return self._record(row, f"CONTRACT_CLAIM_{row.status}", payload.reason, changed=True)

        return self._write(f"claim.{payload.action}", workspace, payload, key, apply, identity, expected)

    def _mapping_source(self, workspace, kind, identity):
        source_model = ContractPackage if kind == "CONTRACT_PACKAGE" else OperationalContract
        return self._get(source_model, workspace, identity)

    def _mapping_query(self, workspace, source_kind, source_id):
        return self._scoped(ContractMapping, workspace).where(
            ContractMapping.source_kind == source_kind,
            ContractMapping.source_id == source_id,
        )

    def mapping_history(self, workspace, source_kind, source_id, *, limit=50, after_id=0):
        self._read_project(workspace)
        self._mapping_source(workspace, source_kind, source_id)
        query = self._mapping_query(workspace, source_kind, source_id)
        version = self.db.scalar(query.with_only_columns(func.max(ContractMapping.version))) or 0
        rows = list(
            self.db.scalars(query.where(ContractMapping.id > after_id).order_by(ContractMapping.id).limit(limit + 1))
        )
        return {
            "items": [self._out(row) for row in rows[:limit]],
            "version": version,
            "next_after_id": rows[limit - 1].id if len(rows) > limit else None,
        }

    def record_mapping(self, workspace, payload, expected, key):
        self._ready(workspace, "mapping.edit")

        def apply():
            self._ready(workspace, "mapping.edit")
            self._mapping_source(workspace, payload.source_kind, payload.source_id)
            query = self._mapping_query(workspace, payload.source_kind, payload.source_id)
            actual = self.db.scalar(query.with_only_columns(func.max(ContractMapping.version))) or 0
            self._version(actual, expected)
            previous = self.db.scalar(
                query.where(
                    ContractMapping.target_kind == payload.target_kind,
                    ContractMapping.target_id == payload.target_id,
                )
                .order_by(ContractMapping.version.desc())
                .limit(1)
            )
            if payload.action == "REMOVE":
                if previous is None or previous.action == "REMOVE":
                    self._error(409, "CONTRACTS_MAPPING_NOT_ACTIVE")
                pin = previous.target_snapshot
                if payload.source_hash and pin["source_hash"] != payload.source_hash:
                    self._error(409, "CONTRACTS_MAPPING_PIN_MISMATCH")
            elif payload.target_kind == "PROCUREMENT_PACKAGE":
                target = self._get(ProcurementPackage, workspace, payload.target_id)
                if target.status in {"CANCELLED", "CLOSED"}:
                    self._error(409, "CONTRACTS_PROCUREMENT_PACKAGE_INACTIVE")
                pin = {
                    "target_kind": "PROCUREMENT_PACKAGE",
                    "target_id": target.id,
                    "target_version": target.version,
                    "code": target.package_code,
                    "title": target.title,
                }
                pin["source_hash"] = _hash(pin)
                if payload.source_hash and pin["source_hash"] != payload.source_hash:
                    self._error(409, "CONTRACTS_MAPPING_PIN_MISMATCH")
            else:
                pin = self._target(workspace, payload.model_dump(include={"target_kind", "target_id", "source_hash"}))
            if payload.action == "SET" and previous and previous.action == "SET" and previous.target_snapshot == pin:
                self._error(409, "CONTRACTS_MAPPING_UNCHANGED")
            effective = payload.effective_date or utc_today()
            if previous and effective < previous.effective_date:
                self._error(422, "CONTRACTS_MAPPING_EFFECTIVE_DATE_INVALID")
            values = payload.model_dump(exclude={"reason", "source_hash", "effective_date"})
            values |= {"effective_date": effective, "target_snapshot": pin, "version": actual + 1}
            row = self._new(ContractMapping, workspace, **values, source_hash=_hash(_json(values)))
            return self._record(row, f"CONTRACT_MAPPING_{payload.action}", payload.reason)

        return self._write("mapping.record", workspace, payload, key, apply, payload.source_id, expected)
