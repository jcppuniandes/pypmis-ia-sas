"""Static Wave 2B boundaries supplement, never replace, behavioral evidence."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, needle: str) -> None:
    assert needle in text, f"Missing architectural contract: {needle}"


def main() -> None:
    migration = read("backend/alembic/versions/20261008_0065_wave2b_basic_data_readiness.py")
    require(migration, "20261005_0064")
    require(migration, "20261008_0065")
    upgrade = migration.split("def downgrade", maxsplit=1)[0]
    assert not re.search(r"op\.(?:drop_table|drop_column|alter_column|rename_table)", upgrade)
    for table in ("project_basic_data_items", "basic_data_readiness_assessments", "basic_data_commands"):
        require(migration, table)
    assert not re.search(r'create_table\(\s*["\']risk_governance', migration)

    foreign_models = {
        "ProjectRisk", "RiskReadinessAssessment", "ProjectFELStatus", "ProjectDefinitionAssessment",
        "BusinessCaseVersion", "InvestmentGatePreparation", "InvestmentDecision",
        "StrategicCapitalAllocationPlan", "PortfolioReviewSession", "PortfolioReviewSnapshot",
    }
    for domain in ("risk_governance", "basic_data"):
        source = read(f"backend/app/modules/{domain}/service.py")
        for primitive in ("AdminConfiguration", "SecurityEvent", "ETAG_MISMATCH"):
            require(source, primitive)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else ""
            assert name not in {"eval", "exec", "compile"}, "No executable policy expressions"
            assert name not in foreign_models, f"No foreign authority record creation: {name}"
        for excluded in (".start_fel(", ".complete_stage(", ".create_risk(", ".decide(", ".monte_carlo("):
            assert excluded not in source, f"Cross-domain command is outside Wave 2B: {excluded}"

    registry = read("backend/app/modules/investment_evidence_policy/service.py")
    require(registry, '"BASIC_DATA_READINESS_PROVIDER": _provider(')
    require(registry, '"BASIC_DATA_READINESS"')
    # Registering an adapter is separate from making it a Gate requirement.
    policy = registry[registry.index("def _requirement"):registry.index("class InvestmentEvidencePolicyService")]
    assert 'provider_key="BASIC_DATA_READINESS_PROVIDER"' not in policy

    legacy = read("backend/app/api/v1/routers/admin_configuration.py")
    for kind in ("risk_governance_policy", "basic_data_readiness_configuration"):
        require(legacy, f'"{kind}"')
    require(legacy, '"GOVERNED_CONFIGURATION_API_REQUIRED"')
    legacy_functions = {
        node.name: node for node in ast.parse(legacy).body if isinstance(node, ast.FunctionDef)
    }
    for command in ("update_configuration", "publish_configuration", "clone_configuration", "_normalized_kind"):
        assert any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_require_legacy_mutation_allowed"
            for node in ast.walk(legacy_functions[command])
        ), f"Legacy {command} must preserve dedicated policy authority"

    blueprint = read("frontend/src/features/enterprise-strategy/navigation/strategicNavigationBlueprint.ts")
    outlet = read("frontend/src/features/enterprise-strategy/StrategicViewOutlet.tsx")
    app = read("frontend/src/App.tsx")
    for view in ("risk-governance-configuration", "basic-data-readiness", "basic-data-configuration"):
        require(blueprint, view)
        require(outlet, view)
        assert view not in app
    assert "BasicData" not in app and "RiskGovernance" not in app

    report = read("docs/77-wave2b-risk-governance-basic-data-release.md")
    sections = [int(value) for value in re.findall(r"^## (\d+)\. ", report, re.MULTILINE)]
    assert sections == list(range(1, 85)), "Report must include all 84 required sections"
    require(read(".github/workflows/ci.yml"), "wave2b-risk-basic-data-postgres:")
    require(read(".github/workflows/ci.yml"), "wave2b-risk-basic-data.spec.ts")
    require(read("docker-compose.wave2b.yml"), "wave2b_migration")
    print("WAVE2B_RELEASE_GUARDRAILS=PASS")


if __name__ == "__main__":
    main()
