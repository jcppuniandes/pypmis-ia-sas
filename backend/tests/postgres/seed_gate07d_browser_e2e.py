"""Seed one disposable Gate 07D browser scenario in the full-stack E2E database."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.test_portfolio_planning_gate07d import _approved_decision
from tests.test_project_proposal_gate07b import _headers

from app.database.session import SessionLocal
from app.domain.models import SecurityAccessAssignment, SecurityRole, UserAccount
from app.main import app


def main() -> None:
    with TestClient(app) as client:
        decision = _approved_decision(client, _headers(client))
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        approver = db.scalar(select(UserAccount).where(UserAccount.email == "ana.control@demo.local"))
        assert admin is not None and approver is not None
        role = db.scalar(
            select(SecurityRole).where(
                SecurityRole.tenant_id == admin.tenant_id,
                SecurityRole.code == "organization_admin",
                SecurityRole.status == "active",
            )
        )
        assert role is not None
        assignment = db.scalar(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == admin.tenant_id,
                SecurityAccessAssignment.user_id == approver.id,
                SecurityAccessAssignment.role_id == role.id,
                SecurityAccessAssignment.scope_type == "organization",
                SecurityAccessAssignment.status == "active",
            )
        )
        if assignment is None:
            db.add(
                SecurityAccessAssignment(
                    tenant_id=admin.tenant_id,
                    subject_type="user",
                    user_id=approver.id,
                    role_id=role.id,
                    scope_type="organization",
                    status="active",
                    granted_by_user_id=admin.id,
                )
            )
            db.commit()
        print(
            json.dumps(
                {
                    "decision_id": decision["id"],
                    "decision_number": decision["decision_number"],
                    "requestor": admin.email,
                    "approver": approver.email,
                }
            )
        )


if __name__ == "__main__":
    main()
