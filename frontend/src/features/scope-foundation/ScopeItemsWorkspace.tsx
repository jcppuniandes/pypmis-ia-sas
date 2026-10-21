import { useState, type FormEvent } from "react";
import type { Command, ScopeItem, ScopeOverview } from "./types";

const emptyItem = {
  scope_code: "",
  name: "",
  description: "",
  parent_scope_item_id: "",
  scope_type: "DELIVERABLE",
  scope_nature: "INSTALL",
  discipline: "",
  area: "",
  zone: "",
  system: "",
  location: "",
  quantity: "1",
  unit: "ea",
  measurement_method: "MANUAL_MEASUREMENT",
  source_reference: "",
};
export default function ScopeItemsWorkspace({
  data,
  busy,
  command,
  can,
  upload,
}: {
  data: ScopeOverview;
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
  const [draft, setDraft] = useState(emptyItem);
  const [selected, setSelected] = useState<ScopeItem | null>(null);
  const [predecessor, setPredecessor] = useState<ScopeItem | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fieldMapping, setFieldMapping] = useState("{}");
  const [reason, setReason] = useState("");
  const [revisionCode, setRevisionCode] = useState("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [removedIds, setRemovedIds] = useState<number[]>([]);
  const [filter, setFilter] = useState("");
  const [nature, setNature] = useState("");
  const [tree, setTree] = useState(false);
  const [detail, setDetail] = useState<unknown>(null);
  const run = (path: string, payload: unknown, version?: number, method?: "POST" | "PUT") => {
    void command(path, payload, version, method).catch(() => undefined);
  };
  const setField = (key: keyof typeof emptyItem, value: string) =>
    setDraft((current) => ({ ...current, [key]: value }));
  function select(item: ScopeItem) {
    setSelected(item);
    setPredecessor(null);
    setDraft(
      Object.fromEntries(
        Object.keys(emptyItem).map((key) => [key, String(item[key as keyof ScopeItem] ?? "")])
      ) as typeof emptyItem
    );
    setDetail(item);
  }
  function save(event: FormEvent) {
    event.preventDefault();
    const origin = selected ?? predecessor;
    run(
      selected ? `/items/${selected.id}` : "/items",
      {
        ...draft,
        parent_scope_item_id: draft.parent_scope_item_id ? Number(draft.parent_scope_item_id) : null,
        quantity: Number(draft.quantity),
        source_type: origin?.source_type ?? "MANUAL",
        source_revision: origin?.source_revision ?? "",
        model_object_ids: origin?.model_object_ids ?? [],
        ...(predecessor ? { predecessor_id: predecessor.id } : {}),
        ...(origin?.lineage_json?.excel
          ? {
              excel_import_id: origin.lineage_json.excel.import_id,
              excel_row_number: origin.lineage_json.excel.row_number,
            }
          : {}),
        ...(origin?.lineage_json?.approved_change_id
          ? { approved_change_id: origin.lineage_json.approved_change_id }
          : {}),
        reason,
      },
      selected?.version,
      selected ? "PUT" : "POST"
    );
  }
  function depth(item: ScopeItem) {
    let parent = item.parent_scope_item_id;
    let level = 0;
    const visited = new Set([item.id]);
    while (parent && !visited.has(parent) && level < 20) {
      visited.add(parent);
      level++;
      parent = data.items.find((row) => row.id === parent)?.parent_scope_item_id ?? null;
    }
    return level;
  }
  const visible = data.items.filter(
    (item) =>
      (!filter ||
        [item.scope_code, item.name, item.source_type, item.area, item.zone, item.system]
          .join(" ")
          .toLowerCase()
          .includes(filter.toLowerCase())) &&
      (!nature || item.scope_nature === nature)
  );
  return (
    <div className="scopePanel">
      <h3>Scope Items · autoridad canónica</h3>
      <div className="scopeFilters">
        <label>
          Buscar Scope
          <input value={filter} onChange={(event) => setFilter(event.target.value)} />
        </label>
        <label>
          Filtrar Nature
          <select value={nature} onChange={(event) => setNature(event.target.value)}>
            <option value="">Todas</option>
            {["INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          <input type="checkbox" checked={tree} onChange={(event) => setTree(event.target.checked)} /> Vista jerárquica
        </label>
      </div>
      <div className="scopeTable">
        <table aria-label="Scope Items table">
          <thead>
            <tr>
              <th>Candidato</th>
              <th>Retirar</th>
              <th>Código / nombre</th>
              <th>Nature</th>
              <th>Cantidad / unidad</th>
              <th>Fuente / revisión</th>
              <th>Estado</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={item.id}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Incluir Scope ${item.scope_code}`}
                    checked={selectedIds.includes(item.id)}
                    disabled={item.status !== "DRAFT"}
                    onChange={(event) =>
                      setSelectedIds((current) =>
                        event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id)
                      )
                    }
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Retirar Scope ${item.scope_code}`}
                    checked={removedIds.includes(item.id)}
                    disabled={item.status !== "APPROVED"}
                    onChange={(event) =>
                      setRemovedIds((current) =>
                        event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id)
                      )
                    }
                  />
                </td>
                <td style={{ paddingLeft: tree ? `${12 + depth(item) * 18}px` : undefined }}>
                  {tree && item.parent_scope_item_id ? "↳ " : ""}
                  {item.scope_code}
                  <strong>{item.name}</strong>
                </td>
                <td>{item.scope_nature}</td>
                <td>
                  {item.quantity} {item.unit}
                  <small>
                    Fuente {item.source_quantity ?? "—"} · aprobada {item.approved_quantity ?? "—"}
                  </small>
                </td>
                <td>
                  {item.source_type}
                  <small>
                    {item.source_reference} · r{item.revision}
                  </small>
                </td>
                <td>
                  {item.status}
                  <small>{item.baseline_reference ? `Baseline #${item.baseline_reference}` : "Sin baseline"}</small>
                </td>
                <td>
                  <button type="button" onClick={() => select(item)}>
                    {can("item.edit") && item.status === "DRAFT" ? "Editar borrador" : "Ver Scope"}
                  </button>
                  {can("item.edit") && item.status === "APPROVED" ? (
                    <button
                      type="button"
                      onClick={() => {
                        select(item);
                        setSelected(null);
                        setPredecessor(item);
                      }}
                    >
                      Preparar Scope sucesor
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {can("item.edit") ? (
        <section>
          <div className="scopeSectionTitle">
            <h4>{selected ? `Scope ${selected.scope_code} · v${selected.version}` : "Nuevo Scope manual"}</h4>
            <button
              type="button"
              onClick={() => {
                setSelected(null);
                setPredecessor(null);
                setDraft(emptyItem);
              }}
            >
              Nuevo Scope
            </button>
          </div>
          <form className="scopeForm" onSubmit={save}>
            {(
              [
                "scope_code",
                "name",
                "description",
                "scope_type",
                "discipline",
                "area",
                "zone",
                "system",
                "location",
                "measurement_method",
                "source_reference",
              ] as const
            ).map((key) => (
              <label key={key}>
                {
                  {
                    scope_code: "Scope Code",
                    name: "Scope Name",
                    description: "Descripción",
                    scope_type: "Scope Type",
                    discipline: "Disciplina",
                    area: "Área",
                    zone: "Zona",
                    system: "Sistema",
                    location: "Ubicación",
                    measurement_method: "Método de medición",
                    source_reference: "Referencia de fuente",
                  }[key]
                }
                <input
                  required={["scope_code", "name", "scope_type"].includes(key)}
                  disabled={busy || Boolean(selected && selected.status !== "DRAFT")}
                  value={draft[key]}
                  onChange={(event) => setField(key, event.target.value)}
                />
              </label>
            ))}
            <label>
              Scope Nature
              <select
                value={draft.scope_nature}
                disabled={busy || Boolean(selected && selected.status !== "DRAFT")}
                onChange={(event) => setField("scope_nature", event.target.value)}
              >
                {["INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label>
              Parent Scope
              <select
                value={draft.parent_scope_item_id}
                onChange={(event) => setField("parent_scope_item_id", event.target.value)}
              >
                <option value="">Sin padre</option>
                {data.items
                  .filter((item) => item.id !== selected?.id)
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.scope_code} · {item.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Quantity
              <input
                required
                min="0"
                step="any"
                type="number"
                value={draft.quantity}
                disabled={busy || Boolean(selected && selected.status !== "DRAFT")}
                onChange={(event) => setField("quantity", event.target.value)}
              />
            </label>
            <label>
              Unit
              <input
                required
                value={draft.unit}
                disabled={busy || Boolean(selected && selected.status !== "DRAFT")}
                onChange={(event) => setField("unit", event.target.value)}
              />
            </label>
            <label>
              Motivo Scope
              <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            <button type="submit" disabled={busy || Boolean(selected && selected.status !== "DRAFT")}>
              {selected ? "Guardar Scope borrador" : "Crear Scope manual"}
            </button>
          </form>
        </section>
      ) : null}
      {detail ? (
        <details>
          <summary>Linaje y detalle Scope</summary>
          <pre>{JSON.stringify(detail, null, 2)}</pre>
        </details>
      ) : null}
      <section>
        <h4>Excel · fuente de primer nivel</h4>
        <p>Excel puede originar Scope sin IFC. No se convierten unidades de forma silenciosa.</p>
        {can("item.edit") ? (
          <form
            className="scopeForm"
            onSubmit={(event) => {
              event.preventDefault();
              if (file) void upload("excel-imports", file, reason, "", fieldMapping);
            }}
          >
            <label>
              Archivo Excel
              <input
                required
                type="file"
                accept=".xlsx,.csv"
                aria-label="Archivo Excel Scope"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>
            <label>
              Motivo Excel
              <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            <label className="scopeWide">
              Mapeo de campos Excel JSON
              <textarea
                rows={3}
                spellCheck={false}
                value={fieldMapping}
                onChange={(event) => setFieldMapping(event.target.value)}
              />
            </label>
            <button type="submit" disabled={busy || !file}>
              Validar Excel y ver staging
            </button>
          </form>
        ) : null}
        <div className="scopeTable">
          <table aria-label="Excel staging">
            <thead>
              <tr>
                <th>Archivo</th>
                <th>Estado</th>
                <th>Filas</th>
                <th>Validación</th>
                <th>Candidato</th>
              </tr>
            </thead>
            <tbody>
              {data.imports.map((stage) => (
                <tr key={stage.id}>
                  <td>
                    {stage.source_file_name}
                    <small className="scopeHash">{stage.source_hash}</small>
                  </td>
                  <td>{stage.status}</td>
                  <td>{stage.row_count ?? stage.rows_json?.length ?? "—"}</td>
                  <td>
                    <details>
                      <summary>Preview y errores</summary>
                      <pre>{JSON.stringify(stage, null, 2)}</pre>
                    </details>
                  </td>
                  <td>
                    {can("item.edit") ? (
                      <button
                        type="button"
                        disabled={
                          busy ||
                          reason.trim().length < 8 ||
                          ["IMPORTED", "ACCEPTED", "CANDIDATE"].includes(stage.status)
                        }
                        onClick={() => run(`/excel-imports/${stage.id}/candidate`, { reason }, stage.version)}
                      >
                        Crear candidato desde Excel
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section>
        <h4>Scope Revision y Approved Scope Baseline</h4>
        <p>
          La revisión agrupa altas, bajas y modificaciones. Preparación, revisión y aprobación son actos separados; el
          baseline original permanece inmutable.
        </p>
        {can("revision.prepare") ? (
          <form
            className="scopeForm"
            onSubmit={(event) => {
              event.preventDefault();
              run("/revisions", {
                revision_code: revisionCode,
                reason,
                ...(selectedIds.length ? { item_ids: selectedIds } : {}),
                removed_scope_item_ids: removedIds,
              });
            }}
          >
            <label>
              Revision Code
              <input required value={revisionCode} onChange={(event) => setRevisionCode(event.target.value)} />
            </label>
            <label>
              Motivo revisión
              <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            <button disabled={busy} type="submit">
              Preparar Scope Revision
            </button>
          </form>
        ) : null}
        <div className="scopeTable">
          <table aria-label="Scope Revisions">
            <thead>
              <tr>
                <th>Revisión</th>
                <th>Estado</th>
                <th>Preparador / revisor</th>
                <th>Contenido y cambios</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {data.revisions.map((revision) => (
                <tr key={revision.id}>
                  <td>
                    {revision.revision_code}
                    <small>v{revision.version}</small>
                  </td>
                  <td>{revision.status}</td>
                  <td>
                    {revision.prepared_by ?? revision.created_by ?? "—"} / {revision.reviewed_by ?? "—"}
                  </td>
                  <td>
                    <details>
                      <summary>Diff y hash</summary>
                      <pre>{JSON.stringify(revision, null, 2)}</pre>
                    </details>
                  </td>
                  <td>
                    {["submit", "review", "approve"].map((action) =>
                      can(`revision.${action}`) ? (
                        <button
                          key={action}
                          disabled={
                            busy ||
                            reason.trim().length < 8 ||
                            (action === "submit"
                              ? revision.status !== "DRAFT"
                              : action === "review"
                                ? revision.status !== "SUBMITTED"
                                : revision.status !== "REVIEWED")
                          }
                          type="button"
                          onClick={() => run(`/revisions/${revision.id}/${action}`, { reason }, revision.version)}
                        >
                          {action === "submit"
                            ? "Enviar revisión"
                            : action === "review"
                              ? "Revisar Scope"
                              : "Aprobar Scope Baseline"}
                        </button>
                      ) : null
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="scopeTable">
          <table aria-label="Approved Scope Baselines">
            <thead>
              <tr>
                <th>Baseline</th>
                <th>Original</th>
                <th>Current Approved</th>
                <th>Revisión</th>
                <th>Snapshot inmutable</th>
              </tr>
            </thead>
            <tbody>
              {data.baselines.map((baseline) => (
                <tr key={baseline.id}>
                  <td>{baseline.baseline_code ?? baseline.id}</td>
                  <td>{baseline.is_original ? "ORIGINAL" : "Sucesor"}</td>
                  <td>{baseline.is_current ? "CURRENT" : "Histórico"}</td>
                  <td>#{baseline.revision_id}</td>
                  <td>
                    <details>
                      <summary>Snapshot y hash</summary>
                      <pre>{JSON.stringify(baseline, null, 2)}</pre>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
