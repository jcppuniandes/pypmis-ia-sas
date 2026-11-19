"""Print the PostgreSQL DDL for the pre-Alembic application bootstrap.

The commit below originally initialized exactly this metadata at app startup.
This is an offline provenance/reproduction tool. It never connects to a DB.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType

from sqlalchemy import create_mock_engine
from sqlalchemy.orm import DeclarativeBase

COMMIT = "dd5b5149efc1b876e72b5f1a2ce390378bc44b81"
MODELS = "backend/app/domain/models.py"
ROOT = Path(__file__).resolve().parents[2]


def main():
    source = subprocess.check_output(["git", "show", f"{COMMIT}:{MODELS}"], cwd=ROOT)
    session = ModuleType("app.database.session")
    session.Base = type(
        "HistoricalBase", (DeclarativeBase,), {"__module__": session.__name__}
    )
    sys.modules[session.__name__] = session
    models = ModuleType("pypmis_pre_alembic_models")
    sys.modules[models.__name__] = models
    exec(compile(source, f"{COMMIT}:{MODELS}", "exec"), models.__dict__)  # noqa: S102 - fixed historical Git object

    ddl = []

    def collect(statement, *_args, **_kwargs):
        compiled = str(statement.compile(dialect=engine.dialect)).strip()
        ddl.append("\n".join(line.rstrip() for line in compiled.splitlines()) + ";")

    engine = create_mock_engine("postgresql://", collect)
    session.Base.metadata.create_all(engine, checkfirst=False)
    # Metadata index/constraint sets have no contractual iteration order.
    deferred = ("ALTER TABLE ", "CREATE INDEX ", "CREATE UNIQUE INDEX ")
    creation = [statement for statement in ddl if not statement.startswith(deferred)]
    finishing = sorted(statement for statement in ddl if statement.startswith(deferred))
    print(f"-- Original pre-Alembic PostgreSQL schema: {COMMIT}")
    print(f"-- Origin: {MODELS}; application startup used Base.metadata.create_all.")
    print(
        "-- Offline compiler: scripts/wave-o2b-close/generate_historical_bootstrap.py"
    )
    print("-- Test fixture only; never apply to an existing or production database.")
    print("\n\n".join(creation + finishing))


if __name__ == "__main__":
    main()
