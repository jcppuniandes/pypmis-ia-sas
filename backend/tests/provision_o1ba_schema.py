"""Isolated pre-O1A ORM bootstrap plus real 0069/O1B-A additive migrations."""

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
    parser.add_argument("--database", choices=("o1ba", "o1ba_regression"), default="o1ba")
    args = parser.parse_args()
    assert os.getenv("PYPMIS_O1BA_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database == args.database
    assert not set(inspect(engine).get_table_names()) - {"alembic_version"}, "Requires fresh isolated O1B-A DB"
    scope_tables = {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith("app.modules.scope_foundation")
    }
    Base.metadata.create_all(
        engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in O1A_TABLES | scope_tables]
    )
    config = Config("alembic.ini")
    command.stamp(config, "20261011_0068")
    command.upgrade(config, "20261019_0069")
    if not args.baseline_only:
        command.upgrade(config, "head")
    print("Isolated pre-O1A ORM baseline + actual additive Alembic migrations; not empty-to-head proof")


if __name__ == "__main__":
    main()
