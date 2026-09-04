"""Gate 07M-FIN orchestration and deterministic calculation services."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, AdminNumberSequence, EnterpriseWorkspace, SecurityEvent
from app.modules.business_case.models import BusinessCase, BusinessCaseRevision
from app.modules.economic_financial_model.engine import (
    ENGINE_VERSION,
    FinancialFormulaError,
    benefit_cost_ratio,
    decimal,
    dscr,
    irr,
    llcr,
    moic,
    npv,
    payback_period,
    wacc,
)
from app.modules.economic_financial_model.models import (
    EconomicFinancialModel,
    EconomicFinancialModelVersion,
    FinancialModelAssumption,
    FinancialModelCashFlow,
    FinancialModelDebtSchedule,
    FinancialModelFinancingInstrument,
    FinancialModelInvestor,
    FinancialModelMetricResult,
    FinancialModelPeriod,
    FinancialModelScenario,
    FinancialModelScenarioOverride,
    FinancialModelSensitivityResult,
)
from app.modules.economic_financial_model.schemas import (
    ConfigurationPreviewOut,
    ModelOut,
    ModelVersionOut,
    ProviderEvidenceOut,
    ReadinessOut,
    RefreshPreviewOut,
)
from app.modules.funds_manager.models import Fund, FundingAssignment, FundingReadinessSnapshot
from app.modules.funds_manager.service import FundsManagerService
from app.modules.portfolio_budget.models import PortfolioBudgetScenario, PortfolioBudgetScenarioProject

CONFIGURATION_KIND = "economic_financial_model_configuration"
READY_OUTPUT = "READY_FOR_GOVERNED_ECONOMIC_FINANCIAL_EVIDENCE"
NEXT_PROCESS = "UPDATE_GATE07J_EVID_FOR_BUSINESS_CASE_AND_ECONOMIC_FINANCIAL_READINESS"
PROVIDER_KEY = "ECONOMIC_FINANCIAL_READINESS_PROVIDER"

MODEL_TYPES = {"COMMERCIAL_PROJECT", "NON_REVENUE_PROJECT", "PUBLIC_ECONOMIC_APPRAISAL", "MIXED"}
VERSION_PURPOSES = {
    "INITIAL_FEASIBILITY",
    "FEL_1_UPDATE",
    "FEL_2_UPDATE",
    "INVESTMENT_SELECTION_UPDATE",
    "FEL_3_UPDATE",
    "FFA_UPDATE",
    "FINANCING_UPDATE",
    "MATERIAL_CHANGE_UPDATE",
    "REVALIDATION",
    "OTHER",
}
DEBT_TYPES = {
    "SENIOR_DEBT",
    "MEZZANINE_DEBT",
    "BANK_LOAN",
    "DEVELOPMENT_BANK_LOAN",
    "BOND",
    "SHAREHOLDER_LOAN",
}
EQUITY_TYPES = {"SPONSOR_EQUITY", "EXTERNAL_INVESTOR_EQUITY", "JV_PARTNER_EQUITY"}
PERIOD_FIELDS = (
    "revenue",
    "economic_benefits",
    "opex",
    "taxes",
    "working_capital_change",
    "capex",
    "debt_drawdown",
    "interest",
    "principal",
    "equity_contribution",
    "distribution",
)


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


DEFAULT_CONFIGURATION: dict[str, Any] = {
    "applicable_project_types": ["*"],
    "applicable_governance_models": ["CAPITAL_OWNER", "PYP", "*"],
    "applicable_gate_profiles": ["PYP-FFA", "*"],
    "applicable_fel_stages": ["FEL-1", "FEL-2", "FEL-3", "FFA", "*"],
    "applicable_model_types": sorted(MODEL_TYPES),
    "required_assumptions": {
        "COMMERCIAL_PROJECT": ["project_discount_rate"],
        "NON_REVENUE_PROJECT": ["economic_discount_rate"],
        "PUBLIC_ECONOMIC_APPRAISAL": ["economic_discount_rate"],
        "MIXED": ["project_discount_rate", "economic_discount_rate"],
    },
    "required_metrics": {
        "COMMERCIAL_PROJECT": ["PROJECT_FINANCIAL_NPV", "PROJECT_IRR"],
        "NON_REVENUE_PROJECT": ["ECONOMIC_NPV", "BENEFIT_COST_RATIO"],
        "PUBLIC_ECONOMIC_APPRAISAL": ["ECONOMIC_NPV", "BENEFIT_COST_RATIO"],
        "MIXED": ["PROJECT_FINANCIAL_NPV", "PROJECT_IRR", "ECONOMIC_NPV", "BENEFIT_COST_RATIO"],
    },
    "funding": {
        "require_governed_assignment_for_financing": True,
        "require_period_alignment": True,
        "require_currency_alignment": True,
    },
    "capex_reconciliation_tolerance_percent": "5",
    "thresholds": {
        "minimum_project_npv": None,
        "minimum_project_irr": None,
        "minimum_economic_npv": None,
        "minimum_bcr": None,
        "minimum_dscr": None,
        "minimum_llcr": None,
    },
    "scenario": {"require_official_base": True, "require_downside": False},
    "separation_of_duties": {
        "reviewer_must_differ_from_preparer": True,
        "funding_confirmer_must_differ_from_reviewer": False,
    },
    "rounding": {"currency": 2, "rate": 8, "ratio": 6},
    "scope": {"workspace_id": None, "inherit_to_descendants": True},
}


class EconomicFinancialModelService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int, context=None) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    # Configuration -----------------------------------------------------
    def ensure_seed(self) -> None:
        exists = self.db.scalar(
            select(AdminConfiguration.id).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "published",
            )
        )
        if exists is not None:
            return
        content = deepcopy(DEFAULT_CONFIGURATION)
        self.db.add(
            AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=CONFIGURATION_KIND,
                code="default",
                name="Default Economic & Financial Model Policy",
                description="Gate 07M-FIN calculation, reconciliation, readiness, scenario and SoD policy.",
                status="published",
                revision=1,
                version=1,
                content_json=content,
                content_hash=_hash(content),
                published_at=utc_now(),
                created_by_user_id=self.actor_id,
            )
        )
        self._event("economic_financial_model.configuration_published", "AdminConfiguration", None, {"seed": True})
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()

    def configurations(self) -> list[AdminConfiguration]:
        self.ensure_seed()
        return list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                )
                .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
            ).all()
        )

    def configuration_preview(
        self,
        project_workspace_id: int,
        business_case_id: int | None,
        configuration_id: int | None,
        content_json: dict | None,
    ) -> ConfigurationPreviewOut:
        project = self._project(project_workspace_id)
        case = self._business_case(project.id, business_case_id)
        config, _chain = self._resolve_configuration(
            project, self._configuration(configuration_id) if configuration_id else None
        )
        content = deepcopy(content_json if content_json is not None else config.content_json)
        issues = self._configuration_issues(content)
        current = self._business_case_revision(case)
        return ConfigurationPreviewOut(
            effective_requirements={
                "business_case_revision": current.id,
                "model_types": content.get("applicable_model_types", []),
                "scenario": content.get("scenario", {}),
            },
            applicable_metrics=sorted(
                {metric for values in content.get("required_metrics", {}).values() for metric in values}
            ),
            required_assumptions=sorted(
                {key for values in content.get("required_assumptions", {}).values() for key in values}
            ),
            funding_linkage_requirements=content.get("funding", {}),
            thresholds=content.get("thresholds", {}),
            readiness_preview="BLOCKED" if issues else "NOT_STARTED",
            warnings=["PREVIEW_ONLY_NO_MODEL_VERSION_CREATED"],
            blockers=issues,
            publishable=not issues,
            persisted=False,
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id, lock=True)
        self._check_version(source.version, expected_version)
        revision = (
            int(
                self.db.scalar(
                    select(func.max(AdminConfiguration.revision)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.code == source.code,
                    )
                )
                or 0
            )
            + 1
        )
        record = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=source.code,
            name=f"{source.name} R{revision}",
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=deepcopy(source.content_json),
            content_hash=source.content_hash,
            created_by_user_id=self.actor_id,
        )
        self.db.add(record)
        self._event(
            "economic_financial_model.configuration_cloned", "AdminConfiguration", source.id, {"revision": revision}
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def update_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        *,
        name: str | None,
        description: str | None,
        content_json: dict,
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_IMMUTABLE"})
        issues = self._configuration_issues(content_json)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_FIN_CONFIGURATION", "issues": issues})
        if name is not None:
            record.name = name
        if description is not None:
            record.description = description
        record.content_json = deepcopy(content_json)
        record.content_hash = _hash(content_json)
        record.version += 1
        record.updated_at = utc_now()
        self._event("economic_financial_model.configuration_updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status == "published":
            return record
        issues = self._configuration_issues(record.content_json)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_FIN_CONFIGURATION", "issues": issues})
        record.status = "published"
        record.published_at = utc_now()
        record.version += 1
        record.updated_at = utc_now()
        self._event("economic_financial_model.configuration_published", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    # Aggregate ----------------------------------------------------------
    def list(self, project_workspace_id: int | None = None) -> list[ModelOut]:
        statement = select(EconomicFinancialModel).where(EconomicFinancialModel.tenant_id == self.tenant_id)
        if project_workspace_id is not None:
            statement = statement.where(EconomicFinancialModel.project_workspace_id == project_workspace_id)
        return [
            self._model_out(item)
            for item in self.db.scalars(statement.order_by(EconomicFinancialModel.updated_at.desc()))
        ]

    def get(self, model_id: int) -> ModelOut:
        return self._model_out(self._model(model_id))

    def by_project(self, project_workspace_id: int) -> ModelOut:
        record = self.db.scalar(
            select(EconomicFinancialModel).where(
                EconomicFinancialModel.tenant_id == self.tenant_id,
                EconomicFinancialModel.project_workspace_id == project_workspace_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "ECONOMIC_FINANCIAL_MODEL_NOT_FOUND"})
        return self._model_out(record)

    def create(self, values: dict[str, Any]) -> ModelOut:
        idempotency_key = str(values["idempotency_key"])
        duplicate = self.db.scalar(
            select(EconomicFinancialModel).where(
                EconomicFinancialModel.tenant_id == self.tenant_id,
                EconomicFinancialModel.create_idempotency_key == idempotency_key,
            )
        )
        if duplicate:
            return self._model_out(duplicate)
        project = self._project(int(values["project_workspace_id"]))
        existing = self.db.scalar(
            select(EconomicFinancialModel).where(
                EconomicFinancialModel.tenant_id == self.tenant_id,
                EconomicFinancialModel.project_workspace_id == project.id,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail={"code": "MODEL_ALREADY_EXISTS_FOR_PROJECT"})
        case = self._business_case(project.id, values.get("business_case_id"))
        case_revision = self._business_case_revision(case)
        config, chain = self._resolve_configuration(project)
        self._validate_version_values(values)
        record = EconomicFinancialModel(
            tenant_id=self.tenant_id,
            model_number=self._next_number(),
            project_workspace_id=project.id,
            business_case_id=case.id,
            owner_user_id=values.get("owner_user_id") or case.owner_user_id,
            sponsor_user_id=values.get("sponsor_user_id") or case.sponsor_user_id,
            status="DRAFT",
            configuration_id=config.id,
            configuration_revision=config.revision,
            configuration_hash=config.content_hash,
            configuration_source_workspace_id=self._chain_source_id(chain),
            configuration_resolution_chain_json=chain,
            create_idempotency_key=idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        version = self._new_version(
            record,
            "INITIAL_FEASIBILITY",
            idempotency_key=f"{idempotency_key}:V1",
            source=None,
            source_values=values,
            case_revision=case_revision,
        )
        record.current_version_id = version.id
        self._event(
            "economic_financial_model.created",
            "EconomicFinancialModel",
            record.id,
            {"project_workspace_id": project.id},
        )
        self.db.commit()
        return self._model_out(record)

    def versions(self, model_id: int) -> list[ModelVersionOut]:
        self._model(model_id)
        return [
            ModelVersionOut.model_validate(item)
            for item in self.db.scalars(
                select(EconomicFinancialModelVersion)
                .where(
                    EconomicFinancialModelVersion.tenant_id == self.tenant_id,
                    EconomicFinancialModelVersion.model_id == model_id,
                )
                .order_by(EconomicFinancialModelVersion.version_number.desc())
            )
        ]

    def create_version(self, model_id: int, purpose: str, idempotency_key: str) -> ModelVersionOut:
        if purpose not in VERSION_PURPOSES or purpose == "INITIAL_FEASIBILITY":
            raise HTTPException(status_code=422, detail={"code": "INVALID_FIN_MODEL_VERSION_PURPOSE"})
        duplicate = self.db.scalar(
            select(EconomicFinancialModelVersion).where(
                EconomicFinancialModelVersion.tenant_id == self.tenant_id,
                EconomicFinancialModelVersion.create_idempotency_key == idempotency_key,
            )
        )
        if duplicate:
            return ModelVersionOut.model_validate(duplicate)
        model = self._model(model_id, lock=True)
        current = self._current_version(model)
        if current.status not in {"COMPLETED", "VOIDED"}:
            raise HTTPException(status_code=409, detail={"code": "OPEN_FIN_MODEL_VERSION_EXISTS"})
        case = self._business_case(model.project_workspace_id, model.business_case_id)
        version = self._new_version(
            model,
            purpose,
            idempotency_key=idempotency_key,
            source=current,
            source_values=None,
            case_revision=self._business_case_revision(case),
        )
        model.current_version_id = version.id
        model.status = "ACTIVE"
        model.updated_by = self.actor_id
        model.updated_at = utc_now()
        model.revision_version += 1
        self._event(
            "economic_financial_model.version_created",
            "EconomicFinancialModelVersion",
            version.id,
            {"purpose": purpose},
        )
        self.db.commit()
        self.db.refresh(version)
        return ModelVersionOut.model_validate(version)

    def update_version(self, version_id: int, expected_version: int, values: dict[str, Any]) -> ModelVersionOut:
        record = self._version(version_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._require_draft(record)
        candidate = {
            key: values.get(key, getattr(record, key))
            for key in (
                "model_type",
                "base_currency",
                "cash_flow_basis",
                "periodicity",
                "model_start_date",
                "model_end_date",
                "construction_start",
                "operations_start",
                "operations_end",
                "terminal_date",
            )
        }
        self._validate_version_values(candidate)
        for key, value in values.items():
            if hasattr(record, key):
                setattr(record, key, value.upper() if key == "base_currency" and value else value)
        self._touch_version(record)
        self._event("economic_financial_model.version_updated", "EconomicFinancialModelVersion", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return ModelVersionOut.model_validate(record)

    # Inputs -------------------------------------------------------------
    def assumptions(self, version_id: int) -> list[FinancialModelAssumption]:
        self._version(version_id)
        return list(
            self.db.scalars(
                select(FinancialModelAssumption)
                .where(
                    FinancialModelAssumption.tenant_id == self.tenant_id,
                    FinancialModelAssumption.model_version_id == version_id,
                )
                .order_by(FinancialModelAssumption.category, FinancialModelAssumption.assumption_key)
            )
        )

    def upsert_assumption(
        self, version_id: int, expected_version: int, values: dict[str, Any]
    ) -> FinancialModelAssumption:
        version = self._version(version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._require_draft(version)
        key = str(values["assumption_key"])
        record = self.db.scalar(
            select(FinancialModelAssumption).where(
                FinancialModelAssumption.tenant_id == self.tenant_id,
                FinancialModelAssumption.model_version_id == version.id,
                FinancialModelAssumption.assumption_key == key,
            )
        )
        if record is None:
            record = FinancialModelAssumption(
                tenant_id=self.tenant_id,
                model_version_id=version.id,
                created_by=self.actor_id,
                **values,
            )
            self.db.add(record)
        else:
            for field, value in values.items():
                setattr(record, field, value)
        self._touch_version(version)
        self.db.commit()
        self.db.refresh(record)
        return record

    def periods(self, version_id: int) -> list[FinancialModelPeriod]:
        self._version(version_id)
        return list(
            self.db.scalars(
                select(FinancialModelPeriod)
                .where(
                    FinancialModelPeriod.tenant_id == self.tenant_id,
                    FinancialModelPeriod.model_version_id == version_id,
                )
                .order_by(FinancialModelPeriod.period_index)
            )
        )

    def upsert_period(self, version_id: int, expected_version: int, values: dict[str, Any]) -> FinancialModelPeriod:
        version = self._version(version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._require_draft(version)
        if values["period_start"] < version.model_start_date or values["period_end"] > version.model_end_date:
            raise HTTPException(status_code=422, detail={"code": "PERIOD_OUTSIDE_MODEL_HORIZON"})
        if values["period_end"] < values["period_start"]:
            raise HTTPException(status_code=422, detail={"code": "INVALID_PERIOD_RANGE"})
        if any(decimal(values.get(field)) < 0 for field in PERIOD_FIELDS if field != "working_capital_change"):
            raise HTTPException(status_code=422, detail={"code": "NEGATIVE_FINANCIAL_INPUT"})
        record = self.db.scalar(
            select(FinancialModelPeriod).where(
                FinancialModelPeriod.tenant_id == self.tenant_id,
                FinancialModelPeriod.model_version_id == version.id,
                FinancialModelPeriod.period_index == values["period_index"],
            )
        )
        if record is None:
            record = FinancialModelPeriod(tenant_id=self.tenant_id, model_version_id=version.id, **values)
            self.db.add(record)
        else:
            for field, value in values.items():
                setattr(record, field, value.upper() if field == "currency" else value)
        self._touch_version(version)
        self.db.commit()
        self.db.refresh(record)
        return record

    def instruments(self, version_id: int) -> list[FinancialModelFinancingInstrument]:
        self._version(version_id)
        return list(
            self.db.scalars(
                select(FinancialModelFinancingInstrument)
                .where(
                    FinancialModelFinancingInstrument.tenant_id == self.tenant_id,
                    FinancialModelFinancingInstrument.model_version_id == version_id,
                )
                .order_by(FinancialModelFinancingInstrument.instrument_key)
            )
        )

    def create_instrument(
        self, version_id: int, expected_version: int, values: dict[str, Any]
    ) -> FinancialModelFinancingInstrument:
        version = self._version(version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._require_draft(version)
        key = str(values.pop("idempotency_key"))
        duplicate = self.db.scalar(
            select(FinancialModelFinancingInstrument).where(
                FinancialModelFinancingInstrument.tenant_id == self.tenant_id,
                FinancialModelFinancingInstrument.create_idempotency_key == key,
            )
        )
        if duplicate:
            return duplicate
        committed = decimal(values["committed_amount"])
        drawn = decimal(values.get("drawn_amount"))
        if drawn > committed:
            raise HTTPException(status_code=422, detail={"code": "DEBT_DRAWDOWN_EXCEEDS_COMMITMENT"})
        assignment = None
        if values.get("funding_assignment_id") is not None:
            assignment = self._funding_assignment(int(values["funding_assignment_id"]))
            if assignment.project_workspace_id not in {None, self._model(version.model_id).project_workspace_id}:
                raise HTTPException(status_code=409, detail={"code": "FUNDING_ASSIGNMENT_PROJECT_MISMATCH"})
            if str(assignment.currency).upper() != str(values["currency"]).upper():
                raise HTTPException(status_code=409, detail={"code": "FUNDING_CURRENCY_MISMATCH"})
            if committed > decimal(assignment.amount):
                raise HTTPException(status_code=409, detail={"code": "FINANCING_MODEL_EXCEEDS_GOVERNED_FUNDING"})
            if (
                assignment.period_start
                and assignment.period_start > version.model_start_date
                or assignment.period_end
                and assignment.period_end < version.model_end_date
            ):
                raise HTTPException(status_code=409, detail={"code": "FUNDING_PERIOD_MISMATCH"})
        fund = self._fund(assignment.fund_id) if assignment else None
        record = FinancialModelFinancingInstrument(
            tenant_id=self.tenant_id,
            model_version_id=version.id,
            funding_source_id=fund.funding_source_id if fund else None,
            fund_id=fund.id if fund else None,
            funding_assignment_hash=assignment.assignment_hash if assignment else None,
            funding_readiness_hash=version.funding_readiness_hash,
            readiness_status="READY" if assignment else "NOT_STARTED",
            create_idempotency_key=key,
            created_by=self.actor_id,
            **values,
        )
        self.db.add(record)
        self._touch_version(version)
        self._event(
            "economic_financial_model.instrument_created",
            "FinancialModelFinancingInstrument",
            None,
            {"funding_linked": assignment is not None},
        )
        if assignment:
            self._event(
                "economic_financial_model.funding_linked",
                "FinancialModelFinancingInstrument",
                None,
                {"funding_assignment_id": assignment.id},
            )
        self.db.commit()
        self.db.refresh(record)
        return record

    def investors(self, version_id: int) -> list[FinancialModelInvestor]:
        self._version(version_id)
        return list(
            self.db.scalars(
                select(FinancialModelInvestor)
                .where(
                    FinancialModelInvestor.tenant_id == self.tenant_id,
                    FinancialModelInvestor.model_version_id == version_id,
                )
                .order_by(FinancialModelInvestor.investor_key)
            )
        )

    def create_investor(self, version_id: int, expected_version: int, values: dict[str, Any]) -> FinancialModelInvestor:
        version = self._version(version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._require_draft(version)
        key = str(values.pop("idempotency_key"))
        duplicate = self.db.scalar(
            select(FinancialModelInvestor).where(
                FinancialModelInvestor.tenant_id == self.tenant_id,
                FinancialModelInvestor.create_idempotency_key == key,
            )
        )
        if duplicate:
            return duplicate
        instrument = self._instrument(int(values["financing_instrument_id"]))
        if instrument.model_version_id != version.id or instrument.instrument_type not in EQUITY_TYPES:
            raise HTTPException(status_code=409, detail={"code": "INVESTOR_EQUITY_INSTRUMENT_REQUIRED"})
        committed = decimal(values["committed_equity"])
        if committed > decimal(instrument.committed_amount):
            raise HTTPException(status_code=409, detail={"code": "EQUITY_CALL_EXCEEDS_COMMITMENT"})
        record = FinancialModelInvestor(
            tenant_id=self.tenant_id,
            model_version_id=version.id,
            create_idempotency_key=key,
            created_by=self.actor_id,
            **values,
        )
        self.db.add(record)
        self._touch_version(version)
        self.db.commit()
        self.db.refresh(record)
        return record

    def scenarios(self, version_id: int) -> list[FinancialModelScenario]:
        self._version(version_id)
        return list(
            self.db.scalars(
                select(FinancialModelScenario)
                .where(
                    FinancialModelScenario.tenant_id == self.tenant_id,
                    FinancialModelScenario.model_version_id == version_id,
                )
                .order_by(FinancialModelScenario.scenario_type, FinancialModelScenario.name)
            )
        )

    def create_scenario(self, version_id: int, expected_version: int, values: dict[str, Any]) -> FinancialModelScenario:
        version = self._version(version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._require_draft(version)
        key = str(values.pop("idempotency_key"))
        overrides = list(values.pop("overrides", []))
        duplicate = self.db.scalar(
            select(FinancialModelScenario).where(
                FinancialModelScenario.tenant_id == self.tenant_id,
                FinancialModelScenario.create_idempotency_key == key,
            )
        )
        if duplicate:
            return duplicate
        if values["scenario_type"] == "BASE" and self._base_scenario(version.id):
            raise HTTPException(status_code=409, detail={"code": "BASE_SCENARIO_ALREADY_EXISTS"})
        scenario = FinancialModelScenario(
            tenant_id=self.tenant_id,
            model_version_id=version.id,
            status="DRAFT",
            output_summary_json={},
            scenario_hash=_hash(values),
            create_idempotency_key=key,
            created_by=self.actor_id,
            **values,
        )
        self.db.add(scenario)
        self.db.flush()
        for item in overrides:
            self.db.add(FinancialModelScenarioOverride(tenant_id=self.tenant_id, scenario_id=scenario.id, **item))
        self._touch_version(version)
        self._event("economic_financial_model.scenario_created", "FinancialModelScenario", scenario.id, {})
        self.db.commit()
        self.db.refresh(scenario)
        return scenario

    # Calculation / lifecycle ------------------------------------------
    def calculate(self, version_id: int, expected_version: int, idempotency_key: str) -> ModelVersionOut:
        version = self._version(version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._require_draft(version)
        if version.calculate_idempotency_key == idempotency_key:
            return ModelVersionOut.model_validate(version)
        duplicate = self.db.scalar(
            select(EconomicFinancialModelVersion).where(
                EconomicFinancialModelVersion.tenant_id == self.tenant_id,
                EconomicFinancialModelVersion.calculate_idempotency_key == idempotency_key,
            )
        )
        if duplicate:
            return ModelVersionOut.model_validate(duplicate)
        periods = self.periods(version.id)
        assumptions = {item.assumption_key: item for item in self.assumptions(version.id)}
        instruments = self.instruments(version.id)
        scenarios = self.scenarios(version.id)
        blockers, warnings = self._validate_calculation_inputs(version, periods, assumptions, instruments, scenarios)

        self.db.execute(delete(FinancialModelCashFlow).where(FinancialModelCashFlow.model_version_id == version.id))
        self.db.execute(
            delete(FinancialModelDebtSchedule).where(FinancialModelDebtSchedule.model_version_id == version.id)
        )
        self.db.execute(
            delete(FinancialModelMetricResult).where(FinancialModelMetricResult.model_version_id == version.id)
        )
        scenario_results: dict[int, dict[str, Any]] = {}
        for scenario in scenarios:
            result = self._calculate_scenario(version, scenario, periods, assumptions, instruments)
            scenario_results[scenario.id] = result
            blockers.extend(result["blockers"])
            warnings.extend(result["warnings"])
            scenario.output_summary_json = result["summary"]
            scenario.scenario_hash = _hash(
                {
                    "source": version.source_snapshot_hash,
                    "overrides": result["overrides"],
                    "summary": result["summary"],
                    "engine": ENGINE_VERSION,
                }
            )
            scenario.status = "CALCULATED"

        base = self._base_scenario(version.id)
        base_result = scenario_results.get(base.id) if base else None
        if base_result:
            metrics = base_result["metrics"]
            version.project_financial_npv = metrics.get("PROJECT_FINANCIAL_NPV")
            version.project_irr = metrics.get("PROJECT_IRR")
            version.economic_npv = metrics.get("ECONOMIC_NPV")
            version.economic_irr = metrics.get("ECONOMIC_IRR")
            version.benefit_cost_ratio = metrics.get("BENEFIT_COST_RATIO")
            version.simple_payback = metrics.get("SIMPLE_PAYBACK")
            version.discounted_payback = metrics.get("DISCOUNTED_PAYBACK")
            version.equity_irr = metrics.get("EQUITY_IRR")
            version.moic = metrics.get("MOIC")
            version.minimum_dscr = metrics.get("MINIMUM_DSCR")
            version.average_dscr = metrics.get("AVERAGE_DSCR")
            version.llcr = metrics.get("LLCR")
            version.debt_to_equity = metrics.get("DEBT_TO_EQUITY")

        reconciliation = self._reconciliation(version, periods, instruments)
        version.total_investment_requirement = reconciliation["total_investment_requirement"]
        version.total_model_financing = reconciliation["total_model_financing"]
        version.governed_funding_assigned = reconciliation["governed_funding_assigned"]
        version.funding_gap = reconciliation["funding_gap"]
        version.funding_reconciliation_status = reconciliation["status"]
        blockers.extend(reconciliation["blockers"])
        warnings.extend(reconciliation["warnings"])

        source_current, source_changes = self._source_current(version)
        if not source_current:
            blockers.append("MODEL_SOURCE_STALE")
            self._event(
                "economic_financial_model.source_stale_detected",
                "EconomicFinancialModelVersion",
                version.id,
                {"changes": source_changes},
            )
        config = self._configuration(self._model(version.model_id).configuration_id)
        blockers.extend(self._threshold_blockers(version, config.content_json))
        blockers = sorted(set(blockers))
        warnings = sorted(set(warnings))
        dimensions = self._readiness_dimensions(version, instruments, scenarios, blockers)
        overall = "STALE" if not source_current else ("BLOCKED" if blockers else "READY")
        version.economic_readiness = dimensions["ECONOMIC_READINESS"]
        version.financial_model_readiness = dimensions["FINANCIAL_MODEL_READINESS"]
        version.funding_reconciliation_readiness = dimensions["FUNDING_RECONCILIATION_READINESS"]
        version.debt_readiness = dimensions["DEBT_READINESS"]
        version.equity_readiness = dimensions["EQUITY_READINESS"]
        version.covenant_readiness = dimensions["COVENANT_READINESS"]
        version.scenario_readiness = dimensions["SCENARIO_READINESS"]
        version.overall_readiness = overall
        version.warnings_json = warnings
        version.blockers_json = blockers
        version.source_current = source_current
        version.calculation_engine_version = ENGINE_VERSION
        version.calculation_trace_json = [
            {
                "metric": key,
                "formula_version": ENGINE_VERSION,
                "scenario_id": base.id if base else None,
                "result": str(value) if value is not None else None,
                "input_reference": version.source_snapshot_hash,
            }
            for key, value in (base_result or {"metrics": {}})["metrics"].items()
        ]
        version.readiness_hash = _hash(
            {"dimensions": dimensions, "warnings": warnings, "blockers": blockers, "source_current": source_current}
        )
        version.model_hash = self._model_hash(version)
        version.calculate_idempotency_key = idempotency_key
        self._touch_version(version)
        self._event(
            "economic_financial_model.calculated",
            "EconomicFinancialModelVersion",
            version.id,
            {"engine": ENGINE_VERSION, "readiness": overall},
        )
        if "COVENANT_BREACH" in blockers:
            self._event(
                "economic_financial_model.covenant_breach_detected", "EconomicFinancialModelVersion", version.id, {}
            )
        self.db.commit()
        self.db.refresh(version)
        return ModelVersionOut.model_validate(version)

    def submit_review(self, version_id: int, expected_version: int, idempotency_key: str) -> ModelVersionOut:
        version = self._version(version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._require_draft(version)
        if version.calculate_idempotency_key is None:
            raise HTTPException(status_code=409, detail={"code": "MODEL_CALCULATION_REQUIRED"})
        if version.overall_readiness != "READY":
            raise HTTPException(
                status_code=409,
                detail={"code": "ECONOMIC_FINANCIAL_MODEL_NOT_READY", "blockers": version.blockers_json},
            )
        version.status = "IN_REVIEW"
        version.submitted_at = utc_now()
        self._touch_version(version)
        self._event(
            "economic_financial_model.review_submitted",
            "EconomicFinancialModelVersion",
            version.id,
            {"idempotency_key": idempotency_key},
        )
        self.db.commit()
        self.db.refresh(version)
        return ModelVersionOut.model_validate(version)

    def complete(
        self, version_id: int, expected_version: int, idempotency_key: str, reviewer_user_id: int | None
    ) -> ModelVersionOut:
        version = self._version(version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        if version.complete_idempotency_key == idempotency_key:
            return ModelVersionOut.model_validate(version)
        if version.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "MODEL_VERSION_NOT_IN_REVIEW"})
        reviewer = reviewer_user_id or self.actor_id
        config = self._configuration(self._model(version.model_id).configuration_id)
        if config.content_json.get("separation_of_duties", {}).get("reviewer_must_differ_from_preparer", True):
            if reviewer == version.preparer_user_id:
                raise HTTPException(status_code=409, detail={"code": "SEPARATION_OF_DUTIES_VIOLATION"})
        current, changes = self._source_current(version)
        if not current:
            raise HTTPException(status_code=409, detail={"code": "MODEL_SOURCE_STALE", "changes": changes})
        if version.overall_readiness != "READY" or version.blockers_json:
            raise HTTPException(status_code=409, detail={"code": "MODEL_VERSION_NOT_READY"})
        version.status = "COMPLETED"
        version.reviewer_user_id = reviewer
        version.completed_by = reviewer
        version.completed_at = utc_now()
        version.complete_idempotency_key = idempotency_key
        version.updated_by = reviewer
        version.updated_at = utc_now()
        version.revision_version += 1
        model = self._model(version.model_id, lock=True)
        model.status = "ACTIVE"
        model.updated_by = reviewer
        model.updated_at = utc_now()
        model.revision_version += 1
        self._sync_draft_business_case(model, version)
        self._event("economic_financial_model.review_completed", "EconomicFinancialModelVersion", version.id, {})
        self._event("economic_financial_model.version_completed", "EconomicFinancialModelVersion", version.id, {})
        self.db.commit()
        self.db.refresh(version)
        return ModelVersionOut.model_validate(version)

    def readiness(self, model_id: int) -> ReadinessOut:
        model = self._model(model_id)
        version = self._current_version(model)
        current, _changes = self._source_current(version)
        status = "STALE" if not current and version.status == "COMPLETED" else version.overall_readiness
        return ReadinessOut(
            model_id=model.id,
            model_version_id=version.id,
            status=status,
            dimensions={
                "ECONOMIC_READINESS": version.economic_readiness,
                "FINANCIAL_MODEL_READINESS": version.financial_model_readiness,
                "FUNDING_RECONCILIATION_READINESS": version.funding_reconciliation_readiness,
                "DEBT_READINESS": version.debt_readiness,
                "EQUITY_READINESS": version.equity_readiness,
                "COVENANT_READINESS": version.covenant_readiness,
                "SCENARIO_READINESS": version.scenario_readiness,
            },
            warnings=version.warnings_json,
            blockers=version.blockers_json if current else sorted({*version.blockers_json, "MODEL_SOURCE_STALE"}),
            source_current=current,
            readiness_hash=version.readiness_hash,
            final_output=READY_OUTPUT if version.status == "COMPLETED" and status == "READY" and current else status,
            persisted=version.status == "COMPLETED",
        )

    def provider_evidence(self, model_id: int) -> ProviderEvidenceOut:
        model = self._model(model_id)
        version = self._current_version(model)
        readiness = self.readiness(model.id)
        scenarios = self.scenarios(version.id)
        can_supply = bool(version.status == "COMPLETED" and readiness.status == "READY" and readiness.source_current)
        return ProviderEvidenceOut(
            provider_key=PROVIDER_KEY,
            source_module="ECONOMIC_FINANCIAL_MODEL",
            evidence_type="ECONOMIC_FINANCIAL_READINESS",
            project_workspace_id=model.project_workspace_id,
            business_case_id=model.business_case_id,
            business_case_revision_id=version.business_case_revision_id,
            business_case_hash=version.business_case_hash,
            economic_financial_model_id=model.id,
            model_version_id=version.id,
            model_version=version.version_number,
            model_type=version.model_type,
            base_currency=version.base_currency,
            as_of_date=version.as_of_date,
            model_hash=version.model_hash,
            project_financial_npv=version.project_financial_npv,
            project_irr=version.project_irr,
            economic_npv=version.economic_npv,
            economic_irr=version.economic_irr,
            benefit_cost_ratio=version.benefit_cost_ratio,
            equity_irr=version.equity_irr,
            moic=version.moic,
            minimum_dscr=version.minimum_dscr,
            llcr=version.llcr,
            debt_to_equity=version.debt_to_equity,
            total_investment_requirement=version.total_investment_requirement,
            total_model_financing=version.total_model_financing,
            governed_funding_assigned=version.governed_funding_assigned,
            funding_gap=version.funding_gap,
            funding_reconciliation_status=version.funding_reconciliation_status,
            economic_readiness=version.economic_readiness,
            financial_model_readiness=version.financial_model_readiness,
            debt_readiness=version.debt_readiness,
            equity_readiness=version.equity_readiness,
            covenant_readiness=version.covenant_readiness,
            overall_readiness=readiness.status,
            scenario_summary=[
                {"id": item.id, "type": item.scenario_type, "name": item.name, "output": item.output_summary_json}
                for item in scenarios
            ],
            warnings=readiness.warnings,
            blockers=readiness.blockers,
            source_current=readiness.source_current,
            can_supply_investment_gate_evidence=can_supply,
        )

    def cash_flows(self, version_id: int, scenario_id: int | None = None) -> list[FinancialModelCashFlow]:
        self._version(version_id)
        if scenario_id is None:
            base = self._base_scenario(version_id)
            scenario_id = base.id if base else 0
        return list(
            self.db.scalars(
                select(FinancialModelCashFlow)
                .where(
                    FinancialModelCashFlow.tenant_id == self.tenant_id,
                    FinancialModelCashFlow.model_version_id == version_id,
                    FinancialModelCashFlow.scenario_id == scenario_id,
                )
                .order_by(FinancialModelCashFlow.period_index)
            )
        )

    def metrics(self, version_id: int, scenario_id: int | None = None) -> list[FinancialModelMetricResult]:
        self._version(version_id)
        if scenario_id is None:
            base = self._base_scenario(version_id)
            scenario_id = base.id if base else 0
        return list(
            self.db.scalars(
                select(FinancialModelMetricResult)
                .where(
                    FinancialModelMetricResult.tenant_id == self.tenant_id,
                    FinancialModelMetricResult.model_version_id == version_id,
                    FinancialModelMetricResult.scenario_id == scenario_id,
                )
                .order_by(FinancialModelMetricResult.metric_key)
            )
        )

    def run_sensitivity(
        self,
        version_id: int,
        expected_version: int,
        *,
        scenario_id: int,
        variable_key: str,
        shock_value: Decimal,
        target_metric: str,
        idempotency_key: str,
    ) -> FinancialModelSensitivityResult:
        version = self._version(version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._require_draft(version)
        duplicate = self.db.scalar(
            select(FinancialModelSensitivityResult).where(
                FinancialModelSensitivityResult.tenant_id == self.tenant_id,
                FinancialModelSensitivityResult.input_hash == _hash({"key": idempotency_key}),
            )
        )
        if duplicate:
            return duplicate
        scenario = self._scenario(scenario_id)
        if scenario.model_version_id != version.id:
            raise HTTPException(status_code=409, detail={"code": "SCENARIO_VERSION_MISMATCH"})
        periods = self.periods(version.id)
        assumptions = {item.assumption_key: item for item in self.assumptions(version.id)}
        instruments = self.instruments(version.id)
        override = FinancialModelScenarioOverride(
            tenant_id=self.tenant_id,
            scenario_id=scenario.id,
            variable_key=variable_key,
            override_type="PERCENTAGE",
            numeric_value=shock_value,
            text_value=None,
        )
        result = self._calculate_scenario(
            version,
            scenario,
            periods,
            assumptions,
            instruments,
            persist=False,
            extra_overrides=[override],
        )
        value = result["metrics"].get(target_metric)
        record = FinancialModelSensitivityResult(
            tenant_id=self.tenant_id,
            model_version_id=version.id,
            scenario_id=scenario.id,
            variable_key=variable_key,
            shock_value=shock_value,
            target_metric=target_metric,
            result_value=value,
            break_even_value=None,
            result_status="CALCULATED" if value is not None else "NOT_COMPUTABLE",
            input_hash=_hash({"key": idempotency_key}),
            created_by=self.actor_id,
        )
        self.db.add(record)
        self._event("economic_financial_model.sensitivity_run", "FinancialModelSensitivityResult", None, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def refresh_preview(self, model_id: int) -> RefreshPreviewOut:
        model = self._model(model_id)
        version = self._current_version(model)
        current, changes = self._source_current(version)
        return RefreshPreviewOut(
            model_id=model.id,
            current_version_id=version.id,
            source_changes=[] if current else changes,
            impacted_sections=sorted({str(item.get("source", "source_lineage")) for item in changes}),
            proposed_purpose="REVALIDATION",
            persisted=False,
        )

    def refresh(self, model_id: int, idempotency_key: str) -> ModelVersionOut:
        model = self._model(model_id, lock=True)
        current = self._current_version(model)
        source_current, _changes = self._source_current(current)
        if source_current:
            raise HTTPException(status_code=409, detail={"code": "MODEL_SOURCE_ALREADY_CURRENT"})
        if current.status not in {"COMPLETED", "VOIDED"}:
            raise HTTPException(status_code=409, detail={"code": "COMPLETE_OR_VOID_CURRENT_VERSION_FIRST"})
        current_funding = None
        if current.funding_readiness_id:
            referenced_funding = self._funding_readiness(current.funding_readiness_id)
            current_funding = FundsManagerService(self.db, self.tenant_id, self.actor_id).readiness(
                referenced_funding.portfolio_workspace_id,
                project_id=referenced_funding.project_workspace_id,
            )
            if not current_funding.source_current:
                raise HTTPException(status_code=409, detail={"code": "CURRENT_READY_FUNDING_SNAPSHOT_REQUIRED"})
        version = self._new_version(
            model,
            "REVALIDATION",
            idempotency_key=idempotency_key,
            source=current,
            source_values={
                "funding_readiness_id": current_funding.snapshot_id if current_funding else None,
            },
            case_revision=self._business_case_revision(
                self._business_case(model.project_workspace_id, model.business_case_id)
            ),
        )
        version.refresh_idempotency_key = idempotency_key
        model.current_version_id = version.id
        model.updated_at = utc_now()
        model.updated_by = self.actor_id
        model.revision_version += 1
        self._event("economic_financial_model.source_refreshed", "EconomicFinancialModelVersion", version.id, {})
        self.db.commit()
        self.db.refresh(version)
        return ModelVersionOut.model_validate(version)

    # Calculation internals --------------------------------------------
    def _calculate_scenario(
        self,
        version: EconomicFinancialModelVersion,
        scenario: FinancialModelScenario,
        periods: list[FinancialModelPeriod],
        assumptions: dict[str, FinancialModelAssumption],
        instruments: list[FinancialModelFinancingInstrument],
        *,
        persist: bool = True,
        extra_overrides: list[FinancialModelScenarioOverride] | None = None,
    ) -> dict[str, Any]:
        overrides = list(
            self.db.scalars(
                select(FinancialModelScenarioOverride).where(
                    FinancialModelScenarioOverride.tenant_id == self.tenant_id,
                    FinancialModelScenarioOverride.scenario_id == scenario.id,
                )
            )
        )
        overrides.extend(extra_overrides or [])
        factors: dict[str, Decimal] = {}
        for item in overrides:
            if item.numeric_value is not None:
                factors[item.variable_key] = decimal(item.numeric_value)

        def adjusted(key: str, value: Decimal) -> Decimal:
            shock = factors.get(key, Decimal("0"))
            return decimal(value) * (Decimal("1") + shock)

        financial_flows: list[Decimal] = []
        economic_flows: list[Decimal] = []
        benefits: list[Decimal] = []
        costs: list[Decimal] = []
        equity_flows: list[Decimal] = []
        cfads_values: list[Decimal] = []
        debt_service_values: list[Decimal] = []
        blockers: list[str] = []
        warnings: list[str] = []
        debt_balances = {item.id: Decimal("0") for item in instruments if item.instrument_type in DEBT_TYPES}

        for period in periods:
            fx = Decimal("1")
            if period.currency.upper() != version.base_currency.upper():
                fx = self._assumption_value(
                    assumptions,
                    f"fx_{period.currency.lower()}_{version.base_currency.lower()}",
                    Decimal("0"),
                )
            revenue = adjusted("revenue", period.revenue) * fx
            economic_benefits = adjusted("economic_benefits", period.economic_benefits) * fx
            opex = adjusted("opex", period.opex) * fx
            taxes = adjusted("taxes", period.taxes) * fx
            capex = adjusted("capex", period.capex) * fx
            working_capital = adjusted("working_capital_change", period.working_capital_change) * fx
            debt_drawdown = adjusted("debt_drawdown", period.debt_drawdown) * fx
            interest = adjusted("interest", period.interest) * fx
            principal = adjusted("principal", period.principal) * fx
            equity_contribution = adjusted("equity_contribution", period.equity_contribution) * fx
            distribution = adjusted("distribution", period.distribution) * fx
            unlevered = revenue - opex - taxes - working_capital - capex
            cfads_value = revenue - opex - taxes - working_capital
            project_cf = unlevered
            economic_cf = economic_benefits + revenue - opex - taxes - working_capital - capex
            equity_cf = distribution - equity_contribution + debt_drawdown - interest - principal
            debt_service = interest + principal
            financial_flows.append(project_cf)
            economic_flows.append(economic_cf)
            benefits.append(revenue + economic_benefits)
            costs.append(opex + taxes + capex + max(working_capital, Decimal("0")))
            equity_flows.append(equity_cf)
            cfads_values.append(cfads_value)
            debt_service_values.append(debt_service)
            if persist:
                row_values = {
                    "period": period.period_index,
                    "revenue": revenue,
                    "benefits": economic_benefits,
                    "opex": opex,
                    "taxes": taxes,
                    "working_capital": working_capital,
                    "capex": capex,
                    "project_cf": project_cf,
                    "cfads": cfads_value,
                    "debt_drawdown": debt_drawdown,
                    "interest": interest,
                    "principal": principal,
                    "equity_contribution": equity_contribution,
                    "distribution": distribution,
                    "equity_cf": equity_cf,
                }
                self.db.add(
                    FinancialModelCashFlow(
                        tenant_id=self.tenant_id,
                        model_version_id=version.id,
                        scenario_id=scenario.id,
                        period_id=period.id,
                        period_index=period.period_index,
                        revenue=revenue,
                        economic_benefits=economic_benefits,
                        opex=opex,
                        taxes=taxes,
                        working_capital_change=working_capital,
                        capex=capex,
                        unlevered_project_cf=project_cf,
                        cfads=cfads_value,
                        debt_drawdown=debt_drawdown,
                        interest=interest,
                        principal=principal,
                        equity_contribution=equity_contribution,
                        distribution=distribution,
                        cash_flow_to_equity=equity_cf,
                        row_hash=_hash(row_values),
                    )
                )
                debt_items = [item for item in instruments if item.instrument_type in DEBT_TYPES]
                total_debt_commitment = sum((decimal(item.committed_amount) for item in debt_items), Decimal("0"))
                for instrument in debt_items:
                    share = (
                        decimal(instrument.committed_amount) / total_debt_commitment
                        if total_debt_commitment
                        else Decimal("0")
                    )
                    opening = debt_balances[instrument.id]
                    draw = debt_drawdown * share
                    principal_paid = min(principal * share, opening + draw)
                    instrument_interest = interest * share
                    closing = opening + draw - principal_paid
                    service = instrument_interest + principal_paid
                    period_dscr = dscr(cfads_value * share, service)
                    covenant_status = (
                        "BREACH"
                        if instrument.minimum_dscr is not None
                        and (period_dscr is None or period_dscr < decimal(instrument.minimum_dscr))
                        else "COMPLIANT"
                    )
                    debt_balances[instrument.id] = closing
                    debt_values = {
                        "instrument": instrument.id,
                        "period": period.id,
                        "opening": opening,
                        "drawdown": draw,
                        "interest": instrument_interest,
                        "principal": principal_paid,
                        "closing": closing,
                    }
                    self.db.add(
                        FinancialModelDebtSchedule(
                            tenant_id=self.tenant_id,
                            model_version_id=version.id,
                            scenario_id=scenario.id,
                            financing_instrument_id=instrument.id,
                            period_id=period.id,
                            opening_balance=opening,
                            drawdown=draw,
                            interest=instrument_interest,
                            fees=Decimal("0"),
                            principal=principal_paid,
                            closing_balance=closing,
                            debt_service=service,
                            dscr=period_dscr,
                            llcr=None,
                            covenant_status=covenant_status,
                            row_hash=_hash(debt_values),
                        )
                    )

        project_rate = self._assumption_value(assumptions, "project_discount_rate", Decimal("0"))
        economic_rate = self._assumption_value(assumptions, "economic_discount_rate", project_rate)
        metrics: dict[str, Decimal | None] = {
            "PROJECT_FINANCIAL_NPV": npv(project_rate, financial_flows),
            "ECONOMIC_NPV": npv(economic_rate, economic_flows),
            "BENEFIT_COST_RATIO": benefit_cost_ratio(economic_rate, benefits, costs),
            "SIMPLE_PAYBACK": payback_period(financial_flows),
            "DISCOUNTED_PAYBACK": payback_period(financial_flows, project_rate),
        }
        for name, values in (
            ("PROJECT_IRR", financial_flows),
            ("ECONOMIC_IRR", economic_flows),
            ("EQUITY_IRR", equity_flows),
        ):
            try:
                metrics[name] = irr(values)
            except FinancialFormulaError as exc:
                metrics[name] = None
                warnings.append(f"{name}_{exc.code}")
        contributions = sum(
            (decimal(item) for item in (period.equity_contribution for period in periods)), Decimal("0")
        )
        distributions = sum((decimal(item) for item in (period.distribution for period in periods)), Decimal("0"))
        metrics["MOIC"] = moic(contributions, distributions)
        dscr_values = [
            value
            for value in (
                dscr(cfads_value, service)
                for cfads_value, service in zip(cfads_values, debt_service_values, strict=False)
            )
            if value is not None
        ]
        metrics["MINIMUM_DSCR"] = min(dscr_values) if dscr_values else None
        metrics["AVERAGE_DSCR"] = sum(dscr_values, Decimal("0")) / Decimal(len(dscr_values)) if dscr_values else None
        total_debt = sum(
            (decimal(item.committed_amount) for item in instruments if item.instrument_type in DEBT_TYPES), Decimal("0")
        )
        total_equity = sum(
            (decimal(item.committed_amount) for item in instruments if item.instrument_type in EQUITY_TYPES),
            Decimal("0"),
        )
        debt_rate = self._assumption_value(assumptions, "cost_of_debt", Decimal("0"))
        metrics["LLCR"] = llcr(cfads_values, debt_rate, total_debt)
        metrics["DEBT_TO_EQUITY"] = None if total_equity == 0 else total_debt / total_equity
        try:
            metrics["WACC"] = wacc(
                total_equity,
                total_debt,
                self._assumption_value(assumptions, "cost_of_equity", project_rate),
                debt_rate,
                self._assumption_value(assumptions, "tax_rate", Decimal("0")),
            )
        except FinancialFormulaError as exc:
            metrics["WACC"] = None
            warnings.append(exc.code)

        if persist:
            for metric_key, value in metrics.items():
                trace = {
                    "metric": metric_key,
                    "engine": ENGINE_VERSION,
                    "scenario": scenario.id,
                    "source": version.source_snapshot_hash,
                }
                self.db.add(
                    FinancialModelMetricResult(
                        tenant_id=self.tenant_id,
                        model_version_id=version.id,
                        scenario_id=scenario.id,
                        metric_key=metric_key,
                        numeric_value=value,
                        status_value="CALCULATED" if value is not None else "NOT_COMPUTABLE",
                        unit="RATIO"
                        if metric_key
                        in {
                            "PROJECT_IRR",
                            "ECONOMIC_IRR",
                            "EQUITY_IRR",
                            "MOIC",
                            "MINIMUM_DSCR",
                            "AVERAGE_DSCR",
                            "LLCR",
                            "DEBT_TO_EQUITY",
                            "WACC",
                            "BENEFIT_COST_RATIO",
                        }
                        else version.base_currency,
                        formula_version=ENGINE_VERSION,
                        input_references_json=[{"source_snapshot_hash": version.source_snapshot_hash}],
                        trace_hash=_hash(trace | {"result": value}),
                    )
                )
        covenant_minimums = [decimal(item.minimum_dscr) for item in instruments if item.minimum_dscr is not None]
        if covenant_minimums and (metrics["MINIMUM_DSCR"] is None or metrics["MINIMUM_DSCR"] < max(covenant_minimums)):
            blockers.append("COVENANT_BREACH")
        return {
            "metrics": metrics,
            "warnings": warnings,
            "blockers": blockers,
            "overrides": [{"variable_key": item.variable_key, "value": str(item.numeric_value)} for item in overrides],
            "summary": {key: str(value) if value is not None else None for key, value in metrics.items()},
        }

    def _validate_calculation_inputs(
        self,
        version: EconomicFinancialModelVersion,
        periods: list[FinancialModelPeriod],
        assumptions: dict[str, FinancialModelAssumption],
        instruments: list[FinancialModelFinancingInstrument],
        scenarios: list[FinancialModelScenario],
    ) -> tuple[list[str], list[str]]:
        blockers: list[str] = []
        warnings: list[str] = []
        config = self._configuration(self._model(version.model_id).configuration_id).content_json
        if not periods:
            blockers.append("FINANCIAL_PERIODS_REQUIRED")
        if not any(item.scenario_type == "BASE" and item.is_official for item in scenarios):
            blockers.append("OFFICIAL_BASE_SCENARIO_REQUIRED")
        if config.get("scenario", {}).get("require_downside") and not any(
            item.scenario_type == "DOWNSIDE" for item in scenarios
        ):
            blockers.append("DOWNSIDE_SCENARIO_REQUIRED")
        for key in config.get("required_assumptions", {}).get(version.model_type, []):
            if key not in assumptions or assumptions[key].numeric_value is None:
                blockers.append(f"ASSUMPTION_REQUIRED:{key}")
        for period in periods:
            if period.currency.upper() != version.base_currency.upper():
                fx_key = f"fx_{period.currency.lower()}_{version.base_currency.lower()}"
                if fx_key not in assumptions or assumptions[fx_key].numeric_value is None:
                    blockers.append(f"FX_RATE_REQUIRED:{fx_key}")
        if version.cash_flow_basis == "REAL" and "inflation_rate" in assumptions:
            warnings.append("REAL_MODEL_IGNORES_NOMINAL_INFLATION")
        if version.cash_flow_basis == "NOMINAL" and "inflation_rate" not in assumptions:
            warnings.append("NOMINAL_MODEL_WITHOUT_EXPLICIT_INFLATION")
        if any(item.instrument_type in DEBT_TYPES and item.interest_basis is None for item in instruments):
            blockers.append("DEBT_INTEREST_BASIS_REQUIRED")
        return blockers, warnings

    def _reconciliation(
        self,
        version: EconomicFinancialModelVersion,
        periods: list[FinancialModelPeriod],
        instruments: list[FinancialModelFinancingInstrument],
    ) -> dict[str, Any]:
        requirement = sum((decimal(item.capex) for item in periods), Decimal("0"))
        model_financing = sum((decimal(item.committed_amount) for item in instruments), Decimal("0"))
        governed = sum(
            (decimal(item.committed_amount) for item in instruments if item.funding_assignment_id), Decimal("0")
        )
        gap = requirement - model_financing
        blockers: list[str] = []
        warnings: list[str] = []
        if model_financing > requirement and requirement > 0:
            blockers.append("FINANCING_EXCEEDS_INVESTMENT_REQUIREMENT")
        if gap > 0:
            blockers.append("FUNDING_GAP")
        if any(item.funding_assignment_id is None for item in instruments):
            blockers.append("GOVERNED_FUNDING_LINK_REQUIRED")
        if version.budget_scenario_id:
            budget_row = self.db.scalar(
                select(PortfolioBudgetScenarioProject).where(
                    PortfolioBudgetScenarioProject.tenant_id == self.tenant_id,
                    PortfolioBudgetScenarioProject.scenario_id == version.budget_scenario_id,
                    PortfolioBudgetScenarioProject.project_workspace_id
                    == self._model(version.model_id).project_workspace_id,
                )
            )
            if budget_row:
                budget_capex = decimal(
                    budget_row.capex_amount if budget_row.capex_amount is not None else budget_row.cost_value
                )
                tolerance = decimal(
                    self._configuration(self._model(version.model_id).configuration_id).content_json.get(
                        "capex_reconciliation_tolerance_percent", "5"
                    )
                ) / Decimal("100")
                if budget_capex and abs(requirement - budget_capex) / budget_capex > tolerance:
                    blockers.append("CAPEX_BUDGET_RECONCILIATION_OUT_OF_TOLERANCE")
            else:
                warnings.append("PROJECT_NOT_FOUND_IN_BUDGET_SCENARIO")
        status = "RECONCILED" if not blockers else "BLOCKED"
        return {
            "total_investment_requirement": requirement,
            "total_model_financing": model_financing,
            "governed_funding_assigned": governed,
            "funding_gap": gap,
            "status": status,
            "blockers": blockers,
            "warnings": warnings,
        }

    def _threshold_blockers(self, version: EconomicFinancialModelVersion, content: dict) -> list[str]:
        values = {
            "minimum_project_npv": version.project_financial_npv,
            "minimum_project_irr": version.project_irr,
            "minimum_economic_npv": version.economic_npv,
            "minimum_bcr": version.benefit_cost_ratio,
            "minimum_dscr": version.minimum_dscr,
            "minimum_llcr": version.llcr,
        }
        blockers: list[str] = []
        for key, threshold in content.get("thresholds", {}).items():
            if threshold is not None and (values.get(key) is None or decimal(values[key]) < decimal(threshold)):
                blockers.append(f"THRESHOLD_NOT_MET:{key}")
        required = content.get("required_metrics", {}).get(version.model_type, [])
        metric_values = {
            "PROJECT_FINANCIAL_NPV": version.project_financial_npv,
            "PROJECT_IRR": version.project_irr,
            "ECONOMIC_NPV": version.economic_npv,
            "ECONOMIC_IRR": version.economic_irr,
            "BENEFIT_COST_RATIO": version.benefit_cost_ratio,
        }
        blockers.extend(f"METRIC_NOT_COMPUTABLE:{key}" for key in required if metric_values.get(key) is None)
        return blockers

    @staticmethod
    def _readiness_dimensions(
        version: EconomicFinancialModelVersion,
        instruments: list[FinancialModelFinancingInstrument],
        scenarios: list[FinancialModelScenario],
        blockers: list[str],
    ) -> dict[str, str]:
        blocked = "BLOCKED" if blockers else "READY"
        has_debt = any(item.instrument_type in DEBT_TYPES for item in instruments)
        has_equity = any(item.instrument_type in EQUITY_TYPES for item in instruments)
        return {
            "ECONOMIC_READINESS": blocked
            if version.model_type in {"NON_REVENUE_PROJECT", "PUBLIC_ECONOMIC_APPRAISAL", "MIXED"}
            else "NOT_APPLICABLE",
            "FINANCIAL_MODEL_READINESS": blocked
            if version.model_type in {"COMMERCIAL_PROJECT", "MIXED"}
            else "NOT_APPLICABLE",
            "FUNDING_RECONCILIATION_READINESS": blocked,
            "DEBT_READINESS": blocked if has_debt else "NOT_APPLICABLE",
            "EQUITY_READINESS": blocked if has_equity else "NOT_APPLICABLE",
            "COVENANT_READINESS": blocked if has_debt else "NOT_APPLICABLE",
            "SCENARIO_READINESS": blocked if scenarios else "NOT_STARTED",
        }

    # Source lineage / aggregate helpers -------------------------------
    def _source_bundle(
        self,
        model: EconomicFinancialModel,
        case_revision: BusinessCaseRevision,
        budget_scenario_id: int | None,
        funding_readiness_id: int | None,
    ) -> tuple[dict, dict, str]:
        references: dict[str, Any] = {
            "business_case": {"id": model.business_case_id, "revision_id": case_revision.id},
        }
        hashes: dict[str, Any] = {"business_case": case_revision.content_hash}
        if budget_scenario_id:
            budget = self._budget_scenario(budget_scenario_id)
            references["budget_scenario"] = {"id": budget.id, "status": budget.status}
            hashes["budget_scenario"] = budget.scenario_hash
        if funding_readiness_id:
            funding = self._funding_readiness(funding_readiness_id)
            references["funding_readiness"] = {"id": funding.id, "status": funding.status}
            hashes["funding_readiness"] = funding.funding_readiness_hash
        return references, hashes, _hash({"references": references, "hashes": hashes})

    def _source_current(self, version: EconomicFinancialModelVersion) -> tuple[bool, list[dict]]:
        model = self._model(version.model_id)
        case = self._business_case(model.project_workspace_id, model.business_case_id)
        current_case = self._business_case_revision(case)
        changes: list[dict] = []
        business_case_changed = (
            current_case.id != version.business_case_revision_id
            or current_case.content_hash != version.business_case_hash
        )
        # A completed Business Case revision may legitimately move forward after
        # FIN has completed in order to capture the exact governed FIN hash.  In
        # that case the two aggregates form a closed, auditable link: FIN still
        # points to the prior approved Business Case source and the current
        # Business Case points back to this precise FIN result.  Treating that
        # bridge as stale made it impossible for both Class A providers to be
        # current at the same time.
        current_case_links_this_version = (
            current_case.status == "COMPLETED"
            and current_case.readiness_status == "READY"
            and current_case.financial_model_status == "AVAILABLE"
            and current_case.economic_financial_model_id == model.id
            and current_case.economic_financial_model_version == version.version_number
            and current_case.economic_financial_model_hash == version.model_hash
        )
        if business_case_changed and not current_case_links_this_version:
            changes.append(
                {"source": "business_case", "before": version.business_case_hash, "after": current_case.content_hash}
            )
        if version.budget_scenario_id:
            budget = self._budget_scenario(version.budget_scenario_id)
            if budget.scenario_hash != version.budget_scenario_hash:
                changes.append(
                    {"source": "budget_scenario", "before": version.budget_scenario_hash, "after": budget.scenario_hash}
                )
        if version.funding_readiness_id:
            funding = self._funding_readiness(version.funding_readiness_id)
            current_funding = FundsManagerService(self.db, self.tenant_id, self.actor_id).readiness(
                funding.portfolio_workspace_id,
                project_id=funding.project_workspace_id,
            )
            if (
                funding.funding_readiness_hash != version.funding_readiness_hash
                or not funding.source_current
                or not current_funding.source_current
                or current_funding.funding_readiness_hash != version.funding_readiness_hash
            ):
                changes.append(
                    {
                        "source": "funding_readiness",
                        "before": version.funding_readiness_hash,
                        "after": current_funding.funding_readiness_hash,
                    }
                )
        return not changes, changes

    def _new_version(
        self,
        model: EconomicFinancialModel,
        purpose: str,
        *,
        idempotency_key: str,
        source: EconomicFinancialModelVersion | None,
        source_values: dict[str, Any] | None,
        case_revision: BusinessCaseRevision,
    ) -> EconomicFinancialModelVersion:
        values = source_values or {}
        number = 1 if source is None else source.version_number + 1
        budget_id = values.get("budget_scenario_id", source.budget_scenario_id if source else None)
        funding_id = values.get("funding_readiness_id", source.funding_readiness_id if source else None)
        references, hashes, snapshot_hash = self._source_bundle(model, case_revision, budget_id, funding_id)
        record = EconomicFinancialModelVersion(
            tenant_id=self.tenant_id,
            model_id=model.id,
            version_number=number,
            version_label=f"V{number}",
            purpose=purpose,
            status="DRAFT",
            model_type=values.get("model_type", source.model_type if source else "COMMERCIAL_PROJECT"),
            base_currency=str(values.get("base_currency", source.base_currency if source else "USD")).upper(),
            cash_flow_basis=values.get("cash_flow_basis", source.cash_flow_basis if source else "NOMINAL"),
            periodicity=values.get("periodicity", source.periodicity if source else "MONTHLY"),
            model_start_date=values.get("model_start_date", source.model_start_date if source else None),
            model_end_date=values.get("model_end_date", source.model_end_date if source else None),
            construction_start=values.get("construction_start", source.construction_start if source else None),
            operations_start=values.get("operations_start", source.operations_start if source else None),
            operations_end=values.get("operations_end", source.operations_end if source else None),
            terminal_date=values.get("terminal_date", source.terminal_date if source else None),
            business_case_revision_id=case_revision.id,
            business_case_hash=case_revision.content_hash,
            budget_scenario_id=budget_id,
            budget_scenario_hash=hashes.get("budget_scenario"),
            funding_readiness_id=funding_id,
            funding_readiness_hash=hashes.get("funding_readiness"),
            source_references_json=references,
            source_hashes_json=hashes,
            source_snapshot_hash=snapshot_hash,
            readiness_hash=_hash({"status": "NOT_STARTED", "source": snapshot_hash}),
            model_hash="",
            preparer_user_id=self.actor_id,
            create_idempotency_key=idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        if source is None:
            self.db.add(
                FinancialModelScenario(
                    tenant_id=self.tenant_id,
                    model_version_id=record.id,
                    scenario_key="BASE",
                    name="Official Base Case",
                    scenario_type="BASE",
                    is_official=True,
                    description="Governed deterministic baseline.",
                    status="DRAFT",
                    output_summary_json={},
                    scenario_hash=_hash({"version": record.id, "scenario": "BASE"}),
                    create_idempotency_key=f"{idempotency_key}:BASE",
                    created_by=self.actor_id,
                )
            )
        else:
            self._copy_inputs(source.id, record.id, idempotency_key)
        record.model_hash = self._model_hash(record)
        return record

    def _copy_inputs(self, source_id: int, target_id: int, key: str) -> None:
        for item in self.assumptions(source_id):
            values = {
                column.name: getattr(item, column.name)
                for column in FinancialModelAssumption.__table__.columns
                if column.name not in {"id", "model_version_id", "created_at"}
            }
            values.update(model_version_id=target_id, created_by=self.actor_id)
            self.db.add(FinancialModelAssumption(**values))
        for item in self.periods(source_id):
            values = {
                column.name: getattr(item, column.name)
                for column in FinancialModelPeriod.__table__.columns
                if column.name not in {"id", "model_version_id"}
            }
            values.update(model_version_id=target_id)
            self.db.add(FinancialModelPeriod(**values))
        instrument_map: dict[int, FinancialModelFinancingInstrument] = {}
        for index, item in enumerate(self.instruments(source_id)):
            values = {
                column.name: getattr(item, column.name)
                for column in FinancialModelFinancingInstrument.__table__.columns
                if column.name not in {"id", "model_version_id", "created_at", "create_idempotency_key"}
            }
            values.update(
                model_version_id=target_id, create_idempotency_key=f"{key}:INST:{index}", created_by=self.actor_id
            )
            clone = FinancialModelFinancingInstrument(**values)
            self.db.add(clone)
            self.db.flush()
            instrument_map[item.id] = clone
        for index, item in enumerate(self.investors(source_id)):
            values = {
                column.name: getattr(item, column.name)
                for column in FinancialModelInvestor.__table__.columns
                if column.name
                not in {"id", "model_version_id", "financing_instrument_id", "created_at", "create_idempotency_key"}
            }
            values.update(
                model_version_id=target_id,
                financing_instrument_id=instrument_map[item.financing_instrument_id].id,
                create_idempotency_key=f"{key}:INV:{index}",
                created_by=self.actor_id,
            )
            self.db.add(FinancialModelInvestor(**values))
        for index, item in enumerate(self.scenarios(source_id)):
            clone = FinancialModelScenario(
                tenant_id=self.tenant_id,
                model_version_id=target_id,
                scenario_key=item.scenario_key,
                name=item.name,
                scenario_type=item.scenario_type,
                is_official=item.is_official,
                description=item.description,
                status="DRAFT",
                output_summary_json={},
                scenario_hash=_hash({"source": item.scenario_hash, "target": target_id}),
                create_idempotency_key=f"{key}:SCN:{index}",
                created_by=self.actor_id,
            )
            self.db.add(clone)

    def _sync_draft_business_case(self, model: EconomicFinancialModel, version: EconomicFinancialModelVersion) -> None:
        case = self._business_case(model.project_workspace_id, model.business_case_id)
        revision = self._business_case_revision(case)
        if revision.status != "DRAFT":
            return
        revision.economic_financial_model_id = model.id
        revision.economic_financial_model_version = version.version_number
        revision.economic_financial_model_hash = version.model_hash
        revision.financial_model_status = "AVAILABLE"
        revision.economic_financial_readiness = version.overall_readiness
        revision.economic_financial_as_of_date = version.as_of_date
        revision.npv = (
            version.project_financial_npv if version.project_financial_npv is not None else version.economic_npv
        )
        revision.irr = version.project_irr if version.project_irr is not None else version.economic_irr
        revision.payback_period = version.simple_payback
        revision.benefit_cost_ratio = version.benefit_cost_ratio
        revision.updated_by = self.actor_id
        revision.updated_at = utc_now()
        revision.revision_version += 1

    # Lookup / validation ----------------------------------------------
    def _model_out(self, model: EconomicFinancialModel) -> ModelOut:
        current = self._current_version(model, required=False)
        return ModelOut(
            **{column.name: getattr(model, column.name) for column in EconomicFinancialModel.__table__.columns},
            current_version=ModelVersionOut.model_validate(current) if current else None,
            final_output=READY_OUTPUT
            if current and current.status == "COMPLETED" and current.overall_readiness == "READY"
            else current.overall_readiness
            if current
            else "NOT_STARTED",
            next_process=NEXT_PROCESS,
        )

    def _model(self, model_id: int, *, lock: bool = False) -> EconomicFinancialModel:
        statement = select(EconomicFinancialModel).where(
            EconomicFinancialModel.id == model_id, EconomicFinancialModel.tenant_id == self.tenant_id
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "ECONOMIC_FINANCIAL_MODEL_NOT_FOUND"})
        return record

    def _version(self, version_id: int, *, lock: bool = False) -> EconomicFinancialModelVersion:
        statement = select(EconomicFinancialModelVersion).where(
            EconomicFinancialModelVersion.id == version_id, EconomicFinancialModelVersion.tenant_id == self.tenant_id
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "ECONOMIC_FINANCIAL_MODEL_VERSION_NOT_FOUND"})
        return record

    def _current_version(
        self, model: EconomicFinancialModel, *, required: bool = True
    ) -> EconomicFinancialModelVersion | None:
        record = self.db.scalar(
            select(EconomicFinancialModelVersion).where(
                EconomicFinancialModelVersion.id == model.current_version_id,
                EconomicFinancialModelVersion.tenant_id == self.tenant_id,
            )
        )
        if record is None and required:
            raise HTTPException(status_code=409, detail={"code": "CURRENT_FIN_MODEL_VERSION_REQUIRED"})
        return record

    def _project(self, project_id: int) -> EnterpriseWorkspace:
        record = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == project_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.workspace_type_code == "project",
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PROJECT_WORKSPACE_NOT_FOUND"})
        return record

    def _business_case(self, project_id: int, case_id: int | None) -> BusinessCase:
        statement = select(BusinessCase).where(
            BusinessCase.tenant_id == self.tenant_id, BusinessCase.project_workspace_id == project_id
        )
        if case_id is not None:
            statement = statement.where(BusinessCase.id == case_id)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=409, detail={"code": "GOVERNED_BUSINESS_CASE_REQUIRED"})
        return record

    def _business_case_revision(self, case: BusinessCase) -> BusinessCaseRevision:
        record = self.db.scalar(
            select(BusinessCaseRevision).where(
                BusinessCaseRevision.id == case.current_revision_id,
                BusinessCaseRevision.tenant_id == self.tenant_id,
                BusinessCaseRevision.business_case_id == case.id,
            )
        )
        if record is None or record.status != "COMPLETED" or record.readiness_status != "READY":
            raise HTTPException(status_code=409, detail={"code": "READY_COMPLETED_BUSINESS_CASE_REVISION_REQUIRED"})
        return record

    def _configuration(self, configuration_id: int | None, *, lock: bool = False) -> AdminConfiguration:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.id == configuration_id,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "FIN_CONFIGURATION_NOT_FOUND"})
        return record

    def _resolve_configuration(
        self, project: EnterpriseWorkspace, explicit: AdminConfiguration | None = None
    ) -> tuple[AdminConfiguration, list[dict]]:
        if explicit:
            return explicit, [
                {
                    "configuration_id": explicit.id,
                    "workspace_id": explicit.content_json.get("scope", {}).get("workspace_id"),
                    "distance": 0,
                }
            ]
        self.ensure_seed()
        configs = list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.status == "published",
                )
                .order_by(AdminConfiguration.revision.desc())
            )
        )
        if not configs:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_FIN_CONFIGURATION_REQUIRED"})
        ancestors: list[int] = []
        current: EnterpriseWorkspace | None = project
        while current:
            ancestors.append(current.id)
            current = self.db.get(EnterpriseWorkspace, current.parent_id) if current.parent_id else None
        ranked: list[tuple[int, AdminConfiguration]] = []
        chain: list[dict] = []
        for item in configs:
            workspace_id = item.content_json.get("scope", {}).get("workspace_id")
            if workspace_id is not None and workspace_id not in ancestors:
                continue
            distance = ancestors.index(workspace_id) if workspace_id in ancestors else len(ancestors)
            ranked.append((distance, item))
            chain.append({"configuration_id": item.id, "workspace_id": workspace_id, "distance": distance})
        ranked.sort(key=lambda value: (value[0], -value[1].revision))
        return ranked[0][1], sorted(chain, key=lambda item: item["distance"])

    def _budget_scenario(self, scenario_id: int) -> PortfolioBudgetScenario:
        record = self.db.scalar(
            select(PortfolioBudgetScenario).where(
                PortfolioBudgetScenario.id == scenario_id, PortfolioBudgetScenario.tenant_id == self.tenant_id
            )
        )
        if record is None or record.status != "FROZEN":
            raise HTTPException(status_code=409, detail={"code": "FROZEN_BUDGET_SCENARIO_REQUIRED"})
        return record

    def _funding_readiness(self, readiness_id: int) -> FundingReadinessSnapshot:
        record = self.db.scalar(
            select(FundingReadinessSnapshot).where(
                FundingReadinessSnapshot.id == readiness_id, FundingReadinessSnapshot.tenant_id == self.tenant_id
            )
        )
        if record is None or record.status != "READY" or not record.source_current:
            raise HTTPException(status_code=409, detail={"code": "CURRENT_READY_FUNDING_SNAPSHOT_REQUIRED"})
        return record

    def _funding_assignment(self, assignment_id: int) -> FundingAssignment:
        record = self.db.scalar(
            select(FundingAssignment).where(
                FundingAssignment.id == assignment_id,
                FundingAssignment.tenant_id == self.tenant_id,
                FundingAssignment.status.in_({"RESERVED", "CONFIRMED"}),
            )
        )
        if record is None:
            raise HTTPException(status_code=409, detail={"code": "GOVERNED_FUNDING_ASSIGNMENT_REQUIRED"})
        return record

    def _fund(self, fund_id: int) -> Fund:
        record = self.db.scalar(select(Fund).where(Fund.id == fund_id, Fund.tenant_id == self.tenant_id))
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "FUND_NOT_FOUND"})
        return record

    def _instrument(self, instrument_id: int) -> FinancialModelFinancingInstrument:
        record = self.db.scalar(
            select(FinancialModelFinancingInstrument).where(
                FinancialModelFinancingInstrument.id == instrument_id,
                FinancialModelFinancingInstrument.tenant_id == self.tenant_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "FINANCING_INSTRUMENT_NOT_FOUND"})
        return record

    def _scenario(self, scenario_id: int) -> FinancialModelScenario:
        record = self.db.scalar(
            select(FinancialModelScenario).where(
                FinancialModelScenario.id == scenario_id, FinancialModelScenario.tenant_id == self.tenant_id
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "FINANCIAL_SCENARIO_NOT_FOUND"})
        return record

    def _base_scenario(self, version_id: int) -> FinancialModelScenario | None:
        return self.db.scalar(
            select(FinancialModelScenario).where(
                FinancialModelScenario.tenant_id == self.tenant_id,
                FinancialModelScenario.model_version_id == version_id,
                FinancialModelScenario.scenario_type == "BASE",
                FinancialModelScenario.is_official.is_(True),
            )
        )

    def _next_number(self) -> str:
        sequence = self.db.scalar(
            select(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == "economic_financial_model",
                AdminNumberSequence.scope_key == "tenant",
            )
            .with_for_update()
        )
        if sequence is None:
            sequence = AdminNumberSequence(
                tenant_id=self.tenant_id, rule_code="economic_financial_model", scope_key="tenant", next_value=2
            )
            self.db.add(sequence)
            value = 1
        else:
            value = sequence.next_value
            sequence.next_value += 1
            sequence.version += 1
            sequence.updated_at = utc_now()
        return f"EFM-{value:06d}"

    @staticmethod
    def _assumption_value(assumptions: dict[str, FinancialModelAssumption], key: str, default: Decimal) -> Decimal:
        item = assumptions.get(key)
        return decimal(item.numeric_value) if item and item.numeric_value is not None else default

    @staticmethod
    def _configuration_issues(content: dict) -> list[str]:
        issues: list[str] = []
        if not MODEL_TYPES.issubset(set(content.get("applicable_model_types", []))):
            issues.append("ALL_GOVERNED_MODEL_TYPES_REQUIRED")
        if "required_metrics" not in content or "required_assumptions" not in content:
            issues.append("READINESS_POLICY_REQUIRED")
        if not content.get("separation_of_duties", {}).get("reviewer_must_differ_from_preparer", False):
            issues.append("PREPARER_REVIEWER_SOD_REQUIRED")
        return issues

    @staticmethod
    def _validate_version_values(values: dict[str, Any]) -> None:
        if values.get("model_type") not in MODEL_TYPES:
            raise HTTPException(status_code=422, detail={"code": "INVALID_MODEL_TYPE"})
        if values.get("cash_flow_basis") not in {"NOMINAL", "REAL"}:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CASH_FLOW_BASIS"})
        if values.get("periodicity") not in {"MONTHLY", "QUARTERLY", "ANNUAL"}:
            raise HTTPException(status_code=422, detail={"code": "INVALID_PERIODICITY"})
        if (
            values.get("model_start_date") is None
            or values.get("model_end_date") is None
            or values["model_end_date"] < values["model_start_date"]
        ):
            raise HTTPException(status_code=422, detail={"code": "INVALID_MODEL_HORIZON"})
        if values.get("construction_start") is None:
            raise HTTPException(status_code=422, detail={"code": "CONSTRUCTION_START_REQUIRED"})

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(
                status_code=412, detail={"code": "ETAG_MISMATCH", "expected": expected, "actual": actual}
            )

    @staticmethod
    def _require_draft(version: EconomicFinancialModelVersion) -> None:
        if version.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "DRAFT_FIN_MODEL_VERSION_REQUIRED"})

    def _touch_version(self, version: EconomicFinancialModelVersion) -> None:
        version.updated_by = self.actor_id
        version.updated_at = utc_now()
        version.revision_version += 1

    def _model_hash(self, version: EconomicFinancialModelVersion) -> str:
        return _hash(
            {
                "model": version.model_id,
                "version": version.version_number,
                "source": version.source_snapshot_hash,
                "engine": version.calculation_engine_version,
                "readiness": version.overall_readiness,
                "metrics": {
                    "project_npv": version.project_financial_npv,
                    "project_irr": version.project_irr,
                    "economic_npv": version.economic_npv,
                    "economic_irr": version.economic_irr,
                    "bcr": version.benefit_cost_ratio,
                    "equity_irr": version.equity_irr,
                    "dscr": version.minimum_dscr,
                },
            }
        )

    @staticmethod
    def _chain_source_id(chain: list[dict]) -> int | None:
        return chain[0].get("workspace_id") if chain else None

    def _event(self, event_type: str, target_type: str, target_id: int | None, metadata: dict) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=target_type,
                target_id=target_id,
                metadata_json=metadata,
            )
        )
