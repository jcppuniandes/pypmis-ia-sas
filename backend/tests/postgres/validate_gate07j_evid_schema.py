"""Validate Gate 07J-EVID's deliberate no-migration architecture."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07J-EVID schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        tables = set(inspect(connection).get_table_names())
        assert "admin_configurations" in tables
        assert "investment_gate_preparations" in tables
        assert "investment_gate_evidence_items" in tables
        assert not {
            "investment_evidence_policies",
            "investment_evidence_providers",
            "investment_decisions",
            "fid_decisions",
        }.intersection(tables)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=("20260830_0052",))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07J-EVID no-migration schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
