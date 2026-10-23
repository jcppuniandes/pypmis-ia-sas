"""Governed Cost recognition, FX and obligation projections.

No method awards/amends a Contract, writes a PO, recognizes a ledger posting,
executes payment or changes Funding. Obligation amounts remain source-owned.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.core.time import utc_now
from app.domain.models import Contract, FundingSource, PurchaseOrder
from app.modules.basic_data.service import _hash
from app.modules.cost_foundation.financial_models import CostActualEntry, CostCommitmentReference, CostFXRate
from app.modules.cost_foundation.models import (
    BudgetLine,
    BudgetVersion,
    ControlAccount,
    CostBaseline,
    CostCBS,
    CostCode,
)
from app.modules.cost_foundation.service import CostFoundationService
from app.modules.operational_context.models import OperationalProjectBinding, ProjectControlsPeriod

FINANCIAL_ACTIONS = (
    "fx.edit",
    "fx.publish",
    "actual.import",
    "actual.approve",
    "actual.adjust",
    "commitment.reconcile",
    "commitment.verify",
)
ZERO = Decimal("0")
QUANTUM = Decimal("0.00000001")
APPROVED_LEGACY_SOURCE_STATES = {
    "active",
    "issued",
    "approved",
    "awarded",
    "signed",
    "closed",
    "executing",
    "completed",
}
EXTERNAL_APPROVED_STATES = {"APPROVED", "AWARDED", "ISSUED", "ACTIVE", "SIGNED", "CLOSED"}


def money(value):
    return Decimal(str(value)).quantize(QUANTUM)


def fx_date_is_effective(effective_from, effective_to, conversion_date):
    """Cost monetary effective dates use the same half-open interval as APU/Rate."""
    return effective_from <= conversion_date and (effective_to is None or conversion_date < effective_to)


def actual_history_balanced(original_amount, original_date, adjustments):
    """A valid current balance cannot conceal a negative historical/as-of balance."""
    by_date = defaultdict(lambda: ZERO)
    by_date[str(original_date)] += money(original_amount)
    for row in adjustments:
        by_date[str(row["recognition_date"])] += money(row["amount"])
    balance = ZERO
    for recognized_on in sorted(by_date):
        balance += by_date[recognized_on]
        if balance < ZERO:
            return False
    return True


def effective_obligation_rows(rows):
    """A proposed refresh never hides a verified source; only its verified successor does."""
    superseded = {
        row.get("supersedes_id") for row in rows if row.get("status") == "VERIFIED" and row.get("supersedes_id")
    }
    return [
        {
            **row,
            "source_status": row.get("source_status", row["status"]),
            "status": "SUPERSEDED_PROJECTION" if row.get("id") in superseded else row["status"],
        }
        for row in rows
    ]


def reconcile_obligations(rows):
    """Pure economic-origin reconciliation; no currency conversion or source mutation."""
    rows = effective_obligation_rows(rows)
    contributors, results, issues = {}, [], []
    verified = [row for row in rows if row.get("status") == "VERIFIED"]
    for row in verified:
        mode, origin = row["inclusion_mode"], row["economic_origin"]
        if mode == "ADDITIVE":
            if origin in contributors:
                issues.append({"code": "DUPLICATE_ECONOMIC_ORIGIN", "origin": origin})
            else:
                contributors[origin] = row
    totals = defaultdict(lambda: ZERO)
    for row in rows:
        contribution, decision = ZERO, "UNVERIFIED_SOURCE"
        mode = row["inclusion_mode"]
        if row.get("status") == "VERIFIED":
            if mode == "REFERENCE_ONLY":
                decision = "REFERENCE_ONLY"
            elif mode in {"INCLUDED", "CALL_OFF"}:
                parent = contributors.get(row.get("parent_economic_origin"))
                if parent is None:
                    decision = "MISSING_ECONOMIC_PARENT"
                    issues.append({"code": decision, "id": row.get("id")})
                elif parent["currency"] != row["currency"]:
                    decision = "PARENT_CURRENCY_MISMATCH"
                    issues.append({"code": decision, "id": row.get("id")})
                elif money(row["amount"]) > money(parent["amount"]):
                    decision = "INCLUDED_AMOUNT_EXCEEDS_PARENT"
                    issues.append({"code": decision, "id": row.get("id")})
                else:
                    decision = "ALREADY_INCLUDED_IN_PARENT"
            elif mode == "ADDITIVE":
                decision = "ADDITIVE_ONCE"
                if contributors.get(row["economic_origin"]) is row:
                    contribution = money(row["amount"])
                    totals[row["currency"]] += contribution
                else:
                    decision = "DUPLICATE_ECONOMIC_ORIGIN"
        results.append({**row, "net_contribution": str(contribution), "reconciliation_decision": decision})
    # A contract ceiling cannot be silently consumed more than once by call-offs.
    children = defaultdict(lambda: ZERO)
    for row in verified:
        if row["inclusion_mode"] == "CALL_OFF":
            children[row.get("parent_economic_origin")] += money(row["amount"])
    for origin, amount in children.items():
        if origin in contributors and amount > money(contributors[origin]["amount"]):
            issues.append({"code": "CALL_OFF_EXCEEDS_PARENT", "origin": origin})
    currencies = sorted(totals)
    state = "RECONCILIATION_REQUIRED" if issues else "NO_AGGREGATION" if len(currencies) > 1 else "RECONCILED"
    return {
        "status": state,
        "items": results,
        "issues": issues,
        "by_currency": {key: str(value) for key, value in sorted(totals.items())},
        "net_commitment": str(totals[currencies[0]]) if len(currencies) == 1 and not issues else None,
        "currency": currencies[0] if len(currencies) == 1 and not issues else None,
        "authority": "READ_MODEL_NOT_CONTRACTUAL_AUTHORITY",
        "gross_not_outstanding": True,
    }


def aggregate_original_money(rows):
    totals = defaultdict(lambda: ZERO)
    for row in rows:
        totals[row["currency"]] += money(row["amount"])
    currencies = sorted(totals)
    return {
        "status": "NO_AGGREGATION" if len(currencies) > 1 else "AGGREGATED" if currencies else "EMPTY",
        "amount": str(totals[currencies[0]]) if len(currencies) == 1 else "0.00000000" if not currencies else None,
        "currency": currencies[0] if len(currencies) == 1 else None,
        "by_currency": {key: str(value) for key, value in sorted(totals.items())},
    }


class CostFinancialService(CostFoundationService):
    def _currency(self, currency, profile):
        allowed = profile.content_json.get("currencies", ["USD", "COP", "EUR"])
        if currency not in allowed or currency != currency.upper():
            self._error(422, "COST_CURRENCY_NOT_GOVERNED")

    def _dimensions(self, workspace, payload):
        for field, model in (("cbs_id", CostCBS), ("cost_code_id", CostCode), ("control_account_id", ControlAccount)):
            identity = getattr(payload, field, None)
            if identity is not None and self._get(model, workspace, identity).status != "ACTIVE":
                self._error(409, "COST_MAPPING_TARGET_INACTIVE")

    def _period_open(self, workspace, period_id, recognized_on):
        period = self.db.scalar(
            select(ProjectControlsPeriod)
            .where(
                ProjectControlsPeriod.tenant_id == self.tenant_id,
                ProjectControlsPeriod.project_workspace_id == workspace,
                ProjectControlsPeriod.id == period_id,
            )
            .with_for_update()
        )
        if period is None:
            self._error(404, "COST_PROJECT_CONTROLS_PERIOD_NOT_FOUND")
        if period.status != "OPEN":
            self._error(409, "COST_PERIOD_NOT_OPEN")
        if not period.period_start <= recognized_on <= period.period_end:
            self._error(422, "COST_RECOGNITION_OUTSIDE_PERIOD")
        return period

    def fx_rates(self, workspace):
        self._permission("read", self._project(workspace))
        return {"items": [self._out(row) for row in self._rows(CostFXRate, workspace)]}

    def create_fx(self, workspace, payload, key):
        self._ready(workspace, "fx.edit")

        def apply():
            _, profile = self._ready(workspace, "fx.edit")
            self._currency(payload.from_currency, profile)
            self._currency(payload.to_currency, profile)
            if not profile.content_json.get("fx_policy", {}).get("allow_conversion", False):
                self._error(409, "COST_FX_CONVERSION_DISABLED_BY_POLICY")
            if payload.from_currency == payload.to_currency or (
                payload.effective_to and payload.effective_to <= payload.effective_from
            ):
                self._error(422, "COST_FX_BASIS_INVALID")
            revision = 1
            if payload.supersedes_id:
                old = self._get(CostFXRate, workspace, payload.supersedes_id)
                if old.code != payload.code or old.status != "PUBLISHED":
                    self._error(409, "COST_FX_SUCCESSOR_REQUIRES_PUBLISHED_SAME_CODE")
                revision = old.revision + 1
            values = payload.model_dump(exclude={"reason"})
            row = CostFXRate(
                **self._base(workspace),
                updated_by=self.actor_id,
                revision=revision,
                content_hash=_hash(payload.model_dump(mode="json", exclude={"reason"})),
                **values,
            )
            self.db.add(row)
            return self._record(row, "FX_RATE_CREATED", payload.reason)

        return self._write("fx.create", workspace, payload, key, apply)

    def publish_fx(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "fx.publish")

        def apply():
            _, profile = self._ready(workspace, "fx.publish")
            row = self._get(CostFXRate, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "DRAFT":
                self._error(409, "COST_FX_NOT_DRAFT")
            if row.created_by == self.actor_id:
                self._error(403, "COST_FX_PUBLISHER_MUST_BE_INDEPENDENT")
            self._currency(row.from_currency, profile)
            self._currency(row.to_currency, profile)
            if not profile.content_json["fx_policy"]["allow_conversion"]:
                self._error(409, "COST_FX_CONVERSION_DISABLED_BY_POLICY")
            row.status, row.published_by, row.published_at = "PUBLISHED", self.actor_id, utc_now()
            return self._record(row, "FX_RATE_PUBLISHED", payload.reason, changed=True)

        return self._write("fx.publish", workspace, payload, key, apply, identity, expected)

    def convert_value(self, workspace, amount, currency, target_currency, conversion_date, fx_rate_id=None):
        """Explicit direct conversion only; no inferred inverse, current rate or fallback."""
        original = {"amount": str(money(amount)), "currency": currency}
        if currency == target_currency:
            return {
                **original,
                "converted_amount": str(money(amount)),
                "target_currency": currency,
                "conversion_date": str(conversion_date),
                "exchange_rate_basis": "IDENTITY",
                "fx_rate_id": None,
                "source": "SAME_CURRENCY",
            }
        if fx_rate_id is None:
            self._error(409, "NO_AGGREGATION")
        row = self._get(CostFXRate, workspace, fx_rate_id)
        if row.status != "PUBLISHED" or row.from_currency != currency or row.to_currency != target_currency:
            self._error(409, "COST_PUBLISHED_DIRECT_FX_REQUIRED")
        if not fx_date_is_effective(row.effective_from, row.effective_to, conversion_date):
            self._error(422, "COST_FX_DATE_OUTSIDE_EFFECTIVE_RANGE")
        return {
            **original,
            "converted_amount": str(money(money(amount) * row.rate)),
            "target_currency": target_currency,
            "conversion_date": str(conversion_date),
            "exchange_rate_basis": row.conversion_basis,
            "fx_rate_id": row.id,
            "fx_revision": row.revision,
            "fx_hash": row.content_hash,
            "exchange_rate": str(row.rate),
            "source": row.source_reference,
        }

    def actuals(self, workspace, target_currency=None, as_of=None):
        self._permission("read", self._project(workspace))
        items = [self._out(row) for row in self._rows(CostActualEntry, workspace)]
        recognized = [
            row
            for row in items
            if row["status"] == "RECOGNIZED" and (as_of is None or date.fromisoformat(row["recognition_date"]) <= as_of)
        ]
        totals = aggregate_original_money(recognized)
        if target_currency:
            profile = self._cost_profile(self._project(workspace))
            if profile is None:
                self._error(409, "PUBLISHED_COST_PROFILE_REQUIRED")
            self._currency(target_currency, profile)
            conversions = [
                self.convert_value(
                    workspace,
                    row["amount"],
                    row["currency"],
                    target_currency,
                    date.fromisoformat(row["recognition_date"]),
                    row["fx_rate_id"],
                )
                for row in recognized
            ]
            totals = {
                "status": "AGGREGATED_WITH_EXPLICIT_FX",
                "amount": str(sum((money(row["converted_amount"]) for row in conversions), ZERO)),
                "currency": target_currency,
                "conversions": conversions,
                "by_currency": totals["by_currency"],
            }
        return {
            "items": items,
            "recognized": totals,
            "accruals_included": False,
            "authority": "COST_RECOGNITION_NOT_ACCOUNTING_LEDGER",
        }

    def import_actual(self, workspace, payload, key, adjusts_id=None):
        action = "actual.adjust" if adjusts_id else "actual.import"
        self._ready(workspace, action)

        def apply():
            _, profile = self._ready(workspace, action)
            self._currency(payload.currency, profile)
            self._dimensions(workspace, payload)
            if not any((payload.cbs_id, payload.cost_code_id, payload.control_account_id)):
                self._error(422, "COST_ACTUAL_COST_MAPPING_REQUIRED")
            self._period_open(workspace, payload.period_id, payload.recognition_date)
            source_types = profile.content_json.get(
                "actual_source_types",
                ["CONTROLLED_MANUAL", "ACCOUNTING_IMPORT", "ERP_INTERFACE", "APPROVED_INVOICE_RECOGNITION"],
            )
            if payload.source_type not in source_types:
                self._error(422, "COST_ACTUAL_SOURCE_TYPE_NOT_GOVERNED")
            if payload.amount == 0:
                self._error(422, "COST_ACTUAL_ZERO_ADJUSTMENT")
            if adjusts_id:
                parent = self._get(CostActualEntry, workspace, adjusts_id)
                if (
                    parent.status != "RECOGNIZED"
                    or parent.entry_kind != "ORIGINAL"
                    or parent.currency != payload.currency
                ):
                    self._error(409, "COST_ACTUAL_ADJUSTMENT_SOURCE_INVALID")
                if payload.recognition_date < parent.recognition_date:
                    self._error(422, "COST_ACTUAL_ADJUSTMENT_PREDATES_ORIGINAL")
            if payload.fx_rate_id:
                fx = self._get(CostFXRate, workspace, payload.fx_rate_id)
                if fx.from_currency != payload.currency:
                    self._error(409, "COST_PUBLISHED_DIRECT_FX_REQUIRED")
                self.convert_value(
                    workspace, payload.amount, payload.currency, fx.to_currency, payload.recognition_date, fx.id
                )
            row = CostActualEntry(
                **self._base(workspace),
                updated_by=self.actor_id,
                entry_kind="ADJUSTMENT" if adjusts_id else "ORIGINAL",
                adjusts_entry_id=adjusts_id,
                **payload.model_dump(exclude={"reason"}),
            )
            self.db.add(row)
            return self._record(row, "ACTUAL_ADJUSTMENT_PROPOSED" if adjusts_id else "ACTUAL_IMPORTED", payload.reason)

        return self._write(
            "actual.adjust" if adjusts_id else "actual.import", workspace, payload, key, apply, adjusts_id
        )

    def decide_actual(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "actual.approve")

        def apply():
            _, profile = self._ready(workspace, "actual.approve")
            row = self._get(CostActualEntry, workspace, identity, lock=True)
            self._version(row.version, expected)
            self._period_open(workspace, row.period_id, row.recognition_date)
            if row.status != "IMPORTED":
                self._error(409, "COST_ACTUAL_NOT_IMPORTED")
            if row.created_by == self.actor_id:
                self._error(403, "COST_ACTUAL_APPROVER_MUST_BE_INDEPENDENT")
            if payload.status == "RECOGNIZED":
                self._currency(row.currency, profile)
                self._dimensions(workspace, row)
                if row.source_type not in profile.content_json["actual_source_types"]:
                    self._error(422, "COST_ACTUAL_SOURCE_TYPE_NOT_GOVERNED")
                if row.fx_rate_id:
                    fx = self._get(CostFXRate, workspace, row.fx_rate_id)
                    if fx.from_currency != row.currency:
                        self._error(409, "COST_PUBLISHED_DIRECT_FX_REQUIRED")
                    self.convert_value(workspace, row.amount, row.currency, fx.to_currency, row.recognition_date, fx.id)
            if row.adjusts_entry_id and payload.status == "RECOGNIZED":
                parent = self._get(CostActualEntry, workspace, row.adjusts_entry_id, lock=True)
                recognized_deltas = self.db.scalars(
                    select(CostActualEntry).where(
                        CostActualEntry.tenant_id == self.tenant_id,
                        CostActualEntry.project_workspace_id == workspace,
                        CostActualEntry.adjusts_entry_id == parent.id,
                        CostActualEntry.status == "RECOGNIZED",
                    )
                ).all()
                if not actual_history_balanced(
                    parent.amount,
                    parent.recognition_date,
                    [self._out(item) for item in recognized_deltas] + [self._out(row)],
                ):
                    self._error(409, "COST_ACTUAL_ADJUSTMENT_EXCEEDS_RECOGNIZED_AMOUNT")
            row.status, row.approved_by, row.approved_at = payload.status, self.actor_id, utc_now()
            return self._record(
                row,
                "ACTUAL_ADJUSTED"
                if row.adjusts_entry_id and row.status == "RECOGNIZED"
                else "ACTUAL_RECOGNIZED"
                if row.status == "RECOGNIZED"
                else "ACTUAL_REJECTED",
                payload.reason,
                changed=True,
            )

        return self._write("actual.decision", workspace, payload, key, apply, identity, expected)

    def _legacy_project(self, workspace):
        bindings = self.db.scalars(
            select(OperationalProjectBinding).where(
                OperationalProjectBinding.tenant_id == self.tenant_id,
                OperationalProjectBinding.project_workspace_id == workspace,
                OperationalProjectBinding.status == "ACTIVE",
            )
        ).all()
        if len(bindings) != 1:
            self._error(409, "COST_VERIFIED_LEGACY_BINDING_REQUIRED")
        return bindings[0].legacy_project_id

    def legacy_sources(self, workspace):
        self._permission("read", self._project(workspace))
        project_id = self._legacy_project(workspace)
        items = []
        for model, kind in ((Contract, "CONTRACT"), (PurchaseOrder, "PO")):
            for row in self.db.scalars(
                select(model).where(model.tenant_id == self.tenant_id, model.project_id == project_id)
            ):
                source_kind = (
                    "SUBCONTRACT" if kind == "CONTRACT" and row.contract_type.upper() == "SUBCONTRACT" else kind
                )
                snapshot = self._source_snapshot(row, source_kind)
                funding = (
                    self.db.scalar(
                        select(FundingSource).where(
                            FundingSource.tenant_id == self.tenant_id,
                            FundingSource.project_id == project_id,
                            FundingSource.id == row.funding_source_id,
                        )
                    )
                    if row.funding_source_id
                    else None
                )
                items.append(
                    {
                        "source_system": "LEGACY",
                        "source_type": source_kind,
                        "source_record_id": row.id,
                        "source_reference": snapshot["source_reference"],
                        "source_revision": snapshot["source_revision"],
                        "source_hash": _hash(snapshot),
                        "source_approval_status": row.status,
                        "amount": snapshot["amount"],
                        "currency": None,
                        "currency_basis_required": True,
                        "funding_currency_reference": funding.currency if funding else None,
                        "linked_contract_id": getattr(row, "contract_id", None),
                    }
                )
        return {
            "items": items,
            "authority": "LEGACY_CONTRACT_PROCUREMENT_READ_ONLY",
            "currency_policy": "EXPLICIT_RECONCILIATION_REQUIRED_NO_USD_DEFAULT",
        }

    @staticmethod
    def _source_snapshot(row, kind):
        snapshot = {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "project_id": row.project_id,
            "source_type": kind,
            "source_reference": row.po_number if kind == "PO" else row.code,
            "amount": str(money(row.committed_amount if kind == "PO" else row.value)),
            "status": row.status,
            "contract_id": getattr(row, "contract_id", None),
            "funding_source_id": row.funding_source_id,
        }
        snapshot["source_revision"] = str(row.version) if hasattr(row, "version") else f"HASH:{_hash(snapshot)[:40]}"
        return snapshot

    def _validate_obligation_source(self, workspace, row):
        if row.source_system == "LEGACY":
            model = PurchaseOrder if row.source_type == "PO" else Contract
            if row.source_type == "CONTRACT_CHANGE_ORDER" or not row.source_record_id:
                self._error(422, "COST_LEGACY_LEGAL_SOURCE_UNSUPPORTED")
            source = self.db.scalar(
                select(model).where(
                    model.tenant_id == self.tenant_id,
                    model.project_id == self._legacy_project(workspace),
                    model.id == row.source_record_id,
                )
            )
            if source is None:
                self._error(404, "COST_OBLIGATION_SOURCE_NOT_FOUND")
            if row.source_type != "PO":
                expected_kind = "SUBCONTRACT" if source.contract_type.upper() == "SUBCONTRACT" else "CONTRACT"
                if row.source_type != expected_kind:
                    self._error(422, "COST_SUBCONTRACT_SOURCE_TYPE_MISMATCH")
            snapshot = self._source_snapshot(source, row.source_type)
            if (
                row.source_hash != _hash(snapshot)
                or row.source_reference != snapshot["source_reference"]
                or row.source_revision != snapshot["source_revision"]
                or money(row.amount) != money(snapshot["amount"])
            ):
                self._error(409, "COST_OBLIGATION_SOURCE_STALE_OR_AMOUNT_MISMATCH")
            if (
                source.status.lower() not in APPROVED_LEGACY_SOURCE_STATES
                or row.source_approval_status.lower() != source.status.lower()
            ):
                self._error(409, "COST_OBLIGATION_SOURCE_NOT_APPROVED")
            if row.source_type == "PO" and row.inclusion_mode in {"INCLUDED", "CALL_OFF"}:
                parents = [
                    item
                    for item in effective_obligation_rows(
                        [self._out(item) for item in self._rows(CostCommitmentReference, workspace)]
                    )
                    if item["economic_origin"] == row.parent_economic_origin
                    and item["inclusion_mode"] == "ADDITIVE"
                    and item["status"] == "VERIFIED"
                ]
                parent = parents[0] if len(parents) == 1 else None
                if (
                    parent is None
                    or parent["source_system"] != "LEGACY"
                    or parent["source_type"] not in {"CONTRACT", "SUBCONTRACT"}
                    or source.contract_id != parent["source_record_id"]
                ):
                    self._error(409, "COST_PO_ECONOMIC_PARENT_SOURCE_MISMATCH")
        elif row.source_approval_status.upper() not in EXTERNAL_APPROVED_STATES or row.source_record_id is not None:
            self._error(422, "COST_VERIFIED_EXTERNAL_APPROVAL_REFERENCE_REQUIRED")

    def propose_commitment(self, workspace, payload, key):
        self._ready(workspace, "commitment.reconcile")

        def apply():
            _, profile = self._ready(workspace, "commitment.reconcile")
            self._currency(payload.currency, profile)
            self._dimensions(workspace, payload)
            if payload.inclusion_mode not in profile.content_json["commitment_inclusion_modes"]:
                self._error(422, "COST_COMMITMENT_INCLUSION_MODE_DISABLED")
            if payload.inclusion_mode in {"INCLUDED", "CALL_OFF"} and not payload.parent_economic_origin:
                self._error(422, "COST_INCLUDED_OBLIGATION_PARENT_REQUIRED")
            all_rows = list(self._rows(CostCommitmentReference, workspace))
            identity = (payload.source_system, payload.source_type, payload.source_reference)
            same_source = [
                item
                for item in all_rows
                if (item.source_system, item.source_type, item.source_reference) == identity
                and item.status != "REJECTED"
            ]
            ancestors, revision = set(), 1
            if payload.supersedes_id:
                old = self._get(CostCommitmentReference, workspace, payload.supersedes_id, lock=True)
                if (
                    old.status != "VERIFIED"
                    or (old.source_system, old.source_type, old.source_reference) != identity
                    or old.economic_origin != payload.economic_origin
                    or old.inclusion_mode != payload.inclusion_mode
                    or old.parent_economic_origin != payload.parent_economic_origin
                ):
                    self._error(409, "COST_COMMITMENT_REFRESH_SOURCE_MISMATCH")
                if old.source_hash == payload.source_hash or old.source_revision == payload.source_revision:
                    self._error(409, "COST_COMMITMENT_REFRESH_CHANGED_SOURCE_REQUIRED")
                if any(item.supersedes_id == old.id and item.status != "REJECTED" for item in all_rows):
                    self._error(409, "COST_COMMITMENT_REFRESH_BRANCH_FORBIDDEN")
                ancestor = old
                while ancestor:
                    ancestors.add(ancestor.id)
                    ancestor = next((item for item in all_rows if item.id == ancestor.supersedes_id), None)
                revision = old.revision + 1
            elif same_source:
                self._error(409, "COST_COMMITMENT_SOURCE_SUCCESSOR_REQUIRED")
            if payload.inclusion_mode == "ADDITIVE":
                if any(
                    item.economic_origin == payload.economic_origin
                    and item.inclusion_mode == "ADDITIVE"
                    and item.status != "REJECTED"
                    and item.id not in ancestors
                    for item in all_rows
                ):
                    self._error(409, "COST_DUPLICATE_ECONOMIC_ORIGIN")
            row = CostCommitmentReference(
                **self._base(workspace),
                updated_by=self.actor_id,
                revision=revision,
                **payload.model_dump(exclude={"reason"}),
            )
            self._validate_obligation_source(workspace, row)
            if payload.fx_rate_id:
                fx = self._get(CostFXRate, workspace, payload.fx_rate_id)
                if fx.from_currency != payload.currency:
                    self._error(409, "COST_PUBLISHED_DIRECT_FX_REQUIRED")
                self.convert_value(
                    workspace, payload.amount, payload.currency, fx.to_currency, payload.effective_date, fx.id
                )
            self.db.add(row)
            return self._record(row, "COMMITMENT_REFERENCE_PROPOSED", payload.reason)

        return self._write("commitment.propose", workspace, payload, key, apply)

    def verify_commitment(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "commitment.verify")

        def apply():
            _, profile = self._ready(workspace, "commitment.verify")
            row = self._get(CostCommitmentReference, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "PROPOSED":
                self._error(409, "COST_OBLIGATION_NOT_PROPOSED")
            if row.created_by == self.actor_id:
                self._error(403, "COST_OBLIGATION_VERIFIER_MUST_BE_INDEPENDENT")
            if payload.status == "VERIFIED":
                self._currency(row.currency, profile)
                self._dimensions(workspace, row)
                if row.inclusion_mode not in profile.content_json["commitment_inclusion_modes"]:
                    self._error(422, "COST_COMMITMENT_INCLUSION_MODE_DISABLED")
                self._validate_obligation_source(workspace, row)
                candidates = [self._out(item) for item in self._rows(CostCommitmentReference, workspace)]
                for item in candidates:
                    if item["id"] == row.id:
                        item["status"] = "VERIFIED"
                effective = effective_obligation_rows(candidates)
                for candidate in effective:
                    if candidate["status"] == "VERIFIED":
                        self._validate_obligation_source(
                            workspace, self._get(CostCommitmentReference, workspace, candidate["id"])
                        )
                if reconcile_obligations(candidates)["issues"]:
                    self._error(409, "COST_OBLIGATION_RECONCILIATION_REQUIRED")
            row.status, row.verified_by, row.verified_at = payload.status, self.actor_id, utc_now()
            return self._record(
                row,
                "COMMITMENT_REFERENCE_VERIFIED" if payload.status == "VERIFIED" else "COMMITMENT_REFERENCE_REJECTED",
                payload.reason,
                changed=True,
            )

        return self._write("commitment.verify", workspace, payload, key, apply, identity, expected)

    def commitments(self, workspace, target_currency=None):
        self._permission("read", self._project(workspace))
        items, stale = [], []
        all_rows = list(self._rows(CostCommitmentReference, workspace))
        for item in effective_obligation_rows([self._out(row) for row in all_rows]):
            row = next(row for row in all_rows if row.id == item["id"])
            if item["status"] == "VERIFIED":
                try:
                    self._validate_obligation_source(workspace, row)
                except HTTPException as error:
                    item["status"] = "SOURCE_STALE"
                    stale.append({"id": row.id, "code": error.detail})
            items.append(item)
        result = reconcile_obligations(items)
        if stale:
            result["issues"] += stale
            result.update(status="RECONCILIATION_REQUIRED", net_commitment=None, currency=None)
        if target_currency and not result["issues"]:
            profile = self._cost_profile(self._project(workspace))
            if profile is None:
                self._error(409, "PUBLISHED_COST_PROFILE_REQUIRED")
            self._currency(target_currency, profile)
            conversions = [
                self.convert_value(
                    workspace,
                    item["net_contribution"],
                    item["currency"],
                    target_currency,
                    date.fromisoformat(item["effective_date"]),
                    item["fx_rate_id"],
                )
                for item in result["items"]
                if item["status"] == "VERIFIED" and money(item["net_contribution"]) != 0
            ]
            result.update(
                status="RECONCILED_WITH_EXPLICIT_FX",
                net_commitment=str(sum((money(item["converted_amount"]) for item in conversions), ZERO)),
                currency=target_currency,
                conversions=conversions,
            )
        return result

    def accrual_contract(self, workspace):
        self._permission("read", self._project(workspace))
        return {
            "status": "DEFERRED_WITH_CONTRACT",
            "functional": False,
            "authority": "ESTIMATED_INCURRED_NOT_RECOGNIZED",
            "interface": {
                "source_system": "required",
                "source_reference": "required_unique",
                "project_workspace_id": workspace,
                "period_id": "required",
                "amount": "decimal",
                "currency": "required",
                "cost_mapping": "required",
                "reversal_reference": "required_on_reversal",
                "replacement_actual_id": "required_on_replacement",
            },
            "double_counting_policy": "ACCRUALS_EXCLUDED_FROM_RECOGNIZED_ACTUAL_AND_EAC; future replacement must atomically reverse accrual and recognize Actual",
            "mutations_available": [],
        }

    def financial_overview(self, workspace):
        self._permission("read", self._project(workspace))
        budgets = [row for row in self._rows(BudgetVersion, workspace) if row.status == "APPROVED"]
        original = min(budgets, key=lambda row: row.id) if budgets else None
        superseded = {row.predecessor_id for row in budgets if row.predecessor_id}
        candidates = [row for row in budgets if row.id not in superseded]
        current = candidates[0] if len(candidates) == 1 else None

        def budget_total(version):
            if version is None:
                return {"status": "NOT_AVAILABLE", "amount": None, "currency": None, "by_currency": {}}
            return aggregate_original_money(
                [
                    self._out(row)
                    for row in self._rows(BudgetLine, workspace)
                    if version and row.budget_version_id == version.id and row.cost_class != "MANAGEMENT_RESERVE"
                ]
            )

        return {
            "original_budget": budget_total(original),
            "current_budget": budget_total(current),
            "current_budget_id": current.id if current else None,
            "current_budget_selection": "UNAMBIGUOUS_APPROVED_SUCCESSOR"
            if current
            else "AMBIGUOUS_CURRENT_BUDGET"
            if candidates
            else "NO_APPROVED_BUDGET",
            "management_reserve": {
                "inside_control_baseline": False,
                "not_added_to_baseline": True,
                "amounts": aggregate_original_money(
                    [
                        self._out(row)
                        for row in self._rows(BudgetLine, workspace)
                        if current and row.budget_version_id == current.id and row.cost_class == "MANAGEMENT_RESERVE"
                    ]
                ),
            },
            "actual": self.actuals(workspace)["recognized"],
            "commitments": self.commitments(workspace),
            "etc": {
                "status": "INTERFACE_READY_NOT_FORECAST_AUTHORITY",
                "accepted_reference_required": True,
                "methods": [
                    "BOTTOM_UP",
                    "QUANTITY_RATE",
                    "COMMITMENT_BASED",
                    "PRODUCTIVITY_BASED",
                    "STATISTICAL",
                    "MANUAL",
                ],
            },
            "eac": {
                "status": "AWAITING_ACCEPTED_ETC_REFERENCE",
                "formula": "RECOGNIZED_ACTUAL + ACCEPTED_ETC",
                "commitments_additional_term": False,
            },
            "accrual": self.accrual_contract(workspace),
            "earned_value": "DEFERRED_O1B_D",
            "model_dimension": "4D_NOT_5D",
            "treasury": False,
        }

    def eac_preview(self, workspace, payload):
        self._permission("read", self._project(workspace))
        _, profile = self._ready(workspace, "read")
        self._currency(payload.currency, profile)
        if payload.method not in profile.content_json["etc_methods"]:
            self._error(422, "COST_ETC_METHOD_NOT_GOVERNED")
        actual = self.actuals(workspace, payload.currency, payload.as_of)["recognized"]
        return {
            "status": "REFERENCE_CALCULATION_ONLY",
            "actual": actual,
            "etc_amount": str(payload.etc_amount),
            "eac_amount": str(money(Decimal(actual["amount"]) + payload.etc_amount)),
            "currency": payload.currency,
            "method": payload.method,
            "acceptance_reference": payload.acceptance_reference,
            "as_of": str(payload.as_of),
            "includes_commitments": payload.includes_commitments,
            "commitment_added_separately": False,
            "forecast_approval_created": False,
        }

    def cash_flow(self, workspace):
        self._permission("read", self._project(workspace))
        approved = [row for row in self._rows(CostBaseline, workspace) if row.status == "APPROVED"]
        original = min(approved, key=lambda row: row.id) if approved else None
        superseded = {row.previous_baseline_id for row in approved if row.previous_baseline_id}
        candidates = [row for row in approved if row.id not in superseded]
        current = candidates[0] if len(candidates) == 1 else None
        phases = [row for baseline in approved for row in self._effective_phasing(workspace, baseline.id)]
        actuals = [row for row in self._rows(CostActualEntry, workspace) if row.status == "RECOGNIZED"]
        commitment_reconciliation = self.commitments(workspace)
        periods = self.db.scalars(
            select(ProjectControlsPeriod)
            .where(
                ProjectControlsPeriod.tenant_id == self.tenant_id,
                ProjectControlsPeriod.project_workspace_id == workspace,
            )
            .order_by(ProjectControlsPeriod.period_start, ProjectControlsPeriod.revision)
        ).all()
        items = []
        for period in periods:

            def spread_total(baseline, period=period):
                if baseline is None:
                    return {"status": "NOT_AVAILABLE", "amount": None, "currency": None, "by_currency": {}}
                by_currency = []
                for row in phases:
                    if baseline and row.baseline_id == baseline.id:
                        for spread in row.spread_json:
                            day = spread.get("date") or spread.get("period_date")
                            if day and period.period_start <= date.fromisoformat(day) <= period.period_end:
                                by_currency.append({"amount": spread["amount"], "currency": row.currency})
                return aggregate_original_money(by_currency)

            items.append(
                {
                    "period_id": period.id,
                    "period_code": period.period_code,
                    "period_revision": period.revision,
                    "period_status": period.status,
                    "planned": spread_total(original),
                    "current": spread_total(current),
                    "actual": aggregate_original_money(
                        [self._out(row) for row in actuals if row.period_id == period.id]
                    ),
                    "commitment": {
                        **aggregate_original_money(
                            [
                                {"amount": row["net_contribution"], "currency": row["currency"]}
                                for row in commitment_reconciliation["items"]
                                if row["status"] == "VERIFIED"
                                and money(row["net_contribution"]) != 0
                                and period.period_start
                                <= date.fromisoformat(row["effective_date"])
                                <= period.period_end
                            ]
                        ),
                        "basis": "OBLIGATION_EFFECTIVE_DATE_NOT_PAYMENT",
                        "not_added_to_actual": True,
                        "reconciliation_status": commitment_reconciliation["status"],
                    },
                    "forecast_reference": None,
                }
            )
            if commitment_reconciliation["issues"]:
                items[-1]["commitment"].update(status="RECONCILIATION_REQUIRED", amount=None, currency=None)
        return {
            "items": items,
            "authority": "COST_PHASING_NOT_TREASURY",
            "payment_forecast": False,
            "commitment_reconciliation": commitment_reconciliation,
        }
