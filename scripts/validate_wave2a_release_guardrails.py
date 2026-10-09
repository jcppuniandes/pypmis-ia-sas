"""Static release guardrails for Wave 2A Strategic Capital Allocation.

The behavioural suites prove lifecycle and aggregation semantics.  This script
guards repository-wide boundaries that are easy to regress without an obvious
unit-test failure: the migration chain, cross-domain write isolation, Gate07J
provider isolation, canonical navigation and the STOP boundary.

It intentionally reports only structural PASS/FAIL.  Running it is not a
substitute for PostgreSQL, browser or regression evidence.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


EXPECTED_REPORT_SECTIONS = (
    "Resumen ejecutivo",
    "Baseline real del repositorio",
    "ADR Wave 2A",
    "Posición en el proceso objetivo",
    "Matriz de autoridad de dominio",
    "REUSE BEFORE CREATE",
    "Concepto Strategic Capital Bucket",
    "Theme versus Bucket",
    "Strategic Objective versus Bucket",
    "Bucket configuration",
    "Allocation Plan aggregate",
    "Allocation Plan lifecycle",
    "Allocation basis",
    "Bucket Allocation Line",
    "Min/Target/Max semantics",
    "Percentage validation",
    "Demand classification",
    "Project/Portfolio classification",
    "Classification precedence",
    "Unclassified policy",
    "Current Demand Position",
    "Current Portfolio Position",
    "Recommended Scenario Position",
    "Approved Investment Position",
    "Modelo Target/Current/Recommended/Approved",
    "Variance model",
    "Multi-currency behavior",
    "No-double-counting controls",
    "Strategic alignment",
    "Planning Cycle integration",
    "Historical snapshots",
    "Source-current y staleness",
    "Refresh Preview / Apply",
    "ADMIN configuration",
    "USER workflow",
    "Matriz ADMIN / USER",
    "Roles y permisos",
    "Separation of duties",
    "ETag",
    "Idempotency",
    "SecurityEvent",
    "Persistence design",
    "Migration",
    "API",
    "Comparison read model",
    "Navigation",
    "PostgreSQL happy path",
    "Percentage negative test",
    "Unclassified coverage test",
    "Multi-currency test",
    "Standalone Project classification test",
    "Lineage classification test",
    "No-double-counting test",
    "Portfolio Rank regression",
    "Budget regression",
    "Resource regression",
    "Gate07I regression",
    "Gate07K regression",
    "Wave 1 regression",
    "Governance Model regression",
    "Browser USER E2E",
    "Browser ADMIN E2E",
    "Performance observation",
    "Deuda técnica",
    "Contrato futuro Periodic Portfolio Review",
    "Análisis final de brechas",
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


def forbid_regex(text: str, pattern: str, context: str) -> None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if match:
        excerpt = match.group(0).replace("\n", " ")[:180]
        raise AssertionError(f"{context}: forbidden pattern {pattern!r}: {excerpt!r}")


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def assert_no_foreign_writes(source: str) -> None:
    """Reject obvious ORM writes to authorities that Wave 2A only reads.

    Direct SELECT imports are permitted because the comparison read model must
    consume existing sources.  Service orchestration and SQLAlchemy write calls
    against those sources are not permitted.
    """

    tree = ast.parse(source)
    forbidden_models = re.compile(
        r"^(?:Portfolio(?:Budget|Resource|Evaluation|Convergence)|"
        r"InvestmentDecision|Fund|Funding|EconomicFinancial|ProjectRank|PortfolioRank)"
    )
    forbidden_service = re.compile(
        r"(?:PortfolioBudget|PortfolioResource|PortfolioEvaluation|PortfolioConvergence|"
        r"InvestmentDecision|FundsManager|EconomicFinancial).*Service$"
    )

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            for name in names:
                if forbidden_service.search(name.rsplit(".", 1)[-1]):
                    raise AssertionError(
                        f"cross-domain write boundary: service import {name!r}"
                    )

        if not isinstance(node, ast.Call):
            continue

        call_name = _call_name(node.func)
        short_name = call_name.rsplit(".", 1)[-1]
        if forbidden_service.search(short_name):
            raise AssertionError(
                f"cross-domain write boundary: service construction {call_name!r}"
            )

        is_write_call = short_name in {"add", "add_all", "delete", "merge", "update"}
        is_sql_write = short_name in {"delete", "update"} and call_name in {
            "delete",
            "update",
        }
        if not (is_write_call or is_sql_write):
            continue
        for argument in node.args:
            name = (
                _call_name(argument.func)
                if isinstance(argument, ast.Call)
                else _call_name(argument)
            )
            if forbidden_models.search(name.rsplit(".", 1)[-1]):
                raise AssertionError(
                    f"cross-domain write boundary: {call_name} targets forbidden authority {name!r}"
                )


def _wave2a_migration() -> tuple[Path, str]:
    candidates = sorted((ROOT / "backend/alembic/versions").glob("*wave2a*.py"))
    if len(candidates) != 1:
        found = ", ".join(path.name for path in candidates) or "none"
        raise AssertionError(
            f"Wave 2A migration: expected exactly one file, found {found}"
        )
    path = candidates[0]
    return path, path.read_text(encoding="utf-8")


def assert_migration_boundary() -> None:
    path, migration = _wave2a_migration()
    require(
        migration,
        'down_revision: str | None = "20260929_0062"',
        "Wave 2A migration parent",
    )
    require(migration, "strategic_capital_allocation", "Wave 2A allocation persistence")
    require(
        migration,
        "strategic_bucket_classification",
        "Wave 2A classification persistence",
    )

    upgrade = migration.split("def downgrade", maxsplit=1)[0]
    for operation in (
        "op.drop_table",
        "op.drop_column",
        "op.alter_column",
        "op.rename_table",
    ):
        forbid(upgrade, operation, f"additive migration {path.name}")

    forbidden_existing_targets = (
        "portfolio_budget",
        "portfolio_resource",
        "portfolio_evaluation",
        "portfolio_convergence",
        "investment_decision",
        "funds_",
        "economic_financial",
    )
    for target in forbidden_existing_targets:
        forbid_regex(
            upgrade,
            rf'op\.(?:add_column|alter_column|drop_column)\(\s*["\'][^"\']*{target}',
            "foreign authority migration mutation",
        )

    for excluded_table in (
        "periodic_portfolio_reviews",
        "portfolio_review_sessions",
        "risk_appetite",
        "risk_capacity",
        "risk_threshold",
        "basic_data_readiness",
        "qra_assessments",
        "owner_capability_readiness",
    ):
        forbid(migration, excluded_table, "Wave 2A STOP boundary")


def assert_backend_boundaries() -> None:
    router = read("backend/app/api/v1/router.py")
    alembic_env = read("backend/alembic/env.py")
    models = read("backend/app/modules/capital_planning/models.py")
    service = read("backend/app/modules/capital_planning/service.py")
    schemas = read("backend/app/modules/capital_planning/schemas.py")
    capital_source = f"{models}\n{service}\n{schemas}"

    require(
        router, "capital_planning_router.router", "Capital Planning API registration"
    )
    require(alembic_env, "capital_planning_models", "Alembic model registration")
    for symbol in (
        "StrategicCapitalAllocationPlan",
        "StrategicCapitalAllocationLine",
        "StrategicBucketClassification",
    ):
        require(capital_source, symbol, "Wave 2A aggregate")

    for control in (
        "ETAG_MISMATCH",
        "Idempotency",
        "SecurityEvent",
        "UNCLASSIFIED",
        "NOT_EVALUABLE",
    ):
        require(capital_source, control, "Wave 2A governed control")

    assert_no_foreign_writes(service)
    for forbidden_event in (
        '"portfolio_budget.',
        '"portfolio_resource.',
        '"portfolio_evaluation.',
        '"portfolio_convergence.',
        '"investment_decision.',
        '"funds_manager.',
    ):
        forbid(service, forbidden_event, "cross-domain event mutation")

    for ranking_pattern in (
        r"\b(?:bucket|project)_rank\b",
        r"\branking_score\b",
        r"def\s+(?:calculate|compute|recalculate|assign)_?rank\b",
        r"\binvestment_winner\b",
    ):
        forbid_regex(capital_source, ranking_pattern, "no new ranking")

    gate_policy = "\n".join(
        read(path)
        for path in (
            "backend/app/modules/investment_evidence_policy/service.py",
            "backend/app/modules/investment_evidence_policy/decision_criteria.py",
            "backend/app/modules/investment_gate_preparation/service.py",
        )
    )
    for pattern in (
        r"STRATEGIC_(?:CAPITAL_)?BUCKET_READINESS_PROVIDER",
        r"STRATEGIC_(?:CAPITAL_)?ALLOCATION_READINESS_PROVIDER",
        r"capital[_ -]planning.*readiness[_ -]provider",
    ):
        forbid_regex(gate_policy, pattern, "Gate07J provider boundary")


def assert_navigation_boundary() -> None:
    blueprint_path = Path(
        "frontend/src/features/enterprise-strategy/navigation/strategicNavigationBlueprint.ts"
    )
    outlet_path = Path(
        "frontend/src/features/enterprise-strategy/StrategicViewOutlet.tsx"
    )
    blueprint = read(blueprint_path.as_posix())
    outlet = read(outlet_path.as_posix())
    app = read("frontend/src/App.tsx")
    application_navigation = read("frontend/src/navigation/applicationNavigation.ts")

    user_views = (
        "strategic-capital-allocation",
        "strategic-capital-allocation-history",
    )
    admin_views = ("strategic-capital-bucket-configuration",)
    for identifier in (*user_views, *admin_views):
        require(blueprint, identifier, "strategic navigation source of truth")
    for view in (*user_views, *admin_views):
        require(outlet, f'"{view}"', "strategic outlet registration")

    require(blueprint, "Strategic Capital Planning & Demand", "USER parent navigation")
    require(
        blueprint,
        "Strategic Capital Planning & Demand Configuration",
        "ADMIN parent navigation",
    )
    require(
        application_navigation,
        'buildStrategicMacroprocess("user")',
        "USER blueprint projection",
    )
    require(
        application_navigation,
        'buildStrategicMacroprocess("admin")',
        "ADMIN blueprint projection",
    )

    for token in (
        "strategic-capital-allocation",
        "strategic-capital-bucket-configuration",
        "StrategicCapitalAllocation",
        "StrategicCapitalBucket",
    ):
        forbid(app, token, "App.tsx expansion guard")

    route_literal = re.compile(
        r"/app/(?:admin/)?strategy/strategic-capital-(?:allocation|bucket)[^\"'`\s]*"
    )
    for path in (ROOT / "frontend/src").rglob("*.ts*"):
        relative = path.relative_to(ROOT)
        if relative == blueprint_path:
            continue
        text = path.read_text(encoding="utf-8")
        match = route_literal.search(text)
        if match:
            raise AssertionError(
                f"navigation outside blueprint: literal {match.group(0)!r} in {relative.as_posix()}"
            )


def assert_release_report_contract() -> None:
    adr = read("docs/72-adr-wave2a-strategic-capital-buckets-allocation.md")
    release = read("docs/73-wave2a-strategic-capital-buckets-allocation-release.md")
    for term in (
        "allocation_plan_id",
        "allocation_plan_hash",
        "bucket_configuration_revision/hash",
        "current_portfolio_position_snapshot",
        "recommended_position_snapshot",
        "approved_position_snapshot",
        "unclassified_exposure",
    ):
        require(adr, term, "future Periodic Portfolio Review contract")
    require(
        release,
        "STRATEGIC_CAPITAL_BUCKETS_AND_ALLOCATION_FRAMEWORK_RELEASE_VALIDATED",
        "exclusive release state contract",
    )
    require(
        release,
        "READY_FOR_STRATEGIC_CAPITAL_ALLOCATION_AND_PORTFOLIO_BALANCE_ANALYSIS",
        "exclusive final output contract",
    )
    if release.count("**Única recomendación:**") != 1:
        raise AssertionError(
            "release report: expected exactly one next-increment recommendation"
        )

    headings = re.findall(r"^##\s+(\d+)\.\s+(.+?)\s*$", release, flags=re.MULTILINE)
    actual_numbers = [int(number) for number, _ in headings]
    if actual_numbers != list(range(1, 69)):
        raise AssertionError(
            "release report: expected exactly 68 sequential numbered sections, "
            f"found {actual_numbers}"
        )
    actual_titles = tuple(title for _, title in headings)
    if actual_titles != EXPECTED_REPORT_SECTIONS:
        mismatches = [
            f"{index}: expected {expected!r}, found {actual!r}"
            for index, (expected, actual) in enumerate(
                zip(EXPECTED_REPORT_SECTIONS, actual_titles, strict=True), start=1
            )
            if expected != actual
        ]
        raise AssertionError(
            "release report section mismatch: " + "; ".join(mismatches)
        )

    matrix_rows = re.findall(
        r"^\|\s*([^|]+?)\s*\|\s*(PASS|FAIL|PENDIENTE|NO EJECUTADO)\s*\|",
        release,
        re.MULTILINE,
    )
    if len(matrix_rows) < 50:
        raise AssertionError(
            f"release report: acceptance matrix is incomplete ({len(matrix_rows)} result rows)"
        )
    matrix_states = [state for _, state in matrix_rows]
    all_pass = bool(matrix_states) and all(state == "PASS" for state in matrix_states)
    objective_marker = "Estado exclusivo objetivo, no declarado todavía"
    final_marker = "Final output objetivo, no declarado todavía"
    if all_pass:
        if objective_marker in release or final_marker in release:
            raise AssertionError(
                "release report: all PASS but exclusive release state remains withheld"
            )
    else:
        require(release, objective_marker, "honest exclusive release-state reporting")
        require(release, final_marker, "honest final-output reporting")


def assert_test_and_ci_wiring() -> None:
    backend_tests = sorted((ROOT / "backend/tests").glob("**/*wave2a*.py"))
    if not backend_tests:
        raise AssertionError("Wave 2A backend tests: no *wave2a*.py suite found")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in backend_tests)
    for evidence in (
        "percentage",
        "unclassified",
        "currency",
        "standalone",
        "lineage",
        "double_count",
        "rank",
        "budget",
        "resource",
        "gate07i",
        "gate07k",
    ):
        require(combined.lower(), evidence, "mandatory Wave 2A regression coverage")

    frontend_tests = sorted(
        (ROOT / "frontend/src").glob("**/*capital*allocation*.test.ts*")
    )
    if not frontend_tests:
        raise AssertionError(
            "Wave 2A frontend tests: no capital allocation unit suite found"
        )

    browser_tests = sorted((ROOT / "frontend/e2e").glob("*capital*allocation*.spec.ts"))
    if not browser_tests:
        raise AssertionError(
            "Wave 2A browser tests: no capital allocation Chromium suite found"
        )
    browser_source = "\n".join(
        path.read_text(encoding="utf-8") for path in browser_tests
    ).lower()
    for evidence in ("chromium", "user", "admin", "allocation", "bucket", "history"):
        require(browser_source, evidence, "mandatory Wave 2A browser coverage")

    for relative_path in (
        "backend/tests/postgres/test_wave2a_strategic_capital_allocation_migration_postgres.py",
        "backend/tests/postgres/test_wave2a_strategic_capital_allocation_postgres.py",
    ):
        if not (ROOT / relative_path).is_file():
            raise AssertionError(f"Wave 2A PostgreSQL suite missing: {relative_path}")

    workflow = read(".github/workflows/ci.yml")
    compose = read("docker-compose.wave2a.yml")
    for token in (
        "wave2a-strategic-capital-allocation-postgres",
        "scripts/validate_wave2a_release_guardrails.py",
        "docker-compose.wave2a.yml",
    ):
        require(workflow, token, "Wave 2A CI wiring")
    for token in (
        "postgres:16-alpine",
        "wave2a-validation",
        "test_wave2a_strategic_capital_allocation_migration_postgres.py",
        "test_wave2a_strategic_capital_allocation_postgres.py",
    ):
        require(compose, token, "Wave 2A PostgreSQL validation wiring")


def main() -> None:
    assert_migration_boundary()
    assert_backend_boundaries()
    assert_navigation_boundary()
    assert_release_report_contract()
    assert_test_and_ci_wiring()
    print("WAVE2A_RELEASE_GUARDRAILS=PASS")


if __name__ == "__main__":
    main()
