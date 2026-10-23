import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CostManagerWorkspace from "./CostManagerWorkspace";
import RegistryPanel from "./RegistryPanel";
import CostMappingsPanel from "./CostMappingsPanel";
import ApuRatesPanel from "./ApuRatesPanel";
import BudgetsPanel from "./BudgetsPanel";
import BaselinesPanel from "./BaselinesPanel";
import PhasingPanel from "./PhasingPanel";
import { ActualsPanel, CommitmentsPanel, CurrencyPanel, OverviewPanel } from "./FinancialPanels";
import GovernedProfilesAdminView from "../awp/GovernedProfilesAdminView";
import { governedProfilesApi } from "../awp/api";
import { costApi } from "./api";
import { moneyDisplay, type CostOverview, type CostPanelProps } from "./types";

const row = { id: 1, version: 4, status: "ACTIVE", revision: 1, code: "C-1", name: "Structure" };
const overview: CostOverview = {
  context: {},
  configuration: { content_json: { cost_code_categories: ["LABOR", "CUSTOM_LOGISTICS"] } },
  allowed_actions: [
    "read",
    "cbs.edit",
    "code.edit",
    "account.edit",
    "mapping.edit",
    "rate.edit",
    "rate.publish",
    "apu.edit",
    "apu.publish",
    "budget.prepare",
    "budget.submit",
    "budget.review",
    "budget.approve",
    "baseline.prepare",
    "baseline.approve",
    "phasing.edit",
    "actual.import",
    "actual.approve",
    "actual.adjust",
    "fx.edit",
    "fx.publish",
    "commitment.reconcile",
    "commitment.verify",
  ],
  cbs: [row],
  cost_codes: [{ ...row, id: 2, code: "LAB-1", category: "LABOR" }],
  control_accounts: [{ ...row, id: 3, code: "CA-1", owner_user_id: 9 }],
  mappings: [],
  rates: [
    {
      ...row,
      id: 4,
      code: "RATE-1",
      resource_type: "LABOR",
      status: "PUBLISHED",
      amount: "20",
      currency: "USD",
      unit: "h",
    },
  ],
  apus: [
    {
      ...row,
      id: 5,
      code: "APU-1",
      status: "PUBLISHED",
      unit: "m2",
      unit_amount: "30",
      currency: "USD",
      components_json: [],
    },
  ],
  budgets: [{ ...row, id: 6, code: "BUD-1", status: "DRAFT", budget_type: "ORIGINAL", currency: "USD" }],
  budget_lines: [
    {
      ...row,
      id: 7,
      budget_version_id: 6,
      line_code: "L-1",
      amount: "300",
      currency: "USD",
      quantity: "10",
      unit: "m2",
      rate: "30",
    },
  ],
  baselines: [{ ...row, id: 8, code: "BL-1", status: "CANDIDATE", budget_version_id: 6 }],
  phasing: [],
  actuals: [{ ...row, id: 9, status: "IMPORTED", source_reference: "AC-1", amount: "10", currency: "USD" }],
  commitment_references: [
    {
      ...row,
      id: 10,
      status: "PROPOSED",
      source_reference: "CTR-1",
      economic_origin: "OBL-1",
      inclusion_mode: "ADDITIVE",
      amount: "1000",
      currency: "USD",
    },
  ],
  history: [],
  scope_items: [{ id: 11, scope_code: "S-1", name: "Approved slab", status: "APPROVED" }],
  plan_items: [{ id: 12, code: "P-1", name: "Sector", status: "PUBLISHED" }],
  packages: [{ id: 13, package_code: "WP-1", name: "Installation" }],
  schedule_versions: [
    {
      id: 14,
      status: "ACCEPTED_CURRENT",
      snapshot_json: {
        activities: [{ external_id: "A100", name: "Install" }],
        wbs: [{ external_id: "W1", name: "Structure" }],
      },
    },
  ],
  periods: [
    { id: 15, period_code: "OCT-26", status: "OPEN" },
    { id: 16, period_code: "OLD", status: "PUBLISHED" },
  ],
  fx_rates: [
    { ...row, id: 17, status: "DRAFT", code: "FX-1", from_currency: "COP", to_currency: "USD", rate: "0.00025" },
  ],
};
const props = (data = overview): CostPanelProps => ({
  data,
  busy: false,
  reason: "Controlled isolated test operation",
  command: vi.fn().mockResolvedValue({ id: 99, version: 1, status: "DRAFT" }),
  can: (action) => data.allowed_actions.includes(action),
  query: vi.fn().mockResolvedValue({ items: [], status: "AGGREGATED", net_commitment: "1000", currency: "USD" }),
});
function change(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } });
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Cost Foundation workspace and authority boundaries", () => {
  it("provides eleven submodules without funding/payment controls", async () => {
    vi.spyOn(costApi, "overview").mockResolvedValue(overview);
    render(<CostManagerWorkspace token="test" workspaceId={77} />);
    expect(await screen.findByRole("navigation", { name: "Cost Manager submodules" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Cost Manager submodules" }).querySelectorAll("button")).toHaveLength(
      11
    );
    expect(screen.queryByRole("button", { name: "Add Funding" })).not.toBeInTheDocument();
    expect(screen.getByText(/Cost no redefine cantidad/)).toBeInTheDocument();
  });
  it("shows deferred accrual contract without functional mutation form", async () => {
    vi.spyOn(costApi, "overview").mockResolvedValue(overview);
    render(<CostManagerWorkspace token="test" workspaceId={77} />);
    fireEvent.click(await screen.findByRole("button", { name: "Accruals" }));
    expect(screen.getByText("DEFERRED_WITH_CONTRACT")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Crear Accrual/ })).not.toBeInTheDocument();
  });
  it("hides mutation forms from read-only actors", async () => {
    vi.spyOn(costApi, "overview").mockResolvedValue({ ...overview, allowed_actions: ["read"] });
    render(<CostManagerWorkspace token="test" workspaceId={77} />);
    await screen.findByRole("table", { name: "CBS" });
    expect(screen.queryByRole("button", { name: "Crear CBS" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Guardar Cost Mapping" })).not.toBeInTheDocument();
  });
  it("keeps an archived Workspace read-only even when role permissions include edit", async () => {
    vi.spyOn(costApi, "overview").mockResolvedValue(overview);
    render(<CostManagerWorkspace token="test" workspaceId={77} readOnly />);
    await screen.findByText(/Workspace archivado/);
    expect(screen.queryByRole("button", { name: "Crear CBS" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Budget" }));
    expect(screen.queryByRole("button", { name: "Crear Budget DRAFT" })).not.toBeInTheDocument();
  });
  it("presents backend failures without an empty working-looking Cost UI", async () => {
    vi.spyOn(costApi, "overview").mockRejectedValue(new Error("Cost access not granted"));
    render(<CostManagerWorkspace token="test" workspaceId={77} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Cost access not granted");
    expect(screen.queryByRole("navigation", { name: "Cost Manager submodules" })).not.toBeInTheDocument();
  });
});

describe("Cost structure and explicit source-first mappings", () => {
  it("creates CBS through the dedicated Cost writer", async () => {
    const panel = props();
    render(<RegistryPanel {...panel} kind="CBS" />);
    change("CBS Code", "CBS-NEW");
    change("CBS Name", "New cost node");
    change("CBS Parent", "1");
    fireEvent.click(screen.getByRole("button", { name: "Crear CBS" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith(
        "/cbs",
        expect.objectContaining({ code: "CBS-NEW", parent_id: 1, reason: panel.reason }),
        undefined,
        "POST"
      )
    );
  });
  it("updates CBS with the selected record ETag and not Schedule", async () => {
    const panel = props();
    render(<RegistryPanel {...panel} kind="CBS" />);
    fireEvent.click(screen.getByRole("button", { name: "Ver CBS C-1" }));
    expect(screen.getByLabelText("CBS Code")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Guardar CBS" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith("/cbs/1", expect.objectContaining({ name: "Structure" }), 4, "PUT")
    );
  });
  it("uses published Cost Code dictionary rather than unconfigured categories", () => {
    render(<RegistryPanel {...props()} kind="Cost Codes" />);
    expect(screen.getByRole("option", { name: "CUSTOM_LOGISTICS" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "EQUIPMENT" })).not.toBeInTheDocument();
  });
  it("requires explicit owner for a Control Account", async () => {
    const panel = props();
    render(<RegistryPanel {...panel} kind="Control Accounts" />);
    change("Control Accounts Code", "CA-2");
    change("Control Accounts Name", "Responsible cost account");
    change("Control Account Owner User ID", "9");
    fireEvent.click(screen.getByRole("button", { name: "Crear Control Accounts" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith(
        "/control-accounts",
        expect.objectContaining({ owner_user_id: 9, responsible_role: "cost_controller" }),
        undefined,
        "POST"
      )
    );
  });
  it.each([
    ["SCOPE", "11"],
    ["PLAN", "12"],
    ["PACKAGE", "13"],
  ])("maps %s explicitly without changing its source", async (kind, identity) => {
    const panel = props();
    render(<CostMappingsPanel {...panel} />);
    change("Cost Mapping Source Kind", kind);
    change(`Cost Mapping ${kind}`, identity);
    change("Cost Mapping CBS", "1");
    change("Cost Mapping source_reference", "SRC-TEST");
    fireEvent.click(screen.getByRole("button", { name: "Guardar Cost Mapping" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith(
        "/mappings",
        expect.objectContaining({
          source_kind: kind,
          source_id: Number(identity),
          cbs_id: 1,
          effective_revision: "1",
          source_reference: "SRC-TEST",
        })
      )
    );
  });
  it.each([
    ["WBS", "W1"],
    ["ACTIVITY", "A100"],
  ])("maps %s from immutable Schedule version", async (kind, external) => {
    const panel = props();
    render(<CostMappingsPanel {...panel} />);
    change("Cost Mapping Source Kind", kind);
    change("Cost Mapping Schedule Version", "14");
    change(`Cost Mapping ${kind}`, external);
    change("Cost Mapping Control Account", "3");
    change("Cost Mapping source_reference", "SCH-REF");
    fireEvent.click(screen.getByRole("button", { name: "Guardar Cost Mapping" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith(
        "/mappings",
        expect.objectContaining({
          source_id: null,
          schedule_version_id: 14,
          source_external_id: external,
          control_account_id: 3,
        })
      )
    );
  });
  it("requires one explicit Cost target before saving mappings", () => {
    render(<CostMappingsPanel {...props()} />);
    expect(screen.getByRole("button", { name: "Guardar Cost Mapping" })).toBeDisabled();
  });
});

describe("APU, rates, currency and budget candidates", () => {
  it("constructs resource-aware APU components, not a direct approved Budget", async () => {
    const panel = props();
    render(<ApuRatesPanel {...panel} />);
    for (const [label, value] of [
      ["APU code", "NEW-APU"],
      ["APU name", "Labor assembly"],
      ["APU effective_from", "2026-10-01"],
      ["APU source_reference", "REFERENCE-APU"],
    ])
      change(label, value);
    change("APU Component 1 Rate", "4");
    change("APU Component 1 Quantity", "1.5");
    fireEvent.click(screen.getByRole("button", { name: "Crear APU DRAFT" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith(
        "/apus",
        expect.objectContaining({
          components: [{ rate_id: 4, category: "LABOR", quantity_per_unit: "1.5", unit: "h" }],
          factors: [],
          reason: panel.reason,
        })
      )
    );
  });
  it("shows rates as immutable published historical records", () => {
    render(<ApuRatesPanel {...props()} />);
    fireEvent.click(screen.getByRole("button", { name: "Ver Cost Rates RATE-1" }));
    expect(screen.getByText(/publicada|histórica/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publicar Rate independiente" })).not.toBeInTheDocument();
  });
  it("creates Budget with explicit pricing date and source references", async () => {
    const panel = props();
    render(<BudgetsPanel {...panel} />);
    change("Budget code", "BUD-NEW");
    change("Budget name", "Original plan");
    change("Budget Pricing Date", "2026-10-21");
    fireEvent.click(screen.getByRole("button", { name: "Crear Budget DRAFT" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith(
        "/budgets",
        expect.objectContaining({ source_references: { pricing_date: "2026-10-21" }, budget_type: "ORIGINAL" })
      )
    );
  });
  it("creates Scope × APU candidate using original quantity authority and Budget ETag", async () => {
    const panel = props();
    render(<BudgetsPanel {...panel} />);
    change("Budget Candidate Line Code", "L-SCOPE");
    change("Budget Candidate Scope", "11");
    change("Budget Candidate APU", "5");
    change("Budget Candidate CBS", "1");
    fireEvent.click(screen.getByRole("button", { name: "Construir Budget Candidate desde Scope" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith(
        "/budgets/6/candidate-from-scope",
        expect.objectContaining({ scope_item_id: 11, apu_id: 5, line_code: "L-SCOPE", cbs_id: 1 }),
        4
      )
    );
    expect(screen.queryByLabelText("Budget Candidate Quantity")).not.toBeInTheDocument();
  });
  it.each([
    ["DRAFT", "Enviar Budget", "SUBMITTED"],
    ["SUBMITTED", "Revisar Budget", "UNDER_REVIEW"],
    ["UNDER_REVIEW", "Aprobar Budget independiente", "APPROVED"],
  ])("performs governed %s Budget lifecycle transition", async (status, label, next) => {
    const panel = props({ ...overview, budgets: [{ ...overview.budgets[0], status }] });
    render(<BudgetsPanel {...panel} />);
    fireEvent.click(screen.getByRole("button", { name: label }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith("/budgets/6/transition", { status: next, reason: panel.reason }, 4)
    );
  });
  it("approved Budget exposes successor but no editable candidate", () => {
    render(<BudgetsPanel {...props({ ...overview, budgets: [{ ...overview.budgets[0], status: "APPROVED" }] })} />);
    expect(screen.getByRole("button", { name: "Crear Budget sucesor" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Construir Budget Candidate desde Scope" })).not.toBeInTheDocument();
  });
  it("never displays a sum for currencies without governed FX", () => {
    expect(moneyDisplay({ status: "NO_AGGREGATION", amount: null })).toContain("NO_AGGREGATION");
    expect(moneyDisplay({ status: "AGGREGATED", amount: "120", currency: "USD" })).toBe("120 USD");
  });
});

describe("Cost Baseline and phasing governance", () => {
  it("creates baseline only from approved Budget selector", () => {
    render(<BaselinesPanel {...props()} />);
    expect(screen.getByLabelText("Cost Baseline Budget").querySelectorAll("option")).toHaveLength(1);
  });
  it("approves baseline with explicit independent command and ETag", async () => {
    const panel = props();
    render(<BaselinesPanel {...panel} />);
    fireEvent.click(screen.getByRole("button", { name: "Ver Cost Baselines BL-1" }));
    fireEvent.click(screen.getByRole("button", { name: "Aprobar Cost Baseline independiente" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith("/baselines/8/approve", { reason: panel.reason }, 4)
    );
  });
  it("phases using existing Activity dates without manual date authority", async () => {
    const panel = props();
    render(<PhasingPanel {...panel} />);
    change("Phasing Cost Baseline", "8");
    change("Phasing Budget Line", "7");
    change("Cost Phasing Method", "ACTIVITY_BASED");
    change("Phasing Schedule Version", "14");
    change("Phasing Activity", "A100");
    change("Phasing Project Controls Period", "15");
    fireEvent.click(screen.getByRole("button", { name: "Distribuir Cost Baseline" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith(
        "/baselines/8/phase",
        expect.objectContaining({
          budget_line_id: 7,
          method: "ACTIVITY_BASED",
          schedule_version_id: 14,
          source_external_id: "A100",
          period_id: 15,
          start_date: null,
          finish_date: null,
        }),
        4
      )
    );
  });
  it("does not expose published period as a phasing mutation target", () => {
    render(<PhasingPanel {...props()} />);
    expect(screen.getByLabelText("Phasing Project Controls Period").querySelector('option[value="16"]')).toBeNull();
  });
  it("approved baseline is absent from editable phasing targets", () => {
    render(<PhasingPanel {...props({ ...overview, baselines: [{ ...overview.baselines[0], status: "APPROVED" }] })} />);
    expect(screen.getByLabelText("Phasing Cost Baseline").querySelectorAll("option")).toHaveLength(1);
  });
});

describe("Recognition, reconciliation and administrative separation", () => {
  it("recognizes Actual independently with source record ETag", async () => {
    const panel = props();
    render(<ActualsPanel {...panel} />);
    fireEvent.click(screen.getByRole("button", { name: "Ver Actual Cost C-1" }));
    fireEvent.click(screen.getByRole("button", { name: "Reconocer Actual independiente" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith(
        "/actuals/9/decision",
        { status: "RECOGNIZED", reason: panel.reason },
        4
      )
    );
  });
  it("excludes published O1A periods from Actual import", () => {
    render(<ActualsPanel {...props()} />);
    expect(screen.getByLabelText("Actual Period").querySelector('option[value="16"]')).toBeNull();
  });
  it("verifies projection independently, without Contract award", async () => {
    const panel = props();
    render(<CommitmentsPanel {...panel} />);
    await screen.findByText("Net Commitment");
    fireEvent.click(screen.getByRole("button", { name: "Ver Commitment References C-1" }));
    fireEvent.click(screen.getByRole("button", { name: "Verificar Commitment independiente" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith(
        "/commitments/10/verify",
        { status: "VERIFIED", reason: panel.reason },
        4
      )
    );
    expect(screen.queryByRole("button", { name: /Award Contract/ })).not.toBeInTheDocument();
  });
  it("exposes all four governed inclusion modes", async () => {
    render(<CommitmentsPanel {...props()} />);
    await screen.findByRole("table", { name: "Commitment References" });
    for (const name of ["INCLUDED", "CALL_OFF", "ADDITIVE", "REFERENCE_ONLY"])
      expect(screen.getByRole("option", { name })).toBeInTheDocument();
  });
  it("publishes FX with exact record ETag and no historical overwrite", async () => {
    const panel = props();
    render(<CurrencyPanel {...panel} />);
    fireEvent.click(screen.getByRole("button", { name: "Ver FX Rates FX-1" }));
    fireEvent.click(screen.getByRole("button", { name: "Publicar FX independiente" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith("/fx-rates/17/publish", { reason: panel.reason }, 4)
    );
  });
  it("publishes Cost configuration via dedicated ADMIN authority", async () => {
    const profile = {
      id: 20,
      version: 2,
      revision: 1,
      code: "COST-PROFILE",
      name: "Cost",
      status: "draft",
      content_json: {},
    };
    vi.spyOn(governedProfilesApi, "list").mockResolvedValue({
      items: [profile],
      default_content: {},
      allowed_actions: ["admin.configure", "admin.publish"],
    });
    const command = vi.spyOn(governedProfilesApi, "command").mockResolvedValue(profile);
    render(<GovernedProfilesAdminView token="test" kind="cost" />);
    fireEvent.click(await screen.findByRole("button", { name: "Ver Cost Profiles COST-PROFILE" }));
    change("Motivo Cost Profiles", "Independent cost policy publication");
    fireEvent.click(screen.getByRole("button", { name: "Publicar Cost Profiles" }));
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith(
        "test",
        "/api/v1/cost/admin/profiles",
        "/20/publish",
        { reason: "Independent cost policy publication" },
        expect.any(String),
        2,
        "POST"
      )
    );
  });
  it("overview retains Forecast/Progress/Treasury boundaries", async () => {
    render(<OverviewPanel {...props()} />);
    await screen.findByRole("table", { name: "Cost Cash Flow" });
    expect(screen.getByText(/EAC = Actual reconocido/)).toBeInTheDocument();
    expect(screen.getByText(/no administra Funding\/FIN/)).toBeInTheDocument();
  });
});
