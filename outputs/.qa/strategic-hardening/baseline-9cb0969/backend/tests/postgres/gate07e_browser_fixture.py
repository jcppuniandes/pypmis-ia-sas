"""Disposable Gate 07E-J-FEL browser fixture and persistent-baseline guard.

The fixture is intentionally created outside product APIs so the browser test can
exercise the real USER/ADMIN APIs from a known precondition.  Teardown uses exact
run-scoped workspace/configuration codes and removes all resulting audit rows.
"""

from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy
from datetime import date
from decimal import Decimal

from sqlalchemy import Text, cast, delete, func, or_, select, text, update

from app.core.security import hash_password
from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    AuthCredential,
    EnterpriseWorkspace,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRole,
    UserAccount,
)
from app.main import app as _app  # noqa: F401 - imports every routed model into SQLAlchemy metadata
from app.modules.enterprise_structure.permissions import ensure_enterprise_permissions
from app.modules.funds_manager.models import (
    Fund,
    FundingAssignment,
    FundingReadinessSnapshot,
    StrategicFundingSource,
)
from app.modules.funds_manager.service import CONFIGURATION_KIND as FUNDS_CONFIGURATION_KIND
from app.modules.funds_manager.service import DEFAULT_CONFIGURATION as FUNDS_DEFAULT_CONFIGURATION
from app.modules.funds_manager.service import FundsManagerService
from app.modules.investment_gate_preparation.models import (
    InvestmentGateEvidenceItem,
    InvestmentGatePreparation,
)
from app.modules.portfolio_analysis.service import (
    CONFIGURATION_KIND as ANALYSIS_CONFIGURATION_KIND,
)
from app.modules.portfolio_analysis.service import DEFAULT_CODE as ANALYSIS_DEFAULT_CODE
from app.modules.portfolio_analysis.service import DEFAULT_CONFIGURATION as ANALYSIS_DEFAULT_CONFIGURATION
from app.modules.portfolio_analysis.service import PortfolioAnalysisService
from app.modules.portfolio_budget.models import (
    PortfolioBudgetScenario,
    PortfolioBudgetScenarioProject,
    PortfolioBudgetTarget,
    PortfolioBudgetTargetPeriod,
    ProjectDependency,
)
from app.modules.portfolio_budget.schemas import BudgetScenarioCreateIn, BudgetTargetCreateIn, TargetPeriodIn
from app.modules.portfolio_budget.service import CONFIGURATION_KIND as BUDGET_CONFIGURATION_KIND
from app.modules.portfolio_budget.service import DEFAULT_CODE as BUDGET_DEFAULT_CODE
from app.modules.portfolio_budget.service import DEFAULT_CONFIGURATION as BUDGET_DEFAULT_CONFIGURATION
from app.modules.portfolio_budget.service import PortfolioBudgetService
from app.modules.portfolio_convergence.models import PortfolioConvergedAlternative, PortfolioScenarioConvergence
from app.modules.portfolio_convergence.schemas import ConvergenceCreateIn, RecommendationIn
from app.modules.portfolio_convergence.service import CONFIGURATION_KIND as CONVERGENCE_CONFIGURATION_KIND
from app.modules.portfolio_convergence.service import DEFAULT_CONFIGURATION as CONVERGENCE_DEFAULT_CONFIGURATION
from app.modules.portfolio_convergence.service import PortfolioConvergenceService
from app.modules.portfolio_evaluation.models import PortfolioProjectEvaluation
from app.modules.portfolio_evaluation.service import (
    CONFIGURATION_KIND as EVALUATION_CONFIGURATION_KIND,
)
from app.modules.portfolio_evaluation.service import DEFAULT_CODE as EVALUATION_DEFAULT_CODE
from app.modules.portfolio_evaluation.service import DEFAULT_CONFIGURATION as EVALUATION_DEFAULT_CONFIGURATION
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService, _hash
from app.modules.portfolio_planning.models import PortfolioProjectMembership
from app.modules.portfolio_resource.models import (
    PortfolioResourceCapacityPeriod,
    PortfolioResourceCapacityPlan,
    PortfolioResourceScenario,
    PortfolioResourceScenarioProject,
    ProjectResourceDemandPeriod,
    ProjectResourceDemandProfile,
)
from app.modules.portfolio_resource.schemas import (
    CapacityPeriodIn,
    CapacityPlanCreateIn,
    DemandPeriodIn,
    DemandProfileCreateIn,
    ResourceScenarioCreateIn,
)
from app.modules.portfolio_resource.service import CONFIGURATION_KIND as RESOURCE_CONFIGURATION_KIND
from app.modules.portfolio_resource.service import DEFAULT_CONFIGURATION as RESOURCE_DEFAULT_CONFIGURATION
from app.modules.portfolio_resource.service import PortfolioResourceService
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.project_definition.models import (
    ProjectDefinitionAction,
    ProjectDefinitionAssessment,
    ProjectFELStatus,
)
from app.modules.project_definition.service import CONFIGURATION_KIND as DEFINITION_CONFIGURATION_KIND
from app.modules.project_definition.service import DEFAULT_FRAMEWORK as DEFINITION_DEFAULT_FRAMEWORK
from app.modules.project_definition.service import ProjectDefinitionService


def _safe_run_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    if len(normalized) < 4:
        raise ValueError("run-id must contain at least four alphanumeric characters")
    return normalized[:48]


def _prefix(run_id: str) -> str:
    return f"G07EH-{_safe_run_id(run_id).upper()}"


def _configuration_code(run_id: str, copy_index: int, context: str) -> str:
    return f"g07eh-{_safe_run_id(run_id)}-r{copy_index}-{context}"


def _workspace(
    db,
    *,
    tenant_id: int,
    actor_id: int,
    parent_id: int,
    workspace_type: str,
    code: str,
    name: str,
    status: str,
    defaults: dict | None = None,
) -> EnterpriseWorkspace:
    record = EnterpriseWorkspace(
        tenant_id=tenant_id,
        parent_id=parent_id,
        workspace_type_code=workspace_type,
        code=code,
        external_key=code.lower(),
        record_code=code,
        name=name,
        status=status,
        defaults_json=defaults or {},
        sort_order=99,
        version=1,
        created_by_user_id=actor_id,
    )
    db.add(record)
    db.flush()
    return record


def _portfolio(db, *, tenant_id: int, actor_id: int, parent_id: int, code: str, name: str):
    return _workspace(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        parent_id=parent_id,
        workspace_type="portfolio",
        code=code,
        name=name,
        status="active",
    )


def _project(
    db,
    *,
    tenant_id: int,
    actor_id: int,
    parent_id: int,
    code: str,
    name: str,
    target_portfolio: EnterpriseWorkspace,
    governance_model: str,
    planning_origin: str = "STRATEGIC_GATE",
    planning_status: str = "READY_FOR_PORTFOLIO_PLANNING",
    target_finish: str = "2028-01-01",
) -> EnterpriseWorkspace:
    snapshot = {
        "project_workspace_id": 0,
        "project_number": code,
        "project_name": name,
        "workspace_status": "pending",
        "planning_origin": planning_origin,
        "planning_stage": "PORTFOLIO_AND_FEL_PLANNING",
        "strategic_gate_decision": {"id": 700, "decision_number": f"SGD-{code}"},
        "project_proposal": {"id": 701, "proposal_number": f"PROP-{code}"},
        "source_idea": {"id": 702, "idea_number": f"IDEA-{code}"},
        "target_portfolio": {"id": target_portfolio.id, "name": target_portfolio.name},
        "strategic_objectives": [{"code": "GROWTH", "name": "Growth"}],
        "proposal_score": "88.0000",
        "rom_cost": "2500000",
        "currency": "COP",
        "target_start": "2027-01-01",
        "target_finish": target_finish,
        "expected_benefits": "Gate 07E-H disposable browser evidence",
        "risk_summary": [{"code": "R-1", "level": "medium"}],
    }
    project_context = {"planning_origin": planning_origin}
    if governance_model:
        project_context["governance_model"] = governance_model
    record = _workspace(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        parent_id=parent_id,
        workspace_type="project",
        code=code,
        name=name,
        status="pending",
        defaults={},
    )
    snapshot["project_workspace_id"] = record.id
    record.defaults_json = {
        "_project": project_context,
        "_portfolio_planning": {
            "status": planning_status,
            "snapshot": snapshot,
            "planning_entry_hash": _hash(snapshot),
            "blocking_issues": [] if planning_status == "READY_FOR_PORTFOLIO_PLANNING" else ["FIXTURE_BLOCKED"],
        },
    }
    return record


def _membership(
    db,
    *,
    tenant_id: int,
    actor_id: int,
    portfolio_id: int,
    project_id: int,
    source: str = "MANUAL",
    is_target: bool = False,
) -> PortfolioProjectMembership:
    record = PortfolioProjectMembership(
        tenant_id=tenant_id,
        portfolio_workspace_id=portfolio_id,
        project_workspace_id=project_id,
        membership_source=source,
        is_target_portfolio=is_target,
        status="ACTIVE",
        effective_from=utc_now(),
        revision_version=1,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(record)
    db.flush()
    return record


def _published_matrix(
    db,
    *,
    tenant_id: int,
    actor_id: int,
    portfolio: EnterpriseWorkspace,
    code: str,
    name: str,
) -> AdminConfiguration:
    content = deepcopy(EVALUATION_DEFAULT_CONFIGURATION)
    content["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    labels = {
        "economic": "Economic Value",
        "capacity": "Organizational Capacity",
    }
    for criterion in content["criteria"]:
        criterion["label"] = labels.get(criterion["code"], criterion["label"])
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=EVALUATION_CONFIGURATION_KIND,
        code=code,
        name=name,
        description="Disposable Gate 07E-H browser matrix; explicit fixture publication only.",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        published_at=utc_now(),
        created_by_user_id=actor_id,
    )
    db.add(record)
    db.flush()
    return record


def _published_analysis(
    db,
    *,
    tenant_id: int,
    actor_id: int,
    portfolio: EnterpriseWorkspace,
    code: str,
    name: str,
) -> AdminConfiguration:
    content = deepcopy(ANALYSIS_DEFAULT_CONFIGURATION)
    content["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=ANALYSIS_CONFIGURATION_KIND,
        code=code,
        name=name,
        description="Disposable Gate 07F browser analysis configuration; explicit fixture publication only.",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        published_at=utc_now(),
        created_by_user_id=actor_id,
    )
    db.add(record)
    db.flush()
    return record


def _published_budget(
    db,
    *,
    tenant_id: int,
    actor_id: int,
    portfolio: EnterpriseWorkspace,
    code: str,
    name: str,
) -> AdminConfiguration:
    content = deepcopy(BUDGET_DEFAULT_CONFIGURATION)
    content["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=BUDGET_CONFIGURATION_KIND,
        code=code,
        name=name,
        description="Disposable Gate 07G browser Budget Planning configuration.",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        published_at=utc_now(),
        created_by_user_id=actor_id,
    )
    db.add(record)
    db.flush()
    return record


def _published_resource(
    db,
    *,
    tenant_id: int,
    actor_id: int,
    portfolio: EnterpriseWorkspace,
    code: str,
    name: str,
) -> AdminConfiguration:
    content = deepcopy(RESOURCE_DEFAULT_CONFIGURATION)
    content["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=RESOURCE_CONFIGURATION_KIND,
        code=code,
        name=name,
        description="Disposable Gate 07H source for Gate 07J-FUND browser closeout.",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        published_at=utc_now(),
        created_by_user_id=actor_id,
    )
    db.add(record)
    db.flush()
    return record


def _published_convergence(
    db,
    *,
    tenant_id: int,
    actor_id: int,
    portfolio: EnterpriseWorkspace,
    code: str,
    name: str,
) -> AdminConfiguration:
    content = deepcopy(CONVERGENCE_DEFAULT_CONFIGURATION)
    content["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=CONVERGENCE_CONFIGURATION_KIND,
        code=code,
        name=name,
        description="Disposable Gate 07I contract source for Gate 07J-FUND browser closeout.",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        published_at=utc_now(),
        created_by_user_id=actor_id,
    )
    db.add(record)
    db.flush()
    return record


def _published_definition_framework(
    db,
    *,
    tenant_id: int,
    actor_id: int,
    project: EnterpriseWorkspace,
    code: str,
    name: str,
) -> AdminConfiguration:
    """Publish non-proprietary FEL metadata scoped to one disposable Project."""

    content = deepcopy(DEFINITION_DEFAULT_FRAMEWORK)
    content["scope"] = {"type": "project", "workspace_id": project.id}
    content["framework_code"] = f"PYP-E2E-{project.code}"
    content["framework_name"] = name
    content["framework_version"] = "1.0-e2e"
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=DEFINITION_CONFIGURATION_KIND,
        code=code,
        name=name,
        description="Disposable, non-proprietary Gate 07J-FEL browser framework.",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        published_at=utc_now(),
        created_by_user_id=actor_id,
    )
    db.add(record)
    db.flush()
    return record


def _published_funds_policy(
    db,
    *,
    tenant_id: int,
    actor_id: int,
    portfolio: EnterpriseWorkspace | None,
    code: str,
    name: str,
    sequence_baseline: list[dict] | None = None,
) -> AdminConfiguration:
    """Publish the deterministic Funds policy used by the release closeout."""

    content = deepcopy(FUNDS_DEFAULT_CONFIGURATION)
    content["scope"] = (
        {"type": "portfolio", "workspace_id": portfolio.id}
        if portfolio is not None
        else {"type": "tenant", "workspace_id": None}
    )
    content["fund_creator_cannot_authorize"] = True
    content["assignment_preparer_cannot_confirm"] = True
    content["allow_confirmed_over_allocation"] = False
    content["allow_reserved_overbooking"] = False
    if sequence_baseline is not None:
        content["_e2e_sequence_baseline"] = deepcopy(sequence_baseline)
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=FUNDS_CONFIGURATION_KIND,
        code=code,
        name=name,
        description="Disposable Gate 07J-FUND browser lifecycle policy.",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        published_at=utc_now(),
        created_by_user_id=actor_id,
    )
    db.add(record)
    db.flush()
    return record


def _definition_reviewer(db, *, tenant_id: int, actor_id: int, run_id: str, copy_index: int) -> UserAccount:
    """Create a run-scoped reviewer with only the governed reviewer role."""

    email = f"g07j-fel-reviewer-{run_id}-r{copy_index}@example.test"
    reviewer = UserAccount(
        tenant_id=tenant_id,
        email=email,
        full_name=f"Gate 07J-FEL Reviewer R{copy_index}",
        title="Definition Reviewer",
        status="active",
    )
    db.add(reviewer)
    db.flush()
    db.add(
        AuthCredential(
            tenant_id=tenant_id,
            user_id=reviewer.id,
            provider="local",
            password_hash=hash_password("1234"),
            is_active=True,
        )
    )
    role = db.scalar(
        select(SecurityRole).where(
            SecurityRole.tenant_id == tenant_id,
            SecurityRole.code == "definition_reviewer",
        )
    )
    if role is None:
        raise RuntimeError("definition_reviewer role is required for Gate 07J-FEL browser evidence")
    db.add(
        SecurityAccessAssignment(
            tenant_id=tenant_id,
            subject_type="user",
            user_id=reviewer.id,
            role_id=role.id,
            scope_type="organization",
            status="active",
            granted_by_user_id=actor_id,
        )
    )
    db.flush()
    return reviewer


def _funding_reviewer(db, *, tenant_id: int, actor_id: int, run_id: str, copy_index: int) -> UserAccount:
    """Create a run-scoped second actor for Fund authorization and Assignment confirmation."""

    email = f"g07j-fund-reviewer-{run_id}-r{copy_index}@example.test"
    reviewer = UserAccount(
        tenant_id=tenant_id,
        email=email,
        full_name=f"Gate 07J-FUND Reviewer R{copy_index}",
        title="Funding Reviewer",
        status="active",
    )
    db.add(reviewer)
    db.flush()
    db.add(
        AuthCredential(
            tenant_id=tenant_id,
            user_id=reviewer.id,
            provider="local",
            password_hash=hash_password("1234"),
            is_active=True,
        )
    )
    role = db.scalar(
        select(SecurityRole).where(
            SecurityRole.tenant_id == tenant_id,
            SecurityRole.code == "funding_reviewer",
        )
    )
    if role is None:
        raise RuntimeError("funding_reviewer role is required for Gate 07J-FUND browser evidence")
    db.add(
        SecurityAccessAssignment(
            tenant_id=tenant_id,
            subject_type="user",
            user_id=reviewer.id,
            role_id=role.id,
            scope_type="organization",
            status="active",
            granted_by_user_id=actor_id,
        )
    )
    db.flush()
    return reviewer


def _summary(record: EnterpriseWorkspace) -> dict:
    return {"id": record.id, "name": record.name, "code": record.code}


def seed(run_id: str, copies: int) -> dict:
    safe = _safe_run_id(run_id)
    teardown(safe, emit=False)
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        if admin is None:
            raise RuntimeError("The demo admin user is required for the disposable browser fixture")
        ensure_enterprise_permissions(db, admin.tenant_id, admin.id)
        parent = db.scalar(
            select(EnterpriseWorkspace)
            .where(
                EnterpriseWorkspace.tenant_id == admin.tenant_id,
                EnterpriseWorkspace.workspace_type_code == "enterprise",
            )
            .order_by(EnterpriseWorkspace.id)
        )
        if parent is None:
            raise RuntimeError("An Enterprise workspace is required for Gate 07E-H")
        prefix = _prefix(safe)
        sequence_baseline = [
            {
                "rule_code": item.rule_code,
                "scope_key": item.scope_key,
                "next_value": item.next_value,
                "version": item.version,
            }
            for item in db.scalars(
                select(AdminNumberSequence).where(
                    AdminNumberSequence.tenant_id == admin.tenant_id,
                    AdminNumberSequence.rule_code.in_(["funding-source", "fund", "funding-assignment"]),
                )
            ).all()
        ]
        tenant_funds_policy = _published_funds_policy(
            db,
            tenant_id=admin.tenant_id,
            actor_id=admin.id,
            portfolio=None,
            code=f"g07eh-{safe}-funds-tenant",
            name=f"Gate07E-J-FEL {safe} Tenant Funds Manager Policy",
            sequence_baseline=sequence_baseline,
        )
        fixtures: list[dict] = []
        for index in range(1, copies + 1):
            label = f"Gate07E-J-FEL {safe} R{index}"
            main = _portfolio(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                parent_id=parent.id,
                code=f"{prefix}-R{index}-PF-MAIN",
                name=f"{label} Main Portfolio",
            )
            secondary = _portfolio(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                parent_id=parent.id,
                code=f"{prefix}-R{index}-PF-SECONDARY",
                name=f"{label} Secondary Portfolio",
            )
            exclusion = _portfolio(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                parent_id=parent.id,
                code=f"{prefix}-R{index}-PF-EXCLUSION",
                name=f"{label} Exclusion Portfolio",
            )
            no_matrix = _portfolio(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                parent_id=parent.id,
                code=f"{prefix}-R{index}-PF-NOMATRIX",
                name=f"{label} No Matrix Portfolio",
            )
            projects: dict[str, EnterpriseWorkspace] = {}
            finishes = {"A": "2028-01-01", "B": "2028-02-01", "C": "2028-03-01"}
            main_memberships: dict[str, PortfolioProjectMembership] = {}
            for key in ("A", "B", "C"):
                project = _project(
                    db,
                    tenant_id=admin.tenant_id,
                    actor_id=admin.id,
                    parent_id=parent.id,
                    code=f"{prefix}-R{index}-PRJ-{key}",
                    name=f"{label} Project {key}",
                    target_portfolio=main,
                    governance_model="CAPITAL_OWNER",
                    target_finish=finishes[key],
                )
                projects[key] = project
                main_memberships[key] = _membership(
                    db,
                    tenant_id=admin.tenant_id,
                    actor_id=admin.id,
                    portfolio_id=main.id,
                    project_id=project.id,
                    source="STRATEGIC_INTAKE" if key == "A" else "MANUAL",
                    is_target=key == "A",
                )
            secondary_membership = _membership(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                portfolio_id=secondary.id,
                project_id=projects["A"].id,
            )
            excluded: dict[str, EnterpriseWorkspace] = {}
            for key, governance in (
                ("CONTRACTOR", "CONTRACTOR_DELIVERY"),
                ("DIRECT", "DIRECT_INTERNAL"),
                ("LEGACY", ""),
            ):
                project = _project(
                    db,
                    tenant_id=admin.tenant_id,
                    actor_id=admin.id,
                    parent_id=parent.id,
                    code=f"{prefix}-R{index}-PRJ-{key}",
                    name=f"{label} {key.title()} Project",
                    target_portfolio=exclusion,
                    governance_model=governance,
                    planning_origin="LEGACY" if key == "LEGACY" else "STRATEGIC_GATE",
                )
                excluded[key] = project
                _membership(
                    db,
                    tenant_id=admin.tenant_id,
                    actor_id=admin.id,
                    portfolio_id=exclusion.id,
                    project_id=project.id,
                )
            blocked = _project(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                parent_id=parent.id,
                code=f"{prefix}-R{index}-PRJ-BLOCKED",
                name=f"{label} Blocked Planning Project",
                target_portfolio=exclusion,
                governance_model="CAPITAL_OWNER",
                planning_status="GATE07D_REWORK_REQUIRED",
            )
            _membership(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                portfolio_id=exclusion.id,
                project_id=blocked.id,
            )
            no_matrix_project = _project(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                parent_id=parent.id,
                code=f"{prefix}-R{index}-PRJ-NOMATRIX",
                name=f"{label} No Matrix Project",
                target_portfolio=no_matrix,
                governance_model="CAPITAL_OWNER",
            )
            _membership(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                portfolio_id=no_matrix.id,
                project_id=no_matrix_project.id,
            )
            missing_membership = _project(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                parent_id=parent.id,
                code=f"{prefix}-R{index}-PRJ-NOMEMBERSHIP",
                name=f"{label} Missing Membership Project",
                target_portfolio=main,
                governance_model="CAPITAL_OWNER",
            )
            main_matrix = _published_matrix(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                portfolio=main,
                code=_configuration_code(safe, index, "main"),
                name=f"{label} Published Matrix",
            )
            secondary_matrix = _published_matrix(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                portfolio=secondary,
                code=_configuration_code(safe, index, "secondary"),
                name=f"{label} Secondary Matrix",
            )
            main_analysis = _published_analysis(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                portfolio=main,
                code=_configuration_code(safe, index, "analysis-main"),
                name=f"{label} Published Portfolio Analysis",
            )
            secondary_analysis = _published_analysis(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                portfolio=secondary,
                code=_configuration_code(safe, index, "analysis-secondary"),
                name=f"{label} Secondary Portfolio Analysis",
            )
            main_budget = _published_budget(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                portfolio=main,
                code=_configuration_code(safe, index, "budget-main"),
                name=f"{label} Published Portfolio Budget Policy",
            )
            secondary_budget = _published_budget(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                portfolio=secondary,
                code=_configuration_code(safe, index, "budget-secondary"),
                name=f"{label} Secondary Portfolio Budget Policy",
            )
            resource_policy = _published_resource(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                portfolio=main,
                code=_configuration_code(safe, index, "resource"),
                name=f"{label} Portfolio Resource Policy",
            )
            convergence_policy = _published_convergence(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                portfolio=main,
                code=_configuration_code(safe, index, "convergence"),
                name=f"{label} Portfolio Convergence Policy",
            )
            definition_framework = _published_definition_framework(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                project=projects["A"],
                code=_configuration_code(safe, index, "definition"),
                name=f"{label} Project Definition Framework",
            )
            reviewer = _definition_reviewer(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                run_id=safe,
                copy_index=index,
            )
            funds_policy = _published_funds_policy(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                portfolio=main,
                code=_configuration_code(safe, index, "funds"),
                name=f"{label} Funds Manager Policy",
            )
            funding_reviewer = _funding_reviewer(
                db,
                tenant_id=admin.tenant_id,
                actor_id=admin.id,
                run_id=safe,
                copy_index=index,
            )
            fixtures.append(
                {
                    "index": index,
                    "main_portfolio": _summary(main),
                    "secondary_portfolio": _summary(secondary),
                    "exclusion_portfolio": _summary(exclusion),
                    "no_matrix_portfolio": _summary(no_matrix),
                    "projects": {key: _summary(value) for key, value in projects.items()},
                    "main_memberships": {
                        key: {"id": value.id, "revision_version": value.revision_version}
                        for key, value in main_memberships.items()
                    },
                    "secondary_membership": {
                        "id": secondary_membership.id,
                        "revision_version": secondary_membership.revision_version,
                    },
                    "excluded_projects": {key: _summary(value) for key, value in excluded.items()},
                    "blocked_project": _summary(blocked),
                    "no_matrix_project": _summary(no_matrix_project),
                    "missing_membership_project": _summary(missing_membership),
                    "main_configuration": {
                        "id": main_matrix.id,
                        "name": main_matrix.name,
                        "code": main_matrix.code,
                        "revision": main_matrix.revision,
                        "version": main_matrix.version,
                        "hash": main_matrix.content_hash,
                    },
                    "secondary_configuration": {
                        "id": secondary_matrix.id,
                        "name": secondary_matrix.name,
                        "code": secondary_matrix.code,
                    },
                    "main_analysis_configuration": {
                        "id": main_analysis.id,
                        "name": main_analysis.name,
                        "code": main_analysis.code,
                        "revision": main_analysis.revision,
                        "version": main_analysis.version,
                        "hash": main_analysis.content_hash,
                    },
                    "secondary_analysis_configuration": {
                        "id": secondary_analysis.id,
                        "name": secondary_analysis.name,
                        "code": secondary_analysis.code,
                    },
                    "main_budget_configuration": {
                        "id": main_budget.id,
                        "name": main_budget.name,
                        "code": main_budget.code,
                        "revision": main_budget.revision,
                        "version": main_budget.version,
                        "hash": main_budget.content_hash,
                    },
                    "secondary_budget_configuration": {
                        "id": secondary_budget.id,
                        "name": secondary_budget.name,
                        "code": secondary_budget.code,
                    },
                    "resource_configuration": {
                        "id": resource_policy.id,
                        "name": resource_policy.name,
                        "code": resource_policy.code,
                        "revision": resource_policy.revision,
                        "version": resource_policy.version,
                        "hash": resource_policy.content_hash,
                    },
                    "convergence_configuration": {
                        "id": convergence_policy.id,
                        "name": convergence_policy.name,
                        "code": convergence_policy.code,
                        "revision": convergence_policy.revision,
                        "version": convergence_policy.version,
                        "hash": convergence_policy.content_hash,
                    },
                    "definition_configuration": {
                        "id": definition_framework.id,
                        "name": definition_framework.name,
                        "code": definition_framework.code,
                        "revision": definition_framework.revision,
                        "version": definition_framework.version,
                        "hash": definition_framework.content_hash,
                    },
                    "definition_reviewer": {
                        "id": reviewer.id,
                        "email": reviewer.email,
                        "password": "1234",
                    },
                    "funds_configuration": {
                        "id": funds_policy.id,
                        "name": funds_policy.name,
                        "code": funds_policy.code,
                        "revision": funds_policy.revision,
                        "version": funds_policy.version,
                        "hash": funds_policy.content_hash,
                    },
                    "funding_reviewer": {
                        "id": funding_reviewer.id,
                        "email": funding_reviewer.email,
                        "password": "1234",
                    },
                }
            )
        db.commit()
        return {
            "run_id": safe,
            "tenant_funds_configuration": {
                "id": tenant_funds_policy.id,
                "code": tenant_funds_policy.code,
                "hash": tenant_funds_policy.content_hash,
            },
            "copies": fixtures,
        }


def teardown(run_id: str, *, emit: bool = True) -> dict:
    safe = _safe_run_id(run_id)
    workspace_prefix = f"{_prefix(safe)}%"
    configuration_prefix = f"g07eh-{safe}%"
    reviewer_prefix = f"g07j-fel-reviewer-{safe}-r%@example.test"
    funding_reviewer_prefix = f"g07j-fund-reviewer-{safe}-r%@example.test"
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        if admin is None:
            raise RuntimeError("Demo tenant not seeded")
        workspaces = list(
            db.scalars(select(EnterpriseWorkspace).where(EnterpriseWorkspace.code.like(workspace_prefix)))
        )
        workspace_ids = [item.id for item in workspaces]
        project_ids = [item.id for item in workspaces if item.workspace_type_code == "project"]
        portfolio_ids = [item.id for item in workspaces if item.workspace_type_code == "portfolio"]
        configurations = list(
            db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.kind.in_(
                        [
                            EVALUATION_CONFIGURATION_KIND,
                            ANALYSIS_CONFIGURATION_KIND,
                            BUDGET_CONFIGURATION_KIND,
                            RESOURCE_CONFIGURATION_KIND,
                            CONVERGENCE_CONFIGURATION_KIND,
                            DEFINITION_CONFIGURATION_KIND,
                            FUNDS_CONFIGURATION_KIND,
                        ]
                    ),
                    AdminConfiguration.code.like(configuration_prefix),
                )
            )
        )
        configuration_ids = [item.id for item in configurations]
        tenant_funds_configuration = next(
            (item for item in configurations if item.code == f"g07eh-{safe}-funds-tenant"),
            None,
        )
        sequence_baseline = list(
            ((tenant_funds_configuration.content_json if tenant_funds_configuration else {}) or {}).get(
                "_e2e_sequence_baseline", []
            )
        )
        reviewers = list(
            db.scalars(
                select(UserAccount).where(
                    or_(
                        UserAccount.email.like(reviewer_prefix),
                        UserAccount.email.like(funding_reviewer_prefix),
                    )
                )
            )
        )
        reviewer_ids = [item.id for item in reviewers]
        funding_assignments = list(
            db.scalars(
                select(FundingAssignment).where(
                    or_(
                        FundingAssignment.portfolio_workspace_id.in_(portfolio_ids or [-1]),
                        FundingAssignment.project_workspace_id.in_(project_ids or [-1]),
                    )
                )
            )
        )
        funding_assignment_ids = [item.id for item in funding_assignments]
        referenced_fund_ids = {item.fund_id for item in funding_assignments}
        funds = list(
            db.scalars(
                select(Fund).where(
                    or_(
                        Fund.id.in_(referenced_fund_ids or {-1}),
                        Fund.fund_name.ilike(f"%{safe}%"),
                    )
                )
            )
        )
        fund_ids = [item.id for item in funds]
        referenced_source_ids = {item.funding_source_id for item in funds if item.funding_source_id}
        funding_sources = list(
            db.scalars(
                select(StrategicFundingSource).where(
                    or_(
                        StrategicFundingSource.id.in_(referenced_source_ids or {-1}),
                        StrategicFundingSource.source_name.ilike(f"%{safe}%"),
                    )
                )
            )
        )
        funding_source_ids = [item.id for item in funding_sources]
        readiness_snapshots = list(
            db.scalars(
                select(FundingReadinessSnapshot).where(
                    FundingReadinessSnapshot.portfolio_workspace_id.in_(portfolio_ids or [-1])
                )
            )
        )
        readiness_snapshot_ids = [item.id for item in readiness_snapshots]
        definition_actions = list(
            db.scalars(
                select(ProjectDefinitionAction).where(
                    ProjectDefinitionAction.project_workspace_id.in_(project_ids or [-1])
                )
            )
        )
        definition_action_ids = [item.id for item in definition_actions]
        definition_assessments = list(
            db.scalars(
                select(ProjectDefinitionAssessment).where(
                    ProjectDefinitionAssessment.project_workspace_id.in_(project_ids or [-1])
                )
            )
        )
        definition_assessment_ids = [item.id for item in definition_assessments]
        fel_statuses = list(
            db.scalars(select(ProjectFELStatus).where(ProjectFELStatus.project_workspace_id.in_(project_ids or [-1])))
        )
        fel_status_ids = [item.id for item in fel_statuses]
        evaluations = list(
            db.scalars(
                select(PortfolioProjectEvaluation).where(
                    or_(
                        PortfolioProjectEvaluation.project_workspace_id.in_(project_ids or [-1]),
                        PortfolioProjectEvaluation.portfolio_workspace_id.in_(portfolio_ids or [-1]),
                    )
                )
            )
        )
        evaluation_ids = [item.id for item in evaluations]
        scenarios = list(
            db.scalars(
                select(PortfolioBudgetScenario).where(
                    PortfolioBudgetScenario.portfolio_workspace_id.in_(portfolio_ids or [-1])
                )
            )
        )
        scenario_ids = [item.id for item in scenarios]
        targets = list(
            db.scalars(
                select(PortfolioBudgetTarget).where(
                    PortfolioBudgetTarget.portfolio_workspace_id.in_(portfolio_ids or [-1])
                )
            )
        )
        target_ids = [item.id for item in targets]
        project_dependencies = list(
            db.scalars(
                select(ProjectDependency).where(
                    or_(
                        ProjectDependency.predecessor_project_workspace_id.in_(project_ids or [-1]),
                        ProjectDependency.successor_project_workspace_id.in_(project_ids or [-1]),
                    )
                )
            )
        )
        project_dependency_ids = [item.id for item in project_dependencies]
        resource_scenarios = list(
            db.scalars(
                select(PortfolioResourceScenario).where(
                    PortfolioResourceScenario.portfolio_workspace_id.in_(portfolio_ids or [-1])
                )
            )
        )
        resource_scenario_ids = [item.id for item in resource_scenarios]
        capacity_plans = list(
            db.scalars(
                select(PortfolioResourceCapacityPlan).where(
                    PortfolioResourceCapacityPlan.portfolio_workspace_id.in_(portfolio_ids or [-1])
                )
            )
        )
        capacity_plan_ids = [item.id for item in capacity_plans]
        demand_profiles = list(
            db.scalars(
                select(ProjectResourceDemandProfile).where(
                    ProjectResourceDemandProfile.project_workspace_id.in_(project_ids or [-1])
                )
            )
        )
        demand_profile_ids = [item.id for item in demand_profiles]
        convergences = list(
            db.scalars(
                select(PortfolioScenarioConvergence).where(
                    PortfolioScenarioConvergence.portfolio_workspace_id.in_(portfolio_ids or [-1])
                )
            )
        )
        convergence_ids = [item.id for item in convergences]
        alternatives = list(
            db.scalars(
                select(PortfolioConvergedAlternative).where(
                    PortfolioConvergedAlternative.convergence_id.in_(convergence_ids or [-1])
                )
            )
        )
        alternative_ids = [item.id for item in alternatives]
        event_targets = [
            *workspace_ids,
            *configuration_ids,
            *evaluation_ids,
            *scenario_ids,
            *target_ids,
            *project_dependency_ids,
            *resource_scenario_ids,
            *capacity_plan_ids,
            *demand_profile_ids,
            *definition_action_ids,
            *definition_assessment_ids,
            *fel_status_ids,
            *funding_assignment_ids,
            *fund_ids,
            *funding_source_ids,
            *readiness_snapshot_ids,
            *convergence_ids,
            *alternative_ids,
        ]
        if event_targets:
            db.execute(delete(SecurityEvent).where(SecurityEvent.target_id.in_(event_targets)))
        if evaluation_ids:
            db.execute(delete(PortfolioProjectEvaluation).where(PortfolioProjectEvaluation.id.in_(evaluation_ids)))
        if definition_action_ids:
            db.execute(delete(ProjectDefinitionAction).where(ProjectDefinitionAction.id.in_(definition_action_ids)))
        if fel_status_ids:
            db.execute(delete(ProjectFELStatus).where(ProjectFELStatus.id.in_(fel_status_ids)))
        if definition_assessment_ids:
            db.execute(
                delete(ProjectDefinitionAssessment).where(ProjectDefinitionAssessment.id.in_(definition_assessment_ids))
            )
        if readiness_snapshot_ids:
            db.execute(delete(FundingReadinessSnapshot).where(FundingReadinessSnapshot.id.in_(readiness_snapshot_ids)))
        if funding_assignment_ids:
            db.execute(delete(FundingAssignment).where(FundingAssignment.id.in_(funding_assignment_ids)))
        if fund_ids:
            db.execute(delete(Fund).where(Fund.id.in_(fund_ids)))
        if funding_source_ids:
            db.execute(delete(StrategicFundingSource).where(StrategicFundingSource.id.in_(funding_source_ids)))
        if convergence_ids:
            db.execute(
                update(PortfolioScenarioConvergence)
                .where(PortfolioScenarioConvergence.id.in_(convergence_ids))
                .values(status="VOIDED", recommended_alternative_id=None)
            )
        if alternative_ids:
            db.execute(
                delete(PortfolioConvergedAlternative).where(PortfolioConvergedAlternative.id.in_(alternative_ids))
            )
        if convergence_ids:
            db.execute(delete(PortfolioScenarioConvergence).where(PortfolioScenarioConvergence.id.in_(convergence_ids)))
        if scenario_ids:
            db.execute(
                delete(PortfolioBudgetScenarioProject).where(
                    PortfolioBudgetScenarioProject.scenario_id.in_(scenario_ids)
                )
            )
            db.execute(delete(PortfolioBudgetScenario).where(PortfolioBudgetScenario.id.in_(scenario_ids)))
        if target_ids:
            db.execute(
                delete(PortfolioBudgetTargetPeriod).where(PortfolioBudgetTargetPeriod.budget_target_id.in_(target_ids))
            )
            db.execute(delete(PortfolioBudgetTarget).where(PortfolioBudgetTarget.id.in_(target_ids)))
        if project_dependency_ids:
            db.execute(delete(ProjectDependency).where(ProjectDependency.id.in_(project_dependency_ids)))
        if resource_scenario_ids:
            db.execute(
                delete(PortfolioResourceScenarioProject).where(
                    PortfolioResourceScenarioProject.scenario_id.in_(resource_scenario_ids)
                )
            )
            db.execute(delete(PortfolioResourceScenario).where(PortfolioResourceScenario.id.in_(resource_scenario_ids)))
        if capacity_plan_ids:
            db.execute(
                delete(PortfolioResourceCapacityPeriod).where(
                    PortfolioResourceCapacityPeriod.capacity_plan_id.in_(capacity_plan_ids)
                )
            )
            db.execute(
                delete(PortfolioResourceCapacityPlan).where(PortfolioResourceCapacityPlan.id.in_(capacity_plan_ids))
            )
        if demand_profile_ids:
            db.execute(
                delete(ProjectResourceDemandPeriod).where(
                    ProjectResourceDemandPeriod.demand_profile_id.in_(demand_profile_ids)
                )
            )
            db.execute(
                delete(ProjectResourceDemandProfile).where(ProjectResourceDemandProfile.id.in_(demand_profile_ids))
            )
        baseline_by_key = {(str(item["rule_code"]), str(item["scope_key"])): item for item in sequence_baseline}
        for rule_code in ("funding-source", "fund", "funding-assignment"):
            sequence = db.scalar(
                select(AdminNumberSequence).where(
                    AdminNumberSequence.tenant_id == admin.tenant_id,
                    AdminNumberSequence.rule_code == rule_code,
                    AdminNumberSequence.scope_key == "tenant",
                )
            )
            original = baseline_by_key.get((rule_code, "tenant"))
            if original is None and sequence is not None:
                db.delete(sequence)
            elif original is not None:
                if sequence is None:
                    sequence = AdminNumberSequence(
                        tenant_id=admin.tenant_id,
                        rule_code=rule_code,
                        scope_key="tenant",
                    )
                    db.add(sequence)
                sequence.next_value = int(original["next_value"])
                sequence.version = int(original["version"])
        if workspace_ids:
            db.execute(
                delete(PortfolioProjectMembership).where(
                    or_(
                        PortfolioProjectMembership.project_workspace_id.in_(project_ids or [-1]),
                        PortfolioProjectMembership.portfolio_workspace_id.in_(portfolio_ids or [-1]),
                    )
                )
            )
        if configuration_ids:
            db.execute(delete(AdminConfiguration).where(AdminConfiguration.id.in_(configuration_ids)))
        if project_ids:
            db.execute(delete(EnterpriseWorkspace).where(EnterpriseWorkspace.id.in_(project_ids)))
        if portfolio_ids:
            db.execute(delete(EnterpriseWorkspace).where(EnterpriseWorkspace.id.in_(portfolio_ids)))
        if reviewer_ids:
            db.execute(delete(SecurityEvent).where(SecurityEvent.user_id.in_(reviewer_ids)))
            db.execute(delete(SecurityAccessAssignment).where(SecurityAccessAssignment.user_id.in_(reviewer_ids)))
            db.execute(delete(AuthCredential).where(AuthCredential.user_id.in_(reviewer_ids)))
            db.execute(delete(UserAccount).where(UserAccount.id.in_(reviewer_ids)))
        db.commit()
        result = {
            "run_id": safe,
            "deleted": {
                "workspaces": len(workspace_ids),
                "memberships": len(project_ids),
                "evaluations": len(evaluation_ids),
                "configurations": len(configuration_ids),
                "budget_scenarios": len(scenario_ids),
                "budget_targets": len(target_ids),
                "project_dependencies": len(project_dependency_ids),
                "resource_scenarios": len(resource_scenario_ids),
                "capacity_plans": len(capacity_plan_ids),
                "demand_profiles": len(demand_profile_ids),
                "convergences": len(convergence_ids),
                "convergence_alternatives": len(alternative_ids),
                "fel_statuses": len(fel_status_ids),
                "definition_assessments": len(definition_assessment_ids),
                "definition_actions": len(definition_action_ids),
                "definition_reviewers": len(reviewer_ids),
                "strategic_funding_sources": len(funding_source_ids),
                "funds": len(fund_ids),
                "funding_assignments": len(funding_assignment_ids),
                "funding_readiness_snapshots": len(readiness_snapshot_ids),
            },
            "remaining_workspaces": db.scalar(
                select(func.count(EnterpriseWorkspace.id)).where(EnterpriseWorkspace.code.like(workspace_prefix))
            ),
            "remaining_configurations": db.scalar(
                select(func.count(AdminConfiguration.id)).where(AdminConfiguration.code.like(configuration_prefix))
            ),
        }
    if emit:
        print(json.dumps(result, sort_keys=True))
    return result


def baseline() -> dict:
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        if admin is None:
            raise RuntimeError("Demo tenant not seeded")
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        project_14 = db.get(EnterpriseWorkspace, 14)
        defaults_md5 = (
            db.scalar(
                select(func.md5(cast(EnterpriseWorkspace.defaults_json, Text))).where(EnterpriseWorkspace.id == 14)
            )
            if project_14
            else None
        )
        starter = list(
            db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == admin.tenant_id,
                    AdminConfiguration.kind == EVALUATION_CONFIGURATION_KIND,
                    AdminConfiguration.code == EVALUATION_DEFAULT_CODE,
                )
            )
        )
        analysis_starter = list(
            db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == admin.tenant_id,
                    AdminConfiguration.kind == ANALYSIS_CONFIGURATION_KIND,
                    AdminConfiguration.code == ANALYSIS_DEFAULT_CODE,
                )
            )
        )
        budget_starter = list(
            db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == admin.tenant_id,
                    AdminConfiguration.kind == BUDGET_CONFIGURATION_KIND,
                    AdminConfiguration.code == BUDGET_DEFAULT_CODE,
                )
            )
        )
        sequence_state = [
            {
                "rule_code": item.rule_code,
                "scope_key": item.scope_key,
                "next_value": item.next_value,
                "version": item.version,
            }
            for item in db.scalars(
                select(AdminNumberSequence)
                .where(AdminNumberSequence.tenant_id == admin.tenant_id)
                .order_by(AdminNumberSequence.rule_code, AdminNumberSequence.scope_key)
            ).all()
        ]
        return {
            "alembic_head": revision,
            "enterprise_workspaces": db.scalar(
                select(func.count(EnterpriseWorkspace.id)).where(EnterpriseWorkspace.tenant_id == admin.tenant_id)
            ),
            "project_workspaces": db.scalar(
                select(func.count(EnterpriseWorkspace.id)).where(
                    EnterpriseWorkspace.tenant_id == admin.tenant_id,
                    EnterpriseWorkspace.workspace_type_code == "project",
                )
            ),
            "project_creation_requests": db.scalar(
                select(func.count(ProjectCreationRequest.id)).where(ProjectCreationRequest.tenant_id == admin.tenant_id)
            ),
            "portfolio_memberships": db.scalar(
                select(func.count(PortfolioProjectMembership.id)).where(
                    PortfolioProjectMembership.tenant_id == admin.tenant_id
                )
            ),
            "gate07e_evaluations": db.scalar(
                select(func.count(PortfolioProjectEvaluation.id)).where(
                    PortfolioProjectEvaluation.tenant_id == admin.tenant_id
                )
            ),
            "fel_statuses": db.scalar(
                select(func.count(ProjectFELStatus.id)).where(ProjectFELStatus.tenant_id == admin.tenant_id)
            ),
            "definition_assessments": db.scalar(
                select(func.count(ProjectDefinitionAssessment.id)).where(
                    ProjectDefinitionAssessment.tenant_id == admin.tenant_id
                )
            ),
            "definition_actions": db.scalar(
                select(func.count(ProjectDefinitionAction.id)).where(
                    ProjectDefinitionAction.tenant_id == admin.tenant_id
                )
            ),
            "gate07j_preparations": db.scalar(
                select(func.count(InvestmentGatePreparation.id)).where(
                    InvestmentGatePreparation.tenant_id == admin.tenant_id
                )
            ),
            "gate07j_evidence_items": db.scalar(
                select(func.count(InvestmentGateEvidenceItem.id)).where(
                    InvestmentGateEvidenceItem.tenant_id == admin.tenant_id
                )
            ),
            "strategic_funding_sources": db.scalar(
                select(func.count(StrategicFundingSource.id)).where(StrategicFundingSource.tenant_id == admin.tenant_id)
            ),
            "funds": db.scalar(select(func.count(Fund.id)).where(Fund.tenant_id == admin.tenant_id)),
            "funding_assignments": db.scalar(
                select(func.count(FundingAssignment.id)).where(FundingAssignment.tenant_id == admin.tenant_id)
            ),
            "funding_readiness_snapshots": db.scalar(
                select(func.count(FundingReadinessSnapshot.id)).where(
                    FundingReadinessSnapshot.tenant_id == admin.tenant_id
                )
            ),
            "admin_configurations": db.scalar(
                select(func.count(AdminConfiguration.id)).where(AdminConfiguration.tenant_id == admin.tenant_id)
            ),
            "user_accounts": db.scalar(
                select(func.count(UserAccount.id)).where(UserAccount.tenant_id == admin.tenant_id)
            ),
            "access_assignments": db.scalar(
                select(func.count(SecurityAccessAssignment.id)).where(
                    SecurityAccessAssignment.tenant_id == admin.tenant_id
                )
            ),
            "number_sequences": sequence_state,
            "gate07e_starter_draft": sum(item.status == "draft" for item in starter),
            "gate07e_starter_published": sum(item.status == "published" for item in starter),
            "gate07f_starter_draft": sum(item.status == "draft" for item in analysis_starter),
            "gate07f_starter_published": sum(item.status == "published" for item in analysis_starter),
            "gate07g_starter_draft": sum(item.status == "draft" for item in budget_starter),
            "gate07g_starter_published": sum(item.status == "published" for item in budget_starter),
            "project_14_defaults_md5": defaults_md5,
        }


def prepare() -> dict:
    """Create deliberate product starter records before persistent-baseline capture."""
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        if admin is None:
            raise RuntimeError("Demo tenant not seeded")
        ensure_enterprise_permissions(db, admin.tenant_id, admin.id)
        PortfolioAnalysisService(db, admin.tenant_id, admin.id).ensure_seed()
        PortfolioBudgetService(db, admin.tenant_id, admin.id).ensure_seed()
        PortfolioResourceService(db, admin.tenant_id, admin.id).ensure_seed()
        PortfolioConvergenceService(db, admin.tenant_id, admin.id).ensure_seed()
        ProjectDefinitionService(db, admin.tenant_id, admin.id).ensure_seed()
        FundsManagerService(db, admin.tenant_id, admin.id).ensure_seed()
    return baseline()


def complete_budget_prerequisites(run_id: str) -> dict:
    """Complete disposable main-Portfolio evaluations for isolated 07F/07G browser runs."""
    from tests.test_portfolio_analysis_gate07f import _complete

    safe = _safe_run_id(run_id)
    prefix = _prefix(safe)
    completed = 0
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        if admin is None:
            raise RuntimeError("Demo tenant not seeded")
        portfolios = list(
            db.scalars(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == admin.tenant_id,
                    EnterpriseWorkspace.workspace_type_code == "portfolio",
                    EnterpriseWorkspace.code.like(f"{prefix}-R%-PF-MAIN"),
                )
            )
        )
        service = PortfolioEvaluationService(db, admin.tenant_id, admin.id)
        for portfolio in portfolios:
            stem = portfolio.code.removesuffix("-PF-MAIN")
            projects = [
                db.scalar(
                    select(EnterpriseWorkspace).where(
                        EnterpriseWorkspace.tenant_id == admin.tenant_id,
                        EnterpriseWorkspace.code == f"{stem}-PRJ-{key}",
                    )
                )
                for key in ("A", "B", "C")
            ]
            if any(project is None for project in projects):
                raise RuntimeError(f"Gate 07G prerequisite projects missing for {portfolio.code}")
            for project, rating in zip(projects, (5, 4, 3), strict=True):
                assert project is not None
                _complete(service, portfolio.id, project.id, rating)
                completed += 1
        db.commit()
    return {"run_id": safe, "completed_evaluations": completed}


def complete_funds_prerequisites(run_id: str) -> dict:
    """Build the governed 07F-07I source chain required by Funds Manager E2E.

    This deliberately uses the domain services instead of HTTP shortcuts so every
    immutable snapshot/hash is identical to production behavior.  Existing frozen
    branches and a current recommendation are reused, making the command safe to
    replay after a partially interrupted browser run.
    """
    from tests.test_portfolio_analysis_gate07f import _complete

    safe = _safe_run_id(run_id)
    prefix = _prefix(safe)
    counters = {
        "completed_evaluations": 0,
        "budget_scenarios": 0,
        "resource_scenarios": 0,
        "recommendations": 0,
    }
    contracts: list[dict] = []
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        if admin is None:
            raise RuntimeError("Demo tenant not seeded")
        portfolios = list(
            db.scalars(
                select(EnterpriseWorkspace)
                .where(
                    EnterpriseWorkspace.tenant_id == admin.tenant_id,
                    EnterpriseWorkspace.workspace_type_code == "portfolio",
                    EnterpriseWorkspace.code.like(f"{prefix}-R%-PF-MAIN"),
                )
                .order_by(EnterpriseWorkspace.code)
            )
        )
        for portfolio in portfolios:
            existing_recommendation = db.scalar(
                select(PortfolioScenarioConvergence).where(
                    PortfolioScenarioConvergence.tenant_id == admin.tenant_id,
                    PortfolioScenarioConvergence.portfolio_workspace_id == portfolio.id,
                    PortfolioScenarioConvergence.status == "RECOMMENDED",
                )
            )
            convergence_service = PortfolioConvergenceService(db, admin.tenant_id, admin.id)
            if existing_recommendation is not None:
                contract = convergence_service.preparation_contract(portfolio.id)
                contracts.append(
                    {
                        "portfolio_id": portfolio.id,
                        "status": contract.final_output,
                        "recommendation_hash": contract.recommendation_hash,
                    }
                )
                continue

            stem = portfolio.code.removesuffix("-PF-MAIN")
            projects = [
                db.scalar(
                    select(EnterpriseWorkspace).where(
                        EnterpriseWorkspace.tenant_id == admin.tenant_id,
                        EnterpriseWorkspace.code == f"{stem}-PRJ-{key}",
                    )
                )
                for key in ("A", "B", "C")
            ]
            if any(project is None for project in projects):
                raise RuntimeError(f"Gate 07J FUND prerequisite projects missing for {portfolio.code}")

            evaluator = PortfolioEvaluationService(db, admin.tenant_id, admin.id)
            for project, rating in zip(projects, (5, 4, 3), strict=True):
                assert project is not None
                completed = db.scalar(
                    select(PortfolioProjectEvaluation).where(
                        PortfolioProjectEvaluation.tenant_id == admin.tenant_id,
                        PortfolioProjectEvaluation.portfolio_workspace_id == portfolio.id,
                        PortfolioProjectEvaluation.project_workspace_id == project.id,
                        PortfolioProjectEvaluation.status == "COMPLETED",
                    )
                )
                if completed is None:
                    _complete(evaluator, portfolio.id, project.id, rating)
                    counters["completed_evaluations"] += 1

            analysis_hash = (
                PortfolioAnalysisService(db, admin.tenant_id, admin.id).overview(portfolio.id).dataset.analysis_hash
            )
            budget_scenario = db.scalar(
                select(PortfolioBudgetScenario)
                .where(
                    PortfolioBudgetScenario.tenant_id == admin.tenant_id,
                    PortfolioBudgetScenario.portfolio_workspace_id == portfolio.id,
                    PortfolioBudgetScenario.status == "FROZEN",
                )
                .order_by(PortfolioBudgetScenario.id.desc())
            )
            if budget_scenario is None:
                budget = PortfolioBudgetService(db, admin.tenant_id, admin.id)
                target = budget.create_target(
                    portfolio.id,
                    BudgetTargetCreateIn(
                        planning_horizon_start=date(2027, 1, 1),
                        planning_horizon_end=date(2027, 12, 31),
                        period_granularity="YEAR",
                        budget_currency="COP",
                        total_budget_target="1000000000",
                        periods=[
                            TargetPeriodIn(
                                period_key="2027",
                                period_start=date(2027, 1, 1),
                                period_end=date(2027, 12, 31),
                                amount="1000000000",
                            )
                        ],
                        source_reference=f"Gate 07J FUND H envelope {portfolio.code}",
                        idempotency_key=f"{safe}-budget-target-{portfolio.id}",
                    ),
                )
                target = budget.publish_target(
                    target.id,
                    target.revision_version,
                    f"{safe}-budget-publish-{portfolio.id}",
                )
                created = budget.create_scenario(
                    portfolio.id,
                    BudgetScenarioCreateIn(
                        scenario_name="Gate 07J FUND H aligned budget",
                        budget_target_id=target.id,
                        creation_mode="FROM_CURRENT_PRIORITY",
                        time_phasing_method="UNPHASED",
                        expected_analysis_hash=analysis_hash,
                        idempotency_key=f"{safe}-budget-scenario-{portfolio.id}",
                    ),
                )
                budget_scenario = budget.freeze_scenario(
                    created.id,
                    created.revision_version,
                    f"{safe}-budget-freeze-{portfolio.id}",
                )
                counters["budget_scenarios"] += 1

            resource_scenario = db.scalar(
                select(PortfolioResourceScenario)
                .where(
                    PortfolioResourceScenario.tenant_id == admin.tenant_id,
                    PortfolioResourceScenario.portfolio_workspace_id == portfolio.id,
                    PortfolioResourceScenario.status == "FROZEN",
                )
                .order_by(PortfolioResourceScenario.id.desc())
            )
            if resource_scenario is None:
                resource = PortfolioResourceService(db, admin.tenant_id, admin.id)
                capacity = resource.create_capacity_plan(
                    portfolio.id,
                    CapacityPlanCreateIn(
                        plan_name="Gate 07J FUND H strategic capacity",
                        planning_horizon_start=date(2027, 1, 1),
                        planning_horizon_end=date(2027, 12, 31),
                        period_granularity="YEAR",
                        source_reference=f"Gate 07J FUND H workforce plan {portfolio.code}",
                        periods=[
                            CapacityPeriodIn(
                                resource_role_key="PROJECT_MANAGER",
                                resource_role_name="Project Manager",
                                role_category="MANAGEMENT",
                                period_key="2027",
                                period_start=date(2027, 1, 1),
                                period_end=date(2027, 12, 31),
                                capacity_value=Decimal("1000"),
                                unit="FTE",
                            )
                        ],
                        idempotency_key=f"{safe}-capacity-{portfolio.id}",
                    ),
                )
                capacity = resource.publish_capacity_plan(
                    capacity.id,
                    capacity.revision_version,
                    f"{safe}-capacity-publish-{portfolio.id}",
                )
                for project in projects:
                    assert project is not None
                    demand = resource.create_demand_profile(
                        project.id,
                        DemandProfileCreateIn(
                            profile_name="Gate 07J FUND H demand",
                            source_type="PROJECT_RESOURCE_DEMAND_PROFILE",
                            source_reference=f"Gate 07J FUND H demand {project.id}",
                            as_of_date=date(2026, 8, 29),
                            planning_start=date(2027, 1, 1),
                            planning_finish=date(2027, 12, 31),
                            generation_method="EXPLICIT_PERIOD_PROFILE",
                            periods=[
                                DemandPeriodIn(
                                    resource_role_key="PROJECT_MANAGER",
                                    resource_role_name="Project Manager",
                                    role_category="MANAGEMENT",
                                    period_key="2027",
                                    period_start=date(2027, 1, 1),
                                    period_end=date(2027, 12, 31),
                                    demand_value=Decimal("0.5"),
                                    unit="FTE",
                                )
                            ],
                            idempotency_key=f"{safe}-demand-{project.id}",
                        ),
                    )
                    resource.publish_demand_profile(
                        demand.id,
                        demand.revision_version,
                        f"{safe}-demand-publish-{project.id}",
                    )
                created = resource.create_scenario(
                    portfolio.id,
                    ResourceScenarioCreateIn(
                        scenario_name="Gate 07J FUND H aligned resources",
                        capacity_plan_id=capacity.id,
                        creation_mode="FROM_CURRENT_PRIORITY",
                        expected_analysis_hash=analysis_hash,
                        idempotency_key=f"{safe}-resource-scenario-{portfolio.id}",
                    ),
                )
                resource_scenario = resource.freeze_scenario(
                    created.id,
                    created.revision_version,
                    f"{safe}-resource-freeze-{portfolio.id}",
                )
                counters["resource_scenarios"] += 1

            convergence = convergence_service.create_convergence(
                portfolio.id,
                ConvergenceCreateIn(
                    name="Gate 07J FUND H source recommendation",
                    description="Frozen budget and resource branches for Funds Manager closeout.",
                    idempotency_key=f"{safe}-convergence-{portfolio.id}",
                ),
            )
            convergence = convergence_service.add_alternative(
                convergence.id,
                convergence.revision_version,
                "Governed aligned baseline",
                budget_scenario.id,
                resource_scenario.id,
                f"{safe}-alternative-{portfolio.id}",
            )
            alternative = convergence.alternatives[0]
            convergence = convergence_service.submit_review(
                convergence.id,
                convergence.revision_version,
                f"{safe}-submit-{portfolio.id}",
            )
            convergence_service.recommend(
                convergence.id,
                convergence.revision_version,
                RecommendationIn(
                    recommended_alternative_id=alternative.id,
                    recommendation_reason="Governed budget and resource branches are aligned for funding readiness.",
                    risks_acknowledged=["Investment authorization remains outside this gate."],
                    decision_support_summary="The selected source alternative is feasible and current for Funds Manager validation.",
                    idempotency_key=f"{safe}-recommend-{portfolio.id}",
                ),
            )
            counters["recommendations"] += 1
            contract = convergence_service.preparation_contract(portfolio.id)
            contracts.append(
                {
                    "portfolio_id": portfolio.id,
                    "status": contract.final_output,
                    "recommendation_hash": contract.recommendation_hash,
                }
            )
        db.commit()
    return {"run_id": safe, **counters, "contracts": contracts}


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    seed_parser = subparsers.add_parser("seed")
    seed_parser.add_argument("--run-id", required=True)
    seed_parser.add_argument("--copies", type=int, default=3, choices=range(1, 6))
    teardown_parser = subparsers.add_parser("teardown")
    teardown_parser.add_argument("--run-id", required=True)
    complete_parser = subparsers.add_parser("complete")
    complete_parser.add_argument("--run-id", required=True)
    funds_parser = subparsers.add_parser("funds-prerequisites")
    funds_parser.add_argument("--run-id", required=True)
    subparsers.add_parser("baseline")
    subparsers.add_parser("prepare")
    args = parser.parse_args()
    if args.command == "seed":
        print(json.dumps(seed(args.run_id, args.copies), sort_keys=True))
    elif args.command == "teardown":
        teardown(args.run_id)
    elif args.command == "baseline":
        print(json.dumps(baseline(), sort_keys=True))
    elif args.command == "complete":
        print(json.dumps(complete_budget_prerequisites(args.run_id), sort_keys=True))
    elif args.command == "funds-prerequisites":
        print(json.dumps(complete_funds_prerequisites(args.run_id), sort_keys=True))
    else:
        print(json.dumps(prepare(), sort_keys=True))


if __name__ == "__main__":
    main()
