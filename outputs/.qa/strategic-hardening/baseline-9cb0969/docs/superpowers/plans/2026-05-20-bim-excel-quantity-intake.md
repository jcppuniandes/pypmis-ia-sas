# BIM/Excel Quantity Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a controlled quantity intake process that imports quantities from Excel/CSV or IFC and normalizes them for WBS/CBS/FBS/AWP mapping.

**Architecture:** Add backend persistence for quantity takeoff runs and lines, a parser service with spreadsheet and IFC adapters, project endpoints for upload/list/detail, and a frontend panel inside the existing project workflow. Quantities are versioned by run and stay read-only until mapped/validated.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, React/Vite, Vitest, standard-library XLSX/IFC parsing.

---

### Task 1: Backend Red Tests

**Files:**
- Create: `backend/tests/test_quantity_takeoff.py`

- [ ] **Step 1: Write failing API tests**

Create tests that upload a minimal XLSX file with BIM quantity columns and an IFC file with an element quantity. Assert that the API returns a run with row counts, mapped/unmapped counts, source type, and retrievable normalized lines.

- [ ] **Step 2: Run tests to verify RED**

Run: `docker compose run --rm api pytest tests/test_quantity_takeoff.py -q`

Expected: fail because the endpoints and models do not exist.

### Task 2: Backend Models, Schemas, Parser Service

**Files:**
- Modify: `backend/app/domain/models.py`
- Modify: `backend/app/domain/schemas.py`
- Create: `backend/app/services/quantity_takeoff.py`
- Create: `backend/alembic/versions/20260520_0019_quantity_takeoff.py`

- [ ] **Step 1: Add `QuantityTakeoffRun` and `QuantityTakeoffLine`**

Persist source filename/type, status, counts, totals, BIM hierarchy fields, classification, quantity, unit, WBS/CBS/FBS/package codes, mapping status, validation notes, and raw data.

- [ ] **Step 2: Add Pydantic output schemas**

Expose runs and lines to the frontend with `from_attributes=True`.

- [ ] **Step 3: Implement parser service**

Support `.csv`, `.xlsx`, `.xls` with normalized header aliases. Support `.ifc` by extracting product GUID/class/name, storey containment, and published `IfcElementQuantity` values when present.

- [ ] **Step 4: Validate mapping**

Compare uploaded `wbs_code`, `cbs_code`, and `fbs_code` against project catalogs. Mark a line as `mapped` only when all three exist; otherwise mark `needs_mapping` with notes.

### Task 3: Backend Endpoints

**Files:**
- Modify: `backend/app/api/v1/routers/projects.py`

- [ ] **Step 1: Add upload endpoint**

`POST /api/v1/projects/{project_id}/quantity-takeoffs/import`

- [ ] **Step 2: Add list/detail endpoints**

`GET /api/v1/projects/{project_id}/quantity-takeoff-runs`

`GET /api/v1/projects/{project_id}/quantity-takeoff-runs/{run_id}/lines`

- [ ] **Step 3: Audit and permission gate**

Allow users with `can_capture_cost` or `can_configure`.

### Task 4: Frontend API and Panel

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/projects.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/tests/AppFlow.test.tsx`

- [ ] **Step 1: Add types and API functions**

Expose quantity runs and lines, plus `loadQuantityTakeoff`.

- [ ] **Step 2: Add Quantity Takeoff panel**

Place it in Project Setup near Activity Sheet. Include upload control, run cards, summary metrics, and a normalized table.

- [ ] **Step 3: Add frontend test**

Assert the panel shows BIM/Excel upload affordance, summary metrics, and normalized quantity columns.

### Task 5: Verification

**Files:**
- No new files.

- [ ] **Step 1: Run backend tests**

Run: `docker compose run --rm api pytest tests/test_quantity_takeoff.py -q`

- [ ] **Step 2: Run frontend tests**

Run: `npm.cmd test -- --run tests/AppFlow.test.tsx`

- [ ] **Step 3: Build frontend**

Run: `docker compose run --rm frontend npm run build`

- [ ] **Step 4: Rebuild/restart services**

Run: `docker compose up -d --build api frontend`

Expected: app available at `http://localhost:5173/app`.
