"""Database-free temporal authorization and source activation guards."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.time import utc_today
from app.modules.contracts_foundation import service as contracts


def test_future_change_does_not_replace_current_effective_contract(monkeypatch):
    """Future approval must not make today's adopted commitment stale."""
    today = utc_today()
    service = contracts.ContractsService(None, 1, 2)
    contract = SimpleNamespace(id=10, status="EFFECTIVE", current_version_id=11, commencement_date=today)
    base = SimpleNamespace(
        id=11,
        contract_id=10,
        status="APPROVED",
        source_hash="valid",
        revision=1,
        effective_date=today,
        completion_date=today + timedelta(days=90),
        value=Decimal("100"),
        terms_reference="Existing terms",
    )
    monkeypatch.setattr(contracts, "_version_hash", lambda row: "valid")
    monkeypatch.setattr(service, "_new_version", lambda *args, **kwargs: SimpleNamespace(id=12))
    monkeypatch.setattr(service, "_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_check_document", lambda *args: {})
    with pytest.raises(HTTPException) as denied:
        service.apply_change_version(
            20,
            contract,
            base,
            value_delta=Decimal("20"),
            time_delta=2,
            effective_date=today + timedelta(days=1),
            document={},
            reason="Independent approved change",
            change_id=30,
        )
    assert denied.value.status_code == 409
    assert denied.value.detail["code"] == "CONTRACTS_FUTURE_CHANGE_ACTIVATION_UNSUPPORTED"
    assert contract.current_version_id == base.id
