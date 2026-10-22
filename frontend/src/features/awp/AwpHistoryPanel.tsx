import { useEffect, useState } from "react";
import { apiFetch } from "../../api/client";
import { operationalError } from "../operational-context/commands";
import { awpProjectRoot } from "./api";
import type { AwpOverview } from "./types";

export default function AwpHistoryPanel({
  token,
  workspaceId,
  data,
}: {
  token: string;
  workspaceId: number;
  data: AwpOverview;
}) {
  const [identity, setIdentity] = useState("");
  const [history, setHistory] = useState<unknown[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    if (!identity) return;
    const [kind, id] = identity.split(":");
    apiFetch<{ items: unknown[] }>(`${awpProjectRoot(workspaceId)}/history/${kind}/${id}`, { token })
      .then((result) => {
        if (active) {
          setHistory(result.items);
          setError("");
        }
      })
      .catch((caught) => active && setError(operationalError(caught)));
    return () => {
      active = false;
    };
  }, [identity, token, workspaceId, data]);
  return (
    <details className="awpPanel">
      <summary>Historial AWP gobernado</summary>
      <label className="awpField">
        <span>Entidad AWP</span>
        <select
          aria-label="AWP history entity"
          value={identity}
          onChange={(event) => {
            setIdentity(event.target.value);
            setHistory([]);
          }}
        >
          <option value="">Seleccionar entidad</option>
          {data.cwas.map((row) => (
            <option key={`c${row.id}`} value={`CWA:${row.id}`}>
              CWA · {row.code}
            </option>
          ))}
          {data.packages.map((row) => (
            <option key={`p${row.id}`} value={`WorkPackage:${row.id}`}>
              Package · {row.package_code}
            </option>
          ))}
          {data.constraints.map((row) => (
            <option key={`x${row.id}`} value={`ExecutionConstraint:${row.id}`}>
              Constraint · {row.code}
            </option>
          ))}
          {data.dependencies.map((row) => (
            <option key={`d${row.id}`} value={`PackageDependency:${row.id}`}>
              Dependency · #{row.id}
            </option>
          ))}
        </select>
      </label>
      {error ? <p role="alert">{error}</p> : null}
      <pre>{JSON.stringify(history, null, 2)}</pre>
    </details>
  );
}
