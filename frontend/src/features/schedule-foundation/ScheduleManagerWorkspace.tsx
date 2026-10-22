import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { operationalError, useOperationalCommandKeys } from "../operational-context/commands";
import { scheduleApi } from "./api";
import { saveScheduleBlob } from "./download";
import RegisterWorkspace from "./RegisterWorkspace";
import WbsWorkspace from "./WbsWorkspace";
import ActivitiesWorkspace from "./ActivitiesWorkspace";
import ReferenceWorkspace from "./ReferenceWorkspace";
import BaselinesWorkspace from "./BaselinesWorkspace";
import ImportExportWorkspace from "./ImportExportWorkspace";
import HealthWorkspace from "./HealthWorkspace";
import FourDWorkspace from "../schedule-four-d/FourDWorkspace";
import { display, type ScheduleCommand, type ScheduleOverview } from "./types";
import "./scheduleFoundation.css";

const tabs = [
  "Schedule Register",
  "WBS",
  "Activities",
  "Calendars",
  "Relationships",
  "Codes & Constraints",
  "Baselines",
  "Import / Export",
  "Schedule Health",
  "4D Model",
] as const;
export default function ScheduleManagerWorkspace({ token, workspaceId }: { token: string; workspaceId: number }) {
  const [tab, setTab] = useState<(typeof tabs)[number]>("Schedule Register");
  const [data, setData] = useState<ScheduleOverview | null>(null);
  const [registerId, setRegisterId] = useState(0);
  const [versionId, setVersionId] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const keys = useOperationalCommandKeys();
  const load = useCallback(async () => setData(await scheduleApi.overview(token, workspaceId)), [token, workspaceId]);
  const queryActivities = useCallback(
    (id: number) => scheduleApi.activities(token, workspaceId, id),
    [token, workspaceId]
  );
  const queryHealth = useCallback((id: number) => scheduleApi.health(token, workspaceId, id), [token, workspaceId]);
  useEffect(() => {
    let active = true;
    scheduleApi
      .overview(token, workspaceId)
      .then((result) => active && setData(result))
      .catch((caught) => active && setError(operationalError(caught)));
    return () => {
      active = false;
    };
  }, [token, workspaceId]);
  const register = data?.registers.find((row) => row.id === registerId) ?? data?.registers[0];
  const versions = data?.versions.filter((row) => row.register_id === register?.id) ?? [];
  const selected =
    versions.find((row) => row.id === versionId) ??
    versions.find((row) => row.id === register?.current_version_id) ??
    versions[versions.length - 1];
  const can = (action: string) => Boolean(data?.allowed_actions.includes(action));
  function selectResult(result: unknown) {
    if (result && typeof result === "object" && "schedule_version" in result) {
      selectResult(result.schedule_version);
      return;
    }
    if (!result || typeof result !== "object" || !("id" in result)) return;
    if ("snapshot_json" in result && "register_id" in result) {
      setVersionId(Number(result.id));
      setRegisterId(Number(result.register_id));
    } else if ("schedule_code" in result) {
      setRegisterId(Number(result.id));
      setVersionId(0);
    }
  }
  const command: ScheduleCommand = async (path, payload, version, method) => {
    setBusy(true);
    setError("");
    setMessage("");
    const fingerprint = { workspaceId, path, payload, version, method };
    try {
      const result = await scheduleApi.command(
        token,
        workspaceId,
        path,
        payload,
        keys.key(path, fingerprint),
        version,
        method
      );
      keys.complete(path, fingerprint);
      selectResult(result);
      await load();
      setMessage("Operación Schedule registrada; las fuentes Scope y los baselines aprobados se conservan.");
      return result;
    } catch (caught) {
      setError(operationalError(caught));
      throw caught;
    } finally {
      setBusy(false);
    }
  };
  async function upload(file: File, reason: string, kind: string) {
    if (!register) return;
    setBusy(true);
    setError("");
    setMessage("");
    const fingerprint = {
      workspaceId,
      registerId: register.id,
      file: file.name,
      size: file.size,
      modified: file.lastModified,
      reason,
      kind,
      version: register.version,
      predecessor: selected?.id,
    };
    try {
      const result = await scheduleApi.upload(
        token,
        workspaceId,
        register.id,
        file,
        reason,
        kind,
        keys.key("schedule.import", fingerprint),
        register.version,
        selected?.id
      );
      keys.complete("schedule.import", fingerprint);
      selectResult(result);
      await load();
      setMessage("Fuente P6 registrada en staging. Aún no es Current ni Baseline aprobado.");
    } catch (caught) {
      setError(operationalError(caught));
    } finally {
      setBusy(false);
    }
  }
  async function download(id: number, filename: string) {
    setError("");
    try {
      const blob = await scheduleApi.download(token, workspaceId, id);
      saveScheduleBlob(blob, filename);
    } catch (caught) {
      setError(operationalError(caught));
    }
  }
  const props = data ? { data, register, selected, busy, can, command } : null;
  return (
    <section className="scheduleFoundation" aria-label="Schedule Manager" aria-busy={busy}>
      <CompactModuleHeader
        title="Schedule Manager"
        eyebrow="USER MODE · CANONICAL PROJECT · O1B-B"
        tone="user"
        description="WBS y Activities consumen Scope y Plan Items aprobados; Primavera P6 conserva la autoridad CPM."
        metrics={[
          { label: "Registers", value: data?.registers.length ?? 0 },
          { label: "Versions", value: data?.versions.length ?? 0 },
          {
            label: "Baselines",
            value: data?.baselines.filter((row) => row.status === "APPROVED_BASELINE").length ?? 0,
          },
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
            <RefreshCw size={14} /> Actualizar Schedule
          </button>
        }
      />
      {error ? (
        <p role="alert" className="scheduleError">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="scheduleNotice">
          {message}
        </p>
      ) : null}
      {!data && !error ? <p role="status">Cargando Schedule canónico…</p> : null}
      {data && props ? (
        <>
          <p className="scheduleBoundary">
            Proyecto canónico #{workspaceId}. Scope define qué entregar; Plan Items definen la descomposición. Schedule
            no aprueba costos ni avance y no calcula CPM. 4D consume las fechas gobernadas sin modificarlas.
          </p>
          <div className="scheduleForm">
            <label>
              Schedule Register activo
              <select
                aria-label="Schedule Register activo"
                value={register?.id ?? ""}
                onChange={(event) => {
                  setRegisterId(Number(event.target.value));
                  setVersionId(0);
                }}
              >
                <option value="" disabled>
                  Seleccionar Schedule Register
                </option>
                {data.registers.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.schedule_code} · {row.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Schedule Version activa
              <select
                aria-label="Schedule Version activa"
                value={selected?.id ?? ""}
                onChange={(event) => setVersionId(Number(event.target.value))}
              >
                <option value="" disabled>
                  Seleccionar versión
                </option>
                {versions.map((row) => (
                  <option key={row.id} value={row.id}>
                    #{row.id} · r{row.revision} · {row.status} · {row.kind} · Data Date {display(row.data_date)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <nav className="scheduleTabs" aria-label="Schedule Manager submodules">
            {tabs.map((label) => (
              <button key={label} type="button" aria-pressed={tab === label} onClick={() => setTab(label)}>
                {label}
              </button>
            ))}
          </nav>
          {tab === "Schedule Register" ? <RegisterWorkspace key={register?.id ?? 0} {...props} /> : null}
          {tab === "WBS" ? <WbsWorkspace key={selected?.id ?? 0} {...props} /> : null}
          {tab === "Activities" ? (
            <ActivitiesWorkspace key={selected?.id ?? 0} {...props} query={queryActivities} />
          ) : null}
          {tab === "Calendars" || tab === "Relationships" || tab === "Codes & Constraints" ? (
            <ReferenceWorkspace {...props} kind={tab} />
          ) : null}
          {tab === "Baselines" ? <BaselinesWorkspace key={selected?.id ?? 0} {...props} /> : null}
          {tab === "Import / Export" ? (
            <ImportExportWorkspace key={register?.id ?? 0} {...props} upload={upload} download={download} />
          ) : null}
          {tab === "Schedule Health" ? <HealthWorkspace {...props} query={queryHealth} /> : null}
          {tab === "4D Model" ? <FourDWorkspace token={token} workspaceId={workspaceId} schedule={data} /> : null}
          <details className="scheduleDetails">
            <summary>Historial Schedule · Current distinto de Baseline</summary>
            <div className="scheduleTable">
              <table aria-label="Schedule version history">
                <thead>
                  <tr>
                    <th>Versión</th>
                    <th>Tipo</th>
                    <th>Estado</th>
                    <th>Data Date</th>
                    <th>Current</th>
                    <th>Baseline</th>
                    <th>Fuente</th>
                  </tr>
                </thead>
                <tbody>
                  {versions.map((row) => (
                    <tr key={row.id}>
                      <td>
                        #{row.id} · r{row.revision}
                      </td>
                      <td>{row.kind}</td>
                      <td>{row.status}</td>
                      <td>{display(row.data_date)}</td>
                      <td>{row.id === register?.current_version_id ? "CURRENT" : "—"}</td>
                      <td>
                        {data.baselines
                          .filter(
                            (baseline) =>
                              baseline.schedule_version_id === row.id && baseline.status === "APPROVED_BASELINE"
                          )
                          .map((baseline) => `${baseline.baseline_type} #${baseline.id}`)
                          .join(", ") || "—"}
                      </td>
                      <td>
                        {row.source_file_name}
                        <small>{row.source_hash}</small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      ) : null}
    </section>
  );
}
