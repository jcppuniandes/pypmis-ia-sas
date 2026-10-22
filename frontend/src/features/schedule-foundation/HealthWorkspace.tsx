import { useEffect, useState } from "react";
import { operationalError } from "../operational-context/commands";
import type { JsonRecord, WorkspaceProps } from "./types";

export default function HealthWorkspace({
  selected,
  query,
}: WorkspaceProps & { query?: (versionId: number) => Promise<JsonRecord> }) {
  const [result, setResult] = useState<{ id: number; version: number; health?: JsonRecord; error?: string } | null>(
    null
  );
  useEffect(() => {
    if (!selected || !query) return;
    let active = true;
    query(selected.id)
      .then((health) => {
        if (active) setResult({ id: selected.id, version: selected.version, health });
      })
      .catch((caught) => {
        if (active) setResult({ id: selected.id, version: selected.version, error: operationalError(caught) });
      });
    return () => {
      active = false;
    };
  }, [selected, query]);
  const currentResult = result?.id === selected?.id && result?.version === selected?.version ? result : null;
  return (
    <section className="schedulePanel">
      <h3>Schedule Health</h3>
      <p>
        La calidad del cronograma evalúa extremos abiertos, calendarios, restricciones, lags, duraciones, actuals y
        trazabilidad. Estos controles no calculan CPM, float ni fechas Early/Late.
      </p>
      {currentResult?.error ? (
        <p role="alert">
          No se pudo actualizar Schedule Health: {currentResult.error}. Se muestra la última evidencia guardada.
        </p>
      ) : null}
      <details className="scheduleDetails" open>
        <summary>Resultado de validación de calidad según Schedule Profile</summary>
        <pre>
          {JSON.stringify(
            currentResult?.health ??
              selected?.health_json ?? { status: "UNKNOWN", reason: "Selecciona una versión validada." },
            null,
            2
          )}
        </pre>
      </details>
      <details className="scheduleDetails">
        <summary>Contrato futuro de Look-Ahead</summary>
        <p>
          Consulta de horizonte por defecto de cuatro semanas y configuración explícita; usa fechas y criticidad de la
          fuente junto a referencias Scope/Plan. No se implementa todavía el ciclo completo de Look-Ahead ni resolución
          de restricciones.
        </p>
      </details>
    </section>
  );
}
