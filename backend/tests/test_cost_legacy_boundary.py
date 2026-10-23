"""Real PostgreSQL characterization of legacy candidate/write authority boundaries."""

from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from tests.cost_release_fixture import REASON, cbs, create_cost_fixture, request
from tests.test_scope_foundation_release import success

from app.database.session import SessionLocal
from app.domain.models import (
    WBS,
    BusinessProcessInstance,
    BusinessProcessLineItem,
    BusinessProcessLineItemRevision,
    ColombiaApuCatalogItem,
    ControlAccount,
    CostBreakdownStructure,
    CostCode,
    FundingSource,
    ProjectMembership,
)
from app.main import app
from app.modules.cost_foundation.legacy_boundary import COST_WRITERS, canonical_cost_project, guard_legacy_cost_write


@pytest.fixture(scope="module")
def fixture():
    with TestClient(app) as client, SessionLocal() as db:
        f = create_cost_fixture(db, client)
        f.db = db
        binding_root = f"/api/v1/operational/projects/{f.project_workspace_id}/binding"
        binding = success(request(f, "GET", binding_root, actor="admin"))
        if binding["state"] != "ACTIVE":
            success(
                request(
                    f,
                    "POST",
                    binding_root,
                    actor="admin",
                    version=binding["version"],
                    payload={**REASON, "legacy_project_id": f.legacy_project_id, "source": "AUTHORIZED_ONBOARDING"},
                ),
                201,
            )
        yield f
        db.rollback()


def test_cost_adoption_is_explicit_and_read_does_not_adopt(fixture):
    f = fixture
    assert canonical_cost_project(f.db, f.tenant_id, f.legacy_project_id) is None
    before = success(request(f, "GET", "/legacy-candidates"))
    assert before["approval_automatic"] is False
    assert before["authority"] == "CANDIDATE_ONLY_NOT_APPROVED_COST"
    assert canonical_cost_project(f.db, f.tenant_id, f.legacy_project_id) is None
    cbs(f)
    assert canonical_cost_project(f.db, f.tenant_id, f.legacy_project_id) == f.project_workspace_id


@pytest.mark.parametrize("writer", sorted(COST_WRITERS))
def test_legacy_direct_cost_writer_requires_canonical_adapter(fixture, writer):
    f = fixture
    if canonical_cost_project(f.db, f.tenant_id, f.legacy_project_id) is None:
        cbs(f)
    with pytest.raises(HTTPException) as denied:
        guard_legacy_cost_write(f.db, f.tenant_id, f.legacy_project_id, writer)
    assert denied.value.status_code == 409
    assert denied.value.detail["code"] == "CANONICAL_COST_AUTHORITY_REQUIRED"
    assert denied.value.detail["candidate_only"] is True
    assert denied.value.detail["project_workspace_id"] == f.project_workspace_id


def test_existing_legacy_business_process_line_cannot_mutate_cost_after_adoption(fixture):
    """Exercise the real HTTP boundary over existing linked monetary source rows."""
    f = fixture
    if canonical_cost_project(f.db, f.tenant_id, f.legacy_project_id) is None:
        cbs(f)
    base = {"tenant_id": f.tenant_id, "project_id": f.legacy_project_id}
    membership = f.db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.tenant_id == f.tenant_id,
            ProjectMembership.project_id == f.legacy_project_id,
            ProjectMembership.user_id == f.users["admin"].id,
        )
    )
    if membership is None:
        f.db.add(
            ProjectMembership(
                **base, user_id=f.users["admin"].id, role="Isolated legacy Cost operator", can_capture_cost=True
            )
        )
    wbs = WBS(**base, code="LEGACY-BOUNDARY-WBS", name="Existing legacy work")
    old_cbs = CostBreakdownStructure(**base, code="LEGACY-BOUNDARY-CBS", description="Existing legacy Cost source")
    funding = FundingSource(
        **base, code="LEGACY-BOUNDARY-FBS", name="Existing legacy funding reference", amount=1000, currency="USD"
    )
    f.db.add_all([wbs, old_cbs, funding])
    f.db.flush()
    account = ControlAccount(
        **base,
        wbs_id=wbs.id,
        code="LEGACY-BOUNDARY-CA",
        name="Existing legacy account",
        responsible="Existing Cost owner",
        discipline="Construction",
        budget=100,
        forecast=100,
    )
    process = BusinessProcessInstance(
        **base,
        trigger_entity_type="Project",
        trigger_entity_id=f.legacy_project_id,
        process_code="BP-CBS-WBS",
        process_name="Existing Cost business process",
        record_no="LEGACY-BOUNDARY-BP",
        title="Existing historical source",
        current_step="Control Review",
        ball_in_court="Project Controls",
    )
    f.db.add_all([account, process])
    f.db.flush()
    code = CostCode(
        **base,
        wbs_id=wbs.id,
        control_account_id=account.id,
        cbs_id=old_cbs.id,
        fbs_id=funding.id,
        code="LEGACY-BOUNDARY-CODE",
        budget=100,
        funds_available=100,
        forecast=100,
    )
    f.db.add(code)
    f.db.flush()
    line = BusinessProcessLineItem(
        **base,
        process_instance_id=process.id,
        line_type="cbs_wbs",
        wbs_id=wbs.id,
        cbs_id=old_cbs.id,
        control_account_id=account.id,
        cost_code_id=code.id,
        amount=100,
    )
    f.db.add(line)
    f.db.commit()
    response = request(
        f,
        "PATCH",
        f"/api/v1/projects/{f.legacy_project_id}/business-process-line-items/{line.id}",
        actor="admin",
        payload={"amount": 250, "change_note": "Must remain candidate-only after canonical adoption"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "CANONICAL_COST_AUTHORITY_REQUIRED"
    f.db.refresh(code)
    f.db.refresh(line)
    assert (code.budget, code.funds_available, code.forecast, line.amount) == (100, 100, 100, 100)
    assert not f.db.scalars(
        select(BusinessProcessLineItemRevision).where(
            BusinessProcessLineItemRevision.tenant_id == f.tenant_id,
            BusinessProcessLineItemRevision.line_item_id == line.id,
        )
    ).all()


def test_existing_apu_catalog_reused_as_source_only_and_get_has_no_business_writes(fixture):
    f = fixture
    source = ColombiaApuCatalogItem(
        tenant_id=f.tenant_id,
        project_id=f.legacy_project_id,
        source_key="existing-catalog",
        external_id="preserve-source",
        item_code="APU-EXISTING",
        item_name="Existing source rate",
        unit="m3",
        unit_rate=100.25,
        currency="COP",
    )
    f.db.add(source)
    f.db.commit()
    writes = []

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement)

    event.listen(f.db.bind, "before_cursor_execute", observe)
    try:
        result = success(request(f, "GET", "/legacy-candidates"))
    finally:
        event.remove(f.db.bind, "before_cursor_execute", observe)
    assert not writes
    row = next(row for row in result["apu_catalog"] if row["id"] == source.id)
    assert row["currency"] == "COP" and Decimal(str(row["unit_rate"])) == Decimal("100.25")
    assert result["budget_currency"] == "REQUIRED_EXPLICIT_BASIS"
    assert f.db.scalar(select(ColombiaApuCatalogItem.unit_rate).where(ColombiaApuCatalogItem.id == source.id)) == 100.25
    assert request(f, "GET", "/legacy-candidates", actor="foreign").status_code in {403, 404}
