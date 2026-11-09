import { useCallback } from "react";
import { parameters } from "./api";
import { Evidence, Facts, ReasonCodes, Records } from "./Fields";
import { useForecastQuery } from "./useForecastQuery";
import { display, object, rows, text, type ForecastPanelProps, type ForecastRow } from "./types";

export function CalculationPanel(props: ForecastPanelProps & { kind: "cost" | "time" | "milestones" | "resources" }) {
  const title = {
    cost: "ETC / EAC",
    time: "Time Forecast",
    milestones: "Forecast Milestones",
    resources: "Resource Forecast",
  }[props.kind];
  const allowed = props.can(props.kind === "cost" ? "eac.view" : "read");
  const result = useForecastQuery(
    props.selected && allowed ? `/versions/${props.selected.id}/calculation` : null,
    props.query,
    props.selected
  );
  const calculation = result.result;
  const domain = object(calculation?.[props.kind === "milestones" ? "time" : props.kind]);
  const items = rows(props.kind === "milestones" ? domain.milestones : domain.items);
  return (
    <section className="progressPanel" aria-label={`${title} Results`}>
      <h3>{title} Results</h3>
      {!props.selected ? <p>Seleccione una versión Forecast para consultar su proyección.</p> : null}
      {!allowed ? <p className="progressWarning">Sin permiso para consultar esta proyección.</p> : null}
      {result.error ? (
        <p className="progressError" role="alert">
          {result.error}
        </p>
      ) : null}
      {calculation ? (
        <>
          <Facts
            values={[
              ["Resultado", domain.status ?? calculation.status],
              ["Versión Forecast", props.selected?.code],
              ["As-of", calculation.as_of],
              ["Período", calculation.period_id],
            ]}
          />
          <ReasonCodes codes={domain.reason_codes ?? calculation.reason_codes} />
          {props.kind === "cost" ? (
            <>
              <p>
                Original Budget, Current Budget, Cost Baseline, Actual y Forecast son bases distintas. El ETC
                comprometido no se vuelve a sumar al EAC.
              </p>
              <Records
                label="Forecast Cost Metrics"
                items={[domain]}
                columns={[
                  ["original_budget", "Original Budget"],
                  ["current_budget", "Current Budget"],
                  ["bac", "Cost Baseline BAC"],
                  ["actual", "Actual"],
                  ["commitment", "Commitment"],
                  ["committed_etc", "Committed ETC"],
                  ["uncommitted_etc", "Uncommitted ETC"],
                  ["allowance", "Allowance"],
                  ["etc", "ETC"],
                  ["eac", "EAC"],
                  ["vac", "VAC"],
                  ["currency", "Moneda"],
                ]}
              />
            </>
          ) : props.kind === "time" ? (
            <>
              <p>
                La proyección consume fechas y campos CPM aceptados de P6; no calcula critical path ni escribe de
                regreso a Schedule.
              </p>
              <Facts
                values={[
                  ["Baseline Finish", domain.baseline_finish],
                  ["Current Finish", domain.current_finish],
                  ["Forecast Finish", domain.forecast_finish],
                  ["Variance days", domain.finish_variance_days],
                  ["Data Date", domain.data_date],
                ]}
              />
            </>
          ) : props.kind === "resources" ? (
            <p>
              Planned, Actual y Forecast Productivity conservan unidad y método. No se suman personas, horas y equipos
              como un único recurso.
            </p>
          ) : (
            <p>
              Los hitos Forecast conservan su referencia y variación frente a Baseline y Current; no modifican hitos
              Schedule.
            </p>
          )}
          <Records
            label={`${title} Calculated Items`}
            items={items}
            columns={
              props.kind === "cost"
                ? [
                    ["code", "Componente"],
                    ["method", "Método"],
                    ["status", "Resultado"],
                    ["remaining_quantity", "Cantidad restante"],
                    ["unit", "Unidad"],
                    ["amount", "ETC"],
                    ["currency", "Moneda"],
                    ["cost_bucket", "ETC bucket"],
                    ["reason_codes", "Motivos"],
                  ]
                : props.kind === "resources"
                  ? [
                      ["code", "Componente"],
                      ["resource_type", "Recurso"],
                      ["remaining_quantity", "Cantidad restante"],
                      ["planned_productivity", "Planned productivity"],
                      ["actual_productivity", "Actual productivity"],
                      ["forecast_productivity", "Forecast productivity"],
                      ["quantity", "Recurso previsto"],
                      ["unit", "Unidad resultado"],
                      ["duration_days", "Duración prevista días"],
                      ["status", "Resultado"],
                      ["reason_codes", "Motivos"],
                    ]
                  : [
                      ["code", "Componente"],
                      ["activity_external_id", "Activity"],
                      ["milestone_type", "Tipo de hito"],
                      ["baseline_finish", "Baseline Finish"],
                      ["current_finish", "Current Finish"],
                      ["forecast_finish", "Forecast Finish"],
                      ["finish_variance_days", "Variación días"],
                      ["method", "Método"],
                      ["status", "Resultado"],
                      ["reason_codes", "Motivos"],
                    ]
            }
          />
          <Evidence title={`${title} entradas fuentes y cálculo backend`} value={domain} />
        </>
      ) : null}
    </section>
  );
}

const metricNames: [string, string][] = [
  ["baseline_finish", "Baseline Finish"],
  ["current_finish", "Current Finish"],
  ["forecast_finish", "Forecast Finish"],
  ["finish_variance_days", "Finish variance days"],
  ["bac", "Cost Baseline BAC"],
  ["current_budget", "Current Budget"],
  ["actual", "Actual Cost"],
  ["commitment", "Commitment"],
  ["etc", "ETC"],
  ["eac", "EAC"],
  ["vac", "VAC"],
  ["pv", "PV"],
  ["ev", "EV"],
  ["ac", "AC"],
  ["cpi", "CPI"],
  ["spi", "SPI"],
  ["physical_progress", "Approved Physical Progress"],
  ["quantity_progress", "Quantity Progress"],
  ["schedule_progress", "Schedule Progress"],
  ["cost_progress", "Cost Progress"],
  ["earned_progress", "Earned Progress"],
  ["readiness", "Readiness"],
  ["open_constraints", "Open Constraints"],
  ["critical_count", "Critical"],
  ["near_critical_count", "Near-Critical"],
];

export function PerformancePanel(props: ForecastPanelProps & { kind: "variance" | "dashboard" | "executive" }) {
  const baseQuery = props.query;
  const query = useCallback((path: string) => baseQuery(path, "performance"), [baseQuery]);
  const allowed = props.can(
    props.kind === "executive" ? "executive.view" : props.kind === "dashboard" ? "dashboard.view" : "read"
  );
  const path =
    props.selected && allowed
      ? `/${props.kind}?${parameters({ forecast_version_id: props.selected.id, period_id: props.periodId, as_of: props.asOf })}`
      : null;
  const result = useForecastQuery(path, query, props.selected);
  const title = { variance: "Variance", dashboard: "Project Controls Dashboard", executive: "Executive Dashboard" }[
    props.kind
  ];
  const value = result.result;
  const metrics = object(value?.metrics);
  const indicators = rows(value?.dashboard_indicators);
  const progressVariance = object(value?.progress_variances);
  return (
    <section className="progressPanel" aria-label={title}>
      <h3>{title}</h3>
      <p>
        Baseline, Current, Actual y Forecast se muestran con fuentes y fechas explícitas. Un resultado NOT_COMPUTABLE
        conserva motivos; no se sustituye por cero.
      </p>
      {!props.selected ? <p>Seleccione una versión Forecast.</p> : null}
      {!allowed ? <p className="progressWarning">Sin permiso para consultar esta vista.</p> : null}
      {result.error ? (
        <p className="progressError" role="alert">
          {result.error}
        </p>
      ) : null}
      {value ? (
        <>
          <Facts
            values={[
              ["Resultado", value.status],
              ...(value.project_status ? ([["Estado del Project", value.project_status]] as [string, unknown][]) : []),
              ["As-of", value.as_of],
              ["Período", value.period_id],
              ["Moneda", value.currency],
            ]}
          />
          <ReasonCodes codes={value.reason_codes} />
          {props.kind !== "variance" && indicators.length ? (
            <Records
              label={`${title} Threshold Indicators`}
              items={indicators.map((row) => ({
                ...row,
                metric_label: metricNames.find(([key]) => key === row.metric)?.[1] ?? row.metric,
              }))}
              columns={[
                ["metric_label", "Indicador"],
                ["value", "Valor"],
                ["threshold", "Umbral publicado"],
                ["unit", "Unidad"],
                ["warning_when", "Alerta si"],
                ["status", "Estado gobernado"],
                ["reason_codes", "Motivos"],
              ]}
            />
          ) : null}
          <Records
            label={`${title} Metrics`}
            items={metricNames.map(([code, name]) => ({ code, name, value: metrics[code] }))}
            columns={[
              ["name", "Métrica"],
              ["value", "Valor gobernado"],
            ]}
          />
          {props.kind === "variance" ? (
            <>
              <Records
                label="Governed Variance Comparison"
                items={rows(value.items)}
                columns={[
                  ["metric", "Métrica"],
                  ["baseline", "Baseline"],
                  ["current", "Current"],
                  ["actual", "Actual"],
                  ["forecast", "Forecast"],
                  ["variance", "Variación"],
                  ["currency", "Moneda"],
                  ["unit", "Unidad"],
                  ["status", "Resultado"],
                ]}
              />
              <Facts
                values={[
                  ["Planned Progress comparable", progressVariance.planned_progress],
                  ["Physical Progress Variance", progressVariance.physical_variance],
                  ["Unidad de variación física", progressVariance.unit],
                  ["Comparabilidad de avance físico", progressVariance.status],
                ]}
              />
              <ReasonCodes codes={progressVariance.reason_codes} />
            </>
          ) : null}
          {rows(value.milestones).length ? (
            <Records
              label={`${title} Key Milestones`}
              items={rows(value.milestones)}
              columns={[
                ["code", "Hito"],
                ["baseline_finish", "Baseline"],
                ["current_finish", "Current"],
                ["forecast_finish", "Forecast"],
                ["finish_variance_days", "Variación días"],
              ]}
            />
          ) : null}
          <Records
            label={`${title} Top Constraints`}
            items={rows(value.top_constraints).map((row) => ({ ...row, title: row.title ?? row.name }))}
            columns={[
              ["code", "Código"],
              ["title", "Restricción"],
              ["status", "Estado"],
              ["blocking", "Bloqueante"],
              ["work_package_id", "Package"],
              ["constraint_type", "Tipo"],
            ]}
          />
          {props.kind === "executive" ? (
            <Records
              label="Executive Dashboard Risk and Issue References"
              items={rows(value.risk_issue_references)}
              columns={[
                ["code", "Referencia"],
                ["kind", "Tipo"],
                ["source_reference", "Fuente"],
                ["evidence_ref", "Evidencia"],
              ]}
            />
          ) : null}
          <Narratives items={rows(value.narratives)} />
          <Evidence
            title={`${title} dominios autoridades y referencias`}
            value={{
              domains: value.domains,
              authority: value.authority,
              source_refs: value.source_refs,
              source_hashes: value.source_hashes,
            }}
          />
        </>
      ) : null}
    </section>
  );
}

export function Narratives({ items }: { items: ForecastRow[] }) {
  return (
    <div className="progressPanel" aria-label="Governed reporting narratives">
      <h4>Narrativa basada en hechos gobernados</h4>
      {items.map((row, index) => (
        <section key={`${text(row, "section")}-${index}`}>
          <h4>{text(row, "section")}</h4>
          <p>{text(row, "text")}</p>
          <Evidence title={`Referencias ${text(row, "section")}`} value={row.fact_references} />
        </section>
      ))}
      {!items.length ? <p>No hay narrativa calculable para la base seleccionada.</p> : null}
    </div>
  );
}

export function TrendsPanel(props: ForecastPanelProps) {
  const baseQuery = props.query;
  const query = useCallback((path: string) => baseQuery(path, "performance"), [baseQuery]);
  const result = useForecastQuery(
    props.selected ? `/trends?${parameters({ forecast_version_id: props.selected.id })}` : "/trends",
    query,
    props.data
  );
  const series = rows(result.result?.series);
  const trendColumns: [string, string][] = series.map((entry) => {
    const metric = text(entry, "metric");
    return [metric, metricNames.find(([key]) => key === metric)?.[1] ?? metric];
  });
  const items = rows(result.result?.items).map((row) => ({
    ...object(row.metrics_json ?? row.metrics),
    ...row,
    baseline_bundle_id: object(object(row.source_refs).bundle).id,
  }));
  return (
    <section className="progressPanel" aria-label="Forecast Trends">
      <h3>Trends</h3>
      <p>
        Los puntos proceden de reportes publicados e inmutables. Una consulta actual no reescribe los resultados de
        períodos anteriores.
      </p>
      {result.error ? (
        <p role="alert" className="progressError">
          {result.error}
        </p>
      ) : null}
      <ReasonCodes codes={result.result?.reason_codes} />
      <Records
        label="Published Period Trends"
        items={items}
        columns={[
          ["period_id", "Período"],
          ["as_of", "As-of"],
          ["currency", "Moneda"],
          ["baseline_bundle_id", "Baseline Bundle"],
          ...trendColumns,
          ["revision", "Revisión"],
        ]}
      />
      <Records
        label="Trend Series Semantics"
        items={series}
        columns={[
          ["metric", "Métrica"],
          ["unit", "Unidad"],
          ["currency", "Moneda"],
          ["status", "Comparabilidad"],
          ["reason_codes", "Motivos"],
          ["basis", "Base"],
        ]}
      />
      <Evidence title="Referencias y semántica de refresh de Trends" value={result.result} />
    </section>
  );
}

function CurveChart({ series }: { series: ForecastRow }) {
  const points = rows(series.points);
  const values = points.map((row) => row.cumulative_value);
  const finite = values
    .filter((value) => value !== null && value !== undefined && value !== "")
    .map(Number)
    .filter(Number.isFinite);
  const maximum = Math.max(...finite, 1);
  const minimum = Math.min(...finite, 0);
  const range = maximum - minimum || 1;
  // Coordinates only visualize backend values. They are not financial or forecast calculations.
  const coordinates = finite.map((value, index) => ({
    x: 45 + (index * 630) / Math.max(points.length - 1, 1),
    y: 165 - ((value - minimum) * 130) / range,
  }));
  return points.length && finite.length === points.length ? (
    <svg
      className="forecastCurve"
      viewBox="0 0 720 210"
      role="img"
      aria-label={`${text(series, "code")} S-Curve ${text(series, "currency", text(series, "unit"))}`}
    >
      <title>{text(series, "code")}</title>
      <desc>Valores acumulados del backend para una única unidad, moneda y base compatibles.</desc>
      <line x1="45" y1="165" x2="680" y2="165" stroke="#8aa0ac" />
      <line x1="45" y1="30" x2="45" y2="165" stroke="#8aa0ac" />
      {coordinates.length === 1 ? (
        <circle cx={coordinates[0].x} cy={coordinates[0].y} r="4" fill="#087d83" />
      ) : (
        <polyline
          points={coordinates.map(({ x, y }) => `${x},${y}`).join(" ")}
          fill="none"
          stroke="#087d83"
          strokeWidth="3"
        />
      )}
      <text x="45" y="195" fontSize="11">
        {text(points[0], "date")}
      </text>
      {points.length > 1 ? (
        <text x="590" y="195" fontSize="11">
          {text(points[points.length - 1], "date")}
        </text>
      ) : null}
      <text x="48" y="22" fontSize="11">
        {display(maximum)} {text(series, "currency", text(series, "unit"))}
      </text>
    </svg>
  ) : null;
}

export function CurvesPanel(props: ForecastPanelProps) {
  const baseQuery = props.query;
  const query = useCallback((path: string) => baseQuery(path, "performance"), [baseQuery]);
  const result = useForecastQuery(
    props.selected
      ? `/curves?${parameters({ forecast_version_id: props.selected.id, period_id: props.periodId, as_of: props.asOf })}`
      : null,
    query,
    props.selected
  );
  return (
    <section className="progressPanel" aria-label="Forecast S-Curves">
      <h3>S-Curves</h3>
      <p>
        Cada serie conserva unidad, moneda, base, versión y referencias. No se mezclan valores incompatibles en una
        misma curva.
      </p>
      {result.error ? (
        <p className="progressError" role="alert">
          {result.error}
        </p>
      ) : null}
      {!props.selected ? <p>Seleccione una versión Forecast.</p> : null}
      {rows(result.result?.series).map((series) => (
        <section className="progressPanel" key={text(series, "code")}>
          <h4>{text(series, "code")}</h4>
          <Facts
            values={[
              ["Estado", series.status],
              ["Unidad", series.unit],
              ["Moneda", series.currency],
              ["Base", series.basis],
            ]}
          />
          <ReasonCodes codes={series.reason_codes} />
          <CurveChart series={series} />
          <Records
            label={`${text(series, "code")} Curve Points`}
            items={rows(series.points)}
            columns={[
              ["date", "Fecha"],
              ["period_value", "Valor del período"],
              ["cumulative_value", "Valor acumulado"],
            ]}
          />
          <Evidence title={`${text(series, "code")} fuentes y versiones`} value={series.source_refs} />
        </section>
      ))}
    </section>
  );
}
