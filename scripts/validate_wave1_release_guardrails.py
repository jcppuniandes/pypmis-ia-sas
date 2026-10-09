"""Static release guardrails for Wave 1 Strategic Capital Planning.

The checks deliberately span repository boundaries that are not available to
the backend unit-test image (CI, migration, API registration and frontend
navigation). Behavioural lifecycle tests remain in the backend and Playwright
suites; this script prevents accidental architectural expansion or stale
release wiring before those suites start.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def require(text: str, needle: str, context: str) -> None:
    if needle not in text:
        raise AssertionError(f"{context}: missing {needle!r}")


def forbid(text: str, needle: str, context: str) -> None:
    if needle.lower() in text.lower():
        raise AssertionError(f"{context}: forbidden {needle!r}")


def main() -> None:
    migration = read("backend/alembic/versions/20260929_0062_wave1_capital_planning.py")
    require(migration, 'revision: str = "20260929_0062"', "migration revision")
    require(migration, 'down_revision: str | None = "20260916_0061"', "migration parent")
    for table in (
        "capital_planning_cycles",
        "capital_planning_cycle_themes",
        "strategic_capital_demands",
        "strategic_capital_demand_themes",
        "strategic_capital_demand_objectives",
        "capital_demand_idea_origins",
    ):
        require(migration, f'"{table}"', "Wave 1 persistence")
    require(
        migration,
        'sa.Column("source_capital_demand_id", sa.Integer(), nullable=True)',
        "standalone Idea compatibility",
    )
    require(
        migration,
        'sa.Column("source_capital_demand_snapshot_hash", sa.String(64), nullable=True)',
        "historical Idea compatibility",
    )
    for excluded_table in (
        "strategic_capital_buckets",
        "periodic_portfolio_reviews",
        "basic_data_readiness",
        "qra_assessments",
        "owner_capability_readiness",
    ):
        forbid(migration, excluded_table, "Wave 1 STOP boundary")

    api_router = read("backend/app/api/v1/router.py")
    alembic_env = read("backend/alembic/env.py")
    require(api_router, "capital_planning_router.router", "API registration")
    require(alembic_env, "capital_planning_models", "Alembic model registration")

    service = read("backend/app/modules/capital_planning/service.py")
    require(service, "from app.modules.idea_demand.service import IdeaDemandService", "Idea authority reuse")
    for forbidden_import in (
        "app.modules.projects",
        "app.modules.project_workspace",
        "app.modules.portfolio_budget",
        "app.modules.funds",
        "app.modules.economic_financial_model",
    ):
        forbid(service, forbidden_import, "Demand side-effect boundary")

    gate_policy = "\n".join(
        read(path)
        for path in (
            "backend/app/modules/investment_evidence_policy/service.py",
            "backend/app/modules/investment_evidence_policy/decision_criteria.py",
            "backend/app/modules/investment_gate_preparation/service.py",
        )
    )
    forbid(gate_policy, "CAPITAL_PLANNING_READINESS_PROVIDER", "Gate07J provider boundary")

    navigation = read("frontend/src/features/enterprise-strategy/navigation/strategicNavigationBlueprint.ts")
    outlet = read("frontend/src/features/enterprise-strategy/StrategicViewOutlet.tsx")
    app = read("frontend/src/App.tsx")
    navigation_ids = (
        "phase-1-strategic-capital-planning-demand",
        "capital-planning-cycles",
        "capital-demand-pipeline",
        "capital-demand-my",
        "capital-demand-review",
        "capital-demand-endorsed",
        "capital-demand-history",
        "capital-planning-configuration",
    )
    for identifier in navigation_ids:
        require(navigation, identifier, "strategic navigation source of truth")
    for identifier in navigation_ids[1:]:
        require(outlet, f'"{identifier}"', "strategic view routing")
    forbid(app, "CapitalPlanning", "App.tsx expansion guard")
    forbid(app, "capital-planning", "App.tsx expansion guard")

    compose = read("docker-compose.wave1.yml")
    for profile in ('profiles: ["validation"]', 'profiles: ["browser"]'):
        require(compose, profile, "Wave 1 compose profile")
    require(
        compose,
        "tests/postgres/test_wave1_capital_planning_release_postgres.py",
        "PostgreSQL release suite wiring",
    )
    require(compose, "e2e/capital-planning.spec.ts", "Chromium release suite wiring")

    ci = read(".github/workflows/ci.yml")
    require(ci, "wave1-capital-planning-postgres:", "dedicated CI job")
    require(ci, "20260929_0062", "CI migration-head assertion")
    forbid(ci, "grep 20260915_0060", "stale CI migration-head assertion")
    forbid(ci, "grep 20260902_0058", "stale CI migration-head assertion")

    print("WAVE1_RELEASE_GUARDRAILS=PASS")


if __name__ == "__main__":
    main()
