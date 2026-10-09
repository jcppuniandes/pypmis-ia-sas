"""Prepare the historical pre-Gate-04H baseline on disposable PostgreSQL.

The repository's Alembic history starts after the original application schema
was already managed by SQLAlchemy metadata.  A brand-new database therefore
needs that historical baseline before Alembic can exercise the Gate 04H
migration.  This helper is deliberately guarded and must never run against a
persistent database.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, inspect, text

from app.database.session import Base
from app.domain import models as domain_models  # noqa: F401
from app.modules.enterprise_structure import models as enterprise_structure_models  # noqa: F401

DATABASE_URL = os.environ["GATE04H_DATABASE_URL"]


def main() -> None:
    if os.getenv("GATE04H_EPHEMERAL") != "true" or not DATABASE_URL.startswith("postgresql+"):
        raise RuntimeError("Ephemeral schema preparation requires disposable PostgreSQL")

    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    try:
        existing_tables = inspect(engine).get_table_names()
        if existing_tables:
            raise RuntimeError(f"Gate 04H bootstrap refuses a non-empty database: {sorted(existing_tables)!r}")

        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                text("DROP TRIGGER IF EXISTS trg_protect_enterprise_core_release ON enterprise_core_releases")
            )
            connection.execute(text("DROP FUNCTION IF EXISTS protect_enterprise_core_release()"))
            connection.execute(text("ALTER TABLE enterprise_core_releases DROP COLUMN last_modified_by_user_id"))
            connection.execute(text("ALTER TABLE enterprise_core_releases DROP COLUMN revision_version"))

        columns = {column["name"] for column in inspect(engine).get_columns("enterprise_core_releases")}
        if {"last_modified_by_user_id", "revision_version"} & columns:
            raise RuntimeError("Failed to prepare the pre-Gate-04H schema")
        print("EPHEMERAL_SCHEMA_READY_AT=20260810_0032")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
