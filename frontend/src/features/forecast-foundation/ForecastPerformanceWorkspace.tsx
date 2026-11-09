import { useCallback, useEffect, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { operationalError, useOperationalCommandKeys } from "../operational-context/commands";
import { forecastApi } from "./api";
import AssumptionsPanel from "./AssumptionsPanel";
import ComponentsPanel from "./ComponentsPanel";
import { Evidence, Facts, Input, Records, Select } from "./Fields";
import { CalculationPanel, CurvesPanel, PerformancePanel, TrendsPanel } from "./ReadPanels";
import { LookAheadPanel, ReportsPanel } from "./ReportingPanels";
import {
  draftFromVersion,
  emptyDraft,
  forecastMethods,
  forecastTabs,
  revision,
  text,
  type ForecastCommand,
  type ForecastDraft,
  type ForecastEditorProps,
  type ForecastOverview,
  type ForecastPanelProps,
  type ForecastRecord,
  type ForecastSurface,
} from "./types";
import "../progress-foundation/progressFoundation.css";
import "./forecastFoundation.css";

export default function ForecastPerformanceWorkspace({
  token,
  workspaceId,
  readOnly = false,
}: {
  token: string;
  workspaceId: number;
  readOnly?: boolean;
}) {
  const [tab, setTab] = useState<(typeof forecastTabs)[number]>("Forecast Overview");
  const [data, setData] = useState<ForecastOverview | null>(null);
  const [selected, setSelected] = useState<ForecastRecord | null>(null);
  const [draft, setDraftState] = useState<ForecastDraft>(emptyDraft);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const keys = useOperationalCommandKeys();
  const query = useCallback(
    (path: string, surface: ForecastSurface = "forecast") => forecastApi.query(token, workspaceId, path, surface),
    [token, workspaceId]
  );
  const load = useCallback(async () => {
    const value = await forecastApi.overview(token, workspaceId);
    setData(value);
    return value;
  }, [token, workspaceId]);
  useEffect(() => {
    let active = true;
    forecastApi
      .overview(token, workspaceId)
      .then((value) => active && setData(value))
      .catch((caught) => active && setError(operationalError(caught)));
    return () => {
      active = false;
    };
  }, [token, workspaceId]);
  const setDraft = (value: ForecastDraft) => {
    setDraftState(value);
    setDirty(true);
  };
  async function select(identity: string) {
    setError("");
    setMessage("");
    if (!identity) {
      setSelected(null);
      setDraftState(emptyDraft());
      setDirty(false);
      return;
    }
    setBusy(true);
    try {
      const row = (await query(`/versions/${identity}`)) as ForecastRecord;
      setSelected(row);
      setDraftState(draftFromVersion(row));
      setDirty(false);
    } catch (caught) {
      setError(operationalError(caught));
    } finally {
      setBusy(false);
    }
  }
  const command: ForecastCommand = async (path, payload, version, method = "POST", surface = "forecast") => {
    if (readOnly) throw new Error("Workspace archivado: Forecast de solo lectura.");
    setBusy(true);
    setError("");
    setMessage("");
    const fingerprint = { workspaceId, surface, path, payload, version, method };
    try {
      const result = await forecastApi.command(
        token,
        workspaceId,
        path,
        payload,
        keys.key(`${surface}${path}`, fingerprint),
        version,
        method,
        surface
      );
      keys.complete(`${surface}${path}`, fingerprint);
      await load();
      setMessage(
        "Operación Forecast registrada. Baseline, Current, Actual y Forecast conservan fuentes y autoridades distintas."
      );
      return result;
    } catch (caught) {
      setError(operationalError(caught));
      throw caught;
    } finally {
      setBusy(false);
    }
  };
  const can = (action: string) =>
    (!readOnly ||
      ["read", "eac.view", "dashboard.view", "executive.view", "lookahead.view", "report.read"].includes(action)) &&
    Boolean(data?.allowed_actions.some((value) => value === action || value === `forecast.${action}`));
  const editable = !busy && (selected ? selected.status === "DRAFT" && can("edit") : can("create"));
  const reasonReady = reason.trim().length >= 8;
  const headerReady = Boolean(
    draft.code &&
    draft.name &&
    draft.bundle_id &&
    draft.period_id &&
    draft.as_of &&
    draft.schedule_version_id &&
    draft.currency &&
    draft.evidence_ref &&
    draft.confidence_rationale.trim().length >= 8
  );
  async function save(successor = false) {
    const path =
      successor && selected
        ? `/versions/${selected.id}/successor`
        : selected
          ? `/versions/${selected.id}`
          : "/versions";
    const value = await command(
      path,
      { ...draft, reason },
      selected ? revision(selected) : undefined,
      selected && !successor ? "PUT" : "POST"
    );
    setSelected(value as ForecastRecord);
    setDraftState(draftFromVersion(value as ForecastRecord));
    setDirty(false);
  }
  async function transition(action: string) {
    if (!selected) return;
    const value = await command(`/versions/${selected.id}/transition`, { action, reason }, revision(selected));
    setSelected(value as ForecastRecord);
    setDraftState(draftFromVersion(value as ForecastRecord));
    setDirty(false);
  }
  async function calculate() {
    if (!selected) return;
    const value = (await command(
      `/versions/${selected.id}/calculate`,
      { reason },
      revision(selected)
    )) as ForecastRecord;
    setSelected(value);
    setDraftState(draftFromVersion(value));
    setDirty(false);
  }
  const props: ForecastPanelProps | null = data
    ? {
        data,
        selected: dirty ? null : selected,
        periodId: draft.period_id ? String(draft.period_id) : "",
        asOf: draft.as_of,
        busy,
        reason,
        query,
        command,
        can,
      }
    : null;
  const editor: ForecastEditorProps | null = props ? { ...props, selected, draft, setDraft, editable } : null;
  return (
    <section className="progressFoundation forecastFoundation" aria-label="Forecast & Performance" aria-busy={busy}>
      <CompactModuleHeader
        title="Forecast & Performance"
        eyebrow="USER MODE · CANONICAL PROJECT · O1C"
        tone="user"
        description="Proyección gobernada, desempeño y reportes. Reutiliza Scope, Schedule, Cost, Progress y AWP sin reescribir sus autoridades."
        metrics={[
          { label: "Forecast Versions", value: data?.versions.length ?? 0 },
          { label: "Approved", value: data?.versions.filter((value) => value.status === "APPROVED").length ?? 0 },
        ]}
        actions={
          <button
            type="button"
            disabled={busy}
            onClick={() => void load().catch((caught) => setError(operationalError(caught)))}
          >
            Actualizar Forecast
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
      {!data && !error ? <p role="status">Cargando Forecast canónico…</p> : null}
      {props && editor ? (
        <>
          <p className="progressBoundary">
            Baseline = referencia aprobada · Actual = ocurrido o reconocido · Current = fuente operacional aceptada ·
            Forecast = proyección gobernada. No hay cálculo CPM ni escritura a P6.
          </p>
          {readOnly ? <p className="progressWarning">Workspace archivado · Forecast de solo lectura.</p> : null}
          <div className="progressForm">
            <Select
              label="Forecast Version"
              value={selected ? String(selected.id) : ""}
              options={data!.versions}
              onChange={(value) => void select(value)}
              disabled={busy}
            />
            <Input
              label="Forecast Controls Period ID"
              value={draft.period_id ? String(draft.period_id) : ""}
              onChange={() => undefined}
              disabled
            />
            <Input label="Forecast as-of date" type="date" value={draft.as_of} onChange={() => undefined} disabled />
            <Input label="Motivo Forecast" value={reason} onChange={setReason} disabled={readOnly} required />
          </div>
          {selected ? (
            <Facts
              values={[
                ["Estado", selected.status],
                ["Vigencia", selected.effective_status],
                ["Revisión", selected.revision],
                ["Versión ETag", selected.version],
                ["Preparador", selected.prepared_by],
                ["Aprobador", selected.approved_by],
              ]}
            />
          ) : null}
          {dirty ? (
            <p role="status" className="progressWarning">
              Cambios locales pendientes. Guarde la versión antes de calcular, enviar o consultar resultados de esa
              base.
            </p>
          ) : null}
          <nav className="progressTabs" aria-label="Forecast & Performance submodules">
            {forecastTabs.map((title) => (
              <button key={title} type="button" aria-pressed={tab === title} onClick={() => setTab(title)}>
                {title}
              </button>
            ))}
          </nav>
          {tab === "Forecast Overview" ? (
            <section className="progressPanel" aria-label="Forecast Overview">
              <h3>Forecast Overview</h3>
              <Records
                label="Forecast Versions"
                items={data!.versions}
                columns={[
                  ["code", "Código"],
                  ["name", "Nombre"],
                  ["status", "Estado"],
                  ["period_id", "Período"],
                  ["as_of", "As-of"],
                  ["revision", "Revisión"],
                  ["content_hash", "Hash"],
                ]}
                select={(row) => void select(text(row, "id"))}
              />
              <div className="progressForm">
                <Input
                  label="Forecast Code"
                  value={draft.code}
                  onChange={(value) => setDraft({ ...draft, code: value })}
                  required
                  disabled={!editable || Boolean(selected)}
                />
                <Input
                  label="Forecast Name"
                  value={draft.name}
                  onChange={(value) => setDraft({ ...draft, name: value })}
                  required
                  disabled={!editable}
                />
                <Select
                  label="Forecast Baseline Bundle"
                  value={draft.bundle_id ? String(draft.bundle_id) : ""}
                  onChange={(value) => setDraft({ ...draft, bundle_id: value ? Number(value) : null })}
                  options={data!.baseline_bundles.filter((value) => value.status === "APPROVED")}
                  required
                  disabled={!editable}
                />
                <Select
                  label="Forecast Period"
                  value={draft.period_id ? String(draft.period_id) : ""}
                  onChange={(value) => setDraft({ ...draft, period_id: value ? Number(value) : null })}
                  options={data!.periods}
                  required
                  disabled={!editable}
                />
                <Input
                  label="Forecast As-of"
                  type="date"
                  value={draft.as_of}
                  onChange={(value) => setDraft({ ...draft, as_of: value })}
                  required
                  disabled={!editable}
                />
                <Select
                  label="Forecast Accepted Schedule"
                  value={draft.schedule_version_id ? String(draft.schedule_version_id) : ""}
                  onChange={(value) => setDraft({ ...draft, schedule_version_id: value ? Number(value) : null })}
                  options={data!.schedule_versions.filter((value) =>
                    ["ACCEPTED_CURRENT", "ACCEPTED"].includes(text(value, "status"))
                  )}
                  required
                  disabled={!editable}
                />
                <Input
                  label="Forecast Currency"
                  value={draft.currency}
                  onChange={(value) => setDraft({ ...draft, currency: value })}
                  required
                  disabled={!editable}
                />
                <Select
                  label="Forecast Method"
                  value={draft.method}
                  onChange={(value) => setDraft({ ...draft, method: value })}
                  values={data!.methods ?? forecastMethods}
                  required
                  disabled={!editable}
                />
                <Select
                  label="Forecast Confidence"
                  value={draft.confidence}
                  onChange={(value) => setDraft({ ...draft, confidence: value })}
                  values={["LOW", "MEDIUM", "HIGH"]}
                  required
                  disabled={!editable}
                />
                <Input
                  label="Forecast Confidence rationale"
                  value={draft.confidence_rationale}
                  onChange={(value) => setDraft({ ...draft, confidence_rationale: value })}
                  required
                  disabled={!editable}
                />
                <Input
                  label="Forecast Data completeness"
                  value={draft.data_completeness}
                  onChange={(value) => setDraft({ ...draft, data_completeness: value })}
                  required
                  disabled={!editable}
                />
                <Input
                  label="Forecast Assumption maturity"
                  value={draft.assumption_maturity}
                  onChange={(value) => setDraft({ ...draft, assumption_maturity: value })}
                  required
                  disabled={!editable}
                />
                <Input
                  label="Forecast Evidence reference"
                  value={draft.evidence_ref}
                  onChange={(value) => setDraft({ ...draft, evidence_ref: value })}
                  required
                  disabled={!editable}
                />
              </div>
              <p>
                La confianza es cualitativa. Cada hipótesis y componente mantiene referencias explícitas; Forecast no es
                una nueva línea base ni un Actual.
              </p>
              <Evidence title="Version sources hashes and immutable calculation" value={selected} />
            </section>
          ) : null}
          {tab === "Assumptions" ? <AssumptionsPanel {...editor} /> : null}
          {tab === "ETC / EAC" ? (
            <>
              <ComponentsPanel {...editor} key="cost_items" family="cost_items" />
              <CalculationPanel {...props} kind="cost" />
            </>
          ) : null}
          {tab === "Time Forecast" ? (
            <>
              <ComponentsPanel {...editor} key="time_items" family="time_items" />
              <CalculationPanel {...props} kind="time" />
            </>
          ) : null}
          {tab === "Milestones" ? (
            <>
              <ComponentsPanel {...editor} key="milestones" family="milestones" />
              <CalculationPanel {...props} kind="milestones" />
            </>
          ) : null}
          {tab === "Resource Forecast" ? (
            <>
              <ComponentsPanel {...editor} key="resource_items" family="resource_items" />
              <CalculationPanel {...props} kind="resources" />
            </>
          ) : null}
          {tab === "Variance & Trends" ? (
            <>
              <PerformancePanel {...props} kind="variance" />
              <TrendsPanel {...props} />
            </>
          ) : null}
          {tab === "S-Curves" ? <CurvesPanel {...props} /> : null}
          {tab === "Project Controls Dashboard" ? <PerformancePanel {...props} kind="dashboard" /> : null}
          {tab === "Executive Dashboard" ? <PerformancePanel {...props} kind="executive" /> : null}
          {tab === "4-Week Look-Ahead" ? <LookAheadPanel {...props} /> : null}
          {tab === "Reporting History" ? <ReportsPanel {...props} /> : null}
          <div className="progressActions forecastEditorActions">
            {can("create") ? (
              <button type="button" disabled={busy} onClick={() => void select("")}>
                Nueva versión Forecast
              </button>
            ) : null}
            {editable ? (
              <button
                type="button"
                disabled={!reasonReady || !headerReady || busy}
                onClick={() => void save().catch(() => undefined)}
              >
                {selected ? "Guardar Forecast borrador" : "Crear Forecast DRAFT"}
              </button>
            ) : null}
            {selected?.status === "APPROVED" && can("edit") ? (
              <button
                type="button"
                disabled={busy || !reasonReady}
                onClick={() => void save(true).catch(() => undefined)}
              >
                Crear Forecast sucesor
              </button>
            ) : null}
            {selected?.status === "DRAFT" && can("etc.calculate") ? (
              <button
                type="button"
                disabled={busy || dirty || !reasonReady}
                onClick={() => void calculate().catch(() => undefined)}
              >
                Calcular ETC y EAC
              </button>
            ) : null}
            {selected?.status === "DRAFT" && can("submit") ? (
              <button
                type="button"
                disabled={busy || dirty || !reasonReady}
                onClick={() => void transition("review").catch(() => undefined)}
              >
                Enviar Forecast a revisión
              </button>
            ) : null}
            {selected?.status === "UNDER_REVIEW" && can("approve") ? (
              <button
                type="button"
                disabled={busy || dirty || !reasonReady}
                onClick={() => void transition("approve").catch(() => undefined)}
              >
                Aprobar Forecast
              </button>
            ) : null}
            {selected?.status === "UNDER_REVIEW" && can("review") ? (
              <button
                type="button"
                disabled={busy || dirty || !reasonReady}
                onClick={() => void transition("reject").catch(() => undefined)}
              >
                Rechazar Forecast
              </button>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
