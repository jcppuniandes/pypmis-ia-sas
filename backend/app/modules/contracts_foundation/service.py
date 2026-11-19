"""Scoped Contracts commands and read-only consumer source resolution."""

from copy import deepcopy
from datetime import UTC, timedelta
from decimal import Decimal
from hmac import compare_digest

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select

from app.core.time import utc_now, utc_today
from app.domain.models import AdminConfiguration, SecurityEvent, UserAccount, WorkspaceModuleSetting
from app.modules.basic_data.service import _hash
from app.modules.contracts_foundation.models import (
    CommercialCommitment,
    ContractHistory,
    ContractPackage,
    ContractVersion,
    OperationalContract,
)
from app.modules.contracts_foundation.permissions import ACTIONS, require_contracts_schema
from app.modules.contracts_foundation.policy import PROFILE_KIND
from app.modules.contracts_foundation.profiles import ContractProfilesMixin
from app.modules.engineering_foundation.integration import EngineeringIntegrationMixin
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.procurement_foundation.consumer_sources import resolve_procurement_source
from app.modules.procurement_foundation.integration import ProcurementIntegrationMixin
from app.modules.procurement_foundation.sourcing_models import ProcurementRFQ, ProcurementVendor
from app.modules.scope_foundation.service import ScopeFoundationService

COLLECTIONS = {
    "packages": ContractPackage,
    "contracts": OperationalContract,
    "versions": ContractVersion,
    "commitments": CommercialCommitment,
    "history": ContractHistory,
}
PROCUREMENT_TYPES = {"PACKAGE", "AWARD", "PO", "PURCHASE_ORDER", "PO_REVISION", "VENDOR"}
CONTRACT_LIVE = {"EXECUTED", "EFFECTIVE"}
VERSION_FIELDS = (
    "tenant_id",
    "project_workspace_id",
    "contract_id",
    "revision",
    "effective_date",
    "value",
    "completion_date",
    "terms_reference",
    "document_reference",
    "supersedes_version_id",
    "source_change_id",
)
COMMITMENT_FIELDS = (
    "tenant_id",
    "project_workspace_id",
    "commitment_code",
    "revision",
    "contract_id",
    "contract_version_id",
    "vendor_id",
    "currency",
    "committed_amount",
    "effective_date",
    "commercial_basis",
    "contract_version_hash",
    "supersedes_id",
    "configuration_id",
    "configuration_hash",
)


def _stamp(value):
    return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.astimezone(UTC).isoformat()


def _material(row, fields):
    payload = {key: getattr(row, key) for key in fields}
    for key, value in payload.items():
        if isinstance(value, Decimal):
            payload[key] = format(value, ".8f")
    return payload


def _version_hash(row):
    return _hash(_material(row, VERSION_FIELDS))


def _commitment_hash(row):
    return _hash(_material(row, COMMITMENT_FIELDS))


def _scoped(model, tenant, workspace):
    return select(model).where(model.tenant_id == tenant, model.project_workspace_id == workspace)


def read_commercial_commitment(db, tenant_id, workspace_id, commitment_id, expected_version=None, expected_hash=None):
    """Typed approved source. The consumer must enforce its own read/write duties."""
    require_contracts_schema(db)
    error = ScopeFoundationService._error
    today = utc_today()
    with db.no_autoflush:

        def load(model, identity):
            row = db.scalar(_scoped(model, tenant_id, workspace_id).where(model.id == identity))
            if row is None:
                error(404, "CONTRACTS_COMMERCIAL_SOURCE_NOT_FOUND")
            return row

        row = load(CommercialCommitment, commitment_id)
        contract = load(OperationalContract, row.contract_id)
        version = load(ContractVersion, row.contract_version_id)
        successor = db.scalar(
            _scoped(CommercialCommitment, tenant_id, workspace_id)
            .where(
                CommercialCommitment.supersedes_id == row.id,
                CommercialCommitment.status == "APPROVED",
                CommercialCommitment.effective_date <= today,
            )
            .limit(1)
        )
        if (
            row.status != "APPROVED"
            or row.approved_at is None
            or successor
            or contract.status not in CONTRACT_LIVE
            or contract.execution_date is None
            or contract.current_version_id != version.id
            or version.contract_id != contract.id
            or version.status != "APPROVED"
        ):
            error(409, "CONTRACTS_COMMERCIAL_SOURCE_NOT_CURRENT")
        profile = db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.id == row.configuration_id,
                AdminConfiguration.tenant_id == tenant_id,
                AdminConfiguration.kind == PROFILE_KIND,
                AdminConfiguration.status == "published",
            )
        )
        if (
            profile is None
            or _hash(profile.content_json) != row.configuration_hash
            or profile.content_hash != row.configuration_hash
            or row.currency != contract.currency
            or row.vendor_id != contract.vendor_id
            or row.configuration_id != contract.configuration_id
            or version.configuration_id != contract.configuration_id
            or row.configuration_hash != contract.configuration_hash
            or version.configuration_hash != contract.configuration_hash
            or row.contract_version_hash != version.source_hash
            or version.source_hash != _version_hash(version)
            or row.source_hash != _commitment_hash(row)
        ):
            error(409, "CONTRACTS_COMMERCIAL_SOURCE_INTEGRITY_INVALID")
        if (
            row.effective_date > today
            or row.effective_date < max(version.effective_date, contract.execution_date)
            or (
                profile.content_json["commitment_policy"]["require_effective_contract"]
                and contract.status != "EFFECTIVE"
            )
        ):
            error(409, "CONTRACTS_COMMERCIAL_SOURCE_NOT_EFFECTIVE")
        if expected_version is not None and expected_version != row.version:
            error(409, "CONTRACTS_COMMERCIAL_SOURCE_VERSION_MISMATCH")
        if expected_hash is not None and not compare_digest(expected_hash, row.source_hash):
            error(409, "CONTRACTS_COMMERCIAL_SOURCE_HASH_MISMATCH")
        return {
            "source_domain": "CONTRACTS",
            "source_entity_type": "COMMERCIAL_COMMITMENT",
            "source_entity_id": row.id,
            "source_version": row.version,
            "source_hash": row.source_hash,
            "observed_at": _stamp(row.approved_at),
            "effective_at": row.effective_date.isoformat(),
            "contract_id": contract.id,
            "contract_version_id": version.id,
            "vendor_id": row.vendor_id,
            "currency": row.currency,
            "committed_amount": format(row.committed_amount, ".8f"),
            "commitment_code": row.commitment_code,
            "revision": row.revision,
            "supersedes_id": row.supersedes_id,
        }


class ContractsService(ContractProfilesMixin, ScopeFoundationService):
    def _require_schema(self):
        if not getattr(self, "_contracts_schema_confirmed", False):
            require_contracts_schema(self.db)
            self._contracts_schema_confirmed = True

    def _project(self, workspace):
        self._require_schema()
        project = super()._project(workspace)
        if project.status.lower() != "active":
            self._error(409, "CONTRACTS_ACTIVE_PROJECT_REQUIRED")
        keys = {"contracts", "contracts-manager"}
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
            self._error(409, "CONTRACTS_MODULE_NOT_ENABLED")
        return project

    def _permission(self, action, workspace=None):
        if self.access_context is None:
            return
        if action not in self._permission_contexts:
            self._permission_contexts[action] = require_enterprise_permission(
                self.db,
                self.tenant_id,
                self.actor_id,
                f"contracts.{action}",
                bootstrap=False,
            )
        context = self._permission_contexts[action]
        if action.startswith("admin.") and not context.organization_wide:
            self._error(403, "CONTRACTS_ORGANIZATION_SCOPE_REQUIRED")
        if workspace is not None:
            self._scope(workspace, context)

    def allowed_actions(self, workspace=None):
        allowed = []
        for action in ACTIONS:
            try:
                self._permission(action, workspace)
                allowed.append(action)
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
        return allowed

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
        profile = self._contracts_profile(project)
        if profile is None:
            self._error(409, "CONTRACTS_PUBLISHED_PROFILE_REQUIRED")
        return project, profile

    def _scoped(self, model, workspace):
        return _scoped(model, self.tenant_id, workspace)

    def _get(self, model, workspace, identity, *, lock=False):
        stmt = self._scoped(model, workspace).where(model.id == identity)
        row = self.db.scalar(stmt.with_for_update().execution_options(populate_existing=True) if lock else stmt)
        if row is None:
            self._error(404, "CONTRACTS_RECORD_NOT_FOUND")
        return row

    def _new(self, model, workspace, **values):
        fields = self._base(workspace)
        if hasattr(model, "updated_by"):
            fields["updated_by"] = self.actor_id
        row = model(**(fields | values))
        self.db.add(row)
        self.db.flush()
        return row

    def _event(self, action, identity, metadata, *, outcome="success"):
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=f"contracts.{action}",
                target_type="ContractsFoundation",
                target_id=identity,
                outcome=outcome,
                metadata_json=deepcopy(metadata),
            )
        )

    def _record(self, row, event, reason, *, changed=False):
        previous = row.version if changed else None
        if changed:
            row.version += 1
            if hasattr(row, "updated_by"):
                row.updated_by, row.updated_at = self.actor_id, utc_now()
        self.db.flush()
        payload = self._out(row)
        self.db.add(
            ContractHistory(
                **self._base(row.project_workspace_id),
                entity_type=type(row).__name__,
                entity_id=row.id,
                entity_version=row.version,
                previous_version=previous,
                event_type=event,
                reason=reason,
                effective_date=getattr(row, "effective_date", None),
                snapshot_json=payload,
            )
        )
        self._event(
            event,
            row.id,
            {
                "project_workspace_id": row.project_workspace_id,
                "entity_type": type(row).__name__,
                "previous_version": previous,
                "version": row.version,
                "reason": reason,
            },
        )
        return payload

    def _write(self, command, workspace, payload, key, apply, identity=None, expected=None):
        self._project(workspace)
        result = self._command(
            f"contracts.{command}",
            key,
            {"project": workspace, "id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )
        return self._redact(workspace, result)

    def configuration(self, workspace):
        project = self._read_project(workspace)
        profile = self._contracts_profile(project)
        return {
            "profile": self._profile_out(profile) if profile else None,
            "allowed_actions": self.allowed_actions(project),
        }

    def resolve_document(self, workspace, document_id, attachment_id, expected_hash=None):
        pin = EngineeringIntegrationMixin._resolve_document(self, workspace, document_id, attachment_id)
        if expected_hash is not None and not compare_digest(expected_hash, pin["sha256"]):
            self._error(409, "CONTRACTS_CDE_HASH_MISMATCH")
        return pin

    def _document(self, workspace, pin):
        return self.resolve_document(workspace, pin.document_id, pin.attachment_id, getattr(pin, "source_hash", None))

    def _check_document(self, workspace, pin):
        if not isinstance(pin, dict) or not {"document_id", "attachment_id", "sha256"} <= pin.keys():
            self._error(409, "CONTRACTS_CDE_REFERENCE_INVALID")
        current = self.resolve_document(workspace, pin["document_id"], pin["attachment_id"], pin["sha256"])
        if current != pin:
            self._error(409, "CONTRACTS_CDE_REFERENCE_STALE")
        return current

    def _redact(self, workspace, value):
        return ProcurementIntegrationMixin._redact(self, workspace, value)

    def document_targets(self, workspace, limit=100, after=0):
        self._read_project(workspace)
        return EngineeringIntegrationMixin.document_targets(self, workspace, limit, after)

    def resolve_reference(self, workspace, reference):
        body = reference.model_dump() if isinstance(reference, BaseModel) else reference
        if body.get("target_kind") not in {
            "CWP",
            "PWP",
            "IWP",
            "CWA",
            "CBS",
            "COST_CODE",
            "CONTROL_ACCOUNT",
            "SCOPE",
            "PLAN",
            "WBS",
            "ACTIVITY",
            "MILESTONE",
        }:
            self._error(422, "CONTRACTS_MAPPING_TARGET_KIND_INVALID")
        pin = ProcurementIntegrationMixin.resolve_reference(self, workspace, body)
        if body.get("target_kind") in {"CWP", "PWP", "IWP", "CWA", "CBS", "COST_CODE", "CONTROL_ACCOUNT"}:
            from app.modules.procurement_foundation.integration import TARGET_MODELS

            target = self._get(TARGET_MODELS[body["target_kind"]], workspace, body["target_id"])
            if getattr(target, "status", "") in {"SUPERSEDED", "CANCELLED", "ARCHIVED", "INACTIVE", "RETIRED", "VOID"}:
                self._error(409, "CONTRACTS_MAPPING_TARGET_INACTIVE")
        return pin

    def resolve_procurement_pin(self, workspace, pin=None, *, source_type=None, source_id=None, package_id=None):
        values = pin.model_dump() if isinstance(pin, BaseModel) else pin
        if values is not None:
            source_type, source_id, package_id = values["source_type"], values["source_id"], values.get("package_id")
        if source_type not in PROCUREMENT_TYPES:
            self._error(422, "CONTRACTS_PROCUREMENT_SOURCE_TYPE_INVALID")
        if source_type == "PURCHASE_ORDER":
            source_type = "PO"
        result = resolve_procurement_source(
            self.db,
            self.tenant_id,
            workspace,
            source_type,
            source_id,
            consumer="CONTRACTS",
            package_id=package_id,
            expected_version=values.get("source_version") if values else None,
            expected_hash=values.get("source_hash") if values else None,
        )
        # Retain verified Procurement provenance but do not expose Cost's mappings here.
        return {key: value for key, value in result.items() if key not in {"cost_mappings", "related_mappings"}}

    def procurement_source(self, workspace, source_type, source_id, package_id):
        self._read_project(workspace)
        return self.resolve_procurement_pin(
            workspace, source_type=source_type, source_id=source_id, package_id=package_id
        )

    def commercial_source(self, workspace, commitment_id, expected_version=None, expected_hash=None):
        self._read_project(workspace)
        return read_commercial_commitment(
            self.db, self.tenant_id, workspace, commitment_id, expected_version, expected_hash
        )

    def _vendor(self, identity):
        row = self.db.scalar(
            select(ProcurementVendor).where(
                ProcurementVendor.tenant_id == self.tenant_id,
                ProcurementVendor.id == identity,
            )
        )
        if row is None:
            self._error(404, "CONTRACTS_COUNTERPARTY_NOT_FOUND")
        if row.status != "ACTIVE":
            self._error(409, "CONTRACTS_COUNTERPARTY_NOT_ACTIVE")
        return {
            "vendor_id": row.id,
            "vendor_code": row.vendor_code,
            "legal_name": row.legal_name,
            "version": row.version,
        }

    def _threshold(self, content, key, value):
        cap = content["approval_thresholds"].get(key)
        if cap is not None and abs(value) > Decimal(cap):
            self._error(409, "CONTRACTS_APPROVAL_THRESHOLD_EXCEEDED")

    def _package_values(self, workspace, payload, profile):
        content = profile.content_json
        if (
            payload.contract_type not in content["contract_types"]
            or payload.commercial_model not in content["commercial_models"]
            or payload.currency not in content["currencies"]
        ):
            self._error(422, "CONTRACTS_PACKAGE_POLICY_INVALID")
        if (
            payload.planned_award_date
            and payload.planned_execution_date
            and payload.planned_award_date > payload.planned_execution_date
        ):
            self._error(422, "CONTRACTS_PACKAGE_DATES_INVALID")
        responsible = payload.responsible_user_id or self.actor_id
        if (
            self.db.scalar(
                select(UserAccount.id).where(
                    UserAccount.tenant_id == self.tenant_id,
                    UserAccount.id == responsible,
                    UserAccount.status == "active",
                )
            )
            is None
        ):
            self._error(404, "CONTRACTS_RESPONSIBLE_NOT_FOUND")
        sources = [self.resolve_procurement_pin(workspace, value) for value in payload.procurement_sources]
        if len({(row["source_type"], row["source_id"], row["package_id"]) for row in sources}) != len(sources):
            self._error(422, "CONTRACTS_PACKAGE_SOURCE_DUPLICATE")
        return payload.model_dump(exclude={"reason", "procurement_sources"}) | {
            "package_code": payload.package_code.upper(),
            "responsible_user_id": responsible,
            "procurement_sources": sources,
            "configuration_id": profile.id,
            "configuration_hash": profile.content_hash,
        }

    def save_package(self, workspace, payload, key, identity=None, expected=None):
        self._ready(workspace, "package.prepare")

        def apply():
            _, profile = self._ready(workspace, "package.prepare")
            values = self._package_values(workspace, payload, profile)
            if identity is None:
                row = self._new(ContractPackage, workspace, **values)
            else:
                row = self._get(ContractPackage, workspace, identity, lock=True)
                self._version(row.version, expected)
                if (
                    row.status != "DRAFT"
                    or self.db.scalar(
                        self._scoped(OperationalContract, workspace)
                        .where(
                            OperationalContract.contract_package_id == row.id,
                        )
                        .limit(1)
                    )
                    is not None
                ):
                    self._error(409, "CONTRACTS_PACKAGE_IMMUTABLE")
                for field, value in values.items():
                    setattr(row, field, value)
            return self._record(
                row, "package.updated" if identity else "package.created", payload.reason, changed=bool(identity)
            )

        return self._write("package.save", workspace, payload, key, apply, identity, expected)

    def transition_package(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "package.prepare")

        def apply():
            self._ready(workspace, "package.prepare")
            row = self._get(ContractPackage, workspace, identity, lock=True)
            self._version(row.version, expected)
            if payload.action == "plan" and row.status == "DRAFT":
                row.status = "PLANNED"
            elif (
                payload.action == "cancel"
                and row.status in {"DRAFT", "PLANNED"}
                and not self.db.scalar(
                    self._scoped(OperationalContract, workspace)
                    .where(OperationalContract.contract_package_id == identity)
                    .limit(1)
                )
            ):
                row.status = "CANCELLED"
            else:
                self._error(409, "CONTRACTS_PACKAGE_TRANSITION_INVALID")
            return self._record(row, f"package.{row.status.lower()}", payload.reason, changed=True)

        return self._write("package.transition", workspace, payload, key, apply, identity, expected)

    def create_contract(self, workspace, payload, key):
        self._ready(workspace, "contract.prepare")

        def apply():
            _, profile = self._ready(workspace, "contract.prepare")
            package = self._get(ContractPackage, workspace, payload.contract_package_id)
            if package.status == "CANCELLED":
                self._error(409, "CONTRACTS_PACKAGE_CANCELLED")
            contract_type = payload.contract_type or package.contract_type
            commercial_model = payload.commercial_model or package.commercial_model
            if (
                contract_type not in profile.content_json["contract_types"]
                or commercial_model not in profile.content_json["commercial_models"]
                or package.currency not in profile.content_json["currencies"]
            ):
                self._error(422, "CONTRACTS_CONTRACT_POLICY_INVALID")
            if not payload.effective_date <= payload.commencement_date <= payload.planned_completion_date:
                self._error(422, "CONTRACTS_CONTRACT_DATES_INVALID")
            vendor = self._vendor(payload.vendor_id)
            source = (
                self.resolve_procurement_pin(workspace, payload.source_instrument) if payload.source_instrument else {}
            )
            self._validate_source_vendor(source, payload.vendor_id, package.currency)
            document = self._document(workspace, payload.document_reference)
            supporting = {
                field: self._document(workspace, pin)
                for field, pin in (
                    ("insurance", payload.insurance_reference),
                    ("bond", payload.bond_reference),
                )
                if pin is not None
            }
            if contract_type == "PURCHASE_ORDER_BASED_AGREEMENT" and source.get("source_type") not in {
                "PO",
                "PO_REVISION",
            }:
                self._error(409, "CONTRACTS_PO_SOURCE_REQUIRED")
            row = self._new(
                OperationalContract,
                workspace,
                contract_number=payload.contract_number.upper(),
                contract_package_id=package.id,
                title=payload.title,
                description=payload.description,
                contract_type=contract_type,
                commercial_model=commercial_model,
                vendor_id=payload.vendor_id,
                counterparty=vendor,
                currency=package.currency,
                original_contract_value=payload.original_contract_value,
                effective_date=payload.effective_date,
                commencement_date=payload.commencement_date,
                planned_completion_date=payload.planned_completion_date,
                governing_reference=payload.governing_reference,
                source_instrument_type="PURCHASE_ORDER"
                if source.get("source_type") == "PO"
                else source.get("source_type"),
                source_instrument_id=source.get("source_id"),
                source_version=source.get("source_version"),
                source_hash=source.get("source_hash"),
                source_reference=source,
                supporting_documents=supporting,
                configuration_id=profile.id,
                configuration_hash=profile.content_hash,
            )
            revision = self._new_version(
                workspace,
                row,
                revision=1,
                effective_date=payload.effective_date,
                value=payload.original_contract_value,
                completion_date=payload.planned_completion_date,
                terms_reference=payload.terms_reference,
                document_reference=document,
            )
            row.current_version_id = revision.id
            self._record(revision, "version.created", payload.reason)
            return self._record(row, "contract.created", payload.reason)

        return self._write("contract.create", workspace, payload, key, apply)

    def _validate_source_vendor(self, pin, vendor_id, currency):
        facts = pin.get("facts", {})
        source_vendor = pin.get("source_id") if pin.get("source_type") == "VENDOR" else facts.get("vendor_id")
        if (source_vendor is not None and source_vendor != vendor_id) or (
            facts.get("currency") is not None and facts["currency"] != currency
        ):
            self._error(409, "CONTRACTS_PROCUREMENT_COUNTERPARTY_OR_CURRENCY_MISMATCH")

    def _new_version(self, workspace, contract, **fields):
        row = ContractVersion(
            **self._base(workspace),
            updated_by=self.actor_id,
            configuration_id=contract.configuration_id,
            configuration_hash=contract.configuration_hash,
            contract_id=contract.id,
            **fields,
        )
        row.source_hash = _version_hash(row)
        self.db.add(row)
        self.db.flush()
        return row

    def transition_contract(self, workspace, identity, payload, expected, key):
        action = f"contract.{payload.action}"
        self._ready(workspace, action)

        def apply():
            self._ready(workspace, action)
            row = self._get(OperationalContract, workspace, identity, lock=True)
            self._version(row.version, expected)
            version = self._get(ContractVersion, workspace, row.current_version_id, lock=True)
            profile = self._pinned_profile(row)
            if version.contract_id != row.id or version.source_hash != _version_hash(version):
                self._error(409, "CONTRACTS_VERSION_INTEGRITY_INVALID")
            if payload.action == "approve" and row.status == version.status == "DRAFT":
                if payload.execution_date or payload.document_reference:
                    self._error(422, "CONTRACTS_APPROVAL_PAYLOAD_INVALID")
                if (
                    profile["separation_of_duties"]["contract_author_cannot_approve"]
                    and row.created_by == self.actor_id
                ):
                    self._error(403, "CONTRACTS_SELF_APPROVAL_FORBIDDEN")
                self._threshold(profile, "contract_approval_limit", version.value)
                self._vendor(row.vendor_id)
                self._check_document(workspace, version.document_reference)
                if row.source_reference:
                    self.resolve_procurement_pin(workspace, row.source_reference)
                version.status, version.approved_by, version.approved_at = "APPROVED", self.actor_id, utc_now()
                row.status = "APPROVED"
                self._record(version, "version.approved", payload.reason, changed=True)
            elif payload.action == "execute" and row.status == version.status == "APPROVED":
                if (
                    profile["separation_of_duties"]["contract_approver_cannot_execute"]
                    and version.approved_by == self.actor_id
                ):
                    self._error(403, "CONTRACTS_EXECUTION_SOD")
                if (
                    payload.document_reference is None
                    or payload.execution_date is None
                    or payload.execution_date > utc_today()
                ):
                    self._error(422, "CONTRACTS_EXECUTION_EVIDENCE_REQUIRED")
                self._vendor(row.vendor_id)
                if row.source_reference:
                    self.resolve_procurement_pin(workspace, row.source_reference)
                row.execution_document = self._document(workspace, payload.document_reference)
                row.execution_date, row.executed_by, row.executed_at = payload.execution_date, self.actor_id, utc_now()
                row.status = "EXECUTED"
            elif payload.action == "effect" and row.status == "EXECUTED" and version.status == "APPROVED":
                if payload.document_reference or payload.execution_date:
                    self._error(422, "CONTRACTS_EFFECTIVE_PAYLOAD_INVALID")
                if version.effective_date > utc_today():
                    self._error(409, "CONTRACTS_EFFECTIVE_DATE_NOT_REACHED")
                self._check_document(workspace, row.execution_document)
                row.status = "EFFECTIVE"
            else:
                self._error(409, "CONTRACTS_CONTRACT_TRANSITION_INVALID")
            return self._record(row, action, payload.reason, changed=True)

        return self._write(action, workspace, payload, key, apply, identity, expected)

    def apply_change_version(
        self, workspace, contract, base, *, value_delta, time_delta, effective_date, document, reason, change_id
    ):
        # This foundation has one current pointer, not a scheduled activation ledger.
        # Keep future changes reviewable without replacing today's approved version.
        if effective_date > utc_today():
            self._error(409, "CONTRACTS_FUTURE_CHANGE_ACTIVATION_UNSUPPORTED")
        if (
            contract.status not in CONTRACT_LIVE
            or contract.current_version_id != base.id
            or base.status != "APPROVED"
            or base.contract_id != contract.id
            or base.source_hash != _version_hash(base)
        ):
            self._error(409, "CONTRACTS_CHANGE_BASE_VERSION_STALE")
        try:
            completion = base.completion_date + timedelta(days=time_delta)
        except OverflowError:
            self._error(422, "CONTRACTS_CHANGE_COMPLETION_INVALID")
        if (
            effective_date < base.effective_date
            or completion < max(effective_date, contract.commencement_date)
            or base.value + value_delta < 0
        ):
            self._error(409, "CONTRACTS_CHANGE_IMPACT_INVALID")
        row = self._new_version(
            workspace,
            contract,
            revision=base.revision + 1,
            effective_date=effective_date,
            value=base.value + value_delta,
            completion_date=completion,
            terms_reference=base.terms_reference,
            document_reference=self._check_document(workspace, document),
            source_change_id=change_id,
            supersedes_version_id=base.id,
            status="APPROVED",
            approved_by=self.actor_id,
            approved_at=utc_now(),
        )
        contract.current_version_id = row.id
        self._record(row, "version.change_order_approved", reason)
        self._record(contract, "contract.version_changed", reason, changed=True)
        return row

    def _commitment_contract(self, workspace, contract_id, version_id, effective):
        contract = self._get(OperationalContract, workspace, contract_id, lock=True)
        version = self._get(ContractVersion, workspace, version_id)
        profile = self._pinned_profile(contract)
        states = {"EFFECTIVE"} if profile["commitment_policy"]["require_effective_contract"] else CONTRACT_LIVE
        if (
            contract.status not in states
            or version.status != "APPROVED"
            or contract.current_version_id != version.id
            or version.contract_id != contract.id
        ):
            self._error(409, "CONTRACTS_CURRENT_EXECUTED_VERSION_REQUIRED")
        if version.source_hash != _version_hash(version):
            self._error(409, "CONTRACTS_VERSION_INTEGRITY_INVALID")
        if effective < max(version.effective_date, contract.execution_date):
            self._error(422, "CONTRACTS_COMMITMENT_EFFECTIVE_DATE_INVALID")
        self._vendor(contract.vendor_id)
        return contract, version, profile

    def create_commitment(self, workspace, payload, key):
        self._ready(workspace, "commitment.prepare")

        def apply():
            self._ready(workspace, "commitment.prepare")
            contract, version, _ = self._commitment_contract(
                workspace,
                payload.contract_id,
                payload.contract_version_id,
                payload.effective_date,
            )
            if payload.committed_amount > version.value:
                self._error(409, "CONTRACTS_COMMITMENT_EXCEEDS_CONTRACT")
            code, revision = payload.commitment_code.upper(), 1
            if payload.supersedes_id:
                old = self._get(CommercialCommitment, workspace, payload.supersedes_id, lock=True)
                if (
                    old.status != "APPROVED"
                    or old.contract_id != contract.id
                    or old.commitment_code != code
                    or payload.effective_date < old.effective_date
                    or old.source_hash != _commitment_hash(old)
                    or self.db.scalar(
                        self._scoped(CommercialCommitment, workspace)
                        .where(
                            CommercialCommitment.supersedes_id == old.id,
                        )
                        .limit(1)
                    )
                ):
                    self._error(409, "CONTRACTS_COMMITMENT_SUCCESSOR_INVALID")
                revision = old.revision + 1
            row = CommercialCommitment(
                **self._base(workspace),
                updated_by=self.actor_id,
                commitment_code=code,
                revision=revision,
                contract_id=contract.id,
                contract_version_id=version.id,
                vendor_id=contract.vendor_id,
                currency=contract.currency,
                committed_amount=payload.committed_amount,
                effective_date=payload.effective_date,
                commercial_basis=payload.commercial_basis,
                contract_version_hash=version.source_hash,
                supersedes_id=payload.supersedes_id,
                configuration_id=contract.configuration_id,
                configuration_hash=contract.configuration_hash,
            )
            row.source_hash = _commitment_hash(row)
            self.db.add(row)
            self.db.flush()
            return self._record(row, "commitment.created", payload.reason)

        return self._write("commitment.create", workspace, payload, key, apply)

    def approve_commitment(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "commitment.approve")

        def apply():
            self._ready(workspace, "commitment.approve")
            row = self._get(CommercialCommitment, workspace, identity, lock=True)
            self._version(row.version, expected)
            _, version, profile = self._commitment_contract(
                workspace, row.contract_id, row.contract_version_id, row.effective_date
            )
            if (
                row.status != "DRAFT"
                or row.source_hash != _commitment_hash(row)
                or row.contract_version_hash != version.source_hash
            ):
                self._error(409, "CONTRACTS_COMMITMENT_NOT_APPROVABLE")
            if profile["separation_of_duties"]["commitment_author_cannot_approve"] and row.created_by == self.actor_id:
                self._error(403, "CONTRACTS_COMMITMENT_SELF_APPROVAL_FORBIDDEN")
            self._threshold(profile, "commitment_approval_limit", row.committed_amount)
            others = self._current_commitments(workspace, row.contract_id)
            total = sum((item.committed_amount for item in others if item.id != row.supersedes_id), Decimal(0))
            if total + row.committed_amount > version.value:
                self._error(409, "CONTRACTS_COMMITMENT_EXCEEDS_CONTRACT")
            row.status, row.approved_by, row.approved_at = "APPROVED", self.actor_id, utc_now()
            return self._record(row, "commitment.approved", payload.reason, changed=True)

        return self._write("commitment.approve", workspace, payload, key, apply, identity, expected)

    def _current_commitments(self, workspace, contract_id, *, effective_as_of=None):
        model = CommercialCommitment
        statement = self._scoped(model, workspace).where(model.contract_id == contract_id, model.status == "APPROVED")
        if effective_as_of is not None:
            statement = statement.where(model.effective_date <= effective_as_of)
        rows = list(self.db.scalars(statement))
        superseded = {row.supersedes_id for row in rows}
        return [row for row in rows if row.id not in superseded]

    def collection(
        self, workspace, collection, *, limit=50, after_id=0, contract_id=None, entity_type=None, entity_id=None
    ):
        self._read_project(workspace)
        model = COLLECTIONS[collection]
        stmt = self._scoped(model, workspace).where(model.id > after_id)
        if contract_id is not None and model in {ContractVersion, CommercialCommitment}:
            stmt = stmt.where(model.contract_id == contract_id)
        if model is ContractHistory:
            if entity_type:
                stmt = stmt.where(model.entity_type == entity_type)
            if entity_id:
                stmt = stmt.where(model.entity_id == entity_id)
        rows = list(self.db.scalars(stmt.order_by(model.id).limit(limit + 1)))
        return self._redact(
            workspace,
            {
                "items": [self._out(row) for row in rows[:limit]],
                "next_after_id": rows[limit - 1].id if len(rows) > limit else None,
            },
        )

    def detail(self, workspace, collection, identity):
        self._read_project(workspace)
        row = self._get(COLLECTIONS[collection], workspace, identity)
        result = self._out(row)
        if collection == "contracts":
            result["current_version"] = self._out(self._get(ContractVersion, workspace, row.current_version_id))
        return self._redact(workspace, result)

    def _reference_valid(self, resolve, *args):
        try:
            resolve(*args)
        except HTTPException as exc:
            if exc.status_code not in {403, 404, 409, 422}:
                raise
            return False
        return True

    def readiness(self, workspace, contract_id):
        from app.modules.contracts_foundation.commercial_models import ContractSOV, OperationalContractNotice

        self._read_project(workspace)
        contract = self._get(OperationalContract, workspace, contract_id)
        version = self._get(ContractVersion, workspace, contract.current_version_id)
        requirements = self._pinned_profile(contract)["readiness_requirements"]
        checks = []

        def check(code, valid, *, evidence=None, missing="MISSING", required=True):
            checks.append(
                {
                    "code": code,
                    "status": "READY" if valid else missing,
                    "required": required,
                    "evidence": evidence or {},
                }
            )

        now = utc_today()
        executed = contract.status in CONTRACT_LIVE and contract.execution_date is not None
        check("CONTRACT_EXECUTION", executed, evidence={"status": contract.status})
        effective = contract.status == "EFFECTIVE" and executed and version.effective_date <= now
        check(
            "CONTRACT_EFFECTIVENESS",
            effective,
            evidence={"effective_date": version.effective_date.isoformat()},
            missing="NOT_EFFECTIVE",
        )
        check(
            "CURRENT_VERSION",
            version.contract_id == contract.id
            and version.status == "APPROVED"
            and version.source_hash == _version_hash(version),
            evidence={"id": version.id, "revision": version.revision, "source_hash": version.source_hash},
            missing="NOT_APPROVED_OR_STALE",
        )
        check(
            "COUNTERPARTY",
            self._reference_valid(self._vendor, contract.vendor_id),
            evidence={"vendor_id": contract.vendor_id},
            missing="BROKEN_REFERENCE",
        )
        for code, reference, required in (
            ("GOVERNING_CDE", version.document_reference, True),
            ("EXECUTION_CDE", contract.execution_document, True),
            ("INSURANCE", contract.supporting_documents.get("insurance"), requirements["insurance"]),
            ("BOND", contract.supporting_documents.get("bond"), requirements["bond"]),
        ):
            check(
                code,
                bool(reference) and self._reference_valid(self._check_document, workspace, reference),
                evidence=reference,
                missing="BROKEN_REFERENCE" if reference else "MISSING",
                required=required,
            )
        if contract.source_reference:
            check(
                "PROCUREMENT_SOURCE",
                self._reference_valid(self.resolve_procurement_pin, workspace, contract.source_reference),
                evidence=contract.source_reference,
                missing="STALE",
            )

        commitments = self._current_commitments(workspace, contract.id, effective_as_of=now)
        valid_commitments = [
            row
            for row in commitments
            if self._reference_valid(
                read_commercial_commitment,
                self.db,
                self.tenant_id,
                workspace,
                row.id,
            )
        ]
        check(
            "COMMERCIAL_COMMITMENT",
            bool(valid_commitments),
            required=requirements["commitment"],
            missing="STALE" if commitments else "MISSING",
            evidence={
                "items": [
                    {"id": row.id, "source_hash": row.source_hash, "contract_version_id": row.contract_version_id}
                    for row in commitments
                ]
            },
        )
        sovs = list(
            self.db.scalars(
                self._scoped(ContractSOV, workspace)
                .where(
                    ContractSOV.contract_id == contract.id,
                    ContractSOV.status == "PUBLISHED",
                )
                .order_by(ContractSOV.id.desc())
                .limit(200)
            )
        )
        check(
            "SOV",
            any(row.contract_version_id == version.id for row in sovs),
            required=requirements["sov"],
            missing="STALE" if sovs else "MISSING",
            evidence={
                "items": [
                    {"id": row.id, "source_hash": row.source_hash, "contract_version_id": row.contract_version_id}
                    for row in sovs
                ]
            },
        )
        notice = self.db.scalar(
            self._scoped(OperationalContractNotice, workspace)
            .where(
                OperationalContractNotice.contract_id == contract.id,
            )
            .order_by(OperationalContractNotice.id.desc())
            .limit(1)
        )
        check(
            "NOTICE",
            notice is not None and self._reference_valid(self._check_document, workspace, notice.document_reference),
            required=requirements["notice"],
            missing="BROKEN_REFERENCE" if notice else "MISSING",
            evidence={"id": notice.id, "source_hash": notice.source_hash} if notice else None,
        )

        blockers = [row for row in checks if row["required"] and row["status"] != "READY"]
        failure_states = {row["status"] for row in blockers}
        if not executed:
            state = "NOT_READY"
        elif "BROKEN_REFERENCE" in failure_states:
            state = "BROKEN_REFERENCE"
        elif failure_states.intersection({"STALE", "NOT_APPROVED_OR_STALE"}):
            state = "STALE"
        else:
            state = "PARTIALLY_READY" if blockers else "READY"
        return self._redact(
            workspace,
            {
                "contract_id": contract.id,
                "contract_version_id": version.id,
                "readiness_status": state,
                "as_of": now.isoformat(),
                "reason_codes": [f"{row['code']}_{row['status']}" for row in blockers],
                "checks": checks,
                "decision_authority": "CONTRACTS_ADVISORY_ONLY",
            },
        )

    def lookahead(self, workspace, horizon_days, as_of=None, status=None, contract_id=None):
        from app.modules.contracts_foundation.commercial_models import (
            ContractChange,
            ContractClaim,
            OperationalContractNotice,
            OperationalPaymentCertificate,
            PaymentApplication,
        )

        self._read_project(workspace)
        if contract_id is not None:
            self._get(OperationalContract, workspace, contract_id)
        as_of = as_of or utc_today()
        try:
            cutoff = as_of + timedelta(days=horizon_days)
        except OverflowError:
            self._error(422, "CONTRACTS_LOOKAHEAD_WINDOW_INVALID")
        status = status.strip().upper() if status else None
        items = []

        def queue(model, kind, due, title, filters, *, owner=None):
            statement = (
                self._scoped(model, workspace).add_columns(due, title).where(due.is_not(None), due <= cutoff, *filters)
            )
            if owner is not None:
                if contract_id is not None:
                    statement = statement.where(owner == contract_id)
            elif contract_id is not None and model is OperationalContract:
                statement = statement.where(model.id == contract_id)
            if status == "OVERDUE":
                statement = statement.where(due < as_of)
            elif status == "UPCOMING":
                statement = statement.where(due >= as_of)
            elif status:
                statement = statement.where(model.status == status)
            for row, date_value, title_value in self.db.execute(statement.order_by(due, model.id).limit(201)):
                items.append(
                    {
                        "event_type": kind,
                        "id": row.id,
                        "source_version": row.version,
                        "source_hash": getattr(row, "source_hash", None),
                        "title": title_value,
                        "contract_id": getattr(row, owner.key)
                        if owner is not None
                        else row.id
                        if model is OperationalContract
                        else None,
                        "due_date": date_value.isoformat(),
                        "status": row.status,
                        "timing": "OVERDUE" if date_value < as_of else "UPCOMING",
                    }
                )

        if contract_id is None:
            queue(
                ContractPackage,
                "PLANNED_AWARD",
                ContractPackage.planned_award_date,
                ContractPackage.title,
                [
                    ContractPackage.status.in_(("DRAFT", "PLANNED")),
                ],
            )
        queue(
            OperationalContract,
            "CONTRACT_EXECUTION",
            ContractPackage.planned_execution_date,
            OperationalContract.title,
            [
                ContractPackage.tenant_id == self.tenant_id,
                ContractPackage.project_workspace_id == workspace,
                ContractPackage.id == OperationalContract.contract_package_id,
                OperationalContract.status.in_(("DRAFT", "APPROVED")),
            ],
        )
        queue(
            OperationalContract,
            "CONTRACT_EFFECTIVE_DATE",
            OperationalContract.effective_date,
            OperationalContract.title,
            [
                OperationalContract.status == "EXECUTED",
            ],
        )
        queue(
            ContractVersion,
            "CONTRACT_COMPLETION",
            ContractVersion.completion_date,
            OperationalContract.title,
            [
                OperationalContract.tenant_id == self.tenant_id,
                OperationalContract.project_workspace_id == workspace,
                OperationalContract.current_version_id == ContractVersion.id,
                OperationalContract.status.in_(CONTRACT_LIVE),
            ],
            owner=ContractVersion.contract_id,
        )
        queue(
            CommercialCommitment,
            "COMMITMENT_APPROVAL",
            CommercialCommitment.effective_date,
            CommercialCommitment.commitment_code,
            [
                CommercialCommitment.status == "DRAFT",
            ],
            owner=CommercialCommitment.contract_id,
        )
        queue(
            ContractChange,
            "CHANGE_ORDER",
            ContractChange.effective_date,
            ContractChange.change_number,
            [
                ContractChange.status.in_(("POTENTIAL", "REQUESTED", "UNDER_REVIEW")),
            ],
            owner=ContractChange.contract_id,
        )
        queue(
            PaymentApplication,
            "PAYMENT_APPLICATION",
            PaymentApplication.effective_date,
            PaymentApplication.application_number,
            [
                PaymentApplication.status == "SUBMITTED",
            ],
            owner=PaymentApplication.contract_id,
        )
        queue(
            OperationalPaymentCertificate,
            "PAYMENT_CERTIFICATE",
            OperationalPaymentCertificate.effective_date,
            OperationalPaymentCertificate.certificate_number,
            [OperationalPaymentCertificate.status == "DRAFT"],
            owner=OperationalPaymentCertificate.contract_id,
        )
        queue(
            OperationalContractNotice,
            "NOTICE_RESPONSE",
            OperationalContractNotice.response_due_date,
            OperationalContractNotice.subject,
            [
                OperationalContractNotice.status.in_(("ISSUED", "RECEIVED")),
            ],
            owner=OperationalContractNotice.contract_id,
        )
        queue(
            ContractClaim,
            "CLAIM_REVIEW",
            ContractClaim.effective_date,
            ContractClaim.claim_number,
            [
                ContractClaim.status == "REGISTERED",
            ],
            owner=ContractClaim.contract_id,
        )
        items.sort(key=lambda row: (row["due_date"], row["event_type"], row["id"]))
        return {
            "as_of": as_of.isoformat(),
            "through": cutoff.isoformat(),
            "horizon_days": horizon_days,
            "items": items[:200],
            "truncated": len(items) > 200,
            "next_after_id": None,
        }

    def _commercial_signals(self, workspace, contract, version):
        from app.modules.contracts_foundation.commercial_models import ContractChange

        pending = ContractChange.status.in_(("POTENTIAL", "REQUESTED", "UNDER_REVIEW"))
        pending_total = self.db.scalar(
            self._scoped(ContractChange, workspace)
            .with_only_columns(func.sum(ContractChange.value_delta))
            .where(ContractChange.contract_id == contract.id, pending)
        ) or Decimal(0)
        current = sum(
            (
                row.committed_amount
                for row in self._current_commitments(workspace, contract.id, effective_as_of=utc_today())
                if self._reference_valid(read_commercial_commitment, self.db, self.tenant_id, workspace, row.id)
            ),
            Decimal(0),
        )
        return {
            "currency": contract.currency,
            "contract_version_id": version.id,
            "original_contract_value": format(contract.original_contract_value, ".8f"),
            "current_contract_value": format(version.value, ".8f"),
            "approved_changes": format(version.value - contract.original_contract_value, ".8f"),
            "pending_change_net": format(pending_total, ".8f"),
            "current_commercial_commitments": format(current, ".8f"),
            "potential_commercial_exposure": format(version.value + pending_total, ".8f"),
            "decision_authority": "COMMERCIAL_INFORMATION_ONLY_NOT_COST_EAC",
        }

    def _procurement_chain(self, workspace, pins):
        chains = []
        for pin in pins:
            chain = {"origin": pin, "current": False}
            chains.append(chain)
            try:
                source = self.resolve_procurement_pin(workspace, pin)
                chain["current"] = True
                facts = source["facts"]
                award = source if source["source_type"] == "AWARD" else None
                if facts.get("award_id"):
                    award = self.resolve_procurement_pin(
                        workspace,
                        source_type="AWARD",
                        source_id=facts["award_id"],
                        package_id=source["package_id"],
                    )
                chain["package"] = self.resolve_procurement_pin(
                    workspace,
                    source_type="PACKAGE",
                    source_id=source["package_id"],
                    package_id=source["package_id"],
                )
                if source["source_type"] in {"PO", "PO_REVISION"}:
                    chain["purchase_order"] = source
                if award:
                    chain["award"] = award
                    rfq = self._get(ProcurementRFQ, workspace, award["facts"]["rfq_id"])
                    chain["rfq"] = self._out(
                        rfq, exclude=("commercial_terms_reference", "technical_package_reference", "document_reference")
                    )
            except HTTPException as exc:
                if exc.status_code not in {403, 404, 409, 422}:
                    raise
                chain["current"] = False
        return chains

    def trace(self, workspace, contract_id):
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
        from app.modules.contracts_foundation.cost_consumer_models import CostCommercialAdoption

        project = self._read_project(workspace)
        contract = self._get(OperationalContract, workspace, contract_id)
        package = self._get(ContractPackage, workspace, contract.contract_package_id)
        current_version = self._get(ContractVersion, workspace, contract.current_version_id)
        pins = package.procurement_sources + ([contract.source_reference] if contract.source_reference else [])
        truncated = []

        def rows(key, model, *filters):
            found = list(self.db.scalars(self._scoped(model, workspace).where(*filters).order_by(model.id).limit(201)))
            if len(found) > 200:
                truncated.append(key)
            return found[:200]

        versions = rows("versions", ContractVersion, ContractVersion.contract_id == contract_id)
        commitments = rows("commitments", CommercialCommitment, CommercialCommitment.contract_id == contract_id)
        sovs = rows("sovs", ContractSOV, ContractSOV.contract_id == contract_id)
        applications = rows("applications", PaymentApplication, PaymentApplication.contract_id == contract_id)
        certificates = rows(
            "certificates", OperationalPaymentCertificate, OperationalPaymentCertificate.contract_id == contract_id
        )
        mappings = rows(
            "mappings",
            ContractMapping,
            or_(
                and_(ContractMapping.source_kind == "CONTRACT", ContractMapping.source_id == contract_id),
                and_(ContractMapping.source_kind == "CONTRACT_PACKAGE", ContractMapping.source_id == package.id),
            ),
        )
        payload = {
            "contract": self._out(contract),
            "package": self._out(package),
            "contract_id": contract.id,
            "procurement_references": pins,
            "versions": versions,
            "commitments": commitments,
            "sovs": sovs,
            "mappings": mappings,
            "sov_lines": rows("sov_lines", ContractSOVLine, ContractSOVLine.sov_id.in_([row.id for row in sovs])),
            "applications": applications,
            "application_lines": rows(
                "application_lines",
                PaymentApplicationLine,
                PaymentApplicationLine.application_id.in_([row.id for row in applications]),
            ),
            "certificates": certificates,
            "certificate_lines": rows(
                "certificate_lines",
                PaymentCertificateLine,
                PaymentCertificateLine.certificate_id.in_([row.id for row in certificates]),
            ),
            "finance_references": rows(
                "finance_references",
                ContractFinanceReference,
                ContractFinanceReference.certificate_id.in_([row.id for row in certificates]),
            ),
            "changes": rows("changes", ContractChange, ContractChange.contract_id == contract_id),
            "notices": rows("notices", OperationalContractNotice, OperationalContractNotice.contract_id == contract_id),
            "claims": rows("claims", ContractClaim, ContractClaim.contract_id == contract_id),
        }
        try:
            context = require_enterprise_permission(
                self.db, self.tenant_id, self.actor_id, "cost.read", bootstrap=False
            )
            self._scope(project, context)
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
        else:
            payload["cost_adoptions"] = rows(
                "cost_adoptions",
                CostCommercialAdoption,
                CostCommercialAdoption.source_entity_id.in_([row.id for row in commitments]),
            )
        return self._redact(
            workspace,
            {
                **{
                    key: [self._out(row) for row in value]
                    if isinstance(value, list) and key != "procurement_references"
                    else value
                    for key, value in payload.items()
                },
                "procurement_chain": self._procurement_chain(workspace, pins),
                "commercial_signals": self._commercial_signals(workspace, contract, current_version),
                "truncated_collections": truncated,
                "decision_authority": "READ_ONLY_TRACE",
            },
        )
