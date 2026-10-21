import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { operationalError, useOperationalCommandKeys } from "../operational-context/commands";
import { scopeApi } from "./api";
import ModelWorkspace from "./ModelWorkspace";
import ScopeItemsWorkspace from "./ScopeItemsWorkspace";
import StrategyWorkspace from "./StrategyWorkspace";
import PlanItemsWorkspace from "./PlanItemsWorkspace";
import type { ScopeOverview, Command } from "./types";
import "./scopeFoundation.css";

const tabs = ["3D Model", "Scope Items", "Strategy & Path of Execution", "Plan Items"] as const;
export default function ScopeManagerWorkspace({ token, workspaceId }: { token: string; workspaceId: number }) {
  const [tab, setTab] = useState<(typeof tabs)[number]>("3D Model");
  const [data, setData] = useState<ScopeOverview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const keys = useOperationalCommandKeys();
  const load = useCallback(async () => setData(await scopeApi.overview(token, workspaceId)), [token, workspaceId]);
  useEffect(() => {
    let active = true;
    scopeApi
      .overview(token, workspaceId)
      .then((result) => active && setData(result))
      .catch((caught) => active && setError(operationalError(caught)));
    return () => {
      active = false;
    };
  }, [token, workspaceId]);
  const command: Command = async (path, payload, version, method) => {
    setBusy(true);
    setError("");
    setMessage("");
    const fingerprint = { workspaceId, path, payload, version, method };
    try {
      const result = await scopeApi.command(
        token,
        workspaceId,
        path,
        payload,
        keys.key(path, fingerprint),
        version,
        method
      );
      keys.complete(path, fingerprint);
      await load();
      setMessage("Operación registrada y contexto actualizado.");
      return result;
    } catch (caught) {
      setError(operationalError(caught));
      throw caught;
    } finally {
      setBusy(false);
    }
  };
  const upload = async (
    kind: "models" | "excel-imports",
    file: File,
    reason: string,
    modelCode = "",
    mapping = "{}"
  ) => {
    setBusy(true);
    setError("");
    setMessage("");
    const fingerprint = {
      workspaceId,
      file: file.name,
      size: file.size,
      modified: file.lastModified,
      reason,
      modelCode,
      mapping,
    };
    try {
      await scopeApi.upload(token, workspaceId, kind, file, reason, keys.key(kind, fingerprint), modelCode, mapping);
      keys.complete(kind, fingerprint);
      await load();
      setMessage("Fuente registrada en staging. Importar no aprueba Scope.");
    } catch (caught) {
      setError(operationalError(caught));
    } finally {
      setBusy(false);
    }
  };
  const can = (action: string) => Boolean(data?.allowed_actions.includes(action));
  return (
    <section className="scopeFoundation" aria-label="Scope Manager" aria-busy={busy}>
      <CompactModuleHeader
        title="Scope Manager"
        eyebrow="USER MODE · CANONICAL PROJECT · O1B-A"
        tone="user"
        description="Scope define qué entregar; la estrategia y Plan Items definen cómo ejecutarlo."
        metrics={[
          { label: "Scope Items", value: data?.items.length ?? 0 },
          { label: "Approved baselines", value: data?.baselines.length ?? 0 },
          { label: "Plan Items", value: data?.plan_items.length ?? 0 },
        ]}
        actions={
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setError("");
              void load().catch((caught) => setError(operationalError(caught)));
            }}
          >
            <RefreshCw size={14} /> Actualizar
          </button>
        }
      />
      {error ? (
        <p role="alert" className="scopeError">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="scopeNotice">
          {message}
        </p>
      ) : null}
      {!data && !error ? <p role="status">Cargando Scope canónico…</p> : null}
      {data ? (
        <>
          <p className="scopeBoundary">
            Workspace canónico #{workspaceId}. Las fuentes IFC/Excel no equivalen a un Scope Baseline aprobado.
            Schedule, Cost, Progress, AWP y 4D no están activos en este incremento.
          </p>
          <nav className="scopeTabs" aria-label="Scope Manager submodules">
            {tabs.map((label) => (
              <button key={label} type="button" aria-pressed={tab === label} onClick={() => setTab(label)}>
                {label}
              </button>
            ))}
          </nav>
          {tab === "3D Model" ? (
            <ModelWorkspace
              data={data}
              token={token}
              workspaceId={workspaceId}
              busy={busy}
              command={command}
              can={can}
              upload={upload}
            />
          ) : null}
          {tab === "Scope Items" ? (
            <ScopeItemsWorkspace data={data} busy={busy} command={command} can={can} upload={upload} />
          ) : null}
          {tab === "Strategy & Path of Execution" ? (
            <StrategyWorkspace data={data} busy={busy} command={command} can={can} />
          ) : null}
          {tab === "Plan Items" ? (
            <PlanItemsWorkspace
              data={data}
              token={token}
              workspaceId={workspaceId}
              busy={busy}
              command={command}
              can={can}
            />
          ) : null}
        </>
      ) : null}
    </section>
  );
}
