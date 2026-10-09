"""Read-only canonical source adapters. No source import, update, CPM or FX here."""

from copy import deepcopy

from sqlalchemy import func, select

from app.domain.models import (
    ActivityRelationship,
    BaselineVersion,
    ControlAccount,
    Project,
    ScheduleActivityMap,
    ScheduleImport,
    ScheduleValidationFinding,
)
from app.modules.basic_data.service import _hash, _json
from app.modules.business_case.models import BusinessCase, BusinessCaseRevision
from app.modules.economic_financial_model.models import (
    EconomicFinancialModel,
    EconomicFinancialModelVersion,
    FinancialModelPeriod,
)
from app.modules.portfolio_budget.models import PortfolioBudgetScenario, PortfolioBudgetScenarioProject


class SourceAdapters:
    def __init__(self, db, tenant_id):
        self.db, self.tenant_id = db, tenant_id

    def operational_project(self, workspace):
        explicit = (workspace.defaults_json or {}).get("_project", {}).get("operational_project_id")
        if explicit is not None:
            row = self.db.scalar(select(Project).where(Project.tenant_id == self.tenant_id, Project.id == explicit))
            if row:
                reverse = (row.configuration or {}).get("enterprise_workspace_id")
                if reverse in {None, workspace.id}:
                    return row
            return None
        # Reverse link is explicit; no equal-id, name or code guessing.
        linked = self.db.scalars(
            select(Project)
            .where(
                Project.tenant_id == self.tenant_id,
                Project.configuration["enterprise_workspace_id"].as_integer() == workspace.id,
            )
            .limit(2)
        ).all()
        return linked[0] if len(linked) == 1 else None

    def schedule(self, workspace, import_id):
        operational = self.operational_project(workspace)
        row = self.db.scalar(
            select(ScheduleImport).where(
                ScheduleImport.tenant_id == self.tenant_id,
                ScheduleImport.project_id == (operational.id if operational else -1),
                ScheduleImport.id == import_id,
            )
        )
        if row is None:
            return None
        maps = self.db.scalars(
            select(ScheduleActivityMap)
            .where(
                ScheduleActivityMap.tenant_id == self.tenant_id,
                ScheduleActivityMap.project_id == operational.id,
                ScheduleActivityMap.schedule_import_id == row.id,
            )
            .order_by(ScheduleActivityMap.id)
        ).all()
        relationships = self.db.scalars(
            select(ActivityRelationship)
            .where(
                ActivityRelationship.tenant_id == self.tenant_id,
                ActivityRelationship.project_id == operational.id,
                ActivityRelationship.schedule_import_id == row.id,
            )
            .order_by(ActivityRelationship.id)
        ).all()
        findings = self.db.scalars(
            select(ScheduleValidationFinding).where(
                ScheduleValidationFinding.tenant_id == self.tenant_id,
                ScheduleValidationFinding.project_id == operational.id,
                ScheduleValidationFinding.schedule_import_id == row.id,
            )
        ).all()
        baselines = self.db.scalars(
            select(BaselineVersion)
            .where(
                BaselineVersion.tenant_id == self.tenant_id,
                BaselineVersion.project_id == operational.id,
                BaselineVersion.schedule_import_id == row.id,
            )
            .order_by(BaselineVersion.version_no)
        ).all()
        latest = self.db.scalar(
            select(ScheduleImport.id)
            .where(ScheduleImport.tenant_id == self.tenant_id, ScheduleImport.project_id == operational.id)
            .order_by(ScheduleImport.imported_at.desc(), ScheduleImport.id.desc())
            .limit(1)
        )
        metadata = deepcopy(getattr(row, "source_metadata", None) or {})
        extras = {str(v.get("external_id")): v for v in metadata.get("activities", []) if isinstance(v, dict)}
        items = [
            {
                "ref": m.external_activity_id,
                "name": m.activity_name,
                "wbs_code": m.wbs_code,
                "planned_start": m.planned_start,
                "planned_finish": m.planned_finish,
                "total_float_days": m.total_float_days,
                "critical_path_imported": m.critical_path,
                **extras.get(m.external_activity_id, {}),
            }
            for m in maps
        ]
        relations = [
            {
                "id": r.id,
                "predecessor": r.predecessor_external_id,
                "successor": r.successor_external_id,
                "type": r.relationship_type.value.upper(),
                "lag_days": r.lag_days,
            }
            for r in relationships
        ]
        material = _json(
            {
                "id": row.id,
                "source": row.source.value,
                "status": row.status.value,
                "file_name": row.file_name,
                "data_date": row.data_date,
                "baseline_name": row.baseline_name,
                "imported_at": row.imported_at,
                "activities": items,
                "relationships": relations,
                "metadata": metadata,
                "baselines": [
                    {"id": b.id, "version": b.version_no, "status": b.status, "data_date": b.data_date}
                    for b in baselines
                ],
                "existing_validation_findings": [
                    {"code": f.check_code, "severity": f.severity, "item_count": f.item_count, "message": f.message}
                    for f in findings
                ],
            }
        )
        return {
            "kind": "SCHEDULE_IMPORT",
            "status": row.status.value,
            "id": row.id,
            "reference": f"schedule-import:{row.id}:{row.file_name}",
            "version": row.id,
            "hash": _hash(material),
            "source_current": latest == row.id,
            "as_of": row.imported_at.isoformat(),
            "data_date": row.data_date.isoformat() if row.data_date else None,
            "items": material["activities"],
            "relationships": relations,
            "raw_relationships": metadata.get("relationships", []),
            "calendars": metadata.get("calendars", []),
            "baseline_refs": material["baselines"],
            "metadata_available": bool(metadata),
            "source_file_hash": metadata.get("source_file_hash"),
            "existing_validation_findings": material["existing_validation_findings"],
            "operational_project_id": operational.id,
            "authority": "EXISTING_MANUAL_P6_IMPORT_NO_CPM_NO_API",
        }

    def schedule_options(self, workspace, *, page=1, page_size=100):
        operational = self.operational_project(workspace)
        query = select(ScheduleImport).where(
            ScheduleImport.tenant_id == self.tenant_id,
            ScheduleImport.project_id == (operational.id if operational else -1),
        )
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.db.scalars(
            query.order_by(ScheduleImport.id.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        items = [
            {
                "kind": "SCHEDULE_IMPORT",
                "id": r.id,
                "reference": f"schedule-import:{r.id}:{r.file_name}",
                "version": r.id,
                "name": r.file_name,
                "data_date": r.data_date.isoformat() if r.data_date else None,
                "metadata_available": bool(getattr(r, "source_metadata", None)),
                "status": r.status.value,
            }
            for r in rows
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "availability": "AVAILABLE" if total else "NOT_AVAILABLE",
            "operational_project_id": operational.id if operational else None,
        }

    def cost_sources(self, workspace):
        result = []
        models = self.db.execute(
            select(EconomicFinancialModel, EconomicFinancialModelVersion)
            .join(
                EconomicFinancialModelVersion,
                EconomicFinancialModelVersion.id == EconomicFinancialModel.current_version_id,
            )
            .where(
                EconomicFinancialModel.tenant_id == self.tenant_id,
                EconomicFinancialModelVersion.tenant_id == self.tenant_id,
                EconomicFinancialModel.project_workspace_id == workspace.id,
            )
        ).all()
        version_ids = [v.id for _, v in models]
        periods = self.db.scalars(
            select(FinancialModelPeriod)
            .where(
                FinancialModelPeriod.tenant_id == self.tenant_id,
                FinancialModelPeriod.model_version_id.in_(version_ids or [-1]),
            )
            .order_by(FinancialModelPeriod.id)
        ).all()
        for model, version in models:
            items = [
                {
                    "ref": f"FIN_CAPEX:{version.id}:{p.id}",
                    "amount": float(p.capex),
                    "currency": p.currency,
                    "period": p.period_label,
                    "basis_date": p.period_start.isoformat(),
                    "unit": p.currency,
                    "source_reference": p.source_reference,
                    "source_hash": p.source_hash,
                }
                for p in periods
                if p.model_version_id == version.id
            ]
            material = _json(
                {
                    "model_id": model.id,
                    "version": version.version_number,
                    "content_hash": getattr(version, "model_hash", None),
                    "status": version.status,
                    "items": items,
                }
            )
            result.append(
                {
                    "kind": "FIN_CAPEX",
                    "id": version.id,
                    "reference": f"fin-capex-version:{version.id}",
                    "version": version.version_number,
                    "hash": _hash(material),
                    "source_current": version.status == "COMPLETED",
                    "status": version.status,
                    "currency": version.base_currency,
                    "amount": sum(i["amount"] for i in items),
                    "items": items,
                    "as_of": version.as_of_date.isoformat(),
                }
            )
        cases = self.db.execute(
            select(BusinessCase, BusinessCaseRevision)
            .join(BusinessCaseRevision, BusinessCaseRevision.id == BusinessCase.current_revision_id)
            .where(
                BusinessCase.tenant_id == self.tenant_id,
                BusinessCaseRevision.tenant_id == self.tenant_id,
                BusinessCase.project_workspace_id == workspace.id,
            )
        ).all()
        for _case, revision in cases:
            result.append(
                {
                    "kind": "BUSINESS_CASE",
                    "id": revision.id,
                    "reference": f"business-case-revision:{revision.id}",
                    "version": revision.revision_number,
                    "hash": _hash(
                        {
                            "content": revision.content_hash,
                            "readiness": revision.readiness_hash,
                            "source": revision.source_snapshot_hash,
                        }
                    ),
                    "source_current": revision.status == "COMPLETED",
                    "status": revision.status,
                    "as_of": revision.as_of_date.isoformat(),
                    "items": [],
                    "scope": deepcopy(revision.scope_json),
                    "assumptions": deepcopy(revision.assumptions_json),
                    "amount": None,
                    "currency": None,
                    "warning": "BUSINESS_CASE_IS_CONTEXT_NOT_ESTIMATE_POPULATION",
                }
            )
        budget_rows = self.db.execute(
            select(PortfolioBudgetScenario, PortfolioBudgetScenarioProject)
            .join(
                PortfolioBudgetScenarioProject, PortfolioBudgetScenarioProject.scenario_id == PortfolioBudgetScenario.id
            )
            .where(
                PortfolioBudgetScenario.tenant_id == self.tenant_id,
                PortfolioBudgetScenarioProject.tenant_id == self.tenant_id,
                PortfolioBudgetScenarioProject.project_workspace_id == workspace.id,
                PortfolioBudgetScenario.status.notin_(["VOIDED", "SUPERSEDED"]),
            )
        ).all()
        for scenario, membership in budget_rows:
            item = {
                "ref": f"PORTFOLIO_BUDGET:{membership.id}",
                "amount": float(membership.cost_value),
                "currency": membership.currency,
                "unit": membership.currency,
                "capex": float(membership.capex_amount) if membership.capex_amount is not None else None,
                "expense": float(membership.expense_amount) if membership.expense_amount is not None else None,
                "unclassified": float(membership.unclassified_amount),
                "basis_date": membership.cost_as_of_date.isoformat(),
            }
            result.append(
                {
                    "kind": "PORTFOLIO_BUDGET",
                    "id": membership.id,
                    "reference": f"portfolio-budget-project:{membership.id}",
                    "version": scenario.scenario_revision,
                    "hash": _hash({"scenario": scenario.scenario_hash, "row": membership.row_hash, "item": item}),
                    "source_current": scenario.status == "FROZEN",
                    "status": scenario.status,
                    "amount": float(membership.cost_value),
                    "currency": membership.currency,
                    "items": [item],
                    "as_of": membership.cost_as_of_date.isoformat(),
                }
            )
        operational = self.operational_project(workspace)
        if operational:
            accounts = self.db.scalars(
                select(ControlAccount)
                .where(ControlAccount.tenant_id == self.tenant_id, ControlAccount.project_id == operational.id)
                .order_by(ControlAccount.id)
            ).all()
            items = [
                {
                    "ref": f"CONTROL_ACCOUNTS:{r.id}",
                    "amount": r.budget,
                    "currency": operational.currency,
                    "unit": operational.currency,
                    "wbs_id": r.wbs_id,
                    "cbs_code": r.cbs_code,
                    "name": r.name,
                    "version": r.version,
                }
                for r in accounts
            ]
            if items:
                result.append(
                    {
                        "kind": "CONTROL_ACCOUNTS",
                        "id": operational.id,
                        "reference": f"control-account-budget:{operational.id}",
                        "version": max(a.version for a in accounts),
                        "hash": _hash(items),
                        "source_current": True,
                        "items": items,
                        "amount": sum(i["amount"] for i in items),
                        "currency": operational.currency,
                        "warning": "COST_CONTROL_CONTEXT_NOT_AUTOMATICALLY_QRA_READY",
                    }
                )
            imports = self.db.scalars(
                select(ScheduleImport)
                .where(ScheduleImport.tenant_id == self.tenant_id, ScheduleImport.project_id == operational.id)
                .order_by(ScheduleImport.id.desc())
            ).all()
            for row in imports:
                item = {
                    "ref": f"SCHEDULE_COST:{row.id}",
                    "amount": row.total_imported_cost,
                    "currency": row.detected_currency,
                    "unit": row.detected_currency,
                    "basis_date": row.data_date.isoformat() if row.data_date else None,
                }
                result.append(
                    {
                        "kind": "SCHEDULE_COST",
                        "id": row.id,
                        "reference": f"schedule-cost:{row.id}",
                        "version": row.id,
                        "hash": _hash(
                            {
                                "item": item,
                                "currency_confirmed": row.currency_confirmed,
                                "summary": row.cost_source_summary,
                            }
                        ),
                        "source_current": bool(imports and imports[0].id == row.id and row.currency_confirmed),
                        "items": [item],
                        "amount": row.total_imported_cost,
                        "currency": row.detected_currency,
                        "as_of": row.imported_at.isoformat(),
                    }
                )
        return result

    @staticmethod
    def external(ref, basis):
        # This is declared evidence for an assessment, not a new estimate database.
        return {
            **ref,
            "source_current": True,
            "items": deepcopy(basis.get("items", [])),
            "currency": basis.get("currency"),
            "amount": basis.get("total_amount"),
            "as_of": basis.get("basis_date"),
            "authority": "DECLARED_EXTERNAL_REFERENCE_CONTENT_NOT_FETCHED",
            "warnings": ["EXTERNAL_CONTENT_AUTHENTICITY_NOT_VERIFIED"],
        }
