"""Schema-only bootstrap for explicitly disposable fresh strategic UAT.

The repository predates complete baseline Alembic creation. Reuse its existing
schema-baseline compatibility bootstrap (metadata through 0067, then real 0068).
No business fixtures, demo Projects, READY evidence or decisions are created.
"""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.database.session import Base, engine
from app.main import app  # noqa: F401 -- registers every actual model


def assert_disposable():
    if (
        os.environ.get("PYPMIS_STRATEGIC_FRESH_UAT") != "disposable-only"
        or engine.dialect.name != "postgresql"
        or engine.url.database != "strategic_fresh_uat"
    ):
        raise RuntimeError("Only explicitly disposable strategic_fresh_uat PostgreSQL is permitted")


def main():
    assert_disposable()
    with engine.connect() as connection:
        current = (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            if inspect(connection).has_table("alembic_version")
            else None
        )
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    later_tables = {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith(
            (
                "app.modules.operational_context",
                "app.modules.scope_foundation",
                "app.modules.schedule_foundation",
                "app.modules.awp",
            )
        )
    }
    if current is None:
        Base.metadata.create_all(
            engine,
            tables=[
                table
                for table in Base.metadata.sorted_tables
                if table.name not in {"qra_runs", "qra_run_reviews"} | later_tables
            ],
        )
        command.stamp(cfg, "20261009_0067")
    # This historic strategic fixture explicitly proves the 0068 boundary,
    # not whichever operational successor happens to be the current head.
    command.upgrade(cfg, "20261011_0068")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261011_0068"
    print("Disposable schema ready at 20261011_0068; no strategic business fixture seeded", flush=True)


if __name__ == "__main__":
    main()
