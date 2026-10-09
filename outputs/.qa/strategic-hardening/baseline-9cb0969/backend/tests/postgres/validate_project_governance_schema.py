"""Validate the PostgreSQL migration contract for multi-source Project creation."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

MULTI_SOURCE_COLUMNS = {
    "governance_model",
    "source_context_id",
    "source_external_key",
    "idempotency_key",
    "source_snapshot_json",
    "source_hash",
    "creation_policy_id",
    "creation_policy_revision",
    "creation_policy_hash",
}

MULTI_SOURCE_INDEXES = {
    "ix_pcr_governance_model",
    "ix_pcr_source_context_id",
    "ix_pcr_source_external_key",
    "ix_pcr_idempotency_key",
    "ix_pcr_creation_policy_id",
    "uq_pcr_source_context_identity",
    "uq_pcr_source_external_identity",
    "uq_pcr_direct_idempotency",
}


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Multi-source Project schema validation requires PostgreSQL")
    with engine.connect() as connection:
        actual_revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual_revision == expected_revision, (actual_revision, expected_revision)
        inspector = inspect(connection)
        columns = {item["name"]: item for item in inspector.get_columns("project_creation_requests")}
        if expected_revision == "20260820_0043":
            assert not MULTI_SOURCE_COLUMNS.intersection(columns)
            return

        assert expected_revision == "20260820_0044"
        assert MULTI_SOURCE_COLUMNS.issubset(columns)
        assert columns["source_snapshot_json"]["nullable"] is False
        foreign_keys = {item.get("name") for item in inspector.get_foreign_keys("project_creation_requests")}
        assert "fk_pcr_creation_policy" in foreign_keys
        indexes = {item["name"]: item for item in inspector.get_indexes("project_creation_requests")}
        assert MULTI_SOURCE_INDEXES.issubset(indexes)
        for name in (
            "uq_pcr_source_context_identity",
            "uq_pcr_source_external_identity",
            "uq_pcr_direct_idempotency",
        ):
            assert indexes[name]["unique"] is True
            predicate = str(indexes[name].get("dialect_options", {}).get("postgresql_where", ""))
            assert "REJECTED" in predicate.upper() and "CANCELLED" in predicate.upper()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=("20260820_0043", "20260820_0044"))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Multi-source Project schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
