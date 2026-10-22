import { useEffect, useMemo, useState } from "react";
import { operationalError } from "../operational-context/commands";
import type { JsonRecord, ScheduleOverview } from "../schedule-foundation/types";
import { fourDApi } from "./api";
import { fourDFilterLabels, type FourDComparison, type FourDFilters, type FourDItem, type FourDView } from "./types";
import { fourDColors, fourDDateInput, itemVisual, shiftFourDDate } from "./visualStates";
import FourDGeometryView from "./FourDGeometryView";
import "./fourD.css";

function text(value: unknown) {
  return value === null || value === undefined ? "—" : String(value);
}
function uniq(options: { value: string; label: string }[]) {
  return [
    ...new Map(
      options.filter((item) => item.value && item.value !== "undefined").map((item) => [item.value, item])
    ).values(),
  ];
}

export default function FourDWorkspace({
  token,
  workspaceId,
  schedule,
}: {
  token: string;
  workspaceId: number;
  schedule: ScheduleOverview;
}) {
  const [source, setSource] = useState("CURRENT");
  const [currentId, setCurrentId] = useState("");
  const [baselineId, setBaselineId] = useState("");
  const [at, setAt] = useState("");
  const [filters, setFilters] = useState<FourDFilters>({});
  const [view, setView] = useState<FourDView | null>(null);
  const [catalog, setCatalog] = useState<FourDItem[]>([]);
  const [comparison, setComparison] = useState<FourDComparison | null>(null);
  const [compare, setCompare] = useState(false);
  const [trace, setTrace] = useState<unknown>(null);
  const [selected, setSelected] = useState<FourDItem | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState("1");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const accepted = schedule.versions.filter((row) => row.status === "ACCEPTED_CURRENT");
  const baselines = schedule.baselines.filter((row) => row.status === "APPROVED_BASELINE");
  const current =
    currentId ||
    String(
      schedule.registers.find((row) => row.current_version_id)?.current_version_id ??
        accepted[accepted.length - 1]?.id ??
        ""
    );
  const baseline = baselineId || String(baselines[baselines.length - 1]?.id ?? "");
  const parameters = useMemo(
    () => ({ source, ...(source === "CURRENT" ? { version_id: current } : { baseline_id: baseline }), at, ...filters }),
    [source, current, baseline, at, filters]
  );
  const queryKey = JSON.stringify(parameters);
  useEffect(() => {
    let active = true;
    if ((source === "CURRENT" && !current) || (source === "BASELINE" && !baseline)) {
      queueMicrotask(() => {
        if (active) {
          setView(null);
          setError(
            "No existe la fuente gobernada seleccionada. Aceptar Current o aprobar Baseline mediante Schedule antes de abrir 4D."
          );
        }
      });
      return () => {
        active = false;
      };
    }
    queueMicrotask(() => {
      if (active) {
        setLoading(true);
        setError("");
      }
    });
    fourDApi
      .view(token, workspaceId, parameters)
      .then((result) => {
        if (active) {
          setView(result);
          if (!Object.values(filters).some(Boolean)) setCatalog(result.items);
        }
      })
      .catch((caught) => {
        if (active) {
          setView(null);
          setError(operationalError(caught));
        }
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
    // Stable serialized query avoids refetching for unrelated presentation changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, workspaceId, queryKey]);
  const selectedDate = at || view?.at || "";
  const inputDate = fourDDateInput(selectedDate, view?.source.timezone ?? "UTC");
  useEffect(() => {
    if (!playing || !selectedDate || loading) return;
    const timer = window.setInterval(
      () => setAt((value) => shiftFourDDate(value || selectedDate, 1)),
      Math.max(150, 1200 / Number(speed))
    );
    return () => window.clearInterval(timer);
  }, [playing, selectedDate, speed, loading]);
  useEffect(() => {
    let active = true;
    if (!compare || !current || !baseline || !selectedDate) {
      queueMicrotask(() => {
        if (active) setComparison(null);
      });
      return () => {
        active = false;
      };
    }
    fourDApi
      .compare(token, workspaceId, { version_id: current, baseline_id: baseline, at: selectedDate, ...filters })
      .then((result) => active && setComparison(result))
      .catch((caught) => {
        if (active) {
          setComparison(null);
          setError(operationalError(caught));
        }
      });
    return () => {
      active = false;
    };
  }, [compare, current, baseline, selectedDate, filters, token, workspaceId]);
  useEffect(() => {
    let active = true;
    if (!selected) {
      queueMicrotask(() => {
        if (active) setTrace(null);
      });
      return () => {
        active = false;
      };
    }
    queueMicrotask(() => {
      if (active) setTrace(null);
    });
    fourDApi
      .traceability(token, workspaceId, selected.scope_item_id, parameters)
      .then((result) => active && setTrace(result.traceability ?? result))
      .catch((caught) => active && setError(operationalError(caught)));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.scope_item_id, queryKey, token, workspaceId]);
  const colors =
    ((view?.configuration?.content_json as JsonRecord | undefined)?.display as JsonRecord | undefined) ??
    (view?.configuration?.display as JsonRecord | undefined) ??
    {};
  const options = (key: string): { value: string; label: string }[] => {
    if (["critical", "near_critical", "blocked"].includes(key))
      return [
        { value: "true", label: "Sí" },
        { value: "false", label: "No" },
      ];
    if (key === "scope_nature")
      return ["INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"].map((value) => ({ value, label: value }));
    if (key === "execution_readiness")
      return ["NOT_ASSESSED", "NOT_READY", "PARTIALLY_READY", "READY", "RELEASED"].map((value) => ({
        value,
        label: value,
      }));
    if (key === "scope_item_id")
      return uniq(
        catalog.map((row) => ({ value: String(row.scope_item_id), label: `${row.scope_code} · ${row.name}` }))
      );
    if (key === "plan_item_id")
      return uniq(
        catalog
          .filter((row) => row.plan_item_id)
          .map((row) => ({ value: String(row.plan_item_id), label: row.plan_code ?? String(row.plan_item_id) }))
      );
    if (["area", "zone", "system"].includes(key))
      return uniq(
        catalog
          .map((row) => ({
            value: text(row[key as "area" | "zone" | "system"]),
            label: text(row[key as "area" | "zone" | "system"]),
          }))
          .filter((row) => row.value !== "—")
      );
    if (key === "wbs")
      return uniq(
        catalog.flatMap((row) =>
          row.wbs.map((item) => ({
            value: text(item.external_id),
            label: `${text(item.code ?? item.external_id)} · ${text(item.name)}`,
          }))
        )
      );
    if (key === "activity")
      return uniq(
        catalog.flatMap((row) =>
          row.activities.map((item) => ({
            value: text(item.external_id),
            label: `${text(item.code ?? item.external_id)} · ${text(item.name)}`,
          }))
        )
      );
    if (key === "activity_status")
      return uniq(
        catalog.flatMap((row) => row.activities.map((item) => ({ value: text(item.status), label: text(item.status) })))
      );
    if (key === "cwa_id")
      return uniq(
        catalog.flatMap((row) =>
          row.cwas.map((item) => ({ value: text(item.id), label: text(item.code ?? item.name) }))
        )
      );
    return uniq(
      catalog.flatMap((row) =>
        row.packages.map((item) => ({
          value: key === "package_type" ? text(item.package_type) : text(item.id),
          label: key === "package_type" ? text(item.package_type) : text(item.package_code ?? item.name),
        }))
      )
    );
  };
  return (
    <section className="fourDWorkspace" aria-label="4D Model" aria-busy={loading}>
      <h3>4D Model · Schedule-driven projection</h3>
      <p className="fourDBoundary">
        4D consume fechas gobernadas de P6; no calcula CPM, float ni pronósticos. La geometría IFC y los baselines
        permanecen inmutables.
      </p>
      <p>
        Los estados representan una proyección temporal del cronograma, no avance físico certificado. El overlay de
        readiness muestra las condiciones operacionales actuales, también al consultar Baseline.
      </p>
      {error ? (
        <p role="alert" className="fourDError">
          {error}
        </p>
      ) : null}
      <div className="fourDControls">
        <label>
          Fuente 4D
          <select
            aria-label="Source 4D"
            value={source}
            onChange={(e) => {
              setSource(e.target.value);
              setPlaying(false);
              setAt("");
            }}
          >
            <option value="CURRENT">Accepted Current</option>
            <option value="BASELINE">Approved Baseline</option>
          </select>
        </label>
        <label>
          Current 4D
          <select aria-label="Current 4D" value={current} onChange={(e) => setCurrentId(e.target.value)}>
            <option value="" disabled>
              Seleccionar accepted
            </option>
            {accepted.map((row) => (
              <option key={row.id} value={row.id}>
                #{row.id} · r{row.revision} · ACCEPTED
              </option>
            ))}
          </select>
        </label>
        <label>
          Baseline 4D
          <select aria-label="Baseline 4D" value={baseline} onChange={(e) => setBaselineId(e.target.value)}>
            <option value="" disabled>
              Seleccionar approved
            </option>
            {baselines.map((row) => (
              <option key={row.id} value={row.id}>
                #{row.id} · {row.baseline_type} · APPROVED_BASELINE
              </option>
            ))}
          </select>
        </label>
        <label>
          Fecha 4D ({view?.source.timezone ?? "UTC"})
          <input
            aria-label="Date 4D"
            type="datetime-local"
            value={inputDate}
            onChange={(e) => {
              setAt(e.target.value);
              setPlaying(false);
            }}
          />
        </label>
        <label>
          Velocidad
          <select aria-label="Speed 4D" value={speed} onChange={(e) => setSpeed(e.target.value)}>
            {["0.5", "1", "2", "4", "8"].map((value) => (
              <option key={value} value={value}>
                {value}×
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="fourDButtons">
        {error ? (
          <button type="button" onClick={() => setFilters({})}>
            Restablecer filtros 4D
          </button>
        ) : null}
        <button
          type="button"
          disabled={!selectedDate || loading}
          onClick={() => setAt(shiftFourDDate(selectedDate, -1))}
        >
          Paso atrás 4D
        </button>
        <button type="button" disabled={!selectedDate} aria-pressed={playing} onClick={() => setPlaying(true)}>
          Play 4D
        </button>
        <button type="button" onClick={() => setPlaying(false)}>
          Pause 4D
        </button>
        <button
          type="button"
          disabled={!selectedDate || loading}
          onClick={() => setAt(shiftFourDDate(selectedDate, 1))}
        >
          Paso adelante 4D
        </button>
        <button
          type="button"
          disabled={!view?.source.data_date}
          onClick={() => {
            setAt(view?.source.data_date ?? "");
            setPlaying(false);
          }}
        >
          AS OF DATA DATE
        </button>
        <label>
          Milestone 4D
          <select
            aria-label="Milestone 4D"
            value=""
            onChange={(e) => {
              if (e.target.value) setAt(e.target.value);
              setPlaying(false);
            }}
          >
            <option value="">Saltar a milestone</option>
            {view?.milestones
              .filter((row) => row.date)
              .map((row) => (
                <option key={row.external_id} value={row.date ?? ""}>
                  {row.name} · {row.date}
                </option>
              ))}
          </select>
        </label>
        <label>
          <input
            aria-label="Compare Baseline Current 4D"
            type="checkbox"
            checked={compare}
            disabled={!current || !baseline}
            onChange={(e) => setCompare(e.target.checked)}
          />{" "}
          Comparar Baseline vs Current
        </label>
      </div>
      {view ? (
        <>
          <dl className="fourDFacts" aria-label="Data Date source context">
            <div>
              <dt>Data Date</dt>
              <dd>{view.source.data_date ?? "NO DATA DATE"}</dd>
            </div>
            <div>
              <dt>Schedule Version</dt>
              <dd>
                #{view.source.schedule_version_id} · {view.source.kind}
              </dd>
            </div>
            <div>
              <dt>Approved Baseline</dt>
              <dd>{baseline || "Sin baseline aprobado"}</dd>
            </div>
            <div>
              <dt>Accepted Current</dt>
              <dd>{current || "Sin current aceptado"}</dd>
            </div>
            <div>
              <dt>Project Controls Period</dt>
              <dd>
                {view.period_associations.length
                  ? view.period_associations
                      .map((row) => text(row.period_code ?? row.project_controls_period_id ?? row.period_id))
                      .join(", ")
                  : "Sin asociación explícita"}
              </dd>
            </div>
          </dl>
          <details open>
            <summary>Filtros 4D</summary>
            <div className="fourDFilters">
              {Object.entries(fourDFilterLabels).map(([key, label]) => (
                <label key={key}>
                  {label}
                  <select
                    aria-label={`Filter 4D ${label}`}
                    value={filters[key] ?? ""}
                    onChange={(e) => setFilters({ ...filters, [key]: e.target.value })}
                  >
                    <option value="">Todos</option>
                    {options(key).map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            <button type="button" onClick={() => setFilters({})}>
              Limpiar filtros 4D
            </button>
          </details>
          <div className="fourDLegend" aria-label="4D state legend">
            {Object.entries(fourDColors).map(([state, color]) => (
              <span key={state}>
                <i
                  style={{
                    backgroundColor:
                      typeof (colors[state] as JsonRecord | undefined)?.color === "string"
                        ? String((colors[state] as JsonRecord).color)
                        : color,
                  }}
                />
                {state}
              </span>
            ))}
          </div>
          <FourDGeometryView
            token={token}
            workspaceId={workspaceId}
            items={view.items}
            colors={colors}
            onSelect={setSelected}
          />
          <div className="fourDTable">
            <table aria-label="4D states and traceability">
              <thead>
                <tr>
                  <th>Scope / Nature</th>
                  <th>Plan</th>
                  <th>Estado semántico</th>
                  <th>Visible</th>
                  <th>Visual classes</th>
                  <th>Packages</th>
                  <th>Activities</th>
                  <th>IFC / Derived</th>
                  <th>Trazabilidad</th>
                </tr>
              </thead>
              <tbody>
                {view.items.map((item) => (
                  <tr key={item.id} data-state={item.state}>
                    <td>
                      {item.scope_code}
                      <small>
                        {item.scope_nature} · {item.name}
                      </small>
                    </td>
                    <td>{item.plan_code ?? "—"}</td>
                    <td>
                      <i className="fourDStateDot" style={{ backgroundColor: itemVisual(item, colors).color }} />
                      {item.semantic_state} · {item.state}
                    </td>
                    <td>{item.visible ? "VISIBLE" : "HIDDEN"}</td>
                    <td>{item.visual_classes.join(", ")}</td>
                    <td>{item.packages.map((row) => text(row.package_code)).join(", ") || "—"}</td>
                    <td>
                      {item.activities
                        .map((row) => `${text(row.code ?? row.external_id)} (${text(row.phase)})`)
                        .join(", ") || "UNMAPPED"}
                    </td>
                    <td>
                      {item.objects.length} IFC / {item.derived_models.length} Derived
                      <small>{item.mapping_issues.length ? JSON.stringify(item.mapping_issues) : "Mapped"}</small>
                    </td>
                    <td>
                      <button type="button" onClick={() => setSelected(item)}>
                        Traceability {item.scope_code}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {comparison ? (
            <section aria-label="4D Baseline Current comparison">
              <h4>Baseline vs Current · {selectedDate}</h4>
              <div className="fourDTable">
                <table>
                  <thead>
                    <tr>
                      <th>Scope</th>
                      <th>Plan</th>
                      <th>Baseline state</th>
                      <th>Current state</th>
                      <th>Variance classification</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.items.map((item) => (
                      <tr key={item.id}>
                        <td>{item.scope_item_id}</td>
                        <td>{item.plan_item_id ?? "—"}</td>
                        <td>{item.baseline_state}</td>
                        <td>{item.current_state}</td>
                        <td>{item.variance_classification}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}
          {selected ? (
            <aside className="fourDTraceability" aria-label="4D traceability panel">
              <h4>Traceability · {selected.scope_code}</h4>
              <p>
                Original IFC GUID / Model Version → Scope Nature → Plan → Derived 3D → CWA / Work Packages → WBS /
                Activities → Schedule source → Readiness.
              </p>
              <pre>{JSON.stringify(trace ?? selected, null, 2)}</pre>
            </aside>
          ) : null}
          <details>
            <summary>Fuentes inmutables, autoridad y diagnóstico 4D</summary>
            <pre>
              {JSON.stringify(
                {
                  source: view.source,
                  source_hashes: view.source_hashes,
                  authority: view.authority,
                  diagnostics: view.diagnostics,
                },
                null,
                2
              )}
            </pre>
          </details>
        </>
      ) : null}
    </section>
  );
}
