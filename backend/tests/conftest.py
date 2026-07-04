"""Shared pytest configuration for API tests.

The API smoke tests exercise seeded demo workflows. Keep that seed isolated from
the developer/runtime database so local project cleanup does not break tests.
"""

import os
from pathlib import Path
from tempfile import gettempdir

from app.core.config import get_settings


test_db_path = Path(os.getenv("PYPMIS_TEST_DB_PATH", Path(gettempdir()) / "pypmis_pytest.sqlite"))
if test_db_path.exists():
    test_db_path.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path.as_posix()}"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
get_settings.cache_clear()
