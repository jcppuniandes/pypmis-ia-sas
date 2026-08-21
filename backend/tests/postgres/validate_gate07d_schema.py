"""Validate the real PostgreSQL shape on both sides of Gate 07D revision 0043."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

GATE07D_COLUMNS = {
    "source_context_type",
    "strategic_gate_decision_id",
    "source_project_proposal_id",
    "source_idea_id",
    "source_decision_hash",
    "source_readiness_hash",
    "strategic_target_portfolio_workspace_id",
    "strategic_mapping_configuration_id",
    "strategic_mapping_revision",
    "strategic_mapping_hash",
    "strategic_source_snapshot_json",
}

REQUEST_FOREIGN_KEYS = {
    "fk_pcr_strategic_decision",
    "fk_pcr_source_proposal",
    "fk_pcr_source_idea",
    "fk_pcr_target_portfolio",
    "fk_pcr_strategic_mapping",
}

REQUEST_INDEXES = {
    "uq_project_creation_strategic_decision",
    "ix_project_creation_requests_source_context_type",
    "ix_project_creation_requests_strategic_gate_decision_id",
    "ix_project_creation_requests_source_project_proposal_id",
    "ix_project_creation_requests_source_idea_id",
    "ix_pcr_strategic_target_portfolio",
    "ix_pcr_strategic_mapping_config",
}


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Gate 07D schema validation requires PostgreSQL")
    with engine.connect() as connection:
        actual_revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual_revision == expected_revision, (actual_revision, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        request_columns = {item["name"] for item in inspector.get_columns("project_creation_requests")}
        if expected_revision == "20260813_0042":
            assert not GATE07D_COLUMNS.intersection(request_columns)
            assert "portfolio_project_memberships" not in tables
            return

        assert expected_revision in {"20260820_0043", "20260820_0044"}
        assert GATE07D_COLUMNS.issubset(request_columns)
        assert REQUEST_FOREIGN_KEYS.issubset(
            {item.get("name") for item in inspector.get_foreign_keys("project_creation_requests")}
        )
        assert REQUEST_INDEXES.issubset({item["name"] for item in inspector.get_indexes("project_creation_requests")})
        assert "portfolio_project_memberships" in tables
        membership_columns = {item["name"] for item in inspector.get_columns("portfolio_project_memberships")}
        assert {
            "tenant_id",
            "portfolio_workspace_id",
            "project_workspace_id",
            "membership_source",
            "is_target_portfolio",
            "status",
            "revision_version",
        }.issubset(membership_columns)
        membership_indexes = {item["name"]: item for item in inspector.get_indexes("portfolio_project_memberships")}
        active_unique = membership_indexes["uq_portfolio_project_membership_active"]
        assert active_unique["unique"] is True
        predicate = str(active_unique.get("dialect_options", {}).get("postgresql_where", ""))
        assert "ACTIVE" in predicate.upper()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=("20260813_0042", "20260820_0043", "20260820_0044"))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07D schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
