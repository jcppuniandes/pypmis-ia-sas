"""Procurement-only role cannot perform real writes owned by other domains."""

import json
import os
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, text
from tests.cost_release_fixture import budget, line
from tests.engineering_release_fixture import TODAY, request
from tests.forecast_release_fixture import body as forecast_body
from tests.procurement_release_fixture import REASON
from tests.test_cost_financial_release import commitment, obligation_payload
from tests.test_procurement_consumer_release import governed, signatures
from tests.test_progress_foundation_release import measurement_body
from tests.test_scope_foundation_release import success

from app.database.session import SessionLocal
from app.domain.models import PermissionCatalog, SecurityAccessAssignment, SecurityRole, SecurityRolePermission

_ = governed  # Pytest discovers the reused module-scoped fixture here.
AUTHORITY_TABLES = (
    "contracts",
    "purchase_orders",
    "budgets",
    "cost_records",
    "cost_budget_versions",
    "cost_budget_lines",
    "cost_actual_entries",
    "cost_commitment_references",
    "cost_history",
    "progress_records",
    "progress_measurements",
    "progress_history",
    "project_controls_periods",
    "forecast_scenarios",
    "forecast_versions",
    "forecast_assumptions",
    "forecast_components",
    "forecast_history",
    "operational_context_commands",
    "operational_procurement_adoptions",
)


def buyer_permissions(f):
    with SessionLocal() as db:
        roles = db.execute(
            select(SecurityRole.id, SecurityRole.code)
            .join(SecurityAccessAssignment, SecurityAccessAssignment.role_id == SecurityRole.id)
            .where(
                SecurityAccessAssignment.user_id == f.users["buyer"].id,
                SecurityAccessAssignment.tenant_id == f.tenant_id,
                SecurityAccessAssignment.status == "active",
                SecurityAccessAssignment.workspace_id == f.project_workspace_id,
            )
        ).all()
        assert [role.code for role in roles] == ["procurement_buyer"]
        permissions = set(
            db.scalars(
                select(PermissionCatalog.key)
                .join(SecurityRolePermission, SecurityRolePermission.permission_id == PermissionCatalog.id)
                .where(SecurityRolePermission.role_id == roles[0].id)
            )
        )
    assert "procurement.read" in permissions
    assert not any(
        permission.startswith(("cost.", "progress.", "forecast.", "operational_context.period."))
        for permission in permissions
    )
    return sorted(permissions)


def authority_hash(f):
    values = signatures(f, AUTHORITY_TABLES)
    return sha256(json.dumps(values, sort_keys=True).encode()).hexdigest(), values


def test_procurement_only_native_authority_writes_are_denied(governed):
    f = governed
    permissions = buyer_permissions(f)
    root = f"/api/v1/procurement/projects/{f.project_workspace_id}"
    assert request(f, "GET", root + "/packages", actor="buyer").status_code == 200
    package = success(
        request(
            f,
            "POST",
            root + "/packages",
            actor="buyer",
            payload={
                **REASON,
                "package_code": f"CLOSE2-AUTH-{uuid4().hex[:8]}",
                "title": "Positive buyer permission control",
                "procurement_type": "MATERIAL",
                "category": "GENERAL",
                "sourcing_method": "RFQ",
                "required_on_site_date": TODAY.isoformat(),
            },
        ),
        201,
    )
    assert package["status"] == "DRAFT"
    budget_row = budget(f, budget_type="CURRENT", predecessor_id=f.cost_budget["id"])
    priced_line = line(f, budget_row)
    draft_budget, draft_line = priced_line["budget_version"], priced_line
    reference = commitment(f, verify=False)
    current = f.current_period
    approved = f.approved_forecast
    draft = f.draft_forecast
    today = TODAY.isoformat()
    measure_payload = measurement_body(f, period_id=current["id"], measurement_date=today, as_of=today)
    measurement = success(
        request(
            f,
            "POST",
            f"/api/v1/progress/projects/{f.project_workspace_id}/measurements",
            actor="cost_controller",
            payload=measure_payload,
        ),
        201,
    )
    before_hash, before_tables = authority_hash(f)
    outcome = []
    test_commands = (
        ("cost", "POST", "/commitments", obligation_payload(effective_date=today), None),
        (
            "cost",
            "POST",
            f"/commitments/{reference['id']}/verify",
            {**REASON, "status": "VERIFIED"},
            reference["version"],
        ),
        (
            "cost",
            "PUT",
            f"/budgets/{draft_budget['id']}/lines/{draft_line['id']}",
            {
                **REASON,
                "line_code": draft_line["line_code"],
                "description": "Unauthorized revision",
                "quantity": "30",
                "unit": draft_line["unit"],
                "rate": "25.00",
                "currency": "USD",
            },
            draft_budget["version"],
        ),
        (
            "cost",
            "POST",
            "/actuals",
            {
                **REASON,
                "source_system": "CLOSE2",
                "source_reference": f"ACT-{uuid4()}",
                "period_id": current["id"],
                "posting_date": today,
                "recognition_date": today,
                "amount": "10",
                "currency": "USD",
                "cbs_id": f.cost_cbs["id"],
                "cost_code_id": f.cost_code["id"],
                "control_account_id": f.cost_account["id"],
                "evidence_ref": "CLOSE2-AUTH-EVIDENCE",
            },
            None,
        ),
        ("progress", "POST", "/measurements", measure_payload | {"code": f"DENY-{uuid4().hex[:8]}"}, None),
        (
            "progress",
            "POST",
            f"/measurements/{measurement['id']}/transition",
            {**REASON, "status": "APPROVED"},
            measurement["version"],
        ),
        ("operational", "POST", f"/periods/{current['id']}/review", REASON, current["version"]),
        ("forecast", "POST", "/versions", forecast_body(f, period_id=current["id"], as_of=today), None),
        (
            "forecast",
            "PUT",
            f"/versions/{approved['id']}",
            forecast_body(f, code=approved["code"]),
            approved["version"],
        ),
        ("forecast", "POST", f"/versions/{draft['id']}/transition", {**REASON, "action": "approve"}, draft["version"]),
    )
    for domain, method, endpoint, payload, version in test_commands:
        path = f"/api/v1/{domain}/projects/{f.project_workspace_id}{endpoint}"
        response = request(f, method, path, actor="buyer", version=version, payload=payload)
        assert response.status_code == 403, (method, endpoint, response.status_code, response.json())
        outcome.append({"domain": domain, "method": method, "endpoint": endpoint, "status": response.status_code})
    after_hash, after_tables = authority_hash(f)
    assert before_hash == after_hash and before_tables == after_tables
    with SessionLocal() as db:
        assert (
            db.scalar(
                text("SELECT count(*) FROM operational_procurement_adoptions WHERE tenant_id=:tenant"),
                {"tenant": f.tenant_id},
            )
            == 0
        )
    destination = os.getenv("PYPMIS_CLOSE2_EVIDENCE")
    if destination:
        path = Path(destination).resolve(strict=True)
        assert "wave-o2b-close2-20261112" in path.parts and ".qa" in path.parts
        (path / "authority-proof.json").write_text(
            json.dumps(
                {
                    "result": "PASS",
                    "tenant_id": f.tenant_id,
                    "workspace_id": f.project_workspace_id,
                    "actor_id": f.users["buyer"].id,
                    "role": "procurement_buyer",
                    "permissions": permissions,
                    "positive_procurement": {"read": 200, "write": 201},
                    "denials": outcome,
                    "before_sha256": before_hash,
                    "after_sha256": after_hash,
                    "before_tables": before_tables,
                    "after_tables": after_tables,
                },
                indent=2,
            ),
            "utf-8",
        )
