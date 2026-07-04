import { useState } from "react";
import { Calculator, CheckCheck, Link2 } from "lucide-react";
import type { BimGeometryMeasurementBatch, BimGeometryMeasurementResult, BimModel, QuantityTakeoffRun } from "../types";

type BimGeometryBatchPanelProps = {
  actionDisabled?: boolean;
  modelAvailable: boolean;
  models?: BimModel[];
  modelStatusMessage?: string;
  run?: QuantityTakeoffRun;
  preview: BimGeometryMeasurementBatch | null;
  onAnalyze: () => void | Promise<void>;
  onApply: () => void | Promise<void>;
  onLinkModel?: (modelId: number) => void | Promise<void>;
};

const quantityFormatter = new Intl.NumberFormat("es-CO", {
  maximumFractionDigits: 3,
});

function formatQuantity(quantity: number, unit: string) {
  return `${quantityFormatter.format(quantity)}${unit ? ` ${unit}` : ""}`;
}

function differenceLabel(result: BimGeometryMeasurementResult) {
  if (result.difference === null) return "Unidades no comparables";
  const sign = result.difference > 0 ? "+" : "";
  const percent =
    result.difference_percent === null
      ? ""
      : ` / ${sign}${quantityFormatter.format(result.difference_percent)}%`;
  return `${sign}${quantityFormatter.format(result.difference)}${percent}`;
}

function statusLabel(status: string) {
  return (
    {
      applied: "Aprobada",
      compare: "Solo comparar",
      invalid: "Sin medida",
      ready: "Lista",
      unmatched: "Sin malla",
    }[status] ?? status
  );
}

function shortHash(value: string | undefined) {
  return value ? value.slice(0, 12) : "Sin hash historico";
}

export default function BimGeometryBatchPanel({
  actionDisabled = false,
  modelAvailable,
  models = [],
  modelStatusMessage = "",
  run,
  preview,
  onAnalyze,
  onApply,
  onLinkModel,
}: BimGeometryBatchPanelProps) {
  const readyCount = preview?.ready_count ?? 0;
  const renderedResults = preview?.results.slice(0, 20) ?? [];
  const [selectedModelId, setSelectedModelId] = useState("");
  const effectiveSelectedModelId = models.some((model) => model.id === Number(selectedModelId))
    ? selectedModelId
    : run?.bim_model_id
      ? String(run.bim_model_id)
      : "";
  const selectedModel = models.find((model) => model.id === Number(effectiveSelectedModelId));
  const linkedModel = models.find((model) => model.id === run?.bim_model_id);

  return (
    <section aria-label="Medicion geometrica masiva" className="bimGeometryBatchPanel">
      <div className="panelHeader compactHeader">
        <div>
          <h3>
            <Calculator size={18} /> Medicion geometrica masiva
          </h3>
          <span>Calcula area, volumen o longitud desde las mallas IFC y compara antes de aprobar.</span>
        </div>
        <div className="bimGeometryBatchActions">
          <button
            className="secondaryAction workflowAction"
            disabled={actionDisabled || !modelAvailable}
            onClick={onAnalyze}
            type="button"
          >
            <Calculator size={16} /> Calcular geometria
          </button>
          <button
            className="primaryAction workflowAction"
            disabled={actionDisabled || !modelAvailable || readyCount === 0}
            onClick={onApply}
            type="button"
          >
            <CheckCheck size={16} /> Aprobar {readyCount} medicion{readyCount === 1 ? "" : "es"}
          </button>
        </div>
      </div>

      <div className="bimRevisionLink">
        <div className="bimRevisionFacts">
          <article>
            <span>Fuente de cantidades</span>
            <strong>{run?.source_file_name || "Sin corrida"}</strong>
            <small>SHA-256 {shortHash(run?.source_sha256)}</small>
          </article>
          <article>
            <span>Revision vinculada</span>
            <strong>{run?.bim_revision_id || "Pendiente"}</strong>
            <small>{linkedModel?.source_file_name || "Selecciona el modelo que origino las cantidades."}</small>
          </article>
        </div>
        <label>
          <span>Modelo / revision IFC</span>
          <select
            disabled={actionDisabled || !models.length}
            onChange={(event) => setSelectedModelId(event.target.value)}
            value={effectiveSelectedModelId}
          >
            <option value="">Selecciona una revision</option>
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.revision_id || `Modelo ${model.id}`} - {model.source_file_name}
              </option>
            ))}
          </select>
        </label>
        <button
          className="secondaryAction workflowAction"
          disabled={
            actionDisabled ||
            !onLinkModel ||
            !selectedModel ||
            selectedModel.id === run?.bim_model_id
          }
          onClick={() => selectedModel && onLinkModel?.(selectedModel.id)}
          type="button"
        >
          <Link2 size={16} /> Vincular revision
        </button>
      </div>

      {!modelAvailable ? (
        <div className="bimGeometryBatchEmpty">
          {modelStatusMessage || "Carga un modelo IFC con geometria renderizable para calcular cantidades dimensionales."}
        </div>
      ) : !preview ? (
        <div className="bimGeometryBatchEmpty">
          Ejecuta el calculo para ver diferencias. Ninguna cantidad se modifica durante esta previsualizacion.
        </div>
      ) : (
        <>
          <div className="bimGeometryBatchSummary">
            <article>
              <span>Vinculadas</span>
              <strong>
                {preview.matched_count}/{preview.total_count}
              </strong>
              <small>Lineas encontradas en la cache geometrica.</small>
            </article>
            <article className={preview.ready_count ? "ready" : ""}>
              <span>Listas</span>
              <strong>
                {preview.ready_count} lista{preview.ready_count === 1 ? "" : "s"}
              </strong>
              <small>Mediciones que corrigen cantidades no dimensionales.</small>
            </article>
            <article>
              <span>Comparar</span>
              <strong>{preview.compare_count}</strong>
              <small>Cantidades actuales validas que no se reemplazaran.</small>
            </article>
            <article className={preview.unmatched_count + preview.invalid_count ? "risk" : ""}>
              <span>Sin resultado</span>
              <strong>{preview.unmatched_count + preview.invalid_count}</strong>
              <small>Sin malla vinculada o sin medida geometrica positiva.</small>
            </article>
          </div>

          <div className="bimGeometryBatchTable">
            <table>
              <thead>
                <tr>
                  <th>Elemento</th>
                  <th>Original</th>
                  <th>Geometria IFC</th>
                  <th>Aprobada</th>
                  <th>Diferencia</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {renderedResults.map((result) => (
                  <tr className={result.status} key={result.line_id}>
                    <td>
                      <strong>{result.element_name || result.ifc_class}</strong>
                      <span>{result.ifc_class}</span>
                      <small>{result.element_guid || `Linea ${result.line_id}`}</small>
                    </td>
                    <td>{formatQuantity(result.source_quantity, result.source_unit)}</td>
                    <td>
                      <strong>{formatQuantity(result.geometry_quantity, result.geometry_unit)}</strong>
                      <span>{result.measurement_rule || "Sin regla"}</span>
                    </td>
                    <td>
                      {result.approved_quantity === null
                        ? "Pendiente"
                        : formatQuantity(result.approved_quantity, result.approved_unit)}
                    </td>
                    <td>{differenceLabel(result)}</td>
                    <td>
                      <strong>{statusLabel(result.status)}</strong>
                      <small>{result.reason}</small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {preview.results.length > renderedResults.length ? (
            <small className="bimGeometryBatchFootnote">
              Se muestran las primeras {renderedResults.length} de {preview.results.length} lineas calculadas.
            </small>
          ) : null}
        </>
      )}
    </section>
  );
}
