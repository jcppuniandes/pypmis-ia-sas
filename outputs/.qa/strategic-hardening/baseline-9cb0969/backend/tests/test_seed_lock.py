"""Tests for seed_demo advisory locking."""

from unittest.mock import MagicMock

from app.database.seed import acquire_seed_demo_lock, release_seed_demo_lock


def test_acquire_lock_returns_true_for_non_postgresql():
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "sqlite"
    assert acquire_seed_demo_lock(db) is True


def test_release_lock_is_noop_for_non_postgresql():
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "sqlite"
    release_seed_demo_lock(db)
    db.execute.assert_not_called()


def test_acquire_lock_calls_pg_try_advisory_lock():
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    db.scalar.return_value = True
    assert acquire_seed_demo_lock(db) is True
    db.scalar.assert_called_once()
    sql_clause = db.scalar.call_args[0][0]
    assert "pg_try_advisory_lock" in sql_clause.text


def test_acquire_lock_returns_false_when_not_acquired():
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    db.scalar.return_value = False
    assert acquire_seed_demo_lock(db) is False
