import { describe, expect, it } from "vitest";
import {
  buildCumulativeEvmCurve,
  deriveProjectEvm,
  formatEvmRatio,
} from "../src/lib/evm";
import type { ActivitySheetRow, ControlSnapshot, CostSheetLine, KPI } from "../src/types";

const emptyKpi: KPI = {
  control_account_id: null,
  pv: 0,
  ev: 0,
  ac: 0,
  spi: 0,
  cpi: 0,
  sv: 0,
  cv: 0,
  bac: 0,
  eac: 0,
  etc: 0,
  vac: 0,
};

function costLine(overrides: Partial<CostSheetLine>): CostSheetLine {
  return {
    control_account_id: 1,
    control_account_code: "CA-001",
    control_account_name: "Control account",
    cbs_code: "CBS-001",
    bac: 0,
    planned_value: 0,
    actual_cost: 0,
    incurred_payment_certificate_value: 0,
    incurred_warehouse_receipt_value: 0,
    committed_contract_value: 0,
    committed_purchase_order_value: 0,
    committed_cost: 0,
    earned_value: 0,
    variance: 0,
    cpi: 0,
    ...overrides,
  };
}

function projectSnapshot(overrides: Partial<ControlSnapshot>): ControlSnapshot {
  return {
    id: 1,
    control_account_id: null,
    period_label: "Current",
    data_date: null,
    pv: 0,
    ev: 0,
    ac: 0,
    spi: 0,
    cpi: 0,
    sv: 0,
    cv: 0,
    bac: 0,
    eac: 0,
    etc: 0,
    vac: 0,
    productivity_index: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function activityRow(overrides: Partial<ActivitySheetRow>): ActivitySheetRow {
  return {
    id: 1,
    activity_sheet_id: 1,
    external_activity_id: "A1000",
    wbs_code: "WBS-001",
    activity_name: "Activity",
    planned_start: "2026-01-01",
    planned_finish: "2026-01-10",
    total_float_days: 0,
    critical_path: true,
    planned_cost: 0,
    planned_value: 0,
    planned_percent: 0,
    cbs_code: "",
    control_account_id: null,
    control_account_code: "",
    mapping_status: "mapped",
    review_note: "",
    ...overrides,
  };
}

describe("dashboard EVM helpers", () => {
  it("derives project PV, EV, AC and ratios from control cost lines when stored project KPI is incomplete", () => {
    const result = deriveProjectEvm(emptyKpi, [
      costLine({ bac: 1000, planned_value: 600, earned_value: 300, actual_cost: 250 }),
      costLine({ bac: 500, planned_value: 200, earned_value: 100, actual_cost: 150 }),
    ]);

    expect(result.pv).toBe(800);
    expect(result.ev).toBe(400);
    expect(result.ac).toBe(400);
    expect(result.bac).toBe(1500);
    expect(result.spi).toBe(0.5);
    expect(result.cpi).toBe(1);
    expect(result.sv).toBe(-400);
    expect(result.cv).toBe(0);
  });

  it("does not present missing EVM denominators as zero performance", () => {
    const result = deriveProjectEvm({ ...emptyKpi, ev: 100, pv: 0, ac: 0 }, []);

    expect(result.spi).toBeNull();
    expect(result.cpi).toBeNull();
    expect(formatEvmRatio(result.spi)).toBe("N/A");
    expect(formatEvmRatio(result.cpi)).toBe("N/A");
  });

  it("derives current PV from activity dates and planned cost when cost sheet planned value is missing", () => {
    const result = deriveProjectEvm(
      { ...emptyKpi, bac: 2000 },
      [costLine({ bac: 2000, planned_value: 0, earned_value: 0, actual_cost: 100 })],
      [activityRow({ planned_cost: 1000, planned_start: "2026-01-01", planned_finish: "2026-01-10" })],
      "2026-01-05",
    );

    expect(result.pv).toBe(500);
    expect(result.bac).toBe(1000);
    expect(result.spi).toBe(0);
    expect(result.eac).toBe(1100);
    expect(result.vac).toBe(-100);
  });

  it("keeps PV, EV and AC at zero when the project only has a baseline and no control cut", () => {
    const result = deriveProjectEvm(
      { ...emptyKpi, bac: 2000 },
      [costLine({ bac: 2000, planned_value: 0, earned_value: 0, actual_cost: 100 })],
      [activityRow({ planned_cost: 1000, planned_start: "2026-01-01", planned_finish: "2026-01-10" })],
      "2026-01-05",
      { baselineOnly: true },
    );

    expect(result.pv).toBe(0);
    expect(result.ev).toBe(0);
    expect(result.ac).toBe(0);
    expect(result.spi).toBeNull();
    expect(result.cpi).toBeNull();
    expect(result.bac).toBe(1000);
    expect(result.eac).toBe(1000);
    expect(result.vac).toBe(0);
  });

  it("uses activity BAC instead of duplicated control-account BAC when both are available", () => {
    const result = deriveProjectEvm(
      { ...emptyKpi, bac: 15400000 },
      [costLine({ bac: 15400000, planned_value: 0, earned_value: 0, actual_cost: 7750 })],
      [
        activityRow({ id: 1, planned_cost: 500000, planned_start: "2026-05-07", planned_finish: "2026-05-10" }),
        activityRow({ id: 2, planned_cost: 300000, planned_start: "2026-05-11", planned_finish: "2026-05-14" }),
        activityRow({ id: 3, planned_cost: 1000000, planned_start: "2026-05-11", planned_finish: "2026-05-14" }),
        activityRow({ id: 4, planned_cost: 300000, planned_start: "2026-08-13", planned_finish: "2026-08-16" }),
        activityRow({ id: 5, planned_cost: 600000, planned_start: "2026-05-15", planned_finish: "2026-05-18" }),
        activityRow({ id: 6, planned_cost: 2000000, planned_start: "2026-05-15", planned_finish: "2026-07-03" }),
        activityRow({ id: 7, planned_cost: 3000000, planned_start: "2026-06-04", planned_finish: "2026-08-12" }),
      ],
      "2026-05-07",
    );

    expect(result.bac).toBe(7700000);
    expect(result.eac).toBe(7707750);
    expect(result.vac).toBe(-7750);
  });

  it("orders the cumulative S curve by data date and appends the current project cut", () => {
    const curve = buildCumulativeEvmCurve(
      [
        projectSnapshot({
          id: 2,
          period_label: "Jun",
          data_date: "2026-06-30",
          pv: 300,
          ev: 210,
          ac: 190,
        }),
        projectSnapshot({
          id: 1,
          period_label: "May",
          data_date: "2026-05-31",
          pv: 100,
          ev: 80,
          ac: 70,
        }),
      ],
      {
        ...emptyKpi,
        pv: 450,
        ev: 400,
        ac: 390,
      },
    );

    expect(curve.map(({ period, PV, EV, AC }) => ({ period, PV, EV, AC }))).toEqual([
      { period: "May", PV: 100, EV: 80, AC: 70 },
      { period: "Jun", PV: 300, EV: 210, AC: 190 },
      { period: "2026-06-03", PV: 450, EV: 400, AC: 390 },
    ]);
  });

  it("builds a planned cumulative S curve from activity costs when snapshot PV is unavailable", () => {
    const curve = buildCumulativeEvmCurve(
      [],
      { pv: 500, ev: 0, ac: 100 },
      [
        activityRow({
          id: 1,
          planned_cost: 1000,
          planned_start: "2026-01-01",
          planned_finish: "2026-01-10",
        }),
        activityRow({
          id: 2,
          planned_cost: 2000,
          planned_start: "2026-02-01",
          planned_finish: "2026-02-10",
        }),
      ],
      "2026-01-05",
    );

    expect(curve.map(({ period, PV, EV, AC }) => ({ period, PV, EV, AC }))).toEqual([
      { period: "2025-12-31", PV: 0, EV: 0, AC: 0 },
      { period: "2026-01-05", PV: 500, EV: 0, AC: 100 },
      { period: "2026-01-31", PV: 1000, EV: null, AC: null },
      { period: "2026-02-10", PV: 3000, EV: null, AC: null },
    ]);
    expect(curve.every((point) => typeof point.timestamp === "number")).toBe(true);
  });

  it("shows only the baseline S curve when no control cut has been captured", () => {
    const curve = buildCumulativeEvmCurve(
      [],
      { pv: 0, ev: 0, ac: 0 },
      [
        activityRow({
          id: 1,
          planned_cost: 1000,
          planned_start: "2026-01-01",
          planned_finish: "2026-01-10",
        }),
      ],
      "2026-01-05",
      { baselineOnly: true },
    );

    expect(curve.map(({ period, PV, EV, AC }) => ({ period, PV, EV, AC }))).toEqual([
      { period: "2025-12-31", PV: 0, EV: null, AC: null },
      { period: "2026-01-10", PV: 1000, EV: null, AC: null },
    ]);
  });
});
