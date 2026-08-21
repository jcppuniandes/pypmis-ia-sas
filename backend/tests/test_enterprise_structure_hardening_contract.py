import os
from pathlib import Path

import pytest

from app.modules.enterprise_structure.models import EnterpriseCoreRelease
from app.modules.enterprise_structure.permissions import REVISION_DUTY_ROLES, STRUCTURE_ROLE_PERMISSIONS


def test_revision_uses_optimistic_versioning_and_actor_traceability() -> None:
    mapper = EnterpriseCoreRelease.__mapper__
    assert mapper.version_id_col is EnterpriseCoreRelease.__table__.c.revision_version
    assert EnterpriseCoreRelease.__table__.c.revision_version.nullable is False
    assert EnterpriseCoreRelease.__table__.c.last_modified_by_user_id.foreign_keys


def test_structure_roles_enforce_the_gate04h_sod_matrix() -> None:
    assert STRUCTURE_ROLE_PERMISSIONS == {
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
    assert REVISION_DUTY_ROLES["admin.enterprise_structure.revision.edit"] == frozenset({"structure_editor"})
    assert REVISION_DUTY_ROLES["admin.enterprise_structure.revision.approve"] == frozenset({"structure_approver"})
    assert REVISION_DUTY_ROLES["admin.enterprise_structure.publish"] == frozenset({"structure_publisher"})


def test_http_ci_and_benchmark_contracts_are_declared() -> None:
    packaged_backend = Path(__file__).resolve().parents[1]
    repository = Path(os.environ.get("PYPMIS_REPOSITORY_ROOT", packaged_backend.parent))
    backend = repository / "backend" if (repository / "backend").is_dir() else packaged_backend
    router = (backend / "app/modules/enterprise_structure/router_admin.py").read_text(encoding="utf-8")
    revision_service = (backend / "app/modules/enterprise_structure/revisions.py").read_text(encoding="utf-8")
    benchmark = (backend / "tests/postgres/snapshot_benchmark.py").read_text(encoding="utf-8")

    assert 'alias="If-Match"' in router
    assert "REVISION_VERSION_CONFLICT" in revision_service
    assert "APPROVAL_INVALIDATED" in revision_service
    assert "FOUR_EYES_VIOLATION" in revision_service
    assert "(100, 1_000, 10_000)" in benchmark

    source_contracts = (
        repository / ".github/workflows/ci.yml",
        repository / "docker-compose.gate04h.yml",
        backend / "Dockerfile",
    )
    if not all(path.is_file() for path in source_contracts):
        pytest.skip("Repository-only CI, Compose and Dockerfile contracts are not packaged in the runtime image")

    workflow = (repository / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    compose = (repository / "docker-compose.gate04h.yml").read_text(encoding="utf-8")
    dockerfile = (backend / "Dockerfile").read_text(encoding="utf-8")

    assert "enterprise-structure-postgres-e2e" in workflow
    assert "install -d -m 0777 artifacts/enterprise_structure/gate04h" in workflow
    assert "pip install ruff==0.16.3" in workflow
    assert "tmpfs:" in compose
    assert "sqlite" not in compose.lower()
    assert "prepare_ephemeral_schema.py" in compose
    assert "alembic stamp 20260810_0032" in compose
    assert "alembic upgrade head" in compose
    assert "COPY pyproject.toml ./" in dockerfile
