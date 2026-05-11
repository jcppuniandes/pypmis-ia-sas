# Ola 2 — Frontend Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Break the 6,447-line monolithic `main.tsx` into a maintainable component tree with React Router navigation, Zustand global state, a typed API client, and a Vitest test suite — without changing any visible behavior.

**Architecture:** All domain types move to `src/types/`. API calls move to `src/api/`. Global state (auth + selected project) moves to `src/store/`. Each view (`/dashboard`, `/schedule`, etc.) becomes its own file under `src/views/`. Shared UI primitives live in `src/components/ui/`. React Router v6 handles navigation; Zustand handles cross-component state. Vitest + Testing Library covers each view with at least one integration test.

**Tech Stack:** React Router v6, Zustand 4, Vitest 2, @testing-library/react, @testing-library/user-event

**Pre-condition:** Ola 1 must be complete (ESLint, Prettier, pinned deps already in place).

---

## File Map

```
frontend/src/
  types/
    index.ts              ← all domain types (moved from main.tsx lines 7-860)
  api/
    client.ts             ← fetch wrapper with auth headers + error handling
    auth.ts               ← /api/v1/auth/* calls
    projects.ts           ← /api/v1/projects/* calls
    dashboard.ts          ← /api/v1/projects/{id}/dashboard
    schedule.ts           ← schedule import + quality gate calls
    cost.ts               ← funding, cash-flow, contracts, POs, certs, receipts
    rfq.ts                ← RFQ packages + bids
    claims.ts             ← claims + entitlement + impact analysis
    documents.ts          ← documents, transmittals, reviews, mail
    awp.ts                ← work packages + constraints
    control.ts            ← progress, control core job
    admin.ts              ← users, memberships, control plan
  store/
    auth.ts               ← Zustand: token, authUser, login(), logout()
    project.ts            ← Zustand: selectedProjectId, dashboard, actions
  views/
    LoginView.tsx
    DashboardView.tsx
    ScheduleView.tsx
    ProgressView.tsx
    CostView.tsx
    AwpView.tsx
    ChangesView.tsx
    ClaimsView.tsx
    RfqView.tsx
    ContractsView.tsx
    DocumentsView.tsx
    BusinessProcessesView.tsx
    RoadmapView.tsx
    AdminView.tsx
  components/
    ui/
      StatusLight.tsx     ← StatusLight component (currently inline in main.tsx:887)
      Spinner.tsx
    layout/
      Sidebar.tsx         ← navigation sidebar (currently inline in main.tsx ~line 2000)
      TopBar.tsx
  App.tsx                 ← Router + route definitions (replaces monolithic App fn)
  main.tsx                ← trimmed to: ReactDOM.createRoot + <App /> only
  styles.css              ← unchanged
  vite-env.d.ts           ← unchanged

frontend/
  vite.config.ts          ← add test config
  vitest.setup.ts         ← testing-library/jest-dom setup
  tests/
    views/
      LoginView.test.tsx
      DashboardView.test.tsx
      ScheduleView.test.tsx
```

---

### Task 1: Install new dependencies

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install React Router + Zustand**

```bash
docker compose exec frontend npm install --save-exact react-router-dom@6 zustand@4
```

- [ ] **Step 2: Install Vitest + Testing Library**

```bash
docker compose exec frontend npm install --save-dev --save-exact \
  vitest@2 \
  @vitest/coverage-v8@2 \
  @testing-library/react@16 \
  @testing-library/user-event@14 \
  @testing-library/jest-dom@6 \
  jsdom@25
```

- [ ] **Step 3: Add test scripts to `frontend/package.json`**

In the `"scripts"` section, add:
```json
"test": "vitest run",
"test:watch": "vitest",
"test:coverage": "vitest run --coverage"
```

- [ ] **Step 4: Update `frontend/vite.config.ts` to include Vitest config**

Replace the full file with:
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
  },
});
```

- [ ] **Step 5: Create `frontend/vitest.setup.ts`**

```ts
import "@testing-library/jest-dom";
```

- [ ] **Step 6: Verify test runner works with no tests yet**

```bash
docker compose exec frontend npm run test
```

Expected: `No test files found` (not an error).

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/vitest.setup.ts
git commit -m "chore(frontend): install react-router-dom, zustand, vitest, testing-library"
```

---

### Task 2: Extract domain types

**Files:**
- Create: `frontend/src/types/index.ts`
- Modify: `frontend/src/main.tsx` (remove type declarations, add import)

- [ ] **Step 1: Create `frontend/src/types/index.ts`**

Cut lines 7–860 from `main.tsx` (all `type Foo = { ... }` declarations) and paste them as the full content of this new file.

The file should start with:
```ts
export type WorkspaceView =
  | "business-processes"
  | "control-dashboard"
  | "schedule"
  | "progress"
  | "cost"
  | "awp"
  | "changes"
  | "claims"
  | "rfq"
  | "contracts"
  | "documents"
  | "roadmap"
  | "bp-entry-forms"
  | "admin";

export type Project = {
  id: number;
  code: string;
  name: string;
  phase: string;
  currency: string;
  start_date: string | null;
  finish_date: string | null;
};
// ... all other types with `export` prefix added
```

Add `export` keyword before every `type` declaration.

- [ ] **Step 2: Add import to `main.tsx`**

At the top of `main.tsx`, after the existing imports, add:
```ts
import type { WorkspaceView, Project, /* ... all types */ } from "./types";
```

Or use a namespace import:
```ts
import type * as T from "./types";
```

Then update all type references in `main.tsx` to use `T.Project`, `T.Dashboard`, etc.

- [ ] **Step 3: Verify TypeScript compiles**

```bash
docker compose exec frontend npm run build
```

Expected: Build succeeds with no type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/ frontend/src/main.tsx
git commit -m "refactor(frontend): extract domain types to src/types/index.ts"
```

---

### Task 3: Create typed API client

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/api/projects.ts`
- Create: `frontend/src/api/dashboard.ts`

- [ ] **Step 1: Create `frontend/src/api/client.ts`**

```ts
const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { token?: string } = {},
): Promise<T> {
  const { token, ...init } = options;
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (init.body && typeof init.body === "string") {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${apiUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
```

- [ ] **Step 2: Create `frontend/src/api/auth.ts`**

```ts
import { apiFetch } from "./client";
import type { AuthSession } from "../types";

export async function login(email: string, password: string): Promise<AuthSession> {
  return apiFetch<AuthSession>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function me(token: string): Promise<AuthSession["user"]> {
  return apiFetch("/api/v1/auth/me", { token });
}
```

- [ ] **Step 3: Create `frontend/src/api/projects.ts`**

```ts
import { apiFetch } from "./client";
import type { Project, ProjectControlPlan, ProjectTeamMember, RoleProfile } from "../types";

export const projects = {
  list: (token: string) =>
    apiFetch<Project[]>("/api/v1/projects", { token }),

  get: (token: string, id: number) =>
    apiFetch<Project>(`/api/v1/projects/${id}`, { token }),

  create: (token: string, data: Omit<Project, "id">) =>
    apiFetch<Project>("/api/v1/projects", {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  controlPlan: (token: string, projectId: number) =>
    apiFetch<ProjectControlPlan>(`/api/v1/projects/${projectId}/control-plan`, { token }),

  team: (token: string, projectId: number) =>
    apiFetch<ProjectTeamMember[]>(`/api/v1/projects/${projectId}/team`, { token }),

  roleProfiles: (token: string) =>
    apiFetch<RoleProfile[]>("/api/v1/projects/role-profiles", { token }),
};
```

- [ ] **Step 4: Create `frontend/src/api/dashboard.ts`**

```ts
import { apiFetch } from "./client";
import type { Dashboard, PilotReadiness } from "../types";

export const dashboard = {
  get: (token: string, projectId: number) =>
    apiFetch<Dashboard>(`/api/v1/projects/${projectId}/dashboard`, { token }),

  pilotReadiness: (token: string, projectId: number) =>
    apiFetch<PilotReadiness>(`/api/v1/projects/${projectId}/pilot-readiness`, { token }),
};
```

- [ ] **Step 5: Write a test for the API client error handling**

Create `frontend/tests/views/api-client.test.ts`:
```ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiFetch, ApiError } from "../../src/api/client";

describe("apiFetch", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("throws ApiError on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: () => Promise.resolve("Unauthorized"),
      statusText: "Unauthorized",
    }));

    await expect(apiFetch("/api/v1/auth/me", { token: "bad" })).rejects.toThrow(ApiError);
  });

  it("returns parsed JSON on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: "ok" }),
    }));

    const result = await apiFetch<{ status: string }>("/api/v1/health");
    expect(result.status).toBe("ok");
  });
});
```

- [ ] **Step 6: Run tests**

```bash
docker compose exec frontend npm run test
```

Expected: 2 tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/ frontend/tests/
git commit -m "refactor(frontend): typed API client with error class"
```

---

### Task 4: Create Zustand auth store

**Files:**
- Create: `frontend/src/store/auth.ts`

- [ ] **Step 1: Create `frontend/src/store/auth.ts`**

```ts
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "../types";

type AuthState = {
  token: string;
  user: User | null;
  login: (token: string, user: User) => void;
  logout: () => void;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: "",
      user: null,
      login: (token, user) => set({ token, user }),
      logout: () => set({ token: "", user: null }),
    }),
    {
      name: "pypmis_auth",
      partialize: (state) => ({ token: state.token, user: state.user }),
    },
  ),
);
```

- [ ] **Step 2: Create `frontend/src/store/project.ts`**

```ts
import { create } from "zustand";
import type { Dashboard } from "../types";

type ProjectState = {
  selectedProjectId: number | null;
  dashboard: Dashboard | null;
  setSelectedProject: (id: number) => void;
  setDashboard: (d: Dashboard | null) => void;
};

export const useProjectStore = create<ProjectState>()((set) => ({
  selectedProjectId: null,
  dashboard: null,
  setSelectedProject: (id) => set({ selectedProjectId: id, dashboard: null }),
  setDashboard: (d) => set({ dashboard: d }),
}));
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/store/
git commit -m "refactor(frontend): add Zustand auth and project stores"
```

---

### Task 5: Create LoginView component + test

**Files:**
- Create: `frontend/src/views/LoginView.tsx`
- Create: `frontend/tests/views/LoginView.test.tsx`

- [ ] **Step 1: Write the failing test first**

Create `frontend/tests/views/LoginView.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import LoginView from "../../src/views/LoginView";

// Mock the API module
vi.mock("../../src/api/auth", () => ({
  login: vi.fn(),
}));

import { login } from "../../src/api/auth";

describe("LoginView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders email and password fields", () => {
    render(<MemoryRouter><LoginView /></MemoryRouter>);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("shows error message on failed login", async () => {
    vi.mocked(login).mockRejectedValue(new Error("Invalid credentials"));
    render(<MemoryRouter><LoginView /></MemoryRouter>);

    await userEvent.type(screen.getByLabelText(/email/i), "bad@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
docker compose exec frontend npm run test -- tests/views/LoginView.test.tsx
```

Expected: FAIL — `LoginView` module not found.

- [ ] **Step 3: Create `frontend/src/views/LoginView.tsx`**

```tsx
import React from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/auth";
import { useAuthStore } from "../store/auth";

export default function LoginView() {
  const navigate = useNavigate();
  const loginStore = useAuthStore((s) => s.login);
  const [email, setEmail] = React.useState(
    import.meta.env.VITE_DEMO_EMAIL ?? "ana.control@demo.local"
  );
  const [password, setPassword] = React.useState(
    import.meta.env.VITE_DEMO_PASSWORD ?? "demo123"
  );
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const session = await login(email, password);
      loginStore(session.access_token, session.user);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-container">
      <h1>P&amp;Pmis Ai SaaS</h1>
      <form onSubmit={handleSubmit}>
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <div role="alert" className="error">{error}</div>}
        <button type="submit" disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
docker compose exec frontend npm run test -- tests/views/LoginView.test.tsx
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/LoginView.tsx frontend/tests/views/LoginView.test.tsx
git commit -m "refactor(frontend): extract LoginView with Zustand auth + tests"
```

---

### Task 6: Add React Router and wire App.tsx

**Files:**
- Create: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx` — reduce to bootstrap only

- [ ] **Step 1: Create `frontend/src/App.tsx`**

```tsx
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuthStore } from "./store/auth";
import LoginView from "./views/LoginView";

// Lazy-loaded views (add as each is extracted in subsequent tasks)
import DashboardView from "./views/DashboardView";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginView />} />
      <Route
        path="/*"
        element={
          <RequireAuth>
            <DashboardView />
          </RequireAuth>
        }
      />
    </Routes>
  );
}
```

- [ ] **Step 2: Create a stub `frontend/src/views/DashboardView.tsx`**

This is a placeholder that will be fleshed out in the next task:
```tsx
export default function DashboardView() {
  return <div>Dashboard (in progress)</div>;
}
```

- [ ] **Step 3: Trim `frontend/src/main.tsx` to bootstrap only**

Replace the entire content of `main.tsx` with:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
```

- [ ] **Step 4: Build to confirm no TypeScript errors**

```bash
docker compose exec frontend npm run build
```

Expected: Build succeeds.

- [ ] **Step 5: Write a smoke test for routing**

Create `frontend/tests/views/App.test.tsx`:
```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../../src/App";

describe("App routing", () => {
  it("redirects unauthenticated user to /login", () => {
    render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run tests**

```bash
docker compose exec frontend npm run test
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.tsx frontend/src/views/DashboardView.tsx frontend/src/main.tsx frontend/tests/
git commit -m "refactor(frontend): add React Router, App.tsx, trim main.tsx to bootstrap"
```

---

### Task 7: Extract remaining views (one per domain)

**Files:**
- Create: `frontend/src/views/ScheduleView.tsx`
- Create: `frontend/src/views/CostView.tsx`
- Create: `frontend/src/views/DocumentsView.tsx`
- Create: `frontend/src/views/RfqView.tsx`
- Create: `frontend/src/views/ClaimsView.tsx`
- Create: `frontend/src/views/AwpView.tsx`
- Create: `frontend/src/views/ChangesView.tsx`
- Create: `frontend/src/views/BusinessProcessesView.tsx`
- Create: `frontend/src/views/ContractsView.tsx`
- Create: `frontend/src/views/AdminView.tsx`
- Create: `frontend/src/views/RoadmapView.tsx`
- Create: `frontend/src/components/ui/StatusLight.tsx`
- Create: `frontend/src/components/layout/Sidebar.tsx`

For each view:

- [ ] **Step 1: Identify the JSX block in the old `main.tsx` (before it was trimmed)**

Each view is rendered in a `if (activeView === "schedule") { return <...> }` or `{activeView === "schedule" && <...>}` block. Cut that JSX block.

- [ ] **Step 2: Create the view file**

Pattern for each view (example: `ScheduleView.tsx`):
```tsx
import type { Dashboard } from "../types";

type Props = {
  dashboard: Dashboard;
  token: string;
  onRefresh: () => void;
};

export default function ScheduleView({ dashboard, token, onRefresh }: Props) {
  // paste JSX from main.tsx here
  // replace dashboard.xxx references to use the prop directly
  // replace state setters that belong here with local useState
  return (
    <div className="view schedule-view">
      {/* pasted content */}
    </div>
  );
}
```

- [ ] **Step 3: Create `frontend/src/components/ui/StatusLight.tsx`**

```tsx
type Props = { value: number };

export default function StatusLight({ value }: Props) {
  const className = value < 0.9 ? "light red" : value < 1 ? "light amber" : "light green";
  return <span className={className} />;
}
```

- [ ] **Step 4: After extracting each view, run the full test suite**

```bash
docker compose exec frontend npm run test && docker compose exec frontend npm run build
```

Expected: No new test failures, build succeeds.

- [ ] **Step 5: Write one integration test per extracted view**

Pattern:
```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import ScheduleView from "../../src/views/ScheduleView";
import type { Dashboard } from "../../src/types";

const mockDashboard = { /* minimal Dashboard shape */ } as Dashboard;

describe("ScheduleView", () => {
  it("renders schedule section heading", () => {
    render(<ScheduleView dashboard={mockDashboard} token="tok" onRefresh={vi.fn()} />);
    expect(screen.getByRole("heading", { name: /schedule/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Commit after each view**

```bash
git add frontend/src/views/<ViewName>.tsx frontend/tests/views/<ViewName>.test.tsx
git commit -m "refactor(frontend): extract <ViewName> into standalone component"
```

---

### Task 8: Update CI to run frontend tests

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add frontend test step to the `frontend-lint` job (or create a new `frontend-test` job)**

In the `verify` job in `.github/workflows/ci.yml`, add after the frontend build step:
```yaml
- name: Run frontend tests
  run: docker compose exec -T frontend npm run test
```

- [ ] **Step 2: Lower the ESLint max-warnings threshold now that views are extracted**

In the `frontend-lint` job, change:
```yaml
- run: cd frontend && npm run lint -- --max-warnings=10
```

(From 50 to 10 since the monolith is gone.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add frontend vitest run to CI pipeline"
```

---

## Self-Review

**Spec coverage:**
- ✓ React Router v6 — Task 6
- ✓ Extract components per domain — Task 7
- ✓ Zustand state management — Task 4
- ✓ Typed API client — Task 3
- ✓ Vitest + Testing Library setup — Task 1
- ✓ Tests per view — Task 7, Step 5
- ✓ CI runs frontend tests — Task 8

**Placeholder scan:** Task 7 Step 2 says "paste JSX from main.tsx" — this is intentional direction (not a TBD), as the content is the existing code being reorganized. The pattern with Props type and return JSX is fully specified.

**Type consistency:** `Dashboard` type from `src/types/index.ts` is used consistently across stores, API client, and view props.
