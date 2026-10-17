"""Shared pytest configuration for API tests.

The API smoke tests exercise seeded demo workflows. Keep that seed isolated from
the developer/runtime database so local project cleanup does not break tests.
"""

import os
import tempfile
from pathlib import Path

import pytest
from tests.sqlite_isolation import owned_database_path, reset_owned_sqlite_database

from app.core.config import get_settings

runtime_dir = Path(
    os.getenv(
        "PYPMIS_PYTEST_RUNTIME_DIR",
        Path(__file__).resolve().parents[1] / ".pytest_tmp" / f"run-{os.getpid()}",
    )
)
runtime_dir.mkdir(parents=True, exist_ok=True)
document_storage_dir = runtime_dir / "document-storage"
document_storage_dir.mkdir(parents=True, exist_ok=True)

# Keep pytest's own temporary trees inside the repository. This prevents stale
# Windows ACLs in the system TEMP directory from contaminating unrelated runs.
for variable in ("TMP", "TEMP", "TMPDIR"):
    os.environ[variable] = str(runtime_dir)
tempfile.tempdir = str(runtime_dir)

postgres_test_url = os.getenv("PYPMIS_TEST_DATABASE_URL", "").strip()
if postgres_test_url:
    os.environ["DATABASE_URL"] = postgres_test_url
else:
    test_db_path = owned_database_path(
        Path(os.getenv("PYPMIS_TEST_DB_PATH", runtime_dir / f"pypmis_pytest-{os.getpid()}.sqlite")), runtime_dir
    )
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path.as_posix()}"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["DOCUMENT_STORAGE_PATH"] = str(document_storage_dir)
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
get_settings.cache_clear()


@pytest.fixture(scope="module", autouse=True)
def _isolated_module_application_database():
    """Keep module workflows intact, but never inherit another module's seed.

    Explicit database URLs belong to dedicated PostgreSQL/migration profiles and
    are never reset here. Their fixtures must own their schema or tenant. The
    ordinary SQLite URL is created by this conftest and verified before unlink.
    Reusing the existing engine object preserves every imported SessionLocal.
    """
    if postgres_test_url:
        yield
        return

    from app.database.session import engine

    reset_owned_sqlite_database(engine, test_db_path, runtime_dir)
    yield
    engine.dispose()
