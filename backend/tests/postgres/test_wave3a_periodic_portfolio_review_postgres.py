"""Real PostgreSQL Wave 3A release evidence using the shared acceptance suite."""

import pytest
from sqlalchemy import inspect
from tests.test_portfolio_review_wave3a import (  # noqa: F401
    test_wave3a_action_acceptance_cannot_bypass_approval_through_update,
    test_wave3a_action_owner_with_other_nonprivileged_role_cannot_edit_someone_elses_action,
    test_wave3a_action_semantics_are_request_only_without_source_mutations,
    test_wave3a_admin_preview_is_nonpersisted_clone_keeps_scope_and_scoped_admin_cannot_escape,
    test_wave3a_automatic_allocation_selection_never_uses_another_portfolios_enterprise_plan,
    test_wave3a_bucket_subject_and_source_authority_are_controlled_not_arbitrary,
    test_wave3a_cancelled_and_superseded_reviews_do_not_allow_action_mutations,
    test_wave3a_completed_history_trends_and_comparison_never_reinterpret_live_sources,
    test_wave3a_controlled_return_cancel_supersede_transitions_are_idempotent_and_terminal,
    test_wave3a_governance_model_is_opt_in_and_empty_portfolio_cannot_freeze,
    test_wave3a_http_etag_idempotency_and_admin_user_approval_dispatch_rbac,
    test_wave3a_http_null_required_update_is_validation_error_and_does_not_mutate,
    test_wave3a_http_owner_organization_and_preparer_scoped_grants_do_not_cross_multiply,
    test_wave3a_http_tenant_and_workspace_scope_are_enforced_for_all_read_models,
    test_wave3a_multicurrency_allocation_is_grouped_and_unclassified_membership_is_preserved,
    test_wave3a_options_do_not_disclose_allocation_plans_outside_workspace_or_tenant_scope,
    test_wave3a_required_missing_sources_block_readiness_and_freeze,
    test_wave3a_snapshot_staleness_refresh_and_source_history_remain_immutable,
    test_wave3a_two_actor_lifecycle_snapshot_preview_freeze_idempotency_and_sod,
)

from app.database.session import engine

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Wave 3A release evidence requires PYPMIS_TEST_DATABASE_URL with PostgreSQL",
)

TABLES = {
    "portfolio_review_sessions",
    "portfolio_review_snapshots",
    "portfolio_review_conclusions",
    "portfolio_review_actions",
    "portfolio_review_commands",
}


def test_wave3a_postgres_dialect_schema_indexes_and_constraints():
    assert engine.dialect.name == "postgresql"
    inspector = inspect(engine)
    assert TABLES.issubset(inspector.get_table_names())
    assert all(len(item["name"]) <= 63 for table in TABLES for item in inspector.get_indexes(table))
    assert "uq_portfolio_review_number" in {
        item["name"] for item in inspector.get_unique_constraints("portfolio_review_sessions")
    }
    assert "uq_portfolio_review_snapshot_version" in {
        item["name"] for item in inspector.get_unique_constraints("portfolio_review_snapshots")
    }
    assert "uq_portfolio_review_command_key" in {
        item["name"] for item in inspector.get_unique_constraints("portfolio_review_commands")
    }
    assert "ck_portfolio_review_completed" in {
        item["name"] for item in inspector.get_check_constraints("portfolio_review_sessions")
    }
