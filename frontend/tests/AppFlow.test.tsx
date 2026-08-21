import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type ValidationModeGlobal = typeof globalThis & { __PYPMIS_VALIDATION_MODE__?: boolean };

function setValidationMode(enabled: boolean) {
  (globalThis as ValidationModeGlobal).__PYPMIS_VALIDATION_MODE__ = enabled;
}
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
  schedule_quality_metrics: [],
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
  claims_forensic_summary: {
    total_claims: 0,
    notice_count: 0,
    compliant_notices: 0,
    late_notices: 0,
    impact_analyses: 0,
    quantified_claims: 0,
    total_claimed_cost: 0,
    total_schedule_impact_days: 0,
    forensic_readiness_score: 0,
  },
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
const deleteProject = vi.fn();
const uploadSchedule = vi.fn();
const guidedFlow = vi.fn();
const processFlowBoard = vi.fn();
const confirmScheduleCurrency = vi.fn();
const operationalSetup = vi.fn();
const updateOperationalSetup = vi.fn();
const activitySheets = vi.fn();
const activitySheetRows = vi.fn();
const activitySheetWbsRows = vi.fn();
const scheduleActivities = vi.fn();
const scheduleRelationships = vi.fn();
const loadActivitySheetData = vi.fn();
const quantityTakeoffRuns = vi.fn();
const quantityTakeoffLines = vi.fn();
const loadQuantityTakeoff = vi.fn();
const bimQuantityRules = vi.fn();
const colombiaApuCatalog = vi.fn();
const syncColombiaApuCatalog = vi.fn();
const suggestQuantityApuItems = vi.fn();
const approveQuantityApuItems = vi.fn();
const assignQuantityControlCodes = vi.fn();
const linkQuantityTakeoffBimModel = vi.fn();
const processGeometryMeasurements = vi.fn();
const recalculateQuantityRules = vi.fn();
const updateBimQuantityRule = vi.fn();
const approveControlledMeasurements = vi.fn();
const assignTeamMember = vi.fn();
const getDashboard = vi.fn();
const matrix = vi.fn();
const wbs = vi.fn();
const createWbs = vi.fn();
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
const updateUser = vi.fn();
const resetUserPassword = vi.fn();
const deactivateUser = vi.fn();
const listRoles = vi.fn();
const removeTeamMember = vi.fn();
const organizationSecurityOverview = vi.fn();
const updateOrganizationSecurity = vi.fn();
const createOrganizationUnit = vi.fn();
const createSecurityGroup = vi.fn();
const addSecurityGroupMember = vi.fn();
const removeSecurityGroupMember = vi.fn();
const createSecurityRole = vi.fn();
const createSecurityAssignment = vi.fn();
const revokeSecurityAssignment = vi.fn();
const effectiveSecurityAccess = vi.fn();

vi.mock("../src/api/projects", () => ({
  projects: {
    list: (...args: unknown[]) => listProjects(...args),
    create: (...args: unknown[]) => createProject(...args),
    deleteProject: (...args: unknown[]) => deleteProject(...args),
    uploadSchedule: (...args: unknown[]) => uploadSchedule(...args),
    guidedFlow: (...args: unknown[]) => guidedFlow(...args),
    processFlowBoard: (...args: unknown[]) => processFlowBoard(...args),
    confirmScheduleCurrency: (...args: unknown[]) => confirmScheduleCurrency(...args),
    operationalSetup: (...args: unknown[]) => operationalSetup(...args),
    updateOperationalSetup: (...args: unknown[]) => updateOperationalSetup(...args),
    activitySheets: (...args: unknown[]) => activitySheets(...args),
    activitySheetRows: (...args: unknown[]) => activitySheetRows(...args),
    activitySheetWbsRows: (...args: unknown[]) => activitySheetWbsRows(...args),
    scheduleActivities: (...args: unknown[]) => scheduleActivities(...args),
    scheduleRelationships: (...args: unknown[]) => scheduleRelationships(...args),
    loadActivitySheetData: (...args: unknown[]) => loadActivitySheetData(...args),
    quantityTakeoffRuns: (...args: unknown[]) => quantityTakeoffRuns(...args),
    quantityTakeoffLines: (...args: unknown[]) => quantityTakeoffLines(...args),
    loadQuantityTakeoff: (...args: unknown[]) => loadQuantityTakeoff(...args),
    bimQuantityRules: (...args: unknown[]) => bimQuantityRules(...args),
    colombiaApuCatalog: (...args: unknown[]) => colombiaApuCatalog(...args),
    syncColombiaApuCatalog: (...args: unknown[]) => syncColombiaApuCatalog(...args),
    suggestQuantityApuItems: (...args: unknown[]) => suggestQuantityApuItems(...args),
    approveQuantityApuItems: (...args: unknown[]) => approveQuantityApuItems(...args),
    assignQuantityControlCodes: (...args: unknown[]) => assignQuantityControlCodes(...args),
    linkQuantityTakeoffBimModel: (...args: unknown[]) => linkQuantityTakeoffBimModel(...args),
    processGeometryMeasurements: (...args: unknown[]) => processGeometryMeasurements(...args),
    recalculateQuantityRules: (...args: unknown[]) => recalculateQuantityRules(...args),
    updateBimQuantityRule: (...args: unknown[]) => updateBimQuantityRule(...args),
    approveControlledMeasurements: (...args: unknown[]) => approveControlledMeasurements(...args),
    assignTeamMember: (...args: unknown[]) => assignTeamMember(...args),
    removeTeamMember: (...args: unknown[]) => removeTeamMember(...args),
  },
}));

vi.mock("../src/api/admin", () => ({
  admin: {
    listUsers: (...args: unknown[]) => listUsers(...args),
    createUser: (...args: unknown[]) => createUser(...args),
    updateUser: (...args: unknown[]) => updateUser(...args),
    resetUserPassword: (...args: unknown[]) => resetUserPassword(...args),
    deactivateUser: (...args: unknown[]) => deactivateUser(...args),
    listRoles: (...args: unknown[]) => listRoles(...args),
  },
}));

vi.mock("../src/api/organizationSecurity", () => ({
  organizationSecurity: {
    overview: (...args: unknown[]) => organizationSecurityOverview(...args),
    updateOrganization: (...args: unknown[]) => updateOrganizationSecurity(...args),
    createUnit: (...args: unknown[]) => createOrganizationUnit(...args),
    createGroup: (...args: unknown[]) => createSecurityGroup(...args),
    addGroupMember: (...args: unknown[]) => addSecurityGroupMember(...args),
    removeGroupMember: (...args: unknown[]) => removeSecurityGroupMember(...args),
    createRole: (...args: unknown[]) => createSecurityRole(...args),
    createAssignment: (...args: unknown[]) => createSecurityAssignment(...args),
    revokeAssignment: (...args: unknown[]) => revokeSecurityAssignment(...args),
    effectiveAccess: (...args: unknown[]) => effectiveSecurityAccess(...args),
  },
}));

vi.mock("../src/api/dashboard", () => ({
  dashboard: {
    get: (...args: unknown[]) => getDashboard(...args),
  },
}));

const bimList = vi.fn();
const bimUpload = vi.fn();
const bimRemove = vi.fn();
const bimSource = vi.fn();
const bimManifest = vi.fn();
const bimPrepareGeometryCache = vi.fn();
const bimGeometryCache = vi.fn();
const bimElementProperties = vi.fn();

vi.mock("../src/api/bimModels", () => ({
  bimModels: {
    list: (...args: unknown[]) => bimList(...args),
    upload: (...args: unknown[]) => bimUpload(...args),
    remove: (...args: unknown[]) => bimRemove(...args),
    source: (...args: unknown[]) => bimSource(...args),
    manifest: (...args: unknown[]) => bimManifest(...args),
    prepareGeometryCache: (...args: unknown[]) => bimPrepareGeometryCache(...args),
    geometryCache: (...args: unknown[]) => bimGeometryCache(...args),
    elementProperties: (...args: unknown[]) => bimElementProperties(...args),
  },
}));

const uploadedBimModel = {
  id: 901,
  project_id: 1,
  source_file_name: "coordination-model.ifc",
  revision_id: "REV-1",
  status: "registered",
  model_identity: {},
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
};

vi.mock("../src/api/integratedControl", () => ({
  integratedControl: {
    matrix: (...args: unknown[]) => matrix(...args),
    wbs: (...args: unknown[]) => wbs(...args),
    createWbs: (...args: unknown[]) => createWbs(...args),
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
  afterEach(() => {
    delete (globalThis as ValidationModeGlobal).__PYPMIS_VALIDATION_MODE__;
  });

  beforeEach(() => {
    vi.clearAllMocks();
    useProjectStore.setState({ selectedProjectId: null, dashboard: null });
    listProjects.mockResolvedValue([demoProject]);
    bimQuantityRules.mockResolvedValue([]);
    colombiaApuCatalog.mockResolvedValue([]);
    bimList.mockResolvedValue([]);
    bimUpload.mockResolvedValue(uploadedBimModel);
    bimRemove.mockResolvedValue({});
    bimSource.mockRejectedValue(new Error("no source in tests"));
    bimManifest.mockResolvedValue({});
    bimPrepareGeometryCache.mockRejectedValue(new Error("no geometry cache in tests"));
    bimGeometryCache.mockRejectedValue(new Error("no geometry cache in tests"));
    bimElementProperties.mockResolvedValue({});
    syncColombiaApuCatalog.mockResolvedValue({ status: "ok", item_count: 0 });
    suggestQuantityApuItems.mockResolvedValue([]);
    approveQuantityApuItems.mockResolvedValue([]);
    assignQuantityControlCodes.mockResolvedValue([]);
    linkQuantityTakeoffBimModel.mockResolvedValue({});
    processGeometryMeasurements.mockResolvedValue({});
    recalculateQuantityRules.mockResolvedValue({});
    updateBimQuantityRule.mockResolvedValue({});
    approveControlledMeasurements.mockResolvedValue({});
    deleteProject.mockResolvedValue({ status: "deleted", project_id: demoProject.id });
    getDashboard.mockResolvedValue(demoDashboard);
    guidedFlow.mockResolvedValue({
      tenant: { id: 1, name: "Demo Energy Infrastructure", slug: "demo-energy", base_currency: "COP" },
      project: {
        id: demoProject.id,
        code: demoProject.code,
        name: demoProject.name,
        status: demoProject.status,
        currency: demoProject.currency,
      },
      steps: [
        {
          key: "tenant",
          label: "Tenant workspace",
          state: "complete",
          summary: "Demo Energy Infrastructure / COP",
          next_action: "Select project",
          owner_role: "Admin",
          target_view: "dashboard",
          blocking_count: 0,
        },
        {
          key: "schedule",
          label: "Schedule intake",
          state: "complete",
          summary: "0 activities imported",
          next_action: "Load XER/XML schedule",
          owner_role: "Planner",
          target_view: "schedule-intake",
          blocking_count: 0,
        },
        {
          key: "setup",
          label: "Project Setup",
          state: "review_required",
          summary: "Control structures need periodic review",
          next_action: "Review setup",
          owner_role: "Project Controls",
          target_view: "setup",
          blocking_count: 0,
        },
        {
          key: "cost_currency",
          label: "Cost and currency gate",
          state: "blocked",
          summary: "Confirm detected currency before baseline approval.",
          next_action: "Confirm currency",
          owner_role: "Project Controls",
          target_view: "baseline",
          blocking_count: 1,
        },
        {
          key: "baseline",
          label: "Baseline",
          state: "blocked",
          summary: "Baseline approval is gated by schedule cost and currency evidence",
          next_action: "Approve baseline",
          owner_role: "Control Manager",
          target_view: "baseline",
          blocking_count: 1,
        },
        {
          key: "progress",
          label: "Progress",
          state: "review_required",
          summary: "Progress capture is available after baseline",
          next_action: "Capture progress",
          owner_role: "Field Engineer",
          target_view: "progress",
          blocking_count: 0,
        },
        {
          key: "integrated_control",
          label: "Integrated Control",
          state: "review_required",
          summary: "Conciliation and control governance review",
          next_action: "Review integrated control",
          owner_role: "Project Controls",
          target_view: "integrated-control",
          blocking_count: 0,
        },
        {
          key: "evidence",
          label: "Evidence",
          state: "review_required",
          summary: "Document evidence register ready",
          next_action: "Review evidence",
          owner_role: "Document Controller",
          target_view: "evidence",
          blocking_count: 0,
        },
        {
          key: "awp",
          label: "Work Packages",
          state: "review_required",
          summary: "AWP register review",
          next_action: "Review Work Packages",
          owner_role: "Workface Planner",
          target_view: "work-packages",
          blocking_count: 0,
        },
      ],
      next_action: {
        key: "cost_currency",
        label: "Confirm currency",
        target_view: "baseline",
        disabled: false,
        reason: "Confirm detected currency before baseline approval.",
      },
      cost_currency_gate: {
        project_id: demoProject.id,
        schedule_import_id: 20,
        detected_currency: "USD",
        currency_confidence: "detected",
        currency_source: "Currency",
        currency_confirmed: false,
        total_imported_cost: 2500,
        cost_loaded_activity_count: 1,
        cost_loaded_activity_percent: 100,
        missing_cost_activity_count: 0,
        cost_source_summary: { "ResourceAssignment.PlannedCost": 1 },
        state: "review_required",
        message: "Confirm detected currency before baseline approval.",
      },
    });
    processFlowBoard.mockResolvedValue({
      project_id: 1,
      overall_status: "blocked",
      completion_percent: 42.3,
      lanes: [
        {
          key: "owner",
          label: "Owner / Direction",
          owner_role: "Owner / Control Manager",
          items: [
            {
              key: "project_authorization",
              label: "Project authorization",
              status: "complete",
              owner_role: "Owner / Direction",
              evidence: "authorized; authorization reference AFE-DEMO-001.",
              next_action: "Maintain approval evidence",
              acceptance_criteria: ["Project code, sponsor, phase, currency and authorization reference are approved."],
              target_view: "setup",
            },
          ],
        },
        {
          key: "project_controls",
          label: "Project Controls",
          owner_role: "Control Manager",
          items: [
            {
              key: "role_matrix",
              label: "Role matrix and approvals",
              status: "review_required",
              owner_role: "Control Manager",
              evidence: "1 project member; 0 BP approval policies.",
              next_action: "Load client role matrix and BP approval policies",
              acceptance_criteria: [
                "Client role matrix is configured for Planning, Controls, Cost/Funding, AWP, Contracts and Document Control.",
              ],
              target_view: "admin",
            },
          ],
        },
        {
          key: "planning",
          label: "Planning / P6",
          owner_role: "Planner",
          items: [
            {
              key: "activity_sheet",
              label: "System Activity Sheet",
              status: "complete",
              owner_role: "Planner",
              evidence: "1 activity sheet; latest import baseline.xml.",
              next_action: "Review Activity Sheet rows",
              acceptance_criteria: ["Activity Sheet is created from the controlled P6 XML/XER source."],
              target_view: "setup",
            },
          ],
        },
        {
          key: "cost_funding",
          label: "Cost / Funding",
          owner_role: "Cost Controller",
          items: [
            {
              key: "fbs_funding",
              label: "FBS / Funding codes",
              status: "complete",
              owner_role: "Cost / Funding",
              evidence: "1 funding code configured.",
              next_action: "Monitor available funds",
              acceptance_criteria: [
                "Each fund has source, type, authorization, restrictions, approved amount, currency and status.",
              ],
              target_view: "costs",
            },
          ],
        },
        {
          key: "awp_construction",
          label: "AWP / Construction",
          owner_role: "Workface Planner",
          items: [
            {
              key: "bim_quantity_takeoff",
              label: "BIM Manager",
              status: "review_required",
              owner_role: "BIM / Workface Planner",
              evidence: "1 run(s); 2 line(s); 1 mapped; 1 need mapping.",
              next_action: "Review unmapped BIM/IFC or Excel quantity lines",
              acceptance_criteria: [
                "Controlled physical quantity items are consolidated from BIM/IFC or Excel quantities.",
              ],
              target_view: "quantity-takeoff",
            },
            {
              key: "awp_packages",
              label: "AWP package chain",
              status: "blocked",
              owner_role: "Workface Planner",
              evidence: "0 packages; 0 blocking constraints.",
              next_action: "Create CWA/CWP/EWP/PWP/IWP/TWP/TOP package drafts",
              acceptance_criteria: [
                "Packages are tied to WBS, control account, path of construction and responsible owner.",
              ],
              target_view: "work-packages",
            },
          ],
        },
      ],
    });
    confirmScheduleCurrency.mockResolvedValue({
      id: 20,
      source: "p6_xml",
      file_name: "baseline.xml",
      status: "validated",
      data_date: "2026-03-11",
      baseline_name: "baseline",
      quality_score: 92,
      validation_summary: "1 activities, 0 relationships.",
      detected_currency: "USD",
      currency_confidence: "confirmed",
      currency_source: "Currency",
      currency_confirmed: true,
      total_imported_cost: 2500,
      cost_loaded_activity_count: 1,
      cost_loaded_activity_percent: 100,
      cost_source_summary: { "ResourceAssignment.PlannedCost": 1 },
      imported_at: "2026-05-01T00:00:00Z",
    });
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
        cbs_code: "CBS-UNI-PLT-CIV-EARTH",
        control_account_id: 101,
        control_account_code: "CA-PLT-CIV",
        mapping_status: "mapped",
        review_note: "",
      },
    ]);
    scheduleActivities.mockResolvedValue([
      {
        activity_id: null,
        activity_name: "Excavacion area planta",
        critical_path: false,
        external_activity_id: "A100",
        id: 21,
        planned_finish: "2026-03-21",
        planned_start: "2026-03-01",
        schedule_import_id: 20,
        total_float_days: 2,
        wbs_code: "PLT-CIV",
      },
    ]);
    scheduleRelationships.mockResolvedValue([]);
    quantityTakeoffRuns.mockResolvedValue([
      {
        id: 61,
        project_id: 1,
        source_file_name: "bim-quantities.xlsx",
        source_type: "xlsx",
        status: "needs_mapping",
        row_count: 2,
        mapped_line_count: 1,
        unmapped_line_count: 1,
        total_quantity: 15.5,
        validation_summary: "2 quantity line(s): 1 mapped, 1 need mapping.",
        version: 1,
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-01T00:00:00Z",
      },
    ]);
    quantityTakeoffLines.mockResolvedValue([
      {
        id: 71,
        project_id: 1,
        run_id: 61,
        source_row_id: "1",
        element_id: "#20",
        element_guid: "GUID-001",
        ifc_class: "IfcWall",
        category: "Muros",
        family: "Muro concreto",
        type_name: "20 cm",
        instance_name: "Muro eje A",
        project_name: "Proyecto Piloto",
        site_name: "Site A",
        building_name: "Building A",
        storey: "Nivel 1",
        system_name: "",
        zone_name: "Zona A",
        assembly_name: "Modulo Civil",
        classification_system: "MasterFormat",
        classification_code: "03 30 00",
        quantity: 12.5,
        unit: "m3",
        measurement_rule: "NetVolume",
        wbs_code: "PLT-CIV",
        cbs_code: "CBS-UNI-PLT-CIV-EARTH",
        fbs_code: "FUND-VIA-GOV-OBR-2027",
        package_code: "CWP-CIV-001",
        wbs_id: 1,
        cbs_id: 401,
        fbs_id: 501,
        work_package_id: 601,
        mapping_status: "mapped",
        validation_notes: "",
        raw_data: {},
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-01T00:00:00Z",
      },
      {
        id: 72,
        project_id: 1,
        run_id: 61,
        source_row_id: "2",
        element_id: "#21",
        element_guid: "GUID-002",
        ifc_class: "IfcDoor",
        category: "Puertas",
        family: "Puerta madera",
        type_name: "90x210",
        instance_name: "Puerta oficina",
        project_name: "Proyecto Piloto",
        site_name: "Site A",
        building_name: "Building A",
        storey: "Nivel 1",
        system_name: "",
        zone_name: "Zona A",
        assembly_name: "Modulo Arquitectura",
        classification_system: "MasterFormat",
        classification_code: "08 11 00",
        quantity: 3,
        unit: "und",
        measurement_rule: "Count",
        wbs_code: "UNKNOWN-WBS",
        cbs_code: "",
        fbs_code: "FUND-VIA-GOV-OBR-2027",
        package_code: "CWP-ARQ-001",
        wbs_id: null,
        cbs_id: null,
        fbs_id: 501,
        work_package_id: null,
        mapping_status: "needs_mapping",
        validation_notes: "Unknown WBS UNKNOWN-WBS; Missing CBS",
        raw_data: {},
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-01T00:00:00Z",
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
        cbs_code: "CBS-UNI-PLT-CIV-EARTH",
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
        code: "CBS-UNI-PLT-CIV-EARTH",
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
    updateOperationalSetup.mockResolvedValue({
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
    createWbs.mockResolvedValue({
      id: 2,
      parent_id: null,
      code: "WBS-MAN-001",
      name: "Manual WBS",
      level: 1,
      description: "Manual scope",
      dictionary: "",
      responsible: "Ana Control",
      status: "active",
    });
    createFbs.mockResolvedValue({});
    createCbs.mockResolvedValue({ id: 402, code: "CBS-NEW", cost_category: "Civil" });
    createCbsFundBusinessProcess.mockResolvedValue({
      id: 701,
      record_no: "BP-CBS-FUND-0001",
      current_step: "Control Review",
    });
    createCbsWbsBusinessProcess.mockResolvedValue({
      id: 700,
      record_no: "BP-CBS-WBS-0001",
      current_step: "Budget Review",
    });
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
    organizationSecurityOverview.mockResolvedValue({
      organization: {
        id: 1,
        code: "DEMO_ENERGY",
        legal_name: "Demo Energy Infrastructure",
        display_name: "Demo Energy Infrastructure",
        base_currency: "COP",
        country_code: "CO",
        timezone: "America/Bogota",
        default_locale: "es-CO",
        status: "active",
      },
      units: [
        {
          id: 1,
          parent_id: null,
          code: "OPS",
          name: "Operations",
          unit_type: "division",
          manager_user_id: 1,
          status: "active",
          sort_order: 0,
          version: 1,
        },
      ],
      users: [
        {
          id: 1,
          email: "carlos.planner@demo.local",
          full_name: "Carlos Planner",
          title: "Planner",
          status: "active",
        },
      ],
      groups: [
        {
          id: 1,
          code: "PROJECT-CONTROLS",
          name: "Project Controls",
          description: "Control team",
          owner_user_id: 1,
          status: "active",
          version: 1,
          member_ids: [1],
        },
      ],
      permissions: [
        {
          id: 1,
          key: "organization.read",
          resource: "organization",
          action: "read",
          description: "Consultar la empresa.",
          risk_level: "standard",
          status: "active",
        },
        {
          id: 2,
          key: "access.manage",
          resource: "access",
          action: "manage",
          description: "Asignar acceso.",
          risk_level: "critical",
          status: "active",
        },
      ],
      roles: [
        {
          id: 1,
          code: "organization_admin",
          name: "Organization Administrator",
          description: "Tenant administrator",
          is_system: true,
          status: "active",
          version: 1,
          permission_keys: ["organization.read", "access.manage"],
        },
      ],
      assignments: [
        {
          id: 1,
          subject_type: "user",
          subject_id: 1,
          subject_name: "Carlos Planner",
          role_id: 1,
          role_code: "organization_admin",
          role_name: "Organization Administrator",
          scope_type: "organization",
          scope_unit_id: null,
          scope_name: "Organization",
          starts_at: null,
          ends_at: null,
          status: "active",
        },
      ],
      security_events: [],
      authentication: {
        local_authentication: true,
        oidc_available: false,
        access_token_minutes: 30,
        refresh_sessions: false,
        password_hash_policy: "PBKDF2-SHA256 (migración a Argon2id pendiente)",
        active_user_count: 1,
      },
    });
    effectiveSecurityAccess.mockResolvedValue({
      user_id: 1,
      user_name: "Carlos Planner",
      permission_keys: ["organization.read", "access.manage"],
      assignments: [],
    });
    updateUser.mockImplementation((_token, _id, payload) => Promise.resolve({ id: 1, status: "active", ...payload }));
    resetUserPassword.mockResolvedValue({
      id: 1,
      email: "carlos.planner@demo.local",
      full_name: "Carlos Planner",
      title: "Planner",
      status: "active",
    });
    deactivateUser.mockResolvedValue({
      id: 1,
      email: "carlos.planner@demo.local",
      full_name: "Carlos Planner",
      title: "Planner",
      status: "inactive",
    });
    removeTeamMember.mockResolvedValue({ status: "removed" });
  });

  it("clears expired sessions instead of rendering the workspace as unavailable", async () => {
    listProjects.mockRejectedValue(new ApiError(401, '{"detail":"Invalid or expired token"}'));

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
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
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /piloto vial awp/i })).toBeInTheDocument();
    });

    const appBrand = screen.getByRole("banner", { name: /application brand/i });
    expect(appBrand).toBeInTheDocument();
    expect(within(appBrand).getByRole("img", { name: /p&pmis construction ai logo/i })).toBeInTheDocument();
    expect(within(appBrand).getByText("P&Pmis Construction AI", { selector: "strong" })).toBeInTheDocument();
    expect(within(appBrand).getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true })).toHaveTextContent(
      "USER MODE"
    );
    expect(screen.getByRole("region", { name: /project workspace and control flow/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /control dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /dashboard evm/i })).toBeInTheDocument();
    expect(screen.getByText(/earned value management/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /resumen evm/i })).toBeInTheDocument();
    expect(screen.getAllByText(/^BAC$/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^EAC$/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^VAC$/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^SV$/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^CV$/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: /curva s acumulada/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /control mix/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /workload by area/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /cbs cost codes/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /fbs funding codes/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^cost manager$/i })).toBeInTheDocument();
    const guidedRail = screen.getByRole("complementary", { name: /project information flow/i });
    const projectAdmin = screen.getByRole("group", { name: /administrative actions/i });
    expect(within(projectAdmin).getByRole("button", { name: /new project/i })).toBeInTheDocument();
    expect(guidedRail.compareDocumentPosition(projectAdmin) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING
    );
    expect(screen.queryByText(/workspace views/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/shell/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /shell/i })).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/shell/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create project/i })).not.toBeInTheDocument();
    expect(within(guidedRail).getAllByRole("button", { name: /open load schedule/i }).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText(/schedule xml or xer/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/baseline gate/i).length).toBeGreaterThan(0);
  });

  it("uses a simplified project information flow instead of scattered navigation", async () => {
    setValidationMode(true);
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });

    expect(screen.queryByText(/workspace views/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^guided flow$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/review & admin/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: /project information flow/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /project information flow map/i })).not.toBeInTheDocument();

    const validationNav = screen.getByRole("navigation", { name: /validation focus/i });
    expect(within(validationNav).getByRole("button", { name: /dashboard/i })).toHaveAttribute("aria-current", "page");
    const enterpriseStrategyMacroprocess = within(validationNav).getByRole("button", {
      name: "Enterprise Strategy Manager",
      exact: true,
    });
    const projectControlMacroprocess = within(validationNav).getByRole("button", {
      name: "Project Control Manager",
      exact: true,
    });
    const facilityMacroprocess = within(validationNav).getByRole("button", {
      name: "Facility Manager",
      exact: true,
    });
    expect(enterpriseStrategyMacroprocess).toHaveAttribute("aria-expanded", "true");
    expect(projectControlMacroprocess).toHaveAccessibleName("Project Control Manager");
    expect(projectControlMacroprocess).toHaveAttribute("aria-expanded", "true");
    expect(facilityMacroprocess).toHaveAccessibleName("Facility Manager");
    expect(facilityMacroprocess).toHaveAttribute("aria-expanded", "false");
    [
      "Idea & Demand Manager",
      "Portfolio Manager",
      "Funds",
      "Workspaces Manager",
      "Partners",
      "Vendors",
      "Commitments",
    ].forEach((moduleName) => {
      expect(within(validationNav).getByRole("button", { name: moduleName, exact: true })).toBeInTheDocument();
    });
    await user.click(within(validationNav).getByRole("button", { name: "Idea & Demand Manager", exact: true }));
    expect(within(validationNav).getByRole("button", { name: "Idea Lifecycle", exact: true })).toBeInTheDocument();
    expect(within(validationNav).queryByRole("button", { name: "SECOP Bidder", exact: true })).not.toBeInTheDocument();
    await user.click(within(validationNav).getByRole("button", { name: "Idea Lifecycle", exact: true }));
    expect(await screen.findByRole("region", { name: /idea lifecycle/i })).toBeInTheDocument();
    await user.click(within(validationNav).getByRole("button", { name: "Portfolio Manager", exact: true }));
    [
      "Portfolio Structure",
      "Strategic Project Planning Entry",
      "Portfolio Projects",
      "Portfolio Evaluation",
      "Portfolio Budget Planning",
      "Portfolio Cash Flow",
      "Strategic Investment Map",
      "Prioritization Matrix",
      "Gate Decision",
    ].forEach((submoduleName) => {
      expect(within(validationNav).getByRole("button", { name: submoduleName, exact: true })).toBeInTheDocument();
    });
    await user.click(within(validationNav).getByRole("button", { name: "Commitments", exact: true }));
    ["Sales Contracts", "SC Changes", "SC Payments", "Purchase Order", "PO Changes", "PO Payments"].forEach(
      (submoduleName) => {
        expect(within(validationNav).getByRole("button", { name: submoduleName, exact: true })).toBeInTheDocument();
      }
    );
    await user.click(within(validationNav).getByRole("button", { name: "Workspaces Manager", exact: true }));
    expect(within(validationNav).getByText("Asset Creator/Receipt", { exact: true })).toBeInTheDocument();
    await user.click(within(validationNav).getByText("Asset Creator/Receipt", { exact: true }));
    expect(await screen.findByRole("heading", { name: "Asset Creator/Receipt", exact: true })).toBeInTheDocument();
    const scopeManagerModule = within(validationNav).getByRole("button", { name: /scope manager/i });
    expect(scopeManagerModule).toHaveAccessibleName("Scope Manager");
    expect(scopeManagerModule).toHaveAttribute("aria-expanded", "false");
    expect(within(validationNav).queryByRole("button", { name: /bim manager/i })).not.toBeInTheDocument();
    await user.click(scopeManagerModule);
    expect(scopeManagerModule).toHaveAttribute("aria-expanded", "true");
    expect(within(validationNav).getByRole("button", { name: /bim manager/i })).toBeInTheDocument();
    [
      "Project Manager",
      "Scope Manager",
      "Schedule Manager",
      "Cost Manager",
      "Risk Manager",
      "Procurement Manager",
      "Progress&Performance Manager",
      "Resource Manager",
      "Claim Manager",
      "Document Manager",
    ].forEach((moduleName) => {
      expect(within(validationNav).getByRole("button", { name: moduleName, exact: true })).toBeInTheDocument();
    });
    const riskManagerModule = within(validationNav).getByRole("button", { name: "Risk Manager", exact: true });
    await user.click(riskManagerModule);
    await user.click(within(validationNav).getByRole("button", { name: /risk register/i }));
    expect(await screen.findByRole("region", { name: /risk register module/i })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /current module guide/i })).not.toBeInTheDocument();
    await user.click(within(validationNav).getByRole("button", { name: "Project Manager", exact: true }));
    expect(within(validationNav).getByRole("button", { name: "AI Assistant", exact: true })).toBeInTheDocument();
    await user.click(within(validationNav).getByRole("button", { name: "Meeting Minutes", exact: true }));
    expect(await screen.findByRole("region", { name: /meeting minutes module/i })).toBeInTheDocument();
    await user.click(within(validationNav).getByRole("button", { name: "Document Manager", exact: true }));
    await user.click(within(validationNav).getByRole("button", { name: "Submittals", exact: true }));
    expect(await screen.findByRole("region", { name: /submittals module/i })).toBeInTheDocument();
    await user.click(facilityMacroprocess);
    ["Asset Manager", "Maintenance Manager", "Condition Assessment Manager"].forEach((moduleName) => {
      expect(within(validationNav).getByRole("button", { name: moduleName, exact: true })).toBeInTheDocument();
    });
    await user.click(within(validationNav).getByRole("button", { name: "Asset Manager", exact: true }));
    ["Asset Inventory", "Asset Warranty", "Asset Meter"].forEach((submoduleName) => {
      expect(within(validationNav).getByText(submoduleName, { exact: true, selector: "span" })).toBeInTheDocument();
    });
    await user.click(within(validationNav).getByRole("button", { name: "Asset Warranty", exact: true }));
    expect(await screen.findByRole("region", { name: /asset warranty module/i })).toBeInTheDocument();
    await user.click(within(validationNav).getByRole("button", { name: "Maintenance Manager", exact: true }));
    await user.click(within(validationNav).getByRole("button", { name: "Service Request", exact: true }));
    expect(await screen.findByRole("region", { name: /service request module/i })).toBeInTheDocument();

    const applicationBrand = screen.getByRole("banner", { name: /application brand/i });
    await user.click(within(applicationBrand).getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }));
    const adminNavigation = screen.getByRole("navigation", { name: "Admin mode navigation", exact: true });
    expect(screen.queryByRole("navigation", { name: /validation focus/i })).not.toBeInTheDocument();
    expect(
      within(adminNavigation).getByRole("button", { name: "Organization & Security", exact: true })
    ).toHaveAttribute("aria-expanded", "true");
    expect(
      within(adminNavigation).getByRole("button", { name: "Company & Organization Manager", exact: true })
    ).toBeInTheDocument();
    expect(
      within(adminNavigation).getByRole("button", { name: "Authentication & Session Management", exact: true })
    ).toBeInTheDocument();
    expect(within(adminNavigation).getByText("User Creator", { exact: true, selector: "span" })).toBeInTheDocument();
    expect(within(adminNavigation).getByRole("button", { name: "Group Creator", exact: true })).toBeInTheDocument();
    expect(within(adminNavigation).getByRole("button", { name: "Permissions", exact: true })).toBeInTheDocument();
    expect(within(adminNavigation).getByRole("button", { name: "Access Control", exact: true })).toBeInTheDocument();
    expect(
      within(adminNavigation).queryByRole("button", { name: "Project Control Manager", exact: true })
    ).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "User Creator", exact: true })).toBeInTheDocument();
    await user.click(
      within(adminNavigation).getByRole("button", { name: "Company & Organization Manager", exact: true })
    );
    expect(await screen.findByRole("region", { name: /company & organization manager module/i })).toBeInTheDocument();
    expect(screen.getByRole("tree", { name: /árbol organizacional/i })).toBeInTheDocument();
    await user.click(
      within(adminNavigation).getByRole("button", { name: "Authentication & Session Management", exact: true })
    );
    expect(
      await screen.findByRole("region", { name: /authentication & session management module/i })
    ).toBeInTheDocument();
    await user.click(within(adminNavigation).getByRole("button", { name: "Group Creator", exact: true }));
    expect(await screen.findByRole("region", { name: /group creator module/i })).toBeInTheDocument();
    await user.click(within(adminNavigation).getByRole("button", { name: "Permissions", exact: true }));
    expect(await screen.findByRole("region", { name: /permissions module/i })).toBeInTheDocument();
    await user.click(within(adminNavigation).getByRole("button", { name: "Access Control", exact: true }));
    expect(await screen.findByRole("region", { name: /access control module/i })).toBeInTheDocument();
    await user.click(within(applicationBrand).getByRole("button", { name: "Cambiar a USER MODE", exact: true }));
    expect(screen.getByRole("navigation", { name: /validation focus/i })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /dashboard evm/i })).toBeInTheDocument();

    const workspace = screen.getByRole("region", { name: /project workspace and control flow/i });
    const hideModuleRail = within(workspace).getByRole("button", { name: /ocultar barra de módulos/i });
    expect(hideModuleRail).toHaveAttribute("aria-expanded", "true");
    await user.click(hideModuleRail);
    expect(workspace).toHaveClass("moduleRailCollapsed");
    expect(within(workspace).queryByRole("navigation", { name: /validation focus/i })).not.toBeInTheDocument();
    const showModuleRail = within(workspace).getByRole("button", { name: /mostrar barra de módulos/i });
    expect(showModuleRail).toHaveAttribute("aria-expanded", "false");
    await user.click(showModuleRail);
    expect(workspace).not.toHaveClass("moduleRailCollapsed");
    expect(within(workspace).getByRole("navigation", { name: /validation focus/i })).toBeInTheDocument();
    [/process flow/i, /planning/i, /costs/i, /decisions/i, /users & roles/i, /baseline/i, /schedule intake/i].forEach(
      (hiddenLabel) => {
        expect(within(validationNav).queryByRole("button", { name: hiddenLabel })).not.toBeInTheDocument();
      }
    );

    const commandBar = screen.getByRole("banner", { name: /tenant command bar/i });
    expect(within(commandBar).getByText(/proyectos asignados/i)).toBeInTheDocument();
    expect(within(commandBar).getByText(/cada usuario ve solo sus proyectos/i)).toBeInTheDocument();
    expect(within(commandBar).queryByText(/demo energy/i)).not.toBeInTheDocument();
    expect(within(commandBar).queryByRole("button", { name: /new project/i })).not.toBeInTheDocument();
    expect(within(commandBar).queryByRole("button", { name: /delete project/i })).not.toBeInTheDocument();

    expect(screen.queryByRole("region", { name: /next controlled action/i })).not.toBeInTheDocument();

    const workspacesManagerModule = within(validationNav).getByRole("button", {
      name: /^workspaces manager$/i,
    });
    expect(workspacesManagerModule).toHaveAccessibleName("Workspaces Manager");
    await user.click(workspacesManagerModule);
    await user.click(within(validationNav).getByRole("button", { name: /project creator/i }));
    const projectCreator = await screen.findByRole("region", { name: /project creator module/i });
    expect(within(projectCreator).getByRole("button", { name: /new project/i })).toBeInTheDocument();
    expect(within(projectCreator).getByRole("button", { name: /delete project/i })).toBeInTheDocument();

    await user.click(within(validationNav).getByRole("button", { name: /scope manager/i }));
    await user.click(within(validationNav).getByRole("button", { name: /bim manager/i }));
    expect(await screen.findByRole("region", { name: /bim manager module/i })).toBeInTheDocument();
  }, 90_000);

  it("opens the blocking cost and currency gate from the next controlled action", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(
      within(screen.getByRole("region", { name: /next controlled action/i })).getByRole("button", {
        name: /open baseline gate/i,
      })
    );

    expect(await screen.findByRole("heading", { name: /baseline control/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /cost and currency gate/i })).toBeInTheDocument();
  });

  it("expands project creation only when requested", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    expect(screen.queryByRole("button", { name: /create project/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /new project/i }));

    expect(screen.getByRole("button", { name: /^create project$/i })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: /create project/i })).toBeInTheDocument();
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
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /new project/i }));
    const projectPanel = screen.getByRole("complementary", { name: /create project/i });

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
        })
      );
    });
  });

  it("lets users create the first project when the workspace is empty", async () => {
    const user = userEvent.setup();
    const createdProject: Project = {
      id: 77,
      code: "NEW-001",
      name: "Nuevo proyecto limpio",
      phase: "Planning",
      currency: "USD",
      calendar_base: "5x8",
      owner: "Owner PMO",
      status: "draft",
      authorization_date: null,
      authorization_ref: "",
      configuration: { funding_required: true, control_level: "control_account" },
      start_date: null,
      finish_date: null,
    };
    let projectCreated = false;
    listProjects.mockImplementation(() => Promise.resolve(projectCreated ? [createdProject] : []));
    createProject.mockImplementation(() => {
      projectCreated = true;
      return Promise.resolve(createdProject);
    });
    useProjectStore.setState({ selectedProjectId: 999, dashboard: null });

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByRole("heading", { name: /create your first project/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /new project/i }));
    const projectPanel = screen.getByRole("complementary", { name: /create project/i });

    fireEvent.change(within(projectPanel).getByLabelText(/^code$/i), { target: { value: "NEW-001" } });
    fireEvent.change(within(projectPanel).getByPlaceholderText(/project control name/i), {
      target: { value: "Nuevo proyecto limpio" },
    });
    await user.click(screen.getByRole("button", { name: /^create project$/i }));

    await waitFor(() => {
      expect(createProject).toHaveBeenCalledWith(
        "tok",
        expect.objectContaining({ code: "NEW-001", name: "Nuevo proyecto limpio" })
      );
    });
    await waitFor(() => {
      expect(useProjectStore.getState().selectedProjectId).toBe(77);
    });
  });

  it("deletes the selected project after confirmation and selects the next project", async () => {
    const user = userEvent.setup();
    const nextProject: Project = {
      ...demoProject,
      id: 2,
      code: "NEXT-002",
      name: "Next controlled project",
    };
    const nextDashboard: Dashboard = {
      ...demoDashboard,
      project: nextProject,
      project_team: demoDashboard.project_team.map((member) => ({
        ...member,
        membership: { ...member.membership, project_id: 2 },
      })),
    };
    listProjects.mockResolvedValue([demoProject, nextProject]);
    getDashboard.mockImplementation((_token, projectId) =>
      Promise.resolve(projectId === 2 ? nextDashboard : demoDashboard)
    );
    deleteProject.mockResolvedValue({ status: "deleted", project_id: 1 });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /^workspaces manager$/i }));
    await user.click(screen.getByRole("button", { name: /project creator/i }));
    const projectCreator = await screen.findByRole("region", { name: /project creator module/i });
    await user.click(within(projectCreator).getByRole("button", { name: /delete project/i }));

    await waitFor(() => {
      expect(deleteProject).toHaveBeenCalledWith("tok", 1);
    });
    await waitFor(() => {
      expect(useProjectStore.getState().selectedProjectId).toBe(2);
    });
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining("CTRL-DEMO-001"));
    confirmSpy.mockRestore();
  });

  it("uploads the selected XML/XER file to the active project", async () => {
    uploadSchedule.mockResolvedValue({
      id: 20,
      source: "p6_xer",
      file_name: "baseline.xer",
      status: "validated",
      data_date: "2026-03-11",
      baseline_name: "baseline",
      quality_score: 92,
      validation_summary: "1 activities, 0 relationships.",
      detected_currency: "USD",
      currency_confidence: "detected",
      currency_source: "PROJECT.currency_id",
      currency_confirmed: false,
      total_imported_cost: 2500,
      cost_loaded_activity_count: 1,
      cost_loaded_activity_percent: 100,
      cost_source_summary: { "TASKRSRC.target_cost": 1 },
      imported_at: "2026-05-01T00:00:00Z",
    });
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /open load schedule/i }));
    const input = screen.getByLabelText(/schedule xml or xer/i);
    const file = new File(["%T\tTASK"], "baseline.xer", { type: "application/octet-stream" });

    await user.upload(input, file);

    await waitFor(() => {
      expect(uploadSchedule).toHaveBeenCalledWith("tok", 1, file);
    });
    expect(await screen.findByText(/baseline.xer uploaded/i)).toBeInTheDocument();
  });

  it("renders DCMA schedule quality metrics in baseline control", async () => {
    const user = userEvent.setup();
    wbs.mockResolvedValue([
      {
        id: 1,
        parent_id: null,
        code: "P&Pmis-PY-1-4",
        name: "Construccion",
        level: 2,
        description: "",
        dictionary: "",
        responsible: "",
        status: "active",
      },
    ]);
    getDashboard.mockResolvedValue({
      ...demoDashboard,
      schedule_import: {
        id: 20,
        source: "p6_xer",
        file_name: "baseline.xer",
        status: "validated",
        data_date: "2026-03-11",
        baseline_name: "baseline",
        quality_score: 84,
        validation_summary: "3 activities, 1 relationships, 1 open logic checks.",
        detected_currency: "USD",
        currency_confidence: "detected",
        currency_source: "PROJECT.currency_id",
        currency_confirmed: true,
        total_imported_cost: 5000,
        cost_loaded_activity_count: 2,
        cost_loaded_activity_percent: 66.67,
        cost_source_summary: {},
        imported_at: "2026-05-01T00:00:00Z",
      },
      schedule_activity_count: 3,
      schedule_relationship_count: 1,
      schedule_quality_metrics: [
        {
          key: "dcma_logic",
          standard: "DCMA 01",
          label: "Logic",
          status: "fail",
          item_count: 1,
          total_count: 3,
          percent: 33.33,
          threshold: "<= 5% missing logic",
          description: "Activities missing predecessor or successor logic.",
        },
        {
          key: "dcma_leads",
          standard: "DCMA 02",
          label: "Leads",
          status: "pass",
          item_count: 0,
          total_count: 1,
          percent: 0,
          threshold: "0 leads",
          description: "Relationships with negative lag.",
        },
        {
          key: "dcma_high_float",
          standard: "DCMA 06",
          label: "High Float",
          status: "pass",
          item_count: 0,
          total_count: 3,
          percent: 0,
          threshold: "<= 5% over 44 days",
          description: "Activities with total float greater than 44 days.",
        },
      ],
    });

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(
      within(screen.getByRole("complementary", { name: /project information flow/i })).getByRole("button", {
        name: /open baseline gate/i,
      })
    );

    expect(screen.getByRole("heading", { name: /dcma metrics/i })).toBeInTheDocument();
    expect(
      screen.getByRole("row", { name: /dcma 01 logic .* fail 1 \/ 3 33\.3% <= 5% missing logic/i })
    ).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /dcma 02 leads .* pass 0 \/ 1 0\.0% 0 leads/i })).toBeInTheDocument();
    expect(
      screen.getByRole("row", { name: /dcma 06 high float .* pass 0 \/ 3 0\.0% <= 5% over 44 days/i })
    ).toBeInTheDocument();
  });

  it("navigates between control flow views from the side rail", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });

    expect(screen.queryByRole("button", { name: /open tenant workspace/i })).not.toBeInTheDocument();
    expect(screen.getByRole("banner", { name: /tenant command bar/i })).toHaveTextContent(/proyectos asignados/i);
    expect(screen.getByRole("banner", { name: /tenant command bar/i })).toHaveTextContent(
      /cada usuario ve solo sus proyectos/i
    );
    expect(screen.getByRole("heading", { name: /dashboard evm/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /cost manager/i }));
    await user.click(screen.getByRole("button", { name: /cost items/i }));
    expect(screen.getByRole("heading", { name: /cost items/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /scope manager/i }));
    await user.click(screen.getByRole("button", { name: /scope changes/i }));
    expect(screen.getByRole("heading", { name: /scope changes/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /dashboard/i }));
    expect(screen.getByRole("heading", { name: /dashboard evm/i })).toBeInTheDocument();

    await user.click(
      within(screen.getByRole("complementary", { name: /project information flow/i })).getByRole("button", {
        name: /open baseline gate/i,
      })
    );
    expect(screen.getByRole("heading", { name: /baseline control/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /open awp packages/i }));
    expect(screen.getByRole("heading", { name: /work packages/i })).toBeInTheDocument();
  });

  it("keeps CBS and FBS details out of the EVM dashboard and shows them as cost traceability", async () => {
    const user = userEvent.setup();
    getDashboard.mockResolvedValue({
      ...demoDashboard,
      cost_sheet: [
        {
          ...demoDashboard.cost_sheet[0],
          control_account_code: "CA-PLT-CIV",
          control_account_name: "Control Account PLT-CIV",
          cbs_code: "CBS-4000",
          bac: 120000,
          earned_value: 0,
          actual_cost: 0,
          cpi: 0,
        },
      ],
    } as Dashboard);

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /dashboard evm/i });
    expect(screen.queryByRole("heading", { name: /cbs cost codes/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /fbs funding codes/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /cost manager/i }));
    await user.click(screen.getByRole("button", { name: /cost items/i }));

    const traceability = await screen.findByRole("region", { name: /cost and funding traceability/i });
    expect(within(traceability).getByRole("heading", { name: /cost and funding traceability/i })).toBeInTheDocument();
    expect(
      within(traceability).getByRole("row", {
        name: /obras civiles planta plt-civ ca-plt-civ control account plt-civ CBS-4000 .* \$120,000 \$0 \$0 N\/A/i,
      })
    ).toBeInTheDocument();
  });

  it("registers the schedule control handbook module in navigation and route", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app/schedule-control"]}>
        <App />
      </MemoryRouter>
    );

    const module = await screen.findByRole("region", {
      name: /^schedule$/i,
    });
    expect(within(module).getByRole("heading", { name: /^schedule$/i })).toBeInTheDocument();
    expect(within(module).getByRole("tab", { name: /wbs/i })).toBeInTheDocument();
    expect(within(module).getByRole("tab", { name: /baseline schedule/i })).toBeInTheDocument();
    expect(within(module).getByRole("tab", { name: /cpm \/ critical path/i })).toBeInTheDocument();
    expect(within(module).getByRole("tab", { name: /progress update/i })).toBeInTheDocument();
    expect(within(module).getByRole("tab", { name: /lookahead planning/i })).toBeInTheDocument();
    expect(within(module).getByRole("tab", { name: /delay identification/i })).toBeInTheDocument();
    expect(within(module).getByRole("tab", { name: /recovery planning/i })).toBeInTheDocument();

    await user.click(within(module).getByRole("tab", { name: /cpm \/ critical path/i }));
    expect(within(module).getByRole("heading", { name: /cpm \/ critical path/i })).toBeInTheDocument();
    expect(within(module).getByText(/critical path:/i)).toBeInTheDocument();
  });

  it("renders the BPM process flow board by role lane", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /scope manager/i }));
    await user.click(screen.getByRole("button", { name: /path of execution/i }));

    expect(await screen.findByRole("heading", { name: /path of execution/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /owner \/ direction/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /project controls/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /planning \/ p6/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /cost \/ funding/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /awp \/ construction/i })).toBeInTheDocument();
    expect(screen.getByText(/role matrix and approvals/i)).toBeInTheDocument();
    expect(screen.getByText(/client role matrix is configured/i)).toBeInTheDocument();
    expect(processFlowBoard).toHaveBeenCalledWith("tok", 1);
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
          cbs_code: "CBS-UNI-PLT-CIV-EARTH",
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
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /open business processes/i }));

    expect(screen.getByText(/vincula wbs, cbs y fbs/i)).toBeInTheDocument();
    expect(screen.getByText(/fbs es fuente de financiacion/i)).toBeInTheDocument();
    expect(screen.getByText(/convencion: cbs-\{proyecto\}-\{wbs\}-\{familia de costo\}/i)).toBeInTheDocument();
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
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /open project and wbs/i }));

    expect(await screen.findByRole("heading", { name: /wbs sheet/i })).toBeInTheDocument();
    expect(screen.getAllByText("PLT-CIV").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Obras civiles planta").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$1,250").length).toBeGreaterThan(0);
    expect(activitySheetWbsRows).toHaveBeenCalledWith("tok", 1, 11);
  });

  it("keeps BIM and Excel quantity takeoff in BIM Manager instead of Project Setup", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /open project and wbs/i }));

    expect(screen.queryByRole("region", { name: /^quantity takeoff$/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/load bim\/ifc or excel quantities/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /scope manager/i }));
    await user.click(screen.getByRole("button", { name: /bim manager/i }));

    const quantityPanel = await screen.findByRole("region", {
      name: /bim manager module/i,
    });
    const quantityRibbonMenus = await within(quantityPanel).findByRole(
      "navigation",
      {
        name: /menus superiores ifc/i,
      },
      { timeout: 5000 }
    );
    await user.click(within(quantityRibbonMenus).getByRole("button", { name: /^Archivo$/i }));
    expect(within(quantityPanel).getByLabelText(/load bim\/ifc or excel quantities/i)).toBeInTheDocument();
    expect(within(quantityPanel).getAllByText(/bim-quantities.xlsx/i).length).toBeGreaterThan(0);
    expect(within(quantityPanel).getAllByText(/GUID-001/i).length).toBeGreaterThan(0);
    await user.click(within(quantityPanel).getByRole("button", { name: /limpiar modelo/i }));
    expect(within(quantityPanel).getByText(/modelo ifc y tabla local despejados/i)).toBeInTheDocument();
    expect(within(quantityPanel).getByText(/no hay elementos candidatos/i)).toBeInTheDocument();
    expect(within(quantityPanel).queryByText(/GUID-001/i)).not.toBeInTheDocument();
    expect(quantityTakeoffRuns).toHaveBeenCalledWith("tok", 1);
    expect(quantityTakeoffLines).toHaveBeenCalledWith("tok", 1, 61);
  });

  it("opens BIM Manager with AWP validation and 3D viewer", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /scope manager/i }));
    await user.click(screen.getByRole("button", { name: /bim manager/i }));

    const module = await screen.findByRole("region", { name: /bim manager module/i });
    expect(within(module).getAllByRole("heading", { name: /bim manager/i }).length).toBeGreaterThan(0);
    const ribbonMenus = await within(module).findByRole(
      "navigation",
      { name: /menus superiores ifc/i },
      { timeout: 5000 }
    );
    await user.click(within(ribbonMenus).getByRole("button", { name: /^Archivo$/i }));
    expect(within(module).getByLabelText(/load bim\/ifc or excel quantities/i)).toBeInTheDocument();
    expect(within(module).queryByRole("region", { name: /quantity provenance/i })).not.toBeInTheDocument();
    await user.click(within(ribbonMenus).getByRole("button", { name: /Informaci[oó]n/i }));
    expect(within(module).getAllByText(/^Ubicacion$/i).length).toBeGreaterThan(0);
    expect(within(module).getAllByText(/^Elementos$/i).length).toBeGreaterThan(0);
    expect(within(module).getAllByText(/^Paquetes$/i).length).toBeGreaterThan(0);
    const provenance = within(module).getByRole("region", { name: /quantity provenance/i });
    expect(within(provenance).getByText(/bim-quantities.xlsx/i)).toBeInTheDocument();
    expect(within(provenance).getByText(/run #61 \/ v1 \/ xlsx/i)).toBeInTheDocument();
    expect(within(provenance).getByText(/tabla unica de cantidades/i)).toBeInTheDocument();
    expect(await within(module).findByText(/geometria real del archivo ifc guardado/i)).toBeInTheDocument();
    const ifcViewer = within(module).getByRole("region", { name: /modelo ifc/i });
    expect(ifcViewer).toHaveClass("ifcGeometryViewer");
    expect(within(module).queryByRole("region", { name: /bim inventory preview/i })).not.toBeInTheDocument();
    expect(within(module).queryByRole("region", { name: /bim quantity takeoff lines/i })).not.toBeInTheDocument();
    const scopeValidation = within(module).getByRole("region", { name: /tabla de cantidades controladas/i });
    expect(within(scopeValidation).getAllByRole("table").length).toBeGreaterThan(0);
    expect(within(scopeValidation).getByText(/ubicacion -> elemento -> codigos de control/i)).toBeInTheDocument();
    expect(within(scopeValidation).getByText(/no duplicar elementos por wbs/i)).toBeInTheDocument();
    expect(within(scopeValidation).getByText(/cantidad total menos cantidad asignada a paquete/i)).toBeInTheDocument();
    expect(
      within(scopeValidation).getByRole("heading", { name: /tabla de cantidades controladas/i })
    ).toBeInTheDocument();
    expect(within(scopeValidation).getAllByText(/CBS-UNI-PLT-CIV-EARTH/i).length).toBeGreaterThan(0);
    expect(within(scopeValidation).getAllByText(/GUID-001/i).length).toBeGreaterThan(0);
    expect(within(scopeValidation).getAllByText(/falta cbs\/wbs/i).length).toBeGreaterThan(0);
    expect(within(module).getAllByText(/GUID-001/i).length).toBeGreaterThan(0);
    expect(within(module).getAllByText(/IfcWall/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole("region", { name: /schedule intake/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /schedule xml or xer/i })).not.toBeInTheDocument();
    expect(quantityTakeoffRuns).toHaveBeenCalledWith("tok", 1);
    expect(quantityTakeoffLines).toHaveBeenCalledWith("tok", 1, 61);
  });

  it("keeps heavy IFC models visible when quantity extraction times out", async () => {
    const user = userEvent.setup();
    loadQuantityTakeoff.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /scope manager/i }));
    await user.click(screen.getByRole("button", { name: /bim manager/i }));

    const module = await screen.findByRole("region", { name: /bim manager module/i });
    const ribbonMenus = await within(module).findByRole(
      "navigation",
      { name: /menus superiores ifc/i },
      { timeout: 5000 }
    );
    await user.click(within(ribbonMenus).getByRole("button", { name: /^Archivo$/i }));
    const input = within(module).getByLabelText(/load bim\/ifc or excel quantities/i);
    const file = new File(["ISO-10303-21;"], "coordination-model.ifc", { type: "application/octet-stream" });
    await user.upload(input, file);

    await waitFor(() => {
      expect(loadQuantityTakeoff).toHaveBeenCalledWith("tok", 1, file, uploadedBimModel.id);
    });
    expect(await within(module).findByText(/quedo registrado para coordinacion bim/i)).toBeInTheDocument();
    expect(within(module).getByText(/la extraccion de cantidades no termino/i)).toBeInTheDocument();
    expect(within(module).getByText(/el procesamiento ifc se interrumpio antes de terminar/i)).toBeInTheDocument();
    expect(within(module).queryByText(/the bim upload did not finish/i)).not.toBeInTheDocument();
  });

  it("loads IFC models larger than the old 8 MB guard instead of doing nothing", async () => {
    const user = userEvent.setup();
    const createdRun = {
      id: 62,
      project_id: 1,
      source_file_name: "coordination-model.ifc",
      source_type: "ifc",
      status: "needs_mapping",
      row_count: 2,
      mapped_line_count: 0,
      unmapped_line_count: 2,
      total_quantity: 15.25,
      validation_summary: "2 quantity line(s): 0 mapped, 2 need mapping.",
      version: 1,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    };
    loadQuantityTakeoff.mockResolvedValueOnce(createdRun);
    quantityTakeoffRuns.mockResolvedValueOnce([createdRun]);

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /scope manager/i }));
    await user.click(screen.getByRole("button", { name: /bim manager/i }));

    const module = await screen.findByRole("region", { name: /bim manager module/i });
    const ribbonMenus = await within(module).findByRole(
      "navigation",
      { name: /menus superiores ifc/i },
      { timeout: 5000 }
    );
    await user.click(within(ribbonMenus).getByRole("button", { name: /^Archivo$/i }));
    const input = within(module).getByLabelText(/load bim\/ifc or excel quantities/i);
    const file = new File([new Uint8Array(9 * 1024 * 1024)], "coordination-model.ifc", {
      type: "application/octet-stream",
    });
    await user.upload(input, file);

    await waitFor(() => {
      expect(loadQuantityTakeoff).toHaveBeenCalledWith("tok", 1, file, uploadedBimModel.id);
    });
    expect(
      await within(module).findByText(/quedo registrado como modelo ifc y se cargaron 2 linea\(s\) de cantidades/i)
    ).toBeInTheDocument();
    expect(within(module).queryByText(/larger than 8 mb/i)).not.toBeInTheDocument();
  });

  it("clears expired sessions when BIM model upload receives a 401", async () => {
    const user = userEvent.setup();
    loadQuantityTakeoff.mockRejectedValueOnce(new ApiError(401, '{"detail":"Invalid or expired token"}'));

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /scope manager/i }));
    await user.click(screen.getByRole("button", { name: /bim manager/i }));

    const module = await screen.findByRole("region", { name: /bim manager module/i });
    const ribbonMenus = await within(module).findByRole(
      "navigation",
      { name: /menus superiores ifc/i },
      { timeout: 5000 }
    );
    await user.click(within(ribbonMenus).getByRole("button", { name: /^Archivo$/i }));
    await user.upload(
      within(module).getByLabelText(/load bim\/ifc or excel quantities/i),
      new File(["ISO-10303-21;"], "coordination-model.ifc", { type: "application/octet-stream" })
    );

    await waitFor(() => {
      expect(authLogout).toHaveBeenCalledTimes(1);
    });
    expect(within(module).queryByText(/invalid or expired token/i)).not.toBeInTheDocument();
  });

  it("auto-saves ready setup before loading the first Activity Sheet", async () => {
    const user = userEvent.setup();
    const createdSheet = {
      id: 12,
      project_id: 1,
      schedule_import_id: 21,
      source_file_name: "activity.xer",
      source: "p6_xer",
      status: "validated",
      row_count: 1,
      data_date: "2026-03-11",
      baseline_name: "activity",
      validation_summary: "1 activities, 0 relationships.",
      version: 1,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    };
    operationalSetup.mockRejectedValueOnce(new ApiError(404, '{"detail":"Project operational setup not found"}'));
    activitySheets.mockResolvedValueOnce([]).mockResolvedValue([createdSheet]);
    loadActivitySheetData.mockResolvedValue(createdSheet);

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /open project and wbs/i }));
    const input = screen.getByLabelText(/load xml\/xer/i);
    expect(input).toBeEnabled();

    const file = new File(["%T\tTASK"], "activity.xer", { type: "application/octet-stream" });
    await user.upload(input, file);

    await waitFor(() => {
      expect(updateOperationalSetup).toHaveBeenCalledWith(
        "tok",
        1,
        expect.objectContaining({
          project_number: "CTRL-DEMO-001",
          status: "ready",
          permissions_configured: true,
          p6_mapping_ready: true,
        })
      );
    });
    expect(loadActivitySheetData).toHaveBeenCalledWith("tok", 1, file);
    expect(await screen.findByText(/Activity data loaded from activity.xer/i)).toBeInTheDocument();
  });

  it("creates a WBS node from Project Setup", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /open project and wbs/i }));

    const wbsCatalogPanel = await screen.findByRole("region", { name: /wbs catalog/i });
    fireEvent.change(within(wbsCatalogPanel).getByLabelText(/^wbs code$/i), { target: { value: "WBS-MAN-001" } });
    fireEvent.change(within(wbsCatalogPanel).getByLabelText(/^wbs name$/i), { target: { value: "Manual WBS" } });
    fireEvent.change(within(wbsCatalogPanel).getByLabelText(/^responsible$/i), { target: { value: "Ana Control" } });

    await user.click(within(wbsCatalogPanel).getByRole("button", { name: /create wbs/i }));

    await waitFor(() => {
      expect(createWbs).toHaveBeenCalledWith(
        "tok",
        1,
        expect.objectContaining({
          code: "WBS-MAN-001",
          name: "Manual WBS",
          responsible: "Ana Control",
        })
      );
    });
    expect(await screen.findByText(/WBS WBS-MAN-001 created/i)).toBeInTheDocument();
  });

  it("shows WBS as a hierarchy and as a table in Project Setup", async () => {
    const user = userEvent.setup();
    wbs.mockResolvedValue([
      {
        id: 9,
        parent_id: null,
        code: "1.0",
        name: "Project Control Baseline",
        level: 1,
        description: "",
        dictionary: "",
        responsible: "",
        status: "draft",
      },
      {
        id: 10,
        parent_id: null,
        code: "P&Pmis-PY-1",
        name: "Proyecto Piloto",
        level: 1,
        description: "",
        dictionary: "",
        responsible: "",
        status: "active",
      },
      {
        id: 14,
        parent_id: null,
        code: "1",
        name: "Legacy flat Ingenieria",
        level: 1,
        description: "",
        dictionary: "",
        responsible: "",
        status: "draft",
      },
      {
        id: 11,
        parent_id: null,
        code: "P&Pmis-PY-1-1",
        name: "Ingenieria",
        level: 2,
        description: "",
        dictionary: "",
        responsible: "",
        status: "active",
      },
      {
        id: 12,
        parent_id: null,
        code: "P&Pmis-PY-1-4",
        name: "Construccion",
        level: 2,
        description: "",
        dictionary: "",
        responsible: "",
        status: "active",
      },
      {
        id: 13,
        parent_id: null,
        code: "P&Pmis-PY-1-4-1",
        name: "Estructura Concreto",
        level: 3,
        description: "",
        dictionary: "",
        responsible: "",
        status: "active",
      },
    ]);

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /open project and wbs/i }));

    const structure = await screen.findByRole("region", { name: /wbs structure/i });
    const wbsTreePanel = within(structure).getByRole("tree");
    expect(within(wbsTreePanel).getAllByText(/Project CTRL-DEMO-001/i).length).toBeGreaterThan(0);
    expect(within(wbsTreePanel).getAllByText("Proyecto Piloto").length).toBeGreaterThan(0);
    expect(within(wbsTreePanel).getAllByText("Estructura Concreto").length).toBeGreaterThan(0);
    expect(within(wbsTreePanel).getByText("CTRL-DEMO-001-1-4-1")).toBeInTheDocument();
    expect(within(wbsTreePanel).queryByText(/P&Pmis/i)).not.toBeInTheDocument();
    expect(within(wbsTreePanel).queryByText("Project Control Baseline")).not.toBeInTheDocument();
    expect(within(wbsTreePanel).queryByText("Legacy flat Ingenieria")).not.toBeInTheDocument();
    expect(within(wbsTreePanel).getByRole("treeitem", { name: /Proyecto Piloto CTRL-DEMO-001/i })).toHaveAttribute(
      "aria-level",
      "1"
    );
    expect(within(wbsTreePanel).getByRole("treeitem", { name: /Estructura Concreto/i })).toHaveAttribute(
      "aria-level",
      "3"
    );

    const table = screen.getByRole("region", { name: /wbs table/i });
    expect(
      within(table).getByRole("row", { name: /Proyecto Piloto CTRL-DEMO-001-1 Project 1 Active/i })
    ).toBeInTheDocument();
    expect(
      within(table).getByRole("row", {
        name: /Estructura Concreto CTRL-DEMO-001-1-4-1 Construccion 3 Active/i,
      })
    ).toBeInTheDocument();
    expect(within(table).queryByText(/P&Pmis/i)).not.toBeInTheDocument();
    expect(within(table).getByText("Estructura Concreto").closest("td")).toHaveStyle({ paddingLeft: "66px" });
  });

  it("anchors WBS CBS FBS mapping on the WBS hierarchy and active traceability", async () => {
    const user = userEvent.setup();
    wbs.mockResolvedValue([
      {
        id: 9,
        parent_id: null,
        code: "1",
        name: "Legacy flat Ingenieria",
        level: 1,
        description: "",
        dictionary: "",
        responsible: "",
        status: "draft",
      },
      {
        id: 10,
        parent_id: null,
        code: "P&Pmis-PY-1",
        name: "Proyecto Piloto",
        level: 1,
        description: "",
        dictionary: "",
        responsible: "",
        status: "active",
      },
      {
        id: 11,
        parent_id: 10,
        code: "P&Pmis-PY-1-4",
        name: "Construccion",
        level: 2,
        description: "",
        dictionary: "",
        responsible: "",
        status: "active",
      },
      {
        id: 12,
        parent_id: 11,
        code: "P&Pmis-PY-1-4-1",
        name: "Estructura Concreto",
        level: 3,
        description: "",
        dictionary: "",
        responsible: "",
        status: "active",
      },
      {
        id: 13,
        parent_id: 11,
        code: "P&Pmis-PY-1-4-2",
        name: "Instalaciones Mecanicas, Electricas, Hidraulicas",
        level: 3,
        description: "",
        dictionary: "",
        responsible: "",
        status: "active",
      },
    ]);
    controlAccounts.mockResolvedValue([
      {
        id: 101,
        wbs_id: 12,
        awp_package_id: null,
        code: "CA-P&Pmis-PY-1-4-1",
        name: "Control Account P&Pmis-PY-1-4-1",
        responsible: "Project Controls",
        discipline: "Structural",
        scope: "",
        budget: 0,
        start_date: null,
        finish_date: null,
        cbs_code: "CBS-PY-STR",
        contract_ref: "CTR-STR-01",
        measurement_rule: "Physical progress by installed concrete quantities.",
        earned_value: 0,
        actual_cost: 0,
        forecast: 0,
        lifecycle_status: "active",
        risk_ref: "",
        closure_note: "",
        version: 1,
        updated_at: "2026-05-01T00:00:00Z",
      },
      {
        id: 102,
        wbs_id: 9,
        awp_package_id: null,
        code: "CA-LEGACY-AWP-GOV",
        name: "Legacy AWP governance account",
        responsible: "Project Controls",
        discipline: "Construction",
        scope: "",
        budget: 0,
        start_date: null,
        finish_date: null,
        cbs_code: "CBS-LEGACY-AWP-GOV",
        contract_ref: "",
        measurement_rule: "",
        earned_value: 0,
        actual_cost: 0,
        forecast: 0,
        lifecycle_status: "closed",
        risk_ref: "",
        closure_note: "",
        version: 1,
        updated_at: "2026-05-01T00:00:00Z",
      },
    ]);
    activitySheetWbsRows.mockResolvedValue([
      {
        wbs_code: "P&Pmis-PY-1-1",
        wbs_name: "Ingenieria",
        activity_count: 1,
        control_account_count: 1,
        planned_cost: 500,
        planned_value: 500,
        unmapped_activity_count: 0,
        needs_review_count: 0,
      },
      {
        wbs_code: "P&Pmis-PY-1-4-1",
        wbs_name: "Estructura Concreto",
        activity_count: 1,
        control_account_count: 1,
        planned_cost: 2000,
        planned_value: 2000,
        unmapped_activity_count: 0,
        needs_review_count: 0,
      },
      {
        wbs_code: "P&Pmis-PY-1-4-2",
        wbs_name: "Instalaciones Mecanicas, Electricas, Hidraulicas",
        activity_count: 1,
        control_account_count: 1,
        planned_cost: 3000,
        planned_value: 3000,
        unmapped_activity_count: 0,
        needs_review_count: 0,
      },
    ]);
    matrix.mockResolvedValue([
      {
        project_id: 1,
        project_code: "CTRL-DEMO-001",
        project_name: "Piloto vial AWP",
        fbs_code: "FBS-OWN-AFE002",
        wbs_code: "P&Pmis-PY-1-4-1",
        awp_package_code: "CWP-P-PMIS-PY-1-4-1-STR-01",
        awp_package_type: "CWP",
        control_account_code: "CA-P&Pmis-PY-1-4-1",
        cbs_code: "CBS-PY-STR",
        cost_code: "CC-PY-STR-001",
        contract_ref: "CTR-STR-01",
        budget: 1500,
        funds_available: 2000,
        committed: 500,
        actual: 0,
        forecast: 1500,
        balance: 500,
        status: "active",
      },
    ]);
    getDashboard.mockResolvedValue({
      ...demoDashboard,
      work_packages: [
        {
          id: 501,
          wbs_id: 12,
          control_account_id: 101,
          parent_id: null,
          package_type: "CWP",
          code: "CWP-P-PMIS-PY-1-4-1-STR-01",
          title: "Structural package",
          description: "Concrete structure construction package.",
          discipline: "Structural",
          sequence_no: 1,
          path_of_construction: "Estructura Concreto sequence before architectural closeout.",
          owner_role: "Workface Planner",
          readiness_status: "constraint_review",
          main_constraints: "Evidence: WBS P&Pmis-PY-1-4-1; CBS CBS-PY-STR.",
          planned_release_date: null,
          planned_start: null,
          planned_finish: null,
          release_required_on: null,
          progress_percent: 0,
          version: 1,
          updated_at: "2026-05-01T00:00:00Z",
        },
      ],
    } satisfies Dashboard);

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /open business processes/i }));

    const structure = await screen.findByRole("region", { name: /wbs master structure/i });
    expect(within(structure).getByRole("treeitem", { name: /Proyecto Piloto CTRL-DEMO-001/i })).toHaveAttribute(
      "aria-level",
      "1"
    );
    expect(within(structure).getByRole("treeitem", { name: /Construccion/i })).toHaveAttribute("aria-level", "2");
    expect(within(structure).getByRole("treeitem", { name: /Estructura Concreto/i })).toHaveAttribute(
      "aria-level",
      "3"
    );
    expect(within(structure).getByText("CTRL-DEMO-001-1-4-1")).toBeInTheDocument();
    expect(within(structure).queryByText(/P&Pmis/i)).not.toBeInTheDocument();
    expect(within(structure).getByRole("treeitem", { name: /Construccion/i })).toHaveTextContent("2 act / $5,000");
    expect(within(structure).queryByText("Legacy flat Ingenieria")).not.toBeInTheDocument();

    const alignmentPanel = screen.getByRole("region", { name: /wbs control alignment/i });
    const concreteAlignment = within(alignmentPanel).getByRole("article", {
      name: /Estructura Concreto control alignment/i,
    });
    expect(within(concreteAlignment).getByText("WBS")).toBeInTheDocument();
    expect(within(concreteAlignment).getByText("Estructura Concreto")).toBeInTheDocument();
    expect(within(concreteAlignment).getByText("Control Account")).toBeInTheDocument();
    expect(within(concreteAlignment).getByText("Control Account - Estructura Concreto")).toBeInTheDocument();
    expect(within(concreteAlignment).getByText("CA-CTRL-DEMO-001-1-4-1")).toBeInTheDocument();
    expect(within(concreteAlignment).getByText("CBS-PY-STR")).toBeInTheDocument();
    expect(within(concreteAlignment).getByText("CC-PY-STR-001")).toBeInTheDocument();
    expect(within(concreteAlignment).getByText("FBS-OWN-AFE002")).toBeInTheDocument();
    expect(within(concreteAlignment).getByText("Structural package")).toBeInTheDocument();
    expect(within(concreteAlignment).getByText("CWP-CTRL-DEMO-001-1-4-1-STR-01")).toBeInTheDocument();
    expect(within(concreteAlignment).getByText("$1,500")).toBeInTheDocument();
    expect(within(alignmentPanel).queryByText(/P&Pmis/i)).not.toBeInTheDocument();

    const matrixPanel = screen.getByRole("region", { name: /wbs traceability matrix/i });
    expect(
      within(matrixPanel).getByRole("row", {
        name: /Estructura Concreto CTRL-DEMO-001-1-4-1 CA-CTRL-DEMO-001-1-4-1 .* CBS-PY-STR FBS-OWN-AFE002 Structural package CWP-CTRL-DEMO-001-1-4-1-STR-01 Active/i,
      })
    ).toBeInTheDocument();
    expect(within(matrixPanel).queryByText(/CA-LEGACY-AWP-GOV/i)).not.toBeInTheDocument();
  });

  it("shows package POC and lets users add manual constraints", async () => {
    const user = userEvent.setup();
    wbs.mockResolvedValueOnce([
      {
        id: 1,
        parent_id: null,
        code: "P&Pmis-PY-1-4",
        name: "Construccion",
        level: 2,
        description: "",
        dictionary: "",
        responsible: "",
        status: "active",
      },
    ]);
    getDashboard.mockResolvedValue({
      ...demoDashboard,
      awp_summary: {
        ...demoDashboard.awp_summary,
        total_packages: 3,
        cwp_count: 1,
        iwp_count: 1,
      },
      work_packages: [
        {
          id: 500,
          wbs_id: 1,
          control_account_id: null,
          parent_id: null,
          package_type: "CWA",
          code: "CWA-P-PMIS-PY-1-4",
          title: "Plant area",
          description: "Construction work area for plant civil works.",
          discipline: "Multi-discipline",
          sequence_no: 1,
          path_of_construction: "Area release before civil works",
          owner_role: "AWP Champion",
          readiness_status: "constraint_review",
          main_constraints:
            "AWP confidence: Medium. Evidence: WBS P&Pmis-PY-1; control account CA-PLT-CIV; CBS CBS-UNI-PLT-CIV-EARTH; 7 schedule activities; 12 quantity lines; 1 funding allocations.",
          planned_release_date: null,
          planned_start: null,
          planned_finish: null,
          release_required_on: null,
          progress_percent: 0,
          version: 1,
          updated_at: "2026-05-01T00:00:00Z",
        },
        {
          id: 501,
          wbs_id: 1,
          control_account_id: 101,
          parent_id: 500,
          package_type: "CWP",
          code: "CWP-P-PMIS-PY-1-4-CIV-01",
          title: "Civil package",
          description: "Draft construction package for civil workface planning.",
          discipline: "Civil",
          sequence_no: 1,
          path_of_construction: "North-to-south civil path",
          owner_role: "Workface Planner",
          readiness_status: "constraint_review",
          main_constraints:
            "AWP confidence: Medium. Evidence: WBS P&Pmis-PY-1-4; control account CA-PLT-CIV; CBS CBS-UNI-PLT-CIV-EARTH; 7 schedule activities; 12 quantity lines; 1 funding allocations. Gate: confirm CWA boundary, CWP sequence, EWP/PWP support, CBS/FBS/control-account alignment and open constraints before field release.",
          planned_release_date: null,
          planned_start: null,
          planned_finish: null,
          release_required_on: null,
          progress_percent: 0,
          version: 1,
          updated_at: "2026-05-01T00:00:00Z",
        },
        {
          id: 502,
          wbs_id: 1,
          control_account_id: 101,
          parent_id: 501,
          package_type: "IWP",
          code: "IWP-P-PMIS-PY-1-4-CIV-01-IW01",
          title: "Civil workface",
          description: "Install workface package for civil execution.",
          discipline: "Civil",
          sequence_no: 3,
          path_of_construction: "Inherits POC from CWP-P-PMIS-PY-1-4-CIV-01; release by workface constraints.",
          owner_role: "Workface Planner",
          readiness_status: "constraint_review",
          main_constraints:
            "AWP confidence: Medium. Evidence: WBS P&Pmis-PY-1-4; control account CA-PLT-CIV; CBS CBS-UNI-PLT-CIV-EARTH; 7 schedule activities; 12 quantity lines; 1 funding allocations.",
          planned_release_date: null,
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
          cbs_code: "CBS-UNI-PLT-CIV-EARTH",
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
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await user.click(screen.getByRole("button", { name: /open awp packages/i }));

    const codingLegend = await screen.findByRole("region", { name: /package coding rule/i });
    expect(within(codingLegend).getByText(/CWA-\[PROJECT\]-\[WBS NAME\]/i)).toBeInTheDocument();
    expect(within(codingLegend).getByText(/CWP-\[PROJECT\]-\[WBS NAME\]-\[DISC\]-\[NN\]/i)).toBeInTheDocument();
    expect(within(codingLegend).getByText(/IWP-\[PROJECT\]-\[WBS NAME\]-\[DISC\]-\[NN\]-IW##/i)).toBeInTheDocument();
    const packageTree = await screen.findByRole("region", { name: /awp package tree/i });
    expect(within(packageTree).getAllByText(/WBS: Construccion/i)).toHaveLength(3);
    expect(within(packageTree).queryByText(/WBS original/i)).not.toBeInTheDocument();
    expect(within(packageTree).getByRole("treeitem", { name: /CWA \/ Construccion Plant area/i })).toHaveAttribute(
      "aria-level",
      "1"
    );
    expect(
      within(packageTree).getByRole("treeitem", { name: /CWP \/ Construccion - Civil Civil package/i })
    ).toHaveAttribute("aria-level", "2");
    expect(
      within(packageTree).getByRole("treeitem", { name: /IWP \/ Construccion - Civil Civil workface/i })
    ).toHaveAttribute("aria-level", "3");
    const pocRoute = screen.getByRole("region", { name: /path of construction route/i });
    expect(within(pocRoute).getByText(/Area release before civil works/i)).toBeInTheDocument();
    expect(within(pocRoute).getByText(/North-to-south civil path/i)).toBeInTheDocument();
    expect(within(pocRoute).queryByText(/release by workface constraints/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Inherits POC from Civil package/i)).toBeInTheDocument();
    expect(screen.getByText(/Workface release constraints/i)).toBeInTheDocument();
    expect(screen.getAllByText(/WBS: Construccion/i).length).toBeGreaterThanOrEqual(3);
    expect(await screen.findByText(/POC: North-to-south civil path/i)).toBeInTheDocument();
    expect(screen.getAllByText(/AWP confidence: Medium/i)).toHaveLength(3);
    expect(screen.getAllByText(/WBS Construccion/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/Draft generated by agent; requires human validation before release/i)).toHaveLength(3);
    expect(screen.queryByRole("heading", { name: /^Control Accounts$/i })).not.toBeInTheDocument();

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
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await screen.findByRole("button", { name: /open awp packages/i });
    await user.click(screen.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }));

    expect(screen.getByRole("heading", { name: "User Creator", exact: true })).toBeInTheDocument();
    await user.type(screen.getAllByLabelText(/^full name$/i)[0], "Nuevo Admin");
    await user.type(screen.getByLabelText(/login email/i), "nuevo.admin@demo.local");
    await user.clear(screen.getByLabelText(/^temporary password$/i));
    await user.type(screen.getByLabelText(/^temporary password$/i), "1234");
    await user.click(screen.getByRole("button", { name: /create user & assign role/i }));

    await waitFor(() => {
      expect(createUser).toHaveBeenCalledWith(
        "tok",
        expect.objectContaining({
          email: "nuevo.admin@demo.local",
          full_name: "Nuevo Admin",
          password: "1234",
        })
      );
    });
    expect(assignTeamMember).toHaveBeenCalledWith("tok", 1, { role: "Control Manager", user_id: 2 });
  });

  it("manages existing tenant users and project access from the dashboard", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter future={routerFuture} initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    await screen.findByRole("heading", { name: /piloto vial awp/i });
    await screen.findByRole("button", { name: /open awp packages/i });
    await user.click(screen.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }));

    fireEvent.change(screen.getByLabelText(/manage tenant user/i), { target: { value: "1" } });
    await user.clear(screen.getByLabelText(/managed full name/i));
    await user.type(screen.getByLabelText(/managed full name/i), "Carlos Planner Senior");
    await user.clear(screen.getByLabelText(/managed title/i));
    await user.type(screen.getByLabelText(/managed title/i), "Senior Planner");
    await user.click(screen.getByRole("button", { name: /^update user$/i }));

    await waitFor(() => {
      expect(updateUser).toHaveBeenCalledWith(
        "tok",
        1,
        expect.objectContaining({ full_name: "Carlos Planner Senior", title: "Senior Planner" })
      );
    });

    await user.clear(screen.getByLabelText(/new temporary password/i));
    await user.type(screen.getByLabelText(/new temporary password/i), "5678");
    await user.click(screen.getByRole("button", { name: /reset password/i }));
    expect(resetUserPassword).toHaveBeenCalledWith("tok", 1, "5678");

    await user.click(screen.getByRole("button", { name: /assign existing user/i }));
    expect(assignTeamMember).toHaveBeenCalledWith("tok", 1, { role: "Control Manager", user_id: 1 });

    await user.click(screen.getByRole("button", { name: /remove access/i }));
    expect(removeTeamMember).toHaveBeenCalledWith("tok", 1, 1);

    await user.click(screen.getByRole("button", { name: /deactivate user/i }));
    expect(deactivateUser).toHaveBeenCalledWith("tok", 1);
  });
});
