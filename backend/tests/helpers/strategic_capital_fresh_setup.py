"""Fresh isolated Capital Owner foundation and real A2-A7 command journey.

Only tenant/user credentials, RBAC assignments and one explicitly declared
administrative objective reference are bootstrap data. No Idea, BA, Proposal,
Gate decision, request, Project or membership is inserted as a final fixture.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.test_business_analysis_gate07a_ba import _complete_payload as ba_payload
from tests.test_project_proposal_gate07b import _complete_payload as proposal_payload

from app.api.v1.routers.admin_configuration import _ensure_seed as seed_admin_metadata
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.domain.models import (
    AdminConfiguration,
    AuthCredential,
    EnterpriseWorkspace,
    SecurityAccessAssignment,
    SecurityRole,
    Tenant,
    UserAccount,
)
from app.main import app
from app.modules.capital_planning.schemas import (
    AllocationLineIn,
    AllocationLinesReplaceIn,
    AllocationPlanCreate,
    BucketClassificationIn,
    BucketClassificationsReplaceIn,
    CycleCreate,
    DemandCreate,
    OriginateIdeaIn,
)
from app.modules.capital_planning.service import CapitalPlanningService
from app.modules.enterprise_structure.models import EnterpriseStrategicObjective
from app.modules.enterprise_structure.permissions import ensure_enterprise_permissions, require_enterprise_permission
from app.modules.enterprise_structure.project_configuration import ProjectWorkspaceConfigurationService
from app.modules.enterprise_structure.project_schemas import ProjectTemplatePayload
from app.modules.enterprise_structure.schemas import EnterpriseNodeCreate
from app.modules.enterprise_structure.service import EnterpriseStructureService

AUTHOR_ROLES = (
    "idea_requestor",
    "idea_owner",
    "business_analysis_author",
    "proposal_requestor",
    "proposal_owner",
    "proposal_evaluator",
    "gate_preparer",
    "project_requestor",
    "project_manager",
    "portfolio_intake_planner",
    "portfolio_membership_manager",
    "portfolio_evaluator",
    "portfolio_analyst",
    "portfolio_budget_planner",
    "portfolio_resource_planner",
    "portfolio_recommendation_preparer",
    "portfolio_review_preparer",
    "business_case_preparer",
    "benefits_plan_author",
    "commercial_strategy_author",
    "project_definition_manager",
    "definition_assessor",
    "risk_manager",
    "permit_manager",
    "funding_manager",
    "financial_model_preparer",
    "investment_gate_preparer",
    "investment_decision_preparer",
    "post_fid_governance_manager",
    "capital_planning_cycle_manager",
    "capital_planning_author",
    "capital_planning_originator",
    "capital_planning_allocation_author",
    "capital_planning_bucket_classifier",
)
REVIEWER_ROLES = (
    "business_analysis_reviewer",
    "proposal_reviewer",
    "gate_reviewer",
    "project_reviewer",
    "portfolio_evaluator",
    "portfolio_budget_planner",
    "portfolio_resource_planner",
    "portfolio_recommendation_reviewer",
    "portfolio_recommender",
    "portfolio_review_authority",
    "business_case_reviewer",
    "benefits_plan_reviewer",
    "commercial_strategy_reviewer",
    # Basic Data item validation is an assessor duty in the current RBAC model.
    # This actor never authors the fresh study records it independently validates.
    "definition_assessor",
    "definition_reviewer",
    "risk_assessor",
    "risk_acceptance_authority",
    "permit_reviewer",
    "permit_manager",
    "funding_reviewer",
    "financial_model_finance_reviewer",
    "financial_model_reviewer",
    "investment_evidence_reviewer",
    "investment_decision_reviewer",
    "capital_planning_reviewer",
    "capital_planning_allocation_reviewer",
)


def _key(action):
    return f"fresh-{action}-{uuid4().hex}"


def _ctx(db, tenant_id, actor_id, permission):
    return require_enterprise_permission(db, tenant_id, actor_id, permission, bootstrap=False)


def _save(data):
    """Persist progress, deliberately excluding bearer tokens and passwords."""
    directory = Path("/artifacts")
    if not directory.exists():
        return
    serializable = {key: value for key, value in data.items() if key not in {"db", "client", "headers"}}
    (directory / "fresh-setup.json").write_text(json.dumps(serializable, indent=2, default=str), encoding="utf-8")
    if data.get("tenant_id"):
        (directory / f"fresh-setup-tenant-{data['tenant_id']}.json").write_text(
            json.dumps(serializable, indent=2, default=str), encoding="utf-8"
        )


def reconcile_fresh_reviewer_authorization(db, manifest_path: str) -> dict:
    """Complete only declared identity grants on an existing disposable journey.

    The existing records and their lifecycle are not rebuilt. The immutable
    pre-reconciliation manifest remains available to distinguish configuration
    preparation from business commands in this same fresh chain.
    """
    from tests.provision_strategic_fresh_uat import assert_disposable

    assert_disposable()
    manifest = Path(manifest_path).resolve(strict=True)
    assert manifest.parent == Path("/artifacts").resolve()
    state = json.loads(manifest.read_text(encoding="utf-8"))
    assert state["status"] == "UPSTREAM_COMPLETE"
    tenant_id, actor_id = state["tenant_id"], state["reviewer_id"]
    actor = db.get(UserAccount, actor_id)
    assert actor is not None and actor.tenant_id == tenant_id
    assert actor.email == state["actors"]["reviewer"]["email"]
    before = manifest.with_name(f"{manifest.stem}-before-reviewer-grants.json")
    assert not before.exists(), "Retain each prior authorization reconciliation; do not overwrite history"
    before.write_bytes(manifest.read_bytes())
    roles = {
        role.code: role
        for role in db.scalars(
            select(SecurityRole).where(SecurityRole.tenant_id == tenant_id, SecurityRole.code.in_(REVIEWER_ROLES))
        )
    }
    assert set(REVIEWER_ROLES) <= roles.keys()
    assignments = list(
        db.scalars(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == tenant_id,
                SecurityAccessAssignment.user_id == actor_id,
                SecurityAccessAssignment.scope_type == "organization",
                SecurityAccessAssignment.status == "active",
            )
        )
    )
    assert assignments
    grantor = assignments[0].granted_by_user_id
    existing = {item.role_id for item in assignments}
    added = []
    for code in REVIEWER_ROLES:
        if roles[code].id not in existing:
            db.add(
                SecurityAccessAssignment(
                    tenant_id=tenant_id,
                    subject_type="user",
                    user_id=actor_id,
                    role_id=roles[code].id,
                    scope_type="organization",
                    status="active",
                    granted_by_user_id=grantor,
                )
            )
            added.append({"role_code": code, "role_id": roles[code].id})
    db.commit()
    state["actors"]["reviewer"]["roles"] = list(REVIEWER_ROLES)
    state.setdefault("authorization_reconciliation", []).append(
        {
            "method": "Explicit disposable administrative identity bootstrap; no business mutation",
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "granted_by_user_id": grantor,
            "added_roles": added,
            "prior_manifest": before.name,
            "author_id_unchanged": state["actor_id"],
            "independent_reviewer": actor_id != state["actor_id"],
        }
    )
    _save(state)
    return state["authorization_reconciliation"][-1]


def _request(client, method, path, headers, *, item=None, payload=None, expected=200):
    actual_headers = dict(headers)
    if item is not None:
        actual_headers["If-Match"] = f'"{item["revision_version"]}"'
    response = client.request(method, f"/api/v1/{path}", headers=actual_headers, json=payload)
    assert response.status_code == expected, f"{method} {path}: {response.status_code} {response.text}"
    return response.json()


def _command(client, headers, root, item, action, payload=None):
    return _request(client, "POST", f"{root}/{item['id']}/{action}", headers, item=item, payload=payload)


def _publish_current_upstream_policies(client, state):
    """Bootstrap neutral defaults, then explicitly publish unrelaxed successors."""
    for domain, listing in (
        ("ideas", "admin/configurations/list"),
        ("business-analyses", "admin/configurations"),
        ("project-proposals", "admin/configurations/list"),
        ("strategic-gate-decisions", "admin/configurations/list"),
    ):
        records = _request(client, "GET", f"{domain}/{listing}", state["headers"]["admin_author"])
        latest = {}
        for record in records:
            if record["status"] == "published" and (
                record["kind"] not in latest or record["revision"] > latest[record["kind"]]["revision"]
            ):
                latest[record["kind"]] = record
        assert latest, domain
        for record in latest.values():
            draft = _request(
                client,
                "POST",
                f"{domain}/admin/configurations/{record['id']}/clone",
                {**state["headers"]["admin_author"], "If-Match": f'"{record["version"]}"'},
            )
            published = _request(
                client,
                "POST",
                f"{domain}/admin/configurations/{draft['id']}/publish",
                {**state["headers"]["admin_publisher"], "If-Match": f'"{draft["version"]}"'},
            )
            assert published["status"] == "published"
            state["configurations"][f"{domain}:{record['kind']}"] = {
                "id": published["id"],
                "revision": published["revision"],
                "hash": published["content_hash"],
                "author_id": state["admin_author_id"],
                "publisher_id": state["admin_publisher_id"],
                "unchanged_default_rules": True,
            }


def _capital_need(db, state, client):
    tid, author, reviewer = state["tenant_id"], state["actor_id"], state["reviewer_id"]
    author_service = CapitalPlanningService(
        db, tid, state["admin_author_id"], _ctx(db, tid, state["admin_author_id"], "capital_planning.admin.configure")
    )
    author_service.ensure_seed()
    published = next(row for row in author_service.configurations() if row.status == "published")
    draft = author_service.clone_configuration(
        published.id, published.version, target_workspace_id=state["enterprise_id"]
    )
    content = deepcopy(published.content_json)
    content.update(
        {
            "workspace_id": state["enterprise_id"],
            "themes": [
                {"code": "growth", "label": "Governed growth", "strategic_objective_codes": [state["objective_code"]]}
            ],
            "drivers": [{"code": "capacity", "label": "Capacity"}],
            "categories": [{"code": "capital", "label": "Capital"}],
            "planning_horizons": [{"code": "2030", "label": "2030"}],
            "urgency_levels": [{"code": "planned", "label": "Planned"}],
            "uncertainty_levels": [{"code": "conceptual", "label": "Conceptual"}],
            "strategic_capital_buckets": [
                {
                    "code": code,
                    "name": label,
                    "description": label,
                    "active": True,
                    "display_order": index,
                    "applicable_theme_codes": ["growth"],
                    "strategic_objective_codes": [state["objective_code"]],
                }
                for index, (code, label) in enumerate(
                    (("grow", "Grow copper capacity"), ("sustain", "Sustain the base")), 1
                )
            ],
        }
    )
    draft = author_service.update_configuration(
        draft.id,
        draft.version,
        name="Fresh copper capital policy",
        description="Explicit isolated administrative taxonomy",
        content=content,
    )
    publisher = CapitalPlanningService(
        db,
        tid,
        state["admin_publisher_id"],
        _ctx(db, tid, state["admin_publisher_id"], "capital_planning.admin.publish"),
    )
    policy = publisher.publish_configuration(draft.id, draft.version)
    state["configurations"]["capital_planning"] = {
        "id": policy.id,
        "revision": policy.revision,
        "hash": policy.content_hash,
    }
    service = CapitalPlanningService(db, tid, author, _ctx(db, tid, author, "capital_planning.cycle.create"))
    cycle = service.create_cycle(
        CycleCreate(
            name="Copper Processing Expansion UAT — 2027-2030",
            planning_horizon_start=date(2027, 1, 1),
            planning_horizon_end=date(2030, 12, 31),
            scope_workspace_id=state["portfolio_id"],
            responsible_organization_workspace_id=state["enterprise_id"],
            applicable_theme_codes=["growth"],
            capital_basis_currency="USD",
            description="Planning only, not Budget or FID authorization",
        ),
        _key("cycle"),
    )
    cycle = service.transition_cycle(cycle.id, "open", cycle.revision_version, _key("cycle-open"))
    demand = service.create_demand(
        DemandCreate(
            name="Copper Processing Expansion — UAT",
            description="Fresh governed capital need",
            planning_cycle_id=cycle.id,
            theme_codes=["growth"],
            strategic_objective_codes=[state["objective_code"]],
            business_or_asset_need="Increase controlled copper processing capacity and recovery",
            strategic_driver="capacity",
            demand_category="capital",
            urgency="planned",
            target_horizon="2030",
            sponsor_user_id=author,
            owning_workspace_id=state["portfolio_id"],
            indicative_capital_need="100000000",
            currency_code="USD",
            uncertainty_level="conceptual",
            potential_portfolio_id=state["portfolio_id"],
            assumptions=["Comparable copper feed remains available"],
            constraints=["No execution authority before FID"],
            dependencies=["Independent options analysis"],
        ),
        _key("demand"),
    )
    demand = service.transition_demand(demand.id, "submit", demand.revision_version, _key("demand-submit"))
    review_service = CapitalPlanningService(
        db, tid, reviewer, _ctx(db, tid, reviewer, "capital_planning.demand.review")
    )
    demand = review_service.transition_demand(demand.id, "review", demand.revision_version, _key("demand-review"))
    endorser = CapitalPlanningService(
        db,
        tid,
        state["capital_endorser_id"],
        _ctx(db, tid, state["capital_endorser_id"], "capital_planning.demand.endorse"),
    )
    demand = endorser.transition_demand(demand.id, "endorse", demand.revision_version, _key("demand-endorse"))
    plan = service.create_allocation_plan(
        AllocationPlanCreate(
            name="Copper strategic allocation target",
            planning_cycle_id=cycle.id,
            scope_workspace_id=state["portfolio_id"],
            allocation_basis="PERCENTAGE",
            description="Strategic intent, never Budget/FID approval",
        ),
        _key("allocation"),
    )
    plan = service.replace_allocation_lines(
        plan.id,
        AllocationLinesReplaceIn(
            lines=[
                AllocationLineIn(bucket_code="grow", target_percentage=80, rationale="Capacity investment intent"),
                AllocationLineIn(
                    bucket_code="sustain", target_percentage=20, rationale="Asset integrity strategic envelope"
                ),
            ]
        ),
        plan.revision_version,
    )
    plan = service.replace_bucket_classifications(
        plan.id,
        BucketClassificationsReplaceIn(
            classifications=[
                BucketClassificationIn(
                    target_type="DEMAND",
                    target_id=demand.id,
                    bucket_code="grow",
                    rationale="Copper capacity strategic need",
                ),
            ]
        ),
        plan.revision_version,
        _key("bucket-classify"),
    ).allocation_plan
    plan = service.transition_allocation_plan(plan.id, "submit", plan.revision_version, _key("allocation-submit"))
    plan = review_service.transition_allocation_plan(
        plan.id, "review", plan.revision_version, _key("allocation-review")
    )
    plan = endorser.transition_allocation_plan(plan.id, "endorse", plan.revision_version, _key("allocation-endorse"))
    origin = service.originate_idea(
        demand.id,
        OriginateIdeaIn(
            expected_benefit="Increase copper processing recovery through independently assessed options",
        ),
        demand.revision_version,
        _key("originate-idea"),
    )
    state.update(
        capital_cycle_id=cycle.id,
        capital_demand_id=demand.id,
        allocation_plan_id=plan.id,
        allocation_snapshot_hash=plan.endorsed_snapshot_hash,
        idea_id=origin.idea_id,
    )
    state["events"].append(
        {
            "case": "A2",
            "cycle": cycle.model_dump(mode="json"),
            "demand": demand.model_dump(mode="json"),
            "allocation": plan.model_dump(mode="json"),
            "idea_origin": origin.model_dump(mode="json"),
            "planning_is_not_fid": True,
        }
    )
    return _request(client, "GET", f"ideas/{origin.idea_id}", state["headers"]["author"])


def setup_fresh_capital_owner(db) -> dict:
    state = {"status": "IN_PROGRESS", "events": [], "configurations": {}, "proof": "Fresh A0-A7, not full A0-A31"}
    try:
        token = uuid4().hex[:10]
        tenant = Tenant(name=f"Fresh Copper UAT {token}", slug=f"fresh-copper-{token}", base_currency="USD")
        db.add(tenant)
        db.flush()
        state.update(tenant_id=tenant.id, tenant_slug=tenant.slug)
        owner = UserAccount(
            tenant_id=tenant.id,
            email=f"bootstrap-{token}@example.test",
            full_name="Isolated administrative bootstrap",
            status="active",
        )
        db.add(owner)
        db.commit()
        ensure_enterprise_permissions(db, tenant.id, owner.id)
        db.commit()
        roles = {r.code: r for r in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant.id))}
        config_roles = tuple(
            code for code in roles if code.endswith("_configuration_admin") or code.endswith("_config_admin")
        )
        configurations = ("configuration_admin", *config_roles)
        actor_roles = {
            "admin_author": configurations,
            "admin_publisher": configurations,
            "author": AUTHOR_ROLES,
            "reviewer": REVIEWER_ROLES,
            "intake": ("idea_intake_reviewer",),
            "idea_decider": ("idea_decision_maker", "gate_decision_maker"),
            "capital_endorser": ("capital_planning_endorser", "capital_planning_allocation_endorser"),
            "project_approver": ("project_approver",),
            "materializer": ("project_materialization_service",),
            "decision_maker": ("investment_decision_maker",),
            "initializer": ("project_workspace_initializer",),
            "activator": ("project_workspace_activator",),
        }
        actors = {}
        password_hash = hash_password("1234")
        for label, codes in actor_roles.items():
            assert set(codes) <= set(roles), sorted(set(codes) - set(roles))
            user = UserAccount(
                tenant_id=tenant.id,
                email=f"{label}-{token}@example.test",
                full_name=f"Fresh Copper {label.replace('_', ' ').title()}",
                status="active",
            )
            db.add(user)
            db.flush()
            db.add(
                AuthCredential(
                    tenant_id=tenant.id, user_id=user.id, provider="local", password_hash=password_hash, is_active=True
                )
            )
            for code in codes:
                db.add(
                    SecurityAccessAssignment(
                        tenant_id=tenant.id,
                        subject_type="user",
                        user_id=user.id,
                        role_id=roles[code].id,
                        scope_type="organization",
                        status="active",
                        granted_by_user_id=owner.id,
                    )
                )
            actors[label] = {"id": user.id, "email": user.email, "roles": list(codes)}
        db.commit()
        state.update(
            tenant_id=tenant.id,
            tenant_slug=tenant.slug,
            actors=actors,
            actor_id=actors["author"]["id"],
            reviewer_id=actors["reviewer"]["id"],
            admin_author_id=actors["admin_author"]["id"],
            admin_publisher_id=actors["admin_publisher"]["id"],
            decision_maker_id=actors["decision_maker"]["id"],
            initializer_id=actors["initializer"]["id"],
            activator_id=actors["activator"]["id"],
            capital_endorser_id=actors["capital_endorser"]["id"],
        )
        headers = {}
        for label, actor in actors.items():
            access_token, _ = create_access_token(
                claims={"sub": actor["id"], "tenant_id": tenant.id, "email": actor["email"]},
                secret_key=get_settings().auth_secret_key,
                expires_delta=timedelta(hours=12),
            )
            headers[label] = {"Authorization": f"Bearer {access_token}"}
        state["headers"] = headers
        client = TestClient(app)
        state["client"] = client
        enterprise_service = EnterpriseStructureService(db, tenant.id, owner.id)
        enterprise_service.ensure_seed()
        enterprise = db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == tenant.id, EnterpriseWorkspace.parent_id.is_(None)
            )
        )
        assert enterprise is not None
        seed_admin_metadata(db, tenant.id, owner.id)
        db.commit()
        business_unit = enterprise_service.create_node(
            EnterpriseNodeCreate(
                code=f"copper-bu-{token}",
                name="Copper investment business unit",
                workspace_type_code="business-unit",
                parent_id=enterprise.id,
            )
        )
        portfolio = enterprise_service.create_node(
            EnterpriseNodeCreate(
                code=f"copper-pf-{token}",
                name="Copper expansion portfolio UAT",
                workspace_type_code="portfolio",
                parent_id=business_unit.id,
            )
        )
        objective = EnterpriseStrategicObjective(
            tenant_id=tenant.id,
            code=f"copper-recovery-{token}",
            name="Controlled copper recovery growth",
            strategic_line="Copper capital strategy",
            priority="high",
            horizon="2030",
            responsible_area="Strategy",
            active=True,
            description="Explicit administrative reference bootstrap; no business final state",
            source_release_code=f"FRESH-UAT-REFERENCE-{token}",
            created_by_user_id=state["admin_author_id"],
        )
        db.add(objective)
        db.commit()
        state.update(
            enterprise_id=enterprise.id,
            business_unit_id=business_unit.id,
            portfolio_id=portfolio.id,
            objective_code=objective.code,
        )
        state["configurations"]["objective"] = {
            "id": objective.id,
            "code": objective.code,
            "method": "Explicit administrative reference bootstrap, not a terminal business fixture",
        }
        state["configurations"]["core"] = {
            "state": "NO_INITIAL_CORE_RELEASE",
            "reason": "Current Project creation/initialization do not require a CORE release; no fabricated publication",
        }
        configuration = ProjectWorkspaceConfigurationService(db, tenant.id, state["admin_author_id"])
        configuration.ensure_seed()
        modules = db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == tenant.id,
                AdminConfiguration.kind == "module_definition",
                AdminConfiguration.status == "published",
            )
        ).all()
        module_codes = [item.code for item in modules if item.code == "scope-manager"]
        template = configuration.create_template(
            ProjectTemplatePayload(
                code=f"FRESH-COPPER-{token}",
                name="Copper governed Project UAT",
                enabled_modules=module_codes,
                default_attributes={"currency": "USD", "country": "CO"},
            )
        )
        validation = configuration.validate_template(template.id)
        assert validation.valid, validation
        published_template = ProjectWorkspaceConfigurationService(
            db, tenant.id, state["admin_publisher_id"]
        ).publish_template(
            template.id,
            validation.content_hash,
        )
        state.update(template_id=published_template.id)
        state["configurations"]["project_template"] = published_template.model_dump(mode="json")
        initial_projects = list(
            db.scalars(
                select(EnterpriseWorkspace.id).where(
                    EnterpriseWorkspace.tenant_id == tenant.id, EnterpriseWorkspace.workspace_type_code == "project"
                )
            )
        )
        assert not initial_projects, {"unexpected_initial_project_ids": initial_projects}
        state["events"].append(
            {
                "case": "A1",
                "enterprise_id": enterprise.id,
                "business_unit": business_unit.model_dump(mode="json"),
                "portfolio": portfolio.model_dump(mode="json"),
                "initial_project_count": len(initial_projects),
            }
        )
        _save(state)
        _publish_current_upstream_policies(client, state)
        idea = _capital_need(db, state, client)
        options = _request(client, "GET", "ideas/options", headers["author"])
        idea = _command(client, headers["author"], "ideas", idea, "submit")
        idea = _command(
            client,
            headers["intake"],
            "ideas",
            idea,
            "screen",
            {
                "checklist": {item["code"]: True for item in options["screening_checklist"]},
                "notes": "Independently screened",
            },
        )
        idea = _command(
            client,
            headers["intake"],
            "ideas",
            idea,
            "route",
            {"route_code": "default", "notes": "Capital planning route"},
        )
        idea = _command(client, headers["intake"], "ideas", idea, "assign-owner", {"owner_user_id": state["actor_id"]})
        idea = _command(client, headers["author"], "ideas", idea, "evaluation/start")
        idea_configs = _request(client, "GET", "ideas/admin/configurations/list", headers["admin_author"])
        matrix = next(c for c in idea_configs if c["kind"] == "idea_evaluation_matrix" and c["status"] == "published")
        idea = _command(
            client,
            headers["author"],
            "ideas",
            idea,
            "evaluation/complete",
            {
                "ratings": [
                    {"criterion_code": item["code"], "rating": 4, "comment": "Copper capacity evidence"}
                    for item in matrix["content_json"]["criteria"]
                ],
                "comments": "Independent BA next",
            },
        )
        idea = _command(
            client,
            headers["idea_decider"],
            "ideas",
            idea,
            "accept",
            {"reason": "Proceed with mandatory independent BA"},
        )
        readiness = _request(client, "GET", f"ideas/{idea['id']}/proposal-readiness", headers["author"])
        assert readiness["status"] == "READY_FOR_BUSINESS_ANALYSIS", readiness
        ba_options = _request(client, "GET", "business-analyses/options", headers["author"])
        analysis_content = ba_payload(ba_options, objective.code)
        analysis_content["statement"] = "Copper processing capacity requires a governed expansion options decision"
        for option in analysis_content["options"]:
            option["rough_cost_range"] = {"low": 90_000_000, "high": 110_000_000, "currency": "USD"}
        analysis = _request(
            client,
            "POST",
            "business-analyses",
            {**headers["author"], "Idempotency-Key": _key("ba")},
            payload={"source_idea_id": idea["id"]},
            expected=201,
        )
        analysis = _request(
            client,
            "PUT",
            f"business-analyses/{analysis['id']}",
            headers["author"],
            item=analysis,
            payload=analysis_content,
        )
        analysis = _command(client, headers["author"], "business-analyses", analysis, "submit")
        analysis = _command(client, headers["reviewer"], "business-analyses", analysis, "start-review")
        analysis = _command(client, headers["reviewer"], "business-analyses", analysis, "complete")
        assert analysis["status"] == "COMPLETED" and analysis["completion_hash"]
        readiness = _request(client, "GET", f"ideas/{idea['id']}/proposal-readiness", headers["author"])
        assert readiness["status"] == "READY_FOR_PROJECT_PROPOSAL", readiness
        state.update(analysis_id=analysis["id"])
        state["events"].append({"case": "A3", "idea": idea, "analysis": analysis, "readiness": readiness})
        proposal = _request(
            client, "POST", "project-proposals", headers["author"], payload={"source_idea_id": idea["id"]}, expected=201
        )
        payload = proposal_payload(proposal)
        payload.update(
            name="Copper Processing Expansion — UAT",
            currency_code="USD",
            rom_cost="100000000",
            target_start_date="2027-01-01",
            target_finish_date="2030-12-31",
            sponsor_user_id=state["actor_id"],
            proposal_owner_user_id=state["actor_id"],
        )
        proposal = _request(
            client, "PUT", f"project-proposals/{proposal['id']}", headers["author"], item=proposal, payload=payload
        )
        proposal = _command(client, headers["author"], "project-proposals", proposal, "submit")
        proposal = _command(client, headers["reviewer"], "project-proposals", proposal, "start-review")
        proposal = _command(client, headers["author"], "project-proposals", proposal, "start-evaluation")
        proposal_configs = _request(
            client, "GET", "project-proposals/admin/configurations/list", headers["admin_author"]
        )
        matrix = next(
            c
            for c in proposal_configs
            if c["kind"] == "project_proposal_evaluation_matrix" and c["status"] == "published"
        )
        proposal = _command(
            client,
            headers["author"],
            "project-proposals",
            proposal,
            "complete-evaluation",
            {
                "ratings": [
                    {"criterion_code": item["code"], "rating": 4, "comment": "Current copper expansion evaluation"}
                    for item in matrix["content_json"]["criteria"]
                ],
                "comments": "Governed Strategic Gate next",
            },
        )
        proposal = _command(client, headers["reviewer"], "project-proposals", proposal, "mark-gate-ready")
        assert proposal["status"] == "READY_FOR_STRATEGIC_GATE"
        state.update(proposal_id=proposal["id"])
        state["events"].append({"case": "A4", "proposal": proposal})
        decision = _request(
            client,
            "POST",
            "strategic-gate-decisions",
            headers["author"],
            payload={"project_proposal_id": proposal["id"]},
            expected=201,
        )
        decision = _request(
            client,
            "PUT",
            f"strategic-gate-decisions/{decision['id']}",
            headers["author"],
            item=decision,
            payload={
                "decision_reason": "Authorize governed portfolio planning, not investment execution",
                "decision_comments": "Independent strategic admission only",
                "conditions": [],
                "decision_maker_user_id": actors["idea_decider"]["id"],
                "evidence_refs": [{"reference": f"UAT-STRATEGIC-{proposal['id']}"}],
                "committee": None,
            },
        )
        decision = _command(client, headers["author"], "strategic-gate-decisions", decision, "submit")
        decision = _command(client, headers["reviewer"], "strategic-gate-decisions", decision, "start-review")
        decision = _command(
            client,
            headers["idea_decider"],
            "strategic-gate-decisions",
            decision,
            "decide",
            {"outcome": "APPROVE", "reason": "Portfolio Intake only; no FID or activation", "conditions": []},
        )
        assert decision["state"] == "DECIDED" and decision["outcome"] == "APPROVE"
        state.update(strategic_gate_id=decision["id"])
        state["events"].append({"case": "A5", "strategic_gate": decision, "is_not_fid": True})
        preview = _request(
            client,
            "POST",
            "strategic-project-planning/preview",
            headers["author"],
            payload={"strategic_gate_decision_id": decision["id"]},
        )
        options = _request(
            client, "GET", f"project-creation-requests/options?parent_workspace_id={portfolio.id}", headers["author"]
        )
        project_type = next(
            item["code"] for item in options["classifications"]["project-type"] if item["code"].lower() == "capital"
        )
        entry = _request(
            client,
            "POST",
            "strategic-project-planning",
            headers["author"],
            payload={
                "strategic_gate_decision_id": decision["id"],
                "project_parent_workspace_id": portfolio.id,
                "project_template_config_id": published_template.id,
                "project_manager_user_id": state["actor_id"],
                "project_type": project_type,
                "expected_decision_hash": preview["source_decision_hash"],
                "expected_readiness_hash": preview["source_readiness_hash"],
                "country": "CO",
            },
            expected=201,
        )
        request = entry["project_creation_request"]
        request = _command(client, headers["author"], "project-creation-requests", request, "submit")
        request = _command(client, headers["reviewer"], "project-creation-requests", request, "start-review")
        request = _command(client, headers["project_approver"], "project-creation-requests", request, "approve")
        materialized = _request(
            client, "POST", f"project-creation-requests/{request['id']}/materialize", headers["materializer"]
        )
        project_id = materialized["materialized_workspace_id"]
        db.expire_all()
        project = db.get(EnterpriseWorkspace, project_id)
        assert project.workspace_type_code == "project" and project.status == "pending"
        final_entry = _request(client, "GET", f"strategic-project-planning/{decision['id']}", headers["author"])
        assert final_entry["can_enter_portfolio_evaluation"] and final_entry["can_enter_project_definition"]
        state.update(
            project_id=project_id,
            project_type=project_type,
            project_creation_request_id=request["id"],
            status="UPSTREAM_COMPLETE",
        )
        state["events"].append(
            {
                "case": "A6",
                "request": materialized,
                "project": {
                    "id": project.id,
                    "status": project.status,
                    "code": project.code,
                    "external_key": project.external_key,
                    "record_code": project.record_code,
                },
            }
        )
        state["events"].append({"case": "A7", "entry": final_entry})
        for record in db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == tenant.id, AdminConfiguration.status == "published"
            )
        ):
            state["configurations"].setdefault(
                f"{record.kind}:{record.code}",
                {"id": record.id, "revision": record.revision, "hash": record.content_hash},
            )
        _save(state)
        state["db"] = db
        return state
    except Exception as exc:
        state.update(status="BLOCKED", error={"type": type(exc).__name__, "message": str(exc)})
        try:
            db.rollback()
        finally:
            _save(state)
        raise
