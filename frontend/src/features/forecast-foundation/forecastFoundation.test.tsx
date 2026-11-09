import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import GovernedProfilesAdminView from "../awp/GovernedProfilesAdminView";
import { governedProfilesApi } from "../awp/api";
import { forecastApi, forecastProjectRoot } from "./api";
import AssumptionsPanel from "./AssumptionsPanel";
import ComponentsPanel from "./ComponentsPanel";
import ForecastPerformanceWorkspace from "./ForecastPerformanceWorkspace";
import { CalculationPanel, CurvesPanel, PerformancePanel, TrendsPanel } from "./ReadPanels";
import { LookAheadPanel, ReportsPanel } from "./ReportingPanels";
import {
  draftFromVersion,
  emptyDraft,
  forecastTabs,
  type ForecastDraft,
  type ForecastEditorProps,
  type ForecastOverview,
  type ForecastPanelProps,
  type ForecastRecord,
} from "./types";

const actions = [
  "read",
  "create",
  "edit",
  "submit",
  "review",
  "approve",
  "assumption.edit",
  "etc.calculate",
  "eac.view",
  "dashboard.view",
  "executive.view",
  "lookahead.view",
  "report.read",
  "report.publish",
  "report.republish",
];
const draft: ForecastDraft = {
  ...emptyDraft(),
  code: "FC-1",
  name: "Controlled Forecast",
  bundle_id: 4,
  period_id: 2,
  as_of: "2026-11-06",
  schedule_version_id: 5,
  currency: "USD",
  confidence_rationale: "Owner corroborated basis",
  data_completeness: "ASSESSED",
  assumption_maturity: "CONFIRMED",
  evidence_ref: "FORECAST-EVIDENCE-1",
  assumptions: [
    {
      code: "RATE",
      name: "Remaining unit rate",
      kind: "RATE",
      value: "100",
      unit: "USD/m3",
      currency: "USD",
      source_reference: "APU-1",
      owner_id: 10,
      effective_date: "2026-11-06",
      confidence: "HIGH",
      status: "CONFIRMED",
      evidence_ref: "RATE-EVIDENCE",
      rationale: "Reviewed rate basis",
    },
  ],
};
const version: ForecastRecord = {
  id: 1,
  version: 2,
  revision: 1,
  code: "FC-1",
  name: "Controlled Forecast",
  status: "DRAFT",
  prepared_by: 10,
  period_id: 2,
  as_of: "2026-11-06",
  input_json: draft,
  result_json: {},
  content_hash: "forecast-frozen-hash",
};
const data: ForecastOverview = {
  context: {},
  configuration: {
    content_json: {
      lookahead: {
        default_horizon_days: 28,
        group_by: "PARENT_WBS",
        near_critical_threshold: { value: "40", unit: "HOUR" },
        exclude_milestones: true,
      },
    },
  },
  allowed_actions: actions,
  versions: [version],
  baseline_bundles: [{ id: 4, code: "BUNDLE", status: "APPROVED" }],
  periods: [{ id: 2, period_code: "NOV", status: "OPEN" }],
  schedule_versions: [{ id: 5, code: "CURRENT", status: "ACCEPTED_CURRENT" }],
  scope_items: [{ id: 6, scope_code: "SCOPE", name: "Install" }],
  plan_items: [],
  packages: [{ id: 8, package_code: "IWP", name: "Install" }],
  control_accounts: [],
  history: [],
};
function panel(overrides: Partial<ForecastPanelProps> = {}): ForecastPanelProps {
  return {
    data,
    selected: version,
    periodId: "2",
    asOf: "2026-11-06",
    busy: false,
    reason: "Controlled Forecast validation",
    query: vi.fn().mockResolvedValue({ items: [] }),
    command: vi.fn().mockResolvedValue(version),
    can: () => true,
    ...overrides,
  };
}
function editor(overrides: Partial<ForecastEditorProps> = {}): ForecastEditorProps {
  return { ...panel(), draft: structuredClone(draft), setDraft: vi.fn(), editable: true, ...overrides };
}
function change(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } });
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Forecast contracts and authority", () => {
  it("keeps dedicated Forecast, Performance and Reporting project roots", () => {
    expect(forecastProjectRoot(14)).toBe("/api/v1/forecast/projects/14");
    expect(forecastProjectRoot(14, "performance")).toBe("/api/v1/performance/projects/14");
    expect(forecastProjectRoot(14, "reporting")).toBe("/api/v1/reporting/projects/14");
  });
  it("creates independent empty draft collections", () => {
    const a = emptyDraft();
    a.assumptions.push(draft.assumptions[0]);
    expect(emptyDraft().assumptions).toEqual([]);
  });
  it("reconstructs only strict input fields and preserves declared decimal strings", () => {
    const result = draftFromVersion(version);
    expect(result).toEqual(draft);
    expect(result.assumptions[0].value).toBe("100");
    expect(result).not.toHaveProperty("id");
    expect(result).not.toHaveProperty("result_json");
  });
  it("opens twelve compact submodules with source separation", async () => {
    vi.spyOn(forecastApi, "overview").mockResolvedValue(data);
    render(<ForecastPerformanceWorkspace token="t" workspaceId={3} />);
    await screen.findByRole("navigation", { name: "Forecast & Performance submodules" });
    for (const name of forecastTabs) expect(screen.getByRole("button", { name })).toBeTruthy();
    expect(screen.getByText(/Baseline = referencia aprobada/)).toBeTruthy();
    expect(screen.getByText(/No hay cálculo CPM/)).toBeTruthy();
  });
  it("does not expose writes in archived mode", async () => {
    vi.spyOn(forecastApi, "overview").mockResolvedValue(data);
    render(<ForecastPerformanceWorkspace token="t" workspaceId={3} readOnly />);
    await screen.findByText("Workspace archivado · Forecast de solo lectura.");
    expect(screen.queryByRole("button", { name: "Crear Forecast DRAFT" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Nueva versión Forecast" })).toBeNull();
  });
  it("creates a governed version with explicit sources and no frontend result", async () => {
    vi.spyOn(forecastApi, "overview").mockResolvedValue(data);
    vi.spyOn(forecastApi, "command").mockResolvedValue(version);
    render(<ForecastPerformanceWorkspace token="t" workspaceId={3} />);
    await screen.findByRole("navigation", { name: "Forecast & Performance submodules" });
    change("Forecast Code", "FC-NEW");
    change("Forecast Name", "New governed projection");
    change("Forecast Baseline Bundle", "4");
    change("Forecast Period", "2");
    change("Forecast As-of", "2026-11-06");
    change("Forecast Accepted Schedule", "5");
    change("Forecast Currency", "USD");
    change("Forecast Confidence rationale", "Independent owner evidence");
    change("Forecast Evidence reference", "EVIDENCE");
    change("Motivo Forecast", "Controlled validation reason");
    fireEvent.click(screen.getByRole("button", { name: "Crear Forecast DRAFT" }));
    await waitFor(() => expect(forecastApi.command).toHaveBeenCalled());
    const args = vi.mocked(forecastApi.command).mock.calls[0];
    expect(args[2]).toBe("/versions");
    expect(args[3]).toMatchObject({
      code: "FC-NEW",
      bundle_id: 4,
      period_id: 2,
      as_of: "2026-11-06",
      currency: "USD",
      evidence_ref: "EVIDENCE",
    });
    expect(args[3]).not.toHaveProperty("eac");
    expect(args[4]).toBeTruthy();
  });
  it("requires save before calculating a locally changed draft", async () => {
    vi.spyOn(forecastApi, "overview").mockResolvedValue(data);
    vi.spyOn(forecastApi, "query").mockResolvedValue(version);
    render(<ForecastPerformanceWorkspace token="t" workspaceId={3} />);
    await screen.findByLabelText("Forecast Version");
    change("Forecast Version", "1");
    await waitFor(() =>
      expect((screen.getByLabelText("Forecast Name") as HTMLInputElement).value).toBe("Controlled Forecast")
    );
    change("Motivo Forecast", "Controlled change reason");
    change("Forecast Name", "Updated local title");
    expect((screen.getByRole("button", { name: "Calcular ETC y EAC" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Cambios locales pendientes/)).toBeTruthy();
  });
});

describe("Typed assumptions and components", () => {
  it("records owner, effective date, source and evidence without persisting until version save", () => {
    const props = editor();
    render(<AssumptionsPanel {...props} />);
    change("Assumption Code", "PROD");
    change("Assumption Name", "Productivity basis");
    change("Assumption Kind", "PRODUCTIVITY");
    change("Assumption Value", "0.2");
    change("Assumption Unit", "m3/day");
    change("Assumption Source reference", "FIELD-STUDY");
    change("Assumption Owner ID", "10");
    change("Assumption Effective date", "2026-11-06");
    change("Assumption Evidence reference", "STUDY-1");
    change("Assumption Rationale", "Observed productivity record");
    fireEvent.click(screen.getByRole("button", { name: "Añadir hipótesis al borrador" }));
    expect(props.setDraft).toHaveBeenCalledWith(
      expect.objectContaining({
        assumptions: expect.arrayContaining([
          expect.objectContaining({ code: "PROD", value: "0.2", owner_id: 10, currency: null }),
        ]),
      })
    );
    expect(props.command).not.toHaveBeenCalled();
  });
  it("rejects duplicate assumption codes", () => {
    const props = editor();
    render(<AssumptionsPanel {...props} />);
    change("Assumption Code", "RATE");
    change("Assumption Owner ID", "10");
    fireEvent.submit(screen.getByRole("button", { name: "Añadir hipótesis al borrador" }).closest("form")!);
    expect(screen.getByRole("alert").textContent).toContain("ya existe");
    expect(props.setDraft).not.toHaveBeenCalled();
  });
  it("does not edit assumptions without the granular duty", () => {
    render(<AssumptionsPanel {...editor({ can: (action) => action !== "assumption.edit" })} />);
    expect((screen.getByLabelText("Assumption Value") as HTMLInputElement).disabled).toBe(true);
  });
  it("declares a quantity-rate component rather than computing ETC in the UI", () => {
    const props = editor();
    render(<ComponentsPanel {...props} family="cost_items" />);
    change("Cost Forecast Components Code", "ETC-1");
    change("Cost Forecast Components Name", "Remaining installed work");
    change("Cost Forecast Components Method", "QUANTITY_RATE");
    change("Cost Forecast Components Scope", "6");
    change("Cost Forecast Components Currency", "USD");
    change("Cost Forecast Components Unit", "m3");
    change("Cost Forecast Components Rate assumption", "RATE");
    fireEvent.click(screen.getByRole("button", { name: "Añadir componente al borrador" }));
    expect(props.setDraft).toHaveBeenCalledWith(
      expect.objectContaining({
        cost_items: [
          expect.objectContaining({
            method: "QUANTITY_RATE",
            scope_item_id: 6,
            assumption_codes: ["RATE"],
            inputs: { cost_bucket: "UNCOMMITTED", rate_assumption_code: "RATE" },
          }),
        ],
      })
    );
    expect(props.command).not.toHaveBeenCalled();
  });
  it("rejects invalid commitment reference IDs", () => {
    const props = editor();
    render(<ComponentsPanel {...props} family="cost_items" />);
    change("Cost Forecast Components Code", "C");
    change("Cost Forecast Components Name", "Commitment");
    change("Cost Forecast Components Commitment IDs", "4,bad");
    fireEvent.click(screen.getByRole("button", { name: "Añadir componente al borrador" }));
    expect(screen.getByRole("alert").textContent).toContain("identificadores positivos");
    expect(props.setDraft).not.toHaveBeenCalled();
  });
  it("keeps Forecast cost spread explicit and separate from Cost Baseline", () => {
    const props = editor();
    render(<ComponentsPanel {...props} family="cost_items" />);
    change("Cost Forecast Components Code", "C");
    change("Cost Forecast Components Name", "Remaining cost");
    change("Cost Forecast Components Phase date", "2026-11-20");
    change("Cost Forecast Components Phase amount", "60");
    fireEvent.click(screen.getByRole("button", { name: "Añadir fecha Forecast" }));
    fireEvent.click(screen.getByRole("button", { name: "Añadir componente al borrador" }));
    expect(props.setDraft).toHaveBeenCalledWith(
      expect.objectContaining({
        cost_items: [
          expect.objectContaining({
            inputs: { cost_bucket: "UNCOMMITTED", phasing: [{ date: "2026-11-20", amount: "60" }] },
          }),
        ],
      })
    );
  });
  it("persists the displayed resource type and productivity basis explicitly", () => {
    const props = editor();
    render(<ComponentsPanel {...props} family="resource_items" />);
    change("Resource Forecast Components Code", "LABOR");
    change("Resource Forecast Components Name", "Remaining labor");
    fireEvent.click(screen.getByRole("button", { name: "Añadir componente al borrador" }));
    expect(props.setDraft).toHaveBeenCalledWith(
      expect.objectContaining({
        resource_items: [
          expect.objectContaining({ inputs: { resource_type: "LABOR", productivity_basis: "QUANTITY_PER_DAY" } }),
        ],
      })
    );
  });
});

describe("Read-only performance and reporting", () => {
  it("preserves NOT_COMPUTABLE and reasons without plausible numeric zero", async () => {
    render(
      <CalculationPanel
        {...panel({
          query: vi.fn().mockResolvedValue({
            status: "NOT_COMPUTABLE",
            cost: { status: "NOT_COMPUTABLE", eac: null, etc: null, reason_codes: ["CURRENCY_MISMATCH"] },
          }),
        })}
        kind="cost"
      />
    );
    await screen.findByText("CURRENCY_MISMATCH");
    expect(screen.getByText("NOT_COMPUTABLE")).toBeTruthy();
    expect(screen.queryByText("0.00")).toBeNull();
  });
  it("shows separate time baseline/current/forecast values and no local CPM", async () => {
    render(
      <CalculationPanel
        {...panel({
          query: vi.fn().mockResolvedValue({
            time: {
              status: "COMPUTABLE",
              baseline_finish: "2026-11-20",
              current_finish: "2026-11-22",
              forecast_finish: "2026-11-24",
              items: [],
            },
          }),
        })}
        kind="time"
      />
    );
    await screen.findByText("2026-11-24");
    expect(screen.getByText("2026-11-20")).toBeTruthy();
    expect(screen.getByText("2026-11-22")).toBeTruthy();
  });
  it("does not request executive data without the executive duty", () => {
    const props = panel({ can: () => false });
    render(<PerformancePanel {...props} kind="executive" />);
    expect(props.query).not.toHaveBeenCalled();
    expect(screen.getByText("Sin permiso para consultar esta vista.")).toBeTruthy();
  });
  it("shows read-model values with authority references", async () => {
    const props = panel({
      query: vi.fn().mockResolvedValue({
        status: "COMPUTABLE",
        project_status: "ACTIVE",
        currency: "USD",
        metrics: { eac: "85", vac: "35", physical_progress: "50" },
        dashboard_indicators: [
          { metric: "cpi", value: "0.9", threshold: "1.25", unit: "RATIO", warning_when: "BELOW", status: "WARNING" },
          {
            metric: "spi",
            value: null,
            threshold: "1",
            unit: "RATIO",
            warning_when: "BELOW",
            status: "NOT_COMPUTABLE",
            reason_codes: ["DASHBOARD_SOURCE_METRIC_REQUIRED"],
          },
        ],
        source_refs: { forecast: 1 },
        narratives: [{ section: "COST", text: "EAC from approved Forecast", fact_references: ["metrics.eac"] }],
      }),
    });
    render(<PerformancePanel {...props} kind="dashboard" />);
    await screen.findByText("85");
    expect(props.query).toHaveBeenCalledWith(expect.stringContaining("/dashboard?"), "performance");
    expect(screen.getByText("EAC from approved Forecast")).toBeTruthy();
    expect(screen.getByText("ACTIVE")).toBeTruthy();
    const indicators = screen.getByRole("table", { name: "Project Controls Dashboard Threshold Indicators" });
    expect(indicators.textContent).toContain("1.25");
    expect(indicators.textContent).toContain("WARNING");
    expect(indicators.textContent).toContain("NOT_COMPUTABLE");
    expect(indicators.textContent).toContain("DASHBOARD_SOURCE_METRIC_REQUIRED");
    expect(props.command).not.toHaveBeenCalled();
  });
  it("keeps explicit variance bases and incompatible physical progress visible", async () => {
    const props = panel({
      query: vi.fn().mockResolvedValue({
        status: "COMPUTABLE",
        metrics: {},
        items: [
          { metric: "FINISH", baseline: "2026-11-15", current: "2026-11-19", forecast: "2026-11-21", variance: 6 },
        ],
        progress_variances: {
          physical_variance: null,
          status: "NOT_COMPUTABLE",
          reason_codes: ["COMPATIBLE_PLANNED_PHYSICAL_CURVE_REQUIRED"],
        },
      }),
    });
    render(<PerformancePanel {...props} kind="variance" />);
    const comparison = await screen.findByRole("table", { name: "Governed Variance Comparison" });
    expect(comparison.textContent).toContain("2026-11-15");
    expect(comparison.textContent).toContain("2026-11-19");
    expect(comparison.textContent).toContain("2026-11-21");
    expect(screen.getByText("COMPATIBLE_PLANNED_PHYSICAL_CURVE_REQUIRED")).toBeTruthy();
    expect(props.command).not.toHaveBeenCalled();
  });
  it("uses published report rows for trends without mutating history", async () => {
    const props = panel({
      query: vi.fn().mockResolvedValue({
        items: [{ id: 1, period_id: 2, metrics_json: { eac: "85", spi: "0.875" }, revision: 1 }],
        series: [{ metric: "spi", unit: "RATIO", status: "COMPUTABLE" }],
      }),
    });
    render(<TrendsPanel {...props} />);
    await screen.findByText("0.875");
    expect(screen.queryByText("85")).toBeNull();
    expect(props.query).toHaveBeenCalledWith("/trends?forecast_version_id=1", "performance");
    expect(props.command).not.toHaveBeenCalled();
  });
  it("renders compatible curves separately with backend points", async () => {
    render(
      <CurvesPanel
        {...panel({
          query: vi.fn().mockResolvedValue({
            series: [
              {
                code: "PLANNED_VALUE",
                unit: "USD",
                currency: "USD",
                status: "COMPUTABLE",
                points: [
                  { date: "2026-11-06", period_value: "10", cumulative_value: "10" },
                  { date: "2026-11-20", period_value: "20", cumulative_value: "30" },
                ],
              },
            ],
          }),
        })}
      />
    );
    await screen.findByRole("img", { name: "PLANNED_VALUE S-Curve USD" });
    expect(screen.getByRole("table", { name: "PLANNED_VALUE Curve Points" })).toBeTruthy();
  });
  it("does not draw missing curve values as zero", async () => {
    render(
      <CurvesPanel
        {...panel({
          query: vi.fn().mockResolvedValue({
            series: [
              {
                code: "FORECAST_COST",
                status: "NOT_COMPUTABLE",
                reason_codes: ["FORECAST_PHASING_REQUIRED"],
                points: [{ date: "2026-11-06", cumulative_value: null }],
              },
            ],
          }),
        })}
      />
    );
    await screen.findByText("FORECAST_PHASING_REQUIRED");
    expect(screen.queryByRole("img")).toBeNull();
  });
  it("draws one observed point without inventing a second date", async () => {
    render(
      <CurvesPanel
        {...panel({
          query: vi.fn().mockResolvedValue({
            series: [
              {
                code: "ACTUAL_COST",
                unit: "MONEY",
                currency: "USD",
                status: "COMPUTABLE",
                points: [{ date: "2026-11-06", cumulative_value: "25" }],
              },
            ],
          }),
        })}
      />
    );
    const graph = await screen.findByRole("img", { name: "ACTUAL_COST S-Curve USD" });
    expect(graph.querySelectorAll("circle")).toHaveLength(1);
    expect(graph.querySelector("polyline")).toBeNull();
  });
  it("runs a four-week Look-Ahead with explicit float unit and no default Top N", async () => {
    const props = panel();
    render(<LookAheadPanel {...props} />);
    expect((screen.getByLabelText("Look-Ahead Horizon days") as HTMLInputElement).value).toBe("28");
    fireEvent.click(screen.getByRole("button", { name: "Ejecutar Look-Ahead" }));
    await waitFor(() => expect(props.query).toHaveBeenCalled());
    const call = vi.mocked(props.query).mock.calls[0];
    expect(call[0]).toContain("horizon_days=28");
    expect(call[0]).toContain("near_critical_unit=HOUR");
    expect(call[0]).not.toContain("top_n=");
    expect(call[1]).toBe("performance");
    expect(props.command).not.toHaveBeenCalled();
  });
  it("applies custom horizon/grouping/filter while preserving UNKNOWN driver", async () => {
    const props = panel({
      query: vi.fn().mockResolvedValue({
        status: "COMPUTABLE",
        horizon_days: 14,
        items: [
          {
            activity_external_id: "A1",
            driving_predecessor: {
              state: "UNKNOWN",
              drivers: [],
              predecessors: [{ predecessor_external_id: "P1", relationship_type: "FS", lag: "2", lag_unit: "HOUR" }],
            },
            critical: true,
            readiness: "BLOCKED",
            constraints: ["ACCESS"],
          },
        ],
      }),
    });
    render(<LookAheadPanel {...props} />);
    change("Look-Ahead Horizon days", "14");
    change("Look-Ahead Group by", "PACKAGE");
    change("Look-Ahead Work Package", "8");
    fireEvent.click(screen.getByRole("button", { name: "Ejecutar Look-Ahead" }));
    await screen.findByText("UNKNOWN");
    expect(props.query).toHaveBeenCalledWith(expect.stringContaining("horizon_days=14"), "performance");
    expect(screen.getByText("BLOCKED")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Look-Ahead Imported Relationships" }).textContent).toContain("P1");
    expect(screen.getByRole("table", { name: "Look-Ahead Imported Relationships" }).textContent).toContain("HOUR");
  });
  it("maps canonical imported activity and group keys without inventing source facts", async () => {
    const props = panel({
      query: vi.fn().mockResolvedValue({
        status: "COMPUTABLE",
        items: [
          { external_id: "P6-5001", finish: "2026-11-20", driving_predecessor: { state: "UNKNOWN", predecessors: [] } },
        ],
        groups: [{ key: "PARENT-1", activity_count: 1, activity_ids: ["P6-5001"] }],
      }),
    });
    render(<LookAheadPanel {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Ejecutar Look-Ahead" }));
    await screen.findByText("PARENT-1");
    expect(screen.getByRole("table", { name: "Look-Ahead Activities" }).textContent).toContain("P6-5001");
    expect(screen.getByRole("table", { name: "Look-Ahead Activities" }).textContent).toContain("2026-11-20");
    expect(props.command).not.toHaveBeenCalled();
  });
  it("saves a Look-Ahead snapshot only through an explicit authorized command", async () => {
    const props = panel({ query: vi.fn().mockResolvedValue({ status: "COMPUTABLE", items: [] }) });
    render(<LookAheadPanel {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Ejecutar Look-Ahead" }));
    await screen.findByRole("button", { name: "Guardar snapshot Look-Ahead" });
    expect(props.command).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Guardar snapshot Look-Ahead" }));
    await waitFor(() =>
      expect(props.command).toHaveBeenCalledWith(
        "/lookahead/snapshots",
        expect.objectContaining({
          forecast_version_id: 1,
          horizon_days: 28,
          reason: props.reason,
          near_critical_unit: "HOUR",
        }),
        undefined,
        "POST",
        "performance"
      )
    );
  });
  it("does not carry a Look-Ahead result into another selected version", async () => {
    const props = panel({ query: vi.fn().mockResolvedValue({ items: [{ activity_external_id: "OLD-ACTIVITY" }] }) });
    const view = render(<LookAheadPanel {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Ejecutar Look-Ahead" }));
    await screen.findByText("OLD-ACTIVITY");
    view.rerender(<LookAheadPanel {...props} selected={{ ...version, id: 99 }} />);
    expect(screen.queryByText("OLD-ACTIVITY")).toBeNull();
  });
  it("publishes a report only by explicit command with reason/evidence", async () => {
    const props = panel({ selected: { ...version, status: "APPROVED" } });
    render(<ReportsPanel {...props} />);
    change("Report Evidence reference", "REPORT-EVIDENCE");
    fireEvent.click(screen.getByRole("button", { name: "Publicar reporte del período" }));
    await waitFor(() =>
      expect(props.command).toHaveBeenCalledWith(
        "/reports",
        { forecast_version_id: 1, evidence_reference: "REPORT-EVIDENCE", reason: props.reason },
        undefined,
        "POST",
        "reporting"
      )
    );
  });
  it("keeps report publication disabled for a draft Forecast", async () => {
    const props = panel();
    render(<ReportsPanel {...props} />);
    await waitFor(() => expect(props.query).toHaveBeenCalledWith("/analytics-contract", "reporting"));
    expect((screen.getByRole("button", { name: "Publicar reporte del período" }) as HTMLButtonElement).disabled).toBe(
      true
    );
  });
  it("does not request report history without report-read duty", () => {
    const props = panel({ can: () => false });
    render(<ReportsPanel {...props} />);
    expect(props.query).not.toHaveBeenCalled();
  });
  it("shows the persisted actor and related Forecast in immutable audit rows", async () => {
    const props = panel({
      data: {
        ...data,
        history: [
          { event_type: "FORECAST_APPROVED", entity_type: "ForecastVersion", entity_id: 17, created_by: 51 },
          {
            event_type: "REPORT_PUBLISHED",
            entity_type: "ForecastReportSnapshot",
            entity_id: 32,
            created_by: 52,
            snapshot_json: { forecast_version_id: 17 },
          },
        ],
      },
    });
    render(<ReportsPanel {...props} />);
    await waitFor(() => expect(props.query).toHaveBeenCalledWith("/analytics-contract", "reporting"));
    const table = screen.getByRole("table", { name: "Forecast Audit History" });
    const records = Array.from(table.querySelectorAll("tbody tr")).map((row) =>
      Array.from(row.querySelectorAll("td")).map((cell) => cell.textContent)
    );
    expect(records[0].slice(0, 4)).toEqual(["FORECAST_APPROVED", "17", "—", "51"]);
    expect(records[1].slice(0, 4)).toEqual(["REPORT_PUBLISHED", "17", "—", "52"]);
  });
});

describe("Forecast ADMIN reuses independent profile publication", () => {
  it("uses the dedicated Forecast profile endpoint and requires a reason", async () => {
    vi.spyOn(governedProfilesApi, "list").mockResolvedValue({
      items: [],
      default_content: { allowed_methods: ["BOTTOM_UP"] },
      allowed_actions: ["admin.configure", "admin.publish"],
    });
    vi.spyOn(governedProfilesApi, "command").mockResolvedValue({
      id: 3,
      version: 1,
      revision: 1,
      code: "FCP",
      name: "Policy",
      status: "DRAFT",
      content_json: {},
    });
    render(<GovernedProfilesAdminView token="t" kind="forecast" />);
    await screen.findByLabelText("Forecast Profiles Code");
    expect(governedProfilesApi.list).toHaveBeenCalledWith("t", "/api/v1/forecast/admin/profiles");
    expect((screen.getByRole("button", { name: "Crear Forecast Profiles DRAFT" }) as HTMLButtonElement).disabled).toBe(
      true
    );
    change("Forecast Profiles Code", "FCP");
    change("Forecast Profiles Name", "Policy");
    change("Motivo Forecast Profiles", "Controlled policy reason");
    fireEvent.click(screen.getByRole("button", { name: "Crear Forecast Profiles DRAFT" }));
    await waitFor(() =>
      expect(governedProfilesApi.command).toHaveBeenCalledWith(
        "t",
        "/api/v1/forecast/admin/profiles",
        "",
        expect.objectContaining({ code: "FCP", reason: "Controlled policy reason" }),
        expect.any(String),
        undefined,
        "POST"
      )
    );
  });
});
