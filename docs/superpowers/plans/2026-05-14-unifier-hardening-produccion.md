# Unifier Hardening Produccion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Endurecer los procesos Unifier MVP para operacion productiva con aprobaciones configurables, permisos por BP, versionado de line items, export de conciliacion, historico de recost y pruebas visuales focalizadas.

**Architecture:** Mantener el patron actual del backend monolitico en `backend/app/api/v1/router.py` para minimizar riesgo, agregando modelos transaccionales compactos y endpoints REST alrededor de los procesos ya creados. En frontend, extender `Integrated Control` sin redisenar la navegacion.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, React/Vite, Vitest, Docker Compose.

---

### Task 1: Backend Hardening Regression Tests

**Files:**
- Modify: `backend/tests/test_unifier_priority_flow.py`

- [x] **Step 1: Add failing assertions for BP policy, line item versioning, exports and recost history**

Add a second test that:
- Creates the same ready project fixture.
- Creates BP CBS-WBS.
- Reads BP line items.
- Rejects editing a line with a stale expected version.
- Edits the line with a current expected version and receives version +1.
- Creates a BP approval policy requiring `Control Manager` for approval.
- Verifies current demo user can approve the process.
- Exports reconciliation as CSV and PDF.
- Runs recost and checks history exists.

- [x] **Step 2: Run focused backend test and verify RED**

Run:

```powershell
docker compose build api
docker compose run --rm api pytest tests/test_unifier_priority_flow.py -q
```

Expected: failing because endpoints/models do not exist yet.

### Task 2: Backend Schema and Models

**Files:**
- Modify: `backend/app/domain/models.py`
- Modify: `backend/app/domain/schemas.py`
- Create: `backend/alembic/versions/20260514_0016_unifier_hardening_production.py`

- [x] **Step 1: Add models**

Add:
- `BusinessProcessPolicy`: process code, action, required role, permission key, active flag.
- `BusinessProcessLineItemRevision`: immutable snapshot of line item edits.
- `ActivitySheetRecostRun`: recost run summary.
- `ActivitySheetRecostRunLine`: row-level recost delta.

- [x] **Step 2: Add schemas**

Add create/out/update schemas for BP policy, BP line item edit, line item revision, recost run and export metadata.

- [x] **Step 3: Add Alembic migration**

Create idempotent tables with foreign keys to existing process, line item, activity sheet, rate sheet and activity row tables.

### Task 3: Backend Endpoints and Services

**Files:**
- Modify: `backend/app/api/v1/router.py`

- [x] **Step 1: BP policy endpoints**

Add:
- `GET /projects/{project_id}/business-process-policies`
- `POST /projects/{project_id}/business-process-policies`

- [x] **Step 2: Permission enforcement**

Extend workflow action permission lookup so process-specific policy overrides template transition permissions.

- [x] **Step 3: Line item endpoints**

Add:
- `GET /projects/{project_id}/business-processes/{process_id}/line-items`
- `PATCH /projects/{project_id}/business-process-line-items/{line_item_id}`
- `GET /projects/{project_id}/business-process-line-items/{line_item_id}/revisions`

- [x] **Step 4: Reconciliation export endpoints**

Add:
- `GET /projects/{project_id}/reconciliation-report/export?format=csv`
- `GET /projects/{project_id}/reconciliation-report/export?format=pdf`

- [x] **Step 5: Recost history**

Update recost endpoint to create run + run line records and add:
- `GET /projects/{project_id}/activity-sheets/{activity_sheet_id}/recost-runs`

### Task 4: Frontend Operations UI

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/integratedControl.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/tests/AppFlow.test.tsx`

- [x] **Step 1: Add types and API functions**

Expose BP policies, line items, revisions, recost runs and export URL helpers.

- [x] **Step 2: Add UI controls**

In Integrated Control, add small panels for:
- BP approval policy creation.
- BP line item list/edit for recent process.
- Recost run history.
- CSV/PDF export buttons.

- [x] **Step 3: Add Vitest coverage**

Mock the new endpoints and assert the new controls render.

### Task 5: Verification and Documentation

**Files:**
- Modify: `docs/23-resumen-estado-instructivos-2026-05-14.md`
- Modify: `tools/generate_estado_instructivos_pdf.py` if needed

- [x] **Step 1: Run verification**

Run:

```powershell
docker compose run --rm api pytest -q
docker compose run --rm frontend npm test
docker compose run --rm frontend npm run build
```

- [x] **Step 2: Update documentation and PDF**

Document the production-hardening endpoints, usage and verification evidence. Generate the updated PDF.

- [x] **Step 3: Relaunch app**

Run:

```powershell
docker compose up -d --build api frontend
```
