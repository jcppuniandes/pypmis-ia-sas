"""Isolated, database-free guards for O2C's Procurement source authority."""

from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.contracts_foundation.policy import DEFAULT_PROFILE, ContractsProfile
from app.modules.contracts_foundation.service import ContractsService
from app.modules.procurement_foundation import consumer_sources as sources


def test_contract_source_fingerprint_ignores_cost_mapping_without_changing_legacy_cost(monkeypatch):
    observed = datetime(2026, 5, 5, 12, tzinfo=UTC)
    mapping = {"id": 5, "version": 1, "target_kind": "CBS", "target_id": 20}

    def resolve_po(reader):
        assert (reader.tenant, reader.workspace, reader.identity, reader.package_id) == (1, 2, 3, 4)
        return sources._Fact(SimpleNamespace(id=4), 1, observed, observed.date(), {"po_id": 3})

    monkeypatch.setattr(sources, "utc_now", lambda: observed)
    monkeypatch.setitem(sources._METHODS, "PO", resolve_po)
    monkeypatch.setattr(sources._Resolver, "mapping_rows", lambda *_: [mapping.copy()])
    db = SimpleNamespace(no_autoflush=nullcontext())

    def resolve(authority=None, expected=None):
        return sources.resolve_procurement_source(
            db, 1, 2, "PO", 3, consumer=authority, package_id=4, expected_hash=expected
        )

    cost, contract = resolve("COST"), resolve("CONTRACTS")
    assert resolve() == cost
    assert cost["cost_mappings"] == [mapping] and contract["cost_mappings"] == []
    assert cost["source_hash"] != contract["source_hash"]
    mapping["version"] = 2
    assert resolve("CONTRACTS", contract["source_hash"]) == contract
    with pytest.raises(HTTPException, match="SOURCE_HASH_MISMATCH"):
        resolve("COST", cost["source_hash"])


def test_vendor_pin_must_match_contract_counterparty():
    service = ContractsService(None, 1, 2)
    with pytest.raises(HTTPException) as error:
        service._validate_source_vendor({"source_type": "VENDOR", "source_id": 5}, 6, "USD")
    assert error.value.status_code == 409
    service._validate_source_vendor({"source_type": "VENDOR", "source_id": 5}, 5, "USD")


def test_contract_duty_separation_defaults_are_explicit():
    profile = ContractsProfile.model_validate(DEFAULT_PROFILE)
    assert profile.separation_of_duties["contract_author_cannot_approve"]
    assert profile.separation_of_duties["contract_approver_cannot_execute"]
    assert profile.separation_of_duties["commitment_author_cannot_approve"]
