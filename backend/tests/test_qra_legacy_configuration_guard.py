"""Legacy generic commands cannot bypass QRA methodology authority."""

import pytest
from tests import test_wave2b_legacy_configuration_guard as legacy

from app.modules.qra_foundation.service import CONFIGURATION_KIND, DEFAULT_CONFIGURATION

client = legacy.client
DEDICATED = "/api/v1/qra-foundation/admin/configurations"


def test_qra_legacy_mutations_reject_all_states_without_writes(client):
    legacy.test_wave2b_legacy_clone_patch_publish_never_mutate_governed_policies_in_any_state(
        client, CONFIGURATION_KIND, DEDICATED, DEFAULT_CONFIGURATION
    )


@pytest.mark.parametrize("normalized_alias", [False, True])
def test_qra_legacy_create_rejects_canonical_and_normalized_aliases(client, normalized_alias):
    legacy.test_wave2b_legacy_create_rejects_governed_kinds_and_normalized_aliases(
        client, CONFIGURATION_KIND, DEDICATED, DEFAULT_CONFIGURATION, normalized_alias
    )


def test_qra_future_legacy_commands_require_authority_guard():
    legacy.test_wave2b_legacy_configuration_mutation_inventory_requires_guard_for_future_commands()
