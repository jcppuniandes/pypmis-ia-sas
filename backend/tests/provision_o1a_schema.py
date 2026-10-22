"""Isolated pre-O1A ORM baseline, followed by a real additive Alembic upgrade.

The historical chain starts after the initial ORM schema. Never claims an empty
database-to-current migration proof. No production database is accepted.
"""

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

import app.main  # noqa: F401
from app.database.session import Base, engine

NEW_TABLES = {"operational_project_bindings", "project_controls_periods", "operational_context_commands"}


def main():
    assert os.getenv("PYPMIS_O1A_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database == "o1a"
    assert not set(inspect(engine).get_table_names()) - {"alembic_version"}, "Requires fresh isolated O1A database"
    later_tables = {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith(
            ("app.modules.scope_foundation", "app.modules.schedule_foundation", "app.modules.awp")
        )
    }
    Base.metadata.create_all(
        engine,
        tables=[table for table in Base.metadata.sorted_tables if table.name not in NEW_TABLES | later_tables],
    )
    configuration = Config("alembic.ini")
    command.stamp(configuration, "20261011_0068")
    command.upgrade(configuration, "20261019_0069")
    assert NEW_TABLES <= set(inspect(engine).get_table_names())
    assert not later_tables & set(inspect(engine).get_table_names())
    print("Pre-O1A ORM baseline + actual 0068 -> 0069 migration initialized in isolated o1a")


if __name__ == "__main__":
    main()
