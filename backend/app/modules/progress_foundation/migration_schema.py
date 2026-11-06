"""Progress requires Alembic guards rather than ORM-only local bootstrap."""

PROGRESS_MIGRATION_TABLE_NAMES = frozenset(
    {
        "progress_measurements",
        "progress_rules",
        "progress_history",
        "progress_control_baseline_bundles",
        "progress_period_snapshots",
        "progress_earned_value_snapshots",
    }
)


def local_bootstrap_tables(metadata):
    return [table for table in metadata.sorted_tables if table.name not in PROGRESS_MIGRATION_TABLE_NAMES]
