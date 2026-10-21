import { useMemo, useState, type FormEvent } from "react";
import BimIfcModelViewer from "../../components/BimIfcModelViewer";
import type { Command, ModelObject, ScopeOverview } from "./types";
import { canonicalViewerLines, canonicalViewerModel, canonicalViewerProvider, modelUnitCode } from "./viewerAdapter";

export default function ModelWorkspace({
  data,
  token,
  workspaceId,
  busy,
  command,
  can,
  upload,
}: {
  data: ScopeOverview;
  token: string;
  workspaceId: number;
  busy: boolean;
  command: Command;
  can: (action: string) => boolean;
  upload: (
    kind: "models" | "excel-imports",
    file: File,
    reason: string,
    modelCode?: string,
    mapping?: string
  ) => Promise<void>;
}) {
  const [selectedId, setSelectedId] = useState(0);
  const [modelCode, setModelCode] = useState("");
  const [reason, setReason] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [filter, setFilter] = useState("");
  const [discipline, setDiscipline] = useState("");
  const [classification, setClassification] = useState("");
  const [mapping, setMapping] = useState("all");
  const [selectedObjects, setSelectedObjects] = useState<number[]>([]);
  const [inspected, setInspected] = useState<ModelObject | null>(null);
  const [scopeCode, setScopeCode] = useState("");
  const [scopeName, setScopeName] = useState("");
  const [scopeNature, setScopeNature] = useState("INSTALL");
  const [quantity, setQuantity] = useState("1");
  const [unit, setUnit] = useState("ea");
  const [sourceQuantity, setSourceQuantity] = useState("SOURCE_OBJECT_COUNT");
  const model = data.models.find((item) => item.id === selectedId) ?? data.models[data.models.length - 1];
  const objects = model?.objects_json ?? [];
  const viewerModel = useMemo(
    () => (model ? canonicalViewerModel(model, workspaceId) : undefined),
    [model, workspaceId]
  );
  const provider = useMemo(
    () => (model ? canonicalViewerProvider(token, workspaceId, model) : undefined),
    [model, token, workspaceId]
  );
  const viewerLines = useMemo(() => canonicalViewerLines(model?.objects_json ?? [], workspaceId), [model, workspaceId]);
  const isolatedRefs = useMemo(
    () => objects.filter((item) => selectedObjects.includes(item.id)).map((item) => item.guid || `#${item.express_id}`),
    [objects, selectedObjects]
  );
  const filtered = objects.filter(
    (object) =>
      (!filter ||
        [object.name, object.guid, object.area, object.zone, object.system, object.level]
          .join(" ")
          .toLowerCase()
          .includes(filter.toLowerCase())) &&
      (!discipline || object.discipline === discipline) &&
      (!classification || object.ifc_class === classification) &&
      (mapping === "all" ||
        (mapping === "scope"
          ? Boolean(object.scope_item_ids?.length)
          : mapping === "plan"
            ? Boolean(object.plan_item_ids?.length)
            : !object.scope_item_ids?.length))
  );
  async function stage(event: FormEvent) {
    event.preventDefault();
    if (file) await upload("models", file, reason, modelCode);
  }
  const run = (path: string, payload: unknown, version?: number) => {
    void command(path, payload, version).catch(() => undefined);
  };
  return (
    <div className="scopePanel">
      <h3>3D Model · fuentes y versiones</h3>
      <p>
        GUID es identidad estable cuando existe; ExpressID pertenece solo a una versión. El original IFC se conserva
        inmutable.
      </p>
      {can("model.import") ? (
        <form onSubmit={(event) => void stage(event)} className="scopeForm">
          <label>
            Código del modelo
            <input required value={modelCode} onChange={(event) => setModelCode(event.target.value)} />
          </label>
          <label>
            Archivo IFC
            <input
              required
              aria-label="Archivo IFC"
              type="file"
              accept=".ifc"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <label>
            Motivo de importación
            <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <button disabled={busy || !file} type="submit">
            Importar IFC a staging
          </button>
        </form>
      ) : null}
      <label>
        Modelo y versión
        <select
          aria-label="Modelo y versión"
          value={model?.id ?? ""}
          onChange={(event) => {
            setSelectedId(Number(event.target.value));
            setSelectedObjects([]);
            setInspected(null);
          }}
        >
          <option value="">Sin modelo</option>
          {data.models.map((item) => (
            <option key={item.id} value={item.id}>
              {item.model_code} · r{item.revision} · {item.status}
              {item.is_current ? " · CURRENT" : ""}
            </option>
          ))}
        </select>
      </label>
      {model ? (
        <>
          <dl className="scopeFacts">
            <div>
              <dt>Archivo</dt>
              <dd>{model.source_file_name}</dd>
            </div>
            <div>
              <dt>Schema / unidades</dt>
              <dd>
                {model.schema} / {modelUnitCode(model)}
              </dd>
            </div>
            <div>
              <dt>Objetos</dt>
              <dd>{model.object_count}</dd>
            </div>
            <div>
              <dt>Fuente SHA256</dt>
              <dd className="scopeHash">{model.source_hash}</dd>
            </div>
          </dl>
          <details>
            <summary>Validación y comparación con versión anterior</summary>
            <pre>{JSON.stringify({ validation: model.validation_summary, diff: model.diff }, null, 2)}</pre>
          </details>
          <div className="scopeActions">
            <label>
              Motivo de revisión / aceptación
              <input minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            {["review", "accept", "reject"].map((action) =>
              can(`model.${action === "reject" ? "accept" : action}`) ? (
                <button
                  key={action}
                  type="button"
                  disabled={busy || reason.trim().length < 8 || ["ACCEPTED", "REJECTED"].includes(model.status)}
                  onClick={() => run(`/models/${model.id}/${action}`, { reason }, model.version)}
                >
                  {action === "review"
                    ? "Revisar versión"
                    : action === "accept"
                      ? "Aceptar versión"
                      : "Rechazar versión"}
                </button>
              ) : null
            )}
          </div>
          <div className="scopeFilters">
            <label>
              Nombre / GUID / área / zona / sistema
              <input value={filter} onChange={(event) => setFilter(event.target.value)} />
            </label>
            <label>
              Disciplina
              <select value={discipline} onChange={(event) => setDiscipline(event.target.value)}>
                <option value="">Todas</option>
                {[...new Set(objects.map((item) => item.discipline).filter(Boolean))].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label>
              Clasificación
              <select value={classification} onChange={(event) => setClassification(event.target.value)}>
                <option value="">Todas</option>
                {[...new Set(objects.map((item) => item.ifc_class).filter(Boolean))].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label>
              Mapeo
              <select value={mapping} onChange={(event) => setMapping(event.target.value)}>
                <option value="all">Todos</option>
                <option value="scope">Con Scope</option>
                <option value="plan">Con Plan Item</option>
                <option value="unmapped">Sin Scope</option>
              </select>
            </label>
          </div>
          <div className="scopeTable">
            <table>
              <thead>
                <tr>
                  <th>Selección</th>
                  <th>Objeto</th>
                  <th>GUID / ExpressID</th>
                  <th>Clase</th>
                  <th>Scope / Plan</th>
                  <th>Properties</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((object) => (
                  <tr key={object.id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Seleccionar BIM ${object.name}`}
                        checked={selectedObjects.includes(object.id)}
                        onChange={(event) =>
                          setSelectedObjects((current) =>
                            event.target.checked ? [...current, object.id] : current.filter((id) => id !== object.id)
                          )
                        }
                      />
                    </td>
                    <td>{object.name}</td>
                    <td>
                      {object.guid || "Sin GUID"}
                      <small>
                        #{object.express_id} · versión {model.id}
                      </small>
                    </td>
                    <td>{object.ifc_class}</td>
                    <td>
                      {object.scope_item_ids?.length ?? 0} / {object.plan_item_ids?.length ?? 0}
                    </td>
                    <td>
                      <button type="button" onClick={() => setInspected(object)}>
                        Inspeccionar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {inspected ? (
            <details open>
              <summary>Properties · {inspected.name}</summary>
              <pre>{JSON.stringify(inspected, null, 2)}</pre>
            </details>
          ) : null}
          {can("item.edit") ? (
            <form
              className="scopeForm"
              onSubmit={(event) => {
                event.preventDefault();
                run("/items", {
                  scope_code: scopeCode,
                  name: scopeName,
                  scope_nature: scopeNature,
                  quantity: Number(quantity),
                  unit,
                  source_type: "IFC",
                  source_reference: `MODEL_VERSION:${model.id}`,
                  model_object_ids: selectedObjects,
                  measurement_method:
                    sourceQuantity === "SOURCE_OBJECT_COUNT" ? "SOURCE_OBJECT_COUNT" : "IFC_PUBLISHED_QUANTITY",
                  ...(sourceQuantity === "SOURCE_OBJECT_COUNT" ? {} : { source_quantity_name: sourceQuantity }),
                  reason,
                });
              }}
            >
              <label>
                Scope Code desde BIM
                <input required value={scopeCode} onChange={(event) => setScopeCode(event.target.value)} />
              </label>
              <label>
                Scope Name desde BIM
                <input required value={scopeName} onChange={(event) => setScopeName(event.target.value)} />
              </label>
              <label>
                Scope Nature
                <select value={scopeNature} onChange={(event) => setScopeNature(event.target.value)}>
                  {["INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
              <label>
                Cantidad Scope
                <input
                  required
                  type="number"
                  min="0"
                  step="any"
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                />
              </label>
              <label>
                Medición fuente IFC
                <select
                  value={sourceQuantity}
                  onChange={(event) => {
                    setSourceQuantity(event.target.value);
                    if (event.target.value === "SOURCE_OBJECT_COUNT") setUnit("ea");
                  }}
                >
                  <option value="SOURCE_OBJECT_COUNT">Conteo explícito de objetos · ea</option>
                  {[
                    ...new Set(
                      objects
                        .filter((object) => selectedObjects.includes(object.id))
                        .flatMap((object) =>
                          Array.isArray(object.quantities)
                            ? object.quantities
                                .map((entry: Record<string, unknown>) => String(entry.name ?? ""))
                                .filter(Boolean)
                            : []
                        )
                    ),
                  ].map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
              <label>
                Unidad Scope
                <input required value={unit} onChange={(event) => setUnit(event.target.value)} />
              </label>
              <button type="submit" disabled={busy || !selectedObjects.length || model.status !== "ACCEPTED"}>
                Crear Scope desde selección BIM
              </button>
            </form>
          ) : null}
          <p>
            {selectedObjects.length
              ? "Selección aislada en la representación visual. El IFC original no cambia."
              : "Selecciona objetos para aislar y definir vínculos M:N con Scope."}
          </p>
          {viewerModel && provider ? (
            <BimIfcModelViewer
              key={model.id}
              projectId={workspaceId}
              token={token}
              model={viewerModel}
              lines={viewerLines}
              sourceProvider={provider}
              isolatedRefs={isolatedRefs}
              sourceLoadDisabled
              clearModelDisabled
              informationContent={
                <p>
                  Fuente canónica de Scope · versión {model.id}. Solo lectura; no aprobación de cantidades, APU ni
                  Scope.
                </p>
              }
            />
          ) : null}
        </>
      ) : (
        <p>No hay fuentes IFC. Scope también puede comenzar con Excel o creación manual.</p>
      )}
    </div>
  );
}
