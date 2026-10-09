"""SQLite round trip for the same additive PostgreSQL Owner Capability migration."""

from tests.postgres.test_wave3b_migration_postgres import verify_round_trip


def test_wave3b_sqlite_upgrade_downgrade_upgrade(tmp_path):
    verify_round_trip(f"sqlite:///{(tmp_path / 'wave3b-migration.sqlite').as_posix()}")
