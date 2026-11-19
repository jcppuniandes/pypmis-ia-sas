"""Read-only security and supersession checks against completed O3A fixtures."""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.operational_context_fixture import fixture_headers

from app.database.session import SessionLocal
from app.domain.models import EnterpriseWorkspace, UserAccount
from app.main import app
from app.modules.contracts_foundation.schemas import ContractPackageIn
from app.modules.field_operations.consumer_sources import read_field_source
from app.modules.schedule_foundation.schemas import RegisterIn

pytestmark = pytest.mark.skipif(
    os.getenv("PYPMIS_O3A_FIXTURE") != "disposable-only", reason="Isolated O3A fixture required"
)
QA = Path(__file__).resolve().parents[2] / "outputs/.qa/wave-o3a-20261118"


def test_field_actor_cannot_write_contracts_or_schedule_and_other_workspace():
    manifest = json.loads((QA / "browser-fixture.json").read_text("utf-8"))
    with SessionLocal() as db, TestClient(app) as client:
        assert (db.bind.url.port, db.bind.url.database, db.bind.url.username) == (5564, "o3a", "o3a")
        actor = db.scalar(
            select(UserAccount).where(
                UserAccount.tenant_id == manifest["tenant_id"], UserAccount.email.like("field_reporter-%")
            )
        )
        assert actor is not None
        headers = fixture_headers(actor) | {"Idempotency-Key": "o3a-forbidden-" + uuid4().hex}
        contract = ContractPackageIn(
            reason="O3A explicit authority negative",
            package_code="NO-FIELD-CONTRACT",
            title="Field actor must not prepare contract",
            contract_type="PURCHASE_ORDER_BASED_AGREEMENT",
            commercial_model="LUMP_SUM",
            currency="USD",
            estimated_value="1",
        )
        schedule = RegisterIn(
            reason="O3A explicit authority negative", schedule_code="NO-FIELD-P6", name="Denied schedule"
        )
        for domain, collection, data in (("contracts", "packages", contract), ("schedule", "registers", schedule)):
            response = client.post(
                f"/api/v1/{domain}/projects/{manifest['project_workspace_id']}/{collection}",
                headers=headers,
                json=data.model_dump(mode="json"),
            )
            assert response.status_code == 403, response.text
        other = db.scalar(
            select(EnterpriseWorkspace)
            .where(
                EnterpriseWorkspace.tenant_id == manifest["tenant_id"],
                EnterpriseWorkspace.workspace_type_code == "project",
                EnterpriseWorkspace.id != manifest["project_workspace_id"],
            )
            .order_by(EnterpriseWorkspace.id)
            .limit(1)
        )
        assert other is not None
        response = client.get(f"/api/v1/field-operations/projects/{other.id}/workfronts", headers=headers)
        assert response.status_code in {403, 404}, response.text


def test_superseded_verified_production_cannot_be_readopted():
    scenario = json.loads((QA / "execution-evidence.json").read_text("utf-8"))
    with SessionLocal() as db:
        assert (db.bind.url.port, db.bind.url.database, db.bind.url.username) == (5564, "o3a", "o3a")
        with pytest.raises(HTTPException) as failure:
            read_field_source(
                db, scenario["tenant_id"], scenario["project_workspace_id"], "PRODUCTION", scenario["production_id"]
            )
        assert failure.value.status_code == 409
        assert failure.value.detail["code"] == "FIELD_CONSUMER_SOURCE_SUPERSEDED"
