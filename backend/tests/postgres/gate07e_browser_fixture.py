"""Disposable Gate 07E-H browser fixture and persistent-baseline guard.

The fixture is intentionally created outside product APIs so the browser test can
exercise the real USER/ADMIN APIs from a known precondition.  Teardown uses exact
run-scoped workspace/configuration codes and removes all resulting audit rows.
"""

from __future__ import annotations

import argparse
import json
import re
from copy import deepcopy

from sqlalchemy import Text, cast, delete, func, or_, select, text

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent, UserAccount
from app.main import app as _app  # noqa: F401 - imports every routed model into SQLAlchemy metadata
from app.modules.portfolio_evaluation.models import PortfolioProjectEvaluation
from app.modules.portfolio_evaluation.service import CONFIGURATION_KIND, DEFAULT_CODE, DEFAULT_CONFIGURATION, _hash
from app.modules.portfolio_planning.models import PortfolioProjectMembership
from app.modules.project_creation.models import ProjectCreationRequest


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
    content = deepcopy(DEFAULT_CONFIGURATION)
    content["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    labels = {
        "economic": "Economic Value",
        "capacity": "Organizational Capacity",
    }
    for criterion in content["criteria"]:
        criterion["label"] = labels.get(criterion["code"], criterion["label"])
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=CONFIGURATION_KIND,
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


def _summary(record: EnterpriseWorkspace) -> dict:
    return {"id": record.id, "name": record.name, "code": record.code}


def seed(run_id: str, copies: int) -> dict:
    safe = _safe_run_id(run_id)
    teardown(safe, emit=False)
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        if admin is None:
            raise RuntimeError("The demo admin user is required for the disposable browser fixture")
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
        fixtures: list[dict] = []
        for index in range(1, copies + 1):
            label = f"Gate07E-H {safe} R{index}"
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
                }
            )
        db.commit()
        return {"run_id": safe, "copies": fixtures}


def teardown(run_id: str, *, emit: bool = True) -> dict:
    safe = _safe_run_id(run_id)
    workspace_prefix = f"{_prefix(safe)}%"
    configuration_prefix = f"g07eh-{safe}%"
    with SessionLocal() as db:
        workspaces = list(
            db.scalars(select(EnterpriseWorkspace).where(EnterpriseWorkspace.code.like(workspace_prefix)))
        )
        workspace_ids = [item.id for item in workspaces]
        project_ids = [item.id for item in workspaces if item.workspace_type_code == "project"]
        portfolio_ids = [item.id for item in workspaces if item.workspace_type_code == "portfolio"]
        configurations = list(
            db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.code.like(configuration_prefix),
                )
            )
        )
        configuration_ids = [item.id for item in configurations]
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
        event_targets = [*workspace_ids, *configuration_ids, *evaluation_ids]
        if event_targets:
            db.execute(delete(SecurityEvent).where(SecurityEvent.target_id.in_(event_targets)))
        if evaluation_ids:
            db.execute(delete(PortfolioProjectEvaluation).where(PortfolioProjectEvaluation.id.in_(evaluation_ids)))
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
        db.commit()
        result = {
            "run_id": safe,
            "deleted": {
                "workspaces": len(workspace_ids),
                "memberships": len(project_ids),
                "evaluations": len(evaluation_ids),
                "configurations": len(configuration_ids),
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
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.code == DEFAULT_CODE,
                )
            )
        )
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
            "admin_configurations": db.scalar(
                select(func.count(AdminConfiguration.id)).where(AdminConfiguration.tenant_id == admin.tenant_id)
            ),
            "gate07e_starter_draft": sum(item.status == "draft" for item in starter),
            "gate07e_starter_published": sum(item.status == "published" for item in starter),
            "project_14_defaults_md5": defaults_md5,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    seed_parser = subparsers.add_parser("seed")
    seed_parser.add_argument("--run-id", required=True)
    seed_parser.add_argument("--copies", type=int, default=3, choices=range(1, 6))
    teardown_parser = subparsers.add_parser("teardown")
    teardown_parser.add_argument("--run-id", required=True)
    subparsers.add_parser("baseline")
    args = parser.parse_args()
    if args.command == "seed":
        print(json.dumps(seed(args.run_id, args.copies), sort_keys=True))
    elif args.command == "teardown":
        teardown(args.run_id)
    else:
        print(json.dumps(baseline(), sort_keys=True))


if __name__ == "__main__":
    main()
