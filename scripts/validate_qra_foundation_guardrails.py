"""Static scope checks supplement, never replace, PostgreSQL and browser proof."""

import ast
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    old = ROOT / "backend/alembic/versions/20261008_0066_owner_capability_readiness.py"
    if not old.exists():
        old = next((ROOT / "backend/alembic/versions").glob("*0066*"))
    assert hashlib.sha256(old.read_bytes()).hexdigest().upper() == "6D59E013EA9B44CBEFAE21AC464EBF5BFFC47680B96CFF355016DB43C71CB5E4"
    migration = read("backend/alembic/versions/20261009_0067_qra_foundation.py")
    assert 'down_revision: str | None = "20261008_0066"' in migration
    upgrade = migration.split("def downgrade", 1)[0]
    assert not re.search(r"op\.(?:drop_table|drop_column|alter_column|rename_table)", upgrade)
    for name in ("qra_cost_source_assessments", "qra_schedule_source_assessments", "qra_model_definitions", "qra_commands"):
        assert name in migration
    assert 'op.add_column("schedule_imports"' in migration and '"source_metadata"' in migration
    assert "model_number" in migration
    service = read("backend/app/modules/qra_foundation/service.py")
    policy = read("backend/app/modules/qra_foundation/policy.py")
    foreign = {"ProjectRisk", "RiskReadinessAssessment", "ProjectFELStatus", "ProjectDefinitionAssessment",
               "InvestmentGatePreparation", "InvestmentDecision", "PortfolioBudgetScenario", "QraRun"}
    for node in ast.walk(ast.parse(service + "\n" + policy)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in foreign | {"eval", "exec", "compile"}
    for forbidden in ("numpy.random", "random.random", ".simulate(", ".monte_carlo(", ".start_fel(", ".decide("):
        assert forbidden not in service + policy
    registry = read("backend/app/modules/investment_evidence_policy/service.py")
    for key in ("COST_SOURCE_READINESS_PROVIDER", "SCHEDULE_SOURCE_READINESS_PROVIDER"):
        assert f'"{key}": _provider(' in registry
        gate_defaults = registry[registry.index("def _requirement"):registry.index("class InvestmentEvidencePolicyService")]
        assert f'provider_key="{key}"' not in gate_defaults
    assert "QRA_FOUNDATION_READINESS_PROVIDER" not in registry
    app = read("frontend/src/App.tsx")
    for view in ("qra-foundation", "qra-methodology-source-readiness"):
        assert view in read("frontend/src/features/enterprise-strategy/navigation/strategicNavigationBlueprint.ts")
        assert view in read("frontend/src/features/enterprise-strategy/StrategicViewOutlet.tsx")
        assert view not in app
    report = read("docs/81-qra-foundation-release.md")
    assert [int(v) for v in re.findall(r"^## (\d+)\. ", report, re.MULTILINE)] == list(range(1, 72))
    ci = read(".github/workflows/ci.yml")
    assert "qra-foundation-postgres:" in ci and "qra-foundation.spec.ts" in ci
    print("QRA_FOUNDATION_GUARDRAILS=PASS")


if __name__ == "__main__":
    main()
