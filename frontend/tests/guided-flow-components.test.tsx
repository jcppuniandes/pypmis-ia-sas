import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import CostCurrencyGate from "../src/components/CostCurrencyGate";
import GuidedProcessRail from "../src/components/GuidedProcessRail";
import NextActionPanel from "../src/components/NextActionPanel";
import TenantCommandBar from "../src/components/TenantCommandBar";
import type { CostCurrencyGate as CostCurrencyGateType, GuidedFlowStep, Project } from "../src/types";

const steps: GuidedFlowStep[] = [
  {
    key: "schedule",
    label: "Schedule intake",
    state: "complete",
    summary: "1 schedule loaded",
    next_action: "Review cost and currency gate",
    owner_role: "Planner",
    target_view: "baseline",
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
];

const gate: CostCurrencyGateType = {
  project_id: 1,
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
};

const projects: Project[] = [
  {
    id: 1,
    code: "CTRL-DEMO-001",
    name: "Demo",
    phase: "Execution",
    currency: "USD",
    calendar_base: "5x8",
    owner: "PMO",
    status: "authorized",
    authorization_date: null,
    authorization_ref: "",
    configuration: {},
    start_date: null,
    finish_date: null,
  },
];

describe("guided flow components", () => {
  it("renders tenant context and project switcher", async () => {
    const onProjectChange = vi.fn();
    render(
      <TenantCommandBar
        project={{ id: 1, code: "CTRL-DEMO-001", name: "Demo", status: "authorized", currency: "USD" }}
        projects={projects}
        selectedProjectId={1}
        userEmail="admin@demo.local"
        userName="Pypmis Admin"
        userTitle="Tenant Administrator"
        onLogout={vi.fn()}
        onProjectChange={onProjectChange}
      />,
    );

    expect(screen.getByText("Acceso de proyecto")).toBeInTheDocument();
    expect(screen.getByText("Proyectos asignados")).toBeInTheDocument();
    expect(screen.getByText("Cada usuario ve solo sus proyectos")).toBeInTheDocument();
    expect(screen.getByText("Pypmis Admin")).toBeInTheDocument();
    expect(screen.getByText(/Tenant Administrator \/ admin@demo.local/i)).toBeInTheDocument();
    expect(screen.queryByText("Demo Energy")).not.toBeInTheDocument();
    expect(screen.queryByText(/base currency/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/demo-energy/i)).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText(/project/i), "1");
    expect(onProjectChange).toHaveBeenCalledWith(1);
  });

  it("renders guided rail step state and next action", async () => {
    const onNavigate = vi.fn();
    render(
      <GuidedProcessRail
        activeKey="dashboard"
        steps={[
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
          ...steps,
        ]}
        onNavigate={onNavigate}
      />,
    );

    expect(screen.queryByText(/Tenant workspace/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Workspace ready/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Demo Energy/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /cost and currency gate/i }));
    expect(onNavigate).toHaveBeenCalledWith("baseline");
  });

  it("confirms detected currency from the gate", async () => {
    const onConfirm = vi.fn();
    render(<CostCurrencyGate gate={gate} projectCurrency="COP" onConfirm={onConfirm} />);

    await userEvent.click(screen.getByRole("button", { name: /confirm currency/i }));
    expect(onConfirm).toHaveBeenCalledWith("USD");
  });

  it("navigates from the next action panel", async () => {
    const onNavigate = vi.fn();
    render(
      <NextActionPanel
        action={{ key: "cost_currency", label: "Confirm currency", target_view: "baseline", disabled: false, reason: "" }}
        step={steps[1]}
        onNavigate={onNavigate}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /open cost and currency gate/i }));
    expect(onNavigate).toHaveBeenCalledWith("baseline");
  });
});
