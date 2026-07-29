# Multi-Tenant Guided Control Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a guided, multi-tenant project controls workflow where users always see tenant context, process state, blocking issues, and the next action after XER/XML upload.

**Architecture:** Add backend-owned guided flow state so React does not duplicate gating rules. Extend schedule ingestion to persist cost/currency evidence, then render it through focused frontend components: command bar, project drawer, process rail, next-action panel, and cost/currency gate.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, pytest, React, TypeScript, Zustand, Vitest, Playwright, Vite/Rolldown.

---

## Scope Check

The design spans backend data, parser behavior, one new API surface, and frontend UX. This is one cohesive feature because the frontend cannot become intuitive until the backend exposes the guided state and cost/currency facts. The plan is split into independently testable tasks with commits after each passing slice.

## File Map

### Backend

- Modify `backend/app/domain/models.py`
  Add tenant base currency and schedule import cost/currency metadata.
- Create `backend/alembic/versions/20260515_0018_guided_flow_currency.py`
  Add DB columns with safe defaults.
- Modify `backend/app/domain/schemas.py`
  Add guided-flow, tenant context, schedule import metadata, and currency confirmation schemas.
- Modify `backend/app/services/schedule_ingestion.py`
  Detect XER/XML currency, summarize cost source fields, persist cost-loaded counts and totals.
- Create `backend/app/services/guided_flow.py`
  Compute step states, next action, responsible role, and blocking counts.
- Modify `backend/app/api/v1/routers/projects.py`
  Add guided-flow endpoint and schedule currency confirmation endpoint.
- Modify `backend/app/database/seed.py`
  Seed tenant base currency and ensure demo data remains consistent.
- Add tests:
  `backend/tests/test_schedule_currency_costs.py`
  `backend/tests/test_guided_flow.py`

### Frontend

- Modify `frontend/src/types/index.ts`
  Add guided-flow, tenant context, schedule cost/currency metadata types.
- Modify `frontend/src/api/projects.ts`
  Add `guidedFlow()` and `confirmScheduleCurrency()`.
- Modify `frontend/src/App.tsx`
  Use backend guided state, move project creation out of rail, route active guided steps to existing views.
- Create `frontend/src/components/TenantCommandBar.tsx`
- Create `frontend/src/components/ProjectCreateDrawer.tsx`
- Create `frontend/src/components/GuidedProcessRail.tsx`
- Create `frontend/src/components/NextActionPanel.tsx`
- Create `frontend/src/components/CostCurrencyGate.tsx`
- Modify `frontend/src/styles.css`
  Add layouts for command bar, drawer, process rail, next action panel, and gate cards.
- Add/update tests:
  `frontend/tests/guided-flow-components.test.tsx`
  `frontend/tests/AppFlow.test.tsx`
  `frontend/e2e/production-readiness.spec.ts`

---

### Task 1: Persist Tenant And Schedule Cost/Currency Metadata

**Files:**
- Modify: `backend/app/domain/models.py`
- Create: `backend/alembic/versions/20260515_0018_guided_flow_currency.py`
- Modify: `backend/app/domain/schemas.py`
- Modify: `backend/app/database/seed.py`
- Test: `backend/tests/test_guided_flow.py`

- [ ] **Step 1: Write failing model/schema test**

Create `backend/tests/test_guided_flow.py` with:

```python
from app.domain.models import ScheduleImport, Tenant


def test_tenant_and_schedule_import_guided_metadata_defaults() -> None:
    tenant = Tenant(name="P&P MIS SAS", slug="pypmis")
    schedule_import = ScheduleImport(
        tenant_id=1,
        project_id=1,
        source="p6_xer",
        file_name="baseline.xer",
        status="validated",
    )

    assert tenant.base_currency == "COP"
    assert schedule_import.detected_currency == ""
    assert schedule_import.currency_confidence == "unknown"
    assert schedule_import.currency_source == ""
    assert schedule_import.currency_confirmed is False
    assert schedule_import.total_imported_cost == 0
    assert schedule_import.cost_loaded_activity_count == 0
    assert schedule_import.cost_loaded_activity_percent == 0
    assert schedule_import.cost_source_summary == {}
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
docker compose exec -T api pytest tests/test_guided_flow.py::test_tenant_and_schedule_import_guided_metadata_defaults -q
```

Expected: FAIL because `Tenant.base_currency` and schedule import metadata fields do not exist.

- [ ] **Step 3: Add model fields**

In `backend/app/domain/models.py`, update `Tenant`:

```python
class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(8), default="COP")
```

Update `ScheduleImport` with these columns near existing import metadata:

```python
    detected_currency: Mapped[str] = mapped_column(String(8), default="")
    currency_confidence: Mapped[str] = mapped_column(String(40), default="unknown")
    currency_source: Mapped[str] = mapped_column(String(160), default="")
    currency_confirmed: Mapped[bool] = mapped_column(default=False)
    total_imported_cost: Mapped[float] = mapped_column(Float, default=0)
    cost_loaded_activity_count: Mapped[int] = mapped_column(Integer, default=0)
    cost_loaded_activity_percent: Mapped[float] = mapped_column(Float, default=0)
    cost_source_summary: Mapped[dict] = mapped_column(JSON, default=dict)
```

- [ ] **Step 4: Add Alembic migration**

Create `backend/alembic/versions/20260515_0018_guided_flow_currency.py`:

```python
"""guided flow currency metadata

Revision ID: 20260515_0018
Revises: 20260514_0017
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260515_0018"
down_revision: str | None = "20260514_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("base_currency", sa.String(length=8), nullable=False, server_default="COP"))
    op.add_column("schedule_imports", sa.Column("detected_currency", sa.String(length=8), nullable=False, server_default=""))
    op.add_column(
        "schedule_imports",
        sa.Column("currency_confidence", sa.String(length=40), nullable=False, server_default="unknown"),
    )
    op.add_column("schedule_imports", sa.Column("currency_source", sa.String(length=160), nullable=False, server_default=""))
    op.add_column(
        "schedule_imports",
        sa.Column("currency_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "schedule_imports",
        sa.Column("total_imported_cost", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "schedule_imports",
        sa.Column("cost_loaded_activity_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "schedule_imports",
        sa.Column("cost_loaded_activity_percent", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "schedule_imports",
        sa.Column("cost_source_summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("schedule_imports", "cost_source_summary")
    op.drop_column("schedule_imports", "cost_loaded_activity_percent")
    op.drop_column("schedule_imports", "cost_loaded_activity_count")
    op.drop_column("schedule_imports", "total_imported_cost")
    op.drop_column("schedule_imports", "currency_confirmed")
    op.drop_column("schedule_imports", "currency_source")
    op.drop_column("schedule_imports", "currency_confidence")
    op.drop_column("schedule_imports", "detected_currency")
    op.drop_column("tenants", "base_currency")
```

- [ ] **Step 5: Extend schemas**

In `backend/app/domain/schemas.py`, update `ScheduleImportOut` to expose:

```python
    detected_currency: str = ""
    currency_confidence: str = "unknown"
    currency_source: str = ""
    currency_confirmed: bool = False
    total_imported_cost: float = 0
    cost_loaded_activity_count: int = 0
    cost_loaded_activity_percent: float = 0
    cost_source_summary: dict[str, object] = Field(default_factory=dict)
```

Add:

```python
class TenantContextOut(BaseModel):
    id: int
    name: str
    slug: str
    base_currency: str

    model_config = ConfigDict(from_attributes=True)


class ScheduleCurrencyConfirm(BaseModel):
    currency: str
```

- [ ] **Step 6: Seed tenant base currency**

In `backend/app/database/seed.py`, wherever the demo tenant is created or updated, set:

```python
tenant.base_currency = tenant.base_currency or "COP"
```

If the tenant is created inline, include `base_currency="COP"`.

- [ ] **Step 7: Run model/schema test**

Run:

```powershell
docker compose build api
docker compose up -d api
docker compose exec -T api pytest tests/test_guided_flow.py::test_tenant_and_schedule_import_guided_metadata_defaults -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add backend/app/domain/models.py backend/app/domain/schemas.py backend/app/database/seed.py backend/alembic/versions/20260515_0018_guided_flow_currency.py backend/tests/test_guided_flow.py
git commit -m "feat(backend): add guided flow currency metadata"
```

---

### Task 2: Detect XER Costs And Currency During Schedule Ingestion

**Files:**
- Modify: `backend/app/services/schedule_ingestion.py`
- Test: `backend/tests/test_schedule_currency_costs.py`

- [ ] **Step 1: Write failing parser test**

Create `backend/tests/test_schedule_currency_costs.py`:

```python
from app.services.schedule_ingestion import ScheduleIngestionService


def test_xer_detects_currency_and_resource_assignment_costs() -> None:
    content = "\n".join(
        [
            "%T\tPROJECT",
            "%F\tproj_id\tproj_short_name\tcurrency_id\tlast_recalc_date",
            "%R\t1\tPYP\tCOP\t2026-05-15 00:00",
            "%T\tPROJWBS",
            "%F\twbs_id\twbs_short_name\twbs_name",
            "%R\t10\tPLT-CIV\tCivil",
            "%T\tTASK",
            "%F\ttask_id\ttask_code\ttask_name\twbs_id\tearly_start_date\tearly_end_date\ttotal_float_hr_cnt",
            "%R\t100\tA100\tExcavacion\t10\t2026-05-01\t2026-05-10\t16",
            "%R\t101\tA101\tRelleno\t10\t2026-05-11\t2026-05-20\t24",
            "%T\tTASKRSRC",
            "%F\ttask_id\tplanned_qty\tunit_cost\tcurrency_id",
            "%R\t100\t5\t100000\tCOP",
        ]
    ).encode()

    parsed = ScheduleIngestionService(db=None).parse("baseline.xer", content)

    assert parsed.detected_currency == "COP"
    assert parsed.currency_confidence == "explicit"
    assert parsed.currency_source == "PROJECT.currency_id"
    assert parsed.total_imported_cost == 500000
    assert parsed.cost_loaded_activity_count == 1
    assert parsed.cost_loaded_activity_percent == 50
    assert parsed.cost_source_summary["TASKRSRC.unit_cost"] == 1
    assert any(finding.check_code == "PARTIAL_COST_LOADING" for finding in parsed.findings)
```

- [ ] **Step 2: Run failing parser test**

Run:

```powershell
docker compose exec -T api pytest tests/test_schedule_currency_costs.py::test_xer_detects_currency_and_resource_assignment_costs -q
```

Expected: FAIL because `ParsedSchedule` lacks currency/cost summary fields.

- [ ] **Step 3: Extend parse dataclasses**

In `backend/app/services/schedule_ingestion.py`, add:

```python
@dataclass(frozen=True)
class CostCurrencyEvidence:
    detected_currency: str = ""
    currency_confidence: str = "unknown"
    currency_source: str = ""
    total_imported_cost: float = 0
    cost_loaded_activity_count: int = 0
    cost_loaded_activity_percent: float = 0
    cost_source_summary: dict[str, int] | None = None
```

Extend `ParsedSchedule`:

```python
    detected_currency: str = ""
    currency_confidence: str = "unknown"
    currency_source: str = ""
    total_imported_cost: float = 0
    cost_loaded_activity_count: int = 0
    cost_loaded_activity_percent: float = 0
    cost_source_summary: dict[str, int] | None = None
```

- [ ] **Step 4: Track cost source fields**

Change `_planned_cost_from_row` to return both value and source:

```python
def _planned_cost_from_row_with_source(self, row: dict[str, str]) -> tuple[float, str]:
    for key in [
        "target_cost",
        "planned_cost",
        "planned_total_cost",
        "budgeted_cost",
        "budgeted_total_cost",
        "baseline_cost",
        "at_complete_cost",
        "at_complete_total_cost",
        "total_cost",
        "remain_cost",
        "remaining_cost",
        "actual_cost",
        "act_reg_cost",
        "act_ot_cost",
        "rem_late_start_cost",
    ]:
        value = self._money_to_float(row.get(key))
        if value:
            return value, key
    component_total = 0.0
    component_keys: list[str] = []
    for key in [
        "target_labor_cost",
        "target_equip_cost",
        "target_material_cost",
        "target_mat_cost",
        "target_expense_cost",
        "planned_labor_cost",
        "planned_equip_cost",
        "planned_material_cost",
        "budgeted_labor_cost",
        "budgeted_equip_cost",
        "budgeted_material_cost",
    ]:
        value = self._money_to_float(row.get(key))
        if value:
            component_total += value
            component_keys.append(key)
    if component_total:
        return component_total, "+".join(component_keys)
    quantity = self._first_float(row, ["target_qty", "planned_qty", "budgeted_units", "remaining_qty"])
    unit_cost = self._first_float(row, ["cost_per_qty", "unit_cost", "price_per_unit"])
    if quantity and unit_cost:
        return quantity * unit_cost, "quantity*unit_cost"
    return 0, ""
```

Keep `_planned_cost_from_row` as a wrapper:

```python
def _planned_cost_from_row(self, row: dict[str, str]) -> float:
    value, _source = self._planned_cost_from_row_with_source(row)
    return value
```

- [ ] **Step 5: Add currency detection helpers**

Add helpers:

```python
def _detect_xer_currency(self, rows_by_table: dict[str, list[dict[str, str]]]) -> tuple[str, str, str]:
    for table_name in ("PROJECT", "PROJPROP", "CURRTYPE"):
        for row in rows_by_table.get(table_name, []):
            for key in ("currency_id", "curr_id", "currency_code", "base_currency"):
                currency = self._normalize_currency(row.get(key))
                if currency:
                    return currency, "explicit", f"{table_name}.{key}"
    for table_name, rows in rows_by_table.items():
        for row in rows:
            for value in row.values():
                currency = self._currency_from_text(value)
                if currency:
                    return currency, "symbol", table_name
    return "", "unknown", ""

def _normalize_currency(self, value: str | None) -> str:
    cleaned = (value or "").strip().upper()
    aliases = {"COL": "COP", "PESO": "COP", "PESOS": "COP", "US$": "USD", "$US": "USD"}
    cleaned = aliases.get(cleaned, cleaned)
    return cleaned if len(cleaned) == 3 and cleaned.isalpha() else ""

def _currency_from_text(self, value: str | None) -> str:
    text = (value or "").upper()
    if "COP" in text or "COL$" in text:
        return "COP"
    if "USD" in text or "US$" in text:
        return "USD"
    if "EUR" in text:
        return "EUR"
    return ""
```

- [ ] **Step 6: Persist parse evidence**

In `ingest()`, set the new `ScheduleImport` fields:

```python
            detected_currency=parsed.detected_currency,
            currency_confidence=parsed.currency_confidence,
            currency_source=parsed.currency_source,
            currency_confirmed=parsed.currency_confidence == "explicit",
            total_imported_cost=parsed.total_imported_cost,
            cost_loaded_activity_count=parsed.cost_loaded_activity_count,
            cost_loaded_activity_percent=parsed.cost_loaded_activity_percent,
            cost_source_summary=parsed.cost_source_summary or {},
```

- [ ] **Step 7: Run tests**

Run:

```powershell
docker compose build api
docker compose up -d api
docker compose exec -T api pytest tests/test_schedule_currency_costs.py -q
docker compose exec -T api pytest tests/test_project_operational_setup_activity_sheet.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add backend/app/services/schedule_ingestion.py backend/tests/test_schedule_currency_costs.py
git commit -m "feat(backend): detect schedule cost currency"
```

---

### Task 3: Add Guided Flow Backend Service And Endpoints

**Files:**
- Create: `backend/app/services/guided_flow.py`
- Modify: `backend/app/domain/schemas.py`
- Modify: `backend/app/api/v1/routers/projects.py`
- Test: `backend/tests/test_guided_flow.py`

- [ ] **Step 1: Write failing endpoint test**

Append to `backend/tests/test_guided_flow.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ana.control@demo.local", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_guided_flow_reports_cost_currency_next_action() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    project = client.get("/api/v1/projects", headers=headers).json()[0]

    response = client.get(f"/api/v1/projects/{project['id']}/guided-flow", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["tenant"]["base_currency"]
    assert body["project"]["id"] == project["id"]
    assert any(step["key"] == "cost_currency" for step in body["steps"])
    assert body["next_action"]["key"] in {
        "load_schedule",
        "confirm_currency",
        "load_rates",
        "map_control_structures",
        "approve_baseline",
        "run_control_core",
    }
```

- [ ] **Step 2: Run failing endpoint test**

Run:

```powershell
docker compose exec -T api pytest tests/test_guided_flow.py::test_guided_flow_reports_cost_currency_next_action -q
```

Expected: FAIL with 404 for guided-flow endpoint.

- [ ] **Step 3: Add schemas**

In `backend/app/domain/schemas.py`, add:

```python
class GuidedFlowTenantOut(BaseModel):
    id: int
    name: str
    slug: str
    base_currency: str


class GuidedFlowProjectOut(BaseModel):
    id: int
    code: str
    name: str
    currency: str
    status: str


class GuidedFlowStepOut(BaseModel):
    key: str
    label: str
    state: str
    summary: str
    primary_action: str
    responsible_role: str
    blocking_count: int = 0
    target_view: str


class GuidedFlowNextActionOut(BaseModel):
    key: str
    label: str
    target_view: str
    disabled: bool = False


class GuidedFlowOut(BaseModel):
    tenant: GuidedFlowTenantOut
    project: GuidedFlowProjectOut
    steps: list[GuidedFlowStepOut]
    next_action: GuidedFlowNextActionOut
```

- [ ] **Step 4: Implement service**

Create `backend/app/services/guided_flow.py`:

```python
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import (
    Activity,
    BaselineVersion,
    ControlAccount,
    CostBreakdownStructure,
    FundingSource,
    Project,
    ScheduleImport,
    Tenant,
)
from app.domain.schemas import (
    GuidedFlowNextActionOut,
    GuidedFlowOut,
    GuidedFlowProjectOut,
    GuidedFlowStepOut,
    GuidedFlowTenantOut,
)

COST_LOADING_READY_PERCENT = 80.0


class GuidedFlowService:
    def __init__(self, db: Session):
        self.db = db

    def build(self, tenant_id: int, project_id: int) -> GuidedFlowOut:
        tenant = self.db.get(Tenant, tenant_id)
        project = self.db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
        if not tenant or not project:
            raise ValueError("Project not found")
        latest_import = self.db.scalar(
            select(ScheduleImport)
            .where(ScheduleImport.tenant_id == tenant_id, ScheduleImport.project_id == project_id)
            .order_by(ScheduleImport.imported_at.desc(), ScheduleImport.id.desc())
        )
        activity_count = self._count(Activity, tenant_id, project_id)
        control_account_count = self._count(ControlAccount, tenant_id, project_id)
        cbs_count = self._count(CostBreakdownStructure, tenant_id, project_id)
        fbs_count = self._count(FundingSource, tenant_id, project_id)
        baseline_count = self._count(BaselineVersion, tenant_id, project_id)

        cost_state = self._cost_state(latest_import)
        steps = [
            self._step("tenant", "Tenant workspace", "ready", tenant.name, "Review tenant", "Tenant Admin", "dashboard"),
            self._step("project_setup", "Project setup", "ready", project.code, "Review setup", "Control Manager", "setup"),
            self._step(
                "schedule_upload",
                "Schedule upload",
                "ready" if latest_import else "blocked",
                latest_import.file_name if latest_import else "No schedule uploaded",
                "Load XER/XML schedule" if not latest_import else "Review schedule",
                "Planner",
                "baseline",
            ),
            self._step(
                "cost_currency",
                "Cost and currency gate",
                cost_state,
                self._cost_summary(latest_import, project.currency),
                self._cost_action(latest_import),
                "Control Manager",
                "integrated-control",
                self._cost_blocking_count(latest_import),
            ),
            self._step(
                "mapping",
                "WBS/CBS/FBS mapping",
                "ready" if control_account_count and cbs_count and fbs_count else "review_required",
                f"{control_account_count} control accounts, {cbs_count} CBS, {fbs_count} FBS",
                "Map control structures",
                "Control Manager",
                "integrated-control",
            ),
            self._step(
                "baseline",
                "Baseline approval",
                "ready" if baseline_count and cost_state == "ready" else "blocked",
                f"{baseline_count} baseline version(s)",
                "Approve baseline",
                "Control Manager",
                "baseline",
                0 if baseline_count and cost_state == "ready" else 1,
            ),
            self._step("progress", "Progress capture", "in_progress", f"{activity_count} activities", "Capture progress", "Planner", "progress"),
            self._step("actual_costs", "Actual costs", "in_progress", "Contracts, POs, actas and warehouse receipts", "Capture actual costs", "Cost Engineer", "costs"),
            self._step("control_core", "Control Core", "in_progress", "SPI/CPI/forecast", "Run Control Core", "Control Manager", "dashboard"),
            self._step("awp", "AWP packaging", "review_required", "Packages and constraints", "Create draft AWP packages", "AWP Lead", "work-packages"),
            self._step("evidence", "Evidence", "in_progress", "Documents and reviews", "Review evidence", "Document Controller", "evidence"),
            self._step("closeout", "Closeout", "not_started", "Open commitments and final documents", "Prepare closeout", "Project Manager", "dashboard"),
        ]
        next_step = next((step for step in steps if step.state in {"blocked", "review_required", "in_progress"}), steps[-1])
        return GuidedFlowOut(
            tenant=GuidedFlowTenantOut(id=tenant.id, name=tenant.name, slug=tenant.slug, base_currency=tenant.base_currency),
            project=GuidedFlowProjectOut(id=project.id, code=project.code, name=project.name, currency=project.currency, status=project.status),
            steps=steps,
            next_action=GuidedFlowNextActionOut(
                key=next_step.key,
                label=next_step.primary_action,
                target_view=next_step.target_view,
                disabled=next_step.state == "blocked",
            ),
        )

    def _step(self, key: str, label: str, state: str, summary: str, action: str, role: str, target: str, blocking: int = 0) -> GuidedFlowStepOut:
        return GuidedFlowStepOut(key=key, label=label, state=state, summary=summary, primary_action=action, responsible_role=role, target_view=target, blocking_count=blocking)
```

Add helper methods `_count`, `_cost_state`, `_cost_summary`, `_cost_action`, `_cost_blocking_count` in the same file:

```python
    def _count(self, model: type, tenant_id: int, project_id: int) -> int:
        return int(self.db.scalar(select(func.count(model.id)).where(model.tenant_id == tenant_id, model.project_id == project_id)) or 0)

    def _cost_state(self, latest_import: ScheduleImport | None) -> str:
        if not latest_import:
            return "blocked"
        if not latest_import.detected_currency or not latest_import.currency_confirmed:
            return "review_required"
        if latest_import.cost_loaded_activity_percent >= COST_LOADING_READY_PERCENT:
            return "ready"
        return "review_required" if latest_import.cost_loaded_activity_count else "blocked"
```


- [ ] **Step 5: Add endpoints**

In `backend/app/api/v1/routers/projects.py`, import the service and schemas:

```python
from app.domain.schemas import GuidedFlowOut, ScheduleCurrencyConfirm
from app.services.guided_flow import GuidedFlowService
```

Add endpoint:

```python
@router.get("/projects/{project_id}/guided-flow", response_model=GuidedFlowOut)
def get_guided_flow(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> GuidedFlowOut:
    _require_membership(db, tenant_id, project_id, user_id)
    return GuidedFlowService(db).build(tenant_id, project_id)
```

- [ ] **Step 6: Run endpoint tests**

Run:

```powershell
docker compose build api
docker compose up -d api
docker compose exec -T api pytest tests/test_guided_flow.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/services/guided_flow.py backend/app/domain/schemas.py backend/app/api/v1/routers/projects.py backend/tests/test_guided_flow.py
git commit -m "feat(backend): expose guided project flow"
```

---

### Task 4: Add Currency Confirmation Endpoint

**Files:**
- Modify: `backend/app/api/v1/routers/projects.py`
- Modify: `backend/app/domain/schemas.py`
- Test: `backend/tests/test_guided_flow.py`

- [ ] **Step 1: Write failing confirmation test**

Append:

```python
def test_confirm_schedule_currency_updates_import_and_project() -> None:
    client = TestClient(app)
    headers = _auth_headers(client)
    project = client.get("/api/v1/projects", headers=headers).json()[0]
    imports = client.get(f"/api/v1/projects/{project['id']}/schedule-imports", headers=headers).json()
    schedule_import = imports[0]

    response = client.post(
        f"/api/v1/projects/{project['id']}/schedule-imports/{schedule_import['id']}/confirm-currency",
        headers=headers,
        json={"currency": "COP"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["detected_currency"] == "COP"
    assert body["currency_confirmed"] is True
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
docker compose exec -T api pytest tests/test_guided_flow.py::test_confirm_schedule_currency_updates_import_and_project -q
```

Expected: FAIL with 404.

- [ ] **Step 3: Implement endpoint**

In `backend/app/api/v1/routers/projects.py`, add:

```python
@router.post("/projects/{project_id}/schedule-imports/{schedule_import_id}/confirm-currency", response_model=ScheduleImportOut)
def confirm_schedule_currency(
    project_id: int,
    schedule_import_id: int,
    payload: ScheduleCurrencyConfirm,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ScheduleImport:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot confirm schedule currency")
    currency = payload.currency.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise HTTPException(status_code=400, detail="Currency must be a three-letter ISO code")
    schedule_import = db.scalar(
        select(ScheduleImport).where(
            ScheduleImport.tenant_id == tenant_id,
            ScheduleImport.project_id == project_id,
            ScheduleImport.id == schedule_import_id,
        )
    )
    if not schedule_import:
        raise HTTPException(status_code=404, detail="Schedule import not found")
    project = _require_project(db, tenant_id, project_id)
    schedule_import.detected_currency = currency
    schedule_import.currency_confirmed = True
    schedule_import.currency_confidence = schedule_import.currency_confidence or "project_default"
    schedule_import.currency_source = schedule_import.currency_source or "user_confirmation"
    project.currency = currency
    db.commit()
    db.refresh(schedule_import)
    return schedule_import
```

- [ ] **Step 4: Run confirmation tests**

Run:

```powershell
docker compose build api
docker compose up -d api
docker compose exec -T api pytest tests/test_guided_flow.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/api/v1/routers/projects.py backend/app/domain/schemas.py backend/tests/test_guided_flow.py
git commit -m "feat(backend): confirm schedule currency"
```

---

### Task 5: Add Frontend API Types And Client Methods

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/projects.ts`
- Test: `frontend/tests/api-client.test.ts`

- [ ] **Step 1: Write failing API type test**

Append to `frontend/tests/api-client.test.ts`:

```typescript
import { projects } from "../src/api/projects";

it("requests guided flow for a project", async () => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => ({
      tenant: { id: 1, name: "P&P MIS SAS", slug: "pypmis", base_currency: "COP" },
      project: { id: 1, code: "CTRL", name: "Control", currency: "COP", status: "draft" },
      steps: [],
      next_action: { key: "load_schedule", label: "Load XER/XML schedule", target_view: "baseline", disabled: false },
    }),
  }) as unknown as typeof fetch;

  await projects.guidedFlow("tok", 1);

  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining("/api/v1/projects/1/guided-flow"),
    expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer tok" }) }),
  );
});
```

- [ ] **Step 2: Run failing frontend test**

Run:

```powershell
docker compose exec -T frontend npm run test -- tests/api-client.test.ts
```

Expected: FAIL because `projects.guidedFlow` does not exist.

- [ ] **Step 3: Add TypeScript types**

In `frontend/src/types/index.ts`, add:

```typescript
export type GuidedFlowStepState = "not_started" | "in_progress" | "review_required" | "ready" | "blocked" | "complete";

export type GuidedFlowStep = {
  key: string;
  label: string;
  state: GuidedFlowStepState;
  summary: string;
  primary_action: string;
  responsible_role: string;
  blocking_count: number;
  target_view: string;
};

export type GuidedFlow = {
  tenant: { id: number; name: string; slug: string; base_currency: string };
  project: { id: number; code: string; name: string; currency: string; status: string };
  steps: GuidedFlowStep[];
  next_action: { key: string; label: string; target_view: string; disabled: boolean };
};
```

Extend `ScheduleImport` type with:

```typescript
  detected_currency: string;
  currency_confidence: string;
  currency_source: string;
  currency_confirmed: boolean;
  total_imported_cost: number;
  cost_loaded_activity_count: number;
  cost_loaded_activity_percent: number;
  cost_source_summary: Record<string, unknown>;
```

- [ ] **Step 4: Add client methods**

In `frontend/src/api/projects.ts`, import `GuidedFlow` and add:

```typescript
  guidedFlow: (token: string, projectId: number) =>
    apiFetch<GuidedFlow>(`/api/v1/projects/${projectId}/guided-flow`, { token }),

  confirmScheduleCurrency: (token: string, projectId: number, scheduleImportId: number, currency: string) =>
    apiFetch<ScheduleImport>(`/api/v1/projects/${projectId}/schedule-imports/${scheduleImportId}/confirm-currency`, {
      method: "POST",
      token,
      body: JSON.stringify({ currency }),
    }),
```

- [ ] **Step 5: Run frontend API test**

Run:

```powershell
docker compose build frontend
docker compose up -d frontend
docker compose exec -T frontend npm run test -- tests/api-client.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/types/index.ts frontend/src/api/projects.ts frontend/tests/api-client.test.ts
git commit -m "feat(frontend): add guided flow client"
```

---

### Task 6: Implement Guided UX Components

**Files:**
- Create: `frontend/src/components/TenantCommandBar.tsx`
- Create: `frontend/src/components/ProjectCreateDrawer.tsx`
- Create: `frontend/src/components/GuidedProcessRail.tsx`
- Create: `frontend/src/components/NextActionPanel.tsx`
- Create: `frontend/src/components/CostCurrencyGate.tsx`
- Test: `frontend/tests/guided-flow-components.test.tsx`

- [ ] **Step 1: Write failing component tests**

Create `frontend/tests/guided-flow-components.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import GuidedProcessRail from "../src/components/GuidedProcessRail";
import NextActionPanel from "../src/components/NextActionPanel";
import TenantCommandBar from "../src/components/TenantCommandBar";

const steps = [
  {
    key: "cost_currency",
    label: "Cost and currency gate",
    state: "review_required" as const,
    summary: "50% activities cost-loaded",
    primary_action: "Confirm detected currency",
    responsible_role: "Control Manager",
    blocking_count: 2,
    target_view: "integrated-control",
  },
];

it("shows tenant and project context with project creation action", () => {
  const onCreateProject = vi.fn();
  render(
    <TenantCommandBar
      tenant={{ id: 1, name: "P&P MIS SAS", slug: "pypmis", base_currency: "COP" }}
      project={{ id: 1, code: "CTRL", name: "Control", currency: "COP", status: "draft" }}
      projects={[{ id: 1, code: "CTRL", name: "Control", currency: "COP" }]}
      selectedProjectId={1}
      onProjectChange={vi.fn()}
      onCreateProject={onCreateProject}
      userEmail="ana.control@demo.local"
      onLogout={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: /new project/i }));
  expect(onCreateProject).toHaveBeenCalled();
  expect(screen.getByText(/P&P MIS SAS/i)).toBeInTheDocument();
});

it("renders guided rail step state and next action", () => {
  const onNavigate = vi.fn();
  render(<GuidedProcessRail activeKey="cost_currency" steps={steps} onNavigate={onNavigate} />);
  fireEvent.click(screen.getByRole("button", { name: /cost and currency gate/i }));
  expect(onNavigate).toHaveBeenCalledWith("integrated-control");
  expect(screen.getByText(/review_required/i)).toBeInTheDocument();
});

it("renders next action responsible role and disabled state", () => {
  render(
    <NextActionPanel
      action={{ key: "confirm_currency", label: "Confirm detected currency", target_view: "integrated-control", disabled: false }}
      step={steps[0]}
      onNavigate={vi.fn()}
    />,
  );
  expect(screen.getByText(/Control Manager/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /confirm detected currency/i })).toBeEnabled();
});
```

- [ ] **Step 2: Run failing component tests**

Run:

```powershell
docker compose exec -T frontend npm run test -- tests/guided-flow-components.test.tsx
```

Expected: FAIL because components do not exist.

- [ ] **Step 3: Implement components**

Create `TenantCommandBar.tsx`:

```tsx
import type { Project } from "../types";

type Tenant = { id: number; name: string; slug: string; base_currency: string };
type ProjectSummary = Pick<Project, "id" | "code" | "name" | "currency">;

export default function TenantCommandBar({
  tenant,
  project,
  projects,
  selectedProjectId,
  onProjectChange,
  onCreateProject,
  userEmail,
  onLogout,
}: {
  tenant: Tenant;
  project: { id: number; code: string; name: string; currency: string; status: string };
  projects: ProjectSummary[];
  selectedProjectId: number;
  onProjectChange: (projectId: number) => void;
  onCreateProject: () => void;
  userEmail: string;
  onLogout: () => void;
}) {
  return (
    <header className="tenantCommandBar">
      <div>
        <span>Tenant</span>
        <strong>{tenant.name}</strong>
        <small>{tenant.slug} / base {tenant.base_currency}</small>
      </div>
      <label>
        <span>Project</span>
        <select onChange={(event) => onProjectChange(Number(event.target.value))} value={selectedProjectId}>
          {projects.map((item) => (
            <option key={item.id} value={item.id}>
              {item.code} / {item.currency}
            </option>
          ))}
        </select>
      </label>
      <strong>{project.name}</strong>
      <button className="workflowAction primary" onClick={onCreateProject} type="button">
        New Project
      </button>
      <button className="quickNavButton" onClick={onLogout} type="button">
        {userEmail}
      </button>
    </header>
  );
}
```

Create `GuidedProcessRail.tsx`:

```tsx
import type { GuidedFlowStep } from "../types";

export default function GuidedProcessRail({
  activeKey,
  steps,
  onNavigate,
}: {
  activeKey: string;
  steps: GuidedFlowStep[];
  onNavigate: (targetView: string) => void;
}) {
  return (
    <aside className="guidedProcessRail" aria-label="Guided control flow">
      <div className="navigatorHeader">
        <strong>Guided Flow</strong>
        <span>Process state</span>
      </div>
      {steps.map((step) => (
        <button
          aria-current={activeKey === step.key || activeKey === step.target_view ? "page" : undefined}
          className={activeKey === step.key || activeKey === step.target_view ? "navigatorItem active" : "navigatorItem"}
          key={step.key}
          onClick={() => onNavigate(step.target_view)}
          type="button"
        >
          <span>{step.label}</span>
          <strong>{step.state}</strong>
        </button>
      ))}
    </aside>
  );
}
```

Create `NextActionPanel.tsx`:

```tsx
import type { GuidedFlow, GuidedFlowStep } from "../types";

export default function NextActionPanel({
  action,
  step,
  onNavigate,
}: {
  action: GuidedFlow["next_action"];
  step: GuidedFlowStep;
  onNavigate: (targetView: string) => void;
}) {
  return (
    <aside className="nextActionPanel" aria-label="Next action">
      <span>Next action</span>
      <h2>{action.label}</h2>
      <p>{step.summary}</p>
      <dl>
        <div>
          <dt>Responsible role</dt>
          <dd>{step.responsible_role}</dd>
        </div>
        <div>
          <dt>Blocking items</dt>
          <dd>{step.blocking_count}</dd>
        </div>
      </dl>
      <button
        className="workflowAction primary"
        disabled={action.disabled}
        onClick={() => onNavigate(action.target_view)}
        type="button"
      >
        {action.label}
      </button>
    </aside>
  );
}
```

Create `CostCurrencyGate.tsx`:

```tsx
import type { ScheduleImport } from "../types";

export default function CostCurrencyGate({
  scheduleImport,
  projectCurrency,
  pending,
  onConfirmCurrency,
}: {
  scheduleImport: ScheduleImport;
  projectCurrency: string;
  pending: boolean;
  onConfirmCurrency: (currency: string) => void;
}) {
  const currency = scheduleImport.detected_currency || projectCurrency;
  return (
    <section className="costCurrencyGate" aria-label="Cost and currency gate">
      <div className="panelHeader">
        <h2>Cost and currency gate</h2>
        <span>{scheduleImport.currency_confirmed ? "Confirmed" : "Review required"}</span>
      </div>
      <div className="controlSummary">
        <div>
          <span>Currency</span>
          <strong>{currency || "Unknown"}</strong>
        </div>
        <div>
          <span>Confidence</span>
          <strong>{scheduleImport.currency_confidence}</strong>
        </div>
        <div>
          <span>Cost loaded</span>
          <strong>{scheduleImport.cost_loaded_activity_percent.toFixed(1)}%</strong>
        </div>
        <div>
          <span>Total imported cost</span>
          <strong>{scheduleImport.total_imported_cost.toLocaleString()}</strong>
        </div>
      </div>
      <p>{scheduleImport.cost_loaded_activity_count} cost-loaded activities from {scheduleImport.file_name}.</p>
      <button
        className="workflowAction primary"
        disabled={pending || !currency || scheduleImport.currency_confirmed}
        onClick={() => onConfirmCurrency(currency)}
        type="button"
      >
        Confirm {currency || "currency"}
      </button>
    </section>
  );
}
```

Create `ProjectCreateDrawer.tsx` with the current project-create form moved out of `App.tsx` and this contract:

```tsx
import type { FormEvent } from "react";

type ProjectDraft = {
  calendar_base: string;
  code: string;
  control_level: string;
  funding_required: boolean;
  authorization_date: string;
  authorization_ref: string;
  name: string;
  owner: string;
  phase: string;
  currency: string;
  status: string;
  start_date: string;
  finish_date: string;
};

export default function ProjectCreateDrawer({
  canConfigure,
  draft,
  error,
  message,
  open,
  pending,
  onClose,
  onDraftChange,
  onSubmit,
}: {
  canConfigure: boolean;
  draft: ProjectDraft;
  error: string | null;
  message: string | null;
  open: boolean;
  pending: boolean;
  onClose: () => void;
  onDraftChange: (draft: ProjectDraft) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  if (!open) return null;
  const setField = <K extends keyof ProjectDraft>(key: K, value: ProjectDraft[K]) => {
    onDraftChange({ ...draft, [key]: value });
  };
  return (
    <aside className="projectCreateDrawer" aria-label="Create project">
      <div className="panelHeader">
        <h2>Create project</h2>
        <button className="quickNavButton" onClick={onClose} type="button">Close</button>
      </div>
      <form className="projectCreateForm" onSubmit={onSubmit}>
        <label><span>Code</span><input disabled={!canConfigure || pending} required value={draft.code} onChange={(event) => setField("code", event.target.value)} /></label>
        <label><span>Name</span><input disabled={!canConfigure || pending} required value={draft.name} onChange={(event) => setField("name", event.target.value)} /></label>
        <label><span>Currency</span><input disabled={!canConfigure || pending} maxLength={3} value={draft.currency} onChange={(event) => setField("currency", event.target.value.toUpperCase())} /></label>
        <label><span>Owner</span><input disabled={!canConfigure || pending} value={draft.owner} onChange={(event) => setField("owner", event.target.value)} /></label>
        <label><span>Authorization Reference</span><input disabled={!canConfigure || pending} value={draft.authorization_ref} onChange={(event) => setField("authorization_ref", event.target.value)} /></label>
        <label><span>Authorization Date</span><input disabled={!canConfigure || pending} type="date" value={draft.authorization_date} onChange={(event) => setField("authorization_date", event.target.value)} /></label>
        <button className="workflowAction primary" disabled={!canConfigure || pending} type="submit">{pending ? "Creating..." : "Create Project"}</button>
      </form>
      {message && <div className="uploadMessage success">{message}</div>}
      {error && <div className="uploadMessage error">{error}</div>}
    </aside>
  );
}
```

- [ ] **Step 4: Run component tests**

Run:

```powershell
docker compose build frontend
docker compose up -d frontend
docker compose exec -T frontend npm run test -- tests/guided-flow-components.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/TenantCommandBar.tsx frontend/src/components/ProjectCreateDrawer.tsx frontend/src/components/GuidedProcessRail.tsx frontend/src/components/NextActionPanel.tsx frontend/src/components/CostCurrencyGate.tsx frontend/tests/guided-flow-components.test.tsx
git commit -m "feat(frontend): add guided flow components"
```

---

### Task 7: Wire Guided Flow Into App Workspace

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/tests/AppFlow.test.tsx`
- Modify: `frontend/e2e/production-readiness.spec.ts`

- [ ] **Step 1: Write failing AppFlow test**

In `frontend/tests/AppFlow.test.tsx`, mock `projects.guidedFlow` and add:

```tsx
it("shows tenant command bar and post-upload cost currency next action", async () => {
  guidedFlow.mockResolvedValue({
    tenant: { id: 1, name: "P&P MIS SAS", slug: "pypmis", base_currency: "COP" },
    project: { id: 1, code: "CTRL-DEMO-001", name: "Piloto vial AWP", currency: "COP", status: "draft" },
    steps: [
      {
        key: "cost_currency",
        label: "Cost and currency gate",
        state: "review_required",
        summary: "50% activities cost-loaded; currency inferred from project COP.",
        primary_action: "Confirm detected currency",
        responsible_role: "Control Manager",
        blocking_count: 2,
        target_view: "integrated-control",
      },
    ],
    next_action: { key: "confirm_currency", label: "Confirm detected currency", target_view: "integrated-control", disabled: false },
  });

  render(
    <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
      <App />
    </MemoryRouter>,
  );

  expect(await screen.findByText(/P&P MIS SAS/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /new project/i })).toBeInTheDocument();
  expect(screen.getByText(/cost and currency gate/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /confirm detected currency/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run failing AppFlow test**

Run:

```powershell
docker compose exec -T frontend npm run test -- tests/AppFlow.test.tsx
```

Expected: FAIL because `App` does not load/render guided flow.

- [ ] **Step 3: Add App state and refresh**

In `frontend/src/App.tsx`, import components and types. Add state:

```tsx
const [guidedFlow, setGuidedFlow] = useState<GuidedFlow | null>(null);
const [projectDrawerOpen, setProjectDrawerOpen] = useState(false);
```

Add loader:

```tsx
async function refreshGuidedFlow(projectId: number) {
  if (!token) return;
  const flow = await projectsApi.guidedFlow(token, projectId);
  setGuidedFlow(flow);
}
```

Call `refreshGuidedFlow(projectId)` after:

- project list load selects a project
- `refreshDashboard(projectId)`
- schedule upload
- activity sheet load
- currency confirmation
- baseline approval
- AWP package generation

- [ ] **Step 4: Replace header and project panel**

Render `TenantCommandBar` at the top when `guidedFlow` exists. Remove the project create panel from `.projectWorkspaceRail`; keep the process rail only.

Render:

```tsx
{guidedFlow && (
  <TenantCommandBar
    tenant={guidedFlow.tenant}
    project={guidedFlow.project}
    projects={projectList}
    selectedProjectId={selectedProjectId ?? project.id}
    onProjectChange={setSelectedProject}
    onCreateProject={() => setProjectDrawerOpen(true)}
    userEmail={user?.email ?? "Signed in"}
    onLogout={logout}
  />
)}
<ProjectCreateDrawer
  canConfigure={canConfigure}
  draft={projectDraft}
  error={projectError}
  message={projectMessage}
  open={projectDrawerOpen}
  pending={projectAction}
  onClose={() => setProjectDrawerOpen(false)}
  onDraftChange={setProjectDraft}
  onSubmit={handleProjectCreate}
/>
```

- [ ] **Step 5: Render guided rail and next action**

Replace `controlFlowItems` rail with:

```tsx
{guidedFlow && (
  <GuidedProcessRail
    activeKey={activeControlView}
    steps={guidedFlow.steps}
    onNavigate={(targetView) => handleControlFlowNavigate(targetView as ControlFlowView)}
  />
)}
```

Render `NextActionPanel` beside the main content:

```tsx
{guidedFlow && (
  <NextActionPanel
    action={guidedFlow.next_action}
    step={guidedFlow.steps.find((step) => step.key === guidedFlow.next_action.key) ?? guidedFlow.steps[0]}
    onNavigate={(targetView) => handleControlFlowNavigate(targetView as ControlFlowView)}
  />
)}
```

- [ ] **Step 6: Add CostCurrencyGate in Integrated Control or Baseline area**

Use latest import:

```tsx
const activeImport = dashboard.schedule_import;
```

Render `CostCurrencyGate` before schedule/control tables when `activeImport` exists. Wire confirm:

```tsx
async function handleConfirmCurrency(currency: string) {
  if (!token || !selectedProjectId || !activeImport) return;
  await projectsApi.confirmScheduleCurrency(token, selectedProjectId, activeImport.id, currency);
  await refreshDashboard(selectedProjectId);
  await refreshGuidedFlow(selectedProjectId);
}
```

- [ ] **Step 7: Add CSS**

In `frontend/src/styles.css`, add:

```css
.tenantCommandBar {
  align-items: center;
  background: #17212b;
  color: #fff;
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(220px, 1fr) minmax(180px, 260px) minmax(180px, 1fr) auto auto;
  padding: 14px 18px;
}

.projectCreateDrawer {
  background: #fff;
  border-left: 1px solid #d8dee5;
  bottom: 0;
  box-shadow: -18px 0 32px rgba(23, 33, 43, 0.16);
  display: grid;
  gap: 14px;
  max-width: 520px;
  overflow-y: auto;
  padding: 18px;
  position: fixed;
  right: 0;
  top: 0;
  width: min(520px, 94vw);
  z-index: 50;
}

.guidedWorkspace {
  display: grid;
  gap: 14px;
  grid-template-columns: 250px minmax(0, 1fr) 300px;
}
```

- [ ] **Step 8: Run AppFlow and E2E tests**

Run:

```powershell
docker compose build frontend
docker compose up -d frontend
docker compose exec -T frontend npm run test -- tests/AppFlow.test.tsx
docker compose exec -T -e E2E_API_URL=http://api:8000 frontend npm run test:e2e
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add frontend/src/App.tsx frontend/src/styles.css frontend/tests/AppFlow.test.tsx frontend/e2e/production-readiness.spec.ts
git commit -m "feat(frontend): wire guided mission control flow"
```

---

### Task 8: Final Verification And Documentation

**Files:**
- Modify: `docs/24-operacion-productiva-formal.md`
- Optional Modify: `docs/Manual_Uso_App_Pypmis_Ai_SaaS_2026-05-15.pdf` only if regenerating manuals in the existing document workflow.

- [ ] **Step 1: Update operating doc**

In `docs/24-operacion-productiva-formal.md`, add a section:

```markdown
## Flujo guiado multi-tenant

El usuario opera dentro de un tenant visible. La app guia el proceso desde proyecto hasta cierre:
tenant, proyecto, cronograma, costos y moneda, WBS/CBS/FBS, baseline, progreso, costos reales, Control Core, AWP, evidencia y cierre.

Despues de cargar XER/XML, el gate de costos y moneda muestra moneda detectada, fuente de deteccion, porcentaje cost-loaded, costo total importado, actividades sin costo y siguiente accion.
```

- [ ] **Step 2: Run full backend verification**

Run:

```powershell
docker compose exec -T api ruff check .
docker compose exec -T api pytest
docker compose exec -T api alembic current
```

Expected:

- ruff: `All checks passed!`
- pytest: all tests passed
- alembic: `20260515_0018 (head)`

- [ ] **Step 3: Run full frontend verification**

Run:

```powershell
docker compose exec -T frontend npm run lint -- --max-warnings=0
docker compose exec -T frontend npm run build
docker compose exec -T frontend npm run test
docker compose exec -T -e E2E_API_URL=http://api:8000 frontend npm run test:e2e
```

Expected: all pass, no ESLint warnings, no chunk warning above current build threshold.

- [ ] **Step 4: Run smoke**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\smoke_check.ps1
```

Expected: health, readiness, authenticated user, projects, dashboard, Cost Manager, RFQ, document control, pilot readiness, and frontend all OK.

- [ ] **Step 5: Commit docs and final polish**

```powershell
git add docs/24-operacion-productiva-formal.md
git commit -m "docs: document guided multi-tenant flow"
```

- [ ] **Step 6: Final status**

Run:

```powershell
git status --short --branch
git log --oneline -8
```

Expected: clean worktree, branch ahead by the new guided-flow commits.
