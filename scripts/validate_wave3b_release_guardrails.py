"""Static Wave 3B boundaries supplement behavioral PostgreSQL/browser evidence."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(source: str, needle: str) -> None:
    assert needle in source, f"Missing Wave 3B architectural contract: {needle}"


def main() -> None:
    migrations = sorted((ROOT / "backend/alembic/versions").glob("*0066*owner*capability*.py"))
    assert len(migrations) == 1, "Exactly one actual additive successor is required"
    migration = migrations[0].read_text(encoding="utf-8")
    require(migration, "20261008_0065")
    require(migration, "20261008_0066")
    upgrade = migration.split("def downgrade", maxsplit=1)[0]
    assert not re.search(r"op\.(?:drop_table|drop_column|alter_column|rename_table)", upgrade)
    for table in ("owner_capability_assessments", "owner_capability_commands"):
        require(migration, table)

    source = read("backend/app/modules/owner_capability/service.py")
    for primitive in ("AdminConfiguration", "SecurityEvent", "BasicDataService"):
        require(source, primitive)
    require(read("backend/app/modules/basic_data/service.py"), "ETAG_MISMATCH")
    foreign_models = {
        "ProjectRisk", "RiskReadinessAssessment", "ProjectFELStatus", "ProjectDefinitionAssessment",
        "ProjectBasicDataItem", "BasicDataReadinessAssessment", "BusinessCaseVersion", "BusinessCaseRevision",
        "InvestmentGatePreparation", "InvestmentDecision", "PortfolioResourceScenario",
        "CommercialStrategyRevision", "CommercialStrategyVersion", "PortfolioReviewSession",
    }
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else ""
        assert name not in {"eval", "exec", "compile"}, "No executable policy expressions"
        assert name not in foreign_models, f"No foreign authority record creation: {name}"
    for excluded in (".start_fel(", ".create_risk(", ".freeze_scenario(", ".decide(", ".monte_carlo("):
        assert excluded not in source, f"Command outside Wave 3B authority: {excluded}"

    registry = read("backend/app/modules/investment_evidence_policy/service.py")
    require(registry, '"OWNER_CAPABILITY_READINESS_PROVIDER": _provider(')
    require(registry, '"OWNER_CAPABILITY_READINESS"')
    policy = registry[registry.index("def _requirement"):registry.index("class InvestmentEvidencePolicyService")]
    assert 'provider_key="OWNER_CAPABILITY_READINESS_PROVIDER"' not in policy
    legacy = read("backend/app/api/v1/routers/admin_configuration.py")
    require(legacy, '"owner_capability_readiness_configuration"')
    require(legacy, '"GOVERNED_CONFIGURATION_API_REQUIRED"')

    blueprint = read("frontend/src/features/enterprise-strategy/navigation/strategicNavigationBlueprint.ts")
    outlet = read("frontend/src/features/enterprise-strategy/StrategicViewOutlet.tsx")
    app = read("frontend/src/App.tsx")
    for view in ("owner-capability-readiness", "owner-capability-configuration"):
        require(blueprint, view)
        require(outlet, view)
        assert view not in app
    assert "OwnerCapability" not in app
    ci = read(".github/workflows/ci.yml")
    require(ci, "wave3b-owner-capability-postgres:")
    require(ci, "owner-capability.spec.ts")
    require(read("docker-compose.wave3b.yml"), "wave3b_migration")
    report_files = list((ROOT / "docs").glob("*wave3b*release*.md"))
    assert len(report_files) == 1, "Require one complete Wave 3B technical source report"
    report = report_files[0].read_text(encoding="utf-8")
    sections = [int(value) for value in re.findall(r"^## (\d+)\. ", report, re.MULTILINE)]
    assert sections == list(range(1, 85)), "Report must include all 84 required sections"
    print("WAVE3B_RELEASE_GUARDRAILS=PASS")


if __name__ == "__main__":
    main()
