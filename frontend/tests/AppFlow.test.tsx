import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { ApiError } from "../src/api/client";
import { useProjectStore } from "../src/store/project";
import type { Dashboard, Project, RoleProfile, User } from "../src/types";

const routerFuture = { v7_relativeSplatPath: true, v7_startTransition: true } as const;

const authLogout = vi.hoisted(() => vi.fn());

const demoProject: Project = {
  id: 1,
  code: "CTRL-DEMO-001",
  name: "Piloto vial AWP",
  phase: "Planning",
  currency: "USD",
  calendar_base: "5x8 Colombia",
  owner: "ANI",
  status: "authorized",
  authorization_date: "2026-05-01",
  authorization_ref: "AFE-DEMO-001",
  configuration: { funding_required: true },
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
  cost_sheet: [
    {
      control_account_id: 101,
      control_account_code: "CA-VIA-CIV-001",
      control_account_name: "Earthworks control account",
      cbs_code: "CBS-4000",
      bac: 120000,
      planned_value: 100000,
      actual_cost: 80000,
      incurred_payment_certificate_value: 60000,
      incurred_warehouse_receipt_value: 20000,
      committed_contract_value: 70000,
      committed_purchase_order_value: 10000,
      committed_cost: 80000,
      earned_value: 90000,
      variance: 10000,
      cpi: 1.125,
    },
  ],
  funding_sources: [
    {
      id: 301,
      project_id: 1,
      code: "FUND-VIA-GOV-OBR-2027",
      name: "Government works funding",
      amount: 250000,
      currency: "USD",
      status: "approved",
      version: 1,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    },
  ],
  control_snapshots: [
    {
      id: 401,
      control_account_id: null,
      period_label: "May",
      data_date: "2026-05-31",
      pv: 120000,
      ev: 90000,
      ac: 80000,
      spi: 0.75,
      cpi: 1.125,
      sv: -30000,
      cv: 10000,
      bac: 200000,
      eac: 177778,
      etc: 97778,
      vac: 22222,
      productivity_index: 0.94,
      created_at: "2026-05-31T00:00:00Z",
    },
  ],
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
    logout: authLogout,
  }),
}));

const listProjects = vi.fn();
const createProject = vi.fn();
const uploadSchedule = vi.fn();
const operationalSetup = vi.fn();
const activitySheets = vi.fn();
const activitySheetRows = vi.fn();
const activitySheetWbsRows = vi.fn();
const loadActivitySheetData = vi.fn();
const assignTeamMember = vi.fn();
const getDashboard = vi.fn();
const matrix = vi.fn();
const wbs = vi.fn();
const controlAccounts = vi.fn();
const cbs = vi.fn();
const costCodes = vi.fn();
const forecastVsFunding = vi.fn();
const closeoutReport = vi.fn();
const rateSheets = vi.fn();
const reconciliationReport = vi.fn();
const businessProcessPolicies = vi.fn();
const businessProcessLineItems = vi.fn();
const businessProcessLineItemRevisions = vi.fn();
const updateBusinessProcessLineItem = vi.fn();
const upsertBusinessProcessPolicy = vi.fn();
const recostRuns = vi.fn();
const exportReconciliationReport = vi.fn();
const controlAuditAgentRuns = vi.fn();
const runControlAuditAgent = vi.fn();
const createAwpDraftPackages = vi.fn();
const createWorkPackageConstraint = vi.fn();
const createFbs = vi.fn();
const createCbs = vi.fn();
const createCbsFundBusinessProcess = vi.fn();
const createCbsWbsBusinessProcess = vi.fn();
const createSovLine = vi.fn();
const createCommitmentFundingLine = vi.fn();
const createRateSheet = vi.fn();
const recostActivitySheet = vi.fn();
const approveBaseline = vi.fn();
const listUsers = vi.fn();
const createUser = vi.fn();
const listRoles = vi.fn();

vi.mock("../src/api/projects", () => ({
  projects: {
    list: (...args: unknown[]) => listProjects(...args),
    create: (...args: unknown[]) => createProject(...args),
    uploadSchedule: (...args: unknown[]) => uploadSchedule(...args),
    operationalSetup: (...args: unknown[]) => operationalSetup(...args),
    activitySheets: (...args: unknown[]) => activitySheets(...args),
    activitySheetRows: (...args: unknown[]) => activitySheetRows(...args),
    activitySheetWbsRows: (...args: unknown[]) => activitySheetWbsRows(...args),
    loadActivitySheetData: (...args: unknown[]) => loadActivitySheetData(...args),
    assignTeamMember: (...args: unknown[]) => assignTeamMember(...args),
  },
}));

vi.mock("../src/api/admin", () => ({
  admin: {
    listUsers: (...args: unknown[]) => listUsers(...args),
    createUser: (...args: unknown[]) => createUser(...args),
    listRoles: (...args: unknown[]) => listRoles(...args),
  },
}));

vi.mock("../src/api/dashboard", () => ({
  dashboard: {
    get: (...args: unknown[]) => getDashboard(...args),
  },
}));

vi.mock("../src/api/integratedControl", () => ({
  integratedControl: {
    matrix: (...args: unknown[]) => matrix(...args),
    wbs: (...args: unknown[]) => wbs(...args),
    controlAccounts: (...args: unknown[]) => controlAccounts(...args),
    cbs: (...args: unknown[]) => cbs(...args),
    costCodes: (...args: unknown[]) => costCodes(...args),
    forecastVsFunding: (...args: unknown[]) => forecastVsFunding(...args),
    closeoutReport: (...args: unknown[]) => closeoutReport(...args),
    rateSheets: (...args: unknown[]) => rateSheets(...args),
    reconciliationReport: (...args: unknown[]) => reconciliationReport(...args),
    businessProcessPolicies: (...args: unknown[]) => businessProcessPolicies(...args),
    businessProcessLineItems: (...args: unknown[]) => businessProcessLineItems(...args),
    businessProcessLineItemRevisions: (...args: unknown[]) => businessProcessLineItemRevisions(...args),
    updateBusinessProcessLineItem: (...args: unknown[]) => updateBusinessProcessLineItem(...args),
    upsertBusinessProcessPolicy: (...args: unknown[]) => upsertBusinessProcessPolicy(...args),
    recostRuns: (...args: unknown[]) => recostRuns(...args),
    exportReconciliationReport: (...args: unknown[]) => exportReconciliationReport(...args),
    controlAuditAgentRuns: (...args: unknown[]) => controlAuditAgentRuns(...args),
    runControlAuditAgent: (...args: unknown[]) => runControlAuditAgent(...args),
    createAwpDraftPackages: (...args: unknown[]) => createAwpDraftPackages(...args),
    createWorkPackageConstraint: (...args: unknown[]) => createWorkPackageConstraint(...args),
    createFbs: (...args: unknown[]) => createFbs(...args),
    createCbs: (...args: unknown[]) => createCbs(...args),
    createCbsFundBusinessProcess: (...args: unknown[]) => createCbsFundBusinessProcess(...args),
    createCbsWbsBusinessProcess: (...args: unknown[]) => createCbsWbsBusinessProcess(...args),
    createSovLine: (...args: unknown[]) => createSovLine(...args),
    createCommitmentFundingLine: (...args: unknown[]) => createCommitmentFundingLine(...args),
    createRateSheet: (...args: unknown[]) => createRateSheet(...args),
    recostActivitySheet: (...args: unknown[]) => recostActivitySheet(...args),
    approveBaseline: (...args: unknown[]) => approveBaseline(...args),
  },
}));

describe("served project control flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useProjectStore.setState({ selectedProjectId: null, dashboard: null });
    listProjects.mockResolvedValue([demoProject]);
    getDashboard.mockResolvedValue(demoDashboard);
    operationalSetup.mockResolvedValue({
      id: 1,
      project_id: 1,
      project_number: "CTRL-DEMO-001",
      setup_template: "Capital Project Controls Template",
      attribute_form: "Project Attribute Form",
      permissions_configured: true,
      modules_configured: true,
      cost_sheet_ready: true,
      funding_sheet_ready: true,
      p6_mapping_ready: true,
      status: "ready",
      readiness_status: "ready",
      readiness_notes: "Ready for controlled data loading.",
      version: 1,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    });
    activitySheets.mockResolvedValue([
      {
        id: 11,
        project_id: 1,
        schedule_import_id: 20,
        source_file_name: "baseline.xml",
        source: "p6_xml",
        status: "validated",
        row_count: 1,
        data_date: "2026-03-11",
        baseline_name: "baseline",
        validation_summary: "1 activities, 0 relationships.",
        version: 1,
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-01T00:00:00Z",
      },
    ]);
    activitySheetWbsRows.mockResolvedValue([
      {
        wbs_code: "PLT-CIV",
        wbs_name: "Obras civiles planta",
        activity_count: 1,
        control_account_count: 1,
        planned_cost: 2500,
        planned_value: 1250,
        unmapped_activity_count: 0,
        needs_review_count: 0,
      },
    ]);
    activitySheetRows.mockResolvedValue([
      {
        id: 21,
        activity_sheet_id: 11,
        external_activity_id: "A100",
        wbs_code: "PLT-CIV",
        activity_name: "Excavacion area planta",
        planned_start: "2026-03-01",
        planned_finish: "2026-03-21",
        total_float_days: 2,
        critical_path: false,
        planned_cost: 2500,
        planned_value: 1250,
        planned_percent: 50,
        cbs_code: "CBS-PLT-CIV-A100",
        control_account_id: 101,
        control_account_code: "CA-PLT-CIV",
        mapping_status: "mapped",
        review_note: "",
      },
    ]);
    matrix.mockResolvedValue([]);
    wbs.mockResolvedValue([
      {
        id: 1,
        parent_id: null,
        code: "PLT-CIV",
        name: "Obras civiles planta",
        level: 1,
        description: "",
        dictionary: "",
        responsible: "",
        status: "draft",
      },
    ]);
    controlAccounts.mockResolvedValue([
      {
        id: 101,
        wbs_id: 1,
        awp_package_id: null,
        code: "CA-PLT-CIV",
        name: "Control Account PLT-CIV",
        responsible: "Project Controls",
        discipline: "Imported Schedule",
        scope: "",
        budget: 0,
        start_date: null,
        finish_date: null,
        cbs_code: "CBS-PLT-CIV-A100",
        contract_ref: "",
        measurement_rule: "",
        earned_value: 0,
        actual_cost: 0,
        forecast: 0,
        lifecycle_status: "active",
        risk_ref: "",
        closure_note: "",
        version: 1,
        updated_at: "2026-05-01T00:00:00Z",
      },
    ]);
    cbs.mockResolvedValue([
      {
        id: 401,
        project_id: 1,
        parent_id: null,
        code: "CBS-PLT-CIV-A100",
        level: 3,
        cost_category: "Civil",
        description: "",
        status: "active",
        version: 1,
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-01T00:00:00Z",
      },
    ]);
    costCodes.mockResolvedValue([]);
    forecastVsFunding.mockResolvedValue({ project_id: 1, rows: [] });
    closeoutReport.mockResolvedValue({
      project_id: 1,
      funding_source_id: null,
      approved_amount: 0,
      committed: 0,
      actual: 0,
      forecast: 0,
      unused_balance: 0,
      open_commitments: 0,
      closed_commitments: 0,
      funding_status: "mixed",
    });
    rateSheets.mockResolvedValue([]);
    reconciliationReport.mockResolvedValue({ project_id: 1, rows: [] });
    businessProcessPolicies.mockResolvedValue([]);
    businessProcessLineItems.mockResolvedValue([]);
    businessProcessLineItemRevisions.mockResolvedValue([]);
    updateBusinessProcessLineItem.mockResolvedValue({
      id: 900,
      process_instance_id: 700,
      amount: 2600,
      quantity: 25,
      description: "Updated line",
      version: 2,
    });
    upsertBusinessProcessPolicy.mockResolvedValue({
      id: 1,
      project_id: 1,
      process_code: "BP-CBS-WBS",
      action: "approve_baseline",
      required_role: "Control Manager",
      permission_key: "can_approve_workflow",
      status: "active",
      version: 1,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    });
    recostRuns.mockResolvedValue([]);
    exportReconciliationReport.mockResolvedValue(new Blob(["demo"]));
    controlAuditAgentRuns.mockResolvedValue([]);
    runControlAuditAgent.mockResolvedValue({
      id: 1,
      project_id: 1,
      agent_code: "control_audit",
      agent_name: "AI Control Auditor",
      run_mode: "deterministic",
      model_name: "deterministic-control-audit-v1",
      status: "completed",
      score: 70,
      summary: "Control Audit Agent found 2 finding(s): 1 high and 1 medium priority.",
      created_by: "Ana Control",
      created_at: "2026-05-01T00:00:00Z",
      findings: [],
    });
    createAwpDraftPackages.mockResolvedValue({
      id: 2,
      project_id: 1,
      agent_code: "control_audit",
      agent_name: "AI Control Auditor",
      run_mode: "deterministic",
      model_name: "deterministic-control-audit-v1",
      status: "completed",
      score: 100,
      summary: "Created 3 draft AWP package(s) and 5 readiness constraint(s). Skipped 0 existing package(s).",
      created_by: "Ana Control",
      created_at: "2026-05-01T00:05:00Z",
      findings: [],
    });
    createWorkPackageConstraint.mockResolvedValue({
      id: 901,
      work_package_id: 501,
      constraint_type: "Materials",
      description: "Confirm valves are bagged and tagged for IWP release.",
      owner_role: "Workface Planner",
      required_by: "2026-06-10",
      status: "open",
      priority: "high",
      evidence_ref: "MAT-VALVES-001",
      closure_note: "",
      exception_ref: "",
      closed_by: "",
      closed_on: null,
      blocking: true,
      version: 1,
      updated_at: "2026-05-01T00:00:00Z",
    });
    createFbs.mockResolvedValue({});
    createCbs.mockResolvedValue({ id: 402, code: "CBS-NEW", cost_category: "Civil" });
    createCbsFundBusinessProcess.mockResolvedValue({ id: 701, record_no: "BP-CBS-FUND-0001", current_step: "Control Review" });
    createCbsWbsBusinessProcess.mockResolvedValue({ id: 700, record_no: "BP-CBS-WBS-0001", current_step: "Budget Review" });
    createSovLine.mockResolvedValue({ id: 1, line_no: "10" });
    createCommitmentFundingLine.mockResolvedValue({ id: 1 });
    createRateSheet.mockResolvedValue({ id: 1, code: "RS-001" });
    recostActivitySheet.mockResolvedValue({ updated_rows: 1, recost_run_id: 1 });
    approveBaseline.mockResolvedValue({ project_id: 1, project_status: "baseline_approved" });
    listUsers.mockResolvedValue([
      {
        id: 1,
        email: "carlos.planner@demo.local",
        full_name: "Carlos Planner",
        title: "Planner",
        status: "active",
      },
    ] satisfies User[]);
    listRoles.mockResolvedValue([
      {
        role: "Control Manager",
        description: "Owns setup",
        can_capture_progress: true,
        can_capture_cost: true,
        can_approve_workflow: true,
        can_manage_contract: true,
        can_configure: true,
      },
      {
        role: "Planner",
        description: "Loads schedule",
        can_capture_progress: true,
        can_capture_cost: false,
        can_approve_workflow: false,
        can_manage_contract: false,
        can_configure: false,
      },
    ] satisfies RoleProfile[]);
  });

  it("clears expired sessions instead of rendering the workspace as unavailable", async () => {
    listProjects.mockRejectedValue(new ApiError(401, '{"detail":"Invalid or expired token"}'));

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(authLogout).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByRole("heading", { name: /workspace unavailable/i })).not.toBeInTheDocument();
  });

  it("opens the selected project dashboard before optional project creation", async () => {
    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /piloto vial awp/i })).toBeInTheDocument();
    });

    expect(screen.getByRole("region", { name: /project workspace and control flow/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /control dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /control dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /dashboard overview/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /control mix/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /workload by area/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /evm s-curve/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /cbs cost codes/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /fbs funding codes/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^project$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /new project/i })).toBeInTheDocument();
    const controlFlowRail = screen.getByRole("complementary", { name: /control flow/i });
    const projectCreatePanel = screen.getByRole("region", { name: /^project$/i });
    expect(controlFlowRail.compareDocumentPosition(projectCreatePanel) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(screen.queryByText(/shell/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /shell/i })).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/shell/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create project/i })).not.toBeInTheDocument();
    expect(screen.getAllByText(/xml\/xer/i).length).toBeGreaterThan(0);
    expect(screen.getByLabelText(/schedule xml or xer/i)).toBeInTheDocument();
    expect(screen.getAllByText(/data quality gate/i).length).toBeGreaterThan(0);
  });

  it("expands project creation only when requested", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    expect(screen.queryByRole("button", { name: /create project/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /new project/i }));

    expect(screen.getByRole("button", { name: /^create project$/i })).toBeInTheDocument();
    expect(screen.queryByText(/shell/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/shell/i)).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText(/project control name/i)).toBeInTheDocument();
  });

  it("creates a project with authorization and control configuration fields", async () => {
    const user = userEvent.setup();
    const createdProject: Project = {
      id: 2,
      code: "MIN-ABC",
      name: "Mining integrated control",
      phase: "Planning",
      currency: "USD",
      calendar_base: "5x8 Colombia",
      owner: "Owner PMO",
      status: "authorized",
      authorization_date: "2026-05-12",
      authorization_ref: "AFE-INT-001",
      configuration: { funding_required: true, control_level: "control_account" },
      start_date: "2026-06-01",
      finish_date: "2027-06-30",
    };
    createProject.mockResolvedValue(createdProject);

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /new project/i }));
    const projectPanel = screen.getByRole("region", { name: /^project$/i });

    fireEvent.change(within(projectPanel).getByLabelText(/^code$/i), { target: { value: "MIN-ABC" } });
    fireEvent.change(within(projectPanel).getByPlaceholderText(/project control name/i), {
      target: { value: "Mining integrated control" },
    });
    fireEvent.change(within(projectPanel).getByLabelText(/owner/i), { target: { value: "Owner PMO" } });
    fireEvent.change(within(projectPanel).getByLabelText(/base calendar/i), { target: { value: "5x8 Colombia" } });
    fireEvent.change(within(projectPanel).getByLabelText(/authorization reference/i), {
      target: { value: "AFE-INT-001" },
    });
    fireEvent.change(within(projectPanel).getByLabelText(/authorization date/i), { target: { value: "2026-05-12" } });
    fireEvent.change(within(projectPanel).getByLabelText(/status/i), { target: { value: "authorized" } });
    expect(within(projectPanel).getByLabelText(/funding required/i)).toBeChecked();
    await user.click(screen.getByRole("button", { name: /^create project$/i }));

    await waitFor(() => {
      expect(createProject).toHaveBeenCalledWith(
        "tok",
        expect.objectContaining({
          code: "MIN-ABC",
          name: "Mining integrated control",
          owner: "Owner PMO",
          calendar_base: "5x8 Colombia",
          status: "authorized",
          authorization_date: "2026-05-12",
          authorization_ref: "AFE-INT-001",
          configuration: { funding_required: true, control_level: "control_account" },
        }),
      );
    });
  });

  it("uploads the selected XML/XER file to the active project", async () => {
    uploadSchedule.mockResolvedValue({ id: 20, file_name: "baseline.xer", quality_score: 92 });
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
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
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
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

  it("renders production hardening controls for BP policies, line versions, exports and recost history", async () => {
    const user = userEvent.setup();
    getDashboard.mockResolvedValue({
      ...demoDashboard,
      business_processes: [
        {
          id: 700,
          process_code: "BP-CBS-WBS",
          process_name: "CBS + WBS Code",
          record_no: "BP-CBS-WBS-0001",
          title: "Budget by WBS and CBS",
          status: "in_review",
          current_step: "Budget Review",
          ball_in_court: "Project Controls",
          trigger_entity_type: "Project",
          trigger_entity_id: 1,
          created_at: "2026-05-01T00:00:00Z",
          updated_at: "2026-05-01T00:00:00Z",
          version: 1,
        },
      ],
    } as Dashboard);
    businessProcessPolicies.mockResolvedValue([
      {
        id: 1,
        project_id: 1,
        process_code: "BP-CBS-WBS",
        action: "approve_baseline",
        required_role: "Control Manager",
        permission_key: "can_approve_workflow",
        status: "active",
        version: 1,
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-01T00:00:00Z",
      },
    ]);
    businessProcessLineItems.mockResolvedValue([
      {
        id: 900,
        process_instance_id: 700,
        line_type: "cbs_wbs",
        wbs_id: 1,
        cbs_id: 401,
        funding_source_id: 301,
        control_account_id: 101,
        cost_code_id: 501,
        amount: 2500,
        quantity: 25,
        description: "Initial controlled line",
        status: "active",
        version: 1,
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-01T00:00:00Z",
      },
    ]);
    businessProcessLineItemRevisions.mockResolvedValue([
      {
        id: 1,
        line_item_id: 900,
        process_instance_id: 700,
        previous_version: 1,
        new_version: 2,
        previous_amount: 2500,
        new_amount: 2600,
        previous_quantity: 25,
        new_quantity: 25,
        previous_description: "Initial controlled line",
        new_description: "Updated line",
        previous_status: "active",
        new_status: "active",
        change_note: "Controlled edit",
        changed_by: "Ana Control",
        created_at: "2026-05-01T00:00:00Z",
      },
    ]);
    recostRuns.mockResolvedValue([
      {
        id: 1,
        activity_sheet_id: 11,
        rate_sheet_id: 1,
        run_no: 1,
        updated_rows: 1,
        total_planned_cost: 3000,
        total_planned_value: 1500,
        created_by: "Ana Control",
        created_at: "2026-05-01T00:00:00Z",
        lines: [],
      },
    ]);
    controlAuditAgentRuns.mockResolvedValue([
      {
        id: 1,
        project_id: 1,
        agent_code: "control_audit",
        agent_name: "AI Control Auditor",
        run_mode: "deterministic",
        model_name: "deterministic-control-audit-v1",
        status: "completed",
        score: 70,
        summary: "Control Audit Agent found 2 finding(s): 1 high and 1 medium priority.",
        created_by: "Ana Control",
        created_at: "2026-05-01T00:00:00Z",
        findings: [
          {
            id: 10,
            run_id: 1,
            severity: "high",
            category: "bp_policy",
            title: "BP-CBS-WBS approval policy is not configured",
            evidence: "BP-CBS-WBS-0001 is active without an approve policy.",
            recommendation: "Configure BP Permissions before production approvals.",
            owner_role: "Control Manager",
            entity_type: "BusinessProcessInstance",
            entity_id: 700,
            status: "open",
            created_at: "2026-05-01T00:00:00Z",
          },
        ],
      },
    ]);
    reconciliationReport.mockResolvedValue({
      project_id: 1,
      rows: [
        {
          wbs_code: "PLT-CIV",
          cbs_code: "CBS-PLT-CIV-A100",
          fbs_code: "FUND-VIA-GOV-OBR-2027",
          control_account_code: "CA-PLT-CIV",
          contract_ref: "CTR-001",
          budget: 2500,
          committed: 0,
          funded_amount: 0,
          sov_amount: 0,
          forecast: 2600,
          variance: -100,
        },
      ],
    });

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /integrated control/i }));

    expect(await screen.findByRole("heading", { name: /bp permissions/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /line versions/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /ai control auditor/i })).toBeInTheDocument();
    expect(screen.getByText(/senior awp packaging advisor/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /export xlsx/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /export pdf/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run audit/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create draft packages/i })).toBeInTheDocument();
    expect(screen.getByText(/approval policy is not configured/i)).toBeInTheDocument();
    expect(screen.getByText(/run 1/i)).toBeInTheDocument();
    expect(screen.getByText(/v1 to v2/i)).toBeInTheDocument();
    expect(businessProcessPolicies).toHaveBeenCalledWith("tok", 1);
    expect(businessProcessLineItems).toHaveBeenCalledWith("tok", 1, 700);
    expect(recostRuns).toHaveBeenCalledWith("tok", 1, 11);
    expect(controlAuditAgentRuns).toHaveBeenCalledWith("tok", 1);

    await user.click(screen.getByRole("button", { name: /run audit/i }));
    await waitFor(() => {
      expect(runControlAuditAgent).toHaveBeenCalledWith("tok", 1);
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /create draft packages/i })).toBeEnabled();
    });

    await user.click(screen.getByRole("button", { name: /create draft packages/i }));
    await waitFor(() => {
      expect(createAwpDraftPackages).toHaveBeenCalledWith("tok", 1);
    });
  });

  it("shows the WBS Sheet roll-up from the latest Activity Sheet", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /project setup/i }));

    expect(await screen.findByRole("heading", { name: /wbs sheet/i })).toBeInTheDocument();
    expect(screen.getAllByText("PLT-CIV").length).toBeGreaterThan(0);
    expect(screen.getByText("Obras civiles planta")).toBeInTheDocument();
    expect(screen.getAllByText("$1,250").length).toBeGreaterThan(0);
    expect(activitySheetWbsRows).toHaveBeenCalledWith("tok", 1, 11);
  });

  it("shows package POC and lets users add manual constraints", async () => {
    const user = userEvent.setup();
    getDashboard.mockResolvedValue({
      ...demoDashboard,
      awp_summary: {
        ...demoDashboard.awp_summary,
        total_packages: 1,
        cwp_count: 1,
      },
      work_packages: [
        {
          id: 501,
          control_account_id: 101,
          parent_id: null,
          package_type: "CWP",
          code: "CWP-PLT-CIV",
          title: "Civil package",
          discipline: "Civil",
          sequence_no: 1,
          path_of_construction: "North-to-south civil path",
          owner_role: "Workface Planner",
          readiness_status: "constraint_review",
          planned_start: null,
          planned_finish: null,
          release_required_on: null,
          progress_percent: 0,
          version: 1,
          updated_at: "2026-05-01T00:00:00Z",
        },
      ],
      work_package_constraints: [],
      control_accounts: [
        {
          id: 101,
          wbs_id: 1,
          awp_package_id: 501,
          code: "CA-PLT-CIV",
          name: "Control Account PLT-CIV",
          responsible: "Project Controls",
          discipline: "Civil",
          scope: "",
          budget: 0,
          start_date: null,
          finish_date: null,
          cbs_code: "CBS-PLT-CIV-A100",
          contract_ref: "",
          measurement_rule: "",
          earned_value: 0,
          actual_cost: 0,
          forecast: 0,
          lifecycle_status: "active",
          risk_ref: "",
          closure_note: "",
          version: 1,
          updated_at: "2026-05-01T00:00:00Z",
        },
      ],
    } satisfies Dashboard);

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /work packages/i }));

    expect(await screen.findByText(/POC: North-to-south civil path/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Package"), { target: { value: "501" } });
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "Materials" } });
    fireEvent.change(screen.getByLabelText("Required"), { target: { value: "2026-06-10" } });
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "high" } });
    fireEvent.change(screen.getByLabelText("Evidence"), { target: { value: "MAT-VALVES-001" } });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Confirm valves are bagged and tagged for IWP release." },
    });
    await user.click(screen.getByRole("button", { name: /add constraint/i }));

    await waitFor(() => {
      expect(createWorkPackageConstraint).toHaveBeenCalledWith("tok", 1, 501, {
        constraint_type: "Materials",
        description: "Confirm valves are bagged and tagged for IWP release.",
        owner_role: "Workface Planner",
        required_by: "2026-06-10",
        status: "open",
        priority: "high",
        evidence_ref: "MAT-VALVES-001",
        blocking: true,
      });
    });
  });

  it("creates a user with password and assigns a project role from the dashboard", async () => {
    const user = userEvent.setup();
    const createdUser: User = {
      id: 2,
      email: "nuevo.admin@demo.local",
      full_name: "Nuevo Admin",
      title: "Admin",
      status: "active",
    };
    createUser.mockResolvedValue(createdUser);
    assignTeamMember.mockResolvedValue({
      user: createdUser,
      membership: {
        id: 12,
        project_id: 1,
        user_id: 2,
        role: "Control Manager",
        can_capture_progress: true,
        can_capture_cost: true,
        can_approve_workflow: true,
        can_manage_contract: true,
        can_configure: true,
      },
    });

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /users & roles/i }));

    expect(screen.getByRole("heading", { name: /users & roles/i })).toBeInTheDocument();
    await user.type(screen.getByLabelText(/full name/i), "Nuevo Admin");
    await user.type(screen.getByLabelText(/login email/i), "nuevo.admin@demo.local");
    await user.clear(screen.getByLabelText(/temporary password/i));
    await user.type(screen.getByLabelText(/temporary password/i), "1234");
    await user.click(screen.getByRole("button", { name: /create user & assign role/i }));

    await waitFor(() => {
      expect(createUser).toHaveBeenCalledWith(
        "tok",
        expect.objectContaining({
          email: "nuevo.admin@demo.local",
          full_name: "Nuevo Admin",
          password: "1234",
        }),
      );
    });
    expect(assignTeamMember).toHaveBeenCalledWith("tok", 1, { role: "Control Manager", user_id: 2 });
  });
});
