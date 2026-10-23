"""Bootstrap a disposable pre-O1A DB then apply additive governed migrations."""

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
    assert os.getenv("PYPMIS_O1BB1_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database in {"o1bb1", "o1bb1_browser", "o1bb1_migration"}
    assert not set(inspect(engine).get_table_names()) - {"alembic_version"}, "Requires a fresh isolated B1 DB"
    governed = {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith(
            (
                "app.modules.scope_foundation",
                "app.modules.schedule_foundation",
                "app.modules.awp",
                "app.modules.cost_foundation",
            )
        )
    }
    o1a = {"operational_project_bindings", "project_controls_periods", "operational_context_commands"}
    Base.metadata.create_all(
        engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in o1a | governed]
    )
    config = Config("alembic.ini")
    command.stamp(config, "20261011_0068")
    for revision in ("20261019_0069", "20261020_0070", "20261021_0071"):
        command.upgrade(config, revision)
    if not args.baseline_only:
        command.upgrade(config, "head")
    print("Disposable ORM baseline through 0068 then real additive migrations. Not empty-to-head proof.")


if __name__ == "__main__":
    main()
