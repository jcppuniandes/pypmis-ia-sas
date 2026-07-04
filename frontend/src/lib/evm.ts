import type { ActivitySheetRow, ControlSnapshot, CostSheetLine, KPI } from "../types";

export type EvmRatio = number | null;

export type ProjectEvm = {
  pv: number;
  ev: number;
  ac: number;
  spi: EvmRatio;
  cpi: EvmRatio;
  sv: number;
  cv: number;
  bac: number;
  eac: number;
  etc: number;
  vac: number;
};

export type EvmCurvePoint = {
  date: string;
  period: string;
  timestamp: number;
  PV: number;
  EV: number | null;
  AC: number | null;
};

export type EvmBuildOptions = {
  baselineOnly?: boolean;
};

function money(value: number | null | undefined) {
  return Number.isFinite(value) ? Number(value) : 0;
}

function round(value: number, precision = 2) {
  const factor = 10 ** precision;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

function parseScheduleDate(value: string | null | undefined) {
  if (!value) return null;
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return null;
  return new Date(Date.UTC(year, month - 1, day));
}

function dateKey(date: Date) {
  return date.toISOString().slice(0, 10);
}

function previousUtcDay(date: Date) {
  return new Date(date.getTime() - 86_400_000);
}

function dayDiff(start: Date, finish: Date) {
  return Math.round((finish.getTime() - start.getTime()) / 86_400_000);
}

function activityCost(row: ActivitySheetRow) {
  return money(row.planned_cost) || money(row.planned_value);
}

function totalActivityBudget(rows: ActivitySheetRow[]) {
  return round(rows.reduce((total, row) => total + activityCost(row), 0));
}

function cumulativePlannedValueAt(rows: ActivitySheetRow[], asOfDate: Date) {
  return rows.reduce((total, row) => {
    const cost = activityCost(row);
    const start = parseScheduleDate(row.planned_start);
    const finish = parseScheduleDate(row.planned_finish);
    if (!cost || !start || !finish) return total;
    if (asOfDate < start) return total;
    if (asOfDate >= finish) return total + cost;

    const durationDays = Math.max(dayDiff(start, finish) + 1, 1);
    const elapsedDays = Math.max(dayDiff(start, asOfDate) + 1, 0);
    return total + cost * Math.min(elapsedDays / durationDays, 1);
  }, 0);
}

function plannedCurveFromActivities(
  rows: ActivitySheetRow[],
  currentEvm: Pick<ProjectEvm, "pv" | "ev" | "ac">,
  dataDate?: string | null,
  options: EvmBuildOptions = {}
) {
  const datedRows = rows.filter(
    (row) => activityCost(row) > 0 && parseScheduleDate(row.planned_start) && parseScheduleDate(row.planned_finish)
  );
  if (!datedRows.length) return [];

  const starts = datedRows
    .map((row) => parseScheduleDate(row.planned_start))
    .filter((date): date is Date => Boolean(date));
  const finishes = datedRows
    .map((row) => parseScheduleDate(row.planned_finish))
    .filter((date): date is Date => Boolean(date));
  const firstStart = new Date(Math.min(...starts.map((date) => date.getTime())));
  const lastFinish = new Date(Math.max(...finishes.map((date) => date.getTime())));
  const dates = new Map<string, Date>();
  const currentDataDate = parseScheduleDate(dataDate);
  const initialPoint = previousUtcDay(firstStart);

  dates.set(dateKey(initialPoint), initialPoint);

  if (!options.baselineOnly && currentDataDate && currentDataDate >= firstStart && currentDataDate <= lastFinish) {
    dates.set(dateKey(currentDataDate), currentDataDate);
  }

  for (
    let cursor = new Date(Date.UTC(firstStart.getUTCFullYear(), firstStart.getUTCMonth() + 1, 0));
    cursor <= lastFinish;
    cursor = new Date(Date.UTC(cursor.getUTCFullYear(), cursor.getUTCMonth() + 2, 0))
  ) {
    const cappedCursor = cursor > lastFinish ? lastFinish : cursor;
    dates.set(dateKey(cappedCursor), cappedCursor);
  }
  dates.set(dateKey(lastFinish), lastFinish);

  return [...dates.values()]
    .sort((first, second) => first.getTime() - second.getTime())
    .map((date) => {
      const isInitialPoint = date.getTime() === initialPoint.getTime();
      const isCurrentPoint = Boolean(currentDataDate && dateKey(date) === dateKey(currentDataDate));
      const isFuturePoint = Boolean(currentDataDate && date > currentDataDate);
      return {
        date: dateKey(date),
        period: dateKey(date),
        timestamp: date.getTime(),
        PV: isInitialPoint ? 0 : round(cumulativePlannedValueAt(datedRows, date)),
        EV: options.baselineOnly
          ? null
          : isInitialPoint
            ? 0
            : isFuturePoint
              ? null
              : isCurrentPoint
                ? round(currentEvm.ev)
                : null,
        AC: options.baselineOnly
          ? null
          : isInitialPoint
            ? 0
            : isFuturePoint
              ? null
              : isCurrentPoint
                ? round(currentEvm.ac)
                : null,
      };
    });
}

export function safeEvmRatio(numerator: number, denominator: number): EvmRatio {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator <= 0) return null;
  return round(numerator / denominator, 3);
}

export function formatEvmRatio(value: EvmRatio) {
  return value === null ? "N/A" : value.toFixed(3);
}

function costSheetTotals(costLines: CostSheetLine[]) {
  return costLines.reduce(
    (totals, line) => {
      const certificateActual =
        money(line.incurred_payment_certificate_value) + money(line.incurred_warehouse_receipt_value);
      const actual = money(line.actual_cost) || certificateActual;
      totals.pv += money(line.planned_value);
      totals.ev += money(line.earned_value);
      totals.ac += actual;
      totals.bac += money(line.bac);
      return totals;
    },
    { pv: 0, ev: 0, ac: 0, bac: 0 }
  );
}

export function deriveProjectEvm(
  projectKpi: KPI,
  costLines: CostSheetLine[] = [],
  activityRows: ActivitySheetRow[] = [],
  dataDate?: string | null,
  options: EvmBuildOptions = {}
): ProjectEvm {
  const totals = costSheetTotals(costLines);
  const hasCostLineEvidence = costLines.length > 0 && Object.values(totals).some((value) => value > 0);
  const asOfDate = parseScheduleDate(dataDate);
  const activityBac = totalActivityBudget(activityRows);
  const activityPv = asOfDate ? cumulativePlannedValueAt(activityRows, asOfDate) : 0;

  const pv = options.baselineOnly
    ? 0
    : hasCostLineEvidence && totals.pv > 0
      ? totals.pv
      : activityPv || money(projectKpi.pv);
  const ev = options.baselineOnly ? 0 : hasCostLineEvidence && totals.ev > 0 ? totals.ev : money(projectKpi.ev);
  const ac = options.baselineOnly ? 0 : hasCostLineEvidence && totals.ac > 0 ? totals.ac : money(projectKpi.ac);
  const bac = activityBac || (hasCostLineEvidence && totals.bac > 0 ? totals.bac : money(projectKpi.bac));
  const spi = safeEvmRatio(ev, pv);
  const cpi = safeEvmRatio(ev, ac);
  const sv = round(ev - pv);
  const cv = round(ev - ac);
  const remainingBudget = Math.max(bac - ev, 0);
  const eac = cpi && cpi > 0 ? round(ac + remainingBudget / cpi) : round(ac + remainingBudget);
  const etc = round(Math.max(eac - ac, 0));
  const vac = round(bac - eac);

  return {
    pv: round(pv),
    ev: round(ev),
    ac: round(ac),
    spi,
    cpi,
    sv,
    cv,
    bac: round(bac),
    eac,
    etc,
    vac,
  };
}

function snapshotSortValue(snapshot: ControlSnapshot, fallbackIndex: number) {
  const date = snapshot.data_date ?? snapshot.created_at;
  if (date) {
    const time = new Date(date).getTime();
    if (Number.isFinite(time)) return time;
  }
  return fallbackIndex;
}

function samePoint(point: EvmCurvePoint, evm: Pick<ProjectEvm, "pv" | "ev" | "ac">) {
  return point.PV === round(evm.pv) && point.EV === round(evm.ev) && point.AC === round(evm.ac);
}

export function buildCumulativeEvmCurve(
  snapshots: ControlSnapshot[],
  currentEvm: Pick<ProjectEvm, "pv" | "ev" | "ac">,
  activityRows: ActivitySheetRow[] = [],
  dataDate?: string | null,
  options: EvmBuildOptions = {}
) {
  const plannedCurve = plannedCurveFromActivities(activityRows, currentEvm, dataDate, options);
  if (plannedCurve.length) return plannedCurve;

  const projectSnapshots = snapshots.filter((snapshot) => snapshot.control_account_id === null);
  const source = projectSnapshots.length ? projectSnapshots : snapshots;
  const points = source
    .map((snapshot, index) => ({ snapshot, sortValue: snapshotSortValue(snapshot, index) }))
    .sort((first, second) => first.sortValue - second.sortValue)
    .map(({ snapshot, sortValue }) => {
      const snapshotDate = snapshot.data_date || new Date(sortValue).toISOString().slice(0, 10);
      return {
        date: snapshotDate,
        period: snapshot.period_label || snapshotDate,
        timestamp: Number.isFinite(sortValue) ? sortValue : new Date(snapshotDate).getTime(),
        PV: round(snapshot.pv),
        EV: round(snapshot.ev),
        AC: round(snapshot.ac),
      };
    });

  if (!points.some((point) => samePoint(point, currentEvm))) {
    const currentDate = dataDate || new Date().toISOString().slice(0, 10);
    points.push({
      date: currentDate,
      period: currentDate,
      timestamp: parseScheduleDate(currentDate)?.getTime() ?? Date.now(),
      PV: round(currentEvm.pv),
      EV: round(currentEvm.ev),
      AC: round(currentEvm.ac),
    });
  }

  return points.length
    ? points
    : [
        {
          date: dataDate || new Date().toISOString().slice(0, 10),
          period: dataDate || new Date().toISOString().slice(0, 10),
          timestamp: parseScheduleDate(dataDate)?.getTime() ?? Date.now(),
          PV: round(currentEvm.pv),
          EV: round(currentEvm.ev),
          AC: round(currentEvm.ac),
        },
      ];
}
