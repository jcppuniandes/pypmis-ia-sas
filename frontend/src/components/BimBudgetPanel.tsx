import { useMemo, useState } from "react";
import { Download, Plus, Search, TableProperties } from "lucide-react";
import { buildBimBudget, buildBimBudgetExcelXml, type BimBudgetRow } from "../lib/bimBudget";
import type { ApuResourceLine, QuantityControlCodeAssignment, QuantityTakeoffLine } from "../types";

type BimBudgetPanelProps = {
  currency: string;
  lines: QuantityTakeoffLine[];
  onOpenQuantities: () => void;
  onUpdateBudgetItem?: (payload: QuantityControlCodeAssignment) => void | Promise<void>;
  projectCode: string;
  projectName: string;
};

type ApuEditorState = {
  key: string;
  resources: ApuResourceLine[];
  row: BimBudgetRow;
};

function currency(value: number, code: string) {
  return new Intl.NumberFormat("es-CO", {
    currency: code || "COP",
    maximumFractionDigits: 2,
    style: "currency",
  }).format(value || 0);
}

function quantity(value: number, unit: string) {
  return `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 4 }).format(value)} ${unit}`;
}

function safeFileName(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
}

export default function BimBudgetPanel({
  currency: projectCurrency,
  lines,
  onOpenQuantities,
  onUpdateBudgetItem,
  projectCode,
  projectName,
}: BimBudgetPanelProps) {
  const [search, setSearch] = useState("");
  const [apuEditor, setApuEditor] = useState<ApuEditorState | null>(null);
  const summary = useMemo(() => buildBimBudget(lines, projectCurrency || "COP"), [lines, projectCurrency]);
  const normalizedSearch = search.trim().toLowerCase();
  const visibleRows = normalizedSearch
    ? summary.rows.filter((row) =>
        [row.code, row.name, row.wbsCode, row.cbsCode, row.fbsCode, row.packageCode, row.elementRefs.join(" ")]
          .join(" ")
          .toLowerCase()
          .includes(normalizedSearch)
      )
    : summary.rows;

  function exportExcel() {
    const workbook = buildBimBudgetExcelXml(summary, { projectCode, projectName });
    const blob = new Blob([workbook], { type: "application/vnd.ms-excel;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `presupuesto-bim-${safeFileName(projectCode || projectName || "proyecto")}.xls`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const gateLabel =
    summary.gate === "ready"
      ? "Listo para revisión presupuestal"
      : summary.gate === "review"
        ? summary.missingAssignmentCount > 0 || !summary.rows.length
          ? "Presupuesto pendiente de completar"
          : "Requiere revisión presupuestal"
        : "Bloqueado por calidad";

  function rowKey(row: BimBudgetRow) {
    return `${row.code}-${row.wbsCode}-${row.cbsCode}-${row.unit}-${row.unitRate}`;
  }

  function startApuEdit(row: BimBudgetRow) {
    setApuEditor({
      key: rowKey(row),
      resources: row.apuStructure.map((resource) => ({ ...resource })),
      row,
    });
  }

  function updateApuResource(index: number, field: keyof ApuResourceLine, value: string) {
    setApuEditor((current) => {
      if (!current) return current;
      const resources = current.resources.map((resource, resourceIndex) => {
        if (resourceIndex !== index) return resource;
        const next = { ...resource };
        if (field === "quantity" || field === "unit_rate") {
          const numericValue = Number(value);
          next[field] = Number.isFinite(numericValue) ? numericValue : 0;
          next.amount = Math.round(next.quantity * next.unit_rate * 100) / 100;
        } else if (field === "component" || field === "description" || field === "unit") {
          next[field] = value;
        }
        return next;
      });
      return { ...current, resources };
    });
  }

  function addApuResource() {
    setApuEditor((current) =>
      current
        ? {
            ...current,
            resources: [
              ...current.resources,
              {
                amount: 0,
                component: "AIU",
                component_type: "AIU",
                description: "Administracion, imprevistos o utilidad",
                quantity: 1,
                status: "review",
                unit: current.row.unit,
                unit_rate: 0,
              },
            ],
          }
        : current
    );
  }

  function saveApuStructure() {
    if (!apuEditor || !onUpdateBudgetItem) return;
    const resources = apuEditor.resources.map((resource) => ({
      ...resource,
      amount: Math.round(resource.quantity * resource.unit_rate * 100) / 100,
    }));
    const unitRate = Math.round(resources.reduce((total, resource) => total + resource.amount, 0) * 100) / 100;
    const row = apuEditor.row;
    onUpdateBudgetItem({
      apu_structure: resources,
      budget_unit: row.unit,
      cbs_code: row.cbsCode,
      cost_item_code: row.code,
      cost_item_name: row.name,
      currency: row.currency,
      fbs_code: row.fbsCode,
      line_ids: row.lineIds,
      note: `Actualizacion de estructura APU ${row.code || row.name}`,
      package_code: row.packageCode,
      source_key: row.sourceKey,
      source_url: row.sourceUrl,
      structure_note: "Estructura APU editada y recalculada desde Presupuesto BIM.",
      structure_status: "user_edited",
      unit_rate: unitRate,
      wbs_code: row.wbsCode,
    });
    setApuEditor(null);
  }

  return (
    <section aria-label="Presupuesto BIM" className="bimBudgetPanel workspaceSection">
      <div className="panelHeader">
        <div>
          <h2>
            <TableProperties size={20} /> Presupuesto BIM
          </h2>
          <span>IFC → cantidad controlada → partida APU → presupuesto trazable</span>
        </div>
        <div className="bimBudgetActions">
          <button className="workflowAction" onClick={onOpenQuantities} type="button">
            Ver cantidades fuente
          </button>
          <button
            className="workflowAction primary"
            disabled={!summary.rows.length}
            onClick={exportExcel}
            type="button"
          >
            <Download size={16} /> Exportar Excel
          </button>
        </div>
      </div>

      <div className="bimBudgetSummary">
        <article>
          <span>Partidas consolidadas</span>
          <strong>{summary.rows.length}</strong>
          <small>
            {summary.assignedLineCount}/{summary.sourceLineCount} líneas con precio
          </small>
        </article>
        <article>
          <span>Total presupuesto</span>
          <strong>
            {!summary.currencyTotals.length
              ? "Sin valor"
              : summary.currencyTotals.length === 1
                ? currency(summary.currencyTotals[0].amount, summary.currencyTotals[0].currency)
                : `${summary.currencyTotals.length} monedas`}
          </strong>
          <small>
            {summary.currencyTotals.map((total) => currency(total.amount, total.currency)).join(" / ") || "Sin valor"}
          </small>
        </article>
        <article className={summary.missingAssignmentCount ? "risk" : ""}>
          <span>Sin partida/APU</span>
          <strong>{summary.missingAssignmentCount}</strong>
          <small>Se completan desde BIM Manager</small>
        </article>
        <article className={summary.duplicateLineCount || summary.unitConflictCount ? "risk" : ""}>
          <span>Control de calidad</span>
          <strong>{summary.duplicateLineCount + summary.unitConflictCount}</strong>
          <small>
            {summary.duplicateLineCount} duplicados / {summary.unitConflictCount} conflictos de unidad
          </small>
        </article>
      </div>

      <div className={`bimBudgetGate ${summary.gate}`} role="status">
        <strong>{gateLabel}</strong>
        <span>
          {summary.gate === "ready"
            ? "Las partidas tienen cantidad, unidad, precio y trazabilidad de control."
            : summary.gate === "blocked"
              ? "Corrige cantidades duplicadas o unidades incompatibles antes de aprobar el presupuesto."
              : "Asigna las partidas APU y precios unitarios faltantes para completar el presupuesto."}
        </span>
      </div>

      <label className="bimBudgetSearch">
        <Search size={16} />
        <span>Buscar partida, WBS, CBS o elemento</span>
        <input onChange={(event) => setSearch(event.target.value)} value={search} />
      </label>

      {visibleRows.length ? (
        <div className="bimBudgetTableWrap">
          <table>
            <thead>
              <tr>
                <th>Partida / APU</th>
                <th>Control</th>
                <th>Cantidad</th>
                <th>Precio unitario</th>
                <th>Total</th>
                <th>Trazabilidad BIM</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => (
                <tr key={rowKey(row)}>
                  <td>
                    <strong>{row.code || "Código pendiente"}</strong>
                    <span>{row.name || "Partida pendiente"}</span>
                    <details className="bimBudgetApuDetails">
                      <summary>Estructura APU ({row.apuStructure.length})</summary>
                      {row.apuStructure.map((resource, index) => (
                        <div key={`${row.code}-${resource.component}-${index}`}>
                          <strong>{resource.component}</strong>
                          <span>{resource.description}</span>
                          <small>
                            {quantity(resource.quantity, resource.unit)} × {currency(resource.unit_rate, row.currency)}{" "}
                            = {currency(resource.amount, row.currency)}
                          </small>
                        </div>
                      ))}
                    </details>
                    {onUpdateBudgetItem && (
                      <button
                        aria-label={`Editar estructura ${row.code || row.name}`}
                        className="bimBudgetEditButton"
                        onClick={() => startApuEdit(row)}
                        type="button"
                      >
                        Editar estructura
                      </button>
                    )}
                    {apuEditor?.key === rowKey(row) && (
                      <div className="bimBudgetApuEditor">
                        {apuEditor.resources.map((resource, index) => (
                          <div className="bimBudgetResourceEditor" key={`${rowKey(row)}-resource-${index}`}>
                            <label>
                              <span>Componente</span>
                              <input
                                aria-label={`Componente recurso ${index + 1}`}
                                onChange={(event) => updateApuResource(index, "component", event.target.value)}
                                value={resource.component}
                              />
                            </label>
                            <label>
                              <span>Descripción</span>
                              <input
                                aria-label={`Descripcion recurso ${index + 1}`}
                                onChange={(event) => updateApuResource(index, "description", event.target.value)}
                                value={resource.description}
                              />
                            </label>
                            <label>
                              <span>Cantidad</span>
                              <input
                                aria-label={`Cantidad recurso ${index + 1}`}
                                min="0"
                                onChange={(event) => updateApuResource(index, "quantity", event.target.value)}
                                step="any"
                                type="number"
                                value={resource.quantity}
                              />
                            </label>
                            <label>
                              <span>Unidad</span>
                              <input
                                aria-label={`Unidad recurso ${index + 1}`}
                                onChange={(event) => updateApuResource(index, "unit", event.target.value)}
                                value={resource.unit}
                              />
                            </label>
                            <label>
                              <span>Precio</span>
                              <input
                                aria-label={`Precio recurso ${index + 1}`}
                                min="0"
                                onChange={(event) => updateApuResource(index, "unit_rate", event.target.value)}
                                step="any"
                                type="number"
                                value={resource.unit_rate}
                              />
                            </label>
                            <strong>{currency(resource.amount, row.currency)}</strong>
                          </div>
                        ))}
                        <div className="bimBudgetEditorActions">
                          <button className="workflowAction" onClick={addApuResource} type="button">
                            <Plus size={15} /> Agregar componente
                          </button>
                          <button className="workflowAction" onClick={() => setApuEditor(null)} type="button">
                            Cancelar
                          </button>
                          <button className="workflowAction primary" onClick={saveApuStructure} type="button">
                            Guardar estructura APU
                          </button>
                        </div>
                      </div>
                    )}
                  </td>
                  <td>
                    <strong>{row.wbsCode || "WBS pendiente"}</strong>
                    <span>{row.cbsCode || "CBS pendiente"}</span>
                    <small>
                      {row.fbsCode || "FBS pendiente"} / {row.packageCode || "Paquete pendiente"}
                    </small>
                  </td>
                  <td>
                    <strong>{quantity(row.quantity, row.unit)}</strong>
                    <span>{row.lineIds.length} línea(s) fuente</span>
                  </td>
                  <td>
                    <strong>{currency(row.unitRate, row.currency)}</strong>
                    <span>por {row.unit}</span>
                  </td>
                  <td>
                    <strong>{currency(row.totalAmount, row.currency)}</strong>
                    <span>{row.status}</span>
                  </td>
                  <td>
                    <strong>{row.elementRefs.length} elemento(s)</strong>
                    <span>{row.elementRefs.slice(0, 3).join(", ")}</span>
                    {row.elementRefs.length > 3 && <small>+{row.elementRefs.length - 3} referencias</small>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="workspaceEmpty compactEmpty">
          <strong>{summary.rows.length ? "No hay coincidencias" : "Presupuesto BIM pendiente"}</strong>
          <span>
            {summary.rows.length
              ? "Limpia el filtro para ver las partidas consolidadas."
              : "Asigna una partida APU y precio unitario desde BIM Manager para construir el presupuesto."}
          </span>
          <button className="workflowAction" onClick={onOpenQuantities} type="button">
            Abrir BIM Manager
          </button>
        </div>
      )}
    </section>
  );
}
