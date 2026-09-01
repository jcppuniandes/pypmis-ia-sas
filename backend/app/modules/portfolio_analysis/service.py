"""Gate 07F derived Portfolio Analysis, Investor Map and Scorecard service."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.portfolio_analysis.schemas import (
    AnalysisFiltersIn,
    AnalysisPreviewOut,
    ConfigurationPreviewOut,
    InvestorMapOut,
    InvestorMapPointOut,
    MetricDefinitionOut,
    PortfolioAnalysisDatasetOut,
    PortfolioAnalysisOverviewOut,
    PortfolioAnalysisReadinessOut,
    PortfolioAnalysisRowOut,
    PortfolioAnalysisSummaryOut,
    PortfolioScorecardOut,
    ProjectAnalysisDetailOut,
)
from app.modules.portfolio_evaluation.models import PortfolioProjectEvaluation
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService
from app.modules.portfolio_planning.models import PortfolioProjectMembership

CONFIGURATION_KIND = "portfolio_analysis_configuration"
DEFAULT_CODE = "gate07f-default"
READY_INPUT = "READY_FOR_PORTFOLIO_ANALYSIS"
READY_OUTPUT = "READY_FOR_PORTFOLIO_SCENARIO_PLANNING"
REWORK_OUTPUT = "GATE07F_REWORK_REQUIRED"


def _metric(
    key: str,
    label: str,
    category: str,
    data_type: str,
    *,
    x: bool = False,
    y: bool = False,
    size: bool = False,
    color: bool = False,
    filterable: bool = False,
    scorecard: bool = True,
    aggregation: list[str] | None = None,
    formatting: str = "text",
    null_behavior: str = "show_na",
    non_negative: bool = False,
    currency_sensitive: bool = False,
) -> dict[str, Any]:
    return {
        "metric_key": key,
        "label": label,
        "category": category,
        "data_type": data_type,
        "allowed_for_x_axis": x,
        "allowed_for_y_axis": y,
        "allowed_for_size": size,
        "allowed_for_color": color,
        "allowed_for_filter": filterable,
        "allowed_for_scorecard": scorecard,
        "aggregation_support": aggregation or [],
        "formatting": formatting,
        "null_behavior": null_behavior,
        "non_negative": non_negative,
        "currency_sensitive": currency_sensitive,
    }


DEFAULT_METRIC_CATALOG: list[dict[str, Any]] = [
    _metric(
        "portfolio_evaluation_score",
        "Portfolio Evaluation Score",
        "PORTFOLIO_SCORE",
        "SCORE",
        x=True,
        y=True,
        size=True,
        filterable=True,
        aggregation=["average", "min", "max"],
        formatting="score_0_100",
        non_negative=True,
    ),
    _metric(
        "portfolio_rank",
        "Portfolio Rank",
        "PORTFOLIO_SCORE",
        "NUMBER",
        x=True,
        y=True,
        filterable=True,
        formatting="integer",
        non_negative=True,
    ),
    _metric(
        "strategic_alignment_score",
        "Strategic Alignment",
        "STRATEGIC",
        "SCORE",
        x=True,
        y=True,
        size=True,
        filterable=True,
        aggregation=["average", "min", "max"],
        formatting="score_0_100",
        non_negative=True,
    ),
    _metric(
        "proposal_score",
        "Proposal Score",
        "STRATEGIC",
        "SCORE",
        x=True,
        y=True,
        size=True,
        filterable=True,
        aggregation=["average"],
        formatting="score_0_100",
        non_negative=True,
    ),
    _metric(
        "risk_score",
        "Risk Rating",
        "RISK",
        "SCORE",
        x=True,
        y=True,
        size=True,
        filterable=True,
        aggregation=["average"],
        formatting="decimal_1",
        non_negative=True,
    ),
    _metric(
        "rom_cost",
        "ROM Cost",
        "FINANCIAL_ROM",
        "NUMBER",
        x=True,
        y=True,
        size=True,
        filterable=True,
        aggregation=["sum_when_currency_compatible"],
        formatting="currency_with_code",
        non_negative=True,
        currency_sensitive=True,
    ),
    _metric(
        "planned_duration_days",
        "Planned Duration",
        "SCHEDULE",
        "NUMBER",
        x=True,
        y=True,
        size=True,
        filterable=True,
        aggregation=["average"],
        formatting="days",
        non_negative=True,
    ),
    _metric("target_start", "Target Start", "SCHEDULE", "DATE", filterable=True, formatting="date"),
    _metric("target_finish", "Target Finish", "SCHEDULE", "DATE", filterable=True, formatting="date"),
    _metric(
        "project_type",
        "Project Type",
        "CLASSIFICATION",
        "CATEGORY",
        color=True,
        filterable=True,
    ),
    _metric(
        "strategic_objective",
        "Strategic Objective",
        "STRATEGIC",
        "CATEGORY",
        color=True,
        filterable=True,
    ),
    _metric("risk_bucket", "Risk Bucket", "RISK", "CATEGORY", color=True, filterable=True),
    _metric(
        "priority_bucket",
        "Priority Bucket",
        "PORTFOLIO_SCORE",
        "CATEGORY",
        color=True,
        filterable=True,
    ),
    _metric("planning_stage", "Planning Stage", "PROJECT_METADATA", "CATEGORY", color=True, filterable=True),
    _metric(
        "membership_source",
        "Membership Source",
        "PROJECT_METADATA",
        "CATEGORY",
        color=True,
        filterable=True,
    ),
    _metric("currency", "Currency", "FINANCIAL_ROM", "CATEGORY", color=True, filterable=True),
    _metric("project_number", "Project Number", "PROJECT_METADATA", "TEXT", scorecard=True),
    _metric("project_name", "Project Name", "PROJECT_METADATA", "TEXT", scorecard=True),
]

DEFAULT_CONFIGURATION: dict[str, Any] = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "applicable_governance_models": ["CAPITAL_OWNER"],
    "metric_catalog": DEFAULT_METRIC_CATALOG,
    "investor_map": {
        "x_axis": "portfolio_evaluation_score",
        "y_axis": "strategic_alignment_score",
        "size": "rom_cost",
        "color": "risk_bucket",
        "reference_lines": [
            {"axis": "x", "value": 70, "label": "Portfolio score reference"},
            {"axis": "y", "value": 70, "label": "Strategic alignment reference"},
        ],
    },
    "scorecard": {
        "columns": [
            "portfolio_rank",
            "project_number",
            "project_name",
            "portfolio_evaluation_score",
            "strategic_alignment_score",
            "risk_score",
            "proposal_score",
            "rom_cost",
            "currency",
            "target_start",
            "target_finish",
            "project_type",
            "strategic_objective",
            "membership_source",
        ],
        "default_sort": [{"metric_key": "portfolio_rank", "direction": "asc"}],
    },
    "buckets": {
        "priority": {"high_min": 75, "medium_min": 50, "labels": ["HIGH", "MEDIUM", "LOW"]},
        "risk": {"high_min": 4, "medium_min": 3, "labels": ["HIGH", "MEDIUM", "LOW"]},
    },
    "filters": [
        "project_type",
        "strategic_objective",
        "risk_bucket",
        "priority_bucket",
        "portfolio_evaluation_score",
        "rom_cost",
        "target_start",
        "target_finish",
        "membership_source",
        "planning_stage",
    ],
    "readiness": {
        "core_required_metrics": [
            "portfolio_evaluation_score",
            "strategic_alignment_score",
            "risk_score",
        ],
        "budget_required_metrics": ["rom_cost", "currency"],
        "resource_required_metrics": ["target_start", "target_finish"],
    },
    "snapshot_policy": "derived_on_demand",
}


class PortfolioAnalysisService:
    def __init__(
        self,
        db: Session,
        tenant_id: int,
        actor_id: int,
        context: EnterprisePermissionContext | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    def ensure_seed(self) -> None:
        existing = self.db.scalar(
            select(AdminConfiguration.id).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == DEFAULT_CODE,
            )
        )
        if existing is not None:
            return
        content = deepcopy(DEFAULT_CONFIGURATION)
        self.db.add(
            AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=CONFIGURATION_KIND,
                code=DEFAULT_CODE,
                name="Default Portfolio Analysis Configuration",
                description="Gate 07F starter configuration. Review and publish explicitly before USER analysis.",
                status="draft",
                revision=1,
                version=1,
                content_json=content,
                content_hash=_hash(content),
                created_by_user_id=self.actor_id,
            )
        )
        self._event("portfolio_analysis.configuration_seeded_as_draft", "AdminConfiguration", None, {})
        self.db.commit()

    # ------------------------------------------------------------------
    # USER MODE derived analysis
    # ------------------------------------------------------------------
    def overview(
        self,
        portfolio_id: int,
        filters: AnalysisFiltersIn | None = None,
        expected_analysis_hash: str | None = None,
    ) -> PortfolioAnalysisOverviewOut:
        dataset, content = self._build_dataset(portfolio_id, filters or AnalysisFiltersIn())
        self._assert_expected_hash(dataset, expected_analysis_hash)
        return self._overview_from_dataset(dataset, content)

    def dataset(self, portfolio_id: int, filters: AnalysisFiltersIn | None = None) -> PortfolioAnalysisDatasetOut:
        return self._build_dataset(portfolio_id, filters or AnalysisFiltersIn())[0]

    def investor_map(self, portfolio_id: int, filters: AnalysisFiltersIn | None = None) -> InvestorMapOut:
        dataset, content = self._build_dataset(portfolio_id, filters or AnalysisFiltersIn())
        return self._investor_map(dataset, content)

    def scorecard(self, portfolio_id: int, filters: AnalysisFiltersIn | None = None) -> PortfolioScorecardOut:
        dataset, content = self._build_dataset(portfolio_id, filters or AnalysisFiltersIn())
        return self._scorecard(dataset, content)

    def readiness(self, portfolio_id: int) -> PortfolioAnalysisReadinessOut:
        dataset, content = self._build_dataset(portfolio_id, AnalysisFiltersIn())
        return self._readiness(dataset, content)

    def preview(
        self,
        portfolio_id: int,
        filters: AnalysisFiltersIn,
        expected_analysis_hash: str | None,
    ) -> AnalysisPreviewOut:
        dataset, content = self._build_dataset(portfolio_id, filters)
        self._assert_expected_hash(dataset, expected_analysis_hash)
        self._event(
            "portfolio_analysis.previewed",
            "EnterpriseWorkspace",
            portfolio_id,
            {"analysis_hash": dataset.analysis_hash, "persisted": False},
        )
        self.db.commit()
        return AnalysisPreviewOut(persisted=False, overview=self._overview_from_dataset(dataset, content))

    def project_detail(self, portfolio_id: int, project_id: int) -> ProjectAnalysisDetailOut:
        dataset, _content = self._build_dataset(portfolio_id, AnalysisFiltersIn())
        row = next((item for item in dataset.rows if item.project_workspace_id == project_id), None)
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_IN_CURRENT_ANALYSIS"})
        evaluations = list(
            self.db.scalars(
                select(PortfolioProjectEvaluation)
                .where(
                    PortfolioProjectEvaluation.tenant_id == self.tenant_id,
                    PortfolioProjectEvaluation.portfolio_workspace_id == portfolio_id,
                    PortfolioProjectEvaluation.project_workspace_id == project_id,
                )
                .order_by(PortfolioProjectEvaluation.evaluation_version.desc())
            ).all()
        )
        current = next(item for item in evaluations if item.id == row.evaluation_id)
        source = dict(current.source_snapshot_json or {})
        return ProjectAnalysisDetailOut(
            row=row,
            evaluation_history=[
                {
                    "id": item.id,
                    "version": item.evaluation_version,
                    "status": item.status,
                    "score": str(item.normalized_score),
                    "completed_at": item.completed_at,
                    "matrix_hash": item.matrix_hash,
                    "source_snapshot_hash": item.source_snapshot_hash,
                }
                for item in evaluations
            ],
            strategic_context={
                "strategic_objectives": source.get("strategic_objectives", []),
                "proposal_score": source.get("proposal_score"),
                "expected_benefits": source.get("expected_benefits"),
                "risk_summary": source.get("risk_summary", []),
            },
            membership=dict(source.get("membership", {})),
            planning_entry={
                "hash": current.planning_entry_hash,
                "snapshot": source.get("planning_entry_snapshot", {}),
            },
        )

    def _build_dataset(
        self,
        portfolio_id: int,
        filters: AnalysisFiltersIn,
        *,
        configuration_override: dict | None = None,
        configuration_record: AdminConfiguration | None = None,
    ) -> tuple[PortfolioAnalysisDatasetOut, dict]:
        portfolio = self._workspace(portfolio_id)
        self._assert_workspace_type(portfolio, "portfolio")
        self._assert_scope(portfolio_id)
        record = configuration_record or self._effective_configuration(portfolio, published_only=True)
        content = deepcopy(
            configuration_override
            if configuration_override is not None
            else record.content_json
            if record
            else DEFAULT_CONFIGURATION
        )
        issues = self._configuration_issues(content)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "issues": issues})

        blockers: list[str] = []
        if configuration_override is None and record is None:
            blockers.append("PUBLISHED_PORTFOLIO_ANALYSIS_CONFIGURATION_REQUIRED")
        evaluation_service = PortfolioEvaluationService(self.db, self.tenant_id, self.actor_id, self.context)
        gate07e = evaluation_service.readiness(portfolio_id)
        if not gate07e.can_enter_portfolio_analysis or gate07e.final_output != READY_INPUT:
            blockers.append("READY_FOR_PORTFOLIO_ANALYSIS_REQUIRED")
            blockers.extend(f"GATE07E_{item}" for item in gate07e.blocking_issues)
        ranking, prioritization_hash = evaluation_service.ranking_projection(portfolio_id)

        memberships = list(
            self.db.scalars(
                select(PortfolioProjectMembership)
                .where(
                    PortfolioProjectMembership.tenant_id == self.tenant_id,
                    PortfolioProjectMembership.portfolio_workspace_id == portfolio_id,
                    PortfolioProjectMembership.status == "ACTIVE",
                )
                .order_by(PortfolioProjectMembership.project_workspace_id)
            ).all()
        )
        membership_by_project = {item.project_workspace_id: item for item in memberships}
        membership_set_hash = _hash(
            [
                {
                    "id": item.id,
                    "project_workspace_id": item.project_workspace_id,
                    "status": item.status,
                    "source": item.membership_source,
                    "revision_version": item.revision_version,
                }
                for item in memberships
            ]
        )
        rows: list[PortfolioAnalysisRowOut] = []
        evaluation_fingerprint: list[dict] = []
        for ranked in ranking:
            project = self._workspace(ranked.project_workspace_id)
            membership = membership_by_project.get(project.id)
            if membership is None or self._governance_model(project) != "CAPITAL_OWNER":
                continue
            evaluation = self.db.scalar(
                select(PortfolioProjectEvaluation).where(
                    PortfolioProjectEvaluation.id == ranked.evaluation_id,
                    PortfolioProjectEvaluation.tenant_id == self.tenant_id,
                    PortfolioProjectEvaluation.status == "COMPLETED",
                )
            )
            if evaluation is None or evaluation.completed_at is None:
                continue
            source = dict(evaluation.source_snapshot_json or {})
            entry = dict(source.get("planning_entry_snapshot") or {})
            target_start = _parse_date(source.get("target_start") or entry.get("target_start"))
            target_finish = _parse_date(source.get("target_finish") or entry.get("target_finish"))
            duration = (
                (target_finish - target_start).days
                if target_start and target_finish and target_finish >= target_start
                else None
            )
            currency = str(source.get("currency") or entry.get("currency") or "").upper() or None
            risk_score = Decimal(evaluation.risk_score)
            score = Decimal(evaluation.normalized_score)
            evaluation_hash = _hash(
                {
                    "id": evaluation.id,
                    "version": evaluation.evaluation_version,
                    "matrix_hash": evaluation.matrix_hash,
                    "source_snapshot_hash": evaluation.source_snapshot_hash,
                    "planning_entry_hash": evaluation.planning_entry_hash,
                    "score": str(score),
                    "strategic_alignment": str(evaluation.strategic_alignment_score),
                    "risk": str(risk_score),
                }
            )
            evaluation_fingerprint.append({"project_workspace_id": project.id, "hash": evaluation_hash})
            rows.append(
                PortfolioAnalysisRowOut(
                    portfolio_workspace_id=portfolio_id,
                    project_workspace_id=project.id,
                    portfolio_membership_id=membership.id,
                    project_number=project.code,
                    project_name=project.name,
                    project_type=_text(source.get("project_type") or entry.get("project_type")),
                    governance_model="CAPITAL_OWNER",
                    workspace_status=project.status,
                    planning_stage=_text(entry.get("planning_stage") or "PORTFOLIO_PLANNING"),
                    strategic_objectives=list(
                        source.get("strategic_objectives") or entry.get("strategic_objectives") or []
                    ),
                    proposal_score=_optional_decimal(source.get("proposal_score") or entry.get("proposal_score")),
                    portfolio_evaluation_score=score,
                    portfolio_rank=ranked.rank,
                    strategic_alignment_score=Decimal(evaluation.strategic_alignment_score),
                    risk_score=risk_score,
                    risk_bucket=self._bucket(risk_score, dict(content.get("buckets", {})).get("risk", {})),
                    priority_bucket=self._bucket(score, dict(content.get("buckets", {})).get("priority", {})),
                    rom_cost=_optional_decimal(source.get("rom_cost") or entry.get("rom_cost")),
                    currency=currency,
                    target_start=target_start,
                    target_finish=target_finish,
                    planned_duration_days=duration,
                    expected_benefits=_text(source.get("expected_benefits") or entry.get("expected_benefits")),
                    risk_summary=list(source.get("risk_summary") or entry.get("risk_summary") or []),
                    sponsor=_text(source.get("sponsor") or entry.get("sponsor")),
                    project_manager=_text(source.get("project_manager") or entry.get("project_manager")),
                    membership_source=membership.membership_source,
                    evaluation_id=evaluation.id,
                    evaluation_version=evaluation.evaluation_version,
                    evaluation_date=evaluation.completed_at,
                    planning_entry_hash=evaluation.planning_entry_hash,
                    evaluation_hash=evaluation_hash,
                    prioritization_hash=prioritization_hash,
                )
            )
        evaluation_set_hash = _hash(evaluation_fingerprint)
        configuration_hash = _hash(content)
        analysis_hash = _hash(
            {
                "portfolio_workspace_id": portfolio_id,
                "membership_set_hash": membership_set_hash,
                "evaluation_set_hash": evaluation_set_hash,
                "prioritization_hash": prioritization_hash,
                "analysis_configuration_hash": configuration_hash,
            }
        )
        currencies = sorted({item.currency for item in rows if item.rom_cost is not None and item.currency})
        warnings: list[str] = []
        if len(currencies) > 1:
            warnings.append("MULTI_CURRENCY_NOT_NORMALIZED")
        if any(item.rom_cost is not None and not item.currency for item in rows):
            warnings.append("ROM_COST_CURRENCY_MISSING")
        if not rows:
            blockers.append("ELIGIBLE_ANALYSIS_DATASET_REQUIRED")
        filtered = [item for item in rows if self._matches(item, filters)]
        dataset = PortfolioAnalysisDatasetOut(
            portfolio_workspace_id=portfolio_id,
            generated_at=utc_now(),
            metric_catalog=[MetricDefinitionOut.model_validate(item) for item in content.get("metric_catalog", [])],
            rows=filtered,
            filters_applied=filters.model_dump(mode="json", exclude_none=True),
            source_prioritization_hash=prioritization_hash,
            membership_set_hash=membership_set_hash,
            evaluation_set_hash=evaluation_set_hash,
            configuration_hash=configuration_hash,
            analysis_hash=analysis_hash,
            warnings=sorted(set(warnings)),
            blockers=sorted(set(blockers)),
        )
        return dataset, content

    def _overview_from_dataset(
        self, dataset: PortfolioAnalysisDatasetOut, content: dict
    ) -> PortfolioAnalysisOverviewOut:
        return PortfolioAnalysisOverviewOut(
            dataset=dataset,
            investor_map=self._investor_map(dataset, content),
            scorecard=self._scorecard(dataset, content),
            summary=self._summary(dataset),
            readiness=self._readiness(dataset, content),
        )

    def _investor_map(self, dataset: PortfolioAnalysisDatasetOut, content: dict) -> InvestorMapOut:
        config = dict(content.get("investor_map", {}))
        x_key = str(config.get("x_axis"))
        y_key = str(config.get("y_axis"))
        size_key = str(config.get("size") or "") or None
        color_key = str(config.get("color"))
        size_applied = bool(size_key)
        warnings = list(dataset.warnings)
        if size_key == "rom_cost" and any(
            warning in dataset.warnings for warning in ("MULTI_CURRENCY_NOT_NORMALIZED", "ROM_COST_CURRENCY_MISSING")
        ):
            size_applied = False
            warnings.append("ROM_COST_BUBBLE_SIZE_DISABLED")
        points: list[InvestorMapPointOut] = []
        for row in dataset.rows:
            source_size = self._metric_value(row, size_key) if size_key else None
            bubble_size = _optional_decimal(source_size) if size_applied else None
            points.append(
                InvestorMapPointOut(
                    project_workspace_id=row.project_workspace_id,
                    project_number=row.project_number,
                    project_name=row.project_name,
                    portfolio_rank=row.portfolio_rank,
                    x=self._metric_value(row, x_key),
                    y=self._metric_value(row, y_key),
                    bubble_size=max(Decimal("1"), bubble_size or Decimal("1")),
                    bubble_size_source=source_size,
                    color=str(self._metric_value(row, color_key) or "UNCLASSIFIED"),
                    tooltip={
                        "rank": row.portfolio_rank,
                        "evaluation_score": str(row.portfolio_evaluation_score),
                        "strategic_alignment": str(row.strategic_alignment_score),
                        "risk": str(row.risk_score),
                        "rom_cost": str(row.rom_cost) if row.rom_cost is not None else None,
                        "currency": row.currency,
                        "target_start": row.target_start,
                        "target_finish": row.target_finish,
                        "strategic_objectives": row.strategic_objectives,
                    },
                )
            )
        return InvestorMapOut(
            portfolio_workspace_id=dataset.portfolio_workspace_id,
            x_metric=x_key,
            y_metric=y_key,
            size_metric=size_key,
            color_metric=color_key,
            size_metric_applied=size_applied,
            reference_lines=list(config.get("reference_lines", [])),
            points=points,
            analysis_hash=dataset.analysis_hash,
            warnings=sorted(set(warnings)),
        )

    def _scorecard(self, dataset: PortfolioAnalysisDatasetOut, content: dict) -> PortfolioScorecardOut:
        config = dict(content.get("scorecard", {}))
        columns = [str(item) for item in config.get("columns", [])]
        rows = [
            {key: self._metric_value(item, key) for key in columns}
            | {"project_workspace_id": item.project_workspace_id}
            for item in dataset.rows
        ]
        sort_rules = list(config.get("default_sort", []))
        for rule in reversed(sort_rules):
            key = str(rule.get("metric_key"))
            reverse = str(rule.get("direction", "asc")).lower() == "desc"
            rows.sort(key=lambda item: (item.get(key) is None, item.get(key)), reverse=reverse)
        return PortfolioScorecardOut(
            portfolio_workspace_id=dataset.portfolio_workspace_id,
            columns=columns,
            default_sort=sort_rules,
            rows=rows,
            analysis_hash=dataset.analysis_hash,
            warnings=dataset.warnings,
        )

    def _summary(self, dataset: PortfolioAnalysisDatasetOut) -> PortfolioAnalysisSummaryOut:
        rows = dataset.rows
        count = len(rows)
        scores = [item.portfolio_evaluation_score for item in rows]
        costs = [item.rom_cost for item in rows if item.rom_cost is not None]
        currencies = sorted({item.currency for item in rows if item.rom_cost is not None and item.currency})
        compatible = len(currencies) == 1 and len(costs) == count and count > 0
        distributions = {
            "project_type": self._distribution(item.project_type or "UNCLASSIFIED" for item in rows),
            "priority_bucket": self._distribution(item.priority_bucket for item in rows),
            "risk_bucket": self._distribution(item.risk_bucket for item in rows),
            "planning_stage": self._distribution(item.planning_stage or "UNCLASSIFIED" for item in rows),
            "strategic_objective": self._objective_distribution(rows),
        }
        return PortfolioAnalysisSummaryOut(
            eligible_projects=count,
            evaluated_projects=count,
            average_portfolio_score=(sum(scores) / Decimal(count)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if count
            else None,
            high_priority_count=sum(item.priority_bucket == "HIGH" for item in rows),
            high_risk_count=sum(item.risk_bucket == "HIGH" for item in rows),
            rom_cost_coverage_percent=(Decimal(len(costs)) * Decimal("100") / Decimal(count)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if count
            else Decimal("0"),
            rom_cost_total=sum(costs, Decimal("0")) if compatible else None,
            rom_cost_currency=currencies[0] if compatible else None,
            distributions=distributions,
        )

    def _readiness(self, dataset: PortfolioAnalysisDatasetOut, content: dict) -> PortfolioAnalysisReadinessOut:
        rows = dataset.rows
        readiness_config = dict(content.get("readiness", {}))
        all_metrics = sorted(
            set(readiness_config.get("core_required_metrics", []))
            | set(readiness_config.get("budget_required_metrics", []))
            | set(readiness_config.get("resource_required_metrics", []))
        )
        coverage = {
            key: (
                Decimal(sum(self._metric_value(item, key) not in (None, "") for item in rows))
                * Decimal("100")
                / Decimal(len(rows))
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if rows
            else Decimal("0")
            for key in all_metrics
        }
        blockers = list(dataset.blockers)
        core = [str(item) for item in readiness_config.get("core_required_metrics", [])]
        missing_core = [item for item in core if coverage.get(item, Decimal("0")) < Decimal("100")]
        if missing_core:
            blockers.append("CORE_ANALYSIS_METRIC_COVERAGE_INCOMPLETE")
        ready = bool(rows) and not blockers
        budget_required = [str(item) for item in readiness_config.get("budget_required_metrics", [])]
        resource_required = [str(item) for item in readiness_config.get("resource_required_metrics", [])]
        currency_compatible = (
            "MULTI_CURRENCY_NOT_NORMALIZED" not in dataset.warnings
            and "ROM_COST_CURRENCY_MISSING" not in dataset.warnings
        )
        budget_ready = (
            ready
            and currency_compatible
            and all(coverage.get(item, Decimal("0")) == Decimal("100") for item in budget_required)
        )
        resource_ready = ready and all(coverage.get(item, Decimal("0")) == Decimal("100") for item in resource_required)
        actions = [
            "can_view_portfolio_analysis",
            "can_view_investor_map",
            "can_view_scorecard",
            "can_preview_analysis",
        ]
        if ready:
            actions.append("can_enter_portfolio_scenario_planning")
        return PortfolioAnalysisReadinessOut(
            portfolio_workspace_id=dataset.portfolio_workspace_id,
            status="READY" if ready else "BLOCKED",
            analysis_hash=dataset.analysis_hash,
            source_prioritization_hash=dataset.source_prioritization_hash,
            membership_set_hash=dataset.membership_set_hash,
            evaluation_set_hash=dataset.evaluation_set_hash,
            configuration_hash=dataset.configuration_hash,
            eligible_project_count=len(rows),
            metric_coverage=coverage,
            warnings=dataset.warnings,
            blockers=sorted(set(blockers)),
            allowed_actions=actions,
            can_enter_budget_planning=budget_ready,
            can_enter_resource_planning=resource_ready,
            can_enter_portfolio_scenario_planning=ready,
            final_output=READY_OUTPUT if ready else REWORK_OUTPUT,
        )

    # ------------------------------------------------------------------
    # ADMIN MODE configuration governance
    # ------------------------------------------------------------------
    def configurations(self) -> list[AdminConfiguration]:
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
        portfolio_id: int | None,
        configuration_id: int | None,
        content_override: dict | None,
    ) -> ConfigurationPreviewOut:
        workspace = self._workspace(portfolio_id) if portfolio_id else None
        selected = self._configuration(configuration_id) if configuration_id else None
        if selected is None:
            selected = (
                self._effective_configuration(workspace, published_only=True) if workspace else self._tenant_published()
            )
        if selected is None:
            selected = self.db.scalar(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                )
                .order_by(AdminConfiguration.revision.desc())
            )
        content = deepcopy(
            content_override
            if content_override is not None
            else selected.content_json
            if selected
            else DEFAULT_CONFIGURATION
        )
        issues = self._configuration_issues(content)
        dataset = None
        warnings: list[str] = []
        blockers: list[str] = []
        if portfolio_id and not issues:
            dataset, _ = self._build_dataset(
                portfolio_id,
                AnalysisFiltersIn(),
                configuration_override=content,
                configuration_record=selected,
            )
            warnings = dataset.warnings
            blockers = dataset.blockers
        self._event(
            "portfolio_analysis.configuration_previewed",
            "AdminConfiguration",
            selected.id if selected else None,
            {"portfolio_workspace_id": portfolio_id, "persisted": False},
        )
        self.db.commit()
        return ConfigurationPreviewOut(
            portfolio_workspace_id=portfolio_id,
            path=[self._workspace_summary(item) for item in self._workspace_path(workspace)] if workspace else [],
            effective=content,
            source={
                "id": selected.id if selected else None,
                "code": selected.code if selected else DEFAULT_CODE,
                "revision": selected.revision if selected else 0,
                "status": selected.status if selected else "draft",
                "hash": _hash(content),
                "preview": content_override is not None,
                "resolution_chain": [item.id for item in self._workspace_path(workspace)] if workspace else [],
            },
            publishable=not issues,
            validation_issues=issues,
            dataset_preview=dataset,
            warnings=warnings,
            blockers=blockers,
            persisted=False,
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id)
        self._check_version(source, expected_version)
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(AdminConfiguration.revision), 0)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.code == source.code,
                    )
                )
                or 0
            )
            + 1
        )
        clone = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=source.code,
            name=source.name,
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=deepcopy(source.content_json or {}),
            content_hash=source.content_hash or _hash(source.content_json),
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._event("portfolio_analysis.configuration_cloned", "AdminConfiguration", clone.id, {"source_id": source.id})
        self.db.commit()
        self.db.refresh(clone)
        return clone

    def update_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        name: str,
        description: str,
        content: dict,
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_IMMUTABLE"})
        self._validate_configuration(content)
        record.name = name.strip()
        record.description = description.strip()
        record.content_json = deepcopy(content)
        record.content_hash = _hash(content)
        record.version += 1
        record.updated_at = utc_now()
        self._event("portfolio_analysis.configuration_updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_IMMUTABLE"})
        self._validate_configuration(dict(record.content_json or {}))
        record.status = "published"
        record.content_hash = _hash(record.content_json)
        record.published_at = utc_now()
        record.updated_at = record.published_at
        record.version += 1
        self._event("portfolio_analysis.configuration_published", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    # ------------------------------------------------------------------
    # Validation, inheritance and helpers
    # ------------------------------------------------------------------
    def _configuration_issues(self, content: dict) -> list[str]:
        issues: list[str] = []
        scope = dict(content.get("scope", {}))
        if scope.get("type", "tenant") not in {"tenant", "enterprise", "business-unit", "portfolio"}:
            issues.append("INVALID_CONFIGURATION_SCOPE")
        if scope.get("type", "tenant") != "tenant" and not scope.get("workspace_id"):
            issues.append("SCOPED_CONFIGURATION_WORKSPACE_REQUIRED")
        if list(content.get("applicable_governance_models", [])) != ["CAPITAL_OWNER"]:
            issues.append("GATE07F_ONLY_SUPPORTS_CAPITAL_OWNER")
        catalog_items = list(content.get("metric_catalog", []))
        catalog = {str(item.get("metric_key")): item for item in catalog_items if item.get("metric_key")}
        if not catalog_items or len(catalog) != len(catalog_items):
            issues.append("INVALID_METRIC_CATALOG")
        investor = dict(content.get("investor_map", {}))
        for field, capability in (
            ("x_axis", "allowed_for_x_axis"),
            ("y_axis", "allowed_for_y_axis"),
            ("size", "allowed_for_size"),
            ("color", "allowed_for_color"),
        ):
            key = str(investor.get(field) or "")
            metric = catalog.get(key)
            if not metric:
                issues.append(f"UNKNOWN_{field.upper()}_METRIC")
            elif not metric.get(capability):
                issues.append(f"METRIC_NOT_ALLOWED_FOR_{field.upper()}")
            if field in {"x_axis", "y_axis"} and metric and metric.get("data_type") not in {"NUMBER", "SCORE"}:
                issues.append("UNSUPPORTED_AXIS_TYPE")
            if field == "size" and metric and not metric.get("non_negative"):
                issues.append("BUBBLE_SIZE_METRIC_MUST_BE_NON_NEGATIVE")
        for line in investor.get("reference_lines", []):
            try:
                if line.get("axis") not in {"x", "y"} or not str(line.get("label", "")).strip():
                    raise ValueError
                Decimal(str(line.get("value")))
            except Exception:
                issues.append("INVALID_REFERENCE_LINE")
        scorecard = dict(content.get("scorecard", {}))
        columns = [str(item) for item in scorecard.get("columns", [])]
        if not columns or len(columns) != len(set(columns)):
            issues.append("INVALID_SCORECARD_COLUMNS")
        if any(key not in catalog or not catalog[key].get("allowed_for_scorecard") for key in columns):
            issues.append("SCORECARD_METRIC_NOT_ALLOWED")
        for rule in scorecard.get("default_sort", []):
            if rule.get("metric_key") not in columns or rule.get("direction") not in {"asc", "desc"}:
                issues.append("INVALID_SCORECARD_SORT")
        configured_filters = [str(item) for item in content.get("filters", [])]
        if any(key not in catalog or not catalog[key].get("allowed_for_filter") for key in configured_filters):
            issues.append("FILTER_METRIC_NOT_ALLOWED")
        for bucket_name in ("priority", "risk"):
            bucket = dict(dict(content.get("buckets", {})).get(bucket_name, {}))
            try:
                high = Decimal(str(bucket.get("high_min")))
                medium = Decimal(str(bucket.get("medium_min")))
                if high <= medium or len(bucket.get("labels", [])) != 3:
                    raise ValueError
            except Exception:
                issues.append(f"INVALID_{bucket_name.upper()}_BUCKETS")
        readiness = dict(content.get("readiness", {}))
        for field in ("core_required_metrics", "budget_required_metrics", "resource_required_metrics"):
            if any(str(key) not in catalog for key in readiness.get(field, [])):
                issues.append("UNKNOWN_READINESS_METRIC")
        serialized = json.dumps(content, ensure_ascii=False).lower()
        forbidden = {
            "portfolio_candidate",
            "analysis_rank",
            "investor_map_rank",
            "global_rank",
            "forced_in",
            "forced_out",
            "investment_approved",
            "execution_authorized",
            "budget_scenario",
            "resource_scenario",
            "fid_approver",
        }
        if any(term in serialized for term in forbidden):
            issues.append("DOWNSTREAM_OR_SELECTION_CAPABILITY_NOT_ALLOWED_IN_GATE07F")
        if content.get("snapshot_policy") != "derived_on_demand":
            issues.append("PERSISTENT_ANALYSIS_SNAPSHOT_NOT_ENABLED")
        return sorted(set(issues))

    def _validate_configuration(self, content: dict) -> None:
        issues = self._configuration_issues(content)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "issues": issues})

    def _effective_configuration(
        self, workspace: EnterpriseWorkspace | None, *, published_only: bool
    ) -> AdminConfiguration | None:
        records = list(
            self.db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    *([AdminConfiguration.status == "published"] if published_only else []),
                )
            ).all()
        )
        path = self._workspace_path(workspace) if workspace else []
        path_ids = {item.id: item for item in path}
        candidates: list[tuple[int, int, AdminConfiguration]] = []
        for record in records:
            scope = dict((record.content_json or {}).get("scope", {}))
            scope_type = str(scope.get("type") or "tenant")
            scope_id = scope.get("workspace_id")
            specificity = 0
            if scope_type != "tenant":
                if scope_id not in path_ids:
                    continue
                scoped = path_ids[int(scope_id)]
                expected = {"enterprise": "enterprise", "business-unit": "business-unit", "portfolio": "portfolio"}.get(
                    scope_type
                )
                if expected and scoped.workspace_type_code != expected:
                    continue
                specificity = {"enterprise": 1, "business-unit": 2, "portfolio": 3}.get(scope_type, 0)
            candidates.append((specificity, record.revision, record))
        return max(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None

    def _tenant_published(self) -> AdminConfiguration | None:
        return self._effective_configuration(None, published_only=True)

    def _configuration(self, configuration_id: int, *, lock: bool = False) -> AdminConfiguration:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.id == configuration_id,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Portfolio analysis configuration not found")
        return record

    @staticmethod
    def _check_version(record: AdminConfiguration, expected: int) -> None:
        if record.version != expected:
            raise HTTPException(status_code=412, detail={"code": "ETAG_MISMATCH"})

    def _assert_expected_hash(self, dataset: PortfolioAnalysisDatasetOut, expected: str | None) -> None:
        if expected is None or expected == dataset.analysis_hash:
            return
        self._event(
            "portfolio_analysis.stale_source_detected",
            "EnterpriseWorkspace",
            dataset.portfolio_workspace_id,
            {"expected": expected, "actual": dataset.analysis_hash},
        )
        self.db.commit()
        raise HTTPException(
            status_code=412,
            detail={"code": "STALE_PORTFOLIO_ANALYSIS_SOURCE", "expected": expected, "actual": dataset.analysis_hash},
        )

    def _workspace(self, workspace_id: int | None) -> EnterpriseWorkspace:
        if workspace_id is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == workspace_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
            )
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace

    @staticmethod
    def _assert_workspace_type(workspace: EnterpriseWorkspace, expected: str) -> None:
        if workspace.workspace_type_code != expected:
            raise HTTPException(status_code=422, detail=f"WORKSPACE_IS_NOT_{expected.upper().replace('-', '_')}")

    def _assert_scope(self, *workspace_ids: int) -> None:
        if self.context is None or self.context.organization_wide:
            return
        if not any(item in self.context.workspace_ids for item in workspace_ids):
            raise HTTPException(status_code=403, detail="Workspace is outside the authorized scope")

    def _workspace_path(self, workspace: EnterpriseWorkspace | None) -> list[EnterpriseWorkspace]:
        if workspace is None:
            return []
        path = [workspace]
        visited = {workspace.id}
        current = workspace
        while current.parent_id is not None:
            parent = self.db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id == current.parent_id,
                )
            )
            if parent is None or parent.id in visited:
                break
            path.append(parent)
            visited.add(parent.id)
            current = parent
        return list(reversed(path))

    @staticmethod
    def _workspace_summary(workspace: EnterpriseWorkspace) -> dict:
        return {
            "id": workspace.id,
            "code": workspace.code,
            "name": workspace.name,
            "workspace_type_code": workspace.workspace_type_code,
            "status": workspace.status,
            "parent_id": workspace.parent_id,
            "version": workspace.version,
        }

    @staticmethod
    def _governance_model(project: EnterpriseWorkspace) -> str:
        context = dict(dict(project.defaults_json or {}).get("_project", {}))
        value = str(context.get("governance_model") or "")
        if not value and context.get("planning_origin") == "STRATEGIC_GATE":
            return "CAPITAL_OWNER"
        return value or "LEGACY"

    @staticmethod
    def _bucket(value: Decimal, config: dict) -> str:
        high = Decimal(str(config.get("high_min", 75)))
        medium = Decimal(str(config.get("medium_min", 50)))
        labels = list(config.get("labels", ["HIGH", "MEDIUM", "LOW"]))
        return str(labels[0] if value >= high else labels[1] if value >= medium else labels[2])

    @staticmethod
    def _metric_value(row: PortfolioAnalysisRowOut, key: str | None) -> Any:
        if not key:
            return None
        if key == "strategic_objective":
            return (
                ", ".join(
                    str(item.get("name") or item.get("code"))
                    for item in row.strategic_objectives
                    if item.get("name") or item.get("code")
                )
                or None
            )
        return getattr(row, key, None)

    @staticmethod
    def _matches(row: PortfolioAnalysisRowOut, filters: AnalysisFiltersIn) -> bool:
        objectives = {str(item.get("code") or item.get("name") or "").lower() for item in row.strategic_objectives}
        return not any(
            (
                filters.project_type and (row.project_type or "").lower() != filters.project_type.lower(),
                filters.strategic_objective and filters.strategic_objective.lower() not in objectives,
                filters.risk_bucket and row.risk_bucket.lower() != filters.risk_bucket.lower(),
                filters.priority_bucket and row.priority_bucket.lower() != filters.priority_bucket.lower(),
                filters.membership_source and row.membership_source.lower() != filters.membership_source.lower(),
                filters.planning_stage and (row.planning_stage or "").lower() != filters.planning_stage.lower(),
                filters.evaluation_score_min is not None
                and row.portfolio_evaluation_score < filters.evaluation_score_min,
                filters.evaluation_score_max is not None
                and row.portfolio_evaluation_score > filters.evaluation_score_max,
                filters.rom_cost_min is not None and (row.rom_cost is None or row.rom_cost < filters.rom_cost_min),
                filters.rom_cost_max is not None and (row.rom_cost is None or row.rom_cost > filters.rom_cost_max),
                filters.target_start_from is not None
                and (row.target_start is None or row.target_start < filters.target_start_from),
                filters.target_finish_to is not None
                and (row.target_finish is None or row.target_finish > filters.target_finish_to),
            )
        )

    @staticmethod
    def _distribution(values) -> list[dict]:
        counts: dict[str, int] = {}
        for value in values:
            counts[str(value)] = counts.get(str(value), 0) + 1
        return [{"key": key, "count": counts[key]} for key in sorted(counts)]

    @staticmethod
    def _objective_distribution(rows: list[PortfolioAnalysisRowOut]) -> list[dict]:
        counts: dict[str, int] = {}
        for row in rows:
            seen: set[str] = set()
            for objective in row.strategic_objectives:
                key = str(objective.get("name") or objective.get("code") or "UNCLASSIFIED")
                if key in seen:
                    continue
                seen.add(key)
                counts[key] = counts.get(key, 0) + 1
        return [{"key": key, "count": counts[key], "overlap_possible": True} for key in sorted(counts)]

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


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
