"""Tables require the frozen 0076 Alembic constraints and are never bootstrapped."""

ENGINEERING_MIGRATION_TABLE_NAMES = frozenset(
    {
        "engineering_design_packages",
        "engineering_deliverables",
        "engineering_revisions",
        "engineering_reviews",
        "engineering_review_comments",
        "engineering_releases",
        "engineering_interfaces",
        "engineering_history",
        "engineering_mappings",
    }
)
