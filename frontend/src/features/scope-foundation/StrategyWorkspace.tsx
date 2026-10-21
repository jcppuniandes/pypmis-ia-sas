import { useState, type FormEvent } from "react";
import type { Command, ExecutionPath, ExecutionStrategy, ScopeOverview } from "./types";

const emptyPath: ExecutionPath = {
  code: "",
  name: "",
  mode: "ORDERED",
  sequence: 1,
  area: "",
  zone: "",
  system: "",
  phase: "",
  condition: "",
};
export default function StrategyWorkspace({
  data,
  busy,
  command,
  can,
}: {
  data: ScopeOverview;
  busy: boolean;
  command: Command;
  can: (action: string) => boolean;
}) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [reason, setReason] = useState("");
  const [paths, setPaths] = useState<ExecutionPath[]>([]);
  const [path, setPath] = useState(emptyPath);
  const [segmentation, setSegmentation] = useState("AREA");
  const [segmentValues, setSegmentValues] = useState("");
  const [segmentQuantity, setSegmentQuantity] = useState("");
  const [rules, setRules] = useState<Record<string, unknown>[]>([]);
  const [awp, setAwp] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<ExecutionStrategy | null>(null);
  const [segmentScopeIds, setSegmentScopeIds] = useState<number[]>([]);
  const [ruleIndex, setRuleIndex] = useState("0");
  const [codePrefix, setCodePrefix] = useState("");
  const [assignments, setAssignments] = useState("{}");
  const run = (endpoint: string, payload: unknown, version?: number, method?: "POST" | "PUT") => {
    void command(endpoint, payload, version, method).catch(() => undefined);
  };
  function addPath() {
    if (!path.code.trim() || !path.name.trim()) {
      setError("Cada ruta requiere código y nombre.");
      return;
    }
    setPaths((current) => [...current, path]);
    setPath({ ...emptyPath, sequence: paths.length + 2 });
    setError("");
  }
  function addRule() {
    setRules((current) => [
      ...current,
      {
        kind: segmentation,
        ...(segmentValues.trim()
          ? {
              values: segmentValues
                .split(",")
                .map((value) => value.trim())
                .filter(Boolean),
            }
          : {}),
        ...(segmentQuantity ? { quantity: Number(segmentQuantity) } : {}),
      },
    ]);
    setSegmentValues("");
    setSegmentQuantity("");
  }
  function save(event: FormEvent) {
    event.preventDefault();
    if (!paths.length) {
      setError("Define al menos una ruta de ejecución.");
      return;
    }
    run(
      selected ? `/strategies/${selected.id}` : "/strategies",
      { code, name, reason, paths, segmentation_rules: rules, awp_applicability: awp ? "APPLICABLE" : "OPTIONAL" },
      selected?.version,
      selected ? "PUT" : "POST"
    );
  }
  function segment(strategy: ExecutionStrategy) {
    try {
      const value: unknown = JSON.parse(assignments);
      if (!value || typeof value !== "object" || Array.isArray(value))
        throw new Error("Las asignaciones deben ser un objeto JSON Scope ID a valor.");
      run(
        `/strategies/${strategy.id}/segment`,
        {
          scope_item_ids: segmentScopeIds,
          rule_index: Number(ruleIndex),
          code_prefix: codePrefix,
          assignments: value,
          reason,
        },
        strategy.version
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Asignaciones inválidas.");
    }
  }
  return (
    <div className="scopePanel">
      <h3>Strategy &amp; Path of Execution</h3>
      <p>
        Define cómo se ejecuta Scope mediante rutas ordenadas, paralelas o condicionales. No crea actividades ni calcula
        CPM.
      </p>
      {error ? (
        <p role="alert" className="scopeError">
          {error}
        </p>
      ) : null}
      {can("strategy.edit") ? (
        <form className="scopeForm" onSubmit={save}>
          <div className="scopeWide">
            <button
              type="button"
              onClick={() => {
                setSelected(null);
                setCode("");
                setName("");
                setPaths([]);
                setRules([]);
              }}
            >
              Nueva Execution Strategy
            </button>
          </div>
          <label>
            Strategy Code
            <input
              required
              disabled={Boolean(selected)}
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </label>
          <label>
            Strategy Name
            <input required value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            Motivo estrategia
            <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <fieldset className="scopeWide">
            <legend>Execution Paths</legend>
            <div className="scopeForm">
              <label>
                Path Code
                <input
                  value={path.code}
                  onChange={(event) => setPath((current) => ({ ...current, code: event.target.value }))}
                />
              </label>
              <label>
                Path Name
                <input
                  value={path.name}
                  onChange={(event) => setPath((current) => ({ ...current, name: event.target.value }))}
                />
              </label>
              <label>
                Path Mode
                <select
                  value={path.mode}
                  onChange={(event) => setPath((current) => ({ ...current, mode: event.target.value }))}
                >
                  {["ORDERED", "PARALLEL", "CONDITIONAL", "AREA", "SYSTEM", "PHASE", "PACKAGE"].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
              <label>
                Secuencia
                <input
                  type="number"
                  min="0"
                  value={path.sequence}
                  onChange={(event) => setPath((current) => ({ ...current, sequence: Number(event.target.value) }))}
                />
              </label>
              {(["area", "zone", "system", "phase", "condition"] as const).map((key) => (
                <label key={key}>
                  {{ area: "Área", zone: "Zona", system: "Sistema", phase: "Fase", condition: "Condición" }[key]}
                  <input
                    value={path[key]}
                    onChange={(event) => setPath((current) => ({ ...current, [key]: event.target.value }))}
                  />
                </label>
              ))}
              <button type="button" disabled={busy} onClick={addPath}>
                Agregar Execution Path
              </button>
            </div>
            {paths.length ? (
              <ol>
                {paths.map((entry, index) => (
                  <li key={`${entry.code}-${index}`}>
                    {entry.code} · {entry.name} · {entry.mode} · secuencia {entry.sequence}
                    <button type="button" onClick={() => setPaths((current) => current.filter((_, i) => i !== index))}>
                      Quitar ruta
                    </button>
                  </li>
                ))}
              </ol>
            ) : null}
          </fieldset>
          <fieldset className="scopeWide">
            <legend>Segmentation Rules</legend>
            <div className="scopeForm">
              <label>
                Regla de segmentación
                <select value={segmentation} onChange={(event) => setSegmentation(event.target.value)}>
                  {["AREA", "LEVEL", "ZONE", "SYSTEM", "QUANTITY_RANGE", "WORKFRONT", "PACKAGE", "MODEL_SELECTION"].map(
                    (value) => (
                      <option key={value}>{value}</option>
                    )
                  )}
                </select>
              </label>
              <label>
                Valores separados por coma
                <input value={segmentValues} onChange={(event) => setSegmentValues(event.target.value)} />
              </label>
              <label>
                Cantidad por segmento
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={segmentQuantity}
                  onChange={(event) => setSegmentQuantity(event.target.value)}
                />
              </label>
              <button type="button" onClick={addRule}>
                Agregar regla
              </button>
            </div>
            {rules.length ? (
              <ul>
                {rules.map((rule, index) => (
                  <li key={index}>
                    {JSON.stringify(rule)}
                    <button type="button" onClick={() => setRules((current) => current.filter((_, i) => i !== index))}>
                      Quitar regla
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </fieldset>
          <label>
            <input type="checkbox" checked={awp} onChange={(event) => setAwp(event.target.checked)} /> Aplicabilidad
            futura AWP declarada, no activación de AWP
          </label>
          <button type="submit" disabled={busy}>
            {selected ? "Guardar Execution Strategy DRAFT" : "Crear Execution Strategy DRAFT"}
          </button>
        </form>
      ) : null}
      {can("plan.edit") ? (
        <fieldset>
          <legend>Generar Plan Items candidatos desde segmentación</legend>
          <p>Selecciona Scope aprobado. Esta operación crea descomposición de ejecución, no actividades Schedule.</p>
          <div className="scopeForm">
            <label>
              Prefijo Plan Items candidatos
              <input value={codePrefix} onChange={(event) => setCodePrefix(event.target.value)} />
            </label>
            <label>
              Índice de regla de segmentación
              <input type="number" min="0" value={ruleIndex} onChange={(event) => setRuleIndex(event.target.value)} />
            </label>
            <label>
              Motivo segmentación
              <input minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            {data.items
              .filter((item) => item.status === "APPROVED")
              .map((item) => (
                <label key={item.id}>
                  <input
                    type="checkbox"
                    checked={segmentScopeIds.includes(item.id)}
                    onChange={(event) =>
                      setSegmentScopeIds((current) =>
                        event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id)
                      )
                    }
                  />
                  {item.scope_code} · {item.name}
                </label>
              ))}
            <label className="scopeWide">
              Asignaciones explícitas por Scope ID JSON
              <textarea
                rows={3}
                spellCheck={false}
                value={assignments}
                onChange={(event) => setAssignments(event.target.value)}
              />
            </label>
          </div>
        </fieldset>
      ) : null}
      <div className="scopeTable">
        <table aria-label="Execution Strategies">
          <thead>
            <tr>
              <th>Estrategia</th>
              <th>Estado</th>
              <th>Rutas y segmentación</th>
              <th>Publicación e historia</th>
            </tr>
          </thead>
          <tbody>
            {data.strategies.map((strategy) => (
              <tr key={strategy.id}>
                <td>
                  {strategy.code}
                  <strong>{strategy.name}</strong>
                  <small>
                    r{strategy.revision} · v{strategy.version}
                  </small>
                </td>
                <td>
                  {strategy.status}
                  {can("strategy.edit") && strategy.status === "DRAFT" ? (
                    <button
                      type="button"
                      onClick={() => {
                        setSelected(strategy);
                        setCode(strategy.code);
                        setName(strategy.name);
                        setPaths(strategy.paths ?? []);
                        setRules(strategy.segmentation_rules ?? []);
                      }}
                    >
                      Editar Execution Strategy
                    </button>
                  ) : null}
                </td>
                <td>
                  <details>
                    <summary>{strategy.paths?.length ?? 0} rutas</summary>
                    <pre>{JSON.stringify(strategy, null, 2)}</pre>
                  </details>
                </td>
                <td>
                  <label>
                    Motivo publicación/sucesor
                    <input value={reason} onChange={(event) => setReason(event.target.value)} />
                  </label>
                  {can("strategy.publish") && strategy.status === "DRAFT" ? (
                    <button
                      type="button"
                      disabled={busy || reason.trim().length < 8}
                      onClick={() => run(`/strategies/${strategy.id}/publish`, { reason }, strategy.version)}
                    >
                      Publicar Execution Strategy
                    </button>
                  ) : null}
                  {can("strategy.edit") && strategy.status === "PUBLISHED" ? (
                    <button
                      type="button"
                      disabled={busy || reason.trim().length < 8}
                      onClick={() => run(`/strategies/${strategy.id}/successor`, { reason }, strategy.version)}
                    >
                      Crear Strategy sucesora DRAFT
                    </button>
                  ) : null}
                  {strategy.status === "PUBLISHED" ? (
                    <small>Publicación inmutable; requiere sucesor para cambiar.</small>
                  ) : null}
                  {can("plan.edit") && strategy.status === "PUBLISHED" ? (
                    <button
                      type="button"
                      disabled={busy || !segmentScopeIds.length || !codePrefix.trim() || reason.trim().length < 8}
                      onClick={() => segment(strategy)}
                    >
                      Generar Plan Items candidatos
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
