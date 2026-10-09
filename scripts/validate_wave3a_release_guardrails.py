"""Static release guardrails for Wave 3A Periodic Portfolio Review.

Behavioural suites remain the authority for lifecycle semantics.  This script
protects architectural boundaries that can otherwise regress silently:
migration lineage, source-domain write isolation, Gate07J provider isolation,
canonical navigation, report completeness and CI wiring.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_REPORT_SECTIONS = (
    "Resumen ejecutivo",
    "Baseline real del repositorio",
    "ADR Wave 3A",
    "Posición en el proceso objetivo",
    "Frontera Portfolio Review vs Project Gate",
    "Matriz de autoridad de dominio",
    "REUSE BEFORE CREATE",
    "Review Session aggregate",
    "Review lifecycle",
    "Review types",
    "Cadence",
    "Scheduling semantics",
    "Snapshot contract",
    "Snapshot adapters",
    "Source-current y staleness",
    "Snapshot Preview / Freeze",
    "Agenda model",
    "Review readiness",
    "Portfolio conclusions",
    "Review Action aggregate",
    "Action types",
    "Action lifecycle",
    "Action authority/dispatch boundary",
    "Source-authority adapter rules",
    "Allocation integration",
    "Bucket variance integration",
    "Budget integration",
    "Resource integration",
    "Gate07I integration",
    "Gate07J integration",
    "Gate07K integration",
    "Gate HOLD vs Portfolio HOLD",
    "Project Matrix",
    "Portfolio summary",
    "Thresholds/alerts",
    "Multi-currency behavior",
    "Historical snapshots",
    "Period comparison",
    "Trends",
    "Action tracking",
    "ADMIN configuration",
    "USER workflow",
    "ADMIN/USER matrix",
    "Roles/permissions",
    "SoD",
    "ETag",
    "Idempotency",
    "SecurityEvent",
    "Persistence",
    "Migration",
    "API",
    "Navigation",
    "PostgreSQL happy path",
    "Action-semantics tests",
    "Bucket action test",
    "Gate-revalidation action test",
    "Snapshot staleness test",
    "Completed-review immutability",
    "Portfolio Rank regression",
    "Budget regression",
    "Resource regression",
    "Gate07I regression",
    "Gate07K regression",
    "Wave 2A regression",
    "Wave 1 regression",
    "Governance Model regression",
    "Browser USER E2E",
    "Browser ADMIN E2E",
    "Direct-route security",
    "Performance observation",
    "Deuda técnica",
    "Análisis final de brechas estratégicas",
    "Estado final de release",
    "Única recomendación del siguiente incremento",
)


def read(relative_path: str) -> str:
    path = ROOT / relative_path
    if not path.exists():
        raise AssertionError(f"required file missing: {relative_path}")
    return path.read_text(encoding="utf-8")


def require(text: str, needle: str, context: str) -> None:
    if needle not in text:
        raise AssertionError(f"{context}: missing {needle!r}")


def forbid(text: str, needle: str, context: str) -> None:
    if needle.lower() in text.lower():
        raise AssertionError(f"{context}: forbidden {needle!r}")


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def assert_no_foreign_writes(source: str) -> None:
    """Allow read adapters while rejecting obvious writes to source authorities."""

    tree = ast.parse(source)
    forbidden_models = re.compile(
        r"^(?:PortfolioProjectMembership|PortfolioProjectEvaluation|"
        r"PortfolioBudget|PortfolioResource|PortfolioScenarioConvergence|"
        r"PortfolioConvergedAlternative|InvestmentGatePreparation|"
        r"InvestmentDecision|StrategicCapitalAllocation|StrategicBucketClassification|"
        r"StrategicCapitalDemand|CapitalPlanningCycle|ProjectResourceDemand|RiskReadinessAssessment)"
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        short_name = call_name.rsplit(".", 1)[-1]
        if short_name not in {"add", "add_all", "delete", "merge", "update"}:
            continue
        for argument in node.args:
            name = (
                _call_name(argument.func)
                if isinstance(argument, ast.Call)
                else _call_name(argument)
            )
            if forbidden_models.search(name.rsplit(".", 1)[-1]):
                raise AssertionError(
                    f"cross-domain write boundary: {call_name} targets {name!r}"
                )


def assert_migration_boundary() -> None:
    migrations = sorted((ROOT / "backend/alembic/versions").glob("*wave3a*.py"))
    if len(migrations) != 1:
        found = ", ".join(path.name for path in migrations) or "none"
        raise AssertionError(f"Wave 3A migration: expected one file, found {found}")
    migration = migrations[0].read_text(encoding="utf-8")
    require(migration, 'revision: str = "20261005_0064"', "migration revision")
    require(migration, 'down_revision: str | None = "20261001_0063"', "migration parent")
    for table in (
        "portfolio_review_sessions",
        "portfolio_review_snapshots",
        "portfolio_review_conclusions",
        "portfolio_review_actions",
        "portfolio_review_commands",
    ):
        require(migration, table, "Wave 3A persistence")
    upgrade = migration.split("def downgrade", maxsplit=1)[0]
    for destructive in (
        "op.drop_table",
        "op.drop_column",
        "op.alter_column",
        "op.rename_table",
    ):
        forbid(upgrade, destructive, "additive migration")
    for foreign in (
        "portfolio_budget",
        "portfolio_resource",
        "portfolio_evaluation",
        "portfolio_convergence",
        "investment_decision",
        "strategic_capital_allocation",
    ):
        if re.search(
            rf'op\.(?:add_column|alter_column|drop_column)\(\s*["\'][^"\']*{foreign}',
            upgrade,
            flags=re.IGNORECASE,
        ):
            raise AssertionError(f"foreign authority migration mutation: {foreign}")


def assert_backend_boundaries() -> None:
    router_registry = read("backend/app/api/v1/router.py")
    alembic_env = read("backend/alembic/env.py")
    models = read("backend/app/modules/portfolio_review/models.py")
    schemas = read("backend/app/modules/portfolio_review/schemas.py")
    service = read("backend/app/modules/portfolio_review/service.py")
    router = read("backend/app/modules/portfolio_review/router.py")
    combined = "\n".join((models, schemas, service, router))

    require(router_registry, "portfolio_review", "API registration")
    require(alembic_env, "portfolio_review", "Alembic model registration")
    for aggregate in (
        "PortfolioReviewSession",
        "PortfolioReviewSnapshot",
        "PortfolioReviewConclusion",
        "PortfolioReviewAction",
    ):
        require(combined, aggregate, "Wave 3A aggregate")
    for control in (
        "ETAG_MISMATCH",
        "Idempotency",
        "SecurityEvent",
        "HOLD_FOR_CAPACITY",
        "REQUEST_REASSESSMENT",
        "REBALANCE_CAPITAL",
        "MOVE_BETWEEN_BUCKETS",
        "REQUEST_GATE_REVALIDATION",
        "NOT_EVALUABLE",
    ):
        require(combined, control, "governed control")
    assert_no_foreign_writes(service)
    for forbidden_call in (
        ".create_scenario(",
        ".freeze_scenario(",
        ".complete_evaluation(",
        ".recommend(",
        ".decide(",
        ".endorse_allocation_plan(",
        ".classify(",
    ):
        forbid(service, forbidden_call, "source-authority command boundary")

    for ranking_pattern in (
        r"def\s+(?:calculate|compute|recalculate|assign)_?rank\b",
        r"\breview_rank\b",
        r"\bcommittee_rank\b",
        r"\badjusted_rank\b",
    ):
        if re.search(ranking_pattern, combined, flags=re.IGNORECASE):
            raise AssertionError(f"no new ranking: forbidden pattern {ranking_pattern!r}")

    for excluded_scope in (
        "risk_appetite",
        "risk_capacity",
        "basic_data_readiness",
        "qra_assessment",
        "owner_capability_readiness",
    ):
        forbid(combined, excluded_scope, "Wave 3A STOP boundary")

    gate_policy = "\n".join(
        read(path)
        for path in (
            "backend/app/modules/investment_evidence_policy/service.py",
            "backend/app/modules/investment_evidence_policy/decision_criteria.py",
            "backend/app/modules/investment_gate_preparation/service.py",
        )
    )
    forbid(
        gate_policy,
        "PORTFOLIO_REVIEW_READINESS_PROVIDER",
        "Gate07J provider boundary",
    )


def assert_navigation_boundary() -> None:
    blueprint_path = Path(
        "frontend/src/features/enterprise-strategy/navigation/strategicNavigationBlueprint.ts"
    )
    blueprint = read(blueprint_path.as_posix())
    outlet = read("frontend/src/features/enterprise-strategy/StrategicViewOutlet.tsx")
    app = read("frontend/src/App.tsx")
    application_navigation = read("frontend/src/navigation/applicationNavigation.ts")

    for view in (
        "portfolio-review-sessions",
        "portfolio-review-overview",
        "portfolio-review-snapshot",
        "portfolio-review-allocation",
        "portfolio-review-project-matrix",
        "portfolio-review-budget-resources",
        "portfolio-review-gate-fid",
        "portfolio-review-exceptions",
        "portfolio-review-conclusions",
        "portfolio-review-actions",
        "portfolio-review-history",
        "portfolio-review-trends",
        "portfolio-review-configuration",
    ):
        require(blueprint, view, "strategic navigation source of truth")
        require(outlet, f'"{view}"', "strategic outlet registration")
    require(application_navigation, 'buildStrategicMacroprocess("user")', "USER blueprint projection")
    require(application_navigation, 'buildStrategicMacroprocess("admin")', "ADMIN blueprint projection")
    for token in ("portfolio-review", "PortfolioReview"):
        forbid(app, token, "App.tsx expansion guard")

    route_literal = re.compile(r"/app/(?:admin/)?strategy/portfolio-review[^\"'`\s]*")
    for path in (ROOT / "frontend/src").rglob("*.ts*"):
        relative = path.relative_to(ROOT)
        if relative == blueprint_path or re.search(r"\.(?:test|spec)\.tsx?$", path.name):
            continue
        match = route_literal.search(path.read_text(encoding="utf-8"))
        if match:
            raise AssertionError(
                f"navigation outside blueprint: {match.group(0)!r} in {relative.as_posix()}"
            )


def assert_report_contract() -> None:
    adr = read("docs/74-adr-wave3a-periodic-portfolio-review.md")
    release = read("docs/75-wave3a-periodic-portfolio-review-release.md")
    for term in (
        "PortfolioReviewSession",
        "PortfolioReviewSnapshot",
        "HOLD_FOR_CAPACITY",
        "Gate07K HOLD",
        "NOT_EVALUABLE",
    ):
        require(adr, term, "ADR authority contract")

    headings = re.findall(r"^##\s+(\d+)\.\s+(.+?)\s*$", release, flags=re.MULTILINE)
    actual_numbers = [int(number) for number, _ in headings]
    if actual_numbers != list(range(1, 75)):
        raise AssertionError(
            "release report: expected exactly 74 sequential numbered sections, "
            f"found {actual_numbers}"
        )
    actual_titles = tuple(title for _, title in headings)
    if actual_titles != EXPECTED_REPORT_SECTIONS:
        raise AssertionError("release report section titles do not match Wave 3A contract")
    if release.count("**Única recomendación:**") != 1:
        raise AssertionError("release report: expected exactly one recommendation")

    matrix_rows = re.findall(
        r"^\|\s*([^|]+?)\s*\|\s*(PASS|FAIL|PENDIENTE|NO EJECUTADO)\s*\|",
        release,
        re.MULTILINE,
    )
    if len(matrix_rows) != 69:
        raise AssertionError(
            f"release report: expected exactly 69 acceptance criteria, found {len(matrix_rows)}"
        )
    states = [state for _, state in matrix_rows]
    if states and all(state == "PASS" for state in states):
        require(
            release,
            "PERIODIC_PORTFOLIO_REVIEW_AND_GOVERNANCE_CYCLE_RELEASE_VALIDATED",
            "exclusive release state",
        )
        require(
            release,
            "READY_FOR_GOVERNED_PERIODIC_PORTFOLIO_REVIEW",
            "exclusive final output",
        )


def assert_test_and_ci_wiring() -> None:
    backend_tests = sorted((ROOT / "backend/tests").glob("**/*wave3a*.py"))
    if not backend_tests:
        raise AssertionError("Wave 3A backend tests are missing")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in backend_tests).lower()
    for evidence in (
        "hold_for_capacity",
        "request_reassessment",
        "rebalance_capital",
        "move_between_buckets",
        "request_gate_revalidation",
        "stale",
        "immutable",
        "rank",
        "budget",
        "resource",
        "portfolioscenarioconvergence",
        "investmentdecision",
    ):
        require(combined, evidence, "mandatory Wave 3A coverage")

    browser = read("frontend/e2e/portfolio-review.spec.ts").lower()
    for evidence in (
        "chromium",
        "user",
        "admin",
        "snapshot",
        "project matrix",
        "budget & resources",
        "gate / fid",
        "conclusions",
        "actions",
        "history",
    ):
        require(browser, evidence, "browser release coverage")

    workflow = read(".github/workflows/ci.yml")
    compose = read("docker-compose.wave3a.yml")
    for token in (
        "wave3a-periodic-portfolio-review-postgres",
        "scripts/validate_wave3a_release_guardrails.py",
        "docker-compose.wave3a.yml",
        "alembic current | grep 20261005_0064",
        "wave3a-postgres-validation",
    ):
        require(workflow, token, "Wave 3A CI wiring")
    for token in (
        "postgres:16-alpine",
        "wave3a-validation",
        "test_wave3a_periodic_portfolio_review_migration_postgres.py",
        "test_wave3a_periodic_portfolio_review_postgres.py",
        "PYPMIS_WAVE3A_MIGRATION_DATABASE_URL",
        "tmpfs:",
        "wave3a-browser-db",
        "wave3a-browser-api",
        "wave3a-browser-frontend",
        "PYPMIS_WAVE3A_BROWSER_FIXTURE: disposable-only",
    ):
        require(compose, token, "Wave 3A PostgreSQL wiring")
    for token in (
        '--grep-invert "Wave 3A real"',
        "--profile browser",
        "E2E_BASE_URL: http://127.0.0.1:5516",
        "E2E_API_URL: http://127.0.0.1:8813",
        "playwright test portfolio-review.spec.ts --project=chromium --workers=1",
    ):
        require(workflow, token, "isolated Wave 3A Chromium CI wiring")


def main() -> None:
    assert_migration_boundary()
    assert_backend_boundaries()
    assert_navigation_boundary()
    assert_report_contract()
    assert_test_and_ci_wiring()
    print("WAVE3A_RELEASE_GUARDRAILS=PASS")


if __name__ == "__main__":
    main()
