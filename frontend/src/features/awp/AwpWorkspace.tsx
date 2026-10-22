import { useCallback, useEffect, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { operationalError, useOperationalCommandKeys } from "../operational-context/commands";
import CwaPanel from "./CwaPanel";
import PackagesPanel from "./PackagesPanel";
import DependenciesPanel from "./DependenciesPanel";
import ConstraintsPanel from "./ConstraintsPanel";
import ReadinessPanel from "./ReadinessPanel";
import AwpHistoryPanel from "./AwpHistoryPanel";
import { awpApi } from "./api";
import type { AwpCommand, AwpOverview } from "./types";
import "./awp.css";

const tabs = [
  "Construction Work Areas",
  "Work Packages",
  "Package Dependencies",
  "Execution Constraints",
  "Readiness",
] as const;
export default function AwpWorkspace({ token, workspaceId }: { token: string; workspaceId: number }) {
  const [data, setData] = useState<AwpOverview | null>(null);
  const [tab, setTab] = useState<(typeof tabs)[number]>("Construction Work Areas");
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const keys = useOperationalCommandKeys();
  const load = useCallback(async () => setData(await awpApi.overview(token, workspaceId)), [token, workspaceId]);
  useEffect(() => {
    let active = true;
    awpApi
      .overview(token, workspaceId)
      .then((result) => active && setData(result))
      .catch((caught) => active && setError(operationalError(caught)));
    return () => {
      active = false;
    };
  }, [token, workspaceId]);
  const command: AwpCommand = async (path, payload, version, method) => {
    setBusy(true);
    setError("");
    setMessage("");
    const fingerprint = { workspaceId, path, payload, version, method };
    try {
      const result = await awpApi.command(
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
      setMessage("Operación AWP registrada. No se modifican Scope ni Schedule históricos.");
      return result;
    } catch (caught) {
      setError(operationalError(caught));
      throw caught;
    } finally {
      setBusy(false);
    }
  };
  const props = data
    ? { data, busy, reason, command, can: (action: string) => data.allowed_actions.includes(action) }
    : null;
  return (
    <section className="awpWorkspace" aria-label="Project Execution AWP" aria-busy={busy}>
      <CompactModuleHeader
        title="Project Execution / AWP"
        eyebrow="USER MODE · CANONICAL PROJECT · O1B-B.1"
        description="CWA, paquetes y readiness de ejecución; las Activities P6 conservan sus fechas y lógica."
        tone="user"
        metrics={[
          { label: "CWA", value: data?.cwas.length ?? 0 },
          { label: "Packages", value: data?.packages.length ?? 0 },
          { label: "Constraints", value: data?.constraints.length ?? 0 },
        ]}
        actions={
          <button
            type="button"
            disabled={busy}
            onClick={() => void load().catch((caught) => setError(operationalError(caught)))}
          >
            Actualizar AWP
          </button>
        }
      />
      {error ? (
        <p role="alert" className="awpError">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="awpNotice">
          {message}
        </p>
      ) : null}
      {!data && !error ? <p role="status">Cargando AWP…</p> : null}
      {props ? (
        <>
          <p className="awpBoundary">
            Scheduled ≠ Ready · ExecutionConstraint ≠ P6 ScheduleConstraint · READY ≠ RELEASED
          </p>
          <label className="awpField">
            <span>Motivo AWP</span>
            <input aria-label="Motivo AWP" minLength={8} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <nav className="awpTabs" aria-label="AWP submodules">
            {tabs.map((label) => (
              <button key={label} type="button" aria-pressed={tab === label} onClick={() => setTab(label)}>
                {label}
              </button>
            ))}
          </nav>
          {tab === "Construction Work Areas" ? (
            <CwaPanel {...props} />
          ) : tab === "Work Packages" ? (
            <PackagesPanel {...props} />
          ) : tab === "Package Dependencies" ? (
            <DependenciesPanel {...props} />
          ) : tab === "Execution Constraints" ? (
            <ConstraintsPanel {...props} />
          ) : (
            <ReadinessPanel {...props} />
          )}
          <AwpHistoryPanel token={token} workspaceId={workspaceId} data={props.data} />
        </>
      ) : null}
    </section>
  );
}
