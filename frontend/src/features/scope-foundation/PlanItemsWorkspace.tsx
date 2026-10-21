import { useMemo, useState, type FormEvent } from "react";
import BimIfcModelViewer from "../../components/BimIfcModelViewer";
import type { Allocation, Command, PlanItem, ScopeOverview } from "./types";
import { canonicalViewerLines, canonicalViewerModel, canonicalViewerProvider } from "./viewerAdapter";

type TransformOutput = {
  code: string;
  name: string;
  allocations: Allocation[];
  model_object_ids?: number[];
  reason?: string;
};
function combinedAllocations(plans: PlanItem[]): Allocation[] {
  const values = new Map<string, Allocation>();
  plans
    .flatMap((plan) => plan.allocations ?? [])
    .forEach((row) => {
      const key = `${row.scope_item_id}:${row.unit}`;
      const previous = values.get(key);
      values.set(key, { ...row, quantity: Number(row.quantity) + Number(previous?.quantity ?? 0) });
    });
  return [...values.values()];
}
export default function PlanItemsWorkspace({
  data,
  token,
  workspaceId,
  busy,
  command,
  can,
}: {
  data: ScopeOverview;
  token: string;
  workspaceId: number;
  busy: boolean;
  command: Command;
  can: (action: string) => boolean;
}) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [reason, setReason] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [selectedPlans, setSelectedPlans] = useState<number[]>([]);
  const [operation, setOperation] = useState("GROUP");
  const [outputs, setOutputs] = useState("[]");
  const [splitCount, setSplitCount] = useState("2");
  const [error, setError] = useState("");
  const [derivedId, setDerivedId] = useState(0);
  const [previewModelId, setPreviewModelId] = useState(0);
  const run = (path: string, payload: unknown, version?: number) => {
    void command(path, payload, version).catch(() => undefined);
  };
  const selected = data.plan_items.filter((plan) => selectedPlans.includes(plan.id));
  function create(event: FormEvent) {
    event.preventDefault();
    const allocations = Object.entries(quantities)
      .filter(([, value]) => value !== "")
      .map(([id, value]) => ({
        scope_item_id: Number(id),
        quantity: Number(value),
        unit: data.items.find((item) => item.id === Number(id))?.unit ?? "",
      }));
    if (!allocations.length) {
      setError("Selecciona al menos una asignación Scope.");
      return;
    }
    const modelObjectIds = [
      ...new Set(
        data.items
          .filter((item) => allocations.some((row) => row.scope_item_id === item.id))
          .flatMap((item) => item.model_object_ids ?? [])
      ),
    ];
    run("/plan-items", {
      code,
      name,
      strategy_id: strategyId ? Number(strategyId) : null,
      allocations,
      model_object_ids: modelObjectIds,
      reason,
    });
  }
  function prepareTransform() {
    if (!selected.length) {
      setError("Selecciona Plan Items de origen.");
      return;
    }
    if (operation === "SPLIT" && (selected.length !== 1 || Number(splitCount) < 2 || Number(splitCount) > 20)) {
      setError("Split requiere un Plan Item y entre 2 y 20 salidas.");
      return;
    }
    const allocations = combinedAllocations(selected);
    const count = operation === "SPLIT" ? Number(splitCount) : 1;
    const next: TransformOutput[] = Array.from({ length: count }, (_, index) => ({
      code: `${code || selected[0].code}-${operation}-${index + 1}`,
      name: `${name || selected[0].name} · ${operation} ${index + 1}`,
      allocations: allocations.map((row) => ({ ...row, quantity: row.quantity / count })),
      model_object_ids: [...new Set(selected.flatMap((plan) => plan.model_object_ids ?? []))],
      reason,
    }));
    setOutputs(JSON.stringify(next, null, 2));
    setError("");
  }
  function transform(event: FormEvent) {
    event.preventDefault();
    try {
      const parsed: unknown = JSON.parse(outputs);
      if (!Array.isArray(parsed) || !parsed.length) throw new Error("Define las salidas de la transformación.");
      run("/plan-items/transform", {
        operation,
        source_plan_item_ids: selectedPlans,
        expected_versions: Object.fromEntries(selected.map((plan) => [String(plan.id), plan.version])),
        outputs: parsed,
        reason,
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Salidas inválidas.");
    }
  }
  const derived =
    data.derived_models.find((item) => item.id === derivedId) ?? data.derived_models[data.derived_models.length - 1];
  const matchingModels = useMemo(
    () =>
      data.models.filter((model) =>
        (model.objects_json ?? []).some((object) => derived?.model_object_ids?.includes(object.id))
      ),
    [data.models, derived]
  );
  const model = useMemo(
    () => matchingModels.find((item) => item.id === previewModelId) ?? matchingModels[0],
    [matchingModels, previewModelId]
  );
  const provider = useMemo(
    () => (model ? canonicalViewerProvider(token, workspaceId, model) : undefined),
    [model, token, workspaceId]
  );
  const viewerModel = useMemo(
    () => (model ? canonicalViewerModel(model, workspaceId) : undefined),
    [model, workspaceId]
  );
  const viewerLines = useMemo(() => canonicalViewerLines(model?.objects_json ?? [], workspaceId), [model, workspaceId]);
  const refs = useMemo(
    () =>
      (model?.objects_json ?? [])
        .filter((object) => derived?.model_object_ids?.includes(object.id))
        .map((object) => object.guid || `#${object.express_id}`),
    [derived, model]
  );
  return (
    <div className="scopePanel">
      <h3>Plan Items · puente de ejecución y control</h3>
      <p>
        Plan Item no es una actividad. El agrupamiento y la descomposición conservan asignaciones por Scope y unidad sin
        crear WBS, CBS ni autoridad de costos.
      </p>
      {error ? (
        <p className="scopeError" role="alert">
          {error}
        </p>
      ) : null}
      <div className="scopeTable">
        <table aria-label="Plan Items">
          <thead>
            <tr>
              <th>Selección</th>
              <th>Plan Item</th>
              <th>Estado</th>
              <th>Asignaciones Scope</th>
              <th>Modelo y revisión</th>
              <th>Publicación</th>
            </tr>
          </thead>
          <tbody>
            {data.plan_items.map((plan) => (
              <tr key={plan.id}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Seleccionar Plan ${plan.code}`}
                    checked={selectedPlans.includes(plan.id)}
                    onChange={(event) =>
                      setSelectedPlans((current) =>
                        event.target.checked ? [...current, plan.id] : current.filter((id) => id !== plan.id)
                      )
                    }
                  />
                </td>
                <td>
                  {plan.code}
                  <strong>{plan.name}</strong>
                </td>
                <td>
                  {plan.status}
                  <small>
                    r{plan.revision} · v{plan.version}
                  </small>
                </td>
                <td>
                  {(plan.allocations ?? []).map((row, i) => (
                    <div key={i}>
                      Scope #{row.scope_item_id}: {row.quantity} {row.unit}
                    </div>
                  ))}
                </td>
                <td>
                  <details>
                    <summary>{plan.model_object_ids?.length ?? 0} objetos · historia</summary>
                    <pre>{JSON.stringify(plan, null, 2)}</pre>
                  </details>
                </td>
                <td>
                  {can("plan.publish") && plan.status === "DRAFT" ? (
                    <button
                      type="button"
                      disabled={busy || reason.trim().length < 8}
                      onClick={() => run(`/plan-items/${plan.id}/publish`, { reason }, plan.version)}
                    >
                      Publicar Plan Item
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {can("plan.edit") ? (
        <>
          <form className="scopeForm" onSubmit={create}>
            <label>
              Plan Code
              <input required value={code} onChange={(event) => setCode(event.target.value)} />
            </label>
            <label>
              Plan Name
              <input required value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label>
              Execution Strategy
              <select value={strategyId} onChange={(event) => setStrategyId(event.target.value)}>
                <option value="">Sin estrategia seleccionada</option>
                {data.strategies.map((strategy) => (
                  <option key={strategy.id} value={strategy.id}>
                    {strategy.code} · {strategy.status}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Motivo Plan Item
              <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            <fieldset className="scopeWide">
              <legend>Scope → Plan allocation · relación M:N</legend>
              <div className="scopeForm">
                {data.items
                  .filter((item) => !["REMOVED", "SUPERSEDED"].includes(item.status))
                  .map((item) => (
                    <label key={item.id}>
                      {item.scope_code} · {item.name} · disponible {item.quantity} {item.unit}
                      <input
                        type="number"
                        min="0"
                        step="any"
                        aria-label={`Asignar cantidad ${item.scope_code}`}
                        placeholder="Sin asignación"
                        value={quantities[String(item.id)] ?? ""}
                        onChange={(event) =>
                          setQuantities((current) => ({ ...current, [String(item.id)]: event.target.value }))
                        }
                      />
                    </label>
                  ))}
              </div>
            </fieldset>
            <button type="submit" disabled={busy}>
              Crear Plan Item
            </button>
          </form>
          <section>
            <h4>Group / Split / Recompose</h4>
            <p>
              Prepara y revisa las salidas antes de aplicar. El servidor reconcilia las cantidades y conserva las
              versiones de origen.
            </p>
            <form className="scopeForm" onSubmit={transform}>
              <label>
                Operación
                <select value={operation} onChange={(event) => setOperation(event.target.value)}>
                  <option>GROUP</option>
                  <option>SPLIT</option>
                  <option>RECOMPOSE</option>
                </select>
              </label>
              <label>
                Número de segmentos
                <input
                  type="number"
                  min="2"
                  max="20"
                  disabled={operation !== "SPLIT"}
                  value={splitCount}
                  onChange={(event) => setSplitCount(event.target.value)}
                />
              </label>
              <label>
                Motivo transformación
                <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
              </label>
              <button type="button" disabled={busy} onClick={prepareTransform}>
                Preparar salidas
              </button>
              <label className="scopeWide">
                Salidas de transformación JSON
                <textarea
                  aria-label="Salidas de transformación JSON"
                  rows={12}
                  spellCheck={false}
                  value={outputs}
                  onChange={(event) => setOutputs(event.target.value)}
                />
              </label>
              <button type="submit" disabled={busy || !selectedPlans.length}>
                Aplicar transformación Plan Items
              </button>
            </form>
          </section>
        </>
      ) : null}
      <section>
        <h4>Derived Operational 3D Model</h4>
        <p>
          Subconjunto lógico versionado con trazabilidad a IFC, Scope y Plan Items. No genera ni modifica geometría
          original.
        </p>
        {can("derived.edit") ? (
          <div className="scopeActions">
            <label>
              Motivo representación derivada
              <input minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            <button
              type="button"
              disabled={busy || !selectedPlans.length || reason.trim().length < 8}
              onClick={() => run("/derived-models", { plan_item_ids: selectedPlans, split_rule: "LOGICAL", reason })}
            >
              Crear Derived 3D subset
            </button>
          </div>
        ) : null}
        <label>
          Versión representación derivada
          <select
            aria-label="Versión representación derivada"
            value={derived?.id ?? ""}
            onChange={(event) => setDerivedId(Number(event.target.value))}
          >
            <option value="">Sin representación</option>
            {data.derived_models.map((item) => (
              <option key={item.id} value={item.id}>
                Derived #{item.id} · r{item.revision} · {item.status}
              </option>
            ))}
          </select>
        </label>
        {derived ? (
          <details>
            <summary>Linaje, reglas e historial de Derived #{derived.id}</summary>
            <pre>{JSON.stringify(derived, null, 2)}</pre>
          </details>
        ) : null}
        {matchingModels.length ? (
          <label>
            Versión IFC para preview
            <select value={model?.id ?? ""} onChange={(event) => setPreviewModelId(Number(event.target.value))}>
              {matchingModels.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.model_code} · r{item.revision}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p>No hay geometría vinculada en la selección. Los Plan Items manuales/Excel no requieren IFC.</p>
        )}
        {model && viewerModel && provider && refs.length ? (
          <BimIfcModelViewer
            key={`${derived?.id}:${model.id}`}
            projectId={workspaceId}
            token={token}
            model={viewerModel}
            lines={viewerLines}
            sourceProvider={provider}
            isolatedRefs={refs}
            sourceLoadDisabled
            clearModelDisabled
            informationContent={
              <p>
                Derived preview lógico #{derived?.id}; {refs.length} referencias IFC. Fuente original SHA256{" "}
                {model.source_hash}.
              </p>
            }
          />
        ) : null}
      </section>
      <section className="scopeFuture">
        <h4>Integraciones futuras · no activas</h4>
        <p>
          WBS Mapping · Activity Mapping · CBS Mapping · AWP Mapping. Ninguna asignación downstream ni timeline 4D se
          crea aquí.
        </p>
      </section>
    </div>
  );
}
