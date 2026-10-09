# AWP Draft Packaging Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an agent action that creates editable AWP draft packages from the current project control structure.

**Architecture:** Reuse `ControlAuditAgentService` as the deterministic agent boundary. The new endpoint creates missing `WorkPackage` and `WorkPackageConstraint` records, then returns a persisted `ControlAgentRunOut` with findings that document what was created or skipped.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, React/Vite, Vitest, Docker Compose.

---

### Task 1: Backend RED Test

**Files:**
- Modify: `backend/tests/test_unifier_priority_flow.py`

- [x] **Step 1: Add failing test**

Add `test_control_audit_agent_creates_awp_draft_packages_from_control_accounts`. The test creates a ready project, loads an Activity Sheet, calls `POST /api/v1/projects/{project_id}/agents/control-audit/awp-draft-packages`, and asserts CWA/CWP/IWP packages plus constraints were created without duplicates.

- [x] **Step 2: Verify RED**

Run:

```powershell
docker compose build api
docker compose run --rm api pytest tests/test_unifier_priority_flow.py::test_control_audit_agent_creates_awp_draft_packages_from_control_accounts -q
```

Expected: FAIL with 404 because the endpoint does not exist yet.

### Task 2: Backend Service and Endpoint

**Files:**
- Modify: `backend/app/services/control_audit_agent.py`
- Modify: `backend/app/api/v1/router.py`

- [x] **Step 1: Add service method**

Add `create_awp_draft_packages(tenant_id, project_id, actor)` to create CWA/CWP/IWP records and open constraints.

- [x] **Step 2: Add route**

Add:

```text
POST /projects/{project_id}/agents/control-audit/awp-draft-packages
```

Return `ControlAgentRunOut`.

- [x] **Step 3: Verify GREEN**

Run the focused backend test. Expected: PASS.

### Task 3: Frontend UI

**Files:**
- Modify: `frontend/src/api/integratedControl.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/tests/AppFlow.test.tsx`

- [x] **Step 1: Add API method**

Expose `createAwpDraftPackages(token, projectId)`.

- [x] **Step 2: Add button**

In the AI Control Auditor panel, add `Create Draft Packages`. On success refresh dashboard and integrated control data.

- [x] **Step 3: Add Vitest coverage**

Extend the production hardening test to click the new button and assert the API call.

### Task 4: Verification

Run:

```powershell
docker compose run --rm api pytest tests/test_unifier_priority_flow.py::test_control_audit_agent_creates_awp_draft_packages_from_control_accounts -q
docker compose run --rm frontend npm test -- --run tests/AppFlow.test.tsx -t "production hardening"
docker compose run --rm frontend npm run build
```

Verified on 2026-05-15:
- Backend focused RED: failed with `404 Not Found`.
- Backend focused GREEN: `1 passed, 29 warnings`.
- Frontend focused Vitest: `1 passed | 8 skipped`.
- Frontend build: `tsc && vite build` succeeded.
