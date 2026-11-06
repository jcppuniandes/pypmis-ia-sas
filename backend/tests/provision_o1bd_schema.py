"""Owned disposable baseline then real additive migrations through Progress."""

import argparse
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

import app.main  # noqa: F401
from app.database.session import Base, engine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-only", action="store_true")
    args = parser.parse_args()
    assert os.getenv("PYPMIS_O1BD_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql"
    assert engine.url.database in {"o1bd", "o1bd_browser", "o1bd_migration"}
    assert not set(inspect(engine).get_table_names()) - {"alembic_version"}, "Fresh isolated DB required"
    governed = {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith(
            (
                "app.modules.scope_foundation",
                "app.modules.schedule_foundation",
                "app.modules.awp",
                "app.modules.cost_foundation",
                "app.modules.progress_foundation",
            )
        )
    }
    o1a = {"operational_project_bindings", "project_controls_periods", "operational_context_commands"}
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in o1a | governed])
    configuration = Config("alembic.ini")
    command.stamp(configuration, "20261011_0068")
    command.upgrade(configuration, "20261022_0073" if args.baseline_only else "head")
    print("Owned ORM baseline0068 then real additive migrations; not empty-to-head proof.")


if __name__ == "__main__":
    main()
