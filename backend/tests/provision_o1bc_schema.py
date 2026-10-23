"""Real additive 0069 through 0073 on explicitly disposable O1B-C databases."""

import argparse
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

import app.main  # noqa: F401
from app.database.session import Base, engine
from app.modules.cost_foundation import financial_models, models  # noqa: F401


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-only", action="store_true")
    args = parser.parse_args()
    assert os.getenv("PYPMIS_O1BC_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql"
    assert engine.url.database in {"o1bc", "o1bc_browser", "o1bc_migration"}
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
            )
        )
    }
    o1a = {"operational_project_bindings", "project_controls_periods", "operational_context_commands"}
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in o1a | governed])
    config = Config("alembic.ini")
    command.stamp(config, "20261011_0068")
    command.upgrade(config, "20261021_0072" if args.baseline_only else "head")
    print("Disposable ORM baseline through 0068 then real additive migrations. Not empty-to-head proof.")


if __name__ == "__main__":
    main()
