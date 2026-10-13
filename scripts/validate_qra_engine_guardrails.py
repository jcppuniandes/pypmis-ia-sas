"""Wave4 static boundaries supplement actual PostgreSQL/Chromium acceptance.

These checks deliberately do not claim runtime authorization, SQL-write or
numerical correctness: the acceptance suites must establish those properties.
"""

import ast
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOUNDATION_SHA256 = "3fa35be0ad72a4c36a60bed73f7a296a1a0eaa519cb560a151b0cd2e71da5f78"
GATE_DEFAULTS_AST_SHA256 = (
    "63924f8a42c2bf6a4d432fe9218808fedbd8743407f666c0954a681b281afcb2"
)
OWNED_TABLES = {"qra_runs", "qra_run_reviews"}


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def tree(path):
    return ast.parse(read(path))


def named_functions(module, names):
    return [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]


def migration_boundary():
    # Text decoding normalizes checkout line endings on Linux and Windows.
    assert (
        digest(read("backend/alembic/versions/20261009_0067_qra_foundation.py"))
        == FOUNDATION_SHA256
    )
    migration = tree("backend/alembic/versions/20261011_0068_qra_calculation_engine.py")
    revision = {
        node.target.id: ast.literal_eval(node.value)
        for node in migration.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert (
        revision["revision"] == "20261011_0068"
        and revision["down_revision"] == "20261009_0067"
    )
    upgrade = named_functions(migration, {"upgrade"})[0]
    created = set()
    for node in ast.walk(upgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "op"
        ):
            assert node.func.attr in {"create_table", "create_index"}, (
                "0068 upgrade must be additive"
            )
            if node.func.attr == "create_table":
                created.add(ast.literal_eval(node.args[0]))
            elif node.func.attr == "create_index":
                assert ast.literal_eval(node.args[1]) in OWNED_TABLES
    assert created == OWNED_TABLES
    # Trigger DDL is in a separate helper; no source-row data mutation is allowed.
    assert not re.search(
        r"\b(?:INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b",
        read("backend/alembic/versions/20261011_0068_qra_calculation_engine.py"),
        re.IGNORECASE,
    )
    downgrade = named_functions(migration, {"downgrade"})[0]
    dropped = {
        ast.literal_eval(node.args[0])
        for node in ast.walk(downgrade)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "drop_table"
    }
    assert dropped == OWNED_TABLES


def execution_boundary():
    service = tree("backend/app/modules/qra_engine/service.py")
    read_only_models = set()
    for node in ast.walk(service):
        if isinstance(node, ast.ImportFrom) and node.module in {
            "app.domain.models",
            "app.modules.qra_foundation.models",
        }:
            read_only_models.update(alias.asname or alias.name for alias in node.names)
    # Numbering and denial audit are the only shared constructor authorities.
    read_only_models -= {"AdminNumberSequence", "SecurityEvent"}
    for node in ast.walk(service):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            assert node.func.id not in read_only_models | {
                "eval",
                "exec",
                "compile",
                "text",
            }
            if node.func.id in {"update", "insert", "delete"}:
                assert isinstance(node.args[0], ast.Name) and node.args[0].id in {
                    "QraRun",
                    "QraRunReview",
                }
        elif isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {
                "delete",
                "bulk_insert_mappings",
                "bulk_update_mappings",
                "bulk_save_objects",
            }
    # The numerical kernel has no ORM, application, subprocess, file/network IO.
    kernel = tree("backend/app/modules/qra_engine/calculation.py")
    allowed_roots = {
        "__future__",
        "heapq",
        "math",
        "collections",
        "datetime",
        "numpy",
        "scipy",
    }
    for node in ast.walk(kernel):
        if isinstance(node, ast.Import):
            assert all(
                alias.name.split(".")[0] in allowed_roots for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            assert node.module and node.module.split(".")[0] in allowed_roots
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "eval", "exec", "compile", "__import__"}


def provider_boundary():
    registry = tree("backend/app/modules/investment_evidence_policy/service.py")
    default_functions = named_functions(
        registry,
        {"_matrix", "gate07m_evid_policy_update", "gate07j_evid2_policy_update"},
    )
    serialized = "\n".join(
        ast.dump(node, include_attributes=False) for node in default_functions
    )
    assert digest(serialized) == GATE_DEFAULTS_AST_SHA256, (
        "Published Gate defaults must not change for Wave4"
    )
    registrations = [
        node.value
        for node in registry.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "PROVIDER_REGISTRY"
    ]
    assert len(registrations) == 1
    entries = {
        ast.literal_eval(key): value
        for key, value in zip(
            registrations[0].keys, registrations[0].values, strict=True
        )
    }
    provider = entries["QRA_RESULT_PROVIDER"]
    assert (
        isinstance(provider, ast.Call)
        and isinstance(provider.func, ast.Name)
        and provider.func.id == "_provider"
    )
    assert ast.literal_eval(provider.args[3]) == "QraResultEvidence.v1"


def navigation_and_isolation():
    app = read("frontend/src/App.tsx")
    blueprint = read(
        "frontend/src/features/enterprise-strategy/navigation/strategicNavigationBlueprint.ts"
    )
    outlet = read("frontend/src/features/enterprise-strategy/StrategicViewOutlet.tsx")
    for view in (
        "qra-approved-models",
        "qra-runs",
        "qra-cost-results",
        "qra-schedule-results",
        "qra-run-evidence",
    ):
        assert view in blueprint and view in outlet and view not in app
    assert "QraEngineWorkspace" not in app
    compose = read("docker-compose.qra-engine.yml")
    assert "tmpfs: [/var/lib/postgresql/data]" in compose
    assert compose.count("tmpfs: [/var/lib/postgresql/data]") == 3
    assert (
        "PYPMIS_TEST_DATABASE_URL:" in compose
        and "PYPMIS_QRA_ENGINE_MIGRATION_DATABASE_URL:" in compose
    )
    for name in ("qra-validation", "qra-browser-api", "qra-browser-worker"):
        block = re.search(
            rf"^  {name}:\n(.*?)(?=^  [\w-]+:|\Z)", compose, re.MULTILINE | re.DOTALL
        )
        assert block and "./backend:/app:ro" in block.group(1)
    assert "./frontend:/app:ro" in compose
    assert "127.0.0.1:8820:8000" in compose and "127.0.0.1:5523:5173" in compose
    assert "PYPMIS_QRA_ENGINE_BROWSER_FIXTURE: disposable-only" in compose
    assert "pypmis-qra-engine-qra-validation:latest" in compose
    ci = read(".github/workflows/ci.yml")
    for job in (
        "qra-foundation-postgres:",
        "qra-foundation-browser:",
        "qra-engine-postgres:",
        "qra-engine-browser:",
    ):
        assert job in ci
    assert "qra-engine.spec.ts" in ci and "qra-foundation.spec.ts" in ci
    assert "ruff format --check backend/app/ backend/tests/" in ci
    assert "ruff check backend/app/ backend/tests/" in ci


def main():
    migration_boundary()
    execution_boundary()
    provider_boundary()
    navigation_and_isolation()
    print(
        "QRA_ENGINE_GUARDRAILS=PASS (static supplement; PostgreSQL and Chromium acceptance still required)"
    )


if __name__ == "__main__":
    main()
