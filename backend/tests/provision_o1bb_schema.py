"""Disposable pre-O1A bootstrap followed by real O1A/Scope/Schedule migrations."""

import argparse
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

import app.main  # noqa: F401
from app.database.session import Base, engine

O1A_TABLES = {"operational_project_bindings", "project_controls_periods", "operational_context_commands"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--database", choices=("o1bb", "o1bb_regression"), default="o1bb")
    args = parser.parse_args()
    assert os.getenv("PYPMIS_O1BB_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database == args.database
    assert not set(inspect(engine).get_table_names()) - {"alembic_version"}, (
        "Requires a fresh isolated Schedule database"
    )
    governed = {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith(
            ("app.modules.scope_foundation", "app.modules.schedule_foundation", "app.modules.awp")
        )
    }
    Base.metadata.create_all(
        engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in O1A_TABLES | governed]
    )
    config = Config("alembic.ini")
    command.stamp(config, "20261011_0068")
    command.upgrade(config, "20261019_0069")
    command.upgrade(config, "20261020_0070")
    if not args.baseline_only:
        command.upgrade(config, "head")
    print("Disposable ORM baseline then actual additive migrations; not an empty-to-head claim")


if __name__ == "__main__":
    main()
