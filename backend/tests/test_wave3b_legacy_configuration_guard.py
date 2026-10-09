"""Owner Capability shares the dedicated authority boundary of governed policy."""

import pytest
from tests import test_wave2b_legacy_configuration_guard as legacy

from app.modules.owner_capability.service import DEFAULT_CONFIGURATION

client = legacy.client
KIND = "owner_capability_readiness_configuration"
DEDICATED = "/api/v1/owner-capability/admin/configurations"


def test_wave3b_legacy_mutations_reject_all_configuration_states_without_writes(client):
    legacy.test_wave2b_legacy_clone_patch_publish_never_mutate_governed_policies_in_any_state(
        client, KIND, DEDICATED, DEFAULT_CONFIGURATION
    )


@pytest.mark.parametrize("normalized_alias", [False, True])
def test_wave3b_legacy_create_rejects_canonical_and_normalized_aliases(client, normalized_alias):
    legacy.test_wave2b_legacy_create_rejects_governed_kinds_and_normalized_aliases(
        client, KIND, DEDICATED, DEFAULT_CONFIGURATION, normalized_alias
    )


def test_wave3b_future_legacy_configuration_commands_must_preserve_authority_guard():
    legacy.test_wave2b_legacy_configuration_mutation_inventory_requires_guard_for_future_commands()
