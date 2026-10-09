"""SQLite dialect round trip for the same additive migration as PostgreSQL."""

from tests.postgres.test_wave2b_migration_postgres import verify_round_trip


def test_wave2b_sqlite_upgrade_downgrade_upgrade(tmp_path):
    verify_round_trip(f"sqlite:///{(tmp_path / 'wave2b-migration.sqlite').as_posix()}")
