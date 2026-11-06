import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ProgressManagerWorkspace from "./ProgressManagerWorkspace";
import MeasurementsPanel from "./MeasurementsPanel";
import RulesPanel from "./RulesPanel";
import { BaselineIntegrationPanel, PeriodReviewPanel } from "./IntegrationPanels";
import { AggregationPanel, EvmPanel, OverlayPanel, ProjectionPanel } from "./ReadPanels";
import GovernedProfilesAdminView from "../awp/GovernedProfilesAdminView";
import { governedProfilesApi } from "../awp/api";
import { progressApi, parameters } from "./api";
import {
  display,
  object,
  percentage,
  progressTabs,
  revision,
  rows,
  type ProgressOverview,
  type ProgressPanelProps,
} from "./types";

const overview: ProgressOverview = {
  context: {},
  configuration: null,
  allowed_actions: [
    "read",
    "capture",
    "submit",
    "review",
    "approve",
    "quantity.certify",
    "milestone.certify",
    "rule.manage",
    "rule.publish",
    "baseline.prepare",
    "baseline.approve",
    "period.freeze",
    "period.publish",
    "evm.view",
  ],
  measurements: [
    {
      id: 10,
      code: "PHY-1",
      name: "Physical scope",
      status: "APPROVED",
      version: 3,
      revision: 1,
      progress_type: "PHYSICAL",
      method: "QUANTITY_BASED",
      numerator: "5",
      denominator: "10",
      progress_value: "50",
      period_progress: "50",
      period_quantity: "5",
      cumulative_quantity: "5",
      scope_item_id: 1,
      period_id: 20,
      source_reference: "FIELD-1",
      measurement_date: "2026-10-21",
      as_of: "2026-10-22",
      unit: "m3",
      phase: "INSTALL",
      input_json: { input_mode: "CUMULATIVE" },
      evidence_json: [{ kind: "FIELD_REPORT", reference: "FIELD-1" }],
    },
    {
      id: 11,
      code: "QTY-1",
      name: "Quantity scope",
      status: "DRAFT",
      version: 2,
      revision: 1,
      progress_type: "QUANTITY",
      method: "QUANTITY_BASED",
      numerator: "4",
      denominator: "10",
      progress_value: "40",
      scope_item_id: 1,
      period_id: 20,
      unit: "m3",
      evidence_json: [{ kind: "FIELD_REPORT", reference: "FIELD-2" }],
    },
  ],
  rules: [
    {
      id: 12,
      version: 2,
      revision: 1,
      status: "PUBLISHED",
      code: "ROC-1",
      name: "Installation credit",
      method: "RULE_OF_CREDIT",
      steps_json: [
        { code: "SET", name: "Set in position", weight: "30" },
        { code: "TESTED", name: "Tested", weight: "70" },
      ],
      scope_natures: ["INSTALL"],
      package_types: ["IWP"],
    },
  ],
  scope_items: [
    {
      id: 1,
      scope_code: "S-1",
      name: "Approved Scope",
      status: "APPROVED",
      quantity: "10",
      unit: "m3",
      scope_nature: "INSTALL",
    },
  ],
  plan_items: [{ id: 2, code: "P-1", name: "Published Plan", status: "PUBLISHED" }],
  packages: [{ id: 3, package_code: "IWP-1", name: "Ready is not progress", status: "READY", package_type: "IWP" }],
  schedule_versions: [{ id: 4, code: "SCH-1", status: "ACCEPTED_CURRENT" }],
  scope_baselines: [{ id: 30, code: "SB-1", approved_by: 2, approved_at: "2026-10-19T08:00:00Z" }],
  schedule_baselines: [{ id: 31, code: "SHB-1", status: "APPROVED_BASELINE" }],
  cost_baselines: [{ id: 32, code: "CB-1", status: "APPROVED" }],
  periods: [
    {
      id: 20,
      version: 2,
      revision: 1,
      period_code: "OCT-2026",
      status: "OPEN",
      cutoff_at: "2026-10-25T22:00:00Z",
      schedule_data_date: "2026-10-22",
    },
  ],
  control_accounts: [{ id: 5, code: "CA-1", name: "Account", status: "ACTIVE" }],
  baseline_bundles: [
    {
      id: 40,
      code: "BUNDLE-1",
      name: "Integrated Control",
      status: "APPROVED",
      version: 3,
      scope_baseline_id: 30,
      schedule_baseline_id: 31,
      cost_baseline_id: 32,
      effective_date: "2026-10-19",
      content_hash: "frozen-hash",
    },
  ],
  history: [
    {
      id: 50,
      event_type: "PROGRESS_APPROVED",
      entity_id: 10,
      entity_type: "measurement",
      revision: 1,
      reason: "Independent approval",
      created_by: 2,
    },
  ],
};
function props(changes: Partial<ProgressPanelProps> = {}): ProgressPanelProps {
  return {
    data: overview,
    periodId: "20",
    asOf: "2026-10-22",
    reason: "Independent governed test reason",
    busy: false,
    can: () => true,
    command: vi.fn().mockResolvedValue({ id: 11, version: 3, status: "DRAFT" }),
    query: vi.fn().mockResolvedValue({ items: [] }),
    ...changes,
  };
}
function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } });
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Progress navigation and command boundaries", () => {
  it("shows all ten requested screens without equating progress authorities", async () => {
    vi.spyOn(progressApi, "overview").mockResolvedValue(overview);
    vi.spyOn(progressApi, "query").mockResolvedValue({ items: [] });
    render(<ProgressManagerWorkspace token="token" workspaceId={99} />);
    expect(await screen.findByRole("heading", { name: "Progress Manager" })).toBeTruthy();
    await screen.findByRole("navigation", { name: "Progress Manager submodules" });
    for (const title of progressTabs) expect(screen.getByRole("button", { name: title })).toBeTruthy();
    expect(screen.getByText(/Physical ≠ Quantity ≠ Schedule ≠ Cost ≠ Earned/)).toBeTruthy();
  });
  it("does not pick cutoff or current date as measurement as-of", async () => {
    vi.spyOn(progressApi, "overview").mockResolvedValue(overview);
    render(<ProgressManagerWorkspace token="token" workspaceId={99} />);
    await screen.findByLabelText("Progress Controls Period");
    expect((screen.getByLabelText("Progress as-of date") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Progress Controls Period") as HTMLSelectElement).value).toBe("");
  });
  it("archived workspace hides capture and snapshot mutations", async () => {
    vi.spyOn(progressApi, "overview").mockResolvedValue(overview);
    render(<ProgressManagerWorkspace token="token" workspaceId={99} readOnly />);
    await screen.findByRole("button", { name: "Quantity Progress" });
    fireEvent.click(screen.getByRole("button", { name: "Quantity Progress" }));
    expect(screen.queryByRole("button", { name: "Crear QUANTITY DRAFT" })).toBeNull();
    expect(screen.getByText(/Workspace archivado/)).toBeTruthy();
  });
  it("reports API failure without substituting zero progress", async () => {
    vi.spyOn(progressApi, "overview").mockRejectedValue(new Error("Progress permission denied"));
    render(<ProgressManagerWorkspace token="token" workspaceId={99} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Progress permission denied");
    expect(screen.queryByText("0 %")).toBeNull();
  });
  it("supports prefixed granular permissions", async () => {
    vi.spyOn(progressApi, "overview").mockResolvedValue({ ...overview, allowed_actions: ["progress.read"] });
    render(<ProgressManagerWorkspace token="token" workspaceId={99} />);
    await screen.findByRole("button", { name: "Quantity Progress" });
    fireEvent.click(screen.getByRole("button", { name: "Quantity Progress" }));
    expect(screen.queryByRole("button", { name: "Nueva medición QUANTITY" })).toBeNull();
  });
});
describe("Governed measurement forms", () => {
  it("sends decimal numerator and source identity but never computed denominator or percent", async () => {
    const p = props();
    render(<MeasurementsPanel {...p} progressType="QUANTITY" />);
    fill("QUANTITY Code", "QTY-NEW");
    fill("QUANTITY Name", "Completed installed quantity");
    fill("QUANTITY SCOPE", "1");
    fill("QUANTITY Source reference", "SOURCE-1");
    fill("QUANTITY Measurement date", "2026-10-21");
    fill("QUANTITY Numerator", "4.125");
    fill("QUANTITY Unit", "m3");
    fill("QUANTITY Evidence reference", "FIELD-REPORT-1");
    fireEvent.submit(screen.getByRole("form", { name: "QUANTITY capture form" }));
    await waitFor(() => expect(p.command).toHaveBeenCalled());
    const payload = vi.mocked(p.command).mock.calls[0][1] as Record<string, unknown>;
    expect(payload).toMatchObject({
      numerator: "4.125",
      period_id: 20,
      as_of: "2026-10-22",
      measurement_date: "2026-10-21",
      scope_item_id: 1,
      denominator_basis: "AUTO",
      evidence_refs: [{ kind: "FIELD_REPORT", reference: "FIELD-REPORT-1" }],
    });
    expect(payload).not.toHaveProperty("progress_value");
    expect(payload).not.toHaveProperty("denominator");
  });
  it("uses an explicitly chosen Project aggregate for approved weighted components", async () => {
    const p = props();
    render(<MeasurementsPanel {...p} progressType="WEIGHTED" />);
    expect(screen.getByLabelText("WEIGHTED Source Kind")).toHaveValue("SCOPE");
    fill("WEIGHTED Source Kind", "PROJECT");
    expect(screen.queryByLabelText("WEIGHTED SCOPE")).toBeNull();
    fill("WEIGHTED Code", "WEIGHTED-PROJECT");
    fill("WEIGHTED Name", "Governed Project aggregate");
    fill("WEIGHTED Source reference", "APPROVED-COMPONENT-SOURCES");
    fill("WEIGHTED Measurement date", "2026-10-21");
    fill("WEIGHTED Unit", "%");
    fill("WEIGHTED Evidence reference", "INDEPENDENT-COMPONENT-REVIEW");
    fill("WEIGHTED Component 10", "1");
    fireEvent.submit(screen.getByRole("form", { name: "WEIGHTED capture form" }));
    await waitFor(() => expect(p.command).toHaveBeenCalled());
    const payload = vi.mocked(p.command).mock.calls[0][1] as Record<string, unknown>;
    expect(payload).toMatchObject({
      method: "WEIGHTED_COMPONENTS",
      scope_item_id: null,
      plan_item_id: null,
      work_package_id: null,
      components: [{ measurement_id: 10, weight: "1" }],
    });
    expect(payload).not.toHaveProperty("progress_value");
    expect(payload).not.toHaveProperty("denominator");
  });
  it.each(["CLOSED", "PUBLISHED", "REVIEW"])("blocks capture in %s periods", (status) => {
    render(
      <MeasurementsPanel
        {...props({ data: { ...overview, periods: [{ ...overview.periods[0], status }] } })}
        progressType="QUANTITY"
      />
    );
    expect(screen.getByRole("button", { name: "Crear QUANTITY DRAFT" })).toBeDisabled();
    expect(screen.getByText(/no está OPEN/)).toBeTruthy();
  });
  it("keeps submit disabled without a command reason", () => {
    render(<MeasurementsPanel {...props({ reason: "" })} progressType="QUANTITY" />);
    fireEvent.click(screen.getByRole("button", { name: "Ver QUANTITY measurements QTY-1" }));
    expect(screen.getByRole("button", { name: "Enviar QUANTITY" })).toBeDisabled();
  });
  it("submits draft with its ETag", async () => {
    const p = props();
    render(<MeasurementsPanel {...p} progressType="QUANTITY" />);
    fireEvent.click(screen.getByRole("button", { name: "Ver QUANTITY measurements QTY-1" }));
    fireEvent.click(screen.getByRole("button", { name: "Enviar QUANTITY" }));
    await waitFor(() =>
      expect(p.command).toHaveBeenCalledWith(
        "/measurements/11/transition",
        { status: "SUBMITTED", reason: p.reason },
        2
      )
    );
  });
  it("approved measurements expose successor not overwrite", () => {
    render(<MeasurementsPanel {...props()} progressType="PHYSICAL" />);
    fireEvent.click(screen.getByRole("button", { name: "Ver PHYSICAL measurements PHY-1" }));
    expect(screen.getByRole("button", { name: "Crear sucesor PHYSICAL" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Guardar PHYSICAL DRAFT" })).toBeNull();
  });
  it("offers explicit nature, phase, period delta and correction fields", () => {
    render(<MeasurementsPanel {...props()} progressType="PHYSICAL" />);
    for (const label of [
      "PHYSICAL Scope Nature",
      "PHYSICAL Nature phase",
      "PHYSICAL Input mode",
      "PHYSICAL Correction kind",
      "PHYSICAL Weight basis",
    ])
      expect(screen.getByLabelText(label)).toBeTruthy();
  });
  it("rule selection reveals weighted completed steps", () => {
    render(<MeasurementsPanel {...props()} progressType="PHYSICAL" />);
    fill("PHYSICAL Method", "RULE_OF_CREDIT");
    fill("PHYSICAL Published rule", "12");
    expect(screen.getByRole("checkbox", { name: "PHYSICAL Step SET" })).toBeTruthy();
    expect(screen.getByText(/Set in position/)).toBeTruthy();
  });
  it("quantity certification uses a distinct command and evidence reference", async () => {
    const data = { ...overview, measurements: [{ ...overview.measurements[1], status: "SUBMITTED" }] };
    const p = props({ data });
    render(<MeasurementsPanel {...p} progressType="QUANTITY" />);
    fireEvent.click(screen.getByRole("button", { name: "Ver QUANTITY measurements QTY-1" }));
    fireEvent.click(screen.getByRole("button", { name: "Certificar QUANTITY" }));
    await waitFor(() =>
      expect(p.command).toHaveBeenCalledWith(
        "/measurements/11/certify",
        { reason: p.reason, evidence_reference: "FIELD-2" },
        2
      )
    );
  });
  it("milestone certification permission does not expose quantity certification", () => {
    const data = {
      ...overview,
      measurements: [{ ...overview.measurements[1], status: "SUBMITTED", method: "QUANTITY_BASED" }],
    };
    render(
      <MeasurementsPanel
        {...props({ data, can: (action) => action === "milestone.certify" })}
        progressType="QUANTITY"
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Ver QUANTITY measurements QTY-1" }));
    expect(screen.queryByRole("button", { name: "Certificar QUANTITY" })).toBeNull();
  });
});
describe("Profiles and rule publication", () => {
  it("reuses the dedicated governed profile ADMIN editor", async () => {
    const list = vi.spyOn(governedProfilesApi, "list").mockResolvedValue({
      items: [],
      default_content: { baseline_policy: { block_stale: true }, weighting_rules: {} },
      allowed_actions: ["admin.configure"],
    });
    render(<GovernedProfilesAdminView token="token" kind="progress" />);
    await screen.findByLabelText("Progress Profiles configuration JSON");
    expect(list).toHaveBeenCalledWith("token", "/api/v1/progress/admin/profiles");
    expect(screen.getByRole("heading", { name: "Progress Profiles" })).toBeTruthy();
  });
  it.each(["create", "update"])("sends an explicit Progress profile reason for %s", async (operation) => {
    const profile = {
      id: 61,
      code: "PROGRESS-REASON",
      name: "Progress policy",
      status: "draft",
      version: 2,
      revision: 1,
      content_json: { baseline_policy: { block_stale: true } },
    };
    vi.spyOn(governedProfilesApi, "list").mockResolvedValue({
      items: operation === "update" ? [profile] : [],
      default_content: profile.content_json,
      allowed_actions: ["admin.configure"],
    });
    const command = vi.spyOn(governedProfilesApi, "command").mockResolvedValue(profile);
    render(<GovernedProfilesAdminView token="token" kind="progress" />);
    await screen.findByLabelText("Progress Profiles configuration JSON");
    if (operation === "update")
      fireEvent.click(screen.getByRole("button", { name: "Ver Progress Profiles PROGRESS-REASON" }));
    else {
      fill("Progress Profiles Code", profile.code);
      fill("Progress Profiles Name", profile.name);
    }
    const save = screen.getByRole("button", {
      name: operation === "update" ? "Guardar Progress Profiles borrador" : "Crear Progress Profiles DRAFT",
    });
    expect(save).toBeDisabled();
    fill("Motivo Progress Profiles", "short");
    expect(save).toBeDisabled();
    fill("Motivo Progress Profiles", "  Explicit governed policy rationale  ");
    expect(save).not.toBeDisabled();
    fireEvent.click(save);
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith(
        "token",
        "/api/v1/progress/admin/profiles",
        operation === "update" ? "/61" : "",
        {
          ...(operation === "update" ? {} : { code: profile.code }),
          name: profile.name,
          content_json: profile.content_json,
          reason: "Explicit governed policy rationale",
        },
        expect.any(String),
        operation === "update" ? 2 : undefined,
        operation === "update" ? "PUT" : "POST"
      )
    );
  });
  it("does not add Progress reason requirements to existing Cost profile authoring", async () => {
    vi.spyOn(governedProfilesApi, "list").mockResolvedValue({
      items: [],
      default_content: {},
      allowed_actions: ["admin.configure"],
    });
    render(<GovernedProfilesAdminView token="token" kind="cost" />);
    const save = await screen.findByRole("button", { name: "Crear Cost Profiles DRAFT" });
    expect(save).not.toBeDisabled();
    expect(screen.queryByLabelText("Motivo Cost Profiles")).toBeNull();
  });
  it("published rules cannot be saved in place", () => {
    render(<RulesPanel {...props()} />);
    fireEvent.click(screen.getByRole("button", { name: "Ver Progress Rules ROC-1" }));
    expect(screen.getByLabelText("Rule Name")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Crear sucesor de regla" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Guardar regla DRAFT" })).toBeNull();
  });
  it("supports discrete and multi-step presets without client-calculated credit", () => {
    render(<RulesPanel {...props()} />);
    fill("Rule Preset", "50/50");
    expect(screen.getByLabelText("Rule Step Weight 2")).toHaveValue(50);
    fill("Rule Preset", "10/20/30/40");
    expect(screen.getByLabelText("Rule Step Weight 4")).toHaveValue(40);
  });
});
describe("Bundle, period and EVM safeguards", () => {
  it("uses explicit approved baseline selectors with native domain approval states", () => {
    render(<BaselineIntegrationPanel {...props()} bundleId="" setBundleId={vi.fn()} />);
    for (const label of [
      "Bundle Scope Baseline",
      "Bundle Schedule Baseline",
      "Bundle Cost Baseline",
      "Bundle Effective date",
    ])
      expect(screen.getByLabelText(label)).toBeTruthy();
    expect(screen.getByLabelText("Bundle Scope Baseline").querySelector('option[value="30"]')).toBeTruthy();
    expect(screen.getByLabelText("Bundle Schedule Baseline").querySelector('option[value="31"]')).toBeTruthy();
    expect(screen.getByLabelText("Bundle Cost Baseline").querySelector('option[value="32"]')).toBeTruthy();
  });
  it("stale bundle displays blocking reason and frozen hash", async () => {
    const p = props({
      query: vi.fn().mockResolvedValue({
        status: "BLOCK",
        effective_state: "REQUIRES_REVIEW",
        reason_codes: ["BUNDLE_SOURCE_DRIFT"],
        frozen_hash: "frozen-hash",
      }),
    });
    render(<BaselineIntegrationPanel {...p} bundleId="40" setBundleId={vi.fn()} />);
    expect(await screen.findByText("BUNDLE_SOURCE_DRIFT")).toBeTruthy();
    expect(screen.getByText("Validación del bundle: BLOCK")).toBeTruthy();
  });
  it("freezes period through the governed transition with ETag", async () => {
    const p = props();
    render(<PeriodReviewPanel {...p} setPeriodId={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Congelar Progress para revisión" }));
    await waitFor(() =>
      expect(p.command).toHaveBeenCalledWith(
        "/periods/20/transition",
        { action: "review", reason: p.reason, notes: "" },
        2
      )
    );
  });
  it("EVM missing basis has no fabricated PV or EV", () => {
    render(<EvmPanel {...props()} bundleId="" setBundleId={vi.fn()} />);
    expect(screen.getByText(/Seleccione bundle aprobado/)).toBeTruthy();
    expect(screen.queryByText("0.00")).toBeNull();
  });
  it("NOT_COMPUTABLE reasons remain visible", async () => {
    const query = vi.fn().mockResolvedValue({
      status: "NOT_COMPUTABLE",
      reason_codes: ["CURRENCY_MISMATCH"],
      pv: null,
      ev: null,
      ac: null,
      cpi: null,
      spi: null,
      earned_lines: [],
    });
    render(<EvmPanel {...props({ query })} bundleId="40" setBundleId={vi.fn()} />);
    expect(await screen.findByText("Resultado EVM: NOT_COMPUTABLE")).toBeTruthy();
    expect(screen.getByText("CURRENCY_MISMATCH")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Publicar snapshot EVM" })).toBeDisabled();
  });
  it("EVM reader cannot publish a snapshot", async () => {
    const query = vi.fn().mockResolvedValue({
      status: "COMPUTABLE",
      pv: "60",
      ev: "50",
      ac: "25",
      cpi: "2",
      spi: "0.83333333",
      currency: "USD",
      earned_lines: [],
    });
    render(
      <EvmPanel {...props({ query, can: (action) => action === "evm.view" })} bundleId="40" setBundleId={vi.fn()} />
    );
    await screen.findByText("Resultado EVM: COMPUTABLE");
    expect(screen.queryByRole("button", { name: "Publicar snapshot EVM" })).toBeNull();
  });
  it("Schedule and Cost projections remain distinct from physical", async () => {
    const p = props({
      query: vi
        .fn()
        .mockResolvedValue({ items: [], authority: "SCHEDULE_READ_PROJECTION", physical_progress_automatic: false }),
    });
    render(<ProjectionPanel {...p} kind="SCHEDULE" />);
    expect(await screen.findByText("SCHEDULE_READ_PROJECTION")).toBeTruthy();
    expect(screen.getByText(/P6 % Complete ≠ Physical Progress/)).toBeTruthy();
  });
  it("4D comparison renders planned and approved semantic states separately", async () => {
    const query = vi.fn().mockResolvedValue({
      authority: {
        schedule_state: "EXISTING_FOUR_D_MODEL",
        physical_state: "APPROVED_PROGRESS_ONLY",
        ifc_mutated: false,
        schedule_mutated: false,
      },
      items: [
        {
          scope_item_id: 1,
          scope_nature: "REMOVE",
          schedule_state: "IN_PROGRESS",
          schedule_semantic_state: "REMOVAL",
          approved_physical_state: { state: "REMOVED", progress_value: "100" },
        },
      ],
    });
    render(<OverlayPanel {...props({ query })} bundleId="40" setBundleId={vi.fn()} />);
    expect(await screen.findByText("REMOVAL")).toBeTruthy();
    expect(screen.getByText("REMOVED · 100 %")).toBeTruthy();
  });
  it("aggregation exposes explicit control levels and weighting evidence", async () => {
    render(<AggregationPanel {...props()} />);
    await screen.findByRole("table", { name: "Approved progress aggregation" });
    expect(screen.getByLabelText("Aggregation Level")).toBeTruthy();
    expect(screen.getByRole("option", { name: "CONTROL_ACCOUNT" })).toBeTruthy();
    expect(screen.getByText(/READY y RELEASED no representan/)).toBeTruthy();
  });
});
describe("Progress presentation helpers", () => {
  it("retains zero percent and distinguishes missing progress", () => {
    expect(percentage("0")).toBe("0 %");
    expect(percentage(null)).toBe("No disponible");
  });
  it("encodes explicit query values without dropping zero", () => {
    expect(parameters({ as_of: "2026-10-22", period_id: 20, empty: "", zero: 0 })).toBe(
      "as_of=2026-10-22&period_id=20&zero=0"
    );
  });
  it("guards collection and object readers", () => {
    expect(rows([{}, null, "x", []])).toEqual([{}]);
    expect(object([])).toEqual({});
  });
  it("keeps native revision and renders structured evidence readably", () => {
    expect(revision({ version: 4, revision: 2 })).toBe(4);
    expect(display({ period: "OPEN" })).toBe("period: OPEN");
  });
});
