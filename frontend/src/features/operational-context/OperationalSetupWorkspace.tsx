import { useCallback, useEffect, useState, type FormEvent } from "react";
import { RefreshCw } from "lucide-react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { operationalApi } from "./api";
import { ConditionList } from "./ConditionList";
import { operationalError, useOperationalCommandKeys } from "./commands";
import type { BindingResult, OperationalPeriod, OperationalProjectContext, PeriodDraft } from "./types";
import "./operationalContext.css";

const emptyPeriod: PeriodDraft = {
  period_code: "",
  period_start: "",
  period_end: "",
  cutoff_at: "",
  timezone: "",
  schedule_data_date: null,
  reason: "",
  notes: "",
};

export default function OperationalSetupWorkspace({ token, workspaceId }: { token: string; workspaceId: number }) {
  return <OperationalSetupContent key={`${token}:${workspaceId}`} token={token} workspaceId={workspaceId} />;
}

function OperationalSetupContent({ token, workspaceId }: { token: string; workspaceId: number }) {
  const [context, setContext] = useState<OperationalProjectContext | null>(null);
  const [binding, setBinding] = useState<BindingResult | null>(null);
  const [periods, setPeriods] = useState<OperationalPeriod[]>([]);
  const [draft, setDraft] = useState(emptyPeriod);
  const [bindingId, setBindingId] = useState("");
  const [bindingReason, setBindingReason] = useState("");
  const [transitionReason, setTransitionReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const keys = useOperationalCommandKeys();

  const load = useCallback(async () => {
    const [nextContext, nextBinding, nextPeriods] = await Promise.all([
      operationalApi.context(token, workspaceId),
      operationalApi.binding(token, workspaceId),
      operationalApi.periods(token, workspaceId),
    ]);
    setContext(nextContext);
    setBinding(nextBinding);
    setPeriods(nextPeriods.items);
  }, [token, workspaceId]);

  useEffect(() => {
    let active = true;
    Promise.all([
      operationalApi.context(token, workspaceId),
      operationalApi.binding(token, workspaceId),
      operationalApi.periods(token, workspaceId),
    ])
      .then(([nextContext, nextBinding, nextPeriods]) => {
        if (!active) return;
        setContext(nextContext);
        setBinding(nextBinding);
        setPeriods(nextPeriods.items);
        setDraft(emptyPeriod);
      })
      .catch((caught: unknown) => active && setError(operationalError(caught)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [token, workspaceId]);

  async function run(name: string, payload: unknown, task: (key: string) => Promise<unknown>, success: string) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await task(keys.key(name, payload));
      keys.complete(name, payload);
      setMessage(success);
      await load();
    } catch (caught) {
      setError(operationalError(caught));
    } finally {
      setBusy(false);
    }
  }

  function openPeriod(event: FormEvent) {
    event.preventDefault();
    void run(
      "period.open",
      draft,
      (key) => operationalApi.openPeriod(token, workspaceId, draft, key),
      "Periodo abierto."
    );
  }

  function reconcileBinding(event: FormEvent) {
    event.preventDefault();
    if (!context) return;
    const payload = {
      legacy_project_id: bindingId ? Number(bindingId) : null,
      reason: bindingReason,
      source: "CONTROLLED_RECONCILIATION",
      expected_binding_version: context.binding_version,
    };
    void run(
      "binding.manage",
      payload,
      (key) => operationalApi.reconcile(token, workspaceId, payload, key),
      "Vinculación reconciliada explícitamente."
    );
  }

  function transition(period: OperationalPeriod, action: "review" | "close" | "publish" | "reopen") {
    const payload = { id: period.id, version: period.version, action, reason: transitionReason };
    void run(
      `period.${action}`,
      payload,
      (key) => operationalApi.transition(token, workspaceId, period, action, transitionReason, key),
      action === "reopen" ? "Nueva revisión creada; publicación anterior preservada." : "Transición registrada."
    );
  }

  if (loading) return <p role="status">Cargando contexto operacional canónico…</p>;
  if (!context)
    return (
      <section className="operationalFoundation" aria-label="Operational Setup">
        <h2>Operational Setup</h2>
        <p role="alert">{error || "Contexto no disponible para este usuario y Proyecto."}</p>
        <button
          type="button"
          onClick={() => void run("refresh", workspaceId, async () => load(), "Contexto actualizado.")}
        >
          Reintentar
        </button>
      </section>
    );

  const can = (action: string) => context.allowed_actions.includes(action);
  const authorization = context.authorization;

  return (
    <section className="operationalFoundation" aria-label="Operational Setup" aria-busy={busy}>
      <CompactModuleHeader
        eyebrow="USER MODE · PROJECT CONTROLS · O1A"
        title="Operational Setup"
        description="Identidad canónica, autorización, vínculo legado y periodo común de control."
        tone="user"
        metrics={[
          { label: "Workspace", value: context.project_workspace_id },
          {
            label: "Authorization",
            value: authorization.authorized_for_operational_context ? "AUTHORIZED" : "BLOCKED",
          },
          { label: "Period", value: context.current_reporting_period?.status ?? "NOT OPEN" },
        ]}
        actions={
          <button
            disabled={busy}
            onClick={() => void run("refresh", workspaceId, async () => load(), "Contexto actualizado.")}
            type="button"
          >
            <RefreshCw size={14} /> Actualizar
          </button>
        }
      />
      {error ? (
        <p className="operationalNotice error" role="alert">
          {error}
        </p>
      ) : null}
      {message ? (
        <p className="operationalNotice" role="status">
          {message}
        </p>
      ) : null}
      <dl className="operationalFacts" aria-label="Canonical operational Project identity">
        {[
          ["Project", context.name],
          ["Canonical Workspace ID", context.project_workspace_id],
          ["External key", context.project_workspace_external_key],
          ["Record Code", context.project_workspace_record_code],
          ["Governance model", context.governance_model],
          ["Project Type", context.project_type],
          ["Activation", context.activation_state],
          ["Authorization route", context.authorization_route],
          ["Authority source", authorization.authority_source],
          ["Authority reference", authorization.authority_reference ?? "No reference"],
          ["Binding status", context.binding_state],
          ["Legacy Project reference", context.legacy_project_id ?? "Not required / not bound"],
          ["Operational Profile", context.operational_profile?.name ?? "No effective profile"],
          ["Effective policy revision", context.effective_policy_revision ?? "Unresolved"],
        ].map(([label, value]) => (
          <div key={String(label)}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="operationalBoundary">
        ACTIVE no autoriza compromisos. Esta base no aprueba presupuesto, línea base, compras, avance ni forecast.
      </p>
      <div className="operationalConditionGrid">
        <ConditionList title="Blocking conditions" items={context.blocking_conditions} />
        <ConditionList title="Commitment conditions" items={authorization.commitment_conditions} />
        <ConditionList title="Warnings" items={[...context.warnings, ...authorization.warnings]} />
      </div>
      <details className="operationalSection">
        <summary>Vinculación canónica ↔ legado · historial</summary>
        <p>
          Los identificadores de Workspace y Project legado son independientes. No se vincula por igualdad de ID, nombre
          o código.
        </p>
        {can("binding.manage") ? (
          <form className="operationalForm" onSubmit={reconcileBinding}>
            <label>
              Legacy Project ID (opcional para reconciliar relación verificada)
              <input
                type="number"
                min="1"
                step="1"
                value={bindingId}
                onChange={(event) => setBindingId(event.target.value)}
              />
            </label>
            <label>
              Motivo de reconciliación
              <input
                required
                minLength={8}
                value={bindingReason}
                onChange={(event) => setBindingReason(event.target.value)}
              />
            </label>
            <button disabled={busy} type="submit">
              Reconciliar vinculación
            </button>
          </form>
        ) : (
          <p>Solo lectura: no tiene permiso de vinculación/reconciliación.</p>
        )}
        <div className="operationalTableScroll">
          <table>
            <thead>
              <tr>
                <th>Revisión</th>
                <th>Legacy Project</th>
                <th>Estado</th>
                <th>Fuente</th>
                <th>Motivo</th>
              </tr>
            </thead>
            <tbody>
              {binding?.history.map((item) => (
                <tr key={item.id}>
                  <td>{item.revision}</td>
                  <td>{item.legacy_project_id}</td>
                  <td>{item.status}</td>
                  <td>{item.source}</td>
                  <td>{item.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      {can("period.open") ? (
        <details className="operationalSection">
          <summary>Abrir periodo común de control</summary>
          <form className="operationalForm" onSubmit={openPeriod}>
            <label>
              Código del periodo
              <input
                required
                value={draft.period_code}
                onChange={(event) => setDraft({ ...draft, period_code: event.target.value })}
              />
            </label>
            <label>
              Inicio
              <input
                required
                type="date"
                value={draft.period_start}
                onChange={(event) => setDraft({ ...draft, period_start: event.target.value })}
              />
            </label>
            <label>
              Fin
              <input
                required
                type="date"
                value={draft.period_end}
                onChange={(event) => setDraft({ ...draft, period_end: event.target.value })}
              />
            </label>
            <label>
              Cutoff ISO (con zona/offset)
              <input
                required
                placeholder="2026-10-31T18:00:00-05:00"
                value={draft.cutoff_at}
                onChange={(event) => setDraft({ ...draft, cutoff_at: event.target.value })}
              />
            </label>
            <label>
              Zona horaria IANA
              <input
                required
                placeholder="America/Bogota"
                value={draft.timezone}
                onChange={(event) => setDraft({ ...draft, timezone: event.target.value })}
              />
            </label>
            <label>
              P6 Data Date (independiente del cutoff)
              <input
                type="date"
                value={draft.schedule_data_date ?? ""}
                onChange={(event) => setDraft({ ...draft, schedule_data_date: event.target.value || null })}
              />
            </label>
            <label>
              Motivo de apertura
              <input
                required
                minLength={8}
                value={draft.reason}
                onChange={(event) => setDraft({ ...draft, reason: event.target.value })}
              />
            </label>
            <label>
              Notas
              <input value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} />
            </label>
            <button disabled={busy} type="submit">
              Abrir periodo
            </button>
          </form>
        </details>
      ) : (
        <p className="operationalBoundary">
          Solo se muestran comandos autorizados por el backend; este contexto no permite abrir periodos.
        </p>
      )}
      <section className="operationalSection" aria-label="Reporting period history">
        <h3>Reporting period history</h3>
        <p>
          OPEN → REVIEW → CLOSED → PUBLISHED. Publicar emite únicamente metadatos del periodo, no un informe completo de
          Project Controls.
        </p>
        {periods.some((period) => period.allowed_actions.length > 0) ? (
          <label className="operationalReason">
            Motivo de transición / nueva revisión
            <input
              minLength={8}
              value={transitionReason}
              onChange={(event) => setTransitionReason(event.target.value)}
            />
          </label>
        ) : null}
        <div className="operationalTableScroll">
          <table>
            <thead>
              <tr>
                <th>Periodo / revisión</th>
                <th>Fechas</th>
                <th>Cutoff / zona</th>
                <th>P6 Data Date</th>
                <th>Estado</th>
                <th>Política</th>
                <th>Comandos autorizados</th>
              </tr>
            </thead>
            <tbody>
              {periods.map((period) => (
                <tr key={period.id}>
                  <td>
                    {period.period_code} · r{period.revision}
                    {period.reopen_parent_id ? <small>Revisión de #{period.reopen_parent_id}</small> : null}
                  </td>
                  <td>
                    {period.period_start}
                    <small>{period.period_end}</small>
                  </td>
                  <td>
                    {period.cutoff_at}
                    <small>{period.timezone}</small>
                  </td>
                  <td>{period.schedule_data_date ?? "No informado"}</td>
                  <td>
                    <strong>{period.status}</strong>
                  </td>
                  <td>{period.source_configuration_revision}</td>
                  <td>
                    <div className="operationalActions">
                      {(["review", "close", "publish", "reopen"] as const)
                        .filter((action) => period.allowed_actions.includes(`period.${action}`))
                        .map((action) => (
                          <button
                            key={action}
                            disabled={busy || transitionReason.trim().length < 8}
                            onClick={() => transition(period, action)}
                            type="button"
                            aria-label={`${action} ${period.period_code} revision ${period.revision}`}
                          >
                            {action}
                          </button>
                        ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!periods.length ? <p>No hay periodos. No se generan periodos, métricas ni snapshots al consultar.</p> : null}
      </section>
      {context.operational_profile ? (
        <details className="operationalSection">
          <summary>Configuración efectiva (solo lectura)</summary>
          <pre>{JSON.stringify(context.operational_profile.content_json, null, 2)}</pre>
        </details>
      ) : null}
    </section>
  );
}
