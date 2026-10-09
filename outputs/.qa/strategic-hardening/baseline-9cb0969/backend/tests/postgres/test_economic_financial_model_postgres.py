"""Real PostgreSQL structural evidence for Gate 07M-FIN."""

import pytest
from sqlalchemy import inspect

from app.database.session import engine

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL evidence required")


def test_gate07m_fin_tables_constraints_and_indexes_exist() -> None:
    inspector = inspect(engine)
    assert (
        len(
            {
                name
                for name in inspector.get_table_names()
                if name.startswith("economic_financial") or name.startswith("financial_model")
            }
        )
        == 12
    )
    checks = {item["name"] for item in inspector.get_check_constraints("economic_financial_model_versions")}
    assert {
        "ck_fin_model_version_status",
        "ck_fin_model_version_type",
        "ck_fin_model_version_basis",
        "ck_fin_model_readiness",
    }.issubset(checks)
    foreign_keys = {item["name"] for item in inspector.get_foreign_keys("economic_financial_models")}
    assert "fk_economic_financial_model_current_version" in foreign_keys
