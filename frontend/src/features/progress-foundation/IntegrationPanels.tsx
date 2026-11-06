import { useState, type FormEvent } from "react";
import { Evidence, Facts, Input, ReasonCodes, Records, Select } from "./Fields";
import { useProgressQuery } from "./useProgressQuery";
import { display, effectiveStatus, object, revision, rows, text, type ProgressPanelProps } from "./types";

export function BaselineIntegrationPanel(
  props: ProgressPanelProps & { bundleId: string; setBundleId: (value: string) => void }
) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [scopeId, setScopeId] = useState("");
  const [scheduleId, setScheduleId] = useState("");
  const [costId, setCostId] = useState("");
  const [effectiveDate, setEffectiveDate] = useState("");
  const selected = props.data.baseline_bundles?.find((row) => text(row, "id") === props.bundleId);
  const validation = useProgressQuery(
    selected ? `/baseline-bundles/${selected.id}/validate` : null,
    props.query,
    props.data
  );
  const ready = !props.busy && props.reason.trim().length >= 8;
  async function create(event: FormEvent) {
    event.preventDefault();
    const result = await props.command("/baseline-bundles", {
      code,
      name,
      scope_baseline_id: Number(scopeId),
      schedule_baseline_id: Number(scheduleId),
      cost_baseline_id: Number(costId),
      effective_date: effectiveDate,
      reason: props.reason,
    });
    props.setBundleId(String(result.id));
  }
  function transition(action: string) {
    if (selected)
      void props
        .command(`/baseline-bundles/${selected.id}/transition`, { action, reason: props.reason }, revision(selected))
        .catch(() => undefined);
  }
  return (
    <section className="progressPanel" aria-label="Project Control Baseline Bundle">
      <h3>Baseline Integration</h3>
      <p>
        El bundle referencia las baselines aprobadas de Scope, Schedule y Cost y el perfil publicado de Progress.
        Congela identificadores, hashes, políticas y mapeos, sin copiar sus autoridades.
      </p>
      <Records
        label="Baseline Bundles"
        items={(props.data.baseline_bundles ?? []).map((row) => ({
          ...row,
          effective_status: object(row.validation).effective_state ?? row.effective_status,
        }))}
        columns={[
          ["code", "Código"],
          ["name", "Nombre"],
          ["status", "Estado"],
          ["effective_status", "Vigencia"],
          ["effective_date", "Fecha efectiva"],
          ["revision", "Revisión"],
          ["content_hash", "Hash aprobado"],
        ]}
        select={(row) => {
          props.setBundleId(text(row, "id"));
          setCode(text(row, "code"));
          setName(text(row, "name"));
          setScopeId(text(row, "scope_baseline_id"));
          setScheduleId(text(row, "schedule_baseline_id"));
          setCostId(text(row, "cost_baseline_id"));
          setEffectiveDate(text(row, "effective_date"));
        }}
      />
      {props.can("baseline.prepare") ? (
        <form className="progressForm" onSubmit={(event) => void create(event).catch(() => undefined)}>
          <Input label="Bundle Code" value={code} onChange={setCode} required />
          <Input label="Bundle Name" value={name} onChange={setName} required />
          <Select
            label="Bundle Scope Baseline"
            value={scopeId}
            onChange={setScopeId}
            options={props.data.scope_baselines.filter((row) => Boolean(row.approved_by && row.approved_at))}
            required
          />
          <Select
            label="Bundle Schedule Baseline"
            value={scheduleId}
            onChange={setScheduleId}
            options={props.data.schedule_baselines?.filter((row) => row.status === "APPROVED_BASELINE")}
            required
          />
          <Select
            label="Bundle Cost Baseline"
            value={costId}
            onChange={setCostId}
            options={props.data.cost_baselines?.filter((row) => row.status === "APPROVED")}
            required
          />
          <Input label="Bundle Effective date" type="date" value={effectiveDate} onChange={setEffectiveDate} required />
          <button type="submit" disabled={!ready}>
            Crear Baseline Bundle DRAFT
          </button>
        </form>
      ) : null}
      {selected ? (
        <>
          <Facts
            values={[
              ["Bundle seleccionado", selected.code],
              ["Estado", selected.status],
              ["Vigencia efectiva", object(selected.validation).effective_state ?? effectiveStatus(selected)],
              ["Preparador", selected.prepared_by ?? selected.created_by],
              ["Aprobador", selected.approved_by],
              ["Hash congelado", selected.content_hash],
            ]}
          />
          <div className="progressActions">
            <button disabled={props.busy} onClick={validation.reload}>
              Validar Baseline Bundle
            </button>
            {props.can("baseline.prepare") && selected.status === "DRAFT" ? (
              <button disabled={!ready} onClick={() => transition("review")}>
                Revisar Baseline Bundle
              </button>
            ) : null}
            {props.can("baseline.approve") && selected.status === "UNDER_REVIEW" ? (
              <button disabled={!ready} onClick={() => transition("approve")}>
                Aprobar Baseline Bundle
              </button>
            ) : null}
            {props.can("baseline.prepare") && selected.status === "APPROVED" ? (
              <button
                disabled={!ready || !code || !name || !scopeId || !scheduleId || !costId || !effectiveDate}
                onClick={() =>
                  void props
                    .command(
                      `/baseline-bundles/${selected.id}/successor`,
                      {
                        code,
                        name,
                        scope_baseline_id: Number(scopeId),
                        schedule_baseline_id: Number(scheduleId),
                        cost_baseline_id: Number(costId),
                        effective_date: effectiveDate,
                        reason: props.reason,
                      },
                      revision(selected)
                    )
                    .then((result) => props.setBundleId(String(result.id)))
                    .catch(() => undefined)
                }
              >
                Crear Baseline Bundle sucesor
              </button>
            ) : null}
          </div>
          {validation.error ? (
            <p role="alert" className="progressError">
              {validation.error}
            </p>
          ) : null}
          {validation.result ? (
            <>
              <p
                role="status"
                className={
                  validation.result.status === "VALID" || validation.result.valid === true
                    ? "progressNotice"
                    : "progressWarning"
                }
              >
                Validación del bundle:{" "}
                {text(validation.result, "status", text(validation.result, "result", "REQUIRES_REVIEW"))}
              </p>
              <p>Vigencia: {text(validation.result, "effective_state")}</p>
              <ReasonCodes codes={validation.result.reason_codes ?? validation.result.blockers} />
              <Evidence title="Consistencia y deriva del bundle" value={validation.result} />
            </>
          ) : null}
          <Evidence
            title="Fuentes y hashes preservados del bundle"
            value={selected.source_snapshot_json ?? selected.source_snapshot ?? selected.snapshot_json ?? selected}
          />
        </>
      ) : null}
    </section>
  );
}
export function PeriodReviewPanel(props: ProgressPanelProps & { setPeriodId: (value: string) => void }) {
  const { result, error } = useProgressQuery(
    props.periodId ? `/periods/${props.periodId}/review` : null,
    props.query,
    props.data
  );
  const [notes, setNotes] = useState("");
  const period = Object.keys(object(result?.period)).length
    ? object(result?.period)
    : props.data.periods.find((row) => text(row, "id") === props.periodId);
  const ready = !props.busy && props.reason.trim().length >= 8 && Boolean(period);
  async function transition(action: string) {
    if (!period) return;
    const changed = await props.command(
      `/periods/${props.periodId}/transition`,
      { action, reason: props.reason, notes },
      revision(period)
    );
    if (action === "reopen") {
      const successor = object(changed.period);
      if (successor.id ?? changed.id) props.setPeriodId(String(successor.id ?? changed.id));
    }
  }
  const frozen = object(result?.snapshot);
  return (
    <section className="progressPanel" aria-label="Progress Period Review">
      <h3>Period Review</h3>
      <p>
        OPEN captura; REVIEW congela el conjunto candidato; CLOSED fija lo aprobado; PUBLISHED conserva un snapshot
        inmutable. La fecha de medición, as-of, cutoff y Schedule Data Date no se equiparan.
      </p>
      {!props.periodId ? <p>Seleccione un Project Controls Period existente.</p> : null}
      {error ? (
        <p role="alert" className="progressError">
          {error}
        </p>
      ) : null}
      {period ? (
        <>
          <Facts
            values={[
              ["Período", period.period_code],
              ["Estado", period.status],
              ["Cutoff", period.cutoff_at],
              ["Schedule Data Date", period.schedule_data_date],
              ["Revisión", period.revision],
              ["Hash del conjunto candidato", frozen.content_hash ?? frozen.candidate_hash],
            ]}
          />
          <div className="progressForm">
            <Input label="Period Review notes" value={notes} onChange={setNotes} />
          </div>
          <div className="progressActions">
            {props.can("period.freeze") && period.status === "OPEN" ? (
              <button disabled={!ready} onClick={() => void transition("review").catch(() => undefined)}>
                Congelar Progress para revisión
              </button>
            ) : null}
            {props.can("period.freeze") && period.status === "REVIEW" ? (
              <button disabled={!ready} onClick={() => void transition("close").catch(() => undefined)}>
                Cerrar período Progress
              </button>
            ) : null}
            {props.can("period.publish") && period.status === "CLOSED" ? (
              <button disabled={!ready} onClick={() => void transition("publish").catch(() => undefined)}>
                Publicar período Progress
              </button>
            ) : null}
            {props.can("period.freeze") && ["CLOSED", "PUBLISHED"].includes(String(period.status)) ? (
              <button disabled={!ready} onClick={() => void transition("reopen").catch(() => undefined)}>
                Reabrir mediante período sucesor
              </button>
            ) : null}
          </div>
          <Records
            label="Period Progress candidates"
            items={rows(result?.measurements)}
            columns={[
              ["code", "Medición"],
              ["progress_type", "Tipo"],
              ["status", "Estado"],
              ["progress_value", "Acumulado %"],
              ["period_progress", "Avance del período %"],
              ["measurement_date", "Medición"],
              ["as_of", "As-of"],
            ]}
          />
          <ReasonCodes codes={result?.reason_codes} />
          <Evidence
            title="Conjunto congelado y snapshot publicado"
            value={{
              candidate_snapshot: frozen.candidate_snapshot_json,
              published_snapshot: frozen.published_snapshot_json,
              period_snapshot: result?.snapshot,
            }}
          />
          <p>Estado publicado: {display(result?.status ?? period.status)}.</p>
        </>
      ) : null}
    </section>
  );
}
