"""Actual additive 0072 up/down/re-up on a separately named disposable PostgreSQL."""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_awp_additive_upgrade_downgrade_reupgrade_preserves_schedule_structure():
    url = os.getenv("PYPMIS_O1BB1_MIGRATION_DATABASE_URL")
    if not url:
        pytest.skip("Requires isolated B1 migration PostgreSQL")
    isolated = create_engine(url)
    assert isolated.dialect.name == "postgresql" and isolated.url.database == "o1bb1_migration"
    before_tables = set(inspect(isolated).get_table_names())
    with isolated.connect() as connection:
        assert connection.scalar(text("select version_num from alembic_version")) == "20261021_0071"
        assert connection.scalar(text("select count(*) from enterprise_workspaces where id=14")) == 0
    protected = {
        name: [(column["name"], str(column["type"])) for column in inspect(isolated).get_columns(name)]
        for name in before_tables
        if name.startswith(("scope_", "schedule_", "operational_"))
    }
    previous = os.environ["DATABASE_URL"]
    config = Config("alembic.ini")
    try:
        os.environ["DATABASE_URL"] = url
        from app.core.config import get_settings

        get_settings.cache_clear()
        command.upgrade(config, "20261021_0072")
        new = set(inspect(isolated).get_table_names()) - before_tables
        assert new == {
            "awp_cwas",
            "awp_work_packages",
            "awp_package_mappings",
            "awp_package_dependencies",
            "awp_execution_constraints",
            "awp_constraint_mappings",
            "awp_readiness_assessments",
            "awp_history",
        }
        with isolated.connect() as connection:
            triggers = connection.scalars(
                text("select tgname from pg_trigger where not tgisinternal and tgname like 'tr_awp_%'")
            )
            assert len(list(triggers)) >= 8
        for name, columns in protected.items():
            assert [(column["name"], str(column["type"])) for column in inspect(isolated).get_columns(name)] == columns
        command.downgrade(config, "20261021_0071")
        assert set(inspect(isolated).get_table_names()) == before_tables
        command.upgrade(config, "20261021_0072")
        assert set(inspect(isolated).get_table_names()) == before_tables | new
    finally:
        os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
        isolated.dispose()
