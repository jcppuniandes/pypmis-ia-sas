"""Forecast tables are created only by the explicit additive Alembic revision."""

FORECAST_MIGRATION_TABLE_NAMES = frozenset(
    {
        "forecast_versions",
        "forecast_assumptions",
        "forecast_components",
        "forecast_history",
        "forecast_report_snapshots",
        "forecast_lookahead_snapshots",
    }
)


def legacy_metadata_sorted_tables(metadata):
    return [table for table in metadata.sorted_tables if table.name not in FORECAST_MIGRATION_TABLE_NAMES]


local_bootstrap_tables = legacy_metadata_sorted_tables
