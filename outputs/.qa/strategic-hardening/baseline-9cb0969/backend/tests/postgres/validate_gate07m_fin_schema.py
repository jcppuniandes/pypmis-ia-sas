"""Validate additive/reversible Gate 07M-FIN PostgreSQL schema."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

REVISION_BEFORE = "20260902_0057"
REVISION_AFTER = "20260902_0058"
TABLES = {
    "economic_financial_models",
    "economic_financial_model_versions",
    "financial_model_assumptions",
    "financial_model_periods",
    "financial_model_financing_instruments",
    "financial_model_investors",
    "financial_model_scenarios",
    "financial_model_scenario_overrides",
    "financial_model_cash_flows",
    "financial_model_debt_schedules",
    "financial_model_metric_results",
    "financial_model_sensitivity_results",
}


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07M-FIN validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == REVISION_BEFORE:
            assert TABLES.isdisjoint(tables)
            return
        assert TABLES.issubset(tables)
        version_columns = {item["name"] for item in inspector.get_columns("economic_financial_model_versions")}
        assert {
            "business_case_hash",
            "source_snapshot_hash",
            "model_hash",
            "calculation_engine_version",
            "overall_readiness",
            "revision_version",
        }.issubset(version_columns)
        model_uniques = {item["name"] for item in inspector.get_unique_constraints("economic_financial_models")}
        assert "uq_economic_financial_model_project" in model_uniques
        scenario_indexes = {item["name"] for item in inspector.get_indexes("financial_model_scenarios")}
        assert "uq_fin_model_official_base" in scenario_indexes


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=(REVISION_BEFORE, REVISION_AFTER))
    validate(parser.parse_args().expect)
    print("Gate07M-FIN schema: PASS")
