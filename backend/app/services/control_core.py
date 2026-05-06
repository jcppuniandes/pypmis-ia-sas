from sqlalchemy import delete, func, inspect, select
from sqlalchemy.orm import Session

from app.domain.models import Alert, Budget, ControlAccount, ControlPeriod, ControlSnapshot, CostRecord, ForecastScenario, KPI, PaymentCertificate, ProgressRecord
from app.services.early_warning import EarlyWarningService
from app.services.evm import EVMEngine, EVMInput


class ControlCoreService:
    def __init__(self, db: Session):
        self.db = db
        self.evm = EVMEngine()
        self.warning = EarlyWarningService()

    def run_project_cycle(self, tenant_id: int, project_id: int) -> KPI:
        period_label = self._current_period_label(tenant_id, project_id)
        self.db.execute(delete(Alert).where(Alert.tenant_id == tenant_id, Alert.project_id == project_id))
        self.db.execute(
            delete(KPI).where(
                KPI.tenant_id == tenant_id,
                KPI.project_id == project_id,
                KPI.period == period_label,
            )
        )
        self.db.execute(
            delete(ControlSnapshot).where(
                ControlSnapshot.tenant_id == tenant_id,
                ControlSnapshot.project_id == project_id,
                ControlSnapshot.period_label == period_label,
            )
        )
        self.db.execute(
            delete(ForecastScenario).where(
                ForecastScenario.tenant_id == tenant_id,
                ForecastScenario.project_id == project_id,
                ForecastScenario.period_label == period_label,
            )
        )

        accounts = self.db.scalars(
            select(ControlAccount).where(
                ControlAccount.tenant_id == tenant_id,
                ControlAccount.project_id == project_id,
            )
        ).all()

        project_totals = {"pv": 0.0, "ev": 0.0, "ac": 0.0, "bac": 0.0}

        for account in accounts:
            kpi = self._calculate_account(tenant_id, project_id, account, period_label)
            self._store_snapshot(
                tenant_id=tenant_id,
                project_id=project_id,
                control_account_id=account.id,
                period_label=period_label,
                kpi=kpi,
                productivity_index=self._productivity_index(account.id),
            )
            project_totals["pv"] += kpi.pv
            project_totals["ev"] += kpi.ev
            project_totals["ac"] += kpi.ac
            project_totals["bac"] += kpi.bac

        project_result = self.evm.calculate(
            EVMInput(
                bac=project_totals["bac"],
                planned_value=project_totals["pv"],
                earned_percent=(project_totals["ev"] / project_totals["bac"] * 100) if project_totals["bac"] else 0,
                actual_cost=project_totals["ac"],
            )
        )
        project_kpi = KPI(tenant_id=tenant_id, project_id=project_id, control_account_id=None, period=period_label, **project_result.__dict__)
        self.db.add(project_kpi)
        self.db.flush()
        self._store_snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            control_account_id=None,
            period_label=period_label,
            kpi=project_kpi,
            productivity_index=self._project_productivity_index(project_id),
        )
        self._create_forecast_scenarios(tenant_id, project_id, period_label, project_kpi)
        self.db.commit()
        self.db.refresh(project_kpi)
        return project_kpi

    def _calculate_account(self, tenant_id: int, project_id: int, account: ControlAccount, period_label: str) -> KPI:
        budget_row = self.db.execute(
            select(
                func.coalesce(func.sum(Budget.bac), 0),
                func.coalesce(func.sum(Budget.cost_loaded_pv), 0),
            ).where(Budget.control_account_id == account.id)
        ).one()
        bac = float(budget_row[0])
        pv = float(budget_row[1])
        certified_ac = 0.0
        if "payment_certificates" in set(inspect(self.db.get_bind()).get_table_names()):
            certified_ac = float(
                self.db.scalar(
                    select(func.coalesce(func.sum(PaymentCertificate.certified_amount), 0)).where(
                        PaymentCertificate.control_account_id == account.id,
                        ~PaymentCertificate.status.in_(["cancelled", "rejected", "void", "draft"]),
                    )
                )
                or 0
            )
        legacy_ac = float(
            self.db.scalar(
                select(func.coalesce(func.sum(CostRecord.amount), 0)).where(CostRecord.control_account_id == account.id)
            )
            or 0
        )
        ac = certified_ac or legacy_ac
        progress = self.db.scalars(
            select(ProgressRecord)
            .where(ProgressRecord.control_account_id == account.id)
            .order_by(ProgressRecord.reported_on.desc(), ProgressRecord.id.desc())
        ).first()
        earned_percent = progress.physical_percent if progress else 0
        productivity_index = None
        if progress and progress.labor_hours:
            productivity_index = min((progress.quantity_installed / progress.labor_hours) / 0.12, 1.2)

        result = self.evm.calculate(EVMInput(bac=bac, planned_value=pv, earned_percent=earned_percent, actual_cost=ac))
        kpi = KPI(tenant_id=tenant_id, project_id=project_id, control_account_id=account.id, period=period_label, **result.__dict__)
        self.db.add(kpi)
        self.db.flush()

        for alert in self.warning.evaluate(result, productivity_index):
            self.db.add(
                Alert(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    control_account_id=account.id,
                    severity=alert["severity"],
                    rule=alert["rule"],
                    message=alert["message"],
                    recommendation=alert["recommendation"],
                )
            )

        return kpi

    def _store_snapshot(
        self,
        tenant_id: int,
        project_id: int,
        control_account_id: int | None,
        period_label: str,
        kpi: KPI,
        productivity_index: float | None,
    ) -> None:
        period = self.db.scalars(
            select(ControlPeriod)
            .where(
                ControlPeriod.tenant_id == tenant_id,
                ControlPeriod.project_id == project_id,
                ControlPeriod.period_label == period_label,
            )
            .order_by(ControlPeriod.data_date.desc(), ControlPeriod.created_at.desc())
        ).first()
        self.db.add(
            ControlSnapshot(
                tenant_id=tenant_id,
                project_id=project_id,
                control_account_id=control_account_id,
                period_label=period_label,
                data_date=period.data_date if period else None,
                pv=kpi.pv,
                ev=kpi.ev,
                ac=kpi.ac,
                spi=kpi.spi,
                cpi=kpi.cpi,
                sv=kpi.sv,
                cv=kpi.cv,
                bac=kpi.bac,
                eac=kpi.eac,
                etc=kpi.etc,
                vac=kpi.vac,
                productivity_index=productivity_index,
            )
        )

    def _create_forecast_scenarios(self, tenant_id: int, project_id: int, period_label: str, kpi: KPI) -> None:
        current_cpi = kpi.cpi if kpi.cpi > 0 else 1
        current_spi = kpi.spi if kpi.spi > 0 else 1
        scenarios = [
            ("Current Performance", "EAC = BAC / current CPI", current_cpi, current_spi),
            ("Recovery Plan", "EAC assumes corrective action improves CPI by 0.10", min(current_cpi + 0.10, 1.10), min(current_spi + 0.08, 1.05)),
            ("Pessimistic Drift", "EAC assumes unresolved productivity and cost drift", max(current_cpi * 0.90, 0.10), max(current_spi * 0.92, 0.10)),
        ]
        for name, method, cpi_factor, spi_factor in scenarios:
            eac = kpi.bac / cpi_factor if cpi_factor else kpi.bac
            etc = max(eac - kpi.ac, 0)
            vac = kpi.bac - eac
            risk = "high" if cpi_factor < 0.9 or spi_factor < 0.9 else "medium" if cpi_factor < 1 or spi_factor < 1 else "low"
            self.db.add(
                ForecastScenario(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    period_label=period_label,
                    name=name,
                    method=method,
                    cpi_factor=round(cpi_factor, 3),
                    spi_factor=round(spi_factor, 3),
                    eac=round(eac, 2),
                    etc=round(etc, 2),
                    vac=round(vac, 2),
                    completion_risk=risk,
                    summary=f"{name}: EAC {round(eac, 2)}, VAC {round(vac, 2)}, risk {risk}.",
                )
            )

    def _productivity_index(self, control_account_id: int) -> float | None:
        progress = self.db.scalars(
            select(ProgressRecord)
            .where(ProgressRecord.control_account_id == control_account_id)
            .order_by(ProgressRecord.reported_on.desc(), ProgressRecord.id.desc())
        ).first()
        if not progress or not progress.labor_hours:
            return None
        return round(min((progress.quantity_installed / progress.labor_hours) / 0.12, 1.2), 3)

    def _project_productivity_index(self, project_id: int) -> float | None:
        row = self.db.execute(
            select(
                func.coalesce(func.sum(ProgressRecord.quantity_installed), 0),
                func.coalesce(func.sum(ProgressRecord.labor_hours), 0),
            ).where(ProgressRecord.project_id == project_id)
        ).one()
        quantity = float(row[0])
        hours = float(row[1])
        if not hours:
            return None
        return round(min((quantity / hours) / 0.12, 1.2), 3)

    def _current_period_label(self, tenant_id: int, project_id: int) -> str:
        period = self.db.scalars(
            select(ControlPeriod)
            .where(
                ControlPeriod.tenant_id == tenant_id,
                ControlPeriod.project_id == project_id,
                ControlPeriod.status == "open",
            )
            .order_by(ControlPeriod.data_date.desc(), ControlPeriod.created_at.desc())
        ).first()
        return period.period_label if period else "current"
