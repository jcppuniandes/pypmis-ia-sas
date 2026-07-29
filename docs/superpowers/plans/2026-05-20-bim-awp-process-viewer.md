# BIM AWP Process Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote BIM/IFC quantity takeoff from a setup panel into a formal process-flow module with a 3D control viewer and AWP/PBS validation cues.

**Architecture:** Keep the existing Phase 1 import service as the data source. Add process-flow evidence from quantity takeoff runs and mapped/unmapped lines, expose a dedicated frontend view, and render a Three.js scene derived from extracted IFC/Excel quantity lines so the user can inspect model-derived scope by storey/class/mapping status.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, TypeScript, Vite, Vitest, Three.js, Playwright/browser verification.

---

### Task 1: Process-Flow Evidence

**Files:**
- Modify: `backend/app/services/process_flow_board.py`
- Test: `backend/tests/test_process_flow_board.py`

- [x] **Step 1: Write a failing backend test**

Add a test that creates a project with and without quantity takeoff evidence and asserts the board includes a `bim_quantity_takeoff` item under the AWP lane, with `target_view="quantity-takeoff"` and evidence for total/mapped/review lines.

- [x] **Step 2: Run the failing test**

Run: `docker compose run --rm api pytest tests/test_process_flow_board.py -q`
Expected: FAIL because the board does not yet include the BIM quantity item.

- [x] **Step 3: Implement process-flow counts**

Import `QuantityTakeoffRun` and `QuantityTakeoffLine`, compute run/line/mapped/review counts, and add an AWP lane item named `BIM quantity takeoff`.

- [x] **Step 4: Run backend tests**

Run: `docker compose run --rm api pytest tests/test_process_flow_board.py tests/test_quantity_takeoff.py -q`
Expected: PASS.

### Task 2: Dedicated BIM Quantity Module

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/types/index.ts`
- Test: `frontend/tests/AppFlow.test.tsx`

- [x] **Step 1: Write a failing frontend flow test**

Add a test that clicks `BIM Quantity Takeoff`, sees the module heading, upload action, AWP/PBS validation cards, latest lines, and a 3D viewer canvas.

- [x] **Step 2: Run the failing frontend test**

Run: `npm.cmd test -- --run tests/AppFlow.test.tsx`
Expected: FAIL because the dedicated view and canvas do not exist.

- [x] **Step 3: Implement the module view**

Add `quantity-takeoff` as a control view, wire process-flow navigation to it, and render the upload/run/line summary already supported in Project Setup as a first-class module.

- [x] **Step 4: Run frontend tests**

Run: `npm.cmd test -- --run tests/AppFlow.test.tsx`
Expected: PASS.

### Task 3: Three.js BIM Control Viewer

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/components/BimModelViewer.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/tests/AppFlow.test.tsx`

- [x] **Step 1: Add Three.js**

Run: `npm.cmd install three` from `frontend/`.
Expected: `three` is added to dependencies and lockfile.

- [x] **Step 2: Create viewer component**

Render a stable canvas with `data-testid="bim-model-viewer-canvas"`, WebGL rendering when available, and graceful fallback text in JSDOM. Use colors aligned to AWP status: review/missing mapping in red/amber, mapped/ready in green, neutral scope in blue/gray.

- [x] **Step 3: Add responsive styling**

Make the viewer full-width inside the module, with a fixed aspect ratio, stable canvas dimensions, and a compact legend/table. Avoid nested decorative cards.

- [x] **Step 4: Build and browser verify**

Run: `npm.cmd run build`, restart `docker compose up -d --build api frontend`, then verify desktop and mobile canvas rendering with browser/Playwright and a WebGL pixel check.

### Task 4: Final Verification

**Files:**
- No new files expected.

- [x] **Step 1: Run backend regression**

Run: `docker compose run --rm api pytest tests/test_process_flow_board.py tests/test_quantity_takeoff.py tests/test_schedule_ingestion.py -q`
Expected: PASS.

- [x] **Step 2: Run frontend regression**

Run: `npm.cmd test -- --run tests/AppFlow.test.tsx` and `npm.cmd run build`
Expected: PASS.

- [x] **Step 3: Verify app at localhost**

Open `http://localhost:5173/app`, navigate to the BIM quantity module, confirm upload controls, AWP/PBS validation, line table, and nonblank 3D canvas on desktop and mobile.
