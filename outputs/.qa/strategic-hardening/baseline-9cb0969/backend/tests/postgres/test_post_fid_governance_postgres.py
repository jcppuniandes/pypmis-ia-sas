"""Real PostgreSQL structural evidence for Gate 07L."""

import pytest
from sqlalchemy import inspect

from app.database.session import engine

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL Gate 07L evidence required")


def test_gate07l_snapshot_constraints_and_indexes_exist() -> None:
    inspector = inspect(engine)
    assert "post_fid_project_eligibilities" in inspector.get_table_names()
    checks = {item["name"] for item in inspector.get_check_constraints("post_fid_project_eligibilities")}
    assert {"ck_post_fid_eligibility_status", "ck_post_fid_single_handoff"}.issubset(checks)
    uniques = {item["name"] for item in inspector.get_unique_constraints("post_fid_project_eligibilities")}
    assert {"uq_post_fid_eligibility_round", "uq_post_fid_eligibility_operation"}.issubset(uniques)
    indexes = {item["name"] for item in inspector.get_indexes("post_fid_project_eligibilities")}
    assert {"ix_post_fid_eligibility_latest", "ix_post_fid_eligibility_queue"}.issubset(indexes)
