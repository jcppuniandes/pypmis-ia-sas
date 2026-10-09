"""Run identical governed Owner acceptance on real disposable PostgreSQL."""

import pytest
from sqlalchemy import inspect
from tests import test_owner_capability_wave3b as owner
from tests import test_wave3b_legacy_configuration_guard as legacy
from tests import test_wave3b_provider_integration as integration

from app.database.session import engine

client = legacy.client
globals().update(
    {
        name: value
        for module in (owner, integration, legacy)
        for name, value in vars(module).items()
        if name.startswith("test_") and callable(value)
    }
)
pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql" or engine.url.database != "wave3b",
    reason="Owner Capability evidence requires disposable PostgreSQL wave3b",
)


def test_wave3b_postgres_schema_has_exact_additive_aggregate_and_immutable_receipt_surface():
    inspector = inspect(engine)
    tables = {"owner_capability_assessments", "owner_capability_commands"}
    assert tables.issubset(inspector.get_table_names())
    assert all(len(index["name"]) <= 63 for table in tables for index in inspector.get_indexes(table))
    assert "uq_owner_capability_version" in {
        row["name"] for row in inspector.get_unique_constraints("owner_capability_assessments")
    }
    assert "ck_owner_capability_completed" in {
        row["name"] for row in inspector.get_check_constraints("owner_capability_assessments")
    }
    assert "uq_owner_capability_command_key" in {
        row["name"] for row in inspector.get_unique_constraints("owner_capability_commands")
    }
