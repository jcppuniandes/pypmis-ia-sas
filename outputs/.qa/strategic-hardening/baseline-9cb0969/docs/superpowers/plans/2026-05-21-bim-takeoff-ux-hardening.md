# BIM Takeoff UX Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make BIM Quantity Takeoff feel like a controlled process module and prevent large IFC uploads from killing the API worker with an opaque browser error.

**Architecture:** Keep the existing synchronous quantity extractor for prepared IFC quantity exports and Excel/CSV takeoff files. Move user-facing BIM/Excel upload ownership into the BIM module, add a contextual process guide, and reject oversized IFC files before regex parsing.

**Tech Stack:** React/Vitest frontend, FastAPI/Pytest backend, existing Docker Compose services.

---

### Task 1: Frontend Regression Tests

**Files:**
- Modify: `frontend/tests/AppFlow.test.tsx`

- [ ] **Step 1: Write failing tests**

Add tests that prove Project Setup no longer renders the Quantity Takeoff uploader, the BIM module owns the BIM/Excel upload, and a network/timeout failure is converted into a specific BIM upload message.

- [ ] **Step 2: Run tests red**

Run: `npm.cmd test -- --run tests/AppFlow.test.tsx`

Expected before implementation: at least one assertion fails because Project Setup still renders Quantity Takeoff and the upload error is the raw `Failed to fetch`.

### Task 2: Backend IFC Guard Test

**Files:**
- Modify: `backend/tests/test_quantity_takeoff.py`

- [ ] **Step 1: Write failing test**

Add a service-level test that calls `QuantityTakeoffService.import_file()` with an `.ifc` payload one byte larger than the synchronous IFC limit and expects HTTP 413 with a clear remediation message.

- [ ] **Step 2: Run test red**

Run: `docker compose run --rm api pytest tests/test_quantity_takeoff.py::test_quantity_takeoff_rejects_oversized_ifc_before_parse -q`

Expected before implementation: import of the new constants fails or the service attempts to parse instead of returning HTTP 413.

### Task 3: Frontend UX Fix

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add contextual module guide**

Render a small `moduleGuide` above the active view with module, objective, status and next action. Keep overview KPI strips only in Dashboard/Process Flow.

- [ ] **Step 2: Move takeoff ownership**

Remove the `Quantity Takeoff` panel from Project Setup and keep upload, summary, viewer, and quantity lines in `BIM Quantity Takeoff Module`.

- [ ] **Step 3: Add upload messaging**

Use dedicated `quantityMessage` and `quantityError` state. Convert `TypeError: Failed to fetch` into a message that explains likely timeout/large model behavior and directs the user to prepared IFC quantity exports or Excel/CSV takeoff.

### Task 4: Backend Guard

**Files:**
- Modify: `backend/app/services/quantity_takeoff.py`

- [ ] **Step 1: Define IFC synchronous limits**

Add `IFC_TAKEOFF_MAX_BYTES = 8 * 1024 * 1024` and expose a human-readable `IFC_TAKEOFF_MAX_MB`.

- [ ] **Step 2: Reject early**

Before `_parse_ifc`, reject oversized `.ifc` payloads with HTTP 413 and a message explaining the current synchronous extractor scope.

### Task 5: Verification

**Files:**
- No code changes expected.

- [ ] **Step 1: Backend tests**

Run: `docker compose run --rm api pytest tests/test_quantity_takeoff.py tests/test_process_flow_board.py -q`

- [ ] **Step 2: Frontend tests**

Run: `npm.cmd test -- --run tests/AppFlow.test.tsx`

- [ ] **Step 3: Production build**

Run: `npm.cmd run build`

- [ ] **Step 4: Browser smoke**

Open `http://localhost:5173/app` and confirm the BIM module is no longer followed by the Schedule Intake card, the Project Setup view does not show the takeoff uploader, and the BIM module explains current IFC/Excel operation.
