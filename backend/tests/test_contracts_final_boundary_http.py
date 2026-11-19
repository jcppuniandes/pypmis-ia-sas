"""Persisted O2C fixture negatives; never creates successful upstream commands."""

import json
import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from tests.operational_context_fixture import fixture_headers

from app.core.time import utc_today
from app.database.session import SessionLocal, engine
from app.domain.models import EnterpriseWorkspace, UserAccount
from app.main import app
from app.modules.contracts_foundation.models import OperationalContract
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.operational_context.models import ProjectControlsPeriod
from app.modules.progress_foundation.schemas import MeasurementIn
from app.modules.schedule_foundation.schemas import RegisterIn
from app.modules.scope_foundation.models import ScopeItem

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2c-20261118"
SCENARIO = QA / "core-attempt-a/scenario.json"
TABLES = (
    "progress_measurements",
    "schedule_registers",
    "schedule_versions",
    "schedule_baselines",
    "cost_budget_versions",
    "cost_actual_entries",
    "forecast_versions",
    "procurement_purchase_orders",
)


def snapshots(db, tenant):
    return {
        table: {
            "count": db.scalar(text(f"SELECT count(*) FROM {table} WHERE tenant_id=:tenant"), {"tenant": tenant}),
            "hash": db.scalar(
                text(
                    f"SELECT md5(coalesce(string_agg(to_jsonb(t)::text,',' ORDER BY id),'')) "
                    f"FROM {table} t WHERE tenant_id=:tenant"
                ),
                {"tenant": tenant},
            ),
        }
        for table in TABLES
    }


def test_persisted_contracts_actor_cannot_write_progress_or_schedule_or_cross_scope():
    if os.getenv("PYPMIS_O2C_FIXTURE") != "disposable-only":
        pytest.skip("Exact disposable O2C PostgreSQL fixture required")
    assert os.getenv("PYPMIS_TEST_DATABASE_URL") == "postgresql+psycopg://o2c:o2c@127.0.0.1:5561/o2c"
    assert (engine.url.host, engine.url.port, engine.url.database, engine.url.username) == (
        "127.0.0.1",
        5561,
        "o2c",
        "o2c",
    )
    assert SCENARIO.is_file(), "Run the positive O2C core scenario before this persisted follow-up"
    scenario = json.loads(SCENARIO.read_text("utf-8"))
    tenant, workspace, identity = (scenario[key] for key in ("tenant_id", "project_workspace_id", "contract_id"))
    assert workspace != 14 and scenario["legacy_project_id"] != 14
    today = utc_today()
    with SessionLocal() as db:
        contract = db.get(OperationalContract, identity)
        assert contract and (contract.tenant_id, contract.project_workspace_id) == (tenant, workspace)
        actor = db.get(UserAccount, scenario["commercial_commitment"]["created_by"])
        assert actor and actor.tenant_id == tenant and actor.id == contract.created_by
        # Avoid issuing a potentially successful command if the persisted actor's duties were expanded.
        for duty in ("progress.capture", "schedule_foundation.register.edit"):
            with pytest.raises(HTTPException) as denied:
                require_enterprise_permission(db, tenant, actor.id, duty, bootstrap=False)
            assert denied.value.status_code == 403
        headers = fixture_headers(actor)
        scope = db.scalar(
            select(ScopeItem)
            .where(
                ScopeItem.tenant_id == tenant,
                ScopeItem.project_workspace_id == workspace,
            )
            .order_by(ScopeItem.id)
        )
        period = db.scalar(
            select(ProjectControlsPeriod).where(
                ProjectControlsPeriod.tenant_id == tenant,
                ProjectControlsPeriod.project_workspace_id == workspace,
                ProjectControlsPeriod.period_start <= today,
                ProjectControlsPeriod.period_end >= today,
                ProjectControlsPeriod.status == "OPEN",
            )
        )
        other = db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == tenant,
                EnterpriseWorkspace.code.like("O1A-other_project-%"),
            )
        )
        assert scope and period and other and other.id not in {14, workspace}
        foreign_contract = db.scalar(
            select(OperationalContract)
            .where(
                OperationalContract.tenant_id != tenant,
            )
            .order_by(OperationalContract.id)
        )
        assert foreign_contract, "An existing other-tenant scenario is required for record-ID hiding"
        foreign_identity = foreign_contract.id
        before = snapshots(db, tenant)
        progress = MeasurementIn.model_validate(
            {
                "reason": "Persisted O2C domain boundary verification",
                "code": f"DENIED-{uuid4().hex[:10]}",
                "name": "Unauthorized Contracts-only progress request",
                "progress_type": "QUANTITY",
                "method": "QUANTITY_BASED",
                "source_reference": "CERTIFIABLE_FIELD_QUANTITY_SHEET",
                "scope_item_id": scope.id,
                "scope_nature": scope.scope_nature,
                "phase": "INSTALL",
                "period_id": period.id,
                "measurement_date": today,
                "as_of": today,
                "numerator": scope.quantity * Decimal("0.75"),
                "unit": scope.unit,
                "evidence_refs": [{"kind": "QUANTITY_SHEET", "reference": "BOUNDARY-QS-001"}],
            }
        ).model_dump(mode="json")
        schedule = RegisterIn.model_validate(
            {
                "reason": "Persisted O2C domain boundary verification",
                "schedule_code": f"DENIED-{uuid4().hex[:10]}",
                "name": "Unauthorized Contracts-only schedule request",
            }
        ).model_dump(mode="json")
    observations = []
    with TestClient(app) as client:
        positive = client.get(f"/api/v1/contracts/projects/{workspace}/contracts/{identity}", headers=headers)
        assert positive.status_code == 200, positive.text
        for domain, resource, body in (
            ("progress", "measurements", progress),
            ("schedule", "registers", schedule),
        ):
            response = client.post(
                f"/api/v1/{domain}/projects/{workspace}/{resource}",
                json=body,
                headers=headers | {"Idempotency-Key": f"o2c-boundary-{uuid4()}"},
            )
            assert response.status_code == 403, response.text
            observations.append({"domain": domain, "status": response.status_code, "detail": response.json()["detail"]})
        cross = client.get(f"/api/v1/contracts/projects/{other.id}/contracts/{identity}", headers=headers)
        assert cross.status_code == 403, cross.text
        assert cross.json() == {"detail": {"code": "OPERATIONAL_PROJECT_CONTEXT_UNAUTHORIZED"}}
        observations.append(
            {"domain": "Contracts other workspace URI", "status": 403, "detail": cross.json()["detail"]}
        )
        hidden = client.get(f"/api/v1/contracts/projects/{workspace}/contracts/{foreign_identity}", headers=headers)
        assert hidden.status_code == 404, hidden.text
        assert hidden.json() == {"detail": {"code": "CONTRACTS_RECORD_NOT_FOUND"}}
        observations.append({"domain": "Contracts foreign record ID", "status": 404, "detail": hidden.json()["detail"]})
    with SessionLocal() as db:
        after = snapshots(db, tenant)
    assert after == before
    (QA / "final-boundary-http.json").write_text(
        json.dumps(
            {
                "tenant_id": tenant,
                "project_workspace_id": workspace,
                "contract_id": identity,
                "actor_id": actor.id,
                "observations": observations,
                "upstream_before": before,
                "upstream_after": after,
                "new_operational_records": 0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
