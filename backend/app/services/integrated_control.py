from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import (
    WBS,
    Contract,
    ControlAccount,
    ControlAccountFundingAllocation,
    CostBreakdownStructure,
    CostCode,
    FundingSource,
    PaymentCertificate,
    Project,
    PurchaseOrder,
    WarehouseReceipt,
    WorkPackage,
)
from app.domain.schemas import (
    BaselineApprovalOut,
    CloseoutReportOut,
    ForecastFundingReport,
    ForecastFundingRow,
    FundingAvailabilityOut,
    IntegratedControlMatrixRow,
)

INACTIVE_COMMITMENT_STATUSES = {"cancelled", "rejected", "void", "draft"}
ACTIVE_FUNDING_STATUSES = {"approved", "partially_committed", "fully_committed", "planned"}


@dataclass(frozen=True)
class FundingBalance:
    approved_amount: float
    committed: float
    executed: float
    available: float


class IntegratedControlService:
    def __init__(self, db: Session):
        self.db = db

    def require_funding_source(self, tenant_id: int, project_id: int, funding_source_id: int) -> FundingSource:
        funding = self.db.scalar(
            select(FundingSource).where(
                FundingSource.tenant_id == tenant_id,
                FundingSource.project_id == project_id,
                FundingSource.id == funding_source_id,
            )
        )
        if not funding:
            raise HTTPException(status_code=404, detail="FBS funding source not found")
        return funding

    def resolve_commitment_funding(
        self,
        tenant_id: int,
        project_id: int,
        funding_source_id: int | None,
        control_account_id: int | None,
    ) -> FundingSource:
        if funding_source_id is not None:
            return self.require_funding_source(tenant_id, project_id, funding_source_id)

        if control_account_id is not None:
            allocations = list(
                self.db.scalars(
                    select(ControlAccountFundingAllocation).where(
                        ControlAccountFundingAllocation.tenant_id == tenant_id,
                        ControlAccountFundingAllocation.project_id == project_id,
                        ControlAccountFundingAllocation.control_account_id == control_account_id,
                        ControlAccountFundingAllocation.status == "active",
                    )
                ).all()
            )
            if len(allocations) == 1:
                return self.require_funding_source(tenant_id, project_id, allocations[0].funding_source_id)

        active_fbs = list(
            self.db.scalars(
                select(FundingSource)
                .where(
                    FundingSource.tenant_id == tenant_id,
                    FundingSource.project_id == project_id,
                    FundingSource.status.in_(ACTIVE_FUNDING_STATUSES),
                )
                .order_by(FundingSource.code)
            ).all()
        )
        if len(active_fbs) == 1:
            return active_fbs[0]
        raise HTTPException(
            status_code=400,
            detail="An associated FBS funding source is required before creating a commitment",
        )

    def ensure_available(
        self,
        tenant_id: int,
        project_id: int,
        funding: FundingSource,
        requested_amount: float,
        *,
        exclude_contract_id: int | None = None,
        exclude_purchase_order_id: int | None = None,
    ) -> FundingBalance:
        balance = self.refresh_funding_balance(
            tenant_id,
            project_id,
            funding,
            exclude_contract_id=exclude_contract_id,
            exclude_purchase_order_id=exclude_purchase_order_id,
        )
        if requested_amount < 0:
            raise HTTPException(status_code=400, detail="Funding request cannot be negative")
        if requested_amount > balance.available:
            raise HTTPException(status_code=409, detail="Requested commitment exceeds available FBS funding")
        return balance

    def refresh_funding_balance(
        self,
        tenant_id: int,
        project_id: int,
        funding: FundingSource,
        *,
        exclude_contract_id: int | None = None,
        exclude_purchase_order_id: int | None = None,
    ) -> FundingBalance:
        committed = self._committed_amount(
            tenant_id,
            project_id,
            funding.id,
            exclude_contract_id=exclude_contract_id,
            exclude_purchase_order_id=exclude_purchase_order_id,
        )
        executed = self._executed_amount(tenant_id, project_id, funding.id)
        approved = _money(funding.amount)
        available = _money(max(approved - committed - executed, 0))
        funding.funds_committed = committed
        funding.funds_executed = executed
        funding.funds_available = available
        if funding.status != "closed":
            if approved > 0 and available <= 0:
                funding.status = "fully_committed"
            elif committed > 0 or executed > 0:
                funding.status = "partially_committed"
        return FundingBalance(approved_amount=approved, committed=committed, executed=executed, available=available)

    def availability(
        self,
        tenant_id: int,
        project_id: int,
        funding_source_id: int,
        requested_amount: float,
    ) -> FundingAvailabilityOut:
        funding = self.require_funding_source(tenant_id, project_id, funding_source_id)
        balance = self.refresh_funding_balance(tenant_id, project_id, funding)
        return FundingAvailabilityOut(
            project_id=project_id,
            funding_source_id=funding.id,
            fbs_code=funding.code,
            approved_amount=balance.approved_amount,
            funds_available=balance.available,
            funds_committed=balance.committed,
            funds_executed=balance.executed,
            requested_amount=_money(requested_amount),
            is_available=requested_amount <= balance.available,
            status=funding.status,
        )

    def matrix(self, tenant_id: int, project_id: int) -> list[IntegratedControlMatrixRow]:
        project = self.db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        cost_codes = list(
            self.db.scalars(
                select(CostCode)
                .where(CostCode.tenant_id == tenant_id, CostCode.project_id == project_id)
                .order_by(CostCode.code)
            ).all()
        )
        wbs_by_id = _by_id(
            self.db.scalars(select(WBS).where(WBS.tenant_id == tenant_id, WBS.project_id == project_id)).all()
        )
        accounts_by_id = _by_id(
            self.db.scalars(
                select(ControlAccount).where(
                    ControlAccount.tenant_id == tenant_id, ControlAccount.project_id == project_id
                )
            ).all()
        )
        cbs_by_id = _by_id(
            self.db.scalars(
                select(CostBreakdownStructure).where(
                    CostBreakdownStructure.tenant_id == tenant_id,
                    CostBreakdownStructure.project_id == project_id,
                )
            ).all()
        )
        fbs_by_id = _by_id(
            self.db.scalars(
                select(FundingSource).where(
                    FundingSource.tenant_id == tenant_id, FundingSource.project_id == project_id
                )
            ).all()
        )
        packages_by_account: dict[int, WorkPackage] = {}
        for package in self.db.scalars(
            select(WorkPackage).where(WorkPackage.tenant_id == tenant_id, WorkPackage.project_id == project_id)
        ).all():
            if package.control_account_id and package.control_account_id not in packages_by_account:
                packages_by_account[package.control_account_id] = package

        rows: list[IntegratedControlMatrixRow] = []
        for cost_code in cost_codes:
            account = accounts_by_id.get(cost_code.control_account_id)
            package = packages_by_account.get(cost_code.control_account_id)
            fbs = fbs_by_id.get(cost_code.fbs_id)
            wbs = wbs_by_id.get(cost_code.wbs_id)
            cbs = cbs_by_id.get(cost_code.cbs_id)
            balance = _money(
                cost_code.funds_available or ((fbs.funds_available if fbs else 0) - cost_code.actual_costs)
            )
            rows.append(
                IntegratedControlMatrixRow(
                    project_id=project.id,
                    project_code=project.code,
                    project_name=project.name,
                    fbs_code=fbs.code if fbs else "",
                    wbs_code=wbs.code if wbs else "",
                    awp_package_code=package.code if package else "",
                    awp_package_type=package.package_type if package else "",
                    control_account_code=account.code if account else "",
                    cbs_code=cbs.code if cbs else "",
                    cost_code=cost_code.code,
                    contract_ref=cost_code.contract_ref,
                    budget=_money(cost_code.budget),
                    funds_available=_money(cost_code.funds_available),
                    committed=_money(cost_code.commitments),
                    actual=_money(cost_code.actual_costs),
                    forecast=_money(cost_code.forecast),
                    balance=balance,
                    status=cost_code.status,
                )
            )
        return rows

    def forecast_report(self, tenant_id: int, project_id: int) -> ForecastFundingReport:
        rows: list[ForecastFundingRow] = []
        funding_sources = list(
            self.db.scalars(
                select(FundingSource)
                .where(FundingSource.tenant_id == tenant_id, FundingSource.project_id == project_id)
                .order_by(FundingSource.code)
            ).all()
        )
        for funding in funding_sources:
            balance = self.refresh_funding_balance(tenant_id, project_id, funding)
            forecast = _money(
                self.db.scalar(
                    select(func.coalesce(func.sum(CostCode.forecast), 0)).where(
                        CostCode.tenant_id == tenant_id,
                        CostCode.project_id == project_id,
                        CostCode.fbs_id == funding.id,
                    )
                )
                or 0
            )
            rows.append(
                ForecastFundingRow(
                    funding_source_id=funding.id,
                    fbs_code=funding.code,
                    approved_amount=balance.approved_amount,
                    funds_available=balance.available,
                    funds_committed=balance.committed,
                    funds_executed=balance.executed,
                    forecast=forecast,
                    forecast_vs_available=_money(balance.available - forecast),
                    forecast_vs_approved=_money(balance.approved_amount - forecast),
                    status=funding.status,
                )
            )
        return ForecastFundingReport(project_id=project_id, rows=rows)

    def approve_baseline(self, tenant_id: int, project_id: int) -> BaselineApprovalOut:
        project = self.db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        counts = {
            "fbs_count": _count(self.db, FundingSource, tenant_id, project_id),
            "wbs_count": _count(self.db, WBS, tenant_id, project_id),
            "control_account_count": _count(self.db, ControlAccount, tenant_id, project_id),
            "cbs_count": _count(self.db, CostBreakdownStructure, tenant_id, project_id),
            "cost_code_count": _count(self.db, CostCode, tenant_id, project_id),
        }
        missing = [name for name, count in counts.items() if count <= 0]
        if missing:
            raise HTTPException(status_code=409, detail=f"Integrated baseline is incomplete: {', '.join(missing)}")
        project.status = "baseline_approved"
        return BaselineApprovalOut(project_id=project_id, project_status=project.status, **counts)

    def closeout_report(
        self, tenant_id: int, project_id: int, funding_source_id: int | None = None
    ) -> CloseoutReportOut:
        funding_sources = self._target_funding_sources(tenant_id, project_id, funding_source_id)
        approved = committed = actual = forecast = unused = 0.0
        open_commitments = 0
        status = ""
        for funding in funding_sources:
            balance = self.refresh_funding_balance(tenant_id, project_id, funding)
            approved += balance.approved_amount
            committed += balance.committed
            actual += balance.executed
            unused += balance.available
            status = funding.status if len(funding_sources) == 1 else "mixed"
            forecast += _money(
                self.db.scalar(
                    select(func.coalesce(func.sum(CostCode.forecast), 0)).where(
                        CostCode.tenant_id == tenant_id,
                        CostCode.project_id == project_id,
                        CostCode.fbs_id == funding.id,
                    )
                )
                or 0
            )
            open_commitments += self._open_commitment_count(tenant_id, project_id, funding.id)
        return CloseoutReportOut(
            project_id=project_id,
            funding_source_id=funding_source_id,
            approved_amount=_money(approved),
            committed=_money(committed),
            actual=_money(actual),
            forecast=_money(forecast),
            unused_balance=_money(unused),
            open_commitments=open_commitments,
            funding_status=status,
        )

    def financial_closeout(
        self, tenant_id: int, project_id: int, funding_source_id: int | None = None
    ) -> CloseoutReportOut:
        funding_sources = self._target_funding_sources(tenant_id, project_id, funding_source_id)
        closed_commitments = 0
        for funding in funding_sources:
            for contract in self.db.scalars(
                select(Contract).where(
                    Contract.tenant_id == tenant_id,
                    Contract.project_id == project_id,
                    Contract.funding_source_id == funding.id,
                    ~Contract.status.in_(INACTIVE_COMMITMENT_STATUSES | {"closed"}),
                )
            ).all():
                contract.status = "closed"
                closed_commitments += 1
            for order in self.db.scalars(
                select(PurchaseOrder).where(
                    PurchaseOrder.tenant_id == tenant_id,
                    PurchaseOrder.project_id == project_id,
                    PurchaseOrder.funding_source_id == funding.id,
                    ~PurchaseOrder.status.in_(INACTIVE_COMMITMENT_STATUSES | {"closed"}),
                )
            ).all():
                order.status = "closed"
                closed_commitments += 1
            self.refresh_funding_balance(tenant_id, project_id, funding)
            funding.status = "closed"
            funding.funds_available = 0
        report = self.closeout_report(tenant_id, project_id, funding_source_id)
        report.closed_commitments = closed_commitments
        report.open_commitments = 0
        report.funding_status = "closed" if funding_source_id is not None else "mixed"
        return report

    def _target_funding_sources(
        self, tenant_id: int, project_id: int, funding_source_id: int | None
    ) -> list[FundingSource]:
        if funding_source_id is not None:
            return [self.require_funding_source(tenant_id, project_id, funding_source_id)]
        return list(
            self.db.scalars(
                select(FundingSource)
                .where(FundingSource.tenant_id == tenant_id, FundingSource.project_id == project_id)
                .order_by(FundingSource.code)
            ).all()
        )

    def _committed_amount(
        self,
        tenant_id: int,
        project_id: int,
        funding_source_id: int,
        *,
        exclude_contract_id: int | None = None,
        exclude_purchase_order_id: int | None = None,
    ) -> float:
        contract_query = select(func.coalesce(func.sum(Contract.value), 0)).where(
            Contract.tenant_id == tenant_id,
            Contract.project_id == project_id,
            Contract.funding_source_id == funding_source_id,
            ~Contract.status.in_(INACTIVE_COMMITMENT_STATUSES),
        )
        if exclude_contract_id is not None:
            contract_query = contract_query.where(Contract.id != exclude_contract_id)
        purchase_order_query = select(func.coalesce(func.sum(PurchaseOrder.committed_amount), 0)).where(
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.project_id == project_id,
            PurchaseOrder.funding_source_id == funding_source_id,
            ~PurchaseOrder.status.in_(INACTIVE_COMMITMENT_STATUSES),
        )
        if exclude_purchase_order_id is not None:
            purchase_order_query = purchase_order_query.where(PurchaseOrder.id != exclude_purchase_order_id)
        return _money((self.db.scalar(contract_query) or 0) + (self.db.scalar(purchase_order_query) or 0))

    def _executed_amount(self, tenant_id: int, project_id: int, funding_source_id: int) -> float:
        certificate_query = (
            select(func.coalesce(func.sum(PaymentCertificate.certified_amount), 0))
            .join(Contract, PaymentCertificate.contract_id == Contract.id)
            .where(
                PaymentCertificate.tenant_id == tenant_id,
                PaymentCertificate.project_id == project_id,
                Contract.funding_source_id == funding_source_id,
                ~PaymentCertificate.status.in_(INACTIVE_COMMITMENT_STATUSES),
            )
        )
        receipt_query = (
            select(func.coalesce(func.sum(WarehouseReceipt.received_value), 0))
            .outerjoin(PurchaseOrder, WarehouseReceipt.purchase_order_id == PurchaseOrder.id)
            .outerjoin(Contract, WarehouseReceipt.contract_id == Contract.id)
            .where(
                WarehouseReceipt.tenant_id == tenant_id,
                WarehouseReceipt.project_id == project_id,
                (PurchaseOrder.funding_source_id == funding_source_id)
                | (Contract.funding_source_id == funding_source_id),
                ~WarehouseReceipt.status.in_(INACTIVE_COMMITMENT_STATUSES),
            )
        )
        return _money((self.db.scalar(certificate_query) or 0) + (self.db.scalar(receipt_query) or 0))

    def _open_commitment_count(self, tenant_id: int, project_id: int, funding_source_id: int) -> int:
        contract_count = self.db.scalar(
            select(func.count(Contract.id)).where(
                Contract.tenant_id == tenant_id,
                Contract.project_id == project_id,
                Contract.funding_source_id == funding_source_id,
                ~Contract.status.in_(INACTIVE_COMMITMENT_STATUSES | {"closed"}),
            )
        )
        order_count = self.db.scalar(
            select(func.count(PurchaseOrder.id)).where(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.project_id == project_id,
                PurchaseOrder.funding_source_id == funding_source_id,
                ~PurchaseOrder.status.in_(INACTIVE_COMMITMENT_STATUSES | {"closed"}),
            )
        )
        return int((contract_count or 0) + (order_count or 0))


def _count(db: Session, model: type, tenant_id: int, project_id: int) -> int:
    return int(
        db.scalar(select(func.count(model.id)).where(model.tenant_id == tenant_id, model.project_id == project_id)) or 0
    )


def _by_id(rows) -> dict[int, object]:
    return {row.id: row for row in rows}


def _money(value: float) -> float:
    return round(float(value or 0), 2)
