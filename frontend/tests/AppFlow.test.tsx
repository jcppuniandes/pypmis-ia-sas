import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { useProjectStore } from "../src/store/project";
import type { Dashboard, Project } from "../src/types";

const demoProject: Project = {
  id: 1,
  code: "CTRL-DEMO-001",
  name: "Piloto vial AWP",
  phase: "Planning",
  currency: "USD",
  start_date: "2026-05-01",
  finish_date: "2026-12-15",
};

const demoDashboard = {
  project: demoProject,
  project_kpi: {
    pv: 120000,
    ev: 90000,
    ac: 80000,
    spi: 0.75,
    cpi: 1.125,
  },
  project_team: [
    {
      user: {
        id: 1,
        email: "carlos.planner@demo.local",
        full_name: "Carlos Planner",
        title: "Planner",
        status: "active",
      },
      membership: {
        id: 10,
        project_id: 1,
        user_id: 1,
        role: "Planner",
        can_capture_progress: true,
        can_capture_cost: false,
        can_approve_workflow: false,
        can_manage_contract: false,
        can_configure: true,
      },
    },
  ],
  schedule_import: null,
  schedule_activity_count: 0,
  schedule_relationship_count: 0,
  schedule_findings: [],
  baseline_versions: [],
  latest_progress_records: [],
  cost_sheet: [],
  changes: [],
  document_control_summary: { controlled_document_score: 0 },
  awp_summary: {
    readiness_score: 0,
    total_packages: 0,
    cwp_count: 0,
    iwp_count: 0,
    twp_count: 0,
    top_count: 0,
    open_constraints: 0,
    blocking_constraints: 0,
    high_priority_constraints: 0,
    closure_evidence_count: 0,
    ready_for_release: 0,
    blocked_packages: 0,
  },
  work_package_constraints: [],
  work_packages: [],
  control_accounts: [],
} as unknown as Dashboard;

vi.mock("../src/store/auth", () => ({
  useAuthStore: () => ({
    token: "tok",
    user: {
      id: 1,
      email: "carlos.planner@demo.local",
      full_name: "Carlos Planner",
      title: "Planner",
      status: "active",
    },
    logout: vi.fn(),
  }),
}));

const listProjects = vi.fn();
const createProject = vi.fn();
const uploadSchedule = vi.fn();
const getDashboard = vi.fn();

vi.mock("../src/api/projects", () => ({
  projects: {
    list: (...args: unknown[]) => listProjects(...args),
    create: (...args: unknown[]) => createProject(...args),
    uploadSchedule: (...args: unknown[]) => uploadSchedule(...args),
  },
}));

vi.mock("../src/api/dashboard", () => ({
  dashboard: {
    get: (...args: unknown[]) => getDashboard(...args),
  },
}));

describe("served project control flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useProjectStore.setState({ selectedProjectId: null, dashboard: null });
    listProjects.mockResolvedValue([demoProject]);
    getDashboard.mockResolvedValue(demoDashboard);
  });

  it("shows project creation and XML/XER schedule intake in the authenticated app", async () => {
    render(
      <MemoryRouter initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /piloto vial awp/i })).toBeInTheDocument();
    });

    expect(screen.getByRole("heading", { name: /project shell/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create project shell/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /project workspace and control flow/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /control dashboard/i })).toBeInTheDocument();
    expect(screen.getAllByText(/xml\/xer/i).length).toBeGreaterThan(0);
    expect(screen.getByLabelText(/schedule xml or xer/i)).toBeInTheDocument();
    expect(screen.getAllByText(/data quality gate/i).length).toBeGreaterThan(0);
  });

  it("uploads the selected XML/XER file to the active project", async () => {
    uploadSchedule.mockResolvedValue({ id: 20, file_name: "baseline.xer", quality_score: 92 });
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    const input = screen.getByLabelText(/schedule xml or xer/i);
    const file = new File(["%T\tTASK"], "baseline.xer", { type: "application/octet-stream" });

    await user.upload(input, file);

    await waitFor(() => {
      expect(uploadSchedule).toHaveBeenCalledWith("tok", 1, file);
    });
    expect(await screen.findByText(/baseline.xer uploaded/i)).toBeInTheDocument();
  });

  it("navigates between control flow views from the side rail", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });

    expect(screen.getByRole("button", { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /control dashboard/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /costs/i }));
    expect(screen.getByRole("heading", { name: /cost control/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /dashboard/i }));
    expect(screen.getByRole("heading", { name: /control dashboard/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /baseline/i }));
    expect(screen.getByRole("heading", { name: /baseline control/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /work packages/i }));
    expect(screen.getByRole("heading", { name: /awp minimum register/i })).toBeInTheDocument();
  });
});
