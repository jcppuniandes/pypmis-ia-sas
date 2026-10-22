"""Refresh only B1 trigger function in explicitly isolated validation databases.

Development repair before release: no business rows, triggers, schema revision or
historical migration is rewritten. Normal application databases are rejected.
"""

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import text

from app.database.session import engine


def main():
    if (
        os.environ.get("PYPMIS_O1BB1_FIXTURE") != "disposable-only"
        or engine.dialect.name != "postgresql"
        or engine.url.database not in {"o1bb1", "o1bb1_browser", "o1bb1_migration"}
    ):
        raise RuntimeError("Only explicit isolated B1 validation databases may refresh development guards")
    path = Path(__file__).resolve().parents[1] / "alembic/versions/20261021_0072_awp_readiness.py"
    specification = importlib.util.spec_from_file_location("b1_guard_migration", path)
    migration = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(migration)
    statements = []
    migration.op = SimpleNamespace(execute=statements.append)
    migration._postgres_guards()
    functions = [
        statement for statement in statements if statement.strip().startswith("CREATE FUNCTION awp_b1_guard()")
    ]
    assert len(functions) == 1
    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261021_0072"
        connection.execute(
            text(functions[0].replace("CREATE FUNCTION awp_b1_guard()", "CREATE OR REPLACE FUNCTION awp_b1_guard()", 1))
        )
    print(f"Refreshed awp_b1_guard only in isolated {engine.url.database}; business_rows_written=0")


if __name__ == "__main__":
    main()
