"""Specific RBAC evaluation for Enterprise Structure endpoints."""

from dataclasses import dataclass
from threading import RLock

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1._helpers import require_tenant_configurator
from app.core.time import utc_now
from app.domain.models import (
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityGroupMember,
    SecurityRole,
    SecurityRolePermission,
    Tenant,
    UserAccount,
)
from app.modules.enterprise_structure.constants import PERMISSION_SEED

WORKSPACE_OPERATION_PERMISSIONS = frozenset(
    {
        "workspace.open",
        "workspace.home.read",
        "workspace.navigator.read",
        "workspace.recent.read",
        "workspace.recent.write",
    }
)

STRUCTURE_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "structure_editor": frozenset(
        {
            "admin.enterprise_structure.revision.create",
            "admin.enterprise_structure.revision.edit",
            "admin.enterprise_structure.revision.validate",
            "admin.enterprise_structure.revision.compare",
        }
    ),
    "structure_approver": frozenset(
        {
            "admin.enterprise_structure.revision.compare",
            "admin.enterprise_structure.revision.approve",
        }
    ),
    "structure_publisher": frozenset(
        {
            "admin.enterprise_structure.revision.compare",
            "admin.enterprise_structure.publish",
            "admin.enterprise_structure.rollback",
        }
    ),
}

STRUCTURE_ROLE_DEFINITIONS = {
    "structure_editor": (
        "Structure Editor",
        "Creates, edits, validates and compares governed workspace revisions.",
    ),
    "structure_approver": (
        "Structure Approver",
        "Compares and approves a validated workspace revision.",
    ),
    "structure_publisher": (
        "Structure Publisher",
        "Publishes approved successors and executes logical rollback.",
    ),
}

PROJECT_CREATION_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "project_requestor": frozenset(
        {
            "project_creation.request.create",
            "project_creation.request.edit",
            "project_creation.request.submit",
            "project_creation.request.read",
            "project_creation.contract_source.create",
            "project_creation.direct.create",
            "project_governance_model.read",
            "enterprise_structure.read",
        }
    ),
    "project_reviewer": frozenset(
        {
            "project_creation.request.read",
            "project_creation.review",
            "project_governance_model.read",
            "enterprise_structure.read",
        }
    ),
    "project_approver": frozenset(
        {
            "project_creation.request.read",
            "project_creation.approve",
            "project_governance_model.read",
            "enterprise_structure.read",
        }
    ),
    "project_materialization_service": frozenset(
        {
            "project_creation.request.read",
            "project_creation.materialize",
            "project_governance_model.read",
            "enterprise_structure.read",
        }
    ),
    "project_manager": frozenset(
        {"enterprise_structure.read", "project_workspace.initialization.read", "project_governance_model.read"}
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
}

PROJECT_CREATION_ROLE_DEFINITIONS = {
    "project_requestor": ("Project Requestor", "Creates and submits governed Project Workspace requests."),
    "project_reviewer": ("Project Reviewer", "Reviews, returns and rejects Project Workspace requests."),
    "project_approver": ("Project Approver", "Approves Project Workspace requests under Four-Eyes."),
    "project_materialization_service": (
        "Project Materialization Service",
        "Highly restricted role that materializes approved Project Workspaces.",
    ),
    "project_manager": ("Project Manager", "Minimum Workspace-scoped access for the assigned Project Manager."),
}

PROJECT_WORKSPACE_LIFECYCLE_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "project_workspace_initializer": frozenset(
        {
            "project_workspace.initialization.read",
            "project_workspace.initialization.execute",
            "enterprise_structure.read",
        }
    ),
    "project_workspace_activator": frozenset(
        {
            "project_workspace.initialization.read",
            "project_workspace.activation.execute",
            "enterprise_structure.read",
        }
    ),
}

PROJECT_WORKSPACE_LIFECYCLE_ROLE_DEFINITIONS = {
    "project_workspace_initializer": (
        "Project Workspace Initializer",
        "Previews, initializes and validates materialized Project Workspaces.",
    ),
    "project_workspace_activator": (
        "Project Workspace Activator",
        "Independently activates Project Workspaces that passed initialization.",
    ),
}

PHYSICAL_WORKSPACE_CREATION_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "physical_workspace_requestor": frozenset(
        {
            "physical_workspace_creation.request.create",
            "physical_workspace_creation.request.edit",
            "physical_workspace_creation.request.submit",
            "physical_workspace_creation.request.read",
            "enterprise_structure.read",
        }
    ),
    "physical_workspace_reviewer": frozenset(
        {
            "physical_workspace_creation.request.read",
            "physical_workspace_creation.review",
            "enterprise_structure.read",
        }
    ),
    "physical_workspace_approver": frozenset(
        {
            "physical_workspace_creation.request.read",
            "physical_workspace_creation.approve",
            "enterprise_structure.read",
        }
    ),
    "physical_workspace_materialization_service": frozenset(
        {
            "physical_workspace_creation.request.read",
            "physical_workspace_creation.materialize",
            "enterprise_structure.read",
        }
    ),
    "physical_workspace_responsible": frozenset({"enterprise_structure.read", "physical_workspace.initialization.read"})
    | WORKSPACE_OPERATION_PERMISSIONS,
}

PHYSICAL_WORKSPACE_CREATION_ROLE_DEFINITIONS = {
    "physical_workspace_requestor": (
        "Physical Workspace Requestor",
        "Creates and submits governed Property, Facility and Warehouse requests.",
    ),
    "physical_workspace_reviewer": (
        "Physical Workspace Reviewer",
        "Reviews, returns and rejects governed physical Workspace requests.",
    ),
    "physical_workspace_approver": (
        "Physical Workspace Approver",
        "Approves governed physical Workspace requests under Four-Eyes.",
    ),
    "physical_workspace_materialization_service": (
        "Physical Workspace Materialization Service",
        "Restricted service role that materializes approved physical Workspaces.",
    ),
    "physical_workspace_responsible": (
        "Physical Workspace Responsible",
        "Minimum Workspace-scoped access for the assigned physical Workspace responsible.",
    ),
}

PHYSICAL_WORKSPACE_LIFECYCLE_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "physical_workspace_initializer": frozenset(
        {
            "physical_workspace.initialization.read",
            "physical_workspace.initialization.execute",
            "enterprise_structure.read",
        }
    ),
    "physical_workspace_activator": frozenset(
        {
            "physical_workspace.initialization.read",
            "physical_workspace.activation.execute",
            "enterprise_structure.read",
        }
    ),
}

PHYSICAL_WORKSPACE_LIFECYCLE_ROLE_DEFINITIONS = {
    "physical_workspace_initializer": (
        "Physical Workspace Initializer",
        "Previews, initializes, retries and validates Property, Facility and Warehouse Workspaces.",
    ),
    "physical_workspace_activator": (
        "Physical Workspace Activator",
        "Independently activates physical Workspaces that passed initialization.",
    ),
}

IDEA_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "idea_requestor": frozenset({"idea.read", "idea.create", "idea.edit", "idea.submit", "idea.cancel"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "idea_intake_reviewer": frozenset({"idea.read", "idea.screen", "idea.route", "idea.assign_owner"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "idea_owner": frozenset({"idea.read", "idea.evaluate"}) | WORKSPACE_OPERATION_PERMISSIONS,
    "idea_decision_maker": frozenset({"idea.read", "idea.decide"}) | WORKSPACE_OPERATION_PERMISSIONS,
    "idea_configuration_admin": frozenset({"idea.read", "idea.admin.configure", "idea.admin.publish"}),
}

IDEA_ROLE_DEFINITIONS = {
    "idea_requestor": ("Idea Requestor", "Creates, edits and submits governed enterprise ideas."),
    "idea_intake_reviewer": ("Idea Intake Reviewer", "Screens, routes and assigns owners to submitted ideas."),
    "idea_owner": ("Idea Owner", "Owns and evaluates assigned ideas."),
    "idea_decision_maker": ("Idea Decision Maker", "Accepts or rejects evaluated ideas."),
    "idea_configuration_admin": ("Idea Configuration Admin", "Configures and publishes the Idea lifecycle."),
}

CAPITAL_PLANNING_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "capital_planning_cycle_manager": frozenset(
        {
            "capital_planning.read",
            "capital_planning.cycle.create",
            "capital_planning.cycle.close",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "capital_planning_author": frozenset(
        {
            "capital_planning.read",
            "capital_planning.demand.create",
            "capital_planning.demand.edit",
            "capital_planning.demand.submit",
            "capital_planning.allocation.read",
            "capital_planning.allocation.create",
            "capital_planning.allocation.edit",
            "capital_planning.allocation.submit",
            "capital_planning.bucket.classify",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "capital_planning_reviewer": frozenset(
        {
            "capital_planning.read",
            "capital_planning.demand.review",
            "capital_planning.allocation.read",
            "capital_planning.allocation.review",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "capital_planning_endorser": frozenset(
        {
            "capital_planning.read",
            "capital_planning.demand.endorse",
            "capital_planning.allocation.read",
            "capital_planning.allocation.endorse",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "capital_planning_originator": frozenset(
        {"capital_planning.read", "capital_planning.idea.originate", "idea.read", "idea.create"}
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "capital_planning_viewer": frozenset({"capital_planning.read", "capital_planning.allocation.read"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "capital_planning_allocation_author": frozenset(
        {
            "capital_planning.read",
            "capital_planning.allocation.read",
            "capital_planning.allocation.create",
            "capital_planning.allocation.edit",
            "capital_planning.allocation.submit",
            "capital_planning.bucket.classify",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "capital_planning_allocation_reviewer": frozenset(
        {"capital_planning.read", "capital_planning.allocation.read", "capital_planning.allocation.review"}
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "capital_planning_allocation_endorser": frozenset(
        {"capital_planning.read", "capital_planning.allocation.read", "capital_planning.allocation.endorse"}
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "capital_planning_bucket_classifier": frozenset(
        {"capital_planning.read", "capital_planning.allocation.read", "capital_planning.bucket.classify"}
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "capital_planning_config_admin": frozenset(
        {
            "capital_planning.read",
            "capital_planning.admin.configure",
            "capital_planning.admin.publish",
            "capital_planning.admin.bucket.configure",
            "capital_planning.admin.bucket.publish",
        }
    ),
}

CAPITAL_PLANNING_ROLE_DEFINITIONS = {
    "capital_planning_cycle_manager": (
        "Capital Planning Cycle Manager",
        "Creates and governs Capital Planning Cycles without configuring reusable policy.",
    ),
    "capital_planning_author": (
        "Capital Demand Author",
        "Creates, edits and submits Strategic Capital Demands.",
    ),
    "capital_planning_reviewer": (
        "Capital Demand Reviewer",
        "Reviews, returns and defers Strategic Capital Demands.",
    ),
    "capital_planning_endorser": (
        "Capital Demand Endorser",
        "Independently endorses governed capital needs without approving investment.",
    ),
    "capital_planning_originator": (
        "Capital Demand Idea Originator",
        "Explicitly originates Ideas from eligible endorsed Demands.",
    ),
    "capital_planning_viewer": (
        "Capital Planning Viewer",
        "Reads authorized cycles, demands, lineage and history.",
    ),
    "capital_planning_allocation_author": (
        "Strategic Allocation Plan Author",
        "Creates and edits governed Strategic Capital Allocation Plans without approving Budget or Funding.",
    ),
    "capital_planning_allocation_reviewer": (
        "Strategic Allocation Plan Reviewer",
        "Reviews and returns Strategic Capital Allocation Plans independently.",
    ),
    "capital_planning_allocation_endorser": (
        "Strategic Allocation Plan Endorser",
        "Endorses strategic allocation intent under separation of duties.",
    ),
    "capital_planning_bucket_classifier": (
        "Strategic Capital Bucket Classifier",
        "Classifies eligible Demands and Project contexts into one primary Bucket.",
    ),
    "capital_planning_config_admin": (
        "Capital Planning Configuration Admin",
        "Configures and publishes reusable Capital Planning policy without live transaction rights.",
    ),
}

BUSINESS_ANALYSIS_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "business_analysis_author": frozenset(
        {
            "business_analysis.read",
            "business_analysis.create",
            "business_analysis.edit",
            "business_analysis.submit",
            "idea.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "business_analysis_reviewer": frozenset({"business_analysis.read", "business_analysis.review", "idea.read"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "business_analysis_viewer": frozenset({"business_analysis.read", "idea.read"}) | WORKSPACE_OPERATION_PERMISSIONS,
    "business_analysis_config_admin": frozenset(
        {
            "business_analysis.read",
            "business_analysis.admin.configure",
            "business_analysis.admin.publish",
        }
    ),
}

BUSINESS_ANALYSIS_ROLE_DEFINITIONS = {
    "business_analysis_author": (
        "Business Analysis Author",
        "Creates and submits governed Business Analysis records.",
    ),
    "business_analysis_reviewer": (
        "Business Analysis Reviewer",
        "Reviews, returns and completes Business Analysis under separation of duties.",
    ),
    "business_analysis_viewer": (
        "Business Analysis Viewer",
        "Reads authorized Business Analysis records and their history.",
    ),
    "business_analysis_config_admin": (
        "Business Analysis Configuration Admin",
        "Configures and publishes reusable Business Analysis policy.",
    ),
}

PROJECT_PROPOSAL_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "proposal_requestor": frozenset(
        {
            "project_proposal.read",
            "project_proposal.create",
            "project_proposal.edit",
            "project_proposal.submit",
            "project_proposal.cancel",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "proposal_owner": frozenset({"project_proposal.read", "project_proposal.edit", "project_proposal.evaluate"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "proposal_reviewer": frozenset(
        {
            "project_proposal.read",
            "project_proposal.review",
            "project_proposal.return",
            "project_proposal.mark_gate_ready",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "proposal_evaluator": frozenset({"project_proposal.read", "project_proposal.evaluate"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "proposal_configuration_admin": frozenset(
        {
            "project_proposal.read",
            "project_proposal.admin.configure",
            "project_proposal.admin.publish",
        }
    ),
}

PROJECT_PROPOSAL_ROLE_DEFINITIONS = {
    "proposal_requestor": ("Proposal Requestor", "Creates and submits Project Proposals from accepted Ideas."),
    "proposal_owner": ("Proposal Owner", "Owns the strategic business case and Proposal evaluation."),
    "proposal_reviewer": ("Proposal Reviewer", "Reviews, returns and marks evaluated Proposals gate-ready."),
    "proposal_evaluator": ("Proposal Evaluator", "Evaluates Project Proposals with a published matrix."),
    "proposal_configuration_admin": (
        "Proposal Configuration Admin",
        "Configures and publishes the Project Proposal lifecycle.",
    ),
}

STRATEGIC_GATE_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "gate_preparer": frozenset(
        {
            "strategic_gate.read",
            "strategic_gate.create",
            "strategic_gate.edit",
            "strategic_gate.submit",
            "strategic_gate.void",
            "project_proposal.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "gate_reviewer": frozenset(
        {"strategic_gate.read", "strategic_gate.review", "strategic_gate.void", "project_proposal.read"}
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "gate_decision_maker": frozenset({"strategic_gate.read", "strategic_gate.decide", "project_proposal.read"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "gate_committee_member": frozenset({"strategic_gate.read", "strategic_gate.decide", "project_proposal.read"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "gate_configuration_admin": frozenset(
        {
            "strategic_gate.read",
            "strategic_gate.admin.configure",
            "strategic_gate.admin.publish",
        }
    ),
}

STRATEGIC_GATE_ROLE_DEFINITIONS = {
    "gate_preparer": ("Gate Preparer", "Prepares and submits governed Strategic Gate Decisions."),
    "gate_reviewer": ("Gate Reviewer", "Reviews Strategic Gate Decisions before formal decision."),
    "gate_decision_maker": ("Gate Decision Maker", "Records formal Strategic Gate outcomes."),
    "gate_committee_member": ("Gate Committee Member", "Participates in committee-based gate decisions."),
    "gate_configuration_admin": (
        "Gate Configuration Admin",
        "Configures and publishes Strategic Gate policies.",
    ),
}

PORTFOLIO_PLANNING_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "portfolio_intake_planner": frozenset(
        {
            "portfolio_project.read",
            "portfolio_project.intake",
            "portfolio_planning.readiness.read",
            "project_definition.readiness.read",
            "strategic_gate.read",
            "project_creation.request.create",
            "project_creation.request.edit",
            "project_creation.request.submit",
            "project_creation.request.read",
            "project_governance_model.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_membership_manager": frozenset(
        {
            "portfolio_project.read",
            "portfolio_project.membership.manage",
            "portfolio_planning.readiness.read",
            "project_definition.readiness.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_configuration_admin": frozenset(
        {
            "portfolio_project.read",
            "portfolio_project.admin.configure",
            "portfolio_project.admin.publish",
        }
    ),
}

PORTFOLIO_PLANNING_ROLE_DEFINITIONS = {
    "portfolio_intake_planner": (
        "Portfolio Intake Planner",
        "Creates strategic Project planning entries from approved Gate decisions.",
    ),
    "portfolio_membership_manager": (
        "Portfolio Membership Manager",
        "Manages analytical Project memberships without changing EWS hierarchy.",
    ),
    "portfolio_configuration_admin": (
        "Portfolio Configuration Admin",
        "Configures and publishes Portfolio Planning entry policies.",
    ),
}

PORTFOLIO_EVALUATION_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "portfolio_evaluator": frozenset(
        {
            "portfolio_evaluation.read",
            "portfolio_evaluation.create",
            "portfolio_evaluation.edit",
            "portfolio_evaluation.complete",
            "portfolio_evaluation.reevaluate",
            "portfolio_prioritization.read",
            "portfolio_project.read",
            "portfolio_planning.readiness.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_prioritization_viewer": frozenset(
        {
            "portfolio_evaluation.read",
            "portfolio_prioritization.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_evaluation_configuration_admin": frozenset(
        {
            "portfolio_evaluation.read",
            "portfolio_evaluation.admin.configure",
            "portfolio_evaluation.admin.publish",
        }
    ),
}

PORTFOLIO_EVALUATION_ROLE_DEFINITIONS = {
    "portfolio_evaluator": (
        "Portfolio Evaluator",
        "Scores eligible CAPITAL_OWNER Projects in their Portfolio context.",
    ),
    "portfolio_prioritization_viewer": (
        "Portfolio Prioritization Viewer",
        "Reads contextual Portfolio rankings and readiness without override authority.",
    ),
    "portfolio_evaluation_configuration_admin": (
        "Portfolio Evaluation Configuration Admin",
        "Configures and publishes Gate 07E matrices and ranking rules.",
    ),
}

PORTFOLIO_ANALYSIS_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "portfolio_analyst": frozenset(
        {
            "portfolio_analysis.read",
            "portfolio_evaluation.read",
            "portfolio_prioritization.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_analysis_viewer": frozenset(
        {
            "portfolio_analysis.read",
            "portfolio_prioritization.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_analysis_configuration_admin": frozenset(
        {
            "portfolio_analysis.read",
            "portfolio_analysis.admin.configure",
            "portfolio_analysis.admin.publish",
        }
    ),
}

PORTFOLIO_ANALYSIS_ROLE_DEFINITIONS = {
    "portfolio_analyst": (
        "Portfolio Analyst",
        "Uses governed Portfolio Analysis, Investor Map and Scorecard views.",
    ),
    "portfolio_analysis_viewer": (
        "Portfolio Analysis Viewer",
        "Reads Portfolio Analysis without source mutation or configuration authority.",
    ),
    "portfolio_analysis_configuration_admin": (
        "Portfolio Analysis Configuration Admin",
        "Configures and publishes Gate 07F metric, map and scorecard rules.",
    ),
}

PORTFOLIO_BUDGET_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "portfolio_budget_planner": frozenset(
        {
            "portfolio_budget.read",
            "portfolio_budget_target.create",
            "portfolio_budget_target.publish",
            "portfolio_budget_scenario.create",
            "portfolio_budget_scenario.edit",
            "portfolio_budget_scenario.freeze",
            "portfolio_budget_scenario.void",
            "portfolio_budget_scenario.force",
            "portfolio_budget_scenario.compare",
            "portfolio_dependency.read",
            "portfolio_dependency.manage",
            "portfolio_analysis.read",
            "portfolio_prioritization.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_budget_viewer": frozenset(
        {
            "portfolio_budget.read",
            "portfolio_budget_scenario.compare",
            "portfolio_dependency.read",
            "portfolio_analysis.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_budget_configuration_admin": frozenset(
        {
            "portfolio_budget.read",
            "portfolio_budget.admin.configure",
            "portfolio_budget.admin.publish",
            "portfolio_dependency.read",
        }
    ),
}

PORTFOLIO_BUDGET_ROLE_DEFINITIONS = {
    "portfolio_budget_planner": (
        "Portfolio Budget Planner",
        "Creates governed Budget Targets and analytical Budget Scenarios without investment approval authority.",
    ),
    "portfolio_budget_viewer": (
        "Portfolio Budget Viewer",
        "Reads Portfolio Budget Planning, comparison and readiness outputs.",
    ),
    "portfolio_budget_configuration_admin": (
        "Portfolio Budget Configuration Admin",
        "Configures and publishes Gate 07G budget planning policies.",
    ),
}

PORTFOLIO_RESOURCE_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "portfolio_resource_planner": frozenset(
        {
            "portfolio_resource.read",
            "portfolio_resource_capacity.create",
            "portfolio_resource_capacity.publish",
            "portfolio_resource_demand.read",
            "portfolio_resource_demand.create",
            "portfolio_resource_demand.publish",
            "portfolio_resource_scenario.create",
            "portfolio_resource_scenario.edit",
            "portfolio_resource_scenario.freeze",
            "portfolio_resource_scenario.void",
            "portfolio_resource_scenario.force",
            "portfolio_resource_scenario.compare",
            "portfolio_analysis.read",
            "portfolio_prioritization.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_resource_viewer": frozenset(
        {
            "portfolio_resource.read",
            "portfolio_resource_demand.read",
            "portfolio_resource_scenario.compare",
            "portfolio_analysis.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_resource_configuration_admin": frozenset(
        {
            "portfolio_resource.read",
            "portfolio_resource.admin.configure",
            "portfolio_resource.admin.publish",
        }
    ),
}

PORTFOLIO_RESOURCE_ROLE_DEFINITIONS = {
    "portfolio_resource_planner": (
        "Portfolio Resource Planner",
        "Plans strategic Role/Pool capacity and governed Resource Scenarios without named assignments.",
    ),
    "portfolio_resource_viewer": (
        "Portfolio Resource Viewer",
        "Reads strategic capacity, demand, comparison and readiness outputs.",
    ),
    "portfolio_resource_configuration_admin": (
        "Portfolio Resource Configuration Admin",
        "Configures and publishes Gate 07H resource planning policies.",
    ),
}

PORTFOLIO_CONVERGENCE_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "portfolio_recommendation_preparer": frozenset(
        {
            "portfolio_convergence.read",
            "portfolio_convergence.create",
            "portfolio_convergence.edit",
            "portfolio_convergence.compare",
            "portfolio_convergence.refresh",
            "portfolio_recommendation.submit",
            "portfolio_budget.read",
            "portfolio_resource.read",
            "portfolio_analysis.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_recommendation_reviewer": frozenset(
        {
            "portfolio_convergence.read",
            "portfolio_convergence.compare",
            "portfolio_recommendation.return",
            "portfolio_budget.read",
            "portfolio_resource.read",
            "portfolio_analysis.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_recommender": frozenset(
        {
            "portfolio_convergence.read",
            "portfolio_convergence.compare",
            "portfolio_recommendation.recommend",
            "portfolio_budget.read",
            "portfolio_resource.read",
            "portfolio_analysis.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_convergence_viewer": frozenset(
        {
            "portfolio_convergence.read",
            "portfolio_convergence.compare",
            "portfolio_budget.read",
            "portfolio_resource.read",
            "portfolio_analysis.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_convergence_configuration_admin": frozenset(
        {
            "portfolio_convergence.read",
            "portfolio_convergence.admin.configure",
            "portfolio_convergence.admin.publish",
        }
    ),
}

PORTFOLIO_CONVERGENCE_ROLE_DEFINITIONS = {
    "portfolio_recommendation_preparer": (
        "Portfolio Recommendation Preparer",
        "Prepares governed scenario convergence alternatives and submits them for review.",
    ),
    "portfolio_recommendation_reviewer": (
        "Portfolio Recommendation Reviewer",
        "Reviews convergence evidence and may return it to draft without recommendation authority.",
    ),
    "portfolio_recommender": (
        "Portfolio Recommender",
        "Issues a formal Portfolio recommendation without investment approval or FID authority.",
    ),
    "portfolio_convergence_viewer": (
        "Portfolio Convergence Viewer",
        "Reads scenario convergence, comparisons and recommendation readiness.",
    ),
    "portfolio_convergence_configuration_admin": (
        "Portfolio Convergence Configuration Admin",
        "Configures and publishes Gate 07I convergence and recommendation policies.",
    ),
}

PORTFOLIO_REVIEW_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "portfolio_review_viewer": frozenset(
        {
            "portfolio_review.read",
            "portfolio_project.read",
            "portfolio_evaluation.read",
            "portfolio_analysis.read",
            "portfolio_budget.read",
            "portfolio_resource.read",
            "portfolio_convergence.read",
            "investment_gate_preparation.read",
            "investment_decision.read",
            "capital_planning.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_review_preparer": frozenset(
        {
            "portfolio_review.read",
            "portfolio_review.create",
            "portfolio_review.prepare",
            "portfolio_review.freeze_snapshot",
            "portfolio_review.action.create",
            "portfolio_review.action.update",
            "portfolio_project.read",
            "portfolio_evaluation.read",
            "portfolio_analysis.read",
            "portfolio_budget.read",
            "portfolio_resource.read",
            "portfolio_convergence.read",
            "investment_gate_preparation.read",
            "investment_decision.read",
            "capital_planning.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_review_authority": frozenset(
        {
            "portfolio_review.read",
            "portfolio_review.conduct",
            "portfolio_review.complete",
            "portfolio_review.action.approve",
            "portfolio_review.action.dispatch",
            "portfolio_project.read",
            "portfolio_evaluation.read",
            "portfolio_analysis.read",
            "portfolio_budget.read",
            "portfolio_resource.read",
            "portfolio_convergence.read",
            "investment_gate_preparation.read",
            "investment_decision.read",
            "capital_planning.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_review_board_member": frozenset(
        {
            "portfolio_review.read",
            "portfolio_review.conduct",
            "portfolio_review.action.approve",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_review_action_owner": frozenset({"portfolio_review.read", "portfolio_review.action.update"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_review_action_approver": frozenset({"portfolio_review.read", "portfolio_review.action.approve"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_review_action_dispatcher": frozenset({"portfolio_review.read", "portfolio_review.action.dispatch"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "portfolio_review_configuration_admin": frozenset(
        {
            "portfolio_review.read",
            "portfolio_review.admin.configure",
            "portfolio_review.admin.publish",
        }
    ),
}

PORTFOLIO_REVIEW_ROLE_DEFINITIONS = {
    "portfolio_review_viewer": (
        "Portfolio Review Viewer",
        "Reads governed Review Sessions, snapshots, matrices, actions and history.",
    ),
    "portfolio_review_preparer": (
        "Portfolio Review Preparer",
        "Creates and prepares sessions and freezes source evidence without decision authority.",
    ),
    "portfolio_review_authority": (
        "Portfolio Review Authority",
        "Conducts and completes Portfolio Reviews independently from preparation.",
    ),
    "portfolio_review_board_member": (
        "Portfolio Review Board Member",
        "Participates in Review conduct and action approval under configured governance.",
    ),
    "portfolio_review_action_owner": (
        "Portfolio Review Action Owner",
        "Tracks accepted governance actions without source-domain mutation authority.",
    ),
    "portfolio_review_action_approver": (
        "Portfolio Review Action Approver",
        "Approves actions independently from their creator.",
    ),
    "portfolio_review_action_dispatcher": (
        "Portfolio Review Action Dispatcher",
        "Records authorized request-only dispatch toward a source authority.",
    ),
    "portfolio_review_configuration_admin": (
        "Portfolio Review Configuration Admin",
        "Configures and publishes reusable Periodic Portfolio Review policy only.",
    ),
}

INVESTMENT_GATE_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "investment_gate_preparer": frozenset(
        {
            "investment_gate_preparation.read",
            "investment_gate_preparation.create",
            "investment_gate_preparation.edit",
            "investment_gate_preparation.refresh",
            "investment_gate_preparation.clone",
            "investment_gate_preparation.void",
            "investment_gate_evidence.add",
            "portfolio_convergence.read",
            "portfolio_budget.read",
            "portfolio_resource.read",
            "portfolio_analysis.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "investment_evidence_reviewer": frozenset(
        {
            "investment_gate_preparation.read",
            "investment_gate_preparation.freeze",
            "investment_gate_evidence.validate",
            "portfolio_convergence.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "investment_gate_preparation_viewer": frozenset(
        {
            "investment_gate_preparation.read",
            "portfolio_convergence.read",
            "portfolio_project.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "investment_gate_configuration_admin": frozenset(
        {
            "investment_gate_preparation.read",
            "investment_gate_preparation.admin.configure",
            "investment_gate_preparation.admin.publish",
        }
    ),
    "investment_evidence_policy_admin": frozenset(
        {
            "investment_gate_preparation.read",
            "investment_evidence_policy.read",
            "investment_evidence_policy.configure",
            "investment_evidence_policy.publish",
            "investment_evidence_provider.read",
        }
    ),
    "investment_evidence_policy_viewer": frozenset(
        {
            "investment_gate_preparation.read",
            "investment_evidence_policy.read",
            "investment_evidence_provider.read",
        }
    ),
}

INVESTMENT_GATE_ROLE_DEFINITIONS = {
    "investment_gate_preparer": (
        "Investment Gate Preparer",
        "Prepara paquetes y evidencia para decision de inversion, sin autoridad de aprobacion o FID.",
    ),
    "investment_evidence_reviewer": (
        "Investment Evidence Reviewer",
        "Valida evidencia con segregacion de funciones y congela paquetes completos.",
    ),
    "investment_gate_preparation_viewer": (
        "Investment Gate Preparation Viewer",
        "Consulta paquetes, cobertura, condiciones, historial y handoff de Gate 07J.",
    ),
    "investment_gate_configuration_admin": (
        "Investment Gate Configuration Admin",
        "Configura y publica perfiles y politicas de Investment Gate Preparation.",
    ),
    "investment_evidence_policy_admin": (
        "Investment Evidence Policy Admin",
        "Configura y publica matrices A/B/C y sus reglas de evidencia, sin autoridad de inversion o FID.",
    ),
    "investment_evidence_policy_viewer": (
        "Investment Evidence Policy Viewer",
        "Consulta matrices efectivas, registro de proveedores y brechas de evidencia.",
    ),
}

PROJECT_DEFINITION_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "project_definition_manager": frozenset(
        {
            "project_definition.read",
            "project_definition.status.manage",
            "project_definition_assessment.create",
            "project_definition_assessment.edit",
            "project_definition_assessment.complete",
            "project_definition_assessment.reevaluate",
            "project_definition_action.manage",
            "project_definition_stage.submit",
            "project_definition.refresh",
            "investment_gate_preparation.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "definition_assessor": frozenset(
        {
            "project_definition.read",
            "project_definition_assessment.create",
            "project_definition_assessment.edit",
            "project_definition_assessment.complete",
            "project_definition_assessment.reevaluate",
            "project_definition_action.manage",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "definition_reviewer": frozenset(
        {
            "project_definition.read",
            "project_definition_stage.review",
            "investment_gate_preparation.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "project_definition_viewer": frozenset({"project_definition.read", "investment_gate_preparation.read"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "project_definition_configuration_admin": frozenset(
        {
            "project_definition.read",
            "project_definition.admin.configure",
            "project_definition.admin.publish",
        }
    ),
}

PROJECT_DEFINITION_ROLE_DEFINITIONS = {
    "project_definition_manager": (
        "Project Definition Manager",
        "Administra etapas FEL, readiness, gaps y evidencia sin autoridad de inversion o FID.",
    ),
    "definition_assessor": (
        "Definition Assessor",
        "Realiza assessments versionados de madurez y gestiona acciones de definicion.",
    ),
    "definition_reviewer": (
        "Definition Reviewer",
        "Revisa y completa etapas FEL con segregacion de funciones.",
    ),
    "project_definition_viewer": (
        "Project Definition Viewer",
        "Consulta FEL, maturity trend, readiness e historia.",
    ),
    "project_definition_configuration_admin": (
        "Project Definition Configuration Admin",
        "Configura y publica frameworks de definicion no propietarios.",
    ),
}

FUNDS_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "funding_manager": frozenset(
        {
            "funds.read",
            "funding_source.create",
            "funding_source.edit",
            "funding_source.manage_status",
            "fund.create",
            "fund.edit",
            "fund.authorize",
            "fund.manage_status",
            "funding_assignment.create",
            "funding_assignment.edit",
            "funding_assignment.reserve",
            "funding_assignment.confirm",
            "funding_assignment.release",
            "funding_assignment.cancel",
            "funding_readiness.read",
            "funding_readiness.refresh",
            "investment_gate_preparation.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "funding_planner": frozenset(
        {
            "funds.read",
            "funding_source.create",
            "funding_source.edit",
            "fund.create",
            "fund.edit",
            "funding_assignment.create",
            "funding_assignment.edit",
            "funding_assignment.reserve",
            "funding_assignment.release",
            "funding_assignment.cancel",
            "funding_readiness.read",
            "funding_readiness.refresh",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "funding_reviewer": frozenset(
        {"funds.read", "fund.authorize", "funding_assignment.confirm", "funding_readiness.read"}
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "funding_viewer": frozenset({"funds.read", "funding_readiness.read"}) | WORKSPACE_OPERATION_PERMISSIONS,
    "funding_configuration_admin": frozenset(
        {"funds.read", "funding_readiness.read", "funds.admin.configure", "funds.admin.publish"}
    ),
}

FUNDS_ROLE_DEFINITIONS = {
    "funding_manager": ("Funding Manager", "Administra Sources, Funds, Assignments y Funding Readiness sin FID."),
    "funding_planner": ("Funding Planner", "Prepara Sources, Funds y reservas estrategicas."),
    "funding_reviewer": ("Funding Reviewer", "Autoriza Funds y confirma asignaciones bajo Four-Eyes."),
    "funding_viewer": ("Funding Viewer", "Consulta cobertura, condiciones, readiness e historia."),
    "funding_configuration_admin": ("Funding Configuration Admin", "Configura y publica politicas de Funds Manager."),
}

RISK_READINESS_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "risk_manager": frozenset(
        {
            "project_risk.read",
            "project_risk.create",
            "project_risk.edit",
            "project_risk.manage_status",
            "project_risk.accept",
            "risk_readiness.read",
            "risk_readiness_assessment.create",
            "risk_readiness_assessment.edit",
            "risk_readiness_assessment.complete",
            "risk_readiness_assessment.reassess",
            "risk_readiness.refresh",
            "investment_gate_risk_evidence.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "risk_owner": frozenset(
        {
            "project_risk.read",
            "project_risk.create",
            "project_risk.edit",
            "project_risk.manage_status",
            "risk_readiness.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "risk_assessor": frozenset(
        {
            "project_risk.read",
            "project_risk.create",
            "project_risk.edit",
            "project_risk.manage_status",
            "risk_readiness.read",
            "risk_readiness_assessment.create",
            "risk_readiness_assessment.edit",
            "risk_readiness_assessment.complete",
            "risk_readiness_assessment.reassess",
            "risk_readiness.refresh",
            "investment_gate_risk_evidence.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "risk_reviewer": frozenset({"project_risk.read", "risk_readiness.read", "investment_gate_risk_evidence.read"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "risk_acceptance_authority": frozenset(
        {
            "project_risk.read",
            "project_risk.accept",
            "risk_readiness.read",
            "investment_gate_risk_evidence.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "risk_viewer": frozenset({"project_risk.read", "risk_readiness.read", "investment_gate_risk_evidence.read"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "risk_configuration_admin": frozenset(
        {
            "project_risk.read",
            "risk_readiness.read",
            "investment_gate_risk_evidence.read",
            "risk_readiness.admin.configure",
            "risk_readiness.admin.publish",
        }
    ),
}

RISK_READINESS_ROLE_DEFINITIONS = {
    "risk_manager": ("Risk Manager", "Administra Project Risk y Risk Readiness sin ERM ni QRA."),
    "risk_owner": ("Risk Owner", "Identifica y mantiene riesgos dentro de su alcance."),
    "risk_assessor": ("Risk Assessor", "Evalua y completa assessments de Risk Readiness."),
    "risk_reviewer": ("Risk Reviewer", "Consulta la evaluacion gobernada y su evidencia."),
    "risk_acceptance_authority": (
        "Risk Acceptance Authority",
        "Acepta riesgo residual conforme a autoridad y segregacion de funciones.",
    ),
    "risk_viewer": ("Risk Viewer", "Consulta registros, readiness e historia."),
    "risk_configuration_admin": (
        "Risk Configuration Admin",
        "Configura y publica politicas de Risk Readiness.",
    ),
}

PERMIT_READINESS_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "permit_manager": frozenset(
        {
            "permit.read",
            "permit.create",
            "permit.edit",
            "permit.status.manage",
            "permit.condition.manage",
            "permit_readiness.read",
            "permit_readiness.create",
            "permit_readiness.edit",
            "permit_readiness.complete",
            "permit_readiness.reassess",
            "permit_readiness.refresh",
            "investment_gate_permit_evidence.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "permit_owner": frozenset(
        {
            "permit.read",
            "permit.create",
            "permit.edit",
            "permit.status.manage",
            "permit.condition.manage",
            "permit_readiness.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "permit_assessor": frozenset(
        {
            "permit.read",
            "permit_readiness.read",
            "permit_readiness.create",
            "permit_readiness.edit",
            "permit_readiness.reassess",
            "permit_readiness.refresh",
            "investment_gate_permit_evidence.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "permit_reviewer": frozenset(
        {
            "permit.read",
            "permit_readiness.read",
            "permit_readiness.complete",
            "investment_gate_permit_evidence.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "permit_viewer": frozenset({"permit.read", "permit_readiness.read", "investment_gate_permit_evidence.read"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "permit_configuration_admin": frozenset(
        {
            "permit.read",
            "permit_readiness.read",
            "investment_gate_permit_evidence.read",
            "permit_readiness.admin.configure",
            "permit_readiness.admin.publish",
        }
    ),
}

PERMIT_READINESS_ROLE_DEFINITIONS = {
    "permit_manager": (
        "Permit Manager",
        "Administra permisos, condiciones y Permit Readiness sin actuar como regulador.",
    ),
    "permit_owner": ("Permit Owner", "Mantiene permisos y condiciones dentro de su alcance."),
    "permit_assessor": ("Permit Assessor", "Evalua y refresca Permit Readiness."),
    "permit_reviewer": ("Permit Reviewer", "Completa assessments bajo segregacion de funciones."),
    "permit_viewer": ("Permit Viewer", "Consulta requisitos, registros, readiness e historia."),
    "permit_configuration_admin": (
        "Permit Configuration Admin",
        "Configura y publica politicas de Permit Readiness.",
    ),
}

INVESTMENT_DECISION_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "investment_decision_preparer": frozenset(
        {
            "investment_decision.read",
            "investment_decision.create",
            "investment_decision.edit",
            "investment_decision.submit",
            "investment_decision.void",
            "investment_gate_preparation.read",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "investment_decision_reviewer": frozenset(
        {"investment_decision.read", "investment_decision.review", "investment_decision.void"}
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "investment_decision_maker": frozenset({"investment_decision.read", "investment_decision.decide"})
    | WORKSPACE_OPERATION_PERMISSIONS,
    "investment_decision_committee_member": frozenset(
        {"investment_decision.read", "investment_decision.vote", "investment_decision.decide"}
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "investment_decision_committee_chair": frozenset(
        {"investment_decision.read", "investment_decision.vote", "investment_decision.decide"}
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "investment_decision_viewer": frozenset({"investment_decision.read"}) | WORKSPACE_OPERATION_PERMISSIONS,
    "investment_decision_configuration_admin": frozenset(
        {
            "investment_decision.read",
            "investment_decision.admin.configure",
            "investment_decision.admin.publish",
        }
    ),
}

INVESTMENT_DECISION_ROLE_DEFINITIONS = {
    "investment_decision_preparer": ("Investment Decision Preparer", "Prepara y somete decisiones Gate 07K."),
    "investment_decision_reviewer": ("Investment Decision Reviewer", "Revisa paquetes y checklist de Decision."),
    "investment_decision_maker": ("Investment Decision Maker", "Registra decisiones formales dentro de su autoridad."),
    "investment_decision_committee_member": ("Investment Decision Committee Member", "Emite votos formales de comite."),
    "investment_decision_committee_chair": (
        "Investment Decision Committee Chair",
        "Preside el comite y sus reglas de voto.",
    ),
    "investment_decision_viewer": ("Investment Decision Viewer", "Consulta Decision, paquete, historia y output."),
    "investment_decision_configuration_admin": (
        "Investment Decision Configuration Admin",
        "Configura y publica la gobernanza de Investment Decision y FID.",
    ),
}

POST_FID_GOVERNANCE_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "post_fid_governance_manager": frozenset(
        {
            "post_fid_governance.read",
            "post_fid_governance.evaluate",
            "post_fid_governance.refresh",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "post_fid_governance_viewer": frozenset({"post_fid_governance.read"}) | WORKSPACE_OPERATION_PERMISSIONS,
    "post_fid_governance_configuration_admin": frozenset(
        {
            "post_fid_governance.read",
            "post_fid_governance.admin.configure",
            "post_fid_governance.admin.publish",
        }
    ),
}

POST_FID_GOVERNANCE_ROLE_DEFINITIONS = {
    "post_fid_governance_manager": (
        "Post-FID Governance Manager",
        "Evalua y refresca elegibilidad post-FID sin inicializar ni activar Projects.",
    ),
    "post_fid_governance_viewer": (
        "Post-FID Governance Viewer",
        "Consulta FID handoff, elegibilidad, condiciones e historia.",
    ),
    "post_fid_governance_configuration_admin": (
        "Post-FID Governance Configuration Admin",
        "Configura y publica la politica Gate 07L.",
    ),
}

BUSINESS_CASE_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "business_case_preparer": frozenset(
        {
            "business_case.read",
            "business_case.create",
            "business_case.edit",
            "business_case.submit_review",
            "business_case.create_revision",
            "business_case.refresh",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "business_case_reviewer": frozenset(
        {
            "business_case.read",
            "business_case.review",
            "business_case.complete",
            "business_case.snapshot",
            "business_case.material_change.review",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "business_case_viewer": frozenset({"business_case.read"}) | WORKSPACE_OPERATION_PERMISSIONS,
    "business_case_configuration_admin": frozenset(
        {"business_case.read", "business_case.admin.configure", "business_case.admin.publish"}
    ),
}

BUSINESS_CASE_ROLE_DEFINITIONS = {
    "business_case_preparer": ("Business Case Preparer", "Prepara y mantiene revisiones longitudinales Gate 07M-BC."),
    "business_case_reviewer": ("Business Case Reviewer", "Revisa, completa y congela evidencia de Business Case."),
    "business_case_viewer": ("Business Case Viewer", "Consulta Business Cases, readiness e historia."),
    "business_case_configuration_admin": (
        "Business Case Configuration Admin",
        "Configura y publica mapping, readiness, SoD, freshness e inheritance Gate 07M-BC.",
    ),
}

ECONOMIC_FINANCIAL_MODEL_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "financial_model_owner": frozenset(
        {
            "economic_financial_model.read",
            "economic_financial_model.create",
            "economic_financial_model.create_version",
            "economic_financial_model.refresh",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "financial_model_preparer": frozenset(
        {
            "economic_financial_model.read",
            "economic_financial_model.create",
            "economic_financial_model.edit",
            "economic_financial_model.calculate",
            "economic_financial_model.submit_review",
            "economic_financial_model.create_version",
            "economic_financial_model.refresh",
            "economic_financial_model.scenario.manage",
            "economic_financial_model.sensitivity.run",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "financial_model_reviewer": frozenset(
        {"economic_financial_model.read", "economic_financial_model.review", "economic_financial_model.complete"}
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "financial_model_finance_reviewer": frozenset(
        {"economic_financial_model.read", "economic_financial_model.review", "economic_financial_model.complete"}
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "financial_model_viewer": frozenset({"economic_financial_model.read"}) | WORKSPACE_OPERATION_PERMISSIONS,
    "financial_model_configuration_admin": frozenset(
        {
            "economic_financial_model.read",
            "economic_financial_model.admin.configure",
            "economic_financial_model.admin.publish",
        }
    ),
}

ECONOMIC_FINANCIAL_MODEL_ROLE_DEFINITIONS = {
    "financial_model_owner": ("Financial Model Owner", "Responsable del modelo economico-financiero del Project."),
    "financial_model_preparer": ("Financial Model Preparer", "Prepara, calcula y somete versiones Gate 07M-FIN."),
    "financial_model_reviewer": ("Financial Model Reviewer", "Revisa y completa modelos con Four-Eyes."),
    "financial_model_finance_reviewer": (
        "Financial Model Finance Reviewer",
        "Ejecuta la revision financiera final aplicable a PYP-FFA.",
    ),
    "financial_model_viewer": ("Financial Model Viewer", "Consulta modelos, readiness, escenarios e historia."),
    "financial_model_configuration_admin": (
        "Financial Model Configuration Admin",
        "Configura y publica la politica Gate 07M-FIN.",
    ),
}

STRATEGIC_BENEFITS_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "benefits_plan_author": frozenset(
        {
            "benefits_plan.read",
            "benefits_plan.create",
            "benefits_plan.edit",
            "benefits_plan.submit",
            "benefits_plan.create_revision",
            "benefits_plan.refresh",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "benefits_plan_reviewer": frozenset(
        {
            "benefits_plan.read",
            "benefits_plan.review",
            "benefits_plan.complete",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "benefits_plan_viewer": frozenset({"benefits_plan.read"}) | WORKSPACE_OPERATION_PERMISSIONS,
    # ADMIN configuration authority is deliberately separate from live Project
    # plan access; organization_admin remains the explicit break-glass role.
    "benefits_plan_config_admin": frozenset(
        {
            "benefits_plan.admin.configure",
            "benefits_plan.admin.publish",
        }
    ),
}

STRATEGIC_BENEFITS_ROLE_DEFINITIONS = {
    "benefits_plan_author": (
        "Strategic Benefits Plan Author",
        "Creates, edits and submits governed Project Strategic Benefits Plan versions.",
    ),
    "benefits_plan_reviewer": (
        "Strategic Benefits Plan Reviewer",
        "Reviews, returns and completes Benefits Plans under separation of duties.",
    ),
    "benefits_plan_viewer": (
        "Strategic Benefits Plan Viewer",
        "Reads authorized Benefits Plans, stable Benefit identities, measures and history.",
    ),
    "benefits_plan_config_admin": (
        "Strategic Benefits Configuration Admin",
        "Configures and publishes reusable Benefits Plan policy without live-record authority.",
    ),
}

COMMERCIAL_STRATEGY_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "commercial_strategy_author": frozenset(
        {
            "commercial_strategy.read",
            "commercial_strategy.create",
            "commercial_strategy.edit",
            "commercial_strategy.submit",
            "commercial_strategy.create_revision",
            "commercial_strategy.refresh",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "commercial_strategy_reviewer": frozenset(
        {
            "commercial_strategy.read",
            "commercial_strategy.review",
            "commercial_strategy.complete",
        }
    )
    | WORKSPACE_OPERATION_PERMISSIONS,
    "commercial_strategy_viewer": frozenset({"commercial_strategy.read"}) | WORKSPACE_OPERATION_PERMISSIONS,
    # Deliberately no transaction read/create/edit rights: ADMIN configuration
    # authority does not grant access to live Project commercial records.
    "commercial_strategy_config_admin": frozenset(
        {
            "commercial_strategy.admin.configure",
            "commercial_strategy.admin.publish",
        }
    ),
}

COMMERCIAL_STRATEGY_ROLE_DEFINITIONS = {
    "commercial_strategy_author": (
        "Commercial Strategy Author",
        "Creates, edits and submits Project commercial strategy versions.",
    ),
    "commercial_strategy_reviewer": (
        "Commercial Strategy Reviewer",
        "Reviews, returns and completes commercial strategy under separation of duties.",
    ),
    "commercial_strategy_viewer": (
        "Commercial Strategy Viewer",
        "Reads authorized Project commercial strategy records and history.",
    ),
    "commercial_strategy_config_admin": (
        "Commercial Strategy Configuration Admin",
        "Configures and publishes reusable commercial strategy policy without live-record authority.",
    ),
}

REVISION_DUTY_ROLES: dict[str, frozenset[str]] = {
    "admin.enterprise_structure.revision.create": frozenset({"structure_editor"}),
    "admin.enterprise_structure.revision.edit": frozenset({"structure_editor"}),
    "admin.enterprise_structure.revision.validate": frozenset({"structure_editor"}),
    "admin.enterprise_structure.revision.compare": frozenset(STRUCTURE_ROLE_PERMISSIONS),
    "admin.enterprise_structure.revision.approve": frozenset({"structure_approver"}),
    "admin.enterprise_structure.publish": frozenset({"structure_publisher"}),
    "admin.enterprise_structure.rollback": frozenset({"structure_publisher"}),
}

# SQLite ignores SELECT ... FOR UPDATE.  The local/test runtime can issue its
# first permission-protected requests concurrently, so serialize only the
# idempotent bootstrap inside this process. PostgreSQL still has the tenant-row
# lock below for cross-process safety.
# Wave 2B reuses existing duties. Preparing or validating Basic Data does not
# confer final-review authority, and configuration-only roles get no live duty.
_BASIC_DATA_PREPARATION = frozenset(
    {
        "basic_data.read",
        "basic_data.item.create",
        "basic_data.item.edit",
        "basic_data.item.validate",
        "basic_data.assessment.create",
        "basic_data.assessment.submit",
    }
)
_BASIC_DATA_REVIEW = frozenset(
    {
        "basic_data.read",
        "basic_data.assessment.review",
        "basic_data.assessment.complete",
    }
)
PROJECT_DEFINITION_ROLE_PERMISSIONS["project_definition_manager"] |= (
    _BASIC_DATA_PREPARATION | _BASIC_DATA_REVIEW | {"risk_governance.read"}
)
PROJECT_DEFINITION_ROLE_PERMISSIONS["definition_assessor"] |= _BASIC_DATA_PREPARATION | {"risk_governance.read"}
PROJECT_DEFINITION_ROLE_PERMISSIONS["definition_reviewer"] |= _BASIC_DATA_REVIEW | {"risk_governance.read"}
PROJECT_DEFINITION_ROLE_PERMISSIONS["project_definition_viewer"] |= {"basic_data.read", "risk_governance.read"}
PROJECT_DEFINITION_ROLE_PERMISSIONS["project_definition_configuration_admin"] |= {
    "basic_data.read",
    "basic_data.admin.configure",
    "basic_data.admin.publish",
    "risk_governance.read",
}
for _wave2b_risk_role in RISK_READINESS_ROLE_PERMISSIONS:
    RISK_READINESS_ROLE_PERMISSIONS[_wave2b_risk_role] |= {"risk_governance.read"}
RISK_READINESS_ROLE_PERMISSIONS["risk_configuration_admin"] |= {
    "risk_governance.admin.configure",
    "risk_governance.admin.publish",
}

# Wave 3B reuses definition duties; ADMIN-only configuration is not preparation.
_OWNER_CAPABILITY_PREPARATION = frozenset(
    {
        "owner_capability.read",
        "owner_capability.assessment.create",
        "owner_capability.assessment.edit",
        "owner_capability.assessment.submit",
        "owner_capability.mitigation.edit",
    }
)
_OWNER_CAPABILITY_REVIEW = frozenset(
    {
        "owner_capability.read",
        "owner_capability.assessment.review",
        "owner_capability.assessment.complete",
    }
)
PROJECT_DEFINITION_ROLE_PERMISSIONS["project_definition_manager"] |= (
    _OWNER_CAPABILITY_PREPARATION | _OWNER_CAPABILITY_REVIEW
)
PROJECT_DEFINITION_ROLE_PERMISSIONS["definition_assessor"] |= _OWNER_CAPABILITY_PREPARATION
PROJECT_DEFINITION_ROLE_PERMISSIONS["definition_reviewer"] |= _OWNER_CAPABILITY_REVIEW
PROJECT_DEFINITION_ROLE_PERMISSIONS["project_definition_viewer"] |= {"owner_capability.read"}
PROJECT_DEFINITION_ROLE_PERMISSIONS["project_definition_configuration_admin"] |= {
    "owner_capability.read",
    "owner_capability.admin.configure",
    "owner_capability.admin.publish",
}

# Existing definition duties prepare/review QRA inputs, not investment decisions.
_QRA_PREPARATION = frozenset({"qra_foundation.read"}) | frozenset(
    f"{resource}.{action}"
    for resource in ("qra_cost_source", "qra_schedule_source", "qra_model")
    for action in ("create", "edit", "submit")
)
_QRA_REVIEW = frozenset({
    "qra_foundation.read", "qra_cost_source.review", "qra_schedule_source.review",
    "qra_model.review", "qra_model.approve",
})
PROJECT_DEFINITION_ROLE_PERMISSIONS["project_definition_manager"] |= _QRA_PREPARATION | _QRA_REVIEW
PROJECT_DEFINITION_ROLE_PERMISSIONS["definition_assessor"] |= _QRA_PREPARATION
PROJECT_DEFINITION_ROLE_PERMISSIONS["definition_reviewer"] |= _QRA_REVIEW
PROJECT_DEFINITION_ROLE_PERMISSIONS["project_definition_viewer"] |= {"qra_foundation.read"}
PROJECT_DEFINITION_ROLE_PERMISSIONS["project_definition_configuration_admin"] |= {
    "qra_foundation.read", "qra_methodology.admin.configure", "qra_methodology.admin.publish",
}

_PERMISSION_SEED_LOCK = RLock()


@dataclass(frozen=True)
class EnterprisePermissionContext:
    user: UserAccount
    organization_wide: bool
    scope_unit_ids: frozenset[int]
    workspace_ids: frozenset[int]
    role_codes: frozenset[str]


def require_enterprise_permission(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission_key: str,
    *,
    allowed_role_codes: frozenset[str] | None = None,
    bootstrap: bool = True,
) -> EnterprisePermissionContext:
    # Existing callers retain their bootstrap behavior. New governed read
    # surfaces can opt out after explicit provisioning and remain read-only.
    if bootstrap:
        ensure_enterprise_permissions(db, tenant_id, user_id)
        db.commit()
    user = db.scalar(
        select(UserAccount).where(
            UserAccount.id == user_id,
            UserAccount.tenant_id == tenant_id,
            UserAccount.status == "active",
        )
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    group_ids = list(
        db.scalars(
            select(SecurityGroupMember.group_id).where(
                SecurityGroupMember.tenant_id == tenant_id,
                SecurityGroupMember.user_id == user_id,
            )
        ).all()
    )
    now = utc_now()
    assignments = list(
        db.scalars(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == tenant_id,
                SecurityAccessAssignment.status == "active",
            )
        ).all()
    )
    assignments = [
        item
        for item in assignments
        if (item.user_id == user_id or (item.group_id is not None and item.group_id in group_ids))
        and (item.starts_at is None or item.starts_at <= now)
        and (item.ends_at is None or item.ends_at > now)
    ]
    role_ids = {item.role_id for item in assignments}
    permitted_role_ids: set[int] = set()
    if role_ids:
        permitted_role_ids = set(
            db.scalars(
                select(SecurityRolePermission.role_id)
                .join(PermissionCatalog, PermissionCatalog.id == SecurityRolePermission.permission_id)
                .join(SecurityRole, SecurityRole.id == SecurityRolePermission.role_id)
                .where(
                    SecurityRolePermission.tenant_id == tenant_id,
                    SecurityRole.tenant_id == tenant_id,
                    SecurityRole.status == "active",
                    SecurityRolePermission.role_id.in_(role_ids),
                    PermissionCatalog.key == permission_key,
                    PermissionCatalog.status == "active",
                )
            ).all()
        )
    effective = [item for item in assignments if item.role_id in permitted_role_ids]
    if allowed_role_codes is not None:
        duty_role_ids = set(
            db.scalars(
                select(SecurityRole.id).where(
                    SecurityRole.tenant_id == tenant_id,
                    SecurityRole.code.in_(allowed_role_codes),
                    SecurityRole.status == "active",
                )
            ).all()
        )
        effective = [item for item in effective if item.role_id in duty_role_ids]
    if not effective:
        raise HTTPException(status_code=403, detail=f"Missing required permission: {permission_key}")
    organization_wide = any(item.scope_type == "organization" for item in effective)
    scope_unit_ids = frozenset(item.scope_unit_id for item in effective if item.scope_unit_id is not None)
    workspace_ids = frozenset(item.workspace_id for item in effective if item.workspace_id is not None)
    effective_role_ids = {item.role_id for item in effective}
    role_codes = frozenset(
        db.scalars(
            select(SecurityRole.code).where(
                SecurityRole.tenant_id == tenant_id,
                SecurityRole.id.in_(effective_role_ids),
            )
        ).all()
        if effective_role_ids
        else []
    )
    return EnterprisePermissionContext(
        user=user,
        organization_wide=organization_wide,
        scope_unit_ids=scope_unit_ids,
        workspace_ids=workspace_ids,
        role_codes=role_codes,
    )


def require_organization_scope(context: EnterprisePermissionContext) -> None:
    if not context.organization_wide:
        raise HTTPException(status_code=403, detail="Organization-wide scope is required for this operation")


def ensure_enterprise_permissions(db: Session, tenant_id: int, user_id: int) -> None:
    with _PERMISSION_SEED_LOCK:
        _ensure_enterprise_permissions_unlocked(db, tenant_id, user_id)


def _ensure_enterprise_permissions_unlocked(db: Session, tenant_id: int, user_id: int) -> None:
    db.execute(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()).scalar_one()
    permissions = {item.key: item for item in db.scalars(select(PermissionCatalog)).all()}
    for key, resource, action, description, risk_level in PERMISSION_SEED:
        if key in permissions:
            continue
        record = PermissionCatalog(
            key=key,
            resource=resource,
            action=action,
            description=description,
            risk_level=risk_level,
            status="active",
        )
        db.add(record)
        db.flush()
        permissions[key] = record

    roles = {
        item.code: item for item in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id)).all()
    }
    if "organization_admin" not in roles:
        require_tenant_configurator(db, tenant_id, user_id)
        role = SecurityRole(
            tenant_id=tenant_id,
            code="organization_admin",
            name="Organization Administrator",
            description="Administración integral de la empresa.",
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    if "configuration_admin" not in roles:
        role = SecurityRole(
            tenant_id=tenant_id,
            code="configuration_admin",
            name="Configuration Administrator",
            description="Gobierno de estructuras, catálogos, reglas y procesos reutilizables.",
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in STRUCTURE_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PROJECT_CREATION_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PROJECT_WORKSPACE_LIFECYCLE_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PHYSICAL_WORKSPACE_CREATION_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PHYSICAL_WORKSPACE_LIFECYCLE_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in BUSINESS_ANALYSIS_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in IDEA_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in CAPITAL_PLANNING_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PROJECT_PROPOSAL_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in STRATEGIC_GATE_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PORTFOLIO_PLANNING_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PORTFOLIO_EVALUATION_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PORTFOLIO_ANALYSIS_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PORTFOLIO_BUDGET_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PORTFOLIO_RESOURCE_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PORTFOLIO_CONVERGENCE_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PORTFOLIO_REVIEW_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in INVESTMENT_GATE_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PROJECT_DEFINITION_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in FUNDS_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in RISK_READINESS_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PERMIT_READINESS_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in INVESTMENT_DECISION_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in POST_FID_GOVERNANCE_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in BUSINESS_CASE_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in ECONOMIC_FINANCIAL_MODEL_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in STRATEGIC_BENEFITS_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in COMMERCIAL_STRATEGY_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    grants_by_role = {
        "organization_admin": {item[0] for item in PERMISSION_SEED},
        "configuration_admin": {item[0] for item in PERMISSION_SEED if item[0].startswith("admin.")}
        | {
            "risk_governance.read",
            "risk_governance.admin.configure",
            "risk_governance.admin.publish",
            "basic_data.read",
            "basic_data.admin.configure",
            "basic_data.admin.publish",
            "owner_capability.read",
            "owner_capability.admin.configure",
            "owner_capability.admin.publish",
            "qra_foundation.read",
            "qra_methodology.admin.configure",
            "qra_methodology.admin.publish",
            "enterprise_structure.read",
            "enterprise_structure.read_history",
            "enterprise_structure.export",
            "idea.read",
            "idea.admin.configure",
            "idea.admin.publish",
            "capital_planning.read",
            "capital_planning.admin.configure",
            "capital_planning.admin.publish",
            "capital_planning.admin.bucket.configure",
            "capital_planning.admin.bucket.publish",
            "business_analysis.read",
            "business_analysis.admin.configure",
            "business_analysis.admin.publish",
            "project_proposal.read",
            "project_proposal.admin.configure",
            "project_proposal.admin.publish",
            "strategic_gate.read",
            "strategic_gate.admin.configure",
            "strategic_gate.admin.publish",
            "portfolio_project.read",
            "portfolio_project.admin.configure",
            "portfolio_project.admin.publish",
            "portfolio_evaluation.read",
            "portfolio_evaluation.admin.configure",
            "portfolio_evaluation.admin.publish",
            "portfolio_prioritization.read",
            "portfolio_analysis.read",
            "portfolio_analysis.admin.configure",
            "portfolio_analysis.admin.publish",
            "portfolio_budget.read",
            "portfolio_budget.admin.configure",
            "portfolio_budget.admin.publish",
            "portfolio_resource.read",
            "portfolio_resource.admin.configure",
            "portfolio_resource.admin.publish",
            "portfolio_convergence.read",
            "portfolio_convergence.admin.configure",
            "portfolio_convergence.admin.publish",
            "portfolio_review.read",
            "portfolio_review.admin.configure",
            "portfolio_review.admin.publish",
            "investment_gate_preparation.read",
            "investment_gate_preparation.admin.configure",
            "investment_gate_preparation.admin.publish",
            "investment_evidence_policy.read",
            "investment_evidence_policy.configure",
            "investment_evidence_policy.publish",
            "investment_evidence_provider.read",
            "project_definition.read",
            "project_definition.admin.configure",
            "project_definition.admin.publish",
            "funds.read",
            "funding_readiness.read",
            "funds.admin.configure",
            "funds.admin.publish",
            "project_risk.read",
            "risk_readiness.read",
            "investment_gate_risk_evidence.read",
            "risk_readiness.admin.configure",
            "risk_readiness.admin.publish",
            "permit.read",
            "permit_readiness.read",
            "investment_gate_permit_evidence.read",
            "permit_readiness.admin.configure",
            "permit_readiness.admin.publish",
            "investment_decision.read",
            "investment_decision.admin.configure",
            "investment_decision.admin.publish",
            "post_fid_governance.read",
            "post_fid_governance.admin.configure",
            "post_fid_governance.admin.publish",
            "business_case.read",
            "business_case.admin.configure",
            "business_case.admin.publish",
            "economic_financial_model.read",
            "economic_financial_model.admin.configure",
            "economic_financial_model.admin.publish",
            "benefits_plan.admin.configure",
            "benefits_plan.admin.publish",
            "commercial_strategy.admin.configure",
            "commercial_strategy.admin.publish",
        },
        "auditor": {"enterprise_structure.read", "enterprise_structure.read_history", "enterprise_structure.export"},
        "viewer": {"enterprise_structure.read"} | WORKSPACE_OPERATION_PERMISSIONS,
        **STRUCTURE_ROLE_PERMISSIONS,
        **PROJECT_CREATION_ROLE_PERMISSIONS,
        **PROJECT_WORKSPACE_LIFECYCLE_ROLE_PERMISSIONS,
        **PHYSICAL_WORKSPACE_CREATION_ROLE_PERMISSIONS,
        **PHYSICAL_WORKSPACE_LIFECYCLE_ROLE_PERMISSIONS,
        **IDEA_ROLE_PERMISSIONS,
        **CAPITAL_PLANNING_ROLE_PERMISSIONS,
        **BUSINESS_ANALYSIS_ROLE_PERMISSIONS,
        **PROJECT_PROPOSAL_ROLE_PERMISSIONS,
        **STRATEGIC_GATE_ROLE_PERMISSIONS,
        **PORTFOLIO_PLANNING_ROLE_PERMISSIONS,
        **PORTFOLIO_EVALUATION_ROLE_PERMISSIONS,
        **PORTFOLIO_ANALYSIS_ROLE_PERMISSIONS,
        **PORTFOLIO_BUDGET_ROLE_PERMISSIONS,
        **PORTFOLIO_RESOURCE_ROLE_PERMISSIONS,
        **PORTFOLIO_CONVERGENCE_ROLE_PERMISSIONS,
        **PORTFOLIO_REVIEW_ROLE_PERMISSIONS,
        **INVESTMENT_GATE_ROLE_PERMISSIONS,
        **PROJECT_DEFINITION_ROLE_PERMISSIONS,
        **FUNDS_ROLE_PERMISSIONS,
        **RISK_READINESS_ROLE_PERMISSIONS,
        **PERMIT_READINESS_ROLE_PERMISSIONS,
        **INVESTMENT_DECISION_ROLE_PERMISSIONS,
        **POST_FID_GOVERNANCE_ROLE_PERMISSIONS,
        **BUSINESS_CASE_ROLE_PERMISSIONS,
        **ECONOMIC_FINANCIAL_MODEL_ROLE_PERMISSIONS,
        **STRATEGIC_BENEFITS_ROLE_PERMISSIONS,
        **COMMERCIAL_STRATEGY_ROLE_PERMISSIONS,
    }
    for role_code, permission_keys in grants_by_role.items():
        role = roles.get(role_code)
        if role is None:
            continue
        existing = set(
            db.scalars(
                select(SecurityRolePermission.permission_id).where(
                    SecurityRolePermission.tenant_id == tenant_id,
                    SecurityRolePermission.role_id == role.id,
                )
            ).all()
        )
        for permission_key in permission_keys:
            permission = permissions[permission_key]
            if permission.id in existing:
                continue
            db.add(
                SecurityRolePermission(
                    tenant_id=tenant_id,
                    role_id=role.id,
                    permission_id=permission.id,
                    granted_by_user_id=user_id,
                )
            )
    organization_admin = roles["organization_admin"]
    active_admin = db.scalar(
        select(SecurityAccessAssignment.id).where(
            SecurityAccessAssignment.tenant_id == tenant_id,
            SecurityAccessAssignment.role_id == organization_admin.id,
            SecurityAccessAssignment.status == "active",
        )
    )
    if active_admin is None:
        require_tenant_configurator(db, tenant_id, user_id)
        db.add(
            SecurityAccessAssignment(
                tenant_id=tenant_id,
                subject_type="user",
                user_id=user_id,
                role_id=organization_admin.id,
                scope_type="organization",
                status="active",
                granted_by_user_id=user_id,
            )
        )
    structure_editor = roles["structure_editor"]
    active_editor = db.scalar(
        select(SecurityAccessAssignment.id).where(
            SecurityAccessAssignment.tenant_id == tenant_id,
            SecurityAccessAssignment.role_id == structure_editor.id,
            SecurityAccessAssignment.status == "active",
        )
    )
    if active_editor is None:
        bootstrap = db.scalar(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == tenant_id,
                SecurityAccessAssignment.role_id == organization_admin.id,
                SecurityAccessAssignment.status == "active",
            )
        )
        db.add(
            SecurityAccessAssignment(
                tenant_id=tenant_id,
                subject_type=bootstrap.subject_type if bootstrap is not None else "user",
                user_id=bootstrap.user_id if bootstrap is not None else user_id,
                group_id=bootstrap.group_id if bootstrap is not None else None,
                role_id=structure_editor.id,
                scope_type=bootstrap.scope_type if bootstrap is not None else "organization",
                scope_unit_id=bootstrap.scope_unit_id if bootstrap is not None else None,
                starts_at=bootstrap.starts_at if bootstrap is not None else None,
                ends_at=bootstrap.ends_at if bootstrap is not None else None,
                status="active",
                granted_by_user_id=user_id,
            )
        )
