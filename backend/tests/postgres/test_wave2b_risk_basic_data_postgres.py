"""Run the unchanged acceptance scenarios on real disposable PostgreSQL."""

import pytest
from sqlalchemy import inspect
from tests import test_basic_data_wave2b as basic
from tests import test_risk_governance_wave2b as risk
from tests import test_wave2b_legacy_configuration_guard as legacy
from tests import test_wave2b_provider_integration as integration

from app.database.session import engine

client = legacy.client

# Re-export the complete suites, preserving pytest parametrization and fixtures.
globals().update(
    {
        name: value
        for module in (basic, risk, integration, legacy)
        for name, value in vars(module).items()
        if name.startswith("test_") and callable(value)
    }
)

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql" or engine.url.database != "wave2b",
    reason="Wave 2B evidence requires the disposable PostgreSQL wave2b database",
)


def test_wave2b_postgres_schema_constraints_and_short_index_names():
    inspector = inspect(engine)
    tables = {"project_basic_data_items", "basic_data_readiness_assessments", "basic_data_commands"}
    assert tables.issubset(inspector.get_table_names())
    assert all(len(index["name"]) <= 63 for table in tables for index in inspector.get_indexes(table))
    assert "uq_basic_data_project_requirement" in {
        row["name"] for row in inspector.get_unique_constraints("project_basic_data_items")
    }
    assert "ck_basic_data_assessment_completed" in {
        row["name"] for row in inspector.get_check_constraints("basic_data_readiness_assessments")
    }
    assert "uq_basic_data_command_key" in {
        row["name"] for row in inspector.get_unique_constraints("basic_data_commands")
    }
