"""Refresh an iterated 0077 function only on the named local O2B fixtures.

Fresh deployment uses Alembic; the migration-only fixture proves its DDL from
0076. This command preserves already-created synthetic validation records.
"""

import argparse
import importlib
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend/alembic/versions"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", choices=("http", "browser"))
    args = parser.parse_args()
    if os.environ.get("PYPMIS_O2B_FIXTURE") != "disposable-only":
        parser.error("Requires explicit disposable-only acknowledgement")
    database, port = {"http": ("o2b", 5555), "browser": ("o2b_browser", 5557)}[
        args.fixture
    ]
    migration = importlib.import_module("20261111_0077_procurement_foundation")
    with psycopg.connect(
        host="127.0.0.1",
        port=port,
        user="o2b",
        password="disposable-o2b",
        dbname=database,
    ) as connection:
        assert connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone() == (database, "o2b")
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchall() == [(migration.revision,)]
        assert connection.execute(
            "SELECT to_regprocedure('o2b_procurement_record_guard()')"
        ).fetchone()[0]
        guard, separator, _ = migration.GUARD.partition(
            "CREATE FUNCTION o2b_procurement_profile_guard"
        )
        assert separator and guard.count("CREATE FUNCTION") == 1
        connection.execute(
            guard.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        )
    print(f"Refreshed local {database} guard from {migration.revision}")


if __name__ == "__main__":
    main()
