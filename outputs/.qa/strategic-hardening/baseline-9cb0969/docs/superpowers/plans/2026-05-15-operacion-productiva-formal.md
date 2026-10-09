# Operacion Productiva Formal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the app for formal production operation with migration evidence, tenant role matrix, browser E2E CI, backups, security/observability hardening, and optional low-cost agent synthesis.

**Architecture:** Keep the deterministic product path intact and add operational controls around it. Production readiness is split between backend API evidence, deploy scripts/runbook, CI gates, and an optional AI synthesis layer that is disabled unless explicitly configured.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, Pydantic, Docker Compose, GitHub Actions, Playwright, React/Vite, pytest, Vitest.

---

### Task 1: Production Operations Guardrails

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/tests/test_config.py`
- Modify: `deploy/vps/.env.example`
- Modify: `deploy/vps/deploy.sh`
- Modify: `deploy/vps/backup.sh`
- Create: `docs/24-operacion-productiva-formal.md`
- Test: `backend/tests/test_production_operations.py`

- [ ] **Step 1: Write failing tests**

Add tests that require production configs to enforce `METRICS_TOKEN`, JSON logs, rate limiting and security headers, and require deploy artifacts to include migration verification and backup retention.

- [ ] **Step 2: Run tests to verify failure**

Run: `docker compose run --rm api pytest tests/test_config.py tests/test_production_operations.py -q`
Expected: failures for missing production checks and missing production operations artifact assertions.

- [ ] **Step 3: Implement config and script changes**

Update production validation, add env defaults for backup retention and AI synthesis, add `alembic current` verification in deploy, and write the production runbook.

- [ ] **Step 4: Run tests to verify pass**

Run: `docker compose run --rm api pytest tests/test_config.py tests/test_production_operations.py -q`
Expected: all selected tests pass.

### Task 2: Tenant Role Matrix API

**Files:**
- Modify: `backend/app/domain/schemas.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `backend/tests/test_production_operations.py`

- [ ] **Step 1: Write failing role matrix API test**

Test `GET /api/v1/projects/{project_id}/role-matrix` returns every supported role, assigned users per role, permission booleans, and active BP policies tied to each role.

- [ ] **Step 2: Run focused test to verify failure**

Run: `docker compose run --rm api pytest tests/test_production_operations.py -k role_matrix -q`
Expected: 404 for the new endpoint.

- [ ] **Step 3: Implement schemas and endpoint**

Add `RoleMatrixPolicyOut`, `RoleMatrixEntryOut`, and `ProjectRoleMatrixOut`; implement the endpoint using `_role_profiles()`, `_project_team()`, and `BusinessProcessPolicy`.

- [ ] **Step 4: Run focused test to verify pass**

Run: `docker compose run --rm api pytest tests/test_production_operations.py -k role_matrix -q`
Expected: role matrix test passes.

### Task 3: Browser E2E Pipeline

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/production-readiness.spec.ts`
- Modify: `.github/workflows/ci.yml`
- Modify: `backend/tests/test_production_operations.py`

- [ ] **Step 1: Write failing artifact test**

Assert the CI workflow contains a Playwright E2E job and the frontend package exposes `test:e2e`.

- [ ] **Step 2: Run artifact test to verify failure**

Run: `docker compose run --rm api pytest tests/test_production_operations.py -k e2e -q`
Expected: failure because Playwright artifacts are absent.

- [ ] **Step 3: Add Playwright config, E2E test and CI job**

Create a real-browser smoke journey: login, open Integrated Control, verify the Senior AWP Packaging Advisor, open Work Packages, and verify AWP register content.

- [ ] **Step 4: Run install/build checks**

Run: `cd frontend && npm install --package-lock-only`
Run: `docker compose run --rm frontend npm run build`
Expected: package lock updates and build passes.

### Task 4: Optional Low-Cost Agent Synthesis

**Files:**
- Modify: `backend/app/services/ai_insights.py`
- Modify: `backend/app/services/control_audit_agent.py`
- Modify: `backend/tests/test_ai_insights.py`
- Modify: `backend/tests/test_unifier_priority_flow.py`

- [ ] **Step 1: Write failing synthesis tests**

Test that disabled provider returns no synthesis, and that the control audit run can append mocked Claude Haiku synthesis when configured.

- [ ] **Step 2: Run tests to verify failure**

Run: `docker compose run --rm api pytest tests/test_ai_insights.py tests/test_unifier_priority_flow.py -q`
Expected: synthesis tests fail before implementation.

- [ ] **Step 3: Implement optional synthesis**

Add `generate_control_agent_synthesis()` and wire it into `ControlAuditAgentService` only when `AI_PROVIDER=claude` and an API key is present. Keep deterministic summaries unchanged when disabled.

- [ ] **Step 4: Run focused tests to verify pass**

Run: `docker compose run --rm api pytest tests/test_ai_insights.py tests/test_unifier_priority_flow.py -q`
Expected: all selected tests pass.

### Task 5: Final Verification

**Files:**
- All modified files.

- [ ] **Step 1: Run backend focused suite**

Run: `docker compose run --rm api pytest tests/test_config.py tests/test_production_operations.py tests/test_ai_insights.py tests/test_unifier_priority_flow.py -q`
Expected: all pass.

- [ ] **Step 2: Run frontend build**

Run: `docker compose run --rm frontend npm run build`
Expected: build passes.

- [ ] **Step 3: Bring up app and verify health**

Run: `docker compose up -d api frontend`
Run: `Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/v1/health/ready`
Run: `Invoke-WebRequest -UseBasicParsing http://localhost:5173`
Expected: both return HTTP 200.

