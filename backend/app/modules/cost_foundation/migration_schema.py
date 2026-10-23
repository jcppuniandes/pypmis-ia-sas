"""Cost authority tables are created only by the guarded Alembic migration."""

COST_MIGRATION_TABLE_NAMES = frozenset(
    {
        "cost_cbs",
        "cost_code_dictionary",
        "cost_control_accounts",
        "cost_mappings",
        "cost_rates",
        "cost_apus",
        "cost_budget_versions",
        "cost_budget_lines",
        "cost_baselines",
        "cost_phasing",
        "cost_history",
        "cost_fx_rates",
        "cost_actual_entries",
        "cost_commitment_references",
    }
)


def local_bootstrap_tables(metadata):
    """Preserve legacy local bootstrap without creating unguarded Cost tables."""
    return [table for table in metadata.sorted_tables if table.name not in COST_MIGRATION_TABLE_NAMES]
