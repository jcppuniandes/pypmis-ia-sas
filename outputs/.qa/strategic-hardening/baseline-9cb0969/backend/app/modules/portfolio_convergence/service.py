"""Gate 07I governed Portfolio Scenario Convergence and Recommendation service."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.portfolio_budget.models import PortfolioBudgetScenarioProject
from app.modules.portfolio_budget.service import (
    READY_OUTPUT as BUDGET_READY_OUTPUT,
)
from app.modules.portfolio_budget.service import (
    PortfolioBudgetService,
)
from app.modules.portfolio_convergence.models import (
    PortfolioConvergedAlternative,
    PortfolioScenarioConvergence,
)
from app.modules.portfolio_convergence.schemas import (
    ConfigurationPreviewOut,
    ConvergedAlternativeOut,
    ConvergenceComparisonOut,
    ConvergenceCreateIn,
    ConvergenceRefreshPreviewOut,
    ConvergenceUpdateIn,
    InvestmentGatePreparationContractOut,
    PortfolioConvergenceOverviewOut,
    PortfolioRecommendationReadinessOut,
    PortfolioScenarioConvergenceOut,
    RecommendationIn,
)
from app.modules.portfolio_resource.models import PortfolioResourceScenarioProject
from app.modules.portfolio_resource.service import (
    READY_OUTPUT as RESOURCE_READY_OUTPUT,
)
from app.modules.portfolio_resource.service import (
    PortfolioResourceService,
)

CONFIGURATION_KIND = "portfolio_convergence_configuration"
DEFAULT_CODE = "gate07i-default"
READY_OUTPUT = "READY_FOR_INVESTMENT_GATE_PREPARATION"
REWORK_OUTPUT = "GATE07I_REWORK_REQUIRED"

DEFAULT_CONFIGURATION: dict[str, Any] = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "applicable_governance_models": ["CAPITAL_OWNER"],
    "required_budget_branch": True,
    "required_resource_branch": True,
    "require_identical_project_sets": True,
    "forced_conflict_is_blocker": True,
    "allow_conditional_recommendation": False,
    "required_recommendation_fields": [
        "recommendation_reason",
        "risks_acknowledged",
        "decision_support_summary",
    ],
    "recommendation_mode": "SINGLE_RECOMMENDER",
    "recommender_sod_required": False,
    "readiness": {"minimum_alternatives": 1, "require_current_sources": True},
}


class PortfolioConvergenceService:
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

    # Configuration bootstrap --------------------------------------
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
                name="Default Portfolio Scenario Convergence Configuration",
                description="Gate 07I starter policy. Review and publish before USER convergence.",
                status="draft",
                revision=1,
                version=1,
                content_json=content,
                content_hash=_hash(content),
                created_by_user_id=self.actor_id,
            )
        )
        self._event("portfolio_convergence.configuration_seeded_as_draft", "AdminConfiguration", None, {})
        self.db.commit()

    # Convergence lifecycle ----------------------------------------
    def convergences(self, portfolio_id: int) -> list[PortfolioScenarioConvergenceOut]:
        self._portfolio(portfolio_id)
        records = list(
            self.db.scalars(
                select(PortfolioScenarioConvergence)
                .where(
                    PortfolioScenarioConvergence.tenant_id == self.tenant_id,
                    PortfolioScenarioConvergence.portfolio_workspace_id == portfolio_id,
                )
                .order_by(
                    PortfolioScenarioConvergence.logical_code,
                    PortfolioScenarioConvergence.convergence_revision.desc(),
                )
            ).all()
        )
        return [self._convergence_out(record) for record in records]

    def convergence(self, convergence_id: int) -> PortfolioScenarioConvergenceOut:
        return self._convergence_out(self._convergence(convergence_id))

    def create_convergence(self, portfolio_id: int, payload: ConvergenceCreateIn) -> PortfolioScenarioConvergenceOut:
        self._portfolio(portfolio_id)
        replay = self.db.scalar(
            select(PortfolioScenarioConvergence).where(
                PortfolioScenarioConvergence.tenant_id == self.tenant_id,
                PortfolioScenarioConvergence.create_idempotency_key == payload.idempotency_key,
            )
        )
        if replay is not None:
            return self._convergence_out(replay)
        configuration = self._effective_configuration(self._portfolio(portfolio_id), published_only=True)
        if configuration is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "PUBLISHED_PORTFOLIO_CONVERGENCE_CONFIGURATION_REQUIRED"},
            )
        policy = deepcopy(configuration.content_json or {})
        self._validate_configuration(policy)
        required_budget = bool(policy["required_budget_branch"])
        required_resource = bool(policy["required_resource_branch"])
        if payload.required_budget_branch is not None and payload.required_budget_branch != required_budget:
            raise HTTPException(status_code=409, detail={"code": "BUDGET_BRANCH_POLICY_MISMATCH"})
        if payload.required_resource_branch is not None and payload.required_resource_branch != required_resource:
            raise HTTPException(status_code=409, detail={"code": "RESOURCE_BRANCH_POLICY_MISMATCH"})
        snapshot = self._source_snapshot(
            portfolio_id,
            required_budget=required_budget,
            required_resource=required_resource,
            configuration_hash=configuration.content_hash,
            require_ready=True,
        )
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(PortfolioScenarioConvergence.convergence_revision), 0)).where(
                        PortfolioScenarioConvergence.tenant_id == self.tenant_id,
                        PortfolioScenarioConvergence.portfolio_workspace_id == portfolio_id,
                        PortfolioScenarioConvergence.logical_code == payload.logical_code,
                    )
                )
                or 0
            )
            + 1
        )
        record = PortfolioScenarioConvergence(
            tenant_id=self.tenant_id,
            portfolio_workspace_id=portfolio_id,
            logical_code=payload.logical_code,
            convergence_revision=revision,
            name=payload.name,
            description=payload.description,
            status="DRAFT",
            required_budget_branch=required_budget,
            required_resource_branch=required_resource,
            source_analysis_hash=snapshot["analysis_hash"],
            source_membership_set_hash=snapshot["membership_set_hash"],
            source_evaluation_set_hash=snapshot["evaluation_set_hash"],
            budget_planning_hash=snapshot.get("budget_planning_hash"),
            resource_planning_hash=snapshot.get("resource_planning_hash"),
            configuration_id=configuration.id,
            configuration_revision=configuration.revision,
            configuration_hash=configuration.content_hash,
            convergence_source_hash=snapshot["source_hash"],
            source_snapshot_json=snapshot,
            revision_version=1,
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._event(
            "portfolio_convergence.created",
            "PortfolioScenarioConvergence",
            record.id,
            {"required_budget_branch": required_budget, "required_resource_branch": required_resource},
        )
        self.db.commit()
        return self._convergence_out(record)

    def update_convergence(
        self,
        convergence_id: int,
        expected_version: int,
        payload: ConvergenceUpdateIn,
    ) -> PortfolioScenarioConvergenceOut:
        record = self._convergence(convergence_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_editable(record)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "CONVERGENCE_NOT_DRAFT"})
        if payload.name is not None:
            record.name = payload.name
        if payload.description is not None:
            record.description = payload.description
        self._touch(record)
        self._event("portfolio_convergence.updated", "PortfolioScenarioConvergence", record.id, {})
        self.db.commit()
        return self._convergence_out(record)

    # Alternatives --------------------------------------------------
    def add_alternative(
        self,
        convergence_id: int,
        expected_version: int,
        alternative_name: str,
        budget_scenario_id: int | None,
        resource_scenario_id: int | None,
        idempotency_key: str,
    ) -> PortfolioScenarioConvergenceOut:
        record = self._convergence(convergence_id, lock=True)
        replay = self.db.scalar(
            select(PortfolioConvergedAlternative).where(
                PortfolioConvergedAlternative.tenant_id == self.tenant_id,
                PortfolioConvergedAlternative.create_idempotency_key == idempotency_key,
            )
        )
        if replay is not None:
            return self._convergence_out(record)
        self._check_version(record.revision_version, expected_version)
        self._assert_editable(record)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "ALTERNATIVE_REQUIRES_DRAFT_CONVERGENCE"})
        snapshot = self._assert_current_source(record)
        policy = self._record_policy(record)
        alternative_data = self._build_alternative(
            record,
            snapshot,
            policy,
            budget_scenario_id,
            resource_scenario_id,
        )
        duplicate = self.db.scalar(
            select(PortfolioConvergedAlternative.id).where(
                PortfolioConvergedAlternative.tenant_id == self.tenant_id,
                PortfolioConvergedAlternative.convergence_id == record.id,
                PortfolioConvergedAlternative.budget_scenario_id == budget_scenario_id,
                PortfolioConvergedAlternative.resource_scenario_id == resource_scenario_id,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail={"code": "ALTERNATIVE_PAIR_ALREADY_EXISTS"})
        alternative = PortfolioConvergedAlternative(
            tenant_id=self.tenant_id,
            convergence_id=record.id,
            alternative_name=alternative_name,
            create_idempotency_key=idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
            **alternative_data,
        )
        self.db.add(alternative)
        self.db.flush()
        self._touch(record)
        self._event(
            "portfolio_convergence.alternative_added",
            "PortfolioConvergedAlternative",
            alternative.id,
            {
                "convergence_id": record.id,
                "alignment": alternative.alignment_status,
                "feasibility": alternative.feasibility_status,
            },
        )
        self.db.commit()
        return self._convergence_out(record)

    def remove_alternative(
        self,
        convergence_id: int,
        alternative_id: int,
        expected_version: int,
    ) -> PortfolioScenarioConvergenceOut:
        record = self._convergence(convergence_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_editable(record)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "ALTERNATIVE_REQUIRES_DRAFT_CONVERGENCE"})
        alternative = self._alternative(alternative_id)
        if alternative.convergence_id != record.id:
            raise HTTPException(status_code=422, detail={"code": "ALTERNATIVE_CONVERGENCE_MISMATCH"})
        self.db.delete(alternative)
        self._touch(record)
        self._event(
            "portfolio_convergence.alternative_removed",
            "PortfolioConvergedAlternative",
            alternative_id,
            {"convergence_id": record.id},
        )
        self.db.commit()
        return self._convergence_out(record)

    def compare(self, convergence_id: int, alternative_ids: list[int]) -> ConvergenceComparisonOut:
        record = self._convergence(convergence_id)
        if not 2 <= len(alternative_ids) <= 5 or len(set(alternative_ids)) != len(alternative_ids):
            raise HTTPException(status_code=422, detail={"code": "COMPARE_REQUIRES_TWO_TO_FIVE_ALTERNATIVES"})
        alternatives = [self._alternative(item) for item in alternative_ids]
        if any(item.convergence_id != record.id for item in alternatives):
            raise HTTPException(status_code=422, detail={"code": "ALTERNATIVE_CONVERGENCE_MISMATCH"})
        outputs = [self._alternative_out(item) for item in alternatives]
        project_matrix: dict[int, dict] = {}
        for output in outputs:
            for row in output.project_matrix:
                project_id = int(row["project_workspace_id"])
                matrix_row = project_matrix.setdefault(
                    project_id,
                    {
                        "project_workspace_id": project_id,
                        "project_number": row.get("project_number"),
                        "project_name": row.get("project_name"),
                    },
                )
                matrix_row[str(output.id)] = {
                    "budget_state": row.get("budget_state"),
                    "resource_state": row.get("resource_state"),
                    "budget_included": row.get("budget_included", False),
                    "resource_included": row.get("resource_included", False),
                }
        left, right = outputs[0], outputs[1]
        left_projects = set(left.strategic_summary.get("selected_project_ids", []))
        right_projects = set(right.strategic_summary.get("selected_project_ids", []))
        pairwise = {
            "from_alternative_id": left.id,
            "to_alternative_id": right.id,
            "projects_differing": sorted(left_projects ^ right_projects),
            "budget_demand_delta": _decimal(right.budget_summary.get("selected_demand"))
            - _decimal(left.budget_summary.get("selected_demand")),
            "budget_variance_delta": _decimal(right.budget_summary.get("variance"))
            - _decimal(left.budget_summary.get("variance")),
            "resource_overload_delta": int(right.resource_summary.get("overloaded_period_count", 0))
            - int(left.resource_summary.get("overloaded_period_count", 0)),
            "resource_peak_utilization_delta": _decimal(right.resource_summary.get("peak_utilization"))
            - _decimal(left.resource_summary.get("peak_utilization")),
            "score_delta": _decimal(right.strategic_summary.get("average_portfolio_score"))
            - _decimal(left.strategic_summary.get("average_portfolio_score")),
            "high_risk_delta": int(right.risk_summary.get("high_risk_count", 0))
            - int(left.risk_summary.get("high_risk_count", 0)),
            "objective_coverage_delta": int(right.strategic_summary.get("objective_coverage", 0))
            - int(left.strategic_summary.get("objective_coverage", 0)),
        }
        self._event(
            "portfolio_convergence.alternatives_compared",
            "PortfolioScenarioConvergence",
            record.id,
            {"alternative_ids": alternative_ids},
        )
        self.db.commit()
        return ConvergenceComparisonOut(
            convergence_id=record.id,
            alternatives=[
                {
                    "id": item.id,
                    "alternative_name": item.alternative_name,
                    "budget_scenario_id": item.budget_scenario_id,
                    "resource_scenario_id": item.resource_scenario_id,
                    "selected_project_count": len(item.strategic_summary.get("selected_project_ids", [])),
                    "alignment": item.alignment_status,
                    "overall_feasibility": item.feasibility_status,
                    "budget_summary": item.budget_summary,
                    "resource_summary": item.resource_summary,
                    "strategic_summary": item.strategic_summary,
                    "risk_summary": item.risk_summary,
                    "warnings": item.warnings,
                    "blockers": item.blockers,
                }
                for item in outputs
            ],
            feasibility_matrix=[
                {
                    "alternative_id": item.id,
                    "alternative": item.alternative_name,
                    "budget": item.budget_feasibility,
                    "resource": item.resource_feasibility,
                    "alignment": item.alignment_status,
                    "overall": item.feasibility_status,
                }
                for item in outputs
            ],
            project_matrix=sorted(project_matrix.values(), key=lambda item: item["project_workspace_id"]),
            pairwise_delta=pairwise,
            warnings=["COMPARISON_IS_DECISION_SUPPORT_ONLY", "NO_OPTIMIZER_OR_INVESTMENT_APPROVAL"],
        )

    # Source refresh ------------------------------------------------
    def refresh_preview(self, convergence_id: int) -> ConvergenceRefreshPreviewOut:
        record = self._convergence(convergence_id)
        self._assert_editable(record)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "REFRESH_REQUIRES_DRAFT_CONVERGENCE"})
        current = dict(record.source_snapshot_json or {})
        proposed = self._source_snapshot(
            record.portfolio_workspace_id,
            required_budget=record.required_budget_branch,
            required_resource=record.required_resource_branch,
            configuration_hash=self._current_configuration_hash(record.portfolio_workspace_id),
            require_ready=False,
        )
        result = ConvergenceRefreshPreviewOut(
            convergence_id=record.id,
            current_source_hash=record.convergence_source_hash,
            proposed_source_hash=proposed["source_hash"],
            source_current=record.convergence_source_hash == proposed["source_hash"],
            budget_scenarios_added=sorted(
                set(proposed.get("budget_scenario_ids", [])) - set(current.get("budget_scenario_ids", []))
            ),
            budget_scenarios_removed=sorted(
                set(current.get("budget_scenario_ids", [])) - set(proposed.get("budget_scenario_ids", []))
            ),
            resource_scenarios_added=sorted(
                set(proposed.get("resource_scenario_ids", [])) - set(current.get("resource_scenario_ids", []))
            ),
            resource_scenarios_removed=sorted(
                set(current.get("resource_scenario_ids", [])) - set(proposed.get("resource_scenario_ids", []))
            ),
            alternatives_to_rebuild=[item.id for item in self._alternative_records(record.id)],
            warnings=sorted(set(proposed.get("warnings", []))),
            blockers=sorted(set(proposed.get("blockers", []))),
            persisted=False,
        )
        self._event(
            "portfolio_convergence.refresh_previewed",
            "PortfolioScenarioConvergence",
            record.id,
            {"source_current": result.source_current},
        )
        self.db.commit()
        return result

    def apply_refresh(
        self,
        convergence_id: int,
        expected_version: int,
        expected_source_hash: str,
        idempotency_key: str,
    ) -> PortfolioScenarioConvergenceOut:
        record = self._convergence(convergence_id, lock=True)
        if record.refresh_idempotency_key == idempotency_key:
            return self._convergence_out(record)
        self._check_version(record.revision_version, expected_version)
        self._assert_editable(record)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "REFRESH_REQUIRES_DRAFT_CONVERGENCE"})
        configuration = self._effective_configuration(
            self._portfolio(record.portfolio_workspace_id), published_only=True
        )
        if configuration is None:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_REQUIRED"})
        proposed = self._source_snapshot(
            record.portfolio_workspace_id,
            required_budget=record.required_budget_branch,
            required_resource=record.required_resource_branch,
            configuration_hash=configuration.content_hash,
            require_ready=True,
        )
        if proposed["source_hash"] != expected_source_hash:
            raise HTTPException(status_code=412, detail={"code": "STALE_PORTFOLIO_CONVERGENCE_SOURCE"})
        self.db.execute(
            delete(PortfolioConvergedAlternative).where(
                PortfolioConvergedAlternative.tenant_id == self.tenant_id,
                PortfolioConvergedAlternative.convergence_id == record.id,
            )
        )
        record.source_analysis_hash = proposed["analysis_hash"]
        record.source_membership_set_hash = proposed["membership_set_hash"]
        record.source_evaluation_set_hash = proposed["evaluation_set_hash"]
        record.budget_planning_hash = proposed.get("budget_planning_hash")
        record.resource_planning_hash = proposed.get("resource_planning_hash")
        record.configuration_id = configuration.id
        record.configuration_revision = configuration.revision
        record.configuration_hash = configuration.content_hash
        record.convergence_source_hash = proposed["source_hash"]
        record.source_snapshot_json = proposed
        record.refresh_idempotency_key = idempotency_key
        record.recommended_alternative_id = None
        record.recommendation_hash = None
        record.warnings_json = proposed.get("warnings", [])
        record.blockers_json = proposed.get("blockers", [])
        self._touch(record)
        self._event("portfolio_convergence.refresh_applied", "PortfolioScenarioConvergence", record.id, {})
        self.db.commit()
        return self._convergence_out(record)

    # Recommendation lifecycle -------------------------------------
    def submit_review(
        self,
        convergence_id: int,
        expected_version: int,
        idempotency_key: str,
    ) -> PortfolioScenarioConvergenceOut:
        record = self._convergence(convergence_id, lock=True)
        if record.submit_idempotency_key == idempotency_key:
            return self._convergence_out(record)
        self._check_version(record.revision_version, expected_version)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "CONVERGENCE_NOT_DRAFT"})
        self._assert_current_source(record)
        if not self._alternative_records(record.id):
            raise HTTPException(status_code=409, detail={"code": "CONVERGED_ALTERNATIVE_REQUIRED"})
        record.status = "IN_REVIEW"
        record.submit_idempotency_key = idempotency_key
        self._touch(record)
        self._event("portfolio_recommendation.submitted", "PortfolioScenarioConvergence", record.id, {})
        self.db.commit()
        return self._convergence_out(record)

    def return_to_draft(
        self,
        convergence_id: int,
        expected_version: int,
        idempotency_key: str,
    ) -> PortfolioScenarioConvergenceOut:
        record = self._convergence(convergence_id, lock=True)
        if record.return_idempotency_key == idempotency_key:
            return self._convergence_out(record)
        self._check_version(record.revision_version, expected_version)
        if record.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "CONVERGENCE_NOT_IN_REVIEW"})
        record.status = "DRAFT"
        record.return_idempotency_key = idempotency_key
        self._touch(record)
        self._event("portfolio_recommendation.returned", "PortfolioScenarioConvergence", record.id, {})
        self.db.commit()
        return self._convergence_out(record)

    def recommend(
        self,
        convergence_id: int,
        expected_version: int,
        payload: RecommendationIn,
    ) -> PortfolioScenarioConvergenceOut:
        record = self._convergence(convergence_id, lock=True)
        if record.recommend_idempotency_key == payload.idempotency_key:
            return self._convergence_out(record)
        self._check_version(record.revision_version, expected_version)
        if record.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "CONVERGENCE_NOT_IN_REVIEW"})
        self._assert_current_source(record)
        alternative = self._alternative(payload.recommended_alternative_id)
        if alternative.convergence_id != record.id:
            raise HTTPException(status_code=422, detail={"code": "ALTERNATIVE_CONVERGENCE_MISMATCH"})
        policy = self._record_policy(record)
        eligible = alternative.feasibility_status == "FEASIBLE"
        if alternative.feasibility_status == "CONDITIONAL" and policy.get("allow_conditional_recommendation"):
            eligible = bool(payload.conditions)
        if not eligible:
            raise HTTPException(
                status_code=409,
                detail={"code": "ALTERNATIVE_NOT_ELIGIBLE_FOR_RECOMMENDATION"},
            )
        if alternative.blockers_json:
            raise HTTPException(status_code=409, detail={"code": "ALTERNATIVE_HAS_BLOCKERS"})
        if policy.get("recommender_sod_required") and record.created_by == self.actor_id:
            raise HTTPException(status_code=409, detail={"code": "RECOMMENDER_SEGREGATION_OF_DUTIES_REQUIRED"})
        missing = self._recommendation_missing_fields(policy, payload)
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"code": "RECOMMENDATION_EVIDENCE_REQUIRED", "fields": missing},
            )
        recommendation_hash = _hash(
            {
                "convergence_id": record.id,
                "convergence_revision": record.convergence_revision,
                "source_hash": record.convergence_source_hash,
                "alternative_hash": alternative.alternative_hash,
                "reason": payload.recommendation_reason,
                "conditions": payload.conditions,
                "risks_acknowledged": payload.risks_acknowledged,
                "decision_support_summary": payload.decision_support_summary,
                "recommended_by": self.actor_id,
            }
        )
        record.recommended_alternative_id = alternative.id
        record.recommendation_reason = payload.recommendation_reason
        record.conditions_json = list(payload.conditions)
        record.risks_acknowledged_json = list(payload.risks_acknowledged)
        record.decision_support_summary = payload.decision_support_summary
        record.recommendation_hash = recommendation_hash
        record.recommended_by = self.actor_id
        record.recommended_at = utc_now()
        record.recommend_idempotency_key = payload.idempotency_key
        record.status = "RECOMMENDED"
        self._touch(record)
        self._event(
            "portfolio_recommendation.recommended",
            "PortfolioScenarioConvergence",
            record.id,
            {"alternative_id": alternative.id, "recommendation_hash": recommendation_hash},
        )
        self.db.commit()
        return self._convergence_out(record, historical=True)

    def clone(
        self,
        convergence_id: int,
        expected_version: int,
        idempotency_key: str,
    ) -> PortfolioScenarioConvergenceOut:
        source = self._convergence(convergence_id, lock=True)
        replay = self.db.scalar(
            select(PortfolioScenarioConvergence).where(
                PortfolioScenarioConvergence.tenant_id == self.tenant_id,
                PortfolioScenarioConvergence.clone_idempotency_key == idempotency_key,
            )
        )
        if replay is not None:
            return self._convergence_out(replay)
        self._check_version(source.revision_version, expected_version)
        configuration = self._effective_configuration(
            self._portfolio(source.portfolio_workspace_id), published_only=True
        )
        if configuration is None:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_REQUIRED"})
        snapshot = self._source_snapshot(
            source.portfolio_workspace_id,
            required_budget=source.required_budget_branch,
            required_resource=source.required_resource_branch,
            configuration_hash=configuration.content_hash,
            require_ready=True,
        )
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(PortfolioScenarioConvergence.convergence_revision), 0)).where(
                        PortfolioScenarioConvergence.tenant_id == self.tenant_id,
                        PortfolioScenarioConvergence.portfolio_workspace_id == source.portfolio_workspace_id,
                        PortfolioScenarioConvergence.logical_code == source.logical_code,
                    )
                )
                or 0
            )
            + 1
        )
        clone = PortfolioScenarioConvergence(
            tenant_id=self.tenant_id,
            portfolio_workspace_id=source.portfolio_workspace_id,
            logical_code=source.logical_code,
            convergence_revision=revision,
            name=f"{source.name} · revision {revision}",
            description=source.description,
            status="DRAFT",
            required_budget_branch=source.required_budget_branch,
            required_resource_branch=source.required_resource_branch,
            source_analysis_hash=snapshot["analysis_hash"],
            source_membership_set_hash=snapshot["membership_set_hash"],
            source_evaluation_set_hash=snapshot["evaluation_set_hash"],
            budget_planning_hash=snapshot.get("budget_planning_hash"),
            resource_planning_hash=snapshot.get("resource_planning_hash"),
            configuration_id=configuration.id,
            configuration_revision=configuration.revision,
            configuration_hash=configuration.content_hash,
            convergence_source_hash=snapshot["source_hash"],
            source_snapshot_json=snapshot,
            clone_idempotency_key=idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._event(
            "portfolio_convergence.cloned",
            "PortfolioScenarioConvergence",
            clone.id,
            {"source_id": source.id},
        )
        self.db.commit()
        return self._convergence_out(clone)

    def void(
        self,
        convergence_id: int,
        expected_version: int,
        idempotency_key: str,
    ) -> PortfolioScenarioConvergenceOut:
        record = self._convergence(convergence_id, lock=True)
        if record.void_idempotency_key == idempotency_key:
            return self._convergence_out(record, historical=True)
        self._check_version(record.revision_version, expected_version)
        if record.status not in {"DRAFT", "IN_REVIEW"}:
            raise HTTPException(status_code=409, detail={"code": "CONVERGENCE_CANNOT_BE_VOIDED"})
        record.status = "VOIDED"
        record.voided_at = utc_now()
        record.void_idempotency_key = idempotency_key
        self._touch(record)
        self._event("portfolio_convergence.voided", "PortfolioScenarioConvergence", record.id, {})
        self.db.commit()
        return self._convergence_out(record, historical=True)

    # Readiness and downstream contract -----------------------------
    def readiness(self, portfolio_id: int) -> PortfolioRecommendationReadinessOut:
        self._portfolio(portfolio_id)
        record = self.db.scalar(
            select(PortfolioScenarioConvergence)
            .where(
                PortfolioScenarioConvergence.tenant_id == self.tenant_id,
                PortfolioScenarioConvergence.portfolio_workspace_id == portfolio_id,
                PortfolioScenarioConvergence.status != "VOIDED",
            )
            .order_by(PortfolioScenarioConvergence.convergence_revision.desc())
        )
        if record is None:
            return PortfolioRecommendationReadinessOut(
                portfolio_workspace_id=portfolio_id,
                convergence_id=None,
                convergence_revision=None,
                status="BLOCKED",
                alternative_count=0,
                recommended_alternative_id=None,
                source_current=False,
                warnings=[],
                blockers=["PORTFOLIO_SCENARIO_CONVERGENCE_REQUIRED"],
                recommendation_hash=None,
                portfolio_recommendation_ready=False,
                can_enter_investment_gate_preparation=False,
                can_enter_fid=False,
                allowed_actions=["can_view_convergence", "can_create_convergence"],
                final_output=REWORK_OUTPUT,
            )
        alternatives = self._alternative_records(record.id)
        warnings = list(record.warnings_json or [])
        blockers = list(record.blockers_json or [])
        try:
            current = self._source_snapshot(
                portfolio_id,
                required_budget=record.required_budget_branch,
                required_resource=record.required_resource_branch,
                configuration_hash=self._current_configuration_hash(portfolio_id),
                require_ready=False,
            )
            source_current = current["source_hash"] == record.convergence_source_hash
            if not current.get("compatible", False):
                blockers.append("CONVERGENCE_SOURCE_MISMATCH")
            blockers.extend(current.get("blockers", []))
            warnings.extend(current.get("warnings", []))
        except HTTPException as exc:
            source_current = False
            blockers.append(_detail_code(exc, "STALE_PORTFOLIO_CONVERGENCE_SOURCE"))
        if not source_current:
            blockers.append("STALE_PORTFOLIO_CONVERGENCE_SOURCE")
        if not alternatives:
            blockers.append("CONVERGED_ALTERNATIVE_REQUIRED")
        recommended = None
        if record.recommended_alternative_id is not None:
            recommended = next((item for item in alternatives if item.id == record.recommended_alternative_id), None)
        if record.status != "RECOMMENDED" or recommended is None:
            blockers.append("FORMAL_PORTFOLIO_RECOMMENDATION_REQUIRED")
        elif recommended.feasibility_status not in {"FEASIBLE", "CONDITIONAL"}:
            blockers.append("RECOMMENDED_ALTERNATIVE_NOT_ELIGIBLE")
        if not record.recommendation_reason or not record.decision_support_summary or not record.recommendation_hash:
            blockers.append("RECOMMENDATION_EVIDENCE_INCOMPLETE")
        blockers = sorted(set(blockers))
        warnings = sorted(set(warnings))
        ready = not blockers
        status = "READY" if ready else "STALE" if not source_current else "BLOCKED"
        return PortfolioRecommendationReadinessOut(
            portfolio_workspace_id=portfolio_id,
            convergence_id=record.id,
            convergence_revision=record.convergence_revision,
            status=status,
            alternative_count=len(alternatives),
            recommended_alternative_id=record.recommended_alternative_id,
            source_current=source_current,
            warnings=warnings,
            blockers=blockers,
            recommendation_hash=record.recommendation_hash,
            portfolio_recommendation_ready=ready,
            can_enter_investment_gate_preparation=ready,
            can_enter_fid=False,
            allowed_actions=self._allowed_actions(record, source_current, len(alternatives), ready),
            final_output=READY_OUTPUT if ready else REWORK_OUTPUT,
        )

    def overview(self, portfolio_id: int) -> PortfolioConvergenceOverviewOut:
        self._portfolio(portfolio_id)
        policy = self._policy(portfolio_id, require_published=False)
        snapshot = self._source_snapshot(
            portfolio_id,
            required_budget=bool(policy["required_budget_branch"]),
            required_resource=bool(policy["required_resource_branch"]),
            configuration_hash=self._current_configuration_hash(portfolio_id, required=False),
            require_ready=False,
        )
        return PortfolioConvergenceOverviewOut(
            portfolio_workspace_id=portfolio_id,
            required_branches={
                "budget": bool(policy["required_budget_branch"]),
                "resource": bool(policy["required_resource_branch"]),
            },
            budget_contract=snapshot.get("budget_contract"),
            resource_contract=snapshot.get("resource_contract"),
            source_compatibility={
                "compatible": snapshot["compatible"],
                "analysis_hash": snapshot["analysis_hash"],
                "membership_set_hash": snapshot["membership_set_hash"],
                "evaluation_set_hash": snapshot["evaluation_set_hash"],
                "warnings": snapshot.get("warnings", []),
                "blockers": snapshot.get("blockers", []),
            },
            candidate_budget_scenarios=snapshot.get("budget_scenarios", []),
            candidate_resource_scenarios=snapshot.get("resource_scenarios", []),
            convergences=self.convergences(portfolio_id),
            readiness=self.readiness(portfolio_id),
            boundaries=[
                "PORTFOLIO_RECOMMENDATION_IS_NOT_INVESTMENT_APPROVAL",
                "CAN_ENTER_FID_IS_ALWAYS_FALSE",
                "NO_SOURCE_REOPENING_OR_THIRD_SELECTION_STATE",
                "NO_OPTIMIZER_OR_AI_WINNER",
                "NO_FUNDS_FUNDING_FEL_PDRI_OR_FID",
                "NO_PROJECT_INITIALIZATION_ACTIVATION_OR_EXECUTION",
            ],
        )

    def preparation_contract(self, portfolio_id: int) -> InvestmentGatePreparationContractOut:
        readiness = self.readiness(portfolio_id)
        if not readiness.portfolio_recommendation_ready or readiness.convergence_id is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "PORTFOLIO_RECOMMENDATION_NOT_READY", "blockers": readiness.blockers},
            )
        record = self._convergence(readiness.convergence_id)
        alternative = self._alternative(record.recommended_alternative_id)
        selected = list(alternative.strategic_summary_json.get("selected_project_ids", []))
        return InvestmentGatePreparationContractOut(
            portfolio_workspace_id=portfolio_id,
            convergence_id=record.id,
            convergence_revision=record.convergence_revision,
            recommended_alternative_id=alternative.id,
            recommendation_hash=record.recommendation_hash or "",
            budget_scenario_ref={
                "id": alternative.budget_scenario_id,
                "hash": alternative.budget_scenario_hash,
            }
            if alternative.budget_scenario_id
            else None,
            resource_scenario_ref={
                "id": alternative.resource_scenario_id,
                "hash": alternative.resource_scenario_hash,
            }
            if alternative.resource_scenario_id
            else None,
            budget_planning_hash=record.budget_planning_hash,
            resource_planning_hash=record.resource_planning_hash,
            analysis_hash=record.source_analysis_hash,
            membership_set_hash=record.source_membership_set_hash,
            evaluation_set_hash=record.source_evaluation_set_hash,
            selected_project_set_reference=selected,
            selected_project_set_hash=alternative.selected_project_set_hash,
            budget_feasibility_summary=dict(alternative.budget_summary_json or {}),
            resource_feasibility_summary=dict(alternative.resource_summary_json or {}),
            strategic_summary=dict(alternative.strategic_summary_json or {}),
            risk_summary=dict(alternative.risk_summary_json or {}),
            conditions=list(record.conditions_json or []),
            warnings=readiness.warnings,
            blockers=[],
            portfolio_recommendation_ready=True,
            can_enter_fid=False,
            final_output=READY_OUTPUT,
        )

    # AdminConfiguration reuse --------------------------------------
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
        portfolio_id: int | None,
        configuration_id: int | None,
        content_override: dict | None,
    ) -> ConfigurationPreviewOut:
        workspace = self._portfolio(portfolio_id) if portfolio_id else None
        record = self._configuration(configuration_id) if configuration_id else None
        effective = deepcopy(
            content_override
            if content_override is not None
            else record.content_json
            if record
            else DEFAULT_CONFIGURATION
        )
        issues = self._configuration_issues(effective)
        source_readiness: dict | None = None
        budget_count = 0
        resource_count = 0
        warnings: list[str] = []
        blockers: list[str] = []
        if portfolio_id and not issues:
            try:
                snapshot = self._source_snapshot(
                    portfolio_id,
                    required_budget=bool(effective["required_budget_branch"]),
                    required_resource=bool(effective["required_resource_branch"]),
                    configuration_hash=_hash(effective),
                    require_ready=False,
                )
                budget_count = len(snapshot.get("budget_scenario_ids", []))
                resource_count = len(snapshot.get("resource_scenario_ids", []))
                warnings.extend(snapshot.get("warnings", []))
                blockers.extend(snapshot.get("blockers", []))
                source_readiness = {
                    "compatible": snapshot["compatible"],
                    "budget_final_output": (snapshot.get("budget_contract") or {}).get("final_output"),
                    "resource_final_output": (snapshot.get("resource_contract") or {}).get("final_output"),
                    "analysis_hash": snapshot["analysis_hash"],
                }
            except HTTPException as exc:
                blockers.append(_detail_code(exc, "SOURCE_READINESS_UNAVAILABLE"))
        source = record or self._effective_configuration(workspace, published_only=True)
        return ConfigurationPreviewOut(
            portfolio_workspace_id=portfolio_id,
            path=[self._workspace_summary(item) for item in self._workspace_path(workspace)],
            effective=effective,
            source={
                "id": source.id,
                "code": source.code,
                "revision": source.revision,
                "status": source.status,
                "content_hash": source.content_hash,
            }
            if source
            else {"type": "starter-default", "status": "draft"},
            source_readiness=source_readiness,
            candidate_budget_scenarios=budget_count,
            candidate_resource_scenarios=resource_count,
            possible_pair_count=(
                budget_count * resource_count
                if effective.get("required_budget_branch") and effective.get("required_resource_branch")
                else budget_count or resource_count
            ),
            validation_issues=issues,
            warnings=sorted(set(warnings)),
            blockers=sorted(set(blockers)),
            publishable=not issues,
            persisted=False,
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id, lock=True)
        self._check_version(source.version, expected_version)
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
            name=f"{source.name} · revision {revision}",
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=deepcopy(source.content_json),
            content_hash=source.content_hash,
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._event("portfolio_convergence.configuration_cloned", "AdminConfiguration", clone.id, {})
        self.db.commit()
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
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_IMMUTABLE"})
        self._validate_configuration(content)
        record.name = name
        record.description = description
        record.content_json = deepcopy(content)
        record.content_hash = _hash(content)
        record.version += 1
        record.updated_at = utc_now()
        self._event("portfolio_convergence.configuration_updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "CONFIGURATION_NOT_DRAFT"})
        self._validate_configuration(record.content_json)
        scope = dict(record.content_json.get("scope", {}))
        for previous in self.configurations():
            if (
                previous.id != record.id
                and previous.status == "published"
                and previous.code == record.code
                and dict(previous.content_json.get("scope", {})) == scope
            ):
                previous.status = "superseded"
                previous.version += 1
        record.status = "published"
        record.published_at = utc_now()
        record.version += 1
        record.content_hash = _hash(record.content_json)
        self._event("portfolio_convergence.configuration_published", "AdminConfiguration", record.id, {})
        self.db.commit()
        return record

    # Source consumption and derived decision support ---------------
    def _source_snapshot(
        self,
        portfolio_id: int,
        *,
        required_budget: bool,
        required_resource: bool,
        configuration_hash: str,
        require_ready: bool,
    ) -> dict:
        if not required_budget and not required_resource:
            raise HTTPException(status_code=422, detail={"code": "AT_LEAST_ONE_SOURCE_BRANCH_REQUIRED"})
        budget_contract = None
        resource_contract = None
        budget_scenarios: list[dict] = []
        resource_scenarios: list[dict] = []
        warnings: list[str] = []
        blockers: list[str] = []
        if required_budget:
            budget_service = PortfolioBudgetService(self.db, self.tenant_id, self.actor_id, self.context)
            budget_service.ensure_seed()
            contract = budget_service.recommendation_contract(portfolio_id)
            budget_contract = contract.model_dump(mode="json")
            budget_scenarios = list(contract.ready_frozen_scenario_refs)
            warnings.extend(contract.warnings)
            blockers.extend(contract.blockers)
            if contract.final_output != BUDGET_READY_OUTPUT or not budget_scenarios:
                blockers.append("READY_FOR_PORTFOLIO_BUDGET_RECOMMENDATION_REQUIRED")
        if required_resource:
            resource_service = PortfolioResourceService(self.db, self.tenant_id, self.actor_id, self.context)
            resource_service.ensure_seed()
            contract = resource_service.recommendation_contract(portfolio_id)
            resource_contract = contract.model_dump(mode="json")
            resource_scenarios = [
                {**item, "scenario_hash": scenario_hash}
                for item, scenario_hash in zip(
                    contract.ready_frozen_scenario_refs,
                    contract.scenario_hashes,
                    strict=False,
                )
            ]
            warnings.extend(contract.warnings)
            blockers.extend(contract.blockers)
            if contract.final_output != RESOURCE_READY_OUTPUT or not resource_scenarios:
                blockers.append("READY_FOR_PORTFOLIO_RESOURCE_RECOMMENDATION_REQUIRED")
        analysis_hashes = {
            value
            for value in (
                budget_contract.get("analysis_hash") if budget_contract else None,
                resource_contract.get("gate07f_analysis_hash") if resource_contract else None,
            )
            if value
        }
        membership_hashes = {
            value
            for value in (
                budget_contract.get("membership_set_hash") if budget_contract else None,
                resource_contract.get("membership_set_hash") if resource_contract else None,
            )
            if value
        }
        evaluation_hashes = {
            value
            for value in (
                budget_contract.get("evaluation_set_hash") if budget_contract else None,
                resource_contract.get("evaluation_set_hash") if resource_contract else None,
            )
            if value
        }
        compatible = len(analysis_hashes) == len(membership_hashes) == len(evaluation_hashes) == 1
        if not compatible:
            blockers.append("CONVERGENCE_SOURCE_MISMATCH")
        analysis_hash = next(iter(analysis_hashes), "")
        membership_hash = next(iter(membership_hashes), "")
        evaluation_hash = next(iter(evaluation_hashes), "")
        snapshot = {
            "portfolio_workspace_id": portfolio_id,
            "required_budget_branch": required_budget,
            "required_resource_branch": required_resource,
            "analysis_hash": analysis_hash,
            "membership_set_hash": membership_hash,
            "evaluation_set_hash": evaluation_hash,
            "budget_planning_hash": budget_contract.get("budget_planning_hash") if budget_contract else None,
            "resource_planning_hash": resource_contract.get("resource_planning_hash") if resource_contract else None,
            "budget_contract": budget_contract,
            "resource_contract": resource_contract,
            "budget_scenarios": budget_scenarios,
            "resource_scenarios": resource_scenarios,
            "budget_scenario_ids": [int(item["id"]) for item in budget_scenarios],
            "resource_scenario_ids": [int(item["id"]) for item in resource_scenarios],
            "compatible": compatible,
            "configuration_hash": configuration_hash,
            "warnings": sorted(set(warnings)),
            "blockers": sorted(set(blockers)),
        }
        snapshot["source_hash"] = _hash(
            {
                "portfolio_workspace_id": portfolio_id,
                "analysis_hash": analysis_hash,
                "membership_set_hash": membership_hash,
                "evaluation_set_hash": evaluation_hash,
                "budget_planning_hash": snapshot["budget_planning_hash"],
                "budget_scenarios": sorted(
                    (int(item["id"]), str(item.get("scenario_hash") or "")) for item in budget_scenarios
                ),
                "resource_planning_hash": snapshot["resource_planning_hash"],
                "resource_scenarios": sorted(
                    (int(item["id"]), str(item.get("scenario_hash") or "")) for item in resource_scenarios
                ),
                "configuration_hash": configuration_hash,
            }
        )
        if require_ready and snapshot["blockers"]:
            code = "CONVERGENCE_SOURCE_MISMATCH" if not compatible else "SOURCE_BRANCH_NOT_READY"
            raise HTTPException(status_code=409, detail={"code": code, "blockers": snapshot["blockers"]})
        return snapshot

    def _build_alternative(
        self,
        record: PortfolioScenarioConvergence,
        snapshot: dict,
        policy: dict,
        budget_scenario_id: int | None,
        resource_scenario_id: int | None,
    ) -> dict:
        if record.required_budget_branch and budget_scenario_id is None:
            raise HTTPException(status_code=422, detail={"code": "BUDGET_SCENARIO_REQUIRED"})
        if record.required_resource_branch and resource_scenario_id is None:
            raise HTTPException(status_code=422, detail={"code": "RESOURCE_SCENARIO_REQUIRED"})
        if not record.required_budget_branch and budget_scenario_id is not None:
            raise HTTPException(status_code=422, detail={"code": "BUDGET_SCENARIO_NOT_REQUIRED"})
        if not record.required_resource_branch and resource_scenario_id is not None:
            raise HTTPException(status_code=422, detail={"code": "RESOURCE_SCENARIO_NOT_REQUIRED"})
        budget_output = None
        resource_output = None
        budget_rows: list[PortfolioBudgetScenarioProject] = []
        resource_rows: list[PortfolioResourceScenarioProject] = []
        if budget_scenario_id is not None:
            if budget_scenario_id not in snapshot["budget_scenario_ids"]:
                raise HTTPException(status_code=409, detail={"code": "BUDGET_SCENARIO_NOT_READY_CURRENT"})
            budget_output = PortfolioBudgetService(self.db, self.tenant_id, self.actor_id, self.context).scenario(
                budget_scenario_id
            )
            budget_rows = list(
                self.db.scalars(
                    select(PortfolioBudgetScenarioProject).where(
                        PortfolioBudgetScenarioProject.tenant_id == self.tenant_id,
                        PortfolioBudgetScenarioProject.scenario_id == budget_scenario_id,
                    )
                ).all()
            )
        if resource_scenario_id is not None:
            if resource_scenario_id not in snapshot["resource_scenario_ids"]:
                raise HTTPException(status_code=409, detail={"code": "RESOURCE_SCENARIO_NOT_READY_CURRENT"})
            resource_output = PortfolioResourceService(self.db, self.tenant_id, self.actor_id, self.context).scenario(
                resource_scenario_id
            )
            resource_rows = list(
                self.db.scalars(
                    select(PortfolioResourceScenarioProject).where(
                        PortfolioResourceScenarioProject.tenant_id == self.tenant_id,
                        PortfolioResourceScenarioProject.scenario_id == resource_scenario_id,
                    )
                ).all()
            )
        budget_included = {row.project_workspace_id for row in budget_rows if _included(row.selection_state)}
        resource_included = {row.project_workspace_id for row in resource_rows if _included(row.selection_state)}
        if budget_output and resource_output:
            if budget_included == resource_included:
                alignment = "ALIGNED"
            elif budget_included & resource_included:
                alignment = "PARTIALLY_ALIGNED"
            else:
                alignment = "MISALIGNED"
            selected_project_ids = sorted(budget_included & resource_included)
        else:
            alignment = "ALIGNED"
            selected_project_ids = sorted(budget_included or resource_included)
        budget_by_project = {row.project_workspace_id: row for row in budget_rows}
        resource_by_project = {row.project_workspace_id: row for row in resource_rows}
        conflicts: list[dict] = []
        for project_id in sorted(budget_by_project.keys() & resource_by_project.keys()):
            budget_state = budget_by_project[project_id].selection_state
            resource_state = resource_by_project[project_id].selection_state
            if (budget_state, resource_state) in {
                ("FORCED_IN", "FORCED_OUT"),
                ("FORCED_OUT", "FORCED_IN"),
            }:
                conflicts.append(
                    {
                        "project_workspace_id": project_id,
                        "budget_state": budget_state,
                        "resource_state": resource_state,
                        "code": "FORCED_STATE_CONFLICT",
                    }
                )
        budget_feasibility = "NOT_REQUIRED"
        budget_summary: dict = {}
        if budget_output:
            budget_summary = {
                "target": budget_output.summary.target_budget,
                "selected_demand": budget_output.summary.selected_demand,
                "variance": budget_output.summary.variance,
                "utilization": budget_output.summary.utilization_percent,
                "period_overloads": sum(
                    1 for item in budget_output.period_view if item.variance is not None and item.variance < 0
                ),
                "currency": next((row.currency for row in budget_output.projects), None),
                "analytical_status": budget_output.summary.analytical_status,
                "warnings": budget_output.warnings,
                "blockers": budget_output.blockers,
            }
            budget_feasibility = (
                "INFEASIBLE"
                if budget_output.blockers
                else "CONDITIONAL"
                if budget_output.summary.analytical_status == "OVER_BUDGET"
                else "BUDGET_FEASIBLE"
            )
        resource_feasibility = "NOT_REQUIRED"
        resource_summary: dict = {}
        if resource_output:
            resource_summary = {
                "demand_coverage": resource_output.summary.demand_coverage_percent,
                "overloaded_roles": resource_output.summary.overloaded_role_count,
                "overloaded_period_count": resource_output.summary.overloaded_period_count,
                "peak_utilization": resource_output.summary.peak_utilization,
                "average_utilization": resource_output.summary.average_utilization,
                "warnings": resource_output.warnings,
                "blockers": resource_output.blockers,
            }
            resource_feasibility = (
                "INFEASIBLE"
                if resource_output.blockers
                else "CONDITIONAL"
                if resource_output.summary.overloaded_period_count > 0
                else "RESOURCE_FEASIBLE"
            )
        blockers: list[str] = []
        warnings: list[str] = []
        if alignment != "ALIGNED":
            warnings.append("PROJECT_SET_MISALIGNMENT")
            if policy.get("require_identical_project_sets", True):
                blockers.append("BLOCKED_FOR_RECOMMENDATION")
        if conflicts:
            warnings.append("FORCED_STATE_CONFLICT")
            if policy.get("forced_conflict_is_blocker", True):
                blockers.append("FORCED_STATE_CONFLICT")
        branch_statuses = {budget_feasibility, resource_feasibility} - {"NOT_REQUIRED"}
        if blockers:
            overall = "BLOCKED"
        elif "INFEASIBLE" in branch_statuses:
            overall = "INFEASIBLE"
        elif "CONDITIONAL" in branch_statuses:
            overall = "CONDITIONAL"
        else:
            overall = "FEASIBLE"
        source_rows = budget_rows if budget_rows else resource_rows
        selected_rows = [row for row in source_rows if row.project_workspace_id in selected_project_ids]
        average_score = _average([Decimal(str(row.portfolio_evaluation_score)) for row in selected_rows])
        average_alignment = _average([Decimal(str(row.strategic_alignment_score)) for row in selected_rows])
        high_risk = sum(str(row.risk_bucket).upper() == "HIGH" for row in selected_rows)
        objective_coverage = (
            len(dict(budget_output.strategic_balance or {}).get("objectives", [])) if budget_output else 0
        )
        strategic_summary = {
            "selected_project_ids": selected_project_ids,
            "project_count": len(selected_project_ids),
            "average_portfolio_score": average_score,
            "strategic_alignment": average_alignment,
            "objective_coverage": objective_coverage,
            "rank_distribution": _distribution([row.portfolio_rank for row in selected_rows]),
            "project_type_distribution": _distribution(
                [str(getattr(row, "project_type", "") or "UNCLASSIFIED") for row in selected_rows]
            ),
        }
        risk_summary = {"high_risk_count": high_risk}
        project_matrix = []
        for project_id in sorted(budget_by_project.keys() | resource_by_project.keys()):
            budget_row = budget_by_project.get(project_id)
            resource_row = resource_by_project.get(project_id)
            row = budget_row or resource_row
            project_matrix.append(
                {
                    "project_workspace_id": project_id,
                    "project_number": row.project_number if row else None,
                    "project_name": row.project_name if row else None,
                    "budget_state": budget_row.selection_state if budget_row else None,
                    "resource_state": resource_row.selection_state if resource_row else None,
                    "budget_included": bool(budget_row and _included(budget_row.selection_state)),
                    "resource_included": bool(resource_row and _included(resource_row.selection_state)),
                }
            )
        selected_hash = _hash(
            {
                "budget_selected_projects": sorted(budget_included),
                "resource_selected_projects": sorted(resource_included),
                "intersection": selected_project_ids,
            }
        )
        alternative_hash = _hash(
            {
                "convergence_source_hash": record.convergence_source_hash,
                "budget_scenario_id": budget_scenario_id,
                "budget_scenario_hash": budget_output.scenario_hash if budget_output else None,
                "resource_scenario_id": resource_scenario_id,
                "resource_scenario_hash": resource_output.scenario_hash if resource_output else None,
                "alignment": alignment,
                "budget_feasibility": budget_feasibility,
                "resource_feasibility": resource_feasibility,
                "overall": overall,
                "selected_project_set_hash": selected_hash,
                "forced_conflicts": conflicts,
            }
        )
        return {
            "budget_scenario_id": budget_scenario_id,
            "budget_scenario_hash": budget_output.scenario_hash if budget_output else None,
            "resource_scenario_id": resource_scenario_id,
            "resource_scenario_hash": resource_output.scenario_hash if resource_output else None,
            "alignment_status": alignment,
            "budget_feasibility": budget_feasibility,
            "resource_feasibility": resource_feasibility,
            "feasibility_status": overall,
            "selected_project_set_hash": selected_hash,
            "budget_summary_json": _jsonable(budget_summary),
            "resource_summary_json": _jsonable(resource_summary),
            "strategic_summary_json": _jsonable(strategic_summary),
            "risk_summary_json": risk_summary,
            "project_matrix_json": project_matrix,
            "forced_conflicts_json": conflicts,
            "warnings_json": sorted(set(warnings)),
            "blockers_json": sorted(set(blockers)),
            "alternative_hash": alternative_hash,
        }

    # Persistence helpers ------------------------------------------
    def _convergence(
        self,
        convergence_id: int | None,
        *,
        lock: bool = False,
    ) -> PortfolioScenarioConvergence:
        statement = select(PortfolioScenarioConvergence).where(
            PortfolioScenarioConvergence.id == convergence_id,
            PortfolioScenarioConvergence.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Portfolio Scenario Convergence not found")
        self._assert_scope(record.portfolio_workspace_id)
        return record

    def _alternative(self, alternative_id: int | None) -> PortfolioConvergedAlternative:
        record = self.db.scalar(
            select(PortfolioConvergedAlternative).where(
                PortfolioConvergedAlternative.id == alternative_id,
                PortfolioConvergedAlternative.tenant_id == self.tenant_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Converged Alternative not found")
        return record

    def _alternative_records(self, convergence_id: int) -> list[PortfolioConvergedAlternative]:
        return list(
            self.db.scalars(
                select(PortfolioConvergedAlternative)
                .where(
                    PortfolioConvergedAlternative.tenant_id == self.tenant_id,
                    PortfolioConvergedAlternative.convergence_id == convergence_id,
                )
                .order_by(PortfolioConvergedAlternative.id)
            ).all()
        )

    def _convergence_out(
        self,
        record: PortfolioScenarioConvergence,
        *,
        historical: bool = False,
    ) -> PortfolioScenarioConvergenceOut:
        alternatives = [self._alternative_out(item) for item in self._alternative_records(record.id)]
        source_current = True
        warnings = list(record.warnings_json or [])
        blockers = list(record.blockers_json or [])
        if not historical and record.status not in {"RECOMMENDED", "SUPERSEDED", "VOIDED"}:
            try:
                current_hash = self._current_source_hash(record)
                source_current = current_hash == record.convergence_source_hash
            except HTTPException:
                source_current = False
            if not source_current:
                warnings.append("STALE_PORTFOLIO_CONVERGENCE_SOURCE")
        ready = record.status == "RECOMMENDED" and source_current
        return PortfolioScenarioConvergenceOut(
            id=record.id,
            tenant_id=record.tenant_id,
            portfolio_workspace_id=record.portfolio_workspace_id,
            logical_code=record.logical_code,
            convergence_revision=record.convergence_revision,
            name=record.name,
            description=record.description,
            status=record.status,
            required_budget_branch=record.required_budget_branch,
            required_resource_branch=record.required_resource_branch,
            source_analysis_hash=record.source_analysis_hash,
            source_membership_set_hash=record.source_membership_set_hash,
            source_evaluation_set_hash=record.source_evaluation_set_hash,
            budget_planning_hash=record.budget_planning_hash,
            resource_planning_hash=record.resource_planning_hash,
            configuration_id=record.configuration_id,
            configuration_revision=record.configuration_revision,
            configuration_hash=record.configuration_hash,
            convergence_source_hash=record.convergence_source_hash,
            source_current=source_current,
            recommended_alternative_id=record.recommended_alternative_id,
            recommendation_reason=record.recommendation_reason,
            conditions=list(record.conditions_json or []),
            risks_acknowledged=list(record.risks_acknowledged_json or []),
            decision_support_summary=record.decision_support_summary,
            recommendation_hash=record.recommendation_hash,
            recommended_by=record.recommended_by,
            recommended_at=record.recommended_at,
            warnings=sorted(set(warnings)),
            blockers=sorted(set(blockers)),
            revision_version=record.revision_version,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
            voided_at=record.voided_at,
            alternatives=alternatives,
            allowed_actions=self._allowed_actions(record, source_current, len(alternatives), ready),
        )

    @staticmethod
    def _alternative_out(record: PortfolioConvergedAlternative) -> ConvergedAlternativeOut:
        return ConvergedAlternativeOut(
            id=record.id,
            convergence_id=record.convergence_id,
            alternative_name=record.alternative_name,
            budget_scenario_id=record.budget_scenario_id,
            budget_scenario_hash=record.budget_scenario_hash,
            resource_scenario_id=record.resource_scenario_id,
            resource_scenario_hash=record.resource_scenario_hash,
            alignment_status=record.alignment_status,
            budget_feasibility=record.budget_feasibility,
            resource_feasibility=record.resource_feasibility,
            feasibility_status=record.feasibility_status,
            selected_project_set_hash=record.selected_project_set_hash,
            budget_summary=dict(record.budget_summary_json or {}),
            resource_summary=dict(record.resource_summary_json or {}),
            strategic_summary=dict(record.strategic_summary_json or {}),
            risk_summary=dict(record.risk_summary_json or {}),
            project_matrix=list(record.project_matrix_json or []),
            forced_conflicts=list(record.forced_conflicts_json or []),
            warnings=list(record.warnings_json or []),
            blockers=list(record.blockers_json or []),
            alternative_hash=record.alternative_hash,
            revision_version=record.revision_version,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    # Configuration inheritance and safeguards ---------------------
    def _configuration_issues(self, content: dict) -> list[str]:
        issues: list[str] = []
        if content.get("applicable_governance_models") != ["CAPITAL_OWNER"]:
            issues.append("CAPITAL_OWNER_ONLY_REQUIRED")
        if not content.get("required_budget_branch") and not content.get("required_resource_branch"):
            issues.append("AT_LEAST_ONE_SOURCE_BRANCH_REQUIRED")
        if content.get("recommendation_mode") != "SINGLE_RECOMMENDER":
            issues.append("UNSUPPORTED_RECOMMENDATION_MODE")
        required_fields = set(content.get("required_recommendation_fields", []))
        allowed_fields = {
            "recommendation_reason",
            "conditions",
            "risks_acknowledged",
            "decision_support_summary",
        }
        if not required_fields or not required_fields <= allowed_fields:
            issues.append("INVALID_RECOMMENDATION_FIELDS")
        serialized = json.dumps(content, sort_keys=True).lower()
        forbidden = {
            "approve_investment",
            "execute_fid",
            "funding_assignment",
            "funding_source",
            "project_initialization",
            "project_activation",
            "project_execution",
            "portfolio_optimizer",
            "ai_winner",
            "pdri",
            "fel_assessment",
        }
        if any(term in serialized for term in forbidden):
            issues.append("DOWNSTREAM_CAPABILITY_NOT_ALLOWED_IN_GATE07I")
        return sorted(set(issues))

    def _validate_configuration(self, content: dict) -> None:
        issues = self._configuration_issues(content)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "issues": issues})

    def _policy(self, portfolio_id: int, *, require_published: bool) -> dict:
        record = self._effective_configuration(self._portfolio(portfolio_id), published_only=True)
        if record is None:
            if require_published:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "PUBLISHED_PORTFOLIO_CONVERGENCE_CONFIGURATION_REQUIRED"},
                )
            return deepcopy(DEFAULT_CONFIGURATION)
        content = deepcopy(record.content_json or {})
        self._validate_configuration(content)
        return content

    def _record_policy(self, record: PortfolioScenarioConvergence) -> dict:
        configuration = self._configuration(record.configuration_id)
        content = deepcopy(configuration.content_json or {})
        self._validate_configuration(content)
        return content

    def _effective_configuration(
        self,
        workspace: EnterpriseWorkspace | None,
        *,
        published_only: bool,
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
                expected = {
                    "enterprise": "enterprise",
                    "business-unit": "business-unit",
                    "portfolio": "portfolio",
                }.get(scope_type)
                if expected and path_ids[int(scope_id)].workspace_type_code != expected:
                    continue
                specificity = {"enterprise": 1, "business-unit": 2, "portfolio": 3}.get(scope_type, 0)
            candidates.append((specificity, record.revision, record))
        return max(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None

    def _configuration(self, configuration_id: int | None, *, lock: bool = False) -> AdminConfiguration:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.id == configuration_id,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Portfolio Convergence configuration not found")
        return record

    def _current_configuration_hash(self, portfolio_id: int, *, required: bool = True) -> str:
        record = self._effective_configuration(self._portfolio(portfolio_id), published_only=True)
        if record is None:
            if required:
                raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_REQUIRED"})
            return _hash(DEFAULT_CONFIGURATION)
        return record.content_hash

    # Workspace, concurrency, actions and audit ---------------------
    def _portfolio(self, portfolio_id: int | None) -> EnterpriseWorkspace:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == portfolio_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
            )
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        if workspace.workspace_type_code != "portfolio":
            raise HTTPException(status_code=422, detail={"code": "WORKSPACE_IS_NOT_PORTFOLIO"})
        self._assert_scope(workspace.id)
        return workspace

    def _assert_scope(self, workspace_id: int) -> None:
        if self.context is None or self.context.organization_wide:
            return
        if workspace_id not in self.context.workspace_ids:
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
            "parent_id": workspace.parent_id,
        }

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(status_code=412, detail={"code": "ETAG_MISMATCH"})

    @staticmethod
    def _assert_editable(record: PortfolioScenarioConvergence) -> None:
        if record.status not in {"DRAFT", "IN_REVIEW"}:
            raise HTTPException(status_code=409, detail={"code": "RECOMMENDED_CONVERGENCE_IMMUTABLE"})

    def _touch(self, record: PortfolioScenarioConvergence) -> None:
        record.revision_version += 1
        record.updated_by = self.actor_id
        record.updated_at = utc_now()

    def _current_source_hash(self, record: PortfolioScenarioConvergence) -> str:
        return self._source_snapshot(
            record.portfolio_workspace_id,
            required_budget=record.required_budget_branch,
            required_resource=record.required_resource_branch,
            configuration_hash=self._current_configuration_hash(record.portfolio_workspace_id),
            require_ready=False,
        )["source_hash"]

    def _assert_current_source(self, record: PortfolioScenarioConvergence) -> dict:
        snapshot = self._source_snapshot(
            record.portfolio_workspace_id,
            required_budget=record.required_budget_branch,
            required_resource=record.required_resource_branch,
            configuration_hash=self._current_configuration_hash(record.portfolio_workspace_id),
            require_ready=True,
        )
        if snapshot["source_hash"] != record.convergence_source_hash:
            self._event(
                "portfolio_convergence.source_stale_detected",
                "PortfolioScenarioConvergence",
                record.id,
                {},
            )
            raise HTTPException(status_code=412, detail={"code": "STALE_PORTFOLIO_CONVERGENCE_SOURCE"})
        return snapshot

    @staticmethod
    def _allowed_actions(
        record: PortfolioScenarioConvergence,
        source_current: bool,
        alternative_count: int,
        ready: bool,
    ) -> list[str]:
        actions = ["can_view_convergence", "can_clone_convergence"]
        if alternative_count >= 2:
            actions.append("can_compare_alternatives")
        if record.status == "DRAFT":
            actions.extend(["can_edit_convergence", "can_void_convergence"])
            if source_current:
                actions.extend(
                    [
                        "can_add_alternative",
                        "can_remove_alternative",
                        "can_submit_recommendation_review",
                    ]
                )
            else:
                actions.append("can_refresh_convergence")
        elif record.status == "IN_REVIEW":
            actions.extend(["can_return_recommendation", "can_void_convergence"])
            if source_current:
                actions.append("can_recommend_alternative")
        if ready:
            actions.append("can_enter_investment_gate_preparation")
        return actions

    @staticmethod
    def _recommendation_missing_fields(policy: dict, payload: RecommendationIn) -> list[str]:
        values = {
            "recommendation_reason": payload.recommendation_reason,
            "conditions": payload.conditions,
            "risks_acknowledged": payload.risks_acknowledged,
            "decision_support_summary": payload.decision_support_summary,
        }
        return [name for name in policy.get("required_recommendation_fields", []) if not values.get(name)]

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


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _included(selection_state: str) -> bool:
    return selection_state in {"SELECTED", "FORCED_IN"}


def _average(values: list[Decimal]) -> Decimal | None:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def _distribution(values: list[Any]) -> list[dict]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return [{"value": key, "count": counts[key]} for key in sorted(counts)]


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _detail_code(exc: HTTPException, fallback: str) -> str:
    return str(exc.detail.get("code", fallback)) if isinstance(exc.detail, dict) else fallback
