# Ola 1 — Code Quality Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce consistent code style and catch bugs automatically by adding Ruff (backend), ESLint + Prettier (frontend), pinned dependencies, and CI quality gates — without touching any business logic.

**Architecture:** Backend gets a `pyproject.toml` with Ruff config. Frontend gets ESLint flat config + Prettier. CI grows two new jobs that block merges on lint failures. No runtime code changes.

**Tech Stack:** Ruff ≥ 0.4, ESLint 9 (flat config), Prettier 3, GitHub Actions

---

## File Map

| Action | File |
|--------|------|
| Create | `backend/pyproject.toml` |
| Modify | `frontend/package.json` — pin versions + add devDeps |
| Create | `frontend/eslint.config.js` |
| Create | `frontend/.prettierrc` |
| Modify | `.github/workflows/ci.yml` — add lint jobs |

---

### Task 1: Add Ruff to backend

**Files:**
- Create: `backend/pyproject.toml`

- [ ] **Step 1: Create `backend/pyproject.toml`**

```toml
[tool.ruff]
target-version = "py312"
line-length = 120
src = ["app", "tests"]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
]
ignore = [
    "B008",  # do not perform function calls in default arguments (FastAPI Depends pattern)
    "E501",  # line too long — handled by formatter
]

[tool.ruff.lint.isort]
known-first-party = ["app"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

- [ ] **Step 2: Install Ruff inside the container and run a check**

```bash
docker compose exec api pip install ruff
docker compose exec api ruff check app/ tests/ --output-format=github
```

Expected: Some warnings or clean output. Note any errors — do NOT auto-fix yet.

- [ ] **Step 3: Run auto-fix for safe rules only**

```bash
docker compose exec api ruff check app/ tests/ --fix --unsafe-fixes=false
docker compose exec api ruff format app/ tests/
```

Expected: Modified files. Review the diff before committing.

- [ ] **Step 4: Add ruff to requirements.txt**

In `backend/requirements.txt`, append:
```
ruff>=0.4.0
```

- [ ] **Step 5: Verify tests still pass**

```bash
docker compose exec -T api pytest
```

Expected: All tests pass (green).

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/requirements.txt backend/app/ backend/tests/
git commit -m "chore(backend): add Ruff linting and formatting config"
```

---

### Task 2: Add ESLint + Prettier to frontend

**Files:**
- Create: `frontend/eslint.config.js`
- Create: `frontend/.prettierrc`
- Modify: `frontend/package.json`

- [ ] **Step 1: Pin all frontend dependency versions**

Run inside the frontend container (or locally with Node 22):
```bash
docker compose exec frontend npm install --save-exact \
  react@latest react-dom@latest lucide-react@latest recharts@latest \
  @vitejs/plugin-react@latest vite@latest typescript@latest

docker compose exec frontend npm install --save-dev --save-exact \
  @types/react@latest @types/react-dom@latest \
  eslint@9 @typescript-eslint/eslint-plugin@latest @typescript-eslint/parser@latest \
  eslint-plugin-react-hooks@latest eslint-plugin-react-refresh@latest \
  prettier@3
```

Expected: `package.json` now has exact version numbers (no `latest`).

- [ ] **Step 2: Create `frontend/eslint.config.js`**

```js
import tseslint from "@typescript-eslint/eslint-plugin";
import tsparser from "@typescript-eslint/parser";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

export default [
  {
    ignores: ["dist/**", "node_modules/**"],
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsparser,
      parserOptions: {
        ecmaVersion: 2022,
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      "@typescript-eslint": tseslint,
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...tseslint.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": "warn",
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    },
  },
];
```

- [ ] **Step 3: Create `frontend/.prettierrc`**

```json
{
  "semi": true,
  "singleQuote": false,
  "trailingComma": "es5",
  "printWidth": 120,
  "tabWidth": 2
}
```

- [ ] **Step 4: Add lint and format scripts to `frontend/package.json`**

In the `"scripts"` section of `frontend/package.json`, add:
```json
"lint": "eslint src/",
"lint:fix": "eslint src/ --fix",
"format": "prettier --write src/",
"format:check": "prettier --check src/"
```

- [ ] **Step 5: Run ESLint and note violations (do not fail yet)**

```bash
docker compose exec frontend npm run lint 2>&1 | head -60
```

Expected: Warnings from the monolithic `main.tsx`. Note them — they won't block CI in this task (we use `--max-warnings` with a high threshold).

- [ ] **Step 6: Run Prettier on existing code**

```bash
docker compose exec frontend npm run format
```

Expected: `main.tsx` and `styles.css` reformatted. Review the diff.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/eslint.config.js frontend/.prettierrc frontend/src/
git commit -m "chore(frontend): add ESLint 9, Prettier, pin dependency versions"
```

---

### Task 3: Add lint gates to CI

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Update `.github/workflows/ci.yml`**

Replace the entire file content with:
```yaml
name: Pilot Readiness CI

on:
  pull_request:
  push:
    branches:
      - main

jobs:
  backend-lint:
    name: Backend lint (Ruff)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ruff
      - run: ruff check backend/app/ backend/tests/ --output-format=github
      - run: ruff format --check backend/app/ backend/tests/

  frontend-lint:
    name: Frontend lint (ESLint + Prettier)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - run: cd frontend && npm ci
      - run: cd frontend && npm run lint -- --max-warnings=50
      - run: cd frontend && npm run format:check

  verify:
    name: Build + Tests
    runs-on: ubuntu-latest
    needs: [backend-lint, frontend-lint]
    steps:
      - uses: actions/checkout@v4
      - name: Build stack
        run: docker compose up -d --build
      - name: Run database migrations
        run: docker compose exec -T api alembic upgrade head
      - name: Run backend tests
        run: docker compose exec -T api pytest
      - name: Run frontend build
        run: docker compose exec -T frontend npm run build
      - name: Show service logs on failure
        if: failure()
        run: docker compose logs --tail=120 api worker frontend
```

Note: `--max-warnings=50` lets the current `main.tsx` warnings through while blocking NEW lint violations. Lower this number as Ola 2 progresses.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add Ruff and ESLint gates, enforce before build+test"
```

- [ ] **Step 3: Push and verify CI passes on GitHub**

```bash
git push origin main
```

Go to GitHub → Actions → check all 3 jobs pass.

---

## Self-Review

**Spec coverage:**
- ✓ Ruff on backend — Task 1
- ✓ ESLint + Prettier on frontend — Task 2
- ✓ Pin versions in package.json — Task 2, Step 1
- ✓ CI quality gates — Task 3

**Placeholder scan:** None found.

**Type consistency:** No cross-task types.
