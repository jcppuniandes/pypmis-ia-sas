import { useState } from "react";
import { parameters } from "./api";
import { Evidence, Facts, Input, ReasonCodes, Records, Select } from "./Fields";
import { display, object, percentage, rows, text, type ProgressPanelProps } from "./types";
import { useProgressQuery } from "./useProgressQuery";
export function ProjectionPanel({ kind, ...props }: ProgressPanelProps & { kind: "SCHEDULE" | "COST" }) {
  const { result, error } = useProgressQuery(
    props.asOf
      ? `/${kind.toLowerCase()}-progress?${parameters({ as_of: props.asOf, period_id: props.periodId })}`
      : null,
    props.query,
    props.data
  );
  return (
    <section className="progressPanel">
      <h3>{kind === "SCHEDULE" ? "Schedule Progress" : "Cost Progress"}</h3>
      <p className="progressBoundary">
        {kind === "SCHEDULE"
          ? "P6 % Complete ≠ Physical Progress. Se consume únicamente la identidad de Schedule aceptada, sin escribir fechas ni avance físico."
          : "Cost Progress ≠ Physical Progress. Actual, Budget y compromisos conservan su autoridad original; una factura o pago no produce avance físico."}
      </p>
      {!props.asOf ? <p>Seleccione una fecha as-of para consultar las fuentes.</p> : null}
      {error ? (
        <p role="alert" className="progressError">
          {error}
        </p>
      ) : null}
      {result ? (
        <>
          <Facts
            values={[
              ["Autoridad", result.authority],
              [
                "Actualización física automática",
                result.physical_progress_automatic === false ? "NO" : result.physical_progress_automatic,
              ],
            ]}
          />
          <Records
            label={`${kind} separate progress`}
            items={rows(result.items).map((row) => ({ ...object(row.source_snapshot), ...row }))}
            columns={[
              [kind === "SCHEDULE" ? "activity_external_id" : "metric", kind === "SCHEDULE" ? "Activity" : "Métrica"],
              ["progress_value", "Avance %"],
              ["result", "Resultado"],
              ["status", "Estado fuente"],
              [kind === "SCHEDULE" ? "as_of" : "cost_recognition_as_of", "As-of fuente"],
              ["schedule_data_date", "Schedule Data Date"],
            ]}
          />
          <ReasonCodes codes={result.reason_codes} />
          <Evidence title={`Fuentes ${kind} y fechas independientes`} value={result} />
        </>
      ) : null}
    </section>
  );
}
export function AggregationPanel(props: ProgressPanelProps) {
  const [type, setType] = useState("PHYSICAL");
  const [group, setGroup] = useState("PROJECT");
  const { result, error } = useProgressQuery(
    props.asOf
      ? `/aggregation?${parameters({ progress_type: type, group_by: group, period_id: props.periodId, as_of: props.asOf })}`
      : null,
    props.query,
    props.data
  );
  return (
    <section className="progressPanel">
      <h3>Progress Overview</h3>
      <p>
        Agregación determinista de mediciones aprobadas y pesos explícitos. READY y RELEASED no representan un
        porcentaje de avance.
      </p>
      <div className="progressForm">
        <Select
          label="Aggregation Progress Type"
          value={type}
          onChange={setType}
          values={["QUANTITY", "PHYSICAL", "MILESTONE", "WEIGHTED"]}
          required
        />
        <Select
          label="Aggregation Level"
          value={group}
          onChange={setGroup}
          values={[
            "PROJECT",
            "SCOPE",
            "PLAN",
            "PACKAGE",
            "ACTIVITY",
            "CONTROL_ACCOUNT",
            "WBS",
            "AREA",
            "SYSTEM",
            "DISCIPLINE",
          ]}
          required
        />
      </div>
      {!props.asOf ? <p>Seleccione fecha as-of y período para consultar resultados gobernados.</p> : null}
      {error ? (
        <p role="alert" className="progressError">
          {error}
        </p>
      ) : null}
      {result ? (
        <>
          <Records
            label="Approved progress aggregation"
            items={rows(result.items)}
            columns={[
              ["key", "Grupo"],
              ["progress_value", "Avance ponderado %"],
              ["total_weight", "Peso total"],
              ["weighting_basis", "Base de ponderación"],
              ["status", "Resultado"],
              ["input_ids", "Mediciones aprobadas"],
            ]}
          />
          <Facts values={[["Hash del cálculo", result.content_hash]]} />
          <ReasonCodes codes={result.reason_codes} />
          <Evidence title="Entradas y fuentes congeladas del cálculo" value={result.inputs_snapshot ?? result} />
        </>
      ) : null}
    </section>
  );
}
export function EvmPanel(props: ProgressPanelProps & { bundleId: string; setBundleId: (value: string) => void }) {
  const params = parameters({ bundle_id: props.bundleId, period_id: props.periodId, as_of: props.asOf });
  const enabled = Boolean(props.bundleId && props.periodId && props.asOf && props.can("evm.view"));
  const [currency, setCurrency] = useState("");
  const path = `/evm?${params}${currency ? `&currency=${encodeURIComponent(currency)}` : ""}`;
  const { result, error } = useProgressQuery(enabled ? path : null, props.query, props.data);
  const curves = useProgressQuery(enabled ? `/curves?${params}` : null, props.query, props.data);
  return (
    <section className="progressPanel" aria-label="Earned Progress and EVM">
      <h3>Earned Progress</h3>
      <p className="progressBoundary">
        EV procede del avance Physical, Quantity o Milestone aprobado y del valor presupuestado de la baseline
        integrada. No utiliza porcentaje de facturas, pagos ni P6.
      </p>
      <div className="progressForm">
        <Select
          label="EVM Baseline Bundle"
          value={props.bundleId}
          onChange={props.setBundleId}
          options={props.data.baseline_bundles?.filter((row) => row.status === "APPROVED")}
          required
        />
        <Input label="EVM Requested currency" value={currency} onChange={setCurrency} />
      </div>
      {!enabled ? (
        <p>Seleccione bundle aprobado, período y fecha as-of. El permiso progress.evm.view es obligatorio.</p>
      ) : null}
      {error ? (
        <p role="alert" className="progressError">
          {error}
        </p>
      ) : null}
      {result ? (
        <>
          <p className={result.status === "COMPUTABLE" ? "progressNotice" : "progressWarning"} role="status">
            Resultado EVM: {text(result, "status", "NOT_COMPUTABLE")}
          </p>
          <Facts
            values={[
              ["PV", result.pv],
              ["EV", result.ev],
              ["AC", result.ac],
              ["CPI", result.cpi],
              ["SPI", result.spi],
              ["Moneda", result.currency],
            ]}
          />
          <ReasonCodes codes={result.reason_codes} />
          <Records
            label="Approved earned lines"
            items={rows(result.earned_lines)}
            columns={[
              ["budget_line_id", "Línea Budget"],
              ["measurement_id", "Medición"],
              ["progress_type", "Tipo fuente"],
              ["progress_value", "Avance %"],
              ["budgeted_value", "Valor presupuestado"],
              ["earned_value", "Valor ganado"],
              ["currency", "Moneda"],
            ]}
          />
          {props.can("period.publish") ? (
            <button
              type="button"
              disabled={
                props.busy ||
                props.reason.trim().length < 8 ||
                result.status !== "COMPUTABLE" ||
                props.data.periods.find((row) => text(row, "id") === props.periodId)?.status === "PUBLISHED"
              }
              onClick={() =>
                void props
                  .command("/evm/snapshots", {
                    bundle_id: Number(props.bundleId),
                    period_id: Number(props.periodId),
                    as_of: props.asOf,
                    ...(currency ? { currency } : {}),
                    reason: props.reason,
                  })
                  .catch(() => undefined)
              }
            >
              Publicar snapshot EVM
            </button>
          ) : null}
          <Evidence title="Base de control y trazabilidad EVM" value={result.basis ?? result} />
        </>
      ) : null}
      {curves.error ? (
        <p role="alert" className="progressError">
          {curves.error}
        </p>
      ) : null}
      {curves.result ? (
        <>
          <h4>Curvas de control aprobadas</h4>
          <Records
            label="Planned S Curve"
            items={rows(curves.result.planned_curve)}
            columns={[
              ["date", "Fecha"],
              ["period_value", "PV del día"],
              ["cumulative_value", "PV acumulado"],
              ["currency", "Moneda"],
            ]}
          />
          <Records
            label="Approved Actual Progress Curve"
            items={rows(curves.result.approved_progress_curve)}
            columns={[
              ["date", "Fecha"],
              ["progress_type", "Tipo"],
              ["progress_value", "Avance aprobado %"],
              ["measurement_ids", "Mediciones"],
            ]}
          />
          <Records
            label="Earned Curve"
            items={rows(curves.result.earned_curve)}
            columns={[
              ["date", "Fecha"],
              ["status", "Resultado"],
              ["ev", "EV"],
              ["reason_codes", "Motivos"],
            ]}
          />
          <Evidence title="Curvas sin autoridad Forecast" value={curves.result} />
        </>
      ) : null}
    </section>
  );
}
export function OverlayPanel(props: ProgressPanelProps & { bundleId: string; setBundleId: (value: string) => void }) {
  const enabled = Boolean(props.bundleId && props.periodId && props.asOf);
  const { result, error } = useProgressQuery(
    enabled
      ? `/four-d-overlay?${parameters({ bundle_id: props.bundleId, period_id: props.periodId, as_of: props.asOf })}`
      : null,
    props.query,
    props.data
  );
  return (
    <section className="progressPanel">
      <h3>Comparación 4D y avance aprobado</h3>
      <p>
        El estado planificado 4D procede de Schedule; el estado físico procede de Progress aprobado. La comparación no
        cambia IFC, cantidades ni fechas.
      </p>
      <Select
        label="4D Progress Baseline Bundle"
        value={props.bundleId}
        onChange={props.setBundleId}
        options={props.data.baseline_bundles?.filter((row) => row.status === "APPROVED")}
      />
      {error ? (
        <p role="alert" className="progressError">
          {error}
        </p>
      ) : null}
      {result ? (
        <>
          <Facts
            values={[
              ["Autoridad física", object(result.authority).physical_state],
              [
                "Geometría IFC modificada",
                object(result.authority).ifc_mutated === false ? "NO" : object(result.authority).ifc_mutated,
              ],
              [
                "Fechas Schedule modificadas",
                object(result.authority).schedule_mutated === false ? "NO" : object(result.authority).schedule_mutated,
              ],
            ]}
          />
          <Records
            label="Schedule versus approved physical progress"
            items={rows(result.items)}
            columns={[
              ["scope_item_id", "Scope"],
              ["scope_nature", "Nature"],
              ["schedule_state", "Estado Schedule 4D"],
              ["schedule_semantic_state", "Semántica Schedule"],
              ["approved_physical_state", "Estado Progress aprobado"],
              ["schedule_mapping_issues", "Identidad y vigencia"],
            ]}
            format={(key, value) =>
              key === "approved_physical_state"
                ? `${text(object(value), "state")} · ${percentage(object(value).progress_value)}`
                : display(value)
            }
          />
          <ReasonCodes codes={result.reason_codes} />
          <Evidence title="Fuentes de la comparación 4D" value={result} />
        </>
      ) : null}
    </section>
  );
}
export function HistoryPanel({ data }: ProgressPanelProps) {
  return (
    <section className="progressPanel">
      <h3>Progress History</h3>
      <p>
        Revisiones, certificación, revisión independiente, aprobación y linaje de fuentes. Un registro aprobado
        permanece inmutable.
      </p>
      <Records
        label="Progress History"
        items={data.history ?? []}
        columns={[
          ["event_type", "Evento"],
          ["entity_type", "Entidad"],
          ["entity_id", "ID"],
          ["revision", "Revisión"],
          ["created_by", "Actor"],
          ["created_at", "Fecha"],
          ["reason", "Motivo"],
        ]}
      />
      <Evidence title="Estado de las fuentes del Project" value={object(data.context)} />
    </section>
  );
}
