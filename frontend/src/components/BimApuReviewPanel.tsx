import { useMemo, useState } from "react";
import { CheckCheck, Layers3, WandSparkles } from "lucide-react";
import { buildBimApuReview, type BimApuReviewStatus } from "../lib/bimApuReview";
import type { QuantityTakeoffLine } from "../types";

type BimApuReviewPanelProps = {
  actionDisabled?: boolean;
  lines: QuantityTakeoffLine[];
  onApproveLines: (lineIds: number[]) => void | Promise<void>;
  onOpenBudget: () => void;
  onSuggestLines: (lineIds: number[]) => void | Promise<void>;
};

function quantity(value: number, unit: string) {
  return `${value.toLocaleString("es-CO", { maximumFractionDigits: 4 })} ${unit}`;
}

function currency(value: number, code: string) {
  return new Intl.NumberFormat("es-CO", {
    currency: code || "COP",
    maximumFractionDigits: 2,
    style: "currency",
  }).format(value || 0);
}

function statusLabel(status: BimApuReviewStatus) {
  if (status === "assigned") return "Aprobado";
  if (status === "ready") return "Listo para aprobar";
  if (status === "blocked") return "Medicion no presupuestable";
  if (status === "review") return "Requiere revisión";
  return "Sin sugerencia";
}

export default function BimApuReviewPanel({
  actionDisabled = false,
  lines,
  onApproveLines,
  onOpenBudget,
  onSuggestLines,
}: BimApuReviewPanelProps) {
  const analysis = useMemo(() => buildBimApuReview(lines), [lines]);
  const [selectedGroupKeys, setSelectedGroupKeys] = useState<string[]>([]);
  const selectedGroups = analysis.groups.filter(
    (group) => group.status === "ready" && selectedGroupKeys.includes(group.groupKey)
  );
  const selectedLineIds = Array.from(new Set(selectedGroups.flatMap((group) => group.lineIds)));

  function toggleGroup(groupKey: string) {
    setSelectedGroupKeys((current) =>
      current.includes(groupKey) ? current.filter((key) => key !== groupKey) : [...current, groupKey]
    );
  }

  function selectReadyGroups() {
    setSelectedGroupKeys(analysis.groups.filter((group) => group.status === "ready").map((group) => group.groupKey));
  }

  function approveSelectedGroups() {
    if (!selectedLineIds.length) return;
    onApproveLines(selectedLineIds);
    setSelectedGroupKeys([]);
  }

  return (
    <section aria-label="Revisión masiva de APU" className="bimApuReviewPanel">
      <div className="panelHeader">
        <div>
          <h3>
            <Layers3 size={18} /> Revisión masiva de APU
          </h3>
          <span>Agrupa cantidades compatibles y aprueba partidas sin revisar elemento por elemento.</span>
        </div>
        <div className="bimApuReviewActions">
          <button
            className="workflowAction"
            disabled={actionDisabled || !analysis.pendingLineIds.length}
            onClick={() => onSuggestLines(analysis.pendingLineIds)}
            type="button"
          >
            <WandSparkles size={16} /> Sugerir APU para pendientes
          </button>
          <button
            className="workflowAction"
            disabled={actionDisabled || !analysis.readyGroupCount}
            onClick={selectReadyGroups}
            type="button"
          >
            Seleccionar listos
          </button>
          <button
            className="workflowAction primary"
            disabled={actionDisabled || !selectedLineIds.length}
            onClick={approveSelectedGroups}
            type="button"
          >
            <CheckCheck size={16} /> Aprobar grupos seleccionados
          </button>
          <button className="workflowAction" onClick={onOpenBudget} type="button">
            Abrir Presupuesto BIM
          </button>
        </div>
      </div>

      <div className="bimApuReviewSummary">
        <article>
          <span>Grupos</span>
          <strong>{analysis.groups.length}</strong>
          <small>Agrupados por elemento, ubicación, medida y unidad.</small>
        </article>
        <article>
          <span>Listos para aprobar</span>
          <strong>{analysis.readyGroupCount}</strong>
          <small>Confianza mínima 70% y unidad compatible.</small>
        </article>
        <article className={analysis.reviewGroupCount ? "risk" : ""}>
          <span>Revisión</span>
          <strong>{analysis.reviewGroupCount}</strong>
          <small>Sugerencias distintas, parciales o de baja confianza.</small>
        </article>
        <article className={analysis.blockedGroupCount ? "risk" : ""}>
          <span>Mediciones no presupuestables</span>
          <strong>{analysis.blockedGroupCount}</strong>
          <small>Requieren area, volumen, longitud o una unidad compatible.</small>
        </article>
      </div>

      {analysis.groups.length ? (
        <div className="bimApuReviewTable">
          <table>
            <thead>
              <tr>
                <th aria-label="Seleccionar grupo" />
                <th>Grupo constructivo</th>
                <th>Cantidad IFC</th>
                <th>Partida sugerida</th>
                <th>Confianza / fuente</th>
                <th>IFC vs presupuesto</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {analysis.groups.map((group) => (
                <tr className={group.status} key={group.groupKey}>
                  <td>
                    <input
                      aria-label={`Seleccionar ${group.elementName}`}
                      checked={selectedGroupKeys.includes(group.groupKey)}
                      disabled={actionDisabled || group.status !== "ready"}
                      onChange={() => toggleGroup(group.groupKey)}
                      type="checkbox"
                    />
                  </td>
                  <td>
                    <strong>{group.elementName}</strong>
                    <span>{group.ifcClasses.join(" / ")}</span>
                    <small>
                      {group.lineIds.length} línea(s) / {group.lineIds.length} referencia(s)
                    </small>
                  </td>
                  <td>
                    <strong>{quantity(group.ifcQuantity, group.unit)}</strong>
                    <span>Unidad de medición IFC</span>
                  </td>
                  <td>
                    <strong>{group.costItemCode || "Partida pendiente"}</strong>
                    <span>{group.costItemName || "Ejecuta la sugerencia automática"}</span>
                    {group.unitRate > 0 && (
                      <small>
                        {currency(group.unitRate, group.currency)} / {group.budgetUnit}
                      </small>
                    )}
                  </td>
                  <td>
                    <strong>{group.confidence ? `${group.confidence}%` : "Pendiente"}</strong>
                    <span>{group.sourceKey || "Fuente pendiente"}</span>
                  </td>
                  <td>
                    {group.hasBudgetComparison ? (
                      <>
                        <strong>{quantity(group.quantityVariance, group.budgetUnit || group.unit)}</strong>
                        <span>
                          IFC {quantity(group.ifcQuantity, group.unit)} / Presupuesto{" "}
                          {quantity(group.budgetQuantity, group.budgetUnit || group.unit)}
                        </span>
                      </>
                    ) : (
                      <strong>Pendiente</strong>
                    )}
                  </td>
                  <td>
                    <strong>{statusLabel(group.status)}</strong>
                    <span>
                      {group.blockReason
                        ? group.blockReason
                        : group.status === "pending"
                          ? "Esperando sugerencia"
                          : group.unitCompatible
                            ? "Unidad compatible"
                            : `${group.unit} ≠ ${group.budgetUnit}`}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="workspaceEmpty compactEmpty">
          <strong>Sin grupos de cantidades</strong>
          <span>Carga el IFC o Excel para iniciar la revisión masiva de APU.</span>
        </div>
      )}
    </section>
  );
}
