# Control Audit Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear un agente auditor read-only que revise el estado Unifier del proyecto y entregue hallazgos priorizados de bajo costo.

**Architecture:** El agente corre dentro del backend como servicio deterministico, persiste cada corrida y sus hallazgos, y solo usa modelo externo en una etapa posterior opcional. La UI lo expone en Integrated Control como un panel operacional con boton Run Audit y lista de hallazgos.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, React/Vite, Vitest, Docker Compose.

---

### Task 1: Backend RED Test

**Files:**
- Modify: `backend/tests/test_unifier_priority_flow.py`

- [x] **Step 1: Add failing test**

Add a test that creates a ready project, BP CBS-WBS, Rate Sheet without recost, then calls:

```text
POST /api/v1/projects/{project_id}/agents/control-audit/run
GET /api/v1/projects/{project_id}/agents/control-audit/runs
```

Expected output includes `agent_code=control_audit`, `status=completed`, persisted findings with categories `bp_policy` and `recost`, and a score below 100.

- [x] **Step 2: Verify RED**

Run:

```powershell
docker compose build api
docker compose run --rm api pytest tests/test_unifier_priority_flow.py -q
```

Expected: FAIL with 404 for the new agent endpoint.

### Task 2: Backend Models, Schemas and Service

**Files:**
- Modify: `backend/app/domain/models.py`
- Modify: `backend/app/domain/schemas.py`
- Create: `backend/alembic/versions/20260514_0017_control_audit_agent.py`
- Create: `backend/app/services/control_audit_agent.py`

- [x] **Step 1: Add persistence models**

Create `ControlAgentRun` and `ControlAgentFinding` tables for run metadata and findings.

- [x] **Step 2: Add Pydantic schemas**

Create `ControlAgentRunOut` and `ControlAgentFindingOut`.

- [x] **Step 3: Implement deterministic service**

Implement checks:
- BP approval policy missing for active BP CBS-WBS or BP CBS-Fund.
- Rate Sheet exists but latest Activity Sheet has no recost run.
- Forecast exceeds funding availability.
- Reconciliation budget/forecast variance exists.
- Recent line item revisions exist and need management visibility.

### Task 3: Backend Endpoints

**Files:**
- Modify: `backend/app/api/v1/router.py`

- [x] **Step 1: Add run endpoint**

Add:

```text
POST /projects/{project_id}/agents/control-audit/run
```

- [x] **Step 2: Add history endpoint**

Add:

```text
GET /projects/{project_id}/agents/control-audit/runs
```

### Task 4: Frontend UI

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/integratedControl.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/tests/AppFlow.test.tsx`

- [x] **Step 1: Add types and API**

Expose control audit runs/findings and run endpoint.

- [x] **Step 2: Add panel**

In Integrated Control, add `AI Control Auditor` panel with score, run button, latest summary and findings.

- [x] **Step 3: Add Vitest coverage**

Assert the panel renders, calls run endpoint, and shows findings.

### Task 5: Verification

Run:

```powershell
docker compose run --rm api pytest -q
docker compose run --rm frontend npm test -- --run
docker compose run --rm frontend npm run build
docker compose up -d api frontend
```

Verified on 2026-05-14:
- Backend: `105 passed, 853 warnings`
- Frontend tests: `25 passed`
- Frontend build: `tsc && vite build` succeeded
- Runtime: API ready, frontend HTTP 200, Browser found `AI Control Auditor` and `Run Audit`
