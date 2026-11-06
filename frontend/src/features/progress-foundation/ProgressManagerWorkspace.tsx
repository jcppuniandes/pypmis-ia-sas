import { useCallback, useEffect, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { operationalError, useOperationalCommandKeys } from "../operational-context/commands";
import { progressApi } from "./api";
import { Facts, Input, Select } from "./Fields";
import { BaselineIntegrationPanel, PeriodReviewPanel } from "./IntegrationPanels";
import MeasurementsPanel from "./MeasurementsPanel";
import { AggregationPanel, EvmPanel, HistoryPanel, OverlayPanel, ProjectionPanel } from "./ReadPanels";
import RulesPanel from "./RulesPanel";
import { progressTabs, text, type ProgressCommand, type ProgressOverview, type ProgressPanelProps } from "./types";
import "./progressFoundation.css";

export default function ProgressManagerWorkspace({
  token,
  workspaceId,
  readOnly = false,
}: {
  token: string;
  workspaceId: number;
  readOnly?: boolean;
}) {
  const [tab, setTab] = useState<(typeof progressTabs)[number]>("Progress Overview");
  const [data, setData] = useState<ProgressOverview | null>(null);
  const [periodId, setPeriodId] = useState("");
  const [asOf, setAsOf] = useState("");
  const [bundleId, setBundleId] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const keys = useOperationalCommandKeys();
  const query = useCallback((path: string) => progressApi.query(token, workspaceId, path), [token, workspaceId]);
  const load = useCallback(async () => setData(await progressApi.overview(token, workspaceId)), [token, workspaceId]);
  useEffect(() => {
    let active = true;
    progressApi
      .overview(token, workspaceId)
      .then((result) => active && setData(result))
      .catch((caught) => active && setError(operationalError(caught)));
    return () => {
      active = false;
    };
  }, [token, workspaceId]);
  const command: ProgressCommand = async (path, payload, version, method) => {
    if (readOnly) throw new Error("Workspace archivado: Progress de solo lectura.");
    setBusy(true);
    setError("");
    setMessage("");
    const fingerprint = { workspaceId, path, payload, version, method };
    try {
      const result = await progressApi.command(
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
      setMessage("Operación Progress registrada. Scope, Schedule, Cost e IFC conservan sus autoridades y fuentes.");
      return result;
    } catch (caught) {
      setError(operationalError(caught));
      throw caught;
    } finally {
      setBusy(false);
    }
  };
  const props: ProgressPanelProps | null = data
    ? {
        data,
        busy,
        reason,
        periodId,
        asOf,
        query,
        command,
        can: (action) =>
          (!readOnly || ["read", "evm.view"].includes(action)) &&
          data.allowed_actions.some((value) => value === action || value === `progress.${action}`),
      }
    : null;
  const period = data?.periods.find((row) => text(row, "id") === periodId);
  return (
    <section className="progressFoundation" aria-label="Progress Manager" aria-busy={busy}>
      <CompactModuleHeader
        title="Progress Manager"
        eyebrow="USER MODE · CANONICAL PROJECT · O1B-D"
        tone="user"
        description="Mediciones y aprobación del avance, integración de baselines y fundamento EVM sin redefinir Scope, P6 ni Cost."
        metrics={[
          { label: "Measurements", value: data?.measurements.length ?? 0 },
          { label: "Approved", value: data?.measurements.filter((row) => row.status === "APPROVED").length ?? 0 },
          { label: "Bundles", value: data?.baseline_bundles?.length ?? 0 },
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
            Actualizar Progress
          </button>
        }
      />
      {error ? (
        <p role="alert" className="progressError">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="progressNotice">
          {message}
        </p>
      ) : null}
      {!data && !error ? <p role="status">Cargando Progress canónico…</p> : null}
      {props ? (
        <>
          {readOnly ? <p className="progressWarning">Workspace archivado · Progress de solo lectura.</p> : null}
          <p className="progressBoundary">
            Physical ≠ Quantity ≠ Schedule ≠ Cost ≠ Earned. P6, facturas, pagos y compromisos no generan avance físico
            automáticamente.
          </p>
          <div className="progressForm">
            <Select
              label="Progress Controls Period"
              value={periodId}
              onChange={setPeriodId}
              options={data!.periods}
              required
            />
            <Input label="Progress as-of date" type="date" value={asOf} onChange={setAsOf} required />
            <Input label="Motivo Progress" value={reason} onChange={setReason} disabled={readOnly} />
          </div>
          {period ? (
            <Facts
              values={[
                ["Período", period.period_code],
                ["Estado", period.status],
                ["Cutoff de controles", period.cutoff_at],
                ["Schedule Data Date", period.schedule_data_date],
              ]}
            />
          ) : null}
          <nav className="progressTabs" aria-label="Progress Manager submodules">
            {progressTabs.map((title) => (
              <button key={title} type="button" aria-pressed={tab === title} onClick={() => setTab(title)}>
                {title}
              </button>
            ))}
          </nav>
          {tab === "Progress Overview" ? (
            <>
              <AggregationPanel {...props} />
              <MeasurementsPanel {...props} key="WEIGHTED" progressType="WEIGHTED" />
              <OverlayPanel {...props} bundleId={bundleId} setBundleId={setBundleId} />
            </>
          ) : null}
          {tab === "Quantity Progress" ? <MeasurementsPanel {...props} key="QUANTITY" progressType="QUANTITY" /> : null}
          {tab === "Physical Progress" ? <MeasurementsPanel {...props} key="PHYSICAL" progressType="PHYSICAL" /> : null}
          {tab === "Schedule Progress" ? <ProjectionPanel {...props} kind="SCHEDULE" /> : null}
          {tab === "Cost Progress" ? <ProjectionPanel {...props} kind="COST" /> : null}
          {tab === "Earned Progress" ? <EvmPanel {...props} bundleId={bundleId} setBundleId={setBundleId} /> : null}
          {tab === "Milestones / Rules of Credit" ? (
            <>
              <RulesPanel {...props} />
              <MeasurementsPanel {...props} key="MILESTONE" progressType="MILESTONE" />
            </>
          ) : null}
          {tab === "Period Review" ? <PeriodReviewPanel {...props} setPeriodId={setPeriodId} /> : null}
          {tab === "Baseline Integration" ? (
            <BaselineIntegrationPanel {...props} bundleId={bundleId} setBundleId={setBundleId} />
          ) : null}
          {tab === "Progress History" ? <HistoryPanel {...props} /> : null}
        </>
      ) : null}
    </section>
  );
}
